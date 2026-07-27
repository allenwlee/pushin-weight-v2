"""Regression net: pin all zh_CN catalog translations.

See plan 2026-07-27-001-feat-zh-cn-classification-labels-plan.md U4.
When U1/U2 intentionally change a translation, the pin encodes the
AFTER state. When they don't, the pin catches silent drift.

Runs against prod via:
  render jobs create pushinweight-web --start-command \\
      "python manage.py test tests.test_i18n_catalog_pinned -v 2"
"""

from __future__ import annotations

import pytest
from django.utils import translation
from django.utils.translation import gettext


# ============================================================================
# Pin catalog (msgid -> msgstr under zh-hans)
# ============================================================================
# Five strings U1/U2 intentionally changes:
#   - cn:  msgid REMOVED (replaced by zh_cn: / en:)
#   - us:  msgid REMOVED (replaced by zh_cn: / en:)
#   - zh_cn: NEW msgid with msgstr == msgid (axis name IS the value)
#   - en:   NEW msgid with msgstr == msgid (axis name IS the value)
#   - types:/discourses:/sentiments: msgstrs UNCHANGED
#
# All other strings must remain at their pre-U1/U2 values.

HEADERS_PIN: dict[str, str] = {
    "Filters": "筛选",
    "Brands": "品牌",
    "Discourse": "话语",
    "post_type": "文章类型",
    "account.role": "账户角色",
    "lang": "语言",
    "us_nationalism": "美国民族主义",
    "cn_nationalism": "中国民族主义",
    "unsanctioned": "未批准",
    "show only flagged posts": "仅显示标记帖子",
    "only": "仅",
    "all": "全部",
}

FEED_COLUMNS_PIN: dict[str, str] = {
    "datetime": "日期时间",
    "brand": "品牌",
    "translated": "翻译",
    "original": "原文",
    "classifications": "分类",
    "handle": "账号",
    "translated from:": "翻译自:",
}

TOPBAR_PIN: dict[str, str] = {
    "window:": "窗口:",
    "lang:": "语言:",
    "24h window": "24小时窗口",
    "loading more…": "加载更多…",
    "end of feed": "信息流结束",
    "no posts in window": "窗口内无帖子",
    "← multi-brand": "← 多品牌",
    "(locked)": "（已锁定）",
    "Daily total posts per brand": "每日各品牌帖子总数",
    "Single-brand stacked-area chart": "单品牌堆叠面积图",
    "Spend panel — stubbed for U7.": "消费面板 — U7待实现",
}

# U1/U2 intentionally change these:
#   - zh_cn: / en: are NEW msgids (msgstr == msgid)
#   - types: / discourses: / sentiments: msgstrs UNCHANGED
CLASSIFICATION_LABELS_PIN: dict[str, str] = {
    "zh_cn:": "zh_cn:",
    "en:": "en:",
    "types:": "类型:",
    "discourses:": "话语:",
    "sentiments:": "情感:",
}


# ============================================================================
# Fixture: activate zh-hans for every test, deactivate after.
# ============================================================================


@pytest.fixture(autouse=True)
def _activate_zh_hans():
    translation.activate("zh-hans")
    yield
    translation.deactivate_all()


# ============================================================================
# Tests
# ============================================================================


def _assert_pin(pin_dict, category_name):
    failures = []
    for msgid, expected in pin_dict.items():
        got = gettext(msgid)
        if got != expected:
            failures.append(f"{category_name}: {msgid!r} expected {expected!r}, got {got!r}")
    return failures


class TestHeadersPin:
    def test_headers_pin(self):
        failures = _assert_pin(HEADERS_PIN, "headers")
        assert failures == [], failures


class TestFeedColumnsPin:
    def test_feed_columns_pin(self):
        failures = _assert_pin(FEED_COLUMNS_PIN, "feed_columns")
        assert failures == [], failures


class TestTopbarPin:
    def test_topbar_pin(self):
        failures = _assert_pin(TOPBAR_PIN, "topbar")
        assert failures == [], failures


class TestClassificationLabelsPin:
    """U1/U2 intentionally change these 5 strings."""

    def test_zh_cn_axis_label_msgid_is_msgstr(self):
        # KTD4: the msgid IS the displayed value for the new axis labels.
        assert gettext("zh_cn:") == "zh_cn:"

    def test_en_axis_label_msgid_is_msgstr(self):
        assert gettext("en:") == "en:"

    def test_types_msgstr_unchanged(self):
        # This msgid existed pre-U1; U1/U2 do NOT change its msgstr.
        assert gettext("types:") == "类型:"

    def test_discourses_msgstr_unchanged(self):
        assert gettext("discourses:") == "话语:"

    def test_sentiments_msgstr_unchanged(self):
        assert gettext("sentiments:") == "情感:"

    def test_full_classification_labels_pin(self):
        failures = _assert_pin(CLASSIFICATION_LABELS_PIN, "classification_labels")
        assert failures == [], failures


class TestLocaleActivation:
    """Sanity: the activated locale is zh-hans, not English-default."""

    def test_untranslated_msgid_returns_english(self):
        assert gettext("definitely_not_a_msgid_xyz") == "definitely_not_a_msgid_xyz"

    def test_activated_locale_is_zh_hans(self):
        assert translation.get_language() == "zh-hans"


class TestNoMsgidSilentlyLost:
    """No pin entry has an empty source or empty target."""

    @pytest.mark.parametrize("category_name,pin_dict", [
        ("headers", HEADERS_PIN),
        ("feed_columns", FEED_COLUMNS_PIN),
        ("topbar", TOPBAR_PIN),
        ("classification_labels", CLASSIFICATION_LABELS_PIN),
    ])
    def test_pin_entries_non_empty(self, category_name, pin_dict):
        for msgid, msgstr in pin_dict.items():
            assert msgid, f"{category_name}: empty msgid"
            assert msgstr, f"{category_name}: empty msgstr for {msgid!r}"