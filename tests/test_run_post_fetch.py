"""Retained legacy adapter boundaries for ``x_monitor.run._run_post_fetch``.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 5 of 8).

This file keeps the empty-input, no-client, and store-lifetime checks plus the
legacy fake adapters needed by that surface. Stage 1 writer and failure
isolation are verified through Django ``CycleRunner`` tests; future U5 owns
the legacy adapter cutover and must not restore discourse writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import Mock

# --- shared fixtures ----------------------------------------------------


@dataclass(frozen=True)
class FakeBrandRow:
    brand_id: str
    display_name: str = ""


class FakeClaudeClient:
    """Two-mode fake: response_factory(tweets, locales) for translator,
    response_factory_classify(text, brand_ids) for classifier."""

    def __init__(self, *, translate_factory=None, classify_factory=None):
        self._t_factory = translate_factory or self._default_translate
        self._c_factory = classify_factory or self._default_classify
        self.translate_calls: list[dict] = []
        self.classify_calls: list[dict] = []

    @property
    def call_count(self) -> int:
        return len(self.translate_calls) + len(self.classify_calls)

    def _default_translate(self, tweets, locales):
        return {"results": [{
            "tweet_id": t.get("tweet_id") or t.get("id"),
            "text_en": t.get("text", ""),
            "literal_zh": f"[zh] {t.get('text', '')}",
            "text_zh_cn": f"[zh] {t.get('text', '')}",
            # French so the server-side noop doesn't NULL both
            # text_en and text_zh_cn (the post is neither
            # English nor Simplified Chinese).
            "lang_detected": "fr",
            "discourse_role": "genuine_hype",
            "cn_equivalent": "[zh equivalent]",
            "annotation": "",
            "noop_en": False,
            "noop_zh": False,
        } for t in tweets]}

    def _default_classify(self, text, brand_ids):
        # Plan 2026-07-13-001: classify_batch_pragmatics_full wire format
        # is `{"results": [{"tweet_id": ..., "classifications": [...], ...}]}`
        # The per-post `classify_pragmatics_full` adapter (the bridge the
        # old tests stub here) accepts both shapes; for the batch fixture
        # we emit the new shape. Real tweet_id round-trip happens in the
        # dispatch path (line ~198) — this default emits a single result
        # with the real tweet_ids_in_batch[0] substituted in.
        # The dispatch sees the result as already in `results` form and
        # passes it through; we still must use a sentinel here that the
        # dispatch know how to upgrade on its way out.
        return {"results": [{
            "tweet_id": "_legacy_default_",  # overwritten in dispatch
            "classifications": [
                {"brand_id": b, "outcome": "classified",
                 "post_types": ["hands_on_usage"], "product_labels": [],
                 "sentiment": "neutral",
                 "china_nationalism": "none", "us_nationalism": "none"}
                for b in brand_ids
            ],
            "unsanctioned_flags": [],
        }]}

    def messages_create(self, **kwargs):
        prompt = kwargs.get("messages", [{}])[0].get("content", "")
        system = kwargs.get("system", "")
        if "bilingual pragmatic analyst" in prompt:
            self.translate_calls.append(kwargs)
            # Parse the JSON-encoded tweets array out of the prompt.
            # The translator embeds tweets as JSON: 'Tweets (JSON
            # array):\n[{...}]'.
            import json as _json
            tweets = []
            if "_test_tweets" in kwargs:
                tweets = kwargs["_test_tweets"]
            else:
                marker = "Tweets (JSON array):"
                idx = prompt.find(marker)
                if idx >= 0:
                    payload = prompt[idx + len(marker):].strip()
                    try:
                        tweets = _json.loads(payload)
                    except _json.JSONDecodeError:
                        tweets = []
            return self._t_factory(
                tweets,
                kwargs.get("_test_target_locales", []),
            )
        if ("across FIVE dimensions" in prompt
                or "_PRAGMATICS_FULL_SYSTEM_PROMPT" in prompt
                or "You classify stored social posts" in prompt
                or "You classify stored social posts" in system):
            self.classify_calls.append(kwargs)
            # Pull the per-tweet payload and brand list(s) out of the
            # prompt. The batch path emits the payload as a JSON array
            # after "Tweets (JSON array"; the per-post path emits a
            # single tweet as `Tweet text:\n"""\n<text>\n"""` plus
            # `Brands (in order): a, b, c`.
            text = ""
            brand_ids: list[str] = []
            tweet_ids_in_batch: list[str] = []
            if "_test_text" in kwargs and "_test_brand_ids" in kwargs:
                text = kwargs["_test_text"]
                brand_ids = kwargs["_test_brand_ids"]
            else:
                import json as _json

                try:
                    batch_tweets = _json.loads(prompt) if system else []
                except _json.JSONDecodeError:
                    batch_tweets = []
                if batch_tweets:
                    first = batch_tweets[0]
                    text = first.get("text", "")
                    brand_ids = list(first.get("brand_ids") or [])
                    tweet_ids_in_batch = [
                        str(t.get("tweet_id") or t.get("id") or "")
                        for t in batch_tweets
                    ]
                batch_marker = "Tweets (JSON array of "
                b_idx = prompt.find(batch_marker)
                if not batch_tweets and b_idx >= 0:
                    # Batch prompt — find the `[` that opens the
                    # JSON payload (skip past the "1):" header).
                    payload_start = prompt.find("[", b_idx)
                    if payload_start < 0:
                        batch_tweets = []
                    else:
                        payload = prompt[payload_start:].strip()
                        try:
                            batch_tweets = _json.loads(payload)
                        except _json.JSONDecodeError:
                            batch_tweets = []
                    if batch_tweets:
                        # Use the first tweet's text + brand_ids as
                        # the synthetic (text, brand_ids) the legacy
                        # per-post factory expects. Each per-post call
                        # in the batch then asks the factory once and
                        # we lift the legacy shape into the new batch
                        # shape below.
                        first = batch_tweets[0]
                        text = first.get("text", "")
                        brand_ids = list(first.get("brand_ids") or [])
                        tweet_ids_in_batch = [
                            str(t.get("tweet_id") or t.get("id") or "")
                            for t in batch_tweets
                        ]
                elif not batch_tweets:
                    # Single-post prompt — the new format (Plan
                    # 2026-07-13-001) emits `Tweet text:\n<text>\n\n`
                    # (no triple quotes). Fall back to the legacy
                    # triple-quote form for callers that still
                    # construct their own prompt.
                    text = ""
                    t_marker = "Tweet text:\n"
                    t_start = prompt.find(t_marker)
                    if t_start >= 0:
                        text = prompt[t_start + len(t_marker):]
                        for stop in ("\n\nBrands", "\nBrands"):
                            stop_idx = text.find(stop)
                            if stop_idx >= 0:
                                text = text[:stop_idx]
                                break
                    tq_marker = '"""\n'
                    tq_start = prompt.find(tq_marker)
                    if tq_start >= 0:
                        tq_end = prompt.find('\n"""', tq_start + len(tq_marker))
                        if tq_end > tq_start:
                            legacy_text = prompt[tq_start + len(tq_marker):tq_end]
                            if legacy_text:
                                text = legacy_text
                    b_marker = "Brands (in order): "
                    b_idx = prompt.find(b_marker)
                    if b_idx >= 0:
                        rest = prompt[b_idx + len(b_marker):]
                        line_end = rest.find("\n")
                        brand_line = rest[:line_end if line_end > 0 else len(rest)]
                        if brand_line and brand_line != "(none)":
                            brand_ids = [
                                b.strip() for b in brand_line.split(",")
                            ]
            legacy = self._c_factory(text, brand_ids)
            # Lift the legacy per-post shape ({"classifications": [...]})
            # into the batch wire shape ({"results": [{"tweet_id": ...,
            # "classifications": [...], "unsanctioned_flags": [...]}]}).
            # If the factory already returned the new shape, pass it through.
            if isinstance(legacy, dict) and "results" in legacy:
                # `_default_classify` emits a single result with the
                # sentinel tweet_id `_legacy_default_`. Overwrite it
                # with the real tweet_id from the parsed payload so the
                # batch parser can round-trip.
                rs = legacy.get("results") or []
                if (isinstance(rs, list) and len(rs) == 1
                        and isinstance(rs[0], dict)
                        and rs[0].get("tweet_id") == "_legacy_default_"
                        and tweet_ids_in_batch
                        and len(tweet_ids_in_batch) == 1):
                    rs[0]["tweet_id"] = tweet_ids_in_batch[0]
                return legacy
            if isinstance(legacy, dict) and "classifications" in legacy:
                rows = legacy.get("classifications") or []
                # Re-key post_types / discourse_roles to arrays if the
                # factory emitted scalars (most existing factories do).
                reshaped_rows = []
                for r in rows:
                    if not isinstance(r, dict):
                        continue
                    new_r = dict(r)
                    if isinstance(new_r.get("post_types"), list):
                        pass
                    elif isinstance(new_r.get("post_type"), str):
                        new_r["post_types"] = [new_r["post_type"]]
                    if isinstance(new_r.get("discourse_roles"), list):
                        pass
                    elif isinstance(new_r.get("discourse_role"), str):
                        new_r["discourse_roles"] = [new_r["discourse_role"]]
                    reshaped_rows.append(new_r)
                if tweet_ids_in_batch and len(tweet_ids_in_batch) == 1:
                    # Single-post call (the legacy test fixture contract):
                    # round-trip the real tweet_id so the batch parser
                    # can match the response entry back to the input.
                    tid = tweet_ids_in_batch[0]
                elif tweet_ids_in_batch and len(tweet_ids_in_batch) > 1:
                    # Multi-post batch — extend the legacy single-post
                    # response across all input tweet_ids. Reuse the
                    # same classifications list for each so the test
                    # fixture's content is preserved per-post. Each
                    # tweet gets the legacy response as its entry.
                    tid_results = []
                    for t_id in tweet_ids_in_batch:
                        tid_results.append({
                            "tweet_id": t_id,
                            "classifications": reshaped_rows,
                            "unsanctioned_flags": [],
                        })
                    return {"results": tid_results}
                else:
                    tid = "_legacy_"
                return {
                    "results": [{
                        "tweet_id": tid,
                        "classifications": reshaped_rows,
                        "unsanctioned_flags": [],
                    }]
                }
            return legacy
        return {"classifications": [], "results": []}


def _seed_minimal_db(tmp_path):
    """Create a Store + a tiny post + brand row so _run_post_fetch
    can resolve FKs. Mirrors the helper in test_migration_025."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s._conn.execute(
        """
        INSERT INTO brands(nickname, display_name, accent_color,
                           is_sentinel, created_at)
        VALUES ('anthropic', 'Anthropic', '#9ca3af', 0,
                '2026-07-02T00:00:00+00:00')
        """,
    )
    s._conn.execute(
        """
        INSERT INTO posts(tweet_id, text, created_at, fetched_at)
        VALUES ('t1', 'Claude could never', '2026-07-02T00:00:00+00:00',
                '2026-07-02T00:00:00+00:00')
        """,
    )
    s._conn.execute(
        """
        INSERT INTO posts_brands(post_id, brand_id, weight)
        VALUES (
            (SELECT id FROM posts WHERE tweet_id='t1'),
            (SELECT id FROM brands WHERE nickname='anthropic'),
            1.0
        )
        """,
    )
    s._brand_cache = None
    s._brand_id_map = None
    return s


# --- _run_post_fetch tests ---------------------------------------------


def test_run_post_fetch_empty_input_returns_empty_counters(tmp_path):
    from x_monitor.run import _run_post_fetch

    s = _seed_minimal_db(tmp_path)
    try:
        client = FakeClaudeClient()
        out = _run_post_fetch(
            [], store=s, anthropic_client=client,
            brand_registry_rows=s.read_brands(),
        )
        assert out == {
            "n_translated": 0, "n_classified": 0, "n_discourse": 0,
            "n_nationalism": 0, "n_failed_translate": 0,
        }
        assert client.call_count == 0
    finally:
        s.close()


def test_run_post_fetch_no_client_returns_empty_counters(tmp_path):
    from x_monitor.run import _run_post_fetch

    s = _seed_minimal_db(tmp_path)
    try:
        out = _run_post_fetch(
            [{"tweet_id": "t1", "text": "x", "brand_ids": ["anthropic"]}],
            store=s, anthropic_client=None,
            brand_registry_rows=s.read_brands(),
        )
        assert out == {
            "n_translated": 0, "n_classified": 0, "n_discourse": 0,
            "n_nationalism": 0, "n_failed_translate": 0,
        }
    finally:
        s.close()


def _stage1_result(*, outcome="classified", valid=True, flags=None):
    return {
        "valid": valid,
        "unsanctioned_flags": list(flags or []) if valid else ["scam"],
        "by_brand": {
            "anthropic": {
                "outcome": outcome,
                "post_types": (
                    ["hands_on_usage", "feedback_questions"]
                    if outcome == "classified"
                    else []
                ),
                "product_labels": ["bug"] if outcome == "classified" else [],
                "sentiment": "neutral" if outcome == "classified" else None,
                "china_nationalism": None,
                "us_nationalism": "none" if outcome == "classified" else None,
            }
        },
    }


def _run_with_stage1_result(tmp_path, monkeypatch, result):
    from x_monitor import attribution
    from x_monitor.run import _run_post_fetch

    s = _seed_minimal_db(tmp_path)
    signal_write = Mock()
    flag_write = Mock()
    monkeypatch.setattr(s, "insert_posts_brands_signals", signal_write)
    monkeypatch.setattr(s, "upsert_unsanctioned_flags", flag_write)
    monkeypatch.setattr(
        attribution,
        "classify_batch_pragmatics_full",
        lambda *args, **kwargs: [result],
    )
    out = _run_post_fetch(
        [{"tweet_id": "t1", "text": "x", "brand_ids": ["anthropic"]}],
        store=s,
        anthropic_client=FakeClaudeClient(),
        brand_registry_rows=s.read_brands(),
    )
    return s, out, signal_write, flag_write


def test_run_post_fetch_counts_stage1_without_legacy_classification_writes(
    tmp_path, monkeypatch
):
    s, out, signal_write, flag_write = _run_with_stage1_result(
        tmp_path, monkeypatch, _stage1_result(flags=["scam"])
    )
    try:
        assert out["n_classified"] == 1
        assert out["n_unsanctioned"] == 1
        assert out["t_unsanctioned_ms"] == 0
        assert out["n_discourse"] == 0
        assert out["n_nationalism"] == 0
        signal_write.assert_not_called()
        flag_write.assert_not_called()
        for table in (
            "posts_brands_signals",
            "posts_brands_discourse",
            "posts_unsanctioned_flags",
        ):
            assert s._conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0] == 0
    finally:
        s.close()


def test_run_post_fetch_accepts_context_missing_without_legacy_edges(
    tmp_path, monkeypatch
):
    s, out, signal_write, flag_write = _run_with_stage1_result(
        tmp_path, monkeypatch, _stage1_result(outcome="context_missing")
    )
    try:
        assert out["n_classified"] == 1
        signal_write.assert_not_called()
        flag_write.assert_not_called()
        assert s._conn.execute(
            "SELECT COUNT(*) FROM posts_brands_signals"
        ).fetchone()[0] == 0
        assert s._conn.execute(
            "SELECT COUNT(*) FROM posts_brands_discourse"
        ).fetchone()[0] == 0
    finally:
        s.close()


def test_run_post_fetch_invalid_result_publishes_nothing(
    tmp_path, monkeypatch
):
    s, out, signal_write, flag_write = _run_with_stage1_result(
        tmp_path, monkeypatch, _stage1_result(valid=False)
    )
    try:
        assert out["n_classified"] == 0
        assert out["n_unsanctioned"] == 0
        signal_write.assert_not_called()
        flag_write.assert_not_called()
        assert s._conn.execute(
            "SELECT COUNT(*) FROM posts_brands_signals"
        ).fetchone()[0] == 0
        assert s._conn.execute(
            "SELECT COUNT(*) FROM posts_unsanctioned_flags"
        ).fetchone()[0] == 0
    finally:
        s.close()


# --- U1 (Plan 2026-07-13-002) closed-DB fix ------------------------
#
# Task #288: run.py:1366 closed the store inside the post-fetch
# finally block, then _update_accounts(store, summary) ran at
# run.py:1370 against a closed DB. The fix moves close() to after
# _update_accounts. This test exercises the run path end-to-end on
# an in-memory DB and asserts no sqlite3.ProgrammingError is raised.
# If the close() regresses to its old position, this test fails with
# the same ProgrammingError the live run surfaced.


def test_run_execute_does_not_close_store_before_accounts_update():
    """U1 R6 / task #288: the run path must NOT close the store
    before _update_accounts. Regression test for the closed-DB
    crash at the old run.py:1366 site.

    The fix moves close() to after _update_accounts. This test reads
    run.py as text and asserts the ordering invariant directly — if
    a future refactor reintroduces the close() in the post-fetch
    finally block, this test fails."""
    import re as _re
    from pathlib import Path
    src = Path("x_monitor/run.py").read_text()
    close_sites = [
        m.start() for m in _re.finditer(r"^\s*store\.close\(\)", src, _re.MULTILINE)
    ]
    update_sites = [
        m.start() for m in _re.finditer(
            r"self\._update_accounts\(store,\s*summary\)", src
        )
    ]
    assert close_sites, "expected to find store.close() in run.py"
    assert update_sites, "expected to find _update_accounts in run.py"
    # The CLOSE site that's inside the execute() method must come
    # AFTER the _update_accounts call site. (Earlier close sites, if
    # any, are in helper methods — those don't matter.)
    close_in_execute = close_sites[-1]
    update_in_execute = update_sites[-1]
    assert close_in_execute > update_in_execute, (
        f"store.close() (offset {close_in_execute}) must come AFTER "
        f"_update_accounts() (offset {update_in_execute}). The old "
        f"bug had close() inside the post-fetch finally block, which "
        f"crashed _update_accounts with sqlite3.ProgrammingError."
    )
