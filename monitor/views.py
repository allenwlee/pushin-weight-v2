"""Pushin' Weight dashboard views — Django port (U7).

Replaces the Flask routes in x_monitor/dashboard.py and
x_monitor/_home_routes.py with Django ORM-powered views behind
the allauth login wall.

Start simple: multi-brand home, single-brand drill-down, JSON feed
and chart APIs. JS-heavy features (infinite scroll, live charts)
are progressively enhanced.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone as django_timezone

from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandCompany,
    Company,
    Post,
    PostBrand,
    PostBrandDiscourse,
    PostBrandSignal,
    PostUnsanctionedFlag,
)

log = logging.getLogger(__name__)

# ============================================================================
# Constants ported from x_monitor/dashboard.py
# ============================================================================

MODEL_DISPLAY_NAMES: dict[str, str] = {
    "minimax": "MiniMax AI",
    "qwen": "Qwen",
    "deepseek": "DeepSeek",
    "glm": "Zhipu GLM",
    "mimo": "Xiaomi MiMo",
    "moonshot_kimi": "Moonshot Kimi",
    "inclusionai": "InclusionAI",
    "mistral": "Mistral",
    "stepfun": "StepFun",
    "ernie": "Baidu ERNIE",
    "hunyuan": "Tencent Hunyuan",
    "llama": "Meta Llama",
    "nemo_megatron": "NVIDIA Megatron",
    "doubao": "ByteDance Doubao",
    "yi": "01.AI Yi",
    "sensechat": "SenseTime SenseChat",
    "exaone": "LG EXAONE",
    "kuaishou": "Kuaishou Kling",
    "sakana_ai": "Sakana AI",
    "upstage": "Upstage Solar",
}

MODEL_ACCENT_COLORS: dict[str, str] = {
    "minimax": "#3b82f6",
    "qwen": "#f97316",
    "deepseek": "#10b981",
    "glm": "#a855f7",
    "mimo": "#eab308",
    "moonshot_kimi": "#ec4899",
    "inclusionai": "#06b6d4",
    "mistral": "#facc15",
    "stepfun": "#22c55e",
    "ernie": "#0ea5e9",
    "hunyuan": "#ec4899",
    "llama": "#14b8a6",
    "nemo_megatron": "#84cc16",
    "doubao": "#f43f5e",
    "yi": "#8b5cf6",
    "sensechat": "#d946ef",
    "exaone": "#0d9488",
    "kuaishou": "#fb923c",
    "sakana_ai": "#6366f1",
    "upstage": "#dc2626",
}

APP_DISPLAY_NAME_ZH = "走个量"  # 走个量
APP_DISPLAY_NAME_EN = "Pushin' Weight"

SUPPORTED_LOCALES: tuple[str, ...] = ("en", "zh-CN", "zh_cn")

_LOCALE_TO_COLUMN: dict[str, str] = {
    "en": "en",
    "zh-CN": "zh_cn",
    "zh_cn": "zh_cn",
    "original": "__source__",
}

# Taxonomy keys — single source of truth for filter control panels
_DASHBOARD_DISCOURSE_KEYS: tuple[str, ...] = (
    "genuine_hype", "sarcasm", "dunk_yingyang",
    "self_deprecation", "cope", "fud",
    "distillation_accusation", "ai_slop_critique",
    "absurdist_meme", "advertising-marketing",
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

ALLOWED_HOME_WINDOWS: tuple[int, ...] = (1, 7, 30, 365)
HOME_WINDOW_DEFAULT: int = 7
HOME_WINDOW_COOKIE: str = "home_window"

FEED_HARD_CAP: int = 500
FEED_DEFAULT_LIMIT: int = 50


# ============================================================================
# Locale helpers
# ============================================================================


def _normalize_locale(locale: str | None) -> str:
    """Return a supported locale or 'en' (with a warning log) for unsupported."""
    if not locale:
        return "en"
    if locale.casefold() == "original":
        return "original"
    for sup in SUPPORTED_LOCALES:
        if locale.casefold() == sup.casefold():
            return sup
    log.warning("unsupported display_locale %r; falling back to 'en'", locale)
    return "en"


def _pick_text(post: Any, locale: str) -> tuple[str | None, bool]:
    """Return (display_text, is_translated) for a post in the given locale.

    Accepts either a Post ORM instance or a dict with text/text_en/text_zh_cn keys.
    """
    column = _LOCALE_TO_COLUMN.get(locale, "en")
    if column == "__source__":
        text = getattr(post, "text", None) if hasattr(post, "text") else post.get("text")
        return text, False
    if column == "zh_cn":
        translated = getattr(post, "text_zh_cn", None) if hasattr(post, "text_zh_cn") else post.get("text_zh_cn")
    else:
        translated = getattr(post, "text_en", None) if hasattr(post, "text_en") else post.get("text_en")
    if translated:
        return translated, True
    text = getattr(post, "text", None) if hasattr(post, "text") else post.get("text")
    return text, False


def _resolve_locale(request: HttpRequest) -> str:
    """Read display locale from cookie or Django's active language.

    Priority: ?locale= query param > locale cookie > Django language > 'en'.
    """
    locale = request.GET.get("locale") or request.COOKIES.get("locale")
    if locale:
        return _normalize_locale(locale)
    # Fall back to Django's detected language
    from django.utils import translation
    lang = translation.get_language()
    if lang and lang != "en":
        return _normalize_locale(lang)
    return "en"


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
) -> QuerySet:
    """Return a QuerySet of Posts for the feed view, with brand and account prefetching.

    Args:
        window_days: optional time window filter
        brand_nickname: optional single-brand scope
        limit: max rows to return
    """
    cutoff = None
    if window_days:
        cutoff = django_timezone.now() - timedelta(days=window_days)

    qs = Post.objects.select_related("author").prefetch_related(
        Prefetch(
            "brands",
            queryset=PostBrand.objects.select_related("brand"),
        ),
    ).order_by("-created_at")

    if cutoff:
        qs = qs.filter(created_at__gte=cutoff)
    if brand_nickname:
        qs = qs.filter(brands__brand__nickname=brand_nickname).distinct()

    return qs[:limit]


# ============================================================================
# Wire serialization (mirrors _feed_row_to_wire from dashboard.py)
# ============================================================================


def _post_to_wire(post: Post, locale: str) -> dict[str, Any]:
    """Serialize a Post ORM instance to the JSON wire shape for the feed.

    Mirrors x_monitor/dashboard.py:_feed_row_to_wire.
    """
    text_translated, is_translated = _pick_text(post, locale)
    text_original = post.text

    # Brand data from PostBrand junction
    brand_nicknames: list[str] = []
    brands_wire: list[dict[str, Any]] = []
    classifications: dict[str, dict[str, Any]] = {}
    for pb in post.brands.all():
        nick = pb.brand.nickname
        brand_nicknames.append(nick)
        brands_wire.append({
            "nickname": nick,
            "display_name": pb.brand.display_name or MODEL_DISPLAY_NAMES.get(nick, nick),
            "display_name_en": pb.brand.display_name_en or pb.brand.display_name or MODEL_DISPLAY_NAMES.get(nick, nick),
            "display_name_zh_cn": pb.brand.display_name_zh_cn or pb.brand.display_name or MODEL_DISPLAY_NAMES.get(nick, nick),
        })

        # Per-brand classifications (stub — full enrichment in later units)
        classifications[nick] = {
            "discourse": [],
            "post_types": [],
            "sentiments": [],
            "cn_nationalism": None,
            "us_nationalism": None,
        }

    # Account data
    account_wire: dict[str, Any] = {"handle": "@unknown", "role": None, "followers_count": 0}
    if post.author:
        account_wire = {
            "handle": post.author.handle or "@unknown",
            "role": None,
            "followers_count": post.author.followers_count or 0,
        }

    created_at_raw = post.created_at.isoformat() if post.created_at else None
    created_at_iso = created_at_raw

    return {
        "tweet_id": post.tweet_id,
        "created_at": created_at_raw,
        "created_at_iso": created_at_iso,
        "lang_detected": post.lang_detected,
        "text": text_original,
        "text_translated": text_translated,
        "is_translated": is_translated,
        "text_en": post.text_en,
        "text_zh_cn": post.text_zh_cn,
        "like_count": post.like_count or 0,
        "brands": brands_wire,
        "brand_nicknames": brand_nicknames,
        "classifications": classifications,
        "unsanctioned": False,  # stub — full enrichment later
        "account": account_wire,
    }


def _enrich_posts_with_classifications(
    posts: QuerySet,
    brand_nickname: str | None = None,
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

    # Account roles for the brand
    role_map: dict[str, str] = {}
    if brand_nickname:
        ba_qs = BrandAccount.objects.filter(
            brand_id=brand_nickname,
        ).select_related("role")
        for ba in ba_qs:
            if ba.account_id:
                role_map[ba.account_id] = ba.role.key if ba.role_id else None

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

    # Build enriched dicts
    result: list[dict[str, Any]] = []
    for post in posts:
        tid = post.tweet_id
        row: dict[str, Any] = {
            "tweet_id": tid,
            "created_at": post.created_at.isoformat() if post.created_at else None,
            "text": post.text,
            "text_en": post.text_en,
            "text_zh_cn": post.text_zh_cn,
            "like_count": post.like_count or 0,
            "lang_detected": post.lang_detected,
            "author_handle": post.author_handle,
            "author_id": post.author_id,
            "headline": post.headline,
            "headline_source": post.headline_source,
            "source_query_id": post.source_query_id,
            "discourse": [],
            "post_types": [],
            "sentiments": [],
            "cn_nationalism": None,
            "us_nationalism": None,
            "role_key": role_map.get(post.author_id) if post.author_id else None,
            "unsanctioned": tid in flag_tweet_ids,
            "brand_nicknames": [],
            "brands": [],
            "classifications_by_brand": {},
            "account": {
                "handle": post.author.handle if post.author else (post.author_handle or "@unknown"),
                "role": role_map.get(post.author_id) if post.author_id else None,
                "followers_count": post.author.followers_count if post.author else 0,
            },
        }

        # Merge per-brand data from PostBrand junction + classifications
        for pb in post.brands.all():
            nick = pb.brand.nickname
            if nick not in row["brand_nicknames"]:
                row["brand_nicknames"].append(nick)
            row["brands"].append({
                "nickname": nick,
                "display_name": MODEL_DISPLAY_NAMES.get(nick, nick),
                "display_name_en": MODEL_DISPLAY_NAMES.get(nick, nick),
                "display_name_zh_cn": MODEL_DISPLAY_NAMES.get(nick, nick),
            })

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
    for key in ("discourse", "post_types", "role", "lang", "cn_nationalism", "us_nationalism"):
        v = request.GET.get(key)
        if v:
            out[key] = [s for s in v.split(",") if s]
    unsanctioned = request.GET.get("unsanctioned")
    if unsanctioned in ("off", "only", "any"):
        out["unsanctioned"] = unsanctioned
    return out


def _post_matches_filter(post: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Return True when a single post satisfies the active control-panel filters.

    Ported from x_monitor/dashboard.py:_post_matches_filter.
    """
    # Brands
    brands = filters.get("brands")
    if brands is not None and brands != "__all__":
        post_brands = post.get("brand_nicknames") or []
        if not any(b in brands for b in post_brands):
            return False

    # Discourse
    discourse = filters.get("discourse")
    if discourse is not None and discourse != "__all__":
        if not discourse:  # empty list means no filter active
            pass
        else:
            post_disc = post.get("discourse") or []
            if post_disc and not any(d in discourse for d in post_disc):
                return False

    # Post types
    post_types = filters.get("post_types")
    if post_types is not None and post_types != "__all__":
        if not post_types:
            pass
        else:
            post_pts = post.get("post_types") or []
            if post_pts and not any(p in post_types for p in post_pts):
                return False

    # Role
    role = filters.get("role")
    if role is not None and role != "__all__":
        if not role:
            pass
        else:
            post_role = post.get("role_key")
            if post_role is None or post_role not in _DASHBOARD_ROLE_FILTER_KEYS[:3]:
                if "other" not in role:
                    return False
            else:
                if post_role not in role:
                    return False

    # Nationalism axes
    for axis in ("cn_nationalism", "us_nationalism"):
        active = filters.get(axis)
        if active is not None and active != "__all__":
            if not active:
                pass
            else:
                post_key = post.get(axis)
                if post_key is not None and post_key not in active:
                    return False

    # Lang
    lang = filters.get("lang")
    if lang is not None and lang != "__all__":
        if not lang:
            pass
        else:
            post_lang = post.get("lang_detected")
            if post_lang is None:
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


# ============================================================================
# Chart serialization (simplified — stub for progressive enhancement)
# ============================================================================


def _serialize_home_chart_simple(
    brand_nicknames: list[str],
    posts_by_brand: dict[str, list[dict[str, Any]]],
    window_days: int = 7,
) -> dict[str, Any]:
    """Simplified multi-brand chart payload.

    Returns per-day, per-brand total post counts. Full sentiment/discourse
    breakdown will be added in a later unit (mirrors serialize_home_chart).
    """
    now = django_timezone.now()
    days: list[str] = [
        (now.date() - timedelta(days=i)).isoformat()
        for i in range(window_days - 1, -1, -1)
    ]

    series: dict[str, list[int]] = {}
    colors: dict[str, str] = {}
    totals: dict[str, int] = {}

    for brand in brand_nicknames:
        series[brand] = [0] * window_days
        colors[brand] = MODEL_ACCENT_COLORS.get(brand, "#9ca3af")
        totals[brand] = 0

    for brand in brand_nicknames:
        for p in posts_by_brand.get(brand, []):
            created_at = p.get("created_at")
            if not created_at:
                continue
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            days_ago = (now.date() - dt.date()).days
            if days_ago < 0 or days_ago >= window_days:
                continue
            idx = window_days - 1 - days_ago
            series[brand][idx] += 1
            totals[brand] += 1

    return {
        "days": days,
        "series": series,
        "colors": colors,
        "totals": totals,
        "window_days": window_days,
        "fetched_at": now.isoformat(),
    }


# ============================================================================
# Views — Multi-brand home
# ============================================================================


def _build_brands_context() -> list[dict[str, Any]]:
    """Return pre-merged brand data list for templates.

    Each dict has nickname, display_name, accent_color — so templates
    can iterate without needing dict-lookup filters.
    """
    brand_qs = Brand.objects.filter(is_sentinel=False).order_by("nickname")
    return [
        {
            "nickname": b.nickname,
            "display_name": b.display_name or MODEL_DISPLAY_NAMES.get(b.nickname, b.nickname),
            "accent_color": b.accent_color or MODEL_ACCENT_COLORS.get(b.nickname, "#9ca3af"),
            "display_name_en": b.display_name_en or b.display_name or MODEL_DISPLAY_NAMES.get(b.nickname, b.nickname),
            "display_name_zh_cn": b.display_name_zh_cn or b.display_name or MODEL_DISPLAY_NAMES.get(b.nickname, b.nickname),
        }
        for b in brand_qs
    ]


@login_required
def home(request: HttpRequest) -> HttpResponse:
    """GET / — multi-brand Pushin' Weight home page.

    Shows all enabled brands with accent colors and a time-windowed post feed.
    """
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)

    # Pre-merged brand data for template iteration
    brands_data = _build_brands_context()
    brand_nicknames = [b["nickname"] for b in brands_data]

    # Get recent posts with brand associations for feed
    feed_posts = _get_feed_posts(window_days=window_days, limit=FEED_DEFAULT_LIMIT)
    feed_rows = [
        _post_to_wire(p, locale)
        for p in feed_posts
    ]

    context = {
        "brands": brands_data,
        "brand_count": len(brands_data),
        "brand_nicknames_json": json.dumps(brand_nicknames),
        "feed": {"rows": feed_rows, "next_cursor": None},
        "active_locale": locale,
        "home_window_days": window_days,
        "allowed_home_windows": list(ALLOWED_HOME_WINDOWS),
        "app_name_zh": APP_DISPLAY_NAME_ZH,
        "app_name_en": APP_DISPLAY_NAME_EN,
        "discourse_keys": _DASHBOARD_DISCOURSE_KEYS,
        "post_type_keys": _DASHBOARD_POST_TYPE_KEYS,
        "role_keys": _DASHBOARD_ROLE_FILTER_KEYS,
        "lang_entries": [{"key": k, "label": _DASHBOARD_LANG_DISPLAY_NAMES.get(k, k)} for k in _DASHBOARD_LANG_FILTER_KEYS],
        "nationalism_keys": _DASHBOARD_NATIONALISM_KEYS,
        "chart_json": json.dumps({"days": [], "series": {}, "colors": {}, "totals": {}}),
    }
    return render(request, "monitor/home.html", context)


# ============================================================================
# Views — Single-brand home
# ============================================================================


@login_required
def brand_home(
    request: HttpRequest,
    company: str,
    brand: str,
) -> HttpResponse:
    """GET /<company>/<brand>/ — single-brand drill-down page.

    company="_" matches brands with no company parent.
    """
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)

    # Validate brand exists
    try:
        brand_obj = Brand.objects.get(nickname=brand, is_sentinel=False)
    except Brand.DoesNotExist:
        raise Http404("Brand not found")

    # Validate company ownership
    company_is_underscore = (company == "_")
    if company_is_underscore:
        if BrandCompany.objects.filter(brand_id=brand).exists():
            raise Http404("Brand has a company parent; use /<company>/<brand>/")
    else:
        try:
            Company.objects.get(nickname=company)
        except Company.DoesNotExist:
            raise Http404("Company not found")
        if not BrandCompany.objects.filter(brand_id=brand, company_id=company).exists():
            raise Http404("Brand not owned by this company")

    # Get posts for this brand
    feed_posts = _get_feed_posts(
        window_days=window_days,
        brand_nickname=brand,
        limit=FEED_DEFAULT_LIMIT,
    )
    feed_rows = [_post_to_wire(p, locale) for p in feed_posts]

    display_name = brand_obj.display_name or MODEL_DISPLAY_NAMES.get(brand, brand)
    accent_color = brand_obj.accent_color or MODEL_ACCENT_COLORS.get(brand, "#9ca3af")

    context = {
        "brand_obj": {
            "nickname": brand,
            "display_name": display_name,
            "accent_color": accent_color,
        },
        "brand_id": brand,
        "company": company,
        "company_underscore": company_is_underscore,
        "feed": {"rows": feed_rows, "next_cursor": None},
        "active_locale": locale,
        "home_window_days": window_days,
        "allowed_home_windows": list(ALLOWED_HOME_WINDOWS),
        "app_name_zh": APP_DISPLAY_NAME_ZH,
        "app_name_en": APP_DISPLAY_NAME_EN,
        "discourse_keys": _DASHBOARD_DISCOURSE_KEYS,
        "post_type_keys": _DASHBOARD_POST_TYPE_KEYS,
        "role_keys": _DASHBOARD_ROLE_FILTER_KEYS,
        "lang_entries": [{"key": k, "label": _DASHBOARD_LANG_DISPLAY_NAMES.get(k, k)} for k in _DASHBOARD_LANG_FILTER_KEYS],
        "nationalism_keys": _DASHBOARD_NATIONALISM_KEYS,
        "chart_json": json.dumps({"days": [], "tab_datasets": {}, "tab": "post_type"}),
    }
    return render(request, "monitor/brand_home.html", context)


# ============================================================================
# JSON API — Feed
# ============================================================================


@login_required
def home_feed_json(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/home.feed.json — paginated feed for multi-brand home.

    Query params: locale, sort, order, offset, limit, filters.
    """
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)

    try:
        offset = int(request.GET.get("offset", 0))
    except ValueError:
        offset = 0
    try:
        limit = int(request.GET.get("limit", FEED_DEFAULT_LIMIT))
    except ValueError:
        limit = FEED_DEFAULT_LIMIT
    limit = min(limit, FEED_HARD_CAP)

    # Get all posts in the window
    all_posts = _get_feed_posts(
        window_days=window_days,
        brand_nickname=None,
        limit=FEED_HARD_CAP,
    )

    # Enrich with classifications for filtering
    enriched = _enrich_posts_with_classifications(all_posts)

    # Apply filters
    filtered = [p for p in enriched if _post_matches_filter(p, filters)]

    # Paginate
    total = len(filtered)
    page = filtered[offset : offset + limit]
    next_offset = offset + limit if offset + limit < total else None

    rows = []
    for p in page:
        text_translated, is_translated = _pick_text(p, locale)
        rows.append({
            "tweet_id": p["tweet_id"],
            "created_at": p["created_at"],
            "created_at_iso": p["created_at"],
            "lang_detected": p.get("lang_detected"),
            "text": p.get("text"),
            "text_translated": text_translated,
            "is_translated": is_translated,
            "text_en": p.get("text_en"),
            "text_zh_cn": p.get("text_zh_cn"),
            "like_count": p.get("like_count", 0),
            "brands": p.get("brands", []),
            "brand_nicknames": p.get("brand_nicknames", []),
            "classifications": p.get("classifications_by_brand", {}),
            "unsanctioned": p.get("unsanctioned", False),
            "account": p.get("account", {}),
        })

    return JsonResponse({
        "rows": rows,
        "next_offset": next_offset,
        "has_more": next_offset is not None,
        "total": total,
        "offset": offset,
        "limit": limit,
        "applied_filters": filters,
        "locale": locale,
    })


@login_required
def brand_feed_json(request: HttpRequest, brand: str) -> JsonResponse:
    """GET /api/v1/brand.feed.json — paginated feed for single-brand page.

    URL params: /api/v1/brand.feed.json?brand=<nickname>
    Query params: locale, sort, order, offset, limit, filters.
    """
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)

    # brand from URL param or query param
    brand_nickname = brand or request.GET.get("brand")
    if not brand_nickname:
        return JsonResponse({"error": "missing brand"}, status=400)

    try:
        offset = int(request.GET.get("offset", 0))
    except ValueError:
        offset = 0
    try:
        limit = int(request.GET.get("limit", FEED_DEFAULT_LIMIT))
    except ValueError:
        limit = FEED_DEFAULT_LIMIT
    limit = min(limit, FEED_HARD_CAP)

    all_posts = _get_feed_posts(
        window_days=window_days,
        brand_nickname=brand_nickname,
        limit=FEED_HARD_CAP,
    )
    enriched = _enrich_posts_with_classifications(all_posts, brand_nickname=brand_nickname)

    filtered = [p for p in enriched if _post_matches_filter(p, filters)]

    total = len(filtered)
    page = filtered[offset : offset + limit]
    next_offset = offset + limit if offset + limit < total else None

    rows = []
    for p in page:
        text_translated, is_translated = _pick_text(p, locale)
        rows.append({
            "tweet_id": p["tweet_id"],
            "created_at": p["created_at"],
            "created_at_iso": p["created_at"],
            "lang_detected": p.get("lang_detected"),
            "text": p.get("text"),
            "text_translated": text_translated,
            "is_translated": is_translated,
            "text_en": p.get("text_en"),
            "text_zh_cn": p.get("text_zh_cn"),
            "like_count": p.get("like_count", 0),
            "brands": p.get("brands", []),
            "brand_nicknames": p.get("brand_nicknames", []),
            "classifications": p.get("classifications_by_brand", {}),
            "unsanctioned": p.get("unsanctioned", False),
            "account": p.get("account", {}),
        })

    return JsonResponse({
        "rows": rows,
        "next_offset": next_offset,
        "has_more": next_offset is not None,
        "total": total,
        "offset": offset,
        "limit": limit,
        "applied_filters": filters,
        "locale": locale,
    })


# ============================================================================
# JSON API — Charts
# ============================================================================


@login_required
def home_chart_json(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/home.chart.json — multi-brand chart data.

    Returns per-day, per-brand post counts for the active window.
    Query params: window, filters.

    Stub implementation — returns simplified totals. Full sentiment/
    discourse breakdown will be added progressively.
    """
    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)

    # Get enabled brands
    brand_nicknames = list(
        Brand.objects.filter(is_sentinel=False)
        .order_by("nickname")
        .values_list("nickname", flat=True)
    )

    # Brand narrowing from filter
    brands_filter = filters.get("brands")
    if brands_filter is not None and brands_filter != "__all__":
        brand_nicknames = [b for b in brand_nicknames if b in brands_filter]

    # Single aggregation query instead of per-brand loop.
    # PostBrand JOIN gives us per-brand post counts grouped by day.
    cutoff = django_timezone.now() - timedelta(days=window_days)
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    agg_rows = (
        PostBrand.objects
        .filter(
            brand__nickname__in=brand_nicknames,
            post__created_at__gte=cutoff,
        )
        .annotate(day=TruncDate("post__created_at"))
        .values("brand__nickname", "day")
        .annotate(count=Count("id"))
        .order_by("day")
    )

    # Build the same payload shape the serializer expects
    now = django_timezone.now()
    days: list[str] = [
        (now.date() - timedelta(days=i)).isoformat()
        for i in range(window_days - 1, -1, -1)
    ]
    day_index: dict[str, int] = {d: i for i, d in enumerate(days)}

    series: dict[str, list[int]] = {
        brand: [0] * window_days for brand in brand_nicknames
    }
    colors: dict[str, str] = {
        brand: MODEL_ACCENT_COLORS.get(brand, "#9ca3af")
        for brand in brand_nicknames
    }
    totals: dict[str, int] = {brand: 0 for brand in brand_nicknames}

    for row in agg_rows:
        brand = row["brand__nickname"]
        day_str = row["day"].isoformat() if row["day"] else None
        count = row["count"]
        if brand in series and day_str in day_index:
            idx = day_index[day_str]
            series[brand][idx] += count
            totals[brand] += count

    payload = {
        "days": days,
        "series": series,
        "colors": colors,
        "totals": totals,
        "window_days": window_days,
        "fetched_at": now.isoformat(),
    }
    payload["applied_filters"] = filters

    # Render as HTML partial so htmx can swap the canvas element.
    # The pw-chart.js reads data-home attribute to draw the chart.
    import json as _json
    return render(
        request,
        "monitor/_home_chart.html",
        {"payload": _json.dumps(payload)},
    )


@login_required
def brand_chart_json(request: HttpRequest, brand: str) -> JsonResponse:
    """GET /api/v1/brand.chart.json — single-brand chart data.

    URL params: /api/v1/brand.chart.json?brand=<nickname>
    Query params: window, filters, tab.

    Stub implementation — returns simplified totals.
    """
    brand_nickname = brand or request.GET.get("brand")
    if not brand_nickname:
        return JsonResponse({"error": "missing brand"}, status=400)

    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)
    tab = request.GET.get("tab", "post_type")

    posts = _get_feed_posts(
        window_days=window_days,
        brand_nickname=brand_nickname,
        limit=FEED_HARD_CAP,
    )
    enriched = _enrich_posts_with_classifications(posts, brand_nickname=brand_nickname)
    filtered = [p for p in enriched if _post_matches_filter(p, filters)]

    # Build simplified chart
    now = django_timezone.now()
    if window_days == 1:
        bucket_count = 288
        days = [
            (now - timedelta(minutes=i)).isoformat()
            for i in range(bucket_count)
        ]
    else:
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
            idx = bucket_count - 1 - (minutes_ago // 5)
        else:
            days_ago = (now.date() - dt.date()).days
            if days_ago < 0 or days_ago >= window_days:
                continue
            idx = window_days - 1 - days_ago
        series[idx] += 1

    payload = {
        "brand_id": brand_nickname,
        "display_name": MODEL_DISPLAY_NAMES.get(brand_nickname, brand_nickname),
        "accent_color": MODEL_ACCENT_COLORS.get(brand_nickname, "#9ca3af"),
        "days": days,
        "tab": tab,
        "tab_datasets": {
            "post_type": {"total": series},
        },
        "applied_filters": filters,
        "window_days": window_days,
        "fetched_at": now.isoformat(),
    }
    import json as _json
    return render(
        request,
        "monitor/_home_chart.html",
        {"payload": _json.dumps(payload)},
    )


# ============================================================================
# Stub views — U1 scaffold (beefed up in U2–U5)
# ============================================================================


@login_required
def spend_stub(request: HttpRequest) -> HttpResponse:
    """GET /spend.html — spend panel stub (U5 fleshes this out)."""
    return render(
        request,
        "monitor/_spend.html",
        {},
    )


def set_locale(request: HttpRequest, locale: str) -> HttpResponse:
    """POST /locale/<locale>/ — set locale cookie and redirect back."""
    normalized = _normalize_locale(locale)
    response = redirect(request.META.get("HTTP_REFERER", "/"))
    response.set_cookie("locale", normalized, max_age=365 * 24 * 3600)
    return response


def set_window(request: HttpRequest, days: int) -> HttpResponse:
    """POST /window/<days>/ — set window cookie and redirect back."""
    response = redirect(request.META.get("HTTP_REFERER", "/"))
    response.set_cookie("home_window", str(days), max_age=365 * 24 * 3600)
    return response
