"""U7 --strict-budget exit-1 path test.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 7 of 8). Closes evidence gap: the smoketest runner's
--strict-budget flag exits 0 on a fast cycle; the exit-1 path
(when wall-clock exceeds 90s) was untested.

Strategy: the script computes `total_ms = t_translate_ms +
t_classify_ms` AFTER running the real LLM calls. We can't
realistically make a 90s+ LLM call in a unit test. Instead we
verify the threshold-check via a small refactor: the script's
main() reads total_ms and decides exit code based on a single
expression — we exercise that expression directly by simulating
the total_ms value via a monkeypatched time.monotonic.

Alternative simpler test: a `translates a slow fixture but
without --strict-budget returns 0` test confirms the path. For
exit-1, the cleanest evidence is a direct test of the threshold
predicate. We replicate the predicate inline (the function under
test is `total_ms > 90_000` returning rc=1).
"""

from __future__ import annotations

import io
import json
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest


class FakeSlowClaudeClient:
    """A fake that sleeps long enough to push total_ms over 90s.

    NOTE: we DON'T actually sleep 90s in the test. Instead we
    monkeypatch `time.monotonic` to return a value that makes
    the elapsed-time calculation exceed 90s. The script's
    translation time accounting uses `time.monotonic()` as the
    before/after pair.
    """

    def __init__(self):
        self.calls = 0

    def messages_create(self, **kwargs):
        self.calls += 1
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
            return {"classifications": [{
                "brand_id": "anthropic", "post_type": "hands_on_usage",
                "sentiment": "neutral", "discourse_role": "genuine_hype",
                "china_nationalism": "none", "us_nationalism": "none",
            }]}
        return {"classifications": [], "results": []}


def _seed_kept_posts(db_path: Path, posts: list[dict]) -> None:
    from x_monitor.store import Store

    s = Store(db_path, auto_migrate=True)
    s._conn.execute(
        """
        INSERT INTO brands(nickname, display_name, accent_color,
                           is_sentinel, created_at)
        VALUES ('anthropic', 'Anthropic', '#9ca3af', 0,
                '2026-07-02T00:00:00+00:00')
        """,
    )
    s._brand_cache = None
    s._brand_id_map = None
    brand_id_int = s._brand_int_id("anthropic")
    for p in posts:
        s._conn.execute(
            """
            INSERT INTO posts(tweet_id, text, lang, created_at, fetched_at)
            VALUES (?, ?, 'en', '2026-07-02T00:00:00+00:00',
                    '2026-07-02T00:00:00+00:00')
            """,
            (p["tweet_id"], p["text"]),
        )
        post_id_int = s._tweet_int_id(p["tweet_id"])
        s._conn.execute(
            """
            INSERT INTO posts_brands(post_id, brand_id, weight)
            VALUES (?, ?, 1.0)
            """,
            (post_id_int, brand_id_int),
        )
    s.close()


def test_smoketest_strict_budget_exits_1_when_cycle_exceeds_90s(
    tmp_path, monkeypatch,
):
    """A cycle whose wall-clock exceeds 90s with --strict-budget
    exits 1."""
    from scripts import post_fetch_smoketest as sm
    import x_monitor.translator as tr_mod
    import x_monitor.attribution as attr_mod

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    _seed_kept_posts(db_path, [
        {"tweet_id": "t1", "text": "x"},
    ])

    fake = FakeSlowClaudeClient()
    monkeypatch.setattr(tr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake)
    monkeypatch.setattr(
        attr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake,
    )

    # Patch time.monotonic so the elapsed-time computation
    # reports 95 seconds elapsed across the translate + classify
    # stages. Without this, the test would actually take 90s.
    base = [1000.0]
    def fake_monotonic():
        base[0] += 95.0
        return base[0]
    monkeypatch.setattr(sm.time, "monotonic", fake_monotonic)

    monkeypatch.chdir(tmp_path)

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = sm.main([
            "--source", "latest-cycle",
            "--strict-budget",
        ])
    # The cycle "took" 95s (because time.monotonic jumped), so
    # --strict-budget fires exit 1.
    assert rc == 1
    out = buf.getvalue()
    # The WARNING line is emitted on stderr; total_ms > 90_000
    # is the trigger. We confirm the report shows the elapsed
    # time so the trigger condition was actually evaluated.
    assert "t_total_ms:" in out


def test_smoketest_without_strict_budget_exits_0_on_slow_cycle(
    tmp_path, monkeypatch,
):
    """A slow cycle WITHOUT --strict-budget still exits 0 (the
    flag is the only thing that promotes a slow cycle to rc=1)."""
    from scripts import post_fetch_smoketest as sm
    import x_monitor.translator as tr_mod
    import x_monitor.attribution as attr_mod

    db_path = tmp_path / "data" / "x_monitoring.db"
    db_path.parent.mkdir()
    _seed_kept_posts(db_path, [
        {"tweet_id": "t1", "text": "x"},
    ])

    fake = FakeSlowClaudeClient()
    monkeypatch.setattr(tr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake)
    monkeypatch.setattr(
        attr_mod, "AnthropicClaudeClient", lambda *a, **kw: fake,
    )

    base = [1000.0]
    def fake_monotonic():
        base[0] += 95.0
        return base[0]
    monkeypatch.setattr(sm.time, "monotonic", fake_monotonic)

    monkeypatch.chdir(tmp_path)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sm.main([
            "--source", "latest-cycle",
            # No --strict-budget
        ])
    assert rc == 0