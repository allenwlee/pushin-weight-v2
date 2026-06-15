# {{AGENT_ATTRIBUTION}}
"""Post-fetch classification for the v1.6 OR-collapsed pipeline.

In the v1.5 architecture, every tweet carried a `source_query_id` (Q1-Q6)
that came for free from the per-query loop: the Q1 call returned release
tweets, the Q3 call returned criticism tweets, etc. In v1.6 we collapse
calls across brands (one account call per brand; 1-3 bucketed intent
calls across all brands), so the per-tweet signal + brand have to be
recovered from the text content after the API call comes back.

Two responsibilities:
  - `classify_signal(text)`: deterministic classifier that maps a
    tweet's text to one of the existing 6 signal buckets (release,
    community_question, criticism, commenter_capture, praise, other).
    First-match-wins in priority order.
  - `attribute_to_brand(text, author_handle, ...)`: pick the most likely
    model_id for a tweet, preferring author_handle membership in a
    brand's official/staff list, then text-contains of brand tokens
    (ASCII word-boundary, CJK substring).

Both functions are pure-Python + deterministic + unit-testable. They
run on every returned tweet of every intent call; total cost is
sub-millisecond per batch.
"""

from __future__ import annotations

import re
from typing import Literal


Signal = Literal[
    "release",
    "community_question",
    "criticism",
    "commenter_capture",
    "other",
    "praise",
]


# ASCII terms use a word-boundary regex (`\\b`). CJK terms use a plain
# substring match because `\\b` does not anchor correctly between CJK and
# Latin/space characters. Praise-only emoji are handled separately.
_ASCII_SIGNAL_TERMS: dict[str, tuple[str, ...]] = {
    "praise":             ("amazing", "incredible", "love it",
                           "mind-blowing", "mind blowing", "好强"),
    "criticism":          ("broken", "terrible", "worst", "bad", "fail"),
    "community_question": ("how-to", "how do", "tutorial", "guide", "how to"),
    "other":              ("benchmark", "eval", "paper", "github", "repo",
                           "code", "release"),
}
_CJK_SIGNAL_TERMS: dict[str, tuple[str, ...]] = {
    "praise":             ("太强了", "太强", "卧槽", "牛"),
    "criticism":          ("翻车", "不行", "不好", "失望"),
    "community_question": ("教程", "怎么", "如何", "请问"),
    "other":              ("开源",),
}
_PRAISE_EMOJI = "🤯"

# First match wins. Praise > criticism > community_question > other.
_SIGNAL_PRIORITY: tuple[str, ...] = (
    "praise",
    "criticism",
    "community_question",
    "other",
)

# Pre-compile the ASCII word-boundary patterns at import time.
_ASCII_SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    sig: re.compile(
        r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b",
        re.IGNORECASE,
    )
    for sig, terms in _ASCII_SIGNAL_TERMS.items()
    if terms
}


def classify_signal(text: str) -> Signal:
    """Return the best-guess signal for a tweet's text.

    First-match wins in the priority order above. Unrecognized text
    returns "other" as the safe default. Pure-Python (no API), so it's
    free and runs on every returned tweet.
    """
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


def _is_cjk(token: str) -> bool:
    """Return True if the token contains any CJK Unified Ideograph."""
    return any("一" <= ch <= "鿿" for ch in token)


def attribute_to_brand(
    text: str,
    author_handle: str,
    brand_tokens: dict[str, list[str]],
    staff_handles: dict[str, list[str]],
) -> str | None:
    """Pick the most likely model_id for a tweet.

    Priority:
    1. If author_handle is in a brand's official/staff list (casefolded
       equality) -> that brand.
    2. If text contains a brand's tokens (casefolded; ASCII word-boundary,
       CJK substring) -> that brand (first match wins in brand_tokens
       iteration order).
    3. None if neither matches (caller drops the tweet or routes to review).

    `staff_handles` is a {brand: [handle, ...]} map; for v1.6 the official
    handles are also folded in by the caller. A None for either map is
    treated as empty.
    """
    h = (author_handle or "").casefold()
    for brand, handles in (staff_handles or {}).items():
        for hh in handles:
            if h and h == hh.casefold():
                return brand
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
