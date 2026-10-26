"""Explicit scheduling authority, UTC slots and cooldowns over persisted jobs."""

import uuid
from datetime import UTC, timedelta
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.collection_jobs import validate_job
from core.collection_state import BusyJob
from core.measurement_taxonomy import require
from core.models import CollectionJob, CollectionRun, DataSource


def metric_authority(source, contract_id):
    identifier = (
        CollectionJob.objects.filter(
            source=source,
            contract_id=contract_id,
            purpose="metric",
            authority_enabled=True,
        )
        .values_list("pk", flat=True)
        .first()
    )
    return str(identifier) if identifier else None


def collection_authority(source, role, *, owner_account_id=None):
    identifier = (
        CollectionJob.objects.filter(
            source=source,
            routine_role=role,
            owner_account_id=owner_account_id,
            purpose="catalog",
            authority_enabled=True,
        )
        .values_list("pk", flat=True)
        .first()
    )
    return str(identifier) if identifier else None


def _retain_previous_dispatch_pointer(source, job):
    """Keep the deployed v1 dispatcher usable until its separate retirement."""
    if job.instruction_version != 1 or job.owner_account_id is not None:
        return
    key = (
        "collection_job_authorities"
        if job.purpose == "metric"
        else "collection_role_authorities"
    )
    coordinate = str(job.contract_id) if job.purpose == "metric" else job.routine_role
    source.metadata = {
        **source.metadata,
        key: {**source.metadata.get(key, {}), coordinate: str(job.pk)},
    }
    source.save(update_fields=["metadata"])


@transaction.atomic
def take_collection_authority(job_id):
    """Explicitly attach one recurring source role to the existing hourly runner."""
    job = CollectionJob.objects.select_for_update().get(pk=job_id)
    source = DataSource.objects.select_for_update().get(pk=job.source_id)
    validate_job(job)
    role = job.scope.get("routine_role")
    require(
        job.purpose == "catalog"
        and job.mode == "recurring"
        and job.source_id in {"hf", "github", "openrouter", "arena"}
        and job.schedule["driver"] == "shared"
        and isinstance(role, str)
        and 0 < len(role) <= 128,
        "reviewed recurring source role required",
    )
    previous = (
        CollectionJob.objects.select_for_update(nowait=True).filter(
            source=source,
            purpose="catalog",
            routine_role=role,
            owner_account_id=job.owner_account_id,
            authority_enabled=True,
        )
        .exclude(pk=job.pk)
        .first()
    )
    require(
        previous is None or previous.state == "cancelled",
        "another job owns collection role dispatch",
    )
    if previous:
        CollectionJob.objects.filter(pk=previous.pk).update(authority_enabled=False)
    job.routine_role, job.authority_enabled = role, True
    job.save(update_fields=["routine_role", "authority_enabled"])
    _retain_previous_dispatch_pointer(source, job)
    return job


def dispatch_collection_roles(*, execute=False, now=None):
    """Extend the deployed wake-up; registration cannot activate a source role."""
    import httpx

    from core.collection_budgets import invocation_budget

    require(
        not execute or settings.BENCHMARK_COLLECTION_ENABLED,
        "source collection is disabled in this environment",
    )
    output = []
    for source in DataSource.objects.order_by("pk"):
        if execute:
            from core.collection_publisher_jobs import enroll_confirmed_accounts

            enroll_confirmed_accounts(source.pk)
        jobs = list(
            CollectionJob.objects.filter(
                source=source,
                purpose="catalog",
                mode="recurring",
                authority_enabled=True,
            ).values_list("pk", flat=True)
        )
        if not jobs:
            continue
        if execute:
            limits = {
                "requests": source.dispatch_max_requests,
                "seconds": source.dispatch_max_seconds,
                "bytes": source.dispatch_max_bytes,
            }
            with httpx.Client(trust_env=False) as client:
                budget = invocation_budget(
                    client,
                    requests=limits["requests"],
                    seconds=limits["seconds"],
                    max_bytes=limits["bytes"],
                )
                rows = dispatch_due(execute=True, budget=budget, job_ids=jobs, now=now)
        else:
            rows = dispatch_due(job_ids=jobs, now=now)
        output.extend({**row, "authority": "source-role"} for row in rows)
    return output


@transaction.atomic
def take_metric_authority(job_id):
    """Registration alone does not replace the current benchmark scheduler."""
    job = CollectionJob.objects.select_for_update().get(pk=job_id)
    source = DataSource.objects.select_for_update().get(pk=job.source_id)
    validate_job(job)
    require(
        job.operation == "collect_metrics" and job.mode == "recurring",
        "recurring metric job required",
    )
    previous = (
        CollectionJob.objects.filter(
            source=source,
            purpose="metric",
            contract_id=job.contract_id,
            authority_enabled=True,
        )
        .exclude(pk=job.pk)
        .exists()
    )
    require(not previous, "another job owns metric dispatch")
    job.authority_enabled = True
    job.save(update_fields=["authority_enabled"])
    _retain_previous_dispatch_pointer(source, job)
    return job


def schedule_slot(job, now):
    now = now.astimezone(UTC)
    schedule = job.schedule
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
    if job.mode != "recurring" or job.schedule["driver"] != "shared":
        reason = "external_or_manual_driver"
    elif job.state != "ready" or not job.source.enabled:
        reason = "paused_or_disabled"
    elif (
        job.purpose == "catalog"
        and job.scope.get("routine_role")
        and (not settings.BENCHMARK_COLLECTION_ENABLED)
    ):
        reason = "source_collection_disabled"
    elif (
        job.purpose == "catalog"
        and job.scope.get("routine_role")
        and (
            collection_authority(
                job.source,
                job.scope["routine_role"],
                owner_account_id=job.owner_account_id,
            )
            != str(job.pk)
        )
    ):
        reason = "unclaimed_collection_role"
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
        continuation = (
            job.last_attempt
            if job.instruction_version == 1
            and job.purpose == "catalog"
            and job.last_attempt_id
            and job.last_attempt.status == "partial"
            and job.last_attempt.completed_at is None
            else None
        )
        slot, following = schedule_slot(
            job, continuation.started_at if continuation else now
        )
        if slot > now or (job.next_due_at and job.next_due_at > now):
            reason = "before_slot"
        elif job.last_success_id and job.last_success.started_at >= slot:
            reason = "slot_succeeded"
        elif (
            job.purpose == "metric"
            and CollectionRun.objects.filter(
                job__source_id=job.source_id,
                job__contract_id=job.contract_id,
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
        preceding_attempt = job.last_attempt_id
        from scripts.benchmark_download_collector.sources import SourceError

        remaining_seconds = int(budget.deadline - budget.clock())
        if remaining_seconds < 1:
            raise SourceError("time_cap")
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
                max_seconds=min(300, remaining_seconds),
                max_bytes=budget.max_bytes - budget.total_bytes_read,
                apply=True,
                stdout=StringIO(),
            )
        finally:
            job.refresh_from_db()
            if job.last_attempt_id and job.last_attempt_id != preceding_attempt:
                budget.remaining -= job.last_attempt.request_count
                budget.total_bytes_read += (
                    job.last_attempt.physical_bytes_received or 0
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
    *,
    budget=None,
    now=None,
    execute=False,
    job_id=None,
    job_ids=None,
    executor=None,
    limit=100,
):
    from core.collection_budgets import charge, job_budget
    from scripts.benchmark_download_collector.sources import SourceError

    require(type(limit) is int and 1 <= limit <= 100, "invalid dispatch job cap")
    now = now or timezone.now()
    jobs = CollectionJob.objects.select_related(
        "source", "contract", "active_run", "last_success", "last_attempt"
    ).order_by("updated_at", "job_key")
    if job_id:
        jobs = jobs.filter(pk=job_id)
    elif job_ids is not None:
        jobs = jobs.filter(pk__in=job_ids)
    else:
        # Imported/manual projection receipts must not consume the dispatch cap.
        jobs = jobs.filter(mode="recurring").filter(
            Q(instruction_version=2, schedule_driver="shared")
            | Q(instruction_version=1, definition__schedule__driver="shared")
        )
    # Numeric work precedes catalog maintenance in a bounded invocation.
    candidates = [(job, due_job(job, now=now)) for job in jobs]
    candidates.sort(
        key=lambda pair: (
            not pair[1]["due"],
            pair[0].purpose != "metric",
            pair[0].updated_at,
            pair[0].job_key,
        )
    )
    selected = candidates[:limit]
    output = []
    for job, decision in selected:
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
                        max(now + timedelta(minutes=15), current.next_retry_at or now)
                        if run.status != "success"
                        else None
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
