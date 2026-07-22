"""Migration 018: INTEGER primary keys for enum tables (roles only post-022).

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 8 of 9).

Migration 018 originally rebuilt BOTH `signals` and `roles` with
INTEGER id PKs, leaving signal_id / role_id FK columns as TEXT-storing-key.
Subsequent migrations have narrowed what 018 verifies:

- Migration 020 (U8 full remediation) converted `role_id` FK columns
  in `brands_accounts` and `companies_accounts` from TEXT-storing-key
  to INTEGER-storing-id (FK → roles.id). Migration 018 did not do that;
  020 did. See `test_migration_020_*` for that verification.

- Migration 022 (U9 kill) DROPPED `signals` + `signal_labels` and the
  `signal_id` column from `posts_brands_signals`. So the "signals has
  INTEGER id PK" tests are NOT verified here — they're history. What
  018 actually contributed to the live schema is the INTEGER id PK on
  `roles`, which 022 did not touch.

What 018 left in place (still verified):
- `roles.id` is INTEGER PRIMARY KEY AUTOINCREMENT.
- `roles.key` is TEXT NOT NULL UNIQUE.
- `roles` is seeded with 3 rows (official, staff, community) at ids 1-3.
- `role_labels.key` continues to FK to `roles.key` (TEXT, UNIQUE).
- `_known_role_keys()` cache returns the 3-key trimmed set of strings.
- The dead-letter guard still drops unknown role values.
- AUTOINCREMENT: id 1-3 are stable; new INSERTs assign id > 3.
- `brands_accounts.role_id` and `companies_accounts.role_id` are
  INTEGER (post-020), not TEXT (post-018). Migration 018 did not do
  this conversion — 020 did — so the TEXT-shape tests that originally
  lived here are replaced by INTEGER-shape verifications below.

Idempotency: re-opening a DB that has 018 applied does not re-run it.
Full stack apply: migrations {1..18, 20, 22} apply on a fresh DB
(migration 021 is INTENTIONALLY absent — reserved for an HF products
crawler that never landed).
"""

import pytest


# --- happy path: roles PK is INTEGER -------------------------------


def test_migration_018_roles_has_integer_id_pk(tmp_path):
    """roles has `id INTEGER PRIMARY KEY AUTOINCREMENT`."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = s._conn.execute("PRAGMA table_info(roles)").fetchall()
        col_map = {r["name"]: r for r in cols}
        assert "id" in col_map, f"id column missing. cols={[c['name'] for c in cols]}"
        assert "INTEGER" in col_map["id"]["type"].upper(), (
            f"id type is {col_map['id']['type']!r}, expected INTEGER"
        )
        assert col_map["id"]["pk"] == 1, (
            f"id is not PK. pk={col_map['id']['pk']}"
        )
    finally:
        s.close()


def test_migration_018_roles_key_is_unique_not_null(tmp_path):
    """roles.key is TEXT NOT NULL UNIQUE (was the old PK)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = s._conn.execute("PRAGMA table_info(roles)").fetchall()
        col_map = {r["name"]: r for r in cols}
        assert col_map["key"]["notnull"] == 1, (
            f"key is not NOT NULL. col={col_map['key']}"
        )
        idx_rows = s._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='roles'"
        ).fetchall()
        idx_names = {r[0] for r in idx_rows}
        auto_unique = {n for n in idx_names if n.startswith("sqlite_autoindex_roles_")}
        assert auto_unique, (
            f"no UNIQUE auto-index on roles.key. indexes={idx_names}"
        )
    finally:
        s.close()


def test_migration_018_roles_id_auto_assigned(tmp_path):
    """roles has 3 rows with ids 1..3 (one per trimmed role)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT id, key FROM roles ORDER BY id"
        ).fetchall()
        assert len(rows) == 3, f"expected 3 roles rows, got {len(rows)}"
        ids = [r["id"] for r in rows]
        assert ids == [1, 2, 3], f"unexpected ids: {ids}"
        for r in rows:
            assert isinstance(r["id"], int), f"id is {type(r['id']).__name__}, not int"
    finally:
        s.close()


def test_migration_018_roles_keys_preserved(tmp_path):
    """The 3 trimmed role keys are present after the rebuild."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {r["key"] for r in s._conn.execute("SELECT key FROM roles").fetchall()}
        assert keys == {"official", "staff", "community"}, (
            f"unexpected roles keys: {keys}"
        )
    finally:
        s.close()


# --- happy path: role_labels FK still resolves ---------------------


def test_migration_018_role_labels_fk_to_roles_key(tmp_path):
    """role_labels.key FK still references roles.key (the UNIQUE
    column in the rebuilt roles table). Migration 020 did not touch
    role_labels — its FK remains a TEXT-storing-key FK to roles.key."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('role_labels')"
        ).fetchall()
        assert any(r[2] == "roles" and r[3] == "key" and r[4] == "key" for r in fks), (
            f"role_labels FK to roles.key missing. FKs found: {fks}"
        )
    finally:
        s.close()


# --- happy path: child table role_id FK columns are INTEGER ---------
# Migration 018 left role_id as TEXT FK → roles.key. Migration 020
# converted it to INTEGER FK → roles.id. The assertions below verify
# the post-020 INTEGER shape; they would have failed under the 018-only
# TEXT shape. This is deliberate — the role_id INTEGER conversion is
# the canonical post-U8 state.


def test_migration_018_brands_accounts_role_id_integer_fk(tmp_path):
    """brands_accounts.role_id is INTEGER FK to roles.id (post-020)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = s._conn.execute(
            "PRAGMA table_info(brands_accounts)"
        ).fetchall()
        col_map = {r["name"]: r for r in cols}
        assert "role_id" in col_map, "role_id column missing"
        assert "INTEGER" in col_map["role_id"]["type"].upper(), (
            f"role_id type is {col_map['role_id']['type']!r}, expected INTEGER"
        )
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('brands_accounts')"
        ).fetchall()
        assert any(
            r[2] == "roles" and r[3] == "role_id" and r[4] == "id"
            for r in fks
        ), f"role_id INTEGER FK to roles.id missing. FKs found: {fks}"
    finally:
        s.close()


def test_migration_018_companies_accounts_role_id_integer_fk(tmp_path):
    """companies_accounts.role_id is INTEGER FK to roles.id (post-020)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = s._conn.execute(
            "PRAGMA table_info(companies_accounts)"
        ).fetchall()
        col_map = {r["name"]: r for r in cols}
        assert "role_id" in col_map, "role_id column missing"
        assert "INTEGER" in col_map["role_id"]["type"].upper(), (
            f"role_id type is {col_map['role_id']['type']!r}, expected INTEGER"
        )
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('companies_accounts')"
        ).fetchall()
        assert any(
            r[2] == "roles" and r[3] == "role_id" and r[4] == "id"
            for r in fks
        ), f"role_id INTEGER FK to roles.id missing. FKs found: {fks}"
    finally:
        s.close()


# --- happy path: indexes preserved ----------------------------------


def test_migration_018_indexes_preserved(tmp_path):
    """The 2 surviving role_id indexes are still present
    (signal_id index is GONE — dropped in 022)."""
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
            "idx_brands_accounts_role_id",
            "idx_companies_accounts_role_id",
        ):
            assert idx in indexes, f"{idx} missing"
        # signal_id index is GONE post-022.
        assert (
            "idx_posts_brands_signals_brand_id_signal_id" not in indexes
        ), "signal_id index should be dropped in 022"
    finally:
        s.close()


# --- idempotency ----------------------------------------------------


def test_migration_018_idempotent(tmp_path):
    """Re-opening a DB that has 018 applied does not re-run it.

    Post-022: signals table is GONE, so we only assert the surviving
    role count."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    s1.close()

    s2 = Store(db, auto_migrate=True)
    try:
        applied = [
            r[0]
            for r in s2._conn.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        ]
        assert applied.count(18) == 1, (
            f"migration 18 applied {applied.count(18)} times"
        )
        n_role = s2._conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
        assert n_role == 3, f"roles has {n_role} rows after re-open"
    finally:
        s2.close()


# --- full stack apply -----------------------------------------------


def test_migration_018_full_stack_apply(tmp_path):
    """All migrations {1..20, 22} apply on a fresh DB (only 21 absent).

    Migration 019 IS applied — it's the additive precursor that created
    the post_type_keys + sentiment_keys tables. Migration 022 then
    rebuilt posts_brands_signals on top of those new tables (dropping
    signal_id and the legacy signals table). Both migrations contribute
    to the live schema. Migration 021 was INTENTIONALLY SKIPPED
    (reserved for an unrelated HF products crawler that never landed).
    See the plan body for the U9 remediation scope.

    The `signals` table is DROPPED post-022; `roles` survives with
    INTEGER id PK.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        expected = sorted(set(range(1, 21)) | {22, 23})
        assert applied == expected, (
            f"unexpected versions: {applied} (expected {expected})"
        )
        # U9: the `signals` table is DROPPED post-022.
        sig_row = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name='signals'"
        ).fetchone()
        assert sig_row is None, "signals table should be DROPPED post-022"
        # `roles` still has INTEGER id PK.
        col = s._conn.execute(
            "SELECT type, pk FROM pragma_table_info('roles') WHERE name='id'"
        ).fetchone()
        assert col is not None, "roles.id missing"
        assert "INTEGER" in col["type"].upper(), (
            f"roles.id type is {col['type']!r}"
        )
        assert col["pk"] == 1, "roles.id is not PK"
    finally:
        s.close()


# --- integration: insert paths --------------------------------------


def test_migration_018_upsert_account_writes_integer_role(tmp_path):
    """upsert_account writes the INTEGER role FK to brands_accounts.role_id
    (post-020). The string key is resolved to roles.id before the insert."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        official_id = s._conn.execute(
            "SELECT id FROM roles WHERE key='official'"
        ).fetchone()["id"]
        s.upsert_account("minimax", "u_018", role="official")
        row = s._conn.execute(
            "SELECT ba.role_id, r.key "
            "FROM brands_accounts ba "
            "JOIN roles r ON r.id = ba.role_id "
            "JOIN accounts a ON a.id = ba.author_id "
            "WHERE a.author_id = ?",
            ("handle:u_018",),
        ).fetchone()
        assert row is not None
        assert row["role_id"] == official_id, (
            f"role_id is {row['role_id']!r}, expected {official_id} "
            f"(INTEGER FK to official)"
        )
        assert row["key"] == "official", (
            f"joined role.key is {row['key']!r}, expected 'official'"
        )
    finally:
        s.close()


# --- integration: dead-letter guard still fires ---------------------


def test_migration_018_unknown_role_dead_lettered(tmp_path):
    """The FK guard still drops unknown role values to the dead-letter."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.upsert_account("minimax", "u_018_ghost", role="ghost_role")
        row = s._conn.execute(
            "SELECT * FROM brands_accounts ba "
            "JOIN accounts a ON a.id = ba.author_id "
            "WHERE a.author_id = ?",
            ("handle:u_018_ghost",),
        ).fetchone()
        assert row is None, "unknown role was not dead-lettered"
        # accounts row IS written (per pre-v1.8 semantics).
        acc = s._conn.execute(
            "SELECT author_id FROM accounts WHERE author_id = ?",
            ("handle:u_018_ghost",),
        ).fetchone()
        assert acc is not None
    finally:
        s.close()


# --- integration: caches still return string keys ------------------


def test_migration_018_known_role_keys_returns_seeded_set(tmp_path):
    """_known_role_keys still returns the 3-key trimmed set of strings."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = s._known_role_keys()
        assert keys == {"official", "staff", "community"}, (
            f"unexpected role keys: {keys}"
        )
    finally:
        s.close()


# --- integration: AUTOINCREMENT semantics --------------------------


def test_migration_018_autoincrement_id_is_monotonic(tmp_path):
    """Adding a new role via INSERT OR IGNORE assigns id 4
    (one past the highest pre-existing id). AUTOINCREMENT never reuses."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        max_id_before = s._conn.execute(
            "SELECT MAX(id) AS m FROM roles"
        ).fetchone()["m"]
        s._conn.execute(
            "INSERT INTO roles (key, created_at) VALUES (?, ?)",
            ("test_new_role", "2026-06-24T00:00:00+00:00"),
        )
        new_row = s._conn.execute(
            "SELECT id FROM roles WHERE key = ?",
            ("test_new_role",),
        ).fetchone()
        assert new_row is not None
        assert new_row["id"] > max_id_before, (
            f"new id {new_row['id']} should be > max pre-existing id {max_id_before}"
        )
        assert isinstance(new_row["id"], int), (
            f"new id is {type(new_row['id']).__name__}, not int"
        )
    finally:
        s.close()
