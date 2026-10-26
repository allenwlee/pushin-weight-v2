"""Frozen query identities for the existing scheduled X cycle."""

from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from core.collection_capture import begin_request, finish_request, link_request
from core.collection_jobs import register_job
from core.collection_state import claim_job, fenced_run, finish_run
from core.measurement_taxonomy import digest, require
from core.models import CollectionScopeRun, DataSource, SearchQuery
from core.provider_batches import save_post_membership


@transaction.atomic
def register_scheduled_cycle(calls, *, limits):
    """Register one recurring job for an unchanged ordered query plan.

    Query identity is fixed on each target. Request windows belong to each
    scope run, because the seven scheduled calls move on every invocation.
    Registration does not dispatch a provider call or activate the job.
    """
    calls = tuple(calls)
    require(calls and len(calls) == len({call.call_id for call in calls}),
            "scheduled calls require unique roles")
    require(set(limits) == {"requests", "bytes", "seconds", "items"},
            "scheduled limits require four finite bounds")
    source, _ = DataSource.objects.get_or_create(
        pk="x", defaults={"name": "X", "source_type": "social"},
    )
    targets = []
    for call in calls:
        query_text = call.query_string
        require(isinstance(query_text, str) and query_text,
                "scheduled query wording required")
        query_id = "x-cycle:" + hashlib.sha256(query_text.encode()).hexdigest()
        query, _ = SearchQuery.objects.get_or_create(
            query_id=query_id, defaults={"query_text": query_text},
        )
        require(query.query_text == query_text, "scheduled query identity changed")
        targets.append({
            "target_key": call.call_id,
            "target_kind": "query",
            "target_role": call.call_id,
            "resolution_state": "resolved",
            "search_query_id": query.pk,
        })
    identity = digest({
        "queries": [(call.call_id, call.query_string) for call in calls],
        "limits": limits,
    })
    return register_job(
        job_key="x-cycle:" + identity,
        source=source, purpose="content", operation="x_cycle",
        mode="recurring",
        definition={"version": 2, "options": {
            "adapter": "twitterapi", "credential_purpose": "scheduled",
        }},
        settings={
            "owner_kind": "source", "schedule_kind": "interval",
            "schedule_driver": "external_render_cron", "interval_seconds": 900,
            "max_requests": limits["requests"], "max_bytes": limits["bytes"],
            "max_seconds": limits["seconds"], "max_items": limits["items"],
        },
        targets=targets,
    )


class ScheduledCycleLineage:
    """Keep a scheduled run's query scopes and committed Post members together."""

    def __init__(self, claim):
        self.claim = claim

    @classmethod
    def start(cls, calls, *, limits, invocation_id):
        from core.collection_jobs import set_job_state

        job = register_scheduled_cycle(calls, limits=limits)
        if job.state == "paused":
            job = set_job_state(job.pk, "ready")
        require(job.state == "ready", "scheduled job is not ready")
        return cls(claim_job(job.pk, invocation_id=invocation_id, manual_authorized=True))

    def begin_call(self, call, *, since_epoch, until_epoch):
        from datetime import UTC, datetime

        lower = datetime.fromtimestamp(since_epoch, UTC)
        upper = datetime.fromtimestamp(until_epoch, UTC)
        require(lower < upper, "scheduled query window is reversed")
        with fenced_run(self.claim) as (job, run):
            target = job.targets.select_related("search_query").get(target_key=call.call_id)
            require(
                target.target_kind == "query"
                and target.target_role == call.call_id
                and target.search_query.query_text == call.query_string
                and target.requested_start_at is None
                and target.requested_end_at is None,
                "scheduled query differs from frozen target",
            )
            scope, created = CollectionScopeRun.objects.get_or_create(
                run=run, scope_kind="x_query", scope_key=call.call_id,
                defaults={
                    "job_target": target, "ownership": {},
                    "requested_start_at": lower, "requested_end_at": upper,
                },
            )
            require(
                created or (
                    scope.job_target_id == target.pk
                    and scope.requested_start_at == lower
                    and scope.requested_end_at == upper
                ),
                "scheduled query window changed after checkpoint",
            )
            return scope.pk

    def begin_exchange(self, scope_id, *, endpoint_url, params):
        """Reserve one physical HTTP attempt before transport starts."""
        require(self.claim.attempt_id is not None, "scheduled attempt is missing")
        with fenced_run(self.claim) as (_, run):
            scope = CollectionScopeRun.objects.get(pk=scope_id, run=run)
            attempt = run.attempts.get(pk=self.claim.attempt_id)
            return begin_request(
                attempt, scope, endpoint_url=endpoint_url,
                cursor=params.get("cursor"),
                requested_start_at=scope.requested_start_at,
                requested_end_at=scope.requested_end_at,
            )

    def finish_exchange(self, request, receipt):
        """Keep the exact response bytes even when the provider rejects it."""
        require(
            receipt.get("outcome") in {"received", "transport_error"},
            "scheduled exchange outcome is invalid",
        )
        cursor_after = None
        body = receipt.get("body")
        if isinstance(body, bytes) and receipt.get("status_code") == 200:
            try:
                parsed = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                parsed = None
            if isinstance(parsed, dict) and isinstance(parsed.get("next_cursor"), str):
                cursor_after = parsed["next_cursor"] or None
        return finish_request(
            request,
            outcome=receipt["outcome"],
            body=body,
            http_status=receipt.get("status_code"),
            cursor=cursor_after,
            error_code=receipt.get("error_type"),
            response_bytes=(
                len(body) if body is not None else None
            ),
        )

    def bind_api(self, api, scope_id):
        require(
            getattr(api, "on_exchange_start", None) is None
            and getattr(api, "on_exchange_finish", None) is None,
            "scheduled provider already has an exchange owner",
        )
        api.on_exchange_start = lambda path, params: self.begin_exchange(
            scope_id, endpoint_url=f"{api.base_url}{path}", params=params,
        )
        api.on_exchange_finish = self.finish_exchange

    @staticmethod
    def unbind_api(api):
        api.on_exchange_start = None
        api.on_exchange_finish = None

    def finish_call(
        self, scope_id, *, post_ids, raw_count, outcome, complete,
        page_by_post=None,
    ):
        require(type(raw_count) is int and raw_count >= 0,
                "scheduled raw count must be nonnegative")
        page_by_post = page_by_post or {}
        with fenced_run(self.claim) as (_, run):
            scope = CollectionScopeRun.objects.select_for_update().get(
                pk=scope_id, run=run,
            )
            saved = save_post_membership(run, scope, post_ids)
            require(set(page_by_post) <= set(saved),
                    "request page refers to an unsaved Post")
            if page_by_post:
                replies = list(scope.requests.filter(
                    transport_outcome="received", http_status=200,
                ).order_by("ordinal"))
                observations = {
                    str(row.post_id): row for row in scope.observations.filter(
                        post_id__in=page_by_post,
                    )
                }
                for post_id, page_number in page_by_post.items():
                    require(
                        type(page_number) is int
                        and 1 <= page_number <= len(replies)
                        and post_id in observations,
                        "scheduled Post has no captured response page",
                    )
                    link_request(
                        observations[post_id], replies[page_number - 1],
                        row_locator=post_id,
                    )
            scope.raw_count = raw_count
            scope.outcome = outcome
            scope.enumeration_complete = complete
            scope.execution_state = "completed" if complete else "yielded"
            scope.coverage_state = (
                "complete" if complete else "partial" if raw_count else "unavailable"
            )
            scope.save(update_fields=[
                "raw_count", "outcome", "enumeration_complete",
                "execution_state", "coverage_state",
            ])
            return len(saved)

    def finish(self, *, success):
        with fenced_run(self.claim) as (_, run):
            require(
                not run.attempts.filter(pk=self.claim.attempt_id, requests__transport_outcome="pending").exists(),
                "scheduled request receipt is unfinished",
            )
            requests = sum(run.attempts.values_list("actual_requests", flat=True))
            unknown = sum(run.attempts.values_list("unknown_sent_requests", flat=True))
        return finish_run(
            self.claim, status="success" if success else "partial",
            request_count=requests,
            report={"physical_accounting_complete": unknown == 0},
            now=timezone.now(),
        )
