from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import JobSourceState, JobSourceSyncRun

from .adapters import fetch_source
from .sync import SyncResult, sync_snapshot, validate_snapshot
from .types import SourceDefinition, SourceSnapshot


@dataclass(frozen=True, slots=True)
class SourceRunResult:
    source_key: str
    status: str
    observed_total: int = 0
    sync: SyncResult | None = None
    error: str = ""


class SourceLeaseLostError(RuntimeError):
    pass


@transaction.atomic
def _claim(definition: SourceDefinition) -> tuple[JobSourceSyncRun, str] | None:
    now = timezone.now()
    JobSourceState.objects.get_or_create(source_key=definition.key)
    state = JobSourceState.objects.select_for_update().get(source_key=definition.key)
    if state.lease_is_active(now=now):
        JobSourceSyncRun.objects.create(
            source_key=definition.key,
            status="skipped",
            finished_at=now,
            error_summary="active source lease",
        )
        return None
    if state.active_run_id:
        JobSourceSyncRun.objects.filter(
            pk=state.active_run_id, status="running"
        ).update(
            status="failed",
            finished_at=now,
            error_summary="reclaimed after source lease expired",
        )
    run = JobSourceSyncRun.objects.create(source_key=definition.key)
    token = uuid.uuid4().hex
    state.lease_token = token
    state.lease_expires_at = now + timedelta(minutes=30)
    state.active_run = run
    state.save(
        update_fields=["lease_token", "lease_expires_at", "active_run", "updated_at"]
    )
    return run, token


@transaction.atomic
def _renew_claim(
    definition: SourceDefinition, run: JobSourceSyncRun, token: str
) -> int | None:
    state = JobSourceState.objects.select_for_update().get(source_key=definition.key)
    if state.lease_token != token or state.active_run_id != run.pk:
        raise SourceLeaseLostError(f"{definition.key} source lease was lost")
    state.lease_expires_at = timezone.now() + timedelta(minutes=30)
    state.save(update_fields=["lease_expires_at", "updated_at"])
    return state.last_snapshot_count


@transaction.atomic
def _release(
    definition: SourceDefinition,
    token: str,
    *,
    snapshot: SourceSnapshot | None = None,
    error: str = "",
) -> None:
    state = JobSourceState.objects.select_for_update().get(source_key=definition.key)
    if state.lease_token != token:
        return
    state.lease_token = None
    state.lease_expires_at = None
    state.active_run = None
    state.last_error = error[:4000]
    fields = [
        "lease_token",
        "lease_expires_at",
        "active_run",
        "last_error",
        "updated_at",
    ]
    if snapshot is not None and snapshot.complete:
        state.last_successful_at = timezone.now()
        state.last_snapshot_count = len(snapshot.jobs)
        fields.extend(["last_successful_at", "last_snapshot_count"])
    state.save(update_fields=fields)


def run_source(
    definition: SourceDefinition,
    *,
    dry_run: bool = False,
    no_close: bool = False,
) -> SourceRunResult:
    if dry_run:
        try:
            snapshot = fetch_source(definition)
            validate_snapshot(snapshot)
            return SourceRunResult(
                definition.key,
                "validated" if snapshot.complete else "partial",
                len(snapshot.jobs),
            )
        except Exception as exc:  # noqa: BLE001 - each source is a failure boundary
            return SourceRunResult(definition.key, "failed", error=str(exc))
    claimed = _claim(definition)
    if claimed is None:
        return SourceRunResult(definition.key, "skipped", error="active source lease")
    run, token = claimed
    snapshot = None
    try:
        snapshot = fetch_source(definition)
        if not snapshot.complete:
            run.status = "partial"
            run.finished_at = timezone.now()
            run.snapshot_complete = False
            run.declared_total = snapshot.declared_total
            run.observed_total = len(snapshot.jobs)
            run.metadata = snapshot.metadata
            run.error_summary = "incomplete snapshot was not persisted"
            run.save()
            _release(definition, token, error=run.error_summary)
            return SourceRunResult(
                definition.key, "partial", len(snapshot.jobs), error=run.error_summary
            )
        last_snapshot_count = _renew_claim(definition, run, token)
        if not snapshot.jobs and last_snapshot_count:
            run.status = "partial"
            run.finished_at = timezone.now()
            run.snapshot_complete = False
            run.declared_total = snapshot.declared_total
            run.observed_total = 0
            run.metadata = snapshot.metadata | {
                "anomaly": "zero_after_nonzero_snapshot",
                "previous_snapshot_count": last_snapshot_count,
            }
            run.error_summary = (
                "zero snapshot after prior non-zero success was not persisted"
            )
            run.save()
            _release(definition, token, error=run.error_summary)
            return SourceRunResult(definition.key, "partial", error=run.error_summary)
        result = sync_snapshot(snapshot, no_close=no_close, run=run)
        _release(definition, token, snapshot=snapshot)
        return SourceRunResult(definition.key, run.status, len(snapshot.jobs), result)
    except Exception as exc:  # noqa: BLE001 - preserve other source commits
        JobSourceSyncRun.objects.filter(pk=run.pk, status="running").update(
            status="failed", finished_at=timezone.now(), error_summary=str(exc)[:4000]
        )
        _release(definition, token, error=str(exc))
        return SourceRunResult(definition.key, "failed", error=str(exc))
