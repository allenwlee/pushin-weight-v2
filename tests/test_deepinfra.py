from __future__ import annotations

import pytest

from x_monitor.deepinfra import (
    DEEPINFRA_ENDPOINT,
    DEEPSEEK_0731_MODEL,
    GEMMA_4_31B_MODEL,
    DeepInfraChatCompletionsClient,
    DeepInfraPermanentError,
)


def test_client_repr_never_contains_api_key():
    secret = "deepinfra-secret-value"
    client = DeepInfraChatCompletionsClient(
        api_key=secret,
        model=GEMMA_4_31B_MODEL,
    )

    assert secret not in repr(client)


def _response(model: str, content: str, *, finish_reason: str = "stop") -> dict:
    return {
        "id": "deepinfra-test-1",
        "model": model,
        "choices": [{"finish_reason": finish_reason, "message": {"content": content}}],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 7,
            "total_tokens": 19,
            "estimated_cost": 0.000123,
            "prompt_tokens_details": {"cached_tokens": 2},
            "completion_tokens_details": {"reasoning_tokens": 1},
        },
    }


def test_direct_request_has_deepinfra_shape_and_profile_settings():
    sent = []

    def transport(request, timeout):
        sent.append((request, timeout))
        return _response(DEEPSEEK_0731_MODEL, '{"ok": true}')

    client = DeepInfraChatCompletionsClient(
        api_key="secret", model=DEEPSEEK_0731_MODEL,
        request_profile="deepseek_0731", transport=transport,
    )
    response = client.messages_create(
        model=DEEPSEEK_0731_MODEL, max_tokens=80,
        system="system prompt", messages=[{"role": "user", "content": "hello"}],
        provider={"only": ["DeepInfra"]}, response_format={"type": "json_object"},
        reasoning={"enabled": False}, timeout=17,
    )

    request, timeout = sent[0]
    assert timeout == 17
    assert request == {
        "model": DEEPSEEK_0731_MODEL,
        "max_tokens": 80,
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
        ],
        "temperature": 1.0,
        "top_p": 1.0,
        "seed": 42,
        "reasoning_effort": "none",
    }
    assert response["ok"] is True
    assert response.provider_usage["provider"] == "DeepInfra"
    assert response.provider_usage["request_identity"].startswith("deepinfra:deepseek_0731:")
    assert response.provider_usage["cost_usd"] == 0.000123
    assert DEEPINFRA_ENDPOINT.endswith("/chat/completions")


def test_text_response_preserves_literal_multiline_content_and_receipt():
    literal = "line one\nline two\n{json-like text}"
    client = DeepInfraChatCompletionsClient(
        api_key="secret", model=GEMMA_4_31B_MODEL,
        request_profile="gemma4_31b",
        transport=lambda _request, _timeout: _response(GEMMA_4_31B_MODEL, literal),
    )
    result = client.messages_create_text(model=GEMMA_4_31B_MODEL, max_tokens=100, messages=[])
    assert result.text == literal
    assert result.provider_usage["input_tokens"] == 12
    assert result.provider_usage["reasoning_tokens"] == 1


def test_gemma_translation_profile_omits_sampler_and_reasoning_controls():
    sent = []
    client = DeepInfraChatCompletionsClient(
        api_key="secret",
        model=GEMMA_4_31B_MODEL,
        request_profile="gemma4_translation_v1",
        transport=lambda request, _timeout: (
            sent.append(request) or _response(GEMMA_4_31B_MODEL, "translated")
        ),
    )

    client.messages_create_text(
        model=GEMMA_4_31B_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": "source"}],
    )

    assert sent == [{
        "model": GEMMA_4_31B_MODEL,
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "source"}],
    }]


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (_response(DEEPSEEK_0731_MODEL, "partial", finish_reason="length"), "incomplete"),
        (_response(DEEPSEEK_0731_MODEL, ""), "content_missing"),
        (_response("wrong/model", "{}"), "model_mismatch"),
        (_response(DEEPSEEK_0731_MODEL, "[]"), "content_shape_invalid"),
    ],
)
def test_direct_response_validation_fails_closed(payload, error):
    client = DeepInfraChatCompletionsClient(
        api_key="secret", model=DEEPSEEK_0731_MODEL,
        transport=lambda _request, _timeout: payload,
    )
    with pytest.raises(DeepInfraPermanentError, match=error) as caught:
        client.messages_create(model=DEEPSEEK_0731_MODEL, max_tokens=20, messages=[])
    assert caught.value.provider_usage["provider_request_id"] == "deepinfra-test-1"
    assert caught.value.provider_usage["total_tokens"] == 19


def test_from_env_uses_only_deepinfra_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DEEPINFRA_API_KEY", "direct-secret")
    client = DeepInfraChatCompletionsClient.from_env(model=GEMMA_4_31B_MODEL)
    assert client is not None
    assert client.api_key == "direct-secret"
    assert client._base_url == DEEPINFRA_ENDPOINT


def test_direct_client_rejects_non_deepinfra_base_url():
    with pytest.raises(ValueError, match="deepinfra_base_url_unsupported"):
        DeepInfraChatCompletionsClient(
            api_key="secret",
            model=DEEPSEEK_0731_MODEL,
            base_url="https://openrouter.ai/api/v1",
        )


@pytest.mark.parametrize("profile", ["headline_rank_v1", "headline_editor_v1", "headline_critic_v1"])
def test_headline_profile_pins_priority_json_and_no_reasoning(profile):
    client = DeepInfraChatCompletionsClient(
        api_key="secret", model=DEEPSEEK_0731_MODEL, request_profile=profile,
    )

    request = client.build_request(max_tokens=800, messages=[{"role": "user", "content": "packet"}])

    assert request["model"] == DEEPSEEK_0731_MODEL
    assert request["service_tier"] == "priority"
    assert request["response_format"] == {"type": "json_object"}
    assert request["reasoning_effort"] == "none"
    with pytest.raises(DeepInfraPermanentError, match="profile_mismatch"):
        client.build_request(max_tokens=800, messages=[], reasoning_effort="low")
    with pytest.raises(DeepInfraPermanentError, match="unsupported_option"):
        client.build_request(max_tokens=800, messages=[], provider={"only": ["elsewhere"]})


def test_headline_profile_rejects_tier_and_usage_mismatch():
    response = _response(DEEPSEEK_0731_MODEL, "headline")
    response["service_tier"] = "standard"
    client = DeepInfraChatCompletionsClient(
        api_key="secret", model=DEEPSEEK_0731_MODEL,
        request_profile="headline_editor_v1",
        transport=lambda _request, _timeout: response,
    )
    with pytest.raises(DeepInfraPermanentError, match="service_tier_mismatch"):
        client.messages_create_text(max_tokens=800, messages=[])

    response["service_tier"] = "priority"
    response["usage"]["completion_tokens_details"]["reasoning_tokens"] = 0
    response["usage"]["estimated_cost"] = None
    with pytest.raises(DeepInfraPermanentError, match="usage_invalid"):
        client.messages_create_text(max_tokens=800, messages=[])

    response["usage"]["estimated_cost"] = 0.001
    result = client.messages_create_text(max_tokens=800, messages=[])
    assert result.provider_usage["service_tier"] == "priority"
    assert result.provider_usage["cost_usd"] == 0.001
