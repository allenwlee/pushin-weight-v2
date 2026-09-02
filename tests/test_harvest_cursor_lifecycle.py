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

from datetime import datetime, timedelta, timezone

import pytest

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner
from x_monitor.apify import TwitterApiRateLimitError, TwitterApiServerError
from x_monitor.config import CycleConfig
from x_monitor.query_plan import PlannedCall

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

    def __init__(self, script):
        self._script = list(script)
        self.calls: list[dict] = []

    def run_search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        step = self._script.pop(0) if self._script else []
        if isinstance(step, Exception):
            raise step
        return list(step), False  # (items, truncated)


@pytest.fixture
def harvest(monkeypatch, seeded_policy_keywords):
    """Drive N sequential cycles, returning the window each one requested."""

    def _run_cycle(calls, script):
        api = ScriptedApi(script)
        monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None: list(calls))
        monkeypatch.setattr(
            cycle_mod.TwitterApiClient,
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


def test_failed_cycle_does_not_advance_the_cursor(harvest):
    from core.models import CallState

    call = [_call()]
    harvest(call, [[_tweet("1")]])
    first = CallState.objects.get().last_completed_at

    harvest(call, [TwitterApiRateLimitError("429")])
    assert CallState.objects.get().last_completed_at == first, (
        "cursor moved despite a failed fetch; that window is now unreachable"
    )


def test_cycle_after_a_failure_recovers_the_missed_span(harvest):
    """THE KEY LIFECYCLE PROPERTY.

    Cycle 2 fails, so cycle 3's window must still reach back far enough to
    cover what cycle 2 was supposed to sweep. Without the hold, a transient
    429 would permanently lose a window.
    """
    call = [_call()]
    a1, _ = harvest(call, [[_tweet("1")]])
    a2, _ = harvest(call, [TwitterApiRateLimitError("429")])
    a3, _ = harvest(call, [[_tweet("3")]])

    cycle1_until = _window(a1)[1]
    cycle2_until = _window(a2)[1]
    cycle3_since = _window(a3)[0]

    assert cycle3_since <= cycle1_until, (
        "cycle 3 did not reach back to cycle 1's end; the failed cycle's "
        "window was skipped"
    )
    assert cycle3_since <= cycle2_until, (
        "cycle 3 does not cover the span cycle 2 failed to fetch"
    )


def test_server_error_also_holds_the_cursor(harvest):
    """Not just rate limits -- any transient failure must hold."""
    from core.models import CallState

    call = [_call()]
    harvest(call, [[_tweet("1")]])
    first = CallState.objects.get().last_completed_at
    harvest(call, [TwitterApiServerError("503")])
    assert CallState.objects.get().last_completed_at == first


def test_recovery_resumes_normal_advance(harvest):
    from core.models import CallState

    call = [_call()]
    harvest(call, [[_tweet("1")]])
    held = CallState.objects.get().last_completed_at
    harvest(call, [TwitterApiRateLimitError("429")])
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
    harvest(calls, [TwitterApiRateLimitError("429"), [_tweet("1")]])

    assert not CallState.objects.filter(call_id="B1").exists()
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
