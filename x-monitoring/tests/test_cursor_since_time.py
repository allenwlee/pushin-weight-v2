"""Regression tests for the cursor precision fix.

Plan 2026-07-13-001 follow-up: the runtime's `since:` operator form
truncated the cursor to date-only, causing each cycle to re-fetch
posts that were already in the DB (because TwitterAPI.io reset
the window to midnight UTC). The DB-level dedupe then dropped
them as duplicates — wasted TwitterAPI.io credits, but the user
saw it as low `n_inserted` relative to `n_results`.

First fix (commit 37c5f08): thread a unix-epoch cursor via a
`sinceTime` query param so the window can advance minute-to-minute.

Second fix (this commit, 2026-07-14): TwitterAPI.io silently DROPS
unknown URL parameters on `advanced_search`, so `sinceTime` as a
URL param was a no-op (verified by direct API test — see
docs/debug/2026-07-14-160222-call-state-not-persisting.md). The
working form is the inline operator `since_time:<epoch>` injected
into the `query` parameter itself. This test was rewritten to pin
that behavior. The `since:` operator form remains as a defensive
date floor.

This test pins:
  (a) apify.run_search accepts `since_time` and injects it into the
      query string as ` since_time:<epoch>` (NOT as a `sinceTime`
      URL param, which TwitterAPI.io silently drops).
  (b) run.py converts prior_iso to unix epoch (NOT date-only
      truncation) when computing the cursor.
  (c) CURSOR_OVERLAP_HOURS is still subtracted before the timestamp
      is sent.
  (d) The `since:` date form is preserved as a defensive floor.
"""

from __future__ import annotations

import re
from pathlib import Path


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


def test_run_search_injects_since_time_as_inline_operator() -> None:
    """run_search must inject `since_time:<epoch>` INTO THE QUERY STRING
    (the only form TwitterAPI.io honors on advanced_search), NOT as a
    separate URL param."""
    src = _read("x_monitor/apify.py")
    # Look for the explicit inline-operator injection in run_search.
    pattern = r"effective_query\s*=\s*f\"\{effective_query\}\s*since_time:\{int\(since_time\)\}\""
    assert re.search(pattern, src), (
        "run_search must inject `since_time:<int(since_time)>` into the "
        "query string. TwitterAPI.io silently drops sinceTime as a URL "
        "param on advanced_search; the inline operator is the only "
        "working form."
    )


def test_walk_search_does_not_write_since_time_as_url_param() -> None:
    """_walk_search must NOT write `params['sinceTime']` in its body —
    TwitterAPI.io silently drops unknown URL params on advanced_search."""
    src = _read("x_monitor/apify.py")
    # We slice from the first executable statement after the docstring
    # (the `out: list[dict[str, Any]] = []` line) up to the matching
    # `return` — docstrings may legitimately mention `sinceTime`.
    body_pattern = re.compile(
        r"def _walk_search.*?\"\"\"\s*\n\s*out:.*?(?=^    def )",
        re.DOTALL | re.MULTILINE,
    )
    walk_body = body_pattern.search(src)
    assert walk_body, "_walk_search body slice not found"
    assert 'params["sinceTime"]' not in walk_body.group(0), (
        "_walk_search must NOT write params['sinceTime'] in its body — "
        "TwitterAPI.io advanced_search silently drops unknown URL params. "
        "The time filter must be in the query string."
    )


def test_walk_search_does_not_inject_since_time_into_query_string() -> None:
    """_walk_search delegates query assembly to run_search; it must
    not re-inject since_time itself."""
    src = _read("x_monitor/apify.py")
    walk_section_pattern = re.compile(
        r"def _walk_search.*?def run_search", re.DOTALL
    )
    walk_body = walk_section_pattern.search(src).group(0)
    bad_patterns = [
        r"effective_query\s*=.*since_time",
        r"query\s*\+.*since_time",
        r"since_time:\{",
    ]
    for pat in bad_patterns:
        assert not re.search(pat, walk_body), (
            f"_walk_search must not inject since_time into query itself; "
            f"run_search owns query assembly. Found pattern: {pat}"
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
    case TwitterAPI.io's `since_time:` operator semantics drift."""
    src = _read("x_monitor/run.py")
    assert "since_cursor = since_dt.date().isoformat()" in src, (
        "run.py must still emit `since_cursor = since_dt.date().isoformat()` "
        "as the defensive date-floor form."
    )


def test_apify_run_search_injects_since_time_into_query_end_to_end() -> None:
    """End-to-end smoke: when apify.run_search is called with
    since_time, the rendered query string contains `since_time:<n>`
    and the URL params dict does NOT carry a separate sinceTime."""
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

    # The inline operator MUST be in the query.
    assert "since_time:1735689600" in captured["params"]["query"], (
        f"expected inline `since_time:1735689600` in query, got "
        f"{captured['params']['query']!r}"
    )
    # The URL params dict MUST NOT carry `sinceTime` — TwitterAPI.io
    # silently drops it on advanced_search.
    assert "sinceTime" not in captured["params"], (
        f"`sinceTime` must NOT be a URL param on advanced_search; "
        f"got {captured['params']}"
    )


def test_run_search_injects_until_time_when_since_time_set() -> None:
    """When since_time is provided, run_search must ALSO inject the
    matching upper bound `until_time:<now>` per TwitterAPI.io's working
    pattern. Both bounds must be inline operators (URL-param forms are
    silently dropped)."""
    src = _read("x_monitor/apify.py")
    # The injection block in run_search must reference until_time.
    pattern = (
        r'if "until_time:" not in effective_query:\s*\n'
        r'\s*effective_query = f"\{effective_query\} until_time:\{int\(time\.time\(\)\)\}"'
    )
    assert re.search(pattern, src), (
        "run_search must inject `until_time:<int(time.time())>` when "
        "since_time is provided. TwitterAPI.io's verified-working pattern "
        "uses both bounds — `since_time:<floor> until_time:<now>`."
    )


def test_apify_run_search_injects_both_bounds_end_to_end() -> None:
    """End-to-end smoke: when since_time is set, the rendered query
    string contains BOTH `since_time:<n>` and `until_time:<now>`."""
    import time as _time
    from x_monitor.apify import TwitterApiClient

    captured: dict = {}

    def fake_get(path, params):
        captured["params"] = dict(params)
        return {"tweets": [], "has_next_page": False, "next_cursor": None}

    api = TwitterApiClient(api_key="test")
    api._get = fake_get  # type: ignore[method-assign]

    before = int(_time.time())
    api.run_search(
        "(minimax OR 海螺) min_faves:0",
        max_results=10,
        max_pages=1,
        since_time=1735689600,
    )
    after = int(_time.time())

    query = captured["params"]["query"]
    assert "since_time:1735689600" in query, (
        f"expected inline `since_time:1735689600` in query, got {query!r}"
    )
    # Upper bound must be present, bracketing the call moment.
    import re as _re
    m = _re.search(r"until_time:(\d+)", query)
    assert m is not None, (
        f"expected inline `until_time:<n>` in query, got {query!r}"
    )
    until_ts = int(m.group(1))
    assert before <= until_ts <= after + 1, (
        f"until_time:{until_ts} is not bracketing the call moment "
        f"[{before}, {after}]"
    )
    # URL params dict must NOT carry untilTime either.
    assert "untilTime" not in captured["params"], (
        f"`untilTime` must NOT be a URL param on advanced_search; "
        f"got {captured['params']}"
    )


def test_run_search_no_until_time_when_no_since_time() -> None:
    """If the caller doesn't pass since_time, run_search must NOT inject
    until_time either — that would be a behavior change for callers that
    only want a static query."""
    from x_monitor.apify import TwitterApiClient

    captured: dict = {}

    def fake_get(path, params):
        captured["params"] = dict(params)
        return {"tweets": [], "has_next_page": False, "next_cursor": None}

    api = TwitterApiClient(api_key="test")
    api._get = fake_get  # type: ignore[method-assign]

    api.run_search(
        "(minimax OR 海螺) min_faves:0",
        max_results=10,
        max_pages=1,
    )

    assert "until_time:" not in captured["params"]["query"], (
        "run_search must NOT inject until_time when since_time is unset "
        "(that's a behavior change for callers using a static query)."
    )
    assert "since_time:" not in captured["params"]["query"], (
        "run_search must NOT inject since_time when since_time is unset."
    )
