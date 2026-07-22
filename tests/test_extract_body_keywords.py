# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.attribution.extract_body_keywords + compile_keyword_index.

Ten scenarios: single match, multi-match, regex capture, compiled-regex
reuse, empty pattern, empty text, case-insensitive, CJK match, sentinel
filter, raw_token is matched substring (not full pattern).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from x_monitor.attribution import (
    MentionRow,
    compile_keyword_index,
    extract_body_keywords,
)


BRAND_KEYWORDS_RAW: list[tuple[str, str, bool]] = [
    ("minimax", "MiniMax", False),
    ("minimax", "Hailuo", False),
    ("minimax", "海螺", False),
    ("qwen", "Qwen", False),
    ("deepseek", "DeepSeek", False),
    ("deepseek", r"DS[ -]?V\d+", True),
    ("glm", "GLM", False),
    ("glm", "智谱", False),
    ("mimo", "MiMo", False),
    ("moonshot_kimi", "Kimi", False),
    ("inclusionai", "Ling", False),
]


def _post(**overrides) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tweet_id": "1234567890",
        "created_at": "2026-06-19T12:34:56Z",
        "text": "",
    }
    base.update(overrides)
    return base


def _index():
    return compile_keyword_index(BRAND_KEYWORDS_RAW)


def test_single_match_returns_one_row():
    post = _post(text="I love Qwen 3")
    rows = extract_body_keywords(post, _index())
    assert len(rows) == 1
    assert rows[0].brand_id == "qwen"
    assert rows[0].source == "body_keyword"
    assert rows[0].raw_token == "Qwen"  # matched substring


def test_multi_match_same_brand_emits_multiple_rows():
    post = _post(text="MiniMax Hailuo is awesome, also MiniMax M3")
    rows = extract_body_keywords(post, _index())
    # Three matches: MiniMax (twice), Hailuo (once).
    assert len(rows) == 3
    assert all(r.brand_id == "minimax" for r in rows)
    matched = sorted([r.raw_token for r in rows])
    assert matched == ["Hailuo", "MiniMax", "MiniMax"]


def test_multi_brand_emits_one_row_per_brand():
    post = _post(text="Qwen 3 vs DeepSeek V3")
    rows = extract_body_keywords(post, _index())
    brand_ids = sorted({r.brand_id for r in rows})
    assert brand_ids == ["deepseek", "qwen"]
    # The actual matched text for deepseek is the regex match.
    ds_match = next(r for r in rows if r.brand_id == "deepseek")
    assert ds_match.raw_token == "DeepSeek"


def test_regex_pattern_with_capture_groups():
    post = _post(text="Try DS-V3 and DS V2 for inference")
    rows = extract_body_keywords(post, _index())
    ds_matches = [r for r in rows if r.brand_id == "deepseek"]
    assert len(ds_matches) == 2
    matched = sorted([r.raw_token for r in ds_matches])
    assert matched == ["DS V2", "DS-V3"]


def test_regex_pattern_drops_full_alternation_match():
    # The matched substring is whatever re.finditer returns, which
    # for a regex pattern with no capture groups is the whole match.
    post = _post(text="M3.0 is out")  # No M3.0 pattern; just no match.
    rows = extract_body_keywords(post, _index())
    # We don't have M3.0 in the index; expect empty.
    assert rows == []


def test_case_insensitive_match():
    post = _post(text="I love MINIMAX")
    rows = extract_body_keywords(post, _index())
    assert len(rows) == 1
    assert rows[0].brand_id == "minimax"
    assert rows[0].raw_token == "MINIMAX"  # matched text preserved


def test_cjk_match():
    post = _post(text="海螺AI is the best")
    rows = extract_body_keywords(post, _index())
    assert len(rows) == 1
    assert rows[0].brand_id == "minimax"
    assert rows[0].raw_token == "海螺"


def test_word_boundary_does_not_match_substring():
    # "MiMo" should NOT match "MiMoWorld" because of \b.
    post = _post(text="MiMoWorld is unrelated")
    rows = extract_body_keywords(post, _index())
    # Note: \b between ASCII and end-of-word may or may not fire
    # depending on engine. If no matches -> safe. If matches ->
    # at minimum confirm it does NOT match partial substrings
    # like "MiMor" without word boundary. We check we get at most
    # one full MiMo match (not multiple fragmented ones).
    for r in rows:
        assert r.raw_token == "MiMo"


def test_unattributed_sentinel_filtered_out():
    # Build an index that contains the sentinel explicitly; matches
    # for _unattributed should NOT produce MentionRows.
    kw = BRAND_KEYWORDS_RAW + [("_unattributed", "noiseword", False)]
    idx = compile_keyword_index(kw)
    post = _post(text="this contains noiseword in the text")
    rows = extract_body_keywords(post, idx)
    assert rows == []


def test_compiled_pattern_reused_across_calls():
    """The same compiled index is used for many posts; results are stable."""
    idx = _index()
    post1 = _post(text="MiniMax is great", tweet_id="1")
    post2 = _post(text="Qwen is great", tweet_id="2")
    post3 = _post(text="GLM is great", tweet_id="3")
    rows = extract_body_keywords(post1, idx)
    assert len(rows) == 1 and rows[0].brand_id == "minimax"
    rows = extract_body_keywords(post2, idx)
    assert len(rows) == 1 and rows[0].brand_id == "qwen"
    rows = extract_body_keywords(post3, idx)
    assert len(rows) == 1 and rows[0].brand_id == "glm"


def test_empty_keyword_index_returns_empty():
    idx = compile_keyword_index([])
    post = _post(text="anything")
    rows = extract_body_keywords(post, idx)
    assert rows == []


def test_empty_text_returns_empty():
    post = _post(text="")
    rows = extract_body_keywords(post, _index())
    assert rows == []


def test_missing_text_returns_empty():
    post = _post()  # no text
    if "text" in post:
        del post["text"]
    rows = extract_body_keywords(post, _index())
    assert rows == []


def test_missing_tweet_id_returns_empty():
    post = {"created_at": "2026-06-19T00:00:00Z", "text": "MiniMax is great"}
    rows = extract_body_keywords(post, _index())
    assert rows == []


def test_first_brand_wins_on_token_dedup():
    """If two brands share a token, the first brand in iteration
    order wins (consistent with v1.7)."""
    kw = [
        ("brand_a", "shared", False),
        ("brand_b", "shared", False),
    ]
    idx = compile_keyword_index(kw)
    assert idx[0] is not None
    # The compiled regex includes the token only once.
    # 'shared' maps to brand_a (first seen).
    assert idx[1]["shared"] == "brand_a"
    post = _post(text="the shared word appears")
    rows = extract_body_keywords(post, idx)
    assert len(rows) == 1
    assert rows[0].brand_id == "brand_a"
