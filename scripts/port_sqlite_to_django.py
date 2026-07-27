#!/usr/bin/env python3
"""Port live x-monitor SQLite data into the Django ORM (PostgreSQL target).

Plan: docs/plans/2026-07-22-150000-feat-x-probe-new-open-model-discovery-harvest-onboard-plan.md
Unit 5 of N (U5 — data port tooling).

This script reads every row from a live x-monitoring SQLite DB and writes it
into the Django ORM. It handles the INTEGER-surrogate-to-natural-key mapping
that the v2 Django schema requires: brands/companies/posts use natural TEXT
keys (nickname, tweet_id) as PK, but the SQLite source uses INTEGER ids.

CLI:
    python scripts/port_sqlite_to_django.py \\
        --source /path/to/x_monitoring.db \\
        [--dry-run] [--limit N] [--since YYYY-MM-DD] [--brands a,b,c]

The script is idempotent (uses get_or_create and update_or_create) and
dry-run-safe (no writes without --write / without --dry-run).

JSON report is emitted to stdout. Use --report-file to write to a file.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, date, datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Django setup (must happen before ORM imports)
# ---------------------------------------------------------------------------
SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

import django

django.setup()

from core.models import (  # noqa: E402
    Account,
    AccountPostAppearance,
    AppliedConfigSnapshot,
    Brand,
    BrandAccount,
    BrandCompany,
    BrandHashtag,
    BrandKeyword,
    BrandSearchTerm,
    CallState,
    Company,
    CompanyAccount,
    DiscourseKey,
    DiscourseLabel,
    HFOrg,
    NationalismKey,
    NationalismLabel,
    Post,
    PostBrand,
    PostBrandDiscourse,
    PostBrandMention,
    PostBrandSignal,
    PostTypeKey,
    PostTypeLabel,
    PostUnsanctionedFlag,
    Product,
    Role,
    RoleLabel,
    SearchQuery,
    SentimentKey,
    SentimentLabel,
    UnsanctionedFlagKey,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Cache for handle->author_id resolution
_handle_to_author_id: dict[str, str] | None = None


def _resolve_by_handle(handle: str, src: sqlite3.Connection) -> str | None:
    """Look up an account's author_id by handle (case-insensitive)."""
    global _handle_to_author_id
    if _handle_to_author_id is None:
        _handle_to_author_id = {}
        rows = src.execute(
            "SELECT handle, author_id FROM accounts WHERE handle IS NOT NULL"
        ).fetchall()
        for h, aid in rows:
            if h and aid:
                _handle_to_author_id[h.lower()] = aid
    if not handle:
        return None
    key = handle.lower()
    if key in _handle_to_author_id:
        return _handle_to_author_id[key]
    # Create a synthetic account on-the-fly for previously unseen handles
    synthetic_id = f"handle:{handle}" if not handle.startswith("handle:") else handle
    _handle_to_author_id[key] = synthetic_id
    return synthetic_id


def _table_exists(src: sqlite3.Connection, table: str) -> bool:
    row = src.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(src: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()}


def _safe_select(
    src: sqlite3.Connection, table: str, desired_cols: list[str],
    where: str | None = None, params: list | None = None,
    order_by: str | None = None, limit: int | None = None,
) -> list[dict[str, Any]]:
    existing = _table_columns(src, table)
    cols = [c for c in desired_cols if c in existing]
    skipped = [c for c in desired_cols if c not in existing]
    if skipped:
        print(f"  [info] {table}: skipping columns not in source: {skipped}", file=sys.stderr)
    query = f"SELECT {', '.join(cols)} FROM {table}"
    if where: query += f" WHERE {where}"
    if order_by: query += f" ORDER BY {order_by}"
    if limit: query += f" LIMIT {limit}"
    rows = src.execute(query, params or []).fetchall()
    return [dict(zip(cols, row)) for row in rows]


def _ensure_account(author_id: str, handle: str, dry_run: bool) -> None:
    """Create an Account row if it doesn't exist (for synthetic/handle-based IDs)."""
    if dry_run or not author_id:
        return
    try:
        from core.models import Account as Acc
        Acc.objects.get_or_create(
            author_id=author_id,
            defaults={"handle": handle or author_id},
        )
    except Exception:
        pass


def _safe_get_or_create(model: Any, defaults: dict, **kwargs: Any) -> Any:
    try:
        return model.objects.get_or_create(defaults=defaults, **kwargs)
    except Exception:
        return None, False


def _safe_update_or_create(model: Any, defaults: dict, **kwargs: Any) -> Any:
    try:
        return model.objects.update_or_create(defaults=defaults, **kwargs)
    except Exception:
        return None, False



def _parse_sqlite_dt(val: str | None) -> datetime | None:
    """Parse a SQLite TEXT datetime into a timezone-aware datetime."""
    if val is None:
        return None
    val = val.strip()
    if not val:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%a %b %d %H:%M:%S %z %Y",
    ):
        try:
            dt = datetime.strptime(val, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    # Last resort: ISO format parse
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        print(f"  [warn] could not parse datetime: {val!r}", file=sys.stderr)
        return None


def _parse_sqlite_bool(val: int | None) -> bool | None:
    """Parse a SQLite INTEGER (0/1) into a Python bool or None."""
    if val is None:
        return None
    return bool(val)


def _parse_sqlite_json(val: str | None) -> Any:
    """Parse a SQLite TEXT blob as JSON, returning None for empty/None."""
    if val is None or not val.strip():
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


# ---------------------------------------------------------------------------
# Port functions — one per table group
# ---------------------------------------------------------------------------


def port_lookup_tables(
    src: sqlite3.Connection, report: dict[str, Any], dry_run: bool
) -> None:
    """Port all enum-family lookup tables (keys + labels)."""

    # -- keys: post_type_keys, sentiment_keys, discourse_keys, nationalism_keys,
    #           roles, unsanctioned_flag_keys
    KEY_TABLES: list[tuple[str, type[Any], str]] = [
        ("post_type_keys", PostTypeKey, "key"),
        ("sentiment_keys", SentimentKey, "key"),
        ("discourse_keys", DiscourseKey, "key"),
        ("nationalism_keys", NationalismKey, "key"),
        ("roles", Role, "key"),
        ("unsanctioned_flag_keys", UnsanctionedFlagKey, "key"),
    ]

    for table, Model, key_col in KEY_TABLES:
        if not _table_exists(src, table):
            print(f"  {table}: SKIPPED (not in source)", file=sys.stderr)
            continue
        rows = src.execute(f"SELECT {key_col} FROM {table}").fetchall()
        for (key_val,) in rows:
            if key_val is None:
                continue
            if not dry_run:
                Model.objects.get_or_create(**{key_col: key_val})
            _inc(report, table, "inserted")
        print(f"  {table}: {len(rows)} rows", file=sys.stderr)

    # Build surrogate ID maps for FK resolution
    role_id_map: dict[int, str] = {}
    if _table_exists(src, "roles"):
        for r in src.execute("SELECT id, key FROM roles").fetchall():
            if r[0] is not None and r[1]:
                role_id_map[r[0]] = r[1]

    key_id_maps: dict[str, dict[int, str]] = {"discourse_keys": {}, "nationalism_keys": {}}
    for tbl, m in key_id_maps.items():
        if _table_exists(src, tbl):
            for r in src.execute(f"SELECT id, key FROM {tbl}").fetchall():
                if r[0] is not None and r[1]:
                    m[r[0]] = r[1]

    # -- labels: post_type_labels, sentiment_labels, discourse_labels,
    #            nationalism_labels, role_labels
    # The FK column in SQLite uses the TEXT key value directly (db_column='key'
    # pattern in Django), so no JOIN needed to resolve surrogate IDs.
    LABEL_TABLES: list[tuple[str, type[Any], str, str]] = [
        ("post_type_labels", PostTypeLabel, "key", "post_type"),
        ("sentiment_labels", SentimentLabel, "key", "sentiment"),
        ("discourse_labels", DiscourseLabel, "key", "discourse"),
        ("nationalism_labels", NationalismLabel, "key", "nationalism"),
        ("role_labels", RoleLabel, "key", "role"),
    ]

    for table, Model, fk_col, django_fk in LABEL_TABLES:
        rows = src.execute(
            f"SELECT {fk_col}, lang, label FROM {table}"
        ).fetchall()
        for fk_val, lang, label in rows:
            if fk_val is None:
                continue
            if not dry_run:
                _safe_get_or_create(
                    Model, {"label": label},
                    **{django_fk + "_id": fk_val, "lang": lang},
                )
            _inc(report, table, "inserted")
        print(f"  {table}: {len(rows)} rows", file=sys.stderr)

    return role_id_map, key_id_maps


def port_brands(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    brand_filter: set[str] | None = None,
) -> dict[int, str]:
    """Port brands. Returns {sqlite_id: nickname} map for junction resolution.

    The _unattributed sentinel is always ported first.
    """
    id_map: dict[int, str] = {}

    # Always do sentinel first
    sentinel = src.execute(
        "SELECT id, nickname, display_name, accent_color, is_sentinel, "
        "created_at, display_name_en, display_name_zh_cn "
        "FROM brands WHERE nickname = '_unattributed'"
    ).fetchone()

    all_rows = src.execute(
        "SELECT id, nickname, display_name, accent_color, is_sentinel, "
        "created_at, display_name_en, display_name_zh_cn "
        "FROM brands ORDER BY is_sentinel DESC, nickname ASC"
    ).fetchall()

    # Reorder: sentinel first, then the rest
    rows: list[tuple] = []
    seen: set[str] = set()
    if sentinel:
        rows.append(sentinel)
        seen.add(sentinel[1])
    for row in all_rows:
        if row[1] not in seen:
            rows.append(row)

    for row in rows:
        sqlite_id, nickname, display_name, accent_color, is_sentinel, \
            created_at, display_name_en, display_name_zh_cn = row

        if brand_filter and nickname not in brand_filter:
            _inc(report, "brands", "skipped")
            id_map[sqlite_id] = nickname
            continue

        defaults = {
            "display_name": display_name,
            "accent_color": accent_color,
            "is_sentinel": _parse_sqlite_bool(is_sentinel) or False,
            "display_name_en": display_name_en,
            "display_name_zh_cn": display_name_zh_cn,
        }

        if not dry_run:
            Brand.objects.update_or_create(
                nickname=nickname, defaults=defaults
            )
        _inc(report, "brands", "inserted")
        id_map[sqlite_id] = nickname

    print(f"  brands: {len(rows)} rows", file=sys.stderr)
    return id_map


def port_companies(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
) -> dict[int, str]:
    """Port companies. Returns {sqlite_id: nickname} map."""
    id_map: dict[int, str] = {}

    desired_cols = [
        "id", "nickname", "display_name", "hq_country", "accent_color",
        "description", "created_at", "display_name_en", "display_name_zh_cn",
    ]
    rows = _safe_select(src, "companies", desired_cols, order_by="nickname ASC")

    for row in rows:
        sqlite_id = row["id"]
        nickname = row["nickname"]

        defaults = {
            "display_name": row.get("display_name"),
            "hq_country": row.get("hq_country"),
            "accent_color": row.get("accent_color"),
            "description": row.get("description"),
            "display_name_en": row.get("display_name_en"),
            "display_name_zh_cn": row.get("display_name_zh_cn"),
        }

        if not dry_run:
            Company.objects.update_or_create(
                nickname=nickname, defaults=defaults
            )
        _inc(report, "companies", "inserted")
        id_map[sqlite_id] = nickname

    print(f"  companies: {len(rows)} rows", file=sys.stderr)
    return id_map


def port_accounts(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    limit: int | None = None,
) -> set[str]:
    """Port accounts. Returns (author_ids, {sqlite_int_id: author_id} map)."""
    author_ids: set[str] = set()
    sqlite_id_map: dict[int, str] = {}

    cols = [
        "id", "author_id", "handle", "display_name", "bio", "bio_fetched_at",
        "verified", "bio_contains_brand", "first_seen_at", "last_seen_at",
        "source_query_ids", "notes", "bio_en", "bio_zh_cn",
        # Migration 039 columns
        "followers_count", "following_count", "favourites_count",
        "statuses_count", "media_count", "fast_followers_count",
        "is_blue_verified", "verified_type", "profile_picture",
        "location", "description", "profile_bio_text", "followers_fetched_at",
    ]

    query = f"SELECT {', '.join(cols)} FROM accounts ORDER BY author_id"
    if limit:
        query += f" LIMIT {limit}"

    rows = src.execute(query).fetchall()

    for row in rows:
        vals = dict(zip(cols, row))
        sqlite_id = vals["id"]
        author_id = vals["author_id"]
        author_ids.add(author_id)
        sqlite_id_map[sqlite_id] = author_id

        defaults: dict[str, Any] = {}
        for col in cols:
            if col in ("id", "author_id"):
                continue
            val = vals[col]
            if val is None:
                if col == "verified":
                    defaults[col] = False
                else:
                    defaults[col] = None
            elif col in ("verified", "bio_contains_brand", "is_blue_verified"):
                defaults[col] = _parse_sqlite_bool(val)
            elif col.endswith("_at"):
                defaults[col] = _parse_sqlite_dt(val)
            elif col.endswith("_count"):
                defaults[col] = int(val)
            else:
                defaults[col] = val

        if not dry_run:
            Account.objects.update_or_create(
                author_id=author_id, defaults=defaults
            )
        _inc(report, "accounts", "inserted")

    print(f"  accounts: {len(rows)} rows", file=sys.stderr)
    return author_ids, sqlite_id_map


def port_posts(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    account_id_map: dict[int, str] | None = None,
    limit: int | None = None,
    since: str | None = None,
) -> dict[int, str]:
    """Port posts. Returns {sqlite_id: tweet_id} map."""
    if account_id_map is None:
        account_id_map = {}
    id_map: dict[int, str] = {}

    cols = [
        "id", "tweet_id", "author_handle", "author_id", "text", "lang",
        "created_at", "fetched_at", "like_count", "retweet_count",
        "reply_count", "quote_count", "in_reply_to_user_id",
        "quoted_status_id", "conversation_id", "entities",
        "source_query_id", "headline", "headline_source",
        "text_en", "text_zh_cn", "lang_detected", "quoted_text",
        "last_quote_count_seen", "last_quote_fetched_at",
        "created_at_epoch",
    ]

    where_clauses: list[str] = []
    params: list[Any] = []
    if since:
        where_clauses.append("created_at >= ? OR tweet_id IN (SELECT tweet_id FROM posts WHERE created_at >= ?)")
        # Simple: filter by created_at on posts where created_at is populated
        where_clauses = ["(created_at >= ? OR created_at IS NULL)"]
        params = [f"{since}T00:00:00"]

    query = f"SELECT {', '.join(cols)} FROM posts"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY created_at ASC"
    if limit:
        query += f" LIMIT {limit}"

    rows = src.execute(query, params).fetchall()

    for row in rows:
        vals = dict(zip(cols, row))
        sqlite_id = vals["id"]
        tweet_id = vals["tweet_id"]

        if not tweet_id:
            _inc(report, "posts", "skipped")
            continue

        raw_author_id = vals.get("author_id")
        author_handle = vals.get("author_handle")
        if raw_author_id is not None:
            resolved_author_id = account_id_map.get(raw_author_id)
        elif author_handle:
            resolved_author_id = _resolve_by_handle(author_handle, src)
        else:
            resolved_author_id = None

        if not resolved_author_id:
            _inc(report, "posts", "skipped")
            continue

        defaults: dict[str, Any] = {}
        for col in cols:
            if col in ("id", "tweet_id", "author_id"):
                continue
            val = vals[col]
            if val is None:
                defaults[col] = None
            elif col in ("like_count", "retweet_count", "reply_count",
                         "quote_count", "last_quote_count_seen"):
                defaults[col] = int(val) if val is not None else None
            elif col == "created_at_epoch":
                defaults[col] = int(val) if val is not None else None
            elif col == "entities":
                defaults[col] = _parse_sqlite_json(val)
            elif col.endswith("_at"):
                defaults[col] = _parse_sqlite_dt(val)
            else:
                defaults[col] = val

        # Ensure account exists (create synthetic if needed)
        _ensure_account(resolved_author_id, author_handle or "", dry_run)

        defaults["author_id"] = resolved_author_id

        if not dry_run:
            _safe_update_or_create(
                Post, defaults, tweet_id=tweet_id,
            )
        _inc(report, "posts", "inserted")
        id_map[sqlite_id] = tweet_id

    print(f"  posts: {len(rows)} rows", file=sys.stderr)
    return id_map


def port_brands_companies(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    brand_id_map: dict[int, str],
    company_id_map: dict[int, str],
    limit: int | None = None,
) -> None:
    """Port brands_companies junction table."""
    query = (
        "SELECT bc.brand_id, bc.company_id, bc.ownership_pct "
        "FROM brands_companies bc "
        "ORDER BY bc.brand_id, bc.company_id"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for brand_id, company_id, ownership_pct in rows:
        brand_nickname = brand_id_map.get(brand_id)
        company_nickname = company_id_map.get(company_id)
        if not brand_nickname or not company_nickname:
            _inc(report, "brands_companies", "skipped")
            continue
        if not dry_run:
            BrandCompany.objects.get_or_create(
                brand_id=brand_nickname,
                company_id=company_nickname,
                defaults={"ownership_pct": ownership_pct or 1.0},
            )
        _inc(report, "brands_companies", "inserted")

    print(f"  brands_companies: {len(rows)} rows", file=sys.stderr)


def port_brands_accounts(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    brand_id_map: dict[int, str],
    account_id_map: dict[int, str] | None = None,
    role_id_map: dict[int, str] | None = None,
    limit: int | None = None,
) -> None:
    """Port brands_accounts junction table."""
    if account_id_map is None:
        account_id_map = {}
    if role_id_map is None:
        role_id_map = {}
    query = (
        "SELECT ba.brand_id, ba.accounts_id, ba.role_id, ba.added_at "
        "FROM brands_accounts ba "
        "ORDER BY ba.brand_id, ba.accounts_id"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for brand_id, accounts_id, role_id, added_at in rows:
        brand_nickname = brand_id_map.get(brand_id)
        resolved_account = account_id_map.get(accounts_id) if accounts_id else None
        resolved_role = role_id_map.get(role_id) if role_id else None
        if not brand_nickname or not resolved_account or not resolved_role:
            _inc(report, "brands_accounts", "skipped")
            continue
        if not dry_run:
            BrandAccount.objects.get_or_create(
                brand_id=brand_nickname,
                account_id=resolved_account,
                role_id=resolved_role,
                defaults={"added_at": _parse_sqlite_dt(added_at)},
            )
        _inc(report, "brands_accounts", "inserted")

    print(f"  brands_accounts: {len(rows)} rows", file=sys.stderr)


def port_companies_accounts(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    company_id_map: dict[int, str],
    account_id_map: dict[int, str] | None = None,
    role_id_map: dict[int, str] | None = None,
    limit: int | None = None,
) -> None:
    """Port companies_accounts junction table."""
    if account_id_map is None:
        account_id_map = {}
    if role_id_map is None:
        role_id_map = {}
    query = (
        "SELECT ca.company_id, ca.author_id, ca.role_id, ca.added_at "
        "FROM companies_accounts ca "
        "ORDER BY ca.company_id, ca.author_id"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for company_id, author_id, role_id, added_at in rows:
        company_nickname = company_id_map.get(company_id)
        resolved_account = account_id_map.get(author_id) if author_id else None
        resolved_role = role_id_map.get(role_id) if role_id else None
        if not company_nickname or not resolved_account or not resolved_role:
            _inc(report, "companies_accounts", "skipped")
            continue
        if not dry_run:
            CompanyAccount.objects.get_or_create(
                company_id=company_nickname,
                account_id=resolved_account,
                role_id=resolved_role,
                defaults={"added_at": _parse_sqlite_dt(added_at)},
            )
        _inc(report, "companies_accounts", "inserted")

    print(f"  companies_accounts: {len(rows)} rows", file=sys.stderr)


def port_hf_orgs(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    company_id_map: dict[int, str],
    limit: int | None = None,
) -> None:
    """Port hf_orgs table."""
    query = (
        "SELECT h.namespace, h.company_id, h.confirmed, h.discovered_via, h.added_at "
        "FROM hf_orgs h "
        "ORDER BY h.namespace"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for namespace, company_id, confirmed, discovered_via, added_at in rows:
        company_nickname = company_id_map.get(company_id) if company_id else None
        if not namespace:
            _inc(report, "hf_orgs", "skipped")
            continue
        if not dry_run:
            HFOrg.objects.get_or_create(
                namespace=namespace,
                defaults={
                    "company_id": company_nickname,
                    "confirmed": _parse_sqlite_bool(confirmed) or False,
                    "discovered_via": discovered_via or "curated",
                    "added_at": _parse_sqlite_dt(added_at),
                },
            )
        _inc(report, "hf_orgs", "inserted")

    print(f"  hf_orgs: {len(rows)} rows", file=sys.stderr)


def port_attribution_map(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    brand_id_map: dict[int, str],
    limit: int | None = None,
) -> None:
    """Port brand_search_terms, brand_keywords, brand_hashtags."""
    # brand_search_terms
    query = (
        "SELECT st.brand_id, st.term, st.added_at "
        "FROM brand_search_terms st "
        "ORDER BY st.brand_id, st.term"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()
    for brand_id, term, added_at in rows:
        brand_nickname = brand_id_map.get(brand_id)
        if not brand_nickname or not term:
            _inc(report, "brand_search_terms", "skipped")
            continue
        if not dry_run:
            BrandSearchTerm.objects.get_or_create(
                brand_id=brand_nickname,
                term=term,
                defaults={"added_at": _parse_sqlite_dt(added_at)},
            )
        _inc(report, "brand_search_terms", "inserted")
    print(f"  brand_search_terms: {len(rows)} rows", file=sys.stderr)

    # brand_keywords
    query = (
        "SELECT bk.brand_id, bk.pattern, bk.is_regex, bk.added_at, bk.is_primary "
        "FROM brand_keywords bk "
        "ORDER BY bk.brand_id, bk.pattern"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()
    for brand_id, pattern, is_regex, added_at, is_primary in rows:
        brand_nickname = brand_id_map.get(brand_id)
        if not brand_nickname or not pattern:
            _inc(report, "brand_keywords", "skipped")
            continue
        if not dry_run:
            BrandKeyword.objects.get_or_create(
                brand_id=brand_nickname,
                pattern=pattern,
                defaults={
                    "is_regex": _parse_sqlite_bool(is_regex) or False,
                    "added_at": _parse_sqlite_dt(added_at),
                    "is_primary": _parse_sqlite_bool(is_primary) or False,
                },
            )
        _inc(report, "brand_keywords", "inserted")
    print(f"  brand_keywords: {len(rows)} rows", file=sys.stderr)

    # brand_hashtags
    query = (
        "SELECT bh.brand_id, bh.tag, bh.added_at "
        "FROM brand_hashtags bh "
        "ORDER BY bh.brand_id, bh.tag"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()
    for brand_id, tag, added_at in rows:
        brand_nickname = brand_id_map.get(brand_id)
        if not brand_nickname or not tag:
            _inc(report, "brand_hashtags", "skipped")
            continue
        if not dry_run:
            BrandHashtag.objects.get_or_create(
                brand_id=brand_nickname,
                hashtag=tag,
                defaults={"added_at": _parse_sqlite_dt(added_at)},
            )
        _inc(report, "brand_hashtags", "inserted")
    print(f"  brand_hashtags: {len(rows)} rows", file=sys.stderr)


def port_posts_brands(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    post_id_map: dict[int, str],
    brand_id_map: dict[int, str],
    limit: int | None = None,
) -> None:
    """Port posts_brands junction table."""
    query = (
        "SELECT pb.post_id, pb.brand_id, pb.weight "
        "FROM posts_brands pb "
        "ORDER BY pb.post_id, pb.brand_id"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for post_id, brand_id, weight in rows:
        tweet_id = post_id_map.get(post_id)
        brand_nickname = brand_id_map.get(brand_id)
        if not tweet_id or not brand_nickname:
            _inc(report, "posts_brands", "skipped")
            continue
        if not dry_run:
            PostBrand.objects.get_or_create(
                post_id=tweet_id,
                brand_id=brand_nickname,
                defaults={"weight": weight or 1.0},
            )
        _inc(report, "posts_brands", "inserted")

    print(f"  posts_brands: {len(rows)} rows", file=sys.stderr)


def port_posts_brands_mentions(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    post_id_map: dict[int, str],
    brand_id_map: dict[int, str],
    limit: int | None = None,
) -> None:
    """Port posts_brands_mentions junction table."""
    query = (
        "SELECT pbm.post_id, pbm.brand_id, pbm.source, pbm.raw_token, pbm.mentioned_at "
        "FROM posts_brands_mentions pbm "
        "ORDER BY pbm.post_id, pbm.brand_id, pbm.source"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for post_id, brand_id, source, raw_token, mentioned_at in rows:
        tweet_id = post_id_map.get(post_id)
        brand_nickname = brand_id_map.get(brand_id)
        if not tweet_id or not brand_nickname or not source:
            _inc(report, "posts_brands_mentions", "skipped")
            continue
        if not dry_run:
            PostBrandMention.objects.get_or_create(
                post_id=tweet_id,
                brand_id=brand_nickname,
                source=source,
                defaults={
                    "raw_token": raw_token,
                    "mentioned_at": _parse_sqlite_dt(mentioned_at),
                },
            )
        _inc(report, "posts_brands_mentions", "inserted")

    print(f"  posts_brands_mentions: {len(rows)} rows", file=sys.stderr)


def port_posts_brands_signals(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    post_id_map: dict[int, str],
    brand_id_map: dict[int, str],
    limit: int | None = None,
) -> None:
    """Port posts_brands_signals junction table.

    post_id in this table is the actual tweet_id string (not an integer
    surrogate), so it's used directly without post_id_map lookup.
    """
    query = (
        "SELECT pbs.post_id, pbs.brand_id, pbs.post_type_key, pbs.sentiment "
        "FROM posts_brands_signals pbs "
        "ORDER BY pbs.post_id, pbs.brand_id, pbs.post_type_key"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for post_id, brand_id, post_type_key, sentiment in rows:
        # post_id and brand_id are already the actual values (tweet_id and nickname)
        tweet_id = str(post_id) if post_id else None
        brand_nickname = brand_id_map.get(brand_id, str(brand_id) if brand_id else None)
        if not tweet_id or not brand_nickname or not post_type_key or not sentiment:
            _inc(report, "posts_brands_signals", "skipped")
            continue
        if not dry_run:
            _safe_get_or_create(
                PostBrandSignal, {},
                post_id=tweet_id, brand_id=brand_nickname,
                post_type_id=post_type_key, sentiment_id=sentiment,
            )
        _inc(report, "posts_brands_signals", "inserted")

    print(f"  posts_brands_signals: {len(rows)} rows", file=sys.stderr)


def port_posts_brands_discourse(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    post_id_map: dict[int, str],
    brand_id_map: dict[int, str],
    key_id_maps: dict[str, dict[int, str]] | None = None,
    limit: int | None = None,
) -> None:
    """Port posts_brands_discourse junction table."""
    if key_id_maps is None:
        key_id_maps = {}
    disc_map = key_id_maps.get("discourse_keys", {})
    nat_map = key_id_maps.get("nationalism_keys", {})
    query = (
        "SELECT pbd.post_id, pbd.brand_id, pbd.discourse_key, pbd.act_id, "
        "pbd.china_nationalism, pbd.us_nationalism "
        "FROM posts_brands_discourse pbd "
        "ORDER BY pbd.post_id, pbd.brand_id, pbd.discourse_key, pbd.act_id"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for post_id, brand_id, discourse_key, act_id, china_nat, us_nat in rows:
        tweet_id = post_id_map.get(post_id)
        brand_nickname = brand_id_map.get(brand_id)
        resolved_discourse = disc_map.get(discourse_key) if discourse_key else None
        resolved_cn = nat_map.get(china_nat) if china_nat else None
        resolved_us = nat_map.get(us_nat) if us_nat else None
        if not tweet_id or not brand_nickname or not resolved_discourse:
            _inc(report, "posts_brands_discourse", "skipped")
            continue
        if not dry_run:
            _safe_get_or_create(
                PostBrandDiscourse,
                {"china_nationalism_id": resolved_cn, "us_nationalism_id": resolved_us},
                post_id=tweet_id, brand_id=brand_nickname,
                discourse_id=resolved_discourse, act_id=act_id,
            )
        _inc(report, "posts_brands_discourse", "inserted")

    print(f"  posts_brands_discourse: {len(rows)} rows", file=sys.stderr)


def port_account_post_appearances(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    limit: int | None = None,
) -> None:
    """Port account_post_appearances junction table."""
    desired_cols = ["author_id", "tweet_id", "role_at_time", "source_query_ids"]
    rows = _safe_select(src, "account_post_appearances", desired_cols,
                        order_by="author_id, tweet_id", limit=limit)

    for row in rows:
        author_id = row["author_id"]
        tweet_id = row["tweet_id"]
        if not author_id or not tweet_id:
            _inc(report, "account_post_appearances", "skipped")
            continue
        if not dry_run:
            _safe_get_or_create(
                AccountPostAppearance,
                {"role_at_time": row.get("role_at_time"),
                 "source_query_ids": row.get("source_query_ids")},
                account_id=author_id, post_id=tweet_id,
            )
        _inc(report, "account_post_appearances", "inserted")

    print(f"  account_post_appearances: {len(rows)} rows", file=sys.stderr)


def port_posts_unsanctioned_flags(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    post_id_map: dict[int, str],
    limit: int | None = None,
) -> None:
    """Port posts_unsanctioned_flags table."""
    desired_cols = ["post_id", "flags", "flag_set", "evidence", "decided_at"]
    rows = _safe_select(src, "posts_unsanctioned_flags", desired_cols,
                        order_by="post_id", limit=limit)

    for row in rows:
        post_id = row["post_id"]
        flags = row.get("flags")
        flag_set = row.get("flag_set")
        # post_id is already the tweet_id string
        tweet_id = str(post_id) if post_id else None
        if not tweet_id or not flags:
            _inc(report, "posts_unsanctioned_flags", "skipped")
            continue
        if not dry_run:
            _safe_update_or_create(
                PostUnsanctionedFlag,
                {"flags": flags, "flag_set": _parse_sqlite_json(flag_set),
                 "evidence": row.get("evidence"),
                 "decided_at": _parse_sqlite_dt(row.get("decided_at"))},
                post_id=tweet_id,
            )
        _inc(report, "posts_unsanctioned_flags", "inserted")

    print(f"  posts_unsanctioned_flags: {len(rows)} rows", file=sys.stderr)


def port_products(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    brand_id_map: dict[int, str],
    limit: int | None = None,
) -> None:
    """Port products table (has BigAutoField id, not natural key)."""
    cols = [
        "id", "repo_id", "brand_id", "hf_org_id", "hf_type", "display_name",
        "author", "sha", "private", "gated", "disabled", "pipeline_tag",
        "library_name", "downloads", "downloads_all_time", "download_velocity",
        "likes", "trending_score", "paperswithcode_id", "created_at",
        "last_modified", "tags_json", "siblings_json", "card_data_json",
        "config_json", "spaces_json", "raw_json", "collected_at", "updated_at",
    ]
    query = f"SELECT {', '.join(cols)} FROM products ORDER BY repo_id"
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for row in rows:
        vals = dict(zip(cols, row))
        repo_id = vals["repo_id"]
        if not repo_id:
            _inc(report, "products", "skipped")
            continue

        brand_nickname = brand_id_map.get(vals["brand_id"]) if vals["brand_id"] else None
        hf_org_ns = vals["hf_org_id"]  # This is the namespace TEXT FK

        defaults: dict[str, Any] = {}
        for col in cols:
            if col in ("id", "repo_id", "brand_id"):
                continue
            val = vals[col]
            if val is None:
                defaults[col] = None
            elif col in ("private", "gated", "disabled"):
                defaults[col] = _parse_sqlite_bool(val)
            elif col in ("downloads", "downloads_all_time", "likes"):
                defaults[col] = int(val) if val is not None else None
            elif col in ("download_velocity", "trending_score"):
                defaults[col] = float(val) if val is not None else None
            elif col.endswith("_at") or col in ("created_at", "last_modified",
                                                  "collected_at", "updated_at"):
                defaults[col] = _parse_sqlite_dt(val)
            elif col.endswith("_json"):
                django_col = col.replace("_json", "")  # tags_json -> tags
                defaults[django_col] = _parse_sqlite_json(val)
            else:
                defaults[col] = val

        if brand_nickname is not None:
            defaults["brand_id"] = brand_nickname
        if hf_org_ns is not None:
            defaults["hf_org_id"] = hf_org_ns

        if not dry_run:
            Product.objects.update_or_create(
                repo_id=repo_id, defaults=defaults
            )
        _inc(report, "products", "inserted")

    print(f"  products: {len(rows)} rows", file=sys.stderr)


def port_search_queries(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    brand_id_map: dict[int, str],
    limit: int | None = None,
) -> None:
    """Port search_queries table."""
    query = (
        "SELECT sq.id, sq.query_id, sq.brand_id, sq.keywords_json, "
        "sq.plan_calls_run_id, sq.created_at "
        "FROM search_queries sq ORDER BY sq.query_id"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for sq_id, query_id, brand_id, keywords_json, plan_calls_run_id, created_at in rows:
        if not query_id:
            _inc(report, "search_queries", "skipped")
            continue
        brand_nickname = brand_id_map.get(brand_id) if brand_id else None
        if not dry_run:
            SearchQuery.objects.update_or_create(
                query_id=query_id,
                defaults={
                    "brand_id": brand_nickname,
                    "keywords": _parse_sqlite_json(keywords_json),
                    "plan_calls_run_id": plan_calls_run_id,
                    "created_at": _parse_sqlite_dt(created_at),
                },
            )
        _inc(report, "search_queries", "inserted")

    print(f"  search_queries: {len(rows)} rows", file=sys.stderr)


def port_call_state(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    limit: int | None = None,
) -> None:
    """Port call_state table (no INTEGER surrogate IDs)."""
    query = (
        "SELECT cs.brand_id, cs.call_id, cs.call_kind, cs.bucket, cs.query_id, "
        "cs.last_completed_at, cs.updated_at "
        "FROM call_state cs ORDER BY cs.brand_id, cs.call_id, cs.call_kind, cs.bucket, cs.query_id"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for brand_id, call_id, call_kind, bucket, query_id, last_completed_at, updated_at in rows:
        if not all([brand_id, call_id, call_kind, query_id]):
            _inc(report, "call_state", "skipped")
            continue
        if not dry_run:
            CallState.objects.update_or_create(
                brand_id=brand_id,
                call_id=call_id,
                call_kind=call_kind,
                bucket=bucket or "",
                query_id=query_id,
                defaults={
                    "last_completed_at": _parse_sqlite_dt(last_completed_at),
                    "updated_at": _parse_sqlite_dt(updated_at),
                },
            )
        _inc(report, "call_state", "inserted")

    print(f"  call_state: {len(rows)} rows", file=sys.stderr)


def port_applied_config_snapshots(
    src: sqlite3.Connection,
    report: dict[str, Any],
    dry_run: bool,
    limit: int | None = None,
) -> None:
    """Port _applied_config_snapshot table."""
    query = (
        "SELECT acs.artifact, acs.content_hash, acs.written_at "
        "FROM _applied_config_snapshot acs ORDER BY acs.artifact"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = src.execute(query).fetchall()

    for artifact, content_hash, written_at in rows:
        if not artifact:
            _inc(report, "_applied_config_snapshot", "skipped")
            continue
        if not dry_run:
            AppliedConfigSnapshot.objects.update_or_create(
                artifact=artifact,
                defaults={
                    "content_hash": content_hash or "",
                    "written_at": _parse_sqlite_dt(written_at),
                },
            )
        _inc(report, "_applied_config_snapshot", "inserted")

    print(f"  _applied_config_snapshot: {len(rows)} rows", file=sys.stderr)


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------


def _inc(report: dict[str, Any], table: str, kind: str) -> None:
    """Increment a counter in the report."""
    if kind not in report:
        report[kind] = {}
    report[kind][table] = report[kind].get(table, 0) + 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Port x-monitor SQLite data into Django ORM (PostgreSQL)."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the source SQLite database (x_monitoring.db).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read source and print report but do not write to Django DB.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit rows per table (useful for smoketesting).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Only port posts created on or after this date.",
    )
    parser.add_argument(
        "--brands",
        type=str,
        default=None,
        help="Comma-separated list of brand nicknames to port (others are skipped).",
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=None,
        help="Write JSON report to this file (default: stdout).",
    )
    parser.add_argument(
        "--skip-posts",
        action="store_true",
        help="Skip posts and post-dependent junction tables.",
    )
    parser.add_argument(
        "--skip-products",
        action="store_true",
        help="Skip products table.",
    )

    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"error: source DB not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    brand_filter: set[str] | None = None
    if args.brands:
        brand_filter = {b.strip() for b in args.brands.split(",") if b.strip()}

    report: dict[str, Any] = {
        "inserted": {},
        "updated": {},
        "skipped": {},
        "errors": [],
        "source_db": str(source_path.resolve()),
        "target_db": "Django ORM (DATABASE_URL from project.settings)",
        "timestamp": datetime.now(UTC).isoformat(),
        "dry_run": args.dry_run,
        "limit": args.limit,
        "since": args.since,
        "brands_filter": sorted(brand_filter) if brand_filter else None,
    }

    print("=" * 64, file=sys.stderr)
    print("Port SQLite -> Django ORM", file=sys.stderr)
    print(f"  Source: {source_path}", file=sys.stderr)
    print(f"  Dry run: {args.dry_run}", file=sys.stderr)
    print(f"  Limit: {args.limit}", file=sys.stderr)
    print(f"  Since: {args.since}", file=sys.stderr)
    if brand_filter:
        print(f"  Brands filter: {brand_filter}", file=sys.stderr)
    print("=" * 64, file=sys.stderr)

    src = sqlite3.connect(str(source_path))
    src.row_factory = sqlite3.Row
    src.execute("PRAGMA journal_mode=WAL")

    try:
        # ---- Layer 1: Lookup tables ----
        print("\n[Layer 1] Lookup tables", file=sys.stderr)
        role_id_map, key_id_maps = port_lookup_tables(src, report, args.dry_run)

        # ---- Layer 2: Entities ----
        print("\n[Layer 2] Entities", file=sys.stderr)
        brand_id_map = port_brands(src, report, args.dry_run, brand_filter)
        company_id_map = port_companies(src, report, args.dry_run)
        _author_ids, account_id_map = port_accounts(
            src, report, args.dry_run, limit=args.limit,
        )

        if not args.skip_posts:
            post_id_map = port_posts(
                src, report, args.dry_run,
                account_id_map=account_id_map,
                limit=args.limit, since=args.since,
            )
        else:
            post_id_map = {}
            print("  posts: SKIPPED", file=sys.stderr)

        # ---- Layer 3: Junctions ----
        print("\n[Layer 3] Junction tables", file=sys.stderr)
        port_brands_companies(
            src, report, args.dry_run, brand_id_map, company_id_map,
            limit=args.limit,
        )
        port_brands_accounts(
            src, report, args.dry_run, brand_id_map, account_id_map,
            role_id_map, limit=args.limit,
        )
        port_companies_accounts(
            src, report, args.dry_run, company_id_map, account_id_map,
            role_id_map, limit=args.limit,
        )
        port_hf_orgs(
            src, report, args.dry_run, company_id_map, limit=args.limit,
        )
        port_attribution_map(
            src, report, args.dry_run, brand_id_map, limit=args.limit,
        )

        if not args.skip_posts:
            port_posts_brands(
                src, report, args.dry_run, post_id_map, brand_id_map,
                limit=args.limit,
            )
            port_posts_brands_mentions(
                src, report, args.dry_run, post_id_map, brand_id_map,
                limit=args.limit,
            )
            port_posts_brands_signals(
                src, report, args.dry_run, post_id_map, brand_id_map,
                limit=args.limit,
            )
            port_posts_brands_discourse(
                src, report, args.dry_run, post_id_map, brand_id_map,
                key_id_maps, limit=args.limit,
            )
            port_account_post_appearances(
                src, report, args.dry_run, limit=args.limit,
            )
            port_posts_unsanctioned_flags(
                src, report, args.dry_run, post_id_map, limit=args.limit,
            )
        else:
            print("  posts_brands: SKIPPED", file=sys.stderr)
            print("  posts_brands_mentions: SKIPPED", file=sys.stderr)
            print("  posts_brands_signals: SKIPPED", file=sys.stderr)
            print("  posts_brands_discourse: SKIPPED", file=sys.stderr)
            print("  account_post_appearances: SKIPPED", file=sys.stderr)
            print("  posts_unsanctioned_flags: SKIPPED", file=sys.stderr)

        # ---- Layer 4: Control plane ----
        print("\n[Layer 4] Control plane", file=sys.stderr)
        if not args.skip_products:
            port_products(
                src, report, args.dry_run, brand_id_map, limit=args.limit,
            )
        else:
            print("  products: SKIPPED", file=sys.stderr)
        port_search_queries(
            src, report, args.dry_run, brand_id_map, limit=args.limit,
        )
        port_call_state(src, report, args.dry_run, limit=args.limit)
        port_applied_config_snapshots(
            src, report, args.dry_run, limit=args.limit,
        )

        # ---- Summary ----
        print("\n" + "=" * 64, file=sys.stderr)
        total_inserted = sum(report["inserted"].values())
        total_skipped = sum(report["skipped"].values())
        print(f"  Total inserted/updated: {total_inserted}", file=sys.stderr)
        print(f"  Total skipped:          {total_skipped}", file=sys.stderr)
        if args.dry_run:
            print("  ** DRY RUN — no writes performed **", file=sys.stderr)
        print("=" * 64, file=sys.stderr)

    except Exception as exc:
        report["errors"].append({
            "phase": "port",
            "error": str(exc),
            "type": type(exc).__name__,
        })
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise
    finally:
        src.close()

    # Emit report
    report_json = json.dumps(report, indent=2, default=str, ensure_ascii=False)
    if args.report_file:
        Path(args.report_file).write_text(report_json)
        print(f"\nReport written to {args.report_file}", file=sys.stderr)
    else:
        print(report_json)


if __name__ == "__main__":
    main()
