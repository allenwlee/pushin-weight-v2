"""Register immutable instructions; runtime business state lives in PostgreSQL."""

from __future__ import annotations

import copy
import re

from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_store import safe_payload
from core.measurement_taxonomy import digest, require
from core.models import CollectionAttempt, CollectionJob, CollectionRun

OPERATIONS = {
    "match_crosswalk": ("catalog", {"github", "openrouter", "arena", "opencode"}),
    "github_catalog": ("catalog", {"github"}),
    "hf_catalog": ("catalog", {"hf"}),
    "model_inventory": ("catalog", {"github", "hf", "openrouter", "arena"}),
    "model_history": ("catalog", {"github", "hf", "openrouter", "arena"}),
    "collect_metrics": ("metric", None),
    "x_cycle": ("content", {"x"}),
    "x_backfill": ("content", {"x"}),
}
BUDGET_LIMITS = {
    "requests": 10000,
    "bytes": 32 * 1024 * 1024,
    "seconds": 3600,
    "items": 100000,
}


def validate_definition(
    *, source_id, purpose, operation, mode, contract_id, definition
):
    safe_payload(definition)
    if isinstance(definition, dict) and definition.get("version") == 2:
        from core.collection_instructions import validate_options

        validate_options(definition, operation)
        require(operation in OPERATIONS, "unsupported operation")
        expected, sources = OPERATIONS[operation]
        require(
            expected == purpose and (sources is None or source_id in sources),
            "operation/source mismatch",
        )
        require(
            (purpose == "metric") == (contract_id is not None),
            "purpose/contract mismatch",
        )
        require(mode in {"manual", "historical", "recurring"}, "unsupported mode")
        if operation == "match_crosswalk":
            require(mode == "historical", "matching jobs are finite manual operations")
        return digest(
            {
                "source": source_id,
                "purpose": purpose,
                "operation": operation,
                "mode": mode,
                "contract": str(contract_id) if contract_id else None,
                "definition": definition,
            }
        )
    require(
        isinstance(definition, dict) and definition.get("version") == 1,
        "instruction version required",
    )
    require(purpose in {"metric", "catalog", "content"}, "unsupported purpose")
    require(
        (purpose == "metric") == (contract_id is not None), "purpose/contract mismatch"
    )
    require(mode in {"manual", "historical", "recurring"}, "unsupported mode")
    require(operation in OPERATIONS, "unsupported operation")
    if operation == "match_crosswalk":
        require(mode == "historical", "matching jobs are finite manual operations")
    expected, sources = OPERATIONS[operation]
    require(
        expected == purpose and (sources is None or source_id in sources),
        "operation/source mismatch",
    )
    schedule = definition.get("schedule", {})
    require(isinstance(schedule, dict), "schedule object required")
    kind, driver = schedule.get("kind"), schedule.get("driver")
    require(
        driver in {"manual", "shared", "external_render_cron"},
        "schedule driver required",
    )
    if mode == "recurring":
        require(
            kind in {"interval", "daily_utc"} and driver != "manual",
            "recurring schedule required",
        )
        if kind == "interval":
            require(
                type(schedule.get("seconds")) is int
                and 1 <= schedule["seconds"] <= 366 * 86400,
                "invalid interval",
            )
        else:
            require(
                type(schedule.get("hour")) is int and 0 <= schedule["hour"] <= 23,
                "invalid UTC hour",
            )
        if driver == "external_render_cron":
            require(
                purpose == "content" and source_id == "x" and operation == "x_cycle",
                "external driver reserved for X cycle",
            )
    else:
        require(
            kind == "manual" and driver == "manual",
            "manual/historical schedule required",
        )
    budgets = definition.get("budgets", {})
    require(isinstance(budgets, dict), "budget object required")
    for key, maximum in BUDGET_LIMITS.items():
        require(
            type(budgets.get(key)) is int and 0 < budgets[key] <= maximum,
            f"invalid {key} budget",
        )
    require(isinstance(definition.get("scope"), dict), "frozen scope required")
    return digest(
        {
            "source": source_id,
            "purpose": purpose,
            "operation": operation,
            "mode": mode,
            "contract": str(contract_id) if contract_id else None,
            "definition": definition,
        }
    )


def validate_job(job, *, deep=True):
    if job.instruction_version == 2:
        from core.collection_instructions import validate_sealed_job

        validate_sealed_job(job, deep=deep)
    if job.operation in {"archived_run", "legacy_direct"}:
        require(
            job.state == "completed"
            and job.active_run_id is None
            and job.next_due_at is None
            and job.next_retry_at is None
            and job.definition.get("execution", {}).get("executable") is False,
            "non-dispatchable instruction record required",
        )
        require(
            job.definition_sha256
            == digest(
                {
                    "source": job.source_id,
                    "purpose": job.purpose,
                    "operation": job.operation,
                    "mode": job.mode,
                    "contract": str(job.contract_id) if job.contract_id else None,
                    "definition": job.definition,
                }
            ),
            "immutable instruction hash mismatch",
        )
        return
    actual = validate_definition(
        source_id=job.source_id,
        purpose=job.purpose,
        operation=job.operation,
        mode=job.mode,
        contract_id=job.contract_id,
        definition=job.definition,
    )
    require(actual == job.definition_sha256, "immutable instruction hash mismatch")
    for pointer in (job.active_run_id, job.last_attempt_id, job.last_success_id):
        if pointer:
            require(
                CollectionRun.objects.filter(
                    pk=pointer,
                    job=job,
                ).exists(),
                "job/run pointer mismatch",
            )
    if job.last_attempt_attempt_id:
        require(
            CollectionAttempt.objects.filter(
                pk=job.last_attempt_attempt_id, run__job=job
            ).exists(),
            "job/attempt pointer mismatch",
        )


@transaction.atomic
def register_job(
    *,
    job_key,
    source,
    purpose,
    operation,
    mode,
    definition,
    contract=None,
    settings=None,
    targets=(),
):
    require(
        isinstance(job_key, str) and re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", job_key),
        "invalid job key",
    )
    definition = copy.deepcopy(definition)
    identity = validate_definition(
        source_id=source.pk,
        purpose=purpose,
        operation=operation,
        mode=mode,
        contract_id=contract.pk if contract else None,
        definition=definition,
    )
    if definition.get("version") == 2:
        from core.collection_instructions import register_relational_job

        return register_relational_job(
            job_key=job_key,
            source=source,
            purpose=purpose,
            operation=operation,
            mode=mode,
            definition=definition,
            contract=contract,
            identity=identity,
            settings=settings,
            targets=targets,
        )
    require(
        settings is None and not targets, "typed settings require instruction version 2"
    )
    from core.data_source_backfill import campaign_fields

    campaign = campaign_fields(
        definition, contract_id=contract.pk if contract else None
    )
    obj, _ = CollectionJob.objects.get_or_create(
        job_key=job_key,
        defaults={
            "source": source,
            "purpose": purpose,
            "operation": operation,
            "mode": mode,
            "definition": definition,
            "definition_sha256": identity,
            "contract": contract,
            **campaign,
        },
    )
    require(
        obj.definition_sha256 == identity,
        "immutable job identity changed; register a new job",
    )
    require(
        all(getattr(obj, field) == value for field, value in campaign.items()),
        "immutable campaign identity changed",
    )
    validate_job(obj)
    return obj


@transaction.atomic
def set_job_state(job_id, state, *, now=None):
    require(
        state in {"ready", "paused", "completed", "cancelled"}, "unsupported job state"
    )
    now = now or timezone.now()
    job = (
        CollectionJob.objects.select_for_update()
        .select_related("source")
        .get(pk=job_id)
    )
    validate_job(job)
    require(
        job.state not in {"completed", "cancelled"} or job.state == state,
        "terminal job cannot be reactivated",
    )
    if state == "ready":
        require(
            job.purpose == "content"
            or job.operation == "match_crosswalk"
            or job.source.enabled,
            "source is disabled",
        )
        job.next_due_at = now if job.mode == "recurring" else None
    else:
        job.next_due_at = job.next_retry_at = None
        if job.active_run_id:
            run = CollectionRun.objects.select_for_update().get(pk=job.active_run_id)
            resumable = state == "paused" and (
                job.purpose == "catalog" or job.instruction_version == 2
            )
            run.status = "interrupted" if resumable else "aborted"
            run.completed_at = None if resumable else now
            run.execution_state = "interrupted" if resumable else "aborted"
            run.coverage_state = "partial"
            run.lease_expires_at = now
            run.error_code = "job_" + state
            run.save()
            run.attempts.filter(outcome="running").update(
                outcome="interrupted",
                stop_reason="job_" + state,
                lease_expires_at=now,
            )
        job.active_run = None
    job.state = state
    job.save()
    return job
