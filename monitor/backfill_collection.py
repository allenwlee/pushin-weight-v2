"""Database bookkeeping for explicit historical batches, using the shared runner.

CollectionJob owns instructions, CollectionRun owns an attempt, and scope rows
own committed pages. Post remains the tweet record. Provider calls never run
inside the transaction that fences the existing Post writer and its cursor.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.management.base import CommandError
from django.db.models import Sum

from core.collection_jobs import validate_job
from core.collection_pages import (
    adopt_unprojected_page_receipts,
    append_page_receipt,
    page_receipts,
)
from core.collection_state import (
    StaleClaim,
    checkpoint_scope,
    claim_job,
    fenced_run,
    finish_run,
    import_scope_checkpoints,
    x_scope_ownership,
)
from core.measurement_taxonomy import require
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionScopeRun,
    Post,
    PostEnrichmentState,
)
from monitor.backfill_resources import (
    BackfillBudget,
    BackfillBudgetExhausted,
    BackfillContext,
    bounded_backfill_config,
)
from monitor.run_lock import harvest_writer_lock
from x_monitor.config import load_config
from x_monitor.twitterapi_credentials import (
    TwitterApiCredentialPurpose,
    require_twitterapi_api_key,
)

ADAPTER_VERSION = "x-backfill/v1"
POLICY_ADAPTER_VERSION = "x-backfill/v2"
CALL_IDS = frozenset({"B1", "B2", "B3", "C1", "C2", "C3", "C4"})
BLOCKED_REASONS = frozenset({
    "invalid_primary_window", "invalid_continuation", "clipped_page", "nonprogressing_cursor",
})
GLOBAL_PROVIDER_STATUSES = frozenset({401, 402, 403, 429})


class BackfillProviderSafetyError(CommandError):
    """Sanitized provider admission failure for the campaign controller."""

    def __init__(self, status, *, retry_after_seconds=None):
        self.response_status_code = status
        self.permanent = status != 429
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"collection_provider_{'safety' if self.permanent else 'rate_limited'}_http_{status}")


@contextmanager
def _brand_scope(brands):
    missing = object()
    previous = getattr(settings, "X_MONITOR_CYCLE_BRAND_FILTER", missing)
    settings.X_MONITOR_CYCLE_BRAND_FILTER = ",".join(brands)
    try:
        yield
    finally:
        if previous is missing:
            delattr(settings, "X_MONITOR_CYCLE_BRAND_FILTER")
        else:
            settings.X_MONITOR_CYCLE_BRAND_FILTER = previous


def config_digest(cfg, *, version=ADAPTER_VERSION):
    # This route selects only B/C collection and admits zero model calls.
    # Inactive downstream lanes must not invalidate a saved provider cursor.
    excluded = {"headline_narrative", "synthesis"}
    if version == ADAPTER_VERSION:
        excluded |= {"llm", "targeted_extraction", "discovery"}
    value = cfg.model_dump(mode="json", exclude=excluded)
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def validate_scope(job, cfg):
    validate_job(job)
    require((job.source_id, job.purpose, job.operation, job.mode) ==
            ("x", "content", "x_backfill", "historical"), "historical X job required")
    scope = job.scope
    version = scope.get("adapter")
    require(version in {ADAPTER_VERSION, POLICY_ADAPTER_VERSION}, "unsupported X adapter")
    require(scope.get("credential_purpose") == TwitterApiCredentialPurpose.ON_DEMAND.value,
            "on-demand credential purpose required")
    actual_db = {key.lower(): settings.DATABASES["default"].get(key) for key in ("NAME", "USER")}
    require(scope.get("database") == actual_db, "backfill database identity changed")
    storage = scope.get("response_storage", "archive")
    require(storage in {"archive", "staging"}, "unsupported response storage")
    if storage == "staging":
        from monitor.backfill_staging import validate_staging
        validate_staging(scope)
    require(scope.get("config_digest") == config_digest(cfg, version=version), "backfill configuration changed")
    units = scope.get("units")
    require(isinstance(units, list) and bool(units), "frozen units required")
    require(len(units) <= job.budgets["items"], "scope item allowance exceeded")
    keys = set()
    for unit in units:
        key, owner = unit.get("scope_key"), unit.get("ownership", {})
        require(isinstance(key, str) and 0 < len(key) <= 256 and key not in keys,
                "unique scope key required")
        keys.add(key)
        require(unit.get("scope_kind") == "x_query", "X query scope required")
        require(unit.get("outcome", "pending") in {"pending", "complete", "blocked"}, "invalid checkpoint outcome")
        require(type(unit.get("enumeration_complete", False)) is bool, "completion boolean required")
        require(not unit.get("enumeration_complete") or unit.get("outcome") == "complete",
                "completed checkpoint outcome mismatch")
        lower, upper = owner.get("since_epoch"), owner.get("until_epoch")
        require(type(lower) is int and type(upper) is int and lower < upper,
                "fixed scope bounds required")
        require(scope["since_epoch"] <= lower < upper <= scope["until_epoch"],
                "scope outside campaign bounds")
        admitted = CALL_IDS | {"A", "RARE_EXTRA"} if version == POLICY_ADAPTER_VERSION else CALL_IDS
        require(owner.get("call_id") in admitted, "unsupported historical collection call")
        query = owner.get("query")
        require(isinstance(query, str) and bool(query.strip()), "frozen query required")
        require(not any(token in query.lower() for token in (
            "since:", "until:", "since_time:", "until_time:", "since_id:", "max_id:",
        )), "scope owns query bounds")
        require(len(f"{query} since_time:{lower} until_time:{upper}") <= 512,
                "provider query length exceeded")
    for key in ("prior_api_requests", "maximum_api_requests"):
        require(type(scope.get(key)) is int and scope[key] >= 0, "cumulative request allowance required")
    require(scope["maximum_api_requests"] > 0, "positive cumulative request allowance required")
    if scope.get("deadline"):
        deadline = datetime.fromisoformat(scope["deadline"])
        require(deadline.tzinfo is not None, "aware campaign deadline required")
    if version == POLICY_ADAPTER_VERSION:
        require(scope.get("policy_sha256") == hashlib.sha256(Path("config/harvest_policy.yaml").read_bytes()).hexdigest(),
                "backfill collection policy changed")
        require(isinstance(scope.get("author_scope", {}).get("contexts"), dict), "frozen author roles required")
        require(type(scope.get("maximum_model_requests")) is int and scope["maximum_model_requests"] > 0,
                "positive cumulative model allowance required")
        require(type(scope.get("model_requests_per_run")) is int and scope["model_requests_per_run"] > 0,
                "positive model invocation allowance required")
        planned = {u["ownership"]["call_id"] for u in units}
        require(planned == set(scope.get("required_call_ids", [])), "required collection route omitted")
        from monitor.cycle import plan_calls_for_cycle
        with _brand_scope(scope["brands"]):
            expected = {c.call_id for c in plan_calls_for_cycle(cfg, scheduled_exclusions=True)}
        if "selected_call_ids" in scope:
            selected = scope["selected_call_ids"]
            require(isinstance(selected, list) and bool(selected)
                    and all(isinstance(value, str) for value in selected)
                    and len(selected) == len(set(selected)) and set(selected) <= expected,
                    "invalid collection route selection")
            expected = set(selected)
        require(planned == expected, "required current-policy collection route omitted")
    return scope


def plan_job_definition(*, cfg, since_epoch, until_epoch, brands, requests, model_requests,
                        seconds, maximum_requests, maximum_models, call_ids=None):
    """Freeze current policy and observed role evidence for an arbitrary UTC range."""
    from core.models import TwitterListMembership
    from monitor.cycle import _resolve_x_monitor_list_id, plan_calls_for_cycle
    from monitor.list_membership import resolve_call_a_author_contexts

    require(type(since_epoch) is int and type(until_epoch) is int and since_epoch < until_epoch,
            "fixed historical range required")
    selected = brands or list(cfg.enabled_models)
    require(set(selected) <= set(cfg.enabled_models), "unknown collection brands")
    with _brand_scope(selected):
        calls = plan_calls_for_cycle(cfg, scheduled_exclusions=True)
    require(bool(calls) and any(c.call_id == "A" for c in calls), "required Call A missing")
    require(all(call.call_id in CALL_IDS | {"A", "RARE_EXTRA"} for call in calls),
            "enabled discovery route lacks historical adapter")
    if call_ids is not None:
        require(isinstance(call_ids, list) and bool(call_ids)
                and all(isinstance(value, str) for value in call_ids)
                and len(call_ids) == len(set(call_ids))
                and set(call_ids) <= {call.call_id for call in calls},
                "invalid collection route selection")
        calls = [call for call in calls if call.call_id in call_ids]
    list_id = _resolve_x_monitor_list_id(cfg)
    authors = list(TwitterListMembership.objects.filter(list_id=list_id, active=True).values_list(
        "account__author_id", flat=True))
    contexts, degraded = resolve_call_a_author_contexts(
        list_id=list_id, items=[{"author_id": author} for author in authors],
    )
    frozen = {}
    for author, context in contexts.items():
        value = asdict(context)
        # Call A follows all canonical author roles, independently of B/C keywords.
        value["official_brands"] = list(value["official_brands"])
        value["staff_brands"] = list(value["staff_brands"])
        stamp = value["last_complete_reconciliation_at"]
        value["last_complete_reconciliation_at"] = stamp.isoformat() if stamp else None
        frozen[author] = value
    units = [{"scope_key": call.call_id, "scope_kind": "x_query", "ownership": {
        "call_id": call.call_id, "query": call.query_string,
        "since_epoch": since_epoch, "until_epoch": until_epoch,
    }} for call in calls]
    definition = {
        "version": 1, "schedule": {"kind": "manual", "driver": "manual"},
        "budgets": {"requests": requests, "seconds": seconds, "bytes": 32 * 1024 * 1024, "items": 100000},
        "scope": {
            "adapter": POLICY_ADAPTER_VERSION, "credential_purpose": "on-demand",
            "brands": selected, "since_epoch": since_epoch, "until_epoch": until_epoch,
            "config_digest": config_digest(cfg, version=POLICY_ADAPTER_VERSION),
            "policy_sha256": hashlib.sha256(Path("config/harvest_policy.yaml").read_bytes()).hexdigest(),
            "database": {k.lower(): settings.DATABASES["default"].get(k) for k in ("NAME", "USER")},
            "prior_api_requests": 0, "maximum_api_requests": maximum_requests,
            "model_requests_per_run": model_requests, "maximum_model_requests": maximum_models,
            "required_call_ids": [call.call_id for call in calls], "units": units,
            "author_scope": {"observed_at": datetime.now(UTC).isoformat(), "list_id": list_id,
                             "historical_membership_reconstructed": False,
                             "contexts": frozen, "degraded": degraded},
        },
    }
    if call_ids is not None:
        definition["scope"]["selected_call_ids"] = [call.call_id for call in calls]
    from core.collection_jobs import validate_definition
    validate_definition(source_id="x", purpose="content", operation="x_backfill", mode="historical",
                        contract_id=None, definition=definition)
    return definition


class DurableBudget(BackfillBudget):
    """Conservative paid-request admission survives process death and retries."""

    def __init__(self, claim, job, seconds):
        limits = job.budgets
        super().__init__(max_api_requests=limits["requests"],
                         max_llm_calls=job.scope.get("model_requests_per_run", 0),
                         run_seconds=seconds)
        self.claim = claim

    def claim_llm_request(self, timeout_seconds=0):
        super().claim_llm_request(timeout_seconds)
        with fenced_run(self.claim) as (job, run):
            count = sum(r.report.get("model_requests", 0) for r in job.runs.all())
            if count >= job.scope.get("maximum_model_requests", 0):
                raise BackfillBudgetExhausted("durable model allowance exhausted")
            run.report = {**run.report, "model_requests": run.report.get("model_requests", 0) + 1}
            run.save(update_fields=["report", "updated_at"])

    def record_model_response(self, response):
        super().record_model_response(response)
        usage = getattr(response, "provider_usage", None)
        if usage is None and hasattr(response, "cost_usd"):
            usage = {"cost_usd": str(response.cost_usd), "input_tokens": response.input_tokens,
                     "output_tokens": response.output_tokens, "response_id": response.response_id}
        with fenced_run(self.claim) as (_, run):
            run.report = {**run.report, "model_responses": [
                *run.report.get("model_responses", []),
                {**self.snapshot()["model_responses"][-1], "usage": usage},
            ]}
            run.save(update_fields=["report", "updated_at"])

    def relevance(self, cfg):
        """Reuse exact returned gates; a sent outcome without a reply is unknown."""
        from x_monitor.reattribute import build_relevancy_client_from_env
        from x_monitor.relevancy import build_binary_relevancy_llm_call

        def call(system, user):
            identity = hashlib.sha256(json.dumps([cfg.llm.model_dump(mode="json"), system, user],
                                                sort_keys=True).encode()).hexdigest()
            job = CollectionJob.objects.get(pk=self.claim.job_id)
            for attempt in job.runs.order_by("started_at"):
                receipt = attempt.report.get("staff_relevance", {}).get(identity)
                if receipt:
                    require(receipt.get("status") == "returned", "staff relevance outcome unknown")
                    return receipt["text"]
            client = build_relevancy_client_from_env(cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND")
            require(client is not None, "on-demand staff relevance credential required")
            def before():
                self.claim_llm_request(cfg.harvest.relevancy_timeout_seconds)
                with fenced_run(self.claim) as (_, run):
                    receipts = run.report.get("staff_relevance", {})
                    receipts[identity] = {"status": "sent", "model": cfg.llm.relevancy_model}
                    run.report = {**run.report, "staff_relevance": receipts}
                    run.save(update_fields=["report", "updated_at"])

            def after(response):
                self.record_model_response(response)
                if isinstance(response, BaseException):
                    return
                with fenced_run(self.claim) as (_, run):
                    receipts = run.report["staff_relevance"]
                    receipts[identity] = {**receipts[identity], "status": "returned",
                                          "text": str(getattr(response, "text", response))}
                    run.report = {**run.report, "staff_relevance": receipts}
                    run.save(update_fields=["report", "updated_at"])
            from monitor.cycle import _BoundedClassifierClient
            bounded = _BoundedClassifierClient(client, maximum_calls=1, pause_seconds=0,
                                               before_call=before, after_call=after)
            invoke = build_binary_relevancy_llm_call(
                client=bounded, model=cfg.llm.relevancy_model,
                timeout_seconds=cfg.harvest.relevancy_timeout_seconds,
            )
            return invoke(system, user)
        return call

    def claim_api_request(self, timeout_seconds=0):
        super().claim_api_request(timeout_seconds)
        with fenced_run(self.claim) as (job, run):
            limits, scope = job.budgets, job.scope
            if scope.get("response_storage") == "staging":
                from core.collection_staging import ensure_staging_bytes

                received_bytes = ensure_staging_bytes(run)
            else:
                received_bytes = run.report.get("response_bytes", 0)
            prior = job.runs.aggregate(total=Sum("request_count"))["total"] or 0
            if (scope["prior_api_requests"] + prior >= scope["maximum_api_requests"]
                    or run.request_count >= limits["requests"]
                    or run.selected_count >= limits["items"]
                    or received_bytes >= limits["bytes"]):
                raise BackfillBudgetExhausted("durable backfill allowance exhausted")
            run.request_count += 1
            run.save(update_fields=["request_count", "updated_at"])
        # Transaction has committed before TwitterApiClient starts transport.

    def record_api_response(self, response):
        super().record_api_response(response)
        with fenced_run(self.claim) as (_, run):
            run.selected_count += response["raw_results"]
            run.report = {
                **run.report,
                "response_bytes": run.report.get("response_bytes", 0) + response.get("response_bytes", 0),
            }
            run.save(update_fields=["selected_count", "report", "updated_at"])

    def record_captured_response(self, request, response):
        """Idempotently account an archive, including a capture/commit crash gap.

        The physical request keeps its original run on legacy continuation.
        The current claim fences reconciliation; counters and the accounted-ID
        marker commit together on that original run.
        """
        from core.models import CollectionRun
        if request.request_category == "x_backfill_staging":
            from core.collection_staging import account_staging_response

            with fenced_run(self.claim):
                original = CollectionRun.objects.select_for_update().get(
                    pk=request.scope_run.run_id, job_id=self.claim.job_id,
                )
                recorded = account_staging_response(original, request, response)
            if recorded and original.pk == self.claim.run_id:
                BackfillBudget.record_api_response(self, response)
            return
        with fenced_run(self.claim):
            original = CollectionRun.objects.select_for_update().get(
                pk=request.scope_run.run_id, job_id=self.claim.job_id,
            )
            accounted = list(original.report.get("prefetch_accounted_requests", []))
            identifier = str(request.pk)
            if identifier in accounted:
                return
            original.selected_count += response["raw_results"]
            original.report = {
                **original.report,
                "response_bytes": original.report.get("response_bytes", 0) + response.get("response_bytes", 0),
                "prefetch_accounted_requests": [*accounted, identifier],
            }
            original.save(update_fields=["selected_count", "report", "updated_at"])
        if original.pk == self.claim.run_id:
            BackfillBudget.record_api_response(self, response)


class PageWriteFailed(RuntimeError):
    pass


class PageCheckpoint:
    def __init__(self, claim, scoped, budget, capture=None):
        self.claim, self.scoped, self.budget = claim, scoped, budget
        self.capture = capture
        self.written = False
        with fenced_run(claim):
            adopt_unprojected_page_receipts(scoped)

    def _response(self):
        return self.capture.response if self.capture is not None else self.budget.snapshot()["api_responses"][-1]

    def _checkpoint(self, progress, *, write=None, post_ids=None, extra=None):
        blocked = progress.get("reason") in BLOCKED_REASONS
        received = progress.get("pages_received", 0) > 0
        advanced = received and not blocked
        drained = advanced and progress.get("drained") is True
        envelopes = page_receipts(self.scoped)
        if received:
            envelopes.append({
                "observed_at": datetime.now(UTC).isoformat(),
                "post_ids": post_ids if post_ids is not None else [], "pages_received": progress["pages_received"],
                "collection_drained": drained,
                "reason": progress.get("reason"),
                "raw_count": self._response()["raw_results"],
                "received_post_ids": list(progress.get("received_post_ids", [])),
                "distinct_received_count": len({pid for pid in progress.get("received_post_ids", []) if pid}),
                "exclusions": sorted(progress.get("exclusions", []), key=lambda value: value["appearance"]),
                "relevancy_degraded": list(progress.get("relevancy_degraded", [])),
                **({"prefetch_request_id": str(self.capture.request.pk),
                    "prefetch_request_run_id": str(self.capture.request.scope_run.run_id),
                    "prefetch_replayed": self.capture.replayed} if self.capture is not None else {}),
                **(extra or {}),
            })
        page_write = write
        if received and self.capture is not None and self.capture.request.scope_run.run_id != self.claim.run_id:
            def replay_write(run, scope):
                # This run selects archived items without another HTTP start.
                # Selection and successful storage must commit together, retaining
                # the shared success_count <= selected_count database constraint.
                run.selected_count += self._response()["raw_results"]
                run.save(update_fields=["selected_count", "updated_at"])
                if page_write is not None:
                    return page_write(run, scope)
            write = replay_write
        self.scoped = checkpoint_scope(
            self.claim, scope_key=self.scoped.scope_key, scope_kind="x_query",
            ownership=x_scope_ownership(self.scoped),
            cursor=progress.get("cursor") if advanced else self.scoped.cursor,
            cursor_history=progress.get("seen_cursors", []) if advanced else self.scoped.recorded_cursors,
            outcome="blocked" if blocked else ("complete" if drained else "pending"),
            enumeration_complete=drained, envelopes=envelopes, write=write,
            raw_count=self.scoped.raw_count + (
                self._response()["raw_results"] if received else 0
            ),
        )
        self.written = True

    def persist(self, runner, items, writer):
        result = None
        ids = []

        def write(run, scope):
            nonlocal result
            result = writer(items)
            if result[3]:
                raise PageWriteFailed("page Post persistence failed; cursor retained")
            if any(not item.get("_persisted_post_id") for item in items):
                raise PageWriteFailed("page Post receipt missing; cursor retained")
            # A slow page may outlive the lease while holding its row locks.
            with fenced_run(self.claim):
                pass
            ids.extend(str(item["_persisted_post_id"]) for item in items if item.get("_persisted_post_id"))
            from core.provider_batches import record_post_membership
            record_post_membership(run, scope, ids)
            from core.models import CollectionObservation
            from monitor.backfill_enrichment import reopen_incomplete_successes
            reopen_incomplete_successes(
                run.job, CollectionObservation.objects.filter(run=run, post_id__in=ids),
            )
            # A successful count is a stored result, including duplicate updates.
            run.success_count += result[0] + result[1]
            run.save(update_fields=["success_count", "updated_at"])

        try:
            self._checkpoint(runner._backfill_fetch_receipt, write=write, post_ids=ids)
        except Exception:
            for item in items:
                for key in ("_db_inserted", "_persisted_post_id", "_db_committed_at"):
                    item.pop(key, None)
            raise
        # The existing per-item savepoints are enclosed by the actual page commit.
        committed_at = runner._wall_now().isoformat()
        for item in items:
            if item.get("_persisted_post_id"):
                item["_db_committed_at"] = committed_at
        return result

    def empty(self, stats):
        if not self.written:
            calls = stats.get("calls", [])
            if len(calls) == 1 and calls[0].get("n_persist_failed") == 0:
                progress = calls[0].get("backfill_progress", {})
                if progress.get("pages_received"):
                    self._checkpoint(progress)

    def failed(self, progress):
        """A returned HTTP error is an attempt receipt, never a drained page."""
        self.scoped = checkpoint_scope(
            self.claim, scope_key=self.scoped.scope_key, scope_kind="x_query",
            ownership=x_scope_ownership(self.scoped), cursor=self.scoped.cursor,
            cursor_history=self.scoped.recorded_cursors, outcome=self.scoped.outcome,
            enumeration_complete=False, raw_count=self.scoped.raw_count,
            envelopes=[*page_receipts(self.scoped), {
                "observed_at": datetime.now(UTC).isoformat(), "pages_received": 0,
                "post_ids": [], "collection_drained": False,
                "reason": progress.get("reason"), "response_status_code": progress["response_status_code"],
                "retry_after_seconds": progress.get("retry_after_seconds"),
            }],
        )

    def persist_rare(self, runner, call, items):
        """Raw rare evidence commits with the cursor, before any Jev request."""
        from core.models import (
            RareTypeSearchDailyBudget,
            RareTypeSearchRun,
            SearchQuery,
        )
        from core.rare_type_search import persist_hit_batch
        now = datetime.now(UTC)
        owner = x_scope_ownership(self.scoped)
        lane = f"bf:{self.claim.job_id}:{hashlib.sha256(self.scoped.scope_key.encode()).hexdigest()[:8]}"
        hit_ids = []

        def write(run, scope):
            query_hash = hashlib.sha256(owner["query"].encode()).hexdigest()
            source, _ = SearchQuery.objects.get_or_create(
                query_id=f"historical-rare:{query_hash}", defaults={"keywords": {"query": owner["query"]}},
            )
            daily, _ = RareTypeSearchDailyBudget.objects.get_or_create(lane=lane, usage_date=now.date())
            raw_count = self._response()["raw_results"]
            lower = datetime.fromtimestamp(owner["since_epoch"], UTC)
            upper = datetime.fromtimestamp(owner["until_epoch"], UTC)
            rare = RareTypeSearchRun.objects.create(
                lane=lane, slot_start=now, daily_budget=daily, source_query=source,
                query_string=owner["query"], query_hash=query_hash,
                query_version=call.query_pack_version or "unknown", window_start=lower, window_end=upper,
                attempted_start=lower, attempted_end=upper,
                status="returned" if raw_count else "empty", request_count=1,
                raw_result_count=raw_count, normalized_result_count=len(items),
                reserved_credits=0, estimated_credits=max(1, raw_count) * 15,
                environment="historical", release_sha=os.environ.get("RENDER_GIT_COMMIT", "unknown")[:64],
                reserved_at=now, dispatched_at=now, returned_at=now, finished_at=now,
                truncated=not runner._backfill_fetch_receipt.get("drained", False),
            )
            hits = persist_hit_batch(rare.pk, items, now=now, raw_count=raw_count)
            hit_ids.extend(hit.pk for hit in hits)
            from core.models import CollectionScopeRareHit

            CollectionScopeRareHit.objects.bulk_create(
                [CollectionScopeRareHit(scope_run=scope, rare_hit=hit) for hit in hits],
                ignore_conflicts=True,
            )
        self._checkpoint(runner._backfill_fetch_receipt, write=write, extra={
            "rare_hit_ids": hit_ids,
            "inbox_post_ids": [str(item.get("id") or item.get("tweet_id")) for item in items],
        })
        return [], 0, 0, 0, 0, 0, []


def _rare_scope_memberships(rows, job_id):
    """Read this job's inbox across continuation runs by frozen scope key."""
    from core.models import CollectionScopeRareHit

    owners = {row.scope_key: set() for row in rows}
    for scope_key, hit_id in CollectionScopeRareHit.objects.filter(
        scope_run__run__job_id=job_id, scope_run__scope_kind="x_query",
        scope_run__scope_key__in=owners,
    ).values_list("scope_run__scope_key", "rare_hit_id"):
        owners[scope_key].add(hit_id)
    return owners


def _drain_historical_rare(claim, job, cfg, budget):
    """Process only this job's saved inbox; never reserve a scheduled slot."""
    from core.models import RareTypeSearchHit
    from core.provider_batches import record_post_membership
    from monitor.cycle import CycleRunner, _build_brand_index, _load_brand_search_terms
    from x_monitor.jev_decisions import build_jev_decision_gate

    rows = list(CollectionScopeRun.objects.filter(run_id=claim.run_id, scope_kind="x_query"))
    owned_hits = _rare_scope_memberships(rows, job.pk)
    hit_ids = set().union(*owned_hits.values()) if owned_hits else set()
    if not hit_ids:
        return
    gate = build_jev_decision_gate(
        cfg, environment="normal", lane=f"bf:{job.pk}",
        before_call=lambda: budget.claim_llm_request(cfg.discovery.rare_types.jev.request_timeout_seconds),
        after_call=budget.record_model_response,
        retry_unknown=False,
    )
    if gate is None:
        return
    for position, hit_id in enumerate(sorted(hit_ids)):
        # Five sequential requests fit the shared 60-second allocation even
        # at the ten-second transport timeout. This is a job allocation, with
        # cumulative admission on CollectionRun, never a live scheduler slot.
        gate.lane = f"bf:{job.pk}:{str(claim.run_id)[:8]}:{position // 5}"
        hit = RareTypeSearchHit.objects.get(pk=hit_id)
        if hit.post_id or hit.gate_state in {"junk", "review_needed", "kept"}:
            continue
        if not budget.can_start(cfg.discovery.rare_types.jev.request_timeout_seconds):
            break
        with fenced_run(claim):
            pass
        gate.process_hit(hit_id, owner=f"backfill:{claim.run_id}")
    context = BackfillContext(budget=budget, enrichment_limit=0)
    runner = CycleRunner(cfg=cfg, cycle_kind="backfill", _backfill_context=context)
    with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.rare") as lease:
        if not lease.acquired:
            # Preserve the reason for incomplete ingestion so the campaign can
            # wait for live harvesting, rather than treating it as a failed gate.
            return "waiting_for_live_writer"
        with fenced_run(claim) as (_, run):
            # Bound each ingestion slice while allowing an entire historical
            # inbox to progress; this never visits the global pending queue.
            while True:
                result = runner._ingest_kept_rare_type_hits(
                    run_id=str(claim.run_id), hit_ids=hit_ids,
                    index=_build_brand_index(job.scope["brands"]),
                    search_terms=_load_brand_search_terms(),
                )
                if result["selected"] == 0 or result["failed"]:
                    break
            for row in rows:
                owned = owned_hits[row.scope_key]
                ids = sorted(set(RareTypeSearchHit.objects.filter(pk__in=owned, post_id__isnull=False)
                                 .values_list("post_id", flat=True)))
                if ids:
                    record_post_membership(run, row, ids)
                    from monitor.backfill_enrichment import reopen_incomplete_successes
                    reopen_incomplete_successes(job, CollectionObservation.objects.filter(run=run, post_id__in=ids))
                    adopt_unprojected_page_receipts(row)
                    append_page_receipt(row, {"post_ids": ids, "rare_gate_publication": True})
                    row.envelopes = page_receipts(row)
                    row.save(update_fields=["envelopes"])
            with fenced_run(claim):
                pass


def _report(job, run_id):
    rows = list(CollectionScopeRun.objects.filter(run_id=run_id, scope_kind="x_query"))
    members = set(CollectionObservation.objects.filter(
        run__job=job, source_subject_kind="post",
    ).values_list("post_id", flat=True))
    ids = sorted(str(pid) for pid in members)
    require(len(rows) == len(job.scope["units"]), "incomplete scope ledger")
    require(Post.objects.filter(pk__in=ids).count() == len(ids), "checkpoint Posts missing")
    complete = PostEnrichmentState.objects.filter(
        post_id__in=ids, translation_status="succeeded", classification_status="succeeded",
    ).count()
    requests = job.runs.aggregate(total=Sum("request_count"))["total"] or 0
    report = {
        "job_id": str(job.pk), "run_id": str(run_id),
        "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND.value,
        "collection_drained": bool(rows) and all(row.enumeration_complete for row in rows),
        "scopes_complete": sum(row.enumeration_complete for row in rows), "scopes_total": len(rows),
        "recovered_post_ids": ids, "enrichment_complete_count": complete,
        "enrichment_pending_count": len(ids) - complete,
        "cumulative_api_requests": job.scope["prior_api_requests"] + requests,
        "provider_billing": None,
    }
    # Membership writes and Post persistence commit in the same page transaction.
    # Continuations retain their observations on the earlier owning run.
    report["post_membership"] = {"version": 1, "distinct_posts": len(ids)}
    if job.scope.get("adapter") == POLICY_ADAPTER_VERSION:
        from collections import Counter

        from core.models import RareTypeSearchHit

        owned_hits = _rare_scope_memberships(rows, job.pk)
        hit_ids = set().union(*owned_hits.values()) if owned_hits else set()
        hits = list(RareTypeSearchHit.objects.filter(pk__in=hit_ids)
                    .values("pk", "gate_state", "post_id"))
        missing = sorted(hit_ids - {h["pk"] for h in hits})
        review = sorted(h["pk"] for h in hits if h["gate_state"] == "review_needed")
        unfinished = sorted(h["pk"] for h in hits
                            if h["gate_state"] not in {"junk", "review_needed"}
                            and not (h["gate_state"] == "kept" and h["post_id"] is not None))
        # Review is a completed adjudication with uncertainty, not unfinished
        # provider work. Retain its identity; success never asserts full recall.
        report.update({
            "rare_gate_pending": len(unfinished) + len(missing),
            "rare_gate_pending_hit_ids": unfinished,
            "rare_gate_missing_hit_ids": missing,
            "rare_gate_review_needed": len(review),
            "rare_gate_review_hit_ids": review,
            "rare_gate_state_counts": dict(Counter(h["gate_state"] for h in hits)),
        })
    return report


def execute_job(job_id, *, read_only=False, retry_blocked=False, collection_options=None):
    from monitor.backfill_prefetch import Prefetcher, PrefetchOptions
    from monitor.cycle import CycleRunner

    options = PrefetchOptions.parse(collection_options)

    job = CollectionJob.objects.get(pk=job_id)
    from core.models import CollectionRequest
    direct_staging = job.scope.get("response_storage") == "staging"
    use_prefetch = direct_staging or collection_options is not None or CollectionRequest.objects.filter(
        attempt__run__job=job, request_category="x_backfill_prefetch",
    ).exists()
    current_policy = job.scope.get("adapter") == POLICY_ADAPTER_VERSION
    raw_cfg = load_config(Path("config.yaml"))
    cfg = bounded_backfill_config(raw_cfg, enrichment_limit=1, collection_policy=current_policy)
    scope = validate_scope(job, raw_cfg if current_policy else cfg)
    if read_only or job.state == "completed":
        return {"job_id": str(job.pk), "state": job.state,
                "report": job.last_attempt.report if job.last_attempt_id else None}
    if job.next_retry_at and job.next_retry_at > datetime.now(UTC):
        remaining = max(1, int((job.next_retry_at - datetime.now(UTC)).total_seconds()) + 1)
        raise BackfillProviderSafetyError(429, retry_after_seconds=min(300, remaining))
    # Resolve this exact key before claiming or sending any HTTP request.
    require_twitterapi_api_key(TwitterApiCredentialPurpose.ON_DEMAND)
    seconds = job.budgets["seconds"]
    if scope.get("deadline") and any(not unit.get("enumeration_complete") for unit in scope["units"]):
        seconds = min(seconds, (datetime.fromisoformat(scope["deadline"]) - datetime.now(UTC)).total_seconds())
    require(seconds > 0, "campaign deadline exhausted")
    # A legacy continuation copies its saved scopes when claimed. Yield before
    # creating that attempt, rather than multiplying checkpoints while live
    # harvesting owns the writer. Per-page locking below still handles a live
    # arrival between this nonblocking admission probe and the next page.
    with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.job") as lease:
        if not lease.acquired:
            return {"job_id": str(job.pk), "state": "waiting_for_live_writer"}
    claim = claim_job(job.pk, invocation_id=str(uuid4()), manual_authorized=True,
                      continue_from=job.last_attempt_id)
    budget = DurableBudget(claim, job, seconds)
    error = None
    deferred_scopes = set()
    scope_errors = []
    global_failure = None
    deferred_state = None
    retry_at = None
    prefetch = None
    pages = None
    try:
        if not CollectionScopeRun.objects.filter(run_id=claim.run_id, scope_kind="x_query").exists():
            import_scope_checkpoints(
                claim, definition_sha256=job.definition_sha256,
                scopes=scope["units"], provenance=scope.get("provenance", {"format": ADAPTER_VERSION}),
            )
        if retry_blocked:
            with fenced_run(claim):
                CollectionScopeRun.objects.filter(run_id=claim.run_id, scope_kind="x_query", outcome="blocked").update(outcome="pending")
        def serial_scopes():
            for _ in range(job.budgets["requests"]):
                requests = job.runs.aggregate(total=Sum("request_count"))["total"] or 0
                if scope["prior_api_requests"] + requests >= scope["maximum_api_requests"]:
                    return
                scoped = CollectionScopeRun.objects.filter(
                    run_id=claim.run_id, scope_kind="x_query", enumeration_complete=False,
                ).exclude(outcome="blocked").exclude(scope_key__in=deferred_scopes).select_related(
                    "run", "job_target__search_query"
                ).order_by("id").first()
                if scoped is None or not budget.can_start(38):
                    return
                yield scoped, None

        if use_prefetch:
            if direct_staging:
                from monitor.backfill_staging import StagingPrefetcher
                prefetch = StagingPrefetcher(claim, job, budget, options)
            else:
                prefetch = Prefetcher(claim, job, budget, options)
            pages = prefetch.pages(deferred_scopes)
        else:
            pages = serial_scopes()
        for scoped, capture in pages:
            with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.job") as lease:
                if not lease.acquired:
                    break
                owner = x_scope_ownership(scoped)
                settings.X_MONITOR_CYCLE_SINCE_TIME = owner["since_epoch"]
                settings.X_MONITOR_CYCLE_UNTIL_TIME = owner["until_epoch"]
                settings.X_MONITOR_CYCLE_LIMIT_PER_CALL = 20
                settings.X_MONITOR_CYCLE_MAX_PAGES_PER_CALL = 1
                settings.X_MONITOR_CYCLE_BRAND_FILTER = ",".join(scope["brands"]) or None
                page = PageCheckpoint(claim, scoped, budget, capture=capture)
                context = BackfillContext(
                    budget=budget, cursor=scoped.cursor, seen_cursors=scoped.recorded_cursors,
                    enrichment_limit=0, query_override=owner["query"], page_writer=page.persist,
                    match_scheduled_policy=current_policy,
                    author_contexts=scope.get("author_scope", {}).get("contexts") if current_policy else None,
                    rare_page_writer=page.persist_rare if current_policy else None,
                    captured_pages=capture.pages() if capture is not None else None,
                )
                try:
                    stats = CycleRunner(cfg=cfg, cycle_kind="backfill", dry_run=False,
                                        _backfill_call_ids=[owner["call_id"]], _backfill_context=context,
                                        _relevancy_llm_call=budget.relevance(cfg) if current_policy else None,
                                        _max_llm_calls=budget.remaining_llm_calls).run()
                except (StaleClaim, BackfillBudgetExhausted):
                    raise
                except Exception as exc:  # noqa: BLE001 - retain this scope and continue independent queries
                    error = error or exc
                    deferred_scopes.add(scoped.scope_key)
                    scope_errors.append({"scope_key": scoped.scope_key, "error": type(exc).__name__})
                    continue
                page.empty(stats)
                progress = next((call.get("backfill_progress", {}) for call in stats.get("calls", [])
                                 if call.get("backfill_progress", {}).get("response_status_code") in GLOBAL_PROVIDER_STATUSES), None)
                if progress is not None:
                    http_status = progress["response_status_code"]
                    delay = progress.get("retry_after_seconds", 30) if http_status == 429 else None
                    error = BackfillProviderSafetyError(http_status, retry_after_seconds=delay)
                    global_failure = {"scope_key": scoped.scope_key, "response_status_code": http_status,
                                      "permanent": error.permanent, "retry_after_seconds": delay}
                    page.failed(progress)
                    scope_errors.append(global_failure)
                    if delay is not None:
                        retry_at = datetime.now(UTC) + timedelta(seconds=delay)
                    break
                if stats.get("status") in {"aborted", "degraded"} or any(
                    call.get("status") in {"error", "persist_incomplete", "length_cap_exceeded"}
                    for call in stats.get("calls", [])
                ):
                    error = error or CommandError("shared backfill runner failed; committed pages retained")
                    deferred_scopes.add(scoped.scope_key)
                    scope_errors.append({"scope_key": scoped.scope_key, "errors": stats.get("errors", [])})
                    if any("TwitterApiAuthError" in str(item) for item in stats.get("errors", [])):
                        break
        if current_policy and not CollectionScopeRun.objects.filter(
            run_id=claim.run_id, scope_kind="x_query", enumeration_complete=False,
        ).exists():
            deferred_state = _drain_historical_rare(claim, job, cfg, budget)
    except StaleClaim:
        # The owner paused or replaced this worker. It cannot publish a finish.
        raise
    except Exception as exc:  # noqa: BLE001 - retain a terminal failure receipt before exit
        error = exc
        if isinstance(exc, BackfillProviderSafetyError):
            global_failure = {"response_status_code": exc.response_status_code,
                              "permanent": exc.permanent, "retry_after_seconds": exc.retry_after_seconds}
            if exc.retry_after_seconds is not None:
                retry_at = datetime.now(UTC) + timedelta(seconds=exc.retry_after_seconds)
    finally:
        if pages is not None:
            pages.close()
    try:
        report = _report(job, claim.run_id)
    except ValueError as exc:
        error = error or exc
        report = {"collection_drained": False, "reconciliation_error": str(exc)}
    report.update({"usage": budget.snapshot(), "revision": os.environ.get("RENDER_GIT_COMMIT"),
                   "scope_errors": scope_errors})
    if prefetch is not None:
        report["prefetch"] = prefetch.metrics
        if error is None and getattr(prefetch, "retry_at", None):
            retry_at = prefetch.retry_at
            report["state"] = "waiting_for_provider"
            report["retry_at"] = retry_at.isoformat()
    if global_failure is not None:
        report["global_failure"] = global_failure
    if deferred_state and error is None:
        report["state"] = deferred_state
    pending = report.get("rare_gate_pending", 0)
    # Another writer may have published the rare Posts since we yielded. Even
    # with zero pending hits, our memberships/checkpoints still need a retry.
    status = "failed" if error else (
        "success" if report["collection_drained"] and not pending and not deferred_state else "partial"
    )
    finish_run(claim, status=status, report=report, retry_at=retry_at,
               error_code=type(error).__name__ if error else None)
    if error:
        if isinstance(error, BackfillProviderSafetyError):
            raise error
        raise CommandError(f"Backfill job failed ({type(error).__name__}); database checkpoint retained") from error
    return report


def benchmark_page(job_id):
    """Measure identical already-stored captured tweets without provider calls.

    This operator probe compares database location using duplicate updates. It
    never fabricates posts or claims to measure the cost of new inserts.
    """
    from monitor.cycle import (
        CycleRunner,
        _build_brand_index,
        _item_created_epoch,
        _load_brand_search_terms,
        _matches_any_term,
    )
    from x_monitor.apify import _normalize_tweet

    cfg = bounded_backfill_config(load_config(Path("config.yaml")), enrichment_limit=1)
    job = CollectionJob.objects.get(pk=job_id)
    scope = validate_scope(job, cfg)
    require(job.state == "completed", "storage probe requires completed collection")
    probe = scope["storage_probe"]
    require_twitterapi_api_key(TwitterApiCredentialPurpose.ON_DEMAND)
    raw = probe["body"]["tweets"]
    require(isinstance(raw, list) and 0 < len(raw) <= 20, "one captured page required")
    require(hashlib.sha256(json.dumps(probe["body"], sort_keys=True).encode()).hexdigest()
            == probe["body_sha256"], "captured page identity changed")
    owner = probe["ownership"]
    require(any(unit["ownership"] == owner for unit in scope["units"]), "probe ownership mismatch")
    items = [_normalize_tweet(item) for item in raw]
    require(all(owner["since_epoch"] <= (_item_created_epoch(item) or 0) < owner["until_epoch"]
                for item in items), "probe outside frozen window")
    runner = CycleRunner(cfg=cfg, cycle_kind="backfill", dry_run=False,
                         _backfill_context=BackfillContext(
                             budget=BackfillBudget(max_api_requests=1, max_llm_calls=0, run_seconds=120),
                             enrichment_limit=0,
                         ), _max_llm_calls=0)
    started = time.monotonic()
    runner._attribute_items(items, _build_brand_index(scope["brands"]), _load_brand_search_terms())
    kept = [item for item in items if not item.get("_unattributed")]
    terms = [term.lower() for term in probe.get("not_include", [])]
    if terms:
        kept = [item for item in kept if not _matches_any_term(
            item.get("text") or "", item.get("quoted_text") or "", terms,
        )]
    ids = [str(item["id"]) for item in kept]
    require(bool(ids) and Post.objects.filter(pk__in=ids).count() == len(set(ids)),
            "probe only updates already-stored posts")
    with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.storage_probe") as lease:
        require(lease.acquired, "storage probe writer is busy")
        write_started = time.monotonic()
        result = runner._persist_items(kept)
        write_seconds = time.monotonic() - write_started
    require(result[0] == 0 and result[3] == 0, "storage probe persistence failed")
    return {"kind": "captured_page_duplicate_updates", "provider_requests": 0, "model_requests": 0,
            "body_sha256": probe["body_sha256"], "updated_posts": result[1],
            "storage_seconds": write_seconds, "attribution_and_storage_seconds": time.monotonic() - started,
            "revision": os.environ.get("RENDER_GIT_COMMIT"), "job_id": str(job.pk)}
