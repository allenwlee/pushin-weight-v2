"""Strict array and brand-cardinality behavior for Stage 1."""

from __future__ import annotations

from copy import deepcopy

import pytest

from core.classification_contract import (
    NATIONALISM_KEYS,
    POST_TYPE_KEYS,
    PRODUCT_LABEL_KEYS,
    SENTIMENT_KEYS,
    parse_stage1_classifications,
)


def row(brand_id: str = "deepseek"):
    return {
        "brand_id": brand_id,
        "outcome": "classified",
        "post_types": ["buzz_releases"],
        "product_labels": [],
        "sentiment": "neutral",
        "china_nationalism": "none",
        "us_nationalism": None,
    }


def test_exact_stage1_vocabularies_are_frozen():
    assert POST_TYPE_KEYS == (
        "buzz_releases",
        "hands_on_usage",
        "performance_comparisons",
        "feedback_questions",
        "advertising_marketing",
        "event_announcement",
        "opinions_reactions",
        "research_explanations",
        "business_finance",
        "other",
    )
    assert PRODUCT_LABEL_KEYS == (
        "bug",
        "complaint",
        "testimonial",
        "product_request",
        "misinformation",
    )
    assert SENTIMENT_KEYS == ("positive", "negative", "neutral", "mixed")
    assert NATIONALISM_KEYS == (
        "none",
        "mild_pro",
        "pro",
        "constructive_critical",
        "anti",
        "mixed",
    )


def test_all_non_other_types_and_all_product_labels_have_no_arbitrary_cap():
    input_row = row()
    input_row["post_types"] = list(POST_TYPE_KEYS[:-1])
    input_row["product_labels"] = list(PRODUCT_LABEL_KEYS)

    parsed = parse_stage1_classifications([input_row], ["deepseek"])

    assert parsed is not None
    assert parsed["deepseek"]["post_types"] == list(POST_TYPE_KEYS[:-1])
    assert parsed["deepseek"]["product_labels"] == list(PRODUCT_LABEL_KEYS)


def test_duplicate_array_values_are_deduplicated_in_first_seen_order():
    input_row = row()
    input_row["post_types"] = [
        "research_explanations",
        "buzz_releases",
        "research_explanations",
    ]
    input_row["product_labels"] = ["bug", "complaint", "bug"]

    parsed = parse_stage1_classifications([input_row], ["deepseek"])

    assert parsed is not None
    assert parsed["deepseek"]["post_types"] == [
        "research_explanations",
        "buzz_releases",
    ]
    assert parsed["deepseek"]["product_labels"] == ["bug", "complaint"]


def test_other_is_valid_only_as_the_explicit_exclusive_judgment():
    other = row()
    other["post_types"] = ["other"]
    invalid = deepcopy(other)
    invalid["post_types"] = ["other", "opinions_reactions"]

    assert parse_stage1_classifications([other], ["deepseek"]) is not None
    assert parse_stage1_classifications([invalid], ["deepseek"]) is None


@pytest.mark.parametrize(
    "classifications,expected",
    [
        ([row("deepseek")], ["deepseek", "qwen"]),
        ([row("deepseek"), row("deepseek")], ["deepseek"]),
        ([row("deepseek"), row("extra")], ["deepseek"]),
        ([row("deepseek")], []),
    ],
)
def test_missing_duplicate_extra_or_empty_expected_brand_sets_fail(
    classifications,
    expected,
):
    assert parse_stage1_classifications(classifications, expected) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("post_types", "buzz_releases"),
        ("product_labels", "bug"),
        ("sentiment", ["neutral"]),
        ("china_nationalism", ["none"]),
        ("us_nationalism", 0),
    ],
)
def test_wrong_field_types_fail_closed(field, value):
    input_row = row()
    input_row[field] = value

    assert parse_stage1_classifications([input_row], ["deepseek"]) is None


def test_context_missing_rejects_type_and_product_edges():
    with_type = row()
    with_type.update(
        outcome="context_missing",
        post_types=["other"],
        product_labels=[],
        sentiment=None,
    )
    with_product = deepcopy(with_type)
    with_product["post_types"] = []
    with_product["product_labels"] = ["complaint"]

    assert parse_stage1_classifications([with_type], ["deepseek"]) is None
    assert parse_stage1_classifications([with_product], ["deepseek"]) is None


def test_unexpected_per_brand_fields_fail_closed():
    input_row = row()
    input_row["primary_type"] = "buzz_releases"

    assert parse_stage1_classifications([input_row], ["deepseek"]) is None
