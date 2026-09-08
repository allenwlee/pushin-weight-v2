"""The small, versioned Stage 1 classifier contract.

The transport parser deliberately does not repair provider output.  A caller
only receives a publishable result when every attributed brand is represented
exactly once and every required dimension is present and valid.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

CONTRACT_VERSION = "stage1-v1"
TAXONOMY_VERSION = "stage1-taxonomy-v1"
PROMPT_VERSION = "stage1-prompt-v1"

POST_TYPE_KEYS = (
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
PRODUCT_LABEL_KEYS = (
    "bug",
    "complaint",
    "testimonial",
    "product_request",
    "misinformation",
)
SENTIMENT_KEYS = ("positive", "negative", "neutral", "mixed")
NATIONALISM_KEYS = ("none", "mild_pro", "pro", "constructive_critical", "anti", "mixed")
OUTCOMES = ("classified", "context_missing")
CLASSIFICATION_FIELDS = frozenset(
    {
        "brand_id",
        "outcome",
        "post_types",
        "product_labels",
        "sentiment",
        "china_nationalism",
        "us_nationalism",
    }
)


def _unique_enum_array(value: Any, allowed: Iterable[str]) -> list[str] | None:
    if not isinstance(value, list):
        return None
    allowed_set = set(allowed)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in allowed_set:
            return None
        if item not in result:
            result.append(item)
    return result


def _nullable_enum(value: Any, allowed: Iterable[str]) -> str | None | object:
    if value is None:
        return None
    if isinstance(value, str) and value in set(allowed):
        return value
    return _INVALID


_INVALID = object()


def parse_stage1_classifications(
    classifications: Any, expected_brand_ids: Iterable[str]
) -> dict[str, dict[str, Any]] | None:
    """Return canonical per-brand rows or ``None`` when output is unsafe.

    This validates the entire post before any database writer can observe a
    partial result. Duplicate type/product values are benign and deduplicated;
    duplicate brand objects, missing dimensions, and unknown values fail.
    """
    expected = list(expected_brand_ids)
    if (
        not expected
        or any(not isinstance(brand_id, str) or not brand_id for brand_id in expected)
        or len(set(expected)) != len(expected)
        or not isinstance(classifications, list)
    ):
        return None
    output: dict[str, dict[str, Any]] = {}
    for row in classifications:
        if not isinstance(row, dict):
            return None
        if set(row) != CLASSIFICATION_FIELDS:
            return None
        brand_id = row.get("brand_id")
        if (
            not isinstance(brand_id, str)
            or brand_id not in expected
            or brand_id in output
        ):
            return None
        outcome = row.get("outcome")
        if outcome not in OUTCOMES:
            return None
        post_types = _unique_enum_array(row.get("post_types"), POST_TYPE_KEYS)
        product_labels = _unique_enum_array(
            row.get("product_labels"), PRODUCT_LABEL_KEYS
        )
        sentiment = _nullable_enum(row.get("sentiment"), SENTIMENT_KEYS)
        china = _nullable_enum(row.get("china_nationalism"), NATIONALISM_KEYS)
        us = _nullable_enum(row.get("us_nationalism"), NATIONALISM_KEYS)
        if (
            post_types is None
            or product_labels is None
            or sentiment is _INVALID
            or china is _INVALID
            or us is _INVALID
            or "sentiment" not in row
            or "china_nationalism" not in row
            or "us_nationalism" not in row
        ):
            return None
        if outcome == "classified":
            if not post_types or sentiment is None:
                return None
            if "other" in post_types and post_types != ["other"]:
                return None
        elif post_types or product_labels:
            return None
        output[brand_id] = {
            "outcome": outcome,
            "post_types": post_types,
            "product_labels": product_labels,
            "sentiment": sentiment,
            "china_nationalism": china,
            "us_nationalism": us,
        }
    return output if set(output) == set(expected) else None
