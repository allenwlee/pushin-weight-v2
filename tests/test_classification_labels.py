"""Tests for U1: _localize_classification_value + {key, label} wire shape.

See plan 2026-07-27-001-feat-zh-cn-classification-labels-plan.md.
Covers R1, R2, R3, R5, R6, R7, R9.

Run against prod via:
  render jobs create pushinweight-web --start-command \
      "python manage.py test tests.test_classification_labels -v 2"
"""

from __future__ import annotations

import pytest

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    CANONICAL_PRODUCT_LABEL_KEYS,
    NATIONALISM_KEYS,
    SENTIMENT_KEYS,
)
from core.classification_labels import (
    DISCOURSE_LABELS,
    NATIONALISM_LABELS,
    POST_TYPE_LABELS,
    PRODUCT_LABEL_LABELS,
    ROLE_LABELS,
    SENTIMENT_LABELS,
)
from core.models import (
    NationalismKey,
    NationalismLabel,
    PostTypeKey,
    PostTypeLabel,
    ProductLabelKey,
    ProductLabelLabel,
    SentimentKey,
    SentimentLabel,
)
from monitor.views import (
    _build_label_cache,
    _locale_to_lang_codes,
    _localize_classification_value,
    _serialize_feed_row,
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


def test_stage1_label_constants_match_the_frozen_taxonomy():
    active = {
        "post_type": (CANONICAL_POST_TYPE_KEYS, POST_TYPE_LABELS),
        "product_label": (CANONICAL_PRODUCT_LABEL_KEYS, PRODUCT_LABEL_LABELS),
        "sentiment": (SENTIMENT_KEYS, SENTIMENT_LABELS),
        "nationalism": (NATIONALISM_KEYS, NATIONALISM_LABELS),
    }

    assert sum(len(keys) for keys, _ in active.values()) == 25
    for keys, labels_by_key in active.values():
        assert all(set(labels_by_key[key]) == {"en", "zh-cn", "ja"} for key in keys)
        assert all(
            labels_by_key[key][lang].strip()
            for key in keys
            for lang in ("en", "zh-cn", "ja")
        )

    assert all("ja" not in labels for labels in DISCOURSE_LABELS.values())
    assert all("ja" not in labels for labels in ROLE_LABELS.values())


def test_japanese_labels_match_the_reviewed_implementation_copy():
    assert {
        **{key: POST_TYPE_LABELS[key]["ja"] for key in CANONICAL_POST_TYPE_KEYS},
        **{
            key: PRODUCT_LABEL_LABELS[key]["ja"]
            for key in CANONICAL_PRODUCT_LABEL_KEYS
        },
        **{f"sentiment:{key}": SENTIMENT_LABELS[key]["ja"] for key in SENTIMENT_KEYS},
        **{
            f"nationalism:{key}": NATIONALISM_LABELS[key]["ja"]
            for key in NATIONALISM_KEYS
        },
    } == {
        "releases_updates": "リリース・アップデート",
        "hands_on_usage": "使用体験",
        "results_evaluations": "結果・評価",
        "questions_requests": "質問・要望",
        "advertising_marketing": "広告・マーケティング",
        "events_opportunities": "イベント・機会",
        "opinions_reactions": "意見・反応",
        "research_explanations": "研究・解説",
        "business_finance": "ビジネス・金融",
        "other": "その他",
        "bug": "バグ",
        "complaint": "苦情",
        "testimonial": "推奨の声",
        "ideas_requests": "アイデア・要望",
        "misinformation": "誤情報の可能性",
        "sentiment:positive": "ポジティブ",
        "sentiment:negative": "ネガティブ",
        "sentiment:neutral": "中立",
        "sentiment:mixed": "賛否混在",
        "nationalism:none": "なし",
        "nationalism:mild_pro": "控えめな支持",
        "nationalism:pro": "支持",
        "nationalism:constructive_critical": "建設的な批判",
        "nationalism:anti": "反対",
        "nationalism:mixed": "賛否混在",
    }


def test_legacy_alias_labels_remain_english_chinese_only():
    legacy_aliases = {
        "buzz_releases": POST_TYPE_LABELS,
        "performance_comparisons": POST_TYPE_LABELS,
        "feedback_questions": POST_TYPE_LABELS,
        "event_announcement": POST_TYPE_LABELS,
        "product_request": PRODUCT_LABEL_LABELS,
    }

    assert all(
        set(labels[key]) == {"en", "zh-cn"}
        for key, labels in legacy_aliases.items()
    )


@pytest.mark.django_db
def test_seed_command_is_idempotent_for_stage1_product_labels():
    from django.core.management import call_command

    call_command("seed_i18n_labels")
    call_command("seed_i18n_labels")

    assert set(CANONICAL_PRODUCT_LABEL_KEYS).issubset(
        ProductLabelKey.objects.values_list("key", flat=True)
    )
    assert ProductLabelLabel.objects.filter(
        product_label_id__in=CANONICAL_PRODUCT_LABEL_KEYS,
        lang__in=("en", "zh-cn", "ja"),
    ).count() == len(CANONICAL_PRODUCT_LABEL_KEYS) * 3
    assert ProductLabelLabel.objects.filter(lang="ja").count() == len(
        CANONICAL_PRODUCT_LABEL_KEYS
    )
    assert ProductLabelLabel.objects.filter(
        product_label_id="product_request", lang__in=("en", "zh-cn")
    ).count() == 2
    assert not ProductLabelLabel.objects.filter(
        product_label_id="product_request", lang="ja"
    ).exists()


class TestLocalizeEmptyCache:
    """Helper resolution against an empty cache stays user-readable."""

    def test_post_type_zh_cn_miss_returns_canonical_fallback(self):
        out = _localize_classification_value(
            "post_type", "hands_on_usage", "zh_cn", label_cache={}
        )
        assert out == "实际使用"

    def test_en_miss_returns_canonical_fallback(self):
        out = _localize_classification_value(
            "product_label", "bug", "en", label_cache={}
        )
        assert out == "Bug"

    def test_unknown_en_key_is_humanized(self):
        out = _localize_classification_value(
            "product_label", "new_signal", "en", label_cache={}
        )
        assert out == "New Signal"

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
            {
                "post_type": set(),
                "product_label": set(),
                "sentiment": set(),
                "nationalism": set(),
            },
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
            {
                "post_type": {"test_post_type_k1"},
                "product_label": set(),
                "sentiment": set(),
                "nationalism": set(),
            },
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
            {
                "post_type": {"test_post_type_k2"},
                "product_label": set(),
                "sentiment": set(),
                "nationalism": set(),
            },
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
                    "product_labels": ["bug"],
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
        ProductLabelKey.objects.update_or_create(key="bug")
        SentimentKey.objects.update_or_create(key="positive")
        NationalismKey.objects.update_or_create(key="none")
        # Seed labels in zh-cn (current seed).
        PostTypeLabel.objects.update_or_create(post_type_id="hands_on_usage", lang="zh-cn", defaults={"label": "实际使用"})
        ProductLabelLabel.objects.update_or_create(
            product_label_id="bug", lang="zh-cn", defaults={"label": "缺陷"}
        )
        SentimentLabel.objects.update_or_create(sentiment_id="positive", lang="zh-cn", defaults={"label": "正面"})
        NationalismLabel.objects.update_or_create(nationalism_id="none", lang="zh-cn", defaults={"label": "无"})
        # Seed labels in en.
        PostTypeLabel.objects.update_or_create(post_type_id="hands_on_usage", lang="en", defaults={"label": "Hands-on usage"})
        ProductLabelLabel.objects.update_or_create(
            product_label_id="bug", lang="en", defaults={"label": "Bug"}
        )
        SentimentLabel.objects.update_or_create(sentiment_id="positive", lang="en", defaults={"label": "Positive"})
        NationalismLabel.objects.update_or_create(nationalism_id="none", lang="en", defaults={"label": "None"})

        for family, key, lang, label in [
            ("post_type", "hands_on_usage", "zh-cn", "实际使用"),
            ("product_label", "bug", "zh-cn", "缺陷"),
            ("sentiment", "positive", "zh-cn", "正面"),
            ("nationalism", "none", "zh-cn", "无"),
            ("post_type", "hands_on_usage", "en", "Hands-on usage"),
            ("product_label", "bug", "en", "Bug"),
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
        assert cls["product_labels"][0] == {"key": "bug", "label": "缺陷"}
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
        assert cls["product_labels"][0] == {"key": "bug", "label": "Bug"}
        assert cls["cn_nationalism"] == {"key": "none", "label": "None"}

    def test_empty_cache_returns_canonical_fallback_labels(self):
        """Miss branch: empty cache still emits active-locale display copy."""
        row = self._make_enriched_row()
        row["label_cache_by_locale"] = {"zh_cn": {}, "en": {}}

        wire = _serialize_feed_row(row, "zh_cn")
        cls = wire["classifications"]["minimax"]
        assert cls["post_types"][0] == {"key": "hands_on_usage", "label": "实际使用"}
        assert cls["cn_nationalism"] == {"key": "none", "label": "无"}

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
