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
        return 1, 0, 1, 0

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


# --- U6 (plan 2026-11-24-012909): replay attempts follow physical requests


class CountingApi(Api):
    """A client double that reports physical requests like ``XClient``."""

    exchanges_started = 0


def _replay(runner, api, *, deadline=None, calls=None):
    return runner._replay_backlog(
        calls=calls or [_call()], api=api, index=None, search_terms={},
        kept_all=[], run_id="replay-run", deadline=deadline or Deadline(),
    )


def _fetch_sending(api, items, outcome):
    def fetch(*args, **kwargs):
        api.exchanges_started += 1
        return list(items), outcome
    return fetch


def _runner_with(replays, max_attempts=8):
    return CycleRunner(
        cfg=Config(
            enabled_models=["deepseek"], daily_ceiling=100,
            harvest=HarvestConfig(backlog=BacklogConfig(
                max_attempts=max_attempts, max_age_hours=24, replays_per_cycle=replays,
            )),
        ),
        cycle_kind="scheduled",
    )


def test_replay_with_every_route_blocked_keeps_its_attempt_and_stops():
    """KTD9 call chain: a real multi-route client whose routes are all open
    far past the deadline sends nothing, so the claim's attempt is refunded,
    the window stays pending (never quarantined) and the loop stops."""
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    call = _call()
    first = _window(call, attempts=0)
    second = _window(call, attempts=0, offset_seconds=-1200)
    tapi = SearchProviderCircuit("replay-tapi", provider="twitterapi", endpoint_family="search")
    twex = SearchProviderCircuit("replay-twex", provider="twexapi", endpoint_family="search")
    for circuit in (tapi, twex):
        CircuitRow.objects.create(purpose=circuit.purpose, consecutive_failures=6,
                                  open_until=timezone.now() + timedelta(hours=1))
    api = XClient(api_key="fixture", twexapi_key="fixture", circuit=tapi, twex_circuit=twex,
                  provider_order=("twitterapi:scheduled", "twexapi"),
                  provider_credentials={"twitterapi:scheduled": "fixture"},
                  provider_circuits={"twitterapi:scheduled": tapi})

    class Plenty:
        def can_start(self, seconds):
            return True

        def remaining(self):
            return 700.0

    reports = _replay(_runner_with(8, max_attempts=1), api, deadline=Plenty())

    assert len(reports) == 1 and reports[0]["request_sent"] is False
    assert reports[0]["status"] == "pending"
    for window in (first, second):
        window.refresh_from_db()
        assert window.state == "pending" and window.attempts == 0


def test_narrowed_replay_keeps_its_attempt_but_no_progress_counts(monkeypatch):
    call = _call()
    window = _window(call, attempts=0)
    runner = _runner_with(1)
    api = CountingApi()
    middle = (window.remaining_since + timedelta(minutes=5)).isoformat()
    monkeypatch.setattr(runner, "_fetch_tweets", _fetch_sending(
        api, [{"id": "narrow-1", "text": "DeepSeek", "created_at": middle}], "truncated"))
    monkeypatch.setattr(runner, "_attribute_items", lambda items, index, terms: len(items))
    monkeypatch.setattr(runner, "_persist_items", lambda items: (len(items), 0, len(items), 0))

    assert _replay(runner, api)[0]["status"] == "pending"
    window.refresh_from_db()
    assert window.attempts == 0
    assert window.remaining_until < window.original_until
    assert window.next_attempt_at is not None

    HarvestBacklogWindow.objects.filter(pk=window.pk).update(next_attempt_at=None)
    monkeypatch.setattr(runner, "_fetch_tweets", _fetch_sending(api, [], "truncated"))
    _replay(runner, api)
    window.refresh_from_db()
    assert window.attempts == 1


@pytest.mark.parametrize(("admitted", "expected"), [(None, 8), (3, 3)])
def test_replays_run_up_to_eight_while_the_tail_allows(monkeypatch, admitted, expected):
    call = _call()
    for n in range(10):
        _window(call, offset_seconds=-1800 * (n + 1))
    runner = _runner_with(8)
    api = CountingApi()
    monkeypatch.setattr(runner, "_fetch_tweets", _fetch_sending(api, [], "ok"))

    class Counting(Deadline):
        starts = 0

        def can_start(self, seconds):
            self.starts += 1
            return admitted is None or self.starts <= admitted

    reports = _replay(runner, api, deadline=Counting())
    assert [report["status"] for report in reports if report.get("window_id")] == ["completed"] * expected
    assert HarvestBacklogWindow.objects.count() == 10 - expected


def test_replay_truncated_return_is_not_reclaimed_in_the_same_cycle(monkeypatch):
    call = _call()
    window = _window(call)
    runner = _runner_with(8)
    api = CountingApi()
    monkeypatch.setattr(runner, "_fetch_tweets", _fetch_sending(api, [], "truncated"))

    reports = _replay(runner, api)

    assert [report["window_id"] for report in reports] == [window.pk]
    window.refresh_from_db()
    assert window.next_attempt_at >= timezone.now() + timedelta(minutes=14)


def test_narrow_replay_on_a_busy_call_skips_the_expected_results_heuristic(monkeypatch):
    """KTD9: the expected-results heuristic ignores window width, so a
    replay's quiet narrow window is a valid empty result, not a failure."""
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    call = _call()
    window = _window(call)
    tapi = SearchProviderCircuit("busy-tapi", provider="twitterapi", endpoint_family="search", threshold=1)
    for n in range(3):
        tapi.observe_query(f"deepseek since_time:{n} until_time:{n + 1}", nonempty=True, now=timezone.now())
    api = XClient(api_key="fixture", circuit=tapi, provider_order=("twitterapi:scheduled",),
                  provider_credentials={"twitterapi:scheduled": "fixture"},
                  provider_circuits={"twitterapi:scheduled": tapi})
    monkeypatch.setattr(api, "_get", lambda *a, **k: (setattr(api, "exchanges_started", api.exchanges_started + 1)
                                                      or {"tweets": [], "has_next_page": False}))

    class Plenty:
        def can_start(self, seconds):
            return True

        def remaining(self):
            return 700.0

    reports = _replay(_runner_with(1), api, deadline=Plenty())

    assert reports[0]["status"] == "completed"
    assert not HarvestBacklogWindow.objects.filter(pk=window.pk).exists()
    row = CircuitRow.objects.get(purpose=tapi.purpose)
    assert row.consecutive_failures == 0 and row.open_until is None
    assert api.query_history_enabled is True
