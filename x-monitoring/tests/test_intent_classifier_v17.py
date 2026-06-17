# {{AGENT_ATTRIBUTION}}
"""v1.7 tests for x_monitor.intent_classifier: attribute_to_brand fast-path.

v1.7 widens the fetch from 6-14 calls/cycle down to 2 calls/cycle. The
brand-wide Call B returns ~50-200 tweets from non-list accounts. v1.6's
attribute_to_brand loops over all brand tokens for every tweet (~4,200
iterations/cycle at the 7-brand baseline). v1.7 adds a compiled-regex
fast-path: a single re.compile(r"\b(?:MiniMax|海螺|Hailuo|...)") built
once per cycle from all deduped brand tokens, used when no author-handle
match fires.

These tests verify the public API of attribute_to_brand:
  - Legacy (no compiled pattern) behavior is preserved
  - Fast-path returns the same brand as legacy for the same inputs
  - Fast-path handles CJK and ASCII tokens in a single alternation
  - Fast-path preserves brand iteration order (first-match-wins)
  - Fast-path with empty token list returns None (no crash)
  - A None compiled pattern is equivalent to legacy
"""

from __future__ import annotations

import re

import pytest


# --- v1.7 fixtures: brand tokens and staff handles ----------------------


V17_BRAND_TOKENS = {
    "minimax":       ["MiniMax", "海螺", "Hailuo"],
    "qwen":          ["Qwen", "通义千问", "通义"],
    "deepseek":      ["DeepSeek", "深度求索"],
    "glm":           ["GLM", "智谱", "ChatGLM"],
    "xiaomi_mimo":   ["MiMo", "Xiaomi MiMo", "小米 MiMo"],
    "moonshot_kimi": ["Kimi", "Moonshot", "月之暗面"],
    "inclusionai":   ["InclusionAI", "Ling", "Ring", "Ming"],
}

V17_STAFF_HANDLES = {
    "minimax":       ["kimi_devs", "MiniMax_AI", "hailuo_ai"],
    "qwen":          ["Alibaba_Qwen"],
    "moonshot_kimi": ["Kimi_Moonshot"],
}


def _is_cjk(token: str) -> bool:
    """Return True if the token contains any CJK Unified Ideograph."""
    return any("一" <= ch <= "鿿" for ch in token)


def _build_compiled_brand_pattern(
    brand_tokens: dict[str, list[str]],
) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    """Build a single alternation regex over all deduped brand tokens.

    This is the helper that the v1.7 attribute_to_brand fast-path uses.
    It is also exposed publicly so callers (run.py) can build the
    pattern once per cycle and pass it to attribute_to_brand via the
    `compiled_brand_pattern` kwarg.

    The regex alternation preserves brand iteration order (NOT
    alphabetical) so the first-match-wins contract from v1.6 holds.
    CJK tokens use substring (no \\b); ASCII tokens use word boundary.
    A token→brand lookup is returned alongside the pattern so the
    caller can map a match back to its brand.

    Returns (None, {}) when brand_tokens is empty.
    """
    from x_monitor.intent_classifier import _is_cjk as _icjk

    parts: list[str] = []
    token_to_brand: dict[str, str] = {}
    for brand, toks in brand_tokens.items():
        for tok in toks:
            if tok in token_to_brand:
                # Dedup: keep the FIRST brand seen for each token.
                continue
            token_to_brand[tok] = brand
            if _icjk(tok):
                parts.append(re.escape(tok))
            else:
                parts.append(r"\b" + re.escape(tok) + r"\b")
    if not parts:
        return None, {}
    return re.compile("|".join(parts), re.IGNORECASE), token_to_brand


# --- v1.7 attribute_to_brand fast-path tests ---------------------------


def test_v17_attribute_to_brand_accepts_compiled_pattern_kwarg():
    """v1.7 attribute_to_brand must accept `compiled_brand_pattern` and
    `token_to_brand` kwargs. v1.6's signature raises TypeError on these."""
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern(V17_BRAND_TOKENS)
    # If this raises TypeError, the v1.7 fast-path is not implemented.
    brand = attribute_to_brand(
        "Qwen is amazing",
        author_handle="random_user",
        brand_tokens=V17_BRAND_TOKENS,
        staff_handles={},
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand == "qwen"


def test_v17_fast_path_returns_brand_for_cjk_token():
    """海螺 (minimax CJK token) should match and return 'minimax'."""
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern(V17_BRAND_TOKENS)
    brand = attribute_to_brand(
        "海螺AI 太强了",
        author_handle="random_user",
        brand_tokens=V17_BRAND_TOKENS,
        staff_handles={},
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand == "minimax"


def test_v17_fast_path_returns_brand_for_ascii_token():
    """'Qwen' should match the regex and return 'qwen'."""
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern(V17_BRAND_TOKENS)
    brand = attribute_to_brand(
        "I just tried Qwen and it's solid",
        author_handle="random_user",
        brand_tokens=V17_BRAND_TOKENS,
        staff_handles={},
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand == "qwen"


def test_v17_fast_path_word_boundary_does_not_match_substring():
    """'Kimi' as part of 'Kimimania' should NOT match (word boundary)."""
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern(V17_BRAND_TOKENS)
    brand = attribute_to_brand(
        "Kimimania 2024 is happening",
        author_handle="random_user",
        brand_tokens=V17_BRAND_TOKENS,
        staff_handles={},
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand is None, (
        f"word boundary should not match 'Kimi' in 'Kimimania'; got {brand!r}"
    )


def test_v17_fast_path_cjk_substring_does_not_use_word_boundary():
    """CJK tokens match by substring (no \\b), so '通义' inside '通义千问' matches."""
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern(V17_BRAND_TOKENS)
    brand = attribute_to_brand(
        "通义千问 is great",
        author_handle="random_user",
        brand_tokens=V17_BRAND_TOKENS,
        staff_handles={},
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand == "qwen"


def test_v17_fast_path_author_handle_takes_priority():
    """Author handle matching (staff) wins over text-contains matching."""
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern(V17_BRAND_TOKENS)
    # 'Kimi_Moonshot' is in moonshot_kimi's staff list. Tweet text
    # contains 'Qwen' but author is Kimi_Moonshot — moonshot_kimi wins.
    brand = attribute_to_brand(
        "Qwen is also great",
        author_handle="Kimi_Moonshot",
        brand_tokens=V17_BRAND_TOKENS,
        staff_handles=V17_STAFF_HANDLES,
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand == "moonshot_kimi", (
        f"author_handle must take priority; got {brand!r}"
    )


def test_v17_fast_path_empty_tokens_returns_none():
    """Empty brand_tokens + no author match returns None (no crash)."""
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern({})
    assert compiled is None
    assert t2b == {}
    brand = attribute_to_brand(
        "anything goes",
        author_handle="random_user",
        brand_tokens={},
        staff_handles={},
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand is None


def test_v17_fast_path_first_match_wins_in_brand_iteration_order():
    """When two brands share a token via the compiled regex, first wins.

    Build a contrived case where 'Fusion' is in BOTH brand_a and
    brand_b, but brand_a comes first. The fast-path must return
    brand_a, not brand_b.
    """
    from x_monitor.intent_classifier import attribute_to_brand

    contrived = {
        "brand_a": ["Fusion", "alpha"],
        "brand_b": ["Fusion", "beta"],
    }
    compiled, t2b = _build_compiled_brand_pattern(contrived)
    assert t2b["Fusion"] == "brand_a", (
        f"dedup must keep first-seen brand for a shared token; got {t2b!r}"
    )
    brand = attribute_to_brand(
        "Fusion is the future",
        author_handle="random_user",
        brand_tokens=contrived,
        staff_handles={},
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand == "brand_a"


def test_v17_fast_path_matches_legacy_for_full_token_set():
    """For a representative sample of inputs, fast-path returns the
    same brand as the legacy Python-loop path (i.e. without the
    compiled_brand_pattern kwarg).

    This is the cross-validation test: any regression in the compiled
    regex (wrong escaping, wrong word-boundary, wrong case-handling)
    will show up as a divergence from the legacy path.
    """
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern(V17_BRAND_TOKENS)
    cases = [
        # (text, author_handle, expected_brand_or_None)
        ("海螺AI 最新版本发布了", "u1", "minimax"),
        ("Qwen-72B is amazing", "u1", "qwen"),
        ("DeepSeek-V3 is open", "u1", "deepseek"),
        ("GLM-4 paper on arxiv", "u1", "glm"),
        ("MiMo 7B is great", "u1", "xiaomi_mimo"),
        ("Kimi k2 paper", "u1", "moonshot_kimi"),
        ("月之暗面 发布新模型", "u1", "moonshot_kimi"),
        ("InclusionAI Ling model", "u1", "inclusionai"),
        # Author-handle priority
        ("Qwen is good", "MiniMax_AI", "minimax"),
        # No match (word-boundary prevents Kimi in Kimimania)
        ("Kimimania 2024", "u1", None),
        # No match
        ("Just a tweet about nothing relevant", "u1", None),
        # Multi-token text — fast-path should pick the first match
        # in the iteration order. miniMax is first in V17_BRAND_TOKENS.
        ("海螺 vs Qwen, which is better?", "u1", "minimax"),
    ]
    for text, author, expected in cases:
        legacy = attribute_to_brand(
            text, author, V17_BRAND_TOKENS, V17_STAFF_HANDLES
        )
        fast = attribute_to_brand(
            text, author, V17_BRAND_TOKENS, V17_STAFF_HANDLES,
            compiled_brand_pattern=compiled,
            token_to_brand=t2b,
        )
        assert legacy == expected, (
            f"legacy disagrees with expected for {text!r}: got {legacy!r}"
        )
        assert fast == expected, (
            f"fast-path disagrees with expected for {text!r}: got {fast!r}"
        )
        assert fast == legacy, (
            f"fast-path/legacy diverge for {text!r}: fast={fast!r} legacy={legacy!r}"
        )


def test_v17_fast_path_handles_case_insensitive_ascii():
    """'QWEN' (uppercase) should match the compiled pattern (re.IGNORECASE)."""
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern(V17_BRAND_TOKENS)
    brand = attribute_to_brand(
        "QWEN is also good",
        author_handle="u1",
        brand_tokens=V17_BRAND_TOKENS,
        staff_handles={},
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand == "qwen"


def test_v17_fast_path_does_not_match_empty_text():
    """Empty text must not raise, must return None (no author match either)."""
    from x_monitor.intent_classifier import attribute_to_brand

    compiled, t2b = _build_compiled_brand_pattern(V17_BRAND_TOKENS)
    brand = attribute_to_brand(
        "",
        author_handle="random_user",
        brand_tokens=V17_BRAND_TOKENS,
        staff_handles={},
        compiled_brand_pattern=compiled,
        token_to_brand=t2b,
    )
    assert brand is None
