# {{AGENT_ATTRIBUTION}}
"""v1.7 tests for x_monitor.translator: LLM-driven translation pass.

v1.7 adds server-side LLM translation of kept posts (en + zh-CN) so the
dashboard can render idiomatically in either locale without relying on
browser-side translation. The translation pass runs AFTER the per-model
relevance filter, so cost scales with the kept set, not the raw API
return volume.

The translator module is designed to be testable WITHOUT hitting the
real Anthropic API: tests inject a `FakeClaudeClient` that records
calls and returns canned responses. The real ClaudeClient (when added)
talks to the fuchitalee gateway via ANTHROPIC_API_KEY.

These tests verify:
  - Batch shape: 20 tweets per LLM call, multiple batches for >20 input
  - Noop detection: source == target locale → text_<locale> = source
  - Brand name preservation: prompt instructs the LLM to keep brand
    names, URLs, and @mentions verbatim
  - Error handling: 5xx/429 retries with backoff; final failure marks
    the tweet as NULL but does not raise
  - Malformed response: that tweet marked failed, others succeed
  - Dry run: no LLM call, returns stub
  - Empty input: no LLM call
"""

from __future__ import annotations

import json
from typing import Any

import pytest


# --- Test fixtures ------------------------------------------------------


class FakeClaudeClient:
    """A canned-response Claude client for translator tests.

    The real ClaudeClient (when implemented) will call the fuchitalee
    gateway via the Anthropic SDK. This fake:
      - Records every call to `messages.create(...)` for assertions
      - Returns `response_factory(tweets, target_locales)` for each call
        (lets the test parameterize per-call behavior)
      - Tracks total call count + total input tweet count

    To simulate 5xx / 429: set `response_factory` to a callable that
    raises an anthropic.APIStatusError for the first N calls.
    """

    def __init__(self, response_factory=None):
        self._factory = response_factory or self._default_factory
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def _default_factory(self, tweets, target_locales):
        # Default: a happy-path response that translates each tweet.
        results = []
        for t in tweets:
            text = t.get("text", "")
            entry = {
                "tweet_id": t.get("tweet_id") or t.get("id"),
                "lang_detected": "en" if text.isascii() else "zh-Hans",
                "text_en": text if text.isascii() else f"[EN] {text}",
                "text_zh_cn": text if not text.isascii() else f"[中文] {text}",
                "noop_en": text.isascii(),
                "noop_zh": not text.isascii(),
            }
            results.append(entry)
        return {"results": results}

    def messages_create(self, **kwargs):
        """Stand-in for the Anthropic SDK's messages.create."""
        # The translator will pass: model=, max_tokens=, messages=[...]
        # We don't care about parsing kwargs here — we just record the
        # call and return a response that the test set up.
        self.calls.append(kwargs)
        return self._factory_for_call(kwargs)

    def _factory_for_call(self, kwargs):
        # The translator's prompt embeds the tweets as JSON; the test
        # factory may need to parse them. For default factory, the
        # tweets arg is implicit (tests inject them via the response).
        return self._factory(self.calls[-1].get("_test_tweets", []),
                             self.calls[-1].get("_test_target_locales", []))


# --- v1.7 translator tests ---------------------------------------------


def test_translate_batch_empty_input_no_llm_call():
    """An empty input list returns [] and does NOT call the LLM."""
    from x_monitor.translator import translate_batch

    client = FakeClaudeClient()
    out = translate_batch([], ["en", "zh_cn"], client=client)
    assert out == []
    assert client.call_count == 0


def test_translate_batch_happy_path_20_tweets_one_call():
    """20 tweets = 1 LLM call. All 20 rows populated with translations."""
    from x_monitor.translator import translate_batch

    tweets = [
        {"tweet_id": f"t{i}", "text": f"tweet {i}", "model_id": "minimax"}
        for i in range(20)
    ]
    client = FakeClaudeClient()
    # Inject the tweets into the call record so the factory can use them.
    def factory(t, locales):
        return {
            "results": [
                {
                    "tweet_id": tw["tweet_id"],
                    "lang_detected": "en",
                    "text_en": tw["text"],
                    "text_zh_cn": f"[zh] {tw['text']}",
                    "noop_en": True,
                    "noop_zh": False,
                }
                for tw in t
            ]
        }
    client._factory = factory
    # Annotate the next call with the tweets so the factory sees them.
    orig = client.messages_create
    def recording_create(**kwargs):
        kwargs["_test_tweets"] = tweets
        kwargs["_test_target_locales"] = ["en", "zh_cn"]
        return orig(**kwargs)
    client.messages_create = recording_create  # type: ignore[assignment]

    out = translate_batch(tweets, ["en", "zh_cn"], client=client)
    assert client.call_count == 1
    assert len(out) == 20
    for i, row in enumerate(out):
        assert row["tweet_id"] == f"t{i}"
        assert row["text_en"] == f"tweet {i}"
        assert row["text_zh_cn"] == f"[zh] tweet {i}"


def test_translate_batch_batches_above_20():
    """22 tweets = 2 LLM calls (20 + 2). The 21st-22nd items are in call 2."""
    from x_monitor.translator import translate_batch, _TRANSLATION_BATCH_SIZE

    tweets = [
        {"tweet_id": f"t{i}", "text": f"tweet {i}"}
        for i in range(22)
    ]
    client = FakeClaudeClient()
    def factory(t, locales):
        return {
            "results": [
                {
                    "tweet_id": tw["tweet_id"],
                    "lang_detected": "en",
                    "text_en": tw["text"],
                    "text_zh_cn": f"[zh] {tw['text']}",
                    "noop_en": True,
                    "noop_zh": False,
                }
                for tw in t
            ]
        }
    client._factory = factory
    orig = client.messages_create
    def recording_create(**kwargs):
        # The translator is expected to slice the tweets list into
        # batches. We don't know the slice boundaries from outside, so
        # we just use the factory's t argument (the test factory
        # already gets the right slice if the translator passes it).
        return orig(**kwargs)
    client.messages_create = recording_create  # type: ignore[assignment]

    out = translate_batch(tweets, ["en", "zh_cn"], client=client)
    assert client.call_count == 2
    assert len(out) == 22
    # The output preserves input order.
    for i, row in enumerate(out):
        assert row["tweet_id"] == f"t{i}"


def test_translate_batch_noop_chinese_source():
    """A Chinese-only tweet: text_zh_cn = source, noop_zh = True.

    The translator's job is to propagate the LLM's response
    faithfully. A well-behaved LLM (Claude Haiku with the right
    prompt) returns `text_zh_cn = source` and `noop_zh = true` when
    the source is already zh-CN. This test injects a fake that models
    that behavior and verifies the translator doesn't mangle it.
    """
    from x_monitor.translator import translate_batch

    tweets = [{"tweet_id": "t1", "text": "海螺AI 最新版本"}]
    client = FakeClaudeClient()
    def noop_factory(t, locales):
        return {
            "results": [
                {
                    "tweet_id": "t1",
                    "lang_detected": "zh-Hans",
                    "text_en": "Hailuo AI latest version",
                    "text_zh_cn": "海螺AI 最新版本",  # noop
                    "noop_en": False,
                    "noop_zh": True,
                }
            ]
        }
    client._factory = noop_factory
    out = translate_batch(tweets, ["en", "zh_cn"], client=client)
    assert len(out) == 1
    row = out[0]
    # The LLM returned text_zh_cn = source and noop_zh = True. The
    # translator must propagate this faithfully — no munging, no
    # second-guessing, no swapping.
    assert row["text_zh_cn"] == "海螺AI 最新版本"
    assert row.get("noop_zh") is True
    assert row["text_en"] == "Hailuo AI latest version"


def test_translate_batch_noop_english_source():
    """An English-only tweet: text_en = source, noop_en = True.

    Mirror of the Chinese noop case — the fake LLM returns the
    source as text_en with noop_en=true, and the translator
    propagates that without modification.
    """
    from x_monitor.translator import translate_batch

    tweets = [{"tweet_id": "t1", "text": "minimax is great"}]
    client = FakeClaudeClient()
    def noop_factory(t, locales):
        return {
            "results": [
                {
                    "tweet_id": "t1",
                    "lang_detected": "en",
                    "text_en": "minimax is great",  # noop
                    "text_zh_cn": "minimax很棒",
                    "noop_en": True,
                    "noop_zh": False,
                }
            ]
        }
    client._factory = noop_factory
    out = translate_batch(tweets, ["en", "zh_cn"], client=client)
    row = out[0]
    assert row["text_en"] == "minimax is great"
    assert row.get("noop_en") is True
    assert row["text_zh_cn"] == "minimax很棒"


def test_translate_batch_emoji_only():
    """An emoji-only tweet: LLM likely returns both as noop."""
    from x_monitor.translator import translate_batch

    tweets = [{"tweet_id": "t1", "text": "🤯"}]
    client = FakeClaudeClient()
    out = translate_batch(tweets, ["en", "zh_cn"], client=client)
    row = out[0]
    # Both noop or one translated — either is acceptable; the test
    # just checks the row exists and has the expected keys.
    assert "tweet_id" in row
    assert "text_en" in row
    assert "text_zh_cn" in row
    assert "lang_detected" in row


def test_translate_batch_url_preservation_via_prompt():
    """The prompt template must instruct the LLM to preserve URLs and
    @mentions verbatim. This is a contract test on the prompt itself."""
    from x_monitor.translator import build_translation_prompt

    prompt = build_translation_prompt(
        tweets=[{"tweet_id": "t1", "text": "Check https://example.com"}],
        target_locales=["en", "zh_cn"],
    )
    # The prompt must mention URL/mention/brand preservation.
    assert "URL" in prompt or "url" in prompt
    assert "@mention" in prompt or "mention" in prompt or "@" in prompt
    # And the tweet's URL appears in the prompt.
    assert "https://example.com" in prompt


def test_translate_batch_brand_names_in_prompt():
    """The prompt must instruct the LLM to keep brand names verbatim
    (the per-model brand list is in data/queries/<m>.yaml)."""
    from x_monitor.translator import build_translation_prompt

    prompt = build_translation_prompt(
        tweets=[{"tweet_id": "t1", "text": "海螺 is great", "model_id": "minimax"}],
        target_locales=["en", "zh_cn"],
        brand_names=["MiniMax", "海螺", "Hailuo"],
    )
    for name in ["MiniMax", "海螺", "Hailuo"]:
        assert name in prompt, f"brand name {name!r} not in prompt"


def test_translate_batch_retries_on_5xx():
    """Two 5xx then a 200 → success; the 200 response is used."""
    from x_monitor.translator import translate_batch

    class Fake5xxThen200(FakeClaudeClient):
        def __init__(self):
            super().__init__()
            self.attempt = 0
        def messages_create(self, **kwargs):
            self.attempt += 1
            self.calls.append(kwargs)
            if self.attempt <= 2:
                # Simulate a 5xx
                raise RuntimeError("anthropic APIStatusError 500")
            # Third attempt: succeed
            return {
                "results": [
                    {
                        "tweet_id": "t1",
                        "lang_detected": "en",
                        "text_en": "ok",
                        "text_zh_cn": "好的",
                        "noop_en": False,
                        "noop_zh": False,
                    }
                ]
            }
    client = Fake5xxThen200()
    out = translate_batch(
        [{"tweet_id": "t1", "text": "ok"}],
        ["en", "zh_cn"],
        client=client,
    )
    assert client.attempt == 3
    assert len(out) == 1
    assert out[0]["text_en"] == "ok"


def test_translate_batch_retries_exhausted_marks_failed():
    """Three 5xx → that tweet marked failed (NULL text_en, NULL text_zh_cn)."""
    from x_monitor.translator import translate_batch

    class FakeAll5xx(FakeClaudeClient):
        def __init__(self):
            super().__init__()
            self.attempt = 0
        def messages_create(self, **kwargs):
            self.attempt += 1
            self.calls.append(kwargs)
            raise RuntimeError("anthropic APIStatusError 500")
    client = FakeAll5xx()
    out = translate_batch(
        [{"tweet_id": "t1", "text": "ok"}],
        ["en", "zh_cn"],
        client=client,
    )
    assert client.attempt == 3  # 3 retries exhausted
    assert len(out) == 1
    row = out[0]
    assert row["text_en"] is None
    assert row["text_zh_cn"] is None
    assert row.get("translation_failed") is True


def test_translate_batch_malformed_response_skips_that_tweet():
    """LLM returns malformed JSON for one tweet → that tweet is marked
    failed, others succeed."""
    from x_monitor.translator import translate_batch

    class FakePartialBad(FakeClaudeClient):
        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            # Return a response missing the 'results' key — the
            # translator should treat this as a parse failure for ALL
            # tweets in this batch.
            return {"unexpected_key": "no results here"}
    client = FakePartialBad()
    out = translate_batch(
        [
            {"tweet_id": "t1", "text": "ok"},
            {"tweet_id": "t2", "text": "also ok"},
        ],
        ["en", "zh_cn"],
        client=client,
    )
    # All 2 tweets in this batch failed (single batch of 2).
    assert len(out) == 2
    for row in out:
        assert row["text_en"] is None
        assert row["text_zh_cn"] is None
        assert row.get("translation_failed") is True


def test_translate_batch_dry_run_no_llm_call():
    """dry_run=True skips the LLM and returns a stub response per tweet."""
    from x_monitor.translator import translate_batch

    client = FakeClaudeClient()
    tweets = [
        {"tweet_id": "t1", "text": "海螺AI"},
        {"tweet_id": "t2", "text": "minimax is great"},
    ]
    out = translate_batch(
        tweets, ["en", "zh_cn"], client=client, dry_run=True
    )
    # No LLM call.
    assert client.call_count == 0
    # Stub: text_en / text_zh_cn are None (NULL in the DB), but each
    # tweet is present in the output.
    assert len(out) == 2
    for row in out:
        assert row["text_en"] is None
        assert row["text_zh_cn"] is None
        assert row.get("dry_run") is True


def test_translate_batch_prompt_includes_tweet_id():
    """The prompt embeds tweet_id for each tweet so the LLM response
    can be matched back to the input row."""
    from x_monitor.translator import build_translation_prompt

    prompt = build_translation_prompt(
        tweets=[
            {"tweet_id": "t_abc_123", "text": "海螺AI"},
            {"tweet_id": "t_xyz_456", "text": "minimax"},
        ],
        target_locales=["en", "zh_cn"],
    )
    assert "t_abc_123" in prompt
    assert "t_xyz_456" in prompt
