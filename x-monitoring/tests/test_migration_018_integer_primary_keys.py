"""Migration 018: INTEGER primary keys for enum tables (signals, roles).

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 8 of 9).

Scope (per the migration file):
- Rebuild `signals` with `id INTEGER PRIMARY KEY AUTOINCREMENT`,
  `key TEXT NOT NULL UNIQUE`, `created_at TEXT NOT NULL`.
- Rebuild `roles` with the same shape.
- signal_labels / role_labels FK columns (key TEXT) continue to reference
  signals.key / roles.key — no rebuild needed because UNIQUE is a valid
  FK target in SQLite.
- posts_brands_signals.signal_id, brands_accounts.role_id,
  companies_accounts.role_id STAY as TEXT columns holding the key string.
  No consumer-side changes.

Verifies:
- signals table has `id INTEGER PRIMARY KEY AUTOINCREMENT`.
- signals.key is UNIQUE NOT NULL.
- signals.id auto-assigns 1..N (one row per seeded key).
- roles table has the same INTEGER id PK shape.
- signal_labels FK to signals.key still validates (FK pragma).
- role_labels FK to roles.key still validates (FK pragma).
- posts_brands_signals.signal_id TEXT FK to signals.key still validates.
- brands_accounts.role_id TEXT FK to roles.key still validates.
- companies_accounts.role_id TEXT FK to roles.key still validates.
- Idempotency: re-opening a DB that has 018 applied does not re-run it.
- Full stack apply: all migrations 001-018 apply on a fresh DB.
- Integration: insert_posts_brands_signals writes TEXT signal_id (the key).
- Integration: upsert_account writes TEXT role_id (the key).
- Integration: _known_signal_keys returns 6 string keys.
- Integration: _known_role_keys returns 3 string keys.
- Integration: dead-letter guard still drops unknown keys.
- AUTOINCREMENT: ids are monotonically increasing.
"""

import pytest


# --- happy path: signals PK is INTEGER -----------------------------


def test_migration_018_signals_has_integer_id_pk(tmp_path):
    """signals has `id INTEGER PRIMARY KEY AUTOINCREMENT`."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
        cols = s._conn.execute("PRAGMA table_info(signals)").fetchall()
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


def test_migration_018_signals_key_is_unique_not_null(tmp_path):
    """signals.key is TEXT NOT NULL UNIQUE (was the old PK)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = s._conn.execute("PRAGMA table_info(signals)").fetchall()
        col_map = {r["name"]: r for r in cols}
        assert col_map["key"]["notnull"] == 1, (
            f"key is not NOT NULL. col={col_map['key']}"
        )
        # UNIQUE constraint can be detected via pragma index_list.
        idx_rows = s._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='signals'"
        ).fetchall()
        idx_names = {r[0] for r in idx_rows}
        # SQLite auto-creates a UNIQUE index for the UNIQUE column.
        # The index name follows the pattern sqlite_autoindex_signals_N.
        auto_unique = {n for n in idx_names if n.startswith("sqlite_autoindex_signals_")}
        assert auto_unique, (
            f"no UNIQUE auto-index on signals.key. indexes={idx_names}"
        )
    finally:
        s.close()


def test_migration_018_signals_id_auto_assigned(tmp_path):
    """signals has 6 rows with ids 1..6 (one per seeded key)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT id, key FROM signals ORDER BY id"
        ).fetchall()
        assert len(rows) == 6, f"expected 6 signals rows, got {len(rows)}"
        ids = [r["id"] for r in rows]
        assert ids == [1, 2, 3, 4, 5, 6], f"unexpected ids: {ids}"
        # Every id is an int (not str).
        for r in rows:
            assert isinstance(r["id"], int), f"id is {type(r['id']).__name__}, not int"
    finally:
        s.close()


def test_migration_018_signals_keys_preserved(tmp_path):
    """The 6 canonical signal keys are present after the rebuild."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {r["key"] for r in s._conn.execute("SELECT key FROM signals").fetchall()}
        assert keys == {
            "release", "community_question", "criticism",
            "commenter_capture", "praise", "other",
        }, f"unexpected signals keys: {keys}"
    finally:
        s.close()


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


# --- happy path: labels FK still resolves ---------------------------


def test_migration_018_signal_labels_fk_to_signals_key(tmp_path):
    """signal_labels.key FK still references signals.key (the UNIQUE
    column in the rebuilt signals table)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('signal_labels')"
        ).fetchall()
        # pragma_foreign_key_list columns: (id, seq, table, from, to, ...)
        assert any(r[2] == "signals" and r[3] == "key" and r[4] == "key" for r in fks), (
            f"signal_labels FK to signals.key missing. FKs found: {fks}"
        )
    finally:
        s.close()


def test_migration_018_role_labels_fk_to_roles_key(tmp_path):
    """role_labels.key FK still references roles.key."""
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


# --- happy path: child table FKs still validate ---------------------


def test_migration_018_posts_brands_signals_signal_id_text_fk(tmp_path):
    """posts_brands_signals.signal_id is still TEXT and still FKs to
    signals.key (which is now UNIQUE)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = s._conn.execute(
            "PRAGMA table_info(posts_brands_signals)"
        ).fetchall()
        col_map = {r["name"]: r for r in cols}
        assert "signal_id" in col_map, "signal_id column missing"
        assert "TEXT" in col_map["signal_id"]["type"].upper(), (
            f"signal_id type is {col_map['signal_id']['type']!r}, expected TEXT"
        )
        # FK resolves to signals.key (TEXT column, UNIQUE).
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        assert any(
            r[2] == "signals" and r[3] == "signal_id" and r[4] == "key"
            for r in fks
        ), f"signal_id FK to signals.key missing. FKs found: {fks}"
    finally:
        s.close()


def test_migration_018_brands_accounts_role_id_text_fk(tmp_path):
    """brands_accounts.role_id is still TEXT and still FKs to roles.key."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = s._conn.execute(
            "PRAGMA table_info(brands_accounts)"
        ).fetchall()
        col_map = {r["name"]: r for r in cols}
        assert "role_id" in col_map, "role_id column missing"
        assert "TEXT" in col_map["role_id"]["type"].upper(), (
            f"role_id type is {col_map['role_id']['type']!r}, expected TEXT"
        )
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('brands_accounts')"
        ).fetchall()
        assert any(
            r[2] == "roles" and r[3] == "role_id" and r[4] == "key"
            for r in fks
        ), f"role_id FK to roles.key missing. FKs found: {fks}"
    finally:
        s.close()


def test_migration_018_companies_accounts_role_id_text_fk(tmp_path):
    """companies_accounts.role_id is still TEXT and still FKs to roles.key."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = s._conn.execute(
            "PRAGMA table_info(companies_accounts)"
        ).fetchall()
        col_map = {r["name"]: r for r in cols}
        assert "role_id" in col_map, "role_id column missing"
        assert "TEXT" in col_map["role_id"]["type"].upper(), (
            f"role_id type is {col_map['role_id']['type']!r}, expected TEXT"
        )
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('companies_accounts')"
        ).fetchall()
        assert any(
            r[2] == "roles" and r[3] == "role_id" and r[4] == "key"
            for r in fks
        ), f"role_id FK to roles.key missing. FKs found: {fks}"
    finally:
        s.close()


# --- happy path: indexes preserved ----------------------------------


def test_migration_018_indexes_preserved(tmp_path):
    """The 3 indexes on the FK columns are still present."""
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
            "idx_posts_brands_signals_brand_id_signal_id",
            "idx_brands_accounts_role_id",
            "idx_companies_accounts_role_id",
        ):
            assert idx in indexes, f"{idx} missing"
    finally:
        s.close()


# --- idempotency ----------------------------------------------------


def test_migration_018_idempotent(tmp_path):
    """Re-opening a DB that has 018 applied does not re-run it."""
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
        # Row counts unchanged.
        n_sig = s2._conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        n_role = s2._conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
        assert n_sig == 6, f"signals has {n_sig} rows after re-open"
        assert n_role == 3, f"roles has {n_role} rows after re-open"
    finally:
        s2.close()


# --- full stack apply -----------------------------------------------


def test_migration_018_full_stack_apply(tmp_path):
    """All migrations 001-018 apply on a fresh DB; the integer-PK
    convention is in effect on signals + roles."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        assert applied == list(range(1, 20)), (
            f"unexpected versions: {applied}"
        )
        # Both enum tables have INTEGER id PK.
        for tbl in ("signals", "roles"):
            col = s._conn.execute(
                f"SELECT type, pk FROM pragma_table_info('{tbl}') WHERE name='id'"
            ).fetchone()
            assert col is not None, f"{tbl}.id missing"
            assert "INTEGER" in col["type"].upper(), (
                f"{tbl}.id type is {col['type']!r}"
            )
            assert col["pk"] == 1, f"{tbl}.id is not PK"
    finally:
        s.close()


# --- integration: insert paths still write TEXT key -----------------


def test_migration_018_insert_posts_brands_signals_writes_text_key(tmp_path):
    """insert_posts_brands_signals still writes the string key to
    signal_id (TEXT FK to signals.key, no change)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_018", "u_018", "2026-06-24T00:00:00+00:00"),
        )
        s.insert_posts_brands_signals("t_018", "minimax", "release")
        row = s._conn.execute(
            "SELECT signal_id FROM posts_brands_signals WHERE post_id = ?",
            ("t_018",),
        ).fetchone()
        assert row is not None
        assert row["signal_id"] == "release", (
            f"signal_id is {row['signal_id']!r}, expected 'release'"
        )
    finally:
        s.close()


def test_migration_018_upsert_account_writes_text_role(tmp_path):
    """upsert_account still writes the string role to brands_accounts.role_id."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.upsert_account("minimax", "u_018", role="official")
        row = s._conn.execute(
            "SELECT role_id FROM brands_accounts WHERE author_id = ?",
            ("handle:u_018",),
        ).fetchone()
        assert row is not None
        assert row["role_id"] == "official", (
            f"role_id is {row['role_id']!r}, expected 'official'"
        )
    finally:
        s.close()


# --- integration: dead-letter guard still fires ---------------------


def test_migration_018_unknown_signal_dead_lettered(tmp_path):
    """The FK guard still drops unknown signal values to the dead-letter."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_018_ghost", "u_018_ghost", "2026-06-24T00:00:00+00:00"),
        )
        s.insert_posts_brands_signals("t_018_ghost", "minimax", "ghost_signal")
        row = s._conn.execute(
            "SELECT * FROM posts_brands_signals WHERE post_id = ?",
            ("t_018_ghost",),
        ).fetchone()
        assert row is None, "unknown signal was not dead-lettered"
    finally:
        s.close()


def test_migration_018_unknown_role_dead_lettered(tmp_path):
    """The FK guard still drops unknown role values to the dead-letter."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.upsert_account("minimax", "u_018_ghost", role="ghost_role")
        row = s._conn.execute(
            "SELECT * FROM brands_accounts WHERE author_id = ?",
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


def test_migration_018_known_signal_keys_returns_seeded_set(tmp_path):
    """_known_signal_keys still returns the 6-key seeded set of strings."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = s._known_signal_keys()
        assert keys == {
            "release", "community_question", "criticism",
            "commenter_capture", "praise", "other",
        }, f"unexpected signal keys: {keys}"
    finally:
        s.close()


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
    """Adding a new signal via INSERT OR IGNORE assigns id 7
    (one past the highest pre-existing id). AUTOINCREMENT never reuses."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        max_id_before = s._conn.execute(
            "SELECT MAX(id) AS m FROM signals"
        ).fetchone()["m"]
        # Add a new signal row directly (mirrors the seed INSERT OR IGNORE
        # pattern in migration 016 for roles).
        s._conn.execute(
            "INSERT INTO signals (key, created_at) VALUES (?, ?)",
            ("test_new_signal", "2026-06-24T00:00:00+00:00"),
        )
        new_row = s._conn.execute(
            "SELECT id FROM signals WHERE key = ?",
            ("test_new_signal",),
        ).fetchone()
        assert new_row is not None
        assert new_row["id"] > max_id_before, (
            f"new id {new_row['id']} should be > max pre-existing id {max_id_before}"
        )
        # And the id is an INTEGER (not TEXT).
        assert isinstance(new_row["id"], int), (
            f"new id is {type(new_row['id']).__name__}, not int"
        )
    finally:
        s.close()


# --- integration: read paths still return string keys ---------------


def test_migration_018_treemap_polarity_returns_string_keys(tmp_path):
    """treemap.compute_polarity_signal_breakdown's result dict still uses
    string keys (signal_id column is still TEXT)."""
    from x_monitor.store import Store
    from x_monitor import treemap

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Seed a post + brand edge + signal row.
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at, "
            "created_at_epoch) VALUES (?, ?, ?, ?)",
            (
                "t_treemap", "u_t", "2026-06-24T00:00:00+00:00",
                1761321600,  # 2026-06-24 epoch
            ),
        )
        s._conn.execute(
            "INSERT INTO posts_brands(brand_id, post_id, weight) "
            "VALUES (?, ?, ?)",
            ("minimax", "t_treemap", 1.0),
        )
        s.insert_posts_brands_signals("t_treemap", "minimax", "praise")

        breakdown = treemap.compute_polarity_signal_breakdown(
            s._conn, "minimax", "0",
        )
        assert isinstance(breakdown, dict)
        # The keys are string signal names (post-018 still TEXT).
        for k in breakdown:
            assert isinstance(k, str), (
                f"breakdown key {k!r} is {type(k).__name__}, not str"
            )
        assert "praise" in breakdown, f"praise missing from {breakdown}"
    finally:
        s.close()
