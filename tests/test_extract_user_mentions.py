# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.attribution.extract_user_mentions (R3).

Eight scenarios per the plan: happy, unknown handle, empty entities,
malformed username, missing tweet_id/created_at, integer author_id,
empty entities list, entities with no user_mentions key.
"""

from __future__ import annotations

from typing import Any

import pytest

from x_monitor.attribution import MentionRow, extract_user_mentions


BRAND_ACCOUNTS: dict[str, str] = {
    "1001": "minimax",
    "1002": "qwen",
    "1003": "deepseek",
}


def _post(**overrides) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tweet_id": "1234567890",
        "created_at": "2026-06-19T12:34:56Z",
        "entities": {},
    }
    base.update(overrides)
    return base


def test_happy_path_single_known_handle():
    post = _post(
        entities={
            "user_mentions": [
                {"id": "1001", "username": "MiniMaxAI"},
            ],
        }
    )
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert len(rows) == 1
    assert rows[0] == MentionRow(
        post_id="1234567890",
        brand_id="minimax",
        source="user_mention",
        raw_token="@MiniMaxAI",
        mentioned_at="2026-06-19T12:34:56Z",
    )


def test_unknown_handle_brand_id_null():
    post = _post(
        entities={
            "user_mentions": [
                {"id": "9999", "username": "random_user"},
            ],
        }
    )
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert len(rows) == 1
    assert rows[0].brand_id is None
    assert rows[0].raw_token == "@random_user"


def test_empty_entities_returns_empty():
    post = _post(entities={})
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert rows == []


def test_entities_with_no_user_mentions_key_returns_empty():
    post = _post(entities={"hashtags": [{"tag": "kimi"}]})
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert rows == []


def test_malformed_username_missing_id_skipped():
    # Missing 'id' -> skipped (can't resolve brand).
    post = _post(
        entities={
            "user_mentions": [
                {"username": "MiniMaxAI"},  # no id
                {"id": "1002", "username": "Alibaba_Qwen"},  # OK
            ],
        }
    )
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert len(rows) == 1
    assert rows[0].brand_id == "qwen"
    assert rows[0].raw_token == "@Alibaba_Qwen"


def test_malformed_username_missing_username_skipped():
    post = _post(
        entities={
            "user_mentions": [
                {"id": "1001"},  # no username
                {"id": "1002", "username": "Alibaba_Qwen"},
            ],
        }
    )
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert len(rows) == 1
    assert rows[0].brand_id == "qwen"


def test_integer_author_id_is_coerced_to_string():
    # TwitterAPI.io sometimes returns id as int in the parsed JSON.
    post = _post(
        entities={
            "user_mentions": [
                {"id": 1001, "username": "MiniMaxAI"},  # int
            ],
        }
    )
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert len(rows) == 1
    assert rows[0].brand_id == "minimax"


def test_missing_tweet_id_returns_empty():
    post = {"created_at": "2026-06-19T00:00:00Z", "entities": {}}
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert rows == []


def test_missing_created_at_returns_empty():
    post = {"tweet_id": "1", "entities": {}}
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert rows == []


def test_entities_none_returns_empty():
    post = _post(entities=None)
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert rows == []


def test_entities_string_null_returns_empty():
    post = _post(entities="null")
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert rows == []


def test_multiple_mentions_all_returned():
    post = _post(
        entities={
            "user_mentions": [
                {"id": "1001", "username": "MiniMaxAI"},
                {"id": "1002", "username": "Alibaba_Qwen"},
                {"id": "9999", "username": "random_user"},
            ],
        }
    )
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert len(rows) == 3
    brand_ids = [r.brand_id for r in rows]
    assert brand_ids == ["minimax", "qwen", None]


def test_falls_back_to_screen_name_if_no_username():
    # Some X payloads use screen_name instead of username.
    post = _post(
        entities={
            "user_mentions": [
                {"id": "1001", "screen_name": "MiniMaxAI"},
            ],
        }
    )
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert len(rows) == 1
    assert rows[0].raw_token == "@MiniMaxAI"


def test_non_dict_entry_in_user_mentions_is_skipped():
    post = _post(
        entities={
            "user_mentions": [
                "not a dict",
                {"id": "1001", "username": "MiniMaxAI"},
            ],
        }
    )
    rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
    assert len(rows) == 1
    assert rows[0].brand_id == "minimax"
