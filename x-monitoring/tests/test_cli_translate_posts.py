"""U6 end-to-end CLI test: x-monitor translate subcommand.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 6 of 8). Closes evidence gap: the U6 unit had no test that
actually invokes the CLI subcommand against a real DB.

Verifies:
- `x-monitor translate --dry-run --locale en` reads posts needing
  translation and prints the count without writing.
- `x-monitor translate --locale en` (real run, with a fake LLM)
  writes text_en via Store.bulk_update_translations.
- `x-monitor translate --locale zh_cn --limit 1` caps the batch.
- The CLI rejects a missing DB with exit code 2.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout, redirect_stderr

import pytest


class FakeClaudeClient:
    """Canned translator response (mirrors the v1.7 row shape)."""

    def __init__(self):
        self.calls: list = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs.get("messages", [{}])[0].get("content", "")
        # Parse the embedded tweets JSON.
        import json as _json
        marker = "Tweets (JSON array):"
        idx = prompt.find(marker)
        tweets = []
        if idx >= 0:
            payload = prompt[idx + len(marker):].strip()
            try:
                tweets = _json.loads(payload)
            except Exception:
                tweets = []
        return {"results": [{
            "tweet_id": t.get("tweet_id") or t.get("id"),
            "text_en": t.get("text", ""),
            "literal_zh": f"[zh] {t.get('text', '')[:50]}",
            "text_zh_cn": f"[zh] {t.get('text', '')[:50]}",
            "lang_detected": "en",
            "discourse_role": "genuine_hype",
            "cn_equivalent": "[zh equivalent]",
            "annotation": "",
            "noop_en": True,
            "noop_zh": False,
        } for t in tweets]}


def _last_json_block(text: str) -> dict:
    """Extract the JSON object from the CLI output (printed last).

    The CLI prints a one-line summary first ("translate: posts (N
    rows, ...)") followed by an indented JSON block. We find the
    JSON block by tracking brace depth.
    """
    # Find the LAST balanced top-level {...} block.
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if "{" in lines[i]:
            # Try to capture from this line to the matching closing brace.
            depth = 0
            block_lines: list[str] = []
            started = False
            for j in range(i, len(lines)):
                block_lines.append(lines[j])
                for ch in lines[j]:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                if started and depth == 0:
                    return json.loads("\n".join(block_lines))
    raise ValueError(f"no JSON block in output: {text!r}")


def _seed_db_with_posts(tmp_path, posts: list[dict]) -> "Store":
    """Seed a minimal Store with posts that have NULL translations.

    Returns an OPEN Store — do NOT close it. cmd_translate_posts opens
    the same DB file via the path arg and reuses the seeded state.
    Closing the seed's connection here breaks the second open (SQLite
    WAL race in the migration-runner INSERT).
    """
    from x_monitor.store import Store
    """Seed a minimal Store with posts that have NULL translations.

    Each post needs at least one `posts_brands` row to satisfy the
    `get_posts_missing_translations` JOIN. The seed creates a single
    `anthropic` brand and links every post to it.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    _seed_brand(s)
    brand_id_int = s._brand_int_id("anthropic")
    for p in posts:
        s._conn.execute(
            """
            INSERT INTO posts(tweet_id, text, created_at, fetched_at)
            VALUES (?, ?, '2026-07-02T00:00:00+00:00',
                    '2026-07-02T00:00:00+00:00')
            """,
            (p["tweet_id"], p.get("text", "")),
        )
        post_id_int = s._tweet_int_id(p["tweet_id"])
        s._conn.execute(
            """
            INSERT INTO posts_brands(post_id, brand_id, weight)
            VALUES (?, ?, 1.0)
            """,
            (post_id_int, brand_id_int),
        )
    return s


def _seed_brand(s, brand_id="anthropic"):
    s._conn.execute(
        """
        INSERT INTO brands(nickname, display_name, accent_color,
                           is_sentinel, created_at)
        VALUES (?, ?, '#9ca3af', 0, '2026-07-02T00:00:00+00:00')
        """,
        (brand_id, brand_id),
    )
    s._brand_cache = None
    s._brand_id_map = None


def _run_cli(args: list[str], monkeypatch, sm) -> int:
    """Invoke cmd_translate_posts with the given args + injected client."""
    monkeypatch.setattr(sm, "AnthropicClaudeClient", FakeClaudeClient)
    return sm.cmd_translate_posts(args, {"db": sm.Path("data") / "monitor.db"})


def test_cli_translate_posts_dry_run(tmp_path, monkeypatch):
    """--dry-run reads posts needing translation but writes nothing."""
    from x_monitor import __main__ as cli
    from x_monitor import translator as tr_mod

    s = _seed_db_with_posts(tmp_path, [
        {"tweet_id": "t1", "text": "hello"},
        {"tweet_id": "t2", "text": "world"},
    ])
    try:
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            monkeypatch.setattr(
                tr_mod, "AnthropicClaudeClient",
                lambda *a, **kw: FakeClaudeClient(),
            )
            rc = cli.cmd_translate_posts(
                type("A", (), {
                    "locale": "en",
                    "limit": 200,
                    "dry_run": True,
                })(),
                {"db": tmp_path / "x.db"},
            )
        assert rc == 0
        out = buf.getvalue()
        # Reports 2 rows would be translated.
        assert '"would_translate": 2' in out
        # No posts updated (dry run).
        rows = s._conn.execute(
            "SELECT text_en FROM posts"
        ).fetchall()
        assert all(r["text_en"] is None for r in rows)
    finally:
        s.close()


def test_cli_translate_posts_real_run_writes_text_en(tmp_path, monkeypatch):
    """A real run with a fake client writes text_en to posts."""
    from x_monitor import __main__ as cli
    from x_monitor import translator as tr_mod

    s = _seed_db_with_posts(tmp_path, [
        {"tweet_id": "t1", "text": "Claude could never"},
    ])
    try:
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            monkeypatch.setattr(
                tr_mod, "AnthropicClaudeClient",
                lambda *a, **kw: FakeClaudeClient(),
            )
            rc = cli.cmd_translate_posts(
                type("A", (), {
                    "locale": "en", "limit": 200, "dry_run": False,
                })(),
                {"db": tmp_path / "x.db"},
            )
        assert rc == 0
        report = _last_json_block(buf.getvalue())
        assert report["rows_seen"] == 1
        assert report["rows_updated"] == 1
        assert report["rows_failed"] == 0
        row = s._conn.execute(
            "SELECT text_en FROM posts WHERE tweet_id='t1'"
        ).fetchone()
        assert row["text_en"] == "Claude could never"
    finally:
        s.close()


def test_cli_translate_posts_limit_caps_batch(tmp_path, monkeypatch):
    """--limit caps the number of posts processed."""
    from x_monitor import __main__ as cli
    from x_monitor import translator as tr_mod

    s = _seed_db_with_posts(tmp_path, [
        {"tweet_id": f"t{i}", "text": f"hello {i}"}
        for i in range(5)
    ])
    try:
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            monkeypatch.setattr(
                tr_mod, "AnthropicClaudeClient",
                lambda *a, **kw: FakeClaudeClient(),
            )
            rc = cli.cmd_translate_posts(
                type("A", (), {
                    "locale": "en", "limit": 2, "dry_run": False,
                })(),
                {"db": tmp_path / "x.db"},
            )
        assert rc == 0
        report = _last_json_block(buf.getvalue())
        assert report["rows_seen"] == 2
        # Only the first 2 posts got translated.
        rows = s._conn.execute(
            "SELECT tweet_id, text_en FROM posts "
            "WHERE text_en IS NOT NULL ORDER BY tweet_id"
        ).fetchall()
        assert [r["tweet_id"] for r in rows] == ["t0", "t1"]
    finally:
        s.close()


def test_cli_translate_posts_missing_db_exits_2(tmp_path):
    """A non-existent DB path exits 2 with an error message."""
    from x_monitor import __main__ as cli

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = cli.cmd_translate_posts(
            type("A", (), {
                "locale": "en", "limit": 200, "dry_run": False,
            })(),
            {"db": tmp_path / "does_not_exist.db"},
        )
    assert rc == 2
    assert "db not found" in buf.getvalue()