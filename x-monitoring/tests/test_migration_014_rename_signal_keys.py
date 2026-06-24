"""Migration 014: rename signal_keys → signals.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 4 of 9, R4).

Verifies:
- signal_keys table no longer exists; signals exists after migration 014.
- signal_labels still exists (labels table name is unchanged).
- posts_brands_signals.signal column renamed to signal_id (still TEXT PK).
- Index idx_posts_brands_signals_brand_id_signal_id exists on the new
  column.
- The FK on posts_brands_signals.signal_id references signals(key).
- The 6 canonical signals are seeded (release, community_question, etc.).
- Idempotency: re-opening a DB that has 014 applied does not re-run it.
- Full stack apply: all migrations 001-014 apply on a fresh DB.
- Integration: insert_posts_brands_signals writes signal_id column;
  the FK guard still fires on unknown signals.
- Integration: _known_signal_keys still returns the seeded set.
"""

import pytest


# --- happy path: table renamed ------------------------------------


def test_migration_014_signal_keys_renamed_to_signals(tmp_path):
    """signal_keys does not exist; signals exists."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'signal_keys'"
        ).fetchall()
        assert rows == [], f"signal_keys still exists: {rows}"
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'signals'"
        ).fetchall()
        assert rows, "signals table not found"
    finally:
        s.close()


def test_migration_014_signal_labels_unchanged(tmp_path):
    """signal_labels (the labels table) is unchanged — it keeps its
    _labels suffix per the universal rule."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'signal_labels'"
        ).fetchall()
        assert rows, "signal_labels table missing"
    finally:
        s.close()


def test_migration_014_signals_seeded_with_six_keys(tmp_path):
    """The 6 canonical signals are seeded: release, community_question,
    criticism, commenter_capture, praise, other."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = {r[0] for r in s._conn.execute("SELECT key FROM signals").fetchall()}
        assert keys == {
            "release", "community_question", "criticism",
            "commenter_capture", "praise", "other",
        }
    finally:
        s.close()


# --- happy path: column renamed -----------------------------------


def test_migration_014_posts_brands_signals_signal_renamed_to_signal_id(tmp_path):
    """posts_brands_signals has signal_id (not signal)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1] for r in s._conn.execute(
                "PRAGMA table_info(posts_brands_signals)"
            ).fetchall()
        }
        assert "signal_id" in cols, f"signal_id missing. cols={cols}"
        assert "signal" not in cols, f"old `signal` column still present. cols={cols}"
    finally:
        s.close()


def test_migration_014_fk_on_signal_id_references_signals(tmp_path):
    """The FK on posts_brands_signals.signal_id references signals(key)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = s._conn.execute(
            "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
        ).fetchall()
        assert any(r[2] == "signals" and r[3] == "signal_id" for r in fks), (
            f"signal_id FK to signals missing. FKs found: {fks}"
        )
    finally:
        s.close()


def test_migration_014_index_rebuilt_on_signal_id(tmp_path):
    """The index idx_posts_brands_signals_brand_id_signal_id exists on
    posts_brands_signals(brand_id, signal_id)."""
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
        assert "idx_posts_brands_signals_brand_id_signal_id" in indexes, (
            f"new index missing. indexes={indexes}"
        )
        assert "idx_posts_brands_signals_brand_signal" not in indexes, (
            f"old index still present. indexes={indexes}"
        )
    finally:
        s.close()


# --- idempotency ---------------------------------------------------


def test_migration_014_idempotent(tmp_path):
    """Re-opening a DB that has 014 applied does not re-run it."""
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
        assert applied.count(14) == 1
    finally:
        s2.close()


# --- full stack apply ----------------------------------------------


def test_migration_014_full_stack_apply(tmp_path):
    """All migrations 001-015 apply on a fresh DB; the singular-noun
    enum table convention is in effect (signals + roles)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        assert applied == list(range(1, 16)), (
            f"unexpected versions: {applied}"
        )
        # Both singular enum tables are in effect.
        for tbl in ("signals", "signal_labels", "roles", "role_labels"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows, f"{tbl} missing"
        # Both old names are gone.
        for old in ("signal_keys", "role_keys"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (old,)
            ).fetchall()
            assert rows == [], f"{old} still exists after 014/015"
    finally:
        s.close()


# --- integration: insert_posts_brands_signals still works ---------


def test_migration_014_insert_posts_brands_signals_writes_signal_id(tmp_path):
    """insert_posts_brands_signals writes to the renamed signal_id column."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_014", "u_014", "2026-06-24T00:00:00+00:00"),
        )
        s.insert_posts_brands_signals("t_014", "minimax", "release")
        row = s._conn.execute(
            "SELECT signal_id FROM posts_brands_signals WHERE post_id = ?",
            ("t_014",),
        ).fetchone()
        assert row["signal_id"] == "release"
    finally:
        s.close()


def test_migration_014_unknown_signal_dead_lettered(tmp_path):
    """The FK guard still drops unknown signal values to the dead-letter."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_014_ghost", "u_014_ghost", "2026-06-24T00:00:00+00:00"),
        )
        s.insert_posts_brands_signals("t_014_ghost", "minimax", "ghost_signal")
        # Row not written.
        row = s._conn.execute(
            "SELECT * FROM posts_brands_signals WHERE post_id = ?",
            ("t_014_ghost",),
        ).fetchone()
        assert row is None
    finally:
        s.close()


# --- integration: _known_signal_keys still works -------------------


def test_migration_014_known_signal_keys_returns_seeded_set(tmp_path):
    """_known_signal_keys still returns the 6-key seeded set (now from
    the renamed signals table)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        keys = s._known_signal_keys()
        assert keys == {
            "release", "community_question", "criticism",
            "commenter_capture", "praise", "other",
        }
    finally:
        s.close()
