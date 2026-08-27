"""Regression net: lang_detected allowlist + validate + repair (plan 2026-08-10-004).

M18: exercises production entry translate_batch_pragmatics with a fake client.
"""

from __future__ import annotations

from typing import Any

import pytest

from x_monitor.translator import (
    LANG_DETECTED_ALLOWLIST,
    build_pragmatics_translation_prompt,
    normalize_lang_detected,
    translate_batch_pragmatics,
    validate_lang_detected,
)


class RecordingClient:
    """Fake LLM client: scripted responses per call index; records calls."""

    def __init__(self, responses: list[dict[str, Any]]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        idx = len(self.calls) - 1
        if idx >= len(self._responses):
            raise RuntimeError(f"unexpected LLM call #{idx + 1}")
        return self._responses[idx]


# --- U1 normalize / allowlist pins ---


def test_allowlist_members_pinned():
    assert LANG_DETECTED_ALLOWLIST == frozenset(
        {"en", "zh-Hans", "zh-Hant", "ja", "ko", "other"}
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("en", "en"),
        ("EN", "en"),
        ("en-US", "en"),
        ("zh", "zh-Hans"),
        ("zh-cn", "zh-Hans"),
        ("zh_Hans", "zh-Hans"),
        ("zh-tw", "zh-Hant"),
        ("zh-Hant", "zh-Hant"),
        ("ja", "ja"),
        ("ko", "ko"),
        ("other", "other"),
        ("", None),
        (None, None),
        ("   ", None),
        ("esperanto", None),
        ("fr", None),
    ],
)
def test_normalize_lang_detected_table(raw, expected):
    assert normalize_lang_detected(raw) == expected
    assert validate_lang_detected(raw) is (expected is not None)


# --- U2 prompt pins ---


def test_prompt_language_first_and_no_280_hard_cap():
    prompt = build_pragmatics_translation_prompt(
        [{"tweet_id": "1", "text": "hello"}],
        ["en", "zh_cn"],
        few_shot_examples=[],
    )
    assert "lang_detected" in prompt
    assert "REQUIRED" in prompt or "required" in prompt.lower()
    assert "en | zh-Hans | zh-Hant | ja | ko | other" in prompt or (
        "zh-Hans" in prompt and "other" in prompt
    )
    # Language-first JSON shape
    assert '"lang_detected": str' in prompt
    idx_lang = prompt.find('"lang_detected": str')
    idx_text = prompt.find('"text_en": str')
    assert idx_lang >= 0 and idx_text >= 0
    assert idx_lang < idx_text
    assert "≤ 280 characters" not in prompt
    assert "<= 280 characters" not in prompt
    assert "280 characters" not in prompt


def test_few_shot_file_every_example_has_lang_detected():
    from pathlib import Path
    import json

    p = Path(__file__).resolve().parent.parent / "x_monitor/data/few_shot_pragmatics.jsonl"
    assert p.is_file()
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        obj = json.loads(line)
        out = obj.get("output") or {}
        assert out.get("lang_detected"), f"line {i} missing lang_detected"


# --- U3/U4 call-chain through translate_batch_pragmatics ---


def test_all_valid_first_response_single_llm_call():
    tweets = [
        {"tweet_id": "a", "text": "hello"},
        {"tweet_id": "b", "text": "world"},
    ]
    client = RecordingClient([
        {"results": [
            {
                "tweet_id": "a",
                "lang_detected": "en",
                "text_en": "hello",
                "literal_zh": "你好",
                "en_equivalent": "A short greeting opens the conversation.",
                "cn_equivalent": "先跟大家打个招呼。",
                "annotation": "",
                "noop_en": True,
                "noop_zh": False,
            },
            {
                "tweet_id": "b",
                "lang_detected": "en",
                "text_en": "world",
                "literal_zh": "世界",
                "en_equivalent": "A one-word greeting to the audience.",
                "cn_equivalent": "跟大家问声好。",
                "annotation": "",
                "noop_en": True,
                "noop_zh": False,
            },
        ]}
    ])
    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    assert client.call_count == 1
    assert all(r.get("lang_detected") for r in out)
    assert all(not r.get("translation_failed") for r in out)


def test_missing_lang_triggers_one_repair_preserves_texts():
    """AE1/AE3 + D1 merge: repair returns lang only → keep first texts."""
    tweets = [
        {"tweet_id": "ok", "text": "MiniMax is great"},
        {"tweet_id": "bad", "text": "DeepSeek rocks"},
    ]
    first = {
        "results": [
            {
                "tweet_id": "ok",
                "lang_detected": "en",
                "text_en": "MiniMax is great",
                "literal_zh": "MiniMax 很棒",
                "en_equivalent": "MiniMax is getting an enthusiastic endorsement.",
                "cn_equivalent": "MiniMax 这波表现很能打。",
                "annotation": "",
                "noop_en": True,
                "noop_zh": False,
            },
            {
                "tweet_id": "bad",
                # missing lang_detected
                "text_en": "DeepSeek rocks",
                "literal_zh": "DeepSeek 真猛",
                "en_equivalent": "DeepSeek is getting an enthusiastic endorsement.",
                "cn_equivalent": "DeepSeek 这波表现很能打。",
                "annotation": "",
                "noop_en": False,
                "noop_zh": False,
            },
        ]
    }
    repair = {
        "results": [
            {
                "tweet_id": "bad",
                "lang_detected": "en",
                "text_en": "",  # empty — must keep first-pass texts
                "literal_zh": "",
                "en_equivalent": "",
                "cn_equivalent": "",
                "annotation": "",
                "noop_en": True,
                "noop_zh": False,
            }
        ]
    }
    client = RecordingClient([first, repair])
    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    assert client.call_count == 2
    second_prompt = client.calls[1]["messages"][0]["content"]
    assert "bad" in second_prompt
    assert "REPAIR" in second_prompt
    # Repair batch must not include the already-valid id as a tweet payload
    assert '"tweet_id": "ok"' not in second_prompt
    by_id = {r["tweet_id"]: r for r in out}
    assert by_id["ok"]["lang_detected"] == "en"
    assert by_id["bad"]["lang_detected"] == "en"
    assert by_id["bad"].get("translation_failed") is not True
    # en noop nulls text_en; literal_zh kept from first pass
    assert by_id["bad"]["text_zh_cn"] == "DeepSeek 真猛"
    assert by_id["bad"]["text_en"] is None  # en noop


def test_repair_still_missing_lang_fails_empty_no_third_call():
    tweets = [{"tweet_id": "x", "text": "hello"}]
    first = {
        "results": [{
            "tweet_id": "x",
            "text_en": "hello",
            "literal_zh": "你好",
            "en_equivalent": "A brief greeting to the audience.",
            "cn_equivalent": "跟大家简单问个好。",
            "annotation": "",
        }]
    }
    repair = {
        "results": [{
            "tweet_id": "x",
            "text_en": "hello",
            "literal_zh": "你好",
            "en_equivalent": "A brief greeting to the audience.",
            "cn_equivalent": "跟大家简单问个好。",
            "annotation": "",
            # still no lang
        }]
    }
    client = RecordingClient([first, repair])
    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    assert client.call_count == 2
    assert out[0].get("translation_failed") is True
    assert out[0]["lang_detected"] is None
    assert out[0]["text_en"] is None
    assert out[0]["text_zh_cn"] is None


def test_success_path_never_null_lang_without_failed_flag():
    tweets = [{"tweet_id": "1", "text": "hi"}]
    client = RecordingClient([
        {"results": [{
            "tweet_id": "1",
            "lang_detected": "en",
            "text_en": "hi",
            "literal_zh": "嗨",
            "en_equivalent": "A brief greeting to the audience.",
            "cn_equivalent": "跟大家简单问个好。",
            "annotation": "",
        }]}
    ])
    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    for r in out:
        if not r.get("translation_failed"):
            assert r.get("lang_detected") is not None


def test_zh_cn_synonym_normalize_then_noop():
    """AE2: zh-cn → zh-Hans; Simplified noop nulls text_zh_cn."""
    tweets = [{"tweet_id": "1", "text": "Claude 真不错"}]
    client = RecordingClient([
        {"results": [{
            "tweet_id": "1",
            "lang_detected": "zh-cn",
            "text_en": "Claude is good",
            "literal_zh": "Claude 真不错",
            "en_equivalent": "Claude is receiving a positive assessment.",
            "cn_equivalent": "Claude 这波表现挺不错。",
            "annotation": "",
        }]}
    ])
    out = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    assert client.call_count == 1
    row = out[0]
    assert row["lang_detected"] == "zh-Hans"
    assert row["text_zh_cn"] is None
    assert row["literal_zh"] is None
    assert row["text_en"] == "Claude is good"


def test_never_three_llm_calls_on_repair_path():
    tweets = [{"tweet_id": "z", "text": "x"}]
    bad = {
        "results": [{
            "tweet_id": "z",
            "text_en": "x",
            "literal_zh": "x",
            "en_equivalent": "The post makes a deliberately minimal statement.",
            "cn_equivalent": "这条就简单说一个 x。",
            "annotation": "",
        }]
    }
    client = RecordingClient([bad, bad])
    translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=client)
    assert client.call_count == 2
