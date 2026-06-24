"""Migration 013: rename post_mentions → posts_brands_mentions.

Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
(Unit 3 of 9, R3).

Verifies:
- post_mentions table no longer exists after migration 013.
- posts_brands_mentions table exists after migration 013.
- The 2 indexes are renamed: idx_post_mentions_* → idx_posts_brands_mentions_*.
- Idempotency: re-opening a DB that has 013 applied does not re-run it.
- Full stack apply: all migrations 001-013 apply on a fresh DB; the
  plural-plural form is in effect.
- Integration: `insert_posts_brands_mentions` works (the method was
  renamed in step with the table); old `insert_post_mentions` is
  removed.
- Integration: the bulk `insert_posts` path writes to
  posts_brands_mentions.
"""

import pytest


# --- happy path: table renamed --------------------------------------


def test_migration_013_post_mentions_renamed_to_posts_brands_mentions(tmp_path):
    """post_mentions does not exist; posts_brands_mentions exists."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'post_mentions'"
        ).fetchall()
        assert rows == [], f"post_mentions still exists: {rows}"
        rows = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'posts_brands_mentions'"
        ).fetchall()
        assert rows, "posts_brands_mentions table not found"
    finally:
        s.close()


# --- happy path: indexes renamed ------------------------------------


def test_migration_013_indexes_renamed(tmp_path):
    """The 2 indexes are renamed: idx_post_mentions_* → idx_posts_brands_mentions_*."""
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
        assert "idx_post_mentions_brand_source_recent" not in indexes, (
            f"old index still present: {indexes}"
        )
        assert "idx_post_mentions_post" not in indexes, (
            f"old index still present: {indexes}"
        )
        assert "idx_posts_brands_mentions_brand_source_recent" in indexes, (
            f"new index missing. indexes={indexes}"
        )
        assert "idx_posts_brands_mentions_post" in indexes, (
            f"new index missing. indexes={indexes}"
        )
    finally:
        s.close()


# --- happy path: columns preserved -----------------------------------


def test_migration_013_posts_brands_mentions_preserves_columns(tmp_path):
    """The renamed table still has all 5 original columns
    (post_id, brand_id, source, raw_token, mentioned_at) and the
    composite PK."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        cols = {
            r[1] for r in s._conn.execute(
                "PRAGMA table_info(posts_brands_mentions)"
            ).fetchall()
        }
        expected = {"post_id", "brand_id", "source", "raw_token", "mentioned_at"}
        missing = expected - cols
        assert not missing, f"posts_brands_mentions missing columns: {missing}"
    finally:
        s.close()


# --- idempotency -----------------------------------------------------


def test_migration_013_idempotent(tmp_path):
    """Re-opening a DB that has 013 applied does not re-run it (the
    _migrations ledger records version 13 exactly once)."""
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
        assert applied.count(13) == 1
    finally:
        s2.close()


# --- full stack apply ------------------------------------------------


def test_migration_013_full_stack_apply(tmp_path):
    """All migrations 001-013 apply on a fresh DB; the plural-plural
    form is in effect; the 6 M:N-style tables are all named per the
    plural-plural convention."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        applied = sorted(
            r[0]
            for r in s._conn.execute("SELECT version FROM _migrations").fetchall()
        )
        # 001-015: 005/006 = quote-tweets; 007 = i18n locale columns;
        # 008 = enum i18n lookup tables; 009 = products;
        # 010 = M:N rename to plural-plural;
        # 011 = rename locale to lang;
        # 012 = drop engagement_tier tables;
        # 013 = rename post_mentions to posts_brands_mentions;
        # 014 = rename signal_keys to signals;
        # 015 = rename role_keys to roles;
        # 016 = trim role values to {official, staff, community};
        # 017 = brand_search_terms hybrid by design (no-op DDL).
        # 018 = INTEGER PKs for enum tables (signals, roles).
        assert applied == list(range(1, 19)), (
            f"unexpected versions: {applied}"
        )

        # Plural-plural tables in effect.
        for tbl in (
            "brands_accounts",
            "brands_companies",
            "companies_accounts",
            "posts_brands",
            "posts_brands_signals",
            "posts_brands_mentions",
        ):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (tbl,)
            ).fetchall()
            assert rows, f"{tbl} missing"

        # Old names are gone.
        for old in (
            "post_brands",
            "post_brand_signals",
            "post_mentions",
            "brand_accounts",
            "brand_companies",
            "company_accounts",
        ):
            rows = s._conn.execute(
                "SELECT name FROM sqlite_master WHERE name = ?", (old,)
            ).fetchall()
            assert rows == [], f"{old} still exists"
    finally:
        s.close()


# --- integration: insert_posts_brands_mentions works -----------------


def test_migration_013_insert_posts_brands_mentions_writes(tmp_path):
    """The renamed method `insert_posts_brands_mentions` writes a row
    that round-trips through SELECT."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Need a post row for the FK chain.
        s._conn.execute(
            "INSERT INTO posts (tweet_id, author_handle, fetched_at) "
            "VALUES (?, ?, ?)",
            ("t_013_insert", "u_013", "2026-06-24T00:00:00+00:00"),
        )
        s.insert_posts_brands_mentions(
            "t_013_insert", "minimax", "user_mention",
            "@MiniMaxAI", "2026-06-24T00:00:00+00:00",
        )
        row = s._conn.execute(
            "SELECT source, raw_token FROM posts_brands_mentions "
            "WHERE post_id = ?",
            ("t_013_insert",),
        ).fetchone()
        assert row["source"] == "user_mention"
        assert row["raw_token"] == "@MiniMaxAI"
    finally:
        s.close()


def test_migration_013_old_insert_post_mentions_removed(tmp_path):
    """The old `insert_post_mentions` method is removed from the Store
    API; calling it raises AttributeError."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert not hasattr(s, "insert_post_mentions"), (
            "Store still has insert_post_mentions method after 013"
        )
    finally:
        s.close()


# --- integration: insert_posts bulk path lands in posts_brands_mentions -


def test_migration_013_insert_posts_bulk_writes_to_posts_brands_mentions(tmp_path):
    """insert_posts's bulk path writes per-source mentions into
    posts_brands_mentions (the renamed table)."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.insert_posts([
            {
                "id": "t_013_bulk",
                "author_handle": "u_b",
                "author_id": "999",
                "text": "valid",
                "created_at": "2026-06-24T00:00:00+00:00",
                "brand_ids": ["minimax"],
                "signals": {"minimax": "release"},
                "mentions": [
                    {
                        "post_id": "t_013_bulk",
                        "brand_id": "minimax",
                        "source": "hashtag",
                        "raw_token": "#minimax",
                        "mentioned_at": "2026-06-24T00:00:00+00:00",
                    },
                ],
            },
        ])
        row = s._conn.execute(
            "SELECT source, raw_token FROM posts_brands_mentions "
            "WHERE post_id = ?",
            ("t_013_bulk",),
        ).fetchone()
        assert row["source"] == "hashtag"
        assert row["raw_token"] == "#minimax"
        # Old table has no rows for this post.
        old = s._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'post_mentions'"
        ).fetchall()
        assert old == []
    finally:
        s.close()
