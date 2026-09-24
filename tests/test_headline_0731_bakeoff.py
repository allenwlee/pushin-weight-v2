"""Finite candidate preflight stays separate from live headline publication."""

from __future__ import annotations

from decimal import Decimal

from monitor.trend_narrative_evaluation import (
    build_synthetic_per_brand_snapshot,
    evaluation_preflight,
)
from scripts.headline_0731_bakeoff import _manifest
from x_monitor.config import HeadlineNarrativeConfig
from x_monitor.deepinfra import DEEPSEEK_0731_MODEL


def test_0731_two_brand_bakeoff_preflight_reserves_the_complete_graph():
    config = HeadlineNarrativeConfig(
        provider="deepinfra",
        base_url="https://api.deepinfra.com/v1/openai",
        model=DEEPSEEK_0731_MODEL,
        editor_prompt_version="headline-editor-0731-v1-ja",
        critic_prompt_version="headline-critic-0731-v1-ja",
        per_brand_batch_size=2,
        per_brand_call_cap=41,
        per_brand_input_token_cap=1_600_000,
        per_brand_output_token_cap=350_000,
        per_brand_cost_cap_usd=Decimal("0.30"),
        per_brand_input_usd_per_million=Decimal("0.09"),
        per_brand_output_usd_per_million=Decimal("0.27"),
        per_brand_worker_concurrency=3,
    )
    preflight = evaluation_preflight(
        _manifest("candidate", concurrency=3),
        [build_synthetic_per_brand_snapshot(5)],
        config,
        include_calibration_controls=False,
    )

    assert preflight["planned_call_count"] == 7
    assert preflight["concurrency"] == 3
    assert preflight["transport_enabled"] is False
    assert [row["stage"] for row in preflight["estimates"]] == [
        "rank", "editor", "critic", "editor", "critic", "editor", "critic"
    ]
    assert max(
        len(row["manifest_brand_keys"]) for row in preflight["estimates"][1:]
    ) == 2
