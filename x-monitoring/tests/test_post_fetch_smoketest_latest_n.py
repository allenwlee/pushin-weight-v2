"""End-to-end smoketest test for --source=latest-n.

Plan: docs/plans/2026-07-07-002-feat-smoketest-latest-n-source-mode-plan.md.
Mirrors `test_post_fetch_smoketest_latest_cycle.py` (FakeClaudeClient,
seed-via-Store pattern) but seeds posts WITHOUT populating
`posts_brands` so the deterministic brand-keyword detector returns
`[]` for some posts. The critical assertion: those no-brand posts
still appear in the smoketest output (not silently dropped).
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout, redirect_stderr

import pytest


class FakeClaudeClient:
    def __init__(self):
        self.calls: list = []

    def messages_create(self, **kwargs):
        prompt = kwargs.get("messages", [{}])[0].get("content", "")
        if "bilingual pragmatic analyst" in prompt:
            import json as _json
            marker = "Tweets (JSON array):"
            idx = prompt.find(marker)
            tweets = []
            if idx >= 0:
                try:
                    tweets = _json.loads(prompt[idx + len(marker):].strip())
                except Exception:
                    tweets = []
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
        if "across FIVE dimensions" in prompt:
            import re
            m = re.search(r"Brands \(in order\): ([^\n]+)", prompt)
            brand_line = m.group(1).strip() if m else ""
            brand_ids = (
                [b.strip() for b in brand_line.split(",")]
                if brand_line and brand_line != "(none)"
                else []
            )
            return {"classifications": [{
                "brand_id": b,
                "post_type": "hands_on_usage",
                "sentiment": "neutral", "discourse_role": "genuine_hype",
                "china_nationalism": "none", "us_nationalism": "none",
            } for b in brand_ids]}
        return {"classifications": [], "results": []}


def _seed_db_with_raw_posts(
    db_path, posts, *, brand="glm", pattern="glm"
) -> None:
    """Seed a DB with raw posts (no posts_brands JOIN). The
    smoketest's `--source=latest-n` path reads these via
    `Store.read_recent_posts(limit)`. We still register one brand
    keyword so the brand-detector can pick up brand-mentioning
    text — but the seed itself does NOT touch `posts_brands`,
    so the "no brand attribution" path is exercised naturally
    by posts that don't mention the keyword."""
    from x_monitor.store import Store

    s = Store(db_path, auto_migrate=True)
    # Brand + keyword so the brand-detector recognizes `pattern` text.
    s._conn.execute(
        """
        INSERT OR IGNORE INTO brands(nickname, display_name, accent_color,
                           is_sentinel, created_at)
        VALUES (?, 'Test Brand', '#9ca3af', 0,
                '2026-07-07T00:00:00+00:00')
        """,
        (brand,),
    )
    s._conn.execute(
        "INSERT OR IGNORE INTO brand_keywords(brand_id, pattern, is_regex, added_at) "
        "VALUES (?, ?, 0, '2026-07-07T00:00:00+00:00')",
        (brand, pattern),
    )
    s._brand_cache = None
    s._brand_id_map = None
    for p in posts:
        s._conn.execute(
            """
            INSERT INTO posts(tweet_id, text, lang, author_handle,
                              created_at, fetched_at)
            VALUES (?, ?, 'en', ?, '2026-07-07T00:00:00+00:00',
                    ?)
            """,
            (
                p["tweet_id"],
                p["text"],
                p.get("author_handle"),
                p.get("fetched_at", "2026-07-07T00:00:00+00:00"),
            ),
        )
    s.close()


def test_smoketest_latest_n_end_to_end(tmp_path, monkeypatch):
    """--source=latest-n reads posts from the DB and runs them
    through the full pipeline."""
    from scripts import post_fetch_smoketest as sm
    import x_monitor.translator as tr_mod
    import x_monitor.attribution as attr_mod

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    _seed_db_with_raw_posts(db_path, [
        {"tweet_id": f"t{i}", "text": f"GLM 5.2 is amazing {i}",
         "author_handle": "test_handle"}
        for i in range(5)
    ])

    fake = FakeClaudeClient()
    monkeypatch.setattr(tr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake)
    monkeypatch.setattr(
        attr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake,
    )

    monkeypatch.chdir(tmp_path)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sm.main(["--source", "latest-n", "--latest", "5"])
    assert rc == 0
    out = buf.getvalue()
    assert "source=latest-n" in out
    assert "n_posts=5" in out
    assert "POST-FETCH SMOKETEST REPORT" in out
    assert "SAMPLE POSTS" in out


def test_smoketest_latest_n_respects_latest_flag(tmp_path, monkeypatch):
    """--latest N caps the number of posts loaded from the DB."""
    from scripts import post_fetch_smoketest as sm
    import x_monitor.translator as tr_mod
    import x_monitor.attribution as attr_mod

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    _seed_db_with_raw_posts(db_path, [
        {"tweet_id": f"t{i:02d}", "text": f"GLM post {i}",
         "author_handle": "h", "fetched_at": f"2026-07-0{7 - (i // 9)}T00:00:0{i % 10}+00:00"}
        for i in range(10)
    ])

    fake = FakeClaudeClient()
    monkeypatch.setattr(tr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake)
    monkeypatch.setattr(
        attr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake,
    )
    monkeypatch.chdir(tmp_path)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sm.main(["--source", "latest-n", "--latest", "3"])
    assert rc == 0
    assert "n_posts=3" in buf.getvalue()


def test_smoketest_latest_n_includes_no_brand_posts(tmp_path, monkeypatch):
    """The critical test: posts with no detected brand are NOT skipped.

    Seed 3 posts — one with brand-mentioning text, two with neutral
    text that no monitored brand matches. The latest-n mode must
    include all 3 (no `posts_no_brand_skipped:` line in the report).
    """
    from scripts import post_fetch_smoketest as sm
    import x_monitor.translator as tr_mod
    import x_monitor.attribution as attr_mod

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    _seed_db_with_raw_posts(db_path, [
        {"tweet_id": "t1", "text": "GLM is great", "author_handle": "h",
         "fetched_at": "2026-07-07T00:00:03+00:00"},
        {"tweet_id": "t2", "text": "the weather is nice today",
         "author_handle": "h2", "fetched_at": "2026-07-07T00:00:02+00:00"},
        {"tweet_id": "t3", "text": "lunch was tasty",
         "author_handle": "h3", "fetched_at": "2026-07-07T00:00:01+00:00"},
    ])

    fake = FakeClaudeClient()
    monkeypatch.setattr(tr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake)
    monkeypatch.setattr(
        attr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake,
    )
    monkeypatch.chdir(tmp_path)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sm.main(["--source", "latest-n", "--latest", "10"])
    assert rc == 0
    out = buf.getvalue()
    assert "n_posts=3" in out
    assert "posts_no_brand_skipped" not in out
    # Sample renders 3 posts (no skip happened) — first post in
    # the section is the one with the highest fetched_at.
    assert "--- Post 1" in out


def test_smoketest_latest_n_renders_url_when_handle_present(
    tmp_path, monkeypatch
):
    """Real posts get a real x.com URL in the sample header."""
    from scripts import post_fetch_smoketest as sm
    import x_monitor.translator as tr_mod
    import x_monitor.attribution as attr_mod

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    _seed_db_with_raw_posts(db_path, [
        {"tweet_id": "abc123", "text": "GLM is great",
         "author_handle": "adlenesifi",
         "fetched_at": "2026-07-07T00:00:01+00:00"},
    ])

    fake = FakeClaudeClient()
    monkeypatch.setattr(tr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake)
    monkeypatch.setattr(
        attr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake,
    )
    monkeypatch.chdir(tmp_path)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sm.main(["--source", "latest-n", "--latest", "5"])
    assert rc == 0
    out = buf.getvalue()
    assert "https://x.com/adlenesifi/status/abc123" in out


def test_smoketest_latest_n_renders_no_handle_fallback(
    tmp_path, monkeypatch
):
    """Posts with NULL author_handle render with the (no handle) fallback."""
    from scripts import post_fetch_smoketest as sm
    import x_monitor.translator as tr_mod
    import x_monitor.attribution as attr_mod

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    _seed_db_with_raw_posts(db_path, [
        {"tweet_id": "xyz", "text": "GLM is great",
         "author_handle": None,
         "fetched_at": "2026-07-07T00:00:01+00:00"},
    ])

    fake = FakeClaudeClient()
    monkeypatch.setattr(tr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake)
    monkeypatch.setattr(
        attr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake,
    )
    monkeypatch.chdir(tmp_path)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sm.main(["--source", "latest-n", "--latest", "5"])
    assert rc == 0
    out = buf.getvalue()
    assert "https://x.com/(no handle)/status/xyz" in out


def test_smoketest_latest_n_empty_db(tmp_path, monkeypatch):
    """An empty DB returns 0 with a friendly message."""
    from scripts import post_fetch_smoketest as sm

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    from x_monitor.store import Store
    s = Store(db_path, auto_migrate=True)
    s.close()
    monkeypatch.chdir(tmp_path)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sm.main(["--source", "latest-n"])
    assert rc == 0
    assert "n_posts=0" in buf.getvalue()
    assert "nothing to report" in buf.getvalue()


def test_smoketest_latest_n_parser_rejects_zero(tmp_path, monkeypatch):
    """--latest 0 is invalid; main() returns 2 with an error."""
    from scripts import post_fetch_smoketest as sm

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    from x_monitor.store import Store
    s = Store(db_path, auto_migrate=True)
    s.close()
    monkeypatch.chdir(tmp_path)

    err = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(err):
        rc = sm.main(["--source", "latest-n", "--latest", "0"])
    assert rc == 2
    assert "--latest must be > 0" in err.getvalue()


def test_smoketest_latest_n_clamps_when_latest_exceeds_limit(
    tmp_path, monkeypatch
):
    """If --latest > --limit, clamp and warn (operator-friendly default)."""
    from scripts import post_fetch_smoketest as sm
    import x_monitor.translator as tr_mod
    import x_monitor.attribution as attr_mod

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    _seed_db_with_raw_posts(db_path, [
        {"tweet_id": f"t{i:02d}", "text": f"GLM {i}",
         "author_handle": "h",
         "fetched_at": f"2026-07-0{7 - (i // 9)}T00:00:0{i % 10}+00:00"}
        for i in range(10)
    ])

    fake = FakeClaudeClient()
    monkeypatch.setattr(tr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake)
    monkeypatch.setattr(
        attr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake,
    )
    monkeypatch.chdir(tmp_path)

    err = io.StringIO()
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(err):
        rc = sm.main([
            "--source", "latest-n", "--latest", "100", "--limit", "5",
        ])
    assert rc == 0
    # The cap kicked in: only 5 posts reported.
    assert "n_posts=5" in buf.getvalue()
    # And the operator got a warning.
    assert "clamping --latest" in err.getvalue()
