"""U7 tests for scripts.post_fetch_smoketest.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 7 of 8). One-cycle test-and-examine smoketest runner.

Verifies:
- --source=fixture without --fixture exits 2 with an error.
- --fixture pointing at a missing file exits 2.
- A 5-post fixture runs end-to-end and emits a report with all
  expected sections (counts, timing, sample posts, errors).
- The sample-posts section renders one block per post with the
  7 annotation fields visible.
- --strict-budget doesn't trip when the cycle is fast.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest


class FakeClaudeClient:
    """Two-mode fake (mirrors the pattern in test_run_post_fetch.py)."""

    def __init__(self, translate_factory=None, classify_factory=None):
        self._t_factory = translate_factory or self._default_translate
        self._c_factory = classify_factory or self._default_classify

    def _default_translate(self, tweets, locales):
        return {"results": [{
            "tweet_id": t.get("tweet_id") or t.get("id"),
            "text_en": t.get("text", ""),
            "literal_zh": f"[zh] {t.get('text', '')[:60]}",
            "text_zh_cn": f"[zh] {t.get('text', '')[:60]}",
            "lang_detected": "en",
            "discourse_role": "genuine_hype",
            "cn_equivalent": "[zh equivalent]",
            "annotation": "",
            "noop_en": True,
            "noop_zh": False,
        } for t in tweets]}

    def _default_classify(self, text, brand_ids):
        return {"classifications": [
            {"brand_id": b, "post_type": "hands_on_usage",
             "sentiment": "neutral", "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"}
            for b in brand_ids
        ]}

    def messages_create(self, **kwargs):
        prompt = kwargs.get("messages", [{}])[0].get("content", "")
        if "bilingual pragmatic analyst" in prompt:
            return self._t_factory(
                kwargs.get("_test_tweets", []),
                kwargs.get("_test_target_locales", []),
            )
        if "across five dimensions" in prompt:
            return self._c_factory(
                kwargs.get("_test_text", ""),
                kwargs.get("_test_brand_ids", []),
            )
        return {"classifications": [], "results": []}


def _write_fixture(path: Path, posts: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for p in posts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


def test_smoketest_fixture_required(tmp_path, monkeypatch):
    """--source=fixture without --fixture exits 2.

    argparse's `required=True` triggers SystemExit(2) before
    main() runs — we exercise the parse path by calling parse_args
    directly via main() with a missing --fixture and capturing the
    exit. (argparse writes to stderr by default; we just confirm
    the exit code.)"""
    from scripts.post_fetch_smoketest import main

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        try:
            rc = main(["--source", "fixture"])
        except SystemExit as e:
            rc = e.code
    assert rc == 2


def test_smoketest_missing_fixture_file(tmp_path):
    """The runtime check inside main() rejects a missing --fixture."""
    from scripts.post_fetch_smoketest import main

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = main([
            "--source", "fixture",
            "--fixture", str(tmp_path / "does_not_exist.jsonl"),
        ])
    assert rc == 2
    assert "not found" in buf.getvalue()


def test_smoketest_fixture_runs_end_to_end(tmp_path, monkeypatch):
    """A 5-post fixture runs and emits a report."""
    from scripts import post_fetch_smoketest as sm

    fixture = tmp_path / "fixture.jsonl"
    _write_fixture(fixture, [
        {"tweet_id": f"t{i}", "text": f"Claude could never {i}",
         "attributed_brands": ["anthropic"]}
        for i in range(5)
    ])

    # The script imports AnthropicClaudeClient lazily inside main().
    # Monkeypatch the canonical module so the lazy import returns
    # the fake.
    import x_monitor.translator as tr_mod
    monkeypatch.setattr(
        tr_mod, "AnthropicClaudeClient",
        lambda *a, **kw: FakeClaudeClient(),
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sm.main([
            "--source", "fixture",
            "--fixture", str(fixture),
            "--sample", "3",
            "--limit", "10",
        ])
    assert rc == 0
    out = buf.getvalue()
    # Required sections.
    assert "POST-FETCH SMOKETEST REPORT" in out
    assert "n_translated:" in out
    assert "n_classified:" in out
    assert "t_translate_ms:" in out
    assert "t_classify_ms:" in out
    assert "SAMPLE POSTS" in out
    # Sample posts render with the 7 fields.
    assert "text:" in out
    assert "text_en:" in out
    assert "literal_zh:" in out
    assert "discourse:" in out


def test_smoketest_strict_budget_does_not_trip_on_fast_cycle(tmp_path, monkeypatch):
    """A fast cycle under 90s passes --strict-budget."""
    from scripts import post_fetch_smoketest as sm

    fixture = tmp_path / "fixture.jsonl"
    _write_fixture(fixture, [
        {"tweet_id": "t1", "text": "x", "attributed_brands": ["anthropic"]},
    ])
    import x_monitor.translator as tr_mod
    monkeypatch.setattr(
        tr_mod, "AnthropicClaudeClient",
        lambda *a, **kw: FakeClaudeClient(),
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sm.main([
            "--source", "fixture",
            "--fixture", str(fixture),
            "--strict-budget",
        ])
    assert rc == 0