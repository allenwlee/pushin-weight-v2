# {{AGENT_ATTRIBUTION}}
"""Local Flask dashboard: 9-model grid + per-model drill-down (Unit 7+8)."""

from __future__ import annotations

import json
import logging
import os
import re

from markupsafe import Markup
import signal
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request, make_response, redirect, url_for
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .account_graph import build_force_directed
from .config import Config
from .store import Store
from .treemap import (
    TreemapTile,
    build_treemap_svg,
    compute_polarity_from_db,
)

log = logging.getLogger(__name__)


# Display name map for the 20 v1 models (11 v1 + 9 pushin_weight additions).
# PR-reviewable; tweak per brand team feedback without touching the rest of the code.
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

# Accent color per model — drives the card border-left + sparkline stroke.
# 20-color palette tuned for the dark bg; adjacent brands are visually distinct.
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


_BRAND_RE = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in MODEL_ACCENT_COLORS) + r")\b",
    flags=re.IGNORECASE,
)


# Supported display locales. Anything else falls back to "en" with a
# warning log. The columns are populated by x_monitor.translator (Unit 4)
# and consumed by _pick_text (Unit 6).
SUPPORTED_LOCALES: tuple[str, ...] = ("en", "zh-CN", "zh_cn")

# Maps a user-facing locale (e.g. "zh-CN") to the DB column suffix
# used in `text_<suffix>`. Both "zh-CN" and "zh_cn" map to "zh_cn".
# "original" maps to a sentinel that signals "_pick_text should
# return the source `text` column directly, not a translation".
_LOCALE_TO_COLUMN: dict[str, str] = {
    "en": "en",
    "zh-CN": "zh_cn",
    "zh_cn": "zh_cn",
    "original": "__source__",
}


# Product rename (U1 of feat/pushin-weight-home-pages, 2026-07-06):
# "Pushin' Weight (走个量)" is the new external-facing name. The
# internal `x_monitor` package name is preserved per plan R17; this
# affects only the chrome (topbar <h1> + <title>) and the per-page
# greeting text.
APP_DISPLAY_NAME_ZH = "走个量"
APP_DISPLAY_NAME_EN = "Pushin' Weight"


def normalize_locale(locale: str | None) -> str:
    """Return a supported locale or "en" (with a warning log) for unsupported.

    Args:
        locale: the user-supplied locale string (from query/cookie).
            None or empty string → "en".

    Returns:
        A member of SUPPORTED_LOCALES. Unsupported values fall back
        to "en" and emit a warning log.
    """
    if not locale:
        return "en"
    # "original" is the v1 of pushin-weight-home-pages (U1) "show source text"
    # locale — it sits in the locale enum but bypasses _pick_text's translation
    # column lookup. Treated as a first-class supported value, not an
    # unknown value that would fall through to "en".
    if locale.casefold() == "original":
        return "original"
    # Case-insensitive check
    for sup in SUPPORTED_LOCALES:
        if locale.casefold() == sup.casefold():
            return sup
    log.warning(
        "unsupported display_locale %r; falling back to 'en'", locale
    )
    return "en"


def _pick_text(
    post: dict[str, Any],
    locale: str,
) -> tuple[str | None, bool]:
    """Return `(display_text, is_translated)` for a post in the given locale.

    The post is expected to have `text` (source), `text_en`, and
    `text_zh_cn` columns. The function reads `text_<column>` for the
    requested locale; if NULL, falls back to the source `text` and
    sets `is_translated=False`.

    Args:
        post: dict with at least `text`, `text_en`, `text_zh_cn`.
        locale: a supported locale from SUPPORTED_LOCALES.

    Returns:
        A 2-tuple of (text, is_translated). `is_translated` is False
        when the dashboard is showing the source `text` because the
        translation is NULL.
    """
    column = _LOCALE_TO_COLUMN.get(locale, "en")
    # "original" locale (U1 of pushin-weight-home-pages) returns the
    # source `text` column directly, regardless of available translations.
    if column == "__source__":
        return post.get("text"), False
    translated = post.get(f"text_{column}")
    if translated:
        return translated, True
    # Fall back to source text. is_translated=False signals to the
    # template to render a "translation pending" / "(English source)"
    # / "(中文原文)" badge.
    return post.get("text"), False


# --- v1.7 i18n dashboard helpers -----------------------------------------
#
# Locale-aware lookups for the dashboard. Both helpers read from the
# per-locale columns seeded by migration 006 / Unit 4's translator.
# The model_definitions list is the model identifier set across the
# dashboard / API / charts; the chart series tuple in
# serialize_grid_card drives the rendered bar segments.

# U9 (migration 022): the legacy 6-signal taxonomy is gone. The chart
# series keys are now sentiments. post_type is reported separately via
# `post_type_breakdown`. This tuple is the single source of truth for
# the order/render of the stacked-bar chart series.
_DASHBOARD_SENTIMENT_KEYS: tuple[str, ...] = (
    "positive", "negative", "neutral", "mixed",
)

_DASHBOARD_POST_TYPE_KEYS: tuple[str, ...] = (
    "buzz_releases", "hands_on_usage",
    "performance_comparisons", "feedback_questions",
    # v1.12 (migration 027): two new keys for promotional / event posts.
    # Pushin' Weight home pages (R7, U2) ship these as part of the
    # post_type filter group.
    "advertising_marketing", "event_announcement",
)

# Pushin' Weight home pages (R7) — 10-key discourse taxonomy. Mirrors
# the 9 keys seeded by migration 026 + the 10th (advertising-marketing
# with a hyphen, per the existing migration 027 insert) added in the
# same migration. The order is the same as the on-screen filter
# checkboxes; do not reorder without updating R7 + A8.
_DASHBOARD_DISCOURSE_KEYS: tuple[str, ...] = (
    "genuine_hype", "sarcasm", "dunk_yingyang",
    "self_deprecation", "cope", "fud",
    "distillation_accusation", "ai_slop_critique",
    "absurdist_meme", "advertising-marketing",
)

# 3-key role taxonomy (R7). Roles live on `brands_accounts.role_id` and
# are resolved to text keys via the `roles` table. Order is on-screen
# order; do not reorder without updating R7.
_DASHBOARD_ROLE_KEYS: tuple[str, ...] = (
    "official", "staff", "community",
)

# 6-step nationalism scale (R7, migration 026). One tuple is used for
# both cn_nationalism and us_nationalism axes; the axis is the dict
# key on the filter shape.
_DASHBOARD_NATIONALISM_KEYS: tuple[str, ...] = (
    "none", "mild_pro", "pro",
    "constructive_critical", "anti", "mixed",
)


def _load_brand_display_names(
    store: Store, locale: str
) -> dict[str, str]:
    """Return {brand_id: display_name} for all enabled brand rows in `locale`.

    Reads `display_name`, `display_name_en`, `display_name_zh_cn` from
    the `brands` table for every brand and resolves each one through
    `Store._pick_i18n_text` (the locale → _en → source fallback chain
    per D6). Falls back to `MODEL_DISPLAY_NAMES[brand_id]` if the row
    has no `display_name` at all (defensive; should not happen
    post-backfill).
    """
    suffix = _LOCALE_TO_COLUMN.get(locale, "en")
    rows = store._conn.execute(
        f"SELECT nickname AS brand_id, display_name, display_name_{suffix} AS locale_name, "
        "display_name_en FROM brands"
    ).fetchall()
    out: dict[str, str] = {}
    for r in rows:
        brand_id = r["brand_id"]
        row = {
            "display_name": r["display_name"],
            "display_name_en": r["display_name_en"],
            "display_name_zh_cn": (
                r["locale_name"] if suffix == "zh_cn" else None
            ),
        }
        text, _is_translated = Store._pick_i18n_text(
            row, "display_name", locale
        )
        out[brand_id] = text or MODEL_DISPLAY_NAMES.get(brand_id, brand_id)
    return out


def _load_signal_labels(store: Store, locale: str) -> dict[str, str]:
    """Return {sentiment_key: localized_label} for the chart series keys.

    U9 (migration 022): replaced the legacy 6-signal `_load_signal_labels`
    with a sentiment-keyed variant. The function name is preserved for
    backwards compat with the trend-chart JS that still emits the
    `data-signal-labels` attribute. New code should prefer
    `_load_sentiment_labels` for clarity.

    Used by the trend-chart JS to render localized tooltip labels. Falls
    back to the English label if the requested locale is missing
    (mirrors Store._pick_enum_label's fallback chain), and to the raw
    sentiment key if both lookups miss (defensive: avoids rendering the
    literal string 'None' on unseeded enums).
    """
    return _load_sentiment_labels(store, locale)


def _load_sentiment_labels(store: Store, locale: str) -> dict[str, str]:
    """Return {sentiment_key: localized_label} for the chart series keys.

    U9 (migration 022): the chart series keys are now sentiment keys
    (positive / negative / neutral / mixed), not the legacy 6-signal
    taxonomy.
    """
    suffix = _LOCALE_TO_COLUMN.get(locale, "en")
    out: dict[str, str] = {}
    for key in _DASHBOARD_SENTIMENT_KEYS:
        out[key] = store._pick_enum_label("sentiment", key, suffix) or key
    return out


def _load_post_type_labels(store: Store, locale: str) -> dict[str, str]:
    """Return {post_type_key: localized_label} for the post-type filter chips.

    U9 (migration 022): post_type is reported alongside sentiment for
    every per-brand classification. The filter chip set is the 4-key
    taxonomy (buzz_releases / hands_on_usage / performance_comparisons /
    feedback_questions).
    """
    suffix = _LOCALE_TO_COLUMN.get(locale, "en")
    out: dict[str, str] = {}
    for key in _DASHBOARD_POST_TYPE_KEYS:
        out[key] = store._pick_enum_label("post_type", key, suffix) or key
    return out


def _load_role_labels(
    store: Store, locale: str, role_ids: list[str]
) -> dict[str, str]:
    """Return {role_id: localized_label} for the role bars on /brand/<id>.

    Defensive: empty input → empty dict.
    """
    suffix = _LOCALE_TO_COLUMN.get(locale, "en")
    out: dict[str, str] = {}
    for key in role_ids:
        out[key] = store._pick_enum_label("role", key, suffix) or key
    return out


def brand_colorize(text: str) -> str:
    """Colorize brand_id matches in `text` with the brand's accent color.

    Word-boundary, case-insensitive. Escapes HTML first so we can safely
    inject raw <span> tags as replacements - the filter is the only path
    that introduces HTML into auto-escaped Jinja output.
    """
    if not text:
        return ""
    escaped = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace(chr(34), "&quot;")
    )
    def _sub(m):
        token = m.group(0)
        canonical = token.lower()
        if canonical not in MODEL_ACCENT_COLORS:
            return token
        color = MODEL_ACCENT_COLORS[canonical]
        return f'<span style="color: {color}; font-weight: 600;">{token}</span>'
    return Markup(_BRAND_RE.sub(_sub, escaped))


# --- Sparkline ------------------------------------------------------------


# --- Card data assembly ---------------------------------------------------


def _load_latest_run(runs_dir: Path) -> dict[str, Any] | None:
    if not runs_dir.exists():
        return None
    latest = runs_dir / "LATEST.json"
    target = latest.resolve() if latest.is_symlink() else None
    if target and target.exists():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def summarize_http_log(log: list[dict] | None) -> dict[str, Any]:
    """Aggregate per-cycle HTTP spend from `summary["http_log"]`.

    Used by both the new dashboard /api/spend.* routes and the existing
    scripts/dump_http_log.py shape (latency_percentiles stays in
    dump_http_log; this helper stays dashboard-local for the panel
    render). Kept here so the same aggregation is reused by tests.

    Returns a dict with:
      - n_requests          total HTTP requests in the cycle
      - total_duration_ms   sum of all per-request durations
      - by_endpoint         {path: {n, mean_ms, max_ms}}
      - by_status           {status_int: count}
      - n_results           sum of n_results across requests
    Empty log -> all zeros, empty dicts.
    """
    out: dict[str, Any] = {
        "n_requests": 0,
        "total_duration_ms": 0,
        "by_endpoint": {},
        "by_status": {},
        "n_results": 0,
    }
    if not log:
        return out

    # Pass 1: aggregate per-endpoint counts and durations.
    per_endpoint: dict[str, dict[str, int]] = {}
    for r in log:
        path = r.get("path") or "?"
        dur = int(r.get("duration_ms") or 0)
        status = r.get("status")
        per_endpoint.setdefault(path, {"n": 0, "total_dur": 0, "max_dur": 0})
        per_endpoint[path]["n"] += 1
        per_endpoint[path]["total_dur"] += dur
        if dur > per_endpoint[path]["max_dur"]:
            per_endpoint[path]["max_dur"] = dur
        if status is not None:
            out["by_status"][status] = out["by_status"].get(status, 0) + 1
        out["n_results"] += int(r.get("n_results") or 0)

    out["n_requests"] = len(log)
    out["total_duration_ms"] = sum(
        int(r.get("duration_ms") or 0) for r in log
    )
    for path, agg in per_endpoint.items():
        n = agg["n"]
        out["by_endpoint"][path] = {
            "n": n,
            "mean_ms": agg["total_dur"] / n if n else 0,
            "max_ms": agg["max_dur"],
        }
    return out


def _parse_post_timestamp(created):
    """Parse a tweet created_at into an aware UTC datetime, or None.

    Accepts ISO 8601 ("Z" or "+HH:MM") and Twitter legacy
    ("Mon Jun 08 22:40:07 +0000 2026").
    """
    if not created:
        return None
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None


# Canonical query_id -> expected_signal mapping. The legacy 6-signal
# taxonomy (Q1=release / Q2=community_question / Q3=criticism /
# Q4=commenter_capture / Q5=other / Q6=praise) was replaced in U9 by the
# (post_type × sentiment) decomposition, so the v1.8 grid card reads
# from posts_brands_signals directly via _read_classification_breakdown_for_brand.
# The combined chart (v2.0) still renders per-signal stacks via
# source_query_id, so this mapping is kept as a local dependency of
# serialize_combined_chart / _qid_to_signal only.
_QID_TO_SIGNAL: dict[str, str] = {
    "Q1": "release",
    "Q2": "community_question",
    "Q3": "criticism",
    "Q4": "commenter_capture",
    "Q5": "other",
    "Q6": "praise",
}



# Allowed values for the polarity window toggle (v1.7.4). 1d is the daily
# pulse (high variance, may be sparse); 7d is the weekly default; 30d is
# the long-range trend (lower variance, requires window_days >= 30, which
# we clamp at read time). The literal tuple is the single source of truth
# for both the route validator and the topbar template loop.
ALLOWED_POLARITY_WINDOWS: tuple[int, ...] = (1, 7, 30)
POLARITY_WINDOW_COOKIE = "polarity_window"


def _resolve_polarity_window(req, default: int) -> int:
    """Read the polarity window from a Flask request's cookies.

    Returns the validated int if the cookie is set to one of the allowed
    values; otherwise returns `default`. Defensive: any malformed value
    (non-int, out of range, negative) falls back to the default rather
    than raising, so a stale or hand-edited cookie can't crash the page.
    """
    raw = req.cookies.get(POLARITY_WINDOW_COOKIE)
    if raw is None:
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    if n not in ALLOWED_POLARITY_WINDOWS:
        return default
    return n


def _clamp_polarity_window(window: int, ceiling: int) -> int:
    """Clamp the polarity window to the config's window_days ceiling.

    The polarity prior window is [anchor - 2N, anchor - N), so it requires
    2*N days of post history. With the default config window_days=14,
    picking 30d from the toggle would extend the prior window to 60d ago,
    which is outside the post history. We silently clamp to the ceiling
    rather than crash or extend the prior window into nothing.

    The user's choice is preserved in the cookie; only the read-time
    computation is clamped. The 1d choice is always honored (N=1 means
    the prior window is 1 day ago, well within any reasonable history).
    """
    return max(1, min(window, ceiling))


# Combined chart window: stock-chart style, 1d-360d. Default 30d (matches
# the treemap default). The combined chart has no prior-window comparison,
# so unlike the polarity window there is NO clamp to dashboard.window_days.
# Picking 360d with only 14d of history renders early days as zeros (the
# operator sees their own data sparsity).
ALLOWED_COMBINED_WINDOWS: tuple[int, ...] = (1, 7, 14, 30, 60, 90, 180, 360)
COMBINED_WINDOW_COOKIE = "combined_window"
COMBINED_WINDOW_DEFAULT = 30


def _resolve_combined_window(req, default: int) -> int:
    """Read the combined chart window from a Flask request's cookies.

    Returns the validated int if the cookie is set to one of the allowed
    values; otherwise returns `default`. Defensive: any malformed value
    (non-int, out of range, negative) falls back to the default rather
    than raising, so a stale or hand-edited cookie can't crash the page.

    Unlike _resolve_polarity_window, this helper does NOT clamp to
    dashboard.window_days — the combined chart has no prior-window
    comparison, and zero-fill early days is the correct behavior when
    the operator picks a window wider than available history.
    """
    raw = req.cookies.get(COMBINED_WINDOW_COOKIE)
    if raw is None:
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    if n not in ALLOWED_COMBINED_WINDOWS:
        return default
    return n


# Pushin' Weight home-page window (U1 of feat/pushin-weight-home-pages,
# 2026-07-06). The user-facing toggle is 1d / 7d / 30d / 1y, which is
# deliberately narrower than the combined chart's 8-value set (1, 7, 14,
# 30, 60, 90, 180, 360) — the home page UX is targeted at the four
# natural time horizons, not the stock-chart granularity. Per A5 the
# cookie is NOT clamped to dashboard.window_days; the home page can show
# any of 1d/7d/30d/1y regardless of post history (early days render as
# zero, matching the combined chart's D4 precedent).
ALLOWED_HOME_WINDOWS: tuple[int, ...] = (1, 7, 30, 365)
HOME_WINDOW_COOKIE = "home_window"
HOME_WINDOW_DEFAULT = 7


def _resolve_home_window(req, default: int) -> int:
    """Read the Pushin' Weight home-page window from a Flask request's cookies.

    Mirrors `_resolve_combined_window`: returns the validated int if the
    cookie is set to one of the allowed values; otherwise returns
    `default`. Defensive: malformed/absent/out-of-range falls back to the
    default rather than raising. Does NOT clamp to dashboard.window_days
    per A5.
    """
    raw = req.cookies.get(HOME_WINDOW_COOKIE)
    if raw is None:
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    if n not in ALLOWED_HOME_WINDOWS:
        return default
    return n


def _qid_to_signal(qid: str) -> str | None:
    """Map a source_query_id to its expected_signal name, or None for unknown.

    Local dependency of serialize_combined_chart (v2.0). Kept alongside
    `_QID_TO_SIGNAL` because the grid card no longer uses signals after U9.
    """
    return _QID_TO_SIGNAL.get(qid)


def resolve_vanity_url_for_brand(
    store: Store, brand_id: str
) -> tuple[str, str] | None:
    """Return `(company_or_underscore, brand)` for a brand's vanity URL.

    U5 of feat/pushin-weight-home-pages (2026-07-06). Joins brands +
    brands_companies + companies. If the brand has exactly one company
    parent, returns `(company.nickname, brand.nickname)`. If the brand
    has no company parent (e.g. `_unattributed`, or any brandless
    orphan), returns `("_", brand.nickname)`. Returns `None` if the
    brand doesn't exist.

    The single-parent constraint matches the v1 model: a brand is
    expected to belong to at most one corporate parent. If a future
    plan adds many-to-many, this helper will need to be updated to
    disambiguate (e.g. by returning a list and asking the caller to
    pick).
    """
    row = store._conn.execute(
        "SELECT nickname FROM brands WHERE nickname = ?",
        (brand_id,),
    ).fetchone()
    if row is None:
        return None
    parent = store._conn.execute(
        """
        SELECT c.nickname AS company_nickname
        FROM brands_companies bc
        JOIN companies c ON c.id = bc.company_id
        WHERE bc.brand_id = (SELECT id FROM brands WHERE nickname = ?)
        LIMIT 2
        """,
        (brand_id,),
    ).fetchall()
    if len(parent) == 0:
        return ("_", brand_id)
    if len(parent) > 1:
        # Defensive: warn and pick the first
        log.warning(
            "brand %r has %d company parents; picking the first",
            brand_id, len(parent),
        )
    return (parent[0]["company_nickname"], brand_id)


def resolve_brand_via_vanity(
    store: Store, company: str, brand: str
) -> str | None:
    """Reverse of `resolve_vanity_url_for_brand`: given a (company,
    brand) pair, return the brand_id if the brand is owned by that
    company. `company="_"` matches brands with no parent.

    Returns None when:
        - the brand doesn't exist;
        - the company doesn't exist;
        - the brand exists but is not owned by the given company
          (R12: `/<wrong-company>/<brand>` returns 404, not 302).

    Used by the `/<company>/<brand>` and `/_/<brand>` routes.
    """
    brand_row = store._conn.execute(
        "SELECT nickname FROM brands WHERE nickname = ?",
        (brand,),
    ).fetchone()
    if brand_row is None:
        return None
    if company == "_":
        # Company-less lookup: the brand must have ZERO company
        # parents for the match to succeed.
        n_parents = store._conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM brands_companies bc
            WHERE bc.brand_id = (SELECT id FROM brands WHERE nickname = ?)
            """,
            (brand,),
        ).fetchone()["n"]
        if n_parents == 0:
            return brand
        return None
    # Company-specific lookup: the company must exist AND own the brand
    company_row = store._conn.execute(
        "SELECT nickname FROM companies WHERE nickname = ?",
        (company,),
    ).fetchone()
    if company_row is None:
        return None
    owned = store._conn.execute(
        """
        SELECT 1
        FROM brands_companies bc
        JOIN brands b   ON b.id   = bc.brand_id
        JOIN companies c ON c.id  = bc.company_id
        WHERE b.nickname = ? AND c.nickname = ?
        """,
        (brand, company),
    ).fetchone()
    if owned is None:
        return None
    return brand


def _read_classification_breakdown_for_brand(
    conn,
    brand_id: str,
    window_start_iso: str,
) -> tuple[
    dict[str, float],
    dict[str, dict[str, float]],
    dict[str, float],
    dict[str, dict[str, float]],
]:
    """Read posts_brands_signals for one brand grouped by sentiment + post_type.

    U9 (migration 022): replaces the legacy signal-keyed breakdown.
    Returns BOTH sentiment totals + per-day AND post_type totals +
    per-day, so the dashboard can render the stacked-bar chart
    (sentiment series) and the post-type filter chips without a
    second query.

    JOINs posts_brands_signals + posts_brands + posts per Decision 18
    (no IN subquery). The _unattributed sentinel is excluded by the
    WHERE clause (Decision 15). Weights are honored (1/N for multi-brand
    posts per Decision 9).

    U8 (migration 020): posts_brands_signals FK columns are INTEGER.
    Join via posts.id and brands.id; resolve the brand slug to its
    INTEGER id before the WHERE filter.

    Returns:
        (sentiment_totals, sentiment_per_day,
         post_type_totals, post_type_per_day) where each dict has the
        same shape:
          totals[key] = float (weighted_count)
          per_day[iso_date][key] = float (weighted_count)
    """
    brand_id_int = conn.execute(
        "SELECT id FROM brands WHERE nickname = ?", (brand_id,)
    ).fetchone()
    if brand_id_int is None:
        return {}, {}, {}, {}
    brand_id_int = int(brand_id_int["id"])
    rows = conn.execute(
        """
        SELECT substr(p.created_at, 1, 10) AS day,
               sk.key AS sentiment,
               ptk.key AS post_type,
               SUM(pb.weight) AS weighted_count
        FROM posts_brands_signals pbs
        JOIN posts_brands pb
          ON pb.post_id = pbs.post_id AND pb.brand_id = pbs.brand_id
        JOIN posts p ON p.id = pbs.post_id
        JOIN sentiment_keys sk ON sk.id = pbs.sentiment
        JOIN post_type_keys ptk ON ptk.id = pbs.post_type
        JOIN brands b ON b.id = pbs.brand_id
        WHERE pbs.brand_id = ?
          AND b.nickname != '_unattributed'
          AND p.created_at >= ?
        GROUP BY day, sk.key, ptk.key
        """,
        (brand_id_int, window_start_iso),
    ).fetchall()
    sent_totals: dict[str, float] = {}
    sent_per_day: dict[str, dict[str, float]] = {}
    pt_totals: dict[str, float] = {}
    pt_per_day: dict[str, dict[str, float]] = {}
    for r in rows:
        sent = r["sentiment"]
        pt = r["post_type"]
        w = float(r["weighted_count"])
        sent_totals[sent] = sent_totals.get(sent, 0.0) + w
        d_sent = sent_per_day.setdefault(r["day"], {})
        d_sent[sent] = d_sent.get(sent, 0.0) + w
        pt_totals[pt] = pt_totals.get(pt, 0.0) + w
        d_pt = pt_per_day.setdefault(r["day"], {})
        d_pt[pt] = d_pt.get(pt, 0.0) + w
    return sent_totals, sent_per_day, pt_totals, pt_per_day


def serialize_grid_card(
    brand_id: str,
    posts: list[dict[str, Any]],
    *,
    window_days: int = 14,
    latest_run: dict[str, Any] | None = None,
    now: datetime | None = None,
    display_locale: str = "en",
    sentiment_breakdown: dict[str, float] | None = None,
    day_sentiment_counts: dict[str, dict[str, float]] | None = None,
    post_type_breakdown: dict[str, float] | None = None,
    day_post_type_counts: dict[str, dict[str, float]] | None = None,
    display_name: str | None = None,
    signal_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return the per-model grid card payload.

    U9 (migration 022): the legacy 6-signal breakdown is replaced by a
    (sentiment × post_type) decomposition. The chart renders 4 sentiment
    series (positive / negative / neutral / mixed). Post-type counts are
    exposed in the response payload for the per-model filter chips
    (buzz_releases / hands_on_usage / performance_comparisons /
    feedback_questions).

    Args:
        brand_id: the model slug (e.g. "minimax").
        posts: list of post dicts (from `Store.get_all_posts`).
        window_days: total window for the chart (default 14).
        latest_run: parsed LATEST.json (or None) for sentinel rendering.
        now: anchor timestamp for window cutoffs (test seam).
        display_locale: which locale to render top-3 post text in.
            Default "en". Supported: "en", "zh-CN", "zh_cn".
            Unsupported → "en" with a warning log.
        display_name: pre-resolved localized brand name (i18n Unit 5).
            When None, falls back to MODEL_DISPLAY_NAMES.
        sentiment_breakdown: pre-resolved {sentiment_key: weighted_count}
            (U9: replaces `signal_breakdown`). Reads from
            posts_brands_signals via _read_classification_breakdown_for_brand.
        day_sentiment_counts: pre-resolved {iso_date: {sentiment_key: count}}.
        post_type_breakdown: pre-resolved {post_type_key: weighted_count}.
        day_post_type_counts: pre-resolved {iso_date: {post_type_key: count}}.
        signal_labels: pre-resolved {sentiment_key: localized_label} for
            the chart series. The parameter name is preserved for
            backwards compat with the JS template attribute
            (`data-signal-labels`); the dict values are sentiment labels.
    """
    locale = normalize_locale(display_locale)
    if now is None:
        # Anchor 'now' to the last run's finished_at when available, so
        # the 24h/7d windows stay meaningful even if the DB hasn't been
        # updated today. Fall back to wall-clock when no run exists yet.
        now = datetime.now(timezone.utc)
        if latest_run and latest_run.get("finished_at"):
            try:
                now = datetime.fromisoformat(
                    latest_run["finished_at"].replace("Z", "+00:00")
                )
            except ValueError:
                pass
    cutoff = now - timedelta(days=window_days)
    cutoff_7d = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)
    in_window: list[dict[str, Any]] = []
    in_7d: list[dict[str, Any]] = []
    in_24h: list[dict[str, Any]] = []
    for p in posts:
        dt = _parse_post_timestamp(p.get("created_at"))
        if dt is None:
            continue
        if dt >= cutoff:
            in_window.append(p)
        if dt >= cutoff_7d:
            in_7d.append(p)
        if dt >= cutoff_24h:
            in_24h.append(p)

    # Per-day per-sentiment + per-day per-post_type counts. U9
    # replaces the v1.7 source_query_id inference with the SQL-backed
    # breakdown read from posts_brands_signals. When the caller passes
    # the new breakdowns, use them directly; the legacy fallback (when
    # neither breakdown is provided) returns empty counts — tests that
    # build synthetic post lists without a DB should pass the
    # breakdowns explicitly.
    sent_counts: Counter[str] = Counter()
    if sentiment_breakdown is not None:
        sent_counts = Counter(sentiment_breakdown)
    _day_sent_counts: dict[str, Counter[str]] = {
        d: Counter(c) for d, c in (day_sentiment_counts or {}).items()
    }
    pt_counts: Counter[str] = Counter()
    if post_type_breakdown is not None:
        pt_counts = Counter(post_type_breakdown)
    _day_pt_counts: dict[str, Counter[str]] = {
        d: Counter(c) for d, c in (day_post_type_counts or {}).items()
    }

    # Materialize the per-day grid into the response shape Chart.js wants:
    # `days` is a list of ISO date strings (oldest -> newest), and each series
    # is a list[int] aligned to `days` with the count for that sentiment on that
    # day (0 if no posts). Four series, ordered to match the bar segments.
    chart_series_keys: tuple[str, ...] = _DASHBOARD_SENTIMENT_KEYS
    chart_days: list[str] = []
    chart_series: dict[str, list[int]] = {k: [] for k in chart_series_keys}
    for i in range(window_days - 1, -1, -1):
        d = (now.date() - timedelta(days=i)).isoformat()
        chart_days.append(d)
        day_counter = _day_sent_counts.get(d, Counter())
        for sig in chart_series_keys:
            chart_series[sig].append(day_counter.get(sig, 0))

    # Top 3 by like_count (ties broken by recency) — exposes DB column
    # `like_count` — the user-facing name (DB column renamed v1.8).
    # v1.7: thread `locale` into _build_top3 so each top-3 row's
    # `display_text` comes from the chosen locale (text_en / text_zh_cn).
    top3 = _build_top3(in_window, locale=locale)
    top3_7d = _build_top3(in_7d, locale=locale)
    top3_24h = _build_top3(in_24h, locale=locale)

    # Degraded sentinels
    sentinels: list[str] = []
    if latest_run:
        degraded = latest_run.get("degraded") or {}
        if degraded.get("cookies"):
            sentinels.append("cookies")
        # Per-model: query_rot
        for q in latest_run.get("queries") or []:
            if q.get("brand_id") == brand_id and q.get("status") == "error":
                sentinels.append(f"q_error:{q.get('query_id')}")
        # Per-model: skipped_budget entries
        for entry in degraded.get("skipped_budget") or []:
            if isinstance(entry, str) and entry.startswith(f"{brand_id}/"):
                sentinels.append("budget")

    # v1.7-i18n (Unit 5): pre-render the sentiment labels as a JSON string
    # so the template can drop it verbatim into a data-signal-labels
    # attribute. We use ensure_ascii=False so non-ASCII (Chinese) labels
    # appear as their UTF-8 form in the HTML, not escaped \uXXXX. The
    # page is served with charset=utf-8, so the browser decodes it
    # correctly. The template attribute name `data-signal-labels` is
    # preserved for backwards compat with the trend-chart JS.
    signal_labels_json = (
        json.dumps(signal_labels, ensure_ascii=False) if signal_labels else ""
    )
    return {
        "brand_id": brand_id,
        "display_name": display_name or MODEL_DISPLAY_NAMES.get(brand_id, brand_id),
        "accent_color": MODEL_ACCENT_COLORS.get(brand_id, "#9ca3af"),
        "chart": {"days": chart_days, "series": chart_series},
        "signal_labels": signal_labels or {},
        "signal_labels_json": signal_labels_json,
        # U9: the breakdown keys are sentiments + post_types (was 6-signal).
        # Old template keys `signal_breakdown` / `signal_labels` are
        # preserved under sentiment for backwards compat; new templates
        # should consume `sentiment_breakdown` + `post_type_breakdown`.
        "sentiment_breakdown": dict(sent_counts),
        "post_type_breakdown": dict(pt_counts),
        "signal_breakdown": dict(sent_counts),
        "top3_posts": top3,
        "top3_7d": top3_7d,
        "top3_24h": top3_24h,
        "n_posts_in_window": len(in_window),
        "n_posts_7d": len(in_7d),
        "n_posts_24h": len(in_24h),
        "degraded_sentinels": sentinels,
        "last_run_at": (latest_run or {}).get("finished_at"),
        "display_locale": locale,
    }


def serialize_combined_chart(
    brands: list[str],
    posts_by_brand: dict[str, list[dict[str, Any]]],
    *,
    window_days: int = 30,
    latest_run: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the combined multi-brand chart payload.

    Aggregates posts for all enabled brands into a per-day, per-brand
    total (series) and a per-day, per-brand, per-signal breakdown (stacked).
    The shape is what static/combined-chart.js expects on the wire.

    Args:
        brands: list of brand model_ids (e.g. ["minimax", "qwen", ...]).
        posts_by_brand: {brand: [post dicts]} aligned with `brands`.
        window_days: total window for the chart (default 30).
        latest_run: parsed LATEST.json (or None) for the now anchor.
            When present, latest_run["finished_at"] wins over `now`
            (matches serialize_grid_card behavior).
        now: anchor timestamp for window cutoffs (test seam).

    Returns:
        {
            "days": [iso_date_str] * window_days,         # oldest -> newest
            "series": {brand: [int] * window_days},        # total per brand per day
            "stacked": {brand: {signal: [int] * window_days}},  # per signal
            "window_days": int,
            "fetched_at": iso_str,
        }
    """
    if now is None:
        now = datetime.now(timezone.utc)
        if latest_run and latest_run.get("finished_at"):
            try:
                now = datetime.fromisoformat(
                    latest_run["finished_at"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

    # The combined chart still renders per-signal stacks via
    # source_query_id (v2.0). Future migration to sentiment/post_type is
    # tracked separately; the grid card already moved to U9 sentiment.
    chart_series_keys: tuple[str, ...] = (
        "release", "community_question", "criticism",
        "commenter_capture", "other", "praise",
    )

    # days: ISO date strings, oldest -> newest
    days: list[str] = [
        (now.date() - timedelta(days=i)).isoformat()
        for i in range(window_days - 1, -1, -1)
    ]

    series: dict[str, list[int]] = {b: [0] * window_days for b in brands}
    stacked: dict[str, dict[str, list[int]]] = {
        b: {sig: [0] * window_days for sig in chart_series_keys}
        for b in brands
    }

    # Single pass per brand: bucket posts into per-day, per-signal counts.
    for brand in brands:
        posts = posts_by_brand.get(brand, [])
        for p in posts:
            signal = _qid_to_signal(p.get("source_query_id") or "")
            if signal is None:
                continue
            dt = _parse_post_timestamp(p.get("created_at"))
            if dt is None:
                continue
            # Skip posts outside the window
            days_ago = (now.date() - dt.date()).days
            if days_ago < 0 or days_ago >= window_days:
                continue
            # Index from the END of `days` (oldest -> newest)
            idx = window_days - 1 - days_ago
            series[brand][idx] += 1
            stacked[brand][signal][idx] += 1

    # Per-brand stroke colors from MODEL_ACCENT_COLORS so the chart
    # renders each line in its brand color (matches the 9-card grid
    # sparkline convention).
    colors = {b: MODEL_ACCENT_COLORS.get(b, "#9ca3af") for b in brands}

    return {
        "days": days,
        "series": series,
        "stacked": stacked,
        "colors": colors,
        "window_days": window_days,
        "fetched_at": now.isoformat(),
    }


def _post_matches_filter(
    post: dict[str, Any],
    filters: dict[str, Any],
) -> bool:
    """Return True when a single post satisfies the active control-panel filters.

    The filter contract is a dict with these keys (all optional; an
    absent key means "no filter on this dimension"):

        - discourse:    list[str] — e.g. ['genuine_hype', 'sarcasm'].
                        A post matches if its `discourse` list overlaps.
        - post_types:   list[str] — e.g. ['buzz_releases'].
                        A post matches if its `post_types` list overlaps.
        - role:         list[str] — e.g. ['official', 'staff'].
                        A post matches if its `role_key` is in the set.
        - cn_nationalism: list[str] | None
                        A post matches if its `cn_nationalism` key is in the
                        set; `None` is treated as "any" when the list is empty.
        - us_nationalism: same shape as cn_nationalism.
        - unsanctioned: "off" | "only" | "any".
                        "off"  → posts with `unsanctioned=True` are EXCLUDED.
                        "only" → posts with `unsanctioned=False` are EXCLUDED.
                        "any"  → no filter.

    Used by both `serialize_home_chart` (U2) and `serialize_feed_page`
    (U4) so the chart and feed share one filter-narrowing predicate.
    """
    # Discourse: any overlap with the active set wins
    discourse = filters.get("discourse") or []
    if discourse:
        post_disc = post.get("discourse") or []
        if not any(d in discourse for d in post_disc):
            return False

    # Post types: any overlap
    post_types = filters.get("post_types") or []
    if post_types:
        post_pts = post.get("post_types") or []
        if not any(p in post_types for p in post_pts):
            return False

    # account.role: post's role_key must be in the set
    role = filters.get("role") or []
    if role:
        post_role = post.get("role_key")
        if post_role not in role:
            return False

    # Nationalism axes
    for axis in ("cn_nationalism", "us_nationalism"):
        active = filters.get(axis) or []
        if active:
            post_key = post.get(axis)
            if post_key not in active:
                return False

    # unsanctioned
    mode = filters.get("unsanctioned") or "off"
    is_flagged = bool(post.get("unsanctioned"))
    if mode == "off" and is_flagged:
        return False
    if mode == "only" and not is_flagged:
        return False

    return True


def serialize_home_chart(
    enabled_models: list[str],
    posts_by_brand: dict[str, list[dict[str, Any]]],
    *,
    window_days: int = 7,
    latest_run: dict[str, Any] | None = None,
    now: datetime | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the multi-brand Pushin' Weight home chart payload (KTD1, U2).

    Mirrors `serialize_combined_chart`'s per-day bucketing loop, but
    narrows the count per (brand, day) by the active control-panel
    filters. The payload shape is:

        {
            "days": [iso_date_str] * window_days,
            "series": {brand: [int] * window_days},   # filtered counts
            "stacked": {brand: {discourse_key: [int] * window_days}},
            "colors": {brand: hex},
            "totals": {brand: int},                    # filtered totals
            "applied_filters": {...},                  # echo of input
            "window_days": int,
            "fetched_at": iso_str,
        }

    Args:
        enabled_models: list of brand model_ids in render order.
        posts_by_brand: {brand: [post dict]} aligned with `enabled_models`.
            Each post dict is expected to carry the filter-narrowing
            attributes denormalized by the route layer:
            `discourse: [str]`, `post_types: [str]`, `role_key: str`,
            `cn_nationalism: str`, `us_nationalism: str`,
            `unsanctioned: bool`. Posts missing these attributes are
            treated as having empty/default values.
        window_days: total window for the chart (default 7).
        latest_run: parsed LATEST.json (or None) for the now anchor.
        now: anchor timestamp for window cutoffs (test seam).
        filters: see `_post_matches_filter` for the shape. None means
            "all on" (the default UI state).
    """
    if now is None:
        now = datetime.now(timezone.utc)
        if latest_run and latest_run.get("finished_at"):
            try:
                now = datetime.fromisoformat(
                    latest_run["finished_at"].replace("Z", "+00:00")
                )
            except ValueError:
                pass
    if filters is None:
        filters = {}

    days: list[str] = [
        (now.date() - timedelta(days=i)).isoformat()
        for i in range(window_days - 1, -1, -1)
    ]

    series: dict[str, list[int]] = {b: [0] * window_days for b in enabled_models}
    stacked: dict[str, dict[str, list[int]]] = {
        b: {dk: [0] * window_days for dk in _DASHBOARD_DISCOURSE_KEYS}
        for b in enabled_models
    }
    totals: dict[str, int] = {b: 0 for b in enabled_models}

    for brand in enabled_models:
        for p in posts_by_brand.get(brand, []):
            if not _post_matches_filter(p, filters):
                continue
            dt = _parse_post_timestamp(p.get("created_at"))
            if dt is None:
                continue
            days_ago = (now.date() - dt.date()).days
            if days_ago < 0 or days_ago >= window_days:
                continue
            idx = window_days - 1 - days_ago
            series[brand][idx] += 1
            totals[brand] += 1
            # Per-discourse breakdown for hover overlay (combined chart's
            # D3 precedent). Posts with no discourse classification
            # land in a "__none__" bucket so the operator can see how
            # many posts were uncategorized.
            post_disc = p.get("discourse") or []
            if not post_disc:
                stacked[brand].setdefault("__none__", [0] * window_days)
                stacked[brand]["__none__"][idx] += 1
            else:
                for dk in post_disc:
                    if dk in _DASHBOARD_DISCOURSE_KEYS:
                        stacked[brand][dk][idx] += 1
                    else:
                        # Unknown discourse key — bucket it so we don't
                        # drop the count silently.
                        stacked[brand].setdefault("__none__", [0] * window_days)
                        stacked[brand]["__none__"][idx] += 1

    colors = {b: MODEL_ACCENT_COLORS.get(b, "#9ca3af") for b in enabled_models}

    return {
        "days": days,
        "series": series,
        "stacked": stacked,
        "colors": colors,
        "totals": totals,
        "applied_filters": dict(filters),
        "window_days": window_days,
        "fetched_at": now.isoformat(),
    }


# Tab keys for the single-brand Pushin' Weight area chart (R14, U3, KTD6).
# The order matches the on-screen tab strip. Each tab maps to a
# `(category_field, category_keys, color_tokens)` triple resolved by
# `_SINGLE_BRAND_TAB_SPECS` below.
_SINGLE_BRAND_TABS: tuple[str, ...] = (
    "post_type", "discourse", "account_roles",
    "us_nationalism", "cn_nationalism", "unsanctioned",
)


_SINGLE_BRAND_TAB_SPECS: dict[str, dict[str, Any]] = {
    "post_type": {
        "field": "post_types",
        # multi-valued list; each post can carry several
        "multi": True,
        "categories": _DASHBOARD_POST_TYPE_KEYS,
        "color_var_prefix": "--pt-",
    },
    "discourse": {
        "field": "discourse",
        "multi": True,
        "categories": _DASHBOARD_DISCOURSE_KEYS,
        "color_var_prefix": "--bar-",
    },
    "account_roles": {
        "field": "role_key",
        "multi": False,
        "categories": _DASHBOARD_ROLE_KEYS,
        "color_var_prefix": "--role-",
    },
    "us_nationalism": {
        "field": "us_nationalism",
        "multi": False,
        "categories": _DASHBOARD_NATIONALISM_KEYS,
        "color_var_prefix": "--nat-",
    },
    "cn_nationalism": {
        "field": "cn_nationalism",
        "multi": False,
        "categories": _DASHBOARD_NATIONALISM_KEYS,
        "color_var_prefix": "--nat-",
    },
    "unsanctioned": {
        # Synthetic 2-bucket split (flagged / unflagged). R7 unsanctioned
        # filter applies in the input filter; this tab counts both
        # buckets regardless of the active filter.
        "field": "__unsanctioned__",
        "multi": False,
        "categories": ("flagged", "unflagged"),
        "color_var_prefix": "__special__",
    },
}


def serialize_single_brand_chart(
    brand_id: str,
    posts: list[dict[str, Any]],
    *,
    window_days: int = 7,
    latest_run: dict[str, Any] | None = None,
    now: datetime | None = None,
    filters: dict[str, Any] | None = None,
    tab: str = "post_type",
) -> dict[str, Any]:
    """Return the single-brand Pushin' Weight area chart payload (R14, U3).

    Aggregates posts for one brand into per-day, per-category counts
    for each of the 6 tabs (post_type / discourse / account_roles /
    us_nationalism / cn_nationalism / unsanctioned). The output
    includes all 6 tab datasets so the JS can toggle visibility on the
    same canvas (KTD6).

    Payload shape:

        {
            "brand_id": str,
            "display_name": str,
            "accent_color": hex,
            "days": [iso_date_str] * window_days,
            "tab_datasets": {
                "post_type":     {category: [int] * window_days},
                "discourse":     {category: [int] * window_days},
                "account_roles": {category: [int] * window_days},
                "us_nationalism":{category: [int] * window_days},
                "cn_nationalism":{category: [int] * window_days},
                "unsanctioned":  {category: [int] * window_days},
            },
            "tab": str,                        # the active tab (echo)
            "color_vars": {category: "var(--token)"},
            "applied_filters": {...},
            "window_days": int,
            "fetched_at": iso_str,
        }

    Args:
        brand_id: model_id of the brand (e.g. "minimax").
        posts: list of denormalized post dicts (see
            `serialize_home_chart` for the expected fields). The route
            layer is responsible for the brand-scope narrowing and the
            joins to `posts_brands_signals`, `posts_brands_discourse`,
            `posts_unsanctioned_flags`, and `accounts` (for role_key).
        tab: which tab is active; determines which tab is echoed in the
            output (the JS can still read any tab from `tab_datasets`).
            Defaults to `post_type` (R14 default).
    """
    if now is None:
        now = datetime.now(timezone.utc)
        if latest_run and latest_run.get("finished_at"):
            try:
                now = datetime.fromisoformat(
                    latest_run["finished_at"].replace("Z", "+00:00")
                )
            except ValueError:
                pass
    if filters is None:
        filters = {}
    if tab not in _SINGLE_BRAND_TABS:
        tab = "post_type"

    days: list[str] = [
        (now.date() - timedelta(days=i)).isoformat()
        for i in range(window_days - 1, -1, -1)
    ]

    tab_datasets: dict[str, dict[str, list[int]]] = {}
    for tab_key, spec in _SINGLE_BRAND_TAB_SPECS.items():
        tab_datasets[tab_key] = {
            cat: [0] * window_days for cat in spec["categories"]
        }

    for p in posts:
        # The unsanctioned tab always counts the full post set (flagged +
        # unflagged) — the unsanctioned filter would otherwise leave the
        # tab with a single empty bucket when off (the default), making
        # the stacked area visually useless. The filter still narrows
        # the OTHER 5 tabs.
        is_flagged = bool(p.get("unsanctioned"))
        post_passes_filter = _post_matches_filter(p, filters)
        if not post_passes_filter and not is_flagged:
            # Skip: not flagged AND filtered out → not visible on any tab
            continue
        dt = _parse_post_timestamp(p.get("created_at"))
        if dt is None:
            continue
        days_ago = (now.date() - dt.date()).days
        if days_ago < 0 or days_ago >= window_days:
            continue
        idx = window_days - 1 - days_ago

        for tab_key, spec in _SINGLE_BRAND_TAB_SPECS.items():
            field = spec["field"]
            categories = spec["categories"]
            if tab_key == "unsanctioned":
                # Always count toward the unsanctioned tab regardless
                # of the active filter (see loop preamble).
                key = "flagged" if is_flagged else "unflagged"
                tab_datasets[tab_key][key][idx] += 1
            else:
                # Other tabs respect the filter strictly.
                if not post_passes_filter:
                    continue
                if spec["multi"]:
                    vals = p.get(field) or []
                    for v in vals:
                        if v in categories:
                            tab_datasets[tab_key][v][idx] += 1
                else:
                    v = p.get(field)
                    if v in categories:
                        tab_datasets[tab_key][v][idx] += 1

    # Color tokens per category. Used by the JS to render each stacked
    # area segment in its brand-specific color. The route layer is
    # responsible for actually resolving the CSS variable to a hex
    # value (the JS reads `getComputedStyle` on the canvas's parent).
    color_vars: dict[str, dict[str, str]] = {}
    for tab_key, spec in _SINGLE_BRAND_TAB_SPECS.items():
        prefix = spec["color_var_prefix"]
        if prefix == "__special__":
            color_vars[tab_key] = {
                "flagged": "var(--yellow)",
                "unflagged": "var(--muted)",
            }
        else:
            color_vars[tab_key] = {
                cat: f"var({prefix}{cat.replace('_', '-')})"
                for cat in spec["categories"]
            }

    return {
        "brand_id": brand_id,
        "display_name": MODEL_DISPLAY_NAMES.get(brand_id, brand_id),
        "accent_color": MODEL_ACCENT_COLORS.get(brand_id, "#9ca3af"),
        "days": days,
        "tab_datasets": tab_datasets,
        "tab": tab,
        "color_vars": color_vars,
        "applied_filters": dict(filters),
        "window_days": window_days,
        "fetched_at": now.isoformat(),
    }


# Pushin' Weight home feed sort columns (R10, U4). The set is a
# deliberate subset — see Open Question Q2 in the plan. Brand and
# account.handle are alpha-sortable; classification columns are
# not single-value sort candidates and ship in v1 as display-only.
_FEED_SORT_COLUMNS: dict[str, str] = {
    "created_at": "created_at",
    "like_count": "like_count",
}

_FEED_DEFAULT_SORT = "created_at"
_FEED_DEFAULT_ORDER = "desc"
_FEED_HARD_CAP = 500
_FEED_DEFAULT_LIMIT = 50


def _feed_encode_cursor(created_at: str, tweet_id: str) -> str:
    """Encode a (created_at, tweet_id) cursor as a string token.

    Format: "<iso>|tweet_id". Uses a pipe (which is not legal in ISO
    timestamps or Twitter IDs) as the separator so we don't have to
    disambiguate from the colons inside ISO 8601 timestamps.
    """
    return f"{created_at}|{tweet_id}"


def _feed_decode_cursor(cursor: str) -> tuple[str, str] | None:
    """Decode a cursor token. Returns (created_at, tweet_id) or None
    on malformed input."""
    if not cursor or "|" not in cursor:
        return None
    iso, _, tweet_id = cursor.partition("|")
    if not iso or not tweet_id:
        return None
    return iso, tweet_id


def _feed_row_to_wire(
    post: dict[str, Any],
    locale: str,
    taxonomy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert one denormalized post dict to the JSON wire shape (R10).

    Args:
        post: denormalized post dict from `_denormalize_posts`.
        locale: locale for `text_translated`.
        taxonomy: optional dict with two keys for FK→label translation:
            - "discourse_id_to_key": dict[int, str]
            - "nationalism_id_to_key": dict[int, str]
          When provided, `discourse` (list of int FKs), `cn_nationalism`
          and `us_nationalism` are translated to their string labels
          before going on the wire. None → raw int FKs (legacy
          behavior; existing unit tests rely on this).
    """
    text_translated, is_translated = _pick_text(post, locale)
    text_original = post.get("text")
    classifications: dict[str, Any] = {}
    brand_nicknames = post.get("brand_nicknames") or []
    by_brand = post.get("classifications_by_brand") or {}
    for nick in brand_nicknames:
        per_brand = dict(by_brand.get(nick, {}))
        if taxonomy is not None and per_brand:
            discourse_map = taxonomy.get("discourse_id_to_key") or {}
            nat_map = taxonomy.get("nationalism_id_to_key") or {}
            if "discourse" in per_brand:
                per_brand["discourse"] = [
                    discourse_map.get(d) if d is not None else None
                    for d in (per_brand.get("discourse") or [])
                ]
            if "cn_nationalism" in per_brand:
                per_brand["cn_nationalism"] = nat_map.get(
                    per_brand["cn_nationalism"]
                )
            if "us_nationalism" in per_brand:
                per_brand["us_nationalism"] = nat_map.get(
                    per_brand["us_nationalism"]
                )
        classifications[nick] = per_brand
    return {
        "tweet_id": post.get("tweet_id"),
        "created_at": post.get("created_at"),
        "lang_detected": post.get("lang_detected"),
        "text": text_original,
        "text_translated": text_translated,
        "is_translated": is_translated,
        "text_en": post.get("text_en"),
        "text_zh_cn": post.get("text_zh_cn"),
        "like_count": post.get("like_count") or 0,
        "brands": post.get("brands") or [],
        "brand_nicknames": brand_nicknames,
        "classifications": classifications,
        "unsanctioned": bool(post.get("unsanctioned")),
        "account": post.get("account") or {},
    }


def serialize_feed_page(
    posts: list[dict[str, Any]],
    *,
    filters: dict[str, Any] | None = None,
    sort: str = _FEED_DEFAULT_SORT,
    order: str = _FEED_DEFAULT_ORDER,
    cursor: str | None = None,
    limit: int = _FEED_DEFAULT_LIMIT,
    brand_scope: str | None = None,
    locale: str = "en",
    seen_cursor_keys: set[tuple[str, str]] | None = None,
    taxonomy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one page of the Pushin' Weight home feed (R9, R10, R11, U4).

    Args:
        posts: list of denormalized post dicts (see
            `serialize_home_chart` for the expected fields). The route
            layer is responsible for the brand-scope narrowing and the
            joins to `posts_brands_signals`, `posts_brands_discourse`,
            `posts_unsanctioned_flags`, and `accounts` (for role_key).
        filters: see `_post_matches_filter` for the shape. None means
            "all on" (the default UI state).
        sort: one of the keys in `_FEED_SORT_COLUMNS`. Unknown values
            fall back to the default.
        order: "asc" or "desc". Unknown values fall back to the default.
        cursor: opaque "<iso>:<tweet_id>" token from the previous
            page's `next_cursor`. When None, returns the first page.
        limit: page size. Clamped to `_FEED_HARD_CAP / 50 * 50` so the
            total feed never exceeds 500 rows per KTD2 / R9.
        brand_scope: when set, only posts whose brand_nicknames contain
            this value are included (server-side filter, R16).
        locale: locale to render the translated column in. Affects
            `_pick_text` only; original text is always returned.
        seen_cursor_keys: cumulative set of (created_at, tweet_id) keys
            already returned by previous pages. The hard cap is enforced
            against this set, NOT against the input `posts` list (the
            caller may have already filtered / windowed it).

    Returns:
        {
            "rows": [<feed wire shape>],
            "next_cursor": str | None,
            "applied_filters": {...},
            "sort": str,
            "order": str,
            "locale": str,
        }

    Pagination semantics:
        - When `order='desc'`, the cursor is the last row from the
          previous page and the next page returns rows with
          (created_at, tweet_id) strictly LESS than the cursor (tie-
          break on tweet_id for posts sharing the same created_at).
        - When `order='asc'`, the opposite.
        - `next_cursor` is None when no more rows fit, OR when the
          caller has already returned `_FEED_HARD_CAP` rows total.
    """
    if filters is None:
        filters = {}
    if sort not in _FEED_SORT_COLUMNS:
        sort = _FEED_DEFAULT_SORT
    if order not in ("asc", "desc"):
        order = _FEED_DEFAULT_ORDER

    cursor_pair = _feed_decode_cursor(cursor) if cursor else None
    if seen_cursor_keys is None:
        seen_cursor_keys = set()

    # Apply the requested sort in memory. The route layer is still
    # encouraged to pre-sort via SQL (more efficient at scale), but
    # this branch handles the in-process case (e.g. a small feed
    # window or a path that joins in Python).
    sort_key = _FEED_SORT_COLUMNS[sort]
    if sort_key == "created_at":
        # Parse every created_at string into an aware UTC datetime before
        # sorting. Lexicographic only works for ISO-formatted strings; the
        # Twitter legacy format ("Mon Jul 14 01:18:36 +0000 2026") sorts
        # by weekday letter ("Wed" > "Mon") — wrong.
        from x_monitor.store import _parse_post_created_at
        epoch_min = datetime.min.replace(tzinfo=timezone.utc)
        def _sort_key(p):
            dt = _parse_post_created_at(p.get("created_at")) or epoch_min
            return (dt, p.get("tweet_id") or "")
        sorted_posts = sorted(posts, key=_sort_key, reverse=(order == "desc"))
    else:  # like_count
        sorted_posts = sorted(
            posts, key=lambda p: p.get("like_count") or 0,
            reverse=(order == "desc"),
        )

    def _post_eligible(p: dict[str, Any]) -> tuple[str, str] | None:
        """Return (created_at, tweet_id) if `p` is eligible for the
        current page; None otherwise. Centralizes brand-scope, filter,
        seen-keys, and cursor narrowing."""
        if brand_scope is not None:
            nicknames = p.get("brand_nicknames") or []
            if brand_scope not in nicknames:
                return None
        if not _post_matches_filter(p, filters):
            return None
        created_at = p.get("created_at") or ""
        tweet_id = p.get("tweet_id") or ""
        if not created_at or not tweet_id:
            return None
        key = (created_at, tweet_id)
        if key in seen_cursor_keys:
            return None
        if cursor_pair is not None:
            cur_iso, cur_tweet = cursor_pair
            if order == "desc":
                if (created_at, tweet_id) >= (cur_iso, cur_tweet):
                    return None
            else:
                if (created_at, tweet_id) <= (cur_iso, cur_tweet):
                    return None
        return key

    rows: list[dict[str, Any]] = []
    had_more_after = False
    for p in sorted_posts:
        if len(rows) >= limit:
            # Page is full; keep scanning ONLY to determine if there
            # is at least one more eligible post (sets next_cursor).
            if _post_eligible(p) is not None:
                had_more_after = True
                break
            continue
        key = _post_eligible(p)
        if key is None:
            continue
        rows.append(_feed_row_to_wire(p, locale, taxonomy=taxonomy))

    # next_cursor: None if this is the last page, OR the caller has
    # already returned the hard cap, OR the cursor token was malformed.
    total_seen = len(seen_cursor_keys) + len(rows)
    next_cursor: str | None = None
    if rows and had_more_after and total_seen < _FEED_HARD_CAP:
        last = rows[-1]
        next_cursor = _feed_encode_cursor(
            last["created_at"], last["tweet_id"]
        )
    if cursor and cursor_pair is None:
        next_cursor = None

    return {
        "rows": rows,
        "next_cursor": next_cursor,
        "applied_filters": dict(filters),
        "sort": sort,
        "order": order,
        "locale": locale,
    }


def _build_top3(
    posts: list[dict[str, Any]],
    *,
    locale: str = "en",
) -> list[dict[str, Any]]:
    """Build the top-3 most-liked list for a window of posts.

    Same dict shape as the legacy `top3_posts` key: exposes DB column
    `like_count` (the DB column name, the user-facing API key), prefers
    a fetched headline over the raw tweet text for `display_text`,
    and truncates `text` to 200 chars.

    v1.7: threads `locale` into _pick_text so each row's
    `display_text` is the chosen locale's translation (text_<locale>).
    Headline preference: if the post has a fetched headline, the
    headline wins (the headline is English-source per the plan, so the
    locale toggle is opt-in for headlines). When the headline is
    missing, _pick_text chooses between text_<locale> and source text.
    """
    sorted_posts = sorted(
        posts,
        key=lambda p: (
            -(p.get("like_count") or 0),
            p.get("created_at") or "",
        ),
    )
    top3: list[dict[str, Any]] = []
    for p in sorted_posts[:3]:
        text = (p.get("text") or "").strip()
        if len(text) > 200:
            text = text[:197] + "..."
        headline = (p.get("headline") or "").strip() or None
        if headline:
            # Headline wins (English source per the plan). Mark
            # is_translated=False because the headline is not the
            # translation — the user is seeing the original English
            # headline regardless of locale.
            display_text = headline
            is_translated = False
        else:
            display_text, is_translated = _pick_text(p, locale)
        top3.append(
            {
                "tweet_id": p.get("tweet_id") or p.get("id"),
                "text": text,
                "headline": headline,
                "headline_source": p.get("headline_source"),
                "display_text": display_text,
                "is_translated": is_translated,
                "like_count": p.get("like_count") or 0,
                "author_handle": p.get("author_handle"),
                "url": _tweet_url(p.get("author_handle"), p.get("tweet_id") or p.get("id")),
            }
        )
    return top3


def _tweet_url(handle: str | None, tweet_id: str | None) -> str | None:
    if not handle or not tweet_id:
        return None
    return f"https://x.com/{handle}/status/{tweet_id}"


# --- DashboardApp ---------------------------------------------------------


class DashboardApp:
    """Wraps a Flask app and provides start/stop/status CLI hooks."""

    def __init__(
        self,
        config: Config,
        data_dir: Path,
        db_path: Path,
    ):
        self.config = config
        self.data_dir = data_dir
        self.db_path = db_path
        self.runs_dir = data_dir / "runs"
        self.template_dir = Path(__file__).parent / "templates"
        self.static_dir = Path(__file__).parent / "static"
        env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html.j2"]),
        )
        # Make our helpers available in templates
        env.globals["MODEL_DISPLAY_NAMES"] = MODEL_DISPLAY_NAMES
        env.globals["MODEL_ACCENT_COLORS"] = MODEL_ACCENT_COLORS
        env.globals["APP_DISPLAY_NAME_ZH"] = APP_DISPLAY_NAME_ZH
        env.globals["APP_DISPLAY_NAME_EN"] = APP_DISPLAY_NAME_EN
        env.filters["brand_colorize"] = brand_colorize

        app = Flask(
            __name__,
            template_folder=str(self.template_dir),
            static_folder=str(self.static_dir),
        )
        # Expose the filter and globals to Flask's own jinja_env so
        # render_template() picks them up too.
        app.jinja_env.filters["brand_colorize"] = brand_colorize
        app.jinja_env.globals["MODEL_DISPLAY_NAMES"] = MODEL_DISPLAY_NAMES
        app.jinja_env.globals["MODEL_ACCENT_COLORS"] = MODEL_ACCENT_COLORS
        app.jinja_env.globals["APP_DISPLAY_NAME_ZH"] = APP_DISPLAY_NAME_ZH
        app.jinja_env.globals["APP_DISPLAY_NAME_EN"] = APP_DISPLAY_NAME_EN
        app.config["JSON_SORT_KEYS"] = False
        # Inject request.endpoint into every template render so the nav
        # strip can pick its active tab without per-route plumbing.
        @app.context_processor
        def _inject_request():
            from flask import request
            return {"request_endpoint": request.endpoint}
        self.app = app
        self._validate_dashboard_config()
        self._register_routes()

    def _build_cards(self, db_path) -> tuple[list[dict], dict | None]:
        """Build card payloads for all enabled models. Shared by /, /api/grid.json, /api/grid.html.

        v1.7: reads the display locale from the request's `?locale=`
        query param (highest priority) or the `locale` cookie
        (fallback), defaulting to "en". The same locale is used for
        every card on the page.

        v1.7-i18n (Unit 5): also reads each brand's localized display
        name from the `brands` table (display_name_<locale> with
        fallback to source) and the per-sentiment chart labels from
        `signal_labels` (the dict values are sentiment labels post-U9).

        U9 (migration 022): the per-model breakdown is the
        sentiment × post_type decomposition read from
        posts_brands_signals via _read_classification_breakdown_for_brand.
        The 6-signal `signal_breakdown` is replaced by the
        sentiment + post_type pair.
        """
        cards: list[dict] = []
        latest_run = _load_latest_run(self.runs_dir)
        locale = self._resolve_locale()
        store = Store(db_path)
        try:
            # v1.7-i18n (Unit 5): read DB-backed brand display names and
            # sentiment labels in this locale once per request. These two
            # queries replace the Python MODEL_DISPLAY_NAMES dict + the
            # hardcoded JS SIGNAL_LABELS constant.
            brand_names = _load_brand_display_names(store, locale)
            signal_labels = _load_signal_labels(store, locale)
            # v1.8 (Unit 4 / R18): compute the breakdown once per model
            # from posts_brands_signals via the JOIN shape from Decision
            # 18. The cutoff is anchored to the latest run's finished_at
            # (matching serialize_grid_card's "now" seam) so the 14d
            # window is stable across cycles.
            anchored_now = datetime.now(timezone.utc)
            if latest_run and latest_run.get("finished_at"):
                try:
                    anchored_now = datetime.fromisoformat(
                        latest_run["finished_at"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
            window_days = self.config.dashboard.window_days
            cutoff_iso = (anchored_now - timedelta(days=window_days)).isoformat()
            for m in self.config.enabled_models:
                posts = store.get_all_posts(m)
                (
                    sent_breakdown, day_sent,
                    pt_breakdown, day_pt,
                ) = _read_classification_breakdown_for_brand(
                    store._conn, m, cutoff_iso,
                )
                cards.append(
                    serialize_grid_card(
                        m, posts, window_days=window_days,
                        latest_run=latest_run, display_locale=locale,
                        sentiment_breakdown=sent_breakdown,
                        day_sentiment_counts=day_sent,
                        post_type_breakdown=pt_breakdown,
                        day_post_type_counts=day_pt,
                        display_name=brand_names.get(m),
                        signal_labels=signal_labels,
                    )
                )
        finally:
            store.close()
        return cards, latest_run

    def _resolve_locale(self) -> str:
        """Read the display locale from the current request.

        Priority: `?locale=` query param > `locale` cookie > "en".
        Invalid locales fall back to "en" (with a warning log) via
        normalize_locale.
        """
        from flask import request
        locale = request.args.get("locale") or request.cookies.get("locale")
        return normalize_locale(locale)
    def _build_treemap_tiles(
        self, latest_run: dict | None, polarity_window_days: int | None = None,
    ) -> list[TreemapTile]:
        """Build TreemapTile list for all enabled models.

        Anchors 'now' to the latest run's finished_at (falls back to wall-clock),
        then for each enabled model:
          - area_weight = total post count for the model to-date (cumulative,
            no time filter). 11 models x 2000 posts total is fine; if this
            ever becomes a hotspot swap len(posts) for a Store.count_posts().
          - polarity_score = compute_polarity(...) in the current + prior N-day windows
            (windowed, so the color reflects rate of change, not all-time mix)

        `polarity_window_days` (v1.7.4) overrides the per-request polarity
        window (1, 7, or 30). When None, falls back to the config default
        `treemap_volume_window_days`. The 30d option is bounded by the
        DashboardConfig validator (must be <= window_days); we silently
        clamp to that limit on read, since the UI exposes only 1/7/30 but
        operators may lower window_days.

        Per-model failures (e.g. broken store read) are caught and rendered as
        no-data tiles so one bad model doesn't take the whole page down.
        """
        if polarity_window_days is None:
            polarity_window_days = self.config.dashboard.treemap_volume_window_days
        polarity_window_days = _clamp_polarity_window(
            polarity_window_days, self.config.dashboard.window_days,
        )
        n_days = polarity_window_days
        # Anchor 'now' to the last run's finished_at when available, mirroring
        # serialize_grid_card so the polarity windows are stable across cycles.
        now = datetime.now(timezone.utc)
        if latest_run and latest_run.get("finished_at"):
            try:
                now = datetime.fromisoformat(
                    latest_run["finished_at"].replace("Z", "+00:00")
                )
            except ValueError:
                pass
        current_window = (now - timedelta(days=n_days), now)
        prior_window = (now - timedelta(days=2 * n_days), now - timedelta(days=n_days))

        store = Store(self.db_path)
        tiles: list[TreemapTile] = []
        # v1.8 — derive last-run timestamp + sector lookup once per build.
        last_run_str = None
        if latest_run and latest_run.get("finished_at"):
            last_run_str = latest_run["finished_at"]
        from .treemap import MODEL_SECTORS
        # v1.7-i18n (Unit 5): resolve localized brand display names from
        # the DB once per treemap build, mirroring _build_cards.
        treemap_locale = self._resolve_locale()
        brand_names = _load_brand_display_names(store, treemap_locale)
        try:
            for m in self.config.enabled_models:
                try:
                    # U8 (migration 020): posts_brands columns are INTEGER
                    # (post_id, brand_id). Look up the brand id and pass
                    # INTEGER to the SQL. The _unattributed check is via
                    # brands.brand_id slug (preserved as TEXT UNIQUE).
                    brand_id_int_row = store._conn.execute(
                        "SELECT id FROM brands WHERE nickname = ?", (m,)
                    ).fetchone()
                    if brand_id_int_row is None:
                        # Brand slug not in brands table — skip the tile.
                        continue
                    brand_id_int = int(brand_id_int_row["id"])
                    # v1.8 (Unit 4 / R17): polarity now reads from
                    # posts_brands_signals + posts_brands via the JOIN shape
                    # from Decision 18. _unattributed is excluded at the
                    # SQL layer (Decision 15). The score is a float in
                    # [-1, +1] or None for the "went dark" sentinel.
                    polarity = compute_polarity_from_db(
                        store._conn, m, polarity_window_days, now=now,
                    )
                    # v1.8 — area_weight is still cumulative (the v1.7
                    # behavior); we read posts_brands count via a focused
                    # SQL query instead of fetching every post via
                    # get_all_posts.
                    area_row = store._conn.execute(
                        "SELECT COUNT(*) AS n FROM posts_brands WHERE brand_id = ?",
                        (brand_id_int,),
                    ).fetchone()
                    area_weight = int(area_row["n"]) if area_row else 0
                    # v1.8 — posts_in_window: count of distinct posts in
                    # [now-N, now) for the brand. JOIN through posts_brands
                    # to honor multi-brand weighting (1/N); we count
                    # distinct post_ids so a 2-brand post is counted once
                    # per brand.
                    n_row = store._conn.execute(
                        """
                        SELECT COUNT(DISTINCT pb.post_id) AS n
                        FROM posts_brands pb
                        JOIN posts p ON p.id = pb.post_id
                        JOIN brands b ON b.id = pb.brand_id
                        WHERE pb.brand_id = ?
                          AND b.nickname != '_unattributed'
                          AND p.created_at >= ?
                        """,
                        (brand_id_int, current_window[0].isoformat()),
                    ).fetchone()
                    posts_in_window = int(n_row["n"]) if n_row else 0
                except Exception as e:
                    log.warning(
                        "treemap tile build failed for %s: %s — rendering as no-data",
                        m, e,
                    )
                    area_weight = 0
                    polarity = None
                    posts_in_window = 0
                tiles.append(
                    TreemapTile(
                        brand_id=m,
                        display_name=brand_names.get(
                            m, MODEL_DISPLAY_NAMES.get(m, m)
                        ),
                        accent_color=MODEL_ACCENT_COLORS.get(m, "#9ca3af"),
                        area_weight=float(area_weight),
                        polarity_score=polarity,
                        posts_in_window=posts_in_window,
                        polarity_window_days=polarity_window_days,
                        last_run_finished_at=last_run_str,
                        sector=MODEL_SECTORS.get(m),
                    )
                )
        finally:
            store.close()
        # R13: sort by area desc, then display_name asc for stable layout
        tiles.sort(key=lambda t: (-t.area_weight, t.display_name))
        return tiles

    def _build_combined_payload(
        self, db_path, *, window_days: int
    ) -> tuple[dict[str, Any], dict | None]:
        """Build the combined chart payload. Shared by /combined, /api/combined.html, /api/combined.json.

        Fetches posts for every enabled model, calls serialize_combined_chart,
        and returns the payload + latest_run (for the window toggle's
        active state). Per-brand failures are caught and rendered as a
        zero-totals line (matches _build_treemap_tiles resilience).
        """
        latest_run = _load_latest_run(self.runs_dir)
        posts_by_brand: dict[str, list[dict[str, Any]]] = {}
        store = Store(db_path)
        try:
            for m in self.config.enabled_models:
                try:
                    posts_by_brand[m] = store.get_all_posts(m)
                except Exception as e:
                    log.warning(
                        "combined chart post fetch failed for %s: %s — using empty list",
                        m, e,
                    )
                    posts_by_brand[m] = []
        finally:
            store.close()
        payload = serialize_combined_chart(
            list(self.config.enabled_models),
            posts_by_brand,
            window_days=window_days,
            latest_run=latest_run,
        )
        return payload, latest_run

    def _validate_dashboard_config(self) -> None:
        """Startup check that every enabled_model has a display_name + accent_color.

        Raised at app boot (not request time) so a misconfigured enabled_models
        list fails fast and visibly, not silently with a fallback accent.
        """
        for m in self.config.enabled_models:
            if m not in MODEL_DISPLAY_NAMES:
                raise ValueError(
                    f"enabled_model '{m}' has no entry in MODEL_DISPLAY_NAMES. "
                    f"Add it before restarting the dashboard."
                )
            if m not in MODEL_ACCENT_COLORS:
                raise ValueError(
                    f"enabled_model '{m}' has no entry in MODEL_ACCENT_COLORS. "
                    f"Add it before restarting the dashboard."
                )

    def _register_routes(self) -> None:
        app = self.app
        data_dir = self.data_dir
        db_path = self.db_path
        window_days = self.config.dashboard.window_days
        treemap_n_days = self.config.dashboard.treemap_volume_window_days

        # === U5: Pushin' Weight home pages (multi + single brand) =======
        # The two new home pages REPLACE the four legacy topbar views.
        # Templates live under templates/home.html.j2 and
        # templates/brand_home.html.j2 (created in U6); they consume the
        # data-layer payloads from U2 (multi-brand chart) and U3
        # (single-brand chart) + U4 (feed). The legacy `/` (treemap),
        # `/grid`, `/combined`, `/treemap`, `/brand/<id>`, `/model/<id>`,
        # `/api/treemap.*`, `/api/combined.*`, `/api/grid.*`, `/api/grid.html`
        # routes are all redirected or removed per the plan's authority
        # hierarchy.

        @app.route("/")
        def home_multi():
            """Multi-brand Pushin' Weight home page (R5–R11).

            U5 supersedes the legacy treemap front page (decision 1 of
            the plan's authority hierarchy). The legacy /treemap and
            /combined routes below redirect here.
            """
            from ._home_routes import render_home_multi
            return render_home_multi(
                app=self.app,
                config=self.config,
                db_path=db_path,
                runs_dir=self.runs_dir,
                request=request,
            )

        @app.route("/grid")
        def grid():
            # U5: 9-card grid is gone — redirect to the new multi-brand home.
            return redirect("/", code=302)
            # (the old page-rendering code below is unreachable; kept
            # until U10 deletes the legacy templates.)
            cards, latest_run = self._build_cards(db_path)
            spend = summarize_http_log(
                (latest_run or {}).get("http_log") or []
            )
            return render_template(
                "grid.html.j2",
                cards=cards,
                poll_seconds=self.config.dashboard.poll_seconds,
                active_locale=self._resolve_locale(),
                spend=spend,
                has_run=latest_run is not None,
                last_run_finished_at=(
                    (latest_run or {}).get("finished_at")
                ),
            )

        @app.route("/api/treemap.html")
        def api_treemap_html():
            # SVG-only htmx partial — no <main> wrapper. The wrapping
            # <main id="treemap"> on the initial page persists, so the
            # hx-trigger attribute stays attached and polling continues.
            latest_run = _load_latest_run(self.runs_dir)
            raw_window = _resolve_polarity_window(
                request, self.config.dashboard.treemap_volume_window_days,
            )
            window = _clamp_polarity_window(
                raw_window, self.config.dashboard.window_days,
            )
            tiles = self._build_treemap_tiles(latest_run, polarity_window_days=window)
            svg = build_treemap_svg(tiles, width=1200, height=800)
            return render_template(
                "_treemap_svg.html.j2",
                treemap_svg=svg,
            )

        @app.route("/api/treemap.json")
        def api_treemap_json():
            # Structured payload for external consumers. Per R13, returns
            # the sorted tile list + fetched_at + window metadata.
            latest_run = _load_latest_run(self.runs_dir)
            raw_window = _resolve_polarity_window(
                request, self.config.dashboard.treemap_volume_window_days,
            )
            window = _clamp_polarity_window(
                raw_window, self.config.dashboard.window_days,
            )
            tiles = self._build_treemap_tiles(latest_run, polarity_window_days=window)
            return jsonify(
                {
                    "tiles": [
                        {
                            "brand_id": t.brand_id,
                            "display_name": t.display_name,
                            "accent_color": t.accent_color,
                            "area_weight": t.area_weight,
                            "polarity_score": t.polarity_score,
                            "posts_in_window": t.posts_in_window,
                            "polarity_window_days": t.polarity_window_days,
                            "last_run_finished_at": t.last_run_finished_at,
                            "sector": t.sector,
                        }
                        for t in tiles
                    ],
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "window": {
                        "treemap_volume_window_days": window,
                        "requested_window_days": raw_window,
                        "default_window_days": self.config.dashboard.treemap_volume_window_days,
                        "allowed_windows": list(ALLOWED_POLARITY_WINDOWS),
                    },
                }
            )

        @app.route("/api/polarity_window/<int:days>")
        def api_set_polarity_window(days: int):
            """Set the polarity window cookie and redirect back to where
            the user came from (or the treemap front page if no Referer).

            The toggle buttons in the topbar link here. After the redirect,
            the next page render reads the new cookie and re-renders the
            treemap with the chosen window. Because the htmx poller on
            /api/treemap.html also reads the cookie, the toggle updates
            on the very next poll (within `poll_seconds`).
            """
            if days not in ALLOWED_POLARITY_WINDOWS:
                # 400, not a redirect: bad days value (e.g. 99) means the
                # client is broken or hostile. Avoid setting a junk cookie.
                return jsonify(
                    {
                        "error": "invalid polarity window",
                        "allowed": list(ALLOWED_POLARITY_WINDOWS),
                    }
                ), 400
            resp = make_response(
                redirect(request.referrer or url_for("index"), code=303)
            )
            resp.set_cookie(
                POLARITY_WINDOW_COOKIE,
                str(days),
                max_age=60 * 60 * 24 * 365,  # 1 year
                samesite="Lax",
                httponly=True,
            )
            return resp

        # ---- Combined chart (Unit 3 of v2.0 plan) ----
        # New 3rd topbar tab. Same 3-route shape as the treemap:
        # initial render + htmx partial + structured JSON.

        @app.route("/combined")
        def combined():
            # U5: combined chart is gone — redirect to the new multi-brand home.
            return redirect("/", code=302)
            # (the old page-rendering code below is unreachable; kept
            # until U10 deletes the legacy templates.)
            raw_window = _resolve_combined_window(
                request, COMBINED_WINDOW_DEFAULT,
            )
            payload, latest_run = self._build_combined_payload(
                db_path, window_days=raw_window,
            )
            spend = summarize_http_log(
                (latest_run or {}).get("http_log") or []
            )
            return render_template(
                "combined.html.j2",
                payload=payload,
                combined_window_days=raw_window,
                allowed_combined_windows=list(ALLOWED_COMBINED_WINDOWS),
                poll_seconds=self.config.dashboard.poll_seconds,
                last_run_at=(latest_run or {}).get("finished_at"),
                brands=self.config.enabled_models,
                spend=spend,
                has_run=latest_run is not None,
                last_run_finished_at=(
                    (latest_run or {}).get("finished_at")
                ),
            )

        @app.route("/api/combined.html")
        def api_combined_html():
            # SVG+canvas htmx partial — no <main> wrapper. The wrapping
            # <main id="combined-chart"> on the initial page persists,
            # so the hx-trigger attribute stays attached and polling
            # continues.
            raw_window = _resolve_combined_window(
                request, COMBINED_WINDOW_DEFAULT,
            )
            payload, _latest_run = self._build_combined_payload(
                db_path, window_days=raw_window,
            )
            return render_template(
                "_combined_chart.html.j2",
                payload=payload,
                combined_window_days=raw_window,
                brands=self.config.enabled_models,
            )

        @app.route("/api/combined.json")
        def api_combined_json():
            # Structured payload for external consumers.
            raw_window = _resolve_combined_window(
                request, COMBINED_WINDOW_DEFAULT,
            )
            payload, _latest_run = self._build_combined_payload(
                db_path, window_days=raw_window,
            )
            return jsonify(
                {
                    **payload,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "window": {
                        "combined_window_days": raw_window,
                        "default_window_days": COMBINED_WINDOW_DEFAULT,
                        "allowed_windows": list(ALLOWED_COMBINED_WINDOWS),
                    },
                }
            )

        @app.route("/api/combined_window/<int:days>")
        def api_set_combined_window(days: int):
            """Set the combined chart window cookie and redirect back.

            The toggle buttons in the topbar link here. After the
            redirect, the next page render reads the new cookie and
            re-renders the combined chart with the chosen window.
            Because the htmx poller on /api/combined.html also reads
            the cookie, the toggle updates on the very next poll
            (within `poll_seconds`).
            """
            if days not in ALLOWED_COMBINED_WINDOWS:
                return jsonify(
                    {
                        "error": "invalid combined window",
                        "allowed": list(ALLOWED_COMBINED_WINDOWS),
                    }
                ), 400
            resp = make_response(
                redirect(request.referrer or url_for("combined"), code=303)
            )
            resp.set_cookie(
                COMBINED_WINDOW_COOKIE,
                str(days),
                max_age=60 * 60 * 24 * 365,  # 1 year
                samesite="Lax",
                httponly=True,
            )
            return resp

        @app.route("/api/grid.html")
        def api_grid_html():
            # HTML fragment of just the cards; htmx polls this every Ns.
            # Returns innerHTML payload so the wrapping <main> element
            # persists and keeps its hx-trigger attribute attached.
            cards, _latest_run = self._build_cards(db_path)
            return render_template(
                "_grid_cards.html.j2",
                cards=cards,
                active_locale=self._resolve_locale(),
            )

        @app.post("/api/set_locale")
        def api_set_locale():
            """Set the `locale` cookie. Returns 200 on success, 400 on invalid.

            The form field is `locale`; valid values are "en", "zh-CN"
            (plus the alias "zh_cn"), and "original" (added in
            feat/pushin-weight-home-pages U1, 2026-07-06). Anything else → 400.
            """
            from flask import make_response, redirect, request
            locale = (request.form.get("locale") or "").strip()
            if not locale:
                return jsonify({"error": "missing locale param"}), 400
            # "original" is a first-class locale value added in
            # feat/pushin-weight-home-pages U1 (2026-07-06) — it signals
            # "show source text, skip translations". Not a synonym for "en".
            if locale.casefold() == "original":
                resp = make_response(jsonify({"locale": "original"}), 200)
                resp.set_cookie(
                    "locale", "original",
                    max_age=60 * 60 * 24 * 365, path="/", samesite="Lax",
                )
                return resp
            # Validate against the supported set; reject unknown locales
            if not any(locale.casefold() == s.casefold() for s in SUPPORTED_LOCALES):
                return jsonify({"error": f"unsupported locale: {locale!r}"}), 400
            # Round-trip to the canonical spelling (e.g. "ZH-cn" → "zh-CN")
            canonical = next(
                s for s in SUPPORTED_LOCALES
                if s.casefold() == locale.casefold()
            )
            resp = make_response(jsonify({"locale": canonical}), 200)
            # 1 year, path=/ so all routes see it
            resp.set_cookie(
                "locale", canonical,
                max_age=60 * 60 * 24 * 365, path="/", samesite="Lax",
            )
            return resp

        @app.route("/api/v1/home.window/<int:days>", methods=["POST", "GET"])
        def api_home_window(days: int):
            """Set the `home_window` cookie (Pushin' Weight home pages, U1).

            Validates against ALLOWED_HOME_WINDOWS = (1, 7, 30, 365). On
            success, 303 back to the home page. On invalid value, 400
            with the allowed set.

            NOTE: redirect target is a server-side canonical (`/`),
            NOT `request.referrer` — the latter is attacker-controllable
            and would enable open redirects (review finding #18).
            """
            if days not in ALLOWED_HOME_WINDOWS:
                return jsonify(
                    {
                        "error": "invalid home window",
                        "allowed": list(ALLOWED_HOME_WINDOWS),
                    }
                ), 400
            resp = make_response(redirect("/", code=303))
            resp.set_cookie(
                HOME_WINDOW_COOKIE,
                str(days),
                max_age=60 * 60 * 24 * 365,  # 1 year
                path="/",  # FIX review #2: without path=/, the cookie
                # is path-scoped to /api/v1/home.window/<int:days> and
                # unreadable at the home pages, so the toggle appears
                # to do nothing.
                samesite="Lax",
                httponly=True,
            )
            return resp

        @app.route(
            "/api/v1/home.locale/<locale>", methods=["POST", "GET"]
        )
        def api_home_locale(locale: str):
            """Set the `locale` cookie (Pushin' Weight home pages, U1).

            Accepts "en", "zh-CN" (alias "zh_cn"), and "original". 303
            back to the home page (server-side canonical, NOT
            request.referrer — that would enable open redirects, see
            review finding #18). 400 on invalid.
            """
            canonical: str | None = None
            if locale.casefold() == "original":
                canonical = "original"
            else:
                for s in SUPPORTED_LOCALES:
                    if locale.casefold() == s.casefold():
                        canonical = s
                        break
            if canonical is None:
                return jsonify(
                    {
                        "error": f"unsupported locale: {locale!r}",
                        "allowed": list(SUPPORTED_LOCALES) + ["original"],
                    }
                ), 400
            resp = make_response(redirect("/", code=303))
            resp.set_cookie(
                "locale", canonical,
                max_age=60 * 60 * 24 * 365, path="/", samesite="Lax",
            )
            return resp

        @app.route("/api/grid.json")
        def api_grid():
            cards, _latest_run = self._build_cards(db_path)
            return jsonify({"cards": cards, "fetched_at": datetime.now(timezone.utc).isoformat()})

        # U5: /model/<id> and /brand/<id> are legacy per-brand drill-down
        # routes (v1.8 decision 16). They now 302 to the new vanity URL
        # (`/<company>/<brand>` or `/_/<brand>`) per the plan's KTD9 +
        # A10. 404 when the brand doesn't exist.

        @app.route("/model/<brand_id>")
        def model_detail(brand_id: str):
            from ._home_routes import legacy_vanity_target
            target = legacy_vanity_target(db_path, brand_id)
            if target is None:
                abort(404)
            return redirect(target, code=302)

        @app.route("/brand/<brand_id>")
        def brand_detail(brand_id: str):
            from ._home_routes import legacy_vanity_target
            target = legacy_vanity_target(db_path, brand_id)
            if target is None:
                abort(404)
            return redirect(target, code=302)

        # U5: /treemap (legacy alias for the old `/` page) and
        # /_unattributed both 302 to `/`.
        @app.route("/treemap")
        def legacy_treemap():
            return redirect("/", code=302)

        @app.route("/_unattributed")
        def legacy_unattributed():
            return redirect("/", code=302)

        # U5: Single-brand home page at /<company>/<brand> (R12).
        @app.route("/<company>/<brand>", methods=["GET"])
        def home_brand(company: str, brand: str):
            from ._home_routes import render_home_brand
            return render_home_brand(
                app=self.app,
                config=self.config,
                db_path=db_path,
                runs_dir=self.runs_dir,
                request=request,
                company=company,
                brand=brand,
                company_underscore=False,
            )

        # U5: Single-brand home for company-less brands at /_/<brand> (R12).
        @app.route("/_/<brand>", methods=["GET"])
        def home_brand_underscore(brand: str):
            from ._home_routes import render_home_brand
            return render_home_brand(
                app=self.app,
                config=self.config,
                db_path=db_path,
                runs_dir=self.runs_dir,
                request=request,
                company="_",
                brand=brand,
                company_underscore=True,
            )

        # === /U5 page routes ===========================================

        # --- U5: /api/v1/* API routes -----------------------------------
        # The chart + feed JSON endpoints power the new home pages and
        # the bottomless-scroll feed. Each delegates to a helper in
        # `x_monitor._home_routes` (defined alongside this file).

        @app.route("/api/v1/home.chart.json")
        def api_home_chart_json():
            from ._home_routes import build_home_chart_payload
            return jsonify(
                build_home_chart_payload(
                    db_path=db_path,
                    runs_dir=self.runs_dir,
                    request=request,
                )
            )

        @app.route("/api/v1/home.chart.html")
        def api_home_chart_html():
            from ._home_routes import render_home_chart_html
            return render_home_chart_html(
                config=self.config,
                db_path=db_path,
                runs_dir=self.runs_dir,
                request=request,
            )

        @app.route("/api/v1/home.feed.json")
        def api_home_feed_json():
            from ._home_routes import build_home_feed_payload
            return jsonify(
                build_home_feed_payload(
                    db_path=db_path,
                    runs_dir=self.runs_dir,
                    request=request,
                )
            )

        @app.route("/api/v1/home.brand.chart.json")
        def api_home_brand_chart_json():
            from ._home_routes import build_brand_chart_payload
            return jsonify(
                build_brand_chart_payload(
                    db_path=db_path,
                    runs_dir=self.runs_dir,
                    request=request,
                )
            )

        @app.route("/api/v1/home.brand.chart.html")
        def api_home_brand_chart_html():
            from ._home_routes import render_brand_chart_html
            return render_brand_chart_html(
                config=self.config,
                db_path=db_path,
                runs_dir=self.runs_dir,
                request=request,
            )

        @app.route("/api/v1/health")
        def api_health():
            return jsonify(
                {
                    "ok": True,
                    "version": "pushin-weight-v1",
                    "app": APP_DISPLAY_NAME_EN,
                    "app_zh": APP_DISPLAY_NAME_ZH,
                }
            )

        @app.route("/api/model/<brand_id>.json")
        def api_model(brand_id: str):
            if brand_id not in self.config.enabled_models:
                abort(404)
            store = Store(db_path)
            try:
                posts = store.get_all_posts(brand_id)
                accounts = store.get_accounts(brand_id)
                # v1.7-i18n (Unit 5): DB-backed display name in the
                # request's locale.
                api_brand_names = _load_brand_display_names(
                    store, self._resolve_locale()
                )
            finally:
                store.close()
            return jsonify(
                {
                    "brand_id": brand_id,
                    "display_name": api_brand_names.get(
                        brand_id, MODEL_DISPLAY_NAMES.get(brand_id, brand_id)
                    ),
                    "n_posts": len(posts),
                    "n_accounts": len(accounts),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        # U6: API-spend panel — aggregated metrics from
        # summary["http_log"]. Two routes so htmx polling can hit
        # the HTML fragment while external consumers use JSON.
        @app.route("/api/spend.html")
        def api_spend_html():
            latest = _load_latest_run(self.runs_dir)
            spend = summarize_http_log(
                (latest or {}).get("http_log") or []
            )
            return render_template(
                "_spend_panel.html.j2",
                spend=spend,
                has_run=latest is not None,
                last_run_finished_at=(
                    (latest or {}).get("finished_at")
                ),
            )

        @app.route("/api/spend.json")
        def api_spend_json():
            latest = _load_latest_run(self.runs_dir)
            spend = summarize_http_log(
                (latest or {}).get("http_log") or []
            )
            return jsonify(
                {
                    "spend": spend,
                    "has_run": latest is not None,
                    "last_run_finished_at": (
                        (latest or {}).get("finished_at")
                    ),
                    "fetched_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }
            )

    # --- process management ----------------------------------------------

    def start_background(self) -> int:
        """Spawn the Flask server in the background, write pid file, return pid."""
        import socket

        host = self.config.dashboard.host
        port = self.config.dashboard.port
        # Bind test
        with socket.socket() as s:
            try:
                s.bind((host, port))
            except OSError:
                raise RuntimeError(
                    f"port {port} in use; change config.yaml::dashboard.port"
                )
        log_path = self.data_dir / "dashboard.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logf = open(log_path, "a")
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"from x_monitor.dashboard import DashboardApp; "
                f"from x_monitor.config import load_config; "
                f"from pathlib import Path; "
                f"c=load_config(Path('config.yaml')); "
                f"app=DashboardApp(c, Path('data'), Path('data/x_monitoring.db')); "
                f"app.app.run(host=c.dashboard.host, port=c.dashboard.port, "
                f"debug=False, use_reloader=False)",
            ],
            stdout=logf,
            stderr=logf,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        pid_path = self.data_dir / "dashboard.pid"
        pid_path.write_text(str(proc.pid), encoding="utf-8")
        return proc.pid

    @staticmethod
    def stop_background(data_dir: Path) -> bool:
        """Send SIGTERM to the dashboard pid. Returns True if a process was found."""
        pid_path = data_dir / "dashboard.pid"
        if not pid_path.exists():
            return False
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return False
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        finally:
            try:
                pid_path.unlink()
            except OSError:
                pass
        return True

    @staticmethod
    def status(data_dir: Path) -> dict[str, Any]:
        pid_path = data_dir / "dashboard.pid"
        log_path = data_dir / "dashboard.log"
        out: dict[str, Any] = {"pid_file": str(pid_path)}
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text(encoding="utf-8").strip())
                out["pid"] = pid
                # Process lookup
                try:
                    os.kill(pid, 0)
                    out["running"] = True
                except ProcessLookupError:
                    out["running"] = False
            except (OSError, ValueError):
                out["running"] = False
        else:
            out["running"] = False
        if log_path.exists():
            try:
                lines = log_path.read_text(encoding="utf-8").splitlines()
                out["log_tail"] = "\n".join(lines[-50:])
            except OSError:
                pass
        return out
