"""The small, versioned Stage 1 classifier contract.

The transport parser deliberately does not repair provider output.  A caller
only receives a publishable result when every attributed brand is represented
exactly once and every required dimension is present and valid.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

CONTRACT_VERSION = "stage1-v1"
LEGACY_STAGE1_TAXONOMY_VERSION = "stage1-taxonomy-v1"
LEGACY_STAGE1_PROMPT_VERSION = "stage1-prompt-v2"
STAGE1_TAXONOMY_V2_VERSION = "stage1-taxonomy-v2"
STAGE1_PROMPT_V3_VERSION = "stage1-prompt-v3"
CANONICAL_TAXONOMY_VERSION = "stage1-taxonomy-v3"
CANONICAL_PROMPT_VERSION = "stage1-prompt-v9"
TAXONOMY_VERSION = CANONICAL_TAXONOMY_VERSION
PROMPT_VERSION = CANONICAL_PROMPT_VERSION
COMPATIBLE_TAXONOMY_VERSIONS = (
    LEGACY_STAGE1_TAXONOMY_VERSION,
    STAGE1_TAXONOMY_V2_VERSION,
    CANONICAL_TAXONOMY_VERSION,
)

LEGACY_POST_TYPE_KEYS = (
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
LEGACY_PRODUCT_LABEL_KEYS = (
    "bug",
    "complaint",
    "testimonial",
    "product_request",
    "misinformation",
)
STAGE1_TAXONOMY_V2_POST_TYPE_KEYS = (
    "releases_updates",
    "hands_on_usage",
    "results_evaluations",
    "questions_requests",
    "advertising_marketing",
    "events_opportunities",
    "opinions_reactions",
    "research_explanations",
    "business_finance",
    "other",
)
CANONICAL_POST_TYPE_KEYS = (
    "releases_updates",
    "hands_on_usage",
    "results_evaluations",
    "questions_requests",
    "advertising_marketing",
    "events",
    "opportunities",
    "job_listings",
    "personnel_changes",
    "opinions_reactions",
    "research_explanations",
    "business_finance",
    "other",
)
CANONICAL_PRODUCT_LABEL_KEYS = (
    "bug",
    "complaint",
    "testimonial",
    "ideas_requests",
    "misinformation",
)
POST_TYPE_KEYS = CANONICAL_POST_TYPE_KEYS
PRODUCT_LABEL_KEYS = CANONICAL_PRODUCT_LABEL_KEYS
SENTIMENT_KEYS = ("positive", "negative", "neutral", "mixed")
NATIONALISM_KEYS = ("none", "mild_pro", "pro", "constructive_critical", "anti", "mixed")
OUTCOMES = ("classified", "context_missing")

# Ordered relation shared by Python callers and parameterized SQL VALUES
# clauses. It includes every compatible source key, including canonical
# identities, so consumers do not need their own alias maps.
TAXONOMY_KEY_CROSSWALK = (
    ("post_type", "buzz_releases", "releases_updates"),
    ("post_type", "releases_updates", "releases_updates"),
    ("post_type", "hands_on_usage", "hands_on_usage"),
    ("post_type", "performance_comparisons", "results_evaluations"),
    ("post_type", "results_evaluations", "results_evaluations"),
    ("post_type", "feedback_questions", "questions_requests"),
    ("post_type", "questions_requests", "questions_requests"),
    ("post_type", "advertising_marketing", "advertising_marketing"),
    ("post_type", "event_announcement", "events_opportunities"),
    ("post_type", "events_opportunities", "events_opportunities"),
    ("post_type", "events", "events"),
    ("post_type", "opportunities", "opportunities"),
    ("post_type", "job_listings", "job_listings"),
    ("post_type", "personnel_changes", "personnel_changes"),
    ("post_type", "opinions_reactions", "opinions_reactions"),
    ("post_type", "research_explanations", "research_explanations"),
    ("post_type", "business_finance", "business_finance"),
    ("post_type", "other", "other"),
    ("product_label", "bug", "bug"),
    ("product_label", "complaint", "complaint"),
    ("product_label", "testimonial", "testimonial"),
    ("product_label", "product_request", "ideas_requests"),
    ("product_label", "ideas_requests", "ideas_requests"),
    ("product_label", "misinformation", "misinformation"),
)

_CANONICAL_KEYS_BY_FAMILY = {
    "post_type": frozenset(
        (*STAGE1_TAXONOMY_V2_POST_TYPE_KEYS, *CANONICAL_POST_TYPE_KEYS)
    ),
    "product_label": frozenset(CANONICAL_PRODUCT_LABEL_KEYS),
}


def _build_taxonomy_key_map() -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for family, source_key, canonical_key in TAXONOMY_KEY_CROSSWALK:
        pair = (family, source_key)
        if pair in result:
            raise ValueError(f"Duplicate taxonomy crosswalk source: {pair!r}")
        if canonical_key not in _CANONICAL_KEYS_BY_FAMILY.get(family, ()):
            raise ValueError(
                f"Invalid taxonomy crosswalk target: {(family, canonical_key)!r}"
            )
        result[pair] = canonical_key
    return result


_TAXONOMY_KEY_MAP = _build_taxonomy_key_map()


def taxonomy_crosswalk_rows(family: str) -> tuple[tuple[str, str], ...]:
    """Return ordered ``(source, canonical)`` rows for SQL ``VALUES`` params."""

    if family not in _CANONICAL_KEYS_BY_FAMILY:
        raise ValueError(f"Unknown taxonomy family: {family!r}")
    return tuple(
        (source_key, canonical_key)
        for row_family, source_key, canonical_key in TAXONOMY_KEY_CROSSWALK
        if row_family == family
    )


def canonicalize_taxonomy_key(family: str, key: str) -> str | None:
    """Return the stable key for one recognized compatible input."""

    return _TAXONOMY_KEY_MAP.get((family, key))


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
    classifications: Any,
    expected_brand_ids: Iterable[str],
    *,
    post_type_keys: Iterable[str] = POST_TYPE_KEYS,
    product_label_keys: Iterable[str] = PRODUCT_LABEL_KEYS,
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
        post_types = _unique_enum_array(row.get("post_types"), post_type_keys)
        product_labels = _unique_enum_array(
            row.get("product_labels"), product_label_keys
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
