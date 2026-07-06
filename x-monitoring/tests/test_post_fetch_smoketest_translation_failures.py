"""U7 (plan 2026-07-04): translation failure breakdown in smoketest report.

Plan: docs/plans/2026-07-04-001-feat-post-fetch-smoketest-and-prompt-tuning-plan.md
Unit U7.

Verifies:
- A batch whose `translate_batch_pragmatics` raises is attributed to every
  tweet in the input batch (per-tweet `class`, `msg`, `retries`).
- The '=== TRANSLATION FAILURES ===' section is printed with one line per
  tweet when the failure path is taken.
- A successful batch omits the section.
- `_MAX_RETRIES` is read from the translator module's `_MAX_RETRIES`
  constant (not hardcoded).
- The whole-batch failure path leaves `n_failed_translate` matching the
  input batch size.

Test strategy:
- We monkeypatch `_call_with_retry` in the translator module to raise
  immediately (no sleep backoff between retries) so the test runs in
  milliseconds rather than the real ~7s per batch.
- We monkeypatch `AnthropicClaudeClient` to a fake that has no LLM
  behavior of its own — `_call_with_retry` is what the smoketest path
  invokes, so the fake just needs to exist.
"""

from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import pytest


class _StubClaudeClient:
    """Empty stub — `_call_with_retry` is monkeypatched in these tests,
    so the LLM behavior is fully controlled by the test.
    """

    def messages_create(self, **kwargs):
        raise RuntimeError("stub should not be called when _call_with_retry is mocked")


def _monkey_call_with_retry(monkeypatch, exc_to_raise: Exception):
    """Replace _call_with_retry to raise `exc_to_raise` on every call,
    without the real sleep-backoff. This makes the failure tests fast.
    """
    from x_monitor import translator

    def _raise(_client, _prompt):
        raise exc_to_raise

    monkeypatch.setattr(translator, "_call_with_retry", _raise)


def _run_pipeline_with_posts(posts, args, monkeypatch):
    """Invoke _run_pipeline with the given posts and a patched
    AnthropicClaudeClient. Returns (rc, stdout).
    """
    from scripts import post_fetch_smoketest
    from x_monitor import translator

    monkeypatch.setattr(
        translator, "AnthropicClaudeClient", lambda: _StubClaudeClient()
    )

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = post_fetch_smoketest._run_pipeline(
            posts, [], args,
        )
    return rc, out_buf.getvalue()


def test_u7_whole_batch_failure_attributes_per_tweet(monkeypatch):
    """RuntimeError on the LLM call → every tweet in the input gets
    a translation_errors entry with `class`, `msg`, `retries`.
    """
    _monkey_call_with_retry(
        monkeypatch, RuntimeError("minimax proxy 502: upstream unavailable")
    )

    posts = [
        {"tweet_id": "t1", "id": "t1", "text": "post 1",
         "brand_ids": ["kimi"]},
        {"tweet_id": "t2", "id": "t2", "text": "post 2",
         "brand_ids": ["kimi"]},
        {"tweet_id": "t3", "id": "t3", "text": "post 3",
         "brand_ids": ["kimi"]},
    ]
    args = argparse.Namespace(
        source="latest-cycle", limit=10, sample=3, strict_budget=False,
    )
    rc, out = _run_pipeline_with_posts(posts, args, monkeypatch)
    assert rc == 0  # fail-soft: never aborts

    # The TRANSLATION FAILURES section appears.
    assert "=== TRANSLATION FAILURES" in out
    # All 3 tweet_ids are attributed.
    for tid in ("t1", "t2", "t3"):
        assert f"tweet_id={tid}" in out, f"{tid} missing from report"
    # Each line carries the exception class + retries.
    assert "class=RuntimeError" in out
    assert "retries=3" in out  # _MAX_RETRIES is 3 in the translator
    # The original error message is in the output (truncated).
    assert "proxy 502" in out


def test_u7_no_failure_section_on_success(monkeypatch):
    """A successful translate call → no TRANSLATION FAILURES section."""
    from x_monitor import translator

    # Monkey translate_batch_pragmatics to return successful rows
    # without going through the real LLM path.
    # Plan 2026-07-06-001: translator no longer emits discourse_role;
    # only classifier (per-brand) does. Successful rows reflect the
    # post-grace translator return contract.
    successful_rows = [
        {"tweet_id": "ok1", "id": "ok1", "text_en": "x",
         "literal_zh": "x", "text_zh_cn": "x",
         "lang_detected": "en",
         "cn_equivalent": "", "annotation": ""},
    ]
    monkeypatch.setattr(
        translator, "translate_batch_pragmatics",
        lambda *a, **kw: successful_rows,
    )
    monkeypatch.setattr(
        translator, "AnthropicClaudeClient", lambda: _StubClaudeClient()
    )

    posts = [
        {"tweet_id": "ok1", "id": "ok1", "text": "post",
         "brand_ids": ["kimi"]},
    ]
    args = argparse.Namespace(
        source="latest-cycle", limit=10, sample=3, strict_budget=False,
    )
    rc, out = _run_pipeline_with_posts(posts, args, monkeypatch)
    assert rc == 0

    # TRANSLATION FAILURES section is omitted.
    assert "=== TRANSLATION FAILURES" not in out


def test_u7_max_retries_read_from_translator_module(monkeypatch):
    """The smoketest reads `_MAX_RETRIES` from `x_monitor.translator`,
    not a hardcoded value. We mock the module attribute to a non-default
    value and assert the report echoes it.
    """
    from x_monitor import translator

    monkeypatch.setattr(translator, "_MAX_RETRIES", 7, raising=True)
    _monkey_call_with_retry(monkeypatch, RuntimeError("proxy err"))

    posts = [
        {"tweet_id": "r7", "id": "r7", "text": "t",
         "brand_ids": ["kimi"]},
    ]
    args = argparse.Namespace(
        source="latest-cycle", limit=10, sample=1, strict_budget=False,
    )
    rc, out = _run_pipeline_with_posts(posts, args, monkeypatch)
    assert rc == 0
    assert "retries=7" in out


def test_u7_n_failed_translate_counts_batch_on_whole_failure(monkeypatch):
    """n_failed_translate in the report header reflects the batch size."""
    _monkey_call_with_retry(monkeypatch, RuntimeError("proxy err"))

    posts = [
        {"tweet_id": f"t{i}", "id": f"t{i}", "text": "t",
         "brand_ids": ["kimi"]}
        for i in range(5)
    ]
    args = argparse.Namespace(
        source="latest-cycle", limit=10, sample=5, strict_budget=False,
    )
    rc, out = _run_pipeline_with_posts(posts, args, monkeypatch)
    assert rc == 0
    assert "n_failed_translate:  5" in out
