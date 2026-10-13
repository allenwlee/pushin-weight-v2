import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "build_review", Path(__file__).with_name("build_review.py")
)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def artifacts():
    wire = {
        "model": "gpt-6-sol", "reasoning_effort": "medium",
        "messages": [{"role": "system", "content": "Locked opening plus all rules"},
                     {"role": "user", "content": "Sources and historical context"}],
    }
    request_hash = hashlib.sha256(json.dumps(wire, ensure_ascii=False).encode()).hexdigest()
    fixture = {
        "revision": "candidate", "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-6-sol", "reasoning_effort": "medium", "service_tier": "default",
        "max_completion_tokens": 4096, "timeout_seconds": 90, "request_hash": request_hash,
        "original_producing_call": 7, "negative_controls": {"changed_context": "rejected"},
        "snapshot": {"wire_request": wire, "source_packet": {"posts": [], "context": []}},
    }
    original = {"call": 7, "copy": {"headline": "Original"}, "url": "https://example.com/story",
                "diagnostics": {"elapsed_seconds": 1}}
    replay = {key: fixture[key] for key in (
        "revision", "endpoint", "model", "reasoning_effort", "service_tier",
        "max_completion_tokens", "timeout_seconds", "request_hash",
    )}
    replay.update(status="replay_passed", complete_request_equal=True,
                  returned_model="gpt-6-sol", assessment=8, copy={"headline": "Replay"},
                  test_producing_call=9, diagnostics={"elapsed_seconds": 1},
                  charged_or_reserved_usd="0.01")
    return fixture, original, replay


def test_review_refuses_changed_wire_even_with_the_same_locked_opening():
    fixture, original, replay = artifacts()
    fixture["snapshot"]["wire_request"]["messages"][0]["content"] += " Extra rule."
    with pytest.raises(ValueError, match="production wire hash"):
        review.build_payload(fixture, original, [replay])


@pytest.mark.parametrize("field", ["revision", "endpoint", "reasoning_effort", "max_completion_tokens"])
def test_review_refuses_mislabeled_production_conditions(field):
    fixture, original, replay = artifacts()
    replay[field] = "changed"
    with pytest.raises(ValueError, match="conditions differ"):
        review.build_payload(fixture, original, [replay])


def test_append_preserves_previous_copy_and_selects_latest():
    fixture, original, first = artifacts()
    second = copy.deepcopy(first)
    second.update(assessment=10, test_producing_call=11, copy={"headline": "Newest"})
    payload = review.build_payload(fixture, original, [first, second])
    assert [run["copy"]["headline"] for run in payload["runs"]] == ["Original", "Replay", "Newest"]
    assert payload["defaultRun"] == "replay-10"
    with pytest.raises(ValueError, match="duplicate"):
        review.build_payload(fixture, original, [first, first])


def test_untrusted_copy_cannot_close_the_embedded_json_block():
    fixture, original, replay = artifacts()
    malicious = '</script><script>globalThis.sourceExecuted = true</script>'
    replay["copy"]["headline"] = malicious
    payload = review.build_payload(fixture, original, [replay])
    html = review.render_html(payload)
    embedded = re.search(r'id="replay-data">(.*?)</script>', html, re.DOTALL).group(1)
    assert "<script>" not in embedded
    assert json.loads(embedded)["runs"][1]["copy"]["headline"] == malicious


def scenario_artifacts():
    fixture, _, result = artifacts()
    fixture.update(case_id="wang", case_title="Wang", reconstruction={"cutoff": "historical"})
    result.update(status="scenario_passed", case_id="wang", published=0, test_text_publications=0,
                  snapshot=copy.deepcopy(fixture["snapshot"]))
    return fixture, result


@pytest.mark.parametrize("field,value", [
    ("case_id", "other-story"), ("returned_model", "other-model"),
    ("request_hash", "other-request"), ("test_text_publications", 1),
    ("snapshot", {"source_packet": {"posts": ["future-post"]}}),
])
def test_scenario_rejects_mixed_cases_models_requests_publication_and_packets(field, value):
    fixture, result = scenario_artifacts()
    result[field] = value
    with pytest.raises(ValueError):
        review.build_scenario_payload(fixture, result)


def test_database_scenario_does_not_label_old_cli_copy_as_identical_conditions():
    fixture, result = scenario_artifacts()
    baseline = {"label": "Earlier CLI example · different conditions", "copy": {"headline": "Old CLI"}}
    payload = review.build_scenario_payload(fixture, result, baseline)
    assert payload["kind"] == "database_scenario"
    assert payload["comparison"] == baseline
    assert len(payload["runs"]) == 1 and payload["runs"][0]["copy"] == result["copy"]


def test_availability_rejects_posts_fetched_after_cutoff_and_missing_rows(monkeypatch):
    from datetime import datetime

    # Importing the harness does not start Django or a provider client.
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    from database_scenario import validate_availability as verify
    cutoff = datetime.fromisoformat("2026-09-24T14:45:00+00:00")
    rows = [{"id": "anchor", "created_at": "2026-09-24T14:19:01+00:00",
             "fetched_at": "2026-09-24T14:31:16+00:00"}]
    verify(rows, ["anchor"], cutoff)
    late = copy.deepcopy(rows)
    late[0]["fetched_at"] = "2026-09-30T00:00:00+00:00"
    with pytest.raises(ValueError, match="availability"):
        verify(late, ["anchor"], cutoff)
    with pytest.raises(ValueError, match="availability"):
        verify([], ["anchor"], cutoff)


def test_one_line_variant_preserves_the_rest_of_the_request(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    from database_scenario import STYLE_LINE, add_style_line

    baseline = {"system": "Locked opening\nFull source-audit instructions",
                "user": "Exact frozen sources and schema", "images": ["https://example.com/image"]}
    untouched = copy.deepcopy(baseline)
    variant = add_style_line(baseline, "Locked opening")
    assert baseline == untouched
    assert variant["system"].replace("\n" + STYLE_LINE, "", 1) == baseline["system"]
    assert {k: v for k, v in variant.items() if k != "system"} == {
        k: v for k, v in baseline.items() if k != "system"
    }
    with pytest.raises(ValueError, match="opening"):
        add_style_line(baseline, "Other voice")


def test_attribution_relaxation_preserves_every_other_instruction_and_input(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    from repair_scenario import NEW_RULE, OLD_RULE, relax_attribution

    baseline = {"system": "Full rules. " + OLD_RULE + " All other factual safeguards.",
                "user": "Exact evidence and schema", "images": ["source-photo"]}
    untouched = copy.deepcopy(baseline)
    variant = relax_attribution(baseline)
    assert variant["system"].replace(NEW_RULE, OLD_RULE, 1) == baseline["system"]
    assert variant["user"] == baseline["user"] and variant["images"] == baseline["images"]
    assert baseline == untouched and "whenever omitting it would mislead" in variant["system"]
    with pytest.raises(ValueError, match="exactly one"):
        relax_attribution({"system": OLD_RULE + OLD_RULE})


def test_supplement_repair_preserves_original_post_and_rejects_false_source_links(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    from repair_scenario import repaired_packet

    packet = {"cutoff": "2026-09-24T14:45:00+00:00",
              "posts": [{"id": "anchor", "images": ["https://example.com/photo"]}],
              "context": [], "story_context": {"included_ids": [], "evidence_bytes": 100}}
    records = []
    for kind in ["reviewed_image_transcription", "official_identity_background"]:
        value = "Reviewed source text"
        records.append({"id": "supplement:" + kind, "platform": "supplemental_evidence",
                        "url": "https://example.com/photo", "created_at": "2025-06-12",
                        "original_text": value, "evidence_role": {
                            "kind": kind, "original_post_id": "anchor",
                            "text_sha256": hashlib.sha256(value.encode()).hexdigest()}})
    supplements = {"case_id": "wang", "records": records}
    before = copy.deepcopy(packet)
    repaired = repaired_packet(packet, supplements, "wang")
    assert packet == before and repaired["posts"] == packet["posts"]
    assert len(repaired["context"]) == 2 and repaired["story_context"]["supplemental_records"] == 2
    bad = copy.deepcopy(supplements)
    bad["records"][0]["url"] = "https://example.com/other-photo"
    with pytest.raises(ValueError, match="original source photo"):
        repaired_packet(packet, bad, "wang")
    bad = copy.deepcopy(supplements)
    bad["records"][0]["original_text"] = "Invented price"
    with pytest.raises(ValueError, match="text changed"):
        repaired_packet(packet, bad, "wang")
    bad = copy.deepcopy(supplements)
    bad["records"][1]["created_at"] = "2026-10-13"
    with pytest.raises(ValueError, match="published after"):
        repaired_packet(packet, bad, "wang")
    assert repaired_packet(packet, {"case_id": "mistral-first", "records": []}, "mistral-first") == packet


def test_repaired_packet_model_comparison_rejects_any_extra_prompt_or_context_change(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    from production_replay import encoded_wire
    from repair_scenario import assert_model_only_delta

    reference = {"model": "gpt-6.1-sol", "reasoning_effort": "high",
                 "messages": [{"role": "system", "content": "Exact relaxed-attribution prompt"},
                              {"role": "user", "content": "Exact repaired evidence"}],
                 "max_completion_tokens": 4096}
    sha = hashlib.sha256(encoded_wire(reference)).hexdigest()
    changed = copy.deepcopy(reference)
    changed.update(model="gpt-6-sol", reasoning_effort="medium")
    assert_model_only_delta(changed, sha)
    changed["messages"][1]["content"] += " Different evidence."
    with pytest.raises(ValueError, match="other settings changed"):
        assert_model_only_delta(changed, sha)
