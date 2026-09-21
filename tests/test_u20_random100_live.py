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


def test_incumbent_route_keeps_content_prompts_and_caps_identical(tmp_path, monkeypatch):
    rows = [{"post_id": "1", "text": "a post", "source_language": "other", "context": []}]
    monkeypatch.setattr(harness, "_capture_synthesis", lambda rows, arm: ([{"model": harness.ARMS[arm]["model"], "max_tokens": 4000, "messages": [{"role": "user", "content": "synthesis"}]}], []))
    target = harness._capture_literal(rows, "0731")
    direct = harness._capture_literal(rows, "incumbent")
    assert len(target) == len(direct) == 3
    assert [request["messages"] for request in target] == [request["messages"] for request in direct]
    assert [request["max_tokens"] for request in target] == [request["max_tokens"] for request in direct]
    assert all({"temperature", "top_p", "seed"}.issubset(request) for request in target)
    assert all(not {"temperature", "top_p", "seed"}.intersection(request) for request in direct)
    assert harness.ARMS["incumbent"]["base_url"] == "https://api.deepseek.com/anthropic"
