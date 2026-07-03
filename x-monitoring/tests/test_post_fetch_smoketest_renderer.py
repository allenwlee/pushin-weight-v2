"""U7: smoketest runner update — multi-discourse + unsanctioned flags output.

Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
Unit U7.

Verifies:
- _render_sample_posts handles multi-value post_types[] / discourse_roles[]
  arrays by expanding into N rows per brand.
- _render_sample_posts surfaces unsanctioned flags per post when present.
- _render_sample_posts renders `discourse: <comma-joined>` when
  discourse_role is an array.
- Backwards compat: legacy scalar post_type / discourse_role values
  still render correctly.
"""

from __future__ import annotations

from scripts.post_fetch_smoketest import _render_sample_posts


def test_u7_renders_one_line_per_brand_with_scalar_fields():
    """Legacy shape: scalar post_type + scalar discourse_role."""
    sample = [
        {"tweet_id": "111", "id": "111", "text": "GLM 5.2 真棒"},
    ]
    trans = [
        {"tweet_id": "111", "text_en": None, "text_zh_cn": "GLM 5.2 真棒",
         "literal_zh": "GLM 5.2 真棒", "discourse_role": "genuine_hype",
         "cn_equivalent": "GLM 5.2 真棒", "annotation": "(none)"},
    ]
    class_rows = {
        "111": [
            {"brand_id": "glm", "post_type": "hands_on_usage",
             "sentiment": "positive", "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    assert "[brand=glm]" in out
    assert "pt=hands_on_usage" in out
    assert "disc=genuine_hype" in out


def test_u7_renders_n_lines_for_multi_post_types():
    """2 post_types × 1 discourse = 2 lines for the same brand."""
    sample = [{"tweet_id": "222", "id": "222", "text": "GLM vs Kimi?"}]
    trans = [{"tweet_id": "222", "literal_zh": "GLM vs Kimi?",
              "discourse_role": "self_deprecation"}]
    class_rows = {
        "222": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons", "feedback_questions"],
             "sentiment": "neutral",
             "discourse_roles": ["self_deprecation"],
             "china_nationalism": "mild_pro", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    # Count occurrences of the brand line.
    n_lines = out.count("[brand=glm]")
    assert n_lines == 2, (
        f"expected 2 lines for 2 post_types; got {n_lines}\n{out}"
    )
    assert "pt=performance_comparisons" in out
    assert "pt=feedback_questions" in out


def test_u7_renders_n_lines_for_multi_discourse_roles():
    """1 post_type × 2 discourse_roles = 2 lines."""
    sample = [{"tweet_id": "333", "id": "333", "text": "GLM is great"}]
    trans = [{"tweet_id": "333", "literal_zh": "GLM 太棒了",
              "discourse_role": ["genuine_hype", "advertising-marketing"]}]
    class_rows = {
        "333": [
            {"brand_id": "glm",
             "post_types": ["hands_on_usage"],
             "sentiment": "positive",
             "discourse_roles": ["genuine_hype", "advertising-marketing"],
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    n_lines = out.count("[brand=glm]")
    assert n_lines == 2
    assert "disc=genuine_hype" in out
    assert "disc=advertising-marketing" in out


def test_u7_renders_cartesian_expansion():
    """2 post_types × 2 discourse_roles = 4 lines."""
    sample = [{"tweet_id": "444", "id": "444", "text": "complex post"}]
    trans = [{"tweet_id": "444", "literal_zh": "复杂 post"}]
    class_rows = {
        "444": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons", "feedback_questions"],
             "sentiment": "mixed",
             "discourse_roles": ["genuine_hype", "advertising-marketing"],
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    n_lines = out.count("[brand=glm]")
    assert n_lines == 4


def test_u7_surfaces_unsanctioned_flags_for_post():
    """When a post has unsanctioned flags, render them in the output."""
    sample = [{"tweet_id": "555", "id": "555", "text": "$GLM $NUSD scam"}]
    trans = [{"tweet_id": "555", "literal_zh": "假"}]
    class_rows = {}  # no classifications
    flags = {"555": ["marketing_spam", "crypto", "unauthorized"]}
    out = _render_sample_posts(sample, trans, class_rows, flags)
    assert "unsanctioned:" in out
    assert "marketing_spam" in out
    assert "crypto" in out
    assert "unauthorized" in out


def test_u7_no_unsanctioned_line_when_empty():
    """When a post has no unsanctioned flags, no 'unsanctioned:' line."""
    sample = [{"tweet_id": "666", "id": "666", "text": "normal post"}]
    trans = [{"tweet_id": "666", "literal_zh": "normal"}]
    class_rows = {}
    out = _render_sample_posts(sample, trans, class_rows)
    assert "unsanctioned:" not in out


def test_u7_discourse_role_array_comma_joined():
    """When discourse_role is an array in the translation row, join with commas."""
    sample = [{"tweet_id": "777", "id": "777", "text": "test"}]
    trans = [{
        "tweet_id": "777",
        "literal_zh": "test",
        "discourse_role": ["genuine_hype", "advertising-marketing"],
    }]
    out = _render_sample_posts(sample, trans, {})
    # The "discourse:" line should show comma-joined values.
    assert "discourse:   genuine_hype,advertising-marketing" in out


def test_u7_empty_discourse_role_defaults_to_uncategorized():
    """Empty array → 'uncategorized' literal."""
    sample = [{"tweet_id": "888", "id": "888", "text": "test"}]
    trans = [{"tweet_id": "888", "literal_zh": "test",
              "discourse_role": []}]
    out = _render_sample_posts(sample, trans, {})
    assert "discourse:   uncategorized" in out


def test_u7_backwards_compat_legacy_scalar_discourse():
    """Legacy scalar discourse_role string still renders correctly."""
    sample = [{"tweet_id": "999", "id": "999", "text": "test"}]
    trans = [{"tweet_id": "999", "literal_zh": "test",
              "discourse_role": "genuine_hype"}]
    out = _render_sample_posts(sample, trans, {})
    assert "discourse:   genuine_hype" in out
    assert "genuine_hype," not in out  # no spurious comma


def test_u7_multiple_brands_render_separately():
    """Two brands each with arrays → both render their rows."""
    sample = [{"tweet_id": "aa1", "id": "aa1", "text": "GLM + Kimi"}]
    trans = [{"tweet_id": "aa1", "literal_zh": "GLM + Kimi"}]
    class_rows = {
        "aa1": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons"],
             "sentiment": "positive",
             "discourse_roles": ["genuine_hype"],
             "china_nationalism": "none", "us_nationalism": "none"},
            {"brand_id": "moonshot_kimi",
             "post_types": ["performance_comparisons"],
             "sentiment": "mixed",
             "discourse_roles": ["self_deprecation"],
             "china_nationalism": "mild_pro", "us_nationalism": "none"},
        ],
    }
    out = _render_sample_posts(sample, trans, class_rows)
    assert out.count("[brand=glm]") == 1
    assert out.count("[brand=moonshot_kimi]") == 1
    assert "disc=genuine_hype" in out
    assert "disc=self_deprecation" in out