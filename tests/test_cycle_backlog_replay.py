from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandAccount,
    HarvestBacklogWindow,
    PostBrand,
    Role,
    TwitterListMembership,
)
from monitor.cycle import CycleRunner, _cursor_key
from x_monitor.attribution import compile_keyword_index
from x_monitor.config import BacklogConfig, Config, HarvestConfig
from x_monitor.query_plan import PlannedCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _call() -> PlannedCall:
    return PlannedCall(
        call_id="B1",
        call_kind="brand_wide",
        brand_id="deepseek",
        bucket=None,
        query_string="deepseek",
        query_length=8,
    )


def _window(call, *, attempts=0, offset_seconds=0):
    now = timezone.now().replace(microsecond=0) + timedelta(seconds=offset_seconds)
    return HarvestBacklogWindow.objects.create(
        **_cursor_key(call),
        original_since=now - timedelta(minutes=15),
        original_until=now,
        remaining_since=now - timedelta(minutes=15),
        remaining_until=now,
        reason_code="page_cap",
        attempts=attempts,
    )


class Deadline:
    def __init__(self, allowed=True):
        self.allowed = allowed

    def can_start(self, seconds):
        return self.allowed

    def remaining(self):
        return 60.0 if self.allowed else 0.0


class Api:
    timeout_s = 1
    max_retries = 0


def _runner(max_attempts=8):
    return CycleRunner(
        cfg=Config(
            enabled_models=["deepseek"],
            daily_ceiling=100,
            harvest=HarvestConfig(
                backlog=BacklogConfig(
                    max_attempts=max_attempts,
                    max_age_hours=24,
                    replays_per_cycle=2,
                )
            ),
        ),
        cycle_kind="scheduled",
    )


def test_successful_replay_uses_persist_core_and_retires_claim(monkeypatch):
    call = _call()
    window = _window(call)
    runner = _runner()
    monkeypatch.setattr(
        runner,
        "_fetch_tweets",
        lambda *a, **k: ([{"id": "tweet-1", "text": "DeepSeek"}], "ok"),
    )
    monkeypatch.setattr(
        runner,
        "_attribute_items",
        lambda items, index, terms: len(items),
    )
    persisted = []

    def persist(items):
        persisted.extend(items)
        return 1, 1, 0

    monkeypatch.setattr(runner, "_persist_items", persist)
    reports = runner._replay_backlog(
        calls=[call],
        api=Api(),
        index=None,
        search_terms={},
        kept_all=[],
        run_id="run-1",
        deadline=Deadline(),
    )

    assert reports[0]["status"] == "completed"
    assert persisted[0]["id"] == "tweet-1"
    assert not HarvestBacklogWindow.objects.filter(pk=window.pk).exists()


def test_deadline_starts_no_claim_and_leaves_pending_ownership():
    call = _call()
    window = _window(call)
    reports = _runner()._replay_backlog(
        calls=[call],
        api=Api(),
        index=None,
        search_terms={},
        kept_all=[],
        run_id="run-1",
        deadline=Deadline(False),
    )

    assert reports == [{"status": "deadline_exhausted"}]
    window.refresh_from_db()
    assert window.state == "pending"
    assert window.attempts == 0


def test_repeated_replay_failure_quarantines_at_attempt_ceiling(monkeypatch):
    call = _call()
    window = _window(call, attempts=1)
    runner = _runner(max_attempts=2)
    monkeypatch.setattr(runner, "_fetch_tweets", lambda *a, **k: ([], "error"))

    reports = runner._replay_backlog(
        calls=[call],
        api=Api(),
        index=None,
        search_terms={},
        kept_all=[],
        run_id="run-1",
        deadline=Deadline(),
    )

    assert reports[0]["status"] == "quarantined"
    window.refresh_from_db()
    assert window.state == "quarantined"
    assert window.quarantine_reason == "error"


def test_explicit_quarantine_claim_skips_older_pending_window():
    call = _call()
    pending = _window(call)
    pending.remaining_since -= timedelta(hours=1)
    pending.original_since = pending.remaining_since
    pending.save()
    quarantined = _window(call, offset_seconds=-30)
    quarantined.state = "quarantined"
    quarantined.save()

    claimed = HarvestBacklogWindow.objects.claim_next(
        owner="backfill",
        run_id="quarantine-run",
        claim_expires_at=timezone.now() + timedelta(minutes=1),
        only_quarantined=True,
    )

    assert claimed.pk == quarantined.pk
    pending.refresh_from_db()
    assert pending.state == "pending"


def test_call_a_replay_uses_current_membership_role_and_records_run(monkeypatch):
    call = PlannedCall(
        call_id="A",
        call_kind="list",
        brand_id="*",
        bucket=None,
        query_string="(list:42)",
        query_length=9,
    )
    _window(call)
    brand = Brand.objects.create(nickname="minimax")
    role = Role.objects.create(key="official")
    account = Account.objects.create(author_id="official", handle="official")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    TwitterListMembership.objects.create(
        list_id=42,
        account=account,
        active=True,
        source="snapshot",
        source_run_id="snapshot-old",
    )
    runner = CycleRunner(
        cfg=Config(
            enabled_models=["minimax"],
            daily_ceiling=100,
            x_monitor_list_id=42,
        ),
        cycle_kind="scheduled",
    )
    monkeypatch.setattr(
        runner,
        "_fetch_tweets",
        lambda *a, **k: ([{
            "id": "replayed-official",
            "author_id": "official",
            "author_handle": "official",
            "text": "off topic",
            "created_at": timezone.now().isoformat(),
        }], "ok"),
    )

    reports = runner._replay_backlog(
        calls=[call],
        api=Api(),
        index=compile_keyword_index([]),
        search_terms={},
        kept_all=[],
        run_id="replay-run",
        deadline=Deadline(),
    )

    assert reports[0]["status"] == "completed"
    assert PostBrand.objects.filter(
        post_id="replayed-official", brand_id="minimax"
    ).exists()
    membership = TwitterListMembership.objects.get(list_id=42, account=account)
    assert membership.source_run_id == "replay-run"
