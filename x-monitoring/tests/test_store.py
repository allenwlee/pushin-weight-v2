# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.store."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from x_monitor.store import Store


def _make_post(tweet_id: str, model_id: str = "minimax", **kwargs) -> dict:
    p = {
        "id": tweet_id,
        "tweet_id": tweet_id,
        "model_id": model_id,
        "author_handle": "user1",
        "author_id": "u1",
        "text": "hello",
        "lang": "en",
        "created_at": "2026-06-07T00:00:00+00:00",
        "favorite_count": 5,
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
            assert store.applied_migrations() == [1, 2, 3]
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
            # The handle isn't in accounts yet; FK on (model_id, handle) should
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
