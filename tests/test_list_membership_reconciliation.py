from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import Account, TwitterListMembership, TwitterListSyncState
from monitor.list_membership import (
    observe_call_a_authors,
    reconcile_complete_snapshot,
    reconciliation_due,
    run_due_reconciliation,
)
from x_monitor.apify import ListMembersSnapshot
from x_monitor.config import Config

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _snapshot(members, *, complete=True, reason=None, pages=1):
    return ListMembersSnapshot(
        members=members,
        complete=complete,
        pages_fetched=pages,
        reason=reason,
    )


def test_complete_snapshot_activates_updates_and_deactivates_atomically():
    now = timezone.now().replace(microsecond=0)
    kept = Account.objects.create(author_id="1", handle="before")
    removed = Account.objects.create(author_id="9", handle="removed")
    TwitterListMembership.objects.create(
        list_id=42,
        account=kept,
        active=False,
        source="seed",
    )
    TwitterListMembership.objects.create(
        list_id=42,
        account=removed,
        active=True,
        source="seed",
    )

    result = reconcile_complete_snapshot(
        list_id=42,
        snapshot=_snapshot([
            {"author_id": "1", "handle": "after", "display_name": "One"},
            {"author_id": "2", "handle": "second", "display_name": "Two"},
        ], pages=2),
        snapshot_id="snapshot-1",
        completed_at=now,
    )

    assert result.deactivated == 1
    assert set(TwitterListMembership.objects.filter(
        list_id=42, active=True
    ).values_list("account_id", flat=True)) == {"1", "2"}
    removed.refresh_from_db()
    assert TwitterListMembership.objects.get(list_id=42, account=removed).active is False
    kept.refresh_from_db()
    assert kept.handle == "after"
    state = TwitterListSyncState.objects.get(list_id=42)
    assert (state.snapshot_id, state.last_complete_at) == (
        "snapshot-1", result.completed_at
    )


def test_incomplete_snapshot_does_not_change_last_complete_active_set():
    account = Account.objects.create(author_id="1", handle="kept")
    membership = TwitterListMembership.objects.create(
        list_id=42, account=account, active=True, source="seed"
    )

    result = reconcile_complete_snapshot(
        list_id=42,
        snapshot=_snapshot(
            [{"author_id": "2", "handle": "partial"}],
            complete=False,
            reason="empty_continuation_page",
        ),
        snapshot_id="partial",
    )

    assert result.status == "incomplete"
    membership.refresh_from_db()
    assert membership.active is True
    assert not Account.objects.filter(author_id="2").exists()
    assert not TwitterListSyncState.objects.filter(list_id=42).exists()


def test_identical_snapshot_is_idempotent_and_handle_change_keeps_identity():
    first = _snapshot([{"author_id": "1", "handle": "first"}])
    reconcile_complete_snapshot(list_id=42, snapshot=first, snapshot_id="one")
    second = _snapshot([{"author_id": "1", "handle": "renamed"}])
    reconcile_complete_snapshot(list_id=42, snapshot=second, snapshot_id="two")

    assert Account.objects.count() == 1
    assert TwitterListMembership.objects.count() == 1
    assert Account.objects.get(author_id="1").handle == "renamed"


def test_call_a_author_is_observed_immediately_without_complete_snapshot():
    result = observe_call_a_authors(
        list_id=42,
        items=[
            {"author_id": "1", "author_handle": "member"},
            {"author_id": "1", "author_handle": "member"},
        ],
        run_id="run-1",
    )

    assert result.observed == 1
    membership = TwitterListMembership.objects.get(list_id=42, account_id="1")
    assert membership.active is True
    assert membership.source == "call_a"
    assert membership.source_run_id == "run-1"
    assert membership.last_complete_reconciliation_at is None


def test_due_state_handles_empty_lists_and_deadline_defers_without_api_call():
    now = timezone.now().replace(microsecond=0)
    TwitterListSyncState.objects.create(
        list_id=42,
        snapshot_id="empty",
        last_complete_at=now,
    )
    assert reconciliation_due(list_id=42, interval_hours=6, now=now) is False
    assert reconciliation_due(
        list_id=42, interval_hours=6, now=now + timedelta(hours=7)
    ) is True

    class Deadline:
        @staticmethod
        def can_start(seconds):
            return False

    class Api:
        max_retries = 0

        def run_list_members(self, *args, **kwargs):
            raise AssertionError("deadline must prevent the request")

    result = run_due_reconciliation(
        api=Api(),
        cfg=Config(enabled_models=["deepseek"], daily_ceiling=100),
        list_id=99,
        deadline=Deadline(),
        run_id="run",
        force=True,
    )
    assert result.status == "deferred"


def test_sync_command_dry_run_never_calls_provider(monkeypatch):
    from x_monitor.apify import TwitterApiClient

    monkeypatch.setattr(
        TwitterApiClient,
        "from_env",
        classmethod(lambda cls: (_ for _ in ()).throw(AssertionError("network"))),
    )
    stdout = StringIO()
    call_command(
        "sync_twitter_list_members",
        list_id=42,
        dry_run=True,
        stdout=stdout,
    )
    assert "dry run" in stdout.getvalue()
