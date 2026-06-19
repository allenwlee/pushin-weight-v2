# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.reattribute (Unit 5).

Covers R19: the `reattribute_all_posts` function and the
`reattribute` CLI subcommand. The 6 plan-mandated scenarios:
  - idempotent re-run
  - 2-brand post produces 2 post_brands rows with weights summing to 1.0
  - legacy entities JSON string handled
  - dry-run leaves DB unchanged
  - --limit caps post count
  - --model <brand_id> filters via post_brands JOIN
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from x_monitor.reattribute import reattribute_all_posts
from x_monitor.store import Store


def _seed_db(d: Path, posts: list, detection: dict | None = None) -> None:
    """Open Store at d/x.db, insert posts + detection registry.

    Detection keys (all optional):
        brand_accounts, brand_hashtags, brand_keywords, brand_search_terms,
        search_queries.
    """
    db = d / "x.db"
    store = Store(db)
    detection = detection or {}
    store._conn.execute(
        "INSERT OR IGNORE INTO brands(brand_id, display_name, accent_color, "
        "is_sentinel, created_at) VALUES (?, ?, ?, ?, ?)",
        ("minimax", "MiniMax", "#a855f7", 0, "2026-06-19T00:00:00+00:00"),
    )
    store._conn.execute(
        "INSERT OR IGNORE INTO brands(brand_id, display_name, accent_color, "
        "is_sentinel, created_at) VALUES (?, ?, ?, ?, ?)",
        ("qwen", "Qwen", "#22c55e", 0, "2026-06-19T00:00:00+00:00"),
    )
    store._conn.execute(
        "INSERT OR IGNORE INTO brands(brand_id, display_name, accent_color, "
        "is_sentinel, created_at) VALUES (?, ?, ?, ?, ?)",
        ("deepseek", "DeepSeek", "#0ea5e9", 0, "2026-06-19T00:00:00+00:00"),
    )
    store._conn.execute(
        "INSERT OR IGNORE INTO brands(brand_id, display_name, accent_color, "
        "is_sentinel, created_at) VALUES (?, ?, ?, ?, ?)",
        ("_unattributed", "Unattributed", "#6b7280", 1, "2026-06-19T00:00:00+00:00"),
    )
    for author_id, brand_id in detection.get("brand_accounts", {}).items():
        store._conn.execute(
            "INSERT OR IGNORE INTO accounts(author_id, handle, "
            "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (author_id, f"user_{author_id}", "2026-06-19T00:00:00+00:00",
             "2026-06-19T00:00:00+00:00"),
        )
        store._conn.execute(
            "INSERT INTO brand_accounts(brand_id, author_id, role, added_at) "
            "VALUES (?, ?, ?, ?)",
            (brand_id, author_id, "official", "2026-06-19T00:00:00+00:00"),
        )
    for tag, brand_id in detection.get("brand_hashtags", {}).items():
        store._conn.execute(
            "INSERT OR IGNORE INTO brand_hashtags(tag, brand_id, added_at) VALUES (?, ?, ?)",
            (tag, brand_id, "2026-06-19T00:00:00+00:00"),
        )
    for brand_id, pattern, is_regex in detection.get("brand_keywords", []):
        store._conn.execute(
            "INSERT OR IGNORE INTO brand_keywords(brand_id, pattern, is_regex, added_at) "
            "VALUES (?, ?, ?, ?)",
            (brand_id, pattern, int(is_regex), "2026-06-19T00:00:00+00:00"),
        )
    for term, brand_id in detection.get("brand_search_terms", {}).items():
        store._conn.execute(
            "INSERT OR IGNORE INTO brand_search_terms(term, brand_id, added_at) VALUES (?, ?, ?)",
            (term, brand_id, "2026-06-19T00:00:00+00:00"),
        )
    for qid, kws in detection.get("search_queries", {}).items():
        brand_id = (detection.get("brand_search_terms") or {}).get(
            kws[0] if kws else "", "minimax"
        )
        store._conn.execute(
            "INSERT INTO search_queries(query_id, brand_id, keywords_json, "
            "created_at) VALUES (?, ?, ?, ?)",
            (qid, brand_id, json.dumps(kws), "2026-06-19T00:00:00+00:00"),
        )
    for p_item in posts:
        entities = p_item.get("entities", {})
        if not isinstance(entities, str):
            entities = json.dumps(entities)
        store._conn.execute(
            """
            INSERT INTO posts(
                tweet_id, author_handle, author_id, text, lang,
                created_at, fetched_at, like_count, retweet_count,
                reply_count, quote_count, entities, source_query_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p_item["tweet_id"],
                p_item.get("author_handle", "user1"),
                p_item.get("author_id"),
                p_item.get("text"),
                p_item.get("lang", "en"),
                p_item.get("created_at", "2026-06-19T00:00:00+00:00"),
                "2026-06-19T00:00:00+00:00",
                p_item.get("like_count", 0),
                p_item.get("retweet_count", 0),
                p_item.get("reply_count", 0),
                p_item.get("quote_count", 0),
                entities,
                p_item.get("source_query_id"),
            ),
        )
    store._conn.commit()
    store.close()


def _row_count(d: Path, sql: str) -> int:
    store = Store(d / "x.db")
    try:
        return store._conn.execute(sql).fetchone()[0]
    finally:
        store.close()


def test_reattribute_idempotent(tmp_path: Path):
    """Run reattribute twice on a 5-post synthetic DB -> identical state."""
    posts = [
        {"tweet_id": str(i), "author_id": "u1", "author_handle": "u1",
         "text": f"hello world {i}",
         "created_at": f"2026-06-19T00:00:0{i}+00:00"}
        for i in range(5)
    ]
    detection = {
        "brand_keywords": [("minimax", "MiniMax", False)],
    }
    with tempfile.TemporaryDirectory() as d_str:
        d = Path(d_str)
        _seed_db(d, posts, detection)
        counts1 = reattribute_all_posts(d / "x.db", batch_size=2)
        pb_count_1 = _row_count(d, "SELECT COUNT(*) FROM post_brands")
        pm_count_1 = _row_count(d, "SELECT COUNT(*) FROM post_mentions")
        counts2 = reattribute_all_posts(d / "x.db", batch_size=2)
        pb_count_2 = _row_count(d, "SELECT COUNT(*) FROM post_brands")
        pm_count_2 = _row_count(d, "SELECT COUNT(*) FROM post_mentions")
    assert counts1["posts_scanned"] == 5
    assert counts2["posts_scanned"] == 5
    assert pb_count_1 == pb_count_2
    assert pm_count_1 == pm_count_2


def test_reattribute_writes_post_brands(tmp_path: Path):
    """2-brand post -> post_brands has 2 rows summing to 1.0."""
    posts = [
        {"tweet_id": "1", "author_id": "u1", "author_handle": "u1",
         "text": "MiniMax Qwen are great together",
         "created_at": "2026-06-19T00:00:00+00:00"},
    ]
    detection = {
        "brand_keywords": [
            ("minimax", "MiniMax", False),
            ("qwen", "Qwen", False),
        ],
    }
    with tempfile.TemporaryDirectory() as d_str:
        d = Path(d_str)
        _seed_db(d, posts, detection)
        counts = reattribute_all_posts(d / "x.db", batch_size=10)
        store = Store(d / "x.db")
        try:
            rows = store._conn.execute(
                "SELECT brand_id, weight FROM post_brands ORDER BY brand_id"
            ).fetchall()
        finally:
            store.close()
    assert counts["posts_scanned"] == 1
    assert counts["post_brands_written"] == 2
    brand_ids = [r["brand_id"] for r in rows]
    assert "minimax" in brand_ids
    assert "qwen" in brand_ids
    weights = {r["brand_id"]: r["weight"] for r in rows}
    assert weights["minimax"] == pytest.approx(0.5)
    assert weights["qwen"] == pytest.approx(0.5)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_reattribute_handles_legacy_entities_json_string(tmp_path: Path):
    """posts.entities stored as JSON string (not dict) is handled."""
    with tempfile.TemporaryDirectory() as d_str:
        d = Path(d_str)
        db = d / "x.db"
        store = Store(db)
        store._conn.execute(
            "INSERT OR IGNORE INTO brands(brand_id, display_name, accent_color, "
            "is_sentinel, created_at) VALUES (?, ?, ?, ?, ?)",
            ("minimax", "MiniMax", "#a855f7", 0, "2026-06-19T00:00:00+00:00"),
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO brands(brand_id, display_name, accent_color, "
            "is_sentinel, created_at) VALUES (?, ?, ?, ?, ?)",
            ("_unattributed", "Unattributed", "#6b7280", 1,
             "2026-06-19T00:00:00+00:00"),
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO brand_keywords(brand_id, pattern, is_regex, added_at) "
            "VALUES (?, ?, ?, ?)",
            ("minimax", "Kimi", 0, "2026-06-19T00:00:00+00:00"),
        )
        # Insert post with entities as a JSON string (legacy migrator behavior).
        store._conn.execute(
            """
            INSERT INTO posts(
                tweet_id, author_handle, author_id, text, lang,
                created_at, fetched_at, entities
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("1", "u1", "u1", "Kimi is awesome", "en",
             "2026-06-19T00:00:00+00:00",
             "2026-06-19T00:00:00+00:00",
             json.dumps({"hashtags": []})),
        )
        store._conn.commit()
        store.close()
        counts = reattribute_all_posts(d / "x.db", batch_size=10)
        store = Store(d / "x.db")
        try:
            rows = store._conn.execute(
                "SELECT brand_id FROM post_brands WHERE brand_id <> "
                "'_unattributed'"
            ).fetchall()
        finally:
            store.close()
    assert counts["posts_scanned"] == 1
    assert counts["post_brands_written"] >= 1
    brand_ids = [r["brand_id"] for r in rows]
    assert "minimax" in brand_ids


def test_reattribute_dry_run_no_writes(tmp_path: Path):
    """dry_run leaves DB unchanged."""
    posts = [
        {"tweet_id": "1", "author_id": "u1", "author_handle": "u1",
         "text": "MiniMax is the best",
         "created_at": "2026-06-19T00:00:00+00:00"},
    ]
    detection = {
        "brand_keywords": [("minimax", "MiniMax", False)],
    }
    with tempfile.TemporaryDirectory() as d_str:
        d = Path(d_str)
        _seed_db(d, posts, detection)
        before_pb = _row_count(d, "SELECT COUNT(*) FROM post_brands")
        before_pm = _row_count(d, "SELECT COUNT(*) FROM post_mentions")
        counts = reattribute_all_posts(
            d / "x.db", batch_size=10, dry_run=True,
        )
        after_pb = _row_count(d, "SELECT COUNT(*) FROM post_brands")
        after_pm = _row_count(d, "SELECT COUNT(*) FROM post_mentions")
    assert counts["posts_scanned"] == 1
    assert counts["post_brands_written"] >= 1
    assert before_pb == after_pb
    assert before_pm == after_pm


def test_reattribute_limit(tmp_path: Path):
    """--limit 5 only processes 5 posts."""
    posts = [
        {"tweet_id": str(i), "author_id": "u1", "author_handle": "u1",
         "text": f"hello {i}",
         "created_at": f"2026-06-19T00:00:0{i % 10}+00:00"}
        for i in range(20)
    ]
    detection = {
        "brand_keywords": [("minimax", "hello", False)],
    }
    with tempfile.TemporaryDirectory() as d_str:
        d = Path(d_str)
        _seed_db(d, posts, detection)
        counts = reattribute_all_posts(
            d / "x.db", batch_size=10, limit=5,
        )
    assert counts["posts_scanned"] == 5


def test_reattribute_brand_filter(tmp_path: Path):
    """--model <brand> filters via post_brands JOIN (post-pass)."""
    posts = [
        {"tweet_id": "1", "author_id": "u1", "author_handle": "u1",
         "text": "MiniMax is great",
         "created_at": "2026-06-19T00:00:00+00:00"},
        {"tweet_id": "2", "author_id": "u2", "author_handle": "u2",
         "text": "Qwen is also great",
         "created_at": "2026-06-19T00:00:01+00:00"},
        {"tweet_id": "3", "author_id": "u3", "author_handle": "u3",
         "text": "DeepSeek too",
         "created_at": "2026-06-19T00:00:02+00:00"},
    ]
    detection = {
        "brand_keywords": [
            ("minimax", "MiniMax", False),
            ("qwen", "Qwen", False),
            ("deepseek", "DeepSeek", False),
        ],
    }
    with tempfile.TemporaryDirectory() as d_str:
        d = Path(d_str)
        _seed_db(d, posts, detection)
        counts_all = reattribute_all_posts(
            d / "x.db", batch_size=10, limit=None,
        )
        assert counts_all["posts_scanned"] == 3
        counts_minimax = reattribute_all_posts(
            d / "x.db", batch_size=10, brand_filter="minimax",
        )
    assert counts_minimax["posts_scanned"] == 1


def test_reattribute_cli_subcommand_registered():
    """`reattribute` subcommand is registered in build_parser()."""
    from x_monitor.__main__ import build_parser
    p = build_parser()
    sub_actions = p._subparsers._group_actions[0].choices
    assert "reattribute" in sub_actions
    p_reatt = sub_actions["reattribute"]
    arg_destinations = {a.dest for a in p_reatt._actions}
    assert "batch_size" in arg_destinations
    assert "dry_run" in arg_destinations
    assert "limit" in arg_destinations
    assert "model" in arg_destinations
    assert "with_llm" in arg_destinations
