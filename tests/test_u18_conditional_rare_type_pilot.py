import copy
import json

import pytest

from scripts import u18_conditional_rare_type_pilot as pilot
from x_monitor.provider_telemetry import ProviderResponse


def packet(text, key="1", language="en"):
    return {"tweet_id": key, "text": text, "context": [], "brand_ids": ["qwen"], "affiliations": [], "source_language": language}


def baseline_row(source, types=None, outcome="classified"):
    return {"row_key": pilot._two_role_fingerprint(source), "target_brand": "qwen", "post_types": types or ["opinions_reactions"], "outcome": outcome, "product_labels": ["testimonial"], "sentiment": "positive", "china_nationalism": "none", "us_nationalism": "none"}


def baseline(*rows):
    return {"batches": [{"batch_index": 0, "batch_size": len(rows), "merged": list(rows), "failed_row_keys": []}]}


def response_for(rows, labels=()):
    return {"rows": [{"row_key": r["row_key"], "target_brand": r["target_brand"], "decisions": {label: {"applies": label in labels, "evidence": r["text"] if label in labels else None} for label in pilot.RARE_TYPES}} for r in rows]}


@pytest.mark.parametrize("text", ["Yesterday's hackathon was fun", "求人に応募しました", "报名参加这个比赛", "I left Qwen last month", "closed beta access"])
def test_text_can_route_omitted_secondary_types(text):
    source = packet(text)
    assert pilot.routing_reasons(source, baseline_row(source))


def test_context_is_screened_but_role_does_not_auto_classify():
    source = packet("Amazing work")
    source["affiliations"] = [{"brand_id": "qwen", "role": "official", "reviewed": True}]
    assert pilot.routing_reasons(source, baseline_row(source)) == []
    source["context"] = [{"kind": "stored_quote", "text": "Register for our meetup"}]
    assert pilot.routing_reasons(source, baseline_row(source))
    assert pilot.routing_reasons(source, baseline_row(source, outcome="context_missing")) == []


def test_multiple_secondary_types_require_separate_evidence_and_preserve_other_axes():
    source = packet("We won a prize at Qwen's hackathon")
    base = baseline(baseline_row(source))
    schedule, _ = pilot.build_schedule([source], base)
    parsed = pilot.validate_decisions(response_for(schedule[0]["rows"], ("events", "opportunities")), schedule[0]["rows"])
    merged = pilot.merge_additions(base, parsed)
    before, after = base["batches"][0]["merged"][0], merged["batches"][0]["merged"][0]
    assert set(after["post_types"]) == {"events", "opportunities", "opinions_reactions"}
    assert {k: v for k, v in before.items() if k != "post_types"} == {k: v for k, v in after.items() if k != "post_types"}
    assert before["post_types"] == ["opinions_reactions"]


@pytest.mark.parametrize("defect", ["missing_row", "duplicate_row", "wrong_brand", "missing_axis", "string_boolean", "invented_evidence", "extra_axis"])
def test_malformed_conditional_response_cannot_change_base(defect):
    source = packet("Qwen meetup")
    schedule, _ = pilot.build_schedule([source], baseline(baseline_row(source)))
    rows = schedule[0]["rows"]
    answer = response_for(rows, ("events",))
    row = answer["rows"][0]
    if defect == "missing_row":
        answer["rows"] = []
    elif defect == "duplicate_row":
        answer["rows"].append(copy.deepcopy(row))
    elif defect == "wrong_brand":
        row["target_brand"] = "minimax"
    elif defect == "missing_axis":
        del row["decisions"]["personnel_changes"]
    elif defect == "string_boolean":
        row["decisions"]["events"]["applies"] = "true"
    elif defect == "invented_evidence":
        row["decisions"]["events"]["evidence"] = "an invented event"
    else:
        row["decisions"]["sentiment"] = {"applies": True, "evidence": "Qwen"}
    with pytest.raises(ValueError):
        pilot.validate_decisions(answer, rows)


def test_conditional_caller_sends_only_selected_rows_and_cannot_repeat_run(tmp_path, monkeypatch):
    yes, no = packet("Attend Qwen meetup", "1"), packet("Qwen seems good", "2")
    base = baseline(baseline_row(yes), baseline_row(no))
    schedule, routing = pilot.build_schedule([yes, no], base)
    assert [r["selected"] for r in routing] == [True, False]
    contract_path = tmp_path / "contract.json"
    contract_path.write_text("{}")
    monkeypatch.setattr(pilot, "load_frozen", lambda p: ({}, base, schedule, {}))
    calls = []

    class Client:
        def messages_create(self, **kwargs):
            calls.append(kwargs)
            rows = json.loads(kwargs["messages"][0]["content"])["rows"]
            return ProviderResponse(response_for(rows, ("events",)), usage={"input_tokens": 100, "cache_read_input_tokens": 30, "output_tokens": 100, "provider": "deepseek", "model": "deepseek-flash", "provider_request_id": "test-123", "selected_endpoint": "deepseek"})

    private = tmp_path / "private"
    pilot.run(contract_path, private, lambda candidate: Client())
    assert len(calls) == 1  # No base role calls, retries, or per-post fallbacks.
    assert calls[0]["model"] == "deepseek-v4-flash"
    assert calls[0]["thinking"] == {"type": "disabled"}
    assert calls[0]["max_tokens"] == 6000
    rows = json.loads(calls[0]["messages"][0]["content"])["rows"]
    assert len(rows) == 1 and rows[0]["text"] == yes["text"]
    assert set(rows[0]) == {"row_key", "target_brand", "text", "context", "affiliations", "source_language", "previous_post_types"}
    saved = json.loads((private / "result.json").read_text())
    assert "events" in saved["merged"]["batches"][0]["merged"][0]["post_types"]
    assert saved["merged"]["batches"][0]["merged"][1] == base["batches"][0]["merged"][1]
    with pytest.raises(FileExistsError):
        pilot.run(contract_path, private, lambda c: pytest.fail("must refuse before client creation"))
    assert len(calls) == 1


def test_failed_transport_is_terminal_and_preserves_baseline(tmp_path, monkeypatch):
    source = packet("Qwen meetup")
    base = baseline(baseline_row(source))
    schedule, _ = pilot.build_schedule([source], base)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text("{}")
    monkeypatch.setattr(pilot, "load_frozen", lambda p: ({}, base, schedule, {}))
    calls = []

    class Client:
        def messages_create(self, **kwargs):
            calls.append(kwargs)
            raise TimeoutError("uncertain billable request")

    private = tmp_path / "private"
    result = pilot.run(contract_path, private, lambda c: Client())
    assert result == {"calls": 1, "valid_rows": 0, "statuses": ["failed"]}
    assert len(calls) == 1
    assert json.loads((private / "result.json").read_text())["merged"] == base


def test_changed_frozen_source_refused_before_any_client(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text("old")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps({"source_receipts": {"baseline": {"path": "source.json", "sha256": pilot.file_hash(source)}}}))
    source.write_text("changed")
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="frozen source changed"):
        pilot.run(contract_path, tmp_path / "private", lambda c: pytest.fail("client must not be constructed"))
    assert not (tmp_path / "private").exists()
