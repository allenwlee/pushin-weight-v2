"""Regression tests for the cursor precision fix.

Plan 2026-07-13-001 follow-up: the runtime's `since:` operator form
truncated the cursor to date-only, causing each cycle to re-fetch
posts that were already in the DB (because TwitterAPI.io reset
the window to midnight UTC). The DB-level dedupe then dropped
them as duplicates — wasted TwitterAPI.io credits, but the user
saw it as low `n_inserted` relative to `n_results`.

Fix: thread a unix-epoch cursor (`sinceTime` query param) through
the advanced_search path so the window can advance minute-to-minute.
The `since:` operator form is kept as a defensive date floor.

This test pins:
  (a) apify.run_search accepts `since_time` and passes it as the
      `sinceTime` query param (NOT as a `since:` operator injection).
  (b) run.py converts prior_iso to unix epoch (NOT date-only
      truncation) when computing the cursor.
  (c) CURSOR_OVERLAP_HOURS is still subtracted before the timestamp
      is sent.
  (d) The `since:` date form is preserved as a defensive floor.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_apify_run_search_accepts_since_time_kwarg() -> None:
    """apify.run_search must accept `since_time: int | None = None`
    as a keyword-only argument."""
    src = _read("x_monitor/apify.py")
    pattern = r"def run_search\([^{]*since_time:\s*int\s*\|\s*None\s*=\s*None"
    assert re.search(pattern, src, re.DOTALL), (
        "apify.run_search must accept since_time: int | None = None"
    )


def test_walk_search_passes_since_time_as_query_param() -> None:
    """_walk_search must pass sinceTime (NOT since: operator injection)
    as a separate query param when since_time is set."""
    src = _read("x_monitor/apify.py")
    # Look for the explicit sinceTime param write.
    assert 'params["sinceTime"] = int(since_time)' in src, (
        "_walk_search must write `params['sinceTime'] = int(since_time)` "
        "when since_time is set."
    )


def test_walk_search_does_not_inject_since_time_into_query_string() -> None:
    """Critical: since_time must NOT be appended to the query string
    as `since:<epoch>` (the operator form has no time precision and
    would defeat the fix)."""
    src = _read("x_monitor/apify.py")
    # The query string assembly block must not include since_time.
    # Walk the function body and confirm no `f"...{since_time}"` or
    # similar leakage.
    bad_patterns = [
        r"effective_query\s*=.*since_time",
        r"query\s*\+.*since_time",
        r"since:\{\s*since_time",
    ]
    for pat in bad_patterns:
        assert not re.search(pat, src), (
            f"_walk_search / run_search must NOT inject since_time "
            f"into the query string. Found pattern: {pat}"
        )


def test_run_py_converts_prior_iso_to_unix_epoch() -> None:
    """run.py must compute since_time_epoch from prior_iso as a unix
    timestamp — NOT truncate to a date."""
    src = _read("x_monitor/run.py")
    # The conversion must use .timestamp() (epoch seconds), not
    # .date().isoformat() (date-only) for the epoch cursor.
    assert "since_time_epoch = int(since_dt.timestamp())" in src, (
        "run.py must compute since_time_epoch = int(since_dt.timestamp()) "
        "(unix epoch, sub-day precision)."
    )


def test_run_py_passes_since_time_to_run_search() -> None:
    """run.py must pass since_time=since_time_epoch to apify.run_search."""
    src = _read("x_monitor/run.py")
    assert "since_time=since_time_epoch" in src, (
        "run.py must thread `since_time=since_time_epoch` to "
        "apify.run_search() so the unix-epoch cursor reaches TwitterAPI.io."
    )


def test_cursor_overlap_still_subtracted() -> None:
    """CURSOR_OVERLAP_HOURS must still be subtracted before computing
    since_dt — the fix is precision, not removing the overlap buffer."""
    src = _read("x_monitor/run.py")
    # The overlap subtraction must precede the timestamp extraction.
    pattern = r"since_dt\s*=\s*prior_dt\s*-\s*timedelta\(\s*hours=CURSOR_OVERLAP_HOURS\s*\)"
    assert re.search(pattern, src), (
        "run.py must still subtract CURSOR_OVERLAP_HOURS before "
        "computing the sinceTime cursor."
    )


def test_since_date_form_kept_as_defensive_floor() -> None:
    """The `since:` (date-only) form is preserved as a hard floor in
    case TwitterAPI.io's sinceTime semantics drift."""
    src = _read("x_monitor/run.py")
    assert "since_cursor = since_dt.date().isoformat()" in src, (
        "run.py must still emit `since_cursor = since_dt.date().isoformat()` "
        "as the defensive date-floor form."
    )


def test_apify_run_search_passes_since_time_through_to_walk() -> None:
    """End-to-end smoke: when apify.run_search is called with
    since_time, _walk_search receives it and the params dict has
    `sinceTime` as a separate query param."""
    from x_monitor.apify import TwitterApiClient

    # Mock the network layer so we can introspect the params dict.
    captured: dict = {}
    def fake_get(path, params):
        captured["path"] = path
        captured["params"] = dict(params)
        return {"tweets": [], "has_next_page": False, "next_cursor": None}

    api = TwitterApiClient(api_key="test")
    api._get = fake_get  # type: ignore[method-assign]

    api.run_search(
        "(minimax OR 海螺) min_faves:0",
        max_results=10,
        max_pages=1,
        since_time=1735689600,  # 2025-01-01 00:00:00 UTC
    )

    assert captured["params"].get("sinceTime") == 1735689600, (
        f"expected sinceTime=1735689600 in query params, got "
        f"{captured['params']}"
    )
    # Confirm `since:` operator is NOT in the query string.
    assert "since:" not in captured["params"]["query"], (
        f"since_time must NOT be appended to the query as `since:<n>`. "
        f"Got query: {captured['params']['query']!r}"
    )