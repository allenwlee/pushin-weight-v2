from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.u20_translation_synthesis_compare import (
    LANGS,
    TARGET_ENDPOINT,
    TARGET_MODEL,
    SYNTHESIS_MAX_OUTPUT_TOKENS,
    capture_requests,
    load_corpus,
    prepare,
)


def _synthetic_corpus(tmp_path: Path, monkeypatch) -> None:
    rows = []
    for language in LANGS:
        for index in range(15):
            rows.append({"example_id": f"{language}-{index:02d}", "source_language": language, "input": {"tweet_id": f"{language}-{index:02d}", "text": f"{language} source {index} https://example.test/{index}", "context": []}})
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps({"rows": rows}))
    import scripts.u20_translation_synthesis_compare as module
    monkeypatch.setattr(module, "CORPUS", path)


def test_prepare_selects_fifteen_source_rows_per_language(tmp_path, monkeypatch):
    _synthetic_corpus(tmp_path, monkeypatch)
    rows = load_corpus()
    assert len(rows) == 45
    assert {language: sum(row["source_language"] == language for row in rows) for language in LANGS} == {language: 15 for language in LANGS}
    assert len({row["post_id"] for row in rows}) == 45


def test_selection_includes_stored_context_in_caller_guard(tmp_path, monkeypatch):
    _synthetic_corpus(tmp_path, monkeypatch)
    path = tmp_path / "corpus.json"
    corpus = json.loads(path.read_text())
    corpus["rows"][0]["input"]["context"] = [
        {"provenance": "stored_quote", "text": "x" * 5000}
    ]
    path.write_text(json.dumps(corpus))
    with pytest.raises(ValueError, match="fewer than 15 en"):
        load_corpus()


def test_true_callers_capture_three_translation_and_forty_five_synthesis_requests(tmp_path, monkeypatch):
    _synthetic_corpus(tmp_path, monkeypatch)
    requests = capture_requests(load_corpus(), TARGET_MODEL)
    assert len(requests["translation"]) == 3
    assert len(requests["synthesis"]) == 45
    assert all(request["messages"][0]["content"].find("Translate each post literally") >= 0 for request in requests["translation"])
    assert all("Write a concise analyst synthesis" in request["messages"][0]["content"] for request in requests["synthesis"])
    assert all("classifier" not in request["messages"][0]["content"].lower() for request in requests["translation"] + requests["synthesis"])
    assert all(request["temperature"] == 1.0 and request["top_p"] == 1.0 and request["seed"] == 42 for request in requests["translation"] + requests["synthesis"])


def test_prepare_is_provider_free_and_freezes_route_and_cost(tmp_path: Path, monkeypatch):
    _synthetic_corpus(tmp_path, monkeypatch)
    output = tmp_path / "u20-run"
    contract = prepare(output)
    assert contract["no_database_writes"] is True
    assert contract["no_classifier_call"] is True
    assert contract["semantic_pass_claim"] is False
    assert contract["transport_not_authorized"] is True
    assert contract["semantic_evaluation_pending"] is True
    assert contract["models"]["0731"]["model"] == TARGET_MODEL
    assert contract["models"]["0731"]["endpoint"] == TARGET_ENDPOINT
    assert all(float(value["reserved_cost_usd"]) <= 0.50 for value in contract["bounds"].values())
    saved = json.loads((output / "requests.json").read_text())
    assert set(saved) == {"incumbent", "0731"}
    assert all(len(arms["translation"]) == 3 and len(arms["synthesis"]) == 45 for arms in saved.values())
    assert all(
        request["max_tokens"] == SYNTHESIS_MAX_OUTPUT_TOKENS
        for arms in saved.values() for request in arms["synthesis"]
    )


def test_prepare_refuses_overwrite_and_missing_capture(tmp_path: Path, monkeypatch):
    _synthetic_corpus(tmp_path, monkeypatch)
    output = tmp_path / "u20-run"
    prepare(output)
    import pytest
    with pytest.raises(ValueError, match="refusing to overwrite"):
        prepare(output)

    missing = tmp_path / "missing-run"
    import scripts.u20_translation_synthesis_compare as module
    original = module.capture_requests
    monkeypatch.setattr(module, "capture_requests", lambda rows, model: {"translation": [], "synthesis": []})
    with pytest.raises(ValueError, match="request count"):
        prepare(missing)
    monkeypatch.setattr(module, "capture_requests", original)

    expensive = tmp_path / "expensive-run"
    monkeypatch.setattr(module, "INPUT_PRICE", module.Decimal("1000000"))
    with pytest.raises(ValueError, match="exceeds hard cap"):
        prepare(expensive)
