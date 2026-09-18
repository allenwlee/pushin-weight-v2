from scripts import u18_fresh40_v4_0731_five_post as subject


def test_five_post_batches_cover_all_40_in_order():
    packets = subject.sol.packets()[:40]
    batches = subject.batches(packets)
    assert [len(batch) for batch in batches] == [5] * 8
    assert [row["case_id"] for batch in batches for row in batch] == subject.control.EXPECTED_CASES


def test_each_request_keeps_model_specific_json_design():
    body = subject.json_mode.request(subject.sol.packets()[:5], "content")
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 1.0
    assert body["top_p"] == 1.0
    assert body["provider"]["only"] == ["OpenInference"]
