#!/usr/bin/env python3
"""Seed companies / brands / brands_companies / accounts / brands_accounts /
hf_orgs from the operator-curated CSV.

Plan: docs/plans/2026-06-25-004-feat-populate-brand-search-terms-plan.md
Units 3 + 4 of 4. Companion test:
tests/test_seed_companies_brands_from_csv.py.

Source data: docs/research/2026-06-25-120000-top-100-llm-brands-stripped.csv
— 17 columns A-Q, 20 data rows covering the 20 enabled brands in
config.yaml.

Column mapping (R10):
  A # (rank)             — informational only, not seeded
  B brands.display_name  — brands.display_name; brand_id = slug
  C brands.display_name_en   — brands.display_name_en
  D brands.display_name_zh_cn — brands.display_name_zh_cn
  E company.display_name — companies.display_name; company_id = slug
  F company.display_name_en   — companies.display_name_en
  G company.display_name_zh_cn — companies.display_name_zh_cn
  H company.hq_country   — companies.hq_country
  I co_hq_city           — not seeded
  J ai_lab_city          — not seeded
  K brands_accounts.role_id='official'  — X URLs, multi-value
  L brands_accounts.role_id='staff'     — X URLs, multi-value
  M notes                — IGNORED (read but discarded; operator direction)
  N github_accounts      — not seeded (no brands_github_orgs table)
  O hf_orgs              — HF URLs, multi-value → hf_orgs.id (namespace)
  P hf_followers_num     — not seeded (informational)
  Q tier                 — not seeded (no brands.tier column)

CLI:
    python3 scripts/2026-06-25-005-seed-companies-brands-from-csv.py \\
        <db_path> <csv_path> [--dry-run] [--limit N]

The script is idempotent (all INSERTs are INSERT OR IGNORE) and
dry-run-safe.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


# --- column indices (0-based) -------------------------------------------
COL_BRAND_NAME = 1
COL_BRAND_NAME_EN = 2
COL_BRAND_NAME_ZH_CN = 3
COL_COMPANY_NAME = 4
COL_COMPANY_NAME_EN = 5
COL_COMPANY_NAME_ZH_CN = 6
COL_COMPANY_COUNTRY = 7
COL_OFFICIAL_X = 10
COL_STAFF_X = 11
COL_NOTES = 12  # read but discarded
COL_HF_ORGS = 14

EXPECTED_HEADER = [
    "#",
    "brands.display_name",
    "brands.display_name_en",
    "brands.display_name_zh_cn",
    "company.display_name",
    "company.display_name_en",
    "company.display_name_zh_cn",
    "company.hq_country",
    "co_hq_city",
    "ai_lab_city",
    "brands_accounts.role_id='official'",
    "brands_accounts.role_id='staff'",
    "notes",
    "github_accounts",
    "hf_orgs",
    "hf_followers_num",
    "tier",
]


# --- operator-curated slug overrides ------------------------------------
# Keys: display_name as it appears in the CSV column.
# Values: canonical id to use for the row.
# These cover:
#   - CJK / non-ASCII display_names that slugify() can't handle.
#   - v1 brand_ids that don't match a naive slug (Mimo→xiaomi_mimo,
#     GLM/ChatGLM→glm, etc.).
#   - v1 company_ids (mistral_ai, inclusion_ai, deepseek_co, etc.).
# New rows that slugify cleanly are handled by the regex fallback.
BRAND_SLUG_OVERRIDES: dict[str, str] = {
    # 11 v1 brand_ids reused.
    "千问": "qwen",
    "MiniMax": "minimax",
    "深度求索": "deepseek",
    "GLM / ChatGLM": "glm",
    "MiMo": "xiaomi_mimo",
    "Moonshot / Kimi": "moonshot_kimi",
    "InclusionAI": "inclusionai",
    "Mistral": "mistral",
    "StepFun / Step": "stepfun",
    "ERNIE / Wenxin": "ernie",
    "腾讯混元": "hunyuan",
    # 9 new brand_ids from plan 2026-06-25-001.
    "Llama": "llama",
    "NeMo / Megatron": "nvidia_nemo",
    "Doubao / Seed": "doubao",
    "零一万物 Yi": "yi",
    "SenseChat / SenseNova": "sensechat",
    "EXAONE": "exaone",
    "Kuaishou / KwaiYii": "kuaishou",
    "Mimo": "xiaomi_mimo",
    "Sakana AI": "sakana",
    "サカナAI": "sakana",
    "업스테이지": "upstage",
}

COMPANY_SLUG_OVERRIDES: dict[str, str] = {
    # 11 v1 company_ids from migration 004 + 009.
    "Meta（元）": "meta",
    "Mistral AI": "mistral_ai",
    "NVIDIA": "nvidia",
    "阿里巴巴": "alibaba",
    "Alibaba": "alibaba",
    "百度": "baidu",
    "Baidu": "baidu",
    "腾讯": "tencent",
    "Tencent": "tencent",
    "字节跳动": "bytedance",
    "ByteDance": "bytedance",
    "深度求索": "deepseek_co",
    "DeepSeek": "deepseek_co",
    "智谱AI": "zhipu",
    "Z.ai": "zhipu",
    "月之暗面": "moonshot",
    "Moonshot AI": "moonshot",
    "MiniMax": "minimax",
    "稀宇科技": "minimax",
    "零一万物": "yi_co",
    "01.AI": "yi_co",
    "蚂蚁 Inclusion AI": "inclusion_ai",
    "Inclusion AI": "inclusion_ai",
    "商汤科技": "sensetime",
    "SenseTime": "sensetime",
    "阶跃星辰": "stepfun_inc",
    "StepFun": "stepfun_inc",
    "小米": "xiaomi",
    "Xiaomi": "xiaomi",
    "LG AI研究院": "lg",
    "LG AI Research": "lg",
    "サカナAI": "sakana_co",
    "Sakana AI": "sakana_co",
    "快手科技": "kuaishou_co",
    "Kuaishou Technology": "kuaishou_co",
    "업스테이지": "upstage_co",
    "Upstage": "upstage_co",
}


# --- helpers -------------------------------------------------------------


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str, overrides: dict[str, str]) -> str:
    """Resolve a display_name → canonical id.

    Lookup order: overrides first, then regex slugify. Empty result
    raises (operator must add an override for CJK / non-ASCII names).
    """
    if name in overrides:
        return overrides[name]
    slug = _SLUG_RE.sub("_", name.lower()).strip("_")
    if not slug:
        raise ValueError(
            f"slugify({name!r}) produced empty slug; "
            f"add an override to the script's slug override map"
        )
    return slug


def split_multivalue(cell: str) -> list[str]:
    """Split a multi-value cell on commas and whitespace runs.

    Returns the deduped list of non-empty stripped tokens, preserving
    insertion order. Trailing punctuation is preserved (callers
    should strip on parse).
    """
    if not cell:
        return []
    # Split on commas OR runs of whitespace, then strip each token.
    tokens = re.split(r"[,\s]+", cell.strip())
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


_HF_URL_RE = re.compile(r"huggingface\.co/([^/?\s,;]+)")
_X_URL_RE = re.compile(r"(?:x|twitter)\.com/([^/?\s,;]+)")


def parse_hf_url(url: str) -> str | None:
    """Extract the HF namespace from a huggingface.co URL.

    Returns the namespace (first path segment), or None if the URL
    doesn't match. Trailing punctuation is stripped.
    """
    if not url:
        return None
    m = _HF_URL_RE.search(url)
    if not m:
        return None
    ns = m.group(1).rstrip("/")
    return ns or None


def parse_x_url(url: str) -> str | None:
    """Extract the X/Twitter handle from a URL.

    Returns the handle (path segment after x.com or twitter.com), or
    None if the URL doesn't match. Trailing `;`, `,`, `/`, `?` are
    stripped (the CSV has trailing punctuation on some cells).
    """
    if not url:
        return None
    m = _X_URL_RE.search(url)
    if not m:
        return None
    handle = m.group(1).rstrip("/;,?")
    return handle or None


def parse_followers(cell: str) -> int:
    """Parse a comma-formatted follower count (e.g. `"38,400"` → 38400).

    Returns 0 on parse error or empty cell. Defensive: never raises.
    """
    if not cell:
        return 0
    try:
        return int(cell.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


def _insert_account(
    conn: sqlite3.Connection,
    author_id: str,
    handle: str,
    now: str,
    has_engagement_tier: bool,
) -> sqlite3.Cursor:
    """INSERT OR IGNORE a row into `accounts`. Adapts to the schema
    variant: production DBs (≤ migration 011) have an engagement_tier
    column; fresh DBs (≥ migration 012) have dropped it.
    """
    if has_engagement_tier:
        return conn.execute(
            "INSERT OR IGNORE INTO accounts"
            "(author_id, handle, verified, bio_contains_brand,"
            " engagement_tier, first_seen_at, last_seen_at)"
            " VALUES (?, ?, 0, 0, 'low', ?, ?)",
            (author_id, handle, now, now),
        )
    return conn.execute(
        "INSERT OR IGNORE INTO accounts"
        "(author_id, handle, verified, bio_contains_brand,"
        " first_seen_at, last_seen_at)"
        " VALUES (?, ?, 0, 0, ?, ?)",
        (author_id, handle, now, now),
    )


# --- main ----------------------------------------------------------------


def _process_row(
    conn: sqlite3.Connection,
    row: list[str],
    now: str,
    *,
    dry_run: bool,
    has_engagement_tier: bool,
    ba_role_col: str,
) -> dict[str, int]:
    """Process one CSV row. Returns counts per table."""
    counts = {
        "companies": 0,
        "brands": 0,
        "brands_companies": 0,
        "accounts": 0,
        "brands_accounts": 0,
        "hf_orgs": 0,
    }
    # Single-value fields.
    brand_name = row[COL_BRAND_NAME]
    brand_name_en = row[COL_BRAND_NAME_EN] or None
    brand_name_zh_cn = row[COL_BRAND_NAME_ZH_CN] or None
    company_name = row[COL_COMPANY_NAME]
    company_name_en = row[COL_COMPANY_NAME_EN] or None
    company_name_zh_cn = row[COL_COMPANY_NAME_ZH_CN] or None
    hq_country = row[COL_COMPANY_COUNTRY] or None

    # Column M (notes) is read at row[COL_NOTES] but discarded — the
    # column is operator-curated free text and not part of the seed
    # contract (operator direction 2026-06-25).
    _notes = row[COL_NOTES]  # noqa: F841 — read & discarded

    brand_id = slugify(brand_name, BRAND_SLUG_OVERRIDES)
    company_id = slugify(company_name, COMPANY_SLUG_OVERRIDES)

    if dry_run:
        counts["companies"] = 1
        counts["brands"] = 1
        counts["brands_companies"] = 1
        for url in split_multivalue(row[COL_OFFICIAL_X]):
            if parse_x_url(url):
                counts["accounts"] += 1
                counts["brands_accounts"] += 1
        for url in split_multivalue(row[COL_STAFF_X]):
            if parse_x_url(url):
                counts["accounts"] += 1
                counts["brands_accounts"] += 1
        for url in split_multivalue(row[COL_HF_ORGS]):
            if parse_hf_url(url):
                counts["hf_orgs"] += 1
        return counts

    # INSERT OR IGNORE companies.
    cur = conn.execute(
        "INSERT OR IGNORE INTO companies"
        "(company_id, display_name, display_name_en, display_name_zh_cn,"
        " hq_country, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (company_id, company_name, company_name_en, company_name_zh_cn,
         hq_country, now),
    )
    counts["companies"] = cur.rowcount

    # INSERT OR IGNORE brands.
    cur = conn.execute(
        "INSERT OR IGNORE INTO brands"
        "(brand_id, display_name, display_name_en, display_name_zh_cn,"
        " accent_color, is_sentinel, created_at)"
        " VALUES (?, ?, ?, ?, ?, 0, ?)",
        (brand_id, brand_name, brand_name_en, brand_name_zh_cn,
         "#9ca3af", now),
    )
    counts["brands"] = cur.rowcount

    # INSERT OR IGNORE brands_companies.
    cur = conn.execute(
        "INSERT OR IGNORE INTO brands_companies"
        "(brand_id, company_id, ownership_pct) VALUES (?, ?, 1.0)",
        (brand_id, company_id),
    )
    counts["brands_companies"] = cur.rowcount

    # hf_orgs.
    for url in split_multivalue(row[COL_HF_ORGS]):
        ns = parse_hf_url(url)
        if not ns:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO hf_orgs"
            "(id, company_id, confirmed, discovered_via, added_at)"
            " VALUES (?, ?, 1, 'curated', ?)",
            (ns, company_id, now),
        )
        counts["hf_orgs"] += cur.rowcount

    # brands_accounts (official + staff).
    for url in split_multivalue(row[COL_OFFICIAL_X]):
        handle = parse_x_url(url)
        if not handle:
            continue
        author_id = "synthetic:" + handle.lower()
        cur = _insert_account(
            conn, author_id, handle, now, has_engagement_tier,
        )
        counts["accounts"] += cur.rowcount
        cur = conn.execute(
            f"INSERT OR IGNORE INTO brands_accounts"
            f"(brand_id, author_id, {ba_role_col}, added_at)"
            f" VALUES (?, ?, 'official', ?)",
            (brand_id, author_id, now),
        )
        counts["brands_accounts"] += cur.rowcount

    for url in split_multivalue(row[COL_STAFF_X]):
        handle = parse_x_url(url)
        if not handle:
            continue
        author_id = "synthetic:" + handle.lower()
        cur = _insert_account(
            conn, author_id, handle, now, has_engagement_tier,
        )
        counts["accounts"] += cur.rowcount
        cur = conn.execute(
            f"INSERT OR IGNORE INTO brands_accounts"
            f"(brand_id, author_id, {ba_role_col}, added_at)"
            f" VALUES (?, ?, 'staff', ?)",
            (brand_id, author_id, now),
        )
        counts["brands_accounts"] += cur.rowcount

    return counts


def main() -> int:
    p = argparse.ArgumentParser(
        description="Seed 6 company/brand/account tables from operator CSV"
    )
    p.add_argument("db_path", type=Path, help="path to x_monitoring.db")
    p.add_argument("csv_path", type=Path, help="path to operator CSV")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned writes; no DB writes",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="process only the first N data rows (after header)",
    )
    args = p.parse_args()

    if not args.db_path.exists():
        print(f"db not found at {args.db_path}", file=sys.stderr)
        return 2
    if not args.csv_path.exists():
        print(f"csv not found at {args.csv_path}", file=sys.stderr)
        return 2

    with args.csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print("csv is empty", file=sys.stderr)
            return 2
        if header != EXPECTED_HEADER:
            print(
                f"csv header mismatch.\n"
                f"  expected: {EXPECTED_HEADER}\n"
                f"  got:      {header}",
                file=sys.stderr,
            )
            return 2
        rows = list(reader)

    if args.limit is not None:
        rows = rows[: args.limit]

    conn = sqlite3.connect(args.db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    now = datetime.now(timezone.utc).isoformat()

    # Detect schema variations: production DB may be at migration 11
    # (engagement_tier present in `accounts`) while a fresh DB through
    # migration 019 has dropped it. Adapt the accounts INSERT to match.
    accounts_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()
    }
    has_engagement_tier = "engagement_tier" in accounts_cols

    # Migration 015 renamed `brands_accounts.role` → `role_id`. Production
    # DBs (≤ migration 014) still have `role`; fresh DBs (≥ migration 015)
    # have `role_id`. Pick whichever column exists.
    ba_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(brands_accounts)").fetchall()
    }
    ba_role_col = "role_id" if "role_id" in ba_cols else "role"

    # Defensive: ensure the role enum table contains 'official', 'staff',
    # and 'community'. The brands_accounts.role column has FK to the
    # role enum (added in migration 008). Migration 016 trims the role
    # family to exactly {official, staff, community}, but until 016
    # lands on production the role_keys table (pre-rename name; migration
    # 015 renamed it to `roles`) may still hold the pre-trim 5 values
    # {official, community, researcher, press, vendor} — 'staff' would
    # fail the FK constraint. INSERT OR IGNORE is a no-op on DBs that
    # already have 'staff' (post-migration-016) and a bootstrap on
    # pre-016 DBs.
    role_table = conn.execute(
        "SELECT name FROM sqlite_master"
        " WHERE type='table' AND name IN ('role_keys', 'roles') LIMIT 1"
    ).fetchone()
    if role_table is not None:
        role_table = role_table[0]
        for role in ("official", "staff", "community"):
            conn.execute(
                f"INSERT OR IGNORE INTO {role_table}(key, created_at)"
                f" VALUES (?, ?)",
                (role, now),
            )

    totals: dict[str, int] = {
        "companies": 0,
        "brands": 0,
        "brands_companies": 0,
        "accounts": 0,
        "brands_accounts": 0,
        "hf_orgs": 0,
    }
    n_processed = 0
    for row in rows:
        if not row or not row[COL_BRAND_NAME]:
            continue
        try:
            counts = _process_row(
                conn, row, now, dry_run=args.dry_run,
                has_engagement_tier=has_engagement_tier,
                ba_role_col=ba_role_col,
            )
        except ValueError as e:
            print(f"  row {n_processed + 1}: {e}", file=sys.stderr)
            continue
        for k, v in counts.items():
            totals[k] += v
        if args.dry_run:
            print(
                f"  {row[COL_BRAND_NAME]}: planned"
                f" brands={counts['brands']}"
                f" companies={counts['companies']}"
                f" accounts={counts['accounts']}"
                f" brands_accounts={counts['brands_accounts']}"
                f" hf_orgs={counts['hf_orgs']}"
            )
        n_processed += 1

    if not args.dry_run:
        conn.commit()

    print()
    print("--- summary ---")
    print(f"  rows processed: {n_processed}")
    if args.dry_run:
        print("  (dry-run: planned writes shown above)")
    else:
        for tbl in [
            "companies", "brands", "brands_companies",
            "accounts", "brands_accounts", "hf_orgs",
        ]:
            n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"  {tbl}: {n} total ({totals[tbl]} new)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())