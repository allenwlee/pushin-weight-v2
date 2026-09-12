"""Pure offline Stage 1 evaluation metrics and provenance boundaries."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from core.classification_evaluation import (
    EvaluationInputError,
    evaluate_classification_files,
    evaluate_classifications,
    required_floor_paths,
)

SOURCE_IDENTITY = {
    "source_revision": "a" * 40,
    "source_revision_kind": "local_git_head",
    "source_worktree_dirty": False,
}


def _row(example_id, brand_id, language, context, classification):
    return {
        "example_id": example_id,
        "brand_id": brand_id,
        "source_language": language,
        "context_provenance": context,
        "input_context_fingerprint": "0" * 64,
        "classification": classification,
    }


def _classification(**changes):
    value = {
        "outcome": "classified",
        "post_types": ["releases_updates"],
        "product_labels": [],
        "sentiment": "neutral",
        "china_nationalism": None,
        "us_nationalism": None,
    }
    value.update(changes)
    return value


def _documents():
    gold = {
        "schema_version": 1,
        "provenance": {
            "kind": "heldout_gold",
            "gold": True,
            "cohort_id": "r17-test-cohort",
            "contract_version": "stage1-v1",
            "taxonomy_version": "stage1-taxonomy-v2",
            "prompt_version": "stage1-prompt-v3",
            "adjudicator": "reviewer-three",
            "annotators": ["reviewer-test", "reviewer-two"],
            "blind_to_candidate": True,
            "adjudication_method": "independent_double_review",
            "adjudication_version": "gold-v1",
            "adjudicated_at": "2026-09-09T00:00:00Z",
        },
        "rows": [
            _row(
                "e1",
                "brand-a",
                "en",
                ["stored_quote"],
                _classification(
                    post_types=["releases_updates", "hands_on_usage"],
                    product_labels=["bug"],
                    sentiment="positive",
                    china_nationalism="none",
                ),
            ),
            _row(
                "e2",
                "brand-a",
                "zh-Hans",
                ["local_parent"],
                _classification(
                    post_types=["other"],
                    sentiment="negative",
                    us_nationalism="anti",
                ),
            ),
            _row(
                "e3",
                "brand-b",
                "ja",
                [],
                _classification(
                    outcome="context_missing",
                    post_types=[],
                    sentiment=None,
                    china_nationalism="none",
                ),
            ),
        ],
    }
    candidate = {
        "schema_version": 1,
        "provenance": {
            "kind": "candidate_output",
            "gold": False,
            "cohort_id": "r17-test-cohort",
            "contract_version": "stage1-v1",
            "taxonomy_version": "stage1-taxonomy-v2",
            "prompt_version": "stage1-prompt-v3",
            "model": "test-model",
            "source_revision": "b" * 40,
            "generated_at": "2026-09-08T00:00:00Z",
        },
        "rows": [
            _row(
                "e1",
                "brand-a",
                "en",
                ["stored_quote"],
                _classification(
                    # Contract normalization makes order and duplicate values
                    # irrelevant to set scoring.
                    post_types=["hands_on_usage", "releases_updates", "hands_on_usage"],
                    product_labels=["bug"],
                    sentiment="positive",
                    china_nationalism="none",
                ),
            ),
            _row(
                "e2",
                "brand-a",
                "zh-cn",
                ["local_parent"],
                _classification(
                    post_types=["other"],
                    product_labels=["complaint"],
                    sentiment="neutral",
                ),
            ),
            _row(
                "e3",
                "brand-b",
                "ja",
                [],
                _classification(
                    outcome="context_missing",
                    post_types=[],
                    sentiment=None,
                ),
            ),
        ],
    }
    return candidate, gold


def _complete_policy(
    *, floor=0.0, min_support=1, min_slice_support=1, required_contexts=None
):
    contexts = required_contexts or ["none", "stored_quote", "local_parent"]
    return {
        "policy_version": 1,
        "min_support": min_support,
        "min_slice_support": min_slice_support,
        "required_contexts": contexts,
        "floors": {path: floor for path in required_floor_paths(contexts)},
    }


def _supported_documents():
    candidate, gold = _documents()
    candidate["rows"] = deepcopy(gold["rows"])
    candidate["rows"][1]["source_language"] = "zh-cn"
    additions = [
        (
            "e4",
            "en",
            ["stored_quote"],
            _classification(
                post_types=["results_evaluations", "questions_requests"],
                product_labels=["complaint", "testimonial"],
                sentiment="mixed",
                us_nationalism="none",
            ),
        ),
        (
            "e5",
            "zh-cn",
            ["local_parent"],
            _classification(
                post_types=["advertising_marketing"],
                product_labels=["ideas_requests"],
                sentiment="neutral",
            ),
        ),
        (
            "e6",
            "ja",
            [],
            _classification(
                post_types=["events_opportunities"],
                product_labels=["misinformation"],
            ),
        ),
        ("e7", "en", [], _classification(post_types=["opinions_reactions"])),
        ("e8", "zh-cn", [], _classification(post_types=["research_explanations"])),
        ("e9", "ja", [], _classification(post_types=["business_finance"])),
    ]
    for example_id, language, context, classification in additions:
        row = _row(example_id, "brand-a", language, context, classification)
        gold["rows"].append(deepcopy(row))
        candidate["rows"].append(deepcopy(row))
    candidate["provenance"] = {
        "kind": "candidate_output",
        "gold": False,
        "cohort_id": "r17-test-cohort",
        "contract_version": "stage1-v1",
        "taxonomy_version": "stage1-taxonomy-v2",
        "prompt_version": "stage1-prompt-v3",
        "model": "test-model",
        "source_revision": "b" * 40,
        "generated_at": "2026-09-08T00:00:00Z",
    }
    return candidate, gold


def test_multilabel_exact_set_jaccard_and_scalar_confusion_are_deterministic():
    candidate, gold = _documents()
    result = evaluate_classifications(
        candidate,
        gold,
        policy=_complete_policy(min_support=2),
        source_identity=SOURCE_IDENTITY,
    )

    assert result["status"] == "ok"
    assert result["coverage"] == {
        "gold_pairs": 3,
        "candidate_pairs": 3,
        "scored_pairs": 3,
        "missing_candidates": 0,
        "invalid_candidates": 0,
        "coverage_rate": 1.0,
        "missing_by_reason": {},
        "invalid_by_reason": {},
    }
    metrics = result["metrics"]["all"]
    assert metrics["post_types"]["exact_set_accuracy"] == {
        "correct": 3,
        "denominator": 3,
        "value": 1.0,
    }
    assert metrics["post_types"]["jaccard"]["value"] == 1.0
    assert metrics["product_labels"]["exact_set_accuracy"]["value"] == pytest.approx(
        2 / 3
    )
    assert metrics["product_labels"]["jaccard"]["value"] == pytest.approx(2 / 3)
    assert metrics["product_labels"]["empty_set_accuracy"] == {
        "correct": 1,
        "denominator": 2,
        "value": 0.5,
    }
    assert metrics["product_labels"]["empty_nonempty_confusion"] == {
        "gold_empty": {"candidate_empty": 1, "candidate_nonempty": 1},
        "gold_nonempty": {"candidate_empty": 0, "candidate_nonempty": 1},
    }
    assert metrics["product_labels"]["labels"]["complaint"] == {
        "support": 0,
        "predicted_positive": 1,
        "tp": 0,
        "fp": 1,
        "fn": 0,
        "precision": 0.0,
        "recall": None,
        "f1": 0.0,
    }
    assert metrics["china_nationalism"]["matrix"]["none"]["unknown"] == 1
    assert metrics["china_nationalism"]["matrix"]["none"]["none"] == 1
    assert metrics["us_nationalism"]["matrix"]["anti"]["unknown"] == 1
    assert metrics["china_nationalism"]["none_unknown_errors"] == {
        "gold_none_candidate_unknown": 1,
        "gold_unknown_candidate_none": 0,
        "total": 1,
    }
    assert "none" in metrics["china_nationalism"]["labels"]
    assert "unknown" in metrics["china_nationalism"]["labels"]
    assert result["metric_conventions"] == {
        "undefined_metric": None,
        "jaccard_empty_vs_empty": 1.0,
        "scalar_null_bucket": "unknown",
    }
    assert set(result["metrics"]["by_language"]) == {"en", "ja", "zh-cn"}
    assert set(result["metrics"]["by_context"]) == {
        "none",
        "local_parent",
        "stored_quote",
    }
    assert result["support_gaps"]
    assert result["assessment"] == {
        "status": "blocked",
        "reason": "insufficient_support",
        "support_gaps": result["support_gaps"],
    }

    repeat = evaluate_classifications(
        candidate,
        gold,
        policy=_complete_policy(min_support=2),
        source_identity=SOURCE_IDENTITY,
    )
    assert result == repeat
    assert result["identity"]["evaluation_identity"].startswith("sha256:")


def test_taxonomy_v3_is_scored_as_a_separate_closed_vocabulary():
    candidate, gold = _documents()
    for document in (candidate, gold):
        document["provenance"]["taxonomy_version"] = "stage1-taxonomy-v3"
        document["provenance"]["prompt_version"] = "stage1-prompt-v18"
        document["rows"][0]["classification"]["post_types"] = ["job_listings"]
    policy = _complete_policy()
    policy["floors"] = {
        path: 0.0
        for path in required_floor_paths(
            policy["required_contexts"], "stage1-taxonomy-v3"
        )
    }

    result = evaluate_classifications(
        candidate,
        gold,
        policy=policy,
        source_identity=SOURCE_IDENTITY,
    )

    assert result["cohort"]["taxonomy_version"] == "stage1-taxonomy-v3"
    assert "job_listings" in result["metrics"]["all"]["post_types"]["labels"]
    assert "events_opportunities" not in result["metrics"]["all"]["post_types"][
        "labels"
    ]
    assert result["support_gaps"]


def test_invalid_and_missing_candidates_are_excluded_but_reported():
    candidate, gold = _documents()
    candidate["rows"] = [candidate["rows"][0], deepcopy(candidate["rows"][1])]
    candidate["rows"][1]["classification"]["sentiment"] = "invalid"

    result = evaluate_classifications(
        candidate,
        gold,
        source_identity=SOURCE_IDENTITY,
    )

    assert result["status"] == "incomplete"
    assert result["coverage"]["scored_pairs"] == 1
    assert result["coverage"]["missing_candidates"] == 1
    assert result["coverage"]["invalid_candidates"] == 1
    assert result["coverage"]["missing_by_reason"] == {"missing_row": 1}
    assert result["coverage"]["invalid_by_reason"] == {"invalid_contract": 1}
    assert (
        result["metrics"]["all"]["post_types"]["exact_set_accuracy"]["denominator"] == 1
    )
    assert result["assessment"] == {
        "status": "unassessed",
        "reason": "no_policy",
    }


def test_missing_classification_is_distinct_from_missing_candidate_row():
    candidate, gold = _documents()
    candidate["rows"][1]["classification"] = None

    result = evaluate_classifications(
        candidate,
        gold,
        source_identity=SOURCE_IDENTITY,
    )

    assert result["coverage"]["missing_by_reason"] == {"missing_classification": 1}
    assert result["coverage"]["invalid_candidates"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "synthetic"),
        ("gold", False),
    ],
)
def test_gold_requires_heldout_adjudication_provenance(field, value):
    candidate, gold = _documents()
    gold["provenance"][field] = value

    with pytest.raises(EvaluationInputError, match="provenance|gold marker"):
        evaluate_classifications(candidate, gold, source_identity=SOURCE_IDENTITY)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("annotators", ["only-one"]),
        ("blind_to_candidate", False),
        ("adjudication_method", ""),
    ],
)
def test_gold_requires_blinded_double_adjudication(field, value):
    candidate, gold = _documents()
    gold["provenance"][field] = value

    with pytest.raises(EvaluationInputError):
        evaluate_classifications(candidate, gold, source_identity=SOURCE_IDENTITY)


def test_candidate_scope_and_cohort_mismatches_fail_before_scoring():
    candidate, gold = _documents()
    candidate["provenance"]["cohort_id"] = "other-cohort"
    with pytest.raises(EvaluationInputError, match="cohorts differ"):
        evaluate_classifications(candidate, gold, source_identity=SOURCE_IDENTITY)

    candidate, gold = _documents()
    candidate["rows"].append(_row("extra", "brand-a", "en", [], _classification()))
    with pytest.raises(EvaluationInputError, match="absent from gold"):
        evaluate_classifications(candidate, gold, source_identity=SOURCE_IDENTITY)


def test_policy_floor_is_optional_explicit_and_identity_bound():
    candidate, gold = _supported_documents()
    no_policy = evaluate_classifications(
        candidate, gold, source_identity=SOURCE_IDENTITY
    )
    floor_policy = evaluate_classifications(
        candidate,
        gold,
        policy=_complete_policy(floor=1.0),
        source_identity=SOURCE_IDENTITY,
    )
    failing_candidate = deepcopy(candidate)
    failing_candidate["rows"][0]["classification"]["product_labels"] = []
    failing_policy = evaluate_classifications(
        failing_candidate,
        gold,
        policy=_complete_policy(floor=1.0),
        source_identity=SOURCE_IDENTITY,
        candidate_sha256="sha256:" + "c" * 64,
        gold_sha256="sha256:" + "d" * 64,
    )

    assert no_policy["assessment"] == {"status": "unassessed", "reason": "no_policy"}
    assert floor_policy["assessment"]["status"] == "pass"
    assert failing_policy["assessment"]["status"] == "fail"
    assert (
        floor_policy["identity"]["evaluation_identity"]
        != no_policy["identity"]["evaluation_identity"]
    )
    assert failing_policy["identity"]["candidate_digest"] == "sha256:" + "c" * 64


def test_required_language_and_configured_context_gates_block_assessment():
    candidate, gold = _supported_documents()
    gold["rows"] = [row for row in gold["rows"] if row["source_language"] != "ja"]
    candidate["rows"] = [
        row for row in candidate["rows"] if row["source_language"] != "ja"
    ]
    result = evaluate_classifications(
        candidate,
        gold,
        policy=_complete_policy(),
        source_identity=SOURCE_IDENTITY,
    )
    assert result["assessment"] == {
        "status": "blocked",
        "reason": "insufficient_support",
        "support_gaps": result["support_gaps"],
    }
    assert "by_language.ja" in result["support_gaps"]

    candidate, gold = _supported_documents()
    policy = _complete_policy(
        required_contexts=[
            "none",
            "stored_quote",
            "local_parent",
            "stored_quote+local_parent",
        ]
    )
    result = evaluate_classifications(
        candidate,
        gold,
        policy=policy,
        source_identity=SOURCE_IDENTITY,
    )
    assert result["assessment"] == {
        "status": "blocked",
        "reason": "insufficient_support",
        "support_gaps": result["support_gaps"],
    }
    assert "by_context.stored_quote+local_parent" in result["support_gaps"]


def test_combined_context_uses_one_canonical_name_and_can_satisfy_policy():
    candidate, gold = _supported_documents()
    combined = _row(
        "e-combined",
        "brand-a",
        "en",
        ["stored_quote", "local_parent"],
        _classification(),
    )
    combined["input_context_fingerprint"] = "4" * 64
    gold["rows"].append(deepcopy(combined))
    candidate_combined = deepcopy(combined)
    candidate_combined["context_provenance"] = ["local_parent", "stored_quote"]
    candidate["rows"].append(candidate_combined)
    policy = _complete_policy(
        floor=1.0,
        required_contexts=[
            "none",
            "stored_quote",
            "local_parent",
            "stored_quote+local_parent",
        ],
    )

    result = evaluate_classifications(
        candidate,
        gold,
        policy=policy,
        source_identity=SOURCE_IDENTITY,
    )

    assert "stored_quote+local_parent" in result["metrics"]["by_context"]
    assert result["support"]["contexts"]["stored_quote+local_parent"] == 1
    assert result["assessment"]["status"] == "pass"


def test_policy_must_cover_every_r17_dimension_and_reject_unknown_fields():
    candidate, gold = _supported_documents()
    partial = _complete_policy()
    partial["floors"].pop("all.us_nationalism.accuracy")
    with pytest.raises(EvaluationInputError, match="floors is incomplete"):
        evaluate_classifications(
            candidate, gold, policy=partial, source_identity=SOURCE_IDENTITY
        )

    unknown = _complete_policy()
    unknown["required_labels"] = ["bug"]
    with pytest.raises(EvaluationInputError, match="unknown fields"):
        evaluate_classifications(
            candidate, gold, policy=unknown, source_identity=SOURCE_IDENTITY
        )


def test_fingerprint_mismatch_is_an_invalid_candidate_coverage_failure():
    candidate, gold = _documents()
    candidate["rows"][0]["input_context_fingerprint"] = "f" * 64

    result = evaluate_classifications(
        candidate,
        gold,
        source_identity=SOURCE_IDENTITY,
    )

    assert result["coverage"]["invalid_by_reason"] == {
        "input_context_fingerprint_mismatch": 1
    }
    assert result["coverage"]["scored_pairs"] == 2


@pytest.mark.parametrize(
    "source_identity",
    [
        {
            "source_revision": "unavailable",
            "source_revision_kind": "unavailable",
            "source_worktree_dirty": None,
        },
        {
            "source_revision": "a" * 40,
            "source_revision_kind": "local_git_head",
            "source_worktree_dirty": True,
        },
    ],
)
def test_policy_cannot_pass_with_unreproducible_evaluator_source(source_identity):
    candidate, gold = _supported_documents()

    result = evaluate_classifications(
        candidate,
        gold,
        policy=_complete_policy(floor=1.0),
        source_identity=source_identity,
    )

    assert result["assessment"] == {
        "status": "blocked",
        "reason": "unreproducible_evaluator_source",
    }


def test_zero_denominator_metrics_are_explicitly_null():
    candidate, gold = _documents()
    result = evaluate_classifications(
        candidate,
        gold,
        source_identity=SOURCE_IDENTITY,
    )

    assert (
        result["metrics"]["all"]["post_types"]["labels"]["business_finance"]["recall"]
        is None
    )
    assert result["metrics"]["all"]["sentiment"]["classes"]["mixed"]["recall"] is None
    assert result["metric_conventions"]["undefined_metric"] is None


def test_files_bind_exact_raw_bytes_into_identity(tmp_path):
    candidate, gold = _documents()
    candidate_path = tmp_path / "candidate.json"
    gold_path = tmp_path / "gold.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    first = evaluate_classification_files(
        candidate_path, gold_path, source_identity=SOURCE_IDENTITY
    )
    candidate_path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    second = evaluate_classification_files(
        candidate_path, gold_path, source_identity=SOURCE_IDENTITY
    )
    assert (
        first["identity"]["candidate_digest"] != second["identity"]["candidate_digest"]
    )
    assert (
        first["identity"]["evaluation_identity"]
        != second["identity"]["evaluation_identity"]
    )


def test_candidate_fingerprint_and_revision_are_strict():
    candidate, gold = _documents()
    del candidate["rows"][0]["input_context_fingerprint"]
    with pytest.raises(EvaluationInputError, match="incomplete|fingerprint"):
        evaluate_classifications(candidate, gold, source_identity=SOURCE_IDENTITY)

    candidate, gold = _documents()
    candidate["rows"][0]["input_context_fingerprint"] = ""
    with pytest.raises(EvaluationInputError, match="input_context_fingerprint"):
        evaluate_classifications(candidate, gold, source_identity=SOURCE_IDENTITY)

    candidate, gold = _documents()
    candidate["provenance"]["source_revision"] = "short"
    with pytest.raises(EvaluationInputError, match="40-hex"):
        evaluate_classifications(candidate, gold, source_identity=SOURCE_IDENTITY)


def test_invalid_policy_and_gold_classification_are_rejected():
    candidate, gold = _documents()
    policy = _complete_policy()
    policy["min_support"] = -1
    with pytest.raises(EvaluationInputError, match="min_support"):
        evaluate_classifications(
            candidate,
            gold,
            policy=policy,
            source_identity=SOURCE_IDENTITY,
        )

    gold["rows"][0]["classification"]["post_types"] = ["unknown-type"]
    with pytest.raises(EvaluationInputError, match="gold classification"):
        evaluate_classifications(candidate, gold, source_identity=SOURCE_IDENTITY)
