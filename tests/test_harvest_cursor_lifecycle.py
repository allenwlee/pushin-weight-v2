"""U4: full cursor lifecycle across many cycles.

Plan: docs/plans/2026-07-27-002-fix-v2-harvest-cursor-regression-plan.md
Unit U4 (R9, R2, R4).

U1 tests the cursor helpers in isolation and U3 pins the invariants that
broke.  This file walks the whole state machine end to end, because the
properties that actually protect collection volume are multi-cycle ones and
cannot be seen from a single run:

    cold start -> steady advance -> failure hold -> recovery -> stale clamp

The most valuable case here is FAILURE HOLD + RECOVERY.  A transient rate
limit must not cost data: because the cursor does not advance on a failed
call, the following cycle's window must still cover the span the failed cycle
was supposed to sweep.  That is the difference between a blip and permanent
data loss, and no single-cycle test can express it.

Each cycle's window is captured from the API stub, so the assertions are about
what was really requested rather than what the code intended.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner
from x_monitor.config import CycleConfig
from x_monitor.query_plan import PlannedCall
from x_monitor.x_client import XClientRateLimitError, XClientServerError

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]
_CYCLE_DEFAULTS = CycleConfig()
_CURSOR_OVERLAP = timedelta(seconds=_CYCLE_DEFAULTS.cursor_overlap_seconds)
_MAX_LOOKBACK = timedelta(hours=_CYCLE_DEFAULTS.max_lookback_hours)


def _call(call_id: str = "B1", brand_id: str = "minimax") -> PlannedCall:
    return PlannedCall(
        call_id=call_id,
        call_kind="brand_wide",
        brand_id=brand_id,
        bucket=None,
        query_string="(alpha OR beta) min_faves:0",
        query_length=27,
    )


def _tweet(tid: str):
    return {
        "id": tid,
        "author_id": f"a{tid}",
        "author_handle": f"user_{tid}",
        "text": "alpha release is great",
        "lang": "en",
        "created_at": "Sat Jul 25 12:00:00 +0000 2026",
    }


class ScriptedApi:
    """Returns scripted results (or raises) and records each window."""

    base_url = "https://api.twitterapi.io"

    def __init__(self, script):
        self._script = list(script)
        self.calls: list[dict] = []

    def run_search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        step = self._script.pop(0) if self._script else []
        if isinstance(step, Exception):
            raise step
        if getattr(self, "on_exchange_start", None) is not None:
            exchange = self.on_exchange_start(
                "/twitter/tweet/advanced_search", {"query": query},
            )
            self.on_exchange_finish(exchange, {
                "outcome": "received", "status_code": 200,
                "body": json.dumps({"tweets": step}).encode(), "error_type": None,
            })
        return list(step), False  # (items, truncated)


@pytest.fixture
def harvest(monkeypatch, seeded_policy_keywords):
    """Drive N sequential cycles, returning the window each one requested."""

    def _run_cycle(calls, script):
        api = ScriptedApi(script)
        monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None, **_kwargs: list(calls))
        monkeypatch.setattr(
            cycle_mod.XClient,
            "from_env",
            classmethod(lambda cls, _purpose: api),
        )
        monkeypatch.setattr(
            CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
        )
        stats = CycleRunner(cycle_kind="scheduled").run()
        return api, stats

    return _run_cycle


def _window(api, i=0):
    return api.calls[i]["since_time"], api.calls[i]["until_time"]


# --- cold start ----------------------------------------------------------


def test_cold_start_begins_at_the_clamped_floor(harvest):
    """An empty call_state must not reach back to the epoch."""
    api, _ = harvest([_call()], [[_tweet("1")]])
    since, until = _window(api)
    span = until - since
    assert span == pytest.approx(_MAX_LOOKBACK.total_seconds(), abs=5), (
        f"cold-start window is {span / 3600:.2f}h; expected the "
        f"{_MAX_LOOKBACK.total_seconds() / 3600:.0f}h clamp"
    )


def test_cold_start_creates_a_cursor_row(harvest):
    from core.models import CallState

    harvest([_call()], [[_tweet("1")]])
    assert CallState.objects.count() == 1


# --- steady advance ------------------------------------------------------


def test_three_successful_cycles_advance_monotonically(harvest):
    call = [_call()]
    a1, _ = harvest(call, [[_tweet("1")]])
    a2, _ = harvest(call, [[_tweet("2")]])
    a3, _ = harvest(call, [[_tweet("3")]])

    sinces = [_window(a)[0] for a in (a1, a2, a3)]
    # Consecutive cycles here run in the same wall-clock second, so the
    # epoch-second floors can tie. Real cycles are 15 min apart. Assert the
    # cursor never REGRESSES, and that it left the cold-start floor.
    assert sinces[0] < sinces[1], (
        f"cursor did not leave the cold-start floor: {sinces}"
    )
    assert sinces[1] <= sinces[2], (
        f"since_time regressed between cycles: {sinces}"
    )


def test_steady_cycles_leave_no_gap_at_any_boundary(harvest):
    """Every boundary must be covered, not just the first."""
    call = [_call()]
    apis = [harvest(call, [[_tweet(str(i))]])[0] for i in range(4)]
    windows = [_window(a) for a in apis]

    for (prev_since, prev_until), (next_since, _) in zip(windows, windows[1:]):
        assert next_since <= prev_until, (
            f"gap: previous window ended {prev_until}, next began "
            f"{next_since} ({next_since - prev_until}s uncovered)"
        )


def test_steady_window_narrows_after_the_first_cycle(harvest):
    """Cold start sweeps the clamp; later cycles sweep only elapsed time plus
    the overlap. A window that stays clamp-wide means the cursor is not
    being read."""
    call = [_call()]
    a1, _ = harvest(call, [[_tweet("1")]])
    a2, _ = harvest(call, [[_tweet("2")]])

    first_span = _window(a1)[1] - _window(a1)[0]
    second_span = _window(a2)[1] - _window(a2)[0]
    assert second_span < first_span, (
        f"second window ({second_span}s) is not narrower than the cold-start "
        f"window ({first_span}s) -- the cursor is being ignored"
    )
    assert second_span <= _CURSOR_OVERLAP.total_seconds() + 10


# --- failure hold + recovery (the properties that protect volume) --------


def _assert_backlog_owns_failed_window(api, failure_stats):
    """KTD8 (plan 2026-11-24-012909): a failed window accepted by the backlog
    is owned by that row, so the cursor advances to the window's end; the
    window itself stays pending with its exact bounds. Nothing is lost."""
    from core.models import CallState, HarvestBacklogWindow

    since, until = _window(api)
    entry = failure_stats["calls"][0]
    assert entry["coverage_transfer"] == "transferred" and entry["cursor_advanced"] is True
    window = HarvestBacklogWindow.objects.get(pk=entry["backlog_window_id"])
    assert window.state == "pending" and window.reason_code == "search_failed"
    assert (int(window.remaining_since.timestamp()), int(window.remaining_until.timestamp())) == (since, until)
    assert int(CallState.objects.get(call_id=window.call_id).last_completed_at.timestamp()) == until


def test_failed_cycle_hands_its_window_to_the_backlog(harvest):
    call = [_call()]
    harvest(call, [[_tweet("1")]])
    api, failure = harvest(call, [XClientRateLimitError("429")])
    _assert_backlog_owns_failed_window(api, failure)


def test_cycle_after_a_failure_recovers_the_missed_span(harvest, monkeypatch):
    """A failed search keeps its window covered even after the live lookback moves."""
    from django.utils import timezone as django_timezone

    from core.models import CallState, HarvestBacklogWindow

    slot = [(datetime.now(timezone.utc) - timedelta(hours=1)).replace(second=0, microsecond=0)]
    monkeypatch.setattr(django_timezone, "now", lambda: slot[0])
    monkeypatch.setattr(CycleRunner, "_wall_now", lambda self: slot[0])
    call = [_call()]
    a1, _ = harvest(call, [[_tweet("1")]])
    slot[0] += timedelta(minutes=15)
    a2, failure = harvest(call, [XClientRateLimitError("429")])
    # KTD8: the backlog accepted the failed window, so it owns that interval.
    _assert_backlog_owns_failed_window(a2, failure)
    assert int(CallState.objects.get().last_completed_at.timestamp()) == _window(a2)[1]
    window = HarvestBacklogWindow.objects.get(pk=failure["calls"][0]["backlog_window_id"])
    assert (int(window.remaining_since.timestamp()), int(window.remaining_until.timestamp())) == _window(a2)
    assert window.remaining_since.timestamp() <= _window(a1)[1]

    slot[0] += timedelta(minutes=15)
    a3, recovered = harvest(call, [[_tweet("3")]])
    assert _window(a3)[1] > _window(a2)[1]
    # It is safe for the live search to move forward if the missed interval
    # is still durably pending or the replay actually searched it.
    assert (
        _window(a3)[0] <= _window(a1)[1]
        or HarvestBacklogWindow.objects.filter(pk=window.pk).exists()
        or any(item.get("window_id") == window.pk and item.get("status") == "completed"
               for item in recovered.get("backlog_replays", []))
    )


def test_server_error_also_hands_its_window_to_the_backlog(harvest):
    """Not just rate limits -- any transient failure keeps its window (KTD8)."""
    call = [_call()]
    harvest(call, [[_tweet("1")]])
    api, failure = harvest(call, [XClientServerError("503")])
    _assert_backlog_owns_failed_window(api, failure)


def test_recovery_resumes_normal_advance(harvest, monkeypatch):
    from types import SimpleNamespace

    from core import x_cycle_lineage
    from core.models import CallState

    # Scheduled harvests occur in separate 15-minute slots.  Keep the
    # lineage clock distinct even when all three fixture runs finish in one second.
    slot = [datetime.now(timezone.utc).replace(second=0, microsecond=0)]
    monkeypatch.setattr(x_cycle_lineage, "timezone", SimpleNamespace(now=lambda: slot[0]))

    call = [_call()]
    harvest(call, [[_tweet("1")]])
    held = CallState.objects.get().last_completed_at
    slot[0] += timedelta(minutes=15)
    harvest(call, [XClientRateLimitError("429")])
    slot[0] += timedelta(minutes=15)
    harvest(call, [[_tweet("3")]])
    assert CallState.objects.get().last_completed_at >= held, (
        "cursor regressed after a recovered failure"
    )


# --- stale cursor (the prod cold-start shape) ----------------------------


def test_stale_cursor_is_clamped_not_swept_whole(harvest):
    """R4 / KTD3: prod's cursor sat ~5 days stale. Deriving the window from it
    unclamped would request a 5-day sweep that silently truncates against the
    per-call page ceiling -- the same silent-loss class this plan fixes."""
    from core.models import CallState

    call = _call()
    stale = datetime.now(timezone.utc) - timedelta(days=5)
    CallState.objects.create(
        brand_id=call.brand_id,
        call_id=call.call_id,
        call_kind=call.call_kind,
        bucket="",
        query_id=call.call_id,
        last_completed_at=stale,
    )

    api, _ = harvest([call], [[_tweet("1")]])
    since, until = _window(api)
    span_hours = (until - since) / 3600.0
    assert span_hours <= 2.01, (
        f"stale cursor produced a {span_hours:.1f}h window; the clamp did "
        "not apply and the fetch may truncate silently"
    )


def test_stale_cursor_advances_normally_afterward(harvest):
    from core.models import CallState

    call = _call()
    stale = datetime.now(timezone.utc) - timedelta(days=5)
    CallState.objects.create(
        brand_id=call.brand_id,
        call_id=call.call_id,
        call_kind=call.call_kind,
        bucket="",
        query_id=call.call_id,
        last_completed_at=stale,
    )
    harvest([call], [[_tweet("1")]])
    assert CallState.objects.get().last_completed_at > stale


# --- multi-call independence + dedup tolerance --------------------------


def test_one_failing_call_does_not_stall_the_others_cursors(harvest):
    """A failure on one of the six calls must not hold back the rest."""
    from core.models import CallState

    calls = [_call("B1"), _call("B2", "doubao")]
    # B1 fails, B2 succeeds (script is consumed in call order).
    api, stats = harvest(calls, [XClientRateLimitError("429"), [_tweet("1")]])

    # KTD8: B1's failed window is owned by the backlog; its cursor advanced.
    _assert_backlog_owns_failed_window(api, stats)
    assert CallState.objects.filter(call_id="B2").exists(), (
        "a failure on an earlier call blocked a later call's cursor"
    )


def test_overlapping_windows_do_not_double_insert(harvest):
    """Documents why the overlap in KTD1 is safe: the same tweet re-delivered
    in the overlap is discarded by tweet_id dedup, so cycles can afford to
    re-request the boundary."""
    from core.models import Brand, Post

    call = [_call("B1", "deepseek")]
    Brand.objects.get_or_create(nickname="deepseek")
    dup = _tweet("dup-1")
    # Must mention a real seeded brand token, else attribution drops it and
    # nothing is ever persisted (making the dedup assertion vacuous).
    dup["text"] = "DeepSeek just shipped a new model"
    harvest(call, [[dup]])
    count_after_first = Post.objects.filter(tweet_id="dup-1").count()
    harvest(call, [[dict(dup)]])

    assert count_after_first == 1
    assert Post.objects.filter(tweet_id="dup-1").count() == 1, (
        "the same tweet was inserted twice; overlapping windows would inflate "
        "counts and the overlap would not be safe"
    )


def test_empty_windows_keep_advancing_across_cycles(harvest):
    """A quiet brand must not stall: consecutive empty-but-successful sweeps
    keep moving the cursor forward (KTD5)."""
    from core.models import CallState

    call = [_call()]
    harvest(call, [[]])
    first = CallState.objects.get().last_completed_at
    harvest(call, [[]])
    # Same-second ties are a test-clock artifact; the point is that an empty
    # sweep is not treated as a failure (which would hold the cursor back).
    assert CallState.objects.get().last_completed_at >= first


# --- U6 (plan 2026-11-24-012909): missed-window coverage -----------------


def _slots(monkeypatch):
    from django.utils import timezone as django_timezone

    slot = [(datetime.now(UTC) - timedelta(hours=2)).replace(second=0, microsecond=0)]
    monkeypatch.setattr(django_timezone, "now", lambda: slot[0])
    monkeypatch.setattr(CycleRunner, "_wall_now", lambda self: slot[0])
    return slot


def test_outage_with_start_jitter_leaves_no_uncovered_second(harvest, monkeypatch):
    """KTD8 / the B9 gap: a call fails for three cycles whose start times
    jitter, then succeeds. The clamped spans and the failed windows coalesce
    into one pending backlog window, and live windows plus that window cover
    every second of the outage."""
    from core.models import HarvestBacklogWindow

    slot = _slots(monkeypatch)
    base = slot[0]
    call = [_call()]
    a1, _ = harvest(call, [[_tweet("1")]])
    failures = []
    for offset in (timedelta(minutes=15, seconds=40), timedelta(minutes=29, seconds=35),
                   timedelta(minutes=45, seconds=10)):
        slot[0] = base + offset
        failures.append(harvest(call, [XClientServerError("503")]))
    assert failures[0][1]["totals"]["n_clamped_spans_queued"] == 1
    assert failures[2][1]["totals"]["n_clamped_spans_queued"] == 1

    pending = list(HarvestBacklogWindow.objects.filter(state="pending"))
    assert len(pending) == 1
    window = pending[0]
    assert int(window.remaining_since.timestamp()) == _window(a1)[1]
    assert int(window.remaining_until.timestamp()) == _window(failures[-1][0])[1]

    slot[0] = base + timedelta(minutes=60)
    a5, recovered = harvest(call, [[_tweet("5")]])
    assert recovered["calls"][0]["status"] == "completed"
    assert _window(a5)[0] <= int(window.remaining_until.timestamp())
    assert HarvestBacklogWindow.objects.filter(pk=window.pk, state="pending").exists()


def test_cursor_older_than_a_day_is_logged_and_counted_not_queued(harvest):
    """KTD8: spans older than the backlog's max_age_hours (24) belong to an
    operator-run X post backfill; they are counted, never queued."""
    from core.models import CallState, HarvestBacklogWindow

    call = _call()
    CallState.objects.create(brand_id=call.brand_id, call_id=call.call_id, call_kind=call.call_kind,
                             bucket="", query_id=call.call_id,
                             last_completed_at=datetime.now(UTC) - timedelta(hours=25))
    _, stats = harvest([call], [[_tweet("1")]])
    assert stats["totals"]["n_clamped_spans_uncovered"] == 1
    assert stats["totals"]["n_clamped_spans_queued"] == 0
    assert not HarvestBacklogWindow.objects.exists()


def test_refused_transfer_holds_the_cursor_and_the_next_cycle_records_the_span(harvest, monkeypatch):
    """KTD8: when the backlog refuses a failed window (capacity), the cursor
    is held; once capacity frees, the next cycle records the clamped span
    instead of silently dropping it. capacity_refused is a counted event."""
    from core.models import CallState, HarvestBacklogWindow

    slot = _slots(monkeypatch)
    base = slot[0]
    call = _call()
    harvest([call], [[_tweet("1")]])
    identity = {"brand_id": call.brand_id, "call_id": call.call_id, "call_kind": call.call_kind,
                "bucket": "", "query_id": call.call_id}
    for n in range(8):
        start = base - timedelta(hours=3, minutes=10 * n)
        HarvestBacklogWindow.objects.create(
            **identity, original_since=start - timedelta(minutes=1), original_until=start,
            remaining_since=start - timedelta(minutes=1), remaining_until=start,
            reason_code="page_cap", next_attempt_at=base + timedelta(days=1),
        )
    slot[0] = base + timedelta(minutes=15)
    _, refused = harvest([call], [XClientServerError("503")])
    assert refused["calls"][0]["coverage_transfer"] == "capacity_refused"
    assert refused["calls"][0]["cursor_advanced"] is False
    assert refused["totals"]["n_backlog_capacity_refused"] == 1
    assert CallState.objects.get().last_completed_at == base

    HarvestBacklogWindow.objects.filter(reason_code="page_cap").order_by("pk").first().delete()
    slot[0] = base + timedelta(minutes=30)
    monkeypatch.setattr(CycleRunner, "_replay_backlog", lambda *a, **k: [])
    api, recovered = harvest([call], [[_tweet("3")]])
    assert recovered["totals"]["n_clamped_spans_queued"] == 1
    clamp = HarvestBacklogWindow.objects.get(reason_code="lookback_clamp")
    assert clamp.remaining_since == base
    assert int(clamp.remaining_until.timestamp()) == _window(api)[0]
