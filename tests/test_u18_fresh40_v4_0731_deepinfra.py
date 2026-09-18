import json

import pytest

from scripts import u18_fresh40_v4_0731_adapted as adapted
from scripts import u18_fresh40_v4_0731_deepinfra as subject
from scripts import u18_fresh40_v4_0731_deepinfra_diagnose as diagnose


def response(batch, role):
    decisions, posts = adapted.slot_map(batch)
    if role == "content":
        values = {
            slot: {"outcome": "classified", "post_types": ["other"], "audience_topics": ["none"]}
            for slot in decisions
        }
        payload = {"decisions": values, "post_promotions": {slot: ["none"] for slot in posts}}
    else:
        values = {
            slot: {
                "product_labels": ["none"], "sentiment": "neutral", "geopolitical_modes": ["none"],
                "china_national_stance": "none", "us_national_stance": "none",
            }
            for slot in decisions
        }
        payload = {"decisions": values}
    return {
        "model": subject.MODEL,
        "provider": subject.PROVIDER,
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "completion_tokens_details": {"reasoning_tokens": 0}},
        "openrouter_metadata": {"endpoints": {"available": [{"provider": subject.PROVIDER, "selected": True}]}},
    }


def test_request_is_deepinfra_without_native_response_format():
    body = subject.request(subject.sol.packets()[:20], "content")
    assert "response_format" not in body
    assert body["provider"]["only"] == ["DeepInfra"]
    assert body["provider"]["allow_fallbacks"] is False
    assert body["provider"]["quantizations"] == ["fp8"]
    assert body["temperature"] == 1.0
    assert body["top_p"] == 1.0
    assert body["seed"] == 42


def test_parse_preserves_cross_axis_label_as_semantic_issue():
    batch = subject.sol.packets()[:2]
    decoded = response(batch, "content")
    parsed = json.loads(decoded["choices"][0]["message"]["content"])
    first_slot = next(iter(parsed["decisions"]))
    parsed["decisions"][first_slot]["audience_topics"] = ["business_finance"]
    decoded["choices"][0]["message"]["content"] = json.dumps(parsed)

    rows, issues = subject.parse(decoded, batch, "content")

    assert len(rows) == 2
    assert {issue["issue"] for issue in issues} == {"invalid label"}
    assert rows[0]["by_brand"][0]["audience_topics"] == ["business_finance"]


def test_parse_rejects_structural_omission():
    batch = subject.sol.packets()[:2]
    decoded = response(batch, "brand")
    parsed = json.loads(decoded["choices"][0]["message"]["content"])
    parsed["decisions"].pop(next(iter(parsed["decisions"])))
    decoded["choices"][0]["message"]["content"] = json.dumps(parsed)

    with pytest.raises(ValueError, match="fixed decision slots missing or extra"):
        subject.parse(decoded, batch, "brand")


def test_attestation_rejects_wrong_selected_provider():
    batch = subject.sol.packets()[:1]
    decoded = response(batch, "content")
    decoded["openrouter_metadata"]["endpoints"]["available"][0]["provider"] = "Other"

    with pytest.raises(ValueError, match="selected endpoint attestation failed"):
        subject.parse(decoded, batch, "content")


def test_representation_normalization_maps_only_empty_sentinels():
    result = {
        "roles": {
            "content": [{
                "case_id": "L45-01",
                "by_brand": [{
                    "brand_id": "brand-1", "outcome": "classified", "post_types": [],
                    "audience_topics": [],
                }],
                "untracked_brand_promotions": [],
            }]
        },
        "semantic_issues": [{"issue": "empty classification array"}],
    }

    normalized = diagnose.representation_normalized(result)

    brand = normalized["roles"]["content"][0]["by_brand"][0]
    assert brand["post_types"] == ["other"]
    assert brand["audience_topics"] == ["none"]
    assert normalized["roles"]["content"][0]["untracked_brand_promotions"] == ["none"]
    assert normalized["semantic_issues"] == []
    assert len(normalized["representation_normalization"]["changes"]) == 3
