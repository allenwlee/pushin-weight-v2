from scripts import u18_fresh40_v4_0731_compare as subject


def test_request_pins_model_provider_quantization_and_disables_reasoning():
    packets = subject.sol.packets()[:20]
    body = subject.request(packets, "content")
    assert body["model"] == "deepseek/deepseek-v4-flash-0731"
    assert body["provider"]["only"] == ["OpenInference"]
    assert body["provider"]["allow_fallbacks"] is False
    assert body["provider"]["quantizations"] == ["fp8"]
    assert body["provider"]["max_price"] == {"prompt": 0.04, "completion": 0.1}
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    assert body["response_format"]["type"] == "json_schema"


def test_request_is_blind_to_owner_answers():
    import json

    body = subject.request(subject.sol.packets()[:20], "brand")
    user_payload = json.loads(body["messages"][-1]["content"])
    forbidden = {"owner", "benchmark", "comments", "answers"}
    assert all(not (set(row) & forbidden) for row in user_payload)
    assert all(not (set(row["context"]) & forbidden) for row in user_payload)


def test_label_metrics_counts_exact_sets_and_label_errors():
    assert subject.control.same(["events", "opportunities"], ["opportunities", "events"])
    assert not subject.control.same(["events"], ["events", "opportunities"])
