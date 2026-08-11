"""U3 regression net: pin the cursor behavior that actually broke.

Plan: docs/plans/2026-07-27-002-fix-v2-harvest-cursor-regression-plan.md
Unit U3 (R8).

WHY THIS FILE EXISTS
--------------------
v2 shipped without v1's incremental cursor.  Every 15-minute cycle re-issued
a bare `queryType=Latest` search and took the newest <=100 posts per query, so
consecutive cycles returned nearly the same posts and anything that scrolled
past that slice in between was never collected.  Daily volume fell from
~2,000-2,400 to ~1,150 and nothing errored -- no exception, no failed check,
no alert.  The dashboard just drifted down.

The sibling file `test_harvest_surface_regression_net.py` (U6) pins the
surface values that were *innocent*.  This file pins the three behaviors whose
absence caused the loss, so it cannot silently regress again:

  1. no scheduled search is unbounded,
  2. the cursor table stays live rather than becoming a fossil,
  3. consecutive windows are contiguous -- no gap between what one cycle
     ends at and the next begins at.

Assertion 1 alone would have caught the original regression on the cutover
commit.

These tests were written before the fix and observed failing against the
unwired code; a regression net that passes on the broken revision is
worthless.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner
from x_monitor.query_plan import PlannedCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

# The six calls a real cycle fires.
CYCLE_CALLS = [
    ("A", "account", "*"),
    ("C1", "brand_wide", "mimo"),
    ("C2", "brand_wide", "ernie"),
    ("B1", "brand_wide", "minimax"),
    ("B2", "brand_wide", "doubao"),
    ("B3", "brand_wide", "nemo_megatron"),
]


def _full_cycle_plan() -> list[PlannedCall]:
    return [
        PlannedCall(
            call_id=cid,
            call_kind=kind,
            brand_id=brand,
            bucket=None,
            query_string="(alpha OR beta) min_faves:0",
            query_length=27,
        )
        for cid, kind, brand in CYCLE_CALLS
    ]


class RecordingApi:
    """Captures the exact window handed to every search this cycle."""

    def __init__(self, results):
        self._results = results
        self.calls: list[dict] = []

    def run_search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return list(self._results), False  # (items, truncated)


def _tweet(tid: str):
    return {
        "id": tid,
        "author_id": f"a{tid}",
        "author_handle": "someone",
        "text": "alpha release is great",
        "lang": "en",
        "created_at": "Sat Jul 25 12:00:00 +0000 2026",
    }


@pytest.fixture
def cycle(monkeypatch):
    """Run one full six-call scheduled cycle against a recording API."""

    def _run(results=None, calls=None):
        api = RecordingApi(results if results is not None else [_tweet("1")])
        monkeypatch.setattr(
            cycle_mod,
            "plan_calls_for_cycle",
            lambda cfg=None: list(calls if calls is not None else _full_cycle_plan()),
        )
        monkeypatch.setattr(
            cycle_mod.TwitterApiClient,
            "from_env",
            classmethod(lambda cls: api),
        )
        monkeypatch.setattr(
            CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
        )
        stats = CycleRunner(cycle_kind="scheduled").run()
        return api, stats

    return _run


# --- axis 1: no unbounded search -----------------------------------------


def test_no_scheduled_search_is_unbounded(cycle):
    """THE ONE THAT WOULD HAVE CAUGHT THE ORIGINAL REGRESSION.

    If any scheduled call reaches the API without a since_time, the cycle is
    skimming the top of the stream again instead of sweeping a window, and
    daily volume silently halves.
    """
    api, _ = cycle()
    assert api.calls, "no searches were issued"
    unbounded = [
        c for c in api.calls if c.get("since_time") is None
    ]
    assert not unbounded, (
        f"{len(unbounded)}/{len(api.calls)} scheduled searches had no "
        "since_time floor. This is the exact 2026-07 regression: an unbounded "
        "Latest query returns the newest ~100 posts and everything that "
        "scrolled past between cycles is lost with no error."
    )


def test_no_scheduled_search_omits_the_upper_bound(cycle):
    """until_time must be explicit so the cursor value can equal it."""
    api, _ = cycle()
    missing = [c for c in api.calls if c.get("until_time") is None]
    assert not missing, (
        f"{len(missing)} searches had no until_time; the stored cursor can "
        "then drift from the window actually queried."
    )


def test_every_call_in_the_cycle_is_bounded_not_just_the_first(cycle):
    """Guards a partial fix that bounds only one code path."""
    api, _ = cycle()
    assert len(api.calls) == len(CYCLE_CALLS), (
        f"expected {len(CYCLE_CALLS)} searches, got {len(api.calls)}"
    )
    for c in api.calls:
        assert c["since_time"] is not None and c["until_time"] is not None


# --- axis 2: the cursor table stays live ---------------------------------


def test_cursor_table_is_written_by_a_scheduled_cycle(cycle):
    """Prod's call_state sat frozen at the cutover date because v2 never
    wrote it. A live harvest must leave a row per successful call."""
    from core.models import CallState

    cycle()
    assert CallState.objects.count() == len(CYCLE_CALLS), (
        f"expected {len(CYCLE_CALLS)} cursor rows, found "
        f"{CallState.objects.count()}. A frozen call_state table is the "
        "signature of a harvest running with no cursor at all."
    )


def test_cursor_timestamps_are_recent_not_stale(cycle):
    """Asserts liveness relative to the run, never a hardcoded date."""
    from core.models import CallState

    before = datetime.now(timezone.utc) - timedelta(minutes=1)
    cycle()
    for row in CallState.objects.all():
        assert row.last_completed_at >= before, (
            f"cursor for {row.call_id} is {row.last_completed_at}, older than "
            "this run -- the cycle is not advancing it"
        )


# --- axis 3: windows are contiguous --------------------------------------


def test_consecutive_windows_do_not_leave_a_gap(cycle):
    """The mechanism of the data loss: if cycle 2 starts after cycle 1 ended,
    the posts in between are never requested by anyone."""
    one_call = _full_cycle_plan()[:1]
    api1, _ = cycle(calls=one_call)
    api2, _ = cycle(calls=one_call)

    first_until = api1.calls[0]["until_time"]
    second_since = api2.calls[0]["since_time"]
    assert second_since <= first_until, (
        f"gap of {second_since - first_until}s between consecutive windows: "
        f"cycle 1 swept through {first_until}, cycle 2 started at "
        f"{second_since}. Posts in that gap are lost permanently."
    )


def test_cursor_actually_moves_forward_between_cycles(cycle):
    """The complement of the gap test, and the subtler failure.

    A cursor pinned at the lookback floor would look healthy (windows always
    'contiguous', rows always present) while re-sweeping the same span every
    cycle and never following the stream forward.
    """
    one_call = _full_cycle_plan()[:1]
    api1, _ = cycle(calls=one_call)
    api2, _ = cycle(calls=one_call)

    assert api2.calls[0]["since_time"] > api1.calls[0]["since_time"], (
        "cycle 2 used the same or an older floor than cycle 1 -- the cursor "
        "is not advancing, so every cycle re-requests the lookback window"
    )


def test_window_is_bounded_in_size(cycle):
    """A window wider than the lookback clamp would silently truncate
    against the per-call page ceiling (the failure this plan fixes)."""
    api, _ = cycle()
    for c in api.calls:
        span_hours = (c["until_time"] - c["since_time"]) / 3600.0
        assert span_hours <= 2.01, (
            f"call {c.get('query', '?')[:20]} requested a {span_hours:.1f}h "
            "window; wider than the clamp means possible silent truncation"
        )


# --- scope note ----------------------------------------------------------


def test_operator_backfill_is_exempt_from_the_unbounded_check(cycle, monkeypatch):
    """Documents that this net targets SCHEDULED cycles.

    The backfill command legitimately supplies its own historical window; it
    is bounded too, just not by the cursor.
    """
    since = int((datetime.now(timezone.utc) - timedelta(days=3)).timestamp())
    until = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())
    monkeypatch.setattr(
        cycle_mod.settings, "X_MONITOR_CYCLE_SINCE_TIME", since, raising=False
    )
    monkeypatch.setattr(
        cycle_mod.settings, "X_MONITOR_CYCLE_UNTIL_TIME", until, raising=False
    )
    api, _ = cycle(calls=_full_cycle_plan()[:1])
    assert api.calls[0]["since_time"] == since
    assert api.calls[0]["until_time"] == until
