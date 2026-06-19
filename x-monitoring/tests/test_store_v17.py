# {{AGENT_ATTRIBUTION}}
"""v1.7 tests for x_monitor.store: migration 003 + translation columns.

v1.7 adds 4 columns to `posts`:
  - text_en        TEXT
  - text_zh_cn     TEXT
  - lang_detected  TEXT
  - signal         TEXT  (post-fetch classify_signal() result)

and 2 new store methods:
  - bulk_update_translations(rows) -> int
  - get_posts_missing_translations(locale, limit) -> list[dict]

The migration 003 is forward-only and applies on top of 001 + 002.

These tests verify:
  - migration 003 applies cleanly on a fresh DB and on a DB with 001+002
  - insert_posts accepts and stores the 4 new columns
  - bulk_update_translations is idempotent and transactional
  - get_posts_missing_translations returns rows in newest-first order
  - bulk_update_translations with an empty list is a no-op
  - bulk_update_translations with a missing tweet_id is silently skipped
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# --- v1.7 migration 003 -------------------------------------------------


def test_migration_003_applies_on_fresh_db(tmp_path):
    """Migration 003 applies on a brand-new DB (no 001/002 needed — Store
    auto-applies all in order). The 4 new columns are present after."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute("PRAGMA table_info(posts)").fetchall()
        cols = {r[1] for r in rows}
        assert "text_en" in cols
        assert "text_zh_cn" in cols
        assert "lang_detected" in cols
        # migration 004 dropped posts.signal (per Decision 1, R6d); columns that were here are now in post_brand_signals
        # Confirm the migration was actually recorded.
        applied = {
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        }
        assert 3 in applied and 4 in applied
    finally:
        s.close()


def test_migration_003_idempotent(tmp_path):
    """Re-opening a DB that already has 003 applied does not re-run it."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s1 = Store(db, auto_migrate=True)
    s1.close()
    # Second open
    s2 = Store(db, auto_migrate=True)
    try:
        applied = [
            r[0]
            for r in s2._conn.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        ]
        # No duplicate version 3 in the migrations table.
        assert applied.count(3) == 1
    finally:
        s2.close()


# --- v1.7 insert_posts: new columns ------------------------------------


def test_insert_posts_accepts_translation_columns(tmp_path):
    """insert_posts accepts posts with text_en, text_zh_cn, lang_detected, signal."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        n = s.insert_posts([
            {
                "id": "t1",
                "brand_id": "minimax",
                "author_handle": "u1",
                "text": "海螺AI 最新版本",
                "text_en": "Hailuo AI latest version",
                "text_zh_cn": "海螺AI 最新版本",  # noop (already zh-CN)
                "lang_detected": "zh-Hans",
                "signal": "release",
            }
        ])
        assert n == 1
        row = s._conn.execute(
            "SELECT text_en, text_zh_cn, lang_detected, signal "
            "FROM posts WHERE tweet_id = 't1'"
        ).fetchone()
        assert row["text_en"] == "Hailuo AI latest version"
        assert row["text_zh_cn"] == "海螺AI 最新版本"
        assert row["lang_detected"] == "zh-Hans"
        # signal moved to post_brand_signals in migration 004 (R6d, Decision 18)
    finally:
        s.close()


def test_insert_posts_without_translation_columns_stores_null(tmp_path):
    """Legacy posts (no translation fields) insert with NULL — back-compat."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.insert_posts([
            {
                "id": "t2",
                "brand_id": "minimax",
                "author_handle": "u2",
                "text": "minimax is great",
                # no text_en / text_zh_cn / lang_detected / signal
            }
        ])
        row = s._conn.execute(
            "SELECT text_en, text_zh_cn, lang_detected, signal "
            "FROM posts WHERE tweet_id = 't2'"
        ).fetchone()
        assert row["text_en"] is None
        assert row["text_zh_cn"] is None
        assert row["lang_detected"] is None
        # signal moved to post_brand_signals in migration 004
    finally:
        s.close()


# --- v1.7 bulk_update_translations --------------------------------------


def test_bulk_update_translations_updates_rows(tmp_path):
    """bulk_update_translations writes the 3 new columns for known tweet_ids."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.insert_posts([
            {"id": "t1", "brand_id": "minimax", "text": "海螺AI"},
            {"id": "t2", "brand_id": "qwen", "text": "Qwen is great"},
            {"id": "t3", "brand_id": "deepseek", "text": "DeepSeek-V3"},
        ])
        updated = s.bulk_update_translations([
            {
                "tweet_id": "t1",
                "text_en": "Hailuo AI",
                "text_zh_cn": "海螺AI",
                "lang_detected": "zh-Hans",
            },
            {
                "tweet_id": "t2",
                "text_en": "Qwen is great",  # noop
                "text_zh_cn": "Qwen很棒",
                "lang_detected": "en",
            },
        ])
        assert updated == 2
        # Verify the rows.
        r1 = s._conn.execute(
            "SELECT text_en, text_zh_cn, lang_detected FROM posts "
            "WHERE tweet_id='t1'"
        ).fetchone()
        assert r1["text_en"] == "Hailuo AI"
        assert r1["lang_detected"] == "zh-Hans"
        r2 = s._conn.execute(
            "SELECT text_en, text_zh_cn, lang_detected FROM posts "
            "WHERE tweet_id='t2'"
        ).fetchone()
        assert r2["text_zh_cn"] == "Qwen很棒"
        # t3 unchanged (still NULL).
        r3 = s._conn.execute(
            "SELECT text_en, text_zh_cn FROM posts WHERE tweet_id='t3'"
        ).fetchone()
        assert r3["text_en"] is None
    finally:
        s.close()


def test_bulk_update_translations_idempotent(tmp_path):
    """Re-running the same bulk_update is a no-op (writes the same values)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.insert_posts([{"id": "t1", "brand_id": "minimax", "text": "x"}])
        rows = [{
            "tweet_id": "t1",
            "text_en": "x",
            "text_zh_cn": "x",
            "lang_detected": "en",
        }]
        n1 = s.bulk_update_translations(rows)
        n2 = s.bulk_update_translations(rows)
        # First call: 1 row updated. Second call: also 1 (the row was
        # found and re-written; the function returns the row count
        # of updates, not the number of changed values).
        assert n1 == 1
        assert n2 == 1
    finally:
        s.close()


def test_bulk_update_translations_empty_list_is_noop(tmp_path):
    """An empty rows list returns 0 and does not touch the DB."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        n = s.bulk_update_translations([])
        assert n == 0
    finally:
        s.close()


def test_bulk_update_translations_skips_missing_tweet_id(tmp_path):
    """A row whose tweet_id does not exist is silently skipped (no error)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.insert_posts([{"id": "t1", "brand_id": "minimax", "text": "x"}])
        n = s.bulk_update_translations([
            {
                "tweet_id": "t_does_not_exist",
                "text_en": "ghost",
                "text_zh_cn": "幽灵",
                "lang_detected": "en",
            },
        ])
        # 0 rows updated (the tweet_id doesn't exist).
        assert n == 0
        # t1 is unchanged.
        r = s._conn.execute(
            "SELECT text_en FROM posts WHERE tweet_id='t1'"
        ).fetchone()
        assert r["text_en"] is None
    finally:
        s.close()


def test_bulk_update_translations_malformed_row_raises_keyerror(tmp_path):
    """A row missing 'tweet_id' raises KeyError BEFORE the transaction starts."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(KeyError):
            s.bulk_update_translations([
                {
                    # missing 'tweet_id'
                    "text_en": "x",
                    "text_zh_cn": "y",
                    "lang_detected": "en",
                }
            ])
    finally:
        s.close()


# --- v1.7 get_posts_missing_translations ------------------------------


def test_get_posts_missing_translations_en(tmp_path):
    """Returns posts where text_en IS NULL, ordered newest-first.

    Use explicit, monotonically-increasing `created_at` values so the
    ordering is deterministic regardless of `_now_iso()`'s second-level
    precision. Relying on time.sleep + insertion order is flaky on
    fast machines.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # 3 posts, t1 oldest, t3 newest. t3 has text_en pre-filled.
        s.insert_posts([
            {"id": "t1", "brand_id": "minimax", "text": "a",
             "created_at": "2026-06-17T01:00:00+00:00"},
            {"id": "t2", "brand_id": "qwen", "text": "b",
             "created_at": "2026-06-17T02:00:00+00:00"},
            {"id": "t3", "brand_id": "deepseek", "text": "c",
             "created_at": "2026-06-17T03:00:00+00:00"},
        ])
        s.bulk_update_translations([
            {
                "tweet_id": "t3",
                "text_en": "c-en",
                "text_zh_cn": "c-zh",
                "lang_detected": "en",
            }
        ])
        missing = s.get_posts_missing_translations("en", limit=10)
        ids = [p["tweet_id"] for p in missing]
        assert "t3" not in ids  # has text_en
        assert "t1" in ids
        assert "t2" in ids
        # Newest-first: t2 (02:00) before t1 (01:00).
        assert ids.index("t2") < ids.index("t1"), (
            f"expected t2 before t1 in newest-first order; got {ids}"
        )
    finally:
        s.close()


def test_get_posts_missing_translations_zh_cn(tmp_path):
    """Returns posts where text_zh_cn IS NULL."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.insert_posts([{"id": "t1", "brand_id": "minimax", "text": "a"}])
        s.bulk_update_translations([
            {
                "tweet_id": "t1",
                "text_en": "a-en",
                "text_zh_cn": "a-zh",  # populated
                "lang_detected": "en",
            }
        ])
        # Now t1 has text_zh_cn. So the missing list is empty.
        missing = s.get_posts_missing_translations("zh_cn", limit=10)
        assert missing == []
    finally:
        s.close()


def test_get_posts_missing_translations_respects_limit(tmp_path):
    """The limit kwarg caps the result count."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        for i in range(5):
            s.insert_posts([
                {"id": f"t{i}", "brand_id": "minimax", "text": f"text{i}"}
            ])
        missing = s.get_posts_missing_translations("en", limit=3)
        assert len(missing) == 3
    finally:
        s.close()


def test_get_posts_missing_translations_invalid_locale_raises(tmp_path):
    """A locale not in {en, zh_cn} raises ValueError (column injection guard)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(ValueError, match="locale"):
            s.get_posts_missing_translations("ja", limit=10)
        with pytest.raises(ValueError, match="locale"):
            s.get_posts_missing_translations("en'; DROP TABLE posts; --", limit=10)
    finally:
        s.close()
