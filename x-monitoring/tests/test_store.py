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
            store.upsert_account("minimax", "alice", role="unknown", engagement_tier="low")
            a1 = store.get_account("minimax", "alice")
            assert a1 is not None
            assert a1["engagement_tier"] == "low"
            store.upsert_account(
                "minimax",
                "alice",
                role="community",
                engagement_tier="high",
            )
            a2 = store.get_account("minimax", "alice")
            assert a2["engagement_tier"] == "high"
            assert a2["role"] == "community"
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
            assert store.applied_migrations() == [1, 2, 3, 4]
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


# --- v1.8: post_brands / post_mentions / post_brand_signals writes ----


def test_insert_posts_writes_post_brands():
    """A 2-brand post writes 2 rows to post_brands; weights sum to 1.0."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([
                _make_post("p1", brand_id=["qwen", "deepseek"]),
            ])
            rows = store._conn.execute(
                "SELECT brand_id, weight FROM post_brands WHERE post_id = 'p1' "
                "ORDER BY brand_id"
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


def test_insert_posts_writes_post_mentions():
    """A post with 2 source mentions writes 2 rows to post_mentions."""
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
                "SELECT source, raw_token FROM post_mentions "
                "WHERE post_id = 'p1' ORDER BY source"
            ).fetchall()
            assert len(rows) == 2
            assert rows[0]["source"] == "hashtag"
            assert rows[0]["raw_token"] == "#qwen"
            assert rows[1]["source"] == "user_mention"
            assert rows[1]["raw_token"] == "@QwenLM"
        finally:
            store.close()


def test_insert_posts_writes_post_brand_signals():
    """A post with 2-brand signals writes 2 rows to post_brand_signals."""
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
                    "signals": {"qwen": "praise", "deepseek": "criticism"},
                }
            ])
            rows = store._conn.execute(
                "SELECT brand_id, signal FROM post_brand_signals "
                "WHERE post_id = 'p1' ORDER BY brand_id"
            ).fetchall()
            assert len(rows) == 2
            assert rows[0]["brand_id"] == "deepseek"
            assert rows[0]["signal"] == "criticism"
            assert rows[1]["brand_id"] == "qwen"
            assert rows[1]["signal"] == "praise"
        finally:
            store.close()


def test_insert_posts_drops_hallucinated_brand_signals():
    """insert_posts must not crash when signals include a brand_id
    not in KNOWN_MODELS (LLM hallucination). The known brand's signal
    lands; the unknown brand's signal is silently dropped (logged).

    Regression: v1.8 hot path crashed with sqlite3.IntegrityError FK
    failure on post_brand_signals when the LLM returned a brand_id
    that wasn't in the brands table. The fix intersects
    `per_brand_signals` against `valid_brands` before INSERT.
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
                    # `fake_brand` is not in KNOWN_MODELS. The LLM
                    # might still return it as a signal — the post
                    # itself is attributed to {qwen, deepseek} but the
                    # signal map can include extras.
                    "signals": {
                        "qwen": "praise",
                        "deepseek": "criticism",
                        "fake_brand": "release",
                    },
                }
            ])
            # Post should still be inserted.
            n_posts = store._conn.execute(
                "SELECT COUNT(*) FROM posts WHERE tweet_id = 'p1'"
            ).fetchone()[0]
            assert n_posts == 1
            # post_brand_signals must contain exactly the 2 known
            # brands — the hallucinated `fake_brand` is dropped.
            rows = store._conn.execute(
                "SELECT brand_id, signal FROM post_brand_signals "
                "WHERE post_id = 'p1' ORDER BY brand_id"
            ).fetchall()
            assert len(rows) == 2
            assert [r["brand_id"] for r in rows] == ["deepseek", "qwen"]
            assert rows[0]["signal"] == "criticism"
            assert rows[1]["signal"] == "praise"
            # post_brands should also only have the known brands
            # (already filtered by valid_brands — this confirms no
            # regression in the post_brands path).
            n_brands = store._conn.execute(
                "SELECT COUNT(*) FROM post_brands WHERE post_id = 'p1'"
            ).fetchone()[0]
            assert n_brands == 2
        finally:
            store.close()


def test_insert_post_brands_upsert_on_conflict():
    """insert_post_brands on conflict overwrites weight (Decision 14)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([_make_post("p1", brand_id="qwen")])
            store.insert_post_brands("p1", "qwen", 0.5)
            store.insert_post_brands("p1", "qwen", 0.7)
            row = store._conn.execute(
                "SELECT weight FROM post_brands WHERE post_id='p1' AND brand_id='qwen'"
            ).fetchone()
            assert row["weight"] == 0.7
            # Only 1 row, not 2.
            n = store._conn.execute(
                "SELECT COUNT(*) FROM post_brands WHERE post_id='p1' AND brand_id='qwen'"
            ).fetchone()[0]
            assert n == 1
        finally:
            store.close()


def test_insert_post_brand_signals_rejects_unattributed():
    """insert_post_brand_signals rejects brand_id='_unattributed' (CHECK)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([_make_post("p1", brand_id="qwen")])
            with pytest.raises(sqlite3.IntegrityError):
                store.insert_post_brand_signals("p1", "_unattributed", "praise")
        finally:
            store.close()


def test_insert_post_mentions_allows_null_brand_id():
    """insert_post_mentions allows brand_id=NULL (un-attributed mentions)."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            store.insert_posts([_make_post("p1", brand_id="qwen")])
            store.insert_post_mentions(
                "p1", None, "user_mention", "@unknown", "2026-06-07T00:00:00+00:00"
            )
            n = store._conn.execute(
                "SELECT COUNT(*) FROM post_mentions "
                "WHERE post_id='p1' AND brand_id IS NULL"
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


def test_read_brand_accounts_returns_dict():
    """read_brand_accounts returns {author_id: brand_id} dict."""
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            # Use the upsert_account helper to seed brand_accounts.
            store.upsert_account("qwen", "alice", role="community")
            store.upsert_account("qwen", "bob", role="staff")
            store.upsert_account("deepseek", "carol", role="staff")
            d = store.read_brand_accounts()
            assert d["handle:alice"] == "qwen"
            assert d["handle:bob"] == "qwen"
            assert d["handle:carol"] == "deepseek"
            assert len(d) == 3
        finally:
            store.close()

