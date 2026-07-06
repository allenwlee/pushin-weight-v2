# {{AGENT_ATTRIBUTION}}
"""Pushin' Weight home page route helpers (U5 of
feat/pushin-weight-home-pages, 2026-07-06).

This module holds the multi-brand and single-brand home-page renderers
plus the home/brand chart + feed JSON endpoints. It lives alongside
`dashboard.py` (rather than inside it) to keep the route registration
readable; the actual @app.route decorators are added in
`dashboard.py::_register_routes` to match the existing pattern.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import jsonify, render_template, request
from jinja2 import TemplateNotFound

from .store import Store
from .dashboard import (
    APP_DISPLAY_NAME_EN,
    APP_DISPLAY_NAME_ZH,
    ALLOWED_HOME_WINDOWS,
    HOME_WINDOW_COOKIE,
    HOME_WINDOW_DEFAULT,
    MODEL_ACCENT_COLORS,
    MODEL_DISPLAY_NAMES,
    _DASHBOARD_DISCOURSE_KEYS,
    _DASHBOARD_NATIONALISM_KEYS,
    _DASHBOARD_POST_TYPE_KEYS,
    _DASHBOARD_ROLE_KEYS,
    _load_brand_display_names,
    _load_latest_run,
    _resolve_home_window,
    resolve_vanity_url_for_brand,
    resolve_brand_via_vanity,
    serialize_feed_page,
    serialize_home_chart,
    serialize_single_brand_chart,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Filter parsing
# ---------------------------------------------------------------------------


def _parse_filters_from_request() -> dict[str, Any]:
    """Read the active control-panel filters from query args.

    The JS encodes them as `filters=<json>`; legacy per-key params
    (`discourse=...`, `post_types=...`, etc.) are also accepted so
    curl-style smoke tests can hit the endpoint without a JSON body.
    """
    raw = request.args.get("filters")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (ValueError, TypeError):
            log.warning("malformed filters JSON; ignoring")
    # Fall back to per-key params (smoke-test friendly)
    out: dict[str, Any] = {}
    for key in ("discourse", "post_types", "role", "cn_nationalism", "us_nationalism"):
        v = request.args.get(key)
        if v:
            out[key] = [s for s in v.split(",") if s]
    unsanctioned = request.args.get("unsanctioned")
    if unsanctioned in ("off", "only", "any"):
        out["unsanctioned"] = unsanctioned
    return out


def _denormalize_posts(
    store: Store,
    brand_id: str,
    window_days: int,
) -> list[dict[str, Any]]:
    """Read posts for one brand, denormalized with the filter-narrowing
    attributes (`discourse`, `post_types`, `role_key`, `cn_nationalism`,
    `us_nationalism`, `unsanctioned`).

    U5's data layer (`serialize_home_chart`, `serialize_feed_page`)
    operates on these denormalized dicts. The route layer is the
    right place to do the joins because the SQL touches 4 tables
    (`posts`, `posts_brands`, `posts_brands_signals`,
    `posts_brands_discourse`) plus an `accounts` join for `role_key`
    plus a `posts_unsanctioned_flags` lookup.

    Returns an empty list when the brand has no posts in the window.
    """
    # Reuse store.get_all_posts for the base rows; then enrich.
    base = store.get_all_posts(brand_id)
    if not base:
        return []
    # Bound the working set to the requested window (matches chart's
    # per-day bucketing). The "now" anchor is wall-clock UTC; we don't
    # thread runs_dir through this helper because the route layer's
    # serialize_* functions anchor on `latest_run` themselves. The SQL
    # filter below uses this wall-clock now as the upper bound.
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    cutoff_iso = (now - timedelta(days=window_days)).isoformat()
    base = [p for p in base if (p.get("created_at") or "") >= cutoff_iso]

    # Pull the auxiliary classifications for these posts in one shot.
    if not base:
        return []
    tweet_ids = [p.get("tweet_id") for p in base if p.get("tweet_id")]
    if not tweet_ids:
        return base
    placeholders = ",".join("?" for _ in tweet_ids)
    brand_id_int = store._brand_int_id(brand_id)
    if brand_id_int is None:
        return base

    # posts_brands_signals → per-(post, post_type) row; collect post_types.
    # Migration 028 changed the schema: post_type_key and sentiment are
    # TEXT-natural-key values (no longer integer FKs to key tables).
    pt_rows = store._conn.execute(
        f"""
        SELECT p.tweet_id, pbs.post_type_key, pbs.sentiment
        FROM posts p
        JOIN posts_brands_signals pbs ON pbs.post_id = p.id
        WHERE p.tweet_id IN ({placeholders})
          AND pbs.brand_id = ?
        """,
        (*tweet_ids, brand_id_int),
    ).fetchall()
    pt_by_tweet: dict[str, list[str]] = {}
    sent_by_tweet: dict[str, list[str]] = {}
    for r in pt_rows:
        pt_by_tweet.setdefault(r["tweet_id"], []).append(r["post_type_key"])
        sent_by_tweet.setdefault(r["tweet_id"], []).append(r["sentiment_key"])

    # posts_brands_discourse → per-(post, discourse) row.
    # Migration 026 schema: the discourse and nationalism columns are
    # TEXT-natural-key values (no longer integer FKs to key tables).
    disc_rows = store._conn.execute(
        f"""
        SELECT p.tweet_id, pbd.discourse_key,
               pbd.china_nationalism, pbd.us_nationalism
        FROM posts p
        JOIN posts_brands_discourse pbd ON pbd.post_id = p.id
        WHERE p.tweet_id IN ({placeholders})
          AND pbd.brand_id = ?
        """,
        (*tweet_ids, brand_id_int),
    ).fetchall()
    disc_by_tweet: dict[str, list[str]] = {}
    nat_by_tweet: dict[str, dict[str, str]] = {}
    for r in disc_rows:
        disc_by_tweet.setdefault(r["tweet_id"], []).append(r["discourse_key"])
        nat_by_tweet.setdefault(r["tweet_id"], {})
        nat_by_tweet[r["tweet_id"]]["cn_nationalism"] = r["cn_nationalism"]
        nat_by_tweet[r["tweet_id"]]["us_nationalism"] = r["us_nationalism"]

    # posts_unsanctioned_flags → per-post bool
    # NOTE (review #3): `posts_unsanctioned_flags` is keyed on post_id only
    # (per migration 027), not (post_id, brand_id). The flag is a property
    # of the post itself, so cross-brand false positives are NOT possible
    # at the SQL layer — the flag is global to the post. The plan's
    # review of this query as missing `AND puf.brand_id = ?` was a
    # false positive; this query is correct.
    # FIX (review #1): parameter tuple shape — was `(tweet_ids,)` which
    # passes a list as a single bound parameter; sqlite3 raised
    # ProgrammingError because the SQL has `len(tweet_ids)` placeholders.
    flag_rows = store._conn.execute(
        f"""
        SELECT p.tweet_id, 1 AS flagged
        FROM posts p
        JOIN posts_unsanctioned_flags puf ON puf.post_id = p.id
        WHERE p.tweet_id IN ({placeholders})
        """,
        tuple(tweet_ids),
    ).fetchall()
    flagged_tweets = {r["tweet_id"] for r in flag_rows}

    # role_key → the post's first author
    role_rows = store._conn.execute(
        f"""
        SELECT p.tweet_id, r.key AS role_key
        FROM posts p
        LEFT JOIN brands_accounts ba ON ba.brand_id = (
            SELECT id FROM brands WHERE nickname = ?
        ) AND ba.author_id = p.author_id
        LEFT JOIN roles r ON r.id = ba.role_id
        WHERE p.tweet_id IN ({placeholders})
        """,
        (brand_id, *tweet_ids),
    ).fetchall()
    role_by_tweet = {r["tweet_id"]: r["role_key"] for r in role_rows if r["role_key"]}

    for p in base:
        twid = p.get("tweet_id")
        p["discourse"] = disc_by_tweet.get(twid, [])
        p["post_types"] = pt_by_tweet.get(twid, [])
        p["sentiments"] = sent_by_tweet.get(twid, [])
        nat = nat_by_tweet.get(twid, {})
        p["cn_nationalism"] = nat.get("cn_nationalism")
        p["us_nationalism"] = nat.get("us_nationalism")
        p["role_key"] = role_by_tweet.get(twid, "community")
        p["unsanctioned"] = twid in flagged_tweets
        p["brand_nicknames"] = [brand_id]
        p["brands"] = [
            {
                "nickname": brand_id,
                "display_name": MODEL_DISPLAY_NAMES.get(brand_id, brand_id),
                "display_name_en": MODEL_DISPLAY_NAMES.get(brand_id, brand_id),
                "display_name_zh_cn": MODEL_DISPLAY_NAMES.get(brand_id, brand_id),
            }
        ]
        p["classifications_by_brand"] = {
            brand_id: {
                "discourse": p["discourse"],
                "post_types": p["post_types"],
                "sentiments": p["sentiments"],
                "cn_nationalism": p["cn_nationalism"],
                "us_nationalism": p["us_nationalism"],
            }
        }
        p["account"] = {
            "handle": p.get("author_handle") or "@unknown",
            "role": p["role_key"],
            "role_label": p["role_key"],
        }
    return base


# ---------------------------------------------------------------------------
# Page renderers
# ---------------------------------------------------------------------------


def render_home_multi(
    *,
    app,
    config,
    db_path: Path,
    runs_dir: Path,
    request,
):
    """Render the multi-brand Pushin' Weight home page."""
    locale = _resolve_request_locale()
    window_days = _resolve_home_window(request, HOME_WINDOW_DEFAULT)
    store = Store(db_path)
    try:
        latest_run = _load_latest_run(runs_dir)
        posts_by_brand: dict[str, list[dict[str, Any]]] = {}
        for b in config.enabled_models:
            try:
                posts_by_brand[b] = _denormalize_posts(store, b, window_days)
            except Exception as exc:
                log.warning("denormalize_posts(%s) failed: %s", b, exc)
                posts_by_brand[b] = []
        chart = serialize_home_chart(
            config.enabled_models,
            posts_by_brand,
            window_days=window_days,
            latest_run=latest_run,
            filters=_parse_filters_from_request(),
        )
        feed = serialize_feed_page(
            [p for plist in posts_by_brand.values() for p in plist],
            filters=_parse_filters_from_request(),
            limit=50,
            locale=locale,
        )
    finally:
        store.close()
    try:
        return render_template(
            "home.html.j2",
            chart=chart,
            feed=feed,
            brands=config.enabled_models,
            brand_display_names=MODEL_DISPLAY_NAMES,
            brand_accent_colors=MODEL_ACCENT_COLORS,
            discourse_keys=_DASHBOARD_DISCOURSE_KEYS,
            post_type_keys=_DASHBOARD_POST_TYPE_KEYS,
            role_keys=_DASHBOARD_ROLE_KEYS,
            nationalism_keys=_DASHBOARD_NATIONALISM_KEYS,
            allowed_home_windows=list(ALLOWED_HOME_WINDOWS),
            home_window_days=window_days,
            active_locale=locale,
            app_name_zh=APP_DISPLAY_NAME_ZH,
            app_name_en=APP_DISPLAY_NAME_EN,
            poll_seconds=config.dashboard.poll_seconds,
        )
    except TemplateNotFound:
        # U6 hasn't landed the template yet — return a 503 with a
        # clear "template not built" message so the operator knows
        # what to do.
        return (
            "<h1>走个量 · Pushin' Weight</h1>"
            "<p>The multi-brand home template is not yet built "
            "(U6 of feat/pushin-weight-home-pages). Routes are wired; "
            "template + JS modules ship in subsequent units.</p>",
            503,
        )


def render_home_brand(
    *,
    app,
    config,
    db_path: Path,
    runs_dir: Path,
    request,
    company: str,
    brand: str,
    company_underscore: bool,
):
    """Render the single-brand Pushin' Weight home page."""
    locale = _resolve_request_locale()
    window_days = _resolve_home_window(request, HOME_WINDOW_DEFAULT)
    store = Store(db_path)
    try:
        resolved = resolve_brand_via_vanity(store, company, brand)
        if resolved is None:
            from flask import abort
            abort(404)
        latest_run = _load_latest_run(runs_dir)
        posts = _denormalize_posts(store, brand, window_days)
        active_tab = request.args.get("tab") or "post_type"
        chart = serialize_single_brand_chart(
            brand,
            posts,
            window_days=window_days,
            latest_run=latest_run,
            filters=_parse_filters_from_request(),
            tab=active_tab,
        )
        feed = serialize_feed_page(
            posts,
            filters=_parse_filters_from_request(),
            limit=50,
            brand_scope=brand,
            locale=locale,
        )
    finally:
        store.close()
    try:
        return render_template(
            "brand_home.html.j2",
            chart=chart,
            feed=feed,
            brand_id=brand,
            company=company,
            company_underscore=company_underscore,
            brand_display_names=MODEL_DISPLAY_NAMES,
            brand_accent_colors=MODEL_ACCENT_COLORS,
            discourse_keys=_DASHBOARD_DISCOURSE_KEYS,
            post_type_keys=_DASHBOARD_POST_TYPE_KEYS,
            role_keys=_DASHBOARD_ROLE_KEYS,
            nationalism_keys=_DASHBOARD_NATIONALISM_KEYS,
            allowed_home_windows=list(ALLOWED_HOME_WINDOWS),
            home_window_days=window_days,
            active_locale=locale,
            app_name_zh=APP_DISPLAY_NAME_ZH,
            app_name_en=APP_DISPLAY_NAME_EN,
            poll_seconds=config.dashboard.poll_seconds,
        )
    except TemplateNotFound:
        return (
            f"<h1>走个量 · {brand}</h1>"
            "<p>The single-brand home template is not yet built "
            "(U6 of feat/pushin-weight-home-pages). Routes are wired; "
            "template + JS modules ship in subsequent units.</p>",
            503,
        )


def _resolve_request_locale() -> str:
    """Read the locale cookie (with normalize_locale fallback)."""
    from .dashboard import normalize_locale
    raw = request.cookies.get("locale")
    return normalize_locale(raw)


# ---------------------------------------------------------------------------
# Legacy vanity URL target
# ---------------------------------------------------------------------------


def legacy_vanity_target(db_path: Path, brand_id: str) -> str | None:
    """Resolve a legacy `/brand/<id>` or `/model/<id>` to the new vanity
    URL, or None when the brand doesn't exist (KTD9)."""
    store = Store(db_path)
    try:
        v = resolve_vanity_url_for_brand(store, brand_id)
    finally:
        store.close()
    if v is None:
        return None
    company, brand = v
    if company == "_":
        return f"/_/{brand}"
    return f"/{company}/{brand}"


# ---------------------------------------------------------------------------
# API payload builders
# ---------------------------------------------------------------------------


def build_home_chart_payload(
    *, db_path: Path, runs_dir: Path, request
) -> dict[str, Any]:
    from .config import Config  # local import to avoid cycle
    cfg_path = db_path.parent / "config.yaml"
    enabled_models = _read_enabled_models(cfg_path)
    window_days = _resolve_home_window(request, HOME_WINDOW_DEFAULT)
    store = Store(db_path)
    try:
        posts_by_brand: dict[str, list[dict[str, Any]]] = {}
        for b in enabled_models:
            try:
                posts_by_brand[b] = _denormalize_posts(store, b, window_days)
            except Exception as exc:
                log.warning("denormalize_posts(%s) failed: %s", b, exc)
                posts_by_brand[b] = []
        return serialize_home_chart(
            enabled_models,
            posts_by_brand,
            window_days=window_days,
            latest_run=_load_latest_run(runs_dir),
            filters=_parse_filters_from_request(),
        )
    finally:
        store.close()


def render_home_chart_html(*, config, db_path, runs_dir, request):
    payload = build_home_chart_payload(
        db_path=db_path, runs_dir=runs_dir, request=request
    )
    try:
        return render_template(
            "_home_chart.html.j2",
            payload=payload,
            brands=config.enabled_models,
            home_window_days=_resolve_home_window(request, HOME_WINDOW_DEFAULT),
        )
    except TemplateNotFound:
        return (
            "<p>home chart partial not yet built (U6)</p>",
            503,
        )


def build_home_feed_payload(
    *, db_path: Path, runs_dir: Path, request
) -> dict[str, Any]:
    from .config import Config
    cfg_path = db_path.parent / "config.yaml"
    enabled_models = _read_enabled_models(cfg_path)
    window_days = _resolve_home_window(request, HOME_WINDOW_DEFAULT)
    cursor = request.args.get("cursor")
    sort = request.args.get("sort") or "created_at"
    order = request.args.get("order") or "desc"
    try:
        limit = int(request.args.get("limit") or 50)
    except ValueError:
        limit = 50
    locale = _resolve_request_locale()
    store = Store(db_path)
    try:
        all_posts: list[dict[str, Any]] = []
        for b in enabled_models:
            try:
                all_posts.extend(_denormalize_posts(store, b, window_days))
            except Exception as exc:
                log.warning("denormalize_posts(%s) failed: %s", b, exc)
        return serialize_feed_page(
            all_posts,
            filters=_parse_filters_from_request(),
            sort=sort,
            order=order,
            cursor=cursor,
            limit=limit,
            locale=locale,
        )
    finally:
        store.close()


def build_brand_chart_payload(
    *, db_path: Path, runs_dir: Path, request, brand: str | None = None
) -> dict[str, Any]:
    if brand is None:
        brand = request.args.get("brand") or request.view_args.get("brand")
    if not brand:
        from flask import abort
        abort(400, "missing brand")
    window_days = _resolve_home_window(request, HOME_WINDOW_DEFAULT)
    tab = request.args.get("tab") or "post_type"
    store = Store(db_path)
    try:
        posts = _denormalize_posts(store, brand, window_days)
        return serialize_single_brand_chart(
            brand,
            posts,
            window_days=window_days,
            latest_run=_load_latest_run(runs_dir),
            filters=_parse_filters_from_request(),
            tab=tab,
        )
    finally:
        store.close()


def render_brand_chart_html(*, config, db_path, runs_dir, request):
    brand = request.view_args.get("brand") or request.args.get("brand")
    if not brand:
        from flask import abort
        abort(400, "missing brand")
    payload = build_brand_chart_payload(
        db_path=db_path, runs_dir=runs_dir, request=request, brand=brand
    )
    try:
        return render_template(
            "_brand_chart.html.j2",
            payload=payload,
            brand=brand,
            home_window_days=_resolve_home_window(request, HOME_WINDOW_DEFAULT),
        )
    except TemplateNotFound:
        return ("<p>brand chart partial not yet built (U6)</p>", 503)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_enabled_models(cfg_path: Path) -> list[str]:
    """Best-effort: read enabled_models from config.yaml.

    Falls back to MODEL_DISPLAY_NAMES keys (which is the v1 set)
    when the config file is missing or malformed. The route layer
    is intentionally tolerant of bad config so a smoke test can
    exercise the endpoint without a real Config instance.
    """
    if not cfg_path.exists():
        return list(MODEL_DISPLAY_NAMES.keys())
    try:
        import yaml
        data = yaml.safe_load(cfg_path.read_text()) or {}
        models = data.get("enabled_models")
        if isinstance(models, list) and models:
            return [str(m) for m in models]
    except Exception as exc:
        log.warning("config.yaml read failed: %s; using defaults", exc)
    return list(MODEL_DISPLAY_NAMES.keys())
