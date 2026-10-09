"""Frozen wire comparison; no provider calls or claim of live semantic quality."""

import hashlib
import json
from pathlib import Path

import pytest

from monitor.editorial.config import load_editorial_config
from monitor.editorial.contracts import Event
from monitor.editorial.grounding import GROUNDING_INSTRUCTIONS
from monitor.editorial.providers import request_payload
from monitor.editorial.voices import load_voice
from monitor.editorial.writing import editor_request, writer_request

FIXTURE = json.loads(
    Path("tests/fixtures/original_content_workflow_acceptance.json").read_text()
)


@pytest.mark.parametrize(
    "case", FIXTURE["cases"], ids=lambda c: f"{c['track']}:{c['locale']}"
)
def test_frozen_wire_savings_preserve_schema_sources_and_grounding(case):
    packet = json.loads(Path("tests/fixtures/" + FIXTURE["source_fixture"]).read_text())
    packet.pop("provenance")
    cfg = load_editorial_config(Path("config/editorial-english-launch.yaml"))
    event = Event.model_validate(FIXTURE["event"])
    if case["track"] == "editor":
        request = editor_request(packet, cfg)
    else:
        voice = load_voice(f"{case['track']}-en-v1").model_copy(
            update={"locale": case["locale"]}
        )
        request = writer_request(event, packet, voice, cfg)
    wire = request_payload(cfg.routes[case["track"]], request)
    encoded = json.dumps(wire, ensure_ascii=False).encode()
    assert request["source_ids"] == case["source_ids"]
    assert (
        hashlib.sha256(
            json.dumps(request["response_schema"], sort_keys=True).encode()
        ).hexdigest()
        == case["schema_sha256"]
    )
    assert GROUNDING_INSTRUCTIONS in request["system"]
    payload = json.loads(request["user"])
    assert "rule" not in payload["source_provenance"]
    assert payload["source_provenance"]["independent_confirmation"] == "not_assessed"
    assert len(encoded) < case["baseline_bytes"]
    # Restore just the redundant rule: every other wire field must match baseline.
    payload["source_provenance"]["rule"] = FIXTURE["baseline_provenance_rule"]
    request["user"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    baseline = json.dumps(
        request_payload(cfg.routes[case["track"]], request), ensure_ascii=False
    ).encode()
    assert len(baseline) == case["baseline_bytes"]
    assert hashlib.sha256(baseline).hexdigest() == case["baseline_sha256"]
