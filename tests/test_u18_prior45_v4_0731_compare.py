import json

from scripts import u18_prior45_v4_0731_compare as subject


def test_original_45_preserve_order_and_production_batches():
    rows = subject.packets()
    manifest = json.loads(subject.MANIFEST_SOURCE.read_text())["rows"]
    assert [len(batch) for batch in subject.batches(rows)] == [20, 20, 5]
    assert [row["case_id"] for row in rows] == [row["case_id"] for row in manifest]


def test_model_request_uses_fixed_slots_and_pinned_deepinfra_without_reasoning():
    body = subject.request(subject.packets()[:2], "content")
    assert body["provider"]["only"] == ["DeepInfra"]
    assert body["provider"]["allow_fallbacks"] is False
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    assert body["temperature"] == 1.0
    assert body["top_p"] == 1.0
    assert body["seed"] == 42
    assert "response_format" not in body
    assert '"P01"' in body["messages"][1]["content"]
    assert '"D01"' in body["messages"][1]["content"]


def test_label_metric_counts_secondary_labels():
    expected = [{"case_id": "H1", "classification": {"post_types": ["events", "opportunities"]}}]
    actual = {"H1": {"post_types": ["events"]}}
    metric = subject._label_metrics(expected, actual, "post_types")
    assert metric["tp"] == 1
    assert metric["fn"] == 1
    assert metric["recall"] == 0.5
