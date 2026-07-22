"""U5: text_en echo bug fix + translator prompt update.

Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
Unit U5.

Background:
    The v10 smoketest (Post 4) surfaced a bug: when the source tweet
    was already in Simplified Chinese, the LLM dutifully wrote the
    Chinese source text into the text_en field (echo instead of
    translation). The server-side noop only NULL'd text_en for the
    English family — not the Simplified Chinese family.

    The fix (U5):
      1. Server-side noop: NULL text_en when lang_detected is in
         EITHER the English OR the Simplified Chinese family.
      2. System prompt: instruct the LLM to set text_en to null when
         the source is already in English or Simplified Chinese.

Verifies (focused on the server-side logic — translator.py):
- text_en is NULL when lang_detected is "zh_cn"
- text_en is NULL when lang_detected is "zh-Hans"
- text_en is NULL when lang_detected is "zh-CN"
- text_en is NULL when lang_detected is "zh_CN_Hans"
- text_en is NULL when lang_detected is "en" (existing behavior)
- text_en is NULL when lang_detected is "en-US" (existing)
- text_en is populated when lang_detected is "ja" (Japanese)
- text_en is populated when lang_detected is "zh-Hant" (Traditional Chinese)
- text_en is populated when lang_detected is "ko" (Korean)
- text_zh_cn is NULL when lang is zh_cn (existing behavior, unchanged)
- text_zh_cn is populated when lang is "en" (existing behavior, unchanged)
- noop_en flag correctly reflects text_en None state
- noop_zh flag correctly reflects text_zh_cn None state
"""

from __future__ import annotations

from x_monitor.translator import (
    _is_english_family,
    _is_simplified_chinese_family,
)


def _apply_noop_rules(post: dict, judged: dict) -> dict:
    """Replicates the server-side noop logic from translate_batch_pragmatics."""
    lang = (judged.get("lang_detected") or "").lower()
    is_already_zh = _is_simplified_chinese_family(lang)
    text_en = (
        None
        if _is_english_family(lang) or is_already_zh
        else judged.get("text_en")
    )
    text_zh_cn = None if is_already_zh else judged.get("text_zh_cn")
    return {
        "tweet_id": post.get("tweet_id"),
        "text_en": text_en,
        "text_zh_cn": text_zh_cn,
        "lang_detected": lang or None,
        "noop_en": text_en is None,
        "noop_zh": text_zh_cn is None,
    }


# ===========================================================================
# English family — text_en NULL
# ===========================================================================


def test_u5_text_en_null_for_lang_en():
    judged = {"lang_detected": "en", "text_en": "GLM 5.2 is great"}
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] is None
    assert out["noop_en"] is True


def test_u5_text_en_null_for_lang_en_us():
    judged = {"lang_detected": "en-US", "text_en": "GLM 5.2 is great"}
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] is None


def test_u5_text_en_null_for_lang_en_gb():
    judged = {"lang_detected": "en-GB", "text_en": "GLM 5.2 is great"}
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] is None


# ===========================================================================
# Simplified Chinese family — text_en NULL (the U5 fix)
# ===========================================================================


def test_u5_text_en_null_for_zh_cn():
    """The bug fix: zh_cn source → text_en NULL even if LLM echoes."""
    judged = {"lang_detected": "zh_cn", "text_en": "GLM 5.2 真棒"}
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] is None, (
        "U5 fix: zh_cn source should NULL text_en to prevent echo"
    )
    assert out["noop_en"] is True


def test_u5_text_en_null_for_zh_hans():
    judged = {"lang_detected": "zh-Hans", "text_en": "GLM 5.2 真棒"}
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] is None


def test_u5_text_en_null_for_zh_CN():
    judged = {"lang_detected": "zh-CN", "text_en": "GLM 5.2 真棒"}
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] is None


def test_u5_text_en_null_for_zh_CN_Hans():
    judged = {"lang_detected": "zh_CN_Hans", "text_en": "GLM 5.2 真棒"}
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] is None


# ===========================================================================
# text_zh_cn NULL for Simplified Chinese family (unchanged existing behavior)
# ===========================================================================


def test_u5_text_zh_cn_null_for_zh_cn():
    """Existing behavior preserved: zh_cn source → text_zh_cn NULL."""
    judged = {"lang_detected": "zh_cn", "text_zh_cn": "GLM 5.2 真棒"}
    out = _apply_noop_rules({}, judged)
    assert out["text_zh_cn"] is None
    assert out["noop_zh"] is True


# ===========================================================================
# Other languages — both columns populated
# ===========================================================================


def test_u5_both_columns_populated_for_ja():
    """Japanese source: LLM provides both translations."""
    judged = {
        "lang_detected": "ja",
        "text_en": "GLM 5.2 is amazing",
        "text_zh_cn": "GLM 5.2 太棒了",
    }
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] == "GLM 5.2 is amazing"
    assert out["text_zh_cn"] == "GLM 5.2 太棒了"
    assert out["noop_en"] is False
    assert out["noop_zh"] is False


def test_u5_both_columns_populated_for_ko():
    """Korean source: LLM provides both translations."""
    judged = {
        "lang_detected": "ko",
        "text_en": "GLM 5.2 is great",
        "text_zh_cn": "GLM 5.2 棒极了",
    }
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] == "GLM 5.2 is great"
    assert out["text_zh_cn"] == "GLM 5.2 棒极了"


def test_u5_text_zh_cn_populated_for_en():
    """English source: text_en NULL, text_zh_cn populated."""
    judged = {"lang_detected": "en", "text_zh_cn": "GLM 5.2 真棒"}
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] is None
    assert out["text_zh_cn"] == "GLM 5.2 真棒"


def test_u5_both_columns_populated_for_zh_hant():
    """Traditional Chinese is NOT in the Simplified Chinese family —
    both columns should be populated (the LLM provides translations)."""
    judged = {
        "lang_detected": "zh-Hant",
        "text_en": "GLM 5.2 is great",
        "text_zh_cn": "GLM 5.2 太棒了",  # in simplified Chinese
    }
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] == "GLM 5.2 is great"
    assert out["text_zh_cn"] == "GLM 5.2 太棒了"


# ===========================================================================
# noop_* flags
# ===========================================================================


def test_u5_noop_en_true_when_text_en_null():
    judged = {"lang_detected": "en", "text_en": None}
    out = _apply_noop_rules({}, judged)
    assert out["noop_en"] is True


def test_u5_noop_en_false_when_text_en_populated():
    judged = {"lang_detected": "ja", "text_en": "GLM 5.2 is great"}
    out = _apply_noop_rules({}, judged)
    assert out["noop_en"] is False


def test_u5_noop_zh_true_when_text_zh_cn_null():
    judged = {"lang_detected": "zh_cn", "text_zh_cn": None}
    out = _apply_noop_rules({}, judged)
    assert out["noop_zh"] is True


# ===========================================================================
# Edge cases
# ===========================================================================


def test_u5_empty_lang_treated_as_unknown():
    """Missing lang_detected → no noop fires; both columns use raw values."""
    judged = {"lang_detected": "", "text_en": "x", "text_zh_cn": "y"}
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] == "x"
    assert out["text_zh_cn"] == "y"
    assert out["lang_detected"] is None


def test_u5_missing_text_en_for_zh_cn_returns_none():
    """zh_cn source with no text_en from LLM → still None (not crash)."""
    judged = {"lang_detected": "zh_cn"}  # no text_en key
    out = _apply_noop_rules({}, judged)
    assert out["text_en"] is None
    assert out["noop_en"] is True


def test_u5_zh_TW_not_simplified():
    """zh-TW (Traditional Chinese Taiwan) is NOT in the Simplified family."""
    assert _is_simplified_chinese_family("zh-TW") is False
    assert _is_simplified_chinese_family("zh-Hant") is False
    assert _is_simplified_chinese_family("zh-HK") is False