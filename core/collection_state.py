"""Short database transactions fence claims, evidence and cursor updates together.

Provider requests run outside these transactions. Callers pass validated payloads
to checkpoint_scope or use fenced_run around their existing database writer.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_store import safe_payload
from core.collection_jobs import validate_job
from core.measurement_taxonomy import digest, require
from core.models import CollectionJob, CollectionRun, CollectionScopeRun


class BusyJob(ValueError):
    """An active claim or cooldown prevents another execution."""


class StaleClaim(ValueError):
    """This worker no longer owns the job's active execution."""


@dataclass(frozen=True)
class RunClaim:
    job_id: uuid.UUID
    run_id: uuid.UUID
    lease_token: uuid.UUID


def _key(job, invocation_id):
    require(
        isinstance(invocation_id, str) and 0 < len(invocation_id) <= 256,
        "invocation identity required",
    )
    return digest({"job": str(job.pk), "invocation": invocation_id})


@transaction.atomic
def claim_job(
    job_id, *, invocation_id=None, manual_authorized=False, continue_from=None, now=None
):
    now = now or timezone.now()
    # Campaign peers share a finite reservation ceiling. Lock in one order before
    # the selected job, including on reclaim, without affecting legacy/X claims.
    candidate = CollectionJob.objects.get(pk=job_id)
    campaign = candidate.definition.get("campaign", {})
    bounded_campaign = (isinstance(campaign, dict)
                        and campaign.get("kind") == "backfiller-data-source-v1")
    if bounded_campaign:
        list(CollectionJob.objects.select_for_update().filter(
            definition__campaign__kind="backfiller-data-source-v1",
            definition__campaign__key=campaign["key"],
        ).order_by("pk"))
    job = (
        CollectionJob.objects.select_for_update(of=("self",))
        .select_related("source", "contract")
        .get(pk=job_id)
    )
    validate_job(job)
    require(
        job.state == "ready" and (job.purpose == "content" or job.source.enabled),
        "job/source is not ready",
    )
    if job.purpose == "content":
        require(manual_authorized, "content caller authorization required")
    if job.next_retry_at and job.next_retry_at > now:
        raise BusyJob("job cooldown is active")
    active = None
    if job.active_run_id:
        active = CollectionRun.objects.select_for_update().get(pk=job.active_run_id)
        if active.status == "running" and active.lease_expires_at > now:
            raise BusyJob("job lease is active")
        if active.status == "running":
            active.status = "interrupted" if job.purpose == "catalog" else "aborted"
            active.completed_at = None if job.purpose == "catalog" else now
            active.error_code = "expired_lease"
            active.report = {
                **active.report,
                "interrupted_execution": {
                    "reconciled_at": now.isoformat(),
                    "process_finished_at": None,
                },
            }
            active.save()
    if bounded_campaign:
        from core.data_source_backfill import campaign_usage, validate_campaign

        campaign = validate_campaign(job.definition, contract_id=job.contract_id)
        usage = campaign_usage(job)
        require(
            usage["invocations"] < campaign["max_invocations"]
            and usage["reserved_requests"] + job.definition["budgets"]["requests"]
            <= campaign["max_requests"],
            "campaign invocation/request limit exhausted",
        )
    invocation_id = invocation_id or str(uuid.uuid4())
    ingestion_key = _key(job, invocation_id)
    require(
        not CollectionRun.objects.filter(ingestion_key=ingestion_key).exists(),
        "invocation already recorded",
    )
    if job.purpose == "catalog" and job.last_attempt_id:
        previous = CollectionRun.objects.select_for_update().get(pk=job.last_attempt_id)
        run = previous if previous.completed_at is None else None
    else:
        run = None
    token = uuid.uuid4()
    lease = now + timedelta(seconds=job.definition["budgets"]["seconds"] + 60)
    if run is None:
        run = CollectionRun(
            job=job,
            source=job.source,
            purpose=job.purpose,
            contract=job.contract,
            ingestion_key=ingestion_key,
            started_at=now,
            scope=copy.deepcopy(job.definition["scope"]),
            report={"definition_sha256": job.definition_sha256},
        )
    if bounded_campaign:
        prior_usage = run.report.get("campaign_usage", {})
        run.report = {**run.report, "campaign_usage": {
            "invocations": prior_usage.get("invocations", 0) + 1,
            "reserved_requests": prior_usage.get("reserved_requests", 0)
            + job.definition["budgets"]["requests"],
            "accounting": "conservative_reservation",
        }}
    run.status, run.completed_at = "running", None
    run.lease_token, run.lease_expires_at = token, lease
    run.error_code = None
    run.invocations = [
        *run.invocations,
        {"invocation_id": invocation_id, "started_at": now.isoformat()},
    ]
    run.save()
    if bounded_campaign and job.purpose == "metric" and job.last_attempt_id:
        previous = CollectionRun.objects.select_for_update().get(pk=job.last_attempt_id)
        if previous.status == "partial" and previous.completed_at is not None:
            require(previous.report.get("definition_sha256") == job.definition_sha256,
                    "continuation identity mismatch")
            for scope in previous.scopes.all():
                scope.pk = None
                scope.run = run
                scope.save(force_insert=True)
            run.report = {**run.report, "continued_from": str(previous.pk)}
            run.save(update_fields=["report", "updated_at"])
    if continue_from is not None:
        require(
            job.purpose == "content" and job.mode == "historical",
            "only a frozen backfill campaign may copy scopes",
        )
        previous = CollectionRun.objects.select_for_update().get(pk=continue_from)
        require(
            previous.job_id == job.pk
            and previous.completed_at is not None
            and previous.report.get("definition_sha256") == job.definition_sha256,
            "continuation identity mismatch",
        )
        require(
            previous.pk == job.last_attempt_id,
            "continuation must use the preceding attempt",
        )
        for scope in previous.scopes.all():
            scope.pk = None
            scope.run = run
            scope.save(force_insert=True)
        run.report = {**run.report, "continued_from": str(previous.pk)}
        run.save(update_fields=["report", "updated_at"])
    job.active_run, job.last_attempt = run, run
    job.next_retry_at = None
    job.save()
    return RunClaim(job.pk, run.pk, token)


@contextmanager
def fenced_run(claim: RunClaim, *, now=None):
    """Lock job then run; perform database writes only while the claim is live."""
    now = now or timezone.now()
    with transaction.atomic():
        job = CollectionJob.objects.select_for_update().get(pk=claim.job_id)
        run = CollectionRun.objects.select_for_update().get(pk=claim.run_id)
        if not (
            job.state == "ready"
            and job.active_run_id == run.pk
            and run.job_id == job.pk
            and run.source_id == job.source_id
            and run.purpose == job.purpose
            and run.contract_id == job.contract_id
            and run.status == "running"
            and run.lease_token == claim.lease_token
            and run.lease_expires_at
            and run.lease_expires_at > now
        ):
            raise StaleClaim("execution claim has expired or been replaced")
        validate_job(job)
        yield job, run


def checkpoint_scope(
    claim: RunClaim,
    *,
    scope_key,
    ownership,
    scope_kind="namespace",
    cursor=None,
    cursor_history=None,
    outcome="pending",
    enumeration_complete=False,
    envelopes=None,
    raw_count=None,
    write: Callable | None = None,
):
    require(
        isinstance(scope_key, str) and 0 < len(scope_key) <= 256, "scope key required"
    )
    require(
        isinstance(scope_kind, str) and 0 < len(scope_kind) <= 32, "scope kind required"
    )
    safe_payload(ownership)
    safe_payload(envelopes or [])
    safe_payload(cursor_history or [])
    require(isinstance(ownership, dict), "scope ownership object required")
    require(
        raw_count is None or type(raw_count) is int and raw_count >= 0,
        "invalid raw count",
    )
    with fenced_run(claim) as (_, run):
        scope, created = CollectionScopeRun.objects.get_or_create(
            run=run,
            scope_kind=scope_kind,
            scope_key=scope_key,
            defaults={"ownership": ownership},
        )
        require(created or scope.ownership == ownership, "scope ownership pin changed")
        if write is not None:
            write(run, scope)
        scope.cursor, scope.outcome = cursor, outcome
        scope.enumeration_complete = enumeration_complete
        if cursor_history is not None:
            scope.cursor_history = cursor_history
        if envelopes is not None:
            scope.envelopes = envelopes
        if raw_count is not None:
            scope.raw_count = raw_count
        scope.save()
        return scope


def finish_run(
    claim: RunClaim,
    *,
    status,
    report=None,
    retry_at=None,
    next_due_at=None,
    request_count=None,
    selected_count=None,
    success_count=None,
    error_code=None,
    now=None,
):
    require(
        status in {"success", "partial", "failed", "aborted"},
        "terminal/yield outcome required",
    )
    safe_payload(report or {})
    now = now or timezone.now()
    with fenced_run(claim, now=now) as (job, run):
        run.status = status
        run.completed_at = (
            None if job.purpose == "catalog" and status == "partial" else now
        )
        run.report = {**run.report, **(report or {})}
        require(
            run.report.get("definition_sha256") == job.definition_sha256,
            "instruction provenance cannot change",
        )
        # Only an adapter proving complete physical accounting may release unused
        # reservation. Interrupted/ambiguous attempts retain their conservative cap.
        reservation = run.report.get("campaign_usage")
        campaign = job.definition.get("campaign")
        if (isinstance(campaign, dict)
                and campaign.get("kind") == "backfiller-data-source-v1"
                and reservation and status == "success"
                and run.report.get("physical_accounting_complete") is True
                and request_count is not None):
            require(request_count <= reservation["reserved_requests"],
                    "accounted requests exceed campaign reservation")
            run.report["campaign_usage"] = {
                **reservation, "reserved_requests": request_count,
                "accounting": "complete_physical_accounting",
            }
        run.error_code = error_code
        for field, value in (
            ("request_count", request_count),
            ("selected_count", selected_count),
            ("success_count", success_count),
        ):
            if value is not None:
                require(
                    type(value) is int and 0 <= value <= 2**31 - 1,
                    "invalid execution counter",
                )
                setattr(run, field, value)
        require(
            run.success_count <= run.selected_count,
            "successful count exceeds selected count",
        )
        run.save()
        job.active_run = None
        if status == "success":
            job.last_success = run
            if job.mode == "historical":
                job.state = "completed"
        job.next_retry_at = retry_at if job.state == "ready" else None
        job.next_due_at = next_due_at if job.state == "ready" else None
        job.save()
        return run


@transaction.atomic
def record_rejection(job_id, *, invocation_id, reason, report=None, now=None):
    """A receipt does not acquire an execution lease or alter active pointers."""
    now = now or timezone.now()
    job = CollectionJob.objects.select_for_update().get(pk=job_id)
    require(
        job.purpose == "content", "rejected invocation receipts are content attempts"
    )
    require(
        isinstance(reason, str) and 0 < len(reason) <= 64, "rejection reason required"
    )
    safe_payload(report or {})
    ingestion_key = _key(job, invocation_id)
    existing = CollectionRun.objects.filter(ingestion_key=ingestion_key).first()
    if existing:
        require(
            existing.job_id == job.pk
            and existing.status == "aborted"
            and existing.error_code == reason
            and existing.lease_token is None,
            "invocation receipt conflict",
        )
        return existing
    return CollectionRun.objects.create(
        job=job,
        source=job.source,
        purpose="content",
        ingestion_key=ingestion_key,
        status="aborted",
        started_at=now,
        completed_at=now,
        error_code=reason,
        scope=job.definition["scope"],
        report={
            **(report or {}),
            "definition_sha256": job.definition_sha256,
            "invocation_id": invocation_id,
            "provider_usage": None,
        },
    )


def import_scope_checkpoints(claim: RunClaim, *, definition_sha256, scopes, provenance):
    """Import committed pilot progress into a current attempt, never old receipts.

    The X adapter decodes its versioned file into this typed scope list. Missing
    historical attempt clocks remain unknown; import time is retrieval evidence.
    """
    safe_payload(provenance)
    safe_payload(scopes)
    require(
        isinstance(provenance, dict) and provenance.get("format"),
        "checkpoint provenance required",
    )
    require(isinstance(scopes, list), "scope list required")
    with fenced_run(claim) as (job, run):
        require(
            job.purpose == "content" and job.mode == "historical",
            "backfill import required",
        )
        require(
            definition_sha256 == job.definition_sha256,
            "checkpoint instruction identity mismatch",
        )
        require(
            len(scopes) <= job.definition["budgets"]["items"],
            "checkpoint item budget exceeded",
        )
        for scope in scopes:
            require(isinstance(scope, dict), "checkpoint scope object required")
            require(
                set(scope)
                <= {
                    "scope_key",
                    "scope_kind",
                    "ownership",
                    "cursor",
                    "cursor_history",
                    "outcome",
                    "enumeration_complete",
                    "envelopes",
                    "raw_count",
                },
                "unsupported checkpoint fields",
            )
            checkpoint_scope(claim, **scope)
        run.report = {
            **run.report,
            "checkpoint_import": {
                "provenance": provenance,
                "imported_at": timezone.now().isoformat(),
                "historical_attempt_timestamps": None,
            },
        }
        run.save(update_fields=["report", "updated_at"])
        return run
