"""Regression net: cycle summary + pricing defaults (plan 2026-08-10-003 U5)."""

from __future__ import annotations

from pathlib import Path

from scripts.harvest_cost.engine import cost_cycle_from_summary
from scripts.harvest_cost.pricing import load_pricing

REPO = Path(__file__).resolve().parent.parent

# Pinned defaults from docs/external_vendors/twitterapi*/twitterapi_index.md
PINNED_TWEET_CREDITS = 15
PINNED_CREDITS_PER_USD = 100_000
PINNED_FLOOR = 15


def test_pricing_defaults_pinned():
    rates = load_pricing(repo_root=REPO)
    assert rates.tweet_credits == PINNED_TWEET_CREDITS
    assert rates.credits_per_usd == PINNED_CREDITS_PER_USD
    assert rates.call_floor_credits == PINNED_FLOOR


def test_summary_contract_keys_for_cost_tool():
    """Cost tool depends on these summary keys — rename fails loudly here."""
    summary = {
        "run_id": "pin-run",
        "finished_at": "2026-08-10T06:37:01+00:00",
        "calls": [
            {
                "call_id": "B1",
                "n_results": 63,
                "fetch_n": 63,
                "status": "completed",
            }
        ],
        "totals": {
            "n_results": 63,
            "n_inserted": 51,
            "n_calls_run": 1,
        },
        "metrics_refresh": {
            "n_due": 200,
            "n_refreshed": 174,
            "n_missing": 26,
        },
    }
    # Required top-level
    assert isinstance(summary["calls"], list)
    assert "n_results" in summary["calls"][0]
    assert "call_id" in summary["calls"][0]
    for k in ("n_results", "n_inserted", "n_calls_run"):
        assert k in summary["totals"]
    mr = summary["metrics_refresh"]
    assert "n_due" in mr or "due" in mr
    assert "n_refreshed" in mr or "refreshed" in mr

    rates = load_pricing(repo_root=REPO)
    cy = cost_cycle_from_summary(summary, rates)
    assert any(ln.label == "B1" and ln.n_results == 63 for ln in cy.lines)
    assert cy.metrics_credits() == 174 * PINNED_TWEET_CREDITS


def test_cycle_module_still_exports_runner():
    from monitor.cycle import CycleRunner

    assert CycleRunner is not None


def test_emit_module_present():
    src = REPO / "scripts" / "harvest_cost" / "emit.py"
    assert src.is_file()
    text = src.read_text(encoding="utf-8")
    assert "persist_cycle_summary" in text
    assert "finalize_and_persist" in text
