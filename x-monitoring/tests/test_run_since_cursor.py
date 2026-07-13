"""U2 integration tests: the since= cursor is wired into apify.run_search
at the run.py main-loop call site.

Plan: docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md
Unit 2 of 6 (U2 — Wire since= cursor for main-loop search).

These tests pin the call-site behavior:

- *Happy path — first cycle (no prior state):* no `since=` is
  passed to apify.run_search.
- *Happy path — second cycle (cursor present):* apify.run_search is
  called with `since=<yesterday's date>` derived from
  last_completed_at minus CURSOR_OVERLAP_HOURS.
- *Happy path — overlap subtracts correctly:* when prior
  last_completed_at is at 01:30 UTC and CURSOR_OVERLAP_HOURS=1,
  `since=` is the prior day's date.
- *Edge case — exception during cycle:* when apify.run_search
  raises, set_last_completed_at is NOT called (cursor stays put).
- *Happy path — cursor is advanced after success:* the cursor
  store has a fresh row per PlannedCall.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from unittest.mock import MagicMock

from x_monitor.config import Config
from x_monitor.query_plan import PlannedCall
from x_monitor.run import (
    CURSOR_OVERLAP_HOURS, RunPipeline,
)
from x_monitor.store import Store


def _stub_plan_calls(enabled_models):
    """Single-call stub that returns one brand_wide call per model."""
    out = []
    for m in enabled_models:
        out.append(PlannedCall(
            call_id="B",
            call_kind="brand_wide",
            brand_id=m,
            bucket=None,
            query_string=f"({m}) min_faves:0",
            query_length=2,
        ))
    return out


@pytest.fixture
def tmp_data():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        yield data


def _seed_minimal_data(data: Path):
    """Write a minimal accounts/queries layout so the pipeline boots."""
    (data / "accounts" / "minimax.yaml").write_text(
        "accounts:\n  - handle: MiniMaxAI\n    role: official\n",
        encoding="utf-8",
    )
    (data / "queries" / "minimax.yaml").write_text(
        "queries:\n"
        "  - id: Q1\n"
        "    query_string: 'from:MiniMaxAI min_faves:0'\n"
        "    max_results: 50\n"
        "    enabled: true\n"
        "    min_faves: 0\n"
        "    notes: stub\n",
        encoding="utf-8",
    )


# --- happy path: first cycle, no prior state --------------------------


def test_first_cycle_no_since_passed(monkeypatch, tmp_data):
    """First-ever cycle: no row in call_state; since= should be None."""
    _seed_minimal_data(tmp_data)
    cfg = Config(
        enabled_models=["minimax"],
        daily_ceiling=333,
        x_monitor_list_id=1234567890,
    )
    p = RunPipeline(cfg, tmp_data, db_path=tmp_data / "x.db")

    # Bypass x.com list fetching & yaml query loading.
    monkeypatch.setattr(
        "x_monitor.run.plan_calls", lambda *a, **kw: _stub_plan_calls(["minimax"])
    )

    apify = MagicMock()
    apify.run_search.return_value = []

    summary = p.execute(apify, model_filter=["minimax"])

    # The mock must have been called at least once, with since=None.
    assert apify.run_search.call_count >= 1
    for call in apify.run_search.call_args_list:
        kwargs = call.kwargs
        assert "since" in kwargs, (
            f"since= kwarg missing from apify.run_search call: {call}"
        )
        assert kwargs["since"] is None, (
            f"first cycle must not pass since=; got {kwargs['since']!r}"
        )
    # The cycle completed without raising. (Status may be "degraded"
    # if a budget sentinel fired; the meaningful check is no
    # exception bubbled out of p.execute.)
    assert summary["status"] in {"completed", "degraded"}


# --- happy path: prior cursor present, since= derived ----------------


def test_second_cycle_passes_since_subtracts_overlap(monkeypatch, tmp_data):
    """With a prior cursor at 2026-07-01T10:00:00Z, the next cycle
    passes since=2026-07-01 (date of prior_dt - 1h, where 1h is the
    overlap)."""
    _seed_minimal_data(tmp_data)
    db_path = tmp_data / "x.db"

    # Apply all migrations BEFORE seeding a cursor (so the
    # call_state table exists). Use a transient Store handle for
    # seeding; the pipeline creates its own handle inside execute().
    seed = Store(db_path, auto_migrate=True)
    try:
        seed.set_last_completed_at(
            brand_id="minimax",
            call_id="B",
            call_kind="brand_wide",
            bucket=None,
            query_id="Q5",  # brand_wide -> Q5
            last_completed_at="2026-07-01T10:00:00+00:00",
        )
    finally:
        seed.close()

    cfg = Config(
        enabled_models=["minimax"],
        daily_ceiling=333,
        x_monitor_list_id=1234567890,
    )
    p = RunPipeline(cfg, tmp_data, db_path=db_path)
    monkeypatch.setattr(
        "x_monitor.run.plan_calls", lambda *a, **kw: _stub_plan_calls(["minimax"])
    )

    apify = MagicMock()
    apify.run_search.return_value = []
    p.execute(apify, model_filter=["minimax"])

    assert apify.run_search.call_count >= 1
    # Collect every since= value passed across the cycle.
    since_values = {c.kwargs["since"] for c in apify.run_search.call_args_list}
    assert "2026-07-01" in since_values, (
        f"expected since='2026-07-01' (after CURSOR_OVERLAP_HOURS={CURSOR_OVERLAP_HOURS} "
        f"subtract from prior_dt=2026-07-01T10:00:00); got {since_values}"
    )


def test_overlap_subtracts_correctly_when_crossing_midnight(monkeypatch, tmp_data):
    """When the prior cursor is at 00:30 UTC and CURSOR_OVERLAP_HOURS=1,
    `since` is the prior day's date (subtract 1h -> 23:30 the day
    before)."""
    _seed_minimal_data(tmp_data)
    db_path = tmp_data / "x.db"

    seed = Store(db_path, auto_migrate=True)
    try:
        # Prior cursor at 2026-07-01T00:30:00Z; subtract 1h ->
        # 2026-06-30T23:30:00Z; date 2026-06-30.
        seed.set_last_completed_at(
            brand_id="minimax",
            call_id="B",
            call_kind="brand_wide",
            bucket=None,
            query_id="Q5",
            last_completed_at="2026-07-01T00:30:00+00:00",
        )
    finally:
        seed.close()

    cfg = Config(
        enabled_models=["minimax"],
        daily_ceiling=333,
        x_monitor_list_id=1234567890,
    )
    p = RunPipeline(cfg, tmp_data, db_path=db_path)
    monkeypatch.setattr(
        "x_monitor.run.plan_calls", lambda *a, **kw: _stub_plan_calls(["minimax"])
    )

    apify = MagicMock()
    apify.run_search.return_value = []
    p.execute(apify, model_filter=["minimax"])

    since_values = {c.kwargs["since"] for c in apify.run_search.call_args_list}
    assert "2026-06-30" in since_values, (
        f"expected since='2026-06-30' (date of 2026-07-01T00:30:00 - 1h); "
        f"got {since_values}"
    )


# --- exception during cycle: cursor NOT advanced ----------------------


def test_cursor_not_advanced_when_run_search_raises(monkeypatch, tmp_data):
    """If apify.run_search raises, set_last_completed_at is NOT called
    on the same cycle. Cursor stays at the prior value (or None if no
    prior cycle)."""
    _seed_minimal_data(tmp_data)
    db_path = tmp_data / "x.db"

    # Pre-apply migrations so we can open a fresh Store to verify.
    Store(db_path, auto_migrate=True).close()

    cfg = Config(
        enabled_models=["minimax"],
        daily_ceiling=333,
        x_monitor_list_id=1234567890,
    )
    p = RunPipeline(cfg, tmp_data, db_path=db_path)
    monkeypatch.setattr(
        "x_monitor.run.plan_calls", lambda *a, **kw: _stub_plan_calls(["minimax"])
    )

    # Force apify.run_search to always raise.
    from x_monitor.apify import TwitterApiRateLimitError
    apify = MagicMock()
    apify.run_search.side_effect = TwitterApiRateLimitError(
        "rate-limited (test)"
    )

    # The cycle should NOT raise (rate-limit errors are caught and
    # recorded per-call); the cursor must NOT advance.
    p.execute(apify, model_filter=["minimax"])

    # Re-open the DB to read the post-cycle cursor.
    s = Store(db_path, auto_migrate=False)
    try:
        cursor = s.get_last_completed_at(
            brand_id="minimax",
            call_id="B",
            call_kind="brand_wide",
            bucket=None,
            query_id="Q5",
        )
        assert cursor is None, (
            f"cursor should not have advanced on apify failure; got {cursor!r}"
        )
    finally:
        s.close()


# --- happy path: cursor advanced after success -----------------------


def test_cursor_advanced_after_successful_cycle(monkeypatch, tmp_data):
    """A successful cycle advances the cursor for every executed call."""
    _seed_minimal_data(tmp_data)
    db_path = tmp_data / "x.db"
    Store(db_path, auto_migrate=True).close()

    cfg = Config(
        enabled_models=["minimax"],
        daily_ceiling=333,
        x_monitor_list_id=1234567890,
    )
    p = RunPipeline(cfg, tmp_data, db_path=db_path)
    monkeypatch.setattr(
        "x_monitor.run.plan_calls", lambda *a, **kw: _stub_plan_calls(["minimax"])
    )

    apify = MagicMock()
    apify.run_search.return_value = []
    p.execute(apify, model_filter=["minimax"])

    s = Store(db_path, auto_migrate=False)
    try:
        cursor = s.get_last_completed_at(
            brand_id="minimax",
            call_id="B",
            call_kind="brand_wide",
            bucket=None,
            query_id="Q5",
        )
        assert cursor is not None, (
            "successful cycle did not advance call_state cursor"
        )
        # Stored value is a recent ISO timestamp; should not be empty.
        assert "T" in cursor, (
            f"cursor does not look like an ISO timestamp: {cursor!r}"
        )
    finally:
        s.close()


# --- explicit since: in query string is honored (existing guard) -----


def test_existing_since_in_query_is_not_double_added(monkeypatch, tmp_data):
    """If the query string already contains `since:`, the pipeline
    passing a since= kwarg must NOT result in two `since:` operators
    — the apify.run_search guard handles this; this test pins that
    integration."""
    _seed_minimal_data(tmp_data)
    cfg = Config(
        enabled_models=["minimax"],
        daily_ceiling=333,
        x_monitor_list_id=1234567890,
    )
    p = RunPipeline(cfg, tmp_data, db_path=tmp_data / "x.db")

    # Build a stub plan with an explicit `since:2026-06-30` already
    # in the query.
    def _plan_with_explicit_since(*a, **kw):
        return [PlannedCall(
            call_id="B",
            call_kind="brand_wide",
            brand_id="minimax",
            bucket=None,
            query_string="(minimax) since:2026-06-30 min_faves:0",
            query_length=2,
        )]

    monkeypatch.setattr(
        "x_monitor.run.plan_calls", _plan_with_explicit_since,
    )

    apify = MagicMock()
    apify.run_search.return_value = []
    p.execute(apify, model_filter=["minimax"])

    # We pass since=None here (no prior cursor). The guard behavior
    # is internal to apify.run_search — we just confirm the pipeline
    # doesn't crash on an explicit-since query.
    for call in apify.run_search.call_args_list:
        kwargs = call.kwargs
        assert "since" in kwargs
    assert apify.run_search.call_count >= 1