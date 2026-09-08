"""Stage 1 single-post classifier and strict parser tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest


@dataclass(frozen=True)
class FakeBrand:
    brand_id: str


def valid_classification(
    brand_id: str = "deepseek",
    **overrides: Any,
) -> dict[str, Any]:
    row = {
        "brand_id": brand_id,
        "outcome": "classified",
        "post_types": ["hands_on_usage", "research_explanations"],
        "product_labels": ["testimonial"],
        "sentiment": "positive",
        "china_nationalism": "none",
        "us_nationalism": None,
    }
    row.update(overrides)
    return row


class FakeClient:
    def __init__(self, response: Any):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_single_prompt_uses_batch_envelope_and_preserves_context():
    from x_monitor.attribution import build_pragmatics_full_prompt

    prompt = build_pragmatics_full_prompt(
        "Reply text",
        ["deepseek"],
        context=[
            {"provenance": "stored_quote", "text": "Quoted artifact"},
            {"provenance": "local_parent", "text": "Parent question"},
        ],
    )
    payload = json.loads(prompt.rsplit("\n", 1)[1])

    assert payload == [{
        "tweet_id": "_single_",
        "text": "Reply text",
        "brand_ids": ["deepseek"],
        "context": [
            {"provenance": "stored_quote", "text": "Quoted artifact"},
            {"provenance": "local_parent", "text": "Parent question"},
        ],
    }]


def test_single_preserves_multilabel_result_and_explicit_unknown():
    from x_monitor.attribution import classify_pragmatics_full

    response = {
        "results": [{
            "tweet_id": "_single_",
            "classifications": [valid_classification()],
            "unsanctioned_flags": ["marketing_spam", "marketing_spam"],
        }]
    }
    client = FakeClient(response)
    result = classify_pragmatics_full(
        "I built a DeepSeek workflow",
        ["deepseek"],
        [FakeBrand("deepseek")],
        client,
        model="deepseek-v4-flash",
        thinking={"type": "disabled"},
    )

    assert result == {
        "by_brand": {
            "deepseek": {
                "outcome": "classified",
                "post_types": ["hands_on_usage", "research_explanations"],
                "product_labels": ["testimonial"],
                "sentiment": "positive",
                "china_nationalism": "none",
                "us_nationalism": None,
            }
        },
        "unsanctioned_flags": ["marketing_spam", "marketing_spam"],
        "valid": True,
    }
    assert client.calls[0]["model"] == "deepseek-v4-flash"
    assert client.calls[0]["thinking"] == {"type": "disabled"}


def test_single_accepts_legacy_unwrapped_transport_response():
    from x_monitor.attribution import classify_pragmatics_full

    client = FakeClient({
        "classifications": [valid_classification()],
        "unsanctioned_flags": [],
    })

    result = classify_pragmatics_full(
        "DeepSeek update", ["deepseek"], [], client
    )

    assert result["valid"] is True
    assert result["by_brand"]["deepseek"]["sentiment"] == "positive"


@pytest.mark.parametrize(
    "classification",
    [
        valid_classification(post_types=["unknown_type"]),
        valid_classification(sentiment="unknown_sentiment"),
        valid_classification(china_nationalism="unknown_axis"),
        valid_classification(product_labels=["unknown_label"]),
        valid_classification(post_types=[]),
        valid_classification(post_types=["other", "hands_on_usage"]),
    ],
)
def test_unknown_or_illegal_values_fail_closed_without_defaults(classification):
    from x_monitor.attribution import classify_pragmatics_full

    client = FakeClient({
        "classifications": [classification],
        "unsanctioned_flags": [],
    })
    result = classify_pragmatics_full(
        "DeepSeek", ["deepseek"], [], client
    )

    assert result == {
        "by_brand": {},
        "unsanctioned_flags": [],
        "valid": False,
    }


@pytest.mark.parametrize(
    "missing_field",
    [
        "outcome",
        "post_types",
        "product_labels",
        "sentiment",
        "china_nationalism",
        "us_nationalism",
    ],
)
def test_missing_required_dimensions_fail_closed(missing_field):
    from x_monitor.attribution import classify_pragmatics_full

    row = valid_classification()
    row.pop(missing_field)
    result = classify_pragmatics_full(
        "DeepSeek",
        ["deepseek"],
        [],
        FakeClient({"classifications": [row]}),
    )

    assert result["valid"] is False


def test_context_missing_is_valid_with_no_edges_and_nullable_scalars():
    from x_monitor.attribution import classify_pragmatics_full

    row = valid_classification(
        outcome="context_missing",
        post_types=[],
        product_labels=[],
        sentiment="negative",
        china_nationalism=None,
        us_nationalism="none",
    )
    result = classify_pragmatics_full(
        "What about this?",
        ["deepseek"],
        [],
        FakeClient({"classifications": [row]}),
    )

    assert result["valid"] is True
    assert result["by_brand"]["deepseek"] == {
        "outcome": "context_missing",
        "post_types": [],
        "product_labels": [],
        "sentiment": "negative",
        "china_nationalism": None,
        "us_nationalism": "none",
    }


def test_missing_unsanctioned_flags_defaults_to_empty_and_unknowns_filter():
    from x_monitor.attribution import classify_pragmatics_full

    missing = classify_pragmatics_full(
        "DeepSeek",
        ["deepseek"],
        [],
        FakeClient({"classifications": [valid_classification()]}),
    )
    filtered = classify_pragmatics_full(
        "DeepSeek",
        ["deepseek"],
        [],
        FakeClient({
            "classifications": [valid_classification()],
            "unsanctioned_flags": [
                "scam", "not_allowed", 42, "scam", "crypto"
            ],
        }),
    )

    assert missing["valid"] is True
    assert missing["unsanctioned_flags"] == []
    assert filtered["unsanctioned_flags"] == ["scam", "scam", "crypto"]


def test_empty_input_missing_client_and_registry_mismatch_make_no_call():
    from x_monitor.attribution import classify_pragmatics_full

    client = FakeClient({})
    expected = {"by_brand": {}, "unsanctioned_flags": [], "valid": False}

    assert classify_pragmatics_full("", ["deepseek"], [], client) == expected
    assert classify_pragmatics_full("text", [], [], client) == expected
    assert classify_pragmatics_full("text", ["deepseek"], [], None) == expected
    assert classify_pragmatics_full(
        "text", ["deepseek"], [FakeBrand("qwen")], client
    ) == expected
    assert client.calls == []


def test_transport_exception_retries_three_times_then_returns_invalid(monkeypatch):
    from x_monitor import attribution

    monkeypatch.setattr(attribution, "_BACKOFF_BASE_SECONDS", 0)
    client = FakeClient(RuntimeError("transport"))

    result = attribution.classify_pragmatics_full(
        "DeepSeek", ["deepseek"], [], client
    )

    assert len(client.calls) == 3
    assert result["valid"] is False
