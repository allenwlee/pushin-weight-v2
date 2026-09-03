"""Pushin' Weight dashboard views — Django port (U7).

Replaces the Flask routes in x_monitor/dashboard.py and
x_monitor/_home_routes.py with Django ORM-powered views behind
the allauth login wall.

Start simple: multi-brand home, single-brand drill-down, JSON feed
and chart APIs. JS-heavy features (infinite scroll, live charts)
are progressively enhanced.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from collections import OrderedDict
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib.auth.decorators import login_required
from django.core.signing import salted_hmac
from django.db.models import (
    Count,
    Exists,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
)
from django.db.models.functions import Coalesce
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext, override
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from core.classification_labels import CLASSIFICATION_LABELS
from core.models import (
    Brand,
    BrandAccount,
    Country,
    CountryLabel,
    DiscourseLabel,
    NationalismLabel,
    Post,
    PostBrand,
    PostBrandDiscourse,
    PostBrandSignal,
    PostEnrichmentState,
    PostTypeLabel,
    PostUnsanctionedFlag,
    RegionLabel,
    RoleLabel,
    SentimentKey,
    SentimentLabel,
)
from monitor.country_flags import country_flag_symbol_id
from monitor.post_enrichment import persisted_output_complete_q

log = logging.getLogger(__name__)

# ============================================================================
# Constants ported from x_monitor/dashboard.py
# ============================================================================

APP_DISPLAY_NAME_ZH = "走个量"
APP_DISPLAY_NAME_EN = "Pushin' Weight"
APP_TITLE_ZH = "走个量Pushin'Weight"  # browser tab only

SUPPORTED_LOCALES: tuple[str, ...] = ("zh_cn", "zh-CN", "zh_hans", "en", "original")

_LOCALE_TO_COLUMN: dict[str, str] = {
    "en": "en",
    "zh-CN": "zh_cn",
    "zh_cn": "zh_cn",
    "zh_hans": "zh_cn",
    "original": "__source__",
}

# Taxonomy keys — single source of truth for filter control panels
_DASHBOARD_DISCOURSE_KEYS: tuple[str, ...] = (
    "genuine_hype", "sarcasm", "dunk_yingyang",
    "self_deprecation", "cope", "fud",
    "distillation_accusation", "ai_slop_critique",
    "absurdist_meme", "advertising-marketing",
)

_DASHBOARD_DISCOURSE_FILTER_KEYS: tuple[str, ...] = (
    *_DASHBOARD_DISCOURSE_KEYS,
    "uncategorized",
)

_DASHBOARD_POST_TYPE_KEYS: tuple[str, ...] = (
    "buzz_releases", "hands_on_usage",
    "performance_comparisons", "feedback_questions",
    "advertising_marketing", "event_announcement",
)

_DASHBOARD_ROLE_FILTER_KEYS: tuple[str, ...] = (
    "official", "staff", "community", "other",
)

_DASHBOARD_NATIONALISM_KEYS: tuple[str, ...] = (
    "none", "mild_pro", "pro",
    "constructive_critical", "anti", "mixed",
)

_DASHBOARD_LANG_FILTER_KEYS: tuple[str, ...] = (
    "en", "zh-hans", "ja", "es", "tr", "fr", "pt", "ko", "id", "ar", "pl",
    "undetected", "other",
)

_DASHBOARD_LANG_PERSISTED_VALUES: dict[str, str] = {
    "zh-hans": "zh-Hans",
}
_DASHBOARD_LANG_FILTER_KEYS_BY_PERSISTED_VALUE: dict[str, str] = {
    persisted_value: filter_key
    for filter_key, persisted_value in _DASHBOARD_LANG_PERSISTED_VALUES.items()
}
_DASHBOARD_LANG_KNOWN_PERSISTED_VALUES: tuple[str, ...] = tuple(
    _DASHBOARD_LANG_PERSISTED_VALUES.get(value, value)
    for value in _DASHBOARD_LANG_FILTER_KEYS
)

_DASHBOARD_LANG_DISPLAY_NAMES: dict[str, str] = {
    "en": "English",
    "zh-hans": "简体中文",
    "ja": "日本語",
    "es": "Español",
    "tr": "Türkçe",
    "fr": "Français",
    "pt": "Português",
    "ko": "한국어",
    "id": "Bahasa Indonesia",
    "ar": "العربية",
    "pl": "Polski",
    "undetected": "undetected",
    "other": "other",
}

_DASHBOARD_LANG_DISPLAY_NAMES_ZH_CN: dict[str, str] = {
    "en": "英语",
    "zh-hans": "简体中文",
    "ja": "日语",
    "es": "西班牙语",
    "tr": "土耳其语",
    "fr": "法语",
    "pt": "葡萄牙语",
    "ko": "韩语",
    "id": "印度尼西亚语",
    "ar": "阿拉伯语",
    "pl": "波兰语",
    "undetected": "未检测",
    "other": "其他",
}

_COMPACT_LANG_NAMES_ZH_CN: dict[str, str] = {
    "ar": "阿拉伯语",
    "cs": "捷克语",
    "da": "丹麦语",
    "de": "德语",
    "el": "希腊语",
    "en": "英语",
    "es": "西班牙语",
    "fa": "波斯语",
    "fi": "芬兰语",
    "fr": "法语",
    "he": "希伯来语",
    "hi": "印地语",
    "hu": "匈牙利语",
    "id": "印度尼西亚语",
    "it": "意大利语",
    "ja": "日语",
    "ko": "韩语",
    "nl": "荷兰语",
    "no": "挪威语",
    "pl": "波兰语",
    "pt": "葡萄牙语",
    "ro": "罗马尼亚语",
    "ru": "俄语",
    "sv": "瑞典语",
    "th": "泰语",
    "tr": "土耳其语",
    "uk": "乌克兰语",
    "vi": "越南语",
}

# Presentation-only V22 lens. Brand has no open/closed schema field, and these
# four settled provider nicknames are the authored closed-model tier.
_HOME_CLOSED_BRAND_NICKNAMES: tuple[str, ...] = (
    "gemini", "gpt", "claude", "grok",
)

# Presentation order established by the chart. This is a priority list, not a
# selectable-brand allowlist: newly onboarded database brands still render and
# are appended alphabetically without a code change.
_HOME_CHART_BRAND_PRIORITY: tuple[str, ...] = (
    "deepseek",
    "qwen",
    "minimax",
    "glm",
    "mimo",
    "moonshot_kimi",
    "inclusionai",
    "mistral",
    "stepfun",
    "ernie",
    "hunyuan",
    "llama",
    "nemo_megatron",
    "doubao",
    "yi",
    "sensechat",
    "exaone",
    "kuaishou",
    "sakana_ai",
    "upstage",
    "chatglm",
    "gemma",
    "kwaiyii",
    "seed",
    "sensenova",
    "step",
    "wenxin",
    "gemini",
    "gpt",
    "claude",
    "grok",
)
_HOME_CHART_BRAND_RANK = {
    nickname: index for index, nickname in enumerate(_HOME_CHART_BRAND_PRIORITY)
}

_DEFAULT_BRAND_ACCENT = "#9ca3af"


def _brand_projection_fields(
    brand: Brand | dict[str, Any],
    locale: str | None = None,
) -> dict[str, str]:
    """Return the single DB-backed identity projection used by live views."""
    def value(name: str) -> str | None:
        if isinstance(brand, dict):
            return brand.get(name)
        return getattr(brand, name, None)

    nickname = value("nickname") or ""
    fallback_name = value("display_name") or nickname
    display_name_en = value("display_name_en") or fallback_name
    display_name_zh_cn = value("display_name_zh_cn") or fallback_name
    display_name = (
        display_name_zh_cn
        if locale and _is_zh_locale(locale)
        else display_name_en
    )
    return {
        "nickname": nickname,
        "display_name": display_name,
        "display_name_en": display_name_en,
        "display_name_zh_cn": display_name_zh_cn,
        "accent_color": value("accent_color") or _DEFAULT_BRAND_ACCENT,
    }


def _home_chart_brand_sort_key(nickname: str) -> tuple[int, str]:
    return (
        _HOME_CHART_BRAND_RANK.get(nickname, len(_HOME_CHART_BRAND_RANK)),
        nickname,
    )


def _live_brand_projection(locale: str | None = None) -> list[dict[str, str]]:
    """Load every non-sentinel brand in the chart's presentation order."""
    brands = [
        _brand_projection_fields(brand, locale)
        for brand in Brand.objects.filter(is_sentinel=False)
    ]
    brands.sort(key=lambda brand: _home_chart_brand_sort_key(brand["nickname"]))
    return brands

ALLOWED_HOME_WINDOWS: tuple[int, ...] = (1, 7, 30, 365)
HOME_WINDOW_DEFAULT: int = 1  # U2 default: 24h window per plan § U2. Was 7; intentional AFTER change.
HOME_WINDOW_DEFAULT_BEFORE: int = 7  # pinned for Net B regression (BEFORE value, not used in code)
HOME_WINDOW_COOKIE: str = "home_window"

FEED_DEFAULT_LIMIT: int = 50
FEED_REQUEST_MAX: int = 100
BRAND_CHART_ROW_LIMIT: int = 500

_HOME_PULSE_CACHE_TTL_SECONDS = 60.0
_HOME_PULSE_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
_HOME_CHART_CACHE_MAX_ENTRIES = 64
_HOME_CHART_CACHE: OrderedDict[
    tuple[Any, ...], tuple[float, dict[str, Any]]
] = OrderedDict()
_HOME_TOP_VOICES_CACHE: dict[
    tuple[int, int], tuple[float, list[dict[str, Any]]]
] = {}
_HOME_PULSE_CACHE_LOCK = Lock()


# ============================================================================
# Locale helpers
# ============================================================================


def _normalize_locale(locale: str | None) -> str:
    """Return a supported locale or 'en' (with a warning log) for unsupported."""
    if not locale:
        return "zh_cn"
    if locale.casefold() == "original":
        return "original"
    if locale.casefold() == "zh-hans":
        return "zh_hans"
    for sup in SUPPORTED_LOCALES:
        if locale.casefold() == sup.casefold():
            return sup
    log.warning("unsupported display_locale %r; falling back to 'en'", locale)
    return "en"


def _is_zh_locale(locale: str) -> bool:
    """Whether a display-locale alias should render the Chinese v22 chrome."""
    return locale in {"zh_cn", "zh-CN", "zh_hans"}


def _pretty_followers(count: int | None) -> str:
    """Format follower count with k/m suffix (e.g. 15234 -> '15.2k')."""
    if count is None:
        return ""
    if count >= 1_000_000:
        v = count / 1_000_000
        return f"{v:.1f}m" if v < 10 else f"{int(v)}m"
    if count >= 1_000:
        v = count / 1_000
        if v >= 100:
            return f"{int(v)}k"
        if v >= 10:
            return f"{v:.1f}k"
        return f"{v:.2f}k"
    return str(count)


def _feed_account_display_name(
    account_name: str | None,
    snapshot_name: str | None,
    handle: str | None,
) -> str:
    """Resolve the public feed identity without changing its handle-based link."""
    return account_name or snapshot_name or handle or "@unknown"


def _pick_translation(post: Any, locale: str) -> tuple[str | None, bool]:
    """Return (display_text, is_translated) for a post in the given locale.

    Returns (None, False) when no locale-appropriate translation exists.
    NO fallback to the source `text` -- the caller renders literal "NULL"
    for missing translations so data gaps are visible at a glance
    (see plan 2026-07-27-003).

    Accepts either a Post ORM instance or a dict with text/text_en/text_zh_cn keys.
    """
    column = _LOCALE_TO_COLUMN.get(locale, "en")
    if column == "__source__":
        # Under "original" the source IS the locale-appropriate translation;
        # no separate fallback to suppress (KTD4 of plan 2026-07-27-003).
        text = getattr(post, "text", None) if hasattr(post, "text") else post.get("text")
        return (text, False) if text else (None, False)
    if column == "zh_cn":
        translated = getattr(post, "text_zh_cn", None) if hasattr(post, "text_zh_cn") else post.get("text_zh_cn")
    else:
        translated = getattr(post, "text_en", None) if hasattr(post, "text_en") else post.get("text_en")
    return (translated, True) if translated else (None, False)


# Family -> Django model class for label lookup.
_LABEL_MODEL_BY_FAMILY: dict[str, type] = {
    "post_type": PostTypeLabel,
    "discourse": DiscourseLabel,
    "sentiment": SentimentLabel,
    "nationalism": NationalismLabel,
    "role": RoleLabel,
}

# Lang-code lookup order. zh-cn (current seed) takes precedence over zh_cn
# (legacy seed). See KTD9.
_ZHCN_LANG_CODES: tuple[str, ...] = ("zh-cn", "zh_cn", "zh-hans")
_EN_LANG_CODES: tuple[str, ...] = ("en",)

def _locale_to_lang_codes(locale: str) -> tuple[str, ...]:
    """Return the ordered tuple of lang codes to try for a display locale.

    `zh_cn` falls through zh-cn -> zh_cn -> zh-hans; `en` and `original`
    both fall through `en` (the source-text locale uses the original
    English-language label rows).
    """
    if locale in {"zh_cn", "zh-CN", "zh_hans"}:
        return _ZHCN_LANG_CODES
    return _EN_LANG_CODES


def _localize_classification_value(
    family: str,
    key: str | None,
    locale: str,
    label_cache: "dict[tuple[str, str, str], str]",
) -> "str | None":
    """Look up a localized label for a classification key.

    family: one of `post_type`, `discourse`, `sentiment`, `nationalism`.
    key: the raw DB taxonomy key (e.g. `hands_on_usage`), or None/empty.
    locale: the display locale (`zh_cn`, `en`, `original`).
    label_cache: a `{(family, key, lang)} -> label` dict built by
        `_build_label_cache`. Pre-fetched for the whole request so the
        loop below stays O(1) per call.

    Returns the resolved label, the canonical fallback label, or a humanized
    English key on an unknown miss. Returns None when `key` is None/empty so
    the caller can skip emission.
    """
    if not key:
        return None
    if family not in _LABEL_MODEL_BY_FAMILY:
        raise ValueError(
            f"Unknown classification family {family!r}; "
            f"expected one of {sorted(_LABEL_MODEL_BY_FAMILY)}"
        )
    for lang in _locale_to_lang_codes(locale):
        cached = label_cache.get((family, key, lang))
        if cached:
            return cached
    display_locale = "zh-cn" if locale in {"zh_cn", "zh-CN", "zh_hans"} else "en"
    canonical = CLASSIFICATION_LABELS.get(family, {}).get(key, {})
    if canonical.get(display_locale):
        return canonical[display_locale]
    if display_locale == "en":
        return key.replace("_", " ").replace("-", " ").title()
    return key


def _build_label_cache(
    keys_by_family: "dict[str, set[str]]",
    locale: str,
) -> "dict[tuple[str, str, str], str]":
    """Bulk-load label rows for the given keys across lang codes for a locale.

    One query per family across the locale's accepted language aliases.
    Returns a dict keyed by
    (family, key, lang) so the helper can iterate langs without re-querying.
    """
    cache: "dict[tuple[str, str, str], str]" = {}
    lang_codes = _locale_to_lang_codes(locale)
    for family, keys in keys_by_family.items():
        if not keys:
            continue
        model = _LABEL_MODEL_BY_FAMILY[family]
        qs = model.objects.filter(
            **{f"{family}_id__in": list(keys)},
            lang__in=lang_codes,
        ).values(f"{family}_id", "lang", "label")
        for row in qs:
            cache[(family, row[f"{family}_id"], row["lang"])] = row["label"]
    return cache


def _dashboard_filter_entries(
    locale: str,
    sentiment_keys: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Project stable filter keys to request-localized display labels."""
    keys_by_family = {
        "discourse": set(_DASHBOARD_DISCOURSE_KEYS),
        "post_type": set(_DASHBOARD_POST_TYPE_KEYS),
        "role": set(_DASHBOARD_ROLE_FILTER_KEYS[:3]),
        "sentiment": set(sentiment_keys),
        "nationalism": set(_DASHBOARD_NATIONALISM_KEYS),
    }
    label_cache = _build_label_cache(keys_by_family, locale)
    use_zh = _is_zh_locale(locale)

    def localized(family: str, keys: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for key in keys:
            if family == "discourse" and key == "uncategorized":
                label = "未分类" if use_zh else "Uncategorized"
            elif family == "role" and key == "other":
                label = "其他" if use_zh else "Other"
            else:
                label = _localize_classification_value(
                    family, key, locale, label_cache
                ) or key
            entries.append({"key": key, "label": label})
        return entries

    lang_names = (
        _DASHBOARD_LANG_DISPLAY_NAMES_ZH_CN
        if use_zh
        else _DASHBOARD_LANG_DISPLAY_NAMES
    )
    return {
        "discourse_entries": localized(
            "discourse", _DASHBOARD_DISCOURSE_FILTER_KEYS
        ),
        "post_type_entries": localized("post_type", _DASHBOARD_POST_TYPE_KEYS),
        "role_entries": localized("role", _DASHBOARD_ROLE_FILTER_KEYS),
        "lang_entries": [
            {"key": key, "label": lang_names.get(key, key)}
            for key in _DASHBOARD_LANG_FILTER_KEYS
        ],
        "sentiment_entries": localized("sentiment", sentiment_keys),
        "nationalism_entries": localized(
            "nationalism", _DASHBOARD_NATIONALISM_KEYS
        ),
    }


def _resolve_locale(request: HttpRequest) -> str:
    """Read display locale from cookie or Django's active language.

    Priority: ?locale= query param > locale cookie > Django language > 'zh_cn'.
    Also activates Django's translation engine so {% trans %} tags resolve
    correctly for the current request.
    """
    from django.utils import translation

    locale = request.GET.get("locale") or request.COOKIES.get("locale")
    if locale:
        normalized = _normalize_locale(locale)
    else:
        lang = translation.get_language()
        if lang and lang != "en":
            normalized = _normalize_locale(lang)
        else:
            normalized = "zh_cn"
    django_code = {
        "zh_cn": "zh-hans",
        "zh-CN": "zh-hans",
        "zh_hans": "zh-hans",
        "en": "en",
        "original": "en",
    }.get(normalized, "en")
    translation.activate(django_code)
    if hasattr(request, "session"):
        request.session["_language"] = django_code
    return normalized


def _resolve_home_window(request: HttpRequest) -> int:
    """Read the home window from filter state, cookie, or default."""
    # Check filters JSON first (JS-driven updates)
    filters_raw = request.GET.get("filters")
    if filters_raw:
        try:
            filters = json.loads(filters_raw)
            if isinstance(filters, dict) and "window" in filters:
                n = int(filters["window"])
                if n in ALLOWED_HOME_WINDOWS:
                    return n
        except (ValueError, TypeError):
            pass
    # Shareable direct-query form. The complete filter payload above remains
    # the normal browser path, but a valid explicit window wins over cookies.
    try:
        direct_window = int(request.GET.get("window", ""))
    except (TypeError, ValueError):
        direct_window = None
    if direct_window in ALLOWED_HOME_WINDOWS:
        return direct_window
    # Fall back to cookie
    raw = request.COOKIES.get(HOME_WINDOW_COOKIE)
    if raw is None:
        return HOME_WINDOW_DEFAULT
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return HOME_WINDOW_DEFAULT
    if n not in ALLOWED_HOME_WINDOWS:
        return HOME_WINDOW_DEFAULT
    return n


# ============================================================================
# Post query helpers
# ============================================================================


def _get_posts_for_brand(
    brand_nickname: str,
    window_days: int | None = None,
    limit: int | None = None,
) -> QuerySet:
    """Return a QuerySet of Posts associated with a brand, ordered by recency.

    Uses the posts_brands junction table. Posts are de-duplicated (one post
    can belong to multiple brands, but we return each post once per brand
    scope).
    """
    cutoff = None
    if window_days:
        cutoff = django_timezone.now() - timedelta(days=window_days)

    qs = Post.objects.filter(
        brands__brand__nickname=brand_nickname,
    ).distinct().order_by("-created_at")

    if cutoff:
        qs = qs.filter(created_at__gte=cutoff)
    if limit:
        qs = qs[:limit]
    return qs


def _get_feed_posts(
    window_days: int | None = None,
    brand_nickname: str | None = None,
    limit: int = FEED_DEFAULT_LIMIT,
    created_at_start: datetime | None = None,
    created_at_end: datetime | None = None,
) -> QuerySet:
    """Return a QuerySet of Posts for the feed view, with brand and account prefetching.

    Args:
        window_days: optional time window filter
        brand_nickname: optional single-brand scope
        limit: max rows to return
        created_at_start: optional inclusive lower bound
        created_at_end: optional exclusive upper bound
    """
    cutoff = None
    if window_days:
        cutoff = django_timezone.now() - timedelta(days=window_days)

    terminal_state = Q(
        enrichment_state__translation_status=PostEnrichmentState.Status.SUCCEEDED,
        enrichment_state__classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    qs = (
        Post.objects.filter(persisted_output_complete_q())
        .filter(Q(enrichment_state__isnull=True) | terminal_state)
        .select_related("author")
        .prefetch_related(
            Prefetch(
                "brands",
                queryset=PostBrand.objects.select_related("brand"),
            ),
        )
    )

    if created_at_start is not None:
        qs = qs.filter(created_at__gte=created_at_start)
    if created_at_end is not None:
        qs = qs.filter(created_at__lt=created_at_end)
    if cutoff and created_at_start is None and created_at_end is None:
        qs = qs.filter(created_at__gte=cutoff)
    if brand_nickname:
        qs = qs.filter(brands__brand__nickname=brand_nickname).distinct()

    return qs.order_by("-created_at")[:limit]


# ============================================================================
# Wire serialization (mirrors _feed_row_to_wire from dashboard.py)
# ============================================================================


def _avatar_initials(handle: str) -> str:
    """Derive 1-2 char avatar initials from an X handle."""
    h = (handle or "").lstrip("@").strip()
    if not h:
        return "?"
    chars = [c for c in h if c.isalnum()]
    if not chars:
        return "?"
    if len(chars) == 1:
        return chars[0].upper()
    return (chars[0] + chars[1]).upper()


def _avatar_color(handle: str) -> str:
    """Stable per-handle avatar background color (HSL hash)."""
    h = (handle or "").lstrip("@").strip().lower()
    if not h:
        return "hsl(0, 0%, 50%)"
    n = 5381
    for ch in h:
        n = ((n << 5) + n) + ord(ch)
        n &= 0xFFFFFFFF
    hue = n % 360
    return f"hsl({hue}, 55%, 45%)"


def _follower_bin(count: int | None) -> str:
    """Return the public-feed follower glyph bucket for a raw count."""
    followers = max(0, int(count or 0))
    if followers < 1_000:
        return "0-1k"
    if followers < 10_000:
        return "1k-10k"
    if followers < 50_000:
        return "10k-50k"
    return "50k-plus"


def _engagement_pretty(followers: int, likes: int, rts: int, replies: int) -> dict[str, str]:
    """Compact pretty-print for engagement counters (128.4k / 1.2k / 340 / 89)."""
    def _fmt(n) -> str:
        if n is None:
            return ""
        n = int(n)
        if n < 1000:
            return str(n)
        for unit, threshold in (("M", 1_000_000), ("k", 1000)):
            if n >= threshold:
                v = n / threshold
                return f"{v:.1f}{unit}"
        return str(n)
    return {
        "followers": _fmt(followers),
        "likes": _fmt(likes),
        "retweets": _fmt(rts),
        "replies": _fmt(replies),
    }


def _feed_relative_age(when, now=None) -> str:
    """Pretty relative age for feed row meta (e.g. "12m" / "2h" / "Mon DD").

    Mirrors the mockup pattern: <24h → "Nm" / "Nh"; <7d → weekday short;
    same year → "Mon DD"; older → "Mon DD YYYY".
    """
    if not when:
        return ""
    from datetime import datetime as _dt
    if isinstance(when, str):
        try:
            when = _dt.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if not isinstance(when, _dt):
        return ""
    n = now or _dt.now(when.tzinfo) if when.tzinfo else _dt.now()
    delta = int((n - when).total_seconds())
    if delta < 0:
        return "just now"
    if delta < 60:
        return "just now"
    if delta < 60 * 60:
        return f"{delta // 60}m"
    if delta < 60 * 60 * 24:
        return f"{delta // 3600}h"
    if delta < 60 * 60 * 24 * 7:
        return when.strftime("%a")
    if n.year == when.year:
        return when.strftime("%b %-d") if hasattr(when, "strftime") else when.strftime("%b %d")
    return when.strftime("%b %-d %Y") if hasattr(when, "strftime") else when.strftime("%b %d %Y")


def _feed_abs_stamp(when, tz_mode: str = "local") -> str:
    """Absolute HH:MM stamp for the meta line. Empty when >= 24h old.

    Mockup pattern: <24h → "(10:21 本地)" or "(10:21 CA)"; >=24h → "".
    """
    if not when:
        return ""
    from datetime import datetime as _dt
    if isinstance(when, str):
        try:
            when = _dt.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if not isinstance(when, _dt):
        return ""
    now = _dt.now(when.tzinfo) if when.tzinfo else _dt.now()
    delta = int((now - when).total_seconds())
    if delta >= 60 * 60 * 24:
        return ""
    if tz_mode == "ca":
        from zoneinfo import ZoneInfo
        try:
            t = when.astimezone(ZoneInfo("America/Los_Angeles"))
            return f"({t.strftime('%H:%M')} CA)"
        except Exception:
            pass
    return f"({when.strftime('%H:%M')} 本地)"


def _feed_signal_keys(classifications: dict[str, dict[str, Any]]) -> tuple[list[str], list[str], str, str]:
    """Flatten per-brand classifications into feed-row signal keys.

    Returns (sentiment_keys, post_type_keys, nat_cn_key, nat_us_key) used by
    the JS signal-painter to populate the .sig-* rows. Order is stable
    (SENT_ORDER / TYPE_ORDER).
    """
    sent_order = ["positive", "neutral", "negative", "mixed"]
    type_order = [
        "buzz_releases", "hands_on_usage", "performance_comparisons",
        "feedback_questions", "advertising_marketing", "event_announcement",
    ]
    sents: set[str] = set()
    types: set[str] = set()
    cn_keys: set[str] = set()
    us_keys: set[str] = set()
    for cls in classifications.values():
        for v in (cls.get("sentiments") or []):
            k = (v.get("key") if isinstance(v, dict) else v) if v else None
            if k:
                sents.add(k)
        for v in (cls.get("post_types") or []):
            k = (v.get("key") if isinstance(v, dict) else v) if v else None
            if k:
                types.add(k)
        cn = cls.get("cn_nationalism")
        if cn:
            k = (cn.get("key") if isinstance(cn, dict) else cn) if cn else None
            if k and k != "none":
                cn_keys.add(k)
        us = cls.get("us_nationalism")
        if us:
            k = (us.get("key") if isinstance(us, dict) else us) if us else None
            if k and k != "none":
                us_keys.add(k)
    sent_list = [k for k in sent_order if k in sents]
    for k in sorted(sents):
        if k not in sent_list:
            sent_list.append(k)
    type_list = [k for k in type_order if k in types]
    for k in sorted(types):
        if k not in type_list:
            type_list.append(k)
    nat_cn = sorted(cn_keys)[0] if cn_keys else ""
    nat_us = sorted(us_keys)[0] if us_keys else ""
    return sent_list, type_list, nat_cn, nat_us


def _feed_tint_class(sentiment_keys: list[str]) -> str:
    """Map sentiment keys → mockup tint class on .feed-row-shell."""
    s = set(sentiment_keys)
    has_p = "positive" in s
    has_n = "negative" in s
    has_m = "mixed" in s
    if has_p and has_n and has_m:
        return "tint-pos-neg-mixed"
    if has_p and has_n:
        return "tint-pos-neg"
    if has_p and has_m:
        return "tint-pos-mixed"
    if has_n and has_m:
        return "tint-neg-mixed"
    if has_p:
        return "tint-positive"
    if has_n:
        return "tint-negative"
    if has_m:
        return "tint-mixed"
    return "tint-neutral"


def _enrichment_status(
    translation_status: str | None,
    classification_status: str | None,
) -> str:
    """Collapse the two durable stages into one additive feed state."""
    statuses = {translation_status, classification_status}
    if PostEnrichmentState.Status.FAILED in statuses:
        return PostEnrichmentState.Status.FAILED
    if statuses == {PostEnrichmentState.Status.SUCCEEDED}:
        return PostEnrichmentState.Status.SUCCEEDED
    return PostEnrichmentState.Status.PENDING


def _enrichment_status_label(status: str, locale: str) -> str:
    """Return compact accessible copy without changing the feed layout."""
    if status == PostEnrichmentState.Status.PENDING:
        return "补充处理中" if locale == "zh_cn" else "enrichment pending"
    if status == PostEnrichmentState.Status.FAILED:
        return "补充失败" if locale == "zh_cn" else "enrichment failed"
    return ""


_DISPLAY_ROLE_PRECEDENCE = ("official", "staff", "community")


def _display_role_key(role_keys: Any) -> str | None:
    """Choose one compact badge without changing multi-role filter semantics."""
    if isinstance(role_keys, str):
        candidates = {role_keys}
    else:
        candidates = {key for key in (role_keys or []) if isinstance(key, str)}
    return next((key for key in _DISPLAY_ROLE_PRECEDENCE if key in candidates), None)


def _display_role_label(
    role_key: str | None,
    locale: str,
    label_cache: dict[tuple[str, str, str], str],
) -> str:
    if not role_key:
        return ""
    localized = _localize_classification_value("role", role_key, locale, label_cache)
    if localized and localized != role_key:
        return localized
    fallback = {
        "official": ("官方", "Official"),
        "staff": ("员工", "Staff"),
        "community": ("社区", "Community"),
    }
    zh_label, en_label = fallback[role_key]
    return zh_label if _is_zh_locale(locale) else en_label


def _geography_label(labels: dict[str, str], locale: str) -> str:
    """Select a complete seeded label without exposing taxonomy keys."""

    key = "zh_cn" if _is_zh_locale(locale) else "en"
    label = labels.get(key)
    return label.strip() if isinstance(label, str) else ""


def _geography_accessible_label(label: str, locale: str) -> str:
    language = "zh-hans" if _is_zh_locale(locale) else "en"
    with override(language):
        return gettext("X reports this account is based in %(place)s") % {
            "place": label
        }


def _compact_language_display(lang_detected: str | None, locale: str) -> str:
    """Project persisted language metadata without guessing from post text."""

    normalized = (lang_detected or "").strip().replace("_", "-").casefold()
    use_zh = _is_zh_locale(locale)
    if not normalized:
        return "未检测" if use_zh else "undetected"
    if normalized == "other":
        return "其他" if use_zh else "other"
    if normalized in {"und", "unknown", "undetected"}:
        return "未检测" if use_zh else "undetected"
    if normalized in {"zh", "zh-cn", "zh-hans"}:
        return "zh-Hans"
    if normalized in {"zh-hant", "zh-tw", "zh-hk", "zh-mo"}:
        return "zh-Hant"

    primary = normalized.split("-", 1)[0]
    if not re.fullmatch(r"[a-z]{2}", primary):
        return "其他" if use_zh else "other"
    if not use_zh:
        return primary
    return _COMPACT_LANG_NAMES_ZH_CN.get(primary, "其他")


_LEADING_REGION_COMPOUND_DIRECTION = re.compile(
    r"^(north(?:ern)?|south(?:ern)?)[ -]?(east(?:ern)?|west(?:ern)?)(?:[ -]+)?",
    re.IGNORECASE,
)
_LEADING_REGION_SINGLE_DIRECTION = re.compile(
    r"^(north(?:ern)?|south(?:ern)?|east(?:ern)?|west(?:ern)?)(?:[ -]+)?",
    re.IGNORECASE,
)


def _compact_region_label(label: str, locale: str) -> str:
    """Abbreviate only the leading direction in English region display text."""

    if _is_zh_locale(locale):
        return label

    compound = _LEADING_REGION_COMPOUND_DIRECTION.match(label)
    if compound:
        first = "N" if compound.group(1).casefold().startswith("north") else "S"
        second = "E" if compound.group(2).casefold().startswith("east") else "W"
        return f"{first}{second} {label[compound.end():]}".rstrip()

    single = _LEADING_REGION_SINGLE_DIRECTION.match(label)
    if single:
        direction = {
            "north": "N",
            "south": "S",
            "east": "E",
            "west": "W",
        }
        stem = next(
            abbreviation
            for prefix, abbreviation in direction.items()
            if single.group(1).casefold().startswith(prefix)
        )
        return f"{stem} {label[single.end():]}".rstrip()
    return label


def _region_geography_wire(
    labels: dict[str, str],
    locale: str,
) -> dict[str, Any] | None:
    label = _geography_label(labels, locale)
    if not label:
        return None
    accessible_label = _geography_accessible_label(label, locale)
    return {
        "kind": "region",
        "label": label,
        "accessible_label": accessible_label,
        "flags": [],
        "text": _compact_region_label(label, locale),
        "relationship_type": "",
    }


def _feed_geography_wire(
    source: dict[str, Any] | None,
    locale: str,
) -> dict[str, Any] | None:
    """Project accepted normalized geography into one presentation-safe object."""

    if not source:
        return None
    country_code = source.get("country_code")
    if not country_code:
        return _region_geography_wire(
            source.get("direct_region_labels") or {}, locale
        )

    label = _geography_label(source.get("country_labels") or {}, locale)
    if not label:
        return None
    parent_code = source.get("parent_country_code")
    parent_label = _geography_label(
        source.get("parent_country_labels") or {}, locale
    )
    parent_symbol = country_flag_symbol_id(parent_code) if parent_code else None
    child_symbol = country_flag_symbol_id(country_code)
    relationship_type = source.get("relationship_type") or ""
    accessible_label = _geography_accessible_label(label, locale)

    if country_code == "TW":
        if parent_code != "CN" or not parent_symbol or not parent_label:
            return _region_geography_wire(
                source.get("fallback_region_labels") or {}, locale
            )
        return {
            "kind": "taiwan",
            "label": label,
            "accessible_label": accessible_label,
            "flags": [
                {
                    "code": parent_code,
                    "symbol_id": parent_symbol,
                    "label": parent_label,
                }
            ],
            "text": f"TW · {label}",
            "relationship_type": relationship_type,
        }

    if not child_symbol:
        return _region_geography_wire(
            source.get("fallback_region_labels") or {}, locale
        )

    flags: list[dict[str, str]] = []
    if parent_code:
        if not parent_symbol or not parent_label:
            return _region_geography_wire(
                source.get("fallback_region_labels") or {}, locale
            )
        flags.append(
            {
                "code": parent_code,
                "symbol_id": parent_symbol,
                "label": parent_label,
            }
        )
    flags.append(
        {"code": country_code, "symbol_id": child_symbol, "label": label}
    )
    return {
        "kind": "hierarchy" if parent_code else "country",
        "label": label,
        "accessible_label": accessible_label,
        "flags": flags,
        "text": "",
        "relationship_type": relationship_type,
    }


def _feed_geography_sources(posts: QuerySet | list[Any]) -> dict[str, dict[str, Any]]:
    """Bulk-load normalized geography and both feed locales for this page."""

    accounts = {
        post.author_id: post.author
        for post in posts
        if getattr(post, "author_id", None) and getattr(post, "author", None)
    }
    country_codes = {
        account.country_id for account in accounts.values() if account.country_id
    }
    direct_region_keys = {
        account.based_in_region_id
        for account in accounts.values()
        if account.based_in_region_id
    }
    country_rows = {
        row["code"]: row
        for row in Country.objects.filter(code__in=country_codes).values(
            "code",
            "display_parent_country_id",
            "display_parent_relationship_type",
            "region_mapping__region_id",
        )
    }
    parent_codes = {
        row["display_parent_country_id"]
        for row in country_rows.values()
        if row["display_parent_country_id"]
    }
    all_country_codes = country_codes | parent_codes
    country_labels: dict[str, dict[str, str]] = {
        code: {} for code in all_country_codes
    }
    for code, lang, label in CountryLabel.objects.filter(
        country_id__in=all_country_codes,
        lang__in=("en", "zh-cn"),
    ).values_list("country_id", "lang", "label"):
        country_labels[code]["zh_cn" if lang == "zh-cn" else "en"] = label

    fallback_region_keys = {
        row["region_mapping__region_id"]
        for row in country_rows.values()
        if row["region_mapping__region_id"]
    }
    all_region_keys = direct_region_keys | fallback_region_keys
    region_labels: dict[str, dict[str, str]] = {
        key: {} for key in all_region_keys
    }
    for key, lang, label in RegionLabel.objects.filter(
        region_id__in=all_region_keys,
        lang__in=("en", "zh-cn"),
    ).values_list("region_id", "lang", "label"):
        region_labels[key]["zh_cn" if lang == "zh-cn" else "en"] = label

    result: dict[str, dict[str, Any]] = {}
    for author_id, account in accounts.items():
        if account.country_id:
            country = country_rows.get(account.country_id)
            if not country:
                continue
            parent_code = country["display_parent_country_id"]
            region_key = country["region_mapping__region_id"]
            result[author_id] = {
                "country_code": account.country_id,
                "country_labels": country_labels.get(account.country_id, {}),
                "parent_country_code": parent_code,
                "parent_country_labels": country_labels.get(parent_code, {}),
                "relationship_type": country[
                    "display_parent_relationship_type"
                ],
                "fallback_region_labels": region_labels.get(region_key, {}),
                "direct_region_labels": {},
            }
        elif account.based_in_region_id:
            result[author_id] = {
                "country_code": None,
                "country_labels": {},
                "parent_country_code": None,
                "parent_country_labels": {},
                "relationship_type": "",
                "fallback_region_labels": {},
                "direct_region_labels": region_labels.get(
                    account.based_in_region_id, {}
                ),
            }
    return result


def _feed_signal_inspections(
    classifications: dict[str, dict[str, Any]],
    brands: list[dict[str, Any]],
    locale: str,
    *,
    unsanctioned: bool,
) -> dict[str, dict[str, list[dict[str, str]]]]:
    """Keep every brand contributor behind each deduplicated visual signal."""

    use_zh = _is_zh_locale(locale)
    family_labels = {
        "sentiment": "情感" if use_zh else "Sentiment",
        "post_type": "帖子类型" if use_zh else "Post Type",
        "nat_cn": "中国民族主义" if use_zh else "China Nationalism",
        "nat_us": "美国民族主义" if use_zh else "U.S. Nationalism",
    }
    brand_names: dict[str, str] = {}
    for brand in brands:
        nickname = str(brand.get("nickname") or "")
        if not nickname:
            continue
        if use_zh:
            name = brand.get("display_name_zh_cn") or brand.get("display_name")
        else:
            name = brand.get("display_name_en") or brand.get("display_name")
        brand_names[nickname] = str(name or nickname)

    result: dict[str, dict[str, list[dict[str, str]]]] = {
        "sentiment": {},
        "post_type": {},
        "nat_cn": {},
        "nat_us": {},
        "unsanctioned": {},
    }

    def append_entry(family: str, key: str, nickname: str, value: str) -> None:
        brand = brand_names.get(nickname, nickname)
        separator = "：" if use_zh else ": "
        text = f"{brand} {family_labels[family]}{separator}{value}"
        result[family].setdefault(key, []).append({
            "brand": brand,
            "value": value,
            "text": text,
        })

    for nickname, classification in classifications.items():
        for item in classification.get("sentiments") or []:
            if isinstance(item, dict) and item.get("key"):
                append_entry(
                    "sentiment", str(item["key"]), nickname,
                    str(item.get("label") or item["key"]),
                )
        for item in classification.get("post_types") or []:
            if isinstance(item, dict) and item.get("key"):
                append_entry(
                    "post_type", str(item["key"]), nickname,
                    str(item.get("label") or item["key"]),
                )
        for family, field_name in (
            ("nat_cn", "cn_nationalism"),
            ("nat_us", "us_nationalism"),
        ):
            item = classification.get(field_name)
            if isinstance(item, dict) and item.get("key") and item["key"] != "none":
                append_entry(
                    family, str(item["key"]), nickname,
                    str(item.get("label") or item["key"]),
                )

    if unsanctioned:
        text = "非官方发布" if use_zh else "Unsanctioned"
        result["unsanctioned"]["true"] = [
            {"brand": "", "value": text, "text": text}
        ]
    return result


def _v22_feed_display_fields(
    classifications: dict[str, dict[str, Any]],
    *,
    locale: str,
    active_brand_scope: str | list[str] | tuple[str, ...] | set[str] | None = "__all__",
    created_at: Any,
    account: dict[str, Any],
    like_count: int | None = None,
    retweet_count: int | None = None,
    reply_count: int | None = None,
    author_handle: str | None = None,
) -> dict[str, Any]:
    """Build the V22 display fields shared by SSR and feed-refresh rows."""
    _, post_type_keys, nat_cn, nat_us = _feed_signal_keys(classifications)
    if active_brand_scope in (None, "__all__"):
        sentiment_classifications = classifications
    else:
        selected_brands = (
            {active_brand_scope}
            if isinstance(active_brand_scope, str)
            else set(active_brand_scope)
        )
        sentiment_classifications = {
            nickname: classification
            for nickname, classification in classifications.items()
            if nickname in selected_brands
        }
    sentiment_keys, _, _, _ = _feed_signal_keys(sentiment_classifications)
    handle = account.get("handle") or author_handle or ""
    followers_count = account.get("followers_count") or 0
    engagement_pretty = _engagement_pretty(
        followers_count,
        like_count or 0,
        retweet_count or 0,
        reply_count or 0,
    )
    return {
        "sentiment_keys": sentiment_keys,
        "post_type_keys": post_type_keys,
        "nat_cn": nat_cn,
        "nat_us": nat_us,
        "tint_class": _feed_tint_class(sentiment_keys),
        "meta_text": _feed_relative_age(created_at),
        "ts_abs_text": _feed_abs_stamp(created_at),
        "avatar_initials": _avatar_initials(handle),
        "avatar_color": _avatar_color(handle),
        "follower_bin": _follower_bin(followers_count),
        "followers_count": followers_count,
        "followers_label": (
            f"{engagement_pretty['followers']} 关注者"
            if _is_zh_locale(locale)
            else f"{engagement_pretty['followers']} followers"
        ),
        "engagement_pretty": engagement_pretty,
    }


def _post_to_wire(
    post: Post,
    locale: str,
    enriched: dict[str, Any] | None = None,
    *,
    active_brand_scope: str | list[str] | tuple[str, ...] | set[str] | None = "__all__",
    include_geography: bool = False,
) -> dict[str, Any]:
    """Serialize a Post ORM instance to the JSON wire shape for the feed.

    Mirrors x_monitor/dashboard.py:_feed_row_to_wire.
    """
    text_translated, is_translated = _pick_translation(post, locale)
    text_original = post.text

    # Brand data from PostBrand junction
    brand_nicknames: list[str] = []
    brands_wire: list[dict[str, Any]] = []
    classifications: dict[str, dict[str, Any]] = {}
    cls_by_brand = enriched.get("classifications_by_brand", {}) if enriched else {}
    label_cache = (
        enriched.get("label_cache_by_locale", {}).get(locale, {})
        if enriched
        else {}
    )

    def _labelize(family: str, key: str | None) -> dict[str, str] | None:
        label = _localize_classification_value(family, key, locale, label_cache)
        if not key:
            return None
        return {"key": key, "label": label if label is not None else key}

    for pb in post.brands.all():
        if pb.brand.is_sentinel:
            continue
        nick = pb.brand.nickname
        brand_nicknames.append(nick)
        brands_wire.append(_brand_projection_fields(pb.brand, locale))

        # Per-brand classifications - from enrichment when available.
        # Each value is reshaped into {key, label} so the JS / template
        # can render the localized label while preserving the raw DB key
        # for tooling / debug.
        cls = cls_by_brand.get(nick, {})
        classifications[nick] = {
            "discourse": [
                v for v in (
                    _labelize("discourse", k)
                    for k in (cls.get("discourse") or [])
                ) if v is not None
            ],
            "post_types": [
                v for v in (
                    _labelize("post_type", k)
                    for k in (cls.get("post_types") or [])
                ) if v is not None
            ],
            "sentiments": [
                v for v in (
                    _labelize("sentiment", k)
                    for k in (cls.get("sentiments") or [])
                ) if v is not None
            ],
            "cn_nationalism": _labelize("nationalism", cls.get("cn_nationalism")),
            "us_nationalism": _labelize("nationalism", cls.get("us_nationalism")),
            "role_label": cls.get("role_label"),
        }

    # Account data — from enrichment when available
    if enriched and enriched.get("account"):
        acc = enriched["account"]
        handle = acc.get("handle") or post.author_handle or "@unknown"
        account_wire = {
            "handle": handle,
            "display_name": _feed_account_display_name(
                acc.get("display_name"), post.author_name, handle
            ),
            "role": acc.get("role_key"),
            "role_label": acc.get("role_label") or "",
            "followers_count": acc.get("followers_count") or 0,
            "followers_pretty": acc.get("followers_pretty") or "",
        }
        if include_geography:
            account_wire["geography"] = _feed_geography_wire(
                acc.get("_geography_source"), locale
            )
    elif post.author:
        handle = post.author.handle or post.author_handle or "@unknown"
        account_wire = {
            "handle": handle,
            "display_name": _feed_account_display_name(
                post.author.display_name, post.author_name, handle
            ),
            "role": None,
            "role_label": "",
            "followers_count": post.author.followers_count or 0,
            "followers_pretty": _pretty_followers(post.author.followers_count),
        }
        if include_geography:
            account_wire["geography"] = None
    else:
        handle = post.author_handle or "@unknown"
        account_wire = {
            "handle": handle,
            "display_name": _feed_account_display_name(None, post.author_name, handle),
            "role": None, "role_label": "",
            "followers_count": 0, "followers_pretty": "",
        }
        if include_geography:
            account_wire["geography"] = None

    role_candidates = (
        enriched.get("role_keys")
        if enriched and enriched.get("role_keys")
        else [account_wire.get("role")]
    )
    display_role = _display_role_key(role_candidates)
    role_label_cache = (
        enriched.get("label_cache_by_locale", {}).get(locale, {})
        if enriched else {}
    )
    account_wire["role"] = display_role
    account_wire["role_label"] = _display_role_label(
        display_role, locale, role_label_cache
    )

    created_at_raw = post.created_at.isoformat() if post.created_at else None
    created_at_iso = created_at_raw
    unsanctioned = enriched.get("unsanctioned", False) if enriched else False
    enrichment_status = (
        enriched.get("enrichment_status", PostEnrichmentState.Status.SUCCEEDED)
        if enriched
        else PostEnrichmentState.Status.SUCCEEDED
    )

    display_fields = _v22_feed_display_fields(
        classifications,
        locale=locale,
        active_brand_scope=active_brand_scope,
        created_at=post.created_at,
        account=account_wire,
        like_count=post.like_count,
        retweet_count=post.retweet_count,
        reply_count=post.reply_count,
        author_handle=post.author_handle,
    )
    signal_inspections = _feed_signal_inspections(
        classifications,
        brands_wire,
        locale,
        unsanctioned=unsanctioned,
    )

    return {
        "tweet_id": post.tweet_id,
        "created_at": created_at_raw,
        "created_at_iso": created_at_iso,
        "lang_detected": post.lang_detected,
        "language_display": _compact_language_display(post.lang_detected, locale),
        "text": text_original,
        "text_original": text_original,
        "text_translated": text_translated,
        "is_translated": is_translated,
        "text_en": post.text_en,
        "text_zh_cn": post.text_zh_cn,
        "commentary_en": post.commentary_en,
        "commentary_zh_cn": post.commentary_zh_cn,
        "like_count": post.like_count or 0,
        "retweet_count": post.retweet_count or 0,
        "reply_count": post.reply_count or 0,
        "quote_count": post.quote_count or 0,
        "brands": brands_wire,
        "brand_nicknames": brand_nicknames,
        "classifications": classifications,
        "signal_inspections": signal_inspections,
        "signal_inspections_json": json.dumps(
            signal_inspections, ensure_ascii=False, separators=(",", ":")
        ),
        "unsanctioned": unsanctioned,
        "enrichment_status": enrichment_status,
        "enrichment_status_label": _enrichment_status_label(
            enrichment_status, locale
        ),
        "account": account_wire,
        **display_fields,
    }



def _enrich_posts_with_classifications(
    posts: QuerySet,
    brand_nickname: str | None = None,
    *,
    include_geography: bool = False,
) -> list[dict[str, Any]]:
    """Enrich a Post QuerySet with per-brand classifications and unsanctioned flags.

    Does bulk queries for PostBrandSignal, PostBrandDiscourse, PostUnsanctionedFlag,
    and BrandAccount to avoid N+1.

    Returns a list of dicts with the denormalized shape expected by serializers
    (_post_matches_filter, serialize_feed_page, etc.).

    When brand_nickname is provided, classifications are scoped to that brand.
    """
    # Accept both QuerySets and plain lists
    if hasattr(posts, "values_list"):
        tweet_ids = list(posts.values_list("tweet_id", flat=True))
    else:
        tweet_ids = [p.tweet_id if hasattr(p, "tweet_id") else p.get("tweet_id") for p in posts]
    if not tweet_ids:
        return []

    # Bulk fetch classifications
    signal_qs = PostBrandSignal.objects.filter(post_id__in=tweet_ids)
    if brand_nickname:
        signal_qs = signal_qs.filter(brand_id=brand_nickname)
    signals = list(signal_qs.values("post_id", "brand_id", "post_type_id", "sentiment_id"))

    discourse_qs = PostBrandDiscourse.objects.filter(post_id__in=tweet_ids)
    if brand_nickname:
        discourse_qs = discourse_qs.filter(brand_id=brand_nickname)
    discourses = list(discourse_qs.values(
        "post_id", "brand_id", "discourse_id",
        "china_nationalism_id", "us_nationalism_id",
    ))

    # Unsanctioned flags
    flag_tweet_ids = set(
        PostUnsanctionedFlag.objects.filter(
            post_id__in=tweet_ids,
        ).values_list("post_id", flat=True)
    )

    enrichment_by_tweet = {
        state["post_id"]: _enrichment_status(
            state["translation_status"], state["classification_status"]
        )
        for state in PostEnrichmentState.objects.filter(
            post_id__in=tweet_ids
        ).values("post_id", "translation_status", "classification_status")
    }

    # Account roles for the brands represented by this page.  A public feed
    # can contain several brands, so role matching must retain the
    # brand/account pair instead of choosing one arbitrary role per account.
    author_ids = {p.author_id for p in posts if p.author_id}
    post_brand_ids = {
        pb.brand_id
        for post in posts
        for pb in post.brands.all()
    }
    role_map: dict[tuple[str, str], str | None] = {}
    if author_ids and post_brand_ids:
        ba_qs = BrandAccount.objects.filter(
            account_id__in=author_ids,
            brand_id__in=post_brand_ids,
        ).select_related("role")
        if brand_nickname:
            ba_qs = ba_qs.filter(brand_id=brand_nickname)
        for ba in ba_qs:
            if ba.account_id:
                role_map[(ba.brand_id, ba.account_id)] = ba.role.key if ba.role_id else None
    geography_by_author = (
        _feed_geography_sources(posts) if include_geography else {}
    )

    # Index by tweet_id
    signals_by_tweet: dict[str, dict[str, dict[str, list[str]]]] = {}
    for s in signals:
        tid = s["post_id"]
        bid = s["brand_id"]
        if tid not in signals_by_tweet:
            signals_by_tweet[tid] = {}
        if bid not in signals_by_tweet[tid]:
            signals_by_tweet[tid][bid] = {"post_types": [], "sentiments": []}
        signals_by_tweet[tid][bid]["post_types"].append(s["post_type_id"])
        signals_by_tweet[tid][bid]["sentiments"].append(s["sentiment_id"])

    discourse_by_tweet: dict[str, dict[str, dict[str, Any]]] = {}
    for d in discourses:
        tid = d["post_id"]
        bid = d["brand_id"]
        if tid not in discourse_by_tweet:
            discourse_by_tweet[tid] = {}
        if bid not in discourse_by_tweet[tid]:
            discourse_by_tweet[tid][bid] = {
                "discourse": [],
                "cn_nationalism": None,
                "us_nationalism": None,
            }
        discourse_by_tweet[tid][bid]["discourse"].append(d["discourse_id"])
        if d["china_nationalism_id"]:
            discourse_by_tweet[tid][bid]["cn_nationalism"] = d["china_nationalism_id"]
        if d["us_nationalism_id"]:
            discourse_by_tweet[tid][bid]["us_nationalism"] = d["us_nationalism_id"]

    # Collect all classification keys present in this page so we can
    # batch-load the label rows for zh_cn + en in one go per family.
    keys_by_family: dict[str, set[str]] = {
        "post_type": set(),
        "discourse": set(),
        "sentiment": set(),
        "nationalism": set(),
        # Keep the query shape constant even when the current page has no
        # named roles; these are the only displayable badge values.
        "role": set(_DISPLAY_ROLE_PRECEDENCE),
    }
    for s in signals:
        if s.get("post_type_id"):
            keys_by_family["post_type"].add(s["post_type_id"])
        if s.get("sentiment_id"):
            keys_by_family["sentiment"].add(s["sentiment_id"])
    for d in discourses:
        if d.get("discourse_id"):
            keys_by_family["discourse"].add(d["discourse_id"])
        if d.get("china_nationalism_id"):
            keys_by_family["nationalism"].add(d["china_nationalism_id"])
        if d.get("us_nationalism_id"):
            keys_by_family["nationalism"].add(d["us_nationalism_id"])

    # Pre-fetch label caches for zh_cn and en up front (1 query per family
    # per lang code = up to 12 queries, vs. N+1 for per-row lookup). The
    # feed view only emits one locale per request, but callers occasionally
    # read enriched rows under multiple locales.
    label_cache_by_locale: dict[str, dict[tuple[str, str, str], str]] = {
        "zh_cn": _build_label_cache(keys_by_family, "zh_cn"),
        "en": _build_label_cache(keys_by_family, "en"),
    }

    # Build enriched dicts
    result: list[dict[str, Any]] = []
    for post in posts:
        tid = post.tweet_id
        account_handle = (
            post.author.handle if post.author else post.author_handle
        ) or "@unknown"
        account_display_name = _feed_account_display_name(
            post.author.display_name if post.author else None,
            post.author_name,
            account_handle,
        )
        row: dict[str, Any] = {
            "tweet_id": tid,
            "created_at": post.created_at.isoformat() if post.created_at else None,
            "text": post.text,
            "text_en": post.text_en,
            "text_zh_cn": post.text_zh_cn,
            "commentary_en": post.commentary_en,
            "commentary_zh_cn": post.commentary_zh_cn,
            "like_count": post.like_count or 0,
            "retweet_count": post.retweet_count or 0,
            "reply_count": post.reply_count or 0,
            "lang_detected": post.lang_detected,
            "author_handle": post.author_handle,
            "author_name": post.author_name,
            "author_id": post.author_id,
            "headline": post.headline,
            "headline_source": post.headline_source,
            "source_query_id": post.source_query_id,
            "discourse": [],
            "post_types": [],
            "sentiments": [],
            "cn_nationalism": None,
            "us_nationalism": None,
            "role_keys": [],
            "role_key": None,
            "unsanctioned": tid in flag_tweet_ids,
            # Legacy rows predate the durable ledger and were already enriched.
            "enrichment_status": enrichment_by_tweet.get(
                tid, PostEnrichmentState.Status.SUCCEEDED
            ),
            "brand_nicknames": [],
            "brands": [],
            "classifications_by_brand": {},
            "account": {
                "handle": account_handle,
                "display_name": account_display_name,
                "role": None,
                "role_key": None,
                "role_label": "",
                "followers_count": post.author.followers_count if post.author else 0,
                "followers_pretty": _pretty_followers(post.author.followers_count if post.author else 0),
            },
        }
        if include_geography:
            row["account"]["_geography_source"] = geography_by_author.get(
                post.author_id
            )

        # Merge per-brand data from PostBrand junction + classifications
        for pb in post.brands.all():
            if pb.brand.is_sentinel:
                continue
            nick = pb.brand.nickname
            if nick not in row["brand_nicknames"]:
                row["brand_nicknames"].append(nick)
            row["brands"].append(_brand_projection_fields(pb.brand))

            cls_data: dict[str, Any] = {
                "discourse": list(row["discourse"]),
                "post_types": list(row["post_types"]),
                "sentiments": list(row["sentiments"]),
                "cn_nationalism": row["cn_nationalism"],
                "us_nationalism": row["us_nationalism"],
            }
            sig_data = (signals_by_tweet.get(tid, {}).get(nick) or {})
            disc_data = (discourse_by_tweet.get(tid, {}).get(nick) or {})
            if sig_data.get("post_types"):
                cls_data["post_types"] = sig_data["post_types"]
                for pt in sig_data["post_types"]:
                    if pt not in row["post_types"]:
                        row["post_types"].append(pt)
            if sig_data.get("sentiments"):
                cls_data["sentiments"] = sig_data["sentiments"]
                for s in sig_data["sentiments"]:
                    if s not in row["sentiments"]:
                        row["sentiments"].append(s)
            if disc_data.get("discourse"):
                cls_data["discourse"] = disc_data["discourse"]
                for d in disc_data["discourse"]:
                    if d not in row["discourse"]:
                        row["discourse"].append(d)
            if disc_data.get("cn_nationalism"):
                cls_data["cn_nationalism"] = disc_data["cn_nationalism"]
                row["cn_nationalism"] = disc_data["cn_nationalism"]
            if disc_data.get("us_nationalism"):
                cls_data["us_nationalism"] = disc_data["us_nationalism"]
                row["us_nationalism"] = disc_data["us_nationalism"]

            row["classifications_by_brand"][nick] = cls_data

            role_key = role_map.get((pb.brand_id, post.author_id)) if post.author_id else None
            if role_key and role_key not in row["role_keys"]:
                row["role_keys"].append(role_key)

        row["role_key"] = next(iter(row["role_keys"]), None)
        row["account"]["role"] = row["role_key"]
        row["account"]["role_key"] = row["role_key"]
        row["account"]["role_label"] = row["role_key"] or ""

        row["label_cache_by_locale"] = label_cache_by_locale
        result.append(row)

    return result



# ============================================================================
# Filter helpers (mirrors _post_matches_filter)
# ============================================================================


def _parse_filters_from_request(request: HttpRequest) -> dict[str, Any]:
    """Read active control-panel filters from query args."""
    raw = request.GET.get("filters")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (ValueError, TypeError):
            log.warning("malformed filters JSON; ignoring")
    out: dict[str, Any] = {}
    for key in (
        "brands", "discourse", "post_types", "role", "lang", "sentiment",
        "cn_nationalism", "us_nationalism", "country", "region",
    ):
        v = request.GET.get(key)
        if v:
            out[key] = [s for s in v.split(",") if s]
    unsanctioned = request.GET.get("unsanctioned")
    if unsanctioned in ("off", "only", "any"):
        out["unsanctioned"] = unsanctioned
    try:
        window = int(request.GET.get("window", ""))
    except (TypeError, ValueError):
        window = None
    if window in ALLOWED_HOME_WINDOWS:
        out["window"] = window
    return out


_HOVER_FREEZE_MAX_DURATION = timedelta(minutes=5)
_HOVER_FREEZE_HORIZON_TOLERANCE = timedelta(minutes=5)


def _parse_hover_freeze_range(
    request: HttpRequest,
    *,
    window_days: int,
    now: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    """Validate the transient one-day chart bucket used by the public feed."""
    raw_start = request.GET.get("freeze_start")
    raw_end = request.GET.get("freeze_end")
    if not raw_start and not raw_end:
        return None
    if not raw_start or not raw_end or window_days != 1:
        raise ValueError("invalid hover-freeze range")

    start = parse_datetime(raw_start)
    end = parse_datetime(raw_end)
    if (
        start is None
        or end is None
        or not django_timezone.is_aware(start)
        or not django_timezone.is_aware(end)
    ):
        raise ValueError("invalid hover-freeze range")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    duration = end - start
    if duration <= timedelta(0) or duration > _HOVER_FREEZE_MAX_DURATION:
        raise ValueError("invalid hover-freeze range")

    current = (now or django_timezone.now()).astimezone(UTC)
    horizon_start = current - timedelta(days=1) - _HOVER_FREEZE_HORIZON_TOLERANCE
    horizon_end = current + _HOVER_FREEZE_HORIZON_TOLERANCE
    if start < horizon_start or end > horizon_end:
        raise ValueError("invalid hover-freeze range")
    return start, end


_HOME_MULTI_VALUE_FILTERS: tuple[str, ...] = (
    "brands", "discourse", "post_types", "role", "lang", "sentiment",
    "cn_nationalism", "us_nationalism", "country", "region",
)


def _normalize_home_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize stable machine keys without treating an empty list as all."""
    source = filters if isinstance(filters, dict) else {}
    normalized: dict[str, Any] = {}
    for key in _HOME_MULTI_VALUE_FILTERS:
        if key not in source:
            continue
        value = source[key]
        if value == "__all__":
            normalized[key] = "__all__"
            continue
        if not isinstance(value, (list, tuple, set)):
            value = [value] if value not in (None, "") else []
        normalized[key] = list(dict.fromkeys(str(item) for item in value if item not in (None, "")))
    mode = source.get("unsanctioned", "off")
    normalized["unsanctioned"] = mode if mode in {"off", "only", "any"} else "off"
    if "window" in source:
        try:
            window = int(source["window"])
        except (TypeError, ValueError):
            window = HOME_WINDOW_DEFAULT
        normalized["window"] = window if window in ALLOWED_HOME_WINDOWS else HOME_WINDOW_DEFAULT
    return normalized


def _home_chart_cache_key(
    window_days: int,
    normalized_filters: dict[str, Any],
    locale: str,
) -> tuple[Any, ...]:
    """Return a bounded semantic key for one complete home projection."""
    normalized_locale = _normalize_locale(locale)
    locale_key = "zh_cn" if _is_zh_locale(normalized_locale) else normalized_locale
    filter_key = []
    for key, value in sorted(normalized_filters.items()):
        if key == "window":
            continue
        canonical_value = tuple(sorted(value)) if isinstance(value, list) else value
        filter_key.append((key, canonical_value))
    return (window_days, locale_key, tuple(filter_key))


def _post_matches_filter(post: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Return True when a single post satisfies the active control-panel filters.

    Ported from x_monitor/dashboard.py:_post_matches_filter.
    """
    filters = _normalize_home_filters(filters)

    # Brands
    brands = filters.get("brands")
    if brands is not None and brands != "__all__":
        if not brands:
            return False
        post_brands = post.get("brand_nicknames") or []
        if not any(b in brands for b in post_brands):
            return False

    # Discourse
    discourse = filters.get("discourse")
    if discourse is not None and discourse != "__all__":
        if not discourse:
            return False
        post_disc = post.get("discourse") or []
        matches_uncategorized = "uncategorized" in discourse and not post_disc
        matches_classified = any(d in discourse for d in post_disc)
        if not matches_uncategorized and not matches_classified:
            return False

    # Post types
    post_types = filters.get("post_types")
    if post_types is not None and post_types != "__all__":
        if not post_types:
            return False
        post_pts = post.get("post_types") or []
        if not any(p in post_types for p in post_pts):
            return False

    # Sentiment
    sentiment = filters.get("sentiment")
    if sentiment is not None and sentiment != "__all__":
        if not sentiment:
            return False
        post_sentiments = post.get("sentiments") or post.get("sentiment_keys") or []
        if not any(value in sentiment for value in post_sentiments):
            return False

    # Role
    role = filters.get("role")
    if role is not None and role != "__all__":
        if not role:
            return False
        else:
            post_roles = post.get("role_keys")
            if post_roles is None:
                post_roles = [post.get("role_key")] if post.get("role_key") else []
            known_post_roles = {
                value for value in post_roles
                if value in _DASHBOARD_ROLE_FILTER_KEYS[:3]
            }
            if not known_post_roles:
                if "other" not in role:
                    return False
            elif not any(value in role for value in known_post_roles):
                return False

    # Nationalism axes
    for axis in ("cn_nationalism", "us_nationalism"):
        active = filters.get(axis)
        if active is not None and active != "__all__":
            if not active:
                return False
            else:
                post_key = post.get(axis)
                if not post_key:
                    if "none" not in active:
                        return False
                elif post_key not in active:
                    return False

    # Lang
    lang = filters.get("lang")
    if lang is not None and lang != "__all__":
        if not lang:
            return False
        else:
            post_lang = post.get("lang_detected")
            post_lang = _DASHBOARD_LANG_FILTER_KEYS_BY_PERSISTED_VALUE.get(
                post_lang, post_lang
            )
            if not post_lang:
                if "undetected" not in lang:
                    return False
            elif post_lang in _DASHBOARD_LANG_FILTER_KEYS:
                if post_lang not in lang:
                    return False
            else:
                if "other" not in lang:
                    return False

    # Unsanctioned
    mode = filters.get("unsanctioned") or "off"
    is_flagged = bool(post.get("unsanctioned"))
    if mode == "off" and is_flagged:
        return False
    if mode == "only" and not is_flagged:
        return False

    return True


def _filter_home_posts_queryset(
    window_days: int,
    normalized_filters: dict[str, Any],
    *,
    now: datetime,
    queryset: QuerySet | None = None,
    created_at_start: datetime | None = None,
    created_at_end: datetime | None = None,
) -> QuerySet:
    """Return the bounded, set-based Post queryset shared by chart aggregation."""
    queryset = queryset if queryset is not None else Post.objects.all()
    if created_at_start is not None or created_at_end is not None:
        if created_at_start is not None:
            queryset = queryset.filter(created_at__gte=created_at_start)
        if created_at_end is not None:
            queryset = queryset.filter(created_at__lt=created_at_end)
    else:
        queryset = queryset.filter(
            created_at__gte=now - timedelta(days=window_days),
            created_at__lt=now,
        )

    relation_filters = {
        "brands": "brands__brand_id__in",
        "post_types": "signals__post_type_id__in",
        "sentiment": "signals__sentiment_id__in",
        "lang": "lang_detected__in",
    }
    for axis, lookup in relation_filters.items():
        active = normalized_filters.get(axis)
        if active is None or active == "__all__":
            continue
        if not active:
            return queryset.none()
        if axis == "lang":
            known = [
                _DASHBOARD_LANG_PERSISTED_VALUES.get(value, value)
                for value in active
                if value not in {"other", "undetected"}
            ]
            condition = Q(lang_detected__in=known)
            if "undetected" in active:
                condition |= Q(lang_detected__isnull=True) | Q(lang_detected="")
            if "other" in active:
                condition |= (
                    ~Q(lang_detected__in=_DASHBOARD_LANG_KNOWN_PERSISTED_VALUES)
                    & ~Q(lang_detected="")
                    & Q(lang_detected__isnull=False)
                )
            queryset = queryset.filter(condition)
        else:
            queryset = queryset.filter(**{lookup: active})

    active_countries = normalized_filters.get("country")
    if active_countries is not None and active_countries != "__all__":
        if not active_countries:
            return queryset.none()
        queryset = queryset.filter(author__country_id__in=active_countries)

    active_regions = normalized_filters.get("region")
    if active_regions is not None and active_regions != "__all__":
        if not active_regions:
            return queryset.none()
        queryset = queryset.filter(
            Q(author__based_in_region_id__in=active_regions)
            | Q(author__country__region_mapping__region_id__in=active_regions)
        )

    active_discourse = normalized_filters.get("discourse")
    if active_discourse is not None and active_discourse != "__all__":
        if not active_discourse:
            return queryset.none()
        classified_keys = [
            value for value in active_discourse if value != "uncategorized"
        ]
        discourse_condition = Q(
            discourse_signals__discourse_id__in=classified_keys
        )
        if "uncategorized" in active_discourse:
            discourse_condition |= Q(discourse_signals__isnull=True)
        queryset = queryset.filter(discourse_condition)

    for axis, field_name in (
        ("cn_nationalism", "china_nationalism_id"),
        ("us_nationalism", "us_nationalism_id"),
    ):
        active = normalized_filters.get(axis)
        if active is None or active == "__all__":
            continue
        if not active:
            return queryset.none()
        relation_lookup = f"discourse_signals__{field_name}__in"
        condition = Q(**{relation_lookup: active})
        if "none" in active:
            condition |= Q(**{f"discourse_signals__{field_name}__isnull": True})
        queryset = queryset.filter(condition)

    active_roles = normalized_filters.get("role")
    if active_roles is not None and active_roles != "__all__":
        if not active_roles:
            return queryset.none()
        known_roles = _DASHBOARD_ROLE_FILTER_KEYS[:3]
        selected_known = [role for role in active_roles if role in known_roles]
        role_scope = normalized_filters.get("brands")
        role_scope_filter = {}
        if role_scope not in (None, "__all__"):
            role_scope_filter["brand_id__in"] = role_scope
        role_post_filter = {"brand__posts__post__tweet_id": OuterRef("tweet_id")}
        has_known_role = BrandAccount.objects.filter(
            account_id=OuterRef("author_id"),
            role_id__in=known_roles,
            **role_scope_filter,
            **role_post_filter,
        )
        has_selected_role = BrandAccount.objects.filter(
            account_id=OuterRef("author_id"),
            role_id__in=selected_known,
            **role_scope_filter,
            **role_post_filter,
        )
        queryset = queryset.annotate(
            _has_known_role=Exists(has_known_role),
            _has_selected_role=Exists(has_selected_role),
        )
        role_condition = Q(_has_selected_role=True)
        if "other" in active_roles:
            role_condition |= Q(_has_known_role=False)
        queryset = queryset.filter(role_condition)

    unsanctioned = normalized_filters.get("unsanctioned", "off")
    if unsanctioned == "off":
        queryset = queryset.filter(unsanctioned_flags__isnull=True)
    elif unsanctioned == "only":
        queryset = queryset.filter(unsanctioned_flags__isnull=False)
    return queryset.distinct()


# ============================================================================
# Chart serialization (simplified — stub for progressive enhancement)
# ============================================================================


def _build_home_chart_payload(
    window_days: int,
    filters: dict[str, Any],
    *,
    now: datetime | None = None,
    locale: str = "en",
    brand_projection: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build multi-brand chart payload dict — shared by chart_json and chart_html.

    Both granularities aggregate a bounded, normalized Post subquery. The pulse
    projection shares the same timestamp so a client can commit both atomically.
    """
    from django.db.models.functions import TruncDate, TruncMinute

    if window_days not in ALLOWED_HOME_WINDOWS:
        window_days = HOME_WINDOW_DEFAULT
    requested_at = now or django_timezone.now()
    normalized_filters = _normalize_home_filters(filters)
    cache_key = None
    cached_payload = None
    if now is None:
        cache_key = _home_chart_cache_key(window_days, normalized_filters, locale)
        cache_now = monotonic()
        with _HOME_PULSE_CACHE_LOCK:
            cached = _HOME_CHART_CACHE.get(cache_key)
            if cached and cache_now - cached[0] < _HOME_PULSE_CACHE_TTL_SECONDS:
                _HOME_CHART_CACHE.move_to_end(cache_key)
                cached_payload = cached[1]
            elif cached:
                del _HOME_CHART_CACHE[cache_key]
        if cached_payload is not None:
            return deepcopy(cached_payload)

    pulse = _build_home_pulse_payload(window_days, now=requested_at)
    now = datetime.fromisoformat(pulse["computed_at"])

    if brand_projection is None:
        brand_projection = _live_brand_projection()
    brand_nicknames = [brand["nickname"] for brand in brand_projection]
    projection_by_nickname = {
        brand["nickname"]: brand for brand in brand_projection
    }

    # Brand narrowing from filter
    brands_filter = normalized_filters.get("brands")
    if brands_filter is not None and brands_filter != "__all__":
        brand_nicknames = [b for b in brand_nicknames if b in brands_filter]

    colors: dict[str, str] = {
        brand: projection_by_nickname[brand]["accent_color"]
        for brand in brand_nicknames
    }
    totals: dict[str, int] = {brand: 0 for brand in brand_nicknames}
    stacked: dict[str, dict[str, list[int]]] = {
        brand: {} for brand in brand_nicknames
    }

    has_post_filters = any(
        axis != "brands"
        and normalized_filters.get(axis) not in (None, "__all__")
        for axis in _HOME_MULTI_VALUE_FILTERS
    )
    if has_post_filters:
        eligible_posts = _filter_home_posts_queryset(
            window_days,
            normalized_filters,
            now=now,
        ).values("tweet_id")
        links = PostBrand.objects.filter(
            brand_id__in=brand_nicknames,
            post_id__in=Subquery(eligible_posts),
        )
    else:
        links = PostBrand.objects.filter(
            brand_id__in=brand_nicknames,
            post__created_at__gte=now - timedelta(days=window_days),
            post__created_at__lt=now,
        )
        unsanctioned = normalized_filters.get("unsanctioned", "off")
        if unsanctioned == "off":
            links = links.filter(post__unsanctioned_flags__isnull=True)
        elif unsanctioned == "only":
            links = links.filter(post__unsanctioned_flags__isnull=False)

    if window_days == 1:
        # Minute granularity: 288 5-minute buckets, oldest-first labels
        granularity = "minute"
        bucket_count = 288
        cutoff = now - timedelta(days=1)
        days: list[str] = [
            (cutoff + timedelta(minutes=5 * i)).isoformat()
            for i in range(bucket_count)
        ]
        series: dict[str, list[int]] = {
            brand: [0] * bucket_count for brand in brand_nicknames
        }
        aggregate_rows = (
            links.annotate(bucket=TruncMinute("post__created_at"))
            .values("brand_id", "bucket")
            .annotate(count=Count("pk"))
        )
        for row in aggregate_rows:
            bucket = row["bucket"]
            if bucket is None:
                continue
            # The queryset applies the exact cutoff before TruncMinute.  A
            # post in the first partial minute truncates just before cutoff,
            # so map that one eligible bucket to the first chart bucket.
            index = max(0, int((bucket - cutoff).total_seconds() // 300))
            brand = row["brand_id"]
            if brand in series and 0 <= index < bucket_count:
                series[brand][index] += row["count"]
                totals[brand] += row["count"]
    else:
        # Day granularity (oldest-first labels)
        granularity = "day"
        days = [
            (now.date() - timedelta(days=i)).isoformat()
            for i in range(window_days - 1, -1, -1)
        ]
        day_index: dict[str, int] = {d: i for i, d in enumerate(days)}
        series = {
            brand: [0] * window_days for brand in brand_nicknames
        }

        agg_rows = (
            links
            .annotate(day=TruncDate("post__created_at"))
            .values("brand_id", "day")
            .annotate(count=Count("pk"))
        )

        for row in agg_rows:
            brand = row["brand_id"]
            day_str = row["day"].isoformat() if row["day"] else None
            count = row["count"]
            if brand in series and day_str in day_index:
                idx = day_index[day_str]
                series[brand][idx] += count
                totals[brand] += count

    computed_at = pulse["computed_at"]
    from monitor.trend_narrative_projection import project_trend_narrative

    selected_narrative_brands = normalized_filters.get("brands")
    if selected_narrative_brands in (None, "__all__"):
        selected_narrative_brands = None
    trend_narrative = project_trend_narrative(
        window_days,
        locale=locale,
        selected_brand_keys=selected_narrative_brands,
        now=now,
        computed_at=computed_at,
    )
    top_voices = {
        "window_days": window_days,
        "computed_at": computed_at,
        "entries": _multi_top_voices(
            window_days=window_days,
            limit=3,
            now=now,
        ),
    }
    payload = {
        "days": days,
        "series": series,
        "colors": colors,
        "totals": totals,
        "granularity": granularity,
        "stacked": stacked,
        "window_days": window_days,
        "computed_at": computed_at,
        "fetched_at": computed_at,
        "pulse": pulse,
        "trend_narrative": trend_narrative,
        "top_voices": top_voices,
    }
    if cache_key is not None:
        with _HOME_PULSE_CACHE_LOCK:
            component_entries = (
                _HOME_PULSE_CACHE.get(window_days),
                _HOME_TOP_VOICES_CACHE.get((window_days, 3)),
            )
            cache_timestamp = min(
                (entry[0] for entry in component_entries if entry is not None),
                default=monotonic(),
            )
            _HOME_CHART_CACHE[cache_key] = (cache_timestamp, deepcopy(payload))
            _HOME_CHART_CACHE.move_to_end(cache_key)
            while len(_HOME_CHART_CACHE) > _HOME_CHART_CACHE_MAX_ENTRIES:
                _HOME_CHART_CACHE.popitem(last=False)
    return payload


# ============================================================================
# Views — Multi-brand home
# ============================================================================


def _round_pulse_percent(current: int, prior: int) -> int | None:
    """Return a signed whole percent using decimal half-away-from-zero."""
    if prior == 0:
        return None
    value = (Decimal(current - prior) * Decimal(100)) / Decimal(prior)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _clear_home_pulse_cache() -> None:
    """Clear bounded shared home projections (used by deterministic tests)."""
    with _HOME_PULSE_CACHE_LOCK:
        _HOME_CHART_CACHE.clear()
        _HOME_PULSE_CACHE.clear()
        _HOME_TOP_VOICES_CACHE.clear()


def _build_home_pulse_payload(
    window_days: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate equal windows for every non-sentinel DB brand in one query."""
    if window_days not in ALLOWED_HOME_WINDOWS:
        window_days = HOME_WINDOW_DEFAULT
    now = now or django_timezone.now()
    cache_now = monotonic()
    with _HOME_PULSE_CACHE_LOCK:
        cached = _HOME_PULSE_CACHE.get(window_days)
        if cached and cache_now - cached[0] < _HOME_PULSE_CACHE_TTL_SECONDS:
            return deepcopy(cached[1])

        midpoint = now - timedelta(days=window_days)
        start = now - timedelta(days=window_days * 2)
        current_counts = (
            PostBrand.objects
            .filter(
                brand_id=OuterRef("nickname"),
                post__created_at__gte=midpoint,
                post__created_at__lt=now,
            )
            .order_by()
            .values("brand_id")
            .annotate(total=Count("post_id"))
            .values("total")[:1]
        )
        prior_counts = (
            PostBrand.objects
            .filter(
                brand_id=OuterRef("nickname"),
                post__created_at__gte=start,
                post__created_at__lt=midpoint,
            )
            .order_by()
            .values("brand_id")
            .annotate(total=Count("post_id"))
            .values("total")[:1]
        )
        rows = list(
            Brand.objects
            .filter(is_sentinel=False)
            .values(
                "nickname",
                "display_name",
                "display_name_en",
                "display_name_zh_cn",
                "accent_color",
            )
            .annotate(
                current_count=Coalesce(Subquery(current_counts), 0),
                prior_count=Coalesce(Subquery(prior_counts), 0),
            )
        )
        rows.sort(key=lambda row: _home_chart_brand_sort_key(row["nickname"]))
        entries: list[dict[str, Any]] = []
        for row in rows:
            current = row.get("current_count") or 0
            prior = row.get("prior_count") or 0
            delta = _round_pulse_percent(current, prior)
            is_new = prior == 0 and current > 0
            if current == 0 and prior == 0:
                delta = 0
            direction = (
                None if is_new
                else "up" if delta > 0
                else "down" if delta < 0
                else "flat"
            )
            entries.append({
                **_brand_projection_fields(row),
                "current_count": current,
                "prior_count": prior,
                "delta_percent": delta,
                "delta_magnitude": abs(delta) if delta is not None else None,
                "status": "new" if is_new else "numeric",
                "direction": direction,
            })
        payload = {
            "window_days": window_days,
            "computed_at": now.isoformat(),
            "entries": entries,
        }
        _HOME_PULSE_CACHE[window_days] = (cache_now, payload)
        return deepcopy(payload)


def _multi_top_voices(
    window_days: int,
    limit: int = 3,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return top N voice authors in the current window.

    Each entry has handle, voice_star (displayed as ☆ N), mention_count,
    followers_count. Ordered by voice_score DESC.

    voice_score = mention_count * log10(followers_count + 10)
    """
    import math

    cache_key = (window_days, limit)
    cache_now = monotonic()
    with _HOME_PULSE_CACHE_LOCK:
        cached = _HOME_TOP_VOICES_CACHE.get(cache_key)
        if cached and cache_now - cached[0] < _HOME_PULSE_CACHE_TTL_SECONDS:
            return deepcopy(cached[1])

    cutoff = (now or django_timezone.now()) - timedelta(days=window_days)
    qs = (
        Post.objects.filter(created_at__gte=cutoff, author__isnull=False)
        .values("author__handle", "author__author_id", "author__followers_count")
        .annotate(mention_count=Count("tweet_id"))
    )
    out: list[dict[str, Any]] = []
    for row in qs:
        handle = row["author__handle"]
        if not handle:
            continue
        followers = row["author__followers_count"] or 0
        mentions = row["mention_count"] or 0
        score = mentions * math.log10(max(followers, 0) + 10)
        star = max(1, int(round(score)))
        out.append({
            "handle": handle,
            "author_id": row["author__author_id"],
            "voice_score": score,
            "voice_star": star,
            "mention_count": mentions,
            "followers_count": followers,
        })
    out.sort(key=lambda v: (-v["voice_score"], -v["followers_count"]))
    result = out[:limit]
    with _HOME_PULSE_CACHE_LOCK:
        _HOME_TOP_VOICES_CACHE[cache_key] = (cache_now, result)
    return deepcopy(result)


def _build_brands_context(locale: str | None = None) -> list[dict[str, Any]]:
    """Return pre-merged brand data list for templates.

    Each dict has nickname, display_name, accent_color — so templates
    can iterate without needing dict-lookup filters.

    Brands are ordered by the chart's established presentation order, with
    newly onboarded brands appended alphabetically.

    Pulse values are intentionally absent here; they live in the chart payload
    so initial and refreshed chart/pulse projections share one timestamp.
    """
    return _live_brand_projection(locale)


def _partition_home_brands(
    brands: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split the V22 brand lens without inventing a persistence field."""
    by_nickname = {brand["nickname"]: brand for brand in brands}
    closed = [
        by_nickname[nickname]
        for nickname in _HOME_CLOSED_BRAND_NICKNAMES
        if nickname in by_nickname
    ]
    open_ = [brand for brand in brands if brand["nickname"] not in _HOME_CLOSED_BRAND_NICKNAMES]
    return open_, closed


def _home_preferences_namespace(request: HttpRequest) -> str:
    """Return an opaque stable browser-preference namespace for this viewer."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return "anonymous"
    return "user-" + salted_hmac(
        "pushinweight.home.preferences",
        str(user.pk),
    ).hexdigest()[:16]


@ensure_csrf_cookie
def home(request: HttpRequest) -> HttpResponse:
    """GET / — multi-brand Pushin' Weight home page.

    Shows all enabled brands with accent colors and a time-windowed post feed.
    """
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)

    # Pre-merged brand data for template iteration
    brands_data = _build_brands_context(locale)
    brand_nicknames = [b["nickname"] for b in brands_data]
    open_brands, closed_brands = _partition_home_brands(brands_data)
    initial_filters = {
        "brands": [brand["nickname"] for brand in open_brands],
        "window": window_days,
    }
    requested_filters = _parse_filters_from_request(request)
    if requested_filters:
        initial_filters.update(_normalize_home_filters(requested_filters))
        # Keep all server projections on the same already-resolved window.
        initial_filters["window"] = window_days

    feed_rows, feed_cursor, feed_has_more, _normalized_feed_filters = _feed_page_wire(
        locale=locale,
        window_days=window_days,
        filters=initial_filters,
        include_geography=True,
    )

    # Initial chart payload so the canvas renders on first load (no placeholder flash)
    initial_chart_payload = _build_home_chart_payload(
        window_days,
        initial_filters,
        locale=locale,
        brand_projection=brands_data,
    )
    initial_chart_payload["applied_filters"] = initial_filters
    sentiment_keys = list(
        SentimentKey.objects.order_by("key").values_list("key", flat=True)
    )
    filter_entries = _dashboard_filter_entries(locale, sentiment_keys)

    context = {
        "brands": brands_data,
        "open_brands": open_brands,
        "closed_brands": closed_brands,
        "top_voices": initial_chart_payload["top_voices"]["entries"],
        "trend_narrative": initial_chart_payload["trend_narrative"],
        "brand_count": len(brands_data),
        "brand_nicknames_json": json.dumps(brand_nicknames),
        "applied_filters_json": json.dumps(initial_filters),
        "feed": {
            "rows": feed_rows,
            "next_cursor": feed_cursor,
            "has_more": feed_has_more,
        },
        "active_locale": locale,
        "is_zh_chrome": _is_zh_locale(locale),
        "home_window_days": window_days,
        "allowed_home_windows": list(ALLOWED_HOME_WINDOWS),
        "app_name_zh": APP_DISPLAY_NAME_ZH,
        "app_name_en": APP_DISPLAY_NAME_EN,
        "app_title_zh": APP_TITLE_ZH,
        "home_preferences_namespace": _home_preferences_namespace(request),
        **filter_entries,
        "pulse": initial_chart_payload["pulse"],
        "payload": json.dumps(initial_chart_payload),
    }
    return render(request, "monitor/home.html", context)


# ============================================================================
# Views — Single-brand home
# ============================================================================


@login_required
def home_internal(request: HttpRequest) -> HttpResponse:
    """GET /internal/ — legacy multi-brand Pushin' Weight home (pre-v22 chrome).

    U1 (route split): legacy home moved here when v22 chrome replaced /.
    Renders the pre-v22 home.html template (now saved as home_internal.html).
    Same data layer as the v22 home (sharing _resolve_locale, _resolve_home_window,
    _build_brands_context, _get_feed_posts, _post_to_wire, _build_home_chart_payload)
    so behavior is identical except for the visual chrome.
    """
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)

    brands_data = _build_brands_context(locale)
    brand_nicknames = [b["nickname"] for b in brands_data]

    feed_rows, feed_cursor, feed_has_more, _normalized_feed_filters = _feed_page_wire(
        locale=locale,
        window_days=window_days,
        filters={"unsanctioned": "any"},
    )

    initial_chart_payload = _build_home_chart_payload(
        window_days,
        {},
        brand_projection=brands_data,
    )
    initial_chart_payload["applied_filters"] = {}

    context = {
        "brands": brands_data,
        "brand_count": len(brands_data),
        "brand_nicknames_json": json.dumps(brand_nicknames),
        "applied_filters_json": json.dumps({}),
        "feed": {
            "rows": feed_rows,
            "next_cursor": feed_cursor,
            "has_more": feed_has_more,
        },
        "active_locale": locale,
        "home_window_days": window_days,
        "allowed_home_windows": list(ALLOWED_HOME_WINDOWS),
        "app_name_zh": APP_DISPLAY_NAME_ZH,
        "app_name_en": APP_DISPLAY_NAME_EN,
        "app_title_zh": APP_TITLE_ZH,
        "discourse_keys": _DASHBOARD_DISCOURSE_KEYS,
        "post_type_keys": _DASHBOARD_POST_TYPE_KEYS,
        "role_keys": _DASHBOARD_ROLE_FILTER_KEYS,
        "lang_entries": [{"key": k, "label": _DASHBOARD_LANG_DISPLAY_NAMES.get(k, k)} for k in _DASHBOARD_LANG_FILTER_KEYS],
        "nationalism_keys": _DASHBOARD_NATIONALISM_KEYS,
        "pulse": initial_chart_payload["pulse"],
        "payload": json.dumps(initial_chart_payload),
    }
    return render(request, "monitor/home_internal.html", context)


@login_required
def brand_home(
    request: HttpRequest,
    brand: str,
) -> HttpResponse:
    """GET /brands/<brand>/ — single-brand drill-down page."""
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)

    # Validate brand exists
    try:
        brand_obj = Brand.objects.get(nickname=brand, is_sentinel=False)
    except Brand.DoesNotExist:
        raise Http404("Brand not found")

    feed_rows, feed_cursor, feed_has_more, _normalized_feed_filters = _feed_page_wire(
        locale=locale,
        window_days=window_days,
        filters={"unsanctioned": "any"},
        brand_nickname=brand,
    )

    brand_projection = _brand_projection_fields(brand_obj, locale)
    display_name = brand_projection["display_name"]
    accent_color = brand_projection["accent_color"]

    # Initial chart payload so the canvas renders on first load (no placeholder flash)
    initial_brand_chart_payload = _build_brand_chart_payload(
        brand, window_days, {}, "post_type", locale=locale
    )
    initial_brand_chart_payload["applied_filters"] = {}

    context = {
        "applied_filters_json": json.dumps({}),
        "brand_obj": {
            "nickname": brand,
            "display_name": display_name,
            "accent_color": accent_color,
        },
        "brand_id": brand,
        "feed": {
            "rows": feed_rows,
            "next_cursor": feed_cursor,
            "has_more": feed_has_more,
        },
        "active_locale": locale,
        "home_window_days": window_days,
        "allowed_home_windows": list(ALLOWED_HOME_WINDOWS),
        "app_name_zh": APP_DISPLAY_NAME_ZH,
        "app_name_en": APP_DISPLAY_NAME_EN,
        "app_title_zh": APP_TITLE_ZH,
        "discourse_keys": _DASHBOARD_DISCOURSE_KEYS,
        "post_type_keys": _DASHBOARD_POST_TYPE_KEYS,
        "role_keys": _DASHBOARD_ROLE_FILTER_KEYS,
        "lang_entries": [{"key": k, "label": _DASHBOARD_LANG_DISPLAY_NAMES.get(k, k)} for k in _DASHBOARD_LANG_FILTER_KEYS],
        "nationalism_keys": _DASHBOARD_NATIONALISM_KEYS,
        "payload": json.dumps(initial_brand_chart_payload),
    }
    return render(request, "monitor/brand_home.html", context)


# ============================================================================
# Cursor pagination helpers (U2 — cursor-based feed pagination)
# ============================================================================

# Supported sort columns (mirrors _FEED_SORT_COLUMNS in x_monitor/dashboard.py)
_FEED_SORT_COLUMNS: dict[str, str] = {
    "created_at": "created_at",
    "like_count": "like_count",
}
_FEED_DEFAULT_SORT = "created_at"
_FEED_DEFAULT_ORDER = "desc"


def _decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    """Decode a cursor token. Returns (created_at_iso, tweet_id) or None.

    Format: "<iso>|<tweet_id>". Uses pipe as separator because pipe is
    not legal in ISO 8601 timestamps or Twitter tweet IDs.
    """
    if not cursor or "|" not in cursor:
        return None
    iso, _, tweet_id = cursor.partition("|")
    if not iso or not tweet_id:
        return None
    return iso.strip(), tweet_id.strip()


def _serialize_feed_row(
    post: dict[str, Any],
    locale: str,
    *,
    active_brand_scope: str | list[str] | tuple[str, ...] | set[str] | None = "__all__",
    include_geography: bool = False,
) -> dict[str, Any]:
    '''Serialize one enriched post dict to the feed wire shape.

    The enriched dict comes from _enrich_posts_with_classifications and
    already carries classifications_by_brand, brands, brand_nicknames,
    account, label_cache_by_locale, etc.
    '''
    text_translated, is_translated = _pick_translation(post, locale)
    text_original = post.get("text")
    label_cache = post.get("label_cache_by_locale", {}).get(locale, {})

    def _labelize(family: str, key: str | None) -> dict[str, str] | None:
        label = _localize_classification_value(family, key, locale, label_cache)
        if not key:
            return None
        return {"key": key, "label": label if label is not None else key}

    classifications: dict[str, dict[str, Any]] = {}
    for nick, cls in (post.get("classifications_by_brand") or {}).items():
        classifications[nick] = {
            "discourse": [
                v for v in (
                    _labelize("discourse", k)
                    for k in (cls.get("discourse") or [])
                ) if v is not None
            ],
            "post_types": [
                v for v in (
                    _labelize("post_type", k)
                    for k in (cls.get("post_types") or [])
                ) if v is not None
            ],
            "sentiments": [
                v for v in (
                    _labelize("sentiment", k)
                    for k in (cls.get("sentiments") or [])
                ) if v is not None
            ],
            "cn_nationalism": _labelize("nationalism", cls.get("cn_nationalism")),
            "us_nationalism": _labelize("nationalism", cls.get("us_nationalism")),
            "role_label": cls.get("role_label"),
        }

    brands = [
        _brand_projection_fields(brand, locale)
        for brand in (post.get("brands") or [])
    ]

    account_wire = dict(post.get("account") or {})
    geography_source = account_wire.pop("_geography_source", None)
    account_handle = account_wire.get("handle") or post.get("author_handle") or "@unknown"
    account_wire["handle"] = account_handle
    account_wire["display_name"] = _feed_account_display_name(
        account_wire.get("display_name"), post.get("author_name"), account_handle
    )
    display_role = _display_role_key(
        post.get("role_keys") or [account_wire.get("role_key") or account_wire.get("role")]
    )
    account_wire["role"] = display_role
    account_wire["role_label"] = _display_role_label(
        display_role, locale, label_cache
    )
    if include_geography:
        account_wire["geography"] = _feed_geography_wire(
            geography_source, locale
        )

    display_fields = _v22_feed_display_fields(
        classifications,
        locale=locale,
        active_brand_scope=active_brand_scope,
        created_at=post.get("created_at"),
        account=account_wire,
        like_count=post.get("like_count"),
        retweet_count=post.get("retweet_count"),
        reply_count=post.get("reply_count"),
        author_handle=post.get("author_handle"),
    )
    unsanctioned = post.get("unsanctioned", False)
    signal_inspections = _feed_signal_inspections(
        classifications,
        brands,
        locale,
        unsanctioned=unsanctioned,
    )

    return {
        "tweet_id": post["tweet_id"],
        "created_at": post.get("created_at"),
        "created_at_iso": post.get("created_at"),
        "lang_detected": post.get("lang_detected"),
        "language_display": _compact_language_display(
            post.get("lang_detected"), locale
        ),
        "text": text_original,
        "text_original": text_original,
        "text_translated": text_translated,
        "is_translated": is_translated,
        "text_en": post.get("text_en"),
        "text_zh_cn": post.get("text_zh_cn"),
        "commentary_en": post.get("commentary_en"),
        "commentary_zh_cn": post.get("commentary_zh_cn"),
        "like_count": post.get("like_count", 0),
        "retweet_count": post.get("retweet_count", 0),
        "reply_count": post.get("reply_count", 0),
        "brands": brands,
        "brand_nicknames": post.get("brand_nicknames", []),
        "classifications": classifications,
        "signal_inspections": signal_inspections,
        "signal_inspections_json": json.dumps(
            signal_inspections, ensure_ascii=False, separators=(",", ":")
        ),
        "unsanctioned": unsanctioned,
        "enrichment_status": post.get(
            "enrichment_status", PostEnrichmentState.Status.SUCCEEDED
        ),
        "enrichment_status_label": _enrichment_status_label(
            post.get("enrichment_status", PostEnrichmentState.Status.SUCCEEDED),
            locale,
        ),
        "account": account_wire,
        **display_fields,
    }


# ============================================================================
# JSON API — Feed
# ============================================================================


_FEED_CURSOR_VERSION = 2


def _encode_feed_cursor(post: Post, *, sort: str, order: str) -> str:
    """Return an opaque cursor bound to the active sort contract."""
    if sort == "like_count":
        value: str | int = int(post.like_count or 0)
    else:
        value = post.created_at.isoformat() if post.created_at else ""
    payload = json.dumps(
        {
            "v": _FEED_CURSOR_VERSION,
            "sort": sort,
            "order": order,
            "value": value,
            "tweet_id": post.tweet_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_feed_cursor(
    cursor: str | None,
    *,
    sort: str,
    order: str,
) -> tuple[Any, str] | None:
    """Decode a current cursor, accepting legacy created-at cursors safely."""
    if not cursor:
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        UnicodeEncodeError,
        binascii.Error,
    ):
        payload = None
    if isinstance(payload, dict):
        if (
            payload.get("v") != _FEED_CURSOR_VERSION
            or payload.get("sort") != sort
            or payload.get("order") != order
            or not isinstance(payload.get("tweet_id"), str)
            or not payload["tweet_id"]
        ):
            return None
        raw_value = payload.get("value")
        if sort == "like_count":
            if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                return None
            return raw_value, payload["tweet_id"]
        if not isinstance(raw_value, str):
            return None
        parsed = parse_datetime(raw_value)
        if parsed is None or not django_timezone.is_aware(parsed):
            return None
        return parsed, payload["tweet_id"]

    if sort != "created_at":
        return None
    legacy = _decode_cursor(cursor)
    if legacy is None:
        return None
    parsed = parse_datetime(legacy[0])
    if parsed is None or not django_timezone.is_aware(parsed):
        return None
    return parsed, legacy[1]


def _feed_page_posts(
    *,
    window_days: int,
    filters: dict[str, Any],
    sort: str,
    order: str,
    cursor: str | None,
    limit: int,
    brand_nickname: str | None = None,
    created_at_start: datetime | None = None,
    created_at_end: datetime | None = None,
    now: datetime | None = None,
) -> tuple[list[Post], str | None, bool, dict[str, Any]]:
    """Return one filtered database page plus a server-owned continuation."""
    normalized = _normalize_home_filters(filters)
    if brand_nickname:
        normalized["brands"] = [brand_nickname]
    current = now or django_timezone.now()
    terminal_state = Q(
        enrichment_state__translation_status=PostEnrichmentState.Status.SUCCEEDED,
        enrichment_state__classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    eligible = Post.objects.filter(persisted_output_complete_q()).filter(
        Q(enrichment_state__isnull=True) | terminal_state
    )
    queryset = _filter_home_posts_queryset(
        window_days,
        normalized,
        now=current,
        queryset=eligible,
        created_at_start=created_at_start,
        created_at_end=created_at_end,
    )

    sort_field = "created_at"
    if sort == "like_count":
        queryset = queryset.annotate(_feed_sort_value=Coalesce("like_count", 0))
        sort_field = "_feed_sort_value"

    decoded = _decode_feed_cursor(cursor, sort=sort, order=order)
    if decoded is not None:
        value, tweet_id = decoded
        comparison = "lt" if order == "desc" else "gt"
        queryset = queryset.filter(
            Q(**{f"{sort_field}__{comparison}": value})
            | Q(**{sort_field: value, f"tweet_id__{comparison}": tweet_id})
        )

    prefix = "-" if order == "desc" else ""
    bounded = max(1, min(int(limit), FEED_REQUEST_MAX))
    page_with_lookahead = list(
        queryset.select_related("author")
        .prefetch_related(
            Prefetch("brands", queryset=PostBrand.objects.select_related("brand"))
        )
        .order_by(f"{prefix}{sort_field}", f"{prefix}tweet_id")[: bounded + 1]
    )
    has_more = len(page_with_lookahead) > bounded
    page = page_with_lookahead[:bounded]
    next_cursor = (
        _encode_feed_cursor(page[-1], sort=sort, order=order)
        if page and has_more
        else None
    )
    return page, next_cursor, has_more, normalized


def _feed_page_wire(
    *,
    locale: str,
    window_days: int,
    filters: dict[str, Any],
    sort: str = _FEED_DEFAULT_SORT,
    order: str = _FEED_DEFAULT_ORDER,
    cursor: str | None = None,
    limit: int = FEED_DEFAULT_LIMIT,
    brand_nickname: str | None = None,
    include_geography: bool = False,
    created_at_start: datetime | None = None,
    created_at_end: datetime | None = None,
) -> tuple[list[dict[str, Any]], str | None, bool, dict[str, Any]]:
    posts, next_cursor, has_more, normalized = _feed_page_posts(
        window_days=window_days,
        filters=filters,
        sort=sort,
        order=order,
        cursor=cursor,
        limit=limit,
        brand_nickname=brand_nickname,
        created_at_start=created_at_start,
        created_at_end=created_at_end,
    )
    enriched = _enrich_posts_with_classifications(
        posts,
        brand_nickname=brand_nickname,
        include_geography=include_geography,
    )
    rows = [
        _serialize_feed_row(
            post,
            locale,
            active_brand_scope=normalized.get("brands", "__all__"),
            include_geography=include_geography,
        )
        for post in enriched
    ]
    return rows, next_cursor, has_more, normalized


def home_feed_json(request: HttpRequest) -> JsonResponse:
    """GET /feed/ — cursor-paginated feed for multi-brand home.

    Query params: cursor, sort, order, limit, filters, brand, offset.
    """
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)
    try:
        freeze_range = _parse_hover_freeze_range(
            request,
            window_days=window_days,
        )
    except ValueError:
        return JsonResponse({"error": "invalid hover-freeze range"}, status=400)
    if freeze_range is not None:
        normalized = _normalize_home_filters(filters)
        filters = {
            "brands": normalized.get("brands", "__all__"),
            "unsanctioned": "any",
            "window": 1,
        }

    # Parse pagination params
    cursor = request.GET.get("cursor") or None
    sort = request.GET.get("sort", _FEED_DEFAULT_SORT)
    order = request.GET.get("order", _FEED_DEFAULT_ORDER)
    brand_nickname = request.GET.get("brand") or None

    try:
        limit = int(request.GET.get("limit", FEED_DEFAULT_LIMIT))
    except ValueError:
        limit = FEED_DEFAULT_LIMIT
    limit = max(1, min(limit, FEED_REQUEST_MAX))

    # Validate sort / order
    if sort not in _FEED_SORT_COLUMNS:
        sort = _FEED_DEFAULT_SORT
    if order not in ("asc", "desc"):
        order = _FEED_DEFAULT_ORDER

    rows, next_cursor, has_more, _normalized = _feed_page_wire(
        locale=locale,
        window_days=window_days,
        filters=filters,
        brand_nickname=brand_nickname,
        cursor=cursor,
        sort=sort,
        order=order,
        limit=limit,
        include_geography=True,
        created_at_start=freeze_range[0] if freeze_range is not None else None,
        created_at_end=freeze_range[1] if freeze_range is not None else None,
    )

    return JsonResponse({
        "rows": rows,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "applied_filters": filters,
        "locale": locale,
    })


@login_required
def brand_feed_json(request: HttpRequest, brand: str) -> JsonResponse:
    """GET /feed/?brand=<nickname> — cursor-paginated feed for single-brand page.

    Query params: cursor, sort, order, limit, filters, brand, offset.
    """
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)

    # Brand from URL kwarg or query param
    brand_nickname = brand or request.GET.get("brand")
    if not brand_nickname:
        return JsonResponse({"error": "missing brand"}, status=400)

    # Parse pagination params
    cursor = request.GET.get("cursor") or None
    sort = request.GET.get("sort", _FEED_DEFAULT_SORT)
    order = request.GET.get("order", _FEED_DEFAULT_ORDER)

    try:
        limit = int(request.GET.get("limit", FEED_DEFAULT_LIMIT))
    except ValueError:
        limit = FEED_DEFAULT_LIMIT
    limit = max(1, min(limit, FEED_REQUEST_MAX))

    # Validate sort / order
    if sort not in _FEED_SORT_COLUMNS:
        sort = _FEED_DEFAULT_SORT
    if order not in ("asc", "desc"):
        order = _FEED_DEFAULT_ORDER

    rows, next_cursor, has_more, _normalized = _feed_page_wire(
        locale=locale,
        window_days=window_days,
        filters=filters,
        brand_nickname=brand_nickname,
        cursor=cursor,
        sort=sort,
        order=order,
        limit=limit,
    )

    return JsonResponse({
        "rows": rows,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "applied_filters": filters,
        "locale": locale,
    })


# ============================================================================
# JSON API — Charts
# ============================================================================


def chart_json(request: HttpRequest) -> JsonResponse:
    """GET /chart/ — multi-brand chart data (JSON).

    Returns per-day (or per-5min for 1d window) per-brand post counts.
    Query params: window, filters.
    """
    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)
    locale = _resolve_locale(request)
    payload = _build_home_chart_payload(window_days, filters, locale=locale)
    payload["applied_filters"] = filters
    return JsonResponse(payload)


def chart_html(request: HttpRequest) -> HttpResponse:
    """GET /chart.html — multi-brand chart HTML partial for htmx swap.

    Renders the same canvas contract used by both public and legacy home.
    """
    window_days = _resolve_home_window(request)
    locale = _resolve_locale(request)
    filters = _parse_filters_from_request(request)
    payload = _build_home_chart_payload(window_days, filters, locale=locale)
    payload["applied_filters"] = filters
    return render(
        request,
        "monitor/_home_chart.html",
        {
            "payload": json.dumps(payload),
        },
    )


def _build_brand_chart_payload(
    brand_nickname: str,
    window_days: int,
    filters: dict[str, Any],
    tab: str = "post_type",
    *,
    locale: str | None = None,
) -> dict[str, Any]:
    """Build single-brand chart payload dict — shared by brand_chart_json and brand_chart_html.

    Returns the full payload dict (not rendered HTML).
    """
    now = django_timezone.now()

    brand_obj = Brand.objects.filter(nickname=brand_nickname).first()
    if brand_obj is not None and brand_obj.is_sentinel:
        raise Http404("Brand not found")

    posts = _get_feed_posts(
        window_days=window_days,
        brand_nickname=brand_nickname,
        limit=BRAND_CHART_ROW_LIMIT,
    )
    enriched = _enrich_posts_with_classifications(posts, brand_nickname=brand_nickname)
    filtered = [p for p in enriched if _post_matches_filter(p, filters)]

    if window_days == 1:
        granularity = "minute"
        bucket_count = 288
        # Oldest-first labels
        days: list[str] = [
            (now - timedelta(minutes=i)).isoformat()
            for i in range(bucket_count - 1, -1, -1)
        ]
    else:
        granularity = "day"
        bucket_count = window_days
        days = [
            (now.date() - timedelta(days=i)).isoformat()
            for i in range(window_days - 1, -1, -1)
        ]

    series = [0] * bucket_count
    for p in filtered:
        created_at = p.get("created_at")
        if not created_at:
            continue
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if window_days == 1:
            minutes_ago = int((now - dt.replace(tzinfo=timezone.utc)).total_seconds() // 60)
            if minutes_ago < 0 or minutes_ago >= 1440:
                continue
            # With oldest-first days array, idx maps directly
            idx = bucket_count - 1 - (minutes_ago // 5)
        else:
            days_ago = (now.date() - dt.date()).days
            if days_ago < 0 or days_ago >= window_days:
                continue
            idx = window_days - 1 - days_ago
        series[idx] += 1

    brand_obj = (
        brand_obj
        if brand_obj is not None and not brand_obj.is_sentinel
        else None
    )
    brand_projection = (
        _brand_projection_fields(brand_obj, locale)
        if brand_obj is not None
        else _brand_projection_fields({"nickname": brand_nickname}, locale)
    )
    return {
        "brand_id": brand_nickname,
        "display_name": brand_projection["display_name"],
        "accent_color": brand_projection["accent_color"],
        "days": days,
        "granularity": granularity,
        "tab": tab,
        "tab_datasets": {
            "post_type": {"total": series},
        },
        "window_days": window_days,
        "fetched_at": now.isoformat(),
    }


@login_required
def brand_chart_json(request: HttpRequest, brand: str) -> JsonResponse:
    """GET /brand-chart/<brand>/ — single-brand chart data (JSON).

    Query params: window, filters, tab.
    """
    brand_nickname = brand or request.GET.get("brand")
    if not brand_nickname:
        return JsonResponse({"error": "missing brand"}, status=400)

    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)
    tab = request.GET.get("tab", "post_type")
    payload = _build_brand_chart_payload(
        brand_nickname, window_days, filters, tab, locale=_resolve_locale(request)
    )
    payload["applied_filters"] = filters
    return JsonResponse(payload)


@login_required
def brand_chart_html(request: HttpRequest, brand: str) -> HttpResponse:
    """GET /brand-chart/<brand>.html — single-brand chart HTML partial for htmx swap.

    Renders _brand_chart.html with the data-brand-chart JSON payload so
    pw-brand-chart.js can read it from the canvas attribute.
    """
    brand_nickname = brand or request.GET.get("brand")
    if not brand_nickname:
        raise Http404("Brand not found")

    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)
    tab = request.GET.get("tab", "post_type")
    payload = _build_brand_chart_payload(
        brand_nickname, window_days, filters, tab, locale=_resolve_locale(request)
    )
    payload["applied_filters"] = filters
    return render(
        request,
        "monitor/_brand_chart.html",
        {"payload": json.dumps(payload)},
    )


# ============================================================================
# Stub views
# ============================================================================


@login_required
def spend_stub(request: HttpRequest) -> HttpResponse:
    """GET /spend.html — spend panel stub."""
    return render(
        request,
        "monitor/_spend.html",
        {},
    )



def _safe_home_redirect(
    request: HttpRequest,
    *,
    drop_query_keys: tuple[str, ...] = (),
) -> str:
    """Keep cookie-setting endpoints on the dashboard origin."""
    referrer = request.META.get("HTTP_REFERER", "")
    if url_has_allowed_host_and_scheme(
        referrer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        if not drop_query_keys:
            return referrer
        parsed = urlsplit(referrer)
        query = urlencode([
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key not in drop_query_keys
        ])
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))
    return "/"


@require_POST
def set_locale(request: HttpRequest, locale: str) -> HttpResponse:
    """POST /locale/<locale>/ — set locale cookie and redirect back."""
    normalized = _normalize_locale(locale)
    from django.utils import translation
    django_code = {
        "zh_cn": "zh-hans",
        "zh-CN": "zh-hans",
        "zh_hans": "zh-hans",
        "en": "en",
        "original": "en",
    }.get(normalized, "en")
    translation.activate(django_code)
    response = redirect(_safe_home_redirect(request, drop_query_keys=("locale",)))
    response.set_cookie("locale", normalized, max_age=365 * 24 * 3600)
    request.session["_language"] = django_code
    return response


@require_POST
def set_window(request: HttpRequest, days: int) -> HttpResponse:
    """POST /window/<days>/ — set window cookie and redirect back."""
    response = redirect(_safe_home_redirect(request))
    response.set_cookie("home_window", str(days), max_age=365 * 24 * 3600)
    return response
