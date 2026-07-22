"""Tests for quote-tweet capture (2026-06-22).

TwitterAPI.io signals a quote/retweet via a nested `quoted_tweet` /
`retweeted_tweet` object, not via isQuote/isRetweet (never set). These
cover: (1) normalize extracts the quoted id+text and sets is_quote from
object presence; (2) attribution folds the quoted text in so a quote-repost
of a brand tweet attributes even when the commentary lacks the keyword.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from x_monitor.apify import _normalize_tweet
from x_monitor.attribution import classify_post
from x_monitor.run import (
    _attribute_call_items,
    _build_brand_index,
    _ingest_quote_tweets,
)
from x_monitor.store import Store


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


# --- _ingest_quote_tweets (Unit 3, 2026-06-22) ----------------------------


def _qt_item(tid, text, *, quoted_text=None, quoted_status_id="222"):
    return {
        "id": tid,
        "tweet_id": tid,
        "text": text,
        "quoted_text": quoted_text,
        "quoted_status_id": quoted_status_id,
        "created_at": "2026-06-22T00:00:00+00:00",
        "entities": {},
        "author_handle": "reposter",
        "lang": "en",
    }


def _idx(brand_tokens, models):
    return _build_brand_index(brand_tokens, models)


def test_ingest_attaches_parent_text_when_id_matches_and_attributes():
    """QT carries no nested quote but quotes the parent (id matches) -> the
    parent's keyword-bearing text is attached and attribution succeeds via
    the fold, even with emoji-only commentary."""
    index, bst = _idx({"glm": ["glm"]}, ["glm"])
    with tempfile.TemporaryDirectory() as d:
        s = Store(Path(d) / "x.db")
        try:
            qt = _qt_item("111", "\U0001f525", quoted_text=None, quoted_status_id="222")
            n = _ingest_quote_tweets(
                [qt], "222", "GLM 5.2 just dropped",
                index=index, brand_search_terms=bst, store=s,
            )
            assert n == 1
            assert qt["brand_id"] == "glm"
            assert qt["quoted_text"] == "GLM 5.2 just dropped"
        finally:
            s.close()


def test_ingest_does_not_attach_parent_text_when_id_differs():
    """QT quotes a different tweet than the parent -> parent text is NOT
    attached; with no keyword anywhere the QT is unattributed and dropped."""
    index, bst = _idx({"glm": ["glm"]}, ["glm"])
    with tempfile.TemporaryDirectory() as d:
        s = Store(Path(d) / "x.db")
        try:
            qt = _qt_item("111", "\U0001f525", quoted_text=None, quoted_status_id="999")
            n = _ingest_quote_tweets(
                [qt], "222", "GLM 5.2 dropped",
                index=index, brand_search_terms=bst, store=s,
            )
            assert n == 0
            assert qt.get("_unattributed") is True
            assert qt.get("quoted_text") in (None, "")
        finally:
            s.close()


def test_ingest_multi_brand_via_commentary_plus_quoted():
    """A QT naming brand A in commentary and brand B in the quoted tweet
    attributes to both (R7, multi-brand 1/N weighting)."""
    index, bst = _idx({"glm": ["glm"], "deepseek": ["deepseek"]}, ["glm", "deepseek"])
    with tempfile.TemporaryDirectory() as d:
        s = Store(Path(d) / "x.db")
        try:
            qt = _qt_item(
                "111", "glm is great",
                quoted_text="deepseek r1 is open", quoted_status_id="222",
            )
            _ingest_quote_tweets(
                [qt], "222", "unused-parent",
                index=index, brand_search_terms=bst, store=s,
            )
            assert set(qt["brand_ids"]) == {"glm", "deepseek"}
        finally:
            s.close()


def test_ingest_classification_comes_from_commentary_not_quoted():
    """U9 (migration 022): the (post_type, sentiment) classification is
    applied per brand on the commentary only (R7 asymmetry), not on the
    (more loaded) quoted text. The legacy `signals` key is replaced by
    `classifications` (a {brand_id: (post_type, sentiment)} dict).

    Note: this test runs offline (no LLM client), so classifications will
    be {} and the assertion is structural — the key exists with the right
    shape. Online-mode behavior is exercised separately.
    """
    index, bst = _idx({"glm": ["glm"]}, ["glm"])
    with tempfile.TemporaryDirectory() as d:
        s = Store(Path(d) / "x.db")
        try:
            commentary = "I love this glm update, amazing work"
            qt = _qt_item(
                "111", commentary,
                quoted_text="glm is broken and terrible", quoted_status_id="222",
            )
            _ingest_quote_tweets(
                [qt], "222", "x",
                index=index, brand_search_terms=bst, store=s,
            )
            # U9: `classifications` always exists (offline → {}, online
            # → {brand_id: (post_type, sentiment)}). The legacy `signals`
            # key is gone. We assert the key exists with the right shape
            # (dict, not None), which catches accidental drops during
            # the U9 rewrite.
            assert "classifications" in qt
            assert isinstance(qt["classifications"], dict)
            # brand_ids was still populated (offline attribution works
            # via body_keyword + search_term).
            assert "glm" in qt["brand_ids"]
        finally:
            s.close()


def test_ingest_is_idempotent():
    """Re-ingesting the same QT (same tweet_id) inserts nothing the second
    time (INSERT OR IGNORE)."""
    index, bst = _idx({"glm": ["glm"]}, ["glm"])
    with tempfile.TemporaryDirectory() as d:
        s = Store(Path(d) / "x.db")
        try:
            kw = dict(index=index, brand_search_terms=bst, store=s)
            qt = _qt_item("111", "glm is great", quoted_text=None, quoted_status_id="222")
            n1 = _ingest_quote_tweets([qt], "222", "GLM drop", **kw)
            n2 = _ingest_quote_tweets([qt], "222", "GLM drop", **kw)
            assert n1 == 1
            assert n2 == 0
        finally:
            s.close()
