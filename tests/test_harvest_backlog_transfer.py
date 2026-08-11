from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from monitor.backlog import transfer_truncated_coverage

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


IDENTITY = {
    "brand_id": "*",
    "call_id": "A",
    "call_kind": "list",
    "bucket": "",
    "query_id": "A",
}


def _state(at):
    from core.models import CallState

    return CallState.objects.create(**IDENTITY, last_completed_at=at)


def test_truncated_transfer_overlaps_oldest_second_and_advances_atomically():
    from core.models import HarvestBacklogWindow

    now = timezone.now().replace(microsecond=0)
    since = now - timedelta(minutes=15)
    oldest = now - timedelta(minutes=4)
    state = _state(since)

    result = transfer_truncated_coverage(
        call_identity=IDENTITY,
        original_since=since,
        original_until=now,
        oldest_seen_at=oldest,
        reason_code="page_cap",
        pending_limit=8,
        quarantined_limit=4,
    )

    assert result.outcome == "transferred"
    assert result.cursor_advanced is True
    state.refresh_from_db()
    assert state.last_completed_at == now
    window = HarvestBacklogWindow.objects.get()
    assert window.remaining_since == since
    assert window.remaining_until == oldest + timedelta(seconds=1)


def test_missing_oldest_transfers_full_interval():
    from core.models import HarvestBacklogWindow

    now = timezone.now().replace(microsecond=0)
    since = now - timedelta(minutes=15)
    _state(since)

    result = transfer_truncated_coverage(
        call_identity=IDENTITY,
        original_since=since,
        original_until=now,
        oldest_seen_at=None,
        reason_code="invalid_oldest",
        pending_limit=8,
        quarantined_limit=4,
    )

    assert result.outcome == "transferred"
    window = HarvestBacklogWindow.objects.get()
    assert (window.remaining_since, window.remaining_until) == (since, now)


def test_capacity_refusal_creates_nothing_and_leaves_cursor_as_owner():
    from core.models import HarvestBacklogWindow

    now = timezone.now().replace(microsecond=0)
    since = now - timedelta(hours=1)
    state = _state(since)
    HarvestBacklogWindow.objects.create(
        **IDENTITY,
        original_since=since,
        original_until=now,
        remaining_since=since,
        remaining_until=since + timedelta(minutes=5),
        reason_code="older_gap",
    )

    result = transfer_truncated_coverage(
        call_identity=IDENTITY,
        original_since=since + timedelta(minutes=30),
        original_until=now,
        oldest_seen_at=None,
        reason_code="page_cap",
        pending_limit=1,
        quarantined_limit=4,
    )

    assert result.outcome == "capacity_refused"
    assert result.cursor_advanced is False
    assert HarvestBacklogWindow.objects.count() == 1
    state.refresh_from_db()
    assert state.last_completed_at == since


def test_cursor_write_failure_rolls_back_new_residual(monkeypatch):
    from core.models import CallState, HarvestBacklogWindow

    now = timezone.now().replace(microsecond=0)
    since = now - timedelta(minutes=15)
    state = _state(since)
    original_save = CallState.save

    def fail_cursor_update(instance, *args, **kwargs):
        if instance.last_completed_at == now:
            raise RuntimeError("cursor unavailable")
        return original_save(instance, *args, **kwargs)

    monkeypatch.setattr(CallState, "save", fail_cursor_update)
    result = transfer_truncated_coverage(
        call_identity=IDENTITY,
        original_since=since,
        original_until=now,
        oldest_seen_at=now - timedelta(minutes=2),
        reason_code="page_cap",
        pending_limit=8,
        quarantined_limit=4,
    )

    assert result.outcome == "cursor_write_failed"
    assert HarvestBacklogWindow.objects.count() == 0
    state.refresh_from_db()
    assert state.last_completed_at == since
