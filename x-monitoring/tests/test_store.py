# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.store."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from x_monitor.store import Store


def _make_post(tweet_id: str, brand_id: str = "minimax", **kwargs) -> dict:
    p = {
        "id": tweet_id,
        "tweet_id": tweet_id,
        "brand_id": brand_id,
        "author_handle": "user1",
        "author_id": "u1",
        "text": "hello",
        "lang": "en",
        "created_at": "2026-06-07T00:00:00+00:00",
        "like_count": 5,
        "retweet_count": 1,
        "entities": {"user_mentions": []},
    }
    p.update(kwargs)
    return p


def test_insert_posts_idempotent():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            posts = [_make_post(str(i)) for i in range(100)]
            n1 = store.insert_posts(posts)
            assert n1 == 100
            # Re-insert same 100 — no new rows.
            n2 = store.insert_posts(posts)
            assert n2 == 0
            row_count = store._conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            assert row_count == 100
        finally:
            store.close()


def test_insert_posts_handles_partial_overlap():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            first = [_make_post(str(i)) for i in range(100)]
            store.insert_posts(first)
            new = [_make_post(str(i)) for i in range(50, 150)]
            n = store.insert_posts(new)
            assert n == 50
            row_count = store._conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            assert row_count == 150
        finally:
            store.close()


def test_upsert_account_updates_last_seen_and_tier():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            # v1.8 (Unit 3): role must be a valid role_key post-migration 007;
            # 'unknown' is no longer seeded. Use 'community' for the
            # upsert; engagement_tier was removed in migration 012.
            store.upsert_account("minimax", "alice", role="community")
            a1 = store.get_account("minimax", "alice")
            assert a1 is not None
            store.upsert_account(
                "minimax",
                "alice",
                role="community",
            )
            a2 = store.get_account("minimax", "alice")
            # U8: role_id is now INTEGER (FK to roles.id). Look up
            # the role key via the roles table to compare against
            # the legacy "community" string contract.
            role_key = store._conn.execute(
                "SELECT r.key FROM roles r WHERE r.id = ?",
                (a2["role_id"],),
            ).fetchone()["key"]
            assert role_key == "community"
            assert a2["last_seen_at"] >= a1["last_seen_at"]
        finally:
            store.close()


def test_migrations_apply_forward_only_and_idempotent():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db", auto_migrate=False)
        try:
            applied_first = store.apply_migrations()
            # Migrations 1 (initial) and 2 (post_headline) should both apply
            # on a fresh DB. The exact set may grow with v1.2+ migrations;
            # what matters is that 1 and 2 are both in the set.
            assert 1 in applied_first
            assert 2 in applied_first
            # Migrations 005/006 (quote-tweets) + 007/008 (i18n) merged to main
            # before this branch. Migration 009 (HF products, renumbered from
            # 005 at rebase time) is present on this branch. The exact list
            # grows as migrations are added; assert the invariant subset, not
            # the whole list.
            applied = store.applied_migrations()
            assert {1, 2, 3, 4, 5, 6, 7, 8}.issubset(set(applied))
            assert 9 in applied
            # Re-apply is a no-op
            applied_second = store.apply_migrations()
            assert applied_second == []
        finally:
            store.close()


def test_get_posts_for_digest_orders_by_created_at_desc():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts(
                [
                    _make_post("1", created_at="2026-06-07T01:00:00+00:00"),
                    _make_post("2", created_at="2026-06-07T03:00:00+00:00"),
                    _make_post("3", created_at="2026-06-07T02:00:00+00:00"),
                ]
            )
            rows = store.get_posts_for_digest("minimax")
            ids = [r["tweet_id"] for r in rows]
            assert ids == ["2", "3", "1"]
        finally:
            store.close()


def test_get_posts_for_digest_respects_since_window():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts(
                [
                    _make_post("1", created_at="2026-06-06T01:00:00+00:00"),
                    _make_post("2", created_at="2026-06-07T03:00:00+00:00"),
                    _make_post("3", created_at="2026-06-07T02:00:00+00:00"),
                ]
            )
            rows = store.get_posts_for_digest("minimax", since_iso="2026-06-07T00:00:00+00:00")
            ids = sorted(r["tweet_id"] for r in rows)
            assert ids == ["2", "3"]
        finally:
            store.close()


def test_account_post_appearances_fk_to_unknown_handle_ignored():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([_make_post("p1")])
            # The handle isn't in accounts yet; FK on (brand_id, handle) should
            # cause an IntegrityError, which we catch silently.
            store.record_appearance("minimax", "ghost", "p1")
            # After upserting the account, the appearance can be recorded.
            store.upsert_account("minimax", "ghost", role="unknown")
            store.record_appearance("minimax", "ghost", "p1")
            row = store._conn.execute(
                "SELECT COUNT(*) FROM account_post_appearances"
            ).fetchone()[0]
            assert row == 1
        finally:
            store.close()


# --- v1.8: posts_brands / posts_brands_mentions / posts_brands_signals writes ----


def test_insert_posts_writes_posts_brands():
    """A 2-brand post writes 2 rows to posts_brands; weights sum to 1.0."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([
                _make_post("p1", brand_id=["qwen", "deepseek"]),
            ])
            # U8 (migration 020): post_id and brand_id are INTEGER.
            # JOIN back to posts / brands to recover the TEXT identities
            # the test contract cares about.
            rows = store._conn.execute(
                "SELECT b.brand_id, pb.weight "
                "FROM posts_brands pb "
                "JOIN brands b ON b.id = pb.brand_id "
                "JOIN posts p ON p.id = pb.post_id "
                "WHERE p.tweet_id = 'p1' "
                "ORDER BY b.brand_id"
            ).fetchall()
            assert len(rows) == 2
            assert rows[0]["brand_id"] == "deepseek"
            assert rows[0]["weight"] == 0.5
            assert rows[1]["brand_id"] == "qwen"
            assert rows[1]["weight"] == 0.5
            # Weight conservation (Decision 17 tolerance).
            total = sum(r["weight"] for r in rows)
            assert abs(total - 1.0) < 0.001
        finally:
            store.close()


def test_insert_posts_writes_posts_brands_mentions():
    """A post with 2 source mentions writes 2 rows to posts_brands_mentions."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([
                {
                    "id": "p1",
                    "tweet_id": "p1",
                    "brand_id": "qwen",
                    "author_handle": "u1",
                    "author_id": "u1",
                    "text": "hello",
                    "lang": "en",
                    "created_at": "2026-06-07T00:00:00+00:00",
                    "entities": {"user_mentions": []},
                    "mentions": [
                        {
                            "post_id": "p1",
                            "brand_id": "qwen",
                            "source": "user_mention",
                            "raw_token": "@QwenLM",
                            "mentioned_at": "2026-06-07T00:00:00+00:00",
                        },
                        {
                            "post_id": "p1",
                            "brand_id": "qwen",
                            "source": "hashtag",
                            "raw_token": "#qwen",
                            "mentioned_at": "2026-06-07T00:00:00+00:00",
                        },
                    ],
                }
            ])
            rows = store._conn.execute(
                "SELECT m.source, m.raw_token FROM posts_brands_mentions m "
                "JOIN posts p ON p.id = m.post_id "
                "WHERE p.tweet_id = 'p1' ORDER BY m.source"
            ).fetchall()
            assert len(rows) == 2
            assert rows[0]["source"] == "hashtag"
            assert rows[0]["raw_token"] == "#qwen"
            assert rows[1]["source"] == "user_mention"
            assert rows[1]["raw_token"] == "@QwenLM"
        finally:
            store.close()


def test_insert_posts_writes_posts_brands_signals():
    """A post with 2-brand (post_type, sentiment) classifications writes
    2 rows to posts_brands_signals.

    U9 (migration 022): the legacy `signals` field (single string
    per brand) is replaced by `post_types` + `sentiments` (parallel
    dicts of brand_id → key). The `signal` column was dropped from
    `posts_brands_signals`; `post_type` + `sentiment` are the only
    classification columns.
    """
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([
                {
                    "id": "p1",
                    "tweet_id": "p1",
                    "brand_id": ["qwen", "deepseek"],
                    "author_handle": "u1",
                    "author_id": "u1",
                    "text": "Qwen vs DeepSeek",
                    "lang": "en",
                    "created_at": "2026-06-07T00:00:00+00:00",
                    "entities": {"user_mentions": []},
                    "post_types": {
                        "qwen": "buzz_releases",
                        "deepseek": "performance_comparisons",
                    },
                    "sentiments": {
                        "qwen": "positive",
                        "deepseek": "negative",
                    },
                }
            ])
            rows = store._conn.execute(
                "SELECT b.brand_id, pt.key AS post_type, sn.key AS sentiment "
                "FROM posts_brands_signals pbs "
                "JOIN brands b ON b.id = pbs.brand_id "
                "JOIN post_type_keys pt ON pt.id = pbs.post_type "
                "JOIN sentiment_keys sn ON sn.id = pbs.sentiment "
                "JOIN posts p ON p.id = pbs.post_id "
                "WHERE p.tweet_id = 'p1' ORDER BY b.brand_id"
            ).fetchall()
            assert len(rows) == 2
            assert rows[0]["brand_id"] == "deepseek"
            assert rows[0]["post_type"] == "performance_comparisons"
            assert rows[0]["sentiment"] == "negative"
            assert rows[1]["brand_id"] == "qwen"
            assert rows[1]["post_type"] == "buzz_releases"
            assert rows[1]["sentiment"] == "positive"
        finally:
            store.close()


def test_insert_posts_drops_hallucinated_brand_classifications():
    """insert_posts must not crash when classifications include a
    brand_id not in the brands table (LLM hallucination). The known
    brand's classification lands; the unknown brand's classification
    is silently dropped (logged).

    U9 (migration 022): the per-brand dict shape changed from
    `signals` (a single string per brand) to parallel
    `post_types` + `sentiments` dicts (one key per brand). The
    drop-on-unknown-brand behavior is the same.

    Regression: v1.8 hot path crashed with sqlite3.IntegrityError FK
    failure on posts_brands_signals when the LLM returned a brand_id
    that wasn't in the brands table. The fix intersects
    classifications against the brands table before INSERT.
    """
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([
                {
                    "id": "p1",
                    "tweet_id": "p1",
                    "brand_id": ["qwen", "deepseek"],
                    "author_handle": "u1",
                    "author_id": "u1",
                    "text": "Qwen vs DeepSeek, also mentioned fake_brand",
                    "lang": "en",
                    "created_at": "2026-06-07T00:00:00+00:00",
                    "entities": {"user_mentions": []},
                    # `fake_brand` is not in the brands table. The LLM
                    # might still return it as a classification — the
                    # post itself is attributed to {qwen, deepseek} but
                    # the classification maps can include extras.
                    "post_types": {
                        "qwen": "buzz_releases",
                        "deepseek": "performance_comparisons",
                        "fake_brand": "buzz_releases",
                    },
                    "sentiments": {
                        "qwen": "positive",
                        "deepseek": "negative",
                        "fake_brand": "positive",
                    },
                }
            ])
            # Post should still be inserted.
            n_posts = store._conn.execute(
                "SELECT COUNT(*) FROM posts WHERE tweet_id = 'p1'"
            ).fetchone()[0]
            assert n_posts == 1
            # posts_brands_signals must contain exactly the 2 known
            # brands — the hallucinated `fake_brand` is dropped.
            rows = store._conn.execute(
                "SELECT b.brand_id "
                "FROM posts_brands_signals pbs "
                "JOIN brands b ON b.id = pbs.brand_id "
                "JOIN posts p ON p.id = pbs.post_id "
                "WHERE p.tweet_id = 'p1' ORDER BY b.brand_id"
            ).fetchall()
            assert len(rows) == 2
            assert [r["brand_id"] for r in rows] == ["deepseek", "qwen"]
            # posts_brands should also only have the known brands
            # (already filtered by valid_brands — this confirms no
            # regression in the posts_brands path).
            n_brands = store._conn.execute(
                "SELECT COUNT(*) FROM posts_brands pb "
                "JOIN posts p ON p.id = pb.post_id "
                "WHERE p.tweet_id = 'p1'"
            ).fetchone()[0]
            assert n_brands == 2
        finally:
            store.close()


def test_insert_posts_keeps_cross_mention_classification():
    """Cross-mention: a classification for a brand in the brands table
    but NOT in the post's own brand_ids must be KEPT (P1 #3 regression
    guard).

    U9: the per-brand classification is now expressed as parallel
    `post_types` + `sentiments` dicts instead of the legacy single
    `signals` dict. The cross-mention-keep behavior is the same.

    Before the known_ids fix, the guard used valid_brands (the post's
    own brand_ids) and dropped cross-mention signals. Now it uses the
    brands-table source of truth, so a post attributed to {qwen} that
    also carries a deepseek classification keeps both.

    Note: deepseek must be in the brands table (migration 004 seeds it).
    We add the post to posts_brands only for qwen, but the
    classification maps include deepseek — the row should still land.
    """
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([
                {
                    "id": "p1",
                    "tweet_id": "p1",
                    "brand_id": ["qwen"],  # post attributed to qwen only
                    "author_handle": "u1",
                    "author_id": "u1",
                    "text": "Qwen is great, also DeepSeek is interesting",
                    "lang": "en",
                    "created_at": "2026-06-07T00:00:00+00:00",
                    "entities": {"user_mentions": []},
                    # cross-mention: deepseek is NOT in brand_ids but IS
                    # a real brand. The known_ids guard keeps it.
                    "post_types": {
                        "qwen": "buzz_releases",
                        "deepseek": "performance_comparisons",
                    },
                    "sentiments": {
                        "qwen": "positive",
                        "deepseek": "negative",
                    },
                }
            ])
            rows = store._conn.execute(
                "SELECT b.brand_id "
                "FROM posts_brands_signals pbs "
                "JOIN brands b ON b.id = pbs.brand_id "
                "JOIN posts p ON p.id = pbs.post_id "
                "WHERE p.tweet_id = 'p1' ORDER BY b.brand_id"
            ).fetchall()
            # Both classifications land — deepseek is a real brand
            # even though the post is only attributed to qwen.
            assert len(rows) == 2
            assert [r["brand_id"] for r in rows] == ["deepseek", "qwen"]
        finally:
            store.close()


def test_insert_posts_all_hallucinated_signals():
    """When every signal brand_id is unknown, none land but the post
    still inserts (P2 #6 edge case)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([
                {
                    "id": "p1",
                    "tweet_id": "p1",
                    "brand_id": ["qwen"],
                    "author_handle": "u1",
                    "author_id": "u1",
                    "text": "qwen text",
                    "lang": "en",
                    "created_at": "2026-06-07T00:00:00+00:00",
                    "entities": {"user_mentions": []},
                    "signals": {
                        "fake1": "praise",
                        "fake2": "criticism",
                    },
                }
            ])
            n_posts = store._conn.execute(
                "SELECT COUNT(*) FROM posts WHERE tweet_id='p1'"
            ).fetchone()[0]
            assert n_posts == 1
            n_sigs = store._conn.execute(
                "SELECT COUNT(*) FROM posts_brands_signals pbs "
                "JOIN posts p ON p.id = pbs.post_id "
                "WHERE p.tweet_id='p1'"
            ).fetchone()[0]
            assert n_sigs == 0
        finally:
            store.close()


def test_insert_posts_legacy_signal_string_broadcast():
    """U9 (migration 022): the legacy single-string `signal` field is
    GONE. insert_posts no longer accepts a top-level `signal` key.
    Posts that pass only `classifications` (or omit both) still
    insert cleanly; the legacy broadcast branch in
    `_extract_per_brand_signals` has been removed.

    This test now asserts the post is inserted with NO
    posts_brands_signals row when no classification dict is provided
    (mirroring the U9 offline path).
    """
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([
                {
                    "id": "p1",
                    "tweet_id": "p1",
                    "brand_id": ["qwen", "deepseek"],
                    "author_handle": "u1",
                    "author_id": "u1",
                    "text": "Qwen vs DeepSeek",
                    "lang": "en",
                    "created_at": "2026-06-07T00:00:00+00:00",
                    "entities": {"user_mentions": []},
                    # No `signal` (legacy) and no `classifications`
                    # (U9). The post still inserts; classification
                    # comes later via the reattribute pipeline.
                }
            ])
            n_sigs = store._conn.execute(
                "SELECT COUNT(*) FROM posts_brands_signals pbs "
                "JOIN posts p ON p.id = pbs.post_id "
                "WHERE p.tweet_id='p1'"
            ).fetchone()[0]
            assert n_sigs == 0
        finally:
            store.close()


def test_insert_posts_brands_upsert_on_conflict():
    """insert_posts_brands on conflict overwrites weight (Decision 14)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([_make_post("p1", brand_id="qwen")])
            store.insert_posts_brands("p1", "qwen", 0.5)
            store.insert_posts_brands("p1", "qwen", 0.7)
            row = store._conn.execute(
                "SELECT pb.weight FROM posts_brands pb "
                "JOIN posts p ON p.id = pb.post_id "
                "JOIN brands b ON b.id = pb.brand_id "
                "WHERE p.tweet_id='p1' AND b.brand_id='qwen'"
            ).fetchone()
            assert row["weight"] == 0.7
            # Only 1 row, not 2.
            n = store._conn.execute(
                "SELECT COUNT(*) FROM posts_brands pb "
                "JOIN posts p ON p.id = pb.post_id "
                "JOIN brands b ON b.id = pb.brand_id "
                "WHERE p.tweet_id='p1' AND b.brand_id='qwen'"
            ).fetchone()[0]
            assert n == 1
        finally:
            store.close()


def test_insert_posts_brands_signals_rejects_unattributed():
    """insert_posts_brands_signals rejects brand_id='_unattributed'.

    Pre-020 (TEXT PK + schema CHECK): the schema raised
    IntegrityError. Post-020 (INTEGER PK): the schema CHECK is
    dropped (sentinel id is data-dependent), so the rejection moves
    to an application-level guard that silently drops the write with
    a warning. The contract is the same: no row should land in
    posts_brands_signals for the sentinel brand.

    U9 (migration 022): the signature changed from
    (post_id, brand_id, signal) to (post_id, brand_id, post_type,
    sentiment). Both classification columns are required (NOT NULL).
    """
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([_make_post("p1", brand_id="qwen")])
            # U8 + U9: silent drop, not IntegrityError. Assert no row
            # was written for the sentinel brand.
            store.insert_posts_brands_signals(
                "p1", "_unattributed", "buzz_releases", "positive",
            )
            n = store._conn.execute(
                "SELECT COUNT(*) FROM posts_brands_signals pbs "
                "JOIN posts p ON p.id = pbs.post_id "
                "WHERE p.tweet_id='p1'"
            ).fetchone()[0]
            assert n == 0
        finally:
            store.close()


def test_insert_posts_brands_mentions_allows_null_brand_id():
    """insert_posts_brands_mentions allows brand_id=NULL (un-attributed mentions)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([_make_post("p1", brand_id="qwen")])
            store.insert_posts_brands_mentions(
                "p1", None, "user_mention", "@unknown", "2026-06-07T00:00:00+00:00"
            )
            # U8: post_id is INTEGER; filter via JOIN.
            n = store._conn.execute(
                "SELECT COUNT(*) FROM posts_brands_mentions m "
                "JOIN posts p ON p.id = m.post_id "
                "WHERE p.tweet_id='p1' AND m.brand_id IS NULL"
            ).fetchone()[0]
            assert n == 1
        finally:
            store.close()


def test_read_brands_returns_12_rows():
    """read_brands returns the 11 real brands + the _unattributed sentinel."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            brands = store.read_brands()
            assert len(brands) == 12
            sentinels = [b for b in brands if b.is_sentinel]
            assert len(sentinels) == 1
            assert sentinels[0].brand_id == "_unattributed"
            # Cache hit on second call returns same list (identity).
            brands2 = store.read_brands()
            assert brands2 is brands
        finally:
            store.close()


def test_read_brands_accounts_returns_dict():
    """read_brands_accounts returns {author_id: brand_id} dict."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            # Use the upsert_account helper to seed brands_accounts.
            # v1.8 (Unit 3): role is FK-validated against roles
            # (renamed from role_keys in 015). The seeded set after
            # U6 is {official, staff, community}; researcher/press/vendor
            # are removed and would hit the dead-letter. Use a seeded
            # role so the brands_accounts edge actually writes.
            store.upsert_account("qwen", "alice", role="community")
            store.upsert_account("qwen", "bob", role="official")
            store.upsert_account("deepseek", "carol", role="staff")
            d = store.read_brands_accounts()
            assert d["handle:alice"] == "qwen"
            assert d["handle:bob"] == "qwen"
            assert d["handle:carol"] == "deepseek"
            assert len(d) == 3
        finally:
            store.close()


def test_migration_006_adds_tracking_and_epoch_columns():
    """Migration 006 adds last_quote_count_seen, last_quote_fetched_at,
    and created_at_epoch to posts."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            cols = {
                r["name"]
                for r in store._conn.execute("PRAGMA table_info(posts)")
            }
            assert "last_quote_count_seen" in cols
            assert "last_quote_fetched_at" in cols
            assert "created_at_epoch" in cols
        finally:
            store.close()


def test_insert_posts_writes_created_at_epoch_twitter_format():
    """insert_posts parses the Twitter-format created_at into an integer
    epoch on created_at_epoch (the basis for time-window queries)."""
    from x_monitor.store import _created_at_epoch

    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            tw = "Mon Jun 08 22:25:20 +0000 2026"
            store.insert_posts([_make_post("1", created_at=tw)])
            row = store._conn.execute(
                "SELECT created_at_epoch FROM posts WHERE tweet_id='1'"
            ).fetchone()
            assert row["created_at_epoch"] == _created_at_epoch(tw)
            assert row["created_at_epoch"] is not None
        finally:
            store.close()


def test_update_quote_tracking_roundtrip_and_unclobbered():
    """update_quote_tracking writes the two tracking columns and survives a
    subsequent INSERT OR IGNORE re-insert of the same post (which must not
    reset them)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([_make_post("1")])
            store.update_quote_tracking("1", 42, "2026-06-22T00:00:00+00:00")
            row = store._conn.execute(
                "SELECT last_quote_count_seen, last_quote_fetched_at "
                "FROM posts WHERE tweet_id='1'"
            ).fetchone()
            assert row["last_quote_count_seen"] == 42
            assert row["last_quote_fetched_at"] == "2026-06-22T00:00:00+00:00"

            # Re-insert the same post (INSERT OR IGNORE) — tracking must be
            # preserved, not reset to defaults.
            store.insert_posts([_make_post("1", text="changed")])
            row = store._conn.execute(
                "SELECT last_quote_count_seen, last_quote_fetched_at, text "
                "FROM posts WHERE tweet_id='1'"
            ).fetchone()
            assert row["last_quote_count_seen"] == 42
            assert row["last_quote_fetched_at"] == "2026-06-22T00:00:00+00:00"
            assert row["text"] == "hello"
        finally:
            store.close()

