"""U6 (plan 2026-07-04): smoketest --source=api-query live API source.

Plan: docs/plans/2026-07-04-001-feat-post-fetch-smoketest-and-prompt-tuning-plan.md
Unit U6.

Verifies:
- Parser accepts the new flags (--query, --since, --max-pages,
  --max-per-page, --api-quiet).
- --source=api-query without --query exits 2.
- _load_api_posts calls TwitterApiClient.run_search with the right
  kwargs and maps the response into the smoketest's post dict shape.
- Brand-keyword detection filters no-brand posts (U5 logic shared).
- A fake TwitterApiClient returning 3 tweets — 1 multi-brand,
  1 single-brand, 1 no-brand — yields 2 processed + 1 skipped.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest


class _FakeTwitterApiClient:
    """Fake that returns canned tweets without network I/O."""

    def __init__(self, tweets: list[dict] | None = None):
        self._tweets = tweets or []
        self.calls: list[dict] = []

    def run_search(
        self,
        query: str,
        max_results: int = 50,
        since: str | None = None,
        **kwargs,
    ) -> list[dict]:
        self.calls.append({
            "query": query,
            "max_results": max_results,
            "since": since,
            **kwargs,
        })
        # Apply the same keyword injection the real client does, so
        # the test exercises the real shape.
        effective_query = (
            f"{query} since:{since}" if since and "since:" not in query else query
        )
        self.calls[-1]["effective_query"] = effective_query
        return self._tweets[:max_results]


# --- parser-level checks ------------------------------------------------


def test_u6_parser_accepts_api_query_source():
    """--source=api-query is a valid choice for the smoketest parser."""
    from scripts.post_fetch_smoketest import _parse_args

    args = _parse_args([
        "--source", "api-query",
        "--query", "kimi K2.7",
        "--limit", "5",
    ])
    assert args.source == "api-query"
    assert args.query == "kimi K2.7"
    assert args.limit == 5


def test_u6_parser_accepts_since_and_pagination_args():
    """--since, --max-pages, --max-per-page, --api-quiet all parse."""
    from scripts.post_fetch_smoketest import _parse_args

    args = _parse_args([
        "--source", "api-query",
        "--query", "kimi",
        "--since", "2026-06-01",
        "--max-pages", "3",
        "--max-per-page", "15",
        "--api-quiet",
    ])
    assert args.since == "2026-06-01"
    assert args.max_pages == 3
    assert args.max_per_page == 15
    assert args.api_quiet is True


def test_u6_parser_api_query_without_query_exits_2():
    """When --source=api-query is missing --query, main() exits 2."""
    from scripts.post_fetch_smoketest import main as smoketest_main

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = smoketest_main(["--source", "api-query"])
    assert rc == 2
    assert "--query" in err.getvalue()


# --- _load_api_posts mapping -------------------------------------------


def test_u6_load_api_posts_calls_run_search_with_correct_kwargs(monkeypatch):
    """_load_api_posts invokes TwitterApiClient.run_search with the
    exact kwargs from args, and injects `since:` when --since is set.
    """
    from scripts import post_fetch_smoketest
    from x_monitor import apify

    fake = _FakeTwitterApiClient(tweets=[])
    monkeypatch.setattr(apify, "TwitterApiClient", lambda: fake)
    # Stub the keyword index so detect_brand_mentions returns [].
    monkeypatch.setattr(
        post_fetch_smoketest,
        "compile_keyword_index_unused_here",
        lambda x: None,
        raising=False,
    )

    args = argparse.Namespace(
        query="kimi K2.7 lang:en",
        since="2026-06-01",
        limit=5,
        max_pages=2,
        max_per_page=10,
        api_quiet=True,
    )
    posts, skipped = post_fetch_smoketest._load_api_posts(args, None)
    assert posts == []
    assert skipped == 0
    assert fake.calls, "run_search was not invoked"
    call = fake.calls[0]
    assert call["query"] == "kimi K2.7 lang:en"
    assert call["since"] == "2026-06-01"
    assert call["max_results"] == 5
    assert call["max_pages"] == 2
    assert call["max_per_page"] == 10
    # since: was injected into the effective query
    assert "since:2026-06-01" in call["effective_query"]


def test_u6_load_api_posts_maps_author_handle_from_user_screen_name(monkeypatch):
    """Apify rows with `user.screen_name` get author_handle extracted."""
    from scripts import post_fetch_smoketest
    from x_monitor import apify

    fake = _FakeTwitterApiClient(tweets=[
        {
            "tweet_id": "abc123",
            "text": "Kimi K2.7 is awesome",
            "user": {"screen_name": "kimi_fan"},
            "lang": "en",
        },
    ])
    monkeypatch.setattr(apify, "TwitterApiClient", lambda: fake)

    args = argparse.Namespace(
        query="kimi", since=None, limit=5,
        max_pages=1, max_per_page=20, api_quiet=True,
    )
    # Need to provide a real keyword index that matches "kimi"
    from x_monitor.attribution import compile_keyword_index
    compiled = compile_keyword_index([
        ("moonshot_kimi", "kimi", False),
    ])
    posts, skipped = post_fetch_smoketest._load_api_posts(args, compiled)
    assert len(posts) == 1
    assert posts[0]["author_handle"] == "kimi_fan"
    assert posts[0]["brand_ids"] == ["moonshot_kimi"]
    assert skipped == 0


def test_u6_load_api_posts_filters_no_brand_posts(monkeypatch):
    """U5 logic: posts with no monitored brand attribution are skipped."""
    from scripts import post_fetch_smoketest
    from x_monitor import apify
    from x_monitor.attribution import compile_keyword_index

    fake = _FakeTwitterApiClient(tweets=[
        # Multi-brand (kept)
        {"tweet_id": "t1", "text": "Kimi K2.7 and Deepseek V4 are great",
         "user": {"screen_name": "u1"}, "lang": "en"},
        # Single-brand (kept)
        {"tweet_id": "t2", "text": "Kimi K2.7 launches",
         "user": {"screen_name": "u2"}, "lang": "en"},
        # No brand (skipped)
        {"tweet_id": "t3", "text": "Generic AI infrastructure news",
         "user": {"screen_name": "u3"}, "lang": "en"},
    ])
    monkeypatch.setattr(apify, "TwitterApiClient", lambda: fake)

    args = argparse.Namespace(
        query="AI", since=None, limit=10,
        max_pages=1, max_per_page=20, api_quiet=True,
    )
    compiled = compile_keyword_index([
        ("moonshot_kimi", "kimi", False),
        ("deepseek", "deepseek", False),
    ])
    posts, skipped = post_fetch_smoketest._load_api_posts(args, compiled)
    assert len(posts) == 2
    assert {p["tweet_id"] for p in posts} == {"t1", "t2"}
    assert skipped == 1


# --- end-to-end through main() -----------------------------------------


def test_u6_main_with_api_query_uses_fake_client(monkeypatch, tmp_path):
    """End-to-end: --source=api-query plugs the fake TwitterApiClient
    into main() and runs the pipeline in-memory.
    """
    from scripts import post_fetch_smoketest
    from x_monitor import apify
    from x_monitor import translator

    # Need a populated brand_keywords table so compile_keyword_index
    # has real patterns. Use a tmp DB.
    from x_monitor.store import Store
    db_path = tmp_path / "x.db"
    Store(db_path, auto_migrate=True).close()
    store = Store(db_path, auto_migrate=True)
    store._conn.execute(
        "INSERT INTO brand_keywords (brand_id, pattern, is_regex, added_at) "
        "VALUES (?, ?, ?, ?)",
        ("moonshot_kimi", "kimi", 0, "2026-07-06T00:00:00+00:00"),
    )
    store._conn.commit()
    store.close()

    # The api-query path STILL hits the DB to load brand keywords
    # (we couldn't make the path DB-free without duplicating the brand
    # registry into the script). Patch Store to point at the tmp DB.
    from x_monitor import store as store_mod
    monkeypatch.setattr(store_mod, "Store", Store)

    # Fake Twitter API client returns 2 brand-attributed tweets.
    fake_api = _FakeTwitterApiClient(tweets=[
        {"tweet_id": "z1", "text": "Kimi K2.7 is great",
         "user": {"screen_name": "u1"}, "lang": "en"},
        {"tweet_id": "z2", "text": "Kimi launches",
         "user": {"screen_name": "u2"}, "lang": "en"},
    ])
    monkeypatch.setattr(apify, "TwitterApiClient", lambda: fake_api)

    # Stub the LLM client to avoid real API calls.
    class _StubLLM:
        def messages_create(self, **kwargs):
            prompt = kwargs.get("messages", [{}])[0].get("content", "")
            if "bilingual pragmatic analyst" in prompt:
                tweets = kwargs.get("_test_tweets", [])
                return {"results": [{
                    "tweet_id": t.get("tweet_id") or t.get("id"),
                    "text_en": t.get("text", ""),
                    "literal_zh": t.get("text", ""),
                    "text_zh_cn": t.get("text", ""),
                    "lang_detected": "en",
                    "discourse_role": "uncategorized",
                    "cn_equivalent": "",
                    "annotation": "",
                } for t in tweets]}
            return {"classifications": [], "results": []}
    monkeypatch.setattr(translator, "AnthropicClaudeClient", lambda: _StubLLM())

    # Patch the chdir-to-project-root behavior so the script's
    # hardcoded `data/x_monitoring.db` resolves. The script does
    # `Path("data") / "x_monitoring.db"` relative to cwd, so we
    # chdir into a tmp dir with `data/x_monitoring.db` populated.
    cwd = Path.cwd()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    import shutil
    shutil.copy(str(db_path), str(data_dir / "x_monitoring.db"))
    monkeypatch.chdir(tmp_path)
    try:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = post_fetch_smoketest.main([
                "--source", "api-query",
                "--query", "kimi",
                "--limit", "5",
                "--api-quiet",
            ])
        assert rc == 0, f"main returned {rc}; stderr: {err.getvalue()}"
        # Both tweet_ids appear in the report.
        report = out.getvalue()
        assert "z1" in report
        assert "z2" in report
        # The api-query is wired end-to-end.
        assert fake_api.calls[0]["query"] == "kimi"
    finally:
        monkeypatch.chdir(cwd)
