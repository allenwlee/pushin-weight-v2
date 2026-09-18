from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import u20_random100_live as harness


def _selection(path: Path) -> None:
    rows = [
        {
            "post_id": str(index), "text": "post " + str(index),
            "declared_language": "en" if index else "fr",
            "stored_detected_language": "other" if index == 0 else "en",
            "created_at": "2026-09-17T00:00:00+00:00", "fetched_at": "2026-09-17T00:00:00+00:00",
            "quoted_text": None, "parent_text": None,
        }
        for index in range(100)
    ]
    path.write_text(json.dumps({"selected_count": 100, "transaction_read_only": "on", "rows": rows}))


def test_freeze_preserves_cycle_language_precedence_and_all_rows(tmp_path):
    selection, rubric, output = tmp_path / "selection.json", tmp_path / "rubric.txt", tmp_path / "input.json"
    _selection(selection); rubric.write_text("rubric")
    frozen = harness.freeze_input(selection, output, rubric)
    assert len(frozen["rows"]) == 100
    assert frozen["rows"][0]["source_language"] == "other"
    assert frozen["unknown_language_policy"].startswith("Pass source_language")
    assert (tmp_path / "review-rubric.txt").read_text() == "rubric"


def test_prepare_rejects_more_than_five_hundred_transports(tmp_path, monkeypatch):
    selection, rubric, input_path = tmp_path / "selection.json", tmp_path / "rubric.txt", tmp_path / "input.json"
    _selection(selection); rubric.write_text("rubric")
    harness.freeze_input(selection, input_path, rubric)
    monkeypatch.setattr(harness, "_capture_literal", lambda rows, arm: [{"max_tokens": 1}] * 501)
    monkeypatch.setattr(harness, "_capture_synthesis", lambda rows, arm: ([], []))
    with pytest.raises(ValueError, match="maximum transport"):
        harness.prepare(input_path, tmp_path / "prepared")


def test_incumbent_capture_routes_direct_without_sampler_fields():
    client = harness.CaptureJSONClient("incumbent")
    client.messages_create(model="deepseek-v4-flash", messages=[])
    assert client.requests == [{"model": "deepseek-v4-flash", "messages": []}]
    assert harness.CaptureTextClient("incumbent").request_profile is None
    assert harness.ARM_ROUTES["incumbent"]["base_url"] == "https://api.deepseek.com/anthropic"


def test_incumbent_transport_does_not_apply_0731_sampler(tmp_path):
    request = {"model": "deepseek-v4-flash", "messages": []}
    transport = harness.executor.FrozenTransport(object(), "incumbent", "commentary", [request], tmp_path / "responses", tmp_path / "ledger.json", {"calls": 1, "input_bytes": 9999, "output_tokens": 1, "dollars": "1"})
    assert transport._canonical(request) == request
