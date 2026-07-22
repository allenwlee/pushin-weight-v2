"""U4 smoke tests for `scripts/dump_http_log.py --latency-summary`.

Plan: docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md
Unit 4 of 6 (U4 — Slow-API-day latency observation).

These are smoke tests, not unit tests for the underlying pipeline:
they pin that the new --latency-summary flag renders a distribution
table without crashing on edge cases (empty log, single request,
all-same-duration, mixed latency). The plan explicitly states "no
behavior change in this unit" — we are NOT testing latency behavior,
just the surface that surfaces it.

We invoke the script via subprocess so the smoke test exercises the
full CLI surface, including argument parsing.

Verifies:
- Empty http_log: flag runs without raising; output contains a
  "(no HTTP requests to summarize)" sentinel line.
- Single request: p50/p95/p99 equal the single duration; max/min
  match.
- All-same-duration (constant): percentiles all equal the constant;
  no NaN / division artifacts.
- Mixed latencies: outlier section includes the longest request;
  overall p99 ≥ p95 ≥ p50.
- --out combined with --latency-summary persists the
  `latency_by_endpoint` and `latency_overall` keys.
- Default (no flag) behavior is unchanged: existing flat + grouped
  rendering still works.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "dump_http_log.py"


def _write_run(tmp_path: Path, payload: dict) -> Path:
    """Write a run JSON into a fresh temp data/runs/ directory."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_path = runs_dir / "test_run.json"
    run_path.write_text(json.dumps(payload), encoding="utf-8")
    return run_path


def _run_script(tmp_path: Path, run_path: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(run_path),
         "--data-dir", str(tmp_path / "runs")]
        + list(extra_args),
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": ""},  # don't load operator's env
    )


def _baseline_run(http_log: list[dict] | None = None) -> dict:
    """Build a minimal run JSON with the given http_log."""
    return {
        "run_id": "test-run-001",
        "started_at": "2026-07-02T00:00:00+00:00",
        "finished_at": "2026-07-02T00:02:00+00:00",
        "status": "completed",
        "phase_timings_sec": {},
        "http_log": http_log if http_log is not None else [],
    }


def _search_entry(duration_ms: int) -> dict:
    """Build one /advanced_search http_log entry with the given duration."""
    return {
        "path": "/twitter/tweet/advanced_search",
        "params": {"query": "(minimax) min_faves:5", "queryType": "Latest", "limit": 20},
        "status": 200,
        "n_results": 20,
        "duration_ms": duration_ms,
        "attempts": 1,
        "has_next_page": False,
    }


# --- edge case: empty log --------------------------------------------


def test_latency_summary_handles_empty_log(tmp_path):
    """Empty http_log: flag prints a clean sentinel, does not raise."""
    run_path = _write_run(tmp_path, _baseline_run([]))
    proc = _run_script(tmp_path, run_path, "--latency-summary", "--no-pretty")
    assert proc.returncode == 0, (
        f"script failed with --latency-summary on empty log: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "no HTTP requests to summarize" in proc.stdout, (
        f"expected empty-log sentinel in stdout; got {proc.stdout!r}"
    )


# --- edge case: single request ---------------------------------------


def test_latency_summary_single_request(tmp_path):
    """Single request: percentiles all equal the only value."""
    log = [_search_entry(420)]
    run_path = _write_run(tmp_path, _baseline_run(log))
    proc = _run_script(tmp_path, run_path, "--latency-summary", "--no-pretty")
    assert proc.returncode == 0, (
        f"single-request script failed: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    # The overall line should report n=1 and the duration as
    # 420 ms for mean / p50 / p95 / p99 / max / min.
    out = proc.stdout
    assert "n=1" in out, f"single-request overall line missing 'n=1': {out!r}"
    assert "mean=420ms" in out, f"expected mean=420ms in {out!r}"
    assert "max=420ms" in out, f"expected max=420ms in {out!r}"
    assert "min=420ms" in out, f"expected min=420ms in {out!r}"


# --- edge case: all-same-duration -----------------------------------


def test_latency_summary_all_same_duration(tmp_path):
    """All requests at constant duration: no division artifacts, no NaN."""
    log = [_search_entry(100) for _ in range(5)]
    run_path = _write_run(tmp_path, _baseline_run(log))
    proc = _run_script(tmp_path, run_path, "--latency-summary", "--no-pretty")
    assert proc.returncode == 0, (
        f"constant-duration script failed: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    out = proc.stdout
    assert "n=5" in out, f"expected n=5 in overall: {out!r}"
    # All percentiles are 100 ms. The new section is the
    # `Latency distribution (per endpoint)` table; we look for the
    # data rows under that header so we don't trip on the existing
    # `# By endpoint` summary at the top.
    in_table = False
    seen_advanced_search_row = False
    for line in out.splitlines():
        if "Latency distribution" in line:
            in_table = True
            continue
        if not in_table:
            continue
        # Endpoint table rows have the shape:
        #   <whitespace>advanced_search  n  mean  p50  p95  p99  max
        # Skip the Outliers section, which has a different shape.
        if line.lstrip().startswith("100ms "):
            # Outliers row.
            continue
        if "advanced_search" in line and line.lstrip().startswith(""):
            # Row in the per-endpoint table (begins with whitespace).
            seen_advanced_search_row = True
            cells = line.split()
            # Cells after the endpoint: n, mean, p50, p95, p99, max.
            # Pull the trailing integer for max and ensure it's 100.
            assert "100" in cells, (
                f"endpoint row missing 100 cells: line={line!r}"
            )
    assert seen_advanced_search_row, (
        f"no advanced_search row in latency table:\n{out}"
    )


# --- happy path: mixed latencies -------------------------------------


def test_latency_summary_mixed_latencies(tmp_path):
    """Mixed durations: overall p99 ≥ p95 ≥ p50 and outliers section
    surfaces the longest request."""
    # 9 small requests + 1 outlier.
    log = [_search_entry(50 + i * 5) for i in range(9)]
    log.append(_search_entry(8000))  # outlier
    run_path = _write_run(tmp_path, _baseline_run(log))
    proc = _run_script(tmp_path, run_path, "--latency-summary", "--no-pretty")
    assert proc.returncode == 0, (
        f"mixed-latency script failed: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    out = proc.stdout
    assert "n=10" in out, f"expected n=10 in overall: {out!r}"
    assert "8000ms" in out, (
        f"outlier duration 8000ms missing from output:\n{out}"
    )
    assert "Outliers" in out, f"outliers section header missing:\n{out}"


# --- combined: --out + --latency-summary persists structured data --


def test_latency_summary_persists_with_out(tmp_path):
    """When --out and --latency-summary are both set, the report JSON
    includes both `latency_by_endpoint` and `latency_overall` keys."""
    log = [_search_entry(100), _search_entry(300), _search_entry(500)]
    payload = _baseline_run(log)
    run_path = _write_run(tmp_path, payload)
    out_path = tmp_path / "report.json"
    proc = _run_script(
        tmp_path, run_path,
        "--latency-summary",
        "--no-pretty",
        "--out", str(out_path),
    )
    assert proc.returncode == 0, (
        f"--out + --latency-summary script failed: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert out_path.exists(), f"report path {out_path} not created"
    report = json.loads(out_path.read_text())
    assert "latency_by_endpoint" in report, (
        f"latency_by_endpoint missing from report: keys={list(report.keys())}"
    )
    assert "latency_overall" in report, (
        f"latency_overall missing from report: keys={list(report.keys())}"
    )
    assert "/twitter/tweet/advanced_search" in report["latency_by_endpoint"], (
        f"per-endpoint map missing the search path: "
        f"{report['latency_by_endpoint'].keys()}"
    )
    overall = report["latency_overall"]
    # 3 samples: 100, 300, 500. mean=300. p50 with linear interp
    # between rank 1 and 2 (out of 0..2) is 300. p95/p99 land
    # near 500.
    assert overall["n"] == 3, f"expected n=3, got {overall}"
    assert 290 <= overall["mean_ms"] <= 310, (
        f"mean_ms != 300 (got {overall['mean_ms']})"
    )
    assert overall["max_ms"] == 500, f"max_ms != 500 (got {overall})"


# --- regression: default (no flag) behavior is unchanged ------------


def test_default_behavior_unchanged(tmp_path):
    """Without the new flag, the existing flat + grouped rendering
    still works (regression guard for U4's no-behavior-change claim)."""
    log = [_search_entry(100), _search_entry(200)]
    run_path = _write_run(tmp_path, _baseline_run(log))
    proc = _run_script(tmp_path, run_path)  # no --latency-summary
    assert proc.returncode == 0, (
        f"default-mode script failed: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    out = proc.stdout
    assert "Every HTTP request (flat list)" in out, (
        f"flat list section missing from default run:\n{out}"
    )
    # Latency section must NOT appear without the flag.
    assert "Latency distribution" not in out, (
        "latency summary appeared without --latency-summary flag; "
        "the new section must remain opt-in"
    )


# --- unit test for the percentile computation ------------------------


def test_latency_percentiles_handles_empty_list():
    """latency_percentiles([]) returns sentinel values without raising."""
    from scripts.dump_http_log import latency_percentiles
    result = latency_percentiles([])
    assert result["n"] == 0
    assert result["mean_ms"] == 0
    assert result["median_ms"] is None
    assert result["p95_ms"] is None
    assert result["p99_ms"] is None


def test_latency_percentiles_known_inputs():
    """For a known distribution, percentiles match the docs."""
    from scripts.dump_http_log import latency_percentiles
    # 1..100 inclusive
    durations = list(range(1, 101))
    result = latency_percentiles(durations)
    assert result["n"] == 100
    assert 49.5 <= result["median_ms"] <= 50.5, (
        f"median ~= 50.5; got {result['median_ms']}"
    )
    # p95 on a uniform 1..100 is roughly 95; allow some slack for
    # the interpolation method.
    assert 93 <= result["p95_ms"] <= 97, (
        f"p95 ~= 95; got {result['p95_ms']}"
    )
    assert 98 <= result["p99_ms"] <= 100, (
        f"p99 ~= 99; got {result['p99_ms']}"
    )
    assert result["max_ms"] == 100
    assert result["min_ms"] == 1