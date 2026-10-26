"""Short database transactions fence claims, evidence and cursor updates together.

Provider requests run outside these transactions. Callers pass validated payloads
to checkpoint_scope or use fenced_run around their existing database writer.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.benchmark_metric_store import safe_payload
from core.collection_cursors import (
    replace_scope_cursor_history,
    validate_cursor_history,
)
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


def _begin_attempt(run, *, attempt_key, limits, now, source_invocation_id=None):
    """Called only while the owning job/run is locked, before provider work."""
    run.attempts.filter(outcome="running").update(
        outcome="interrupted",
        stop_reason="expired_lease",
    )
    previous = run.attempts.order_by("-ordinal").first()
    return CollectionAttempt.objects.create(
        run=run,
        attempt_key=attempt_key,
        source_invocation_id=source_invocation_id,
        ordinal=previous.ordinal + 1 if previous else 1,
        lease_token=run.lease_token,
        lease_expires_at=run.lease_expires_at,
        started_at=now,
        outcome="running",
        reserved_requests=limits.get("requests"),
        reserved_bytes=limits.get("bytes", limits.get("total_bytes")),
        response_byte_limit=limits.get("response_bytes"),
        effective_seconds=limits.get("seconds"),
        effective_items=limits.get("items", limits.get("models")),
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
    if run._state.adding:
        run.save(force_insert=True)
    else:
        run.save(update_fields=[
            "status", "completed_at", "execution_state", "lease_token",
            "lease_expires_at", "updated_at",
        ])
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
    job_id, *, invocation_id=None, manual_authorized=False, continue_from=None,
    typed=False, now=None,
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
    if typed:
        require(
            (
                job.purpose == "catalog"
                and job.operation in {
                    "model_history", "github_catalog", "model_inventory",
                    "hf_catalog", "match_crosswalk",
                }
                or job.purpose == "metric" and job.operation == "collect_metrics"
                or job.source_id == "x" and job.purpose == "content"
                and job.operation == "x_backfill" and job.mode == "historical"
                and manual_authorized
                or job.source_id == "x" and job.purpose == "content"
                and job.operation == "x_cycle" and job.mode == "recurring"
                and manual_authorized
            )
            and (not bounded_campaign or job.campaign_id is not None),
            "typed claim requires a supported sealed campaign and operation",
        )
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
            active.save(update_fields=[
                "status", "completed_at", "execution_state", "error_code", "updated_at",
            ])
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
    if job.mode == "recurring" and (
        job.instruction_version == 2
        or typed and job.purpose == "metric" and job.operation == "collect_metrics"
    ):
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
    new_run = run is None
    token = uuid.uuid4()
    lease = now + timedelta(seconds=job.budgets["seconds"] + 60)
    if run is None:
        run = CollectionRun(
            job=job,
            ingestion_key=ingestion_key,
            started_at=now,
            scheduled_slot_at=slot,
        )
        if typed and job.source_id == "x" and job.operation == "x_backfill":
            run.physical_bytes_received = 0
    if bounded_campaign and job.campaign_id is None:
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
    if typed and not run._state.adding:
        run.save(update_fields=[
            "status", "completed_at", "execution_state", "lease_token",
            "lease_expires_at", "error_code", "updated_at",
        ])
    else:
        run.save()
    attempt = _begin_attempt(
        run, attempt_key=ingestion_key, limits=job.budgets, now=now,
        source_invocation_id=invocation_id,
    )
    if typed:
        if job.operation == "model_history":
            require(
                not run.scopes.filter(
                    scope_kind__in=["model_coverage", "native_publication_coverage"],
                    resource_observation__isnull=True,
                ).exists(),
                "historical history coverage needs typed adoption before resume",
            )
        compatibility = {"ownership": {}} if any(
            field.name == "ownership" for field in CollectionScopeRun._meta.fields
        ) else {}
        if job.operation == "model_history":
            marker_kind, marker_phase = "history_execution", "typed-history-v1"
        elif job.operation == "github_catalog":
            marker_kind, marker_phase = "catalog_execution", "typed-github-catalog-v1"
        elif job.operation in {"model_inventory", "hf_catalog"}:
            marker_kind, marker_phase = "inventory_execution", "typed-inventory-v1"
        elif job.operation == "collect_metrics":
            marker_kind, marker_phase = "metric_execution", "typed-metric-v1"
        elif job.operation == "match_crosswalk":
            marker_kind, marker_phase = "match_execution", "typed-product-match-v1"
        elif job.source_id == "x" and job.operation == "x_backfill":
            marker_kind, marker_phase = "x_backfill_execution", "typed-backfill-v1"
        elif job.source_id == "x" and job.operation == "x_cycle":
            marker_kind, marker_phase = "x_cycle_execution", "typed-x-cycle-v1"
        else:
            raise ValueError("typed collection claim has no execution marker")
        if (
            job.operation == "github_catalog"
            or job.operation == "model_inventory" and job.source_id == "openrouter"
            or job.operation == "collect_metrics"
            or job.operation == "match_crosswalk"
            or job.source_id == "x" and job.operation == "x_backfill"
            or job.source_id == "x" and job.operation == "x_cycle"
        ) and not run.scopes.filter(
            scope_kind=marker_kind, scope_key="execution", phase=marker_phase,
        ).exists():
            retained_fields = {field.name for field in CollectionRun._meta.fields}
            require(
                (new_run or not (job.source_id == "x" and job.operation in {"x_backfill", "x_cycle"}))
                and not run.scopes.exists()
                and ("report" not in retained_fields or not run.report)
                and ("invocations" not in retained_fields or not run.invocations)
                and run.legacy_archive_id is None,
                "historical collection run requires typed adoption before resume",
            )
        marker, _ = CollectionScopeRun.objects.get_or_create(
            run=run, scope_kind=marker_kind, scope_key="execution",
            defaults={"phase": marker_phase, **compatibility},
        )
        require(
            marker.phase == marker_phase
            and marker.resource_observation_id is None,
            "typed collection execution marker changed",
        )
    if bounded_campaign and job.purpose == "metric" and job.last_attempt_id:
        previous = CollectionRun.objects.select_for_update().get(pk=job.last_attempt_id)
        if previous.status == "partial" and previous.completed_at is not None:
            from core.collection_pages import copy_continuation_scopes

            copy_continuation_scopes(previous, run)
            run.continuation_of = previous
            run.save(update_fields=["continuation_of", "updated_at"])
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
            previous.job_id == job.pk and previous.completed_at is not None,
            "continuation identity mismatch",
        )
        require(
            previous.pk == job.last_attempt_id,
            "continuation must use the preceding attempt",
        )
        from core.collection_pages import copy_continuation_scopes

        copy_continuation_scopes(previous, run)
        run.continuation_of = previous
        run.save(update_fields=["continuation_of", "updated_at"])
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


def x_scope_ownership(scope):
    """Read a pinned X query from typed owners, with legacy rollout fallback."""
    if getattr(scope, "job_target_id", None) is None:
        require(
            scope.run.job.instruction_version == 1,
            "sealed X scope requires a typed query target",
        )
        x_query_instruction(scope.ownership)
        return scope.ownership
    target = scope.job_target
    recurring_cycle = scope.run.job.operation == "x_cycle" and scope.run.job.instruction_version == 2
    require(
        scope.scope_kind == "x_query"
        and target.job_id == scope.run.job_id
        and target.target_key == scope.scope_key
        and target.target_kind == "query"
        and target.resolution_state == "resolved"
        and target.search_query_id is not None
        and (
            target.requested_start_at is None and target.requested_end_at is None
            if recurring_cycle
            else (
                scope.requested_start_at == target.requested_start_at
                and scope.requested_end_at == target.requested_end_at
            )
        )
        and scope.requested_start_at is not None
        and scope.requested_end_at is not None,
        "X scope typed query pin differs from its run",
    )
    start = scope.requested_start_at.timestamp()
    end = scope.requested_end_at.timestamp()
    require(start.is_integer() and end.is_integer(), "X scope request epoch is not whole")
    ownership = {
        "call_id": target.target_role,
        "query": target.search_query.query_text,
        "since_epoch": int(start),
        "until_epoch": int(end),
    }
    x_query_instruction(ownership)
    return ownership


def ensure_x_query_target(job, scope_key, *, query_text, call_id, start_at, end_at):
    """Pin one query and call role per job scope; never modify a sealed target."""
    recurring_cycle = job.operation == "x_cycle" and job.instruction_version == 2
    query_id = (
        ("x-cycle:" if recurring_cycle else "x-backfill:")
        + hashlib.sha256(query_text.encode()).hexdigest()
    )
    search_query, _ = SearchQuery.objects.get_or_create(
        query_id=query_id, defaults={"query_text": query_text}
    )
    require(search_query.query_text == query_text, "X query identity changed")
    target = job.targets.filter(target_key=scope_key).first()
    if target is None:
        CollectionJob.objects.select_for_update().only("pk").get(pk=job.pk)
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
    target_start, target_end = (None, None) if recurring_cycle else (start_at, end_at)
    require(
        target.target_kind == "query"
        and target.target_role == call_id
        and target.search_query_id == search_query.pk
        and target.requested_start_at == target_start
        and target.requested_end_at == target_end,
        "frozen X query target differs from scope ownership",
    )
    return target


def record_scope_request_uses(scope, envelopes):
    """Pin ordered page uses, including an earlier run's captured reply."""
    from core.benchmark_metric_store import aware_instant
    from core.models import CollectionRequest, CollectionScopeRequestUse

    wanted = [
        (ordinal, envelope)
        for ordinal, envelope in enumerate(envelopes)
        if envelope.get("prefetch_request_id")
    ]
    if not wanted:
        require(not scope.request_uses.exists(), "typed request use exceeds scope receipt")
        return 0
    ids = [str(envelope["prefetch_request_id"]) for _, envelope in wanted]
    require(len(ids) == len(set(ids)), "scope repeats the same captured request")
    requests = {
        str(request.pk): request
        for request in CollectionRequest.objects.filter(pk__in=ids)
        .select_related("scope_run__run")
        .only("pk", "transport_outcome", "http_status", "archive_id",
              "request_category", "scope_run__run__job_id")
    }
    require(len(requests) == len(ids), "scope captured request is missing")
    existing = {
        str(use.request_id): use
        for use in scope.request_uses.all()
    }
    require(set(existing) <= set(ids), "typed request use exceeds scope receipt")
    missing = []
    for ordinal, envelope in wanted:
        request = requests[str(envelope["prefetch_request_id"])]
        observed_at = aware_instant(envelope["observed_at"])
        require(
            request.scope_run.run.job_id == scope.run.job_id
            and request.transport_outcome == "received"
            and request.http_status == 200
            and (
                request.archive_id is not None
                or request.request_category == "x_backfill_staging"
            )
            and str(request.scope_run.run_id) == envelope["prefetch_request_run_id"],
            "captured request is outside the scope's collection job",
        )
        use = existing.get(str(request.pk))
        if use:
            require(
                use.ordinal == ordinal and use.observed_at == observed_at,
                "scope captured request order or time changed",
            )
        else:
            missing.append(
                CollectionScopeRequestUse(
                    scope_run=scope, request=request,
                    ordinal=ordinal, observed_at=observed_at,
                )
            )
    CollectionScopeRequestUse.objects.bulk_create(missing)
    return len(missing)


def _validate_typed_hf_scope(job, run, kind, key, ownership, observation):
    """Match transient HF scope claims to frozen selection and typed parents."""
    require(
        job.source_id == "hf" and job.purpose == "catalog"
        and job.operation in {"model_inventory", "hf_catalog"}
        and kind in {"namespace", "hf_metadata", "hf_profile"},
        "typed checkpoint is limited to HF inventory scopes",
    )
    frozen = job.scope.get("hf_scope")
    require(isinstance(frozen, dict), "frozen HF inventory scope required")
    entries = frozen.get("namespaces")
    require(isinstance(entries, list), "frozen HF namespaces required")
    if kind == "namespace":
        require(
            observation is None and ownership in entries
            and key == ownership.get("namespace"),
            "HF namespace checkpoint differs from frozen selection",
        )
        return
    if kind == "hf_metadata":
        require(
            observation is not None and observation.run_id == run.pk
            and observation.observation_kind == "creation_inventory"
            and observation.scope_run is not None
            and observation.scope_run.scope_kind == "namespace"
            and ownership == {
                "namespace": observation.scope_run.scope_key,
                "repository": observation.source_identifier,
            }
            and any(entry.get("namespace") == ownership["namespace"] for entry in entries)
            and key in {
                observation.source_identifier + ":detail",
                observation.source_identifier + ":expanded",
            },
            "HF metadata checkpoint differs from its captured listing",
        )
        return
    from core.models import Account

    require(
        observation is None and set(ownership) == {"account_id"}
        and any(entry.get("namespace") == key for entry in entries)
        and Account.objects.filter(
            pk=ownership["account_id"], data_source_id="hf",
            normalized_identifier=key.casefold(),
        ).exists(),
        "HF profile checkpoint differs from its frozen account",
    )


def _validate_typed_projection_scope(job, kind, key, ownership, contract, observation):
    """Pin a typed projection parent to the frozen source and contract."""
    require(
        kind == "numeric_projection" and contract is not None
        and observation is None and job.source_id in contract.source_configuration,
        "typed numeric projection requires its source contract",
    )
    require(
        (
            job.purpose == "catalog"
            and key == str(contract.pk)
            and ownership == {
                "contract_id": str(contract.pk),
                "contract_hash": contract.contract_hash,
            }
        ) or (
            job.purpose == "metric" and job.operation == "collect_metrics"
            and job.contract_id == contract.pk and key == "saved-evidence"
            and ownership == {"contract_hash": contract.contract_hash}
        ),
        "typed numeric projection identity differs from frozen contract",
    )


def _validate_typed_model_history_scope(
    job, run, kind, key, ownership, start_at, end_at, observation,
):
    """Tie coverage checkpoints to the sealed cohort and typed runtime window."""
    from core.benchmark_metric_store import aware_instant

    frozen = job.scope
    require(
        job.purpose == "catalog" and job.operation == "model_history"
        and job.source_id in {"hf", "github", "openrouter", "arena"}
        and observation is None and isinstance(frozen, dict)
        and isinstance(frozen.get("cohort_hash"), str),
        "typed model history needs its sealed cohort",
    )
    runtime = run.scopes.filter(
        scope_kind="publication_runtime", scope_key="window",
    ).first()
    if kind == "publication_runtime":
        days = frozen.get("publication_recheck_days", 7)
        require(
            job.source_id in {"openrouter", "arena"}
            and key == "window"
            and frozen.get("publication_window_policy") == "rolling-completed-days-v1"
            and ownership == {
                "policy": frozen["publication_window_policy"],
                "cohort_hash": frozen["cohort_hash"],
            }
            and type(days) is int and 1 <= days <= 90
            and start_at is not None and end_at is not None,
            "typed publication window differs from sealed policy",
        )
        start, end = aware_instant(start_at), aware_instant(end_at)
        require(
            start.astimezone(UTC).time() == datetime.min.time()
            and end.astimezone(UTC).time() == datetime.min.time()
            and end - start == timedelta(days=days),
            "typed publication window must span completed UTC days",
        )
        return
    if kind == "model_coverage":
        models = frozen.get("models", [])
        selected = [row for row in models if row.get("product_key") == key]
        require(len(selected) == 1, "typed model coverage has no unique frozen model")
        model = selected[0]
        require(
            ownership == {
                "product_key": key,
                "cohort_hash": frozen["cohort_hash"],
                "provider_pins": model.get("provider_pins", []),
            }
            and start_at is not None and end_at is not None
            and aware_instant(start_at) == aware_instant(model["creation"]["at"])
            and aware_instant(end_at) == (
                runtime.requested_end_at if runtime is not None
                else aware_instant(frozen["cutoff"])
            ),
            "typed model coverage differs from frozen request window",
        )
        return
    require(
        kind == "native_publication_coverage" and key == "selection"
        and job.source_id in {"openrouter", "arena"}
        and frozen.get("models", []) == []
        and bool(frozen.get("native_publication_identifiers"))
        and ownership == {"cohort_hash": frozen["cohort_hash"]}
        and start_at is not None and end_at is not None
        and aware_instant(start_at) == (
            runtime.requested_start_at if runtime is not None
            else aware_instant(frozen["global_start_at"])
        )
        and aware_instant(end_at) == (
            runtime.requested_end_at if runtime is not None
            else aware_instant(frozen["cutoff"])
        ),
        "typed native publication coverage differs from frozen selection",
    )


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
    requested_start_date=None,
    requested_end_date=None,
    projection_contract=None,
    resource_observation=None,
    typed=False,
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
    if cursor_history is not None:
        validate_cursor_history(cursor_history)
    require(isinstance(ownership, dict), "scope ownership object required")
    if typed:
        require(
            envelopes is None,
            "typed checkpoint cannot use legacy envelopes",
        )
    if projection_contract is not None:
        require(
            scope_kind in {
                "numeric_projection", "publication_selection", "metric_fetch",
                "archive_projection",
            }
            and (
                scope_kind == "metric_fetch"
                or ownership.get("contract_hash") == projection_contract.contract_hash
            )
            and (
                "contract_id" not in ownership
                or ownership["contract_id"] == str(projection_contract.pk)
            ),
            "projection contract pin changed",
        )
    if scope_kind == "publication_selection":
        require(
            projection_contract is not None
            and resource_observation is not None
            and set(ownership) == {"contract_hash", "publication_observation_id"}
            and ownership["publication_observation_id"] == resource_observation.pk
            and scope_key == digest([
                resource_observation.pk, projection_contract.contract_hash,
            ]),
            "publication selection identity changed",
        )
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
        from core.collection_datasets import resolve_dataset

        if typed:
            if scope_kind == "metric_fetch":
                require(
                    run.job.purpose == "metric"
                    and (
                        run.job.operation == "collect_metrics"
                        or run.job.operation == "legacy_direct"
                        and run.job.definition.get("execution", {}).get("driver") == "persist_source"
                    )
                    and run.job.contract_id == projection_contract.pk
                    and run.job.source_id in projection_contract.source_configuration
                    and scope_key == "source"
                    and ownership == {"contract_id": str(projection_contract.pk)}
                    and resource_observation is None,
                    "typed metric fetch differs from the frozen contract",
                )
            elif scope_kind in {"publication_window", "publication_selection"}:
                from core.model_history_publications import validate_typed_scope

                validate_typed_scope(
                    run.job, run, scope_kind, scope_key, ownership,
                    projection_contract, resource_observation,
                )
            elif scope_kind in {"archive_snapshot", "archive_projection"}:
                from core.model_history_archives import validate_typed_scope

                validate_typed_scope(
                    run.job, run, scope_kind, scope_key, ownership,
                    projection_contract, resource_observation,
                )
            elif scope_kind == "model_catalog" and run.job.source_id == "openrouter":
                require(projection_contract is None, "unexpected inventory contract")
                from core.model_inventory import validate_typed_scope

                validate_typed_scope(
                    run.job, run, scope_kind, scope_key, ownership,
                    resource_observation,
                )
            elif scope_kind == "product_match":
                matches = [
                    choice for choice in run.job.scope.get("matches", [])
                    if choice.get("candidate_id") == scope_key
                ]
                require(
                    run.job.operation == "match_crosswalk"
                    and run.job.purpose == "catalog"
                    and projection_contract is None
                    and resource_observation is None
                    and len(matches) == 1
                    and ownership == {
                        "product_key": matches[0]["product_key"],
                        "input_sha256": matches[0]["input_sha256"],
                    },
                    "typed product match differs from frozen candidate",
                )
            elif scope_kind == "staged_post_copy":
                require(projection_contract is None, "unexpected promotion contract")
                from monitor.backfill_promotion import validate_typed_scope

                validate_typed_scope(
                    run.job, run, scope_kind, scope_key, ownership,
                    resource_observation,
                )
            elif scope_kind == "numeric_projection":
                _validate_typed_projection_scope(
                    run.job, scope_kind, scope_key, ownership,
                    projection_contract, resource_observation,
                )
            elif (
                run.job.source_id == "github" and run.job.purpose == "catalog"
                and run.job.operation == "github_catalog"
            ):
                require(projection_contract is None, "unexpected GitHub scope contract")
                from core.github_catalog import validate_typed_scope

                validate_typed_scope(
                    run.job, run, scope_kind, scope_key, ownership,
                    resource_observation,
                )
            elif scope_kind == "archive_import":
                require(
                    run.job.purpose == "catalog"
                    and run.job.operation == "model_history"
                    and projection_contract is None
                    and resource_observation is None
                    and set(ownership) == {"dataset_id", "contract_id"}
                    and ownership["contract_id"]
                    == run.job.scope.get("numeric_contract_id"),
                    "archive import must use the frozen history contract",
                )
            elif scope_kind == "x_query" and run.job.operation == "x_backfill":
                require(
                    run.job.source_id == "x"
                    and run.job.purpose == "content"
                    and projection_contract is None
                    and resource_observation is None
                    and sum(
                        unit.get("scope_kind") == "x_query"
                        and unit.get("scope_key") == scope_key
                        and unit.get("ownership") == ownership
                        for unit in run.job.scope.get("units", [])
                        if isinstance(unit, dict)
                    ) == 1,
                    "typed X query differs from the frozen backfill unit",
                )
            elif scope_kind in {
                "publication_runtime", "model_coverage", "native_publication_coverage",
            }:
                require(projection_contract is None, "unexpected history scope contract")
                _validate_typed_model_history_scope(
                    run.job, run, scope_kind, scope_key, ownership,
                    requested_start_at, requested_end_at, resource_observation,
                )
            elif (
                run.job.operation == "model_history" and scope_kind in {
                    "hf_history_head", "hf_repository_history", "repository_history",
                    "repository_events", "release_assets", "repository_tree",
                    "repository_file",
                }
            ):
                require(projection_contract is None, "unexpected native-history contract")
                from core.model_native_history import validate_typed_scope

                validate_typed_scope(
                    run.job, run, scope_kind, scope_key, ownership,
                    resource_observation,
                )
            else:
                require(projection_contract is None, "unexpected typed scope contract")
                _validate_typed_hf_scope(
                    run.job, run, scope_kind, scope_key, ownership,
                    resource_observation,
                )
        dataset = resolve_dataset(run.job.source_id, ownership)
        target = None
        if scope_kind == "product_match":
            from core.collection_matching import ensure_product_match_target

            target = ensure_product_match_target(run.job, scope_key, ownership)
        if scope_kind == "x_query":
            target = ensure_x_query_target(
                run.job, scope_key, query_text=query_text, call_id=call_id,
                start_at=requested_start_at, end_at=requested_end_at,
            )
        if typed:
            compatibility = {"ownership": {}} if any(
                field.name == "ownership" for field in CollectionScopeRun._meta.fields
            ) else {}
        else:
            compatibility = {"ownership": ownership}
        scope, created = CollectionScopeRun.objects.get_or_create(
            run=run,
            scope_kind=scope_kind,
            scope_key=scope_key,
            defaults={
                **compatibility, "job_target": target,
                "projection_contract": projection_contract,
                "resource_observation": resource_observation,
            },
        )
        if not typed:
            require(created or scope.ownership == ownership, "scope ownership pin changed")
        elif scope_kind == "metric_fetch":
            require(
                created or scope.phase == "typed-metric-fetch-v1",
                "historical metric fetch needs typed adoption before resume",
            )
            scope.phase = "typed-metric-fetch-v1"
        elif typed and scope_kind == "product_match":
            require(
                created or scope.phase == "typed-product-match-v1",
                "historical match scope needs typed adoption before resume",
            )
            scope.phase = "typed-product-match-v1"
        if dataset is not None:
            require(scope.source_dataset_id in (None, dataset.pk), "scope dataset pin changed")
            scope.source_dataset = dataset
        require(
            created or scope.job_target_id in (None, target.pk if target else None),
            "scope target pin changed",
        )
        if target and scope.job_target_id is None:
            scope.job_target = target
        require(
            created or scope.projection_contract_id in (
                None, projection_contract.pk if projection_contract else None
            ),
            "scope projection contract changed",
        )
        if projection_contract and scope.projection_contract_id is None:
            scope.projection_contract = projection_contract
        if resource_observation is not None:
            require(
                scope.resource_observation_id in (None, resource_observation.pk),
                "scope source observation changed",
            )
            scope.resource_observation = resource_observation
        if typed and scope_kind not in {
            "model_coverage", "native_publication_coverage",
        }:
            require(
                scope.resource_observation_id == (
                    resource_observation.pk if resource_observation is not None else None
                ),
                "typed scope has a different source observation",
            )
        for field, value in (
            ("requested_start_at", requested_start_at),
            ("requested_end_at", requested_end_at),
            ("requested_start_date", requested_start_date),
            ("requested_end_date", requested_end_date),
        ):
            if value is not None:
                if field.endswith("_at"):
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
        if typed and scope_kind in {
            "model_coverage", "native_publication_coverage",
        }:
            from core.models import Product

            result = scope.resource_observation
            require(
                result is not None and result.run_id == run.pk
                and result.scope_run_id == scope.pk
                and result.observation_kind == "coverage"
                and result.source_subject_kind == (
                    "model" if scope_kind == "model_coverage" else "aggregate"
                )
                and (
                    Product.objects.filter(
                        pk=result.product_id, product_key=scope_key,
                    ).exists()
                    if scope_kind == "model_coverage" else result.product_id is None
                ),
                "typed history coverage has no owned result observation",
            )
        if scope.source_dataset_id is not None:
            scope.observations.filter(
                pk__gt=last_observation, source_dataset__isnull=True,
            ).update(source_dataset=scope.source_dataset)
        if envelopes is not None:
            record_scope_request_uses(scope, envelopes)
            if scope_kind == "x_query":
                from core.collection_pages import project_page_receipts

                project_page_receipts(scope, envelopes, cursor=cursor)
        requests = ()
        if not typed and (envelopes or scope.requests.exists()):
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
        # Imported observations also own typed facts. A captured HTTP request
        # is optional evidence, not a prerequisite for projecting those facts.
        from core.collection_resources import project_observation_facts

        if not typed:
            for observation in scope.observations.filter(pk__gt=last_observation):
                for request in requests:
                    link_request(
                        observation, request, row_locator=observation.source_identifier
                    )
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
            replace_scope_cursor_history(scope, cursor_history)
        if envelopes is not None and scope_kind != "x_query":
            scope.envelopes = envelopes
        if raw_count is not None:
            scope.raw_count = raw_count
        if typed:
            scope.save(update_fields=[
                "source_dataset", "job_target", "projection_contract",
                "resource_observation", "result_run", "phase",
                "admission_outcome", "error_code",
                "requested_start_at", "requested_end_at",
                "requested_start_date", "requested_end_date",
                "cursor", "outcome", "enumeration_complete", "execution_state",
                "coverage_state", "raw_count",
            ])
        else:
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
    typed=False,
    physical_accounting_complete=None,
    now=None,
):
    require(
        status in {"success", "partial", "failed", "aborted"},
        "terminal/yield outcome required",
    )
    if typed:
        require(
            report is None and type(physical_accounting_complete) is bool,
            "typed completion needs explicit physical accounting and no legacy report",
        )
    else:
        require(
            physical_accounting_complete is None,
            "legacy completion keeps its existing accounting receipt",
        )
        safe_payload(report or {})
    with fenced_run(claim, now=now) as (job, run):
        if typed:
            metric_collection = (
                job.purpose == "metric" and job.operation == "collect_metrics"
                and job.contract_id is not None
                and job.source_id in job.contract.source_configuration
                and request_count is not None
            )
            model_history = (
                job.purpose == "catalog" and job.operation == "model_history"
                and job.source_id in {"hf", "github", "openrouter", "arena"}
                and request_count is not None
            )
            github_catalog = (
                job.source_id == "github" and job.purpose == "catalog"
                and job.operation == "github_catalog"
                and request_count is not None
            )
            x_backfill = (
                job.source_id == "x" and job.purpose == "content"
                and job.operation == "x_backfill" and request_count is not None
            )
            x_cycle = (
                job.source_id == "x" and job.purpose == "content"
                and job.operation == "x_cycle" and request_count is not None
            )
            product_match = (
                job.purpose == "catalog" and job.operation == "match_crosswalk"
                and request_count == 0
            )
            require(
                (job.purpose == "catalog" and (
                    job.source_id == "hf" and job.operation in {"model_inventory", "hf_catalog"}
                    or job.source_id == "openrouter" and job.operation == "model_inventory"
                ))
                or metric_collection or model_history or github_catalog or x_backfill
                or x_cycle
                or product_match,
                "typed completion needs a supported collection operation",
            )
        now = now or timezone.now()
        run.status = status
        run.completed_at = (
            None
            if (job.purpose == "catalog" or job.instruction_version == 2)
            and status == "partial"
            else now
        )
        if not typed:
            supplied_report = dict(report or {})
            require(
                supplied_report.pop("definition_sha256", job.definition_sha256)
                == job.definition_sha256
                and run.report.get("definition_sha256", job.definition_sha256)
                == job.definition_sha256,
                "instruction provenance cannot change",
            )
            run.report = {**run.report, **supplied_report}
            run.report.pop("definition_sha256", None)
            # Only an adapter proving complete physical accounting may release
            # unused reservation. Ambiguous attempts retain their cap.
            reservation = run.report.get("campaign_usage") if job.campaign_id is None else None
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
        changed = ["status", "completed_at", "error_code", "updated_at"]
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
                changed.append(field)
        require(
            run.success_count <= run.selected_count,
            "successful count exceeds selected count",
        )
        if typed:
            run.save(update_fields=changed)
        else:
            run.save()
        complete_attempt(
            claim,
            run,
            status=status,
            request_count=request_count,
            accounting_complete=(
                physical_accounting_complete if typed
                else (report or {}).get("physical_accounting_complete") is True
            ),
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
def record_rejection(job_id, *, invocation_id, reason, report=None, typed=False, now=None):
    """A receipt does not acquire an execution lease or alter active pointers."""
    now = now or timezone.now()
    job = CollectionJob.objects.select_for_update().get(pk=job_id)
    require(
        job.purpose == "content", "rejected invocation receipts are content attempts"
    )
    if typed:
        require(
            job.source_id == "x" and job.operation == "x_backfill",
            "typed rejection requires a bounded X backfill",
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
    if typed:
        from core.collection_capture import archive_document

        diagnostic = {
            **(report or {}),
            "definition_sha256": job.definition_sha256,
            "invocation_id": invocation_id,
            "provider_usage": None,
        }
        archive = archive_document(
            json.dumps(
                {"report": diagnostic, "error_code": reason},
                sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode(),
            encoding="selected-json-canonical-v1",
            capture_kind="x_backfill_rejection",
        )
        run = CollectionRun.objects.create(
            job=job, ingestion_key=ingestion_key, status="aborted",
            execution_state="aborted", started_at=now, completed_at=now,
            error_code=reason, legacy_archive=archive,
        )
        CollectionAttempt.objects.create(
            run=run, attempt_key=ingestion_key,
            source_invocation_id=invocation_id, ordinal=1,
            started_at=now, finished_at=now, outcome="aborted",
            stop_reason=reason,
        )
        return run
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


def import_scope_checkpoints(
    claim: RunClaim, *, definition_sha256, scopes, provenance, typed=False,
):
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
        if typed:
            require(
                job.source_id == "x" and job.operation == "x_backfill",
                "typed checkpoint import requires X backfill",
            )
            import_key = digest([str(run.pk), provenance, scopes])
            prior = run.scopes.filter(
                scope_kind="x_checkpoint_import", scope_key=import_key,
                phase="typed-import-v1",
            ).first()
            if prior is not None:
                require(
                    prior.legacy_archive_id is not None,
                    "typed checkpoint import evidence is missing",
                )
                return run
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
            if typed:
                from core.collection_pages import append_page_receipt

                receipts = scope.get("envelopes", [])
                require(isinstance(receipts, list), "checkpoint pages must be a list")

                def retain_pages(_, stored, pages=receipts):
                    for page in pages:
                        append_page_receipt(stored, page)

                checkpoint_scope(
                    claim,
                    **{key: value for key, value in scope.items() if key != "envelopes"},
                    typed=True,
                    write=retain_pages if receipts else None,
                )
                continue
            checkpoint_scope(claim, **scope)
        if typed:
            from core.collection_capture import archive_document

            archive = archive_document(
                json.dumps(
                    {
                        "definition_sha256": definition_sha256,
                        "provenance": provenance,
                        "imported_at": timezone.now().isoformat(),
                        "historical_attempt_timestamps": None,
                        "scope_count": len(scopes),
                    },
                    sort_keys=True, separators=(",", ":"), allow_nan=False,
                ).encode(),
                encoding="selected-json-canonical-v1",
                capture_kind="x_checkpoint_import",
            )
            compatibility = {"ownership": {}} if any(
                field.name == "ownership" for field in CollectionScopeRun._meta.fields
            ) else {}
            CollectionScopeRun.objects.create(
                run=run, scope_kind="x_checkpoint_import", scope_key=import_key,
                phase="typed-import-v1", outcome="complete",
                enumeration_complete=True, execution_state="completed",
                coverage_state="complete", legacy_archive=archive,
                **compatibility,
            )
            return run
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
