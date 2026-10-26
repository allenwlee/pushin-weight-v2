"""Frozen query identities for the existing scheduled X cycle."""

from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from core.collection_capture import (
    archive_legacy,
    begin_request,
    finish_request,
    link_request,
    read_document,
)
from core.collection_jobs import register_job
from core.collection_state import (
    BusyJob,
    claim_job,
    fenced_run,
    finish_run,
    x_scope_ownership,
)
from core.measurement_taxonomy import digest, require
from core.models import (
    CollectionJob,
    CollectionRun,
    CollectionScopeRun,
    DataSource,
    SearchQuery,
)
from core.provider_batches import save_post_membership

EXECUTION_KIND = "x_cycle_execution"
EXECUTION_PHASE = "typed-x-cycle-v1"


def _scope_compatibility():
    return {"ownership": {}} if any(
        field.name == "ownership" for field in CollectionScopeRun._meta.fields
    ) else {}


def _legacy_evidence(row, empty):
    """Only the explicit adoption boundary reads old collection documents."""
    fields = {field.name for field in type(row)._meta.fields}
    if set(empty) <= fields:
        return {name: getattr(row, name) for name in empty}
    require(row.legacy_archive_id is not None, "scheduled legacy evidence is missing")
    document = read_document(row.legacy_archive)
    require(isinstance(document, dict) and set(empty) <= set(document),
            "scheduled legacy evidence is incomplete")
    return {name: document[name] for name in empty}


def _adopt_same_slot(job, *, now):
    """Under the job lock, prove settled old execution before typed reclaim."""
    from core.collection_scheduling import schedule_slot

    if not job.last_attempt_id:
        return
    run = CollectionRun.objects.select_for_update().get(pk=job.last_attempt_id, job=job)
    if run.completed_at is not None or run.scheduled_slot_at != schedule_slot(job, now)[0]:
        return
    if run.status == "running" and run.lease_expires_at and run.lease_expires_at > now:
        raise BusyJob("job lease is active")
    if run.scopes.filter(scope_kind=EXECUTION_KIND, scope_key="execution", phase=EXECUTION_PHASE).exists():
        require(not run.attempts.filter(requests__transport_outcome="pending").exists(),
                "scheduled previous request receipt is unfinished")
        return
    require(run.status == "partial" and job.active_run_id is None,
            "scheduled legacy execution must be settled before adoption")
    empty_run = {"report": {}, "invocations": [], "request_params": {},
                 "source_metadata": {}, "raw_payload": None}
    document = _legacy_evidence(run, empty_run)
    report = document["report"]
    require(isinstance(report, dict) and set(report) == {"physical_accounting_complete"}
            and type(report["physical_accounting_complete"]) is bool
            and all(document[key] == value for key, value in empty_run.items() if key != "report"),
            "scheduled legacy execution has unsupported source evidence")
    scopes = {scope.pk: scope for scope in run.scopes.select_related(
        "job_target__search_query", "legacy_archive",
    )}
    for scope in scopes.values():
        scope.run = run
        owner = x_scope_ownership(scope)
        require(owner["call_id"] == scope.scope_key
                and _legacy_evidence(scope, {"ownership": {}, "cursor_history": [], "envelopes": []})
                == {"ownership": {}, "cursor_history": [], "envelopes": []},
                "scheduled legacy scope has unsupported evidence")
    requests = {}
    total_requests = total_unknown = 0
    attempts = list(run.attempts.order_by("ordinal").prefetch_related("requests__archive"))
    require(attempts, "scheduled legacy execution has no attempts")
    for attempt in attempts:
        require(attempt.outcome != "running" and attempt.finished_at is not None,
                "scheduled legacy attempt is unsettled")
        rows = list(attempt.requests.all())
        observed_bytes = unknown = 0
        for request in rows:
            scope = scopes.get(request.scope_run_id)
            require(scope is not None and request.receipt_kind == "physical"
                    and request.transport_outcome in {"received", "transport_error"}
                    and request.accounting_complete == (request.transport_outcome == "received")
                    and request.requested_start_at == scope.requested_start_at
                    and request.requested_end_at == scope.requested_end_at,
                    "scheduled legacy request owner or outcome differs")
            if request.archive_id is not None:
                archive = request.archive
                require(request.response_bytes == archive.byte_count == len(archive.body)
                        and hashlib.sha256(bytes(archive.body)).hexdigest() == archive.content_sha256,
                        "scheduled legacy response bytes differ")
            else:
                require(request.transport_outcome == "transport_error" and request.response_bytes is None,
                        "scheduled legacy response evidence is missing")
            observed_bytes += request.response_bytes or 0
            unknown += int(request.transport_outcome != "received")
            requests[request.pk] = request
        require(attempt.actual_requests == len(rows)
                and attempt.actual_response_bytes == observed_bytes
                and attempt.unknown_sent_requests == unknown,
                "scheduled legacy attempt accounting differs")
        total_requests += len(rows)
        total_unknown += unknown
    require(run.request_count == total_requests
            and report["physical_accounting_complete"] == (total_unknown == 0)
            and attempts[-1].accounting_complete == report["physical_accounting_complete"],
            "scheduled legacy run accounting differs")
    for observation in run.observations.select_related("legacy_archive", "post").prefetch_related("inputs"):
        require(observation.source_subject_kind == "post" and observation.post_id is not None
                and observation.scope_run_id in scopes
                and observation.source_identifier == str(observation.post_id)
                and observation.post.pk == observation.post_id,
                "scheduled legacy Post membership differs")
        empty = {"listing": {}, "dimensions": {}, "source_metadata": {}, "groups": {}, "envelopes": []}
        require(_legacy_evidence(observation, empty) == empty,
                "scheduled legacy Post has unsupported source evidence")
        for link in observation.inputs.all():
            request = requests.get(link.input_request_id)
            require(request is not None and request.archive_id is not None
                    and request.transport_outcome == "received" and request.http_status == 200
                    and request.scope_run_id == observation.scope_run_id
                    and link.input_role == "response" and link.row_locator == str(observation.post_id)
                    and link.input_sha256 == request.archive.content_sha256,
                    "scheduled legacy Post input differs")
    CollectionScopeRun.objects.create(
        run=run, scope_kind=EXECUTION_KIND, scope_key="execution", phase=EXECUTION_PHASE,
        legacy_archive=archive_legacy(document), **_scope_compatibility(),
    )


def scheduled_cycle_report(run):
    """Keep the scheduled report's existing single accounting fact."""
    require(run.job.source_id == "x" and run.job.purpose == "content"
            and run.job.operation == "x_cycle" and run.job.mode == "recurring",
            "scheduled X collection required")
    attempt = run.attempts.order_by("-ordinal").only("accounting_complete").first()
    return {"physical_accounting_complete": attempt.accounting_complete is True if attempt else False}


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
    @transaction.atomic
    def start(cls, calls, *, limits, invocation_id):
        from core.collection_jobs import set_job_state

        job = register_scheduled_cycle(calls, limits=limits)
        if job.state == "paused":
            job = set_job_state(job.pk, "ready")
        require(job.state == "ready", "scheduled job is not ready")
        job = CollectionJob.objects.select_for_update().get(pk=job.pk)
        now = timezone.now()
        _adopt_same_slot(job, now=now)
        return cls(claim_job(job.pk, invocation_id=invocation_id, manual_authorized=True,
                            typed=True, now=now))

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
                    "job_target": target, **_scope_compatibility(), "phase": EXECUTION_PHASE,
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
                not run.attempts.filter(requests__transport_outcome="pending").exists(),
                "scheduled request receipt is unfinished",
            )
            requests = sum(run.attempts.values_list("actual_requests", flat=True))
            unknown = sum(run.attempts.values_list("unknown_sent_requests", flat=True))
        return finish_run(
            self.claim, status="success" if success else "partial",
            request_count=requests, typed=True,
            physical_accounting_complete=unknown == 0,
            now=timezone.now(),
        )
