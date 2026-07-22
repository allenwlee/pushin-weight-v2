"""v12 (plan 2026-07-06-001 U2): _post_process_pragmatics helper tests.

Verifies the parser-layer demotion of post_type='hands_on_usage' to a
more specific type when the raw source text contains a strong marker
for performance_comparisons or event_announcement.

The helper is a pure function (no LLM, no DB, no I/O); these tests
exercise the helper directly without spinning up `_run_post_fetch`.
Integration with `_run_post_fetch` is exercised by the existing
`test_run_post_fetch.py` smoke tests.
"""

from __future__ import annotations

import pytest

from x_monitor.run import _post_process_pragmatics


def _by_brand(post_type: str = "hands_on_usage") -> dict[str, dict[str, str]]:
    return {
        "moonshot_kimi": {
            "post_type": post_type,
            "sentiment": "neutral",
            "discourse_role": "uncategorized",
            "china_nationalism": "none",
            "us_nationalism": "none",
        },
    }


# --- Happy path: demote to event_announcement -------------------------------


def test_happy_path_a_one_line_announcement_demotes_to_event_announcement():
    """Post text 'X is generally available in Y' (180 chars) → event_announcement."""
    text = "Kimi K2.7 Code is generally available in GitHub Copilot"
    out = _post_process_pragmatics(_by_brand(), text)
    assert out["moonshot_kimi"]["post_type"] == "event_announcement"


def test_happy_path_a_demotion_preserves_other_prongs():
    """Demotion only touches post_type — sentiment / discourse_role /
    nationalism are preserved verbatim."""
    text = "Kimi K2.7 Code is generally available in GitHub Copilot"
    out = _post_process_pragmatics(_by_brand(), text)
    prongs = out["moonshot_kimi"]
    assert prongs["sentiment"] == "neutral"
    assert prongs["discourse_role"] == "uncategorized"
    assert prongs["china_nationalism"] == "none"
    assert prongs["us_nationalism"] == "none"


# --- Happy path: demote to performance_comparisons -------------------------


def test_happy_path_b_vs_marker_demotes_to_performance_comparisons():
    """Post text with ' vs ' marker → performance_comparisons."""
    text = "LLM Drag Race: GPT-4o-mini vs Llama 3.3 70B, measure TTFT"
    out = _post_process_pragmatics(_by_brand(), text)
    assert out["moonshot_kimi"]["post_type"] == "performance_comparisons"


def test_benchmark_marker_alone_demotes_to_performance_comparisons():
    """Post text with 'benchmark' alone (no release verb) → performance_comparisons."""
    text = "We benchmarked Kimi K2.7 against Claude 4.7 on coding tasks; results below."
    out = _post_process_pragmatics(_by_brand(), text)
    assert out["moonshot_kimi"]["post_type"] == "performance_comparisons"


# --- Edge cases: no override ----------------------------------------------


def test_edge_case_a_lm_already_correct_post_type_left_alone():
    """If the LLM correctly returned event_announcement, the helper doesn't override."""
    text = "Kimi K2.7 Code is generally available in GitHub Copilot"
    out = _post_process_pragmatics(_by_brand(post_type="event_announcement"), text)
    assert out["moonshot_kimi"]["post_type"] == "event_announcement"


def test_edge_case_b_real_hands_on_usage_text_no_markers():
    """Real hands-on usage post (no release/benchmark markers) → unchanged."""
    text = "I'm using Kimi K2.7 Code to refactor my codebase"
    out = _post_process_pragmatics(_by_brand(), text)
    assert out["moonshot_kimi"]["post_type"] == "hands_on_usage"


def test_edge_case_c_benchmark_and_release_verb_perf_wins():
    """Both a benchmark marker AND a release verb present: performance_comparisons
    wins (plan Edge case C). The order is `perf first, event second`."""
    text = "Kimi K2.7 Code is now live, scored 89% on MMLU benchmark"
    out = _post_process_pragmatics(_by_brand(), text)
    assert out["moonshot_kimi"]["post_type"] == "performance_comparisons"


def test_event_marker_alone_long_text_no_override():
    """An event marker in a >280-char post does NOT demote (length guard)."""
    text = (
        "Kimi K2.7 Code is generally available in GitHub Copilot, "
        "and we wrote a long retrospective covering the rollout, "
        "enterprise adoption patterns, the competitive landscape, "
        "internal team migration paths, the developer ergonomics, "
        "and a careful comparison with prior Copilot history here"
    )
    assert len(text) >= 280
    out = _post_process_pragmatics(_by_brand(), text)
    assert out["moonshot_kimi"]["post_type"] == "hands_on_usage"


# --- Error / null paths ---------------------------------------------------


def test_error_path_a_empty_text_returns_unchanged():
    """Empty text → no override."""
    out = _post_process_pragmatics(_by_brand(), "")
    assert out["moonshot_kimi"]["post_type"] == "hands_on_usage"


def test_error_path_b_empty_by_brand_returns_empty():
    """Empty by_brand → empty out (no error)."""
    assert _post_process_pragmatics({}, "any text here") == {}


# --- Multi-brand integration ---------------------------------------------


def test_multi_brand_only_hands_on_usage_entries_demote():
    """When by_brand has 2 brands and only one has hands_on_usage,
    only that entry demotes; the other stays."""
    text = "Kimi K2.7 Code is generally available in GitHub Copilot"
    by_brand = {
        "moonshot_kimi": {
            "post_type": "hands_on_usage", "sentiment": "neutral",
            "discourse_role": "uncategorized", "china_nationalism": "none",
            "us_nationalism": "none",
        },
        "deepseek": {
            "post_type": "performance_comparisons", "sentiment": "positive",
            "discourse_role": "genuine_hype", "china_nationalism": "none",
            "us_nationalism": "none",
        },
    }
    out = _post_process_pragmatics(by_brand, text)
    assert out["moonshot_kimi"]["post_type"] == "event_announcement"
    # The non-matching brand is untouched.
    assert out["deepseek"]["post_type"] == "performance_comparisons"
    assert out["deepseek"]["sentiment"] == "positive"


def test_synthetic_e2e_five_posts_three_demoted_two_unchanged():
    """5-post synthetic batch: 3 demote, 2 unchanged.

    Mirrors the plan's 'Integration' scenario — verifies the helper
    composition works for mixed input."""
    posts = [
        # (text, original_post_type, expected_post_type)
        (
            "Kimi K2.7 Code is generally available in GitHub Copilot",
            "hands_on_usage", "event_announcement",
        ),
        (
            "LLM Drag Race: GPT-4o-mini vs Llama 3.3 70B, measure TTFT",
            "hands_on_usage", "performance_comparisons",
        ),
        (
            "We benchmarked Kimi against Claude on MMLU; results below.",
            "hands_on_usage", "performance_comparisons",
        ),
        (
            "I'm using Kimi to refactor my codebase; very useful.",
            "hands_on_usage", "hands_on_usage",  # no marker → unchanged
        ),
        (
            "Generic commentary about the AI landscape.",
            "hands_on_usage", "hands_on_usage",  # no marker → unchanged
        ),
    ]
    for text, original, expected in posts:
        out = _post_process_pragmatics(_by_brand(post_type=original), text)
        assert out["moonshot_kimi"]["post_type"] == expected, (
            f"text={text!r} expected {expected}, got {out['moonshot_kimi']['post_type']}"
        )