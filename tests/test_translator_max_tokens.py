"""Regression net for the translator's per-call max_tokens + thinking wiring.

Pins (plan 2026-08-04-001):
  * _max_tokens_for_batch_size(n) returns min(8192, max(4096, 200 * n))
    for any n >= 1. At _TRANSLATION_BATCH_SIZE=20, this evaluates to
    4096 (the minimum). Lower values risk JSON truncation on
    rich-content batches; higher values cap at 8192 to control
    runaway cost.
  * _call_with_retry threads `thinking` kwarg = {"type": "disabled"}
    when ANTHROPIC_BASE_URL routes through api.deepseek.com
    (DS V4 is a reasoning model that consumes the entire output
    budget on internal deliberation unless thinking is disabled).
  * _call_with_retry OMITS the `thinking` kwarg when ANTHROPIC_BASE_URL
    routes through api.minimax.io (M3 ignores the parameter; the
    SDK would pass it through but the model wouldn't honor it).

BEFORE history (this file replaced itself 3 times):
  * 2026-08-04 02953d6: pinned max_tokens=16384 (after bumping from
    4096 when M3 truncation was first observed). The bump did NOT
    lift the M3 proxy-side cap (~890-1800 tokens); the swap to DS V4
    on 2026-08-04 (commit TBD) is the structural fix.
  * 2026-08-04 (commit TBD, plan 2026-08-04-001): swapped translator
    to deepseek-v4-pro. max_tokens is now per-batch (helper above).
    The 16384 pin is wrong for the new code; this file pins the
    new contract (4096 at default batch_size=20) plus the
    thinking-kwarg contract.
"""
from __future__ import annotations

import json
import os


# Pin values.
# _max_tokens_for_batch_size(20) = min(8192, max(8192, 200*20))
#                              = min(8192, max(8192, 4000))
#                              = min(8192, 8192)
#                              = 8192
EXPECTED_MAX_TOKENS_AT_BATCH_20 = 8192  # BEFORE 2026-08-04 followup: 4096; raised to give 2x headroom over observed rich-content batches (text_en + literal_zh + cn_equivalent + annotation vs single per-brand tuple).

# _max_tokens_for_batch_size(40) = min(8192, max(4096, 200*40))
#                              = min(8192, 8000)
#                              = 8000
EXPECTED_MAX_TOKENS_AT_BATCH_40 = 8192  # BEFORE 2026-08-04 followup: 8000; floor raised to 8192 dominates (min(8192, max(8192, 200*40)) = min(8192, 8192) = 8192).

# _max_tokens_for_batch_size(100) = min(8192, max(4096, 200*100))
#                              = min(8192, 20000)
#                              = 8192  (capped)
EXPECTED_MAX_TOKENS_AT_BATCH_100 = 8192


def _build_prompt(n_tweets: int) -> str:
    """Build a prompt with n_tweets in JSON shape, mirroring what
    build_translation_prompt emits. The translator's
    _tweet_count_in_prompt counts "tweet_id": occurrences.
    """
    tweets = [{"tweet_id": str(i), "text": f"hello {i}"} for i in range(n_tweets)]
    return "Tweet text array: " + json.dumps(tweets)


def test_max_tokens_helper_returns_expected_per_batch():
    """Unit-level pin: _max_tokens_for_batch_size is the contract.

    At batch_size=20, the helper returns 4096 (200*20=4000, clamped to
    4096 minimum). At batch_size=40 it returns 8000. At batch_size=100
    it caps at 8192. The cap prevents runaway cost on large batches.
    """
    from x_monitor.translator import _max_tokens_for_batch_size

    assert _max_tokens_for_batch_size(1) == 8192, (
        "BEFORE: floor was 4096 in commit 02953d6; 1 tweet clamps to 4096."
    )
    assert _max_tokens_for_batch_size(20) == EXPECTED_MAX_TOKENS_AT_BATCH_20
    assert _max_tokens_for_batch_size(40) == EXPECTED_MAX_TOKENS_AT_BATCH_40
    assert _max_tokens_for_batch_size(100) == EXPECTED_MAX_TOKENS_AT_BATCH_100
    assert _max_tokens_for_batch_size(0) == 8192, (
        "BEFORE: 0-tweet batch still gets the 4096 floor; defends against "
        "an empty-prompt divide-by-zero or trivial-budget misconfig."
    )


def test_translator_calls_messages_create_with_per_batch_max_tokens():
    """When translate_batch runs, every messages_create call from the
    translator must request max_tokens sized to the batch.

    Pin: 20-tweet batch -> 4096 tokens. Lower values risk JSON
    truncation on rich-content batches (per prod observation 2026-08-04,
    commit 02953d6).
    """
    from x_monitor.translator import translate_batch

    class _FakeClient:
        def __init__(self):
            self.calls: list[dict] = []
        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            return {"results": [
                {
                    "tweet_id": str(i),
                    "text_en": f"hello {i}",
                    "literal_zh": None,
                    "lang_detected": "en",
                    "noop_en": True,
                    "noop_zh": False,
                }
                for i in range(20)
            ]}

    client = _FakeClient()
    tweets = [{"tweet_id": str(i), "text": f"hello {i}", "id": str(i)} for i in range(20)]
    translate_batch(tweets, ["en", "zh_cn"], client=client)

    assert client.calls, "messages_create was never invoked"
    for kwarg_set in client.calls:
        max_tokens = kwarg_set.get("max_tokens")
        assert max_tokens == EXPECTED_MAX_TOKENS_AT_BATCH_20, (
            f"BEFORE: pre-swap code passed max_tokens=16384 (hardcoded, "
            f"after a 4096 -> 16384 bump in commit 02953d6 that did NOT "
            f"lift the M3 proxy-side cap). Post-swap (plan 2026-08-04-001) "
            f"max_tokens is per-batch via _max_tokens_for_batch_size. "
            f"Got {max_tokens}; expected {EXPECTED_MAX_TOKENS_AT_BATCH_20} "
            f"for a 20-tweet batch. If you intentionally changed the helper "
            f"or the default batch size, update this pin."
        )


def test_translator_threads_thinking_disabled_to_deepseek(monkeypatch):
    """When ANTHROPIC_BASE_URL routes through api.deepseek.com, the
    translator's messages_create call must include
    thinking={"type": "disabled"} to prevent the reasoning model
    from consuming the output budget on internal deliberation.

    Pin: thinking kwarg is a dict with key "type" == "disabled".
    Pre-fix: _call_with_retry never passed `thinking`, so the
    DS V4 reasoning model ate the output budget.
    """
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("MINIMAX_API_TOKEN", "dummy")  # ignored on DS V4 path

    from x_monitor.translator import translate_batch

    class _FakeClient:
        def __init__(self):
            self.calls: list[dict] = []
        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            return {"results": []}

    client = _FakeClient()
    tweets = [{"tweet_id": "t1", "text": "hi", "id": "t1"}]
    translate_batch(tweets, ["en", "zh_cn"], client=client)

    assert client.calls, "messages_create was never invoked"
    thinking = client.calls[0].get("thinking")
    assert thinking == {"type": "disabled"}, (
        f"BEFORE: pre-swap code did not pass `thinking`. Post-swap "
        f"(plan 2026-08-04-001) the translator threads "
        f'{{"type": "disabled"}} when ANTHROPIC_BASE_URL routes '
        f"through api.deepseek.com. Got {thinking!r}; expected "
        f'{{"type": "disabled"}}.'
    )


def test_translator_omits_thinking_for_minimax(monkeypatch):
    """When ANTHROPIC_BASE_URL routes through api.minimax.io (M3),
    the translator must OMIT the `thinking` kwarg entirely. M3
    ignores the parameter; passing it would leak an SDK parameter
    the model doesn't honor.

    Pin: thinking kwarg is None / absent.
    Pre-fix: thinking was never threaded, so this test would pass on
    pre-fix code. The pin keeps it true post-fix: the fix must
    preserve the omit-for-M3 path.
    """
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "minimax/MiniMax-M3.0[1m]")
    monkeypatch.setenv("MINIMAX_API_TOKEN", "dummy")

    from x_monitor.translator import translate_batch

    class _FakeClient:
        def __init__(self):
            self.calls: list[dict] = []
        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            return {"results": []}

    client = _FakeClient()
    tweets = [{"tweet_id": "t1", "text": "hi", "id": "t1"}]
    translate_batch(tweets, ["en", "zh_cn"], client=client)

    assert client.calls, "messages_create was never invoked"
    thinking = client.calls[0].get("thinking")
    assert thinking is None, (
        f"BEFORE: pre-swap code never passed `thinking` (test would "
        f"pass on pre-fix code too). Post-swap (plan 2026-08-04-001) "
        f"must preserve this for M3: the helper _resolve_thinking_default() "
        f"returns None when ANTHROPIC_BASE_URL does NOT contain "
        f"'deepseek.com', and _call_with_retry omits the kwarg when "
        f"None. Got {thinking!r}; expected None."
    )
