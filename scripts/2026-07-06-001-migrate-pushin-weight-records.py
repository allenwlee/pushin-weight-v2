#!/usr/bin/env python3
"""Migrate the curated seed layer of pushin_weight Postgres into x_monitoring.db.

Plan: docs/plans/2026-07-06-002-feat-pushin-weight-records-migration-plan.md
Unit 4 of 6 (U4 — the data-side CLI script; U1 is the schema-side
migration that this script assumes has already been applied).

Companion test: tests/test_migrate_pushin_weight_records.py.

This script ports the 13 source tables that constitute the curated seed
layer (NOT posts/products/runs — source is empty for those):

  1.  brands                          (post-migration 030: 6 new + 3 renames done)
  2.  companies                       (post-migration 030: 9 new done)
  3.  accounts                        (49 source rows)
  4.  brands_accounts                 (62 source edges)
  5.  brands_companies                (11 source edges)
  6.  hf_orgs                         (21 source rows)
  7.  brand_search_terms              (72 source rows; 7 brands have any)
  8.  brand_keywords                  (0 source rows; target's 029 owns these)
  9.  brand_hashtags                  (0 source rows)
  10. discourse                       (10 keys + 20 labels; 2 aliases)
  11. post_types                      (4 source keys + 8 labels; aliases to 6 target keys)
  12. nationalism                     (6 keys + 12 labels; 1:1)
  13. roles                           (3 keys + 6 labels; 1:1)

Three layers:
  - Source reader: subprocess to psql, OR read from a SQLite fixture
  - Alias resolver: reads the YAML alias map and applies source→target slugs
  - Target writer: direct sqlite3 with INSERT OR IGNORE; resolves INTEGER
    surrogate ids via follow-up SELECTs (because Store.upsert_account
    gates on KNOWN_MODELS, and the 6 new brands aren't in that frozenset)

CLI:
    python3 scripts/2026-07-06-001-migrate-pushin-weight-records.py \\
        --target-db data/x_monitoring.db \\
        --alias-map scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml \\
        --source-connstr "host=localhost port=5432 user=fuchitalee dbname=pushin_weight" \\
        [--write] [--fixture tests/fixtures/pushin_weight_seed.sqlite]

The script is idempotent (every INSERT is INSERT OR IGNORE) and
dry-run-safe (no write transaction opens without --write).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("error: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

PSQL_BIN = "/opt/homebrew/opt/postgresql@17/bin/psql"

# Lookup tables to port, in FK order. Parents before children.
# Each entry: (source_table, target_table, key_column, has_locale, has_label)
# - has_locale: source has a 'locale' column to rename to 'lang' for target
# - has_label: source has a `label` column to copy verbatim
LOOKUP_TABLES: list[dict[str, Any]] = [
    {
        "source": "discourse",
        "target": "discourse_keys",
        "key_col": "key",
        "label_source": "discourse_labels",
        "label_target": "discourse_labels",
        "label_key_col": "discourse_key",
    },
    {
        "source": "post_types",
        "target": "post_type_keys",
        "key_col": "key",
        "label_source": "post_type_labels",
        "label_target": "post_type_labels",
        "label_key_col": "post_type_key",
    },
    {
        "source": "nationalism",
        "target": "nationalism_keys",
        "key_col": "key",
        "label_source": "nationalism_labels",
        "label_target": "nationalism_labels",
        "label_key_col": "nationalism_key",
    },
    {
        "source": "roles",
        "target": "roles",
        "key_col": "key",
        "label_source": "role_labels",
        "label_target": "role_labels",
        "label_key_col": "role_key",
    },
]

# Edge tables to port AFTER accounts + brands + companies are in target.
# Each entry: (source_table, target_table, source_fk_columns, target_fk_columns)
# source_fk_columns are slug/TEXT; target_fk_columns are INTEGER surrogate ids.
EDGE_TABLES: list[dict[str, Any]] = [
    {
        "source": "brands_accounts",
        "target": "brands_accounts",
        "source_fks": {"brand_id": "brands", "author_id": "accounts", "role_key": "roles"},
        "target_fks": {"brand_id": "brands.id", "author_id": "accounts.id", "role_id": "roles.id"},
        "extra_cols": ["added_at"],
    },
    {
        "source": "brands_companies",
        "target": "brands_companies",
        "source_fks": {"brand_id": "brands", "company_id": "companies"},
        "target_fks": {"brand_id": "brands.id", "company_id": "companies.id"},
        "extra_cols": ["ownership_pct"],
    },
    {
        "source": "brand_search_terms",
        "target": "brand_search_terms",
        "source_fks": {"brand_id": "brands"},
        "target_fks": {"brand_id": "brands.id"},
        "extra_cols": ["term", "added_at"],
    },
    {
        "source": "hf_orgs",
        "target": "hf_orgs",
        "source_fks": {"company_id": "companies"},
        "target_fks": {"company_id": "companies.id"},
        "extra_cols": ["namespace", "confirmed", "discovered_via", "added_at"],
    },
]


# -----------------------------------------------------------------------------
# Source reader
# -----------------------------------------------------------------------------

def _read_source_table_psql(
    connstr: str, table: str, columns: list[str]
) -> list[dict[str, Any]]:
    """Read all rows from a Postgres table via `psql -At -F\\t`.

    Returns list of dicts (column → value). Values are strings; the
    caller is responsible for type coercion.
    """
    cols = ",".join(f'"{c}"' for c in columns)
    sql = f'SELECT {cols} FROM "{table}";'
    cmd = [PSQL_BIN, connstr, "-At", "-F\t", "-c", sql]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"psql failed for table {table!r}: {proc.stderr.strip()}"
        )
    rows: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != len(columns):
            # Postgres null renders as empty string; tolerate short rows
            parts = parts + [""] * (len(columns) - len(parts))
        rows.append(dict(zip(columns, parts)))
    return rows


def _read_source_table_sqlite(
    fixture_path: Path, table: str, columns: list[str]
) -> list[dict[str, Any]]:
    """Read all rows from a SQLite fixture table."""
    conn = sqlite3.connect(str(fixture_path))
    conn.row_factory = sqlite3.Row
    try:
        cols_csv = ",".join('"' + c + '"' for c in columns)
        cur = conn.execute(f'SELECT {cols_csv} FROM "{table}"')
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Alias resolver
# -----------------------------------------------------------------------------

class AliasResolver:
    """Loads the YAML alias map and resolves source → target slugs/keys."""

    def __init__(self, alias_map: dict[str, Any]) -> None:
        self.brands: dict[str, str] = alias_map.get("brands", {})
        self.companies: dict[str, str] = alias_map.get("companies", {})
        self.discourse: dict[str, str] = alias_map.get("discourse", {})
        self.post_type: dict[str, str] = alias_map.get("post_type", {})
        self.sentinels_dropped: set[str] = set(
            alias_map.get("sentinels_dropped", [])
        )

    def resolve_brand(self, source_id: str) -> str | None:
        """Return target slug for a source brand id, or None if dropped."""
        if source_id in self.sentinels_dropped:
            return None
        # Reverse the map: source_id is the value
        for target, source in self.brands.items():
            if source == source_id:
                return target
        # 1:1 (source == target)
        return source_id

    def resolve_company(self, source_id: str) -> str | None:
        for target, source in self.companies.items():
            if source == source_id:
                return target
        return source_id

    def resolve_discourse(self, source_key: str) -> str | None:
        for target, source in self.discourse.items():
            if source == source_key:
                return target
        return source_key  # 1:1

    def resolve_post_type(self, source_key: str) -> str | None:
        for target, source in self.post_type.items():
            if source == source_key:
                return target
        return source_key  # 1:1

    def resolve_role(self, source_key: str) -> str:
        # roles are 1:1
        return source_key


# -----------------------------------------------------------------------------
# Type coercion
# -----------------------------------------------------------------------------

def _coerce_bool(v: Any) -> int:
    """Postgres boolean (rendered as 't'/'f' by psql -At) → 0/1."""
    if isinstance(v, bool):
        return int(v)
    s = str(v).strip().lower()
    if s in ("t", "true", "1"):
        return 1
    if s in ("f", "false", "0"):
        return 0
    return 0


def _coerce_timestamptz(v: Any) -> str:
    """Postgres TIMESTAMPTZ (rendered as ISO 8601 with offset by psql -At)
    → ISO TEXT (preserves the +09:00 offset per KTD5)."""
    if v is None or v == "":
        return ""
    s = str(v).strip()
    # Already ISO 8601 — pass through.
    # If psql gave us a date-only string, leave it; the column accepts TEXT.
    return s


# -----------------------------------------------------------------------------
# Target writer (per-table)
# -----------------------------------------------------------------------------

class TargetWriter:
    """Wraps a sqlite3 connection to x_monitoring.db and exposes per-table
    upsert methods that resolve TEXT slugs to INTEGER surrogate ids."""

    def __init__(self, db_path: Path, write: bool) -> None:
        self.db_path = db_path
        self.write = write
        # isolation_level=None gives us autocommit; we manage BEGIN/COMMIT
        # explicitly per table when --write is set.
        self._conn = sqlite3.connect(str(db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = OFF")

    def close(self) -> None:
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.close()

    # --- slug → INTEGER id caches --------------------------------------

    def _brand_id(self, nickname: str) -> int | None:
        row = self._conn.execute(
            "SELECT id FROM brands WHERE nickname = ?", (nickname,)
        ).fetchone()
        return row["id"] if row else None

    def _company_id(self, nickname: str) -> int | None:
        row = self._conn.execute(
            "SELECT id FROM companies WHERE nickname = ?", (nickname,)
        ).fetchone()
        return row["id"] if row else None

    def _account_id(self, author_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT id FROM accounts WHERE author_id = ?", (author_id,)
        ).fetchone()
        return row["id"] if row else None

    def _role_id(self, key: str) -> int | None:
        row = self._conn.execute(
            "SELECT id FROM roles WHERE key = ?", (key,)
        ).fetchone()
        return row["id"] if row else None

    def _lookup_key_id(self, target_table: str, key: str) -> int | None:
        # For tables like discourse_keys, post_type_keys, etc.
        row = self._conn.execute(
            f'SELECT id FROM "{target_table}" WHERE key = ?', (key,)
        ).fetchone()
        return row["id"] if row else None

    def _target_count(self, table: str) -> int:
        row = self._conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()
        return row["n"]

    # --- per-table upserts --------------------------------------------

    def upsert_accounts(
        self, rows: list[dict[str, Any]], report: dict[str, Any]
    ) -> int:
        """Insert accounts. Skipped columns: bio_en, bio_zh_cn, notes, raw_payload.
        R10: raw_payload, notes, bio_en, bio_zh_cn are dropped silently."""
        inserted: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for r in rows:
            author_id = r.get("author_id", "").strip()
            if not author_id:
                continue
            if self._account_id(author_id) is not None:
                skipped.append({"author_id": author_id})
                continue
            if not self.write:
                inserted.append({"author_id": author_id})
                continue
            self._conn.execute(
                """
                INSERT OR IGNORE INTO accounts (
                    author_id, handle, display_name, bio, bio_fetched_at,
                    verified, bio_contains_brand, first_seen_at, last_seen_at,
                    source_query_ids
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    author_id,
                    r.get("handle", "").strip() or None,
                    r.get("display_name", "").strip() or None,
                    r.get("bio", "").strip() or None,
                    _coerce_timestamptz(r.get("bio_fetched_at", "")) or None,
                    _coerce_bool(r.get("verified", "f")),
                    _coerce_bool(r.get("bio_contains_brand", "")) if r.get("bio_contains_brand") else None,
                    _coerce_timestamptz(r.get("first_seen_at", "")),
                    _coerce_timestamptz(r.get("last_seen_at", "")),
                    r.get("source_query_ids", "").strip() or None,
                ),
            )
            inserted.append({"author_id": author_id})
        report["accounts"] = {
            "table": "accounts",
            "source_rows": len(rows),
            "inserted": len(inserted),
            "skipped_duplicate": len(skipped),
        }
        return len(inserted)

    def upsert_brand_search_terms(
        self,
        rows: list[dict[str, Any]],
        resolver: AliasResolver,
        report: dict[str, Any],
    ) -> int:
        """Insert brand_search_terms. brand_id is resolved via alias map."""
        inserted = 0
        skipped_dup = 0
        dropped: list[dict[str, Any]] = []
        for r in rows:
            source_brand = r.get("brand_id", "").strip()
            target_brand = resolver.resolve_brand(source_brand)
            if target_brand is None:
                dropped.append({"row": r, "reason": "sentinel-without-target-equivalent"})
                continue
            brand_id_int = self._brand_id(target_brand)
            if brand_id_int is None:
                dropped.append({"row": r, "reason": f"target brand {target_brand!r} not in brands"})
                continue
            term = r.get("term", "").strip()
            if not term:
                continue
            if not self.write:
                inserted += 1
                continue
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO brand_search_terms (brand_id, term, added_at)
                VALUES (?, ?, ?)
                """,
                (brand_id_int, term, _coerce_timestamptz(r.get("added_at", "")) or None),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped_dup += 1
        report["brand_search_terms"] = {
            "table": "brand_search_terms",
            "source_rows": len(rows),
            "inserted": inserted,
            "skipped_duplicate": skipped_dup,
            "dropped_no_alias": len(dropped),
            "dropped_samples": dropped[:5],
        }
        return inserted

    def upsert_brands_accounts(
        self,
        rows: list[dict[str, Any]],
        resolver: AliasResolver,
        report: dict[str, Any],
    ) -> int:
        """Insert brands_accounts. Resolves 3 FKs via the alias map."""
        inserted = 0
        skipped_dup = 0
        dropped: list[dict[str, Any]] = []
        for r in rows:
            source_brand = r.get("brand_id", "").strip()
            target_brand = resolver.resolve_brand(source_brand)
            if target_brand is None:
                dropped.append({"row": r, "reason": "sentinel-source"})
                continue
            brand_id_int = self._brand_id(target_brand)
            if brand_id_int is None:
                dropped.append({"row": r, "reason": f"brand {target_brand!r} not seeded"})
                continue
            author_id = r.get("author_id", "").strip()
            account_id_int = self._account_id(author_id)
            if account_id_int is None:
                dropped.append({"row": r, "reason": f"account {author_id!r} not seeded"})
                continue
            role_key = r.get("role_key", "").strip()
            target_role = resolver.resolve_role(role_key)
            role_id_int = self._role_id(target_role)
            if role_id_int is None:
                dropped.append({"row": r, "reason": f"role {target_role!r} not seeded"})
                continue
            if not self.write:
                inserted += 1
                continue
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO brands_accounts (brand_id, accounts_id, role_id, added_at)
                VALUES (?, ?, ?, ?)
                """,
                (brand_id_int, account_id_int, role_id_int,
                 _coerce_timestamptz(r.get("added_at", "")) or None),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped_dup += 1
        report["brands_accounts"] = {
            "table": "brands_accounts",
            "source_rows": len(rows),
            "inserted": inserted,
            "skipped_duplicate": skipped_dup,
            "dropped_no_alias": len(dropped),
            "dropped_samples": dropped[:5],
        }
        return inserted

    def upsert_brands_companies(
        self,
        rows: list[dict[str, Any]],
        resolver: AliasResolver,
        report: dict[str, Any],
    ) -> int:
        """Insert brands_companies. Resolves 2 FKs via the alias map."""
        inserted = 0
        skipped_dup = 0
        dropped: list[dict[str, Any]] = []
        for r in rows:
            source_brand = r.get("brand_id", "").strip()
            target_brand = resolver.resolve_brand(source_brand)
            if target_brand is None:
                dropped.append({"row": r, "reason": "sentinel-source"})
                continue
            brand_id_int = self._brand_id(target_brand)
            if brand_id_int is None:
                dropped.append({"row": r, "reason": f"brand {target_brand!r} not seeded"})
                continue
            source_company = r.get("company_id", "").strip()
            target_company = resolver.resolve_company(source_company)
            if target_company is None:
                dropped.append({"row": r, "reason": f"company {source_company!r} not resolved"})
                continue
            company_id_int = self._company_id(target_company)
            if company_id_int is None:
                dropped.append({"row": r, "reason": f"company {target_company!r} not seeded"})
                continue
            ownership_pct = r.get("ownership_pct", "")
            try:
                ownership_pct_f = float(ownership_pct) if ownership_pct else None
            except ValueError:
                ownership_pct_f = None
            if not self.write:
                inserted += 1
                continue
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO brands_companies (brand_id, company_id, ownership_pct)
                VALUES (?, ?, ?)
                """,
                (brand_id_int, company_id_int, ownership_pct_f),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped_dup += 1
        report["brands_companies"] = {
            "table": "brands_companies",
            "source_rows": len(rows),
            "inserted": inserted,
            "skipped_duplicate": skipped_dup,
            "dropped_no_alias": len(dropped),
            "dropped_samples": dropped[:5],
        }
        return inserted

    def upsert_hf_orgs(
        self,
        rows: list[dict[str, Any]],
        resolver: AliasResolver,
        report: dict[str, Any],
    ) -> int:
        """Insert hf_orgs. company_id resolved via alias map."""
        inserted = 0
        skipped_dup = 0
        dropped: list[dict[str, Any]] = []
        for r in rows:
            source_company = r.get("company_id", "").strip()
            target_company = resolver.resolve_company(source_company)
            if target_company is None:
                dropped.append({"row": r, "reason": f"company {source_company!r} not resolved"})
                continue
            company_id_int = self._company_id(target_company)
            if company_id_int is None:
                dropped.append({"row": r, "reason": f"company {target_company!r} not seeded"})
                continue
            namespace = r.get("namespace", "").strip()
            if not namespace:
                continue
            confirmed = _coerce_bool(r.get("confirmed", "f"))
            discovered_via = r.get("discovered_via", "curated").strip() or "curated"
            added_at = _coerce_timestamptz(r.get("added_at", "")) or None
            if not self.write:
                inserted += 1
                continue
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO hf_orgs (namespace, company_id, confirmed, discovered_via, added_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (namespace, company_id_int, confirmed, discovered_via, added_at),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped_dup += 1
        report["hf_orgs"] = {
            "table": "hf_orgs",
            "source_rows": len(rows),
            "inserted": inserted,
            "skipped_duplicate": skipped_dup,
            "dropped_no_alias": len(dropped),
            "dropped_samples": dropped[:5],
        }
        return inserted

    def upsert_lookup_keys(
        self,
        rows: list[dict[str, Any]],
        target_table: str,
        resolver: AliasResolver,
        resolve_fn,
        report: dict[str, Any],
        label: str,
    ) -> int:
        """Insert lookup-table keys (discourse, post_types, nationalism, roles)."""
        inserted = 0
        skipped_dup = 0
        dropped: list[dict[str, Any]] = []
        renamed: list[dict[str, Any]] = []
        for r in rows:
            source_key = r.get("key", "").strip()
            target_key = resolve_fn(source_key)
            if target_key is None:
                dropped.append({"row": r, "reason": f"{label} not resolved"})
                continue
            if target_key != source_key:
                renamed.append({"from": source_key, "to": target_key})
            if self._lookup_key_id(target_table, target_key) is not None:
                skipped_dup += 1
                continue
            if not self.write:
                inserted += 1
                continue
            self._conn.execute(
                f'INSERT OR IGNORE INTO "{target_table}" (key, created_at) VALUES (?, ?)',
                (target_key, _coerce_timestamptz(r.get("created_at", "")) or None),
            )
            inserted += 1
        report[target_table] = {
            "table": target_table,
            "source_rows": len(rows),
            "inserted": inserted,
            "skipped_duplicate": skipped_dup,
            "renamed": renamed,
            "dropped_no_alias": len(dropped),
        }
        return inserted

    def upsert_lookup_labels(
        self,
        rows: list[dict[str, Any]],
        target_table: str,
        label_key_col: str,
        resolver: AliasResolver,
        resolve_fn,
        report: dict[str, Any],
        label: str,
    ) -> int:
        """Insert lookup-table labels (discourse_labels, post_type_labels, ...).
        Source uses 'locale' column; target uses 'lang'. Source key column
        (e.g. 'discourse_key') is renamed to 'key' for target."""
        inserted = 0
        skipped_dup = 0
        dropped: list[dict[str, Any]] = []
        for r in rows:
            source_key = r.get(label_key_col, "").strip()
            target_key = resolve_fn(source_key)
            if target_key is None:
                dropped.append({"row": r, "reason": f"{label} parent not resolved"})
                continue
            lang = r.get("locale", "").strip() or r.get("lang", "").strip()
            label_text = r.get("label", "").strip()
            if not lang or not label_text:
                continue
            if not self.write:
                inserted += 1
                continue
            cur = self._conn.execute(
                f'INSERT OR IGNORE INTO "{target_table}" (key, lang, label) VALUES (?, ?, ?)',
                (target_key, lang, label_text),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped_dup += 1
        # Report key: if target_table ends in '_labels', don't double-suffix.
        report_key = target_table if target_table.endswith("_labels") else target_table + "_labels"
        report[report_key] = {
            "table": report_key,
            "source_rows": len(rows),
            "inserted": inserted,
            "skipped_duplicate": skipped_dup,
            "dropped_no_alias": len(dropped),
            "dropped_samples": dropped[:5],
        }
        return inserted


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate pushin_weight curated seed → x_monitoring.db"
    )
    parser.add_argument(
        "--target-db", type=Path, required=True,
        help="Path to x_monitoring.db (target)",
    )
    parser.add_argument(
        "--alias-map", type=Path, required=True,
        help="Path to the alias YAML",
    )
    parser.add_argument(
        "--source-connstr", default=None,
        help='psql connstr (e.g. "host=localhost port=5432 dbname=pushin_weight")',
    )
    parser.add_argument(
        "--fixture", type=Path, default=None,
        help="Path to a SQLite fixture file (overrides --source-connstr)",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Apply changes (default is dry-run)",
    )
    parser.add_argument(
        "--report-out", type=Path, default=None,
        help="Override the JSON report output path",
    )
    args = parser.parse_args(argv)

    if not args.source_connstr and not args.fixture:
        print(
            "error: either --source-connstr or --fixture is required",
            file=sys.stderr,
        )
        return 2
    if args.source_connstr and args.fixture:
        print(
            "error: --source-connstr and --fixture are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    if not args.alias_map.exists():
        print(f"error: alias map not found: {args.alias_map}", file=sys.stderr)
        return 2
    if not args.target_db.exists():
        print(f"error: target DB not found: {args.target_db}", file=sys.stderr)
        return 2

    with open(args.alias_map, encoding="utf-8") as f:
        alias_data = yaml.safe_load(f)
    resolver = AliasResolver(alias_data)

    def read(table: str, columns: list[str]) -> list[dict[str, Any]]:
        if args.fixture:
            return _read_source_table_sqlite(args.fixture, table, columns)
        return _read_source_table_psql(args.source_connstr, table, columns)

    target = TargetWriter(args.target_db, write=args.write)
    report: dict[str, Any] = {
        "mode": "write" if args.write else "dry-run",
        "target_db": str(args.target_db),
        "source": (
            f"fixture:{args.fixture}" if args.fixture
            else f"postgres:{args.source_connstr}"
        ),
        "alias_map": str(args.alias_map),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # --- 1. Lookup tables (keys + labels) -----------------------------
        for lt in LOOKUP_TABLES:
            if lt["target"] == "discourse_keys":
                resolve_fn = resolver.resolve_discourse
            elif lt["target"] == "post_type_keys":
                resolve_fn = resolver.resolve_post_type
            else:  # nationalism_keys, roles
                resolve_fn = lambda k: k  # noqa: E731 — 1:1
            rows = read(lt["source"], [lt["key_col"], "created_at"])
            target.upsert_lookup_keys(
                rows, lt["target"], resolver, resolve_fn, report, lt["source"]
            )
            label_rows = read(
                lt["label_source"], [lt["label_key_col"], "locale", "label"]
            )
            target.upsert_lookup_labels(
                label_rows, lt["label_target"], lt["label_key_col"],
                resolver, resolve_fn, report, lt["label_source"],
            )

        # --- 2. Accounts (parent of brands_accounts) -----------------------
        account_rows = read(
            "accounts",
            [
                "author_id", "handle", "display_name", "bio", "bio_fetched_at",
                "verified", "bio_contains_brand", "first_seen_at", "last_seen_at",
                "source_query_ids",
            ],
        )
        target.upsert_accounts(account_rows, report)

        # --- 3. Edge tables ------------------------------------------------
        brand_search_rows = read(
            "brand_search_terms", ["brand_id", "term", "added_at"]
        )
        target.upsert_brand_search_terms(brand_search_rows, resolver, report)

        brands_accounts_rows = read(
            "brands_accounts", ["brand_id", "author_id", "role_key", "added_at"]
        )
        target.upsert_brands_accounts(brands_accounts_rows, resolver, report)

        brands_companies_rows = read(
            "brands_companies", ["brand_id", "company_id", "ownership_pct"]
        )
        target.upsert_brands_companies(brands_companies_rows, resolver, report)

        hf_orgs_rows = read(
            "hf_orgs", ["namespace", "confirmed", "discovered_via", "added_at", "company_id"]
        )
        target.upsert_hf_orgs(hf_orgs_rows, resolver, report)

        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["target_row_counts"] = {
            t: target._target_count(t)
            for t in [
                "discourse_keys", "post_type_keys", "nationalism_keys", "roles",
                "accounts", "brands_accounts", "brands_companies", "hf_orgs",
                "brand_search_terms",
            ]
        }
    finally:
        target.close()

    # --- 4. Emit report --------------------------------------------------
    json_text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    print(json_text)

    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(json_text, encoding="utf-8")
    else:
        # Default: data/migration_logs/migrate-pushin-weight-records-<ts>.json
        log_dir = Path("data/migration_logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = log_dir / f"migrate-pushin-weight-records-{ts}.json"
        out.write_text(json_text, encoding="utf-8")
        print(f"\nreport written: {out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
