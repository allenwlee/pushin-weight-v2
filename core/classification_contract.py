"""Versioned, fail-closed contracts for persisted Stage 1 classification.

``stage1-taxonomy-v4`` is the current write vocabulary.  The v1--v3
definitions remain named here because rows written under those versions must
remain readable; accepting an older row is deliberately separate from
rewriting its meaning as a new row.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


CONTRACT_VERSION = "stage1-v1"
LEGACY_STAGE1_TAXONOMY_VERSION = "stage1-taxonomy-v1"
LEGACY_STAGE1_PROMPT_VERSION = "stage1-prompt-v2"
STAGE1_TAXONOMY_V2_VERSION = "stage1-taxonomy-v2"
STAGE1_PROMPT_V3_VERSION = "stage1-prompt-v3"
STAGE1_TAXONOMY_V3_VERSION = "stage1-taxonomy-v3"
STAGE1_PROMPT_V23_VERSION = "stage1-prompt-v23"
CANONICAL_TAXONOMY_VERSION = "stage1-taxonomy-v4"
CANONICAL_PROMPT_VERSION = "stage1-prompt-v4"
TAXONOMY_VERSION = CANONICAL_TAXONOMY_VERSION
PROMPT_VERSION = CANONICAL_PROMPT_VERSION
COMPATIBLE_TAXONOMY_VERSIONS = (
    LEGACY_STAGE1_TAXONOMY_VERSION,
    STAGE1_TAXONOMY_V2_VERSION,
    STAGE1_TAXONOMY_V3_VERSION,
    CANONICAL_TAXONOMY_VERSION,
)

LEGACY_POST_TYPE_KEYS = (
    "buzz_releases", "hands_on_usage", "performance_comparisons",
    "feedback_questions", "advertising_marketing", "event_announcement",
    "opinions_reactions", "research_explanations", "business_finance", "other",
)
LEGACY_PRODUCT_LABEL_KEYS = (
    "bug", "complaint", "testimonial", "product_request", "misinformation",
)
STAGE1_TAXONOMY_V2_POST_TYPE_KEYS = (
    "releases_updates", "hands_on_usage", "results_evaluations",
    "questions_requests", "advertising_marketing", "events_opportunities",
    "opinions_reactions", "research_explanations", "business_finance", "other",
)
STAGE1_TAXONOMY_V3_POST_TYPE_KEYS = (
    "releases_updates", "hands_on_usage", "results_evaluations",
    "questions_requests", "advertising_marketing", "events", "opportunities",
    "job_listings", "personnel_changes", "opinions_reactions",
    "research_explanations", "business_finance", "other",
)
STAGE1_TAXONOMY_V3_PRODUCT_LABEL_KEYS = (
    "bug", "complaint", "testimonial", "ideas_requests", "misinformation",
)

# Current-write v4 vocabulary. ``results_analysis`` deliberately replaces the
# ambiguous v3 ``results_evaluations`` spelling; old rows keep their original
# key/version while readers can use the alias map below for a current concept.
CANONICAL_POST_TYPE_KEYS = (
    "releases_updates", "hands_on_usage", "results_analysis",
    "questions_requests", "advertising_marketing", "events", "opportunities",
    "job_listings", "personnel_changes", "opinions_reactions",
    "research_explanations", "business_finance", "news_reporting", "other",
)
CANONICAL_PRODUCT_LABEL_KEYS = (
    "bug", "complaint", "testimonial", "ideas_requests", "investigate_claim",
)
POST_TYPE_KEYS = CANONICAL_POST_TYPE_KEYS
PRODUCT_LABEL_KEYS = CANONICAL_PRODUCT_LABEL_KEYS
AUDIENCE_TOPIC_KEYS = (
    "local_inference", "cost_performance", "model_distillation",
    "evals_benchmarks", "openness_license", "agents_tools",
    "api_developer_surface",
)
GEOPOLITICAL_MODE_KEYS = ("reporting", "framework", "nationalism")
UNTRACKED_BRAND_PROMOTION_KEYS = ("general", "spam", "scam", "crypto", "unauthorized")
SENTIMENT_KEYS = ("positive", "negative", "neutral", "mixed")
NATIONALISM_KEYS = ("none", "mild_pro", "pro", "constructive_critical", "anti", "mixed")
NATIONAL_STANCE_KEYS = NATIONALISM_KEYS
OUTCOMES = ("classified", "context_missing")

# Transport-only sentinels. They are never persisted as label-key rows.
_NONE = "none"
_UNAVAILABLE = "unavailable"
_UNKNOWN = "unknown"

TAXONOMY_KEY_CROSSWALK = (
    ("post_type", "buzz_releases", "releases_updates"),
    ("post_type", "releases_updates", "releases_updates"),
    ("post_type", "hands_on_usage", "hands_on_usage"),
    ("post_type", "performance_comparisons", "results_analysis"),
    ("post_type", "results_evaluations", "results_analysis"),
    ("post_type", "results_analysis", "results_analysis"),
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
    ("post_type", "news_reporting", "news_reporting"),
    ("post_type", "other", "other"),
    ("product_label", "bug", "bug"),
    ("product_label", "complaint", "complaint"),
    ("product_label", "testimonial", "testimonial"),
    ("product_label", "product_request", "ideas_requests"),
    ("product_label", "ideas_requests", "ideas_requests"),
    # v3's meaning remains historical. A current v4 claim flag is never inferred.
    ("product_label", "misinformation", "misinformation"),
    ("product_label", "investigate_claim", "investigate_claim"),
)

_CANONICAL_KEYS_BY_FAMILY = {
    "post_type": frozenset(
        (*LEGACY_POST_TYPE_KEYS, *STAGE1_TAXONOMY_V2_POST_TYPE_KEYS,
         *STAGE1_TAXONOMY_V3_POST_TYPE_KEYS, *CANONICAL_POST_TYPE_KEYS)
    ),
    "product_label": frozenset(
        (*LEGACY_PRODUCT_LABEL_KEYS, *STAGE1_TAXONOMY_V3_PRODUCT_LABEL_KEYS,
         *CANONICAL_PRODUCT_LABEL_KEYS)
    ),
}


def _build_taxonomy_key_map() -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for family, source_key, canonical_key in TAXONOMY_KEY_CROSSWALK:
        pair = (family, source_key)
        if pair in result:
            raise ValueError(f"Duplicate taxonomy crosswalk source: {pair!r}")
        if canonical_key not in _CANONICAL_KEYS_BY_FAMILY.get(family, ()):
            raise ValueError(f"Invalid taxonomy crosswalk target: {(family, canonical_key)!r}")
        result[pair] = canonical_key
    return result


_TAXONOMY_KEY_MAP = _build_taxonomy_key_map()


def taxonomy_crosswalk_rows(family: str) -> tuple[tuple[str, str], ...]:
    """Return ordered ``(source, current-concept)`` rows for SQL values."""
    if family not in _CANONICAL_KEYS_BY_FAMILY:
        raise ValueError(f"Unknown taxonomy family: {family!r}")
    return tuple(
        (source_key, canonical_key)
        for row_family, source_key, canonical_key in TAXONOMY_KEY_CROSSWALK
        if row_family == family
    )


def canonicalize_taxonomy_key(family: str, key: str) -> str | None:
    """Return the current concept key for a recognized compatible input."""
    return _TAXONOMY_KEY_MAP.get((family, key))


# v3 shape remains accepted only for its old callers and historical fixtures.
LEGACY_CLASSIFICATION_FIELDS = frozenset({
    "brand_id", "outcome", "post_types", "product_labels", "sentiment",
    "china_nationalism", "us_nationalism",
})
# Kept as the historical public name because v1--v3 evaluation artifacts use
# it. New write callers name the v4 field set explicitly.
CLASSIFICATION_FIELDS = LEGACY_CLASSIFICATION_FIELDS
V4_CLASSIFICATION_FIELDS = frozenset({
    "brand_id", "outcome", "post_types", "audience_topics",
    "product_labels", "sentiment", "geopolitical_modes",
    "china_national_stance", "us_national_stance",
})


def _unique_enum_array(value: Any, allowed: Iterable[str]) -> list[str] | None:
    if not isinstance(value, list):
        return None
    allowed_set = set(allowed)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in allowed_set or item in result:
            return None
        result.append(item)
    return result


def _legacy_enum_array(value: Any, allowed: Iterable[str]) -> list[str] | None:
    """v1--v3 accepted duplicate model labels by keeping first-seen order."""
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


def _enum_or_none(value: Any, allowed: Iterable[str]) -> str | None | object:
    if value is None:
        return None
    return value if isinstance(value, str) and value in set(allowed) else _INVALID


_INVALID = object()


def _validate_expected(expected_brand_ids: Iterable[str]) -> list[str] | None:
    expected = list(expected_brand_ids)
    if (
        not expected
        or any(not isinstance(brand_id, str) or not brand_id for brand_id in expected)
        or len(set(expected)) != len(expected)
    ):
        return None
    return expected


def _parse_legacy_classifications(
    classifications: Any, expected_brand_ids: Iterable[str], *,
    post_type_keys: Iterable[str] = STAGE1_TAXONOMY_V3_POST_TYPE_KEYS,
    product_label_keys: Iterable[str] = STAGE1_TAXONOMY_V3_PRODUCT_LABEL_KEYS,
) -> dict[str, dict[str, Any]] | None:
    """Validate an immutable v1--v3 row without projecting it to v4."""
    expected = _validate_expected(expected_brand_ids)
    if expected is None or not isinstance(classifications, list):
        return None
    output: dict[str, dict[str, Any]] = {}
    for row in classifications:
        if not isinstance(row, dict) or set(row) != LEGACY_CLASSIFICATION_FIELDS:
            return None
        brand_id = row.get("brand_id")
        if not isinstance(brand_id, str) or brand_id not in expected or brand_id in output:
            return None
        outcome = row.get("outcome")
        post_types = _legacy_enum_array(row.get("post_types"), post_type_keys)
        labels = _legacy_enum_array(row.get("product_labels"), product_label_keys)
        sentiment = _enum_or_none(row.get("sentiment"), SENTIMENT_KEYS)
        china = _enum_or_none(row.get("china_nationalism"), NATIONALISM_KEYS)
        us = _enum_or_none(row.get("us_nationalism"), NATIONALISM_KEYS)
        if outcome not in OUTCOMES or post_types is None or labels is None or _INVALID in (sentiment, china, us):
            return None
        if outcome == "classified":
            if not post_types or sentiment is None or ("other" in post_types and post_types != ["other"]):
                return None
        elif post_types or labels:
            return None
        output[brand_id] = {
            "outcome": outcome, "post_types": post_types, "product_labels": labels,
            "sentiment": sentiment, "china_nationalism": china, "us_nationalism": us,
        }
    return output if set(output) == set(expected) else None


def _normalize_sentinel_array(
    value: Any, *, allowed: Iterable[str], none: str = _NONE,
    unavailable: str | None = None,
) -> tuple[list[str], str] | None:
    sentinel_values = (none,) if unavailable is None else (none, unavailable)
    values = _unique_enum_array(value, (*allowed, *sentinel_values))
    if values is None or not values:
        return None
    if set(sentinel_values).intersection(values):
        if len(values) != 1:
            return None
        return [], values[0]
    return values, "selected"


def parse_stage1_v4_classifications(
    classifications: Any, expected_brand_ids: Iterable[str],
) -> dict[str, dict[str, Any]] | None:
    """Validate and normalize one complete v4 post result.

    The parser converts only transport sentinels (``none``, ``unavailable``,
    ``unknown``) to storage values. It never makes semantic repairs.
    """
    expected = _validate_expected(expected_brand_ids)
    if expected is None or not isinstance(classifications, list):
        return None
    output: dict[str, dict[str, Any]] = {}
    for row in classifications:
        if not isinstance(row, dict) or set(row) != V4_CLASSIFICATION_FIELDS:
            return None
        brand_id = row.get("brand_id")
        if not isinstance(brand_id, str) or brand_id not in expected or brand_id in output:
            return None
        outcome = row.get("outcome")
        post_types = _unique_enum_array(row.get("post_types"), POST_TYPE_KEYS)
        topics = _normalize_sentinel_array(
            row.get("audience_topics"), allowed=AUDIENCE_TOPIC_KEYS, unavailable=_UNAVAILABLE
        )
        labels = _normalize_sentinel_array(row.get("product_labels"), allowed=PRODUCT_LABEL_KEYS)
        modes = _normalize_sentinel_array(
            row.get("geopolitical_modes"), allowed=GEOPOLITICAL_MODE_KEYS,
            unavailable=_UNAVAILABLE,
        )
        sentiment = _enum_or_none(row.get("sentiment"), (*SENTIMENT_KEYS, _UNKNOWN))
        china = _enum_or_none(row.get("china_national_stance"), (*NATIONAL_STANCE_KEYS, _UNKNOWN))
        us = _enum_or_none(row.get("us_national_stance"), (*NATIONAL_STANCE_KEYS, _UNKNOWN))
        if (
            outcome not in OUTCOMES or post_types is None or topics is None or labels is None
            or modes is None or _INVALID in (sentiment, china, us)
        ):
            return None
        topic_values, topic_state = topics
        label_values, _label_state = labels
        mode_values, mode_state = modes
        if sentiment == _UNKNOWN:
            sentiment = None
        if china == _UNKNOWN:
            china = None
        if us == _UNKNOWN:
            us = None
        if outcome == "classified":
            if not post_types or ("other" in post_types and post_types != ["other"]):
                return None
            if sentiment is None:
                return None
        elif post_types or label_values or sentiment is not None or mode_values or china is not None or us is not None:
            return None
        if outcome == "context_missing" and topic_state != _UNAVAILABLE:
            return None
        if mode_state == _UNAVAILABLE:
            if china is not None or us is not None:
                return None
        elif "nationalism" not in mode_values:
            if china != "none" or us != "none":
                return None
        output[brand_id] = {
            "outcome": outcome,
            "post_types": post_types,
            "audience_topics": topic_values,
            "audience_topics_state": topic_state,
            "product_labels": label_values,
            "sentiment": sentiment,
            "geopolitical_modes": mode_values,
            "geopolitical_modes_state": mode_state,
            "china_national_stance": china,
            "us_national_stance": us,
        }
    return output if set(output) == set(expected) else None


def parse_stage1_classifications(
    classifications: Any, expected_brand_ids: Iterable[str], *,
    post_type_keys: Iterable[str] | None = None,
    product_label_keys: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]] | None:
    """Parse a complete current v4 result or a frozen v1--v3 result."""
    if not isinstance(classifications, list) or not classifications:
        return None
    first = classifications[0]
    if isinstance(first, dict) and set(first) == V4_CLASSIFICATION_FIELDS:
        return parse_stage1_v4_classifications(classifications, expected_brand_ids)
    return _parse_legacy_classifications(
        classifications, expected_brand_ids,
        post_type_keys=(post_type_keys or (*STAGE1_TAXONOMY_V3_POST_TYPE_KEYS, *POST_TYPE_KEYS)),
        product_label_keys=(product_label_keys or (*STAGE1_TAXONOMY_V3_PRODUCT_LABEL_KEYS, *PRODUCT_LABEL_KEYS)),
    )
