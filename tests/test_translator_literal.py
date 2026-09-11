from __future__ import annotations

from x_monitor.provider_telemetry import ProviderResponse
from x_monitor.translator import (
    build_literal_translation_prompt,
    translate_batch_literal,
)


class _Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_literal_prompt_requires_three_locales_and_forbids_commentary():
    prompt = build_literal_translation_prompt(
        [{"tweet_id": "1", "text": "モデルを公開しました"}]
    )

    assert '"text_en"' in prompt
    assert '"text_zh_cn"' in prompt
    assert '"text_ja"' in prompt
    assert "Do not add analysis, commentary, or facts" in prompt


def test_literal_translation_validates_identity_and_allocates_usage_once():
    client = _Client(
        ProviderResponse(
            {
                "results": [
                    {
                        "tweet_id": "1",
                        "lang_detected": "ja",
                        "text_en": "First",
                        "text_zh_cn": "第一",
                        "text_ja": "一番目",
                    },
                    {
                        "tweet_id": "2",
                        "lang_detected": "en",
                        "text_en": "Second",
                        "text_zh_cn": "第二",
                        "text_ja": "二番目",
                    },
                ]
            },
            usage={"input_tokens": 5, "output_tokens": 3},
        )
    )

    rows = translate_batch_literal(
        [
            {"tweet_id": "1", "text": "一番目"},
            {"tweet_id": "2", "text": "Second"},
        ],
        client,
    )

    assert [row["input_tokens"] for row in rows] == [3, 2]
    assert [row["output_tokens"] for row in rows] == [2, 1]
    assert sum(row["input_tokens"] for row in rows) == 5
    assert sum(row["output_tokens"] for row in rows) == 3
    assert client.calls[0]["max_tokens"] == 2048


def test_literal_translation_rejects_wrong_identity_or_missing_japanese():
    client = _Client(
        {
            "results": [
                {
                    "tweet_id": "wrong",
                    "lang_detected": "en",
                    "text_en": "source",
                    "text_zh_cn": "来源",
                    "text_ja": "原文",
                },
                {
                    "tweet_id": "2",
                    "lang_detected": "en",
                    "text_en": "source",
                    "text_zh_cn": "来源",
                    "text_ja": "",
                },
            ]
        }
    )

    rows = translate_batch_literal(
        [
            {"tweet_id": "1", "text": "source"},
            {"tweet_id": "2", "text": "source"},
        ],
        client,
    )

    assert all(row["translation_failed"] for row in rows)
