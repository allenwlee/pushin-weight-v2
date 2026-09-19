"""Provider-free contract tests for Stage 1C preproduction assessments."""

from __future__ import annotations

import json
from pathlib import Path

from core.stage1c_evaluation import validate_stage1c_evaluation_contract

FIXTURE = Path(__file__).parent / "fixtures" / "stage1c_evaluation_contract_v1.json"


def test_stage1c_contract_is_complete_and_deterministic():
    first = validate_stage1c_evaluation_contract(FIXTURE)
    second = validate_stage1c_evaluation_contract(FIXTURE)

    assert first == second
    assert first["status"] == "ready_for_measurement"
    assert first["missing_strata"] == []
    assert first["missing_assessments"] == []
    assert first["support_gaps"] == []
    assert first["contract_errors"] == []
    assert len(first["identity"]) == 64


def test_missing_support_blocks_preproduction_measurement(tmp_path):
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["classification_strata"][1]["minimum_examples"] = 0
    path = tmp_path / "blocked.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    result = validate_stage1c_evaluation_contract(path)

    assert result["status"] == "blocked"
    assert result["support_gaps"] == ["rare_positive"]


def test_missing_language_and_floor_metric_block_contract(tmp_path):
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["required_slices"]["languages"].remove("ja")
    value["assessment_floors"]["job_extraction"]["metrics"].remove(
        "provenance_retention"
    )
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    result = validate_stage1c_evaluation_contract(path)

    assert result["status"] == "blocked"
    assert result["contract_errors"] == [
        "assessment_floors.job_extraction.metrics",
        "required_slices.languages",
    ]
