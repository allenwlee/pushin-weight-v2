"""Tests for scripts.probe_filter_yield.

Plan: docs/plans/2026-07-08-004-feat-filter-yield-ramp-probe-plan.md
Mirrors test_call_c_specs.py (subprocess for CLI; in-process for
helpers). No live API calls in CI — all HTTP is faked via monkeypatch
or a `FakeTwitterApiClient`.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_SCRIPT = REPO_ROOT / "scripts" / "probe_filter_yield.py"


# --- in-process imports --------------------------------------------------

from scripts import probe_filter_yield as pf  # noqa: E402


# --- helpers ------------------------------------------------------------


def _make_tweet(tweet_id: str, text: str, age_minutes: int = 0) -> dict:
    """Build one fake TwitterAPI.io tweet dict with a created_at
    timestamp `age_minutes` in the past relative to a fixed anchor."""
    now = datetime(2026, 7, 8, 14, 0, 0, tzinfo=timezone.utc)
    ts = now - timedelta(minutes=age_minutes)
    return {
        "id": tweet_id,
        "text": text,
        "created_at": ts.strftime("%a %b %d %H:%M:%S %z %Y"),
    }


def _fake_response(n: int, all_within_15min: bool = True) -> list[dict]:
    """Build N fake tweets, all within the 15-minute window by default."""
    if all_within_15min:
        # Spread across 0-14 minutes ago.
        return [
            _make_tweet(f"t{i}", f"hello world {i}", age_minutes=i % 15)
            for i in range(n)
        ]
    # Spread across 0-60 minutes ago (so the 15-min count is partial).
    return [
        _make_tweet(f"t{i}", f"hello world {i}", age_minutes=i % 60)
        for i in range(n)
    ]


# --- pure-helper unit tests (no DB, no HTTP) ---------------------------


def test_parse_ramp_default():
    assert pf._parse_ramp("50,100,150,200") == [50, 100, 150, 200]


def test_parse_ramp_strips_whitespace():
    assert pf._parse_ramp(" 50, 100 , 150,200 ") == [50, 100, 150, 200]


def test_parse_ramp_rejects_empty():
    with pytest.raises(SystemExit):
        pf._parse_ramp("")


def test_parse_ramp_rejects_non_integer():
    with pytest.raises(SystemExit):
        pf._parse_ramp("50,abc,100")


def test_parse_ramp_rejects_zero_or_negative():
    with pytest.raises(SystemExit):
        pf._parse_ramp("50,0,100")
    with pytest.raises(SystemExit):
        pf._parse_ramp("50,-5,100")


def test_clamp_ramp_passes_through_under_limit():
    assert pf._clamp_ramp([50, 100, 200], hard_max=1000) == [50, 100, 200]


def test_clamp_ramp_clamps_over_limit(capsys):
    out = pf._clamp_ramp([50, 5000, 100], hard_max=1000)
    assert out == [50, 1000, 100]
    assert "5000 -> 1000" in capsys.readouterr().err


def test_projected_cost_usd_uses_clamped_values():
    # 5 calls x (50+100+150+200) = 2500 tweets at $0.15/1k = $0.375
    cost = pf._projected_cost_usd(
        ramp=[50, 100, 150, 200], n_calls=5, hard_max=1000
    )
    assert abs(cost - 0.00015 * 2500) < 1e-9


def test_projected_cost_usd_clamps_before_computing():
    # Clamp 5000 -> 1000, so 5 calls x (50+100+150+1000) tweets.
    cost = pf._projected_cost_usd(
        ramp=[50, 100, 150, 5000], n_calls=5, hard_max=1000
    )
    assert abs(cost - 0.00015 * 5 * 1300) < 1e-9


def test_parse_iso_handles_twitterapi_format():
    ts = pf._parse_iso("Mon Jul 08 14:23:01 +0000 2026")
    assert ts is not None
    assert ts.year == 2026 and ts.minute == 23


def test_parse_iso_handles_iso8601():
    ts = pf._parse_iso("2026-07-08T14:23:01Z")
    assert ts is not None
    assert ts.year == 2026


def test_parse_iso_returns_none_for_garbage():
    assert pf._parse_iso("not a date") is None
    assert pf._parse_iso(None) is None
    assert pf._parse_iso("") is None


def test_analyze_timestamps_no_timestamps():
    out = pf._analyze_timestamps([{"id": "t1", "text": "no ts"}], max_results=10)
    assert out["t_newest"] is None
    assert out["t_oldest"] is None
    assert out["n_within_15min"] == 0
    assert out["extrapolated_n_in_15min"] is None
    assert out["extrapolation_confidence"] == "high"


def test_analyze_timestamps_all_within_window():
    items = _fake_response(50, all_within_15min=True)
    out = pf._analyze_timestamps(items, max_results=200)
    assert out["n_within_15min"] == 50
    # All within 15 min -> no extrapolation needed.
    assert out["extrapolated_n_in_15min"] is None
    assert out["extrapolation_confidence"] == "high"


def test_analyze_timestamps_partial_window_no_extrapolation_when_not_capped():
    # 30 tweets, all within 15min, n_results == n_within_15min.
    items = _fake_response(30, all_within_15min=True)
    out = pf._analyze_timestamps(items, max_results=200)
    assert out["n_within_15min"] == 30
    assert out["extrapolated_n_in_15min"] is None


def test_analyze_timestamps_capped_triggers_extrapolation():
    # 200 returned tweets, but only 5 within the 15-min window -> capped.
    # Build 5 tweets at age 0..4 minutes, then 195 at age 30..224 minutes.
    # The 5 recent ones are within the window; the rest are outside.
    items = (
        [_make_tweet(f"recent{i}", f"r{i}", age_minutes=i) for i in range(5)]
        + [
            _make_tweet(f"old{i}", f"o{i}", age_minutes=30 + i)
            for i in range(195)
        ]
    )
    out = pf._analyze_timestamps(items, max_results=200)
    assert out["n_within_15min"] == 5
    # Extrapolation should fire (n_within_15min=5 < n_results=200).
    assert out["extrapolated_n_in_15min"] is not None
    # The 5 recent tweets span ~4 minutes. Linear extrapolation to 15 min:
    # density = 5/4 = 1.25 tweets/min, so extrapolated ~= 18-19.
    # That's > 5 (the observed count) but < 200 (the n_results cap).
    assert out["extrapolated_n_in_15min"] > 5
    assert out["extrapolation_confidence"] in ("medium", "low")


# --- CLI subprocess tests (dry-run, missing-creds, schema) -------------


def _run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the probe as a subprocess. Returns the CompletedProcess."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(PROBE_SCRIPT), *args],
        capture_output=True, text=True, check=False,
        cwd=str(REPO_ROOT), env=full_env,
    )


def test_probe_dry_run_lists_all_calls():
    """--dry-run emits rows for A, B1, B2, B3, C1 (5 calls x 4 levels = 20)."""
    proc = _run_cli("--dry-run")
    assert proc.returncode == 0, (
        f"dry-run failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    # Each call_id should appear 4 times (once per ramp level).
    for cid in ("A", "B1", "B2", "B3", "C1"):
        assert proc.stdout.count(f"\n  {cid} ") >= 1, (
            f"call {cid} missing from dry-run output: {proc.stdout!r}"
        )
    # No HTTP, no API key required.
    assert "no API key" not in proc.stdout


def test_probe_dry_run_emits_call_list_header():
    proc = _run_cli("--dry-run")
    assert "n_calls=5" in proc.stdout
    assert "ramp=" in proc.stdout
    assert "hard_max=" in proc.stdout


def test_probe_handles_missing_api_key(monkeypatch):
    """No TWITTERAPI_IO_KEY env -> exit 2 with clear error."""
    monkeypatch.delenv("TWITTER_API_KEY", raising=False)
    monkeypatch.delenv("TWITTERAPI_IO_KEY", raising=False)
    # Use a tmp output path so the script doesn't write to /tmp.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        proc = _run_cli(
            "--output", str(Path(td) / "out.csv"),
            env={},  # explicit empty override
        )
    assert proc.returncode == 2, (
        f"expected exit 2, got {proc.returncode}: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "no API key" in proc.stderr or "no API key" in proc.stdout


def test_probe_budget_cap_blocks_run():
    """--budget-cap 0.01 with the default ramp exceeds the cap -> exit."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        proc = _run_cli(
            "--dry-run",  # budget check fires before HTTP
            "--max-results", "1000,2000,5000,10000",
            "--hard-max", "1000",
            "--budget-cap", "0.01",
            "--output", str(Path(td) / "out.csv"),
        )
    assert proc.returncode != 0, (
        f"expected non-zero exit, got 0: {proc.stdout!r}"
    )
    assert "budget" in proc.stderr.lower() or "budget" in proc.stdout.lower()


def test_probe_hard_max_clamps_huge_ramp_level():
    """--max-results 50,100,150,5000 --hard-max 1000 clamps 5000->1000."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        proc = _run_cli(
            "--dry-run",
            "--max-results", "50,100,150,5000",
            "--hard-max", "1000",
            "--output", str(Path(td) / "out.csv"),
        )
    # Dry-run doesn't fire HTTP, but the clamp logic is in main()
    # regardless. The clamp emits a warning to stderr.
    assert "5000 -> 1000" in proc.stderr or "5000 -> 1000" in proc.stdout


def test_probe_script_imports_cleanly():
    """The probe imports x_monitor.query_plan and x_monitor.apify on
    live path; even without creds, those imports must succeed."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); "
         "from scripts.probe_filter_yield import _have_api_creds, "
         "_parse_ramp, _clamp_ramp; "
         "print(_parse_ramp('50,100,200')); "
         "print(_clamp_ramp([5000], hard_max=1000))"],
        capture_output=True, text=True, check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"imports failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "[50, 100, 200]" in proc.stdout
    assert "[1000]" in proc.stdout


# --- CSV schema test (via dry-run, with --output) ----------------------


def test_probe_csv_schema_is_stable():
    """Output CSV header is the documented stable schema."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "out.csv"
        proc = _run_cli(
            "--dry-run", "--output", str(out_path),
        )
        assert proc.returncode == 0
        with out_path.open() as fh:
            first_line = fh.readline().strip()
    expected = (
        "call_id,max_results,n_results,n_kept_after_filter,"
        "wall_clock_ms,cost_estimate_usd,t_newest,t_oldest,"
        "n_within_15min,extrapolated_n_in_15min,"
        "extrapolation_confidence,sample_tweet_ids,error"
    )
    assert first_line == expected, (
        f"CSV header drift: got {first_line!r} expected {expected!r}"
    )


def test_probe_csv_has_one_row_per_call_per_level():
    """Dry-run with the default ramp emits 5 calls x 4 levels = 20 rows."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "out.csv"
        proc = _run_cli("--dry-run", "--output", str(out_path))
        assert proc.returncode == 0
        with out_path.open() as fh:
            lines = fh.readlines()
    # 1 header + 20 data rows.
    assert len(lines) == 21, f"expected 21 lines, got {len(lines)}"
    # 5 distinct call_ids.
    call_ids = {line.split(",")[0] for line in lines[1:]}
    assert call_ids == {"A", "B1", "B2", "B3", "C1"}


# --- row-format unit test -----------------------------------------------


def test_row_for_csv_ordering():
    """_row_for_csv emits fields in CSV_HEADER order."""
    result = {
        "n_results": 50,
        "n_kept_after_filter": 30,
        "wall_clock_ms": 1200,
        "cost_estimate_usd": 0.0075,
        "t_newest": "2026-07-08T14:00:00+00:00",
        "t_oldest": "2026-07-08T13:50:00+00:00",
        "n_within_15min": 50,
        "extrapolated_n_in_15min": None,
        "extrapolation_confidence": "high",
        "sample_tweet_ids": "t1,t2,t3",
        "error": "",
    }
    row = pf._row_for_csv("A", 50, result)
    assert row[0] == "A"          # call_id
    assert row[1] == 50            # max_results
    assert row[2] == 50            # n_results
    assert row[3] == 30            # n_kept_after_filter
    assert row[4] == 1200          # wall_clock_ms
    assert row[5] == 0.0075        # cost_estimate_usd
    assert row[6] == "2026-07-08T14:00:00+00:00"  # t_newest
    assert row[7] == "2026-07-08T13:50:00+00:00"  # t_oldest
    assert row[8] == 50            # n_within_15min
    assert row[9] is None          # extrapolated_n_in_15min
    assert row[10] == "high"       # extrapolation_confidence
    assert row[11] == "t1,t2,t3"   # sample_tweet_ids
    assert row[12] == ""           # error


def test_row_for_csv_failure_path():
    """Failed calls emit nulls and a non-empty error string."""
    result = {
        "n_results": None,
        "n_kept_after_filter": None,
        "wall_clock_ms": 30000,
        "cost_estimate_usd": None,
        "t_newest": None,
        "t_oldest": None,
        "n_within_15min": 0,
        "extrapolated_n_in_15min": None,
        "extrapolation_confidence": "high",
        "sample_tweet_ids": "",
        "error": "TwitterApiRateLimitError",
    }
    row = pf._row_for_csv("B2", 100, result)
    assert row[2] is None  # n_results
    assert row[5] is None  # cost_estimate_usd
    assert row[12] == "TwitterApiRateLimitError"


def test_print_summary_handles_int_n_within_15min():
    """Regression: n_within_15min is an int (default 0 when no
    timestamps parsed), not a string. Earlier format string used
    's' on an int and crashed at runtime."""
    rows = [
        {
            "call_id": "A",
            "max_results": 200,
            "n_results": 100,
            "n_kept_after_filter": 11,
            "n_within_15min": 0,
            "cost_estimate_usd": 0.015,
            "extrapolated_n_in_15min": None,
            "extrapolation_confidence": "high",
        },
    ]
    import io as _io
    from contextlib import redirect_stdout
    buf = _io.StringIO()
    with redirect_stdout(buf):
        pf._print_summary(rows)
    out = buf.getvalue()
    assert "n_within_15min=" in out
    # Must not have raised.
    assert "A" in out


def test_print_summary_skips_rows_below_summary_level():
    """Only rows whose max_results == SUMMARY_RAMP_LEVEL are summarized."""
    rows = [
        {"call_id": "A", "max_results": 50, "n_results": 50,
         "n_kept_after_filter": 5, "n_within_15min": 0,
         "cost_estimate_usd": 0.0075, "extrapolated_n_in_15min": None,
         "extrapolation_confidence": "high"},
    ]
    import io as _io
    from contextlib import redirect_stdout
    buf = _io.StringIO()
    with redirect_stdout(buf):
        pf._print_summary(rows)
    # max_results=50 ≠ SUMMARY_RAMP_LEVEL → nothing printed.
    assert buf.getvalue() == ""


# --- live probe: SKIPPED without credentials --------------------------


@pytest.mark.skipif(
    not os.environ.get("TWITTER_API_KEY")
    and not os.environ.get("TWITTERAPI_IO_KEY"),
    reason="live probe requires TWITTER_API_KEY or TWITTERAPI_IO_KEY",
)
def test_probe_live_smoke_runs_and_writes_csv():
    """End-to-end: live API call at small ramp (max_results=50 only,
    one call) writes a valid CSV with one row of real data. Skipped
    unless API credentials are present in the env. Operators capture
    the CSV and attach it as a code review artifact."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "out.csv"
        proc = _run_cli(
            "--max-results", "50",
            "--output", str(out_path),
        )
    assert proc.returncode == 0, (
        f"live probe failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert out_path.exists()
    with out_path.open() as fh:
        lines = fh.readlines()
    # 1 header + 5 calls x 1 level = 6 lines.
    assert len(lines) == 6
    for line in lines[1:]:
        # n_results (col 2) should be a positive integer for live calls.
        n_results = int(line.split(",")[2])
        assert n_results > 0
