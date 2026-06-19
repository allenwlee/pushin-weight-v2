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
    brand_id for a tweet, preferring author_handle membership in a
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


def build_compiled_brand_pattern(
    brand_tokens: dict[str, list[str]],
) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    """Build a single alternation regex over all deduped brand tokens.

    v1.7 fast-path: instead of looping `re.search()` per brand per token
    per tweet (v1.6: ~4,200 iterations/cycle at 7 brands), we compile
    ONE regex that matches any brand token and walk each tweet with
    a single `regex.search()`. The matched text is mapped back to its
    brand via the returned `token_to_brand` lookup.

    The alternation preserves brand iteration order (NOT alphabetical)
    so the first-match-wins contract from v1.6 holds. CJK tokens use
    substring (no \b); ASCII tokens use word boundary. ASCII tokens
    are casefolded at match time via `re.IGNORECASE`.

    Dedup rule: if the same token appears in two brands, the FIRST
    brand in the input iteration order wins. This matches v1.6's
    first-match-wins semantics.

    Returns (None, {}) when `brand_tokens` is empty. The caller
    (typically run.py) passes both back into `attribute_to_brand` as
    the `compiled_brand_pattern` and `token_to_brand` kwargs.

    See docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md
    §"Compiled-regex fast-path for wide-net brand attribution" (Decision 3).
    """
    parts: list[str] = []
    token_to_brand: dict[str, str] = {}
    for brand, toks in brand_tokens.items():
        for tok in toks:
            if tok in token_to_brand:
                # Dedup: keep the FIRST brand seen for each token.
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
    compiled_brand_pattern: re.Pattern[str] | None = None,
    token_to_brand: dict[str, str] | None = None,
) -> str | None:
    """Pick the most likely brand_id for a tweet.

    Priority:
    1. If author_handle is in a brand's official/staff list (casefolded
       equality) -> that brand.
    2. If text contains a brand's tokens (casefolded; ASCII word-boundary,
       CJK substring) -> that brand (first match wins in brand_tokens
       iteration order).
    3. None if neither matches (caller drops the tweet or routes to review).

    v1.7 fast-path: when `compiled_brand_pattern` and `token_to_brand`
    are both provided, step 2 uses a single `re.search()` over a
    pre-compiled alternation regex instead of looping per brand per
    token. The caller (run.py) builds the pattern once per cycle via
    `build_compiled_brand_pattern(brand_tokens)` and passes it in.
    When either kwarg is None/empty, the legacy Python loop is used
    (unchanged from v1.6) — this preserves backward compatibility for
    tests and any callers that haven't migrated to the fast-path yet.

    `staff_handles` is a {brand: [handle, ...]} map; for v1.6 the official
    handles are also folded in by the caller. A None for either map is
    treated as empty.
    """
    h = (author_handle or "").casefold()
    for brand, handles in (staff_handles or {}).items():
        for hh in handles:
            if h and h == hh.casefold():
                return brand
    # v1.7 fast-path: when a compiled pattern is provided, use it.
    if compiled_brand_pattern is not None:
        if not text:
            return None
        m = compiled_brand_pattern.search(text)
        if m is None:
            return None
        matched_text = m.group(0)
        # Map the matched text back to its brand via token_to_brand.
        # Case-insensitive equality because the regex is re.IGNORECASE.
        if token_to_brand:
            cf = matched_text.casefold()
            for tok, brand in token_to_brand.items():
                if tok.casefold() == cf:
                    return brand
        # Defensive fallback (should not fire if pattern was built
        # by build_compiled_brand_pattern): scan brand_tokens for
        # substring match. This handles the case where a caller
        # constructed the regex by hand and the token_to_brand map
        # was missed.
        for brand, tokens in (brand_tokens or {}).items():
            for tok in tokens:
                if tok and tok in matched_text:
                    return brand
        return None
    # Legacy v1.6 path: per-brand, per-token loop.
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
