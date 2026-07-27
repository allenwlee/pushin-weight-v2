"""Tests for U1: _localize_classification_value + {key, label} wire shape.

See plan 2026-07-27-001-feat-zh-cn-classification-labels-plan.md.
Covers R1, R2, R3, R5, R6, R7, R9.

Run against prod via:
  render jobs create pushinweight-web --start-command \
      "python manage.py test tests.test_classification_labels -v 2"
"""

from __future__ import annotations

import pytest

from monitor.views import (
    _build_label_cache,
    _locale_to_lang_codes,
    _localize_classification_value,
    _serialize_feed_row,
)
from core.models import (
    DiscourseLabel,
    DiscourseKey,
    NationalismKey,
    NationalismLabel,
    PostTypeKey,
    PostTypeLabel,
    SentimentKey,
    SentimentLabel,
)


# ============================================================================
# Pure-function tests (no DB)
# ============================================================================


class TestLocaleToLangCodes:
    def test_zh_cn_returns_zh_cn_first(self):
        assert _locale_to_lang_codes("zh_cn") == ("zh-cn", "zh_cn", "zh-hans")

    def test_en_returns_en_only(self):
        assert _locale_to_lang_codes("en") == ("en",)

    def test_original_returns_en_only(self):
        assert _locale_to_lang_codes("original") == ("en",)

    def test_unknown_locale_defaults_to_en(self):
        assert _locale_to_lang_codes("fr") == ("en",)


class TestLocalizeEmptyCache:
    """Helper resolution against an empty cache falls back to the raw key."""

    def test_post_type_zh_cn_miss_returns_key(self):
        out = _localize_classification_value(
            "post_type", "hands_on_usage", "zh_cn", label_cache={}
        )
        assert out == "hands_on_usage"

    def test_en_miss_returns_key(self):
        out = _localize_classification_value(
            "discourse", "sarcasm", "en", label_cache={}
        )
        assert out == "sarcasm"

    def test_none_key_returns_none(self):
        out = _localize_classification_value(
            "post_type", None, "zh_cn", label_cache={}
        )
        assert out is None

    def test_empty_string_key_returns_none(self):
        out = _localize_classification_value(
            "post_type", "", "zh_cn", label_cache={}
        )
        assert out is None

    def test_unknown_family_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown classification family"):
            _localize_classification_value(
                "bogus", "anything", "zh_cn", label_cache={}
            )


# ============================================================================
# Cache-hit tests (no DB; uses a hand-built cache dict)
# ============================================================================


class TestLocalizeHitPrecedence:
    """KTD9: zh-cn takes precedence over zh_cn takes precedence over zh-hans."""

    def test_zh_cn_prefers_zh_cn(self):
        cache = {
            ("post_type", "hands_on_usage", "zh-cn"): "实际使用",
            ("post_type", "hands_on_usage", "zh_cn"): "实际使用体验",
        }
        out = _localize_classification_value(
            "post_type", "hands_on_usage", "zh_cn", cache
        )
        assert out == "实际使用"

    def test_zh_cn_falls_back_to_zh_cn_when_zh_dash_missing(self):
        cache = {
            ("post_type", "hands_on_usage", "zh_cn"): "实际使用体验",
        }
        out = _localize_classification_value(
            "post_type", "hands_on_usage", "zh_cn", cache
        )
        assert out == "实际使用体验"

    def test_zh_cn_falls_back_to_zh_hans(self):
        cache = {
            ("post_type", "hands_on_usage", "zh-hans"): "实际使用简体",
        }
        out = _localize_classification_value(
            "post_type", "hands_on_usage", "zh_cn", cache
        )
        assert out == "实际使用简体"

    def test_en_hit_returns_en_label(self):
        cache = {
            ("sentiment", "positive", "en"): "Positive",
        }
        out = _localize_classification_value(
            "sentiment", "positive", "en", cache
        )
        assert out == "Positive"

    def test_nationalism_zh_cn_hit(self):
        cache = {
            ("nationalism", "none", "zh-cn"): "无",
        }
        out = _localize_classification_value(
            "nationalism", "none", "zh_cn", cache
        )
        assert out == "无"


# ============================================================================
# Build-cache tests (real DB but isolated by label-row uniqueness)
# ============================================================================


@pytest.mark.django_db
class TestBuildLabelCache:
    """_build_label_cache fetches rows by (family, key, lang)."""

    def test_returns_empty_dict_when_no_keys(self):
        cache = _build_label_cache(
            {"post_type": set(), "discourse": set(), "sentiment": set(), "nationalism": set()},
            "zh_cn",
        )
        assert cache == {}

    def test_populates_cache_with_zh_cn_precedence(self):
        # Insert a row under the legacy zh_cn lang; verify it shows up
        # under cache[(family, key, "zh_cn")].
        PostTypeKey.objects.update_or_create(key="test_post_type_k1")
        PostTypeLabel.objects.update_or_create(
            post_type_id="test_post_type_k1",
            lang="zh_cn",
            defaults={"label": "zh_cn_label"},
        )
        cache = _build_label_cache(
            {"post_type": {"test_post_type_k1"}, "discourse": set(), "sentiment": set(), "nationalism": set()},
            "zh_cn",
        )
        assert ("post_type", "test_post_type_k1", "zh_cn") in cache
        assert cache[("post_type", "test_post_type_k1", "zh_cn")] == "zh_cn_label"

    def test_prefers_zh_dash_when_both_present(self):
        PostTypeKey.objects.update_or_create(key="test_post_type_k2")
        PostTypeLabel.objects.update_or_create(
            post_type_id="test_post_type_k2",
            lang="zh_cn",
            defaults={"label": "zh_cn_label"},
        )
        PostTypeLabel.objects.update_or_create(
            post_type_id="test_post_type_k2",
            lang="zh-cn",
            defaults={"label": "zh_dash_label"},
        )
        cache = _build_label_cache(
            {"post_type": {"test_post_type_k2"}, "discourse": set(), "sentiment": set(), "nationalism": set()},
            "zh_cn",
        )
        # Helper uses zh-cn first; build_label_cache stores both, the
        # lookup function chooses zh-cn.
        out = _localize_classification_value(
            "post_type", "test_post_type_k2", "zh_cn", cache
        )
        assert out == "zh_dash_label"


# ============================================================================
# Serializer wire-shape tests (text_original + {key, label} classifications)
# ============================================================================


@pytest.mark.django_db
class TestSerializeFeedRow:
    """Wire shape: classifications emit {key, label}; text_original present."""

    def _make_enriched_row(self) -> dict:
        return {
            "tweet_id": "test_tweet_1",
            "created_at": "2026-07-27T00:00:00+00:00",
            "text": "original English source",
            "text_en": "English translation",
            "text_zh_cn": "中文翻译",
            "like_count": 0,
            "lang_detected": "en",
            "brand_nicknames": [],
            "brands": [],
            "classifications_by_brand": {
                "minimax": {
                    "discourse": ["genuine_hype"],
                    "post_types": ["hands_on_usage"],
                    "sentiments": ["positive"],
                    "cn_nationalism": "none",
                    "us_nationalism": None,
                },
            },
            "account": {"handle": "@test", "role": None, "role_label": "", "followers_count": 0, "followers_pretty": ""},
        }

    def _build_cache(self) -> dict:
        cache = {}
        # Seed keys if not present (idempotent in test DB).
        PostTypeKey.objects.update_or_create(key="hands_on_usage")
        DiscourseKey.objects.update_or_create(key="genuine_hype")
        SentimentKey.objects.update_or_create(key="positive")
        NationalismKey.objects.update_or_create(key="none")
        # Seed labels in zh-cn (current seed).
        PostTypeLabel.objects.update_or_create(post_type_id="hands_on_usage", lang="zh-cn", defaults={"label": "实际使用"})
        DiscourseLabel.objects.update_or_create(discourse_id="genuine_hype", lang="zh-cn", defaults={"label": "真实热度"})
        SentimentLabel.objects.update_or_create(sentiment_id="positive", lang="zh-cn", defaults={"label": "正面"})
        NationalismLabel.objects.update_or_create(nationalism_id="none", lang="zh-cn", defaults={"label": "无"})
        # Seed labels in en.
        PostTypeLabel.objects.update_or_create(post_type_id="hands_on_usage", lang="en", defaults={"label": "Hands-on usage"})
        DiscourseLabel.objects.update_or_create(discourse_id="genuine_hype", lang="en", defaults={"label": "Genuine hype"})
        SentimentLabel.objects.update_or_create(sentiment_id="positive", lang="en", defaults={"label": "Positive"})
        NationalismLabel.objects.update_or_create(nationalism_id="none", lang="en", defaults={"label": "None"})

        for family, key, lang, label in [
            ("post_type", "hands_on_usage", "zh-cn", "实际使用"),
            ("discourse", "genuine_hype", "zh-cn", "真实热度"),
            ("sentiment", "positive", "zh-cn", "正面"),
            ("nationalism", "none", "zh-cn", "无"),
            ("post_type", "hands_on_usage", "en", "Hands-on usage"),
            ("discourse", "genuine_hype", "en", "Genuine hype"),
            ("sentiment", "positive", "en", "Positive"),
            ("nationalism", "none", "en", "None"),
        ]:
            cache[(family, key, lang)] = label
        return cache

    def test_zh_cn_emits_labeled_classifications(self):
        cache = self._build_cache()
        row = self._make_enriched_row()
        row["label_cache_by_locale"] = {"zh_cn": cache, "en": {}}

        wire = _serialize_feed_row(row, "zh_cn")
        cls = wire["classifications"]["minimax"]
        assert cls["post_types"][0] == {"key": "hands_on_usage", "label": "实际使用"}
        assert cls["discourse"][0] == {"key": "genuine_hype", "label": "真实热度"}
        assert cls["sentiments"][0] == {"key": "positive", "label": "正面"}
        assert cls["cn_nationalism"] == {"key": "none", "label": "无"}
        assert cls["us_nationalism"] is None  # None key emits None

    def test_en_emits_labeled_classifications(self):
        cache = self._build_cache()
        row = self._make_enriched_row()
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": cache}

        wire = _serialize_feed_row(row, "en")
        cls = wire["classifications"]["minimax"]
        assert cls["post_types"][0] == {"key": "hands_on_usage", "label": "Hands-on usage"}
        assert cls["discourse"][0] == {"key": "genuine_hype", "label": "Genuine hype"}
        assert cls["cn_nationalism"] == {"key": "none", "label": "None"}

    def test_empty_cache_returns_raw_keys(self):
        """Miss branch: empty cache => label == key."""
        row = self._make_enriched_row()
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": {}}

        wire = _serialize_feed_row(row, "zh_cn")
        cls = wire["classifications"]["minimax"]
        assert cls["post_types"][0] == {"key": "hands_on_usage", "label": "hands_on_usage"}
        assert cls["cn_nationalism"] == {"key": "none", "label": "none"}

    def test_text_original_prefers_text_zh_cn_under_zh_cn(self):
        row = self._make_enriched_row()
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": {}}
        wire = _serialize_feed_row(row, "zh_cn")
        # text_original = post.text (the source text column is always
        # the original English per R7; the locale-aware translation
        # goes in text_translated).
        assert wire["text_original"] == "original English source"
        assert wire["text"] == "original English source"
        assert wire["text_translated"] == "中文翻译"

    def test_text_original_is_source_under_en(self):
        row = self._make_enriched_row()
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": {}}
        wire = _serialize_feed_row(row, "en")
        assert wire["text_original"] == "original English source"
        # text_translated under en = text_en or fallback to text
        assert wire["text_translated"] == "English translation"

    def test_text_original_is_source_under_original(self):
        row = self._make_enriched_row()
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": {}}
        wire = _serialize_feed_row(row, "original")
        assert wire["text_original"] == "original English source"
        # text_translated under original = post.text (source)
        assert wire["text_translated"] == "original English source"