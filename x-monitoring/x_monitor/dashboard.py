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
    compute_polarity,
)

log = logging.getLogger(__name__)


# Display name map for the 11 v1 models. PR-reviewable; tweak per brand team
# feedback without touching the rest of the code.
MODEL_DISPLAY_NAMES: dict[str, str] = {
    "minimax": "MiniMax AI",
    "qwen": "Qwen",
    "deepseek": "DeepSeek",
    "glm": "Zhipu GLM",
    "xiaomi_mimo": "Xiaomi MiMo",
    "moonshot_kimi": "Moonshot Kimi",
    "inclusionai": "InclusionAI",
    "mistral": "Mistral",
    "stepfun": "StepFun",
    "ernie": "Baidu ERNIE",
    "hunyuan": "Tencent Hunyuan",
}

# Accent color per model — drives the card border-left + sparkline stroke.
MODEL_ACCENT_COLORS: dict[str, str] = {
    "minimax": "#3b82f6",
    "qwen": "#f97316",
    "deepseek": "#10b981",
    "glm": "#a855f7",
    "xiaomi_mimo": "#eab308",
    "moonshot_kimi": "#ec4899",
    "inclusionai": "#06b6d4",
    "mistral": "#facc15",
    "stepfun": "#22c55e",
    "ernie": "#0ea5e9",
    "hunyuan": "#ec4899",
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
_LOCALE_TO_COLUMN: dict[str, str] = {
    "en": "en",
    "zh-CN": "zh_cn",
    "zh_cn": "zh_cn",
}


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
    translated = post.get(f"text_{column}")
    if translated:
        return translated, True
    # Fall back to source text. is_translated=False signals to the
    # template to render a "translation pending" / "(English source)"
    # / "(中文原文)" badge.
    return post.get("text"), False


def brand_colorize(text: str) -> str:
    """Colorize model_id matches in `text` with the brand's accent color.

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


# Canonical query_id -> expected_signal mapping. Single source of truth
# shared by the totals branch and the per-day branch in serialize_grid_card.
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

# Combined chart window: stock-chart style, 1d-360d. Default 30d (matches
# the treemap default). The combined chart has no prior-window comparison,
# so unlike the polarity window there is NO clamp to dashboard.window_days.
# Picking 360d with only 14d of history renders early days as zeros (the
# operator sees their own data sparsity).
ALLOWED_COMBINED_WINDOWS: tuple[int, ...] = (1, 7, 14, 30, 60, 90, 180, 360)
COMBINED_WINDOW_COOKIE = "combined_window"
COMBINED_WINDOW_DEFAULT = 30


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


def _qid_to_signal(qid: str) -> str | None:
    """Map a source_query_id to its expected_signal name, or None for unknown."""
    return _QID_TO_SIGNAL.get(qid)


def serialize_grid_card(
    model_id: str,
    posts: list[dict[str, Any]],
    *,
    window_days: int = 14,
    latest_run: dict[str, Any] | None = None,
    now: datetime | None = None,
    display_locale: str = "en",
) -> dict[str, Any]:
    """Return the per-model grid card payload.

    Args:
        model_id: the model slug (e.g. "minimax").
        posts: list of post dicts (from `Store.get_all_posts`).
        window_days: total window for the chart (default 14).
        latest_run: parsed LATEST.json (or None) for sentinel rendering.
        now: anchor timestamp for window cutoffs (test seam).
        display_locale: which locale to render top-3 post text in.
            Default "en". Supported: "en", "zh-CN", "zh_cn".
            Unsupported → "en" with a warning log.
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

    # Per-day per-signal counts. day_signal_counts[iso_date][signal] = int.
    # A single pass populates both the totals (sig_counts) and the per-day
    # grid that powers the stacked area chart.
    sig_counts: Counter[str] = Counter()
    day_signal_counts: dict[str, Counter[str]] = {}
    for p in in_window:
        sqid = p.get("source_query_id") or ""
        signal = _qid_to_signal(sqid)
        if signal is None:
            continue
        sig_counts[signal] += 1
        dt = _parse_post_timestamp(p.get("created_at"))
        if dt is None:
            continue
        day_signal_counts.setdefault(dt.date().isoformat(), Counter())[signal] += 1

    # Materialize the per-day grid into the response shape Chart.js wants:
    # `days` is a list of ISO date strings (oldest -> newest), and each series
    # is a list[int] aligned to `days` with the count for that signal on that
    # day (0 if no posts). Six series, ordered to match the bar segments.
    chart_series_keys: tuple[str, ...] = (
        "release", "community_question", "criticism",
        "commenter_capture", "other", "praise",
    )
    chart_days: list[str] = []
    chart_series: dict[str, list[int]] = {k: [] for k in chart_series_keys}
    for i in range(window_days - 1, -1, -1):
        d = (now.date() - timedelta(days=i)).isoformat()
        chart_days.append(d)
        day_counter = day_signal_counts.get(d, Counter())
        for sig in chart_series_keys:
            chart_series[sig].append(day_counter.get(sig, 0))

    # Top 3 by like_count (ties broken by recency) — exposes DB column
    # `favorite_count` under the user-facing name `like_count`.
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
            if q.get("model_id") == model_id and q.get("status") == "error":
                sentinels.append(f"q_error:{q.get('query_id')}")
        # Per-model: skipped_budget entries
        for entry in degraded.get("skipped_budget") or []:
            if isinstance(entry, str) and entry.startswith(f"{model_id}/"):
                sentinels.append("budget")

    return {
        "model_id": model_id,
        "display_name": MODEL_DISPLAY_NAMES.get(model_id, model_id),
        "accent_color": MODEL_ACCENT_COLORS.get(model_id, "#9ca3af"),
        "chart": {"days": chart_days, "series": chart_series},
        "signal_breakdown": dict(sig_counts),
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


def _build_top3(
    posts: list[dict[str, Any]],
    *,
    locale: str = "en",
) -> list[dict[str, Any]]:
    """Build the top-3 most-liked list for a window of posts.

    Same dict shape as the legacy `top3_posts` key: exposes DB column
    `favorite_count` under the user-facing name `like_count`, prefers
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
            -(p.get("favorite_count") or 0),
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
                "like_count": p.get("favorite_count") or 0,
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
        """
        cards: list[dict] = []
        latest_run = _load_latest_run(self.runs_dir)
        locale = self._resolve_locale()
        store = Store(db_path)
        try:
            for m in self.config.enabled_models:
                posts = store.get_all_posts(m)
                cards.append(
                    serialize_grid_card(
                        m, posts, window_days=self.config.dashboard.window_days,
                        latest_run=latest_run, display_locale=locale,
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
        try:
            for m in self.config.enabled_models:
                try:
                    posts = store.get_all_posts(m)
                    # area_weight = total posts to-date (cumulative). Windowing
                    # is reserved for polarity, where rate-of-change is the
                    # right signal.
                    area_weight = len(posts)
                    polarity = compute_polarity(posts, current_window, prior_window)
                    # v1.8 — count posts inside the current polarity window for
                    # the native <title> tooltip. Same filter compute_polarity
                    # uses internally; we recompute here because we only need
                    # the count, not the signal breakdown.
                    posts_in_window = sum(
                        1 for post in posts
                        if (current_window[0] <= (_ts := _parse_post_timestamp(post.get("created_at")) or current_window[0]) < current_window[1])
                    )
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
                        model_id=m,
                        display_name=MODEL_DISPLAY_NAMES.get(m, m),
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

        @app.route("/")
        def index():
            # Treemap front page (Finviz-style). The htmx wrapper polls the
            # partial endpoint every Ns; this initial render is the
            # same data the first poll will return.
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
                "treemap.html.j2",
                treemap_svg=svg,
                tiles=tiles,
                treemap_window_days=window,
                selected_window_days=raw_window,
                allowed_polarity_windows=list(ALLOWED_POLARITY_WINDOWS),
                poll_seconds=self.config.dashboard.poll_seconds,
                last_run_at=(latest_run or {}).get("finished_at"),
            )

        @app.route("/grid")
        def grid():
            # 9-card grid (preserved from v1.6). Moved off / when the treemap
            # became the default front page.
            cards, _latest_run = self._build_cards(db_path)
            return render_template(
                "grid.html.j2",
                cards=cards,
                poll_seconds=self.config.dashboard.poll_seconds,
                active_locale=self._resolve_locale(),
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
                            "model_id": t.model_id,
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

            The form field is `locale`; valid values are "en" and "zh-CN"
            (plus the alias "zh_cn"). Anything else → 400.
            """
            from flask import make_response, redirect, request
            locale = (request.form.get("locale") or "").strip()
            if not locale:
                return jsonify({"error": "missing locale param"}), 400
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

        @app.route("/api/grid.json")
        def api_grid():
            cards, _latest_run = self._build_cards(db_path)
            return jsonify({"cards": cards, "fetched_at": datetime.now(timezone.utc).isoformat()})

        # ---- Combined chart (Unit 3 of v2.0 plan) ----
        # New 3rd topbar tab. Same 3-route shape as the treemap:
        # initial render + htmx partial + structured JSON.

        @app.route("/combined")
        def combined():
            # Combined chart front page (full page with topbar + htmx poll).
            raw_window = _resolve_combined_window(
                request, COMBINED_WINDOW_DEFAULT,
            )
            payload, latest_run = self._build_combined_payload(
                db_path, window_days=raw_window,
            )
            return render_template(
                "combined.html.j2",
                payload=payload,
                combined_window_days=raw_window,
                allowed_combined_windows=list(ALLOWED_COMBINED_WINDOWS),
                poll_seconds=self.config.dashboard.poll_seconds,
                last_run_at=(latest_run or {}).get("finished_at"),
                brands=self.config.enabled_models,
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

        @app.route("/model/<model_id>")
        def model_detail(model_id: str):
            if model_id not in self.config.enabled_models:
                abort(404)
            from .account_graph import build_force_directed

            store = Store(db_path)
            try:
                posts = store.get_all_posts(model_id)
                accounts = store.get_accounts(model_id)
            finally:
                store.close()
            # Re-derive edges from posts for the drill-down graph
            from .accounts import derive_edges, find_clusters

            posts_for_edges = [
                {
                    "id": p.get("tweet_id"),
                    "author_handle": p.get("author_handle"),
                    "in_reply_to_user_id": p.get("in_reply_to_user_id"),
                    "quoted_status_id": p.get("quoted_status_id"),
                    "entities": json.loads(p.get("entities") or "{}"),
                    "conversation_id": p.get("conversation_id"),
                }
                for p in posts
            ]
            edges = derive_edges(posts_for_edges, model_id)
            clusters = find_clusters(
                posts_for_edges,
                edges,
                min_commenters=self.config.clustering.min_commenters,
                min_posts=self.config.clustering.min_posts,
            )
            # Build graph nodes from accounts; if empty (first run), fall back
            # to unique authors in posts.
            nodes = list(accounts)
            if not nodes:
                from .accounts import Account as _Acc

                seen: set[str] = set()
                for p in posts:
                    h = p.get("author_handle")
                    if h and h not in seen:
                        seen.add(h)
                        nodes.append(_Acc(handle=h))
            graph_svg = build_force_directed(nodes, edges, width=800, height=600)
            role_counts: Counter[str] = Counter(a.get("role", "unknown") for a in accounts)
            return render_template(
                "model_detail.html.j2",
                model_id=model_id,
                display_name=MODEL_DISPLAY_NAMES.get(model_id, model_id),
                accent_color=MODEL_ACCENT_COLORS.get(model_id, "#9ca3af"),
                posts=posts[:200],
                clusters=clusters,
                graph_svg=graph_svg,
                role_counts=dict(role_counts),
                latest_run=_load_latest_run(self.runs_dir),
            )

        @app.route("/api/model/<model_id>.json")
        def api_model(model_id: str):
            if model_id not in self.config.enabled_models:
                abort(404)
            store = Store(db_path)
            try:
                posts = store.get_all_posts(model_id)
                accounts = store.get_accounts(model_id)
            finally:
                store.close()
            return jsonify(
                {
                    "model_id": model_id,
                    "display_name": MODEL_DISPLAY_NAMES.get(model_id, model_id),
                    "n_posts": len(posts),
                    "n_accounts": len(accounts),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
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
