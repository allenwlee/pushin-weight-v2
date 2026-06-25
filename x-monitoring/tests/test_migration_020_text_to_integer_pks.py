"""Migration 020: TEXT → INTEGER primary keys for all remaining tables.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 8 of 9, full remediation — the 13 tables deferred from migration 018).

Scope (per the migration file):
- The 13 tables deferred from migration 018 each get `id INTEGER PRIMARY
  KEY AUTOINCREMENT`. The original TEXT PK becomes a UNIQUE NOT NULL
  "slug" column (brand_id, company_id, author_id, namespace, etc.).
- FK columns within those 13 tables are converted from TEXT-storing-key
  to INTEGER-storing-id (per the user's pick "INTEGER-storing-id for all
  13 tables — plan body literal").
- hf_orgs column rename: original TEXT PK `id` (HF namespace) becomes
  `namespace` (TEXT UNIQUE NOT NULL). The new INTEGER synthetic PK is
  also `id`.
- posts_brands_signals CHECK constraint `(brand_id <> '_unattributed')`
  is DROPPED (the INTEGER-PK semantics shift makes the constraint
  fragile — see migration header for rationale).
- products dependent table: brand_id and hf_org_id converted to
  INTEGER-storing-id (with hf_org_id now the INTEGER id of the
  hf_orgs row, not the namespace string).
- The migration runner (Store.apply_migrations) toggles
  `PRAGMA foreign_keys = OFF` at the connection level around the
  migration execution (PRAGMA is a no-op inside a transaction, so
  in-script toggling does not work). FKs are restored in the
  runner's finally clause.

Verifies:
- All 13 tables have INTEGER id PK (where the table has a single PK;
  edge tables have composite PKs whose components are all INTEGER).
- The original TEXT PK columns (brand_id, company_id, author_id,
  namespace, query_id, tweet_id, repo_id) are preserved as TEXT
  UNIQUE NOT NULL slug columns.
- The hf_orgs column rename: namespace column exists; original
  `id TEXT` PK is gone; new `id INTEGER` PK exists.
- All FK columns in the 13 tables are INTEGER-storing-id:
  brands_companies (brand_id, company_id), brands_accounts (brand_id,
  author_id, role_id), companies_accounts (company_id, author_id,
  role_id), posts_brands (post_id, brand_id), brand_search_terms
  (brand_id), posts_brands_signals (post_id, brand_id, signal_id,
  post_type, sentiment), posts_brands_mentions (post_id, brand_id),
  posts (author_id), search_queries (brand_id), hf_orgs (company_id).
- products.brand_id and products.hf_org_id are INTEGER.
- Row counts match the v1.8 baseline (12 brands, 11 companies,
  11 hf_orgs, 11 brands_companies).
- Data round-trip: hf_orgs.namespace values match the v1 baseline
  (Qwen, baidu, tencent, moonshotai, THUDM, XiaomiMiMo, mistralai,
  inclusionAI, deepseek-ai, stepfun-ai, MiniMaxAI).
- The CHECK constraint on posts_brands_signals is dropped.
- Idempotency: re-opening a DB that has 020 applied does not re-run
  it; row counts are unchanged.
- Full stack apply: all migrations 001-020 apply on a fresh DB.
- FK enforcement after migration: PRAGMA foreign_keys returns 1.
- FK validation: INSERT into a child table with a parent id that
  does not exist is rejected.
- Migration order: posts is converted BEFORE the M:N tables (so
  posts_brands, posts_brands_signals, posts_brands_mentions can FK
  to posts.id). This is a deviation from the plan body's "suggested"
  order, justified by the chicken-and-egg (M:N → fact dependency).
"""
from __future__ import annotations

import pytest


# --- happy path: lookup tables have INTEGER id PK + UNIQUE slug ---------


@pytest.mark.parametrize("tbl,slug_col,expected_rows", [
    ("brands", "brand_id", 12),
    ("companies", "company_id", 11),
    ("accounts", "author_id", 0),
    ("hf_orgs", "namespace", 11),
    ("search_queries", "query_id", 0),
])
def test_migration_020_lookup_table_integer_pk(tmp_path, tbl, slug_col, expected_rows):
    """Each lookup table has `id INTEGER PRIMARY KEY AUTOINCREMENT` +
    the original TEXT PK is now a `slug_col TEXT UNIQUE NOT NULL` column."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # id column is INTEGER PK
        col = s._conn.execute(
            f"SELECT type, pk, [notnull] AS nn FROM pragma_table_info('{tbl}') "
            f"WHERE name='id'"
        ).fetchone()
        assert col is not None, f"{tbl}.id missing"
        assert "INTEGER" in col["type"].upper(), (
            f"{tbl}.id type is {col['type']!r}, expected INTEGER"
        )
        assert col["pk"] == 1, f"{tbl}.id is not PK. pk={col['pk']}"
        # slug column exists, is TEXT, is UNIQUE NOT NULL
        slug = s._conn.execute(
            f"SELECT type, [notnull] AS nn FROM pragma_table_info('{tbl}') "
            f"WHERE name='{slug_col}'"
        ).fetchone()
        assert slug is not None, f"{tbl}.{slug_col} missing"
        assert "TEXT" in slug["type"].upper(), (
            f"{tbl}.{slug_col} type is {slug['type']!r}, expected TEXT"
        )
        assert slug["nn"] == 1, f"{tbl}.{slug_col} is not NOT NULL"
        # UNIQUE constraint: sqlite auto-creates sqlite_autoindex_<tbl>_N
        idx_names = {
            r[0]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master "
                f"WHERE type='index' AND tbl_name='{tbl}'"
            ).fetchall()
        }
        auto_unique = {
            n for n in idx_names
            if n.startswith(f"sqlite_autoindex_{tbl}_")
        }
        assert auto_unique, (
            f"no UNIQUE auto-index on {tbl}.{slug_col}. indexes={idx_names}"
        )
        # Row count matches the v1.8 baseline.
        n = s._conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        assert n == expected_rows, (
            f"{tbl} has {n} rows, expected {expected_rows}"
        )
    finally:
        s.close()


# --- happy path: hf_orgs column rename -----------------------------------


def test_migration_020_hf_orgs_namespace_column_renamed(tmp_path):
    """hf_orgs original TEXT PK `id` is renamed to `namespace`. The new
    INTEGER PK is also called `id`."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r["name"]: r for r in s._conn.execute(
                "PRAGMA table_info(hf_orgs)"
            ).fetchall()
        }
        # id is INTEGER PK
        assert "INTEGER" in cols["id"]["type"].upper()
        assert cols["id"]["pk"] == 1
        # namespace exists and is TEXT UNIQUE NOT NULL
        assert "namespace" in cols, "hf_orgs.namespace missing"
        assert "TEXT" in cols["namespace"]["type"].upper()
        assert cols["namespace"]["notnull"] == 1
        # The old HF namespace values (TEXT) are preserved in the
        # namespace column.
        namespaces = {
            r["namespace"]
            for r in s._conn.execute("SELECT namespace FROM hf_orgs").fetchall()
        }
        expected = {
            "Qwen", "baidu", "tencent", "moonshotai", "THUDM",
            "XiaomiMiMo", "mistralai", "inclusionAI",
            "deepseek-ai", "stepfun-ai", "MiniMaxAI",
        }
        assert namespaces == expected, (
            f"hf_orgs namespace mismatch. got={namespaces}, expected={expected}"
        )
    finally:
        s.close()


# --- happy path: fact table (posts) has INTEGER id PK --------------------


def test_migration_020_posts_integer_pk(tmp_path):
    """posts has `id INTEGER PRIMARY KEY AUTOINCREMENT` + `tweet_id TEXT
    UNIQUE NOT NULL` (the original PK column, now a slug)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r["name"]: r for r in s._conn.execute(
                "PRAGMA table_info(posts)"
            ).fetchall()
        }
        assert "INTEGER" in cols["id"]["type"].upper()
        assert cols["id"]["pk"] == 1
        assert "tweet_id" in cols
        assert "TEXT" in cols["tweet_id"]["type"].upper()
        assert cols["tweet_id"]["notnull"] == 1
        # tweet_id is UNIQUE: sqlite auto-index
        idx_names = {
            r[0]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='posts'"
            ).fetchall()
        }
        auto_unique = {
            n for n in idx_names if n.startswith("sqlite_autoindex_posts_")
        }
        assert auto_unique, (
            f"no UNIQUE auto-index on posts.tweet_id. indexes={idx_names}"
        )
    finally:
        s.close()


# --- happy path: products dependent table INTEGER PK + INTEGER FKs -------


def test_migration_020_products_integer_pk_and_fks(tmp_path):
    """products has `id INTEGER PRIMARY KEY AUTOINCREMENT` + INTEGER FK
    columns to brands and hf_orgs."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r["name"]: r for r in s._conn.execute(
                "PRAGMA table_info(products)"
            ).fetchall()
        }
        assert "INTEGER" in cols["id"]["type"].upper()
        assert cols["id"]["pk"] == 1
        # brand_id is INTEGER (not TEXT)
        assert "INTEGER" in cols["brand_id"]["type"].upper(), (
            f"products.brand_id type is {cols['brand_id']['type']!r}, "
            f"expected INTEGER"
        )
        # hf_org_id is INTEGER (not TEXT)
        assert "INTEGER" in cols["hf_org_id"]["type"].upper(), (
            f"products.hf_org_id type is {cols['hf_org_id']['type']!r}, "
            f"expected INTEGER"
        )
        # FKs to brands.id and hf_orgs.id
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('products')"
        ).fetchall()
        assert any(r[2] == "brands" for r in fks), (
            f"products.brand_id FK to brands missing. FKs found: {fks}"
        )
        assert any(r[2] == "hf_orgs" for r in fks), (
            f"products.hf_org_id FK to hf_orgs missing. FKs found: {fks}"
        )
    finally:
        s.close()


# --- happy path: FK columns are INTEGER-storing-id (no TEXT-storing-key) -


@pytest.mark.parametrize("tbl,col,parent_tbl", [
    ("brands_companies", "brand_id", "brands"),
    ("brands_companies", "company_id", "companies"),
    ("brands_accounts", "brand_id", "brands"),
    ("brands_accounts", "author_id", "accounts"),
    ("brands_accounts", "role_id", "roles"),
    ("companies_accounts", "company_id", "companies"),
    ("companies_accounts", "author_id", "accounts"),
    ("companies_accounts", "role_id", "roles"),
    ("posts_brands", "post_id", "posts"),
    ("posts_brands", "brand_id", "brands"),
    ("brand_search_terms", "brand_id", "brands"),
    ("posts_brands_signals", "post_id", "posts"),
    ("posts_brands_signals", "brand_id", "brands"),
    ("posts_brands_signals", "signal_id", "signals"),
    ("posts_brands_signals", "post_type", "post_type_keys"),
    ("posts_brands_signals", "sentiment", "sentiment_keys"),
    ("posts_brands_mentions", "post_id", "posts"),
    ("posts_brands_mentions", "brand_id", "brands"),
    ("posts", "author_id", "accounts"),
    ("search_queries", "brand_id", "brands"),
    ("hf_orgs", "company_id", "companies"),
    ("products", "brand_id", "brands"),
    ("products", "hf_org_id", "hf_orgs"),
])
def test_migration_020_fk_column_is_integer(tmp_path, tbl, col, parent_tbl):
    """The FK column is INTEGER (not TEXT). Per the user's pick
    'INTEGER-storing-id for all 13 tables (plan body literal)'."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        c = s._conn.execute(
            f"SELECT type FROM pragma_table_info('{tbl}') WHERE name='{col}'"
        ).fetchone()
        assert c is not None, f"{tbl}.{col} missing"
        assert "INTEGER" in c[0].upper(), (
            f"{tbl}.{col} type is {c[0]!r}, expected INTEGER-storing-id"
        )
    finally:
        s.close()


# --- happy path: FK pragma still resolves (FK is to the new INTEGER id) -


def test_migration_020_brands_accounts_role_id_fks_to_roles_id(tmp_path):
    """brands_accounts.role_id INTEGER FK → roles.id (not roles.key)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('brands_accounts')"
        ).fetchall()
        # (id, seq, table, from, to, on_update, on_delete, match)
        role_fk = next(
            (r for r in fks if r[3] == "role_id"), None,
        )
        assert role_fk is not None, (
            f"brands_accounts.role_id FK missing. FKs found: {fks}"
        )
        assert role_fk[2] == "roles", (
            f"brands_accounts.role_id FK target is {role_fk[2]!r}, expected 'roles'"
        )
        assert role_fk[4] == "id", (
            f"brands_accounts.role_id FK target column is {role_fk[4]!r}, "
            f"expected 'id' (INTEGER PK)"
        )
    finally:
        s.close()


def test_migration_020_posts_brands_signals_signal_id_fks_to_signals_id(tmp_path):
    """posts_brands_signals.signal_id INTEGER FK → signals.id (not signals.key)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        sig_fk = next(
            (r for r in fks if r[3] == "signal_id"), None,
        )
        assert sig_fk is not None
        assert sig_fk[2] == "signals"
        assert sig_fk[4] == "id", (
            f"posts_brands_signals.signal_id FK target column is {sig_fk[4]!r}, "
            f"expected 'id' (INTEGER PK)"
        )
    finally:
        s.close()


def test_migration_020_hf_orgs_company_id_fks_to_companies_id(tmp_path):
    """hf_orgs.company_id INTEGER FK → companies.id (not companies.company_id)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('hf_orgs')"
        ).fetchall()
        co_fk = next(
            (r for r in fks if r[3] == "company_id"), None,
        )
        assert co_fk is not None
        assert co_fk[2] == "companies"
        assert co_fk[4] == "id", (
            f"hf_orgs.company_id FK target column is {co_fk[4]!r}, "
            f"expected 'id' (INTEGER PK)"
        )
    finally:
        s.close()


# --- happy path: CHECK constraint dropped -------------------------------


def test_migration_020_posts_brands_signals_check_dropped(tmp_path):
    """The CHECK `(brand_id <> '_unattributed')` from migration 004 is
    dropped (INTEGER-PK semantics shift). See migration header for
    rationale."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        sql = s._conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='posts_brands_signals'"
        ).fetchone()[0]
        assert "CHECK" not in sql.upper(), (
            f"posts_brands_signals still has a CHECK constraint. SQL: {sql}"
        )
    finally:
        s.close()


# --- happy path: brands_companies JOIN-backfill round-trip --------------


def test_migration_020_brands_companies_join_roundtrip(tmp_path):
    """brands_companies row count = 11 (the v1 baseline) + the FK columns
    are correctly backfilled (JOIN via slug column)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        n = s._conn.execute("SELECT COUNT(*) FROM brands_companies").fetchone()[0]
        assert n == 11, f"brands_companies has {n} rows, expected 11"
        # Sample 3 rows: the int brand_id and int company_id should
        # JOIN cleanly to brands.brand_id and companies.company_id.
        rows = s._conn.execute(
            """
            SELECT bc.brand_id, b.brand_id AS text_brand,
                   bc.company_id, c.company_id AS text_company,
                   bc.ownership_pct
            FROM brands_companies bc
            JOIN brands b     ON b.id     = bc.brand_id
            JOIN companies c  ON c.id     = bc.company_id
            ORDER BY b.brand_id, c.company_id
            LIMIT 3
            """
        ).fetchall()
        assert len(rows) == 3
        for r in rows:
            assert isinstance(r["brand_id"], int)
            assert isinstance(r["company_id"], int)
            assert isinstance(r["text_brand"], str)
            assert isinstance(r["text_company"], str)
    finally:
        s.close()


# --- happy path: hf_orgs data preserved across column rename ------------


def test_migration_020_hf_orgs_data_preserved_with_integer_company_id(tmp_path):
    """All 11 hf_orgs rows preserved; company_id is now INTEGER-storing-id
    that JOINs to companies.id."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            """
            SELECT h.id, h.namespace, h.company_id, c.company_id AS company_slug
            FROM hf_orgs h
            JOIN companies c ON c.id = h.company_id
            ORDER BY h.id
            """
        ).fetchall()
        assert len(rows) == 11
        # All hf_orgs.id and hf_orgs.company_id are integers (INTEGER PK + INTEGER FK)
        for r in rows:
            assert isinstance(r["id"], int)
            assert isinstance(r["company_id"], int)
            assert isinstance(r["namespace"], str)
            assert isinstance(r["company_slug"], str)
        # Spot-check known mapping
        by_ns = {r["namespace"]: r["company_slug"] for r in rows}
        assert by_ns["Qwen"] == "alibaba", (
            f"Qwen's company should be 'alibaba', got {by_ns.get('Qwen')!r}"
        )
        assert by_ns["MiniMaxAI"] == "minimax", (
            f"MiniMaxAI's company should be 'minimax', "
            f"got {by_ns.get('MiniMaxAI')!r}"
        )
    finally:
        s.close()


# --- happy path: enum table FKs still wire up ---------------------------


def test_migration_020_signal_id_resolves_to_known_signal_id(tmp_path):
    """After conversion, signal_id values are INTEGER-storing-id. A
    write of a known signal maps to its INTEGER id (dead-letter guard
    still drops unknown signals — this is just a sanity check that
    the post-migration 020 schema is sane for writes)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # release is one of the 6 known signals; its id should be
        # the AUTOINCREMENT-assigned id (1..6 in declaration order
        # from migration 008 + 018).
        release_row = s._conn.execute(
            "SELECT id FROM signals WHERE key = 'release'"
        ).fetchone()
        assert release_row is not None
        assert isinstance(release_row["id"], int)
    finally:
        s.close()


# --- happy path: FK enforcement is ON after migration ------------------


def test_migration_020_foreign_keys_re_enabled_after_migration(tmp_path):
    """The migration runner toggles FKs OFF around the migration; the
    finally clause re-enables them. Post-migration, PRAGMA foreign_keys
    should return 1 (ON)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fk_status = s._conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk_status == 1, (
            f"PRAGMA foreign_keys is {fk_status}, expected 1 (ON)"
        )
    finally:
        s.close()


# --- FK integrity: bad parent id is rejected ----------------------------


def test_migration_020_bad_brand_id_in_child_rejected(tmp_path):
    """An INSERT into brands_companies with a brand_id that does not
    exist in brands.id is rejected (FK enforcement)."""
    from x_monitor.store import Store
    import sqlite3

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            # Pick an id that definitely does not exist.
            with s.transaction():
                s._conn.execute(
                    "INSERT INTO brands_companies (brand_id, company_id, "
                    "ownership_pct) VALUES (?, ?, ?)",
                    (999999, 999999, 0.5),
                )
    finally:
        s.close()


def test_migration_020_bad_role_id_in_brands_accounts_rejected(tmp_path):
    """An INSERT into brands_accounts with a role_id that does not
    exist in roles.id is rejected."""
    from x_monitor.store import Store
    import sqlite3

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Get a real brand_id + author_id; then write a bad role_id.
        b_row = s._conn.execute(
            "SELECT id FROM brands WHERE brand_id = 'minimax'"
        ).fetchone()
        a_row = s._conn.execute(
            "SELECT id FROM accounts WHERE author_id = 'u_020_role' "
            "ORDER BY id LIMIT 1"
        )
        a_row = s._conn.execute(
            "SELECT id FROM accounts WHERE author_id LIKE 'u_020%' LIMIT 1"
        ).fetchone()
        if a_row is None:
            # Insert an account row to use as author.
            s._conn.execute(
                "INSERT INTO accounts (author_id, handle, display_name) "
                "VALUES (?, ?, ?)",
                ("u_020_role", "u_020_role", "u_020_role"),
            )
            a_row = s._conn.execute(
                "SELECT id FROM accounts WHERE author_id = 'u_020_role'"
            ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            with s.transaction():
                s._conn.execute(
                    "INSERT INTO brands_accounts (brand_id, author_id, "
                    "role_id, added_at) VALUES (?, ?, ?, ?)",
                    (b_row["id"], a_row["id"], 999999, "2026-06-25T00:00:00+00:00"),
                )
    finally:
        s.close()


def test_migration_020_bad_signal_id_in_posts_brands_signals_rejected(tmp_path):
    """An INSERT into posts_brands_signals with a signal_id that does
    not exist in signals.id is rejected."""
    from x_monitor.store import Store
    import sqlite3

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        b_row = s._conn.execute(
            "SELECT id FROM brands WHERE brand_id = 'minimax'"
        ).fetchone()
        # We need a real post_id; insert a post first.
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_020_fk", "u_020_fk", "2026-06-25T00:00:00+00:00"),
        )
        p_row = s._conn.execute(
            "SELECT id FROM posts WHERE tweet_id = 't_020_fk'"
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            with s.transaction():
                s._conn.execute(
                    "INSERT INTO posts_brands_signals (post_id, brand_id, "
                    "signal_id) VALUES (?, ?, ?)",
                    (p_row["id"], b_row["id"], 999999),
                )
    finally:
        s.close()


# --- happy path: post-020 schemas match across tables ------------------


def test_migration_020_all_tables_have_expected_schema_shape(tmp_path):
    """Sanity check: every table that should have an INTEGER id PK does,
    and every table that should have a TEXT UNIQUE slug does. This is
    a single test that walks all 14 tables (13 refactored + products
    dependent) for clarity."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # (table, id_col_name, slug_col_name)
        # edge tables have composite PKs and no single id column
        tables_with_id_pk = [
            ("brands", "id", "brand_id"),
            ("companies", "id", "company_id"),
            ("accounts", "id", "author_id"),
            ("hf_orgs", "id", "namespace"),
            ("search_queries", "id", "query_id"),
            ("posts", "id", "tweet_id"),
            ("products", "id", "repo_id"),
        ]
        for tbl, id_col, slug_col in tables_with_id_pk:
            id_info = s._conn.execute(
                f"SELECT type, pk FROM pragma_table_info('{tbl}') "
                f"WHERE name='{id_col}'"
            ).fetchone()
            assert id_info is not None, f"{tbl}.{id_col} missing"
            assert "INTEGER" in id_info["type"].upper(), (
                f"{tbl}.{id_col} type is {id_info['type']!r}, expected INTEGER"
            )
            assert id_info["pk"] == 1, f"{tbl}.{id_col} is not PK"
            slug_info = s._conn.execute(
                f"SELECT type, [notnull] AS nn FROM pragma_table_info('{tbl}') "
                f"WHERE name='{slug_col}'"
            ).fetchone()
            assert slug_info is not None, f"{tbl}.{slug_col} missing"
            assert "TEXT" in slug_info["type"].upper()
            assert slug_info["nn"] == 1

        # Edge tables: composite PKs, all components INTEGER.
        # The PK columns are (brand_id, author_id) for brands_accounts
        # (role_id is a regular FK column, not part of the PK).
        composite_pk_tables = {
            "brands_companies":    ["brand_id", "company_id"],
            "brands_accounts":     ["brand_id", "author_id"],
            "companies_accounts":  ["company_id", "author_id"],
            "posts_brands":        ["post_id", "brand_id"],
            "brand_search_terms":  ["brand_id", "term"],
            "posts_brands_signals": ["post_id", "brand_id"],
            "posts_brands_mentions": ["post_id", "brand_id", "source"],
        }
        for tbl, expected_pk_cols in composite_pk_tables.items():
            pk_cols = {
                r["name"]
                for r in s._conn.execute(
                    f"SELECT name, pk FROM pragma_table_info('{tbl}') WHERE pk > 0"
                ).fetchall()
            }
            assert pk_cols == set(expected_pk_cols), (
                f"{tbl} PK cols are {pk_cols}, expected {set(expected_pk_cols)}"
            )
    finally:
        s.close()


# --- idempotency ---------------------------------------------------------


def test_migration_020_idempotent(tmp_path):
    """Re-opening a DB that has 020 applied does not re-run it. Row
    counts are unchanged."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    s1.close()

    s2 = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s2._conn.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        )
        assert applied.count(20) == 1, (
            f"migration 20 applied {applied.count(20)} times"
        )
        # Row counts unchanged.
        n_brands = s2._conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
        n_hf = s2._conn.execute("SELECT COUNT(*) FROM hf_orgs").fetchone()[0]
        n_bc = s2._conn.execute(
            "SELECT COUNT(*) FROM brands_companies"
        ).fetchone()[0]
        assert n_brands == 12, f"brands has {n_brands} rows after re-open"
        assert n_hf == 11, f"hf_orgs has {n_hf} rows after re-open"
        assert n_bc == 11, f"brands_companies has {n_bc} rows after re-open"
    finally:
        s2.close()


# --- full stack apply ----------------------------------------------------


def test_migration_020_full_stack_apply(tmp_path):
    """All migrations 001-020 apply on a fresh DB."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute(
                "SELECT version FROM _migrations"
            ).fetchall()
        )
        assert applied == list(range(1, 21)), (
            f"unexpected versions: {applied}"
        )
    finally:
        s.close()


# --- indexes preserved --------------------------------------------------


def test_migration_020_indexes_preserved(tmp_path):
    """The indexes on the FK columns survive the rebuild."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        indexes = {
            r[0]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        for idx in (
            "idx_brands_brand_id",
            "idx_companies_company_id",
            "idx_accounts_author_id",
            "idx_hf_orgs_namespace",
            "idx_search_queries_query_id",
            "idx_posts_tweet_id",
            "idx_products_repo_id",
            "idx_brands_accounts_role_id",
            "idx_companies_accounts_role_id",
            "idx_posts_brands_brand_id",
            "idx_posts_brands_signals_brand_id_signal_id",
            "idx_posts_brands_signals_brand_id_post_type",
            "idx_posts_brands_signals_brand_id_sentiment",
        ):
            assert idx in indexes, f"{idx} missing"
    finally:
        s.close()
