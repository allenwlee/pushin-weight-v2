"""Pure, fail-closed quality assessment for the combined rare-type search.

This module performs no network or database I/O. Captured provider answers and
independently reviewed live cohorts are inputs; it never manufactures them.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from x_monitor.config import JevDecisionsConfig
from x_monitor.jev_decisions import (
    QUESTION_SET,
    derive_gate_outcome,
    encode_request_payload,
    public_post_state,
    question_content_hash,
    threshold_values_hash,
)

DOMAIN_TYPES = (
    "personnel_changes",
    "job_listings",
    "events",
    "opportunities",
    "model_releases",
)
HARD_NEGATIVE_FAMILIES = {
    "mill",
    "lineup",
    "f1",
    "joke",
    "static_bio",
    "recap",
    "price_only",
    "conference_ad",
}
ASSESSMENT_BUDGET_USD = Decimal("0.25")


class QualityEvidenceError(ValueError):
    """The supplied evidence cannot be scored without guessing."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _decimal(value: Any, *, field: str) -> Decimal:
    if isinstance(value, bool):
        raise QualityEvidenceError(f"{field} must be a decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QualityEvidenceError(f"{field} must be a decimal") from exc
    if not result.is_finite() or result < 0:
        raise QualityEvidenceError(f"{field} must be a nonnegative finite decimal")
    return result


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def assessment_identity(
    *,
    query_version: str,
    planner_query: str,
    config: JevDecisionsConfig,
    fixture_path: Path,
) -> dict[str, str]:
    """Freeze every input that can change a gate result before inference."""

    if question_content_hash() != config.question_content_sha256:
        raise QualityEvidenceError("configured question content hash mismatch")
    if (
        threshold_values_hash(config.no_threshold, config.yes_threshold)
        != config.threshold_values_sha256
    ):
        raise QualityEvidenceError("configured threshold values hash mismatch")
    fixture_bytes = fixture_path.read_bytes()
    try:
        corpus = json.loads(fixture_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualityEvidenceError("fixture JSON invalid") from exc
    return {
        "query_version": query_version,
        "planner_query_sha256": _sha256(planner_query.encode("utf-8")),
        "requested_model": config.model,
        "attested_model": config.model,
        "requested_provider": config.provider,
        "attested_provider": config.provider,
        "question_version": config.question_set_version,
        "question_content_sha256": config.question_content_sha256,
        "threshold_version": config.threshold_version,
        "threshold_values_sha256": config.threshold_values_sha256,
        "yes_threshold": format(config.yes_threshold, "f"),
        "no_threshold": format(config.no_threshold, "f"),
        "fixture_sha256": _sha256(fixture_bytes),
        "corpus_content_sha256": _sha256(_canonical_bytes(corpus)),
    }


def _validated_cases(corpus: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    cases = corpus.get("cases")
    if not isinstance(cases, list):
        raise QualityEvidenceError("corpus cases missing")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping) or not isinstance(case.get("id"), str):
            raise QualityEvidenceError("corpus case identity invalid")
        case_id = case["id"]
        if case_id in seen:
            raise QualityEvidenceError(f"duplicate corpus case: {case_id}")
        seen.add(case_id)
        reference = case.get("reference")
        if not isinstance(reference, Mapping) or not isinstance(
            reference.get("keep"), bool
        ):
            raise QualityEvidenceError(f"reference label missing: {case_id}")
        types = reference.get("types")
        if not isinstance(types, list) or any(
            item not in DOMAIN_TYPES for item in types
        ):
            raise QualityEvidenceError(f"reference types invalid: {case_id}")
        if len(types) != len(set(types)):
            raise QualityEvidenceError(f"duplicate reference type: {case_id}")
        if reference["keep"] != bool(types):
            raise QualityEvidenceError(f"reference keep/types mismatch: {case_id}")
        hard_negative = reference.get("hard_negative")
        if hard_negative is not None and hard_negative not in HARD_NEGATIVE_FAMILIES:
            raise QualityEvidenceError(f"hard-negative family invalid: {case_id}")
    return cases


def _validated_prediction(
    row: Mapping[str, Any], *, case_id: str, config: JevDecisionsConfig
) -> tuple[dict[str, float], str]:
    if row.get("model") != config.model:
        raise QualityEvidenceError(f"response model mismatch: {case_id}")
    if row.get("provider") != config.provider:
        raise QualityEvidenceError(f"response provider mismatch: {case_id}")
    response_id = row.get("response_id")
    if not isinstance(response_id, str) or not response_id:
        raise QualityEvidenceError(f"response id missing: {case_id}")
    evidence_kind = row.get("evidence_kind")
    if evidence_kind not in {"captured_real", "mock"}:
        raise QualityEvidenceError(f"response evidence kind invalid: {case_id}")
    probabilities = row.get("probabilities")
    if not isinstance(probabilities, Mapping):
        raise QualityEvidenceError(f"response probabilities missing: {case_id}")
    if set(probabilities) != set(QUESTION_SET):
        raise QualityEvidenceError(f"response questions mismatch: {case_id}")
    cleaned: dict[str, float] = {}
    for question, value in probabilities.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise QualityEvidenceError(f"response probability invalid: {case_id}")
        probability = float(value)
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise QualityEvidenceError(f"response probability invalid: {case_id}")
        cleaned[question] = probability
    usage = row.get("usage")
    if not isinstance(usage, Mapping):
        raise QualityEvidenceError(f"response usage missing: {case_id}")
    _decimal(usage.get("cost_usd"), field=f"response usage cost: {case_id}")
    for token_field in ("input_tokens", "output_tokens"):
        token_value = usage.get(token_field)
        if (
            isinstance(token_value, bool)
            or not isinstance(token_value, int)
            or token_value < 0
        ):
            raise QualityEvidenceError(f"response usage invalid: {case_id}")
    return cleaned, evidence_kind


def evaluate_fixture_predictions(
    *,
    corpus: Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]],
    config: JevDecisionsConfig,
) -> dict[str, Any]:
    """Score captured answers using U7's canonical gate derivation."""

    cases = _validated_cases(corpus)
    expected_ids = {case["id"] for case in cases}
    by_id: dict[str, Mapping[str, Any]] = {}
    response_ids: set[str] = set()
    for prediction in predictions:
        case_id = prediction.get("case_id")
        if not isinstance(case_id, str):
            raise QualityEvidenceError("prediction case id missing")
        if case_id in by_id:
            raise QualityEvidenceError(f"duplicate prediction: {case_id}")
        if case_id not in expected_ids:
            raise QualityEvidenceError(f"unexpected prediction: {case_id}")
        response_id = prediction.get("response_id")
        if isinstance(response_id, str) and response_id in response_ids:
            raise QualityEvidenceError(f"duplicate response id: {response_id}")
        if isinstance(response_id, str):
            response_ids.add(response_id)
        by_id[case_id] = prediction
    missing = sorted(expected_ids - set(by_id))
    if missing:
        raise QualityEvidenceError(f"missing predictions: {', '.join(missing)}")

    rows: list[dict[str, Any]] = []
    evidence_kinds: set[str] = set()
    confusion = {
        "true_positive": 0,
        "false_positive": 0,
        "true_negative": 0,
        "false_negative": 0,
    }
    type_counts = {
        type_name: {"true_positive": 0, "false_positive": 0, "false_negative": 0}
        for type_name in DOMAIN_TYPES
    }
    hard_negative_false_keeps: list[str] = []
    exact_matches = 0
    captured_cost = Decimal(0)
    for case in cases:
        case_id = case["id"]
        probabilities, evidence_kind = _validated_prediction(
            by_id[case_id], case_id=case_id, config=config
        )
        expected_request_sha256 = _sha256(
            encode_request_payload(public_post_state(case["public_payload"]), config)
        )
        if by_id[case_id].get("request_sha256") != expected_request_sha256:
            raise QualityEvidenceError(f"request hash mismatch: {case_id}")
        captured_cost += _decimal(
            by_id[case_id]["usage"]["cost_usd"],
            field=f"response usage cost: {case_id}",
        )
        evidence_kinds.add(evidence_kind)
        outcome, derived_tuple = derive_gate_outcome(probabilities, config)
        derived = set(derived_tuple)
        expected = set(case["reference"]["types"])
        predicted_keep = outcome == "kept"
        expected_keep = bool(case["reference"]["keep"])
        confusion[
            ("true_" if predicted_keep == expected_keep else "false_")
            + ("positive" if predicted_keep else "negative")
        ] += 1
        for type_name in DOMAIN_TYPES:
            if type_name in derived and type_name in expected:
                type_counts[type_name]["true_positive"] += 1
            elif type_name in derived:
                type_counts[type_name]["false_positive"] += 1
            elif type_name in expected:
                type_counts[type_name]["false_negative"] += 1
        if derived == expected:
            exact_matches += 1
        if case["reference"].get("hard_negative") and predicted_keep:
            hard_negative_false_keeps.append(case_id)
        rows.append(
            {
                "case_id": case_id,
                "outcome": outcome,
                "derived_types": sorted(derived),
                "reference_keep": expected_keep,
                "reference_types": sorted(expected),
            }
        )

    tp = confusion["true_positive"]
    fp = confusion["false_positive"]
    fn = confusion["false_negative"]
    per_type = {}
    for type_name, counts in type_counts.items():
        type_tp = counts["true_positive"]
        type_fp = counts["false_positive"]
        type_fn = counts["false_negative"]
        per_type[type_name] = {
            **counts,
            "precision": _ratio(type_tp, type_tp + type_fp),
            "recall": _ratio(type_tp, type_tp + type_fn),
        }
    return {
        "evidence_kind": next(iter(evidence_kinds))
        if len(evidence_kinds) == 1
        else "mixed",
        "case_count": len(cases),
        "keeper_confusion": confusion,
        "keeper_precision": _ratio(tp, tp + fp),
        "keeper_recall": _ratio(tp, tp + fn),
        "per_type": per_type,
        "multilabel": {
            "exact_matches": exact_matches,
            "exact_match_ratio": _ratio(exact_matches, len(cases)),
        },
        "hard_negative_false_keeps": sorted(hard_negative_false_keeps),
        "captured_cost_usd": format(captured_cost, "f"),
        "rows": rows,
    }


def _corpus_reasons(corpus: Mapping[str, Any]) -> list[str]:
    cases = _validated_cases(corpus)
    reasons = []
    if sum(not case["reference"]["keep"] for case in cases) < 25:
        reasons.append("negative_fixture_count_below_floor")
    for type_name in DOMAIN_TYPES:
        if sum(type_name in case["reference"]["types"] for case in cases) < 5:
            reasons.append(f"positive_fixture_count_below_floor:{type_name}")
    hard_negative_families = {case["reference"].get("hard_negative") for case in cases}
    if not HARD_NEGATIVE_FAMILIES <= hard_negative_families:
        reasons.append("hard_negative_coverage_incomplete")
    personnel_languages = {
        str(case.get("public_payload", {}).get("lang", "")).lower()
        for case in cases
        if "personnel_changes" in case["reference"]["types"]
    }
    if not (
        any(language.startswith("en") for language in personnel_languages)
        and any(
            language in {"zh", "zh-cn", "zh_cn", "zh-hans"}
            for language in personnel_languages
        )
        and any(language.startswith("ja") for language in personnel_languages)
    ):
        reasons.append("multilingual_personnel_coverage_incomplete")
    return reasons


def _validate_identity_for_assessment(
    identity: Mapping[str, str],
    *,
    corpus: Mapping[str, Any],
    config: JevDecisionsConfig,
) -> None:
    expected = {
        "requested_model": config.model,
        "attested_model": config.model,
        "requested_provider": config.provider,
        "attested_provider": config.provider,
        "question_version": config.question_set_version,
        "question_content_sha256": question_content_hash(),
        "threshold_version": config.threshold_version,
        "threshold_values_sha256": threshold_values_hash(
            config.no_threshold, config.yes_threshold
        ),
        "yes_threshold": format(config.yes_threshold, "f"),
        "no_threshold": format(config.no_threshold, "f"),
        "corpus_content_sha256": _sha256(_canonical_bytes(corpus)),
    }
    mismatches = [key for key, value in expected.items() if identity.get(key) != value]
    if mismatches:
        raise QualityEvidenceError(
            f"assessment identity mismatch: {', '.join(sorted(mismatches))}"
        )


def _live_reasons(
    live_evidence: Mapping[str, Any] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    if not isinstance(live_evidence, Mapping):
        return ["live_evidence_missing"], []
    cohorts = live_evidence.get("cohorts")
    if not isinstance(cohorts, list) or not cohorts:
        return ["live_sample_too_small"], []
    if live_evidence.get("overlap_source") != "production_read_only_exact_ids":
        return ["overlap_unknown"], []
    reasons: list[str] = []
    metrics: list[dict[str, Any]] = []
    all_ids: set[str] = set()
    cohort_ids: set[str] = set()
    total_estimated_credits = 0
    for cohort in cohorts:
        if not isinstance(cohort, Mapping):
            raise QualityEvidenceError("live cohort invalid")
        cohort_id = cohort.get("cohort_id")
        post_ids = cohort.get("post_ids")
        if (
            not isinstance(cohort_id, str)
            or not isinstance(post_ids, list)
            or any(not isinstance(post_id, str) for post_id in post_ids)
        ):
            raise QualityEvidenceError("live cohort identity invalid")
        if cohort_id in cohort_ids:
            raise QualityEvidenceError(f"duplicate live cohort id: {cohort_id}")
        cohort_ids.add(cohort_id)
        if len(post_ids) != len(set(post_ids)):
            raise QualityEvidenceError(f"duplicate live post ids: {cohort_id}")
        raw_paid = cohort.get("raw_paid_result_count", cohort.get("raw_count"))
        assessable = cohort.get("captured_assessable_count", len(post_ids))
        estimated_credits = cohort.get("estimated_credits")
        counts = {
            name: cohort.get(name)
            for name in (
                "independently_read_keepers",
                "already_stored",
                "mill",
                "recruiter",
            )
        }
        if any(value is None for value in counts.values()):
            reasons.append(
                "overlap_unknown"
                if counts["already_stored"] is None
                else "live_counts_unknown"
            )
            continue
        numeric_values = [raw_paid, assessable, estimated_credits, *counts.values()]
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in numeric_values
        ):
            raise QualityEvidenceError(f"live cohort counts invalid: {cohort_id}")
        if assessable > raw_paid or any(
            value > len(post_ids) for value in counts.values()
        ):
            raise QualityEvidenceError(
                f"live cohort counts exceed source rows: {cohort_id}"
            )
        total_estimated_credits += estimated_credits
        if assessable != len(post_ids) or raw_paid > assessable:
            reasons.append("live_captured_rows_incomplete")
        if any(post_id in all_ids for post_id in post_ids):
            reasons.append("live_duplicate_ids_across_windows")
        all_ids.update(post_ids)
        denominator = len(post_ids)
        if denominator < 10:
            reasons.append(f"live_sample_too_small:{cohort_id}")
        yield_rate = _ratio(counts["independently_read_keepers"], denominator)
        overlap_rate = _ratio(counts["already_stored"], denominator)
        mill_rate = _ratio(counts["mill"], denominator)
        recruiter_rate = _ratio(counts["recruiter"], denominator)
        metrics.append(
            {
                "cohort_id": cohort_id,
                "raw_paid_result_count": raw_paid,
                "captured_assessable_count": assessable,
                "unique_post_count": denominator,
                "keeper_yield": yield_rate,
                "overlap_rate": overlap_rate,
                "mill_rate": mill_rate,
                "recruiter_rate": recruiter_rate,
                "estimated_credits": estimated_credits,
                "keepers_per_estimated_credit": _ratio(
                    counts["independently_read_keepers"], estimated_credits
                ),
            }
        )
        if yield_rate is not None and yield_rate < 0.60:
            reasons.append("live_keeper_yield_below_floor")
        if overlap_rate is not None and overlap_rate > 0.20:
            reasons.append("live_overlap_above_ceiling")
        if mill_rate is not None and mill_rate > 0.20:
            reasons.append("live_mill_above_ceiling")
        if recruiter_rate is not None and recruiter_rate > 0.20:
            reasons.append("live_recruiter_above_ceiling")
    if len(all_ids) < 10:
        reasons.append("live_sample_too_small")
    if total_estimated_credits > 1_200:
        reasons.append("live_credit_budget_exceeded")
    return list(dict.fromkeys(reasons)), metrics


def complete_assessment(
    *,
    identity: Mapping[str, str],
    corpus: Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]],
    config: JevDecisionsConfig,
    live_evidence: Mapping[str, Any] | None,
    budget: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a digestible enablement assessment without performing inference."""

    _validate_identity_for_assessment(identity, corpus=corpus, config=config)
    fixture_metrics = evaluate_fixture_predictions(
        corpus=corpus, predictions=predictions, config=config
    )
    fail_reasons = _corpus_reasons(corpus)
    inconclusive_reasons: list[str] = []
    precision = fixture_metrics["keeper_precision"]
    recall = fixture_metrics["keeper_recall"]
    if precision is None or precision < 0.90:
        fail_reasons.append("fixture_keeper_precision_below_floor")
    if recall is None or recall < 0.90:
        fail_reasons.append("fixture_keeper_recall_below_floor")
    if fixture_metrics["hard_negative_false_keeps"]:
        fail_reasons.append("hard_negative_false_keep")
    if fixture_metrics["evidence_kind"] != "captured_real":
        inconclusive_reasons.append("mock_only_evidence")

    live_reasons, live_metrics = _live_reasons(live_evidence)
    measured_live_failures = {
        "live_keeper_yield_below_floor",
        "live_overlap_above_ceiling",
        "live_mill_above_ceiling",
        "live_recruiter_above_ceiling",
        "live_credit_budget_exceeded",
    }
    fail_reasons.extend(
        reason for reason in live_reasons if reason in measured_live_failures
    )
    inconclusive_reasons.extend(
        reason for reason in live_reasons if reason not in measured_live_failures
    )

    reserved = _decimal(budget.get("reserved_usd"), field="reserved_usd")
    confirmed_raw = budget.get("confirmed_usd")
    confirmed = (
        None
        if confirmed_raw is None
        else _decimal(confirmed_raw, field="confirmed_usd")
    )
    usage_complete = budget.get("usage_complete")
    if not isinstance(usage_complete, bool):
        raise QualityEvidenceError("usage_complete must be boolean")
    if reserved > ASSESSMENT_BUDGET_USD or (
        confirmed is not None and confirmed > ASSESSMENT_BUDGET_USD
    ):
        fail_reasons.append("assessment_budget_exceeded")
    if not usage_complete or confirmed is None:
        inconclusive_reasons.append("usage_unknown")
    captured_cost = Decimal(fixture_metrics["captured_cost_usd"])
    if confirmed is not None and confirmed < captured_cost:
        fail_reasons.append("confirmed_usage_below_captured")

    fail_reasons = list(dict.fromkeys(fail_reasons))
    inconclusive_reasons = list(dict.fromkeys(inconclusive_reasons))
    if fail_reasons:
        status = "fail"
        reasons = fail_reasons + inconclusive_reasons
    elif inconclusive_reasons:
        status = "inconclusive"
        reasons = inconclusive_reasons
    else:
        status = "pass"
        reasons = []
    assessment: dict[str, Any] = {
        "schema_version": "rare-type-quality-assessment-v1",
        "identity": dict(identity),
        "status": status,
        "quality_gate_passed": status == "pass",
        "enablement_eligible": False,
        "enablement_approved": False,
        "reasons": reasons,
        "fixture_metrics": fixture_metrics,
        "live_metrics_by_window": live_metrics,
        "budget": {
            "ceiling_usd": format(ASSESSMENT_BUDGET_USD, "f"),
            "reserved_usd": format(reserved, "f"),
            "confirmed_usd": None if confirmed is None else format(confirmed, "f"),
            "usage_complete": usage_complete,
        },
    }
    assessment["assessment_digest"] = _sha256(_canonical_bytes(assessment))
    return assessment


def validate_assessment(
    assessment: Mapping[str, Any], *, expected_identity: Mapping[str, str]
) -> bool:
    """Validate the artifact U6 may consume before considering enablement."""

    if assessment.get("identity") != dict(expected_identity):
        raise QualityEvidenceError("assessment identity mismatch")
    supplied_digest = assessment.get("assessment_digest")
    if not isinstance(supplied_digest, str):
        raise QualityEvidenceError("assessment digest missing")
    unsigned = dict(assessment)
    unsigned.pop("assessment_digest", None)
    if supplied_digest != _sha256(_canonical_bytes(unsigned)):
        raise QualityEvidenceError("assessment digest mismatch")
    if (
        assessment.get("status") != "pass"
        or assessment.get("quality_gate_passed") is not True
    ):
        raise QualityEvidenceError("assessment quality gate did not pass")
    return True
