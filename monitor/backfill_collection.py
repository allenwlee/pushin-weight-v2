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
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.management.base import CommandError
from django.db.models import Sum

from core.collection_jobs import validate_job
from core.collection_state import (
    StaleClaim,
    checkpoint_scope,
    claim_job,
    fenced_run,
    finish_run,
    import_scope_checkpoints,
)
from core.measurement_taxonomy import require
from core.models import CollectionJob, CollectionScopeRun, Post, PostEnrichmentState
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
CALL_IDS = frozenset({"B1", "B2", "B3", "C1", "C2", "C3"})
BLOCKED_REASONS = frozenset({
    "invalid_primary_window", "invalid_continuation", "clipped_page", "nonprogressing_cursor",
})


def config_digest(cfg):
    # This route selects only B/C collection and admits zero model calls.
    # Inactive downstream lanes must not invalidate a saved provider cursor.
    value = cfg.model_dump(mode="json", exclude={
        "headline_narrative", "synthesis", "llm", "targeted_extraction", "discovery",
    })
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def validate_scope(job, cfg):
    validate_job(job)
    require((job.source_id, job.purpose, job.operation, job.mode) ==
            ("x", "content", "x_backfill", "historical"), "historical X job required")
    scope = job.definition["scope"]
    require(scope.get("adapter") == ADAPTER_VERSION, "unsupported X adapter")
    require(scope.get("credential_purpose") == TwitterApiCredentialPurpose.ON_DEMAND.value,
            "on-demand credential purpose required")
    actual_db = {key.lower(): settings.DATABASES["default"].get(key) for key in ("NAME", "USER")}
    require(scope.get("database") == actual_db, "backfill database identity changed")
    require(scope.get("config_digest") == config_digest(cfg), "backfill configuration changed")
    units = scope.get("units")
    require(isinstance(units, list) and bool(units), "frozen units required")
    require(len(units) <= job.definition["budgets"]["items"], "scope item allowance exceeded")
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
        require(owner.get("call_id") in CALL_IDS, "only historical B/C calls supported")
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
    return scope


class DurableBudget(BackfillBudget):
    """Conservative paid-request admission survives process death and retries."""

    def __init__(self, claim, job, seconds):
        limits = job.definition["budgets"]
        super().__init__(max_api_requests=limits["requests"], max_llm_calls=0, run_seconds=seconds)
        self.claim = claim

    def claim_api_request(self, timeout_seconds=0):
        super().claim_api_request(timeout_seconds)
        with fenced_run(self.claim) as (job, run):
            limits, scope = job.definition["budgets"], job.definition["scope"]
            prior = job.runs.aggregate(total=Sum("request_count"))["total"] or 0
            if (scope["prior_api_requests"] + prior >= scope["maximum_api_requests"]
                    or run.request_count >= limits["requests"]
                    or run.selected_count >= limits["items"]
                    or run.report.get("response_bytes", 0) >= limits["bytes"]):
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


class PageWriteFailed(RuntimeError):
    pass


class PageCheckpoint:
    def __init__(self, claim, scoped, budget):
        self.claim, self.scoped, self.budget = claim, scoped, budget
        self.written = False

    def _checkpoint(self, progress, *, write=None, post_ids=None):
        blocked = progress.get("reason") in BLOCKED_REASONS
        received = progress.get("pages_received", 0) > 0
        advanced = received and not blocked
        drained = advanced and progress.get("drained") is True
        envelopes = list(self.scoped.envelopes)
        if received:
            envelopes.append({
                "observed_at": datetime.now(UTC).isoformat(),
                "post_ids": post_ids if post_ids is not None else [], "pages_received": progress["pages_received"],
                "collection_drained": drained,
                "reason": progress.get("reason"),
            })
        self.scoped = checkpoint_scope(
            self.claim, scope_key=self.scoped.scope_key, scope_kind="x_query",
            ownership=self.scoped.ownership,
            cursor=progress.get("cursor") if advanced else self.scoped.cursor,
            cursor_history=progress.get("seen_cursors", []) if advanced else self.scoped.cursor_history,
            outcome="blocked" if blocked else ("complete" if drained else "pending"),
            enumeration_complete=drained, envelopes=envelopes, write=write,
            raw_count=self.scoped.raw_count + (
                self.budget.snapshot()["api_responses"][-1]["raw_results"] if received else 0
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
            # A slow page may outlive the lease while holding its row locks.
            with fenced_run(self.claim):
                pass
            ids.extend(str(item["_persisted_post_id"]) for item in items if item.get("_persisted_post_id"))
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


def _report(job, run_id):
    rows = list(CollectionScopeRun.objects.filter(run_id=run_id, scope_kind="x_query"))
    ids = sorted({str(pid) for row in rows for envelope in row.envelopes
                  for pid in envelope.get("post_ids", [])})
    require(len(rows) == len(job.definition["scope"]["units"]), "incomplete scope ledger")
    require(Post.objects.filter(pk__in=ids).count() == len(ids), "checkpoint Posts missing")
    complete = PostEnrichmentState.objects.filter(
        post_id__in=ids, translation_status="succeeded", classification_status="succeeded",
    ).count()
    requests = job.runs.aggregate(total=Sum("request_count"))["total"] or 0
    return {
        "job_id": str(job.pk), "run_id": str(run_id),
        "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND.value,
        "collection_drained": bool(rows) and all(row.enumeration_complete for row in rows),
        "scopes_complete": sum(row.enumeration_complete for row in rows), "scopes_total": len(rows),
        "recovered_post_ids": ids, "enrichment_complete_count": complete,
        "enrichment_pending_count": len(ids) - complete,
        "cumulative_api_requests": job.definition["scope"]["prior_api_requests"] + requests,
        "provider_billing": None,
    }


def execute_job(job_id, *, read_only=False):
    from monitor.cycle import CycleRunner

    cfg = bounded_backfill_config(load_config(Path("config.yaml")), enrichment_limit=1)
    job = CollectionJob.objects.get(pk=job_id)
    scope = validate_scope(job, cfg)
    if read_only or job.state == "completed":
        return {"job_id": str(job.pk), "state": job.state,
                "report": job.last_attempt.report if job.last_attempt_id else None}
    # Resolve this exact key before claiming or sending any HTTP request.
    require_twitterapi_api_key(TwitterApiCredentialPurpose.ON_DEMAND)
    seconds = job.definition["budgets"]["seconds"]
    if scope.get("deadline") and any(not unit.get("enumeration_complete") for unit in scope["units"]):
        seconds = min(seconds, (datetime.fromisoformat(scope["deadline"]) - datetime.now(UTC)).total_seconds())
    require(seconds > 0, "campaign deadline exhausted")
    claim = claim_job(job.pk, invocation_id=str(uuid4()), manual_authorized=True,
                      continue_from=job.last_attempt_id)
    budget = DurableBudget(claim, job, seconds)
    error = None
    try:
        if not CollectionScopeRun.objects.filter(run_id=claim.run_id).exists():
            import_scope_checkpoints(
                claim, definition_sha256=job.definition_sha256,
                scopes=scope["units"], provenance=scope.get("provenance", {"format": ADAPTER_VERSION}),
            )
        for _ in range(job.definition["budgets"]["requests"]):
            requests = job.runs.aggregate(total=Sum("request_count"))["total"] or 0
            if scope["prior_api_requests"] + requests >= scope["maximum_api_requests"]:
                break
            scoped = CollectionScopeRun.objects.filter(
                run_id=claim.run_id, scope_kind="x_query", enumeration_complete=False,
            ).order_by("id").first()
            if scoped is None or scoped.outcome == "blocked" or not budget.can_start(38):
                break
            with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.job") as lease:
                if not lease.acquired:
                    break
                owner = scoped.ownership
                settings.X_MONITOR_CYCLE_SINCE_TIME = owner["since_epoch"]
                settings.X_MONITOR_CYCLE_UNTIL_TIME = owner["until_epoch"]
                settings.X_MONITOR_CYCLE_LIMIT_PER_CALL = 20
                settings.X_MONITOR_CYCLE_MAX_PAGES_PER_CALL = 1
                settings.X_MONITOR_CYCLE_BRAND_FILTER = ",".join(scope["brands"]) or None
                page = PageCheckpoint(claim, scoped, budget)
                context = BackfillContext(
                    budget=budget, cursor=scoped.cursor, seen_cursors=scoped.cursor_history,
                    enrichment_limit=0, query_override=owner["query"], page_writer=page.persist,
                )
                stats = CycleRunner(cfg=cfg, cycle_kind="backfill", dry_run=False,
                                    _backfill_call_ids=[owner["call_id"]], _backfill_context=context,
                                    _max_llm_calls=0).run()
                page.empty(stats)
                if stats.get("status") in {"aborted", "degraded"} or any(
                    call.get("status") in {"error", "persist_incomplete", "length_cap_exceeded"}
                    for call in stats.get("calls", [])
                ):
                    raise CommandError("shared backfill runner failed; committed pages retained")
    except StaleClaim:
        # The owner paused or replaced this worker. It cannot publish a finish.
        raise
    except Exception as exc:  # noqa: BLE001 - retain a terminal failure receipt before exit
        error = exc
    try:
        report = _report(job, claim.run_id)
    except ValueError as exc:
        error = error or exc
        report = {"collection_drained": False, "reconciliation_error": str(exc)}
    report.update({"usage": budget.snapshot(), "revision": os.environ.get("RENDER_GIT_COMMIT")})
    status = "failed" if error else ("success" if report["collection_drained"] else "partial")
    finish_run(claim, status=status, report=report,
               error_code=type(error).__name__ if error else None)
    if error:
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
