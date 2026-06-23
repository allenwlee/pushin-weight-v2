# {{AGENT_ATTRIBUTION}}
"""Migration 009 tests: products + hf_orgs tables (company-centric redesign).

Migration 009 adds two additive tables (no existing data touched):
  - hf_orgs  : 1:N edge companies → HF orgs; curated seed (confirmed=1).
               Replaces the prior `brand_hf_orgs` M:N design (the brand was
               operator-curated and could span HF namespaces; HF orgs are
               owned by the corporate parent company).
  - products : one row per HF model; brands 1:N products AND
               companies 1:N products (via hf_orgs.hf_org_id); wide scalar
               columns + JSON columns + raw_json. hf_type is CHECK-
               constrained to ('model','dataset','space') with default 'model'.

These tests verify:
  - 009 applies on a fresh DB (Store auto-migrates 001→009) and both tables
    exist with the expected columns; version 9 is in the ledger.
  - brand_hf_orgs is GONE (the prior design's table does not exist after 009).
  - the curated company→HF-org seed is present (11 rows, all confirmed).
  - re-opening is idempotent (no duplicate seed rows, ledger version 9 once).
  - hf_type CHECK rejects an invalid kind; default is 'model'.
  - products.brand_id FK rejects an unknown brand; ON DELETE SET NULL clears it.
  - products.hf_org_id FK rejects an unknown hf_org; ON DELETE SET NULL clears it.
  - 009 does not disturb migration 004's 12-brand seed.
  - 009 adds the missing `minimax` company + brand_companies edge.
"""

from __future__ import annotations

import sqlite3

import pytest


# --- migration 009: tables + seed --------------------------------------


def test_migration_009_creates_tables_and_columns(tmp_path):
    """Both tables exist with key columns; ledger records version 9."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        product_cols = {
            r[1] for r in s._conn.execute("PRAGMA table_info(products)").fetchall()
        }
        for required in {
            "repo_id", "brand_id", "hf_org_id", "hf_type", "display_name", "author",
            "sha", "private", "gated", "disabled", "pipeline_tag", "library_name",
            "downloads", "downloads_all_time", "download_velocity", "likes",
            "trending_score", "paperswithcode_id", "created_at", "last_modified",
            "tags_json", "siblings_json", "card_data_json", "config_json",
            "spaces_json", "raw_json", "collected_at", "updated_at",
        }:
            assert required in product_cols, f"products missing column: {required}"

        org_cols = {
            r[1] for r in s._conn.execute("PRAGMA table_info(hf_orgs)").fetchall()
        }
        for required in {"id", "company_id", "confirmed", "discovered_via", "added_at"}:
            assert required in org_cols, f"hf_orgs missing column: {required}"

        # Prior design must be gone.
        tables = {
            r[0]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "brand_hf_orgs" not in tables, "brand_hf_orgs should be dropped"

        applied = {
            r[0] for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        }
        assert 9 in applied
    finally:
        s.close()


def test_migration_009_seeds_curated_orgs(tmp_path):
    """11 curated company→HF-org rows, all confirmed=1."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT id, company_id, confirmed, discovered_via "
            "FROM hf_orgs ORDER BY id"
        ).fetchall()
        assert len(rows) == 11, f"expected 11 seed rows, got {len(rows)}"
        for r in rows:
            assert r["confirmed"] == 1
            assert r["discovered_via"] == "curated"
        # Spot-check a known mapping.
        by_id = {r["id"]: r["company_id"] for r in rows}
        assert by_id["deepseek-ai"] == "deepseek_co"
        assert by_id["THUDM"] == "zhipu"
        assert by_id["MiniMaxAI"] == "minimax"
    finally:
        s.close()


def test_migration_009_seeds_minimax_company(tmp_path):
    """Migration 009 also adds the missing `minimax` company + brand_companies edge."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        row = s._conn.execute(
            "SELECT * FROM companies WHERE company_id = 'minimax'"
        ).fetchone()
        assert row is not None
        assert row["display_name"] == "MiniMax"
        edge = s._conn.execute(
            "SELECT * FROM brand_companies WHERE brand_id = 'minimax' AND company_id = 'minimax'"
        ).fetchone()
        assert edge is not None
        assert edge["ownership_pct"] == 1.0
    finally:
        s.close()


def test_migration_009_idempotent(tmp_path):
    """Re-opening a DB with 009 applied does not duplicate the seed."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    s1.close()
    s2 = Store(db, auto_migrate=True)
    try:
        applied = [
            r[0] for r in s2._conn.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        ]
        assert applied.count(9) == 1
        n = s2._conn.execute("SELECT COUNT(*) FROM hf_orgs").fetchone()[0]
        assert n == 11
    finally:
        s2.close()


# --- products: hf_type CHECK constraint --------------------------------


def test_products_hf_type_defaults_to_model(tmp_path):
    """Omitting hf_type stores the 'model' default."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        # 'deepseek-ai' is already seeded by migration 009 (curated).
        s._conn.execute(
            "INSERT INTO products (repo_id, brand_id, hf_org_id, collected_at, updated_at) "
            "VALUES (?, NULL, ?, ?, ?)",
            ("deepseek-ai/DeepSeek-V3", "deepseek-ai", "t", "t"),
        )
        row = s._conn.execute(
            "SELECT hf_type FROM products WHERE repo_id = 'deepseek-ai/DeepSeek-V3'"
        ).fetchone()
        assert row["hf_type"] == "model"
    finally:
        s.close()


def test_products_hf_type_accepts_valid_kinds(tmp_path):
    """All three allowed kinds insert cleanly."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        # Seed three distinct hf_orgs for the FK.
        for org in ("org-m", "org-d", "org-s"):
            s._conn.execute(
                "INSERT INTO hf_orgs (id, company_id, confirmed, discovered_via, added_at) "
                "VALUES (?, ?, 1, 'curated', '2026-06-22T00:00:00+00:00')",
                (org, "alibaba"),  # re-use one company_id; hf_org PK is the namespace
            )
        for kind, org in (("model", "org-m"), ("dataset", "org-d"), ("space", "org-s")):
            s._conn.execute(
                "INSERT INTO products (repo_id, brand_id, hf_org_id, hf_type, "
                "collected_at, updated_at) VALUES (?, NULL, ?, ?, ?, ?)",
                (f"{org}/{kind}", org, kind, "t", "t"),
            )
    finally:
        s.close()


def test_products_hf_type_rejects_invalid(tmp_path):
    """An hf_type outside the allowed set is rejected by the CHECK constraint."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            s._conn.execute(
                "INSERT INTO products (repo_id, brand_id, hf_org_id, hf_type, "
                "collected_at, updated_at) VALUES (?, NULL, ?, ?, ?, ?)",
                ("org/bogus", "org", "bogus", "t", "t"),
            )
    finally:
        s.close()


# --- products: brand_id FK behavior ------------------------------------


def test_products_brand_fk_rejects_unknown_brand(tmp_path):
    """A brand_id not in brands is rejected (PRAGMA foreign_keys=ON)."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            s._conn.execute(
                "INSERT INTO products (repo_id, brand_id, hf_org_id, collected_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("x/y", "no_such_brand", "x", "t", "t"),
            )
    finally:
        s.close()


def test_products_brand_fk_on_delete_set_null(tmp_path):
    """Deleting a brand NULLs its products.brand_id (ON DELETE SET NULL)."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        # 'deepseek-ai' is already seeded by migration 009 (curated).
        s._conn.execute(
            "INSERT INTO products (repo_id, brand_id, hf_org_id, collected_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("deepseek-ai/DeepSeek-V3", "deepseek", "deepseek-ai", "t", "t"),
        )
        s._conn.execute("DELETE FROM brands WHERE brand_id = 'deepseek'")
        row = s._conn.execute(
            "SELECT brand_id FROM products WHERE repo_id = 'deepseek-ai/DeepSeek-V3'"
        ).fetchone()
        assert row["brand_id"] is None
    finally:
        s.close()


# --- products: hf_org_id FK behavior -----------------------------------


def test_products_hf_org_fk_rejects_unknown_org(tmp_path):
    """A hf_org_id not in hf_orgs is rejected."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            s._conn.execute(
                "INSERT INTO products (repo_id, brand_id, hf_org_id, collected_at, updated_at) "
                "VALUES (?, NULL, ?, ?, ?)",
                ("x/y", "no_such_org", "t", "t"),
            )
    finally:
        s.close()


def test_products_hf_org_fk_on_delete_set_null(tmp_path):
    """Deleting an hf_org NULLs its products.hf_org_id (ON DELETE SET NULL)."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO hf_orgs (id, company_id, confirmed, discovered_via, added_at) "
            "VALUES (?, ?, 1, 'curated', '2026-06-22T00:00:00+00:00')",
            ("test-org", "alibaba"),
        )
        s._conn.execute(
            "INSERT INTO products (repo_id, brand_id, hf_org_id, collected_at, updated_at) "
            "VALUES (?, NULL, ?, ?, ?)",
            ("test-org/repo", "test-org", "t", "t"),
        )
        s._conn.execute("DELETE FROM hf_orgs WHERE id = 'test-org'")
        row = s._conn.execute(
            "SELECT hf_org_id FROM products WHERE repo_id = 'test-org/repo'"
        ).fetchone()
        assert row["hf_org_id"] is None
    finally:
        s.close()


# --- migration 009 does not disturb 004 --------------------------------


def test_migration_009_preserves_brands_seed(tmp_path):
    """009 is additive: read_brands() still returns the 12 seeded brands."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        brands = s.read_brands()
        assert len(brands) == 12
    finally:
        s.close()


def test_migration_009_company_count(tmp_path):
    """009 adds the minimax company (the 11th); 004's seed had 10."""
    from x_monitor.store import Store

    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        companies = s.read_companies()
        assert len(companies) == 11
        ids = {c.company_id for c in companies}
        assert "minimax" in ids
    finally:
        s.close()
