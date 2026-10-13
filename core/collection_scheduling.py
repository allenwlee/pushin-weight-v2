"""Explicit scheduling authority, UTC slots and cooldowns over persisted jobs."""

import uuid
from datetime import UTC, timedelta
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from core.collection_jobs import validate_job
from core.collection_state import BusyJob
from core.measurement_taxonomy import require
from core.models import CollectionJob, CollectionRun, DataSource


def metric_authority(source, contract_id):
    return source.metadata.get("collection_job_authorities", {}).get(str(contract_id))


@transaction.atomic
def take_metric_authority(job_id):
    """Registration alone does not replace the current benchmark scheduler."""
    job = (
        CollectionJob.objects.select_for_update()
        .select_related("source")
        .get(pk=job_id)
    )
    validate_job(job)
    require(
        job.operation == "collect_metrics" and job.mode == "recurring",
        "recurring metric job required",
    )
    source = DataSource.objects.select_for_update().get(pk=job.source_id)
    pointers = dict(source.metadata.get("collection_job_authorities", {}))
    old = pointers.get(str(job.contract_id))
    require(old in (None, str(job.pk)), "another job owns metric dispatch")
    pointers[str(job.contract_id)] = str(job.pk)
    source.metadata = {**source.metadata, "collection_job_authorities": pointers}
    source.save(update_fields=["metadata"])
    return job


def schedule_slot(job, now):
    now = now.astimezone(UTC)
    schedule = job.definition["schedule"]
    if schedule["kind"] == "daily_utc":
        slot = now.replace(hour=schedule["hour"], minute=0, second=0, microsecond=0)
        return slot, slot + timedelta(days=1)
    seconds = schedule["seconds"]
    slot = timezone.datetime.fromtimestamp(
        int(now.timestamp()) // seconds * seconds, tz=UTC
    )
    return slot, slot + timedelta(seconds=seconds)


def due_job(job, *, now=None):
    now = now or timezone.now()
    validate_job(job)
    reason, slot, following = "due", None, None
    if job.mode != "recurring" or job.definition["schedule"]["driver"] != "shared":
        reason = "external_or_manual_driver"
    elif job.state != "ready" or not job.source.enabled:
        reason = "paused_or_disabled"
    elif job.purpose == "metric" and (
        not settings.BENCHMARK_COLLECTION_ENABLED
        or not job.contract.source_configuration[job.source_id].get(
            "scheduling_enabled", False
        )
    ):
        reason = "metric_activation_disabled"
    elif job.purpose == "metric" and metric_authority(
        job.source, job.contract_id
    ) != str(job.pk):
        reason = "legacy_scheduler_owns_dispatch"
    elif (
        job.active_run_id
        and job.active_run.status == "running"
        and job.active_run.lease_expires_at > now
    ):
        reason = "active_lease"
    elif job.next_retry_at and job.next_retry_at > now:
        reason = "cooldown"
    else:
        slot, following = schedule_slot(job, now)
        if slot > now or (job.next_due_at and job.next_due_at > now):
            reason = "before_slot"
        elif job.last_success_id and job.last_success.started_at >= slot:
            reason = "slot_succeeded"
        elif (
            job.purpose == "metric"
            and CollectionRun.objects.filter(
                source_id=job.source_id,
                contract_id=job.contract_id,
                status="success",
                started_at__gte=slot,
            ).exists()
        ):
            reason = "legacy_slot_succeeded"
    return {
        "job_id": str(job.pk),
        "source": job.source_id,
        "operation": job.operation,
        "due": reason == "due",
        "reason": reason,
        "slot": slot.isoformat() if slot else None,
        "following_slot": following.isoformat() if following else None,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
    }


def execute_due_job(job, decision, budget):
    """Use existing adapters; X's Render cron never enters this dispatcher."""
    import os

    from core.github_catalog import execute_github_catalog
    from core.github_metadata_client import GitHubMetadataClient
    from core.model_history_collection import execute_model_history
    from core.model_inventory import execute_model_inventory

    if job.operation == "collect_metrics":
        now = timezone.now().astimezone(UTC)
        config = job.contract.source_configuration[job.source_id]
        end = now.date() - timedelta(
            days=config.get("completed_day_lag", 1)
            if job.source_id == "openrouter"
            else 0
        )
        start = (
            end - timedelta(days=config.get("recheck_days", 7) - 1)
            if job.source_id == "openrouter"
            else end
        )
        before = budget.remaining
        try:
            call_command(
                "collect_benchmark_metrics",
                contract=str(job.contract_id),
                source=job.source_id,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                job=str(job.pk),
                slot=decision["slot"],
                batch_id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL, f"pw-job:{job.pk}:{decision['slot']}"
                    )
                ),
                max_requests=min(100, before),
                max_seconds=max(1, min(300, int(budget.deadline - budget.clock()))),
                max_bytes=budget.max_bytes - budget.total_bytes_read,
                apply=True,
                stdout=StringIO(),
            )
        finally:
            job.refresh_from_db()
            if job.last_attempt_id:
                budget.remaining -= job.last_attempt.request_count
                budget.total_bytes_read += job.last_attempt.source_metadata.get(
                    "physical_bytes_received", 0
                )
        return job.last_attempt
    if job.operation == "github_catalog":
        return execute_github_catalog(
            job.pk,
            client=GitHubMetadataClient(
                budget, key=os.environ.get("PUSHINWEIGHT_GITHUB_API_TOKEN")
            ),
        )
    if job.operation in {"model_inventory", "hf_catalog"}:
        return execute_model_inventory(
            job.pk, budget=budget, key=os.environ.get("BENCHMARK_OPENROUTER_API_KEY")
        )
    if job.operation == "model_history":
        return execute_model_history(
            job.pk, budget=budget, key=os.environ.get("BENCHMARK_OPENROUTER_API_KEY")
        )
    raise ValueError("external or unsupported dispatcher operation")


def dispatch_due(
    *, budget=None, now=None, execute=False, job_id=None, executor=None, limit=100
):
    from core.collection_budgets import charge, job_budget
    from scripts.benchmark_download_collector.sources import SourceError

    require(type(limit) is int and 1 <= limit <= 100, "invalid dispatch job cap")
    now = now or timezone.now()
    jobs = CollectionJob.objects.select_related(
        "source", "contract", "active_run", "last_success"
    ).order_by("created_at", "job_key")
    if job_id:
        jobs = jobs.filter(pk=job_id)
    # Numeric work precedes catalog maintenance in a bounded invocation.
    selected = list(jobs.filter(purpose="metric")[:limit])
    selected += list(jobs.exclude(purpose="metric")[: limit - len(selected)])
    output = []
    for job in selected:
        decision = due_job(job, now=now)
        decision["applied"] = False
        output.append(decision)
        if not execute or not decision["due"]:
            continue
        require(budget is not None, "execution budget required")
        try:
            child = job_budget(budget, job)
        except SourceError:
            decision["reason"] = "invocation_budget_exhausted"
            break
        initial = child.remaining
        run = None
        try:
            run = (executor or execute_due_job)(job, decision, child)
            decision.update(applied=True, run_id=str(run.pk), status=run.status)
        except (BusyJob, CommandError, SourceError):
            job.refresh_from_db()
            run = job.last_attempt
            decision["reason"] = "bounded_execution_pending"
        finally:
            charge(budget, child, initial)
        if run is not None:
            with transaction.atomic():
                current = CollectionJob.objects.select_for_update().get(pk=job.pk)
                if (
                    current.last_attempt_id == run.pk
                    and current.active_run_id is None
                    and current.state == "ready"
                ):
                    current.next_retry_at = (
                        now + timedelta(minutes=15) if run.status != "success" else None
                    )
                    current.next_due_at = (
                        timezone.datetime.fromisoformat(decision["following_slot"])
                        if run.status == "success"
                        else None
                    )
                    current.save(
                        update_fields=["next_retry_at", "next_due_at", "updated_at"]
                    )
    return output
