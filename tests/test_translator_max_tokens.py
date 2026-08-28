"""Regression net for the translator's per-call max_tokens + thinking wiring.

Pins (plan 2026-08-05-003): see test docstrings below for the per-pin
contracts. This file owns three regression pins:

  1. _max_tokens_for_batch_size(n) returns min(65536, max(16384, 1500*n))
     for any n >= 1. At _TRANSLATION_BATCH_SIZE=20, this evaluates to
     30000 (1500 * 20). The extra headroom covers required English
     commentary added to the previous rich response shape. Raised from the prior 8192 ceiling after
     2026-08-05 prod observation: a 20-post rich-content batch
     consumed 19,554 output tokens at DS V4 Pro, halting the response
     at stop_reason=max_tokens with mid-JSON truncation. The 8192 cap
     was based on an outdated "DS V4 beta max" assumption; live API
     accepts up to 65536.
  2. _call_with_retry threads `thinking` kwarg = {"type": "disabled"}
     when ANTHROPIC_BASE_URL routes through api.deepseek.com
     (DS V4 is a reasoning model that consumes the entire output
     budget on internal deliberation unless thinking is disabled).
  3. _call_with_retry OMITS the `thinking` kwarg when ANTHROPIC_BASE_URL
     routes through api.minimax.io (M3 ignores the parameter; the
     SDK would pass it through but the model wouldn't honor it).

BEFORE history (this file replaced itself 4 times):
  * 2026-08-04 02953d6: pinned max_tokens=16384 (after bumping from
    4096 when M3 truncation was first observed). The bump did NOT
    lift the M3 proxy-side cap (~890-1800 tokens); the swap to DS V4
    on 2026-08-04 (commit TBD) is the structural fix.
  * 2026-08-04 (commit TBD, plan 2026-08-04-001): swapped translator
    to deepseek-v4-pro. max_tokens is now per-batch (helper above).
    The 16384 pin is wrong for the new code; this file pins the
    new contract (4096 at default batch_size=20) plus the
    thinking-kwarg contract.
  * 2026-08-04 4d3db60: helper bumped to 8192 cap with floor 8192
    (rich-content headroom). The 8192 cap was wrong — DS V4's
    real max is 65536, and 20-post rich batches need ~20K.
  * 2026-08-05 (current, plan 2026-08-05-003): cap raised to 65536,
    coefficient raised to 1000 tokens/post, floor 16384.
"""
from __future__ import annotations

import json
import os


def test_max_tokens_helper_covers_prod_observed_rich_batch():
    """Regression pin (plan 2026-08-05-003).

    On 2026-08-05 the translator's 20-post batch in prod hit
    19,554 output tokens at DeepSeek V4 Pro (stop_reason=max_tokens).
    The prior 8192 cap silently truncated every rich batch in the
    5-10K-token range, causing ~25% of prod cycles to fail
    (`translator_batch_failed`, `text_zh_cn IS NULL`).

    This test fails loudly if the helper ever returns a value below
    20,000 for a 20-tweet batch — that would re-introduce the
    truncation class.

    Empirical basis (from the 2026-08-05 repro):
      20 posts, 22,306 input chars -> 19,554 output tokens
      ~977 tokens/post, scaling to ~20,000 for a 20-post batch
      with 5% headroom.
    """
    from x_monitor.translator import _max_tokens_for_batch_size

    n_20 = _max_tokens_for_batch_size(20)
    assert n_20 >= 20_000, (
        f"Translator 20-post budget regressed to {n_20}; the 2026-08-05 "
        f"fix required >= 20,000 to cover the prod-observed 19,554-token "
        f"rich-batch case. If you intentionally changed the coefficient "
        f"or cap, update this pin AND document the new prod measurement."
    )


def test_max_tokens_helper_cap_matches_deepseek_max():
    """Regression pin (plan 2026-08-05-003).

    Verifies the hard cap is at or below DeepSeek V4 Pro's documented
    max output (65536). The prior 8192 cap was based on an outdated
    "DS V4 beta max" assumption and was the root cause of mass
    truncation. API probe (2026-08-05) confirmed DS V4 accepts
    max_tokens=65536 (HTTP 200).
    """
    from x_monitor.translator import _max_tokens_for_batch_size

    # 100 posts -> formula returns 65,536 (capped).
    capped = _max_tokens_for_batch_size(100)
    assert capped <= 65536, (
        f"Helper cap ({capped}) exceeds DeepSeek V4 Pro documented max "
        f"(65536); requests above this would 400."
    )
    assert capped >= 20000, (
        f"Helper cap ({capped}) is below the prod-observed 20-post "
        f"requirement (20,000)."
    )


def test_max_tokens_helper_rejects_pre_8192_truncation():
    """Regression pin (plan 2026-08-05-003).

    Historical trap: a poorly-design helper could return e.g. 4096
    or 8192 once the cap was misconfigured. The 2026-08-05 prod
    truncation happened because the helper was a constant 8192 for
    every batch size (due to `min(8192, max(8192, 200 * n))`
    collapsing to 8192). This test fails if the helper returns
    the same value for batch sizes 1 vs 100 — that would mean
    the "scales with batch size" property was lost.
    """
    from x_monitor.translator import _max_tokens_for_batch_size

    small = _max_tokens_for_batch_size(1)
    medium = _max_tokens_for_batch_size(20)
    large = _max_tokens_for_batch_size(60)

    # 1-post batch hits the floor; 20-post batch sizes by 1000/post;
    # 60-post batch exceeds 16384 floor and goes linear.
    assert small < medium < large, (
        f"Helper is not scaling with batch size: "
        f"n=1 -> {small}, n=20 -> {medium}, n=60 -> {large}. "
        f"This is the 2026-08-05 truncation bug shape: the helper "
        f"was a constant 8192 for every n."
    )


# Pin values.
# _max_tokens_for_batch_size(20) = min(65536, max(16384, 1500*20))
#                              = 30000
EXPECTED_MAX_TOKENS_AT_BATCH_20 = 30000

# _max_tokens_for_batch_size(40) = min(65536, max(16384, 1500*40))
#                              = 60000
EXPECTED_MAX_TOKENS_AT_BATCH_40 = 60000

# _max_tokens_for_batch_size(100) = min(65536, max(16384, 1500*100))
#                              = min(65536, 100000)
#                              = 65536  (capped at DS V4 max)
EXPECTED_MAX_TOKENS_AT_BATCH_100 = 65536  # Capped at DS V4's documented max output.


def test_max_tokens_helper_returns_expected_per_batch():
    """Unit-level pin: _max_tokens_for_batch_size is the contract.

    At batch_size=20, the helper returns 30000 (1500 * 20). At
    batch_size=40 it returns 60000. At batch_size=100 it caps at
    65536 (DS V4 max). The coefficient retains room for the added
    required English commentary field.
    """
    from x_monitor.translator import _max_tokens_for_batch_size

    assert _max_tokens_for_batch_size(1) == 16384, (
        "Floor is 16384 (>= 1 post must cover framing + cn_equivalent); "
        "BEFORE 2026-08-05: floor was 8192, which was itself wrong "
        "(was thought to be DS V4 beta max)."
    )
    assert _max_tokens_for_batch_size(20) == EXPECTED_MAX_TOKENS_AT_BATCH_20
    assert _max_tokens_for_batch_size(40) == EXPECTED_MAX_TOKENS_AT_BATCH_40
    assert _max_tokens_for_batch_size(100) == EXPECTED_MAX_TOKENS_AT_BATCH_100
    assert _max_tokens_for_batch_size(0) == 16384, (
        "0-tweet batch still gets the 16384 floor; defends against "
        "an empty-prompt divide-by-zero or trivial-budget misconfig. "
        "BEFORE 2026-08-05: was 8192."
    )


def test_translator_calls_messages_create_with_per_batch_max_tokens():
    """When translate_batch runs, every messages_create call from the
    translator must request max_tokens sized to the batch.

    Pin: 20-tweet batch -> 30000 tokens (1500 tokens/post * 20
    posts). Lower values caused JSON truncation on rich-content
    batches (per prod observation 2026-08-05, plan 2026-08-05-003;
    8192-cap prior fix truncated at 19,554 output tokens for a
    20-post batch).
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
            f"Pre-swap code (M3 era) passed max_tokens=16384 hardcoded; "
            f"prior post-swap pin (plan 2026-08-04-001) was 4096, then "
            f"raised to 8192 on 2026-08-04. Both were wrong — 8192 "
            f"truncated a 20-post rich batch at 19,554 output tokens "
            f"(plan 2026-08-05-003). Got {max_tokens}; expected "
            f"{EXPECTED_MAX_TOKENS_AT_BATCH_20} for a 20-tweet batch. "
            f"If you intentionally changed the helper or the default "
            f"batch size, update this pin."
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
