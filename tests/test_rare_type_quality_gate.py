from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from x_monitor.config import load_config
from x_monitor.jev_decisions import (
    QUESTION_SET,
    encode_request_payload,
    public_post_state,
)
from x_monitor.rare_type_extra_search import QUERY_VERSION, planned_query_string

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/rare_type_extra_search/gate_cases.json"
TYPES = {
    "personnel_changes",
    "job_listings",
    "events",
    "opportunities",
    "model_releases",
}


def _corpus() -> dict:
    return json.loads(FIXTURE.read_text())


def _cfg():
    return load_config(REPO / "config.yaml").discovery.rare_types.jev


def _identity() -> dict:
    from x_monitor.rare_type_quality_gate import assessment_identity

    return assessment_identity(
        query_version=QUERY_VERSION,
        planner_query=planned_query_string(),
        config=_cfg(),
        fixture_path=FIXTURE,
    )


def _probabilities(*types: str, junk: str | None = None) -> dict[str, float]:
    values = {question: 0.1 for question in QUESTION_SET}
    values["ai_related"] = 0.9 if types else 0.1
    if "personnel_changes" in types:
        values.update(person_identity=0.9, role_change=0.9)
    if "job_listings" in types:
        values["role_opening"] = 0.9
    if "events" in types:
        values["attendance_event"] = 0.9
    if "opportunities" in types:
        values["bounded_opportunity"] = 0.9
    if "model_releases" in types:
        values.update(model_release=0.9, source_announcement=0.9)
    if junk:
        values[f"junk_{junk}"] = 0.9
    return values


def _predictions(
    *, evidence_kind: str = "captured_real", corpus: dict | None = None
) -> list[dict]:
    rows = []
    for case in (corpus or _corpus())["cases"]:
        reference = case["reference"]
        hard_negative = reference.get("hard_negative")
        junk = (
            hard_negative
            if hard_negative
            in {
                "mill",
                "lineup",
                "f1",
                "joke",
                "static_bio",
                "price_only",
                "conference_ad",
            }
            else None
        )
        rows.append(
            {
                "case_id": case["id"],
                "response_id": f"response-{case['id']}",
                "model": _cfg().model,
                "provider": _cfg().provider,
                "request_sha256": hashlib.sha256(
                    encode_request_payload(
                        public_post_state(case["public_payload"]), _cfg()
                    )
                ).hexdigest(),
                "probabilities": _probabilities(*reference["types"], junk=junk),
                "evidence_kind": evidence_kind,
                "usage": {
                    "cost_usd": "0.0001",
                    "input_tokens": 1000,
                    "output_tokens": 0,
                },
            }
        )
    return rows


def _live(*, overlap=2, independently_read_keepers=6, mill=2, recruiter=2):
    return {
        "cohorts": [
            {
                "cohort_id": "15m-primary",
                "window": "15m",
                "post_ids": [f"p{i}" for i in range(1, 11)],
                "independently_read_keepers": independently_read_keepers,
                "already_stored": overlap,
                "mill": mill,
                "recruiter": recruiter,
                "raw_paid_result_count": 10,
                "captured_assessable_count": 10,
                "estimated_credits": 150,
            },
            {
                "cohort_id": "7d-research",
                "window": "7d",
                "post_ids": [f"r{i}" for i in range(1, 11)],
                "independently_read_keepers": 6,
                "already_stored": 2,
                "mill": 2,
                "recruiter": 2,
                "raw_paid_result_count": 10,
                "captured_assessable_count": 10,
                "estimated_credits": 150,
            },
        ],
        "overlap_source": "production_read_only_exact_ids",
    }


def test_corpus_is_balanced_realistic_and_keeps_labels_out_of_provider_state():
    cases = _corpus()["cases"]
    assert len({case["id"] for case in cases}) == len(cases)
    assert {
        type_name for case in cases for type_name in case["reference"]["types"]
    } == TYPES
    assert any(case["reference"]["keep"] for case in cases)
    assert any(not case["reference"]["keep"] for case in cases)
    hard_negatives = {case["reference"].get("hard_negative") for case in cases}
    assert {
        "mill",
        "lineup",
        "f1",
        "joke",
        "static_bio",
        "recap",
        "price_only",
        "conference_ad",
    } <= hard_negatives
    encoded_states = json.dumps(
        [public_post_state(case["public_payload"]) for case in cases],
        ensure_ascii=False,
    )
    assert '"reference"' not in encoded_states
    assert '"provenance"' not in encoded_states
    assert '"synthetic_people"' not in encoded_states


def test_identity_freezes_exact_query_model_question_threshold_and_fixture_bytes():
    identity = _identity()
    cfg = _cfg()
    assert identity == {
        "query_version": QUERY_VERSION,
        "planner_query_sha256": hashlib.sha256(
            planned_query_string().encode()
        ).hexdigest(),
        "requested_model": cfg.model,
        "attested_model": cfg.model,
        "requested_provider": cfg.provider,
        "attested_provider": cfg.provider,
        "question_version": cfg.question_set_version,
        "question_content_sha256": cfg.question_content_sha256,
        "threshold_version": cfg.threshold_version,
        "threshold_values_sha256": cfg.threshold_values_sha256,
        "yes_threshold": "0.80",
        "no_threshold": "0.20",
        "role_opening_threshold": "0.30",
        "attendance_event_threshold": "0.50",
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "corpus_content_sha256": hashlib.sha256(
            json.dumps(
                _corpus(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
    }


def test_fixture_predictions_use_canonical_gate_and_report_confusion_and_per_type_metrics():
    from x_monitor.rare_type_quality_gate import evaluate_fixture_predictions

    result = evaluate_fixture_predictions(
        corpus=_corpus(), predictions=_predictions(), config=_cfg()
    )
    assert result["evidence_kind"] == "captured_real"
    assert result["keeper_confusion"]["false_positive"] == 0
    assert result["keeper_confusion"]["false_negative"] == 0
    assert result["keeper_precision"] == 1.0
    assert result["keeper_recall"] == 1.0
    assert set(result["per_type"]) == TYPES
    assert all(
        metrics["precision"] == metrics["recall"] == 1.0
        for metrics in result["per_type"].values()
    )
    assert result["multilabel"]["exact_match_ratio"] == 1.0


def test_duplicate_missing_extra_and_attestation_mismatches_fail_closed():
    from x_monitor.rare_type_quality_gate import (
        QualityEvidenceError,
        evaluate_fixture_predictions,
    )

    rows = _predictions()
    with pytest.raises(QualityEvidenceError, match="duplicate"):
        evaluate_fixture_predictions(
            corpus=_corpus(), predictions=rows + [rows[0]], config=_cfg()
        )
    with pytest.raises(QualityEvidenceError, match="missing"):
        evaluate_fixture_predictions(
            corpus=_corpus(), predictions=rows[:-1], config=_cfg()
        )
    extra = rows + [{**rows[0], "case_id": "not-in-corpus"}]
    with pytest.raises(QualityEvidenceError, match="unexpected"):
        evaluate_fixture_predictions(corpus=_corpus(), predictions=extra, config=_cfg())
    wrong_model = deepcopy(rows)
    wrong_model[0]["model"] = "alias-or-wrong-model"
    with pytest.raises(QualityEvidenceError, match="model"):
        evaluate_fixture_predictions(
            corpus=_corpus(), predictions=wrong_model, config=_cfg()
        )
    wrong_request = deepcopy(rows)
    wrong_request[0]["request_sha256"] = "0" * 64
    with pytest.raises(QualityEvidenceError, match="request hash"):
        evaluate_fixture_predictions(
            corpus=_corpus(), predictions=wrong_request, config=_cfg()
        )


def test_canonical_threshold_boundaries_are_inclusive_and_review_between():
    from x_monitor.rare_type_quality_gate import evaluate_fixture_predictions

    corpus = {"schema_version": "x", "cases": [deepcopy(_corpus()["cases"][0])]}
    row = _predictions()[0]
    row["probabilities"] = _probabilities("personnel_changes")
    row["probabilities"].update(ai_related=0.8, person_identity=0.8, role_change=0.8)
    assert (
        evaluate_fixture_predictions(corpus=corpus, predictions=[row], config=_cfg())[
            "rows"
        ][0]["outcome"]
        == "kept"
    )
    row["probabilities"]["role_change"] = 0.799
    assert (
        evaluate_fixture_predictions(corpus=corpus, predictions=[row], config=_cfg())[
            "rows"
        ][0]["outcome"]
        == "review_needed"
    )


def test_complete_assessment_passes_only_real_complete_evidence_and_has_stable_digest():
    from x_monitor.rare_type_quality_gate import complete_assessment

    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=_predictions(),
        config=_cfg(),
        live_evidence=_live(),
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert assessment["status"] == "pass"
    assert assessment["quality_gate_passed"] is True
    assert assessment["enablement_eligible"] is False
    assert assessment["enablement_approved"] is False
    assert [row["cohort_id"] for row in assessment["live_metrics_by_window"]] == [
        "15m-primary",
        "7d-research",
    ]
    assert assessment["live_metrics_by_window"][0][
        "keepers_per_estimated_credit"
    ] == pytest.approx(0.04)
    assert (
        assessment["assessment_digest"]
        == complete_assessment(
            identity=_identity(),
            corpus=_corpus(),
            predictions=_predictions(),
            config=_cfg(),
            live_evidence=_live(),
            budget={
                "reserved_usd": "0.25",
                "confirmed_usd": "0.0056",
                "usage_complete": True,
            },
        )["assessment_digest"]
    )


def test_complete_assessment_accepts_complete_direct_usage_with_unconfirmed_invoice():
    from x_monitor.rare_type_quality_gate import complete_assessment

    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=_predictions(),
        config=_cfg(),
        live_evidence=_live(),
        budget={
            "reserved_usd": "0.25",
            "estimated_usd_from_usage": "0.0056",
            "confirmed_usd": None,
            "usage_complete": True,
        },
    )
    assert assessment["status"] == "pass"
    assert assessment["budget"]["invoice_confirmed"] is False
    assert assessment["budget"]["estimated_usd_from_usage"] == "0.0056"


def test_direct_usage_missing_tokens_is_inconclusive_and_estimate_over_cap_fails():
    from x_monitor.rare_type_quality_gate import complete_assessment

    base = {
        "identity": _identity(),
        "corpus": _corpus(),
        "predictions": _predictions(),
        "config": _cfg(),
        "live_evidence": _live(),
    }
    missing = complete_assessment(
        **base,
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": None,
            "estimated_usd_from_usage": None,
            "usage_complete": False,
        },
    )
    assert missing["status"] == "inconclusive"
    assert "usage_unknown" in missing["reasons"]
    over = complete_assessment(
        **base,
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": None,
            "estimated_usd_from_usage": "0.251",
            "usage_complete": True,
        },
    )
    assert over["status"] == "fail"
    assert "assessment_budget_exceeded" in over["reasons"]


def test_legacy_confirmed_budget_schema_remains_supported():
    from x_monitor.rare_type_quality_gate import complete_assessment

    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=_predictions(),
        config=_cfg(),
        live_evidence=_live(),
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert assessment["status"] == "pass"
    assert assessment["budget"]["invoice_confirmed"] is True


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"predictions_kind": "mock"}, "mock_only_evidence"),
        ({"live": None}, "live_evidence_missing"),
        ({"live": _live(overlap=None)}, "overlap_unknown"),
        (
            {
                "live": {
                    "cohorts": [],
                    "overlap_source": "production_read_only_exact_ids",
                }
            },
            "live_evidence_empty",
        ),
        (
            {
                "budget": {
                    "reserved_usd": "0.251",
                    "confirmed_usd": None,
                    "usage_complete": False,
                }
            },
            "assessment_budget_exceeded",
        ),
        (
            {
                "budget": {
                    "reserved_usd": "0.25",
                    "confirmed_usd": None,
                    "usage_complete": False,
                }
            },
            "usage_unknown",
        ),
    ],
)
def test_complete_assessment_is_inconclusive_or_failed_when_enablement_evidence_is_absent(
    change, reason
):
    from x_monitor.rare_type_quality_gate import complete_assessment

    predictions = _predictions(
        evidence_kind="mock"
        if change.get("predictions_kind") == "mock"
        else "captured_real"
    )
    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=predictions,
        config=_cfg(),
        live_evidence=change.get("live", _live()),
        budget=change.get(
            "budget",
            {"reserved_usd": "0.25", "confirmed_usd": "0.0056", "usage_complete": True},
        ),
    )
    assert assessment["status"] in {"fail", "inconclusive"}
    assert assessment["enablement_approved"] is False
    assert reason in assessment["reasons"]


def test_hard_negative_false_keep_and_zero_denominators_fail_without_division_errors():
    from x_monitor.rare_type_quality_gate import (
        complete_assessment,
        evaluate_fixture_predictions,
    )

    corpus = {
        "schema_version": "x",
        "cases": [
            deepcopy(
                next(
                    c
                    for c in _corpus()["cases"]
                    if c["id"] == "neg_mill_india_whatsapp"
                )
            )
        ],
    }
    false_keep = deepcopy(
        next(
            row for row in _predictions() if row["case_id"] == corpus["cases"][0]["id"]
        )
    )
    false_keep["probabilities"] = _probabilities("job_listings")
    result = evaluate_fixture_predictions(
        corpus=corpus, predictions=[false_keep], config=_cfg()
    )
    assert result["hard_negative_false_keeps"] == [corpus["cases"][0]["id"]]
    assert result["keeper_precision"] == 0.0
    assert result["keeper_recall"] is None
    full_predictions = _predictions()
    full_predictions[
        next(
            i
            for i, row in enumerate(full_predictions)
            if row["case_id"] == false_keep["case_id"]
        )
    ] = false_keep
    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=full_predictions,
        config=_cfg(),
        live_evidence=_live(),
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert assessment["status"] == "fail"
    assert "hard_negative_false_keep" in assessment["reasons"]


def test_low_aggregate_quality_and_high_live_noise_are_reported_without_failing():
    from x_monitor.rare_type_quality_gate import (
        FUNCTIONAL_EXEMPLARS,
        complete_assessment,
    )

    predictions = _predictions()
    for row, case in zip(predictions, _corpus()["cases"], strict=True):
        if case["reference"]["keep"] and case["id"] not in FUNCTIONAL_EXEMPLARS:
            row["probabilities"] = _probabilities()
    for row, case in zip(predictions, _corpus()["cases"], strict=True):
        if (
            not case["reference"]["keep"]
            and case["reference"].get("hard_negative") is None
        ):
            row["probabilities"] = _probabilities("job_listings")
    live = _live(overlap=9, independently_read_keepers=1, mill=9, recruiter=9)
    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=predictions,
        config=_cfg(),
        live_evidence=live,
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert assessment["status"] == "pass"
    assert assessment["reasons"] == []
    assert assessment["fixture_metrics"]["keeper_precision"] < 0.9
    assert assessment["fixture_metrics"]["keeper_recall"] < 0.9
    assert assessment["live_metrics_by_window"][0]["keeper_yield"] == 0.1
    assert assessment["live_metrics_by_window"][0]["overlap_rate"] == 0.9
    assert assessment["live_metrics_by_window"][0]["mill_rate"] == 0.9
    assert assessment["live_metrics_by_window"][0]["recruiter_rate"] == 0.9


def test_each_named_functional_exemplar_must_route_as_expected():
    from x_monitor.rare_type_quality_gate import (
        FUNCTIONAL_EXEMPLARS,
        complete_assessment,
    )

    for case_id in FUNCTIONAL_EXEMPLARS:
        predictions = _predictions()
        next(row for row in predictions if row["case_id"] == case_id)[
            "probabilities"
        ] = _probabilities()
        assessment = complete_assessment(
            identity=_identity(),
            corpus=_corpus(),
            predictions=predictions,
            config=_cfg(),
            live_evidence=_live(),
            budget={
                "reserved_usd": "0.25",
                "confirmed_usd": "0.0056",
                "usage_complete": True,
            },
        )
        assert assessment["status"] == "fail"
        assert f"functional_exemplar_failed:{case_id}" in assessment["reasons"]


def test_complete_nonempty_live_evidence_has_no_minimum_sample_pass_bar():
    from x_monitor.rare_type_quality_gate import complete_assessment

    live = _live()
    live["cohorts"] = [live["cohorts"][0]]
    live["cohorts"][0].update(
        post_ids=["p1"],
        independently_read_keepers=0,
        already_stored=1,
        mill=1,
        recruiter=1,
        raw_paid_result_count=1,
        captured_assessable_count=1,
        estimated_credits=15,
    )
    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=_predictions(),
        config=_cfg(),
        live_evidence=live,
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert assessment["status"] == "pass"
    assert assessment["reasons"] == []


def test_functionally_complete_fixture_has_no_minimum_case_count_pass_bar():
    from x_monitor.rare_type_quality_gate import complete_assessment

    selected = []
    cases = _corpus()["cases"]
    for family in (
        "mill",
        "lineup",
        "f1",
        "joke",
        "static_bio",
        "recap",
        "price_only",
        "conference_ad",
    ):
        selected.append(
            next(
                case
                for case in cases
                if case["reference"].get("hard_negative") == family
            )
        )
    for type_name in TYPES:
        selected.append(
            next(case for case in cases if type_name in case["reference"]["types"])
        )
    for language in ("en", "zh", "ja"):
        selected.append(
            next(
                case
                for case in cases
                if "personnel_changes" in case["reference"]["types"]
                and case["public_payload"]["lang"].lower().startswith(language)
            )
        )
    corpus = {
        "schema_version": _corpus()["schema_version"],
        "cases": list({case["id"]: case for case in selected}.values()),
    }
    identity = deepcopy(_identity())
    identity["corpus_content_sha256"] = hashlib.sha256(
        json.dumps(
            corpus, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    assessment = complete_assessment(
        identity=identity,
        corpus=corpus,
        predictions=_predictions(corpus=corpus),
        config=_cfg(),
        live_evidence=_live(),
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert len(corpus["cases"]) < 25
    assert assessment["status"] == "pass"
    assert assessment["reasons"] == []


def test_missing_paid_rows_cannot_inflate_live_quality():
    from x_monitor.rare_type_quality_gate import complete_assessment

    live = _live()
    live["cohorts"][0]["raw_paid_result_count"] = 20
    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=_predictions(),
        config=_cfg(),
        live_evidence=live,
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert assessment["status"] == "inconclusive"
    assert "live_captured_rows_incomplete" in assessment["reasons"]


def test_large_research_window_cannot_replace_an_empty_primary_window():
    from x_monitor.rare_type_quality_gate import complete_assessment

    live = _live()
    live["cohorts"][0].update(
        post_ids=[],
        independently_read_keepers=0,
        already_stored=0,
        mill=0,
        recruiter=0,
        raw_paid_result_count=0,
        captured_assessable_count=0,
        estimated_credits=15,
    )
    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=_predictions(),
        config=_cfg(),
        live_evidence=live,
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert assessment["status"] == "inconclusive"
    assert "live_cohort_empty:15m-primary" in assessment["reasons"]
    assert assessment["live_metrics_by_window"][0]["keeper_yield"] is None


def test_validate_assessment_rejects_identity_drift_and_tampering():
    from x_monitor.rare_type_quality_gate import (
        QualityEvidenceError,
        complete_assessment,
        validate_assessment,
    )

    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=_predictions(),
        config=_cfg(),
        live_evidence=_live(),
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert validate_assessment(assessment, expected_identity=_identity()) is True
    changed_identity = {**_identity(), "query_version": "changed"}
    with pytest.raises(QualityEvidenceError, match="identity"):
        validate_assessment(assessment, expected_identity=changed_identity)
    tampered = deepcopy(assessment)
    tampered["fixture_metrics"]["keeper_precision"] = 0.1
    with pytest.raises(QualityEvidenceError, match="digest"):
        validate_assessment(tampered, expected_identity=_identity())


def test_assessment_rejects_corpus_identity_drift_and_impossible_live_counts():
    from x_monitor.rare_type_quality_gate import (
        QualityEvidenceError,
        complete_assessment,
    )

    changed_corpus = deepcopy(_corpus())
    changed_corpus["cases"][0]["reference"]["rationale"] += " changed"
    with pytest.raises(QualityEvidenceError, match="identity"):
        complete_assessment(
            identity=_identity(),
            corpus=changed_corpus,
            predictions=_predictions(),
            config=_cfg(),
            live_evidence=_live(),
            budget={
                "reserved_usd": "0.25",
                "confirmed_usd": "0.0056",
                "usage_complete": True,
            },
        )
    live = _live()
    live["cohorts"][0]["mill"] = 11
    with pytest.raises(QualityEvidenceError, match="exceed"):
        complete_assessment(
            identity=_identity(),
            corpus=_corpus(),
            predictions=_predictions(),
            config=_cfg(),
            live_evidence=live,
            budget={
                "reserved_usd": "0.25",
                "confirmed_usd": "0.0056",
                "usage_complete": True,
            },
        )


def test_complete_assessment_requires_hard_negative_and_multilingual_coverage():
    from x_monitor.rare_type_quality_gate import complete_assessment

    for mutation, expected_reason in (
        (
            lambda corpus: [
                case["reference"].pop("hard_negative", None)
                for case in corpus["cases"]
                if case["reference"].get("hard_negative") == "recap"
            ],
            "hard_negative_coverage_incomplete",
        ),
        (
            lambda corpus: [
                case["public_payload"].update(lang="en")
                for case in corpus["cases"]
                if "personnel_changes" in case["reference"]["types"]
            ],
            "multilingual_personnel_coverage_incomplete",
        ),
    ):
        corpus = deepcopy(_corpus())
        mutation(corpus)
        identity = deepcopy(_identity())
        identity["corpus_content_sha256"] = hashlib.sha256(
            json.dumps(
                corpus, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        assessment = complete_assessment(
            identity=identity,
            corpus=corpus,
            predictions=_predictions(corpus=corpus),
            config=_cfg(),
            live_evidence=_live(),
            budget={
                "reserved_usd": "0.25",
                "confirmed_usd": "0.0056",
                "usage_complete": True,
            },
        )
        assert assessment["status"] == "fail"
        assert expected_reason in assessment["reasons"]


def test_confirmed_total_cannot_be_below_captured_response_usage():
    from x_monitor.rare_type_quality_gate import complete_assessment

    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=_predictions(),
        config=_cfg(),
        live_evidence=_live(),
        budget={"reserved_usd": "0.25", "confirmed_usd": "0", "usage_complete": True},
    )
    assert assessment["status"] == "fail"
    assert "confirmed_usage_below_captured" in assessment["reasons"]


def test_live_credit_budget_and_duplicate_cohort_ids_fail_closed():
    from x_monitor.rare_type_quality_gate import (
        QualityEvidenceError,
        complete_assessment,
    )

    live = _live()
    live["cohorts"][1]["estimated_credits"] = 1_186
    assessment = complete_assessment(
        identity=_identity(),
        corpus=_corpus(),
        predictions=_predictions(),
        config=_cfg(),
        live_evidence=live,
        budget={
            "reserved_usd": "0.25",
            "confirmed_usd": "0.0056",
            "usage_complete": True,
        },
    )
    assert assessment["status"] == "fail"
    assert "live_credit_budget_exceeded" in assessment["reasons"]

    duplicate = _live()
    duplicate["cohorts"][1]["cohort_id"] = "15m-primary"
    with pytest.raises(QualityEvidenceError, match="duplicate live cohort"):
        complete_assessment(
            identity=_identity(),
            corpus=_corpus(),
            predictions=_predictions(),
            config=_cfg(),
            live_evidence=duplicate,
            budget={
                "reserved_usd": "0.25",
                "confirmed_usd": "0.0056",
                "usage_complete": True,
            },
        )


def test_default_feature_remains_off_and_assessor_does_not_mutate_config():
    cfg = load_config(REPO / "config.yaml")
    before = FIXTURE.read_bytes()
    assert cfg.discovery.rare_types.enabled is False
    _identity()
    assert load_config(REPO / "config.yaml").discovery.rare_types.enabled is False
    assert FIXTURE.read_bytes() == before
