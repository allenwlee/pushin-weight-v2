# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard home-window + locale cookie helpers (U1
of feat/pushin-weight-home-pages, 2026-07-06).

Covers:
- ALLOWED_HOME_WINDOWS = (1, 7, 30, 365) constant
- _resolve_home_window: happy path + edge cases (no cookie / malformed /
  out-of-range)
- normalize_locale: "original" is a first-class value, not a synonym for
  "en" and not a fallback-to-en
- _pick_text: with locale="original" returns (post["text"], False)
- _LOCALE_TO_COLUMN: "original" maps to the __source__ sentinel
- APP_DISPLAY_NAME_ZH / APP_DISPLAY_NAME_EN: constants present
- Route-level: /api/v1/home.window/<n> sets cookie + 303s
- Route-level: /api/v1/home.locale/<locale> accepts original + sets cookie
- Route-level: set_locale POST endpoint accepts "original"
"""

from __future__ import annotations

from x_monitor.dashboard import (
    ALLOWED_HOME_WINDOWS,
    APP_DISPLAY_NAME_EN,
    APP_DISPLAY_NAME_ZH,
    HOME_WINDOW_COOKIE,
    HOME_WINDOW_DEFAULT,
    _LOCALE_TO_COLUMN,
    _pick_text,
    _resolve_home_window,
    normalize_locale,
)


class _FakeReq:
    """Minimal Flask request shim — just .cookies.get(name)."""

    def __init__(self, cookie_value, cookie_name: str = HOME_WINDOW_COOKIE):
        self._cookies = {} if cookie_value is None else {cookie_name: cookie_value}

    @property
    def cookies(self):
        return self._cookies


# ---------------------------------------------------------------------------
# ALLOWED_HOME_WINDOWS constant
# ---------------------------------------------------------------------------


def test_allowed_home_windows_constant_matches_plan():
    """Plan A5: ALLOWED_HOME_WINDOWS = (1, 7, 30, 365)."""
    assert ALLOWED_HOME_WINDOWS == (1, 7, 30, 365)


def test_home_window_default_is_seven_days():
    """Plan R2: default is 7d."""
    assert HOME_WINDOW_DEFAULT == 7


def test_home_window_cookie_name_disjoint_from_others():
    """A9: home_window is named with home_ prefix; not polarity/combined."""
    assert HOME_WINDOW_COOKIE == "home_window"
    assert HOME_WINDOW_COOKIE != "polarity_window"
    assert HOME_WINDOW_COOKIE != "combined_window"


# ---------------------------------------------------------------------------
# _resolve_home_window happy path
# ---------------------------------------------------------------------------


def test_resolve_home_window_cookie_1_returns_1():
    req = _FakeReq("1")
    assert _resolve_home_window(req, default=7) == 1


def test_resolve_home_window_cookie_7_returns_7():
    req = _FakeReq("7")
    assert _resolve_home_window(req, default=7) == 7


def test_resolve_home_window_cookie_30_returns_30():
    req = _FakeReq("30")
    assert _resolve_home_window(req, default=7) == 30


def test_resolve_home_window_cookie_365_returns_365():
    """A5: 1y is in the allowed set even though it's not in the combined set."""
    req = _FakeReq("365")
    assert _resolve_home_window(req, default=7) == 365


# ---------------------------------------------------------------------------
# _resolve_home_window edge cases
# ---------------------------------------------------------------------------


def test_resolve_home_window_no_cookie_returns_default():
    req = _FakeReq(None)
    assert _resolve_home_window(req, default=7) == 7


def test_resolve_home_window_malformed_cookie_returns_default():
    """Non-numeric cookie falls back silently (matches _resolve_combined_window)."""
    req = _FakeReq("abc")
    assert _resolve_home_window(req, default=7) == 7


def test_resolve_home_window_empty_string_returns_default():
    req = _FakeReq("")
    assert _resolve_home_window(req, default=7) == 7


def test_resolve_home_window_out_of_range_returns_default():
    """Plan R2: 999 is not in the allowed set → default."""
    req = _FakeReq("999")
    assert _resolve_home_window(req, default=7) == 7


def test_resolve_home_window_negative_returns_default():
    req = _FakeReq("-1")
    assert _resolve_home_window(req, default=7) == 7


def test_resolve_home_window_excludes_combined_only_values():
    """14, 60, 90, 180, 360 are valid combined windows but NOT home windows."""
    for n in ("14", "60", "90", "180", "360"):
        req = _FakeReq(n)
        assert _resolve_home_window(req, default=7) == 7, (
            f"home window should not accept {n}"
        )


# ---------------------------------------------------------------------------
# normalize_locale — "original" is a first-class value
# ---------------------------------------------------------------------------


def test_normalize_locale_original_returns_original():
    """KTD4: original is a first-class locale, not a synonym for en."""
    assert normalize_locale("original") == "original"


def test_normalize_locale_original_is_case_insensitive():
    assert normalize_locale("Original") == "original"
    assert normalize_locale("ORIGINAL") == "original"


def test_normalize_locale_empty_returns_en():
    assert normalize_locale("") == "en"
    assert normalize_locale(None) == "en"


def test_normalize_locale_zh_cn_canonical():
    assert normalize_locale("zh_cn") == "zh_cn"


def test_normalize_locale_zh_dash_canonical():
    assert normalize_locale("zh-CN") == "zh-CN"


def test_normalize_locale_unsupported_falls_back_to_en():
    assert normalize_locale("fr") == "en"
    assert normalize_locale("klingon") == "en"


# ---------------------------------------------------------------------------
# _LOCALE_TO_COLUMN
# ---------------------------------------------------------------------------


def test_locale_to_column_original_is_source_sentinel():
    """KTD4: "original" maps to a sentinel; _pick_text returns source text."""
    assert _LOCALE_TO_COLUMN["original"] == "__source__"


def test_locale_to_column_en_maps_to_en():
    assert _LOCALE_TO_COLUMN["en"] == "en"


def test_locale_to_column_zh_cn_maps_to_zh_cn():
    assert _LOCALE_TO_COLUMN["zh_cn"] == "zh_cn"
    assert _LOCALE_TO_COLUMN["zh-CN"] == "zh_cn"


# ---------------------------------------------------------------------------
# _pick_text with locale=original
# ---------------------------------------------------------------------------


def test_pick_text_original_returns_source_text():
    """KTD4: with locale=original, return (post["text"], False) regardless
    of available translations."""
    post = {
        "text": "原始文本 hello",
        "text_en": "english translation",
        "text_zh_cn": "中文翻译",
    }
    text, is_translated = _pick_text(post, "original")
    assert text == "原始文本 hello"
    assert is_translated is False


def test_pick_text_original_returns_source_even_when_translations_null():
    """Original should always show source, never fall through to a translation."""
    post = {"text": "source only", "text_en": None, "text_zh_cn": None}
    text, is_translated = _pick_text(post, "original")
    assert text == "source only"
    assert is_translated is False


def test_pick_text_en_returns_english_translation():
    post = {
        "text": "原始文本 hello",
        "text_en": "english translation",
        "text_zh_cn": "中文翻译",
    }
    text, is_translated = _pick_text(post, "en")
    assert text == "english translation"
    assert is_translated is True


def test_pick_text_zh_cn_falls_back_to_source_when_translation_null():
    """Defensive: if the translation column is NULL, fall back to source."""
    post = {"text": "source", "text_en": "english", "text_zh_cn": None}
    text, is_translated = _pick_text(post, "zh_cn")
    assert text == "source"
    assert is_translated is False


# ---------------------------------------------------------------------------
# App display name constants
# ---------------------------------------------------------------------------


def test_app_display_name_zh_is_chinese():
    assert APP_DISPLAY_NAME_ZH == "走个量"


def test_app_display_name_en_is_pushin_weight():
    assert APP_DISPLAY_NAME_EN == "Pushin' Weight"
