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


def test_active_tuning_manifest_rejects_competing_model_arm():
    import pytest

    with pytest.raises(ValueError, match="0731_only_workflow"):
        _manifest("incumbent", concurrency=3)


def test_finance_calibration_repairs_require_independent_review(monkeypatch):
    import json

    from monitor import trend_narrative_evaluation as evaluation
    from monitor.trend_narrative_generation import _finance_contract

    config = HeadlineNarrativeConfig(
        provider="deepinfra", model=DEEPSEEK_0731_MODEL,
        base_url="https://api.deepinfra.com/v1/openai",
        editor_prompt_version="headline-editor-finance-v1-ja",
        critic_prompt_version="headline-critic-finance-v1-ja",
        editor_request_profile="headline_editor_v3", critic_request_profile="headline_critic_v3",
    )
    assert _finance_contract(config.editor_prompt_version)
    batch = evaluation._calibration_control_batch([build_synthetic_per_brand_snapshot(3)])
    # The real request builder, schema, and validator run. Only transport is replaced.
    def execute(stage, envelope, request, config, ledger, calls, **kwargs):
        packet = envelope["analysis_packet"]
        repaired = evaluation._supported_editor_response({
            "analysis_packet": packet, "packet_hash": envelope["packet_hash"],
            "batch_key": envelope["batch_key"], "prompt_version": config.editor_prompt_version,
        })
        raw = {"critic_response_schema_version": 3, "packet_hash": envelope["packet_hash"],
               "batch_key": envelope["batch_key"], "decisions": [
                   {"brand_key": n["brand_key"], "decision": "repair", "narrative": n, "hold_code": None}
                   for n in repaired["brands"]]}
        call = {"raw_response": json.dumps(raw)}
        calls.append(call)
        return call

    monkeypatch.setattr(evaluation, "_execute_call", execute)
    result = evaluation._run_calibration_controls(batch, config, evaluation._EvaluationLedger(_manifest("candidate")), [],
                                                api_key="test", client_factory=None, cancellation_path=None)
    assert len(result) == 8
    assert all(row["mechanically_valid"] for row in result)
    assert not any(row["false_accept"] for row in result)
    assert sum(row["repair_review_required"] for row in result) == 7
    assert all(row["narrative"] for row in result)


def test_active_0731_preflight_rejects_stale_pricing():
    from dataclasses import replace

    import pytest

    from monitor.trend_narrative_evaluation import EvaluationConfigurationError

    config = HeadlineNarrativeConfig(provider="deepinfra", model=DEEPSEEK_0731_MODEL,
                                     base_url="https://api.deepinfra.com/v1/openai")
    manifest = replace(_manifest("candidate"), pricing_checked_at="2026-08-01T00:00:00Z")
    with pytest.raises(EvaluationConfigurationError, match="pricing_snapshot_stale"):
        evaluation_preflight(manifest, [build_synthetic_per_brand_snapshot(1)], config,
                             include_calibration_controls=False)


def test_finance_gold_control_establishes_brand_and_preserves_percent_unit():
    from monitor import trend_narrative_evaluation as evaluation
    from monitor.trend_narrative_generation import build_per_brand_editor_request

    config = HeadlineNarrativeConfig(provider="deepinfra", model=DEEPSEEK_0731_MODEL,
        base_url="https://api.deepinfra.com/v1/openai",
        editor_prompt_version="headline-editor-finance-v7-ja", editor_request_profile="headline_editor_v4",
        critic_prompt_version="headline-critic-finance-source-audit-v5-ja", critic_request_profile="headline_critic_v5")
    batch = evaluation._calibration_batch([], config)
    dossier = batch["dossiers"][0]
    assert all(dossier['display_name_en'] in source['excerpt'] for source in dossier['evidence'])
    envelope, _ = build_per_brand_editor_request(batch, config)
    gold = evaluation._supported_editor_response(envelope)["brands"][0]
    assert "15%" in gold["secondary_en"] and "15%" in gold["secondary_zh_cn"]
    assert "Selected posts" in gold["headline_en"]
    assert all(value in gold["secondary_ja"] for value in ("15%", "100", "115", "リリース発表ではない"))
