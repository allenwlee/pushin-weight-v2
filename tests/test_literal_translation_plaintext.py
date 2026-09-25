"""Focused contracts for one-post, one-locale plain-text translation."""

from __future__ import annotations

import re
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


def test_local_provider_request_rejection_is_not_a_sent_attempt():
    from x_monitor.deepinfra import DeepInfraPermanentError
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    client = PlaintextClient([DeepInfraPermanentError("deepinfra_model_mismatch")])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "bad-config", "text": "An update", "lang": "en"}], client,
        deadline=type("OneCallDeadline", (), {"request_timeout": lambda self: 0 if len(client.calls) else 10})(),
    )[0]

    assert row["translation_failed"] is True
    assert row["provider_calls"] == 0
    assert row["failure_reasons"]["zh-Hans"] == "not_sent_configuration"


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


def test_long_post_chunks_are_bounded_and_resume_only_missing_pieces():
    from x_monitor.literal_translation import (
        CHUNK_TRANSLATION_PROMPT_VERSION,
        _split_translation_chunks,
        translate_batch_literal_plaintext,
    )

    source = ("alpha " * 800 + "\n\n") * 5
    assert 23_000 < len(source) < 25_000
    chunks = _split_translation_chunks(source)
    assert len(chunks) > 2
    assert "".join(chunks) == source
    assert max(map(len, chunks)) <= 5_000
    saved: dict[str, dict[str, dict[str, dict[int, str]]]] = {"long": {}}

    class ChunkClient:
        def __init__(self, *, fail_at: int | None = None):
            self.calls = []
            self.fail_at = fail_at

        def messages_create_text(self, **kwargs):
            self.calls.append(kwargs)
            prompt = _prompt(kwargs)
            assert CHUNK_TRANSLATION_PROMPT_VERSION in prompt
            chunk = prompt.split("CHUNK:\n", 1)[1]
            assert len(chunk) <= 5_000
            if self.fail_at == len(self.calls):
                raise TimeoutError("socket timeout")
            return TextResponse("译" + chunk)

    def persist(**kwargs):
        saved["long"].setdefault(kwargs["source_language"], {}).setdefault(kwargs["target_language"], {})[
            kwargs["chunk_index"]
        ] = kwargs["translated_text"]
        return True

    tweet = {"tweet_id": "long", "text": source, "lang": "en"}
    first = ChunkClient(fail_at=3)
    row = translate_batch_literal_plaintext(
        [tweet], first, on_chunk_success=persist
    )[0]
    assert row["translation_failed"] is True
    assert row["provider_calls"] >= 3
    assert row["new_chunks"] >= 2
    completed_before = sum(len(locale) for language in saved["long"].values() for locale in language.values())

    second = ChunkClient()
    resumed = translate_batch_literal_plaintext(
        [tweet], second, cached_chunks=saved, on_chunk_success=persist
    )[0]
    assert resumed["translation_failed"] is False
    assert resumed["text_en"] == source
    assert len(second.calls) == (2 * len(chunks)) - completed_before


def test_long_unknown_source_language_detection_uses_only_first_chunk():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    source = "English words " * 800
    client = PlaintextClient([TextResponse("en")])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "detect-long", "text": source}],
        client,
        deadline=type("OneCallDeadline", (), {"request_timeout": lambda self: 0 if len(client.calls) else 10})(),
    )[0]

    assert len(client.calls) == 1
    assert len(_prompt(client.calls[0]).split("SOURCE:\n", 1)[1]) == 5_000
    assert row["lang_detected"] == "en"
    assert row["provider_calls"] == 1
    assert row["translation_failed"] is True


def _payload_markers_and_paragraphs(call: dict[str, Any]) -> tuple[list[str], list[str]]:
    payload = _prompt(call).split("SOURCE:\n", 1)[1]
    marker_matches = list(re.finditer(r"(?m)^\[\[PW\d+:(?:\d{3}|END)\]\]$", payload))
    assert marker_matches and marker_matches[0].start() == 0
    markers = [match.group(0) for match in marker_matches]
    paragraphs = [
        payload[match.end() + 1 : marker_matches[index + 1].start() - 1]
        for index, match in enumerate(marker_matches[:-1])
    ]
    return markers, paragraphs


def _marked_reply(
    call: dict[str, Any], translated: list[str], *, final_protocol_newline: bool = False
) -> str:
    markers, _ = _payload_markers_and_paragraphs(call)
    reply = "\n".join(
        [item for marker, value in zip(markers[:-1], translated) for item in (marker, value)]
        + [markers[-1]]
    )
    return reply + ("\n" if final_protocol_newline else "")


def test_paragraph_tracking_preserves_separators_quotes_and_calls_once_per_target():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    source = '"Quoted" line\n \n\nSecond paragraph\n\n\nThird paragraph'
    client = PlaintextClient(
        [TextResponse("placeholder") for _ in range(2)]
    )

    class MarkingClient(PlaintextClient):
        def messages_create_text(self, **kwargs: Any) -> TextResponse:
            self.calls.append(kwargs)
            _, source_parts = _payload_markers_and_paragraphs(kwargs)
            return TextResponse(_marked_reply(kwargs, [f"T:{p}" for p in source_parts]))

    client = MarkingClient([])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "paragraphs", "text": source, "lang": "en"}],
        client,
        paragraph_tracking=True,
    )[0]
    assert row["text_en"] == source
    assert row["text_zh_cn"] == 'T:"Quoted" line\n \n\nT:Second paragraph\n\n\nT:Third paragraph'
    assert row["text_ja"] == row["text_zh_cn"]
    assert len(client.calls) == 2
    assert all("literal-translation-lines-v13" in _prompt(c) for c in client.calls)
    assert all("Include every block" in _prompt(c) for c in client.calls)
    assert all(" -> " not in _prompt(c) for c in client.calls)
    assert all(c["max_tokens"] <= 8192 for c in client.calls)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda markers: markers[:-1],
        lambda markers: [markers[0], markers[0], *markers[1:]],
        lambda markers: [markers[1], markers[0], *markers[2:]],
        lambda markers: [markers[0], markers[0][:-4] + "999]]", *markers[1:]],
    ],
    ids=["missing", "duplicate", "out-of-order", "unknown"],
)
def test_paragraph_marker_validation_fails_and_retains_usage(mutation):
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    class BadClient(PlaintextClient):
        def messages_create_text(self, **kwargs: Any) -> TextResponse:
            self.calls.append(kwargs)
            markers, _ = _payload_markers_and_paragraphs(kwargs)
            bad = mutation(markers)
            response = "\n".join(
                [item for index, marker in enumerate(bad[:-1]) for item in (marker, f"translated-{index}")]
                + [bad[-1]]
            )
            return TextResponse(response, {"input_tokens": 7, "output_tokens": 3})

    client = BadClient([])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "bad-markers", "text": "one\n\ntwo", "lang": "en"}],
        client,
        paragraph_tracking=True,
    )[0]
    assert len(client.calls) == 2
    assert row["translation_failed"] is True
    assert row["text_zh_cn"] is None and row["text_ja"] is None
    assert row["input_tokens"] == 14
    assert row["output_tokens"] == 6


def test_paragraph_markers_avoid_source_collision_and_native_copy_is_exact():
    from x_monitor.literal_translation import (
        _paragraph_protocol,
        translate_batch_literal_plaintext,
    )

    source = "contains [[PW0:001]] and [[PW1:END]] and a quote: `x`\n\nsecond"
    markers, payload, _ = _paragraph_protocol(source, "zh-Hans")
    assert all(marker not in source for marker in markers)
    assert all(marker in payload for marker in markers)
    assert markers[0].startswith("[[PW2:")
    assert all(8 <= len(marker) <= 12 for marker in markers)

    class CollisionClient(PlaintextClient):
        def messages_create_text(self, **kwargs: Any) -> TextResponse:
            self.calls.append(kwargs)
            return TextResponse(
                _marked_reply(kwargs, ["保留 [[PW0:001]] 和 [[PW1:END]]", "第二"])
            )

    client = CollisionClient([])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "native-paragraph", "text": source, "lang": "en"}],
        client,
        paragraph_tracking=True,
    )[0]
    assert row["text_en"] == source
    assert len(client.calls) == 2
    assert "[[PW0:001]]" in row["text_zh_cn"]
    assert "[[PW1:END]]" in row["text_zh_cn"]


def test_paragraph_tracking_restores_blank_boundaries_and_keeps_raw_output_whitespace():
    from x_monitor.literal_translation import (
        _paragraph_protocol,
        translate_batch_literal_plaintext,
    )

    source = "\n \n\n\tfirst  \n \n\n second\t\n\n \n"
    _, _, separators = _paragraph_protocol(source, "zh-Hans")

    class WhitespaceClient(PlaintextClient):
        def messages_create_text(self, **kwargs: Any) -> TextResponse:
            self.calls.append(kwargs)
            return TextResponse(
                _marked_reply(kwargs, ["  第一  ", "\t第二\t"], final_protocol_newline=True)
            )

    client = WhitespaceClient([])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "boundaries", "text": source, "lang": "en"}],
        client,
        paragraph_tracking=True,
    )[0]
    expected = separators[0] + "  第一  " + separators[1] + "\t第二\t" + separators[2]
    assert row["text_zh_cn"] == expected
    assert row["text_ja"] == expected
    assert row["text_en"] == source


def test_paragraph_tracking_keeps_single_paragraph_on_original_raw_protocol():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    client = PlaintextClient([TextResponse("zh"), TextResponse("ja")])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "single", "text": '\n\n"quoted" single line\n\n', "lang": "en"}],
        client,
        paragraph_tracking=True,
    )[0]
    assert len(client.calls) == 2
    assert all("literal-translation-lines-v13" not in _prompt(call) for call in client.calls)
    assert row["text_zh_cn"] == "zh"


def test_untranslated_japanese_prose_is_rejected_without_retry_and_retains_usage():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    source = "日本語の発音について説明します。こちらの例を読んでください。発音と意味の違いを確認しましょう。"
    client = PlaintextClient([
        TextResponse(source, {"input_tokens": 11, "output_tokens": 21}),
        TextResponse("这是日语发音的说明。请阅读例子并注意发音与意思的区别。", {"input_tokens": 12, "output_tokens": 22}),
    ])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "wrong-language", "text": source, "lang": "ja"}], client,
    )[0]
    assert len(client.calls) == 2
    assert row["translation_failed"] is True
    assert row["text_en"] is None
    assert row["text_ja"] == source
    assert row["text_zh_cn"] is not None
    assert row["input_tokens"] == 23 and row["output_tokens"] == 43


def test_quantity_contradiction_is_rejected_even_when_headline_is_correct():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    client = PlaintextClient([
        TextResponse("训练使用了[[PQ0:001]]。"),
        TextResponse("[[PQ0:001]]。本文では100億トークンで学習したと述べる。"),
    ])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "wrong-number", "text": "Trained on 10.9 trillion tokens.", "lang": "en"}], client,
    )[0]
    assert len(client.calls) == 2
    assert row["text_zh_cn"] is not None
    assert row["text_ja"] is None
    assert row["translation_failed"] is True


def test_paragraph_framing_blank_lines_are_removed_without_stripping_indentation():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    class FramingClient(PlaintextClient):
        def messages_create_text(self, **kwargs):
            self.calls.append(kwargs)
            return TextResponse(_marked_reply(kwargs, ["\n \n  第一\n", "  続き  \n\n", "\n\t第二\t\n"]))

    source = "first\ncontinuation\n \n\nsecond"
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "framing", "text": source, "lang": "en"}], FramingClient([]),
        paragraph_tracking=True,
    )[0]
    assert row["text_zh_cn"] == "  第一\n  続き  \n \n\n\t第二\t"
    assert not row["translation_failed"]


@pytest.mark.parametrize("source,translated,target", [
    ("ChatGPT → チャットジーピーティー", "ChatGPT → チャットジーピーティー", "en"),
    ("```\n日本語のコード例をそのまま残してくださいという例です\n```", "```\n日本語のコード例をそのまま残してくださいという例です\n```", "en"),
    ("日本語の発音について説明します。こちらの例を読んでください。", "Read these Japanese pronunciation examples: オブシディアン", "en"),
    ("繁體中文的相同漢字在簡體中也可能保持相同的寫法。", "繁體中文的相同漢字在簡體中也可能保持相同的寫法。", "zh-Hans"),
])
def test_source_copy_detector_leaves_short_examples_code_and_translated_prose_alone(source, translated, target):
    from x_monitor.literal_translation import _is_untranslated_copy

    assert not _is_untranslated_copy(source, translated, target)


def test_caller_restores_localized_token_quantity_without_model_arithmetic():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    source = "More than 10.9 trillion tokens.\n\nThe next trillion tokens."

    class ProtectedClient(PlaintextClient):
        def messages_create_text(self, **kwargs):
            self.calls.append(kwargs)
            _, blocks = _payload_markers_and_paragraphs(kwargs)
            assert "10.9" not in blocks[0]
            assert "next" in blocks[1]
            return TextResponse(_marked_reply(kwargs, [
                "使用[[PQ0:001]]以上。", "次の[[PQ0:002]]。",
            ]), {"input_tokens": 5, "output_tokens": 7})

    client = ProtectedClient([])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "protected", "text": source, "lang": "en"}], client, paragraph_tracking=True,
    )[0]
    assert row["text_en"] == source
    assert row["text_ja"] == "使用10.9兆トークン以上。\n\n次の1兆トークン。"
    assert not row["translation_failed"]
    assert len(client.calls) == 2


@pytest.mark.parametrize("suffix", ["", "[[PW0::END]]"])
def test_complete_paragraphs_accept_observed_terminal_variants_without_repair_call(suffix):
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    class TerminalClient(PlaintextClient):
        def messages_create_text(self, **kwargs):
            self.calls.append(kwargs)
            response = _marked_reply(kwargs, ["第一", "第二"])
            return TextResponse(response.removesuffix("[[PW0:END]]") + suffix)

    client = TerminalClient([])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "terminal", "text": "first\n\nsecond", "lang": "en"}], client,
        paragraph_tracking=True,
    )[0]
    assert not row["translation_failed"]
    assert row["text_zh_cn"] == "第一\n\n第二"
    assert len(client.calls) == 2


@pytest.mark.parametrize("reply", [
    "[[PW0:001]]\nfirst\n[[PW0:END]]",  # missing numbered block
    "[[PW0:001]]\nfirst\n[[PW0:002]]\n",  # empty final content
    "[[PW0:001]]\nfirst\n[[PW0:002]]\nsecond\n[[PW0:999",  # partial garbage
    "[[PW0:001]]\nfirst\n[[PW0:002]]\nsecond\n[[PW0:END]]\ngarbage",
    "[[PW0:001]]\nfirst\n[[PW0:002]]\nsecond\n[[PW0::END]]\ngarbage",
])
def test_terminal_normalization_does_not_relax_content_or_marker_integrity(reply):
    from x_monitor.literal_translation import _parse_paragraph_response

    text, usage, elapsed = _parse_paragraph_response(reply, ["[[PW0:001]]", "[[PW0:002]]", "[[PW0:END]]"], ["", "\n\n", ""], {"input_tokens": 9}, 7)
    assert text is None and usage["input_tokens"] == 9 and elapsed == 7


@pytest.mark.parametrize("paragraph_tracking", [False, True])
def test_fidelity_rules_reach_both_real_translation_formats(paragraph_tracking):
    """Prompt-delivery pin, not a simulated claim of translation accuracy."""
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    source = "Use Model A with characters B and C.\n\nPronunciation: Widget → ウィジェット"
    client = PlaintextClient([TextResponse("译文"), TextResponse("訳文")])
    row = translate_batch_literal_plaintext(
        [{"tweet_id": "semantic-prompt", "text": source, "lang": "en"}],
        client, paragraph_tracking=paragraph_tracking,
    )[0]
    assert row["text_en"] == source
    assert len(client.calls) == 2
    for call in client.calls:
        prompt = _prompt(call)
        assert "whole post as context" in prompt
        assert "who did what to whom" in prompt
        assert "retain pronunciation spellings" in prompt
        assert "currency and denomination" in prompt
        assert "Do not soften insults" in prompt
        assert "every source line break" in prompt
        assert "block independently" not in prompt


def test_pronunciation_examples_are_protected_and_single_lines_framed():
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    source = 'Pronunciations\nWidget → ウィジェット（not 「ウィジェト」）\n\nEnd'

    class EchoMarkers(PlaintextClient):
        def messages_create_text(self, **kwargs):
            self.calls.append(kwargs)
            _, blocks = _payload_markers_and_paragraphs(kwargs)
            assert len(blocks) == 3
            assert 'ウィジェット' not in _prompt(kwargs)
            assert 'ウィジェト' not in _prompt(kwargs)
            return TextResponse(_marked_reply(kwargs, blocks))

    client = EchoMarkers([])
    row = translate_batch_literal_plaintext(
        [{'tweet_id': 'readings', 'text': source, 'lang': 'en'}],
        client, paragraph_tracking=True,
    )[0]
    assert row['text_en'] == row['text_zh_cn'] == row['text_ja'] == source
    assert len(client.calls) == 2


def test_pronunciation_protection_is_narrow_and_collision_safe():
    from x_monitor.translation_invariants import (
        protect_translation_spans,
        restore_token_quantities,
    )

    source = 'Ordinary prose 「カーソル」. [[PQ0:001]]\nWidget → ウィジェット（not 「ウィジェト」）\nA → ordinary translation'
    payload, replacements = protect_translation_spans(source, 'en')
    assert 'Ordinary prose 「カーソル」' in payload
    assert 'A → ordinary translation' in payload
    assert len(replacements) == 2
    assert all(k.startswith('[[PQ1:') for k in replacements)
    assert restore_token_quantities(payload, replacements) == source
    marker = next(iter(replacements))
    assert restore_token_quantities(payload.replace(marker, ''), replacements) is None
    assert restore_token_quantities(payload + marker, replacements) is None


def test_line_framing_rejects_inserted_internal_newline_and_retains_usage():
    from x_monitor.literal_translation import _parse_paragraph_response

    value, usage, _ = _parse_paragraph_response(
        '[[PW0:001]]\nfirst\ninvented line\n[[PW0:END]]',
        ['[[PW0:001]]', '[[PW0:END]]'], ['', ''], {'input_tokens': 12}, 0,
    )
    assert value is None
    assert usage['input_tokens'] == 12


def test_readings_and_quantities_share_unique_restorable_markers():
    from x_monitor.translation_invariants import (
        protect_translation_spans,
        restore_token_quantities,
    )

    source = '10.9 trillion tokens\r\nWidget → ウィジェット\r\nWidget → ウィジェット'
    payload, replacements = protect_translation_spans(source, 'ja')
    assert len(replacements) == 3
    assert restore_token_quantities(payload, replacements) == source.replace('10.9 trillion tokens', '10.9兆トークン')


def test_long_pronunciation_only_source_copy_is_not_untranslated_prose():
    from x_monitor.literal_translation import _is_untranslated_copy

    source = '\n'.join(['Widget → ウィジェット', 'Another → アナザー'] * 5)
    assert not _is_untranslated_copy(source, source, 'en')
    prose = 'これは発音を説明する長い日本語の文章です。説明文までコピーしてはいけません。\n' + source
    assert _is_untranslated_copy(prose, prose, 'en')
