"""Provider-free validation for the frozen Stage 1C assessment contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REQUIRED_STRATA = {"prevalence", "rare_positive", "event_opportunity_boundary"}
REQUIRED_ASSESSMENTS = {
    "classification",
    "job_discovery",
    "personnel_discovery",
    "job_extraction",
    "affiliation_extraction",
}
REQUIRED_SLICES = {
    "languages": {"en", "zh-cn", "ja"},
    "sources": {"official", "staff", "named_person", "third_party"},
    "personnel_statuses": {"current", "former", "future", "unknown"},
}
REQUIRED_METRICS = {
    "classification": {
        "per_type_precision",
        "per_type_recall",
        "prevalence_false_positive_rate",
    },
    "job_discovery": {"post_precision", "coverage_estimate"},
    "personnel_discovery": {"post_precision", "coverage_estimate"},
    "job_extraction": {
        "role_precision",
        "role_recall",
        "field_completeness",
        "provenance_retention",
    },
    "affiliation_extraction": {
        "claim_precision",
        "claim_recall",
        "status_accuracy",
        "date_non_fabrication",
    },
}
REQUIRED_COUNTING_UNITS = {
    "classification": "post_brand",
    "discovery": "source_post",
    "job_extraction": "listing_or_requisition",
    "affiliation_extraction": "person_brand_claim",
    "organizations": "review_candidate_or_known_brand",
}


def validate_stage1c_evaluation_contract(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "stage1c-evaluation-contract-v1":
        raise ValueError("unsupported Stage 1C evaluation schema")
    stratum_rows = value.get("classification_strata", [])
    if not isinstance(stratum_rows, list):
        raise TypeError("classification_strata must be an array")
    stratum_ids = [row.get("id") for row in stratum_rows if isinstance(row, dict)]
    strata = set(stratum_ids)
    floor_rows = value.get("assessment_floors", {})
    if not isinstance(floor_rows, dict):
        raise TypeError("assessment_floors must be an object")
    assessments = set(floor_rows)
    missing_strata = sorted(REQUIRED_STRATA - strata)
    missing_assessments = sorted(REQUIRED_ASSESSMENTS - assessments)
    support_gaps = []
    for index, row in enumerate(stratum_rows):
        if not isinstance(row, dict):
            support_gaps.append(f"row_{index}")
        elif (
            type(row.get("minimum_examples")) is not int
            or row["minimum_examples"] < 1
        ):
            support_gaps.append(str(row.get("id") or f"row_{index}"))
    support_gaps.sort()
    contract_errors: list[str] = []
    if value.get("contract_status") != "ready_for_measurement":
        contract_errors.append("contract_status")
    if len(stratum_ids) != len(strata):
        contract_errors.append("duplicate_classification_strata")
    slice_rows = value.get("required_slices", {})
    if not isinstance(slice_rows, dict):
        contract_errors.append("required_slices")
    else:
        for name, required in REQUIRED_SLICES.items():
            values = slice_rows.get(name)
            if not isinstance(values, list) or set(values) != required:
                contract_errors.append(f"required_slices.{name}")
    for assessment, required in REQUIRED_METRICS.items():
        row = floor_rows.get(assessment)
        if not isinstance(row, dict):
            continue
        metrics = row.get("metrics")
        if not isinstance(metrics, list) or set(metrics) != required:
            contract_errors.append(f"assessment_floors.{assessment}.metrics")
        if row.get("values") != "preregister_before_candidate_scoring":
            contract_errors.append(f"assessment_floors.{assessment}.values")
    if value.get("counting_units") != REQUIRED_COUNTING_UNITS:
        contract_errors.append("counting_units")
    if not isinstance(value.get("production_rule"), str) or not value[
        "production_rule"
    ].strip():
        contract_errors.append("production_rule")
    identity = hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        "identity": identity,
        "status": (
            "ready_for_measurement"
            if not (
                missing_strata
                or missing_assessments
                or support_gaps
                or contract_errors
            )
            else "blocked"
        ),
        "missing_strata": missing_strata,
        "missing_assessments": missing_assessments,
        "support_gaps": support_gaps,
        "contract_errors": sorted(contract_errors),
    }
