"""Atomic ownership transfer and bounded replay helpers for harvest windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from django.db import transaction
from django.utils import timezone as django_timezone

from core.models import BackfillJob, CallState, HarvestBacklogWindow

TransferOutcome = Literal[
    "transferred",
    "already_drained",
    "capacity_refused",
    "cursor_write_failed",
]


@dataclass(frozen=True)
class CoverageTransferResult:
    outcome: TransferOutcome
    cursor_advanced: bool
    backlog_window_id: int | None = None
    residual_since: datetime | None = None
    residual_until: datetime | None = None


def _aware(value: datetime | int) -> datetime:
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _residual_until(
    *, original_since: datetime, original_until: datetime, oldest_seen_at: datetime | None
) -> datetime:
    """Return an exclusive upper bound with a deliberate one-second overlap."""

    if oldest_seen_at is None:
        return original_until
    oldest = _aware(oldest_seen_at).replace(microsecond=0)
    if oldest < original_since or oldest >= original_until:
        return original_until
    return min(original_until, oldest + timedelta(seconds=1))


def transfer_truncated_coverage(
    *,
    call_identity: dict[str, str],
    original_since: datetime | int,
    original_until: datetime | int,
    oldest_seen_at: datetime | None,
    reason_code: str,
    pending_limit: int,
    quarantined_limit: int,
) -> CoverageTransferResult:
    """Atomically move unfinished coverage to the ledger and advance its cursor.

    A capacity refusal or cursor-write exception leaves ``CallState`` as the
    sole owner of the original interval.  The tweet upserts happen before this
    decision and remain safe to repeat by tweet ID.
    """

    since = _aware(original_since)
    until = _aware(original_until)
    if since >= until:
        raise ValueError("original harvest interval must be non-empty")
    remaining_until = _residual_until(
        original_since=since,
        original_until=until,
        oldest_seen_at=oldest_seen_at,
    )

    try:
        with transaction.atomic():
            state, _ = CallState.objects.get_or_create(**call_identity)
            state = CallState.objects.select_for_update().get(pk=state.pk)

            if remaining_until <= since:
                state.last_completed_at = until
                state.save(update_fields=["last_completed_at", "updated_at"])
                return CoverageTransferResult(
                    outcome="already_drained",
                    cursor_advanced=True,
                )

            normalized = HarvestBacklogWindow.objects.normalize_residual(
                call_identity=call_identity,
                original_since=since,
                original_until=until,
                remaining_since=since,
                remaining_until=remaining_until,
                reason_code=reason_code,
                pending_limit=pending_limit,
                quarantined_limit=quarantined_limit,
            )
            if not normalized.ownership_recorded:
                transaction.set_rollback(True)
                return CoverageTransferResult(
                    outcome="capacity_refused",
                    cursor_advanced=False,
                    residual_since=since,
                    residual_until=remaining_until,
                )

            state.last_completed_at = until
            state.save(update_fields=["last_completed_at", "updated_at"])
            return CoverageTransferResult(
                outcome="transferred",
                cursor_advanced=True,
                backlog_window_id=normalized.window_id,
                residual_since=since,
                residual_until=remaining_until,
            )
    except Exception:
        return CoverageTransferResult(
            outcome="cursor_write_failed",
            cursor_advanced=False,
            residual_since=since,
            residual_until=remaining_until,
        )


def finish_claim(window_id: int) -> bool:
    """Finish a claim while retaining job-owned recovery audit rows."""

    with transaction.atomic():
        window = (
            HarvestBacklogWindow.objects.select_for_update()
            .filter(pk=window_id, state=HarvestBacklogWindow.State.CLAIMED)
            .first()
        )
        if window is None:
            return False
        if window.backfill_job_id is None:
            window.delete()
            return True

        job = BackfillJob.objects.select_for_update().get(pk=window.backfill_job_id)
        window.state = HarvestBacklogWindow.State.COMPLETED
        window.claim_owner = ""
        window.claim_run_id = ""
        window.claimed_at = None
        window.claim_expires_at = None
        window.save()
        unfinished = job.windows.exclude(
            state=HarvestBacklogWindow.State.COMPLETED
        ).exists()
        if not unfinished:
            completed_at = django_timezone.now()
            job.state = BackfillJob.State.COMPLETED
            job.completed_at = completed_at
            job.save(update_fields=["state", "completed_at", "updated_at"])
        return True


def return_claim(
    window_id: int,
    *,
    reason: str,
    max_attempts: int,
    max_age_hours: int,
    remaining_until: datetime | None = None,
    now: datetime | None = None,
) -> str:
    """Return an interrupted claim to pending or quarantine it at a ceiling."""

    now = now or django_timezone.now()
    with transaction.atomic():
        window = HarvestBacklogWindow.objects.select_for_update().filter(
            pk=window_id, state=HarvestBacklogWindow.State.CLAIMED
        ).first()
        if window is None:
            return "ownership_changed"
        if remaining_until is not None:
            narrowed = min(_aware(remaining_until), window.remaining_until)
            if narrowed > window.remaining_since:
                window.remaining_until = narrowed
        too_old = window.first_seen_at <= now - timedelta(hours=max_age_hours)
        if window.attempts >= max_attempts or too_old:
            window.state = HarvestBacklogWindow.State.QUARANTINED
            window.quarantine_reason = reason[:128]
            window.quarantined_at = now
            outcome = "quarantined"
        else:
            window.state = HarvestBacklogWindow.State.PENDING
            outcome = "pending"
        window.claim_owner = ""
        window.claim_run_id = ""
        window.claimed_at = None
        window.claim_expires_at = None
        window.save()
        return outcome
