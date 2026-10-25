"""Short database transactions fence claims, evidence and cursor updates together.

Provider requests run outside these transactions. Callers pass validated payloads
to checkpoint_scope or use fenced_run around their existing database writer.
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.benchmark_metric_store import safe_payload
from core.collection_jobs import validate_job
from core.measurement_taxonomy import digest, require
from core.models import (
    CollectionAttempt,
    CollectionJob,
    CollectionJobTarget,
    CollectionRun,
    CollectionScopeRun,
    SearchQuery,
)


class BusyJob(ValueError):
    """An active claim or cooldown prevents another execution."""


class StaleClaim(ValueError):
    """This worker no longer owns the job's active execution."""


@dataclass(frozen=True)
class RunClaim:
    job_id: uuid.UUID
    run_id: uuid.UUID
    lease_token: uuid.UUID
    direct_driver: str | None = None
    attempt_id: uuid.UUID | None = None


def _begin_attempt(run, *, attempt_key, limits, now):
    """Called only while the owning job/run is locked, before provider work."""
    run.attempts.filter(outcome="running").update(
        outcome="interrupted",
        stop_reason="expired_lease",
    )
    previous = run.attempts.order_by("-ordinal").first()
    return CollectionAttempt.objects.create(
        run=run,
        attempt_key=attempt_key,
        ordinal=previous.ordinal + 1 if previous else 1,
        lease_token=run.lease_token,
        lease_expires_at=run.lease_expires_at,
        started_at=now,
        outcome="running",
        reserved_requests=limits.get("requests"),
        reserved_bytes=limits.get("bytes"),
        effective_seconds=limits.get("seconds"),
        effective_items=limits.get("items"),
    )


def complete_attempt(
    claim,
    run,
    *,
    status,
    request_count=None,
    accounting_complete=False,
    error_code=None,
    now=None,
):
    """Finish an attempt inside the caller's already-fenced transaction."""
    run.execution_state = (
        "completed"
        if status == "success"
        else "yielded"
        if status == "partial"
        else status
    )
    run.coverage_state = (
        "complete"
        if status == "success"
        and not run.observations.filter(metric_gaps__isnull=False).exists()
        else "partial"
        if status in {"partial", "success"}
        else "unavailable"
    )
    run.save(update_fields=["execution_state", "coverage_state"])
    if claim.attempt_id is None:
        return
    attempt = CollectionAttempt.objects.select_for_update().get(
        pk=claim.attempt_id, run=run
    )
    prior_requests = sum(
        run.attempts.exclude(pk=attempt.pk).values_list("actual_requests", flat=True)
    )
    if request_count is not None:
        attempt.actual_requests = max(
            attempt.actual_requests, request_count - prior_requests
        )
    attempt.outcome = status
    attempt.finished_at = now or timezone.now()
    attempt.stop_reason = error_code
    attempt.accounting_complete = (
        accounting_complete
        and request_count is not None
        and attempt.unknown_sent_requests == 0
    )
    attempt.save()


@transaction.atomic
def register_direct_job(*, source_id, purpose, contract_id=None, scope, driver, limits):
    """Save an immutable receipt before constructing a direct caller's run."""
    require(
        driver in {"persist_source", "execute_catalog"}, "unsupported direct driver"
    )
    definition = {
        "version": 1,
        "scope": copy.deepcopy(scope),
        "schedule": {"kind": "manual", "driver": driver},
        "budgets": copy.deepcopy(limits),
        "budget_authority": "direct_invocation",
        "execution": {"driver": driver, "executable": False},
    }
    safe_payload(definition)
    require(isinstance(scope, dict), "frozen scope required")
    identity = {
        "source": source_id,
        "purpose": purpose,
        "contract": str(contract_id) if contract_id else None,
        "operation": "legacy_direct",
        "mode": "manual",
        "definition": definition,
    }
    key = f"direct:{driver}:{digest(identity)}"
    identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"pushinweight:{key}")
    require(
        not CollectionJob.objects.filter(job_key=key).exclude(pk=identifier).exists(),
        "direct job key collision",
    )
    values = {
        "job_key": key,
        "source_id": source_id,
        "purpose": purpose,
        "contract_id": contract_id,
        "operation": "legacy_direct",
        "mode": "manual",
        "definition": definition,
        "definition_sha256": digest(identity),
        "state": "completed",
    }
    job, _ = CollectionJob.objects.get_or_create(pk=identifier, defaults=values)
    require(
        all(getattr(job, name) == value for name, value in values.items()),
        "direct job identity collision",
    )
    validate_job(job)
    return job


@transaction.atomic
def claim_direct_run(run, *, driver, seconds, limits, now=None):
    """Lease an explicit invocation under its existing caller advisory lock.

    Registration precedes run construction; archived instructions stay unchanged
    when the original catalog driver resumes with new invocation limits.
    """
    require(
        driver in {"persist_source", "execute_catalog"}, "unsupported direct driver"
    )
    require(
        isinstance(seconds, (int, float)) and 0 < seconds < float("inf"),
        "finite direct invocation duration required",
    )
    job = CollectionJob.objects.select_for_update().get(pk=run.job_id)
    validate_job(job)
    require(
        job.operation in {"legacy_direct", "archived_run"},
        "shared jobs require the shared collector claim",
    )
    require(
        (driver == "persist_source" and job.purpose == "metric")
        or (
            driver == "execute_catalog"
            and job.purpose == "catalog"
            and job.source_id == "hf"
        ),
        "direct driver instruction mismatch",
    )
    require(
        job.operation == "archived_run"
        or job.definition["execution"]["driver"] == driver,
        "direct driver instruction mismatch",
    )
    if not run._state.adding:
        stored = CollectionRun.objects.select_for_update().get(pk=run.pk)
        require(
            stored.job_id == run.job_id
            and stored.lease_token == run.lease_token
            and stored.status == run.status,
            "direct run changed while acquiring ownership",
        )
        now = now or timezone.now()
        if (
            stored.status == "running"
            and stored.lease_expires_at
            and stored.lease_expires_at > now
        ):
            raise BusyJob("direct run lease is active")
    now = now or timezone.now()
    run.job = job
    run.status, run.completed_at = "running", None
    run.execution_state = "running"
    run.lease_token = uuid.uuid4()
    run.lease_expires_at = now + timedelta(seconds=seconds)
    run.save()
    attempt = _begin_attempt(
        run,
        attempt_key=digest([str(run.pk), str(run.lease_token)]),
        limits=limits,
        now=now,
    )
    return RunClaim(job.pk, run.pk, run.lease_token, driver, attempt.pk)


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
    campaign = candidate.campaign_settings
    bounded_campaign = (
        isinstance(campaign, dict)
        and campaign.get("kind") == "backfiller-data-source-v1"
    )
    if bounded_campaign:
        if candidate.campaign_id:
            from core.models import CollectionCampaign

            CollectionCampaign.objects.select_for_update().get(pk=candidate.campaign_id)
        else:
            list(
                CollectionJob.objects.select_for_update()
                .filter(
                    definition__campaign__kind="backfiller-data-source-v1",
                    definition__campaign__key=campaign["key"],
                )
                .order_by("pk")
            )
    job = (
        CollectionJob.objects.select_for_update(of=("self",))
        .select_related("source", "contract")
        .get(pk=job_id)
    )
    validate_job(job)
    require(
        job.state == "ready"
        and (
            job.purpose == "content"
            or job.operation == "match_crosswalk"
            or job.source.enabled
        ),
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
            resumable = job.purpose == "catalog" or job.instruction_version == 2
            active.status = "interrupted" if resumable else "aborted"
            active.completed_at = None if resumable else now
            active.execution_state = "interrupted"
            active.error_code = "expired_lease"
            active.report = {
                **active.report,
                "interrupted_execution": {
                    "reconciled_at": now.isoformat(),
                    "process_finished_at": None,
                },
            }
            active.save()
            active.attempts.filter(outcome="running").update(
                outcome="interrupted",
                stop_reason="expired_lease",
            )
    if bounded_campaign:
        from core.data_source_backfill import campaign_usage, validate_campaign

        campaign = validate_campaign(job.instructions, contract_id=job.contract_id)
        usage = campaign_usage(job)
        require(
            usage["invocations"] < campaign["max_invocations"]
            and usage["reserved_requests"] + job.budgets["requests"]
            <= campaign["max_requests"],
            "campaign invocation/request limit exhausted",
        )
    invocation_id = invocation_id or str(uuid.uuid4())
    ingestion_key = _key(job, invocation_id)
    require(
        not CollectionRun.objects.filter(ingestion_key=ingestion_key).exists()
        and not CollectionAttempt.objects.filter(attempt_key=ingestion_key).exists(),
        "invocation already recorded",
    )
    slot = None
    if job.instruction_version == 2 and job.mode == "recurring":
        from core.collection_scheduling import schedule_slot

        slot, _ = schedule_slot(job, now)
    if (
        job.purpose == "catalog" or job.instruction_version == 2
    ) and job.last_attempt_id:
        previous = CollectionRun.objects.select_for_update().get(pk=job.last_attempt_id)
        run = (
            previous
            if previous.completed_at is None
            and (slot is None or previous.scheduled_slot_at == slot)
            else None
        )
    else:
        run = None
    if continue_from is not None and job.instruction_version == 2:
        run = CollectionRun.objects.select_for_update().get(pk=continue_from)
        require(
            run.job_id == job.pk and run.completed_at is None,
            "continuation must resume an unfinished collection of this job",
        )
        require(
            active is None or active.pk == run.pk or active.completed_at is not None,
            "another unfinished collection owns the active slot",
        )
    token = uuid.uuid4()
    lease = now + timedelta(seconds=job.budgets["seconds"] + 60)
    if run is None:
        run = CollectionRun(
            job=job,
            ingestion_key=ingestion_key,
            started_at=now,
            scheduled_slot_at=slot,
            report={"definition_sha256": job.definition_sha256},
        )
    if bounded_campaign:
        prior_usage = run.report.get("campaign_usage", {})
        run.report = {
            **run.report,
            "campaign_usage": {
                "invocations": prior_usage.get("invocations", 0) + 1,
                "reserved_requests": prior_usage.get("reserved_requests", 0)
                + job.budgets["requests"],
                "reserved_before_current": prior_usage.get("reserved_requests", 0),
                "recorded_before_current": run.request_count,
                "current_invocation_reservation": job.budgets["requests"],
                "accounting": "conservative_reservation",
            },
        }
    run.status, run.completed_at = "running", None
    run.execution_state = "running"
    run.lease_token, run.lease_expires_at = token, lease
    run.error_code = None
    run.invocations = [
        *run.invocations,
        {"invocation_id": invocation_id, "started_at": now.isoformat()},
    ]
    run.save()
    attempt = _begin_attempt(
        run, attempt_key=ingestion_key, limits=job.budgets, now=now
    )
    if bounded_campaign and job.purpose == "metric" and job.last_attempt_id:
        previous = CollectionRun.objects.select_for_update().get(pk=job.last_attempt_id)
        if previous.status == "partial" and previous.completed_at is not None:
            require(
                previous.report.get("definition_sha256") == job.definition_sha256,
                "continuation identity mismatch",
            )
            for scope in previous.scopes.all():
                scope.pk = None
                scope.run = run
                scope.save(force_insert=True)
            run.report = {**run.report, "continued_from": str(previous.pk)}
            run.save(update_fields=["report", "updated_at"])
    if continue_from is not None and job.instruction_version == 2:
        require(
            str(continue_from) == str(run.pk),
            "continuation must resume the same logical collection",
        )
    elif continue_from is not None:
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
    job.last_attempt_attempt = attempt
    job.next_retry_at = None
    job.save()
    return RunClaim(job.pk, run.pk, token, attempt_id=attempt.pk)


@contextmanager
def fenced_run(claim: RunClaim, *, now=None):
    """Lock job then run; perform database writes only while the claim is live."""
    with transaction.atomic():
        job = CollectionJob.objects.select_for_update().get(pk=claim.job_id)
        run = CollectionRun.objects.select_for_update().get(pk=claim.run_id)
        now = now or timezone.now()
        if not (
            (
                (
                    claim.direct_driver in {"persist_source", "execute_catalog"}
                    and job.operation in {"legacy_direct", "archived_run"}
                    and job.state == "completed"
                    and job.active_run_id is None
                )
                or (
                    claim.direct_driver is None
                    and job.state == "ready"
                    and job.active_run_id == run.pk
                )
            )
            and run.job_id == job.pk
            and run.status == "running"
            and run.lease_token == claim.lease_token
            and run.lease_expires_at
            and run.lease_expires_at > now
        ):
            raise StaleClaim("execution claim has expired or been replaced")
        # The claim already verified frozen membership. Database seal guards
        # prevent changing it; avoid rereading every target on each checkpoint.
        validate_job(job, deep=False)
        if (
            claim.attempt_id is not None
            and not CollectionAttempt.objects.filter(
                pk=claim.attempt_id,
                run=run,
                outcome="running",
                lease_token=claim.lease_token,
                lease_expires_at__gt=now,
            ).exists()
        ):
            raise StaleClaim("execution attempt has expired or been replaced")
        run.job = job
        yield job, run


def x_query_instruction(ownership):
    """Return the frozen X query and window without accepting partial ownership."""
    require(
        isinstance(ownership, dict)
        and set(ownership) == {"call_id", "query", "since_epoch", "until_epoch"}
        and isinstance(ownership["call_id"], str)
        and 0 < len(ownership["call_id"]) <= 32
        and isinstance(ownership["query"], str)
        and bool(ownership["query"]),
        "X scope requires its frozen call and query",
    )
    lower, upper = ownership["since_epoch"], ownership["until_epoch"]
    require(
        type(lower) is int and type(upper) is int and 0 <= lower < upper,
        "X scope requires ordered integer request epochs",
    )
    return (
        ownership["query"], ownership["call_id"],
        datetime.fromtimestamp(lower, UTC), datetime.fromtimestamp(upper, UTC),
    )


def ensure_x_query_target(job, scope_key, *, query_text, call_id, start_at, end_at):
    """Pin one query and call role per job scope; never modify a sealed target."""
    query_id = "x-backfill:" + hashlib.sha256(query_text.encode()).hexdigest()
    search_query, _ = SearchQuery.objects.get_or_create(
        query_id=query_id, defaults={"query_text": query_text}
    )
    require(search_query.query_text == query_text, "X query identity changed")
    target = job.targets.filter(target_key=scope_key).first()
    if target is None:
        CollectionJob.objects.select_for_update().get(pk=job.pk)
        target = job.targets.filter(target_key=scope_key).first()
    if target is None:
        require(
            job.instruction_version == 1,
            "sealed X job requires a frozen query target",
        )
        maximum = job.targets.aggregate(Max("ordinal"))["ordinal__max"]
        ordinal = 0 if maximum is None else maximum + 1
        target = CollectionJobTarget.objects.create(
            job=job, target_key=scope_key, ordinal=ordinal,
            target_kind="query", target_role=call_id,
            resolution_state="resolved", search_query=search_query,
            requested_start_at=start_at, requested_end_at=end_at,
        )
    require(
        target.target_kind == "query"
        and target.target_role == call_id
        and target.search_query_id == search_query.pk
        and target.requested_start_at == start_at
        and target.requested_end_at == end_at,
        "frozen X query target differs from scope ownership",
    )
    return target


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
    requested_start_at=None,
    requested_end_at=None,
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
    if scope_kind == "x_query":
        query_text, call_id, lower_at, upper_at = x_query_instruction(ownership)
        require(
            requested_start_at is None or requested_start_at == lower_at,
            "X scope requested start differs from ownership",
        )
        require(
            requested_end_at is None or requested_end_at == upper_at,
            "X scope requested end differs from ownership",
        )
        requested_start_at, requested_end_at = lower_at, upper_at
    require(
        raw_count is None or type(raw_count) is int and raw_count >= 0,
        "invalid raw count",
    )
    with fenced_run(claim) as (_, run):
        target = None
        if scope_kind == "product_match":
            from core.collection_matching import ensure_product_match_target

            target = ensure_product_match_target(run.job, scope_key, ownership)
        if scope_kind == "x_query":
            target = ensure_x_query_target(
                run.job, scope_key, query_text=query_text, call_id=call_id,
                start_at=requested_start_at, end_at=requested_end_at,
            )
        scope, created = CollectionScopeRun.objects.get_or_create(
            run=run,
            scope_kind=scope_kind,
            scope_key=scope_key,
            defaults={"ownership": ownership, "job_target": target},
        )
        require(created or scope.ownership == ownership, "scope ownership pin changed")
        require(
            created or scope.job_target_id in (None, target.pk if target else None),
            "scope target pin changed",
        )
        if target and scope.job_target_id is None:
            scope.job_target = target
        for field, value in (
            ("requested_start_at", requested_start_at),
            ("requested_end_at", requested_end_at),
        ):
            if value is not None:
                from core.benchmark_metric_store import aware_instant

                value = aware_instant(value)
                require(
                    getattr(scope, field) in (None, value),
                    "scope request bounds changed",
                )
                setattr(scope, field, value)
        last_observation = (
            scope.observations.order_by("-pk").values_list("pk", flat=True).first() or 0
        )
        if write is not None:
            write(run, scope)
        if envelopes or scope.requests.exists():
            from core.collection_capture import link_request
            from core.models import CollectionObservationInput, CollectionRequest

            identifiers = (
                {
                    envelope["collection_request_id"]
                    for envelope in envelopes
                    if envelope.get("collection_request_id")
                    and (
                        envelope.get("outcome") == "ok" or envelope.get("status") == 200
                    )
                }
                if envelopes
                else set()
            )
            identifiers.update(
                scope.requests.filter(transport_outcome="received").values_list(
                    "pk", flat=True
                )
            )
            used = CollectionObservationInput.objects.filter(
                observation__scope_run=scope,
                input_request_id__in=identifiers,
            ).values_list("input_request_id", flat=True)
            requests = CollectionRequest.objects.filter(
                pk__in=identifiers, archive__isnull=False
            ).exclude(pk__in=used)
            for observation in scope.observations.filter(pk__gt=last_observation):
                for request in requests:
                    link_request(
                        observation, request, row_locator=observation.source_identifier
                    )
                from core.collection_resources import project_observation_facts

                project_observation_facts(observation)
        scope.cursor, scope.outcome = cursor, outcome
        scope.enumeration_complete = enumeration_complete
        scope.execution_state = "completed" if enumeration_complete else "yielded"
        scope.coverage_state = (
            "complete"
            if enumeration_complete
            and outcome in {"complete", "observed", "success", "ok"}
            else "partial"
            if not enumeration_complete
            else "unavailable"
        )
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
    with fenced_run(claim, now=now) as (job, run):
        now = now or timezone.now()
        run.status = status
        run.completed_at = (
            None
            if (job.purpose == "catalog" or job.instruction_version == 2)
            and status == "partial"
            else now
        )
        run.report = {**run.report, **(report or {})}
        require(
            run.report.get("definition_sha256") == job.definition_sha256,
            "instruction provenance cannot change",
        )
        # Only an adapter proving complete physical accounting may release unused
        # reservation. Interrupted/ambiguous attempts retain their conservative cap.
        reservation = run.report.get("campaign_usage")
        campaign = job.campaign_settings
        if (
            isinstance(campaign, dict)
            and campaign.get("kind") == "backfiller-data-source-v1"
            and reservation
            and status == "success"
            and (report or {}).get("physical_accounting_complete") is True
            and request_count is not None
            and all(
                key in reservation
                for key in (
                    "reserved_before_current",
                    "recorded_before_current",
                    "current_invocation_reservation",
                )
            )
        ):
            # The successor proves only its own physical usage. Earlier partial
            # or expired invocations retain their reservation, even when a
            # catalog attempt reuses the same run row after a hard interruption.
            current_requests = request_count - reservation["recorded_before_current"]
            require(
                0 <= current_requests <= reservation["current_invocation_reservation"],
                "accounted requests exceed current invocation reservation",
            )
            run.report["campaign_usage"] = {
                **reservation,
                "reserved_requests": reservation["reserved_before_current"]
                + current_requests,
                "accounting": "complete_current_invocation_accounting",
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
        complete_attempt(
            claim,
            run,
            status=status,
            request_count=request_count,
            accounting_complete=(report or {}).get("physical_accounting_complete")
            is True,
            error_code=error_code,
            now=now,
        )
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
        ingestion_key=ingestion_key,
        status="aborted",
        started_at=now,
        completed_at=now,
        error_code=reason,
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
            len(scopes) <= job.budgets["items"],
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
