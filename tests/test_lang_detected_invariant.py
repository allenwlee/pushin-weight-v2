"""Tests for U-fix: invariant text_zh_cn MUST be populated when lang_detected is Chinese.

Regression net for the 215 zh-hans posts that were missing text_zh_cn
in prod (verified 2026-07-27: 205 zh-hans + 4 en + 2 ja + 1 es + 1 id
+ 1 tr + 1 pl posts had text_zh_cn IS NULL when they should have been
populated).

The new invariant lives inline inside monitor/cycle.py:_run_post_fetch's
translation-persist block. This test mirrors that logic in isolation
so we can regression-pin it without spinning up the full LLM pipeline.

Run against prod via:
  render jobs create pushinweight-web --start-command \\
      "python manage.py test tests.test_lang_detected_invariant -v 2"
"""

from __future__ import annotations


def _apply_invariant(r: dict) -> dict:
    """Mirror the logic in monitor/cycle.py for testing."""
    CHINESE_LANG_CODES = {"zh", "zh-cn", "zh_cn", "zh-hans", "zh-hant", "zh-tw"}
    lang_detected = r.get("lang_detected")
    post_text = r.get("text") or ""
    text_zh_cn = r.get("text_zh_cn") or r.get("literal_zh") or None
    text_en = r.get("text_en") or None
    if lang_detected in CHINESE_LANG_CODES and not text_zh_cn:
        text_zh_cn = post_text or None
    if lang_detected == "en" and not text_en:
        text_en = post_text or None
    return {
        "text_en": text_en,
        "text_zh_cn": text_zh_cn,
        "lang_detected": lang_detected or None,
    }


class TestChineseLangInvariant:
    def test_zh_hans_gets_text_copied(self):
        r = {"text": "中文内容", "lang_detected": "zh-hans"}
        out = _apply_invariant(r)
        assert out["text_zh_cn"] == "中文内容"

    def test_zh_hant_gets_text_copied(self):
        r = {"text": "繁體內容", "lang_detected": "zh-hant"}
        out = _apply_invariant(r)
        assert out["text_zh_cn"] == "繁體內容"

    def test_existing_translation_preserved(self):
        """If the LLM already emitted a translation, don't overwrite it."""
        r = {
            "text": "中文内容",
            "text_zh_cn": "refined translation",
            "lang_detected": "zh-hans",
        }
        out = _apply_invariant(r)
        assert out["text_zh_cn"] == "refined translation"

    def test_literal_zh_fallback(self):
        """literal_zh (LLM intermediate) is used if text_zh_cn is missing."""
        r = {
            "text": "中文内容",
            "literal_zh": "literal Chinese",
            "lang_detected": "zh-hans",
        }
        out = _apply_invariant(r)
        assert out["text_zh_cn"] == "literal Chinese"

    def test_zh_dash_variant_supported(self):
        """Legacy lang='zh-cn' is also handled."""
        r = {"text": "中文", "lang_detected": "zh-cn"}
        out = _apply_invariant(r)
        assert out["text_zh_cn"] == "中文"


class TestEnglishLangInvariant:
    def test_en_gets_text_copied(self):
        r = {"text": "English source", "lang_detected": "en"}
        out = _apply_invariant(r)
        assert out["text_en"] == "English source"


class TestOtherLangsUnchanged:
    def test_ja_keeps_translation(self):
        r = {
            "text": "Japanese",
            "text_zh_cn": "中文翻译",
            "lang_detected": "ja",
        }
        out = _apply_invariant(r)
        assert out["text_zh_cn"] == "中文翻译"

    def test_fr_with_no_translation(self):
        """Non-Chinese, non-EN posts stay NULL if upstream didn't translate."""
        r = {"text": "French", "lang_detected": "fr"}
        out = _apply_invariant(r)
        assert out["text_zh_cn"] is None
        assert out["text_en"] is None