"""Stage 1 rendering checks for the retired post-fetch smoketest."""

from __future__ import annotations

from scripts.post_fetch_smoketest import _render_sample_posts


def test_renderer_shows_stage1_arrays_without_discourse():
    sample = [{"tweet_id": "111", "text": "GLM benchmark", "author_handle": "u"}]
    translations = [{"tweet_id": "111", "literal_zh": "GLM 基准"}]
    rows = {
        "111": [{
            "brand_id": "glm",
            "outcome": "classified",
            "post_types": ["performance_comparisons", "research_explanations"],
            "product_labels": ["bug", "complaint"],
            "sentiment": "mixed",
            "china_nationalism": None,
            "us_nationalism": "none",
        }]
    }
    output = _render_sample_posts(sample, translations, rows)
    assert "glm outcome=classified" in output
    assert "      - performance_comparisons" in output
    assert "      - research_explanations" in output
    assert "    product_labels:" in output
    assert "      - bug" in output
    assert "      - complaint" in output
    assert "    sentiment=mixed" in output
    assert "    cn=(unknown)" in output
    assert "    us=none" in output
    assert "discourse" not in output


def test_renderer_shows_context_missing_without_fabricated_defaults():
    sample = [{"tweet_id": "222", "text": "What about this?"}]
    rows = {
        "222": [{
            "brand_id": "deepseek",
            "outcome": "context_missing",
            "post_types": [],
            "product_labels": [],
            "sentiment": None,
            "china_nationalism": None,
            "us_nationalism": None,
        }]
    }
    output = _render_sample_posts(sample, [], rows)
    assert "deepseek outcome=context_missing" in output
    assert "types=(none)" in output
    assert "product_labels=(none)" in output
    assert "sentiment=(unknown)" in output
    assert "cn=(unknown)" in output
    assert "us=(unknown)" in output


def test_renderer_keeps_brand_rows_separate_without_cartesian_expansion():
    sample = [{"tweet_id": "333", "text": "GLM and Kimi"}]
    base = {
        "outcome": "classified",
        "post_types": ["performance_comparisons", "feedback_questions"],
        "product_labels": ["product_request"],
        "sentiment": "neutral",
        "china_nationalism": "none",
        "us_nationalism": "none",
    }
    rows = {
        "333": [
            {"brand_id": "glm", **base},
            {"brand_id": "moonshot_kimi", **base},
        ]
    }
    output = _render_sample_posts(sample, [], rows)
    assert output.count("glm outcome=classified") == 1
    assert output.count("moonshot_kimi outcome=classified") == 1


def test_renderer_handles_no_classification_and_unsanctioned_flags():
    sample = [{"tweet_id": "444", "text": "$FAKE", "author_handle": None}]
    output = _render_sample_posts(
        sample, [], {}, unsanctioned_flags={"444": ["crypto", "unauthorized"]}
    )
    assert "types=(none)" in output
    assert "brand_mentions: (none)" in output
    assert "unsanctioned: crypto,unauthorized" in output


def test_renderer_accepts_legacy_scalar_type_and_omits_empty_flags():
    sample = [{"tweet_id": "445", "text": "Hands-on test"}]
    rows = {
        "445": [
            {
                "brand_id": "glm",
                "outcome": "classified",
                "post_type": "hands_on_usage",
                "sentiment": "positive",
                "china_nationalism": "none",
                "us_nationalism": "none",
            }
        ]
    }

    output = _render_sample_posts(
        sample,
        [],
        rows,
        unsanctioned_flags={"445": []},
    )

    assert "  types=hands_on_usage" in output
    assert "    post_types=hands_on_usage" in output
    assert "unsanctioned:" not in output


def test_renderer_ignores_retired_translator_discourse_field():
    sample = [{"tweet_id": "555", "text": "test"}]
    translations = [{"tweet_id": "555", "discourse_role": "genuine_hype"}]
    output = _render_sample_posts(sample, translations, {})
    assert "discourse" not in output


def test_renderer_builds_twitter_url_from_handle():
    output = _render_sample_posts(
        [{"tweet_id": "abc123", "text": "x", "author_handle": "alice"}], [], {}
    )
    assert "url=https://x.com/alice/status/abc123" in output


def test_renderer_uses_explicit_missing_handle_fallback():
    for handle in (None, ""):
        output = _render_sample_posts(
            [{"tweet_id": "xyz", "text": "x", "author_handle": handle}], [], {}
        )
        assert "url=https://x.com/(no handle)/status/xyz" in output
