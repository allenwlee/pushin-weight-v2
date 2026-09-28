"""Source-visible ownership cohort and guarded repair-target contract.

These tests use frozen local evidence only. They never construct a model or
provider client and make no database or network request.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

import pytest

from core.classification_contract import parse_stage1_v4_classifications


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/u18a_label_owner_regressions_v1.json"
MANIFEST = ROOT / "docs/analysis/2026-09-28-023934-u18a-label-owner-repair-manifest.json"
REPAIR_IDS = {
    "2101798119298277764", "2102033817418748243",
    "2103615895600017738", "2104375726627790944",
    "2104483144233853085",
}
TOKEN_MACHINE_IDS = {
    "2101798119298277764", "2101837112115093617",
    "2101887098726821978", "2102033817418748243",
    "2103615895600017738", "2104375726627790944",
}
CANONICAL_FIELDS = {
    "outcome", "post_types", "audience_topics", "audience_topics_state",
    "product_labels", "sentiment", "geopolitical_modes",
    "geopolitical_modes_state", "china_national_stance", "us_national_stance",
}
SUBJECT_FIELDS = {"name", "handle", "domain", "account_handle", "evidence"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_source_evidence(case: dict) -> None:
    source = case["source_text"].casefold()
    if not case["evidence_quotes"] or any(
        not quote or quote.casefold() not in source
        for quote in case["evidence_quotes"]
    ):
        raise ValueError(f"{case['case_id']}: evidence quote absent from visible source")
    expected = case["expected"]
    if set(expected["by_brand"]) != set(case["brand_ids"]):
        raise ValueError(f"{case['case_id']}: exact brand set mismatch")
    if case["tracked_brand_id"] not in case["brand_ids"]:
        raise ValueError(f"{case['case_id']}: missing tracked brand")
    subjects = expected["promoted_subjects"]
    if case["promoted_subject"] is None:
        if subjects or expected["untracked_brand_promotions"]:
            raise ValueError(f"{case['case_id']}: unexpected promotion")
    elif (
        not subjects
        or not expected["untracked_brand_promotions"]
        or case["promoted_subject"] not in {subject["name"] for subject in subjects}
    ):
        raise ValueError(f"{case['case_id']}: promoted subject mismatch")
    for subject in subjects:
        if set(subject) != SUBJECT_FIELDS or subject["evidence"].casefold() not in source:
            raise ValueError(f"{case['case_id']}: subject evidence absent from source")


def _wire_row(brand_id: str, canonical: dict) -> dict:
    if set(canonical) != CANONICAL_FIELDS:
        raise ValueError(f"{brand_id}: incomplete canonical judgment")
    return {
        "brand_id": brand_id,
        "outcome": canonical["outcome"],
        "post_types": canonical["post_types"],
        "audience_topics": (
            canonical["audience_topics"]
            if canonical["audience_topics_state"] == "selected"
            else [canonical["audience_topics_state"]]
        ),
        "product_labels": canonical["product_labels"] or ["none"],
        "sentiment": canonical["sentiment"],
        "geopolitical_modes": (
            canonical["geopolitical_modes"]
            if canonical["geopolitical_modes_state"] == "selected"
            else [canonical["geopolitical_modes_state"]]
        ),
        "china_national_stance": canonical["china_national_stance"],
        "us_national_stance": canonical["us_national_stance"],
    }


def _check_complete_target(expected: dict, brand_ids: list[str]) -> None:
    if set(expected) != {"by_brand", "untracked_brand_promotions", "promoted_subjects"}:
        raise ValueError("incomplete post target")
    if set(expected["by_brand"]) != set(brand_ids):
        raise ValueError("exact brand set mismatch")
    wire_rows = [_wire_row(brand_id, value) for brand_id, value in expected["by_brand"].items()]
    if parse_stage1_v4_classifications(wire_rows, brand_ids) != expected["by_brand"]:
        raise ValueError("invalid canonical Stage 1 judgment")
    if not isinstance(expected["untracked_brand_promotions"], list):
        raise ValueError("missing post-level promotion array")
    if not isinstance(expected["promoted_subjects"], list):
        raise ValueError("missing promoted-subject array")
    if bool(expected["untracked_brand_promotions"]) != bool(expected["promoted_subjects"]):
        raise ValueError("promotion/subject mismatch")


def _check_manifest(manifest: dict) -> None:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("selected_content_revision") != "stage1-content-0731-v6"
        or manifest.get("selected_brand_revision") != "stage1-brand-interpretation-0731-v5"
        or manifest.get("selected_merge_revision") != "stage1-two-role-merge-0731-v6"
    ):
        raise ValueError("unapproved prompt lineage")
    if set(manifest.get("posts", {})) != REPAIR_IDS:
        raise ValueError("repair cohort differs from approved five IDs")
    for post_id, row in manifest["posts"].items():
        if set(row) != {
            "input_context_fingerprint", "by_brand",
            "untracked_brand_promotions", "promoted_subjects",
        }:
            raise ValueError(f"{post_id}: incomplete repair row")
        if not re.fullmatch(r"[0-9a-f]{64}", row["input_context_fingerprint"]):
            raise ValueError(f"{post_id}: invalid input fingerprint")
        _check_complete_target(
            {key: row[key] for key in ("by_brand", "untracked_brand_promotions", "promoted_subjects")},
            list(row["by_brand"]),
        )


def test_frozen_cohort_covers_recurrence_boundaries_and_positive_controls():
    fixture = _load(FIXTURE)
    cases = fixture["cases"]
    assert fixture["schema_version"] == 1
    assert fixture["provenance"]["gold"] is False
    assert {case["post_id"] for case in cases if case["kind"] == "repair"} == REPAIR_IDS
    assert {case["post_id"] for case in cases if case["promoted_subject"] == "Token Machine" and case["kind"] != "synthetic_positive"} == TOKEN_MACHINE_IDS
    assert sum(case["kind"] == "evaluation_only" for case in cases) == 2
    assert sum(case["kind"] == "synthetic_positive" for case in cases) == 3
    for case in cases:
        _check_source_evidence(case)
        _check_complete_target(case["expected"], case["brand_ids"])


def test_prize_and_platform_campaign_do_not_transfer_advertising():
    cases = {case["case_id"]: case for case in _load(FIXTURE)["cases"]}
    negatives = [case for case in cases.values() if case["kind"] in {"repair", "evaluation_only"}]
    for case in negatives:
        for judgment in case["expected"]["by_brand"].values():
            assert "advertising_marketing" not in judgment["post_types"]
    assert cases["bai_glm_campaign"]["author_handle"] == "xxyweb3"
    assert cases["bai_glm_campaign"]["promoted_subject"] == "B.AI"
    assert cases["bai_glm_campaign"]["expected"]["promoted_subjects"][0]["handle"] == "@BAI_AGI"


def test_direct_brand_pitches_and_real_co_promotion_remain_positive():
    cases = {case["case_id"]: case for case in _load(FIXTURE)["cases"]}
    for case_id in ("direct_deepseek_api_pitch", "direct_zhipu_api_pitch", "tracked_and_untracked_co_promotion"):
        case = cases[case_id]
        assert "advertising_marketing" in case["expected"]["by_brand"][case["tracked_brand_id"]]["post_types"]
    co = cases["tracked_and_untracked_co_promotion"]["expected"]
    assert co["untracked_brand_promotions"] == ["general"]
    assert co["promoted_subjects"][0]["name"] == "Token Machine"


def test_repair_manifest_is_complete_and_matches_source_review():
    manifest = _load(MANIFEST)
    _check_manifest(manifest)
    cases = {case["post_id"]: case for case in _load(FIXTURE)["cases"] if case["kind"] == "repair"}
    for post_id, row in manifest["posts"].items():
        case = cases[post_id]
        assert set(row["by_brand"]) == set(case["brand_ids"])
        for key in ("by_brand", "untracked_brand_promotions", "promoted_subjects"):
            assert row[key] == case["expected"][key]


def test_invalid_source_quote_and_incomplete_repair_are_rejected():
    case = deepcopy(_load(FIXTURE)["cases"][0])
    case["evidence_quotes"].append("This sentence was never in the post")
    with pytest.raises(ValueError, match="evidence quote absent"):
        _check_source_evidence(case)

    manifest = _load(MANIFEST)
    del manifest["posts"]["2104375726627790944"]["by_brand"]["deepseek"]["product_labels"]
    with pytest.raises(ValueError, match="incomplete canonical judgment"):
        _check_manifest(manifest)
    manifest = _load(MANIFEST)
    manifest["selected_merge_revision"] = "stage1-two-role-merge-0731-v5"
    with pytest.raises(ValueError, match="unapproved prompt lineage"):
        _check_manifest(manifest)


def test_known_v5_deepseek_error_disagrees_with_frozen_target():
    deepseek = next(
        case for case in _load(FIXTURE)["cases"]
        if case["post_id"] == "2104375726627790944"
    )["expected"]["by_brand"]["deepseek"]
    observed_v5_post_types = ["advertising_marketing"]
    assert observed_v5_post_types != deepseek["post_types"]
    assert "advertising_marketing" not in deepseek["post_types"]
