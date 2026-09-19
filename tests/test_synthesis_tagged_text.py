from types import SimpleNamespace

import pytest

from x_monitor.provider_telemetry import ProviderTextResponse
from x_monitor.synthesis import (
    SynthesisResponse,
    build_tagged_synthesis_prompt,
    synthesize_post,
)


class _TextClient:
    _base_url = "https://api.deepinfra.com/v1/openai/chat/completions"

    def __init__(self, text: str):
        self.text = text
        self.calls: list[dict] = []

    def messages_create_text(self, **kwargs):
        self.calls.append(kwargs)
        return ProviderTextResponse(
            self.text,
            provider_usage={"input_tokens": 11, "output_tokens": 22},
        )


def _config(**overrides):
    values = {
        "model": "google/gemma-4-31B-it-turbo",
        "max_output_tokens_per_post": 4096,
        "max_input_tokens_per_post": 20_000,
        "timeout_seconds": 60,
        "response_format": "tagged_text",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _answer(post_id="p1"):
    return (
        f"[[POST_ID]]{post_id}[[/POST_ID]]\n"
        "[[EN]]The author describes a model result.[[/EN]]\n"
        "[[ZH_CN]]作者描述了模型结果。[[/ZH_CN]]\n"
        "[[JA]]著者はモデルの結果を説明しています。[[/JA]]"
    )


def test_tagged_request_matches_gemma_contract_and_reports_usage():
    client = _TextClient(_answer())
    context = {"post": "hello\nworld", "stored_quote": "quoted"}

    result = synthesize_post(
        post_id="p1", context=context, client=client, config=_config()
    )

    assert isinstance(result, SynthesisResponse)
    assert result.texts["en"].startswith("The author")
    assert result.input_tokens == 11
    assert result.output_tokens == 22
    request = client.calls[0]
    assert request["model"] == "google/gemma-4-31B-it-turbo"
    assert request["max_tokens"] == 4096
    assert request["temperature"] == 0.2
    assert "thinking" not in request
    assert "reasoning" not in request
    system, user = build_tagged_synthesis_prompt(post_id="p1", context=context)
    assert request["system"] == system
    assert request["messages"] == [{"role": "user", "content": user}]
    assert '"post_id":"p1"' in user
    assert "hello\\nworld" in user


def test_tagged_parser_accepts_gemma_collapsed_middle_boundaries():
    answer = (
        "[[POST_ID]]p1[[/POST_ID]]\n"
        "[[EN]]English explanation.[[/ZH_CN]]"
        "中文解释。[[/JA]]"
        "日本語の説明。[[/JA]]"
    )

    result = synthesize_post(
        post_id="p1", context={"post": "x"}, client=_TextClient(answer), config=_config()
    )

    assert result.texts == {
        "en": "English explanation.",
        "zh-cn": "中文解释。",
        "ja": "日本語の説明。",
    }


def test_tagged_parser_accepts_gemma_wrong_english_closer():
    answer = (
        "[[POST_ID]]p1[[/POST_ID]]\n"
        "[[EN]]English explanation.[[/ZH_CN]]\n"
        "[[ZH_CN]]中文解释。[[/ZH_CN]]\n"
        "[[JA]]日本語の説明。[[/JA]]"
    )

    result = synthesize_post(
        post_id="p1", context={"post": "x"}, client=_TextClient(answer), config=_config()
    )

    assert result.texts == {
        "en": "English explanation.",
        "zh-cn": "中文解释。",
        "ja": "日本語の説明。",
    }


def test_tagged_parser_accepts_gemma_next_locale_closers_with_openers():
    answer = (
        "[[POST_ID]]p1[[/POST_ID]]\n"
        "[[EN]]English explanation.[[/ZH_CN]]\n"
        "[[ZH_CN]]中文解释。[[/JA]]\n"
        "[[JA]]日本語の説明。[[/JA]]"
    )

    result = synthesize_post(
        post_id="p1", context={"post": "x"}, client=_TextClient(answer), config=_config()
    )

    assert result.texts == {
        "en": "English explanation.",
        "zh-cn": "中文解释。",
        "ja": "日本語の説明。",
    }


@pytest.mark.parametrize(
    "answer,error",
    [
        (_answer("wrong"), "synthesis_response_identity_mismatch"),
        (_answer() + "\nextra", "synthesis_response_tagged_text_invalid"),
        (_answer().replace("[[EN]]", "[[EN]][[EN]]"), "synthesis_response_tagged_text_invalid"),
        (_answer().replace("[[JA]]著者はモデルの結果を説明しています。", "[[JA]][[/JA]]"), "synthesis_response_tagged_text_invalid"),
        (_answer().replace("[[JA]]著者はモデルの結果を説明しています。", "[[JA]]The author describes a model result."), "synthesis_response_locale_duplication"),
    ],
)
def test_tagged_parser_rejects_malformed_or_unsafe_output(answer, error):
    with pytest.raises(ValueError, match=error):
        synthesize_post(
            post_id="p1", context={"post": "x"}, client=_TextClient(answer), config=_config()
        )


def test_legacy_json_path_remains_unchanged():
    class JsonClient:
        def messages_create(self, **kwargs):
            assert kwargs["thinking"] == {"type": "disabled"}
            return {
                "post_id": "p1",
                "commentary_en": "English",
                "commentary_zh_cn": "中文",
                "commentary_ja": "日本語",
            }

    result = synthesize_post(
        post_id="p1",
        context={"post": "x"},
        client=JsonClient(),
        config=_config(response_format="json"),
    )
    assert result.texts == {"en": "English", "zh-cn": "中文", "ja": "日本語"}
