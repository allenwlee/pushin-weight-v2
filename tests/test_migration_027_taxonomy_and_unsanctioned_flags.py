"""Migration 027: taxonomy extension + posts_unsanctioned_flags.

Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
Unit U1a.

Scope:
- Extend post_type_keys with `advertising_marketing` + `event_announcement`
  and matching labels (en + zh_cn).
- Extend discourse_keys with `advertising-marketing` (hyphenated per KTD7)
  and matching labels.
- Create posts_unsanctioned_flags table with:
    post_id TEXT PK (FK → posts.tweet_id ON DELETE CASCADE),
    flags TEXT NOT NULL (JSON array),
    flag_set TEXT GENERATED ALWAYS AS (json_extract(flags, '$')) STORED,
    evidence TEXT,
    decided_at TEXT NOT NULL.
- Index idx_unsanctioned_flag_set on the flag_set generated column.

Verifies:
- Schema: new tables + indexes + generated column exist after migration.
- Seeds: 2 new post_type_keys rows + 1 new discourse_keys row + matching
  labels.
- Happy path: insert a row with JSON flags array; flag_set populated
  automatically; read back via SELECT.
- Idempotency: INSERT OR IGNORE re-applies without duplicating.
- FK enforcement: insert with bogus post_id fails with FK violation.
- Empty flags array is accepted as valid.
"""

from __future__ import annotations

import sqlite3

import pytest


# --- schema ----------------------------------------------------------


def test_migration_027_posts_unsanctioned_flags_table_present(tmp_path):
    """Migration 027 creates the posts_unsanctioned_flags table."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='posts_unsanctioned_flags'"
        ).fetchall()
        assert rows, "posts_unsanctioned_flags table missing after 027"
    finally:
        s.close()


def test_migration_027_generated_column_flag_set_present(tmp_path):
    """flag_set is a STORED generated column from json_extract(flags, '$')."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name='posts_unsanctioned_flags'"
        ).fetchall()
        sql = rows[0]["sql"]
        assert "GENERATED ALWAYS AS (json_extract(flags, '$')) STORED" in sql, (
            f"flag_set generated column missing or wrong shape: {sql}"
        )
    finally:
        s.close()


def test_migration_027_index_on_flag_set_present(tmp_path):
    """idx_unsanctioned_flag_set exists on the flag_set column."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='posts_unsanctioned_flags' "
            "AND name='idx_unsanctioned_flag_set'"
        ).fetchall()
        assert rows, "idx_unsanctioned_flag_set missing"
    finally:
        s.close()


# --- seeds -----------------------------------------------------------


def test_migration_027_post_type_keys_extended(tmp_path):
    """advertising_marketing + event_announcement seeded into post_type_keys."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT key FROM post_type_keys WHERE key IN "
            "('advertising_marketing', 'event_announcement') ORDER BY key"
        ).fetchall()
        assert [r["key"] for r in rows] == [
            "advertising_marketing", "event_announcement"
        ], "missing one or both new post_type_keys"
    finally:
        s.close()


def test_migration_027_post_type_labels_extended(tmp_path):
    """Labels for the 2 new post_type_keys are seeded in en + zh_cn."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT key, lang, label FROM post_type_labels WHERE key IN "
            "('advertising_marketing', 'event_announcement') "
            "ORDER BY key, lang"
        ).fetchall()
        labels = {(r["key"], r["lang"]): r["label"] for r in rows}
        assert ("advertising_marketing", "en") in labels
        assert ("advertising_marketing", "zh_cn") in labels
        assert ("event_announcement", "en") in labels
        assert ("event_announcement", "zh_cn") in labels
    finally:
        s.close()


def test_migration_027_discourse_key_advertising_marketing_added(tmp_path):
    """The advertising-marketing (HYPHENATED) discourse key is seeded."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT key FROM discourse_keys WHERE key = 'advertising-marketing'"
        ).fetchall()
        assert rows, "discourse_keys row missing for 'advertising-marketing'"
        # Confirm the hyphen variant, not the underscore variant
        underscore_rows = s._conn.execute(
            "SELECT key FROM discourse_keys WHERE key = 'advertising_marketing'"
        ).fetchall()
        assert not underscore_rows, (
            "underscore variant 'advertising_marketing' should NOT be seeded; "
            "the key is intentionally hyphenated per plan KTD7"
        )
    finally:
        s.close()


def test_migration_027_discourse_labels_advertising_marketing_added(tmp_path):
    """Labels for advertising-marketing are seeded in en + zh_cn."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT lang, label FROM discourse_labels "
            "WHERE key = 'advertising-marketing' ORDER BY lang"
        ).fetchall()
        assert len(rows) == 2, "expected 2 labels for advertising-marketing"
        assert {r["lang"] for r in rows} == {"en", "zh_cn"}
    finally:
        s.close()


# --- CRUD -----------------------------------------------------------


def _insert_test_post(s: "Store", tweet_id: str) -> None:
    """Insert a minimal posts row so the FK to posts_unsanctioned_flags passes."""
    s._conn.execute(
        "INSERT OR IGNORE INTO posts (tweet_id, text) VALUES (?, ?)",
        (tweet_id, f"test post {tweet_id}"),
    )
    s._conn.commit()


def test_migration_027_insert_with_flags_array(tmp_path):
    """Insert a row with ['scam','crypto']; flag_set populates from JSON."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        tid = "9999999999999999999"
        _insert_test_post(s, tid)
        s._conn.execute(
            "INSERT INTO posts_unsanctioned_flags "
            "(post_id, flags, decided_at) VALUES (?, ?, ?)",
            (tid, '["scam","crypto"]', "2026-07-03T00:00:00+00:00"),
        )
        s._conn.commit()
        row = s._conn.execute(
            "SELECT post_id, flags, flag_set FROM posts_unsanctioned_flags "
            "WHERE post_id = ?",
            (tid,),
        ).fetchone()
        assert row["post_id"] == tid
        assert row["flags"] == '["scam","crypto"]'
        # The generated column extracts the JSON-as-text value.
        assert row["flag_set"] == '["scam","crypto"]'
    finally:
        s.close()


def test_migration_027_insert_with_empty_flags_array(tmp_path):
    """Empty flags array is a valid row (caller chose 'no flags')."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        tid = "8888888888888888888"
        _insert_test_post(s, tid)
        s._conn.execute(
            "INSERT INTO posts_unsanctioned_flags "
            "(post_id, flags, decided_at) VALUES (?, ?, ?)",
            (tid, "[]", "2026-07-03T00:00:00+00:00"),
        )
        s._conn.commit()
        row = s._conn.execute(
            "SELECT flags FROM posts_unsanctioned_flags WHERE post_id = ?",
            (tid,),
        ).fetchone()
        assert row["flags"] == "[]"
    finally:
        s.close()


def test_migration_027_insert_with_evidence(tmp_path):
    """Optional evidence column accepts text."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        tid = "7777777777777777777"
        _insert_test_post(s, tid)
        s._conn.execute(
            "INSERT INTO posts_unsanctioned_flags "
            "(post_id, flags, evidence, decided_at) VALUES (?, ?, ?, ?)",
            (
                tid,
                '["marketing_spam"]',
                "quoted: try free at example.com",
                "2026-07-03T00:00:00+00:00",
            ),
        )
        s._conn.commit()
        row = s._conn.execute(
            "SELECT evidence FROM posts_unsanctioned_flags WHERE post_id = ?",
            (tid,),
        ).fetchone()
        assert row["evidence"] == "quoted: try free at example.com"
    finally:
        s.close()


def test_migration_027_fk_violation_on_missing_post(tmp_path):
    """Insert with a post_id that doesn't exist in posts fails with FK error."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Enable FKs for this test (apply_migrations toggles them off
        # only during script execution; restore happens in finally).
        s._conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            s._conn.execute(
                "INSERT INTO posts_unsanctioned_flags "
                "(post_id, flags, decided_at) VALUES (?, ?, ?)",
                (
                    "0000000000000000000_nonexistent",
                    '["scam"]',
                    "2026-07-03T00:00:00+00:00",
                ),
            )
    finally:
        s.close()


def test_migration_027_duplicate_post_id_rejected(tmp_path):
    """PRIMARY KEY (post_id) rejects a second row for the same post."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        tid = "6666666666666666666"
        _insert_test_post(s, tid)
        s._conn.execute(
            "INSERT INTO posts_unsanctioned_flags "
            "(post_id, flags, decided_at) VALUES (?, ?, ?)",
            (tid, '["scam"]', "2026-07-03T00:00:00+00:00"),
        )
        s._conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            s._conn.execute(
                "INSERT INTO posts_unsanctioned_flags "
                "(post_id, flags, decided_at) VALUES (?, ?, ?)",
                (tid, '["crypto"]', "2026-07-03T00:00:01+00:00"),
            )
    finally:
        s.close()


def test_migration_027_idempotent_reapply(tmp_path):
    """Re-running apply_migrations does not duplicate seed rows."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()
    # Re-open and re-apply
    s = Store(db, auto_migrate=True)
    try:
        count_pt = s._conn.execute(
            "SELECT COUNT(*) FROM post_type_keys WHERE key = 'advertising_marketing'"
        ).fetchone()[0]
        assert count_pt == 1, "INSERT OR IGNORE should keep seed count = 1"
        count_disc = s._conn.execute(
            "SELECT COUNT(*) FROM discourse_keys WHERE key = 'advertising-marketing'"
        ).fetchone()[0]
        assert count_disc == 1
    finally:
        s.close()


# --- full-stack apply -----------------------------------------------


def test_migration_027_full_apply(tmp_path):
    """All migrations including 027 apply cleanly on a fresh DB."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(s.applied_migrations())
        assert 27 in applied, f"migration 027 not applied; have {applied}"
    finally:
        s.close()


# --- cascade delete -------------------------------------------------


def test_migration_027_cascade_delete_with_post(tmp_path):
    """Deleting a post removes its posts_unsanctioned_flags row."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute("PRAGMA foreign_keys = ON")
        tid = "5555555555555555555"
        _insert_test_post(s, tid)
        s._conn.execute(
            "INSERT INTO posts_unsanctioned_flags "
            "(post_id, flags, decided_at) VALUES (?, ?, ?)",
            (tid, '["crypto"]', "2026-07-03T00:00:00+00:00"),
        )
        s._conn.commit()
        before = s._conn.execute(
            "SELECT COUNT(*) FROM posts_unsanctioned_flags WHERE post_id = ?",
            (tid,),
        ).fetchone()[0]
        assert before == 1
        s._conn.execute("DELETE FROM posts WHERE tweet_id = ?", (tid,))
        s._conn.commit()
        after = s._conn.execute(
            "SELECT COUNT(*) FROM posts_unsanctioned_flags WHERE post_id = ?",
            (tid,),
        ).fetchone()[0]
        assert after == 0, "CASCADE delete should have removed the flags row"
    finally:
        s.close()