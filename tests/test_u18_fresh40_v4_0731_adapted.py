import json

from scripts import u18_fresh40_v4_0731_adapted as subject


def test_adapted_schema_uses_fixed_slots_without_generated_id_fields():
    packets = subject.sol.packets()[:20]
    schema = subject.response_schema(packets, "content")
    decisions = schema["properties"]["decisions"]["properties"]
    promotions = schema["properties"]["post_promotions"]["properties"]
    expected_decisions = sum(len(packet["brand_ids"]) for packet in packets)
    assert list(decisions) == [f"D{number:02d}" for number in range(1, expected_decisions + 1)]
    assert list(promotions) == [f"P{number:02d}" for number in range(1, 21)]
    encoded = json.dumps(schema)
    assert "case_id" not in encoded
    assert "brand_id" not in encoded


def test_adapted_request_uses_official_sampling_and_pinned_route():
    body = subject.request(subject.sol.packets()[:20], "brand")
    assert body["temperature"] == 1.0
    assert body["top_p"] == 1.0
    assert body["seed"] == 42
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    assert body["provider"]["only"] == ["OpenInference"]
    assert body["provider"]["allow_fallbacks"] is False
    assert body["response_format"]["type"] == "json_schema"


def test_slot_map_preserves_case_and_brand_order():
    packets = subject.sol.packets()[:2]
    decisions, posts = subject.slot_map(packets)
    assert list(posts) == ["P01", "P02"]
    assert [brand for _, brand in decisions.values()] == ["deepseek", "doubao", "glm", "minimax", "deepseek"]
