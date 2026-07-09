# {{AGENT_ATTRIBUTION}}
"""Live-gated regression test for scripts.probe_filter_yield (plan 005 U5).

Plan: docs/plans/2026-07-09-001-feat-list-yaml-db-sync-plan.md (Unit 5)
Baseline: data/2026-07-08T065743Z-filter_yield_baseline.csv
         (commit 45da4c9 of plan 2026-07-08-004)

Goal: re-run the probe for each Call B group and assert the kept-rate
didn't regress more than 20% from the baseline. The 20% threshold is
deliberately loose — plan 005 acknowledges natural variance in
post-flow rates; tighter thresholds would flag false regressions.

Gate: ``TWITTER_API_KEY`` or ``TWITTERAPI_IO_KEY`` must be in the
environment. Without credentials, the test SKIPs — same pattern as
the existing live-only test in ``test_probe_filter_yield.py``.

Why we re-run, not just diff: a "no diff" check against the baseline
CSV would only catch output schema drift, not yield drift. We need
to actually run the probe and compare kept/n_results.
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_SCRIPT = REPO_ROOT / "scripts" / "probe_filter_yield.py"
BASELINE_CSV = REPO_ROOT / "data" / "2026-07-08T065743Z-filter_yield_baseline.csv"

# Allowed degradation from baseline. 0.8 = at most 20% drop in kept-rate.
DEGRADATION_THRESHOLD = 0.8

# Skip the test if neither live credential is set.
LIVE_GATE = (
    os.environ.get("TWITTER_API_KEY") or os.environ.get("TWITTERAPI_IO_KEY")
)


def _baseline_by_call_id() -> dict[str, dict[str, int]]:
    """Index the baseline CSV by call_id, returning n_results and n_kept_after_filter.

    Returns a dict like ``{"A": {"n_results": 50, "n_kept": 5}, ...}``.
    """
    if not BASELINE_CSV.exists():
        pytest.skip(f"baseline CSV not found at {BASELINE_CSV}")
    out: dict[str, dict[str, int]] = {}
    with BASELINE_CSV.open() as f:
        for row in csv.DictReader(f):
            call_id = row["call_id"]
            n_results = int(row["n_results"])
            n_kept = int(row["n_kept_after_filter"])
            # The baseline may have multiple rows per call_id (different
            # max_results); keep the first row we see for each call_id —
            # we only need the kept-rate, and a single point is enough.
            if call_id not in out:
                out[call_id] = {"n_results": n_results, "n_kept": n_kept}
    return out


def _run_probe_for(call_id: str) -> dict[str, int]:
    """Run the probe for one call_id and parse the resulting CSV.

    Subprocess approach mirrors the live-only test in
    ``test_probe_filter_yield.py``: invoke the script as a subprocess
    so the env (TWITTERAPI_IO_KEY etc.) is propagated cleanly.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out_csv = Path(td) / "probe.csv"
        # Probe CLI accepts --calls (plan 004 spec). We pass the single
        # call_id and a small max-results to keep the test fast.
        proc = subprocess.run(
            [
                sys.executable, str(PROBE_SCRIPT),
                "--calls", call_id,
                "--max-results", "50",
                "--output", str(out_csv),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, (
            f"probe for {call_id} failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
        with out_csv.open() as f:
            row = next(csv.DictReader(f))
        return {
            "n_results": int(row["n_results"]),
            "n_kept": int(row["n_kept_after_filter"]),
        }


@pytest.mark.skipif(
    not LIVE_GATE,
    reason="live probe regression requires TWITTER_API_KEY or TWITTERAPI_IO_KEY",
)
def test_probe_no_regression_per_call_id() -> None:
    """For each call_id in the baseline, run the probe and assert the
    kept-rate did not regress more than 20% from the baseline.
    """
    baseline = _baseline_by_call_id()
    failures: list[str] = []
    for call_id, base in baseline.items():
        # Skip Call A — plan 005 is about Call B groups; the baseline
        # has Call A but the regression risk is on the per-B-group
        # splitting introduced in v1.7.x. Call A is a single group so
        # it isn't affected by U5's surface area.
        if not call_id.startswith("B"):
            continue

        base_rate = base["n_kept"] / base["n_results"] if base["n_results"] else 0.0
        current = _run_probe_for(call_id)
        current_rate = current["n_kept"] / current["n_results"] if current["n_results"] else 0.0

        if base_rate > 0 and current_rate < DEGRADATION_THRESHOLD * base_rate:
            failures.append(
                f"{call_id}: baseline kept-rate={base_rate:.2%} "
                f"({base['n_kept']}/{base['n_results']}); "
                f"current kept-rate={current_rate:.2%} "
                f"({current['n_kept']}/{current['n_results']}); "
                f"threshold={DEGRADATION_THRESHOLD:.0%} of baseline"
            )

    assert not failures, (
        "filter-yield regression detected:\n  " + "\n  ".join(failures)
    )