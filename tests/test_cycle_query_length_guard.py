"""U5 tests: post-injection query length guard.

Plan: docs/plans/2026-07-27-002-fix-v2-harvest-cursor-regression-plan.md
Unit U5 (R7, KTD6).

`assert_under_length_cap` runs inside plan_calls on the PRE-injection query,
so it cannot see the ~44 chars the cursor's time operators add.  That gap
matters because an over-cap query is the nastiest failure mode in this
pipeline: TwitterAPI.io answers it with zero results and NO error, so the
call looks like a legitimately quiet window -- and once the cursor ships, a
"successful empty window" advances the cursor straight past the span that was
never actually searched.

So the guard must do two things, and both are tested here: refuse to issue
the call, and leave the cursor unmoved so the window is retried.

The second assertion below is the important one in the other direction: C1
sits at 505/512 after injection today, so a guard that is even slightly too
strict would silently disable a real production call.
"""

from __future__ import annotations

import pytest

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner, _cursor_key
from x_monitor.queries import X_LENGTH_CAP
from x_monitor.query_plan import PlannedCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

# Matches the real injected suffix: " since_time:<10> until_time:<10>".
TIME_OPERATOR_OVERHEAD = 44


def _planned(call_id: str, query: str) -> PlannedCall:
    return PlannedCall(
        call_id=call_id,
        call_kind="brand_wide",
        brand_id="minimax",
        bucket=None,
        query_string=query,
        query_length=len(query),
    )


def _query_of_length(n: int) -> str:
    """Build a syntactically plausible query of exactly n chars."""
    head = "(alpha OR "
    tail = ") min_faves:0"
    filler = "x" * (n - len(head) - len(tail))
    q = f"{head}{filler}{tail}"
    assert len(q) == n
    return q


class FakeApi:
    def __init__(self):
        self.calls: list[dict] = []

    def run_search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return [
            {
                "id": "1",
                "author_id": "a1",
                "author_handle": "someone",
                "text": "alpha release",
                "lang": "en",
                "created_at": "Sat Jul 25 12:00:00 +0000 2026",
            }
        ], False  # (items, truncated)


@pytest.fixture
def wired(monkeypatch, seeded_policy_keywords):
    def _run(calls):
        api = FakeApi()
        monkeypatch.setattr(
            cycle_mod, "plan_calls_for_cycle", lambda cfg=None: list(calls)
        )
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

    return _run


def _entry(stats, call_id):
    """Return the LIVE summary entry for a call.

    run() records a "planned" entry for every call up front and then appends a
    second entry per call during the live loop, so each call_id appears twice.
    The last one is the outcome.
    """
    matches = [c for c in stats["calls"] if c["call_id"] == call_id]
    assert matches, f"no summary entry for {call_id}"
    return matches[-1]


# --- the guard trips above the cap ---------------------------------------


def test_over_cap_query_is_not_sent(wired):
    """500 base + 44 operators = 544 > 512. No credits should be burned."""
    call = _planned("BIG", _query_of_length(500))
    api, _ = wired([call])
    assert api.calls == [], (
        "an over-cap query was still sent; TwitterAPI.io will return zero "
        "results with no error and the window will look quiet"
    )


def test_over_cap_query_is_reported_distinctly(wired):
    """It must not masquerade as a quiet window in the run summary."""
    call = _planned("BIG", _query_of_length(500))
    _, stats = wired([call])
    assert _entry(stats, "BIG")["status"] == "length_cap_exceeded"
    assert any("length" in e.lower() for e in stats["errors"]), (
        f"over-cap call not surfaced in cycle errors: {stats['errors']}"
    )


def test_over_cap_call_does_not_advance_cursor(wired):
    """THE POINT OF THE GUARD.

    Without this, an over-cap call returns zero results, looks like a
    successful empty sweep, advances the cursor, and the unsearched window is
    lost permanently.
    """
    from core.models import CallState

    call = _planned("BIG", _query_of_length(500))
    wired([call])
    assert not CallState.objects.filter(**_cursor_key(call)).exists(), (
        "cursor advanced past a window that was never actually searched"
    )


def test_over_cap_call_does_not_block_other_calls(wired):
    """One bad spec must not take the whole cycle down."""
    big = _planned("BIG", _query_of_length(500))
    ok = _planned("OK", "(alpha OR beta) min_faves:0")
    api, stats = wired([big, ok])
    assert len(api.calls) == 1
    assert api.calls[0]["query"].startswith("(alpha OR beta)")
    assert _entry(stats, "OK")["status"] in {"completed", "no_results"}


# --- the guard does NOT trip at or below the cap -------------------------


def test_c1_real_length_still_passes(wired):
    """C1 measured 461 base -> 505 after operators -> 7 chars spare.

    A guard that is off by a few chars here would silently disable a real
    production call, which is the same class of harm it exists to prevent.
    """
    call = _planned("C1LIKE", _query_of_length(461))
    api, stats = wired([call])
    assert len(api.calls) == 1, (
        "C1's real length was rejected; the guard is too strict and would "
        "disable a working production call"
    )
    assert _entry(stats, "C1LIKE")["status"] in {"completed", "no_results"}


def test_query_exactly_at_the_cap_after_injection_passes(wired):
    """Boundary: base + 44 == 512 exactly is still legal."""
    call = _planned("EDGE", _query_of_length(X_LENGTH_CAP - TIME_OPERATOR_OVERHEAD))
    api, _ = wired([call])
    assert len(api.calls) == 1, "a query exactly at the cap was rejected"


def test_query_one_char_over_the_cap_is_rejected(wired):
    """Boundary: one char past the cap must trip."""
    call = _planned(
        "EDGE1", _query_of_length(X_LENGTH_CAP - TIME_OPERATOR_OVERHEAD + 1)
    )
    api, _ = wired([call])
    assert api.calls == [], "a query one char over the cap was still sent"


def test_short_query_is_unaffected(wired):
    """Call A is ~20 chars; the guard must be invisible to it."""
    call = _planned("A", "(list:123) min_faves:0")
    api, _ = wired([call])
    assert len(api.calls) == 1
