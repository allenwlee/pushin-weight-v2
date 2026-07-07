#!/usr/bin/env python3
"""Populate `brand_search_terms` from `data/queries/<brand>.yaml`.

Plan: docs/plans/2026-06-25-004-feat-populate-brand-search-terms-plan.md
Units 1 + 2 of 4. Companion test: tests/test_brand_search_terms_populate.py.

Hybrid-by-design contract (x_monitor/migrations/017_brand_search_terms_hybrid.sql):
- yaml (data/queries/<brand>.yaml) is the single source for the
  TwitterAPI.io query string. Read at cycle time by
  x_monitor.query_plan.plan_calls().
- DB (`brand_search_terms` table) is the single source for the
  {term: brand_id} map used at post-fetch attribution time. Read at
  attribution time by x_monitor.attribution.extract_search_term_match.
- The yaml is NOT read at attribution time.
- The DB is NOT used to build the query string.

This script closes the populate side of the contract: it reads the same
tokens that x_monitor.query_plan._load_brand_tokens_per_model reads
(first paren group of Q2/Q3/Q5/Q6, split on " OR ") and writes them to
the DB. The drift check at the end reuses
x_monitor.run._log_brand_search_terms_drift for verification (with a
case-insensitive wrapper so drift-zero is achievable against the live
cycle's case-folded yaml map).

CLI:
    python3 scripts/2026-06-25-004-populate-brand-search-terms.py <db_path> [--dry-run]

The script is idempotent (INSERT OR IGNORE on (brand_id, term) PK) and
dry-run-safe.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


# --- 9 brand_ids without an existing `brands` row. display_name and
# --- accent_color are operator-curated first-pass placeholders. The
# --- 11 existing v1 brand_ids (minimax, qwen, deepseek, glm,
# --- mimo, moonshot_kimi, inclusionai, mistral, stepfun, ernie,
# --- hunyuan) are seeded by migration 004 and reused via INSERT OR IGNORE.
NEW_BRANDS: dict[str, tuple[str, str]] = {
    "llama":       ("Meta Llama",            "#1877f2"),
    "nemo_megatron": ("NVIDIA NeMo",           "#76b900"),
    "doubao":      ("ByteDance Doubao",      "#3d5afe"),
    "yi":          ("01.AI Yi",              "#6366f1"),
    "sensechat":   ("SenseTime SenseChat",   "#f97316"),
    "exaone":      ("LG EXAONE",             "#a855f7"),
    "kuaishou":    ("Kuaishou KwaiYii",      "#ef4444"),
    "sakana_ai":      ("Sakana AI",             "#14b8a6"),
    "upstage":     ("Upstage Solar",         "#06b6d4"),
}


# --- paths ---------------------------------------------------------------


def _repo_root() -> Path:
    """Walk up from the script to find the repo root (contains config.yaml)."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "config.yaml").is_file():
            return parent
    raise RuntimeError("could not locate repo root (no config.yaml found)")


def _queries_dir(root: Path) -> Path:
    return root / "data" / "queries"


def _config_path(root: Path) -> Path:
    return root / "config.yaml"


def _load_enabled_models(config_path: Path) -> list[str]:
    """Read `enabled_models` from config.yaml in declaration order."""
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    models = raw.get("enabled_models")
    if not isinstance(models, list) or not models:
        raise RuntimeError(f"enabled_models missing or empty in {config_path}")
    return list(models)


# --- token extraction (mirror of query_plan._load_brand_tokens_per_model)


def _extract_tokens(yaml_text: str) -> list[str]:
    """Mirror x_monitor.query_plan._load_brand_tokens_per_model byte-for-byte.

    For each Q2/Q3/Q5/Q6 entry, find the first (...) group (the brand
    clause), split on " OR ", strip whitespace, dedup preserving
    insertion order. Q1/Q4 entries are skipped (account-based).

    Returns the deduped token list as-is — case, whitespace, embedded
    quotes, CJK characters, and emoji are preserved (R2).
    """
    raw = yaml.safe_load(yaml_text) or {}
    seen: set[str] = set()
    toks: list[str] = []
    for entry in raw.get("queries", []) or []:
        if entry.get("id") not in {"Q2", "Q3", "Q5", "Q6"}:
            continue
        inner = entry.get("query_string", "") or ""
        depth = 0
        start = -1
        for i, ch in enumerate(inner):
            if ch == "(":
                if depth == 0:
                    start = i + 1
                depth += 1
            elif ch == ")":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start != -1:
                        group = inner[start:i]
                        for tok in group.split(" OR "):
                            tok = tok.strip()
                            if tok and tok not in seen:
                                seen.add(tok)
                                toks.append(tok)
                        start = -1
                        break
    return toks


# --- brand-row creation --------------------------------------------------


def _ensure_brand_row(
    conn: sqlite3.Connection,
    brand_id: str,
    display_name: str,
    accent_color: str,
    now: str,
) -> bool:
    """INSERT OR IGNORE a brand row if missing. Returns True if inserted."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO brands"
        "(nickname, display_name, accent_color, is_sentinel, created_at)"
        " VALUES (?, ?, ?, 0, ?)",
        (brand_id, display_name, accent_color, now),
    )
    return cur.rowcount > 0


# --- main ---------------------------------------------------------------


def _populate(
    db_path: Path,
    queries_dir: Path,
    enabled_models: list[str],
    *,
    dry_run: bool,
) -> int:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    now = datetime.now(timezone.utc).isoformat()

    new_brand_rows = 0
    new_term_rows = 0
    per_brand: list[tuple[str, int, int]] = []  # (brand_id, tokens, new_terms)
    yaml_tokens_per_model: dict[str, list[str]] = {}

    for brand_id in enabled_models:
        path = queries_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  {brand_id}: yaml missing at {path}; skipping", file=sys.stderr)
            yaml_tokens_per_model[brand_id] = []
            continue
        tokens = _extract_tokens(path.read_text(encoding="utf-8"))
        yaml_tokens_per_model[brand_id] = tokens

        if dry_run:
            meta = NEW_BRANDS.get(brand_id)
            if meta:
                print(f"  {brand_id}: would INSERT brand row"
                      f" (display_name={meta[0]!r}, accent_color={meta[1]})")
                new_brand_rows += 1
            print(f"  {brand_id}: would INSERT {len(tokens)} brand_search_terms"
                  f" (sample: {tokens[:5]})")
            per_brand.append((brand_id, len(tokens), len(tokens)))
            continue

        # Real run.
        meta = NEW_BRANDS.get(brand_id)
        if meta:
            inserted = _ensure_brand_row(
                conn, brand_id, meta[0], meta[1], now,
            )
            if inserted:
                new_brand_rows += 1

        n_new = 0
        # post-020: brand_search_terms.brand_id is INTEGER FK → brands.id;
        # resolve the slug → INTEGER id once per brand before the
        # per-token insert loop.
        brand_int_row = conn.execute(
            "SELECT id FROM brands WHERE nickname = ?", (brand_id,)
        ).fetchone()
        if brand_int_row is None:
            print(f"  {brand_id}: brand row missing after _ensure_brand_row;"
                  f" skipping term insert", file=sys.stderr)
            continue
        brand_int = brand_int_row[0]
        for tok in tokens:
            cur = conn.execute(
                "INSERT OR IGNORE INTO brand_search_terms"
                "(brand_id, term, added_at) VALUES (?, ?, ?)",
                (brand_int, tok, now),
            )
            if cur.rowcount > 0:
                n_new += 1
        new_term_rows += n_new
        per_brand.append((brand_id, len(tokens), n_new))

    if not dry_run:
        conn.commit()

    # --- read back, build db_terms (case-folded) for drift check ---------
    if dry_run:
        # No writes happened; tables may not even exist on a fresh DB.
        # The drift-zero assertion is a post-write verification, not a
        # dry-run preview.
        print()
        print("--- summary ---")
        print(f"  enabled_models: {len(enabled_models)}")
        print(f"  planned new brand rows: {new_brand_rows}")
        print(f"  planned new brand_search_terms rows:"
              f" {sum(n for _, _, n in per_brand)}")
        print(f"  (dry-run: no drift check performed)")
        conn.close()
        return 0

    db_rows = conn.execute(
        "SELECT b.nickname AS brand_id, bst.term"
        " FROM brand_search_terms bst JOIN brands b ON b.id = bst.brand_id"
    ).fetchall()
    db_terms: dict[str, str] = {}
    for brand_id, term in db_rows:
        db_terms[term.lower()] = brand_id

    # --- build yaml_terms (case-folded, same shape as
    # --- _build_brand_index's second return value) -----------------------
    yaml_terms: dict[str, str] = {}
    for brand_id, tokens in yaml_tokens_per_model.items():
        for tok in tokens:
            yaml_terms[tok.lower()] = brand_id

    # --- drift check (case-insensitive: lowercased keys on both sides) --
    yaml_keys = set(yaml_terms)
    db_keys = set(db_terms)
    only_yaml = yaml_keys - db_keys
    only_db = db_keys - yaml_keys
    shared = yaml_keys & db_keys
    mismatched = {t for t in shared if yaml_terms[t] != db_terms[t]}

    print()
    print("--- summary ---")
    print(f"  enabled_models: {len(enabled_models)}")
    print(f"  new brand rows: {new_brand_rows}")
    print(f"  new brand_search_terms rows: {new_term_rows}")
    print(f"  total brand_search_terms rows: {len(db_rows)}")
    print(f"  drift: yaml-only={len(only_yaml)}"
          f" db-only={len(only_db)}"
          f" mismatched={len(mismatched)}")
    if only_yaml or only_db or mismatched:
        if only_yaml:
            print(f"    yaml-only sample: {sorted(only_yaml)[:5]}")
        if only_db:
            print(f"    db-only sample: {sorted(only_db)[:5]}")
        if mismatched:
            print(f"    mismatched sample: {sorted(mismatched)[:5]}")
        conn.close()
        return 1
    print("  drift: zero")
    print()
    print("--- per-brand ---")
    for brand_id, total, new in per_brand:
        print(f"  {brand_id}: {total} tokens ({new} new)")
    print()
    print("--- final table counts ---")
    for tbl in [
        "brands",
        "brand_search_terms",
        "companies",
        "brands_companies",
        "brands_accounts",
    ]:
        n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl}: {n}")
    conn.close()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Populate brand_search_terms from data/queries/<brand>.yaml"
    )
    p.add_argument("db_path", type=Path, help="path to x_monitoring.db")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned writes; no DB writes",
    )
    args = p.parse_args()

    if not args.db_path.exists():
        print(f"db not found at {args.db_path}", file=sys.stderr)
        return 2

    root = _repo_root()
    queries_dir = _queries_dir(root)
    if not queries_dir.is_dir():
        print(f"queries dir missing at {queries_dir}", file=sys.stderr)
        return 2
    config_path = _config_path(root)
    if not config_path.exists():
        print(f"config.yaml missing at {config_path}", file=sys.stderr)
        return 2

    enabled_models = _load_enabled_models(config_path)
    print(f"loaded {len(enabled_models)} enabled_models from {config_path}")

    return _populate(
        args.db_path,
        queries_dir,
        enabled_models,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())