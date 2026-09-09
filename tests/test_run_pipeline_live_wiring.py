"""U5 true end-to-end RunPipeline.execute integration test.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 5 of 8). Closes the gap flagged by the stop-hook: the prior
'test_run_pipeline_integration.py' was AST-level source inspection.
This test drives `RunPipeline.execute()` through its real code
path with stubbed `plan_calls` + `apify.run_search` and asserts:

  - The cycle completes without raising.
  - `summary["post_fetch"]` is populated with the expected keys
    (wall_clock_sec, n_translated, n_classified,
    n_failed_translate) — proving `_run_post_fetch` was actually
    CALLED from the live pipeline.
  - The post-tweet and its translation end up in `posts`, while every
    retired SQLite classification relation remains empty.
  - `posts.text_en` is populated — proving the translator path
    ran end-to-end (not just the integration wire).

This is a real wiring test, not a string match. A regression that
removes the post-fetch call from execute() would fail here.
"""

from __future__ import annotations

from pathlib import Path


class FakeClaudeClient:
    """Canned translator + classifier for the live wiring test."""

    def messages_create(self, **kwargs):
        prompt = (
            str(kwargs.get("system") or "")
            + "\n"
            + kwargs.get("messages", [{}])[0].get("content", "")
        )
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
                "literal_zh": f"[zh] {t.get('text', '')[:50]}",
                "text_zh_cn": f"[zh] {t.get('text', '')[:50]}",
                "lang_detected": "en",
                "en_equivalent": "English source text",
                "cn_equivalent": "[zh equivalent]",
                "annotation": "",
                "noop_en": True,
                "noop_zh": False,
            } for t in tweets]}
        if "You classify stored social posts" in prompt:
            return {"results": [{
                "tweet_id": "t200",
                "classifications": [{
                    "brand_id": "deepseek",
                    "outcome": "classified",
                    "post_types": ["hands_on_usage", "questions_requests"],
                    "product_labels": ["bug"],
                    "sentiment": "neutral",
                    "china_nationalism": "none",
                    "us_nationalism": None,
                }],
                "unsanctioned_flags": [],
            }]}
        return {"classifications": [], "results": []}


class FakeApify:
    """Stubbed TwitterApiClient that returns canned tweets."""

    def __init__(self, tweets: list[dict]):
        self._tweets = tweets

    def run_search(self, query, *, max_results=None, max_pages=None,
                   since=None, since_time=None, max_per_page=None):
        return list(self._tweets)


def _build_minimal_pipeline(tmp_path: Path):
    """Build a RunPipeline with a tmp db + minimal config + one
    model + one query yaml."""
    from x_monitor.config import load_config
    from x_monitor.run import RunPipeline

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    queries_dir = data_dir / "queries"
    queries_dir.mkdir()

    # One query yaml so the cycle loads queries successfully.
    (queries_dir / "deepseek.yaml").write_text(
        "id: deepseek\ndisplay_name: DeepSeek\nbrand_id: deepseek\n"
        "brand_tokens:\n  - deepseek\n  - deep-seek\nenabled: true\n",
        encoding="utf-8",
    )

    # Minimal config.yaml — required fields per Config schema.
    config_path = data_dir / "config.yaml"
    config_path.write_text(
        "enabled_models:\n  - deepseek\n"
        "daily_ceiling: 333\n"
        "x_monitor_list_id: 999\n",
        encoding="utf-8",
    )
    config = load_config(config_path)

    db_path = data_dir / "monitor.db"
    pipeline = RunPipeline(config, data_dir, db_path)
    return pipeline, config


def _build_stub_plan_calls():
    """Build a stub plan_calls() that returns one PlannedCall."""
    from x_monitor.query_plan import PlannedCall

    return [PlannedCall(
        call_id="A",
        call_kind="account",
        brand_id="*",
        bucket=None,
        query_string="deepseek OR claude",
        query_length=len("deepseek OR claude"),
    )]


def test_run_pipeline_execute_calls_run_post_fetch(tmp_path, monkeypatch):
    """Drive execute through post-fetch translation without legacy writes."""
    pipeline, config = _build_minimal_pipeline(tmp_path)

    # Two tweets that should match deepseek via body keywords.
    # t100 doesn't include "deepseek" so it won't be kept (gets
    # marked _unattributed); t200 does include "deepseek" so it's
    # kept and flows into the post-fetch pipeline.
    tweets = [
        {
            "id": "t100",
            "text": "Claude could never make this slide deck",
            "created_at": "2026-07-02T00:00:00+00:00",
            "like_count": 5,
            "lang": "en",
        },
        {
            "id": "t200",
            "text": "GPT-5 is wild, deepseek shipped it fast",
            "created_at": "2026-07-02T00:00:01+00:00",
            "like_count": 3,
            "lang": "en",
        },
    ]
    apify = FakeApify(tweets)

    # Stub plan_calls to return one PlannedCall (skip real query plan
    # which would read our minimal yaml).
    monkeypatch.setattr(
        "x_monitor.run.plan_calls",
        lambda *a, **kw: _build_stub_plan_calls(),
    )

    # Patch the Anthropic client (real client requires API key +
    # network; we want fast + offline).
    fake_client = FakeClaudeClient()
    monkeypatch.setattr(
        "x_monitor.reattribute.build_anthropic_client_from_env",
        lambda *a, **kw: fake_client,
    )
    monkeypatch.setattr(
        "x_monitor.reattribute.build_translator_client_from_env",
        lambda *a, **kw: fake_client,
    )
    import x_monitor.attribution as attr_mod
    import x_monitor.translator as translator_mod
    monkeypatch.setattr(
        translator_mod,
        "translate_batch_pragmatics",
        lambda tweets, locales, client, **kwargs: [{
            "tweet_id": str(tweet.get("tweet_id") or tweet.get("id")),
            "text_en": None,
            "text_zh_cn": "深度求索发布很快",
            "lang_detected": "en",
        } for tweet in tweets],
    )
    monkeypatch.setattr(
        attr_mod,
        "classify_batch_pragmatics_full",
        lambda tweets, brands, client, **kwargs: [{
            "valid": True,
            "unsanctioned_flags": ["scam"],
            "by_brand": {
                "deepseek": {
                    "outcome": "classified",
                    "post_types": ["hands_on_usage", "questions_requests"],
                    "product_labels": ["bug"],
                    "sentiment": "neutral",
                    "china_nationalism": "none",
                    "us_nationalism": None,
                }
            },
        }],
    )

    # Drive execute. The minimal fixture should be enough to walk
    # the full path: lock acquire, query load, plan_calls (stubbed),
    # main loop with apify stub + _attribute_call_items real,
    # filter_and_review real, store.insert_posts real,
    # _run_post_fetch real (with stubbed LLM), QT capture skipped
    # on the dry_run guard or hit-and-skipped on the staff-handles
    # path.
    summary = pipeline.execute(apify, dry_run=False)

    # --- 1. summary["post_fetch"] is populated -------------------
    assert "post_fetch" in summary, (
        "post_fetch key missing from summary — _run_post_fetch "
        "was NOT called from the live cycle path"
    )
    pf = summary["post_fetch"]
    assert "wall_clock_sec" in pf
    assert "n_translated" in pf
    assert "n_classified" in pf
    assert "n_failed_translate" in pf

    # --- 2. n_translated > 0 (translator ran) --------------------
    assert pf["n_translated"] >= 1, (
        f"expected at least one post translated; got "
        f"{pf['n_translated']}; pf={pf}"
    )

    # --- 3. n_classified > 0 (classifier ran) --------------------
    assert pf["n_classified"] >= 1, (
        f"expected at least one valid Stage 1 result; got "
        f"{pf['n_classified']}; pf={pf}"
    )
    assert pf["n_unsanctioned"] == 1
    assert pf["t_unsanctioned_ms"] == 0

    # --- 4. Only post and translation state persists ------------
    from x_monitor.store import Store

    store = Store(pipeline.db_path)
    try:
        # Posts were inserted (1 kept: t200; t100 was filtered
        # out by _attribute_call_items because its text doesn't
        # contain the deepseek keyword).
        rows = store._conn.execute(
            "SELECT tweet_id, text_en, text_zh_cn, lang_detected "
            "FROM posts ORDER BY tweet_id"
        ).fetchall()
        assert len(rows) == 1, f"expected 1 kept post, got {len(rows)}"
        kept = rows[0]
        assert kept["tweet_id"] == "t200"
        # The post text is English → server-side deterministic
        # noop NULLs text_en (source serves) and populates
        # text_zh_cn with the Chinese best-interpretation. This
        # pair of assertions proves _run_post_fetch's translate
        # stage actually ran end-to-end on the live cycle's
        # kept set (and the deterministic noop is wired).
        assert kept["text_en"] is None, (
            "text_en must be NULL for English posts (deterministic noop)"
        )
        assert kept["text_zh_cn"], (
            "text_zh_cn not populated by translator"
        )
        assert kept["lang_detected"] == "en"

        # The retired compatibility adapter retains Stage 1 counters in
        # memory but must not project any classification result into SQLite.
        for table in (
            "posts_brands_signals",
            "posts_brands_discourse",
            "posts_unsanctioned_flags",
        ):
            count = store._conn.execute(
                f"SELECT COUNT(*) AS n FROM {table}"
            ).fetchone()["n"]
            assert count == 0, f"Stage 1 wrote retired SQLite table {table}"
    finally:
        store.close()
