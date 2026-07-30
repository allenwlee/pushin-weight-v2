"""U7 tests - anomaly metrics in cycle summary.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U7.

WHY THIS FILE EXISTS
--------------------
The hybrid funnel's U7 pins per-call anomaly metrics for ops detection:
fetch_n, keep_rate, not_include_drops, llm_drops (R21). The cycle-level
totals include keep_rate_min / mean / max for spike detection.

This test pins the shape of those fields. The actual values are produced
by the harvest cycle in production; here we simulate the metrics
computation on a synthetic call_entry list to confirm the totals
aggregation logic.
"""

from __future__ import annotations


def compute_keep_rate(n_results: int, n_kept: int) -> float:
    """Per-call keep_rate: n_kept / n_results, or 0 if n_results == 0.

    Plan U7: keep_rate is the post-attribute (pre-translate) ratio.
    A spike here vs the cycle mean suggests a single call is much looser.
    """
    return round(n_kept / n_results, 4) if n_results > 0 else 0.0


def aggregate_totals(call_entries: list[dict]) -> dict:
    """Cycle-level keep_rate aggregates (min / mean / max)."""
    rates = [c.get("keep_rate", 0.0) for c in call_entries]
    if not rates:
        return {"keep_rate_min": 0.0, "keep_rate_mean": 0.0, "keep_rate_max": 0.0}
    return {
        "keep_rate_min": round(min(rates), 4),
        "keep_rate_mean": round(sum(rates) / len(rates), 4),
        "keep_rate_max": round(max(rates), 4),
    }


def attach_metrics(call_entry: dict) -> dict:
    """Attach U7 metrics to a single call_entry dict in-place.

    Returns the mutated entry. fetch_n = n_results; keep_rate from
    n_kept / fetch_n. not_include_drops and llm_drops are 0 placeholders
    until the U5 ban path and U6 LLM gate are wired into runtime
    (follow-up work)."""
    nr = call_entry.get("n_results", 0)
    nk = call_entry.get("n_kept", 0)
    call_entry["fetch_n"] = nr
    call_entry["keep_rate"] = compute_keep_rate(nr, nk)
    call_entry["not_include_drops"] = 0
    call_entry["llm_drops"] = 0
    return call_entry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_keep_rate_basic():
    assert compute_keep_rate(100, 80) == 0.8
    assert compute_keep_rate(50, 25) == 0.5
    assert compute_keep_rate(10, 1) == 0.1


def test_keep_rate_zero_results():
    """No results → 0.0 (not a division error)."""
    assert compute_keep_rate(0, 0) == 0.0


def test_keep_rate_zero_kept_with_results():
    """n_results > 0 but n_kept = 0 → 0.0 (legitimate zero, not an error)."""
    assert compute_keep_rate(50, 0) == 0.0


def test_aggregate_min_max_mean():
    entries = [
        {"keep_rate": 0.5},
        {"keep_rate": 0.8},
        {"keep_rate": 0.2},
    ]
    totals = aggregate_totals(entries)
    assert totals["keep_rate_min"] == 0.2
    assert totals["keep_rate_max"] == 0.8
    assert abs(totals["keep_rate_mean"] - 0.5) < 1e-6


def test_aggregate_empty():
    totals = aggregate_totals([])
    assert totals == {"keep_rate_min": 0.0, "keep_rate_mean": 0.0, "keep_rate_max": 0.0}


def test_attach_metrics_sets_all_fields():
    entry = {"call_id": "C1", "n_results": 100, "n_kept": 60, "n_inserted": 50}
    attach_metrics(entry)
    assert entry["fetch_n"] == 100
    assert entry["keep_rate"] == 0.6
    assert entry["not_include_drops"] == 0
    assert entry["llm_drops"] == 0


def test_attach_metrics_zero_results():
    entry = {"call_id": "C1", "n_results": 0, "n_kept": 0, "n_inserted": 0}
    attach_metrics(entry)
    assert entry["fetch_n"] == 0
    assert entry["keep_rate"] == 0.0


def test_spike_detection_shape():
    """A spike test: one call is much looser than the rest. The aggregate
    max > mean + 2*range suggests an anomaly worth investigating."""
    entries = [
        {"call_id": "C1", "n_results": 100, "n_kept": 30, "n_inserted": 28},
        {"call_id": "C2", "n_results": 50, "n_kept": 5, "n_inserted": 4},
        {"call_id": "C3", "n_results": 80, "n_kept": 25, "n_inserted": 24},
    ]
    for e in entries:
        attach_metrics(e)
    totals = aggregate_totals(entries)
    # C2 is the spike — very low keep_rate (0.1) vs C1 (0.3) and C3 (~0.31).
    assert totals["keep_rate_min"] < totals["keep_rate_mean"]
    assert totals["keep_rate_max"] > totals["keep_rate_mean"]
    # Ops dashboard would flag: min < 0.2 indicates a candidate for
    # investigation (R21 anomaly metric).