# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.attribution.extract_search_term_match (R6).

Five scenarios: matched term, unmatched term (emits sentinel row
with brand_id=None), no keywords at all, case-insensitive match,
multiple matching terms each emit one row.
"""

from __future__ import annotations

from typing import Any

import pytest

from x_monitor.attribution import MentionRow, extract_search_term_match


BRAND_SEARCH_TERMS: dict[str, str] = {
    "minimax": "minimax",
    "qwen": "qwen",
    "deepseek": "deepseek",
    "kimi": "moonshot_kimi",
}


def _post(**overrides) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tweet_id": "1234567890",
        "created_at": "2026-06-19T12:34:56Z",
    }
    base.update(overrides)
    return base


def test_matched_term_emits_one_row():
    post = _post()
    rows = extract_search_term_match(
        post,
        search_query=["minimax"],
        brand_search_terms=BRAND_SEARCH_TERMS,
    )
    assert len(rows) == 1
    assert rows[0] == MentionRow(
        post_id="1234567890",
        brand_id="minimax",
        source="search_term",
        raw_token="minimax",
        mentioned_at="2026-06-19T12:34:56Z",
    )


def test_unmatched_keyword_emits_sentinel_row():
    # R6: always emits at least one row, even when no keyword matches.
    post = _post()
    rows = extract_search_term_match(
        post,
        search_query=["random_term"],
        brand_search_terms=BRAND_SEARCH_TERMS,
    )
    assert len(rows) == 1
    assert rows[0].brand_id is None
    assert rows[0].source == "search_term"
    assert rows[0].raw_token == ""  # raw_token empty for unmatched


def test_empty_search_query_emits_sentinel_row():
    post = _post()
    rows = extract_search_term_match(
        post,
        search_query=[],
        brand_search_terms=BRAND_SEARCH_TERMS,
    )
    assert len(rows) == 1
    assert rows[0].brand_id is None
    assert rows[0].raw_token == ""


def test_multiple_matching_terms_each_emit_row():
    post = _post()
    rows = extract_search_term_match(
        post,
        search_query=["minimax", "qwen", "deepseek"],
        brand_search_terms=BRAND_SEARCH_TERMS,
    )
    assert len(rows) == 3
    brand_ids = [r.brand_id for r in rows]
    assert brand_ids == ["minimax", "qwen", "deepseek"]
    raw_tokens = [r.raw_token for r in rows]
    assert raw_tokens == ["minimax", "qwen", "deepseek"]


def test_case_insensitive_match_when_registry_differs():
    # Brand_search_terms may have lowercase keys; the query may be
    # mixed-case. The extractor casefolds the term to find a match.
    registry: dict[str, str] = {"minimax": "minimax"}  # lowercase key
    post = _post()
    rows = extract_search_term_match(
        post,
        search_query=["MiniMax"],  # mixed case
        brand_search_terms=registry,
    )
    assert len(rows) == 1
    assert rows[0].brand_id == "minimax"


def test_missing_tweet_id_returns_empty():
    post = {"created_at": "2026-06-19T00:00:00Z"}
    rows = extract_search_term_match(
        post,
        search_query=["minimax"],
        brand_search_terms=BRAND_SEARCH_TERMS,
    )
    assert rows == []


def test_missing_created_at_returns_empty():
    post = {"tweet_id": "1"}
    rows = extract_search_term_match(
        post,
        search_query=["minimax"],
        brand_search_terms=BRAND_SEARCH_TERMS,
    )
    assert rows == []


def test_empty_term_skipped():
    post = _post()
    rows = extract_search_term_match(
        post,
        search_query=["", "minimax", ""],
        brand_search_terms=BRAND_SEARCH_TERMS,
    )
    # Empty terms are skipped; only "minimax" emits a row.
    assert len(rows) == 1
    assert rows[0].brand_id == "minimax"
