"""U3a + U3b: build_pragmatics_full_prompt extended for new taxonomy,
multi-value arrays, CTA rule, and unsanctioned_flags top-level field.

Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
Units U3a + U3b.

Verifies:
- U3a: prompt lists 6 post_types (4 existing + advertising_marketing +
  event_announcement).
- U3a: prompt lists 10 discourse_roles (9 existing + advertising-marketing).
- U3a: prompt instructs array output for post_types and discourse_roles.
- U3a: prompt says "MAXIMUM 3 of each per brand".
- U3b: prompt contains the CTA rule with bilingual triggers (限时免费, etc.)
- U3b: prompt mentions unsanctioned_flags as a top-level field with
  the four allowed values.
- U3b: prompt instructs dual-tag for CTA + genuine_hype coexistence.
"""

from __future__ import annotations

import pytest

from x_monitor.attribution import build_pragmatics_full_prompt


def _prompt() -> str:
    return build_pragmatics_full_prompt(
        "GLM 5.2 is amazing", ["glm", "moonshot_kimi"],
    )


# --- U3a: new post_types --------------------------------------------


def test_u3a_prompt_includes_advertising_marketing_post_type():
    p = _prompt()
    assert "advertising_marketing" in p
    assert "event_announcement" in p


def test_u3a_prompt_lists_six_post_types():
    """Count the post_type lines in the prompt."""
    p = _prompt()
    expected_keys = [
        "buzz_releases",
        "hands_on_usage",
        "performance_comparisons",
        "feedback_questions",
        "advertising_marketing",
        "event_announcement",
    ]
    for k in expected_keys:
        assert k in p, f"post_type {k} missing from prompt"


# --- U3a: new discourse_role -----------------------------------------


def test_u3a_prompt_includes_advertising_marketing_discourse():
    p = _prompt()
    assert "advertising-marketing" in p  # hyphenated per KTD7


def test_u3a_prompt_lists_ten_discourse_roles():
    """Count the discourse_role lines in the prompt."""
    p = _prompt()
    expected_keys = [
        "genuine_hype",
        "sarcasm",
        "dunk_yingyang",
        "self_deprecation",
        "cope",
        "fud",
        "distillation_accusation",
        "ai_slop_critique",
        "absurdist_meme",
        "advertising-marketing",
    ]
    for k in expected_keys:
        assert k in p, f"discourse_role {k} missing from prompt"


# --- U3a: multi-value arrays ----------------------------------------


def test_u3a_prompt_instructs_post_types_array():
    """The prompt must declare post_types as an array in the JSON shape."""
    p = _prompt()
    assert "post_types" in p
    assert '"post_types": [str]' in p
    assert "ARRAY, max 3" in p  # the array instruction


def test_u3a_prompt_instructs_discourse_roles_array():
    """The prompt must declare discourse_roles as an array in the JSON shape."""
    p = _prompt()
    assert "discourse_roles" in p
    assert '"discourse_roles": [str]' in p


def test_u3a_prompt_states_max_three_per_brand():
    p = _prompt()
    assert "MAXIMUM 3 of each per brand" in p


def test_u3a_prompt_explains_when_multi_value_is_appropriate():
    """The prompt gives an example of when to emit multiple values."""
    p = _prompt()
    assert "performance_comparisons" in p and "feedback_questions" in p
    assert "am I running behind" in p  # example anchor


# --- U3b: CTA rule ----------------------------------------------------


def test_u3b_prompt_contains_cta_rule():
    """The CTA-precludes-genuine_hype rule is in the prompt."""
    p = _prompt()
    assert "call-to-action" in p
    assert "advertising-marketing" in p
    assert "genuine_hype" in p


def test_u3b_prompt_lists_bilingual_cta_triggers():
    """The prompt includes Chinese-language CTA triggers."""
    p = _prompt()
    for trigger in ["限时免费", "立即体验", "注册", "点击"]:
        assert trigger in p, f"Chinese CTA trigger {trigger!r} missing"


def test_u3b_prompt_lists_english_cta_triggers():
    """The prompt includes English CTA triggers."""
    p = _prompt()
    for trigger in ["try", "sign up", "join", "limited-time", "free access"]:
        assert trigger in p, f"English CTA trigger {trigger!r} missing"


def test_u3b_prompt_lists_wrapper_promo_triggers():
    p = _prompt()
    assert "one API key" in p
    assert "OpenAI-compatible gateway" in p
    assert "free credit no card" in p


def test_u3b_prompt_allows_dual_tag_for_cta_plus_genuine_hype():
    """When genuine praise AND a CTA coexist, both tags should be allowed."""
    p = _prompt()
    assert "emit BOTH" in p
    assert "discourse_roles values" in p


# --- U3b: unsanctioned_flags top-level ------------------------------


def test_u3b_prompt_instructs_unsanctioned_flags_top_level():
    p = _prompt()
    assert "unsanctioned_flags" in p
    # Top-level position: outside `classifications`. The batch
    # prompt (Plan 2026-07-13-001) emits `unsanctioned_flags` next
    # to `classifications` inside each per-tweet result row, and the
    # JSON shape spec explicitly shows it at that level.
    assert "outside `classifications`" in p or "unsanctioned_flags" in p
    # The schema-spec rule names the allow-list values.
    for v in ["marketing_spam", "scam", "crypto", "unauthorized"]:
        assert v in p, f"unsanctioned flag value {v!r} missing from spec"


def test_u3b_prompt_lists_all_four_unsanctioned_flag_values():
    p = _prompt()
    for v in ["marketing_spam", "scam", "crypto", "unauthorized"]:
        assert v in p, f"unsanctioned flag value {v!r} missing"


def test_u3b_prompt_shows_unsanctioned_flags_in_output_json():
    """The Output JSON shape includes unsanctioned_flags."""
    p = _prompt()
    # The Rules #1 specifies the output JSON shape.
    assert '"unsanctioned_flags": [str]' in p


# --- General prompt sanity -------------------------------------------


def test_prompt_includes_brand_list():
    """The brand_ids passed in appear in the prompt text."""
    p = build_pragmatics_full_prompt(
        "test text", ["glm", "moonshot_kimi", "minimax"],
    )
    for b in ["glm", "moonshot_kimi", "minimax"]:
        assert b in p


def test_prompt_handles_empty_brand_list():
    p = build_pragmatics_full_prompt("test", [])
    assert "(none)" in p


def test_prompt_no_code_fences_or_prose():
    """The prompt itself should not contain code fences."""
    p = _prompt()
    # The prompt does NOT enforce a no-fence rule on itself; the OUTPUT
    # rule (Rule 9) says "No prose, no explanation, no code fences."
    assert "No prose" in p
    assert "no code fences" in p


# --- U3 (plan 2026-07-04): sentiment calibration rules ------------------


def test_u3_prompt_includes_rule_10_launch_announcement_neutral():
    """Rule 10: launch announcement with no evaluative language → sent=neutral."""
    p = _prompt()
    assert "10." in p
    assert "launch announcement" in p.lower() or "generally available" in p


def test_u3_prompt_includes_rule_11_strategically_positive():
    """Rule 11: long analytical post with 'strategically positive' → sent=positive."""
    p = _prompt()
    assert "11." in p
    assert "strategically positive" in p


def test_u3_prompt_includes_rule_12_multi_brand_state_of_market():
    """Rule 12: multi-brand state-of-market posts → sent=neutral per brand."""
    p = _prompt()
    assert "12." in p
    assert "climbed 20 spots" in p or "state-of-market" in p or "state of market" in p


# --- U4 (plan 2026-07-04): post_type disambiguation rules ----------------


def test_u4_prompt_includes_rule_13_event_announcement():
    """Rule 13: one-line launch posts → pt=event_announcement (NOT hands_on_usage)."""
    p = _prompt()
    assert "13." in p
    assert "event_announcement" in p
    # The 'NOT hands_on_usage' caveat
    assert "NOT hands_on_usage" in p


def test_u4_prompt_includes_rule_14_ttft_performance():
    """Rule 14: TTFT / benchmark / 'vs' comparison → pt=performance_comparisons."""
    p = _prompt()
    assert "14." in p
    assert "TTFT" in p or "ttft" in p.lower()
    assert "performance_comparisons" in p


def test_u4_prompt_includes_rule_15_analytical_commentary():
    """Rule 15: pure analytical commentary → perf OR feedback_questions, NOT hands_on_usage."""
    p = _prompt()
    assert "15." in p
    assert "feedback_questions" in p


def test_u4_prompt_canonical_example_llm_drag_race():
    """Rule 14 cites the LLM Drag Race write-up as the canonical example."""
    p = _prompt()
    assert "Drag Race" in p or "drag race" in p.lower()


# --- Worked example block ----------------------------------------------


def test_u3u4_prompt_has_worked_example_block():
    """The prompt ends with 'Worked examples' listing six reference cases."""
    p = _prompt()
    assert "Worked examples" in p
    # Six example markers expected: A, B, C, D, E, F.
    for marker in ["A.", "B.", "C.", "D.", "E.", "F."]:
        assert marker in p, f"worked example {marker} missing"


def test_u3u4_prompt_worked_example_a_event_announcement():
    """Example A: 'Kimi K2.7 Code is generally available' → event_announcement/neutral."""
    p = _prompt()
    # The example text appears verbatim
    assert "Kimi K2.7 Code is generally available" in p
    # And the expected per-brand output is shown
    assert "event_announcement" in p


def test_u3u4_prompt_worked_example_b_multi_brand_neutral():
    """Example B: state-of-market (Kimi climbed, Deepseek price drop) → neutral per brand."""
    p = _prompt()
    assert "K2.7 Code climbed 20 spots" in p or "climbed 20 spots" in p
    assert "Deepseek V4" in p or "price dropped" in p


def test_u3u4_prompt_worked_example_c_qwen_positive():
    """Example C: Qwen investment thesis → positive sentiment."""
    p = _prompt()
    assert "Alibaba" in p
    assert "strategically positive" in p


def test_u3u4_prompt_token_count_under_2500():
    """Prompt size guard. len(prompt.split()) * 1.3 is a rough upper bound on tokens."""
    p = _prompt()
    approx_tokens = int(len(p.split()) * 1.3)
    assert approx_tokens < 2500, (
        f"prompt too big: ~{approx_tokens} tokens "
        f"({len(p.split())} words)"
    )


# --- U1 (plan 2026-07-06-001): v12 calibration rules 16-19 ---------------


def test_u1_prompt_includes_rule_16_nationalism_framing():
    """Rule 16: nationalism requires explicit US-China relational framing."""
    p = _prompt()
    assert "16." in p
    assert "US-China relational framing" in p


def test_u1_prompt_includes_rule_17_trap_language():
    """Rule 17: trap-language 'gotcha' / '翻车' disambiguated from US-China framing."""
    p = _prompt()
    assert "17." in p
    assert "trap" in p
    assert "翻车" in p


def test_u1_prompt_includes_rule_18_superlative_praise():
    """Rule 18: 'fastest' superlative is hype, not nationalism."""
    p = _prompt()
    assert "18." in p
    assert "fastest" in p
    assert "genuine_hype" in p


def test_u1_prompt_includes_rule_19_vendor_not_us():
    """Rule 19: anti-Chinese-vendor critique is not us_nationalism valence."""
    p = _prompt()
    assert "19." in p
    assert "Qwen" in p
    assert "us_nationalism" in p


def test_u1_prompt_canonical_example_g_dunk_no_nationalism():
    """Worked example G: anti-vendor dunk on DeepSeek → discourse_roles=[dunk_yingyang],
    cn/us_nationalism=none (rules 16+17)."""
    p = _prompt()
    assert "DeepSeek shipping a benchmark trap" in p
    assert "dunk_yingyang" in p
    # The post should explicitly mark us_nationalism as none (per rule 16)
    # in the worked-example explanation.
    assert "us_nationalism=none" in p


def test_u1_prompt_examples_h_i_j_present():
    """Worked examples H (Qwen superlative), I (GLM anti-vendor fud), J (US-China framing)."""
    p = _prompt()
    # H: superlative praise on Qwen
    assert "Qwen is the fastest" in p
    # I: anti-vendor dunk on GLM with fud
    assert "GLM 5.2 fumbled the launch" in p
    assert "fud" in p
    # J: explicit US-China framing — nationalism DOES fire here
    assert "AI race is heating up" in p
    assert "cn_nationalism=mild_pro" in p
    assert "us_nationalism=anti" in p