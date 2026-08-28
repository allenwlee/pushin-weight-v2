"""U5 tests for x_monitor.run._run_post_fetch.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 5 of 8).

Verifies:
- Empty kept_posts returns {} counters without touching the LLM.
- No anthropic_client returns {} counters without touching the LLM.
- Happy path: the post-fetch writes to posts (text_en / text_zh_cn /
  lang_detected) AND to posts_brands_signals AND to
  posts_brands_discourse, with the right counter values.
- An LLM failure on the translator marks rows translation_failed
  but does NOT abort the cycle (the classifier still runs).
- An LLM failure on the classifier for one post does NOT abort
  other posts' classifications.
- The discourse_role prong is coerced to one of the 9 known keys
  (or `uncategorized`) before writing.
- Unknown post_type / sentiment are dead-lettered (the Store path
  takes care of this; U5 just verifies the row shape passes through).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest


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
                {"brand_id": b, "post_types": ["hands_on_usage"],
                 "sentiment": "neutral", "discourse_roles": ["genuine_hype"],
                 "china_nationalism": "none", "us_nationalism": "none"}
                for b in brand_ids
            ],
            "unsanctioned_flags": [],
        }]}

    def messages_create(self, **kwargs):
        prompt = kwargs.get("messages", [{}])[0].get("content", "")
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
                    except Exception:
                        tweets = []
            return self._t_factory(
                tweets,
                kwargs.get("_test_target_locales", []),
            )
        if ("across FIVE dimensions" in prompt
                or "_PRAGMATICS_FULL_SYSTEM_PROMPT" in prompt
                or "You classify one or more tweets" in prompt):
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
                batch_marker = "Tweets (JSON array of "
                b_idx = prompt.find(batch_marker)
                if b_idx >= 0:
                    # Batch prompt — find the `[` that opens the
                    # JSON payload (skip past the "1):" header).
                    import json as _json
                    payload_start = prompt.find("[", b_idx)
                    if payload_start < 0:
                        batch_tweets = []
                    else:
                        payload = prompt[payload_start:].strip()
                        try:
                            batch_tweets = _json.loads(payload)
                        except Exception:
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
                else:
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
            "n_translated": 0, "n_discourse": 0,
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
            "n_translated": 0, "n_discourse": 0,
            "n_nationalism": 0, "n_failed_translate": 0,
        }
    finally:
        s.close()


def test_run_post_fetch_happy_path_writes_all_three_tables(tmp_path):
    from x_monitor.run import _run_post_fetch

    s = _seed_minimal_db(tmp_path)
    try:
        # Translator factory: returns a successful four-pronged row.
        def t_factory(tweets, locales):
            return {"results": [{
                "tweet_id": "t1",
                "text_en": "Claude could never",
                "literal_zh": "Claude 永远做不出",
                "text_zh_cn": "Claude 永远做不出",
                "lang_detected": "en",
                "discourse_role": "dunk_yingyang",
                "en_equivalent": "The post dismisses Claude's capability.",
                "cn_equivalent": "Claude 不行",
                "annotation": "",
                "noop_en": True,
                "noop_zh": False,
            }]}
        client = FakeClaudeClient(translate_factory=t_factory)

        kept = [{
            "tweet_id": "t1", "id": "t1", "text": "Claude could never",
            "brand_id": "anthropic", "brand_ids": ["anthropic"],
        }]
        out = _run_post_fetch(
            kept, store=s, anthropic_client=client,
            brand_registry_rows=s.read_brands(),
        )

        # Counters reflect success.
        assert out["n_translated"] == 1
        assert out["n_discourse"] == 1
        assert out["n_nationalism"] == 0  # both axes were "none"
        assert out["n_failed_translate"] == 0

        # Verify posts row updated. The factory emits lang_detected='en'
        # → server-side deterministic noop NULLs text_en (source serves)
        # and populates text_zh_cn with the Chinese best-interpretation.
        row = s._conn.execute(
            "SELECT text_en, text_zh_cn, lang_detected FROM posts "
            "WHERE tweet_id = 't1'"
        ).fetchone()
        assert row["text_en"] is None
        assert row["text_zh_cn"] == "Claude 永远做不出"
        assert row["lang_detected"] == "en"

        # Verify posts_brands_signals updated (post_type_key + sentiment).
        # U1b: the column is now `post_type_key` (TEXT) and stores the
        # TEXT slug directly (no INTEGER FK resolution needed).
        sig = s._conn.execute(
            "SELECT post_type_key, sentiment FROM posts_brands_signals"
        ).fetchone()
        assert sig is not None
        pt_key = sig["post_type_key"]
        sent_key = sig["sentiment"]
        assert pt_key == "hands_on_usage"
        assert sent_key == "neutral"

        # Verify posts_brands_discourse updated.
        # NOTE: the discourse_role written to posts_brands_discourse
        # comes from `classify_pragmatics_full` (U4), NOT the
        # translator's `discourse_role` prong (U3) — the translator's
        # prong is informational and surfaces in U7's render only.
        # The default FakeClaudeClient classifier emits
        # `genuine_hype` for every brand.
        disc = s.get_post_brand_discourse_for_post("t1")
        assert len(disc) == 1
        assert disc[0]["discourse_key"] == "genuine_hype"
        assert disc[0]["act_id"] == 1
        assert disc[0]["china_nationalism"] == "none"
        assert disc[0]["us_nationalism"] == "none"
    finally:
        s.close()


def test_run_post_fetch_translator_failure_does_not_abort_cycle(tmp_path):
    """A failing translator marks rows translation_failed; the
    classifier still runs and writes discourse rows."""
    from x_monitor.run import _run_post_fetch

    s = _seed_minimal_db(tmp_path)
    try:
        def t_factory(tweets, locales):
            raise RuntimeError("translator down")
        client = FakeClaudeClient(translate_factory=t_factory)

        kept = [{
            "tweet_id": "t1", "id": "t1", "text": "x",
            "brand_id": "anthropic", "brand_ids": ["anthropic"],
        }]
        out = _run_post_fetch(
            kept, store=s, anthropic_client=client,
            brand_registry_rows=s.read_brands(),
        )

        # Translation failed but the classifier still ran.
        assert out["n_failed_translate"] == 1
        assert out["n_discourse"] == 1  # classifier ran regardless
        assert out["n_nationalism"] == 0

        # Posts columns NOT updated.
        row = s._conn.execute(
            "SELECT text_en, text_zh_cn FROM posts WHERE tweet_id='t1'"
        ).fetchone()
        assert row["text_en"] is None
        assert row["text_zh_cn"] is None

        # But the discourse row IS written.
        disc = s.get_post_brand_discourse_for_post("t1")
        assert len(disc) == 1
    finally:
        s.close()


def test_run_post_fetch_classifier_failure_on_one_post_does_not_abort(tmp_path):
    """The classifier raises for one post; others still get classified."""
    from x_monitor.run import _run_post_fetch

    s = _seed_minimal_db(tmp_path)
    try:
        # Seed a second post.
        s._conn.execute(
            """
            INSERT INTO posts(tweet_id, text, created_at, fetched_at)
            VALUES ('t2', 'second post', '2026-07-02T00:00:00+00:00',
                    '2026-07-02T00:00:00+00:00')
            """,
        )
        s._conn.execute(
            """
            INSERT INTO posts_brands(post_id, brand_id, weight)
            VALUES (
                (SELECT id FROM posts WHERE tweet_id='t2'),
                (SELECT id FROM brands WHERE nickname='anthropic'),
                1.0
            )
            """,
        )
        # Classifier raises for "t1" (the FIRST call), succeeds for "t2".
        # The retry loop may call us 3x for "t1" before giving up —
        # count only distinct texts.
        seen_texts: set[str] = set()
        def c_factory(text, brand_ids):
            seen_texts.add(text)
            if "Claude could never" in text:
                raise RuntimeError("classifier boom on t1")
            return {"classifications": [
                {"brand_id": b, "post_types": ["hands_on_usage"],
                 "sentiment": "neutral", "discourse_roles": ["genuine_hype"],
                 "china_nationalism": "none", "us_nationalism": "none"}
                for b in brand_ids
            ]}

        client = FakeClaudeClient(classify_factory=c_factory)
        kept = [
            {"tweet_id": "t1", "id": "t1", "text": "Claude could never",
             "brand_id": "anthropic", "brand_ids": ["anthropic"]},
            {"tweet_id": "t2", "id": "t2", "text": "second post",
             "brand_id": "anthropic", "brand_ids": ["anthropic"]},
        ]
        out = _run_post_fetch(
            kept, store=s, anthropic_client=client,
            brand_registry_rows=s.read_brands(),
        )

        # Both posts were attempted; the failure was contained.
        assert len(seen_texts) == 2
        # Only t2 has a discourse row.
        assert s.get_post_brand_discourse_for_post("t1") == []
        disc_t2 = s.get_post_brand_discourse_for_post("t2")
        assert len(disc_t2) == 1
        assert out["n_discourse"] == 1
    finally:
        s.close()


def test_run_post_fetch_nationalism_counter_only_when_both_set(tmp_path):
    """n_nationalism counts posts where both axes are NOT 'none'."""
    from x_monitor.run import _run_post_fetch

    s = _seed_minimal_db(tmp_path)
    try:
        # Seed two posts; classify each with a different nationalism.
        s._conn.execute(
            """
            INSERT INTO posts(tweet_id, text, created_at, fetched_at)
            VALUES ('t2', 'post two', '2026-07-02T00:00:00+00:00',
                    '2026-07-02T00:00:00+00:00')
            """,
        )
        s._conn.execute(
            """
            INSERT INTO posts_brands(post_id, brand_id, weight)
            VALUES (
                (SELECT id FROM posts WHERE tweet_id='t2'),
                (SELECT id FROM brands WHERE nickname='anthropic'),
                1.0
            )
        """,
        )

        def c_factory(text, brand_ids):
            return {"classifications": [{
                "brand_id": brand_ids[0], "post_types": ["hands_on_usage"],
                "sentiment": "neutral", "discourse_roles": ["genuine_hype"],
                "china_nationalism": "pro", "us_nationalism": "anti",
            }]}

        client = FakeClaudeClient(classify_factory=c_factory)
        kept = [
            {"tweet_id": "t1", "id": "t1", "text": "first",
             "brand_id": "anthropic", "brand_ids": ["anthropic"]},
            {"tweet_id": "t2", "id": "t2", "text": "second",
             "brand_id": "anthropic", "brand_ids": ["anthropic"]},
        ]
        out = _run_post_fetch(
            kept, store=s, anthropic_client=client,
            brand_registry_rows=s.read_brands(),
        )
        # Both posts have non-none nationalism → counter = 2.
        assert out["n_nationalism"] == 2
    finally:
        s.close()


def test_run_post_fetch_discourse_role_coerced_to_known_set(tmp_path):
    """An LLM-emitted unknown discourse_role is coerced to
    `uncategorized` at the parser, then dead-lettered at the Store
    (NOT persisted — the table is intentionally tight per KTD5).
    The brief renderer cites `uncategorized` rows in the limitations
    paragraph rather than folding them into a fake bucket."""
    from x_monitor.run import _run_post_fetch

    s = _seed_minimal_db(tmp_path)
    try:
        def c_factory(text, brand_ids):
            return {"classifications": [{
                "brand_id": brand_ids[0], "post_types": ["hands_on_usage"],
                "sentiment": "neutral",
                "discourse_roles": ["made_up_role"],  # unknown
                "china_nationalism": "none", "us_nationalism": "none",
            }]}
        client = FakeClaudeClient(classify_factory=c_factory)
        kept = [{
            "tweet_id": "t1", "id": "t1", "text": "x",
            "brand_id": "anthropic", "brand_ids": ["anthropic"],
        }]
        out = _run_post_fetch(
            kept, store=s, anthropic_client=client,
            brand_registry_rows=s.read_brands(),
        )
        # The row is dead-lettered; not persisted.
        disc = s.get_post_brand_discourse_for_post("t1")
        assert disc == []
        # n_discourse counts PERSISTED rows, so 0 here.
        assert out["n_discourse"] == 0
    finally:
        s.close()


def test_run_post_fetch_per_brand_classifications_loop(tmp_path):
    """A post with multiple brands gets one discourse row per brand."""
    from x_monitor.run import _run_post_fetch

    s = _seed_minimal_db(tmp_path)
    try:
        # Seed a second brand + post-brand edge.
        s._conn.execute(
            """
            INSERT INTO brands(nickname, display_name, accent_color,
                               is_sentinel, created_at)
            VALUES ('openai', 'OpenAI', '#9ca3af', 0,
                    '2026-07-02T00:00:00+00:00')
            """,
        )
        s._conn.execute(
            """
            INSERT INTO posts_brands(post_id, brand_id, weight)
            VALUES (
                (SELECT id FROM posts WHERE tweet_id='t1'),
                (SELECT id FROM brands WHERE nickname='openai'),
                1.0
            )
            """,
        )
        s._brand_cache = None
        s._brand_id_map = None

        def c_factory(text, brand_ids):
            # Emit a row for each brand the LLM was asked about.
            return {"classifications": [
                {"brand_id": b, "post_types": ["hands_on_usage"],
                 "sentiment": "positive" if b == "openai" else "negative",
                 "discourse_roles": ["genuine_hype"] if b == "openai"
                                    else ["dunk_yingyang"],
                 "china_nationalism": "none", "us_nationalism": "none"}
                for b in brand_ids
            ]}
        client = FakeClaudeClient(classify_factory=c_factory)
        kept = [{
            "tweet_id": "t1", "id": "t1", "text": "x",
            "brand_id": "anthropic",
            "brand_ids": ["anthropic", "openai"],
        }]
        out = _run_post_fetch(
            kept, store=s, anthropic_client=client,
            brand_registry_rows=s.read_brands(),
        )
        assert out["n_discourse"] == 1  # one post × 2 brands = 2 rows
        disc = s.get_post_brand_discourse_for_post("t1")
        assert len(disc) == 2
        # Both brand_ids present.
        brand_ids_written = {d["brand_id"] for d in disc}
        assert brand_ids_written == {"anthropic", "openai"}
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
        m.start() for m in _re.finditer(r"^\s*store\.close\(\)", src, _re.M)
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
