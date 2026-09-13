from __future__ import annotations

import copy
import json

import pytest

from scripts.u18_runtime_pro_reviewer_pilot import (
    EXPECTED_CLASSIFICATION_FIELDS,
    PILOT_ID,
    PilotInputError,
    _build_rows,
    _classification,
    _packets,
    _review_batch,
    evaluate_owner_reference,
)

VALID_CLASSIFICATION = {
    "outcome": "classified",
    "post_types": ["events"],
    "product_labels": [],
    "sentiment": "neutral",
    "china_nationalism": "none",
    "us_nationalism": "none",
}


def _synthetic_inputs(tmp_path):
    source_rows = []
    manifest_rows = []
    candidate_rows = []
    reference_rows = []
    for index, language in enumerate(("en", "ja", "zh-cn") * 10):
        example_id = f"example-{index:02d}"
        brand_id = f"brand-{index:02d}"
        case_id = f"H{index:010d}"
        source_rows.append(
            {
                "example_id": example_id,
                "brand_id": brand_id,
                "source_language": language,
                "input_context_fingerprint": f"fingerprint-{index}",
                "input": {"text": f"post {index}", "context": []},
            }
        )
        manifest_rows.append(
            {
                "case_id": case_id,
                "example_id": example_id,
                "brand_id": brand_id,
                "source_language": language,
                "selection_bucket": (
                    "stable_model_vs_gold" if index % 2 else "model_run_conflict"
                ),
            }
        )
        candidate_rows.append(
            {
                "example_id": example_id,
                "brand_id": brand_id,
                "classification": VALID_CLASSIFICATION,
            }
        )
        reference_rows.append(
            {
                "example_id": example_id,
                "brand_id": brand_id,
                "classification": VALID_CLASSIFICATION,
            }
        )
    source = tmp_path / "source.json"
    manifest = tmp_path / "manifest.json"
    candidate = tmp_path / "candidate.json"
    reference = tmp_path / "reference.json"
    source.write_text(json.dumps({"rows": source_rows}), encoding="utf-8")
    manifest.write_text(json.dumps({"rows": manifest_rows}), encoding="utf-8")
    candidate.write_text(json.dumps({"rows": candidate_rows}), encoding="utf-8")
    reference.write_text(
        json.dumps(
            {
                "status": "owner_accepted_unblinded",
                "human_grounded": False,
                "rows": reference_rows,
            }
        ),
        encoding="utf-8",
    )
    return source, manifest, candidate, reference


def test_locked_cohort_has_only_deterministic_hard_cases_and_three_language_slices(tmp_path):
    source, manifest, candidate, reference = _synthetic_inputs(tmp_path)
    cohort, _ = _build_rows(
        source_path=source,
        manifest_path=manifest,
        candidate_path=candidate,
        reference_path=reference,
    )
    rows = cohort["rows"]

    assert cohort["cohort_id"] == PILOT_ID
    assert len(rows) == 30
    assert {row["source_language"] for row in rows} == {"en", "ja", "zh-cn"}
    assert all(
        row["primary"]["outcome"] in {"classified", "context_missing"}
        for row in rows
    )
    assert all(set(row["primary"]) == EXPECTED_CLASSIFICATION_FIELDS for row in rows)
    assert all("owner_override" not in row for row in rows)
    assert cohort["selection"]["controls_excluded"] is True


def test_classification_parser_accepts_inner_contract_and_rejects_envelope_fields():
    valid = VALID_CLASSIFICATION
    brand_id = "qwen"

    parsed = _classification(valid, brand_id)
    assert set(parsed) == EXPECTED_CLASSIFICATION_FIELDS

    with pytest.raises(PilotInputError, match="classification fields differ"):
        _classification({**valid, "brand_id": brand_id}, brand_id)


def test_provider_packet_does_not_include_owner_reference_fields():
    packet = _packets(
        [
            {
                "example_id": "example-1",
                "brand_id": "qwen",
                "source_language": "en",
                "input": {"text": "post", "context": []},
                "primary": VALID_CLASSIFICATION,
            }
        ]
    )[0]

    assert set(packet) == {
        "example_id",
        "brand_id",
        "source_language",
        "source",
        "primary",
    }
    assert "owner_override" not in json.dumps(packet)
    assert "reference" not in json.dumps(packet).lower()


def test_malformed_review_fails_closed_after_one_review_retry():
    class MalformedClient:
        def __init__(self):
            self.calls = 0

        def call(self, *_args, **_kwargs):
            self.calls += 1
            return {}

    client = MalformedClient()
    row = {
        "example_id": "example-1",
        "brand_id": "qwen",
        "source_language": "en",
        "input": {"text": "post", "context": []},
        "primary": VALID_CLASSIFICATION,
    }

    with pytest.raises(PilotInputError, match="failed closed"):
        _review_batch([row], client)  # type: ignore[arg-type]
    assert client.calls == 2


def test_owner_reference_evaluation_is_explicitly_diagnostic_and_nonhuman():
    reference = {
        "status": "owner_accepted_unblinded",
        "human_grounded": False,
        "rows": [
            {
                "example_id": f"example-{index:02d}",
                "brand_id": f"brand-{index:02d}",
                "source_language": ("en", "ja", "zh-cn")[index % 3],
                "classification": VALID_CLASSIFICATION,
            }
            for index in range(30)
        ],
    }
    candidate = {
        "provenance": {"kind": "candidate_output"},
        "rows": [
            {
                "example_id": row["example_id"],
                "brand_id": row["brand_id"],
                "classification": copy.deepcopy(row["classification"]),
            }
            for row in reference["rows"]
        ],
    }

    report = evaluate_owner_reference(
        candidate,
        reference,
        budget={"lane": "test"},
        budget_sha256="budget-sha-for-test",
    )

    assert report["status"] == "ok"
    assert report["assessment"]["status"] == "owner_override_diagnostic"
    assert report["assessment"]["human_gold"] is False
    assert report["assessment"]["release_quality_claim_authorized"] is False
    assert report["provenance"]["budget_sha256"] == "budget-sha-for-test"
    assert report["summary"]["rows"] == 30
    assert report["summary"]["post_type_exact"] == 1
    assert report["summary"]["product_label_exact"] == 1
