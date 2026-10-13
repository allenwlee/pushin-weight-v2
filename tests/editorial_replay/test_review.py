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
