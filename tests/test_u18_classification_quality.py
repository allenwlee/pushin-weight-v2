from __future__ import annotations

import json

import pytest

from scripts import u18_classification_quality as quality
from x_monitor.provider_telemetry import ProviderResponse


class _Client:
    def __init__(self, **_kwargs):
        pass

    def messages_create(self, **_kwargs):
        return ProviderResponse(
            {"results": []}, usage={"input_tokens": 7, "output_tokens": 3}
        )


def test_transport_refuses_attempt_after_its_frozen_cap(monkeypatch, tmp_path):
    budget = {
        "lanes": {
            "test": {
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "maximum_requests": 1,
                "maximum_transport_attempts": 1,
                "maximum_input_tokens": 100,
                "maximum_output_tokens": 4096,
                "input_usd_per_million": "0.14",
                "output_usd_per_million": "0.28",
                "maximum_cost_usd": "1",
                "maximum_retries_per_request": 0,
            }
        }
    }
    budget_path = tmp_path / "budget.json"
    budget_path.write_text(json.dumps(budget))
    monkeypatch.setattr(quality, "BUDGET_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_AMENDMENT_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_FALLBACK_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_V3_ONLY_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_REPAIR_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_FINAL_REPAIR_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_MINIMAX_BATCH5_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_V3R2_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_V3R2_REPAIR_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_CONTRACT_REVIEW_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_PROMPT_V7_PATH", budget_path)
    monkeypatch.setattr(quality, "PRIVATE", tmp_path)
    monkeypatch.setattr(quality, "AnthropicClaudeClient", _Client)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    transport = quality.BudgetedTransport("test")

    transport.call("request-1", system="a", user="b")
    with pytest.raises(RuntimeError, match="transport attempt cap exhausted"):
        transport.call("request-1", system="a", user="b")

    state = json.loads((tmp_path / "usage-test.json").read_text())
    assert state["logical_request_ids"] == ["request-1"]
    assert state["transport_attempts"] == 1
    assert state["attempts_by_request"] == {"request-1": 1}
    assert state["observed_input_tokens"] == 7
    assert state["observed_output_tokens"] == 3


def test_v2_and_v3_parsers_keep_separate_type_vocabularies():
    classification = {
        "outcome": "classified",
        "post_types": ["job_listings"],
        "product_labels": [],
        "sentiment": "neutral",
        "china_nationalism": None,
        "us_nationalism": None,
    }

    parsed = quality._classification(
        classification, "brand", quality.CANONICAL_POST_TYPE_KEYS
    )
    assert parsed["post_types"] == ["job_listings"]
    with pytest.raises(ValueError, match="closed contract"):
        quality._classification(
            classification, "brand", quality.STAGE1_TAXONOMY_V2_POST_TYPE_KEYS
        )


def test_v3_review_projects_combined_legacy_types_without_mixing_populations():
    projected = quality._project_v3_to_v2(
        {
            "outcome": "classified",
            "post_types": ["events", "opportunities", "job_listings"],
            "product_labels": [],
            "sentiment": "neutral",
            "china_nationalism": None,
            "us_nationalism": None,
        }
    )
    assert projected["post_types"] == ["events_opportunities"]


def test_corrected_gold_uses_exact_production_semantics_without_candidates():
    assert quality._CONTRACT_SEMANTICS in quality.CONTRACT_REVIEW_SYSTEM
    assert "blind to classifier candidates" in quality.CONTRACT_REVIEW_SYSTEM
    assert "candidate_v3r3" not in quality.CONTRACT_REVIEW_SYSTEM
    assert (
        "Product-label keys are forbidden in post_types"
        in quality.CONTRACT_REPAIR_SYSTEM
    )
    assert quality.TAXONOMIES["v3r3"]["prompt_version"] == "stage1-prompt-v6"
    assert quality.TAXONOMIES["v3r4"]["prompt_version"] == "stage1-prompt-v7"


def test_invalid_candidate_row_preserves_coverage_and_raw_response_identity():
    source = {
        "example_id": "post-1",
        "brand_id": "llama",
        "source_language": "en",
        "context_provenance": [],
        "input_context_fingerprint": "a" * 64,
        "stratum": "prevalence",
        "source_role": "third_party",
        "source_hint": None,
    }
    row = quality._invalid_candidate_row(
        source,
        {"results": [{"invalid": True}]},
        ValueError("closed contract"),
    )

    assert row["example_id"] == "post-1"
    assert "classification" not in row
    assert row["invalid_reason"] == "closed contract"
    assert len(row["invalid_response_sha256"]) == 64
