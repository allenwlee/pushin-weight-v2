"""Migration 015: rename role_keys → roles.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 5 of 9, R5).

Verifies:
- role_keys table no longer exists; roles exists after migration 015.
- role_labels still exists (labels table name is unchanged).
- The 5 canonical roles are seeded (official, community, researcher, press, vendor).
- brands_accounts.role column renamed to role_id (still TEXT PK).
- companies_accounts.role column renamed to role_id.
- Indexes idx_brands_accounts_role_id and idx_companies_accounts_role_id
  exist on the new column.
- The FKs on brands_accounts.role_id and companies_accounts.role_id
  reference roles(key).
- Idempotency: re-opening a DB that has 015 applied does not re-run it.
- Full stack apply: all migrations 001-015 apply on a fresh DB.
- Integration: upsert_account writes role_id column; the FK guard
  still fires on unknown roles.
- Integration: get_account / get_accounts return role_id (renamed from role).
"""

import pytest


# --- happy path: table renamed ------------------------------------


def test_migration_015_role_keys_renamed_to_roles(tmp_path):
    """role_keys does not exist; roles exists."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'role_keys'"
        ).fetchall()
        assert rows == [], f"role_keys still exists: {rows}"
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'roles'"
        ).fetchall()
        assert rows, "roles table not found"
    finally:
        s.close()


def test_migration_015_role_labels_unchanged(tmp_path):
    """role_labels (the labels table) is unchanged — it keeps its
    _labels suffix per the universal rule."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'role_labels'"
        ).fetchall()
        assert rows, "role_labels table missing"
    finally:
        s.close()


def test_migration_015_roles_seeded_with_five_keys(tmp_path):
    """The 3 canonical roles are seeded (post-U6 trim): official, staff,
    community. Migration 008 originally seeded 5; migration 016 trimmed
    the unused researcher/press/vendor values."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {r[0] for r in s._conn.execute("SELECT key FROM roles").fetchall()}
        assert keys == {"official", "staff", "community"}
    finally:
        s.close()


# --- happy path: columns renamed ----------------------------------


def test_migration_015_brands_accounts_role_renamed_to_role_id(tmp_path):
    """brands_accounts has role_id (not role)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1] for r in s._conn.execute(
                "PRAGMA table_info(brands_accounts)"
            ).fetchall()
        }
        assert "role_id" in cols, f"role_id missing. cols={cols}"
        assert "role" not in cols, f"old `role` column still present. cols={cols}"
    finally:
        s.close()


def test_migration_015_companies_accounts_role_renamed_to_role_id(tmp_path):
    """companies_accounts has role_id (not role)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1] for r in s._conn.execute(
                "PRAGMA table_info(companies_accounts)"
            ).fetchall()
        }
        assert "role_id" in cols, f"role_id missing. cols={cols}"
        assert "role" not in cols, f"old `role` column still present. cols={cols}"
    finally:
        s.close()


def test_migration_015_fk_on_brands_accounts_role_id_references_roles(tmp_path):
    """The FK on brands_accounts.role_id references roles(key)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('brands_accounts')"
        ).fetchall()
        assert any(r[2] == "roles" and r[3] == "role_id" for r in fks), (
            f"role_id FK to roles missing. FKs found: {fks}"
        )
    finally:
        s.close()


def test_migration_015_fk_on_companies_accounts_role_id_references_roles(tmp_path):
    """The FK on companies_accounts.role_id references roles(key)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('companies_accounts')"
        ).fetchall()
        assert any(r[2] == "roles" and r[3] == "role_id" for r in fks), (
            f"role_id FK to roles missing. FKs found: {fks}"
        )
    finally:
        s.close()


def test_migration_015_indexes_rebuilt_on_role_id(tmp_path):
    """The indexes idx_brands_accounts_role_id and idx_companies_accounts_role_id
    exist on the new role_id columns."""
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
        assert "idx_brands_accounts_role_id" in indexes, (
            f"new index missing. indexes={indexes}"
        )
        assert "idx_companies_accounts_role_id" in indexes, (
            f"new index missing. indexes={indexes}"
        )
        # Old indexes are gone.
        assert "idx_brands_accounts_role" not in indexes, (
            f"old index still present. indexes={indexes}"
        )
        assert "idx_companies_accounts_role" not in indexes, (
            f"old index still present. indexes={indexes}"
        )
    finally:
        s.close()


# --- idempotency ---------------------------------------------------


def test_migration_015_idempotent(tmp_path):
    """Re-opening a DB that has 015 applied does not re-run it."""
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
        assert applied.count(15) == 1
    finally:
        s2.close()


# --- full stack apply ----------------------------------------------


def test_migration_015_full_stack_apply(tmp_path):
    """All migrations {1..20, 22} apply on a fresh DB (only 21 absent).

    Migration 015's intent (rename role_keys → roles) is preserved: the
    `roles` table survives post-022 (only the 6-signal taxonomy was
    killed, not roles). The `signals` + `signal_labels` tables were
    dropped in 022.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        expected = sorted(set(range(1, 21)) | {22})
        assert applied == expected, (
            f"unexpected versions: {applied} (expected {expected})"
        )
        # The surviving singular enum table convention.
        for tbl in ("roles", "role_labels"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows, f"{tbl} missing"
        # The 6-signal taxonomy tables are GONE post-022.
        for tbl in ("signals", "signal_labels"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows == [], f"{tbl} should be GONE post-022"
        # Both old names are gone.
        for old in ("signal_keys", "role_keys"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (old,)
            ).fetchall()
            assert rows == [], f"{old} still exists after 014/015"
    finally:
        s.close()


# --- integration: upsert_account still works ----------------------


def test_migration_015_upsert_account_writes_role_id(tmp_path):
    """upsert_account writes the renamed role_id column on brands_accounts.
    Post-020: role_id is INTEGER FK to roles.id (post-U8 conversion)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        official_id = s._conn.execute(
            "SELECT id FROM roles WHERE key='official'"
        ).fetchone()["id"]
        s.upsert_account("minimax", "u_015", role="official")
        row = s._conn.execute(
            "SELECT ba.role_id "
            "FROM brands_accounts ba "
            "JOIN accounts a ON a.id = ba.author_id "
            "WHERE a.author_id = ?",
            ("handle:u_015",),
        ).fetchone()
        assert row is not None
        assert row["role_id"] == official_id, (
            f"role_id is {row['role_id']!r}, expected {official_id} "
            f"(INTEGER FK to official)"
        )
    finally:
        s.close()


def test_migration_015_unknown_role_dead_lettered(tmp_path):
    """The FK guard still drops unknown role values to the dead-letter."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.upsert_account("minimax", "u_015_ghost", role="ghost_role")
        # brands_accounts row NOT written for unknown role.
        row = s._conn.execute(
            "SELECT * FROM brands_accounts WHERE author_id = ?",
            ("handle:u_015_ghost",),
        ).fetchone()
        assert row is None
        # accounts row IS written (per pre-v1.8 semantics).
        acc = s._conn.execute(
            "SELECT author_id FROM accounts WHERE author_id = ?",
            ("handle:u_015_ghost",),
        ).fetchone()
        assert acc is not None
    finally:
        s.close()


# --- integration: get_account returns role_id ---------------------


def test_migration_015_get_account_returns_role_id(tmp_path):
    """get_account returns the renamed role_id column. Post-020:
    role_id is INTEGER FK to roles.id, so the dict's role_id value
    is the integer id (not the string key)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        community_id = s._conn.execute(
            "SELECT id FROM roles WHERE key='community'"
        ).fetchone()["id"]
        s.upsert_account("minimax", "u_015_get", role="community")
        result = s.get_account("minimax", "u_015_get")
        assert result is not None
        assert result.get("role_id") == community_id, (
            f"role_id is {result.get('role_id')!r}, expected {community_id} "
            f"(INTEGER FK to community)"
        )
    finally:
        s.close()


def test_migration_015_known_role_keys_returns_seeded_set(tmp_path):
    """_known_role_keys returns the 3-key trimmed set (now from the
    renamed roles table; post-U6 trim in 016)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = s._known_role_keys()
        assert keys == {"official", "staff", "community"}
    finally:
        s.close()
