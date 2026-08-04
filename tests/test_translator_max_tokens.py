"""Regression net pinning the translator's per-call max_tokens budget.

BEFORE: x_monitor/translator.py::_call_with_retry set max_tokens=4096
on every messages_create call. For 20-tweet translation batches with
rich translations (e.g., Chinese-vendor benchmark discussion with
500+ char text_en + literal_zh + lang_detected per tweet), the response
frequently exceeded 4096 tokens and got truncated mid-JSON. The
truncated response was unrecoverable: parse_llm_response correctly
rejects it, translate_batch marks the batch as translation_failed=True,
and lang_detected stays NULL for every tweet in the batch.

Observed in prod on 2026-08-04 04:33-04:39 (Render cron
crn-d9gv94o4n6ts739tqaug) and 05:30+: responses of 9444 and 11611 bytes
(~2-3K tokens) truncated mid-tweet, lang_detected coverage dropped to
~30-50% on the post-deploy 1h cohort.

M3 model supports up to 128K output tokens per the platform docs
(https://platform.minimax.io/docs/api-reference/text-openai-api);
16384 gives ~4-8x headroom for typical batches without runaway cost.

If you intentionally change this value, update the pin and add a
comment explaining why the new value is correct for the current
batch size + typical response length.
"""
from __future__ import annotations

import os


EXPECTED_MAX_TOKENS = 16384


def test_translator_max_tokens_pinned_at_16384():
    """Every messages_create call from the translator must request
    max_tokens=16384 (or higher). Lower values risk JSON truncation
    on 20-tweet batches; the value was raised from 4096 on 2026-08-04
    after prod observation.
    """
    from x_monitor.translator import translate_batch

    # Minimal in-memory FakeClaudeClient — same shape as test_translator.py
    class _FakeClient:
        def __init__(self):
            self.calls: list[dict] = []
        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            # Return a single-tweet valid response so the batch parses cleanly.
            return {"results": [
                {
                    "tweet_id": "t1",
                    "text_en": "hello",
                    "literal_zh": None,
                    "lang_detected": "en",
                    "noop_en": True,
                    "noop_zh": False,
                }
            ]}

    client = _FakeClient()
    tweets = [{"tweet_id": "t1", "text": "hello world", "id": "t1"}]
    translate_batch(tweets, ["en", "zh_cn"], client=client)

    assert client.calls, "messages_create was never invoked"
    for kwarg_set in client.calls:
        max_tokens = kwarg_set.get("max_tokens")
        assert max_tokens == EXPECTED_MAX_TOKENS, (
            f"BEFORE: max_tokens={max_tokens}; expected {EXPECTED_MAX_TOKENS}. "
            f"If you intentionally changed the value (e.g., bumped to handle "
            f"longer batches or lowered to control cost), update this pin "
            f"AND add a BEFORE comment explaining the new value."
        )
