# {{AGENT_ATTRIBUTION}}
"""Compat shim for v1.7 `intent_classifier` API surface (R20).

In v1.7, `x_monitor.intent_classifier` owned two responsibilities:
  - `classify_signal(text)` - first-match-wins per-bucket signal map.
  - `attribute_to_brand(text, ...)` - first-match-wins single brand.

In v1.8 the canonical home moved to `x_monitor.attribution`:
  - `classify_signal(text, brand_ids, brand_registry, anthropic_client)`
    now returns a per-brand signal dict (the per-brand decomposition).
  - `attribute_to_brands(...)` returns all detected brands with
    confidence scores.

This shim preserves the v1.7 public API (so legacy callers and tests
still pass) by:
  - Re-exporting the v1.8 names from `attribution` under the v1.7
    names that callers expect (MentionRow, attribute_to_brands,
    compute_post_brands, compile_keyword_index, etc.).
  - Keeping the legacy `classify_signal(text)` (single-string) shim,
    which emits a `DeprecationWarning` on every call directing
    callers to `classify_signal` in `x_monitor.attribution`.
  - Keeping the legacy `attribute_to_brand(text, ...)` (single
    brand) shim which calls the v1.8 `attribute_to_brands` and
    returns the first match (or None).

The legacy `build_compiled_brand_pattern` and `_is_cjk` helpers are
also kept for callers that still use them.

A follow-up commit (not this one) deletes this file once all
callers migrate.
"""

from __future__ import annotations

import re
import warnings


# --- Re-exports from x_monitor.attribution (R20) ------------------------

# The canonical v1.8 names. Tests in test_intent_classifier_v17.py
# import these from `x_monitor.intent_classifier` and assert they
# are the SAME objects as those in `x_monitor.attribution` (so the
# compat shim does not duplicate the dataclass identity).
from x_monitor.attribution import (  # noqa: F401  (re-exports)
    MentionRow,
    BrandRow,
    validate_raw_token,
    compile_keyword_index,
    extract_user_mentions,
    extract_hashtag_mentions,
    extract_body_keywords,
    extract_search_term_match,
    compute_post_brands,
    attribute_to_brands,
    AnthropicClaudeClient,
    BRAND_SOURCE_PRIORITY,
    UNATTRIBUTED_BRAND_ID,
    Source,
    SourceType,
)


# --- Legacy compat: classify_signal (text-only, single bucket) ----------

# Aliases for tests / callers that referenced the original names.
Signal = SourceType


# Legacy v1.7 priority order. Kept here so the legacy `classify_signal`
# body is independent of `attribution.py` (which no longer carries
# these terms).
_ASCII_SIGNAL_TERMS: dict[str, tuple[str, ...]] = {
    "praise":             ("amazing", "incredible", "love it",
                           "mind-blowing", "mind blowing", "好强"),
    "criticism":          ("broken", "terrible", "worst", "bad", "fail"),
    "community_question": ("how-to", "how do", "tutorial", "guide", "how to"),
    "other":              ("benchmark", "eval", "paper", "github", "repo",
                           "code", "release"),
}
_CJK_SIGNAL_TERMS: dict[str, tuple[str, ...]] = {
    "praise":             ("太强了", "太强", "占嘑", "牛"),
    "criticism":          ("翻车", "不行", "不好", "失望"),
    "community_question": ("教程", "怎么", "如何", "请问"),
    "other":              ("开源",),
}
_PRAISE_EMOJI = "\U0001F92F"
_SIGNAL_PRIORITY: tuple[str, ...] = (
    "praise",
    "criticism",
    "community_question",
    "other",
)
_ASCII_SIGNAL_PATTERNS: dict[str, "re.Pattern[str]"] = {
    sig: re.compile(
        r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b",
        re.IGNORECASE,
    )
    for sig, terms in _ASCII_SIGNAL_TERMS.items()
    if terms
}


def classify_signal(text: str) -> str:  # type: ignore[override]
    """Legacy v1.7 single-string signal classifier.

    First-match-wins in `_SIGNAL_PRIORITY`. Returns one of:
      release, community_question, criticism, commenter_capture,
      praise, other.

    .. deprecated::
        v1.8: use `x_monitor.attribution.classify_signal(text, brand_ids,
        brand_registry, anthropic_client)` for the per-brand
        decomposition. This shim remains for callers that don't have
        brand context (ad-hoc rendering, headline classification).
    """
    warnings.warn(
        "x_monitor.intent_classifier.classify_signal is deprecated; "
        "use x_monitor.attribution.classify_signals_per_brand "
        "(or x_monitor.attribution.classify_signal with brand_ids) "
        "for the v1.8 per-brand signal decomposition.",
        DeprecationWarning,
        stacklevel=2,
    )
    if not text:
        return "other"
    for sig in _SIGNAL_PRIORITY:
        pat = _ASCII_SIGNAL_PATTERNS.get(sig)
        if pat and pat.search(text):
            return sig
        for term in _CJK_SIGNAL_TERMS.get(sig, ()):
            if term in text:
                return sig
    if _PRAISE_EMOJI in text:
        return "praise"
    return "other"


# --- Legacy compat: attribute_to_brand (single brand) ------------------


def _is_cjk(token: str) -> bool:
    """Return True if the token contains any CJK Unified Ideograph."""
    return any("一" <= ch <= "鿿" for ch in token)


def build_compiled_brand_pattern(
    brand_tokens: dict[str, list[str]],
) -> "tuple[re.Pattern[str] | None, dict[str, str]]":
    """Build a single alternation regex over all deduped brand tokens.

    Legacy v1.7 helper. Re-implemented here so callers that still
    import `build_compiled_brand_pattern` from
    `x_monitor.intent_classifier` keep working without duplicating
    the logic in `attribution.compile_keyword_index` (which has a
    different signature: `(brand_id, pattern, is_regex)` triples
    loaded from the DB).
    """
    parts: list[str] = []
    token_to_brand: dict[str, str] = {}
    for brand, toks in brand_tokens.items():
        for tok in toks:
            if tok in token_to_brand:
                continue
            token_to_brand[tok] = brand
            if _is_cjk(tok):
                parts.append(re.escape(tok))
            else:
                parts.append(r"\b" + re.escape(tok) + r"\b")
    if not parts:
        return None, {}
    return re.compile("|".join(parts), re.IGNORECASE), token_to_brand


def attribute_to_brand(
    text: str,
    author_handle: str,
    brand_tokens: dict[str, list[str]],
    staff_handles: dict[str, list[str]],
    *,
    compiled_brand_pattern: "re.Pattern[str] | None" = None,
    token_to_brand: "dict[str, str] | None" = None,
) -> str | None:
    """Legacy v1.7 single-brand classifier (compat shim).

    First-match-wins. Returns the brand_id string (e.g. "minimax")
    or None when no brand matches.

    Priority:
      1. author_handle in a brand's staff_handles list.
      2. text contains a brand's token (ASCII word-boundary, CJK
         substring) using the compiled regex fast-path when both
         `compiled_brand_pattern` and `token_to_brand` are provided.
      3. None.

    Kept identical to the v1.7 implementation so existing tests
    (test_intent_classifier_v17.py) pass without modification.
    """
    h = (author_handle or "").casefold()
    for brand, handles in (staff_handles or {}).items():
        for hh in handles:
            if h and h == hh.casefold():
                return brand
    if compiled_brand_pattern is not None:
        if not text:
            return None
        m = compiled_brand_pattern.search(text)
        if m is None:
            return None
        matched_text = m.group(0)
        if token_to_brand:
            cf = matched_text.casefold()
            for tok, brand in token_to_brand.items():
                if tok.casefold() == cf:
                    return brand
        for brand, tokens in (brand_tokens or {}).items():
            for tok in tokens:
                if tok and tok in matched_text:
                    return brand
        return None
    t = (text or "").casefold()
    for brand, tokens in (brand_tokens or {}).items():
        for tok in tokens:
            tt = tok.casefold()
            if not tt:
                continue
            if _is_cjk(tok):
                if tt in t:
                    return brand
            else:
                if re.search(r"\b" + re.escape(tt) + r"\b", t):
                    return brand
    return None


__all__ = [
    # Re-exports from x_monitor.attribution
    "MentionRow",
    "BrandRow",
    "validate_raw_token",
    "compile_keyword_index",
    "extract_user_mentions",
    "extract_hashtag_mentions",
    "extract_body_keywords",
    "extract_search_term_match",
    "compute_post_brands",
    "attribute_to_brands",
    "AnthropicClaudeClient",
    "BRAND_SOURCE_PRIORITY",
    "UNATTRIBUTED_BRAND_ID",
    "Source",
    "SourceType",
    # Legacy compat
    "Signal",
    "classify_signal",
    "attribute_to_brand",
    "build_compiled_brand_pattern",
    "_is_cjk",
]
