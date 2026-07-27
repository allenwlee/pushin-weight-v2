"""Tests for U2 of plan 2026-07-27-003: translation column NULL-without-fallback.

The wire field `text_translated` carries `None` (not a fallback to source
text) when no locale-appropriate translation exists. The template + JS
render literal "NULL" when `text_translated IS None`.

Run against prod via:
  render jobs create pushinweight-web --start-command \\
      "python manage.py test tests.test_translation_null_fallback -v 2"
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from monitor.views import _pick_translation, _serialize_feed_row


# ============================================================================
# Pure-function tests (no DB) for _pick_translation
# ============================================================================


def _post(text="", text_en=None, text_zh_cn=None):
    """Build a SimpleNamespace that quacks like a Post for _pick_translation."""
    return SimpleNamespace(text=text, text_en=text_en, text_zh_cn=text_zh_cn)


class TestPickTranslationZhCn:
    def test_hit_returns_zh_cn(self):
        post = _post(text="english", text_zh_cn="中文")
        out, translated = _pick_translation(post, "zh_cn")
        assert out == "中文"
        assert translated is True

    def test_miss_returns_none_no_fallback(self):
        """The key behavior change: missing zh_cn -> None, NOT 'english'."""
        post = _post(text="english", text_zh_cn=None)
        out, translated = _pick_translation(post, "zh_cn")
        assert out is None
        assert translated is False

    def test_empty_string_returns_none(self):
        post = _post(text="english", text_zh_cn="")
        out, translated = _pick_translation(post, "zh_cn")
        assert out is None
        assert translated is False


class TestPickTranslationEn:
    def test_hit_returns_en(self):
        post = _post(text="source", text_en="English")
        out, translated = _pick_translation(post, "en")
        assert out == "English"
        assert translated is True

    def test_miss_returns_none_no_fallback(self):
        """Even though text='english' is the source, EN-miss must return None."""
        post = _post(text="english", text_en=None)
        out, translated = _pick_translation(post, "en")
        assert out is None
        assert translated is False


class TestPickTranslationOriginal:
    def test_hit_returns_source(self):
        post = _post(text="source")
        out, translated = _pick_translation(post, "original")
        assert out == "source"
        assert translated is False

    def test_miss_returns_none(self):
        post = _post(text=None, text_en=None, text_zh_cn=None)
        out, translated = _pick_translation(post, "original")
        assert out is None
        assert translated is False

    def test_empty_source_returns_none(self):
        post = _post(text="", text_en=None, text_zh_cn=None)
        out, translated = _pick_translation(post, "original")
        assert out is None
        assert translated is False


# ============================================================================
# Serializer wire-shape tests
# ============================================================================


@pytest.mark.django_db
class TestSerializeFeedRowTranslationField:
    def _make_enriched_row(self):
        return {
            "tweet_id": "test_tweet_1",
            "created_at": "2026-07-27T00:00:00+00:00",
            "text": "english source",
            "text_en": None,
            "text_zh_cn": None,
            "like_count": 0,
            "lang_detected": "en",
            "brand_nicknames": [],
            "brands": [],
            "classifications_by_brand": {},
            "account": {"handle": "@test", "role": None, "role_label": "", "followers_count": 0, "followers_pretty": ""},
        }

    def test_zh_cn_miss_emits_null_in_wire(self):
        row = self._make_enriched_row()
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": {}}
        wire = _serialize_feed_row(row, "zh_cn")
        # The wire carries Python None, not a fallback to "english source".
        assert wire["text_translated"] is None
        assert wire["text"] == "english source"  # text stays as source

    def test_en_miss_emits_null_in_wire(self):
        row = self._make_enriched_row()
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": {}}
        wire = _serialize_feed_row(row, "en")
        assert wire["text_translated"] is None
        assert wire["text"] == "english source"

    def test_original_miss_emits_null_in_wire(self):
        row = self._make_enriched_row()
        row["text"] = None
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": {}}
        wire = _serialize_feed_row(row, "original")
        assert wire["text_translated"] is None
        assert wire["text"] is None

    def test_zh_cn_hit_emits_string(self):
        row = self._make_enriched_row()
        row["text_zh_cn"] = "中文翻译"
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": {}}
        wire = _serialize_feed_row(row, "zh_cn")
        assert wire["text_translated"] == "中文翻译"