"""Test for get_all_posts chronological ordering with Twitter-legacy created_at.

This is a regression test for the bug where model_detail.html.j2 renders
posts ordered by lexicographic sort of the Twitter-legacy `created_at` TEXT
column, which puts e.g. "Wed Jun 10 21:31:32 +0000 2026" before the
chronologically newer "Mon Jun 15 19:05:46 +0000 2026" because:
  - "Wed" > "Mon" alphabetically, and
  - "10" > "09" / "08" / "06"
The result is the user sees 5-day-old posts on /model/<brand_id> even
though fresher posts are in the DB.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from x_monitor.store import Store


def _make_post(tweet_id: str, created_at: str) -> dict:
    return {
        "tweet_id": tweet_id,
        "brand_id": "minimax",
        "author_handle": "user1",
        "author_id": "u1",
        "text": "hello",
        "lang": "en",
        "created_at": created_at,
        "like_count": 5,
        "retweet_count": 1,
        "entities": {"user_mentions": []},
    }


def test_get_all_posts_orders_chronologically_with_twitter_legacy_timestamps():
    """Posts stored with Twitter-legacy created_at format must be returned
    in chronological DESC order, not lexicographic DESC order.

    Lex DESC would yield: Wed Jun 10 21:31:32, Wed Jun 10 17:56:50,
                          ..., Tue Jun 09 23:20:30, ..., Mon Jun 15 19:05:46
    Chronological DESC should yield: Mon Jun 15 19:05:46,
                          Sun Jun 14 ..., Sat Jun 06 ...
    """
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            # Insert in a non-sorted order to be sure ordering is from the query.
            store.insert_posts(
                [
                    # Newest chronologically
                    _make_post("newest", "Mon Jun 15 19:05:46 +0000 2026"),
                    # Oldest
                    _make_post("oldest", "Sat Jun 06 13:06:15 +0000 2026"),
                    # Lex-largest (Wed Jun 10) — must NOT come first
                    _make_post("wed_jun10", "Wed Jun 10 21:31:32 +0000 2026"),
                    # Mid-range
                    _make_post("mid_sun", "Sun Jun 14 22:00:00 +0000 2026"),
                    _make_post("mid_tue", "Tue Jun 09 12:00:00 +0000 2026"),
                ]
            )
            rows = store.get_all_posts("minimax")
            ids = [r["tweet_id"] for r in rows]
            assert ids == ["newest", "mid_sun", "wed_jun10", "mid_tue", "oldest"], (
                f"Expected chronological DESC, got: {ids}"
            )
        finally:
            store.close()
