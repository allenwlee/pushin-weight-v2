"""Current nine-call query exhibit and offline spend sensitivity.

The query pool pins nine call IDs in historical order. Brand ownership is
independent of those IDs; deterministic packing keeps whole brand blocks and
explicitly named family groups together.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts.harvest_cost.engine import cost_cycle_from_summary
from scripts.harvest_cost.pricing import PricingRates
from x_monitor.harvest_policy import active_excluded_author_handles, load_policy
from x_monitor.query_plan import plan_calls
from x_monitor.specs_from_policy import (
    primary_keywords_from_policy,
    specs_from_policy,
    validate_derived_call_ids,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "config" / "harvest_policy.yaml"
SMOKE_SUMMARY_PATH = REPO_ROOT / "tests" / "harvester_costs" / "_smoke" / "ae1.json"

# This is intentionally the planner's order, not the historical Appendix
# presentation order. The configured query pool owns this sequence.
EXPECTED_PLANNER_CALL_ORDER = ("A", "B1", "C1", "C2", "C3", "C4", "B2", "B3", "B4")

EXPECTED_QUERY_EXHIBIT = json.loads((REPO_ROOT / "tests/golden/harvest_portfolio_queries.json").read_text())


def _planned_calls():
    policy = load_policy(POLICY_PATH)
    specs = validate_derived_call_ids(specs_from_policy(policy))
    return plan_calls(
        2067062923525275922,
        specs,
        primary_keywords=primary_keywords_from_policy(policy),
        excluded_author_handles=active_excluded_author_handles(policy),
    )


def test_current_planner_order_and_exact_queries_match_exhibit() -> None:
    """The exact strings sent by the policy-derived planner stay reviewable."""
    calls = _planned_calls()
    assert tuple(call.call_id for call in calls) == EXPECTED_PLANNER_CALL_ORDER
    assert {call.call_id: call.query_string for call in calls} == {
        call_id: f"{query} -from:xxyweb3"
        for call_id, query in EXPECTED_QUERY_EXHIBIT.items()
    }
    assert all(call.query_length == len(call.query_string) for call in calls)
    assert all(call.query_string.count("-from:xxyweb3") == 1 for call in calls)


def test_dots_family_tokens_are_on_owned_call_and_in_onboard_csv() -> None:
    """Family names remain in the owning dots block; bare 'dots' does not."""
    import csv

    calls = _planned_calls()
    dots_query = next(call.query_string for call in calls if call.call_id == "C4")
    for token in (
        '"dots 3 note"',
        'dots studio',
        '"dots.3-note"',
        "dots.ocr",
        "dots.tts",
        "dots.llm1",
        "dots.vlm",
        "dots.mocr",
    ):
        assert token in dots_query
    policy = load_policy(POLICY_PATH)
    assert "dots" not in policy.brands["dots"].tokens

    csv_path = REPO_ROOT / "config/brands/2026-08-31-013447-harvester-quality-upgrade.csv"
    with csv_path.open(newline="", encoding="utf-8") as stream:
        dots_row = next(
            row for row in csv.DictReader(stream) if row["brand_nickname"] == "dots"
        )
    aliases = dots_row["keyword_aliases"].split("|")
    for token in (
        "dots 3 note",
        "dots-3-note",
        "dots.3-note",
        "dots3 note",
        "dots-studio",
        "dots.ocr",
        "dots.tts",
        "dots.llm1",
        "dots.vlm",
        "dots.mocr",
    ):
        assert token in aliases
    assert "dots" not in aliases
    assert "dots" != dots_row["keyword_primary"]


def test_exhibit_keeps_the_nine_logical_call_contract() -> None:
    calls = _planned_calls()
    assert len(calls) == 9
    assert {call.call_id for call in calls} == {
        "A", "B1", "B2", "B3", "C1", "C2", "C3", "C4", "B4"
    }
    assert all(call.query_length < 512 for call in calls)


def test_smoke_cost_sensitivity_is_offline_and_keeps_seven_calls() -> None:
    """B1/C3 volume changes are visible without provider or DB access."""
    summary = json.loads(SMOKE_SUMMARY_PATH.read_text(encoding="utf-8"))
    assert len(summary["calls"]) == 7

    rates = PricingRates(
        tweet_credits=15.0,
        call_floor_credits=15.0,
        credits_per_usd=100_000.0,
    )
    baseline = cost_cycle_from_summary(summary, rates)

    sensitivity = deepcopy(summary)
    deltas = {"B1": 7, "C3": 4}
    for call in sensitivity["calls"]:
        call["n_results"] += deltas.get(call["call_id"], 0)
    changed = cost_cycle_from_summary(sensitivity, rates)

    assert len(sensitivity["calls"]) == 7
    assert changed.total_credits - baseline.total_credits == (
        sum(deltas.values()) * 15
    )
    assert changed.total_credits > baseline.total_credits
