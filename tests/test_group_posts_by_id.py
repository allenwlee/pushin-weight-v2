"""U2 dedup tests for _home_routes._group_posts_by_id."""

import pytest

from x_monitor._home_routes import _group_posts_by_id


def _post(*, tweet_id, brand_nickname, brand_block=None, **rest):
    """Build a post in the shape `_denormalize_posts` produces."""
    return {
        "tweet_id": tweet_id,
        "text": "stub",
        "created_at": "2026-07-14T01:18:36+00:00",
        "brand_nicknames": [brand_nickname],
        "brands": [
            brand_block
            or {
                "nickname": brand_nickname,
                "display_name": brand_nickname,
                "display_name_en": brand_nickname,
                "display_name_zh_cn": brand_nickname,
            }
        ],
        "classifications_by_brand": {
            brand_nickname: rest.pop(
                "classifications",
                {"discourse": [], "post_types": [], "sentiments": []},
            )
        },
        "account": {"handle": "@u", "role": None, "role_label": None},
        **rest,
    }


def test_group_merge_dedups_two_brands_one_post():
    posts = [
        _post(
            tweet_id="t-1",
            brand_nickname="minimax",
            classifications={"discourse": ["fud"], "post_types": [], "sentiments": []},
        ),
        _post(
            tweet_id="t-1",
            brand_nickname="qwen",
            classifications={"discourse": ["cope"], "post_types": [], "sentiments": []},
        ),
    ]
    out = _group_posts_by_id(posts)
    assert len(out) == 1, f"expected 1 row, got {len(out)}"
    row = out[0]
    assert "minimax" in row["brand_nicknames"]
    assert "qwen" in row["brand_nicknames"]
    assert {b["nickname"] for b in row["brands"]} == {"minimax", "qwen"}
    # classifications preserved per brand
    assert row["classifications_by_brand"]["minimax"]["discourse"] == ["fud"]
    assert row["classifications_by_brand"]["qwen"]["discourse"] == ["cope"]


def test_group_preserves_first_seen_order():
    posts = [
        _post(tweet_id="t-a", brand_nickname="minimax"),
        _post(tweet_id="t-b", brand_nickname="qwen"),
        _post(tweet_id="t-a", brand_nickname="qwen"),
    ]
    out = _group_posts_by_id(posts)
    assert [p["tweet_id"] for p in out] == ["t-a", "t-b"]


def test_group_drops_posts_without_tweet_id():
    posts = [
        {"tweet_id": None, "text": "no id"},
        _post(tweet_id="t-1", brand_nickname="minimax"),
    ]
    out = _group_posts_by_id(posts)
    assert len(out) == 1
    assert out[0]["tweet_id"] == "t-1"


def test_group_keeps_first_occurrence_text():
    posts = [
        _post(tweet_id="t-1", brand_nickname="minimax", text="first-occurrence-text"),
        _post(tweet_id="t-1", brand_nickname="qwen", text="second-occurrence-text"),
    ]
    out = _group_posts_by_id(posts)
    assert out[0]["text"] == "first-occurrence-text"
