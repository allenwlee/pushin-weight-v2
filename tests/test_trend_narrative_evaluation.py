"""Finite per-brand evaluation contracts."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from monitor.trend_narrative_evaluation import (
    EvaluationConfigurationError,
    EvaluationManifest,
    _EvaluationLedger,
    _every_eligible_brand_decided,
    _execute_call,
    _supported_editor_response,
    build_synthetic_per_brand_snapshot,
    calibrate_historical_materiality,
    evaluation_preflight,
    run_per_brand_evaluation,
    select_evaluation_snapshot,
    write_evaluation_artifacts,
)
from monitor.trend_narrative_generation import HeadlineGenerationError
from x_monitor.config import HeadlineNarrativeConfig


def _manifest(**overrides) -> EvaluationManifest:
    values = {
        "run_id": "per-brand-eval-test",
        "reviewer": "codex:test",
        "model": "deepseek-v4-flash",
        "max_calls": 17,
        "input_token_budget": 2_000_000,
        "output_token_budget": 200_000,
        "dollar_budget": "10",
        "input_dollars_per_million_tokens": "0.50",
        "output_dollars_per_million_tokens": "2.00",
        "pricing_version": "test-pricing-v1",
        "pricing_checked_at": "2026-08-27T00:00:00+00:00",
        "context_window_tokens": 500_000,
        "brand_cap": 25,
        "concurrency": 1,
    }
    values.update(overrides)
    return EvaluationManifest.from_mapping(values)


def _snapshots():
    return [build_synthetic_per_brand_snapshot(count) for count in (1, 3, 5)]


class _Messages:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **request):
        self.owner.requests.append(request)
        self.owner.active += 1
        self.owner.max_active = max(self.owner.max_active, self.owner.active)
        try:
            content = request["messages"][0]["content"]
            payload = None
            if content.startswith("Critique"):
                envelope = json.loads(content.split("\n", 1)[1])
                editor = json.loads(envelope["editor_response_raw"])
                decisions = []
                for narrative in editor["brands"]:
                    headline = narrative["headline_en"]
                    hold_code = (
                        "event_conflation"
                        if "Imaginary-Two" in headline
                        else "unsupported_event"
                        if "launched Imaginary-One" in headline
                        else "unsupported_causality"
                        if "made every deployment faster" in headline
                        else "translation_not_equivalent"
                        if "moon-mining" in narrative["headline_zh_cn"]
                        or "月球采矿" in narrative["headline_zh_cn"]
                        else "cross_brand_evidence"
                        if "Separate brands' reports" in headline
                        else "unsupported_quote"
                        if "guaranteed 10x faster" in headline
                        else "unsafe_instruction_following"
                        if "as the post instructed" in headline
                        else None
                    )
                    if (
                        self.owner.invalid_unsupported_control
                        and hold_code == "unsupported_event"
                    ):
                        payload = "{malformed-control"
                        break
                    repaired_adversarial = (
                        hold_code == "unsupported_event"
                        and self.owner.repair_adversarial
                    )
                    decisions.append(
                        {
                            "brand_key": narrative["brand_key"],
                            "decision": (
                                "repair"
                                if repaired_adversarial
                                else "hold"
                                if hold_code
                                else "approve"
                            ),
                            "narrative": (
                                narrative
                                if repaired_adversarial or hold_code is None
                                else None
                            ),
                            "hold_code": (
                                hold_code
                                if hold_code and not repaired_adversarial
                                else None
                            ),
                        }
                    )
                if not isinstance(payload, str):
                    payload = {
                        "critic_response_schema_version": 1,
                        "packet_hash": envelope["packet_hash"],
                        "batch_key": envelope["batch_key"],
                        "decisions": decisions,
                    }
            else:
                envelope = json.loads(content.split("request_envelope=", 1)[1])
                if "rank every manifest brand" in request["system"].casefold():
                    payload = {
                        "rank_response_schema_version": 1,
                        "packet_hash": envelope["packet_hash"],
                        "batch_key": envelope["batch_key"],
                        "ordered_brands": [
                            {
                                "brand_key": dossier["brand_key"],
                                "confidence": "medium",
                                "reason_refs": [
                                    {
                                        "kind": "fact",
                                        "id": dossier["facts"][0]["fact_id"],
                                    }
                                ],
                            }
                            for dossier in reversed(
                                envelope["analysis_packet"]["dossiers"]
                            )
                        ],
                    }
                else:
                    payload = _supported_editor_response(envelope)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text=(
                            payload
                            if isinstance(payload, str)
                            else json.dumps(payload, ensure_ascii=False)
                        )
                    )
                ],
                usage=SimpleNamespace(input_tokens=500, output_tokens=200),
            )
        finally:
            self.owner.active -= 1
            if self.owner.cancel_path is not None and len(self.owner.requests) == 1:
                self.owner.cancel_path.touch()


class _Client:
    def __init__(
        self,
        cancel_path: Path | None = None,
        *,
        repair_adversarial: bool = False,
        invalid_unsupported_control: bool = False,
    ):
        self.requests = []
        self.active = 0
        self.max_active = 0
        self.cancel_path = cancel_path
        self.repair_adversarial = repair_adversarial
        self.invalid_unsupported_control = invalid_unsupported_control
        self.messages = _Messages(self)

    def factory(self, **_kwargs):
        return self


def test_manifest_requires_explicit_model_reviewer_budgets_and_concurrency_one():
    with pytest.raises(EvaluationConfigurationError, match="reviewer"):
        _manifest(reviewer=None)
    with pytest.raises(EvaluationConfigurationError, match="model_must_be_explicit"):
        _manifest(model="ambient")
    with pytest.raises(EvaluationConfigurationError, match="concurrency"):
        _manifest(concurrency=2)
    with pytest.raises(EvaluationConfigurationError, match="finite"):
        _manifest(dollar_budget="NaN")


def test_synthetic_preflight_exactly_counts_rank_editor_critic_and_controls():
    preflight = evaluation_preflight(
        _manifest(),
        _snapshots(),
        HeadlineNarrativeConfig(),
        include_calibration_controls=True,
    )

    assert preflight["planned_call_count"] == 17
    assert preflight["publication_enabled"] is False
    assert preflight["concurrency"] == 1
    assert [row["planned_call_count"] for row in preflight["windows"]] == [3, 3, 3]
    assert {row["stage"] for row in preflight["estimates"]} == {
        "rank",
        "editor",
        "critic",
        "critic_calibration",
    }
    assert all(row["packet_bytes"] <= 128 * 1024 for row in preflight["estimates"])


def test_preflight_refuses_each_finite_resource_cap_before_transport():
    for override, code in (
        ({"max_calls": 16}, "call_cap"),
        ({"input_token_budget": 10}, "input_token_cap"),
        ({"output_token_budget": 10}, "output_token_cap"),
        ({"dollar_budget": "0.000001"}, "dollar_cap"),
    ):
        with pytest.raises(EvaluationConfigurationError, match=code):
            evaluation_preflight(
                _manifest(**override),
                _snapshots(),
                HeadlineNarrativeConfig(),
                include_calibration_controls=True,
            )


def test_execution_rechecks_actual_context_and_packet_before_transport():
    context_ledger = _EvaluationLedger(_manifest(context_window_tokens=5))
    with pytest.raises(HeadlineGenerationError, match="evaluation_context_limit"):
        context_ledger.reserve({"max_tokens": 5, "messages": []})

    packet_ledger = _EvaluationLedger(_manifest(max_packet_bytes=10))
    with pytest.raises(HeadlineGenerationError, match="evaluation_packet_limit"):
        _execute_call(
            "editor",
            {"analysis_packet": {"content": "too-large"}},
            {"max_tokens": 1, "messages": []},
            HeadlineNarrativeConfig(),
            packet_ledger,
            [],
            api_key="unit-secret",
            client_factory=lambda **_kwargs: pytest.fail("transport started"),
            cancellation_path=None,
        )


def test_runner_uses_one_transport_at_a_time_and_records_closed_artifact():
    client = _Client()
    artifact = run_per_brand_evaluation(
        _manifest(),
        _snapshots(),
        HeadlineNarrativeConfig(),
        include_calibration_controls=True,
        api_key="unit-secret",
        client_factory=client.factory,
    )

    assert artifact["execution"]["stop_reason"] == "completed"
    assert artifact["execution"]["calls_used"] == 17
    assert len(client.requests) == 17
    assert client.max_active == 1
    assert artifact["publication_enabled"] is False
    assert artifact["activation_assessment"] == {
        "complete": True,
        "every_eligible_brand_decided": True,
        "zero_unsupported_publications": True,
        "calibration_pass": True,
    }
    assert artifact["critic_calibration"]["unsupported_false_accepts"] == 0
    assert artifact["critic_calibration"]["supported_false_holds"] == 0
    assert artifact["critic_calibration"]["invalid_controls"] == 0
    assert artifact["critic_calibration"]["complete_control_set"] is True
    assert {
        control["control"] for control in artifact["critic_calibration"]["controls"]
    } == {
        "supported_gold",
        "unsupported_event",
        "unsupported_causality",
        "event_conflation",
        "mistranslation",
        "cross_evidence_synthesis",
        "invented_detail",
        "unsafe_instruction",
    }
    assert all(
        outcome["quantitative_evidence_present"]
        for outcome in artifact["brand_outcomes"]
    )
    assert all(
        item["verdict"] == "pass"
        for outcome in artifact["brand_outcomes"]
        for item in outcome["rubric"].values()
    )
    assert all(call["raw_response"] for call in artifact["calls"])
    assert all(call["mechanical"]["valid"] is True for call in artifact["calls"])
    assert "unit-secret" not in json.dumps(artifact)


def test_real_style_run_without_controls_cannot_claim_activation_calibration():
    artifact = run_per_brand_evaluation(
        _manifest(),
        _snapshots(),
        HeadlineNarrativeConfig(),
        include_calibration_controls=False,
        api_key="unit-secret",
        client_factory=_Client().factory,
    )

    assert artifact["critic_calibration"]["status"] == "not_run"
    assert artifact["critic_calibration"]["activation_pass"] is False
    assert artifact["activation_assessment"]["calibration_pass"] is False
    assert artifact["activation_assessment"]["zero_unsupported_publications"] is False


def test_completion_counts_repeated_brand_fixtures_instead_of_collapsing_them():
    snapshots = _snapshots()
    outcomes = [
        {
            "window_days": snapshot["window_days"],
            "brand_key": dossier["brand_key"],
            "outcome": "approve",
        }
        for snapshot in snapshots
        for dossier in snapshot["dossiers"]
    ]

    assert _every_eligible_brand_decided(snapshots, outcomes)
    outcomes.pop()
    assert not _every_eligible_brand_decided(snapshots, outcomes)


def test_unsupported_critic_repair_counts_as_a_false_publication():
    client = _Client(repair_adversarial=True)
    artifact = run_per_brand_evaluation(
        _manifest(),
        _snapshots(),
        HeadlineNarrativeConfig(),
        include_calibration_controls=True,
        api_key="unit-secret",
        client_factory=client.factory,
    )

    assert artifact["critic_calibration"]["unsupported_false_accepts"] == 1
    assert artifact["critic_calibration"]["activation_pass"] is False
    assert artifact["activation_assessment"]["zero_unsupported_publications"] is False


def test_invalid_unsupported_control_cannot_pass_calibration():
    artifact = run_per_brand_evaluation(
        _manifest(),
        _snapshots(),
        HeadlineNarrativeConfig(),
        include_calibration_controls=True,
        api_key="unit-secret",
        client_factory=_Client(invalid_unsupported_control=True).factory,
    )

    assert artifact["critic_calibration"]["invalid_controls"] == 1
    assert artifact["critic_calibration"]["activation_pass"] is False
    assert artifact["activation_assessment"]["calibration_pass"] is False
    assert artifact["activation_assessment"]["zero_unsupported_publications"] is False


def test_started_transport_failure_is_conservatively_counted_and_recorded():
    class _FailingMessages:
        @staticmethod
        def create(**_request):
            raise TimeoutError

    artifact = run_per_brand_evaluation(
        _manifest(),
        _snapshots(),
        HeadlineNarrativeConfig(),
        include_calibration_controls=True,
        api_key="unit-secret",
        client_factory=lambda **_kwargs: SimpleNamespace(messages=_FailingMessages()),
    )

    assert artifact["execution"]["stop_reason"] == "headline_provider_timeout"
    assert artifact["execution"]["calls_used"] == 1
    assert Decimal(artifact["execution"]["accounted_cost_dollars"]) > 0
    assert len(artifact["calls"]) == 1
    assert artifact["calls"][0]["raw_response"] == ""
    assert artifact["calls"][0]["mechanical"] == {
        "valid": False,
        "error_code": "headline_provider_timeout",
    }


def test_cancellation_between_calls_keeps_partial_artifact_and_starts_no_next_call(
    tmp_path,
):
    cancel = tmp_path / "cancel"
    client = _Client(cancel)
    artifact = run_per_brand_evaluation(
        _manifest(),
        _snapshots(),
        HeadlineNarrativeConfig(),
        include_calibration_controls=True,
        api_key="unit-secret",
        client_factory=client.factory,
        cancellation_path=cancel,
    )

    assert artifact["execution"]["stop_reason"] == "cancelled"
    assert artifact["execution"]["calls_used"] == 1
    assert len(client.requests) == 1
    assert len(artifact["calls"]) == 1


def test_stratified_cap_preserves_sparse_flat_nonenglish_first_party_and_volume():
    snapshot = build_synthetic_per_brand_snapshot(5)
    selected = select_evaluation_snapshot(snapshot, 5)

    assert selected["evaluation_sampling"]["strategy"] == "all_brands"
    assert len(selected["dossiers"]) == 5

    expanded = deepcopy(snapshot)
    for index in range(5, 12):
        dossier = deepcopy(snapshot["dossiers"][-1])
        dossier["brand_key"] = f"extra-{index}"
        expanded["dossiers"].append(dossier)
    capped = select_evaluation_snapshot(expanded, 5)

    assert capped["evaluation_sampling"]["strategy"] == "stratified_cap"
    assert len(capped["dossiers"]) == 5
    keys = {row["brand_key"] for row in capped["dossiers"]}
    assert {"sparse-lab", "flat-model", "zh-model", "official-ai"} <= keys


def test_artifacts_include_readable_headlines_and_full_json(tmp_path):
    client = _Client()
    artifact = run_per_brand_evaluation(
        _manifest(),
        [build_synthetic_per_brand_snapshot(1)],
        HeadlineNarrativeConfig(),
        include_calibration_controls=True,
        api_key="unit-secret",
        client_factory=client.factory,
    )
    paths = write_evaluation_artifacts(
        artifact, output_dir=tmp_path, stem="2026-08-27-000000-evaluation"
    )

    assert json.loads(paths[0].read_text())["calls"][0]["provider_request"]
    markdown = paths[1].read_text()
    assert "Sparse Lab conversation" in markdown
    assert "Publication writes: `False`" in markdown


def _facts(window, value):
    return {
        "window_days": window,
        "comparison_allowed": True,
        "candidates": [
            {
                "family_facts": {
                    "volume": {"change_pct": str(value)},
                    "engagement": {"intensity_change_pct": str(value + 1)},
                    **{
                        family: {"labels": [{"brand_change_pp": str(value + 2)}]}
                        for family in (
                            "post_type",
                            "discourse",
                            "sentiment",
                            "china_nationalism",
                            "us_nationalism",
                        )
                    },
                }
            }
        ],
    }


def test_historical_materiality_calibration_remains_bounded_and_read_only():
    anchors = [datetime(2026, 8, day, tzinfo=UTC) for day in (10, 11, 12)]
    report = calibrate_historical_materiality(
        anchors=anchors,
        windows=(7,),
        minimum_samples=3,
        epsilon=Decimal("0.1"),
        facts_loader=lambda window, anchor: _facts(window, Decimal(anchor.day - 9)),
    )

    assert report["read_only"] is True
    assert report["config_written"] is False
    volume = next(row for row in report["groups"] if row["family"] == "volume")
    assert volume["status"] == "proposed"
    assert volume["sample_count"] == 3
