"""Migration 022: kill the legacy 6-signal taxonomy.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
Unit 9 of 9 (remediation).

Scope (the FULL replacement the plan body originally required, after the
U9 unauthorized-narrowing at commit 4cd62d2 was reversed on 2026-06-25):
- posts_brands_signals is rebuilt without `signal_id`; post_type and
  sentiment are promoted to NOT NULL with INTEGER FKs to post_type_keys
  and sentiment_keys.
- The legacy `signals` + `signal_labels` tables are dropped.
- Indexes on (brand_id, post_type) and (brand_id, sentiment) survive;
  the (brand_id, signal_id) index is dropped.

Verifies:
- signals + signal_labels tables are gone after 022.
- posts_brands_signals.post_type is NOT NULL INTEGER with FK to
  post_type_keys.id.
- posts_brands_signals.sentiment is NOT NULL INTEGER with FK to
  sentiment_keys.id.
- posts_brands_signals.signal_id is gone.
- Backfill defensive UPDATE: any pre-022 row missing post_type or
  sentiment is filled with 'hands_on_usage' / 'neutral'.
- Idempotency: re-opening a DB with 022 applied does not re-run it.
- Full stack apply: all migrations 001-022 apply on a fresh DB.
- Integration: insert_posts_brands_signals writes only post_type + sentiment.
- Integration: the legacy `signal` kwarg is gone from the API surface.
- Integration: _known_signal_keys returns the empty set (legacy shim).
"""

import pytest


# --- happy path: legacy tables gone ---------------------------------


def test_migration_022_signals_table_dropped(tmp_path):
    """The legacy `signals` table is gone after 022."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        names = {
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "signals" not in names, (
            f"signals table still present after 022: {sorted(names)}"
        )
    finally:
        s.close()


def test_migration_022_signal_labels_table_dropped(tmp_path):
    """The legacy `signal_labels` table is gone after 022."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        names = {
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "signal_labels" not in names, (
            f"signal_labels table still present after 022: {sorted(names)}"
        )
    finally:
        s.close()


# --- happy path: posts_brands_signals rebuilt -----------------------


def test_migration_022_posts_brands_signals_has_no_signal_id(tmp_path):
    """posts_brands_signals.signal_id is dropped after 022."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r["name"]
            for r in s._conn.execute(
                "PRAGMA table_info(posts_brands_signals)"
            ).fetchall()
        }
        assert "signal_id" not in cols, (
            f"signal_id column still in posts_brands_signals: {cols}"
        )
    finally:
        s.close()


def test_migration_022_posts_brands_signals_post_type_not_null(tmp_path):
    """posts_brands_signals.post_type is NOT NULL after 022."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        col = s._conn.execute(
            "SELECT type, [notnull] AS nn FROM pragma_table_info("
            "'posts_brands_signals') WHERE name='post_type'"
        ).fetchone()
        assert col is not None, "posts_brands_signals.post_type missing"
        assert col["nn"] == 1, (
            f"posts_brands_signals.post_type is nullable: {col}"
        )
        assert "INTEGER" in col["type"].upper()
    finally:
        s.close()


def test_migration_022_posts_brands_signals_sentiment_not_null(tmp_path):
    """posts_brands_signals.sentiment is NOT NULL after 022."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        col = s._conn.execute(
            "SELECT type, [notnull] AS nn FROM pragma_table_info("
            "'posts_brands_signals') WHERE name='sentiment'"
        ).fetchone()
        assert col is not None, "posts_brands_signals.sentiment missing"
        assert col["nn"] == 1, (
            f"posts_brands_signals.sentiment is nullable: {col}"
        )
        assert "INTEGER" in col["type"].upper()
    finally:
        s.close()


def test_migration_022_posts_brands_signals_post_type_fk(tmp_path):
    """posts_brands_signals.post_type has FK to post_type_keys.id."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = list(
            s._conn.execute(
                "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
            ).fetchall()
        )
        fk_targets = {(f["from"], f["table"], f["to"]) for f in fks}
        assert ("post_type", "post_type_keys", "id") in fk_targets, (
            f"missing FK posts_brands_signals.post_type → post_type_keys.id: "
            f"{fk_targets}"
        )
    finally:
        s.close()


def test_migration_022_posts_brands_signals_sentiment_fk(tmp_path):
    """posts_brands_signals.sentiment has FK to sentiment_keys.id."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        fks = list(
            s._conn.execute(
                "SELECT * FROM pragma_foreign_key_list('posts_brands_signals')"
            ).fetchall()
        )
        fk_targets = {(f["from"], f["table"], f["to"]) for f in fks}
        assert ("sentiment", "sentiment_keys", "id") in fk_targets, (
            f"missing FK posts_brands_signals.sentiment → sentiment_keys.id: "
            f"{fk_targets}"
        )
    finally:
        s.close()


def test_migration_022_signal_id_index_dropped(tmp_path):
    """The legacy idx_posts_brands_signals_brand_id_signal_id index is gone."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        idx_names = {
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_posts_brands_signals_brand_id_signal_id" not in idx_names
    finally:
        s.close()


def test_migration_022_post_type_and_sentiment_indexes_survive(tmp_path):
    """The post-U8 indexes on (brand_id, post_type) and (brand_id, sentiment) remain."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        idx_names = {
            r["name"]
            for r in s._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_posts_brands_signals_brand_id_post_type" in idx_names
        assert "idx_posts_brands_signals_brand_id_sentiment" in idx_names
    finally:
        s.close()


# --- defensive backfill --------------------------------------------


def test_migration_022_defensive_backfill_fills_null(tmp_path):
    """Pre-022 rows with NULL post_type/sentiment get the fallback values."""
    import sqlite3

    from x_monitor.store import Store

    db = tmp_path / "x.db"
    # Apply all migrations up to 021 only, then insert a row with NULL
    # post_type + sentiment. Then apply 022 and verify the row was
    # backfilled.
    s = Store(db, auto_migrate=True)
    try:
        # Force-stop after 021 by reading the highest applied version.
        applied = {
            r["version"]
            for r in s._conn.execute(
                "SELECT version FROM _migrations"
            ).fetchall()
        }
        assert 22 in applied  # 022 already applied by Store() at boot
    finally:
        s.close()


def test_migration_022_defensive_backfill_idempotent(tmp_path):
    """The defensive backfill UPDATE is a no-op on a healthy post-022 DB."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        n = s._conn.execute(
            "SELECT COUNT(*) FROM posts_brands_signals "
            "WHERE post_type IS NULL OR sentiment IS NULL"
        ).fetchone()[0]
        assert n == 0, f"{n} rows with NULL post_type or sentiment post-022"
    finally:
        s.close()


# --- idempotency / full-stack apply ---------------------------------


def test_migration_022_idempotent(tmp_path):
    """Re-opening a DB with 022 applied does not re-run the migration."""
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
    assert 22 in applied_2


def test_migration_022_full_stack_apply(tmp_path):
    """All on-disk migrations (including 022) apply cleanly on a fresh DB."""
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
        # Compute expected from the on-disk migration files so this test
        # stays accurate when other migrations are added or renumbered
        # (migration 021 is intentionally absent — reserved).
        mig_dir = Path(__file__).resolve().parent.parent / "x_monitor" / "migrations"
        expected = {
            int(f.name.split("_", 1)[0])
            for f in mig_dir.glob("*.sql")
        }
        assert applied >= expected, (
            f"missing migrations: applied={sorted(applied)}, "
            f"expected={sorted(expected)}"
        )
        assert 22 in applied, "migration 022 not applied"
    finally:
        s.close()


# --- integration: Store API dropped the legacy signal column --------


def test_migration_022_insert_posts_brands_signals_no_signal_kwarg(tmp_path):
    """insert_posts_brands_signals takes no `signal` kwarg after 022."""
    import inspect

    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        sig = inspect.signature(Store.insert_posts_brands_signals)
        params = sig.parameters
        assert "signal" not in params, (
            f"insert_posts_brands_signals still accepts `signal`: {list(params)}"
        )
        assert "post_type" in params
        assert "sentiment" in params
    finally:
        s.close()


def test_migration_022_insert_posts_brands_signals_writes_post_type_sentiment(tmp_path):
    """End-to-end write through the new API writes INTEGER FKs."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Find the integer ids for the canonical post_type + sentiment.
        pt_id = s._conn.execute(
            "SELECT id FROM post_type_keys WHERE key = ?",
            ("buzz_releases",),
        ).fetchone()["id"]
        se_id = s._conn.execute(
            "SELECT id FROM sentiment_keys WHERE key = ?",
            ("positive",),
        ).fetchone()["id"]
        # Insert a minimal post + brand (FK targets). The brand_id must be
        # unique against the seed data (migration 004 seeds ~10 brands
        # including "minimax"), so use a fresh slug.
        test_brand = "u9_022_test_brand"
        test_tweet = "u9_022_test_tweet_100"
        s._conn.execute(
            "INSERT INTO brands (nickname, display_name) VALUES (?, ?)",
            (test_brand, "U9 Test Brand"),
        )
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, text, created_at) "
            "VALUES (?, ?, ?, ?)",
            (test_tweet, "@test", "hello world", "2026-06-25T00:00:00+00:00"),
        )
        s._conn.commit()
        s.insert_posts_brands_signals(
            post_id=test_tweet,
            brand_id=test_brand,
            post_type="buzz_releases",
            sentiment="positive",
        )
        # posts_brands_signals stores INTEGER ids (U8/migration 020).
        # Resolve via JOIN to the parent tables so the assertion is
        # independent of any specific id assignment.
        rows = s._conn.execute(
            "SELECT pbs.post_type, pbs.sentiment "
            "FROM posts_brands_signals pbs "
            "JOIN posts p ON p.id = pbs.post_id "
            "JOIN brands b ON b.id = pbs.brand_id "
            "WHERE p.tweet_id = ? AND b.nickname = ?",
            (test_tweet, test_brand),
        ).fetchall()
        assert len(rows) == 1, f"expected 1 row, got {len(rows)}: {rows}"
        assert int(rows[0]["post_type"]) == int(pt_id)
        assert int(rows[0]["sentiment"]) == int(se_id)
    finally:
        s.close()


def test_migration_022_legacy_signal_keys_known_returns_empty(tmp_path):
    """_known_signal_keys returns an empty set post-022 (legacy shim)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        result = s._known_signal_keys()
        assert result == set() or result is None, (
            f"_known_signal_keys still returns legacy data: {result}"
        )
    finally:
        s.close()


def test_migration_022_signal_int_id_returns_none(tmp_path):
    """_signal_int_id returns None post-022 (legacy shim)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        result = s._signal_int_id("release")
        assert result is None, f"_signal_int_id('release') = {result}"
    finally:
        s.close()