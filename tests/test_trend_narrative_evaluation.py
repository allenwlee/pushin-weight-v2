from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from monitor.trend_narrative_candidates import project_provider_packet
from monitor.trend_narrative_evaluation import (
    DENSITY_EXCERPT_CHARACTERS,
    DIMENSIONS,
    EVIDENCE_BUDGETS,
    EvaluationConfigurationError,
    EvaluationManifest,
    blank_editorial_rubric,
    build_evaluation_calls,
    build_synthetic_snapshot,
    calibrate_historical_materiality,
    evaluation_preflight,
    load_evaluation_scenarios,
    missing_pairwise_combinations,
    propose_materiality_bands,
    run_synthetic_evaluation,
    validate_editorial_rubric,
)
from x_monitor.config import HeadlineNarrativeConfig

SCENARIOS = Path("tests/fixtures/trend_narrative_evaluation_scenarios.json")


def _manifest(**overrides) -> EvaluationManifest:
    values = {
        "run_id": "unit-evaluation",
        "model": "deepseek-v4-pro",
        "max_calls": 28,
        "input_token_budget": 20_000_000,
        "dollar_budget": "100.00",
        "input_dollars_per_million_tokens": "1.00",
        "output_dollars_per_million_tokens": "2.00",
        "pricing_checked_at": "2026-08-14T00:00:00Z",
        "context_window_tokens": 300_000,
        "concurrency": 1,
    }
    values.update(overrides)
    return EvaluationManifest.from_mapping(values)


def _valid_payload() -> dict:
    return {
        "body_en": "DeepSeek conversation showed the clearest sustained shift in this window.",
        "body_zh_cn": "DeepSeek 在这一时段呈现出最清晰且持续的讨论变化。",
        "observations_en": [],
        "observations_zh_cn": [],
        "selected_candidate_ids": ["deepseek:full_window"],
        "subjects": [
            {
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "candidate_id": "deepseek:full_window",
                "observed_name": "",
                "evidence_ids": [],
            }
        ],
        "claims": [
            {
                "observation_index": -1,
                "candidate_ids": ["deepseek:full_window"],
                "families": ["volume"],
                "evidence_ids": [],
                "quantitative_fact_ids": [],
                "event_anchor": "",
                "explanation_type": "aggregate_trajectory",
                "evidence_confidence": "aggregate_only",
            }
        ],
    }


class _FakeMessages:
    def __init__(self, owner, payload):
        self.owner = owner
        self.payload = payload

    def create(self, **request):
        self.owner.active += 1
        self.owner.max_active = max(self.owner.max_active, self.owner.active)
        self.owner.requests.append(request)
        if self.owner.cancel_path is not None and len(self.owner.requests) == 1:
            self.owner.cancel_path.touch()
        try:
            text = (
                self.payload
                if isinstance(self.payload, str)
                else json.dumps(self.payload, ensure_ascii=False)
            )
            return SimpleNamespace(
                content=[SimpleNamespace(text=text)],
                usage=SimpleNamespace(input_tokens=500, output_tokens=120),
            )
        finally:
            self.owner.active -= 1


class _FakeClient:
    def __init__(self, payload=None, *, cancel_path=None):
        self.requests = []
        self.active = 0
        self.max_active = 0
        self.cancel_path = cancel_path
        self.messages = _FakeMessages(self, payload or _valid_payload())

    def factory(self, **_kwargs):
        return self


def test_scenario_fixture_pairwise_covers_all_eight_dimensions():
    scenarios = load_evaluation_scenarios(SCENARIOS)

    assert len(scenarios) == 16
    assert set(scenarios[0]["dimensions"]) == set(DIMENSIONS)
    assert missing_pairwise_combinations(scenarios) == []


def test_call_plan_separates_count_and_density_sweeps():
    calls = build_evaluation_calls(load_evaluation_scenarios(SCENARIOS))
    count_calls = [call for call in calls if call.sweep == "evidence_count"]
    density_calls = [call for call in calls if call.sweep == "excerpt_density"]

    assert len(calls) == 28
    assert {call.evidence_budget for call in count_calls} == set(EVIDENCE_BUDGETS)
    assert {call.excerpt_characters for call in count_calls} == {1_000}
    assert {call.evidence_budget for call in density_calls} == {24}
    assert {call.excerpt_characters for call in density_calls} == set(
        DENSITY_EXCERPT_CHARACTERS
    )


def test_evidence_budget_variants_are_strict_supersets_with_fixed_facts():
    calls = build_evaluation_calls(load_evaluation_scenarios(SCENARIOS))
    count_calls = [
        call
        for call in calls
        if call.sweep == "evidence_count" and call.scenario_id == "pair-16"
    ]
    snapshots = [build_synthetic_snapshot(call) for call in count_calls]
    evidence_ids = [
        [row["evidence_id"] for row in snapshot["candidates"][0]["evidence"]]
        for snapshot in snapshots
    ]

    assert [len(ids) for ids in evidence_ids] == list(EVIDENCE_BUDGETS)
    assert all(
        evidence_ids[index] == evidence_ids[index + 1][: len(evidence_ids[index])]
        for index in range(len(evidence_ids) - 1)
    )
    assert (
        len(
            {
                json.dumps(snapshot["candidates"][0]["family_facts"], sort_keys=True)
                for snapshot in snapshots
            }
        )
        == 1
    )


def test_synthetic_snapshot_uses_production_provider_projection_and_packet_bound():
    call = next(
        call
        for call in build_evaluation_calls(load_evaluation_scenarios(SCENARIOS))
        if call.sweep == "evidence_count" and call.evidence_budget == 48
    )
    packet = project_provider_packet(build_synthetic_snapshot(call))

    assert len(packet["candidates"][0]["evidence"]) == 48
    assert len(json.dumps(packet, ensure_ascii=False).encode()) < 128 * 1024
    assert "series" not in packet["candidates"][0]
    assert "coarse_series" in packet["candidates"][0]


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"max_calls": None}, "evaluation_manifest_missing:max_calls"),
        (
            {"input_token_budget": None},
            "evaluation_manifest_missing:input_token_budget",
        ),
        ({"dollar_budget": None}, "evaluation_manifest_missing:dollar_budget"),
        ({"dollar_budget": "NaN"}, "evaluation_budgets_must_be_finite"),
        ({"model": "ambient-default"}, "evaluation_model_must_be_explicit"),
        (
            {"context_window_tokens": None},
            "evaluation_manifest_missing:context_window_tokens",
        ),
        ({"concurrency": 2}, "evaluation_concurrency_must_be_one"),
        ({"pricing_checked_at": "yesterday"}, "evaluation_pricing_timestamp_invalid"),
    ],
)
def test_manifest_requires_finite_budgets_exact_model_and_concurrency_one(
    overrides, error
):
    with pytest.raises(EvaluationConfigurationError, match=error):
        _manifest(**overrides)


def test_preflight_is_provider_free_and_reports_resource_envelope():
    scenarios = load_evaluation_scenarios(SCENARIOS)
    preflight = evaluation_preflight(_manifest(), scenarios, HeadlineNarrativeConfig())

    assert preflight["transport_enabled"] is False
    assert preflight["planned_call_count"] == 28
    assert preflight["planned_calls_fit_call_cap"] is True
    assert preflight["concurrency"] == 1
    assert all(item["packet_bytes"] > 0 for item in preflight["estimates"])
    assert all(item["estimated_input_tokens"] > 0 for item in preflight["estimates"])


def test_preflight_refuses_a_request_outside_checked_context_limit():
    with pytest.raises(EvaluationConfigurationError, match="context_limit"):
        evaluation_preflight(
            _manifest(context_window_tokens=2_000),
            load_evaluation_scenarios(SCENARIOS),
            HeadlineNarrativeConfig(),
        )


def test_runner_is_sequential_exact_model_and_records_complete_artifact():
    fake = _FakeClient()
    artifact = run_synthetic_evaluation(
        _manifest(),
        load_evaluation_scenarios(SCENARIOS),
        HeadlineNarrativeConfig(),
        api_key="unit-secret",
        client_factory=fake.factory,
    )

    assert artifact["execution"]["stop_reason"] == "completed"
    assert artifact["execution"]["calls_used"] == 28
    assert fake.max_active == 1
    assert len(fake.requests) == 28
    assert {request["model"] for request in fake.requests} == {"deepseek-v4-pro"}
    assert {request["max_tokens"] for request in fake.requests} == {1_600}
    assert {
        json.dumps(request["thinking"], sort_keys=True) for request in fake.requests
    } == {'{"type": "disabled"}'}
    result = artifact["results"][0]
    assert result["packet_bytes"] > 0
    assert result["provider_usage"] == {
        "reported": True,
        "input_tokens": 500,
        "output_tokens": 120,
    }
    assert result["latency_ms"] >= 0
    assert result["raw_output"]
    assert result["bilingual_output"]["body_en"].startswith("DeepSeek")
    assert result["validator"] == {"valid": True, "error_code": ""}
    validate_editorial_rubric(result["rubric"])


def test_raw_output_survives_contract_failure():
    fake = _FakeClient("not json")
    artifact = run_synthetic_evaluation(
        _manifest(max_calls=1),
        load_evaluation_scenarios(SCENARIOS),
        HeadlineNarrativeConfig(),
        api_key="unit-secret",
        client_factory=fake.factory,
    )

    assert artifact["results"][0]["raw_output"] == "not json"
    assert artifact["results"][0]["validator"] == {
        "valid": False,
        "error_code": "headline_output_json_invalid",
    }


def test_call_input_and_dollar_boundaries_stop_before_next_transport():
    scenarios = load_evaluation_scenarios(SCENARIOS)
    first_estimate = evaluation_preflight(
        _manifest(), scenarios, HeadlineNarrativeConfig()
    )["estimates"][0]

    call_fake = _FakeClient()
    call_artifact = run_synthetic_evaluation(
        _manifest(max_calls=1),
        scenarios,
        HeadlineNarrativeConfig(),
        api_key="unit-secret",
        client_factory=call_fake.factory,
    )
    assert len(call_fake.requests) == 1
    assert call_artifact["execution"]["stop_reason"] == "call_budget_exhausted"

    token_fake = _FakeClient()
    token_artifact = run_synthetic_evaluation(
        _manifest(input_token_budget=first_estimate["estimated_input_tokens"] - 1),
        scenarios,
        HeadlineNarrativeConfig(),
        api_key="unit-secret",
        client_factory=token_fake.factory,
    )
    assert token_fake.requests == []
    assert token_artifact["execution"]["stop_reason"] == "input_token_budget_exhausted"

    dollar_fake = _FakeClient()
    dollar_artifact = run_synthetic_evaluation(
        _manifest(dollar_budget="0.000001"),
        scenarios,
        HeadlineNarrativeConfig(),
        api_key="unit-secret",
        client_factory=dollar_fake.factory,
    )
    assert dollar_fake.requests == []
    assert dollar_artifact["execution"]["stop_reason"] == "dollar_budget_exhausted"


def test_cancellation_is_checked_between_calls(tmp_path):
    cancellation_path = tmp_path / "cancel"
    fake = _FakeClient(cancel_path=cancellation_path)

    artifact = run_synthetic_evaluation(
        _manifest(),
        load_evaluation_scenarios(SCENARIOS),
        HeadlineNarrativeConfig(),
        api_key="unit-secret",
        client_factory=fake.factory,
        cancellation_path=cancellation_path,
    )

    assert len(fake.requests) == 1
    assert artifact["execution"]["stop_reason"] == "cancelled"


def test_reported_usage_reconciles_reserved_budget_for_following_calls():
    scenarios = load_evaluation_scenarios(SCENARIOS)
    estimates = evaluation_preflight(_manifest(), scenarios, HeadlineNarrativeConfig())[
        "estimates"
    ]
    reconciled_cap = (
        estimates[0]["estimated_input_tokens"]
        + estimates[1]["estimated_input_tokens"]
        - 1
    )
    fake = _FakeClient()
    artifact = run_synthetic_evaluation(
        _manifest(input_token_budget=reconciled_cap),
        scenarios,
        HeadlineNarrativeConfig(),
        api_key="unit-secret",
        client_factory=fake.factory,
    )

    # Carrying the first reservation forward would reject call two by one
    # token. Reconciliation to its reported 500 input tokens admits call two.
    assert artifact["execution"]["calls_used"] >= 2
    assert len(fake.requests) >= 2


def test_synthetic_runner_never_publishes_enqueues_or_harvests(monkeypatch):
    from core.models import TrendNarrative
    from monitor.cycle import CycleRunner
    from monitor.tasks import refresh_trend_narratives

    def forbidden(*_args, **_kwargs):
        pytest.fail("synthetic evaluation crossed a production mutation boundary")

    monkeypatch.setattr(TrendNarrative, "save", forbidden)
    monkeypatch.setattr(CycleRunner, "run", forbidden)
    monkeypatch.setattr(refresh_trend_narratives, "delay", forbidden)
    fake = _FakeClient()

    artifact = run_synthetic_evaluation(
        _manifest(max_calls=1),
        load_evaluation_scenarios(SCENARIOS),
        HeadlineNarrativeConfig(),
        api_key="unit-secret",
        client_factory=fake.factory,
    )

    assert artifact["execution"]["calls_used"] == 1


def test_rubric_contract_is_closed_and_notes_are_required():
    rubric = blank_editorial_rubric()
    validate_editorial_rubric(rubric)
    rubric["supported_why"]["verdict"] = "maybe"

    with pytest.raises(EvaluationConfigurationError, match="rubric_value"):
        validate_editorial_rubric(rubric)


def _facts(window, value, *, comparison_allowed=True):
    return {
        "window_days": window,
        "comparison_allowed": comparison_allowed,
        "candidates": [
            {
                "family_facts": {
                    "volume": {"change_pct": str(value)},
                    "engagement": {"intensity_change_pct": str(value + 1)},
                    "post_type": {"labels": [{"brand_change_pp": str(value + 2)}]},
                    "discourse": {"labels": [{"brand_change_pp": str(value + 3)}]},
                    "sentiment": {"labels": [{"brand_change_pp": str(value + 4)}]},
                    "china_nationalism": {"labels": []},
                    "us_nationalism": {"labels": []},
                }
            }
        ],
    }


def test_historical_calibration_is_bounded_read_only_and_groups_window_family():
    anchors = [datetime(2026, 8, day, tzinfo=UTC) for day in (10, 11, 12)]
    calls = []

    def loader(window, anchor):
        calls.append((window, anchor))
        return _facts(window, Decimal(anchor.day - 9))

    report = calibrate_historical_materiality(
        anchors=anchors,
        windows=(7,),
        minimum_samples=3,
        epsilon=Decimal("0.1"),
        facts_loader=loader,
    )

    assert len(calls) == 3
    assert report["read_only"] is True
    assert report["config_written"] is False
    volume = next(group for group in report["groups"] if group["family"] == "volume")
    assert volume["status"] == "proposed"
    assert volume["sample_count"] == 3
    assert volume["anchor_coverage"] == "1.000000"
    assert volume["distribution"] == {
        "p50": "2.000000",
        "p75": "2.500000",
        "p90": "2.800000",
    }


def test_calibration_rejects_under_sampled_groups_without_a_proposal():
    report = propose_materiality_bands(
        [
            {
                "window_days": 7,
                "family": "volume",
                "anchor": "one",
                "absolute_change": "0.1",
            }
        ],
        expected_anchors={7: 4},
        minimum_samples=2,
        epsilon=Decimal("0.1"),
    )
    volume = next(group for group in report["groups"] if group["family"] == "volume")

    assert volume["status"] == "insufficient_samples"
    assert volume["proposed_bands"] == {}
    assert volume["anchor_coverage"] == "0.250000"


def test_calibration_anchor_count_has_a_hard_upper_bound():
    anchors = [datetime(2026, 8, 14, tzinfo=UTC)] * 65

    with pytest.raises(EvaluationConfigurationError, match="anchor_bound"):
        calibrate_historical_materiality(anchors=anchors, facts_loader=lambda *_: {})
