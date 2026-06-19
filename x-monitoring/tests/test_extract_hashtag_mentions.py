# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.attribution.extract_hashtag_mentions (R4).

Six scenarios: happy, case-insensitive, unknown hashtag silently dropped,
empty entities, missing tweet_id, hashtag with leading '#' already
(we re-strip), entities with no hashtags key.
"""

from __future__ import annotations

from typing import Any

import pytest

from x_monitor.attribution import MentionRow, extract_hashtag_mentions


BRAND_HASHTAGS: dict[str, str] = {
    "kimi": "moonshot_kimi",
    "minimax": "minimax",
    "qwen": "qwen",
    "deepseek": "deepseek",
}


def _post(**overrides) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tweet_id": "1234567890",
        "created_at": "2026-06-19T12:34:56Z",
        "entities": {},
    }
    base.update(overrides)
    return base


def test_happy_path_single_tag():
    post = _post(entities={"hashtags": [{"tag": "kimi"}]})
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert len(rows) == 1
    assert rows[0] == MentionRow(
        post_id="1234567890",
        brand_id="moonshot_kimi",
        source="hashtag",
        raw_token="#kimi",
        mentioned_at="2026-06-19T12:34:56Z",
    )


def test_case_insensitive_match():
    post = _post(entities={"hashtags": [{"tag": "MINIMAX"}]})
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert len(rows) == 1
    assert rows[0].brand_id == "minimax"
    assert rows[0].raw_token == "#minimax"  # lowercased


def test_unknown_hashtag_silently_dropped():
    post = _post(entities={"hashtags": [{"tag": "worldcup-2026"}]})
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert rows == []


def test_mixed_known_and_unknown_keeps_only_known():
    post = _post(
        entities={
            "hashtags": [
                {"tag": "kimi"},          # known
                {"tag": "worldcup-2026"}, # unknown
                {"tag": "Qwen"},          # known (case insensitive)
            ],
        }
    )
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    brand_ids = [r.brand_id for r in rows]
    assert brand_ids == ["moonshot_kimi", "qwen"]


def test_empty_entities_returns_empty():
    post = _post(entities={})
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert rows == []


def test_entities_with_no_hashtags_key_returns_empty():
    post = _post(entities={"user_mentions": []})
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert rows == []


def test_hashtag_with_leading_hash_is_stripped():
    # X API never returns the leading '#', but defensive normalization
    # is implemented.
    post = _post(entities={"hashtags": [{"tag": "#kimi"}]})
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert len(rows) == 1
    assert rows[0].brand_id == "moonshot_kimi"
    assert rows[0].raw_token == "#kimi"


def test_missing_tweet_id_returns_empty():
    post = {"created_at": "2026-06-19T00:00:00Z", "entities": {}}
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert rows == []


def test_entities_none_returns_empty():
    post = _post(entities=None)
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert rows == []


def test_non_dict_entry_is_skipped():
    post = _post(
        entities={
            "hashtags": [
                "not a dict",
                {"tag": "kimi"},
            ],
        }
    )
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert len(rows) == 1
    assert rows[0].brand_id == "moonshot_kimi"


def test_empty_tag_skipped():
    post = _post(entities={"hashtags": [{"tag": ""}]})
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert rows == []


def test_missing_tag_key_skipped():
    post = _post(entities={"hashtags": [{"other_key": "value"}]})
    rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
    assert rows == []
