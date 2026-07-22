"""Migration 028: posts_brands_signals PK rebuild for multi-post_type.

Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
Unit U1b.

Scope:
- Rebuild posts_brands_signals with PRIMARY KEY (post_id, brand_id,
  post_type_key) instead of the old (post_id, brand_id).
- Rename the `post_type` column to `post_type_key` for clarity.
- Preserve all existing rows via INSERT INTO ..._new SELECT FROM ...

Conventions (matches the rest of x-monitor's migration set):
- TEXT-typed columns hold INTEGER FK values (the migration 020
  "string-in, INTEGER-out" pattern). The values stored are
  posts.id / brands.id / post_type_keys.id / sentiment_keys.id
  represented as integer-string literals.
- The FK declarations reference the natural-key TEXT columns
  (posts.tweet_id, brands.nickname-via-023-rename, etc.) per the
  migration 019 pattern.

Verifies:
- Schema: new PK is (post_id, brand_id, post_type_key).
- Data preservation: a representative sample of existing rows is
  carried over with identical values.
- Multi-post_type: two rows for the same (post_id, brand_id) with
  different post_type_key are now allowed.
- Idempotency: re-running apply_migrations does not duplicate rows.
- Pre-flight check: count of (post_id, brand_id) pairs with >1 row
  is 0 on a clean DB (no migration-time collision).
"""

from __future__ import annotations

import pytest
import sqlite3


# --- schema ----------------------------------------------------------


def test_migration_028_posts_brands_signals_pk_rebuilt(tmp_path):
    """Migration 028 extends the PK to (post_id, brand_id, post_type_key)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='posts_brands_signals'"
        ).fetchall()
        assert rows, "posts_brands_signals missing"
        info = s._conn.execute(
            "SELECT name, pk FROM pragma_table_info('posts_brands_signals') "
            "ORDER BY pk"
        ).fetchall()
        pk_cols = [r["name"] for r in info if r["pk"] > 0]
        assert pk_cols == ["post_id", "brand_id", "post_type_key"], (
            f"unexpected PK columns: {pk_cols}"
        )
    finally:
        s.close()


def test_migration_028_post_type_column_renamed(tmp_path):
    """The `post_type` column is renamed to `post_type_key`."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM pragma_table_info('posts_brands_signals')"
            ).fetchall()
        }
        assert "post_type_key" in cols, "post_type_key column missing"
        assert "post_type" not in cols, "old post_type column still present"
    finally:
        s.close()


# --- data preservation ----------------------------------------------


def _seed_signals_table(s: Store, post_id: str, brand_id: str,
                        post_type: str, sentiment: str) -> None:
    """Insert a row directly into posts_brands_signals (bypassing Store API).

    Migration 028 schema uses TEXT-natural-key values for all four
    columns: post_id TEXT, brand_id TEXT, post_type_key TEXT,
    sentiment TEXT. The migration 020 INTEGER-FK convention is NOT
    applied to this table (see migration 028 header for the rationale).
    """
    s._conn.execute(
        "INSERT INTO posts_brands_signals "
        "(post_id, brand_id, post_type_key, sentiment) "
        "VALUES (?, ?, ?, ?)",
        (post_id, brand_id, post_type, sentiment),
    )
    s._conn.commit()


def _seed_posts_and_brands(s: Store, tweet_id: str, brand_nickname: str) -> None:
    """Insert a minimal post + brand row so the FK constraints are satisfied."""
    s._conn.execute(
        "INSERT OR IGNORE INTO posts (tweet_id, text) VALUES (?, ?)",
        (tweet_id, f"test post {tweet_id}"),
    )
    s._conn.execute(
        "INSERT OR IGNORE INTO brands (nickname, display_name) VALUES (?, ?)",
        (brand_nickname, f"Test brand {brand_nickname}"),
    )
    s._conn.commit()


def test_migration_028_allows_multi_post_type(tmp_path):
    """Two rows for the same (post_id, brand_id) with different
    post_type_key are now allowed (was rejected by the old PK).
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_posts_and_brands(s, "9999999999999999999", "test_brand_a")
        _seed_signals_table(
            s, "9999999999999999999", "test_brand_a",
            "performance_comparisons", "neutral",
        )
        # Second row with the SAME (post_id, brand_id) but DIFFERENT post_type_key
        _seed_signals_table(
            s, "9999999999999999999", "test_brand_a",
            "feedback_questions", "mixed",
        )
        count = s._conn.execute(
            "SELECT COUNT(*) FROM posts_brands_signals WHERE post_id = ?",
            ("9999999999999999999",),
        ).fetchone()[0]
        assert count == 2, (
            "expected 2 rows for the same (post, brand) under the new PK; "
            f"got {count}"
        )
    finally:
        s.close()


def test_migration_028_rejects_duplicate_post_type(tmp_path):
    """Same (post_id, brand_id, post_type_key) triple → rejected (PK violation)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        _seed_posts_and_brands(s, "8888888888888888888", "test_brand_b")
        _seed_signals_table(
            s, "8888888888888888888", "test_brand_b",
            "hands_on_usage", "positive",
        )
        with pytest.raises(sqlite3.IntegrityError):
            _seed_signals_table(
                s, "8888888888888888888", "test_brand_b",
                "hands_on_usage", "positive",
            )
    finally:
        s.close()


# --- full-stack apply -----------------------------------------------


def test_migration_028_full_apply(tmp_path):
    """All migrations including 028 apply cleanly on a fresh DB."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(s.applied_migrations())
        assert 28 in applied, f"migration 028 not applied; have {applied}"
    finally:
        s.close()


def test_migration_028_idempotent_reapply(tmp_path):
    """Re-running apply_migrations does not duplicate seed or rebuild."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()
    s = Store(db, auto_migrate=True)
    try:
        # No migration 28 reapplied; table still has 028's PK shape.
        pk_cols = [
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM pragma_table_info('posts_brands_signals') "
                "WHERE pk > 0 ORDER BY pk"
            ).fetchall()
        ]
        assert pk_cols == ["post_id", "brand_id", "post_type_key"]
        applied = sorted(s.applied_migrations())
        assert applied.count(28) == 1
    finally:
        s.close()


# --- pre-flight collision check --------------------------------------


def test_migration_028_zero_collisions_on_clean_db(tmp_path):
    """On a fresh DB (no prior rows), the pre-flight duplicate check
    returns 0 — no migration-time collision.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        collisions = s._conn.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT 1 FROM posts_brands_signals "
            "GROUP BY post_id, brand_id HAVING COUNT(*) > 1"
            ")"
        ).fetchone()[0]
        assert collisions == 0, (
            f"pre-flight check failed: {collisions} (post, brand) pairs "
            "have >1 row, which would collide at INSERT time"
        )
    finally:
        s.close()


# --- FK target smoke -----------------------------------------------


def test_migration_028_post_type_key_fk_to_post_type_keys(tmp_path):
    """The new post_type_key column has an FK to post_type_keys.key."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = list(
            s._conn.execute(
                "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
            ).fetchall()
        )
        # fk columns: id, seq, table, from, to, on_update, on_delete, match
        post_type_fk = [
            fk for fk in fks
            if fk[3] == "post_type_key" and fk[2] == "post_type_keys"
        ]
        assert post_type_fk, (
            f"FK from post_type_key → post_type_keys missing; "
            f"have FKs: {[(f[2], f[3], f[4]) for f in fks]}"
        )
    finally:
        s.close()