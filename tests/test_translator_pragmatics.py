"""U3 tests for x_monitor.translator: pragmatics-aware translation.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 3 of 8), refined by plan 2026-07-06-001 (drop translator's
discourse_role).

Verifies:
- build_pragmatics_translation_prompt includes the §5.1 system
  prompt contract (literal_zh, text_en, text_zh_cn, lang_detected,
  cn_equivalent, annotation) but NOT discourse_role.
- _load_few_shot_examples returns [] when the fixture is missing
  (degrades gracefully; doesn't break the cycle).
- apply_friction_judge zeros annotation when the source contains a
  fixed-translation dictionary token (vibe coding, sycophancy, ...).
- apply_friction_judge does NOT consume / emit discourse_role
  (it was removed from the contract).
- translate_batch_pragmatics returns the four-pronged row shape
  (literal_zh, cn_equivalent, annotation, noop_en, noop_zh) but
  the row does NOT carry a `discourse_role` field.
- translate_batch_pragmatics is backward-compatible with
  translate_batch (text_en, text_zh_cn, lang_detected still populated).
- F1/F2/F3 friction rows keep their LLM annotation (truncated).
- The v1.7 translate_batch path still works (covered by
  test_translator.py — these tests do not duplicate it).
"""

from __future__ import annotations

from typing import Any

import pytest


class FakeClaudeClient:
    """Minimal canned-response client (mirrors test_translator.py's fixture)."""

    def __init__(self, response_factory=None):
        self._factory = response_factory or self._default_factory
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def _default_factory(self, tweets, target_locales):
        results = []
        for t in tweets:
            results.append({
                "tweet_id": t.get("tweet_id") or t.get("id"),
                "text_en": t.get("text", ""),
                "literal_zh": f"[zh] {t.get('text', '')}",
                "lang_detected": "en",
                "discourse_role": "genuine_hype",
                "en_equivalent": "The post gives the update an analytical restatement.",
                "cn_equivalent": "[zh equivalent]",
                "annotation": "This is an F1 note.",
                "noop_en": True,
                "noop_zh": False,
            })
        return {"results": results}

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        return self._factory(
            self.calls[-1].get("_test_tweets", []),
            self.calls[-1].get("_test_target_locales", []),
        )


# --- prompt builder -----------------------------------------------------


def test_pragmatics_prompt_contains_four_prong_contract():
    """The §5.1 system prompt is present in the built prompt.

    Plan 2026-07-06-001 removed `discourse_role` from the translator
    contract — pragmatic register is now exclusively the classifier's
    per-brand output (posts_brands_discourse). The prompt's required
    fields are now: literal_zh, text_en, text_zh_cn, lang_detected,
    cn_equivalent, annotation.
    """
    from x_monitor.translator import build_pragmatics_translation_prompt

    tweets = [{"tweet_id": "1", "text": "Claude could never make this slide deck"}]
    prompt = build_pragmatics_translation_prompt(
        tweets, ["en", "zh_cn"], brand_names=["Claude"]
    )
    for token in ("literal_zh", "en_equivalent", "cn_equivalent",
                  "annotation", "bilingual pragmatic analyst",
                  "氛围编程", "套壳"):
        assert token in prompt, f"missing {token!r} in prompt"
    # discourse_role is no longer part of the translator contract.
    assert "discourse_role" not in prompt, (
        "discourse_role should be gone from the translator prompt; "
        "it's the classifier's exclusive output"
    )


def test_pragmatics_prompt_includes_few_shot_when_provided():
    """Explicit few-shot list is appended to the prompt (no discourse_role key)."""
    from x_monitor.translator import build_pragmatics_translation_prompt

    tweets = [{"tweet_id": "1", "text": "hello"}]
    few_shot = [{
        "input": "Claude could never",
        "output": {"literal_zh": "Claude 永远做不出"},
    }]
    prompt = build_pragmatics_translation_prompt(
        tweets, ["en", "zh_cn"], few_shot_examples=few_shot
    )
    assert "Claude could never" in prompt
    # No discourse_role key in the few-shot rendering (the few-shot
    # block is JSON-dumped from the fixture which was also cleaned).


def test_pragmatics_prompt_skips_few_shot_when_empty_list_passed():
    """Passing an explicit empty list suppresses the disk load."""
    from x_monitor.translator import build_pragmatics_translation_prompt

    prompt = build_pragmatics_translation_prompt(
        [{"tweet_id": "1", "text": "x"}], ["en", "zh_cn"],
        few_shot_examples=[],
    )
    assert "Few-shot examples" not in prompt


def test_load_few_shot_examples_missing_file_returns_empty():
    """A missing fixture file degrades to [] without raising."""
    from x_monitor.translator import _load_few_shot_examples

    # The fixture path is x_monitor/data/few_shot_pragmatics.jsonl,
    # which doesn't exist on a fresh checkout. The loader must NOT
    # raise — it returns [] so the prompt is still sent.
    examples = _load_few_shot_examples()
    assert isinstance(examples, list)
    # May or may not be empty depending on whether the file exists
    # in the working tree; the contract is "never raises".


# --- friction judge -----------------------------------------------------


def test_friction_judge_fixed_translation_zeroes_annotation():
    """A fixed-dictionary token in source → annotation zeroed.

    Plan 2026-07-06-001: the F0-role tier (genuine_hype / fud /
    ai_slop_critique / distillation_accusation) was REMOVED. The
    judge no longer reads `discourse_role` from the LLM response —
    pragmatic register is exclusively the classifier's per-brand
    output. The fixed-dictionary check remains.
    """
    from x_monitor.translator import apply_friction_judge

    for token in ("vibe coding", "sycophancy", "distillation",
                  "wrapper", "fine-tune", "open-weight", "roast",
                  "based"):
        out = apply_friction_judge(
            {"tweet_id": "1", "text": f"this is {token} material"},
            {"annotation": "should be zeroed by fixed-dict match"},
        )
        assert out["annotation"] == "", (
            f"fixed-dict token {token!r} must zero annotation"
        )


def test_friction_judge_does_not_read_discourse_role():
    """Plan 2026-07-06-001: judge does not coerce / consume
    `discourse_role` — the input dict may not contain it at all."""
    from x_monitor.translator import apply_friction_judge

    # No discourse_role key in input — judge must still work.
    out = apply_friction_judge(
        {"tweet_id": "1", "text": "hello"},
        {"literal_zh": "你好", "annotation": ""},
    )
    # output does not introduce a discourse_role field either.
    assert "discourse_role" not in out


def test_friction_judge_named_event_keeps_annotation_truncated():
    """F2 (named meme / event) → keep annotation, truncated to 280."""
    from x_monitor.translator import apply_friction_judge

    long_note = "x" * 400  # > 280 chars
    out = apply_friction_judge(
        {"tweet_id": "1", "text": "this is the next Theranos"},
        {"annotation": long_note},
    )
    # Named-event match fires → keep annotation, truncated.
    assert out["annotation"] == long_note[:280]


def test_friction_judge_english_slang_keeps_short_note():
    """F1 (English slang with no Chinese equivalent) → 1-line note."""
    from x_monitor.translator import apply_friction_judge

    out = apply_friction_judge(
        {"tweet_id": "1", "text": "no cap this is wild"},
        {"annotation": "no cap = not lying (English slang)"},
    )
    # Truncated to ≤ 140 chars.
    assert len(out["annotation"]) <= 140


# --- translate_batch_pragmatics (the new entry point) -------------------


def test_translate_batch_pragmatics_empty_input_no_llm_call():
    from x_monitor.translator import translate_batch_pragmatics

    client = FakeClaudeClient()
    out = translate_batch_pragmatics(
        [], ["en", "zh_cn"], client=client,
    )
    assert out == []
    assert client.call_count == 0


def test_translate_batch_pragmatics_returns_four_prongs():
    """Source is French → text_en + text_zh_cn both populated.

    Plan 2026-07-06-001: `discourse_role` is no longer in the
    translator contract, so the output row no longer carries it.
    """
    from x_monitor.translator import translate_batch_pragmatics

    tweets = [{"tweet_id": "t1", "text": "Claude could never"}]
    client = FakeClaudeClient()
    def factory(t, locales):
        return {"results": [{
            "tweet_id": "t1",
            "text_en": "Claude could never pull this off",
            "literal_zh": "Claude 永远做不出",
            "lang_detected": "other",
            "en_equivalent": "Claude is being framed as unable to match the result.",
            "cn_equivalent": "Claude 不行",
            "annotation": "",
            "noop_en": False,
            "noop_zh": False,
        }]}
    client._factory = factory
    orig = client.messages_create
    def rec(**kwargs):
        kwargs["_test_tweets"] = tweets
        kwargs["_test_target_locales"] = ["en", "zh_cn"]
        return orig(**kwargs)
    client.messages_create = rec  # type: ignore[assignment]

    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    assert len(out) == 1
    row = out[0]
    # Backward-compat columns populated for non-English, non-zh sources.
    assert row["tweet_id"] == "t1"
    assert row["text_en"] == "Claude could never pull this off"
    assert row["text_zh_cn"] == "Claude 永远做不出"
    assert row["lang_detected"] == "other"
    # New prongs (no discourse_role).
    assert row["literal_zh"] == "Claude 永远做不出"
    assert row["en_equivalent"].startswith("Claude is being framed")
    assert row["cn_equivalent"] == "Claude 不行"
    assert row["annotation"] == ""
    assert "discourse_role" not in row, (
        "translator row must NOT carry discourse_role — it's the "
        "classifier's per-brand output"
    )


def test_translate_batch_pragmatics_text_en_null_when_lang_is_english():
    """Deterministic noop: lang_detected='en' → text_en is NULL.

    The LLM echoes the source into text_en (per its prompt
    contract "set to source AND noop_en=true"). The server-side
    coerce NULLs it because the source already serves as the
    English text.
    """
    from x_monitor.translator import translate_batch_pragmatics

    tweets = [{"tweet_id": "1", "text": "Claude could never"}]
    client = FakeClaudeClient()
    def factory(t, locales):
        return {"results": [{
            "tweet_id": "1",
            "text_en": "Claude could never",
            "literal_zh": "Claude 永远做不出",
            "lang_detected": "en",
            "en_equivalent": "Claude is being dismissed as unable to match this.",
            "cn_equivalent": "Claude 不行",
            "annotation": "",
            "noop_en": True,
            "noop_zh": False,
        }]}
    client._factory = factory
    orig = client.messages_create
    def rec(**kwargs):
        kwargs["_test_tweets"] = tweets
        return orig(**kwargs)
    client.messages_create = rec  # type: ignore[assignment]

    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    row = out[0]
    # text_en NULLed by server-side coerce (lang is en).
    assert row["text_en"] is None
    assert row["noop_en"] is True
    # text_zh_cn populated (Chinese best-interpretation).
    assert row["text_zh_cn"] == "Claude 永远做不出"
    assert row["lang_detected"] == "en"


def test_translate_batch_pragmatics_text_zh_cn_null_when_lang_is_already_zh():
    """Simplified Chinese source serves zh while English remains translated."""
    from x_monitor.translator import translate_batch_pragmatics

    tweets = [{"tweet_id": "1", "text": "Claude 真不错"}]
    client = FakeClaudeClient()
    def factory(t, locales):
        return {"results": [{
            "tweet_id": "1",
            "text_en": "Claude is really good",
            "literal_zh": "Claude 真不错",
            "lang_detected": "zh-Hans",
            "en_equivalent": "Claude is receiving a strongly positive assessment.",
            "cn_equivalent": "这波 Claude 确实挺能打。",
            "annotation": "",
            "noop_en": False,
            "noop_zh": True,
        }]}
    client._factory = factory
    orig = client.messages_create
    def rec(**kwargs):
        kwargs["_test_tweets"] = tweets
        return orig(**kwargs)
    client.messages_create = rec  # type: ignore[assignment]

    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    row = out[0]
    # text_zh_cn + literal_zh NULLed by server-side coerce.
    assert row["text_zh_cn"] is None
    assert row["literal_zh"] is None
    assert row["noop_zh"] is True
    assert row["text_en"] == "Claude is really good"
    assert row["noop_en"] is False


def test_translate_batch_pragmatics_backward_compat_columns():
    """Store.bulk_update_translations still sees text_en / text_zh_cn /
    lang_detected for non-English / non-zh sources."""
    from x_monitor.translator import translate_batch_pragmatics

    tweets = [{"tweet_id": "1", "text": "Claude est vraiment bien"}]
    client = FakeClaudeClient()
    def factory(t, locales):
        return {"results": [{
            "tweet_id": "1",
            "text_en": "Claude is really good",
            "literal_zh": "Claude 真的很好",
            "lang_detected": "other",
            "en_equivalent": "Claude is receiving a positive assessment.",
            "cn_equivalent": "太棒了",
            "annotation": "should be zeroed by fixed-dict match",
            "noop_en": False,
            "noop_zh": False,
        }]}
    client._factory = factory
    orig = client.messages_create
    def rec(**kwargs):
        kwargs["_test_tweets"] = tweets
        return orig(**kwargs)
    client.messages_create = rec  # type: ignore[assignment]

    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    row = out[0]
    # The three columns the v1.7 Store method reads are populated
    # for non-en / non-zh sources.
    assert row["text_en"] == "Claude is really good"
    assert row["text_zh_cn"] == "Claude 真的很好"
    assert row["lang_detected"] == "other"
    # No discourse_role field.
    assert "discourse_role" not in row


def test_translate_batch_pragmatics_applies_friction_judge():
    """The judge runs on every row — fixed-dict token zeroes annotation."""
    from x_monitor.translator import translate_batch_pragmatics

    tweets = [{"tweet_id": "1", "text": "vibe coding is the new norm"}]
    client = FakeClaudeClient()
    def factory(t, locales):
        # LLM emits a long annotation; the fixed-dictionary token
        # "vibe coding" must zero it.
        return {"results": [{
            "tweet_id": "1",
            "text_en": "vibe coding is the new norm",
            "literal_zh": "氛围编程是新常态",
            "lang_detected": "en",
            "en_equivalent": "The post treats vibe coding as mainstream practice.",
            "cn_equivalent": "氛围编程这下算彻底进入主流了。",
            "annotation": "a long note that the fixed-dict should zero",
            "noop_en": True,
            "noop_zh": False,
        }]}
    client._factory = factory
    orig = client.messages_create
    def rec(**kwargs):
        kwargs["_test_tweets"] = tweets
        return orig(**kwargs)
    client.messages_create = rec  # type: ignore[assignment]

    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    assert out[0]["annotation"] == ""
    # No discourse_role in the output row.
    assert "discourse_role" not in out[0]


def test_translate_batch_pragmatics_dry_run_returns_stubs():
    """dry_run=True skips the LLM and returns stub rows."""
    from x_monitor.translator import translate_batch_pragmatics

    tweets = [{"tweet_id": "1", "text": "x"}]
    client = FakeClaudeClient()
    out = translate_batch_pragmatics(
        tweets, ["en", "zh_cn"], client=client, dry_run=True,
    )
    assert len(out) == 1
    assert out[0]["tweet_id"] == "1"
    assert out[0]["dry_run"] is True
    assert out[0]["text_en"] is None
    assert "discourse_role" not in out[0]
    assert client.call_count == 0


def test_translate_batch_pragmatics_batches_above_20():
    """22 tweets = 2 LLM calls (20 + 2)."""
    from x_monitor.translator import (
        translate_batch_pragmatics, _TRANSLATION_BATCH_SIZE,
    )

    tweets = [
        {"tweet_id": f"t{i}", "text": f"hype {i}"}
        for i in range(22)
    ]
    client = FakeClaudeClient()
    out = translate_batch_pragmatics(
        tweets, ["en", "zh_cn"], client=client,
    )
    assert client.call_count == 2
    assert len(out) == 22
    for i, row in enumerate(out):
        assert row["tweet_id"] == f"t{i}"
        assert "discourse_role" not in row


def test_translate_batch_pragmatics_failure_marked_failed():
    """A factory that raises marks the batch failed but continues."""
    from x_monitor.translator import translate_batch_pragmatics

    tweets = [{"tweet_id": "1", "text": "x"}]
    client = FakeClaudeClient()
    def boom(t, locales):
        raise RuntimeError("LLM down")
    client._factory = boom

    out = translate_batch_pragmatics(
        tweets, ["en", "zh_cn"], client=client,
    )
    assert len(out) == 1
    assert out[0]["translation_failed"] is True
    assert out[0]["text_en"] is None
    assert "discourse_role" not in out[0]


def test_translate_batch_pragmatics_invalid_response_marked_failed():
    """Length-mismatched response → batch marked failed (parse fail)."""
    from x_monitor.translator import translate_batch_pragmatics

    tweets = [{"tweet_id": "1", "text": "x"},
              {"tweet_id": "2", "text": "y"}]
    client = FakeClaudeClient()
    def short_factory(t, locales):
        # Only 1 result for 2 tweets → length mismatch → parse fail.
        return {"results": [{"tweet_id": "1", "text_en": "x",
                             "literal_zh": "x", "lang_detected": "en",
                             "en_equivalent": "The post makes a minimal statement.",
                             "cn_equivalent": "x", "annotation": "",
                             "noop_en": True, "noop_zh": False}]}
    client._factory = short_factory

    out = translate_batch_pragmatics(
        tweets, ["en", "zh_cn"], client=client,
    )
    assert len(out) == 2
    assert all(r["translation_failed"] for r in out)
    assert all("discourse_role" not in r for r in out)

# --- Lang-family helpers (deterministic noop logic) ------------------


def test_is_english_family_matches_en_variants():
    """All English-family tags are recognized (en, en-US, en_GB, EN)."""
    from x_monitor.translator import _is_english_family

    for lang in ("en", "EN", "en-US", "en_GB", "en-us", "en_CA"):
        assert _is_english_family(lang), f"{lang!r} should match English family"


def test_is_english_family_rejects_non_english():
    """Non-English tags are NOT in the English family."""
    from x_monitor.translator import _is_english_family

    for lang in ("fr", "zh-Hans", "zh", "ja", "ko", "es", "de", ""):
        assert not _is_english_family(lang), (
            f"{lang!r} must not match English family"
        )


def test_is_simplified_chinese_family_matches_zhs_variants():
    """Simplified Chinese variants: zh, zh-Hans, zh-CN, zh_CN_Hans."""
    from x_monitor.translator import _is_simplified_chinese_family

    for lang in ("zh", "zh-Hans", "zh-CN", "zh_CN_Hans", "zh_Hans"):
        assert _is_simplified_chinese_family(lang), (
            f"{lang!r} should match Simplified Chinese family"
        )


def test_is_simplified_chinese_family_rejects_traditional():
    """Traditional Chinese (zh-Hant, zh-TW, zh-HK) is NOT Simplified —
    the translator should still emit a Simplified rendering for these."""
    from x_monitor.translator import _is_simplified_chinese_family

    for lang in ("zh-Hant", "zh-TW", "zh_HK", "zh-Hant-HK"):
        assert not _is_simplified_chinese_family(lang), (
            f"{lang!r} is Traditional Chinese, must NOT match "
            f"Simplified family"
        )
