"""Tests for quote-tweet capture (2026-06-22).

TwitterAPI.io signals a quote/retweet via a nested `quoted_tweet` /
`retweeted_tweet` object, not via isQuote/isRetweet (never set). These
cover: (1) normalize extracts the quoted id+text and sets is_quote from
object presence; (2) attribution folds the quoted text in so a quote-repost
of a brand tweet attributes even when the commentary lacks the keyword.
"""
from __future__ import annotations

from x_monitor.apify import _normalize_tweet
from x_monitor.run import _build_brand_index, _attribute_call_items


def test_normalize_tweet_extracts_quoted_content():
    item = {
        "id": "111",
        "text": "this is huge \U0001f525",  # reposter commentary, no brand word
        "lang": "en",
        "createdAt": "2026-06-22T00:00:00Z",
        "author": {"userName": "reposter", "name": "R", "followers": 10},
        "quoted_tweet": {
            "id": "222",
            "text": "GLM 5.2 is now available — a coding model",
            "author": {"userName": "Zai_org"},
        },
    }
    n = _normalize_tweet(item)
    assert n["is_quote"] is True
    assert n["is_retweet"] is False
    assert n["quoted_status_id"] == "222"
    assert n["quoted_text"] == "GLM 5.2 is now available — a coding model"
    assert n["quoted_author_handle"] == "Zai_org"


def test_normalize_tweet_no_quote_is_clean():
    item = {
        "id": "111",
        "text": "hello",
        "lang": "en",
        "createdAt": "2026-06-22T00:00:00Z",
        "author": {"userName": "a", "name": "A", "followers": 0},
    }
    n = _normalize_tweet(item)
    assert n["is_quote"] is False
    assert n["quoted_status_id"] is None
    assert n["quoted_text"] is None
    assert n["quoted_author_handle"] is None


def test_normalize_tweet_detects_retweet_via_object():
    item = {
        "id": "111",
        "text": "RT @x: hi",
        "lang": "en",
        "createdAt": "2026-06-22T00:00:00Z",
        "author": {"userName": "a", "name": "A", "followers": 0},
        "retweeted_tweet": {"id": "999", "text": "hi"},
    }
    n = _normalize_tweet(item)
    assert n["is_retweet"] is True
    assert n["is_quote"] is False  # a pure RT is not a quote


def test_attribute_folds_quoted_text():
    """Commentary lacks the keyword, but the quoted tweet contains it ->
    must still attribute to the brand."""
    brand_tokens = {"glm": ["glm"]}
    index, brand_search_terms = _build_brand_index(brand_tokens, ["glm"])
    items = [
        {
            "id": "111",
            "text": "\U0001f525\U0001f525\U0001f525",  # no brand keyword
            "quoted_text": "GLM 5.2 just dropped",
            "created_at": "2026-06-22T00:00:00+00:00",
            "entities": {},
        }
    ]
    _attribute_call_items(items, index, brand_search_terms)
    assert items[0].get("brand_id") == "glm"
    assert not items[0].get("_unattributed")
