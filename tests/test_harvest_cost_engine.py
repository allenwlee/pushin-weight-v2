"""Tests for scripts.harvest_cost.engine (plan 2026-08-10-003 U2)."""

from __future__ import annotations

from scripts.harvest_cost.engine import (
    cost_cycle_from_summary,
    cost_period,
    credits_for_tweet_units,
    extrapolate,
    render_markdown,
)
from scripts.harvest_cost.pricing import PricingRates

RATES = PricingRates(
    tweet_credits=15,
    call_floor_credits=15,
    credits_per_usd=100_000,
    source_path="test",
)


def test_credits_for_tweet_units():
    assert credits_for_tweet_units(63, RATES) == 63 * 15
    assert credits_for_tweet_units(0, RATES, apply_floor=True) == 15
    assert credits_for_tweet_units(1, RATES, apply_floor=True) == 15
    assert credits_for_tweet_units(2, RATES, apply_floor=True) == 30


def test_ae1_b1_and_metrics():
    """Covers AE1: B1=63, metrics refreshed=174 → 945 + 2610."""
    summary = {
        "run_id": "20260810T063111_0000-db83da0c",
        "finished_at": "2026-08-10T06:37:01+00:00",
        "calls": [
            {"call_id": "A", "n_results": 2, "status": "completed"},
            {"call_id": "B1", "n_results": 63, "status": "completed"},
            {"call_id": "B2", "n_results": 5, "status": "completed"},
            {"call_id": "B3", "n_results": 4, "status": "completed"},
            {"call_id": "C1", "n_results": 5, "status": "completed"},
            {"call_id": "C2", "n_results": 4, "status": "completed"},
            {"call_id": "C3", "n_results": 4, "status": "completed"},
        ],
        "metrics_refresh": {"n_due": 200, "n_refreshed": 174, "n_missing": 26},
        "totals": {"n_results": 87, "n_inserted": 51, "n_calls_run": 7},
    }
    cy = cost_cycle_from_summary(summary, RATES)
    b1 = next(ln for ln in cy.lines if ln.label == "B1")
    assert b1.credits == 945
    metrics = next(ln for ln in cy.lines if ln.source == "metrics")
    assert metrics.n_results == 174
    assert metrics.credits == 174 * 15
    assert abs(cy.total_usd(RATES) - cy.total_credits / 100_000) < 1e-9


def test_multi_cycle_rollup():
    s1 = {
        "run_id": "c1",
        "finished_at": "2026-08-10T06:00:00+00:00",
        "calls": [{"call_id": "A", "n_results": 10}],
        "totals": {"n_results": 10, "n_inserted": 10, "n_calls_run": 1},
    }
    s2 = {
        "run_id": "c2",
        "finished_at": "2026-08-10T06:15:00+00:00",
        "calls": [{"call_id": "A", "n_results": 20}],
        "totals": {"n_results": 20, "n_inserted": 20, "n_calls_run": 1},
    }
    period = cost_period([s1, s2], RATES)
    assert period.total_credits == (10 + 20) * 15
    assert period.mean_cycle_credits() == 15 * 15


def test_metrics_only():
    s = {
        "run_id": "m",
        "calls": [],
        "metrics_refresh": {"refreshed": 50, "due": 50},
        "totals": {"n_results": 0, "n_inserted": 0, "n_calls_run": 0},
    }
    cy = cost_cycle_from_summary(s, RATES)
    assert cy.metrics_credits() == 50 * 15
    assert cy.search_credits() == 0


def test_qt_disabled_zero():
    s = {
        "run_id": "q",
        "calls": [{"call_id": "A", "n_results": 1}],
        "quote_tweets": {"disabled": True},
        "totals": {"n_results": 1, "n_inserted": 1, "n_calls_run": 1},
    }
    cy = cost_cycle_from_summary(s, RATES)
    qt = [ln for ln in cy.lines if ln.source == "qt"]
    assert qt and qt[0].credits == 0


def test_residual_fallback_b1():
    s = {
        "run_id": "r",
        "totals": {"n_results": 87},
        "b1_n_results": 63,
    }
    cy = cost_cycle_from_summary(s, RATES)
    labels = {ln.label for ln in cy.lines}
    assert "B1" in labels
    assert any(ln.source == "residual" for ln in cy.lines)


def test_render_markdown_contains_totals():
    s = {
        "run_id": "x",
        "finished_at": "2026-08-10T06:37:01+00:00",
        "calls": [{"call_id": "B1", "n_results": 63}],
        "metrics_refresh": {"n_refreshed": 174, "n_due": 200},
        "totals": {"n_results": 63, "n_inserted": 50, "n_calls_run": 1},
    }
    md = render_markdown(cost_period([s], RATES))
    assert "945" in md
    assert "2610" in md or "2,610" in md or "2610" in md.replace(",", "")
    assert "generated_by: scripts.harvest_cost" in md


def test_extrapolate():
    ext = extrapolate(100.0)
    assert ext["per_day_96_cycles"] == 9600
