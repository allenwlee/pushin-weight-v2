"""Focused contracts for one-post, one-locale plain-text translation."""

from __future__ import annotations

import threading
from typing import Any

import pytest


class TextResponse:
    def __init__(self, text: str, usage: dict[str, int] | None = None) -> None:
        self.text = text
        self.provider_usage = usage


class PlaintextClient:
    def __init__(
        self, replies: list[object], *, request_profile: str | None = None
    ) -> None:
        self.replies = list(replies)
        self.request_profile = request_profile
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def messages_create_text(self, **kwargs: Any) -> TextResponse:
        with self._lock:
            self.calls.append(kwargs)
            reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply  # type: ignore[return-value]


def _prompt(call: dict[str, Any]) -> str:
    return call["messages"][0]["content"]


def test_native_source_is_byte_exact_and_only_other_two_locales_are_called():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    source = 'A "quoted" path C:\\tmp\nhttps://example.test/a\n\nSecond paragraph'
    translated_zh = "“译文” C:\\tmp\nhttps://example.test/a\n\n第二段"
    client = PlaintextClient(
        [
            TextResponse(translated_zh, {"input_tokens": 11, "output_tokens": 5}),
            TextResponse("日本語訳", {"input_tokens": 13, "output_tokens": 7}),
        ]
    )

    row = translate_batch_literal_plaintext(
        [{"tweet_id": "native", "text": source, "lang_detected": "en"}], client
    )[0]

    assert row["text_en"] == source
    assert row["text_en"].encode("utf-8") == source.encode("utf-8")
    assert row["text_zh_cn"] == translated_zh
    assert row["text_ja"] == "日本語訳"
    assert row["lang_detected"] == "en"
    assert not row["translation_failed"]
    assert len(client.calls) == 2
    assert all("English" not in _prompt(call) for call in client.calls)
    assert row["input_tokens"] == 24
    assert row["output_tokens"] == 12


@pytest.mark.parametrize("source_language", ["zh-Hant", "ko", "other"])
def test_non_native_supported_source_calls_all_three_locales(source_language: str):
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    client = PlaintextClient(
        [TextResponse("en"), TextResponse("zh"), TextResponse("ja")]
    )

    row = translate_batch_literal_plaintext(
        [{"tweet_id": source_language, "text": "繁體原文", "lang": source_language}],
        client,
    )[0]

    assert len(client.calls) == 3
    assert row["lang_detected"] == source_language
    assert row["text_en"] == "en"
    assert row["text_zh_cn"] == "zh"
    assert row["text_ja"] == "ja"
    assert row["translation_failed"] is False


def test_unknown_language_uses_tiny_detection_then_translates_all_locales():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    client = PlaintextClient(
        [
            TextResponse("other", {"input_tokens": 3, "output_tokens": 1}),
            TextResponse("English", {"input_tokens": 10, "output_tokens": 4}),
            TextResponse("中文", {"input_tokens": 11, "output_tokens": 5}),
            TextResponse("日本語", {"input_tokens": 12, "output_tokens": 6}),
        ]
    )

    row = translate_batch_literal_plaintext(
        [{"tweet_id": "unknown", "text": "bonjour le monde", "lang_detected": "??"}],
        client,
    )[0]

    assert len(client.calls) == 4
    assert client.calls[0]["max_tokens"] == 16
    assert "Identify only the source language" in _prompt(client.calls[0])
    assert row["lang_detected"] == "other"
    assert row["text_en"] == "English"
    assert row["translation_failed"] is False
    assert row["input_tokens"] == 36
    assert row["output_tokens"] == 16


def test_detector_rejects_unrequested_iso_code_instead_of_silently_mapping_it():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    client = PlaintextClient(
        [TextResponse("fr", {"input_tokens": 3, "output_tokens": 1})]
    )
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "bad-detector", "text": "bonjour le monde"}], client
    )[0]

    assert len(client.calls) == 1
    assert row["lang_detected"] is None
    assert row["translation_failed"] is True
    assert row["input_tokens"] == 3
    assert row["output_tokens"] == 1


def test_missing_locale_isolated_and_keeps_successes_and_error_usage():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    error = RuntimeError("provider failed")
    error.provider_usage = {"input_tokens": 9, "output_tokens": 2}  # type: ignore[attr-defined]
    client = PlaintextClient(
        [
            TextResponse("简体", {"input_tokens": 5, "output_tokens": 3}),
            error,
        ]
    )

    row = translate_batch_literal_plaintext(
        [{"tweet_id": "partial", "text": "source", "source_language": "en"}], client
    )[0]

    assert row["text_en"] == "source"
    assert row["text_zh_cn"] == "简体"
    assert row["text_ja"] is None
    assert row["translation_failed"] is True
    assert row["input_tokens"] == 14
    assert row["output_tokens"] == 5
    assert len(client.calls) == 2


def test_expired_deadline_prevents_every_provider_call():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    class ExpiredDeadline:
        def request_timeout(self) -> float:
            return 0.0

    client = PlaintextClient([])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "late", "text": "source", "lang": "en"}],
        client,
        deadline=ExpiredDeadline(),
    )[0]

    assert client.calls == []
    assert row["translation_failed"] is True
    assert row["text_en"] == "source"
    assert row["text_zh_cn"] is None
    assert row["text_ja"] is None


def test_deadline_error_is_a_failed_row_and_does_not_abort_parallel_batch():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    class BrokenDeadline:
        def request_timeout(self) -> float:
            raise RuntimeError("clock failed")

    client = PlaintextClient([])
    rows = translate_batch_literal_plaintext(
        [
            {"tweet_id": "one", "text": "one", "lang": "en"},
            {"tweet_id": "two", "text": "two", "lang": "en"},
        ],
        client,
        deadline=BrokenDeadline(),
        max_workers=2,
    )

    assert client.calls == []
    assert [row["tweet_id"] for row in rows] == ["one", "two"]
    assert [row["text_en"] for row in rows] == ["one", "two"]
    assert all(row["translation_failed"] for row in rows)


def test_profile_request_shape_budget_and_parallel_output_order_are_bounded():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    class OrderedClient(PlaintextClient):
        def messages_create_text(self, **kwargs: Any) -> TextResponse:
            prompt = _prompt(kwargs)
            marker = prompt.rsplit("SOURCE:\n", 1)[1]
            with self._lock:
                self.calls.append(kwargs)
            return TextResponse(
                f"translated-{marker}", {"input_tokens": 1, "output_tokens": 1}
            )

    long_source = "x" * 2_600
    client = OrderedClient([], request_profile="deepseek_0731")
    rows = translate_batch_literal_plaintext(
        [
            {"tweet_id": "one", "text": long_source, "lang": "en"},
            {"tweet_id": "two", "text": "two", "lang": "en"},
        ],
        client,
        max_workers=2,
    )

    assert [row["tweet_id"] for row in rows] == ["one", "two"]
    assert [row["text_en"] for row in rows] == [long_source, "two"]
    assert all(call["temperature"] == 1.0 for call in client.calls)
    assert all(call["top_p"] == 1.0 for call in client.calls)
    assert all(call["seed"] == 42 for call in client.calls)
    assert max(call["max_tokens"] for call in client.calls) <= 8_192
    assert min(call["max_tokens"] for call in client.calls) >= 1_024
    assert any(call["max_tokens"] > 1_024 for call in client.calls)


def test_blank_source_fails_without_calling_the_provider():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    client = PlaintextClient([])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "blank", "text": " \n\t ", "lang": "en"}], client
    )[0]

    assert client.calls == []
    assert row["translation_failed"] is True
    assert row["text_en"] is None
