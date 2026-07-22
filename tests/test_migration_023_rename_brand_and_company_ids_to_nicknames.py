"""Migration 023: rename parent-table slug columns to nickname.

Plan: docs/plans/2026-06-26-001-refactor-brand-id-to-nickname-plan.md

This migration is **parent-only**. Child-table FK columns are NOT renamed
because they already reference the INTEGER surrogate PKs
(`brands.id` / `companies.id`), not the slug columns. After this
migration:

  brands.brand_id        → brands.nickname      (slug, TEXT)
  brands.id              → brands.id            (INTEGER PK, unchanged)
  companies.company_id   → companies.nickname   (slug, TEXT)
  companies.id           → companies.id         (INTEGER PK, unchanged)
  child.brand_id         → child.brand_id       (FK → brands.id, unchanged)
  child.company_id       → child.company_id     (FK → companies.id, unchanged)

The Store API aliases `b.nickname AS brand_id` in SELECTs from brands
so consumers reading `row["brand_id"]` continue to receive the slug
string without any consumer-side changes.

Verifies:
- Parent-table slug columns renamed with correct type/constraints.
- Parent-table slug indexes recreated on the new column names.
- Child-table brand_id / company_id columns are NOT renamed.
- Idempotency: re-opening the DB does not re-run 023.
- Full stack apply: all on-disk migrations including 023 apply cleanly.
- FK preservation: child FK columns still resolve to brands.id /
  companies.id after migration.
- Round-trip via direct SQL: insert + select through the new parent
  column names returns the same data.
"""

import pytest


def _columns(conn, table: str) -> set[str]:
    return {
        r["name"]
        for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _index_names(conn) -> set[str]:
    return {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }


# --- happy path: parent tables -------------------------------------


def test_migration_023_brands_brand_id_renamed_to_nickname(tmp_path):
    """brands.brand_id is gone; brands.nickname exists with same type."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = _columns(s._conn, "brands")
        assert "brand_id" not in cols, (
            f"brands.brand_id still present after 023: {cols}"
        )
        assert "nickname" in cols, (
            f"brands.nickname missing after 023: {cols}"
        )

        col = s._conn.execute(
            "SELECT type, [notnull] AS nn, [pk] AS pk "
            "FROM pragma_table_info('brands') WHERE name='nickname'"
        ).fetchone()
        assert col is not None
        # Post-020: TEXT UNIQUE NOT NULL slug on top of INTEGER PK.
        assert "TEXT" in col["type"].upper(), (
            f"brands.nickname type={col['type']}, expected TEXT"
        )
        assert col["nn"] == 1, f"brands.nickname is nullable: {col}"
        assert col["pk"] == 0, (
            f"brands.nickname is the PK (got pk={col['pk']}); "
            f"brands.id should be the PK"
        )

        # Verify the INTEGER PK is still on brands.id, not on nickname.
        pk_col = s._conn.execute(
            "SELECT type FROM pragma_table_info('brands') WHERE pk = 1"
        ).fetchone()
        assert pk_col is not None
        assert "INTEGER" in pk_col["type"].upper(), (
            f"brands PK column is not INTEGER: {pk_col['type']}"
        )
    finally:
        s.close()


def test_migration_023_companies_company_id_renamed_to_nickname(tmp_path):
    """companies.company_id is gone; companies.nickname exists with same type."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = _columns(s._conn, "companies")
        assert "company_id" not in cols, (
            f"companies.company_id still present after 023: {cols}"
        )
        assert "nickname" in cols, (
            f"companies.nickname missing after 023: {cols}"
        )

        col = s._conn.execute(
            "SELECT type, [notnull] AS nn, [pk] AS pk "
            "FROM pragma_table_info('companies') WHERE name='nickname'"
        ).fetchone()
        assert col is not None
        assert "TEXT" in col["type"].upper(), (
            f"companies.nickname type={col['type']}, expected TEXT"
        )
        assert col["nn"] == 1, f"companies.nickname is nullable: {col}"
        assert col["pk"] == 0, (
            f"companies.nickname is the PK (got pk={col['pk']}); "
            f"companies.id should be the PK"
        )
    finally:
        s.close()


# --- happy path: child-table FK columns UNCHANGED ------------------


@pytest.mark.parametrize(
    "table",
    [
        "brands_companies",
        "brands_accounts",
        "posts_brands",
        "posts_brands_signals",
        "posts_brands_mentions",
        "search_queries",
    ],
)
def test_migration_023_child_table_brand_id_unchanged(tmp_path, table):
    """Child-table brand_id FK column is NOT renamed (still points to brands.id)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = _columns(s._conn, table)
        assert "brand_id" in cols, (
            f"{table}.brand_id missing after 023 (should be unchanged): {cols}"
        )
        # And there's no spurious brand_nickname column added.
        assert "brand_nickname" not in cols, (
            f"{table}.brand_nickname should not exist after 023: {cols}"
        )
    finally:
        s.close()


@pytest.mark.parametrize(
    "table",
    [
        "brands_companies",
        "companies_accounts",
        "hf_orgs",
    ],
)
def test_migration_023_child_table_company_id_unchanged(tmp_path, table):
    """Child-table company_id FK column is NOT renamed."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = _columns(s._conn, table)
        assert "company_id" in cols, (
            f"{table}.company_id missing after 023 (should be unchanged): {cols}"
        )
        assert "company_nickname" not in cols, (
            f"{table}.company_nickname should not exist after 023: {cols}"
        )
    finally:
        s.close()


# --- happy path: child FKs still resolve to parent ids -------------


def test_migration_023_child_fks_still_target_parent_ids(tmp_path):
    """After 023, child FK columns still reference brands.id / companies.id."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        for table, fk_col, parent in (
            ("brands_companies",   "brand_id",   "brands"),
            ("brands_accounts",    "brand_id",   "brands"),
            ("posts_brands",       "brand_id",   "brands"),
            ("posts_brands_signals","brand_id",  "brands"),
            ("posts_brands_mentions","brand_id", "brands"),
            ("search_queries",     "brand_id",   "brands"),
            ("brands_companies",   "company_id", "companies"),
            ("companies_accounts", "company_id", "companies"),
            ("hf_orgs",            "company_id", "companies"),
        ):
            fks = list(
                s._conn.execute(
                    f"SELECT * FROM pragma_foreign_key_list('{table}')"
                ).fetchall()
            )
            match = [
                (f["from"], f["table"], f["to"])
                for f in fks
                if f["from"] == fk_col
            ]
            assert (fk_col, parent, "id") in match, (
                f"{table}.{fk_col} FK target changed after 023: {match}"
            )
    finally:
        s.close()


# --- happy path: indexes rebuilt ------------------------------------


def test_migration_023_parent_indexes_rebuilt(tmp_path):
    """idx_brands_nickname and idx_companies_nickname exist after 023."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        names = _index_names(s._conn)
        assert "idx_brands_nickname" in names, (
            f"idx_brands_nickname missing after 023; have {sorted(names)}"
        )
        assert "idx_companies_nickname" in names, (
            f"idx_companies_nickname missing after 023; have {sorted(names)}"
        )
    finally:
        s.close()


def test_migration_023_old_parent_index_names_gone(tmp_path):
    """The pre-023 parent-slug index names are gone."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        names = _index_names(s._conn)
        assert "idx_brands_brand_id" not in names, (
            "idx_brands_brand_id still present after 023"
        )
        assert "idx_companies_company_id" not in names, (
            "idx_companies_company_id still present after 023"
        )
    finally:
        s.close()


def test_migration_023_child_indexes_unchanged(tmp_path):
    """Child-table indexes on brand_id / company_id are NOT touched."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        names = _index_names(s._conn)
        # Indexes on child FK columns should be unchanged.
        for idx in (
            "idx_posts_brands_brand_id",
            "idx_posts_brands_signals_brand_id_post_type",
            "idx_posts_brands_signals_brand_id_sentiment",
            "idx_hf_orgs_company",
            "idx_search_queries_brand_id",
        ):
            assert idx in names, (
                f"{idx} missing after 023 (child indexes should be unchanged)"
            )
    finally:
        s.close()


# --- happy path: data round-trip via direct SQL --------------------


def test_migration_023_brand_data_round_trip(tmp_path):
    """A brand inserted through the new column name is read back identically."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        slug = "u9_023_test_brand"
        s._conn.execute(
            "INSERT INTO brands (nickname, display_name) VALUES (?, ?)",
            (slug, "U9 023 Test Brand"),
        )
        s._conn.commit()
        row = s._conn.execute(
            "SELECT nickname, display_name FROM brands WHERE nickname = ?",
            (slug,),
        ).fetchone()
        assert row is not None, f"brand {slug} not found after insert"
        assert row["nickname"] == slug
        assert row["display_name"] == "U9 023 Test Brand"
    finally:
        s.close()


def test_migration_023_alias_back_via_sql(tmp_path):
    """`SELECT b.nickname AS brand_id FROM brands b` returns the slug as brand_id."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        slug = "u9_023_alias_test"
        s._conn.execute(
            "INSERT INTO brands (nickname, display_name) VALUES (?, ?)",
            (slug, "Alias Test"),
        )
        s._conn.commit()
        row = s._conn.execute(
            "SELECT b.nickname AS brand_id FROM brands b WHERE b.nickname = ?",
            (slug,),
        ).fetchone()
        assert row is not None
        # Alias back gives callers `row["brand_id"]` even though the
        # underlying column is `nickname`.
        assert row["brand_id"] == slug
    finally:
        s.close()


# --- FK preservation ------------------------------------------------


def test_migration_023_fk_enforcement_on(tmp_path):
    """FKs are re-enabled after migration."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fk_state = s._conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk_state == 1, f"foreign_keys off after migration: {fk_state}"
    finally:
        s.close()


# --- idempotency / full-stack apply --------------------------------


def test_migration_023_idempotent(tmp_path):
    """Re-opening the DB with 023 applied does not re-run it."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied_1 = {
            r["version"]
            for r in s._conn.execute(
                "SELECT version FROM _migrations"
            ).fetchall()
        }
    finally:
        s.close()

    s = Store(db, auto_migrate=True)
    try:
        applied_2 = {
            r["version"]
            for r in s._conn.execute(
                "SELECT version FROM _migrations"
            ).fetchall()
        }
    finally:
        s.close()

    assert applied_1 == applied_2
    assert 23 in applied_2


def test_migration_023_full_stack_apply(tmp_path):
    """All on-disk migrations (including 023) apply cleanly on a fresh DB."""
    from pathlib import Path

    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = {
            r["version"]
            for r in s._conn.execute(
                "SELECT version FROM _migrations"
            ).fetchall()
        }
        mig_dir = Path(__file__).resolve().parent.parent / "x_monitor" / "migrations"
        expected = {
            int(f.name.split("_", 1)[0])
            for f in mig_dir.glob("*.sql")
        }
        assert applied >= expected, (
            f"missing migrations: applied={sorted(applied)}, "
            f"expected={sorted(expected)}"
        )
        assert 23 in applied, "migration 023 not applied"
    finally:
        s.close()


def test_migration_023_slug_values_preserved(tmp_path):
    """The slug VALUES are unchanged after the rename (only column name)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT nickname FROM brands ORDER BY nickname"
        ).fetchall()
        slugs = [r["nickname"] for r in rows]
        for slug in slugs:
            assert isinstance(slug, str)
            assert slug, "empty slug after rename"
            assert "_nick" not in slug, (
                f"slug appears transformed: {slug!r}"
            )
    finally:
        s.close()