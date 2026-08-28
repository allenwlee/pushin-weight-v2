"""Shared persisted-output policy for durable post enrichment."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.db.models import F, Q
from django.db.models.functions import Lower, Trim
from django.db.models.lookups import Exact

CANONICAL_LANG_CODES = frozenset(
    {"en", "zh-Hans", "zh-Hant", "ja", "ko", "other"}
)

ENRICHMENT_COUNT_KEYS = (
    "n_enrichment_claimed",
    "n_enrichment_claimed_current_cycle",
    "n_enrichment_claimed_carryover",
    "n_enrichment_succeeded",
    "n_enrichment_succeeded_current_cycle",
    "n_enrichment_succeeded_carryover",
    "n_enrichment_pending",
    "n_enrichment_pending_current_cycle",
    "n_enrichment_pending_carryover",
    "n_enrichment_failed",
    "n_enrichment_failed_current_cycle",
    "n_enrichment_failed_carryover",
    "n_enrichment_deferred",
    "n_enrichment_quarantined",
)

_STAGE_STATUSES = frozenset({"pending", "succeeded", "failed"})


def present_text(value: Any) -> str | None:
    """Return normalized meaningful text, excluding translator sentinels."""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or normalized.casefold() in {"n/a", "na"}:
        return None
    return normalized


def commentary_is_distinct(value: Any, *source_values: Any) -> bool:
    """Require commentary to add text beyond source and translation fields."""

    commentary = present_text(value)
    if commentary is None:
        return False
    folded = commentary.casefold()
    return all(
        folded != source.casefold()
        for candidate in source_values
        if (source := present_text(candidate)) is not None
    )


def persisted_output_complete(
    *,
    source_text: Any,
    lang_detected: Any,
    text_en: Any,
    text_zh_cn: Any,
    commentary_en: Any,
    commentary_zh_cn: Any,
) -> bool:
    """Return whether all durable bilingual output is canonical and genuine."""

    lang = present_text(lang_detected)
    outputs_present = all(
        present_text(value) is not None
        for value in (text_en, text_zh_cn, commentary_en, commentary_zh_cn)
    )
    if lang not in CANONICAL_LANG_CODES or not outputs_present:
        return False
    comparison_values = (source_text, text_en, text_zh_cn)
    return commentary_is_distinct(
        commentary_en, *comparison_values, commentary_zh_cn
    ) and commentary_is_distinct(
        commentary_zh_cn, *comparison_values, commentary_en
    )


def post_persisted_output_complete(post: Any) -> bool:
    """Scalar policy adapter for a Post-like object."""

    return persisted_output_complete(
        source_text=post.text,
        lang_detected=post.lang_detected,
        text_en=post.text_en,
        text_zh_cn=post.text_zh_cn,
        commentary_en=post.commentary_en,
        commentary_zh_cn=post.commentary_zh_cn,
    )


def enrichment_stage_outcome(
    *, translation_status: Any, classification_status: Any
) -> str:
    """Collapse the two durable stage states into one safe outcome."""

    statuses = (translation_status, classification_status)
    if any(status not in _STAGE_STATUSES for status in statuses):
        raise ValueError("invalid enrichment stage status")
    if "failed" in statuses:
        return "failed"
    if statuses == ("succeeded", "succeeded"):
        return "succeeded"
    return "pending"


def enrichment_fact_terminal_complete(fact: Mapping[str, Any]) -> bool:
    """Return whether a redacted per-post fact proves durable completion."""

    try:
        outcome = enrichment_stage_outcome(
            translation_status=fact.get("translation_status"),
            classification_status=fact.get("classification_status"),
        )
    except ValueError:
        return False
    return outcome == "succeeded" and fact.get("output_complete") is True


def _field(prefix: str, name: str) -> str:
    return f"{prefix}{name}"


def _present_text_q(field_name: str) -> Q:
    return (
        Q(**{f"{field_name}__isnull": False})
        & ~Q(**{f"{field_name}__regex": r"^\s*$"})
        & ~Q(**{f"{field_name}__iregex": r"^\s*n/?a\s*$"})
    )


def _normalized_exact_q(left: str, right: str) -> Q:
    return Q(
        Exact(
            Lower(Trim(F(left))),
            Lower(Trim(F(right))),
        )
    )


def _commentary_distinct_q(commentary: str, source: str) -> Q:
    return ~(_present_text_q(source) & _normalized_exact_q(commentary, source))


def persisted_output_complete_q(*, prefix: str = "") -> Q:
    """ORM predicate equivalent to :func:`persisted_output_complete`.

    ``prefix`` lets callers apply the Post policy through a relation, for
    example ``prefix="post__"`` from ``PostEnrichmentState``.
    """

    source = _field(prefix, "text")
    lang = _field(prefix, "lang_detected")
    text_en = _field(prefix, "text_en")
    text_zh_cn = _field(prefix, "text_zh_cn")
    commentary_en = _field(prefix, "commentary_en")
    commentary_zh_cn = _field(prefix, "commentary_zh_cn")
    canonical_lang = Q(
        **{
            f"{lang}__regex": (
                r"^\s*(en|zh-Hans|zh-Hant|ja|ko|other)\s*$"
            )
        }
    )
    required = (
        canonical_lang
        & _present_text_q(text_en)
        & _present_text_q(text_zh_cn)
        & _present_text_q(commentary_en)
        & _present_text_q(commentary_zh_cn)
    )
    distinct = Q()
    for commentary in (commentary_en, commentary_zh_cn):
        for comparison in (source, text_en, text_zh_cn):
            distinct &= _commentary_distinct_q(commentary, comparison)
    distinct &= _commentary_distinct_q(commentary_en, commentary_zh_cn)
    return required & distinct
