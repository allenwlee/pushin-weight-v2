from __future__ import annotations

import copy
import hashlib
import json

import pytest

from core.classification_contract import (
    STAGE1_TAXONOMY_V3_POST_TYPE_KEYS as CANONICAL_POST_TYPE_KEYS,
    STAGE1_TAXONOMY_V3_PRODUCT_LABEL_KEYS as PRODUCT_LABEL_KEYS,
)
from scripts.u18_runtime_pro_reviewer_pilot import (
    EXPECTED_CLASSIFICATION_FIELDS,
    PILOT_ID,
    PilotInputError,
    _build_rows,
    _classification,
    _packets,
    _review_batch,
    evaluate_owner_reference,
    replay_saved_responses,
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


def test_saved_response_replay_reuses_one_quote_for_multiple_changes_without_transport(
    tmp_path, monkeypatch
):
    """The recovery path never constructs a client or changes saved responses."""
    import scripts.u18_runtime_pro_reviewer_pilot as pilot

    source, manifest, candidate, reference = _synthetic_inputs(tmp_path)
    cohort, reference_subset = _build_rows(
        source_path=source,
        manifest_path=manifest,
        candidate_path=candidate,
        reference_path=reference,
    )
    cohort_path = tmp_path / "cohort.json"
    reference_subset_path = tmp_path / "reference-subset.json"
    cohort_path.write_text(json.dumps(cohort), encoding="utf-8")
    reference_subset_path.write_text(json.dumps(reference_subset), encoding="utf-8")
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir()
    response_specs = []
    for start in range(0, len(cohort["rows"]), 5):
        batch = cohort["rows"][start : start + 5]
        request_id = f"review-{batch[0]['example_id']}-{batch[-1]['example_id']}"
        results = []
        for row in batch:
            classification = copy.deepcopy(row["primary"])
            decision = "accept"
            change_reasons = []
            evidence = []
            if row["example_id"] == "example-00":
                classification["post_types"] = ["job_listings"]
                decision = "replace"
                change_reasons = [
                    "missing_post_type",
                    "unsupported_post_type",
                ]
                evidence = [
                    {"source": "source", "context_index": None, "quote": "post 0"}
                ]
            results.append(
                {
                    "example_id": row["example_id"],
                    "brand_id": row["brand_id"],
                    "decision": decision,
                    "classification": classification,
                    "post_type_verdicts": {
                        key: key in classification["post_types"]
                        for key in CANONICAL_POST_TYPE_KEYS
                    },
                    "product_label_verdicts": {
                        key: key in classification["product_labels"]
                        for key in PRODUCT_LABEL_KEYS
                    },
                    "change_reasons": change_reasons,
                    "evidence": evidence,
                }
            )
        response_path = responses_dir / f"{request_id}.json"
        response_path.write_text(json.dumps({"results": results}), encoding="utf-8")
        response_specs.append(
            {
                "request_id": request_id,
                "path": str(response_path.relative_to(tmp_path)),
                "sha256": hashlib.sha256(response_path.read_bytes()).hexdigest(),
            }
        )
    usage_path = tmp_path / "usage.json"
    usage_path.write_text(json.dumps({"transport_attempts": 7}), encoding="utf-8")
    budget_path = tmp_path / "replay-budget.json"
    budget_path.write_text(
        json.dumps(
            {
                "schema_version": "u18-saved-response-replay/v1",
                "frozen_at": "2026-09-13T23:20:00+09:00",
                "selector_version": pilot._PRAGMATICS_COMPLETENESS_SELECTOR_VERSION,
                "prompt_sha256": pilot.PROMPT_SHA256,
                "transport": {
                    "maximum_cost_usd": "0",
                    "maximum_input_tokens": 0,
                    "maximum_output_tokens": 0,
                    "maximum_requests": 0,
                    "maximum_transport_attempts": 0,
                },
                "inputs": {
                    "cohort_sha256": hashlib.sha256(cohort_path.read_bytes()).hexdigest(),
                    "owner_reference_subset_sha256": hashlib.sha256(
                        reference_subset_path.read_bytes()
                    ).hexdigest(),
                    "original_usage_path": "usage.json",
                    "original_usage_sha256": hashlib.sha256(usage_path.read_bytes()).hexdigest(),
                },
                "responses": response_specs,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pilot, "ROOT", tmp_path)

    class NoTransport:
        def __init__(self, **_kwargs):
            raise AssertionError("saved-response replay must not construct transport")

    monkeypatch.setattr(pilot, "BudgetedPilotClient", NoTransport)
    output_path = tmp_path / "candidate.json"
    evaluation_path = tmp_path / "evaluation.json"
    report = replay_saved_responses(
        replay_budget_path=budget_path,
        cohort_path=cohort_path,
        reference_path=reference_subset_path,
        output_path=output_path,
        diagnostic_path=evaluation_path,
    )

    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["summary"]["transport_attempts"] == 0
    assert output["provenance"]["transport_attempts"] == 0
    assert output["provenance"]["generated_at"] == "2026-09-13T23:20:00+09:00"
    assert output["rows"][0]["review"]["change_reasons"] == [
        "missing_post_type",
        "unsupported_post_type",
    ]
    assert len(output["rows"][0]["review"]["evidence"]) == 1
