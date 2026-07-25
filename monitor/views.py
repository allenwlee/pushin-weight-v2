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
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
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

APP_DISPLAY_NAME_ZH = "走个量"
APP_DISPLAY_NAME_EN = "Pushin' Weight"
APP_TITLE_ZH = "走个量Pushin'Weight"  # browser tab only

SUPPORTED_LOCALES: tuple[str, ...] = ("zh_cn", "zh-CN", "zh_hans", "en", "original")

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
        return "zh_cn"
    if locale.casefold() == "original":
        return "original"
    for sup in SUPPORTED_LOCALES:
        if locale.casefold() == sup.casefold():
            return sup
    log.warning("unsupported display_locale %r; falling back to 'en'", locale)
    return "en"


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


def _post_to_wire(post: Post, locale: str, enriched: dict[str, Any] | None = None) -> dict[str, Any]:
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

        # Per-brand classifications — from enrichment when available
        cls_by_brand = enriched.get("classifications_by_brand", {}) if enriched else {}
        cls = cls_by_brand.get(nick, {})
        classifications[nick] = {
            "discourse": cls.get("discourse", []),
            "post_types": cls.get("post_types", []),
            "sentiments": cls.get("sentiments", []),
            "cn_nationalism": cls.get("cn_nationalism"),
            "us_nationalism": cls.get("us_nationalism"),
            "role_label": cls.get("role_label"),
        }

    # Account data — from enrichment when available
    if enriched and enriched.get("account"):
        acc = enriched["account"]
        account_wire = {
            "handle": acc.get("handle") or "@unknown",
            "role": acc.get("role_key"),
            "role_label": acc.get("role_label") or "",
            "followers_count": acc.get("followers_count") or 0,
            "followers_pretty": acc.get("followers_pretty") or "",
        }
    elif post.author:
        account_wire = {
            "handle": post.author.handle or "@unknown",
            "role": None,
            "role_label": "",
            "followers_count": post.author.followers_count or 0,
            "followers_pretty": _pretty_followers(post.author.followers_count),
        }
    else:
        account_wire = {
            "handle": "@unknown", "role": None, "role_label": "",
            "followers_count": 0, "followers_pretty": "",
        }

    created_at_raw = post.created_at.isoformat() if post.created_at else None
    created_at_iso = created_at_raw
    unsanctioned = enriched.get("unsanctioned", False) if enriched else False

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
        "unsanctioned": unsanctioned,
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
                "role_key": role_map.get(post.author_id) if post.author_id else None,
                "role_label": role_map.get(post.author_id) or "",
                "followers_count": post.author.followers_count if post.author else 0,
                "followers_pretty": _pretty_followers(post.author.followers_count if post.author else 0),
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


def _build_home_chart_payload(
    window_days: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Build multi-brand chart payload dict — shared by chart_json and chart_html.

    Uses PostBrand aggregation for day-level windows, and per-post bucketing
    for the 1d minute window. Returns the full payload dict (not rendered HTML).
    """
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    now = django_timezone.now()

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

    colors: dict[str, str] = {
        brand: MODEL_ACCENT_COLORS.get(brand, "#9ca3af")
        for brand in brand_nicknames
    }
    totals: dict[str, int] = {brand: 0 for brand in brand_nicknames}
    stacked: dict[str, dict[str, list[int]]] = {
        brand: {} for brand in brand_nicknames
    }

    if window_days == 1:
        # Minute granularity: 288 5-minute buckets, oldest-first labels
        granularity = "minute"
        bucket_count = 288
        days: list[str] = [
            (now - timedelta(minutes=i)).isoformat()
            for i in range(bucket_count - 1, -1, -1)
        ]
        series: dict[str, list[int]] = {
            brand: [0] * bucket_count for brand in brand_nicknames
        }

        cutoff = now - timedelta(days=1)
        for brand in brand_nicknames:
            posts = _get_feed_posts(
                window_days=1,
                brand_nickname=brand,
                limit=FEED_HARD_CAP,
            )
            for p in posts:
                if not p.created_at:
                    continue
                minutes_ago = int((now - p.created_at).total_seconds() // 60)
                if minutes_ago < 0 or minutes_ago >= 1440:
                    continue
                idx = bucket_count - 1 - (minutes_ago // 5)
                series[brand][idx] += 1
                totals[brand] += 1
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

        cutoff = now - timedelta(days=window_days)
        agg_rows = (
            PostBrand.objects
            .filter(
                brand__nickname__in=brand_nicknames,
                post__created_at__gte=cutoff,
            )
            .annotate(day=TruncDate("post__created_at"))
            .values("brand__nickname", "day")
            .annotate(count=Count("pk"))
            .order_by("day")
        )

        for row in agg_rows:
            brand = row["brand__nickname"]
            day_str = row["day"].isoformat() if row["day"] else None
            count = row["count"]
            if brand in series and day_str in day_index:
                idx = day_index[day_str]
                series[brand][idx] += count
                totals[brand] += count

    return {
        "days": days,
        "series": series,
        "colors": colors,
        "totals": totals,
        "granularity": granularity,
        "stacked": stacked,
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

    Brands are ordered by post volume (descending) for the top 15,
    then alphabetically for any remaining brands.
    """
    _BRAND_ORDER = [
        "deepseek", "qwen", "glm", "minimax", "llama", "mistral",
        "mimo", "doubao", "yi", "hunyuan", "stepfun", "ernie",
        "kuaishou", "upstage", "inclusionai",
    ]
    _order_map = {nick: i for i, nick in enumerate(_BRAND_ORDER)}

    brand_qs = Brand.objects.filter(is_sentinel=False)
    brands = [
        {
            "nickname": b.nickname,
            "display_name": b.display_name or MODEL_DISPLAY_NAMES.get(b.nickname, b.nickname),
            "accent_color": b.accent_color or MODEL_ACCENT_COLORS.get(b.nickname, "#9ca3af"),
            "display_name_en": b.display_name_en or b.display_name or MODEL_DISPLAY_NAMES.get(b.nickname, b.nickname),
            "display_name_zh_cn": b.display_name_zh_cn or b.display_name or MODEL_DISPLAY_NAMES.get(b.nickname, b.nickname),
        }
        for b in brand_qs
    ]
    brands.sort(key=lambda b: (_order_map.get(b["nickname"], 999), b["nickname"]))
    return brands


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
    enriched = _enrich_posts_with_classifications(feed_posts)
    enriched_map = {e["tweet_id"]: e for e in enriched}
    feed_rows = [
        _post_to_wire(p, locale, enriched_map.get(p.tweet_id))
        for p in feed_posts
    ]

    # Initial chart payload so the canvas renders on first load (no placeholder flash)
    initial_chart_payload = _build_home_chart_payload(window_days, {})
    initial_chart_payload["applied_filters"] = {}

    context = {
        "brands": brands_data,
        "brand_count": len(brands_data),
        "brand_nicknames_json": json.dumps(brand_nicknames),
        "applied_filters_json": json.dumps({}),
        "feed": {"rows": feed_rows, "next_cursor": None},
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
        "payload": json.dumps(initial_chart_payload),
    }
    return render(request, "monitor/home.html", context)


# ============================================================================
# Views — Single-brand home
# ============================================================================


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

    # Get posts for this brand
    feed_posts = _get_feed_posts(
        window_days=window_days,
        brand_nickname=brand,
        limit=FEED_DEFAULT_LIMIT,
    )
    enriched = _enrich_posts_with_classifications(feed_posts, brand_nickname=brand)
    enriched_map = {e["tweet_id"]: e for e in enriched}
    feed_rows = [_post_to_wire(p, locale, enriched_map.get(p.tweet_id)) for p in feed_posts]

    display_name = brand_obj.display_name or MODEL_DISPLAY_NAMES.get(brand, brand)
    accent_color = brand_obj.accent_color or MODEL_ACCENT_COLORS.get(brand, "#9ca3af")

    # Initial chart payload so the canvas renders on first load (no placeholder flash)
    initial_brand_chart_payload = _build_brand_chart_payload(brand, window_days, {}, "post_type")
    initial_brand_chart_payload["applied_filters"] = {}

    context = {
        "applied_filters_json": json.dumps({}),
        "brand_obj": {
            "nickname": brand,
            "display_name": display_name,
            "accent_color": accent_color,
        },
        "brand_id": brand,
        "feed": {"rows": feed_rows, "next_cursor": None},
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


def _encode_cursor(created_at: str, tweet_id: str) -> str:
    """Encode a (created_at, tweet_id) pair as a cursor string."""
    return f"{created_at}|{tweet_id}"


def _post_passes_cursor(
    post: dict[str, Any],
    cursor_pair: tuple[str, str],
    order: str,
) -> bool:
    """Check whether a post dict should be included given the cursor.

    For desc: return posts with (created_at, tweet_id) < cursor.
    For asc:  return posts with (created_at, tweet_id) > cursor.
    """
    p_iso = post.get("created_at") or ""
    p_tweet = post.get("tweet_id") or ""
    if not p_iso or not p_tweet:
        return False
    cur_iso, cur_tweet = cursor_pair
    if order == "desc":
        return (p_iso, p_tweet) < (cur_iso, cur_tweet)
    else:
        return (p_iso, p_tweet) > (cur_iso, cur_tweet)


def _serialize_feed_row(post: dict[str, Any], locale: str) -> dict[str, Any]:
    """Serialize one enriched post dict to the feed wire shape.

    The enriched dict comes from _enrich_posts_with_classifications and
    already carries classifications_by_brand, brands, brand_nicknames,
    account, etc.
    """
    text_translated, is_translated = _pick_text(post, locale)
    return {
        "tweet_id": post["tweet_id"],
        "created_at": post.get("created_at"),
        "created_at_iso": post.get("created_at"),
        "lang_detected": post.get("lang_detected"),
        "text": post.get("text"),
        "text_translated": text_translated,
        "is_translated": is_translated,
        "text_en": post.get("text_en"),
        "text_zh_cn": post.get("text_zh_cn"),
        "like_count": post.get("like_count", 0),
        "brands": post.get("brands", []),
        "brand_nicknames": post.get("brand_nicknames", []),
        "classifications": post.get("classifications_by_brand", {}),
        "unsanctioned": post.get("unsanctioned", False),
        "account": post.get("account", {}),
    }


# ============================================================================
# JSON API — Feed
# ============================================================================


def _paginate_feed(
    posts: list[dict[str, Any]],
    *,
    cursor: str | None = None,
    sort: str = _FEED_DEFAULT_SORT,
    order: str = _FEED_DEFAULT_ORDER,
    limit: int = FEED_DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Paginate a list of enriched+filtered post dicts.

    Returns (page, next_cursor, has_more).

    Cursor-based pagination is used for sort=created_at (the default).
    For sort=like_count, falls back to offset-based pagination because
    the DOM cursor is always built from created_at|tweet_id.

    Args:
        posts: list of enriched post dicts, already sorted and filtered.
        cursor: raw cursor string from query param (may be None/malformed).
        sort: "created_at" or "like_count".
        order: "asc" or "desc".
        limit: page size.
        offset: fallback offset for like_count sort.
    """
    cursor_pair = _decode_cursor(cursor) if cursor else None

    if sort == "like_count" or cursor_pair is None:
        # Offset-based fallback
        page = posts[offset:offset + limit]
        has_more = (offset + limit) < len(posts)
        next_cursor: str | None = None
        if page and has_more:
            # Even in offset mode, provide a cursor so pw-feed.js can
            # read it from the last DOM row on the next scroll event.
            last = page[-1]
            if last.get("created_at") and last.get("tweet_id"):
                next_cursor = _encode_cursor(last["created_at"], last["tweet_id"])
        return page, next_cursor, has_more

    # Cursor-based pagination for created_at sort
    rows: list[dict[str, Any]] = []
    had_more_after = False

    for p in posts:
        if len(rows) >= limit:
            # Page is full; scan one more eligible post to determine has_more.
            if _post_passes_cursor(p, cursor_pair, order):
                had_more_after = True
                break
            continue

        if not _post_passes_cursor(p, cursor_pair, order):
            continue

        rows.append(p)

    # has_more: true only when we scanned past a full page and found at
    # least one more eligible post.  When the loop exits naturally with
    # had_more_after=False, we either never filled the page (ran out of
    # data) or filled it on the last post (no more to scan).
    has_more = had_more_after

    next_cursor: str | None = None
    if rows and has_more:
        last = rows[-1]
        if last.get("created_at") and last.get("tweet_id"):
            next_cursor = _encode_cursor(last["created_at"], last["tweet_id"])

    return rows, next_cursor, has_more


@login_required
def home_feed_json(request: HttpRequest) -> JsonResponse:
    """GET /feed/ — cursor-paginated feed for multi-brand home.

    Query params: cursor, sort, order, limit, filters, brand, offset.
    """
    locale = _resolve_locale(request)
    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)

    # Parse pagination params
    cursor = request.GET.get("cursor") or None
    sort = request.GET.get("sort", _FEED_DEFAULT_SORT)
    order = request.GET.get("order", _FEED_DEFAULT_ORDER)
    brand_nickname = request.GET.get("brand") or None

    try:
        limit = int(request.GET.get("limit", FEED_DEFAULT_LIMIT))
    except ValueError:
        limit = FEED_DEFAULT_LIMIT
    limit = min(limit, FEED_HARD_CAP)

    try:
        offset = int(request.GET.get("offset", 0))
    except ValueError:
        offset = 0

    # Validate sort / order
    if sort not in _FEED_SORT_COLUMNS:
        sort = _FEED_DEFAULT_SORT
    if order not in ("asc", "desc"):
        order = _FEED_DEFAULT_ORDER

    # Get all posts in the window
    all_posts = _get_feed_posts(
        window_days=window_days,
        brand_nickname=brand_nickname,
        limit=FEED_HARD_CAP,
    )

    # Enrich with classifications for filtering
    enriched = _enrich_posts_with_classifications(
        all_posts, brand_nickname=brand_nickname,
    )

    # Apply filters
    filtered = [p for p in enriched if _post_matches_filter(p, filters)]

    # Sort in memory (DB already returns -created_at for default)
    if sort == "like_count":
        filtered.sort(key=lambda p: p.get("like_count", 0), reverse=(order == "desc"))
    else:
        # created_at: DB already returns desc; reverse to asc if needed
        if order == "asc":
            filtered.reverse()

    # Paginate
    page, next_cursor, has_more = _paginate_feed(
        filtered,
        cursor=cursor,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )

    rows = [_serialize_feed_row(p, locale) for p in page]

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
    limit = min(limit, FEED_HARD_CAP)

    try:
        offset = int(request.GET.get("offset", 0))
    except ValueError:
        offset = 0

    # Validate sort / order
    if sort not in _FEED_SORT_COLUMNS:
        sort = _FEED_DEFAULT_SORT
    if order not in ("asc", "desc"):
        order = _FEED_DEFAULT_ORDER

    all_posts = _get_feed_posts(
        window_days=window_days,
        brand_nickname=brand_nickname,
        limit=FEED_HARD_CAP,
    )
    enriched = _enrich_posts_with_classifications(
        all_posts, brand_nickname=brand_nickname,
    )

    filtered = [p for p in enriched if _post_matches_filter(p, filters)]

    # Sort in memory
    if sort == "like_count":
        filtered.sort(key=lambda p: p.get("like_count", 0), reverse=(order == "desc"))
    else:
        if order == "asc":
            filtered.reverse()

    # Paginate
    page, next_cursor, has_more = _paginate_feed(
        filtered,
        cursor=cursor,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )

    rows = [_serialize_feed_row(p, locale) for p in page]

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


@login_required
def chart_json(request: HttpRequest) -> JsonResponse:
    """GET /chart/ — multi-brand chart data (JSON).

    Returns per-day (or per-5min for 1d window) per-brand post counts.
    Query params: window, filters.
    """
    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)
    payload = _build_home_chart_payload(window_days, filters)
    payload["applied_filters"] = filters
    return JsonResponse(payload)


@login_required
def chart_html(request: HttpRequest) -> HttpResponse:
    """GET /chart.html — multi-brand chart HTML partial for htmx swap.

    Renders _home_chart.html with the data-home JSON payload so
    pw-chart.js can read it from the canvas attribute.
    """
    window_days = _resolve_home_window(request)
    filters = _parse_filters_from_request(request)
    payload = _build_home_chart_payload(window_days, filters)
    payload["applied_filters"] = filters
    return render(
        request,
        "monitor/_home_chart.html",
        {"payload": json.dumps(payload)},
    )


def _build_brand_chart_payload(
    brand_nickname: str,
    window_days: int,
    filters: dict[str, Any],
    tab: str = "post_type",
) -> dict[str, Any]:
    """Build single-brand chart payload dict — shared by brand_chart_json and brand_chart_html.

    Returns the full payload dict (not rendered HTML).
    """
    now = django_timezone.now()

    posts = _get_feed_posts(
        window_days=window_days,
        brand_nickname=brand_nickname,
        limit=FEED_HARD_CAP,
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

    return {
        "brand_id": brand_nickname,
        "display_name": MODEL_DISPLAY_NAMES.get(brand_nickname, brand_nickname),
        "accent_color": MODEL_ACCENT_COLORS.get(brand_nickname, "#9ca3af"),
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
    payload = _build_brand_chart_payload(brand_nickname, window_days, filters, tab)
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
    payload = _build_brand_chart_payload(brand_nickname, window_days, filters, tab)
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


@csrf_exempt
def debug_i18n(request):
    from django.utils import translation
    from django.utils.translation import gettext as _
    from django.conf import settings
    from django.http import JsonResponse
    import os
    locale_dir = settings.BASE_DIR / "locale"
    mo_path = locale_dir / "zh_Hans" / "LC_MESSAGES" / "django.mo"
    translation.activate("zh-hans")
    return JsonResponse({
        "language_code": settings.LANGUAGE_CODE,
        "get_language": translation.get_language(),
        "mo_exists": os.path.exists(str(mo_path)),
        "mo_size": os.path.getsize(str(mo_path)) if os.path.exists(str(mo_path)) else 0,
        "Filters": _("Filters"),
        "datetime": _("datetime"),
        "brand": _("brand"),
        "translated": _("translated"),
        "Password": _("Password"),
    })


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
    response = redirect(request.META.get("HTTP_REFERER", "/"))
    response.set_cookie("locale", normalized, max_age=365 * 24 * 3600)
    request.session["_language"] = django_code
    return response


def set_window(request: HttpRequest, days: int) -> HttpResponse:
    """POST /window/<days>/ — set window cookie and redirect back."""
    response = redirect(request.META.get("HTTP_REFERER", "/"))
    response.set_cookie("home_window", str(days), max_age=365 * 24 * 3600)
    return response
