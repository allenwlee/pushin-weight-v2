from scripts import u18_fresh40_v4_0731_json_mode as subject


def test_json_mode_avoids_large_provider_schema_and_keeps_fixed_slots():
    packets = subject.sol.packets()[:20]
    body = subject.request(packets, "content")
    assert body["response_format"] == {"type": "json_object"}
    assert "D27" in body["messages"][0]["content"]
    assert "P20" in body["messages"][0]["content"]
    assert "json_schema" not in str(body["response_format"])


def test_json_mode_uses_official_sampling_and_pinned_route():
    body = subject.request(subject.sol.packets()[:20], "brand")
    assert body["temperature"] == 1.0
    assert body["top_p"] == 1.0
    assert body["seed"] == 42
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    assert body["provider"]["only"] == ["OpenInference"]
    assert body["provider"]["allow_fallbacks"] is False
