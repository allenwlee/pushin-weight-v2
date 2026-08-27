"""Regression net for required bilingual translator commentary."""

from __future__ import annotations

from typing import Any

from x_monitor.translator import (
    build_pragmatics_translation_prompt,
    translate_batch_pragmatics,
)


class RecordingClient:
    def __init__(self, *responses: dict[str, Any]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.responses[len(self.calls) - 1]


def _complete_row(tweet_id: str, **overrides: Any) -> dict[str, Any]:
    row = {
        "tweet_id": tweet_id,
        "lang_detected": "en",
        "text_en": "MiniMax shipped an update",
        "literal_zh": "MiniMax 发布了更新",
        "en_equivalent": "MiniMax has another product update worth watching.",
        "cn_equivalent": "MiniMax 又上新了，值得关注。",
        "annotation": "",
        "noop_en": True,
        "noop_zh": False,
    }
    row.update(overrides)
    return row


def test_prompt_requires_distinct_bilingual_commentary():
    prompt = build_pragmatics_translation_prompt(
        [{"tweet_id": "1", "text": "MiniMax shipped an update"}],
        ["en", "zh_cn"],
        few_shot_examples=[],
    )

    assert "en_equivalent" in prompt
    assert "cn_equivalent" in prompt
    assert "never use 'n/a'" in prompt.lower()
    assert "must not copy" in prompt


def test_complete_commentary_row_uses_one_call_and_returns_both_locales():
    tweets = [{"tweet_id": "1", "text": "MiniMax shipped an update"}]
    client = RecordingClient({"results": [_complete_row("1")]})

    result = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client)

    assert len(client.calls) == 1
    assert result[0]["en_equivalent"].startswith("MiniMax has")
    assert result[0]["cn_equivalent"].startswith("MiniMax 又")
    assert result[0].get("translation_failed") is not True


def test_missing_english_commentary_gets_one_targeted_full_row_repair():
    tweets = [
        {"tweet_id": "ok", "text": "MiniMax shipped an update"},
        {"tweet_id": "repair", "text": "DeepSeek shipped an update"},
    ]
    first = {
        "results": [
            _complete_row("ok"),
            _complete_row("repair", en_equivalent=""),
        ]
    }
    repaired = {
        "results": [
            _complete_row(
                "repair",
                text_en="",
                literal_zh="",
                en_equivalent="DeepSeek has a fresh release to evaluate.",
            )
        ]
    }
    client = RecordingClient(first, repaired)

    result = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client)

    assert len(client.calls) == 2
    repair_prompt = client.calls[1]["messages"][0]["content"]
    assert '"tweet_id": "repair"' in repair_prompt
    assert '"tweet_id": "ok"' not in repair_prompt
    by_id = {row["tweet_id"]: row for row in result}
    assert by_id["repair"]["text_zh_cn"] == "MiniMax 发布了更新"
    assert by_id["repair"]["en_equivalent"].startswith("DeepSeek has")


def test_commentary_that_copies_source_is_incomplete_after_one_repair():
    tweets = [{"tweet_id": "1", "text": "MiniMax shipped an update"}]
    duplicate = _complete_row(
        "1",
        en_equivalent="MiniMax shipped an update",
        cn_equivalent="MiniMax 发布了更新",
    )
    client = RecordingClient(
        {"results": [duplicate]},
        {"results": [duplicate]},
    )

    result = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client)

    assert len(client.calls) == 2
    assert result[0]["translation_failed"] is True
    assert result[0]["en_equivalent"] is None
    assert result[0]["cn_equivalent"] is None


def test_commentary_that_copies_either_translation_is_incomplete():
    tweets = [{"tweet_id": "1", "text": "MiniMax shipped an update"}]
    duplicate = _complete_row(
        "1",
        en_equivalent="MiniMax 发布了更新",
        cn_equivalent="MiniMax shipped an update",
    )
    client = RecordingClient(
        {"results": [duplicate]},
        {"results": [duplicate]},
    )

    result = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client)

    assert len(client.calls) == 2
    assert result[0]["translation_failed"] is True
    assert result[0]["en_equivalent"] is None
    assert result[0]["cn_equivalent"] is None


def test_zh_hans_source_still_requires_english_translation_and_commentary():
    tweets = [{"tweet_id": "1", "text": "MiniMax 发布了更新"}]
    client = RecordingClient(
        {
            "results": [
                _complete_row(
                    "1",
                    lang_detected="zh-Hans",
                    text_en="MiniMax shipped an update",
                    literal_zh="",
                    en_equivalent="MiniMax has another update worth watching.",
                    cn_equivalent="MiniMax 又上新了，值得关注。",
                    noop_en=False,
                    noop_zh=True,
                )
            ]
        }
    )

    result = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client)

    assert len(client.calls) == 1
    assert result[0]["lang_detected"] == "zh-Hans"
    assert result[0]["text_en"] == "MiniMax shipped an update"
    assert result[0]["text_zh_cn"] is None


def test_emoji_only_post_receives_real_bilingual_interpretation():
    tweets = [{"tweet_id": "1", "text": "🚀🔥"}]
    client = RecordingClient(
        {
            "results": [
                _complete_row(
                    "1",
                    lang_detected="other",
                    text_en="Excitement about a launch.",
                    literal_zh="对发布表示兴奋。",
                    en_equivalent="The launch reaction is pure excitement.",
                    cn_equivalent="这波发布直接燃起来了。",
                    noop_en=False,
                )
            ]
        }
    )

    result = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client)

    assert result[0]["text_zh_cn"]
    assert result[0]["en_equivalent"]
    assert result[0]["cn_equivalent"]
