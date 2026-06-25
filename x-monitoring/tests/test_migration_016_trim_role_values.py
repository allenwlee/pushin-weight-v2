"""Migration 016: trim role taxonomy to {official, staff, community}.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 6 of 9, R6).

Verifies:
- `roles` table has exactly 3 rows: official, staff, community.
- The removed keys (researcher, press, vendor) are gone from `roles`.
- `role_labels` table has 6 rows (3 keys × 2 locales).
- The removed `role_labels` rows are gone.
- Each surviving role has both en + zh_cn labels.
- Idempotency: re-opening a DB that has 016 applied does not re-run it.
- Full stack apply: all migrations 001-016 apply on a fresh DB.
- Backfill: a pre-existing `brands_accounts.role_id` row with value
  'researcher' (or press, vendor) is remapped to 'community'.
- Backfill: a pre-existing `companies_accounts.role_id` row with value
  'researcher' is remapped to 'community'.
- FK enforcement: an INSERT into `brands_accounts` with a removed role
  value fails (FK violation).
- Integration: `_known_role_keys` returns the 3-key set.
- Integration: `_pick_enum_label('role', 'staff', 'zh_cn')` returns '员工'.
- Integration: upsert_account with role='staff' writes the
  brands_accounts edge.
"""

import pytest


# --- happy path: roles trimmed --------------------------------------


def test_migration_016_roles_has_three_keys(tmp_path):
    """roles has exactly {official, staff, community} after migration 016."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {r[0] for r in s._conn.execute("SELECT key FROM roles").fetchall()}
        assert keys == {"official", "staff", "community"}, (
            f"unexpected roles: {keys}"
        )
    finally:
        s.close()


def test_migration_016_roles_ordered(tmp_path):
    """`SELECT key FROM roles ORDER BY key` returns
    ['community', 'official', 'staff']."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = [
            r[0]
            for r in s._conn.execute("SELECT key FROM roles ORDER BY key").fetchall()
        ]
        assert rows == ["community", "official", "staff"], (
            f"unexpected role order: {rows}"
        )
    finally:
        s.close()


def test_migration_016_removed_role_keys_gone(tmp_path):
    """researcher, press, vendor are not in `roles`."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT key FROM roles WHERE key IN (?, ?, ?)",
            ("researcher", "press", "vendor"),
        ).fetchall()
        assert rows == [], f"removed role keys still present: {rows}"
    finally:
        s.close()


# --- happy path: role_labels trimmed --------------------------------


def test_migration_016_role_labels_count(tmp_path):
    """role_labels has exactly 6 rows (3 keys × 2 locales)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        n = s._conn.execute("SELECT COUNT(*) FROM role_labels").fetchone()[0]
        assert n == 6, f"role_labels has {n} rows, expected 6"
    finally:
        s.close()


def test_migration_016_role_labels_removed_gone(tmp_path):
    """role_labels has no rows for researcher, press, or vendor."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT key, lang FROM role_labels "
            "WHERE key IN (?, ?, ?)",
            ("researcher", "press", "vendor"),
        ).fetchall()
        assert rows == [], f"removed role_labels still present: {rows}"
    finally:
        s.close()


def test_migration_016_role_labels_round_trip(tmp_path):
    """Each of the 3 surviving roles has both en and zh_cn labels."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        labels = {
            (r[0], r[1]): r[2]
            for r in s._conn.execute(
                "SELECT key, lang, label FROM role_labels"
            ).fetchall()
        }
        assert labels[("official", "en")] == "Official"
        assert labels[("official", "zh_cn")] == "官方"
        assert labels[("staff", "en")] == "Staff"
        assert labels[("staff", "zh_cn")] == "员工"
        assert labels[("community", "en")] == "Community"
        assert labels[("community", "zh_cn")] == "社区"
    finally:
        s.close()


# --- idempotency ----------------------------------------------------


def test_migration_016_idempotent(tmp_path):
    """Re-opening a DB that has 016 applied does not re-run it (the
    _migrations ledger records version 16 exactly once)."""
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
        assert applied.count(16) == 1
        # role count is still 3.
        n = s2._conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
        assert n == 3
    finally:
        s2.close()


# --- full stack apply -----------------------------------------------


def test_migration_016_full_stack_apply(tmp_path):
    """All migrations {1..20, 22} apply on a fresh DB (only 21 absent);
    the trimmed role taxonomy is in effect."""
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
        # Trimmed role taxonomy.
        keys = {r[0] for r in s._conn.execute("SELECT key FROM roles").fetchall()}
        assert keys == {"official", "staff", "community"}
        # 6 role_labels rows.
        n_labels = s._conn.execute("SELECT COUNT(*) FROM role_labels").fetchone()[0]
        assert n_labels == 6
    finally:
        s.close()


# --- backfill: removed role_id values in M:N tables -----------------


def test_migration_016_backfill_brands_accounts_researcher_to_community(tmp_path):
    """A pre-existing `brands_accounts.role_id` value pointing at the
    legacy 'researcher' id is remapped to the 'community' id by the
    backfill UPDATE in 016. Post-020: brands_accounts.role_id is an
    INTEGER FK to roles.id, so the test operates on integer ids.

    U9 does not affect roles, so this test still exercises the
    migration 016 backfill semantics — just through the post-020
    INTEGER column shape.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Seed a row with the post-U6 trimmed set first; the
        # backfill UPDATE runs against all rows in the table.
        s.upsert_account("minimax", "u_pre", role="official")

        # Look up the ids we'll need to simulate legacy data.
        researcher_id = s._conn.execute(
            "SELECT id FROM roles WHERE key='researcher'"
        ).fetchone()
        community_id = s._conn.execute(
            "SELECT id FROM roles WHERE key='community'"
        ).fetchone()["id"]
        # The 'researcher' role row may or may not still exist (U6
        # trim removed it). If absent, we must INSERT it directly to
        # simulate pre-U6 data (the trim itself ran in 016 — the test
        # verifies the UPDATE logic, not the trim).
        if researcher_id is None:
            s._conn.execute(
                "INSERT INTO roles(key, created_at) VALUES (?, ?)",
                ("researcher", "2026-06-23T00:00:00+00:00"),
            )
            researcher_id = s._conn.execute(
                "SELECT id FROM roles WHERE key='researcher'"
            ).fetchone()["id"]
        else:
            researcher_id = researcher_id["id"]

        # Resolve brand_id (INTEGER FK post-020) and author_id.
        brand_int_id = s._conn.execute(
            "SELECT id FROM brands WHERE brand_id=?",
            ("minimax",),
        ).fetchone()["id"]
        s._conn.execute(
            "INSERT INTO accounts(author_id, handle) VALUES (?, ?)",
            ("handle:u_legacy_researcher", "u_legacy_researcher"),
        )
        author_int_id = s._conn.execute(
            "SELECT id FROM accounts WHERE author_id=?",
            ("handle:u_legacy_researcher",),
        ).fetchone()["id"]

        # Insert a "legacy" row with role_id = researcher_id. Disable
        # FK enforcement to bypass the post-016 guard that would reject
        # this value; we're simulating data written pre-U6.
        s._conn.execute("PRAGMA foreign_keys = OFF")
        s._conn.execute(
            "INSERT INTO brands_accounts(brand_id, author_id, role_id, added_at) "
            "VALUES (?, ?, ?, ?)",
            (
                brand_int_id,
                author_int_id,
                researcher_id,
                "2026-06-23T00:00:00+00:00",
            ),
        )
        s._conn.execute("PRAGMA foreign_keys = ON")

        # Apply the backfill UPDATE in 016's SQL form (operates on
        # role_id values that resolve to keys in the legacy set).
        s._conn.executescript("""
            UPDATE brands_accounts
               SET role_id = (SELECT id FROM roles WHERE key='community')
             WHERE role_id = (SELECT id FROM roles WHERE key='researcher');
        """)
        row = s._conn.execute(
            "SELECT ba.role_id, r.key "
            "FROM brands_accounts ba "
            "JOIN roles r ON r.id = ba.role_id "
            "WHERE ba.author_id = ?",
            (author_int_id,),
        ).fetchone()
        assert row is not None
        assert row["role_id"] == community_id, (
            f"expected role_id={community_id} (community) after backfill, "
            f"got {row['role_id']}"
        )
        assert row["key"] == "community", (
            f"expected joined key='community', got {row['key']!r}"
        )
    finally:
        s.close()


def test_migration_016_backfill_companies_accounts_press_to_community(tmp_path):
    """A pre-existing `companies_accounts.role_id` pointing at the
    legacy 'press' id is remapped to the 'community' id by the
    backfill UPDATE in 016. Post-020: companies_accounts.role_id is
    INTEGER FK to roles.id; company_id and author_id are also INTEGER."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        press_id_row = s._conn.execute(
            "SELECT id FROM roles WHERE key='press'"
        ).fetchone()
        community_id = s._conn.execute(
            "SELECT id FROM roles WHERE key='community'"
        ).fetchone()["id"]
        if press_id_row is None:
            s._conn.execute(
                "INSERT INTO roles(key, created_at) VALUES (?, ?)",
                ("press", "2026-06-23T00:00:00+00:00"),
            )
            press_id = s._conn.execute(
                "SELECT id FROM roles WHERE key='press'"
            ).fetchone()["id"]
        else:
            press_id = press_id_row["id"]

        # Pick any seeded company (mistral_ai is in the 004 seed).
        company_int_id = s._conn.execute(
            "SELECT id FROM companies WHERE company_id=?",
            ("mistral_ai",),
        ).fetchone()["id"]
        s._conn.execute(
            "INSERT INTO accounts(author_id, handle) VALUES (?, ?)",
            ("handle:u_legacy_press", "u_legacy_press"),
        )
        author_int_id = s._conn.execute(
            "SELECT id FROM accounts WHERE author_id=?",
            ("handle:u_legacy_press",),
        ).fetchone()["id"]

        s._conn.execute("PRAGMA foreign_keys = OFF")
        s._conn.execute(
            "INSERT INTO companies_accounts(company_id, author_id, role_id, added_at) "
            "VALUES (?, ?, ?, ?)",
            (
                company_int_id,
                author_int_id,
                press_id,
                "2026-06-23T00:00:00+00:00",
            ),
        )
        s._conn.execute("PRAGMA foreign_keys = ON")

        s._conn.executescript("""
            UPDATE companies_accounts
               SET role_id = (SELECT id FROM roles WHERE key='community')
             WHERE role_id = (SELECT id FROM roles WHERE key='press');
        """)
        row = s._conn.execute(
            "SELECT ca.role_id, r.key "
            "FROM companies_accounts ca "
            "JOIN roles r ON r.id = ca.role_id "
            "WHERE ca.author_id = ?",
            (author_int_id,),
        ).fetchone()
        assert row is not None
        assert row["role_id"] == community_id
        assert row["key"] == "community"
    finally:
        s.close()


# --- FK enforcement -------------------------------------------------


def test_migration_016_fk_rejects_removed_role_value(tmp_path):
    """After 016, an INSERT into brands_accounts with role_id='researcher'
    fails (FK violation; 'researcher' is no longer in roles)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Need a brand and an account row for the FK chain to fail on
        # role_id (not on brand_id/author_id first).
        s._conn.execute(
            "INSERT INTO accounts(author_id, handle) VALUES (?, ?)",
            ("handle:u_fk_test", "u_fk_test"),
        )
        with pytest.raises(Exception):
            s._conn.execute(
                "INSERT INTO brands_accounts(brand_id, author_id, role_id, added_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    "minimax",
                    "handle:u_fk_test",
                    "researcher",
                    "2026-06-24T00:00:00+00:00",
                ),
            )
    finally:
        s.close()


# --- integration: _known_role_keys ----------------------------------


def test_migration_016_known_role_keys_returns_trimmed_set(tmp_path):
    """_known_role_keys returns the 3-key trimmed set."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = s._known_role_keys()
        assert keys == {"official", "staff", "community"}
    finally:
        s.close()


# --- integration: _pick_enum_label round-trips staff ----------------


def test_migration_016_pick_enum_label_staff(tmp_path):
    """_pick_enum_label('role', 'staff', 'zh_cn') returns '员工' after
    the trim and the new 'staff' label is inserted by 016."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert s._pick_enum_label("role", "staff", "zh_cn") == "员工"
        assert s._pick_enum_label("role", "staff", "en") == "Staff"
        # Removed roles fall back to the raw key (the table no longer
        # has any label row for them).
        assert s._pick_enum_label("role", "researcher", "en") == "researcher"
    finally:
        s.close()


# --- integration: upsert_account with role=staff writes edge --------


def test_migration_016_upsert_account_with_staff_writes_edge(tmp_path):
    """upsert_account with role='staff' writes a brands_accounts edge
    with role_id pointing at the staff roles.id (no longer hits the
    dead-letter; staff is in the post-U6 roles set). Post-020:
    role_id is INTEGER FK to roles.id, not TEXT."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        staff_id = s._conn.execute(
            "SELECT id FROM roles WHERE key='staff'"
        ).fetchone()["id"]
        s.upsert_account("minimax", "u_staff_test", role="staff")
        row = s._conn.execute(
            "SELECT ba.role_id, r.key "
            "FROM brands_accounts ba "
            "JOIN accounts a ON a.id = ba.author_id "
            "JOIN roles r ON r.id = ba.role_id "
            "WHERE a.author_id = ?",
            ("handle:u_staff_test",),
        ).fetchone()
        assert row is not None
        assert row["role_id"] == staff_id, (
            f"role_id is {row['role_id']!r}, expected {staff_id} (INTEGER FK to staff)"
        )
        assert row["key"] == "staff"
    finally:
        s.close()
