"""File-only management command coverage for classification evaluation."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from django.db import connection

from core.management.commands.evaluate_classifications import Command

FIXTURE_PATH = Path("tests/fixtures/classification_evaluation_v1.json")


def _artifact_paths(tmp_path: Path) -> tuple[Path, Path]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["provenance"]["kind"] == "synthetic"
    assert fixture["provenance"]["gold"] is False

    candidate = {
        "schema_version": 1,
        "provenance": fixture["candidate_provenance"],
        "rows": [
            {
                **{
                    key: case[key]
                    for key in (
                        "example_id",
                        "brand_id",
                        "source_language",
                        "context_provenance",
                        "input_context_fingerprint",
                    )
                },
                "classification": case["candidate"],
            }
            for case in fixture["cases"]
        ],
    }
    gold = {
        "schema_version": 1,
        "provenance": fixture["gold_provenance"],
        "rows": [
            {
                **{
                    key: case[key]
                    for key in (
                        "example_id",
                        "brand_id",
                        "source_language",
                        "context_provenance",
                        "input_context_fingerprint",
                    )
                },
                "classification": case["gold"],
            }
            for case in fixture["cases"]
        ],
    }
    candidate_path = tmp_path / "candidate.json"
    gold_path = tmp_path / "gold.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    return candidate_path, gold_path


def test_command_writes_repeatable_result_without_database_queries(
    tmp_path, monkeypatch
):
    candidate_path, gold_path = _artifact_paths(tmp_path)
    output_path = tmp_path / "result.json"
    stdout = StringIO()

    def fail_if_database_is_opened(*_args, **_kwargs):
        raise AssertionError("classification evaluator must not open the database")

    monkeypatch.setattr(connection, "cursor", fail_if_database_is_opened)
    Command(stdout=stdout).handle(
        candidate=candidate_path,
        gold=gold_path,
        policy=None,
        output=output_path,
    )

    result = json.loads(output_path.read_text(encoding="utf-8"))
    response = json.loads(stdout.getvalue())
    assert result["status"] == "ok"
    assert result["assessment"] == {"status": "unassessed", "reason": "no_policy"}
    assert response == {
        "assessment": "unassessed",
        "evaluation_identity": result["identity"]["evaluation_identity"],
        "output": str(output_path),
        "status": "ok",
    }
    first_bytes = output_path.read_bytes()

    Command(stdout=StringIO()).handle(
        candidate=candidate_path,
        gold=gold_path,
        policy=None,
        output=output_path,
    )
    assert output_path.read_bytes() == first_bytes


def test_command_prints_result_when_output_path_is_omitted(tmp_path):
    candidate_path, gold_path = _artifact_paths(tmp_path)
    stdout = StringIO()

    Command(stdout=stdout).handle(
        candidate=candidate_path,
        gold=gold_path,
        policy=None,
        output=None,
    )

    assert json.loads(stdout.getvalue())["coverage"]["scored_pairs"] == 3


def test_command_rejects_non_gold_truth_without_partial_output(tmp_path):
    candidate_path, gold_path = _artifact_paths(tmp_path)
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    gold["provenance"]["kind"] = "synthetic"
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    stdout = StringIO()
    stderr = StringIO()

    with pytest.raises(SystemExit) as caught:
        Command(stdout=stdout, stderr=stderr).handle(
            candidate=candidate_path,
            gold=gold_path,
            policy=None,
            output=tmp_path / "must-not-exist.json",
        )

    assert caught.value.code == 2
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue())["error"]["code"] == "provenance_invalid"
    assert not (tmp_path / "must-not-exist.json").exists()


def test_command_parser_errors_are_structured_json(capsys):
    parser = Command().create_parser("manage.py", "evaluate_classifications")

    with pytest.raises(SystemExit) as caught:
        parser.parse_args(["--candidate", "candidate.json"])

    assert caught.value.code == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "error"
    assert error["error"]["code"] == "invalid_arguments"


def test_command_rejects_invalid_utf8_as_structured_error(tmp_path):
    candidate_path, gold_path = _artifact_paths(tmp_path)
    candidate_path.write_bytes(b"\xff")
    stderr = StringIO()

    with pytest.raises(SystemExit) as caught:
        Command(stdout=StringIO(), stderr=stderr).handle(
            candidate=candidate_path,
            gold=gold_path,
            policy=None,
            output=None,
        )

    assert caught.value.code == 2
    assert json.loads(stderr.getvalue())["error"]["code"] == "artifact_unreadable"
