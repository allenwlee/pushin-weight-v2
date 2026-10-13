"""Register immutable instructions; runtime business state lives in PostgreSQL."""

from __future__ import annotations

import copy
import re

from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_store import safe_payload
from core.measurement_taxonomy import digest, require
from core.models import CollectionJob, CollectionRun

OPERATIONS = {
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


def validate_job(job):
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
                    source_id=job.source_id,
                    purpose=job.purpose,
                    contract_id=job.contract_id,
                ).exists(),
                "job/run pointer mismatch",
            )


@transaction.atomic
def register_job(
    *, job_key, source, purpose, operation, mode, definition, contract=None
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
        },
    )
    require(
        obj.definition_sha256 == identity,
        "immutable job identity changed; register a new job",
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
        require(job.source.enabled, "source is disabled")
        job.next_due_at = now if job.mode == "recurring" else None
    else:
        job.next_due_at = job.next_retry_at = None
        if job.active_run_id:
            run = CollectionRun.objects.select_for_update().get(pk=job.active_run_id)
            run.status = "interrupted" if run.purpose == "catalog" else "aborted"
            run.completed_at = None if run.purpose == "catalog" else now
            run.lease_expires_at = now
            run.error_code = "job_" + state
            run.save()
        job.active_run = None
    job.state = state
    job.save()
    return job
