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
    monkeypatch.setattr(quality, "BUDGET_TEMPERATURE_ZERO_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_GOLD_AUDIT_PATH", budget_path)
    monkeypatch.setattr(quality, "BUDGET_PRODUCTION_BATCH_PATH", budget_path)
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


def test_final_budget_profile_cannot_fall_through_to_development_budget(
    monkeypatch, tmp_path
):
    final_budget = {
        "lanes": {
            "final_only": {
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "maximum_examples": 700,
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
    budget_path = tmp_path / "final-budget.json"
    budget_path.write_text(json.dumps(final_budget))
    monkeypatch.setattr(quality, "BUDGET_FINAL_GATE_PATH", budget_path)
    monkeypatch.setattr(quality, "PRIVATE", tmp_path)
    monkeypatch.setattr(quality, "AnthropicClaudeClient", _Client)
    monkeypatch.setenv("U18_BUDGET_PROFILE", "final")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")

    transport = quality.BudgetedTransport("final_only")

    assert transport.budget["maximum_examples"] == 700
    with pytest.raises(RuntimeError, match="absent from the final evaluation budget"):
        quality.BudgetedTransport("development_only")


def test_cohort_rejects_duplicate_example_ids_before_transport(monkeypatch, tmp_path):
    cohort_path = tmp_path / "cohort-source.json"
    cohort_path.write_text(
        json.dumps(
            {
                "rows": [
                    {"example_id": "post-1", "brand_id": "brand-a"},
                    {"example_id": "post-1", "brand_id": "brand-b"},
                ]
            }
        )
    )
    monkeypatch.setattr(quality, "COHORT_PATH", cohort_path)

    with pytest.raises(ValueError, match="example_id values must be unique"):
        quality._read_cohort()


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
    assert (
        "Product-label keys are forbidden in post_types"
        in quality.CONTRACT_GOLD_AUDIT_REPAIR_SYSTEM
    )
    assert "source-verifiable evidence" in quality.CONTRACT_GOLD_AUDIT_REPAIR_SYSTEM
    assert quality.TAXONOMIES["v3r3"]["prompt_version"] == "stage1-prompt-v6"
    assert quality.TAXONOMIES["v3r4"]["prompt_version"] == "stage1-prompt-v7"
    assert quality.TAXONOMIES["v3r5"]["prompt_version"] == "stage1-prompt-v8"


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


def test_blinded_review_packet_excludes_selection_and_role_hints():
    source = {
        "example_id": "post-1",
        "brand_id": "llama",
        "source_language": "en",
        "context_provenance": [],
        "stratum": "event_opportunity_boundary",
        "source_role": "official",
        "source_hint": "opportunity",
        "input": {
            "tweet_id": "post-1",
            "text": "Source text",
            "brand_ids": ["llama"],
            "context": [],
        },
    }

    packet = quality._review_input(source)

    assert packet == {
        "example_id": "post-1",
        "brand_id": "llama",
        "source_language": "en",
        "context_provenance": [],
        "source": source["input"],
    }
    assert "stratum" not in packet
    assert "source_role" not in packet
    assert "source_hint" not in packet


def test_gold_audit_requires_exact_source_evidence():
    source = {
        "example_id": "post-1",
        "brand_id": "llama",
        "input": {"text": "Lee joined the lab.", "context": []},
    }
    classification = {
        "outcome": "classified",
        "post_types": ["personnel_changes"],
        "product_labels": [],
        "sentiment": "neutral",
        "china_nationalism": "none",
        "us_nationalism": "none",
    }
    response = {
        "results": [
            {
                "example_id": "post-1",
                "brand_id": "llama",
                "v3": classification,
                "job_discovery_relevant": False,
                "personnel_discovery_relevant": True,
                "evidence": [
                    {"field": "personnel_changes", "quote": "Lee joined the lab"}
                ],
                "uncertainty_notes": [],
            }
        ]
    }

    parsed = quality._parse_contract_audit(response, [source])
    assert parsed[0]["evidence"][0]["quote"] == "Lee joined the lab"

    response["results"][0]["evidence"][0]["quote"] = "fabricated quote"
    with pytest.raises(ValueError, match="exact source substring"):
        quality._parse_contract_audit(response, [source])


def test_gold_audit_allows_empty_evidence_only_for_context_missing():
    source = {
        "example_id": "post-1",
        "brand_id": "llama",
        "input": {"text": "Unrelated sports recap", "context": []},
    }
    classification = {
        "outcome": "context_missing",
        "post_types": [],
        "product_labels": [],
        "sentiment": None,
        "china_nationalism": None,
        "us_nationalism": None,
    }
    response = {
        "results": [
            {
                "example_id": "post-1",
                "brand_id": "llama",
                "v3": classification,
                "job_discovery_relevant": False,
                "personnel_discovery_relevant": False,
                "evidence": [],
                "uncertainty_notes": ["No usable brand context."],
            }
        ]
    }

    assert quality._parse_contract_audit(response, [source])[0]["evidence"] == []

    response["results"][0]["v3"] = {
        **classification,
        "outcome": "classified",
        "post_types": ["other"],
        "sentiment": "neutral",
    }
    with pytest.raises(ValueError, match="must not be empty"):
        quality._parse_contract_audit(response, [source])


def test_gold_audit_resolves_markdown_and_unicode_to_actual_source_span():
    source = "**general‑purpose AI** works"

    assert (
        quality._resolve_source_quote(source, "general-purpose AI")
        == "general‑purpose AI"
    )
    assert quality._resolve_source_quote(source, "unrelated claim") is None


def test_gold_audit_resolves_rendered_html_entity_to_actual_source_span():
    source = "speed of &gt; 100 tok/s"

    assert (
        quality._resolve_source_quote(source, "speed of > 100 tok/s")
        == "speed of &gt; 100 tok/s"
    )


def test_gold_audit_resolves_source_line_wrapping_to_actual_source_span():
    source = "美国最大的优势集中在：\n\nfrontier model、\n\n芯片"

    assert (
        quality._resolve_source_quote(
            source, "美国最大的优势集中在：frontier model、芯片"
        )
        == source
    )


def test_gold_audit_resolves_curly_quote_to_actual_source_span():
    source = "the world’s most advanced technologies"

    assert (
        quality._resolve_source_quote(source, "the world's most advanced technologies")
        == source
    )


def test_audited_v3_projection_recovers_frozen_v2_type_semantics():
    common = {
        "outcome": "classified",
        "product_labels": [],
        "sentiment": "neutral",
        "china_nationalism": "none",
        "us_nationalism": "none",
    }

    combined = quality._project_v3_classification_to_v2(
        {
            **common,
            "post_types": ["opportunities", "events", "job_listings"],
        }
    )
    personnel_only = quality._project_v3_classification_to_v2(
        {**common, "post_types": ["personnel_changes"]}
    )
    personnel_with_business = quality._project_v3_classification_to_v2(
        {**common, "post_types": ["personnel_changes", "business_finance"]}
    )

    assert combined["post_types"] == ["events_opportunities"]
    assert personnel_only["post_types"] == ["other"]
    assert personnel_with_business["post_types"] == ["business_finance"]


def test_v3r6_candidate_uses_the_production_batch_size():
    assert quality.TAXONOMIES["v3r6"]["batch_size"] == 20
    assert quality.TAXONOMIES["v3r6"]["prompt_version"] == "stage1-prompt-v8"


def test_v3r7_candidate_tests_prompt_v9_at_the_production_batch_size():
    assert quality.TAXONOMIES["v3r7"]["batch_size"] == 20
    assert quality.TAXONOMIES["v3r7"]["prompt_version"] == "stage1-prompt-v9"


def test_v3r8_candidate_tests_pro_model_with_the_same_prompt_and_batch_size():
    assert quality.TAXONOMIES["v3r8"]["batch_size"] == 20
    assert quality.TAXONOMIES["v3r8"]["prompt_version"] == "stage1-prompt-v9"


def test_v3r9_candidate_tests_prompt_v10_at_the_production_batch_size():
    assert quality.TAXONOMIES["v3r9"]["batch_size"] == 20
    assert quality.TAXONOMIES["v3r9"]["prompt_version"] == "stage1-prompt-v10"
