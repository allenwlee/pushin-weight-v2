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
        # Array shape (post_types[] / discourse_roles[]) — matches
        # the schema build_pragmatics_full_prompt asks the LLM to emit.
        # U2b (2026-07-06): classify_pragmatics_full routes through
        # the array parser, so fixtures must use the array shape.
        return {"classifications": [
            {"brand_id": b, "post_types": ["hands_on_usage"],
             "sentiment": "neutral", "discourse_roles": ["genuine_hype"],
             "china_nationalism": "none", "us_nationalism": "none"}
            for b in brand_ids
        ]}

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
        if "across FIVE dimensions" in prompt:
            self.classify_calls.append(kwargs)
            # Pull `Tweet text:\n"""\n<text>\n"""` and `Brands (in
            # order): a, b, c` out of the prompt.
            text = ""
            brand_ids: list[str] = []
            if "_test_text" in kwargs and "_test_brand_ids" in kwargs:
                text = kwargs["_test_text"]
                brand_ids = kwargs["_test_brand_ids"]
            else:
                # Parse from prompt.
                t_marker = '"""\n'
                t_start = prompt.find(t_marker)
                if t_start >= 0:
                    t_end = prompt.find('\n"""', t_start + len(t_marker))
                    if t_end > t_start:
                        text = prompt[t_start + len(t_marker):t_end]
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
            return self._c_factory(text, brand_ids)
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