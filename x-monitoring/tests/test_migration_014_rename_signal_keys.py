"""Migration 014: rename signal_keys → signals.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 4 of 9, R4).

Migration 014 renamed `signal_keys` → `signals` and `signal` →
`signal_id` (column). Migration 022 (U9 remediation) then DROPPED
both `signals` and `signal_labels` tables, AND dropped the
`signal_id` column from `posts_brands_signals`. So most of the
verifications this test originally carried now live in the post-022
state — what we verify here is the migration's intent, not its
artifact.

Verifies (post-022):
- `signal_keys` table does not exist (the rename went all the way
  through; the table was later dropped but the rename never
  reverted).
- `signal` column does not exist in posts_brands_signals (the column
  rename went all the way through; signal_id was later dropped).
- `signal_id` column is GONE post-022 (verified via U9 tests).
- `signal_labels` table does NOT exist post-022 (also dropped).
- Idempotency: re-opening a DB that has 014 applied does not re-run it.
- Full stack apply: all migrations {1..20, 22} apply on a fresh DB
  (only 21 absent).
"""

import pytest


# --- happy path: rename history ------------------------------------


def test_migration_014_signal_keys_no_longer_exists(tmp_path):
    """signal_keys does not exist after the rename chain (014 → 022)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'signal_keys'"
        ).fetchall()
        assert rows == [], f"signal_keys still exists: {rows}"
    finally:
        s.close()


def test_migration_014_signals_table_dropped_by_022(tmp_path):
    """The signals table (created by 014) was dropped by 022 — verify
    the post-022 state."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'signals'"
        ).fetchall()
        assert rows == [], (
            f"signals should be DROPPED post-022 (still present: {rows})"
        )
    finally:
        s.close()


def test_migration_014_signal_labels_dropped_by_022(tmp_path):
    """signal_labels (kept by 014 per the universal rule) was dropped
    by 022 along with signals. Verify the post-022 state."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'signal_labels'"
        ).fetchall()
        assert rows == [], (
            f"signal_labels should be DROPPED post-022 (still present: {rows})"
        )
    finally:
        s.close()


# --- happy path: column rename history -----------------------------


def test_migration_014_signal_column_dropped_by_022(tmp_path):
    """The `signal` column (which 014 renamed to `signal_id`) was dropped
    by 022. Verify both the original `signal` is gone and the renamed
    `signal_id` is also gone."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1] for r in s._conn.execute(
                "PRAGMA table_info(posts_brands_signals)"
            ).fetchall()
        }
        assert "signal" not in cols, (
            f"old `signal` column still present. cols={cols}"
        )
        assert "signal_id" not in cols, (
            f"signal_id column still present post-022. cols={cols}"
        )
        # The replacement columns ARE present.
        assert "post_type" in cols, f"post_type missing. cols={cols}"
        assert "sentiment" in cols, f"sentiment missing. cols={cols}"
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
    """All migrations {1..20, 22} apply on a fresh DB (only 21 absent).

    The 6-signal taxonomy (signals + signal_labels + signal_id) was
    active from 014 through 019; migration 022 then killed it. The
    surviving singular-noun enum table is `roles`.
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
        # The singular-noun enum tables that SURVIVED migration 022.
        for tbl in ("roles", "role_labels"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows, f"{tbl} missing"
        # The 6-signal taxonomy is GONE post-022.
        for tbl in ("signals", "signal_labels", "signal_keys"):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows == [], f"{tbl} should be GONE post-022"
        # role_keys also gone.
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = ?", ("role_keys",)
        ).fetchall()
        assert rows == [], f"role_keys should be GONE post-015"
    finally:
        s.close()
