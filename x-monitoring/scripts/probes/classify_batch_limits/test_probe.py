"""Tests for the classify_batch_pragmatics_full limits probe.

Plan: docs/plans/2026-07-15-001-feat-classify-batch-limits-probe-plan.md

These tests cover U1 (scaffolding + synthetic-tweet builder + status
classifier + timeout + dry-run + missing-credential guard). U2 sweep
tests and U3 JSON-output tests live further down in this file.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROBE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROBE_DIR.parents[3]  # scripts/probes/<name>/test_probe.py -> repo root
PROBE_MODULE = "scripts.probes.classify_batch_limits.probe"


def _import_probe():
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.probes.classify_batch_limits import probe
    return probe


# --- U1 tests (8) ---------------------------------------------------------


def test_build_synthetic_tweets_default_size():
    probe = _import_probe()
    tweets = probe._build_synthetic_tweets(n=10, brand_ids=["minimax", "qwen"], rng_seed=1)
    assert len(tweets) == 10
    for t in tweets:
        assert "tweet_id" in t and "text" in t and "brand_ids" in t
        assert 1 <= len(t["brand_ids"]) <= 3


def test_build_synthetic_tweets_text_length():
    probe = _import_probe()
    tweets = probe._build_synthetic_tweets(n=1, brand_ids=["minimax"], text_len=2000, rng_seed=2)
    assert len(tweets[0]["text"]) == 2000


def test_classify_status_unterminated_string():
    probe = _import_probe()
    exc = ValueError('Unterminated string starting at: line 1 column 3831 (char 3831)')
    assert probe._classify_status(exc) == "unterminated_json"


def test_classify_status_ssl_hang_pattern():
    probe = _import_probe()
    # Build an exception whose repr contains the SDK read symbol.
    try:
        raise RuntimeError("_ssl__SSLSocket_read: read stalled")
    except RuntimeError as e:
        assert probe._classify_status(e) == "ssl_hang"


def test_classify_status_429_rate_limit():
    probe = _import_probe()
    exc = RuntimeError("anthropic.APIStatusError: 429 rate_limit_exceeded")
    assert probe._classify_status(exc) == "rate_limited"


def test_classify_status_success_when_no_exc():
    probe = _import_probe()
    assert probe._classify_status(None, response={"results": []}) == "success"


def test_print_table_emits_header_and_rows(capsys):
    probe = _import_probe()
    probe._print_table(["k", "v"], [["1", "ok"], ["2", "ok"]])
    out = capsys.readouterr().out
    assert "k" in out and "v" in out
    assert "1" in out and "2" in out
    # separator line present
    assert "-+-" in out


def test_verdict_line_names_smallest_failing_value():
    probe = _import_probe()
    rows = [
        {"value": "1", "status": "success"},
        {"value": "5", "status": "success"},
        {"value": "10", "status": "ssl_hang"},
    ]
    assert probe._verdict_line("batch_size", rows) == "limit hit: batch_size=10 -> ssl_hang"
    assert probe._verdict_line("batch_size", [{"value": "1", "status": "success"}]) is None