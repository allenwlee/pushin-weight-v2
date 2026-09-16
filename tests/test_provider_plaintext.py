"""Network-edge contracts for literal provider text responses."""

from __future__ import annotations

import json

import pytest


class _Response:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


def _openrouter_payload(*, content: object, finish_reason: str = "stop", provider: str = "Provider A", model: str = "vendor/model") -> dict:
    return {
        "id": "req-plain-1",
        "model": model,
        "openrouter_metadata": {"endpoints": {"available": [{
            "model": model,
            "provider": provider,
            "selected": True,
        }]}},
        "choices": [{
            "finish_reason": finish_reason,
            "message": {"content": content},
        }],
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 4,
            "total_tokens": 12,
            "cost": 0.003,
        },
    }


def _fake_openrouter_connection(monkeypatch, payload: object, *, status: int = 200):
    from x_monitor import openrouter

    sent: list[dict] = []

    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, _method, _path, body=None, headers=None):
            sent.append(json.loads(body))

        def getresponse(self):
            return _Response(status, payload)

        def close(self):
            pass

    monkeypatch.setattr(openrouter.http.client, "HTTPSConnection", Connection)
    return sent


def _openrouter_client():
    from x_monitor.openrouter import OpenRouterChatCompletionsClient

    return OpenRouterChatCompletionsClient(
        api_key="test-key", model="vendor/model", provider="Provider A"
    )


def test_openrouter_raw_text_preserves_literal_multiline_json_like_source_and_usage(monkeypatch):
    from x_monitor.provider_telemetry import ProviderTextResponse

    literal = '```json\n{"literal": "source, not a response envelope"}\n```\n"quoted"\n'
    sent = _fake_openrouter_connection(
        monkeypatch, _openrouter_payload(content=literal)
    )

    response = _openrouter_client().messages_create_text(
        model="vendor/model",
        max_tokens=24,
        messages=[{"role": "user", "content": "translate this"}],
    )

    assert isinstance(response, ProviderTextResponse)
    assert response.text == literal
    assert response.provider_usage["cost_usd"] == 0.003
    assert "response_format" not in sent[0]


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (_openrouter_payload(content="partial", finish_reason="length"), "incomplete"),
        (_openrouter_payload(content=""), "content_missing"),
        (_openrouter_payload(content=None), "content_missing"),
        (_openrouter_payload(content="translation", provider="other"), "provider_mismatch"),
        (_openrouter_payload(content="translation", model="other/model"), "model_mismatch"),
    ],
)
def test_openrouter_raw_text_rejects_invalid_provider_responses_with_usage(monkeypatch, payload, error):
    from x_monitor.openrouter import OpenRouterPermanentError

    _fake_openrouter_connection(monkeypatch, payload)

    with pytest.raises(OpenRouterPermanentError, match=error) as caught:
        _openrouter_client().messages_create_text(
            model="vendor/model", max_tokens=24, messages=[]
        )

    assert caught.value.provider_usage["provider_request_id"] == "req-plain-1"
    assert caught.value.provider_usage["total_tokens"] == 12


def test_openrouter_raw_text_rejects_rate_and_transport_failures(monkeypatch):
    from x_monitor import openrouter

    _fake_openrouter_connection(monkeypatch, {"error": "limited"}, status=429)
    with pytest.raises(openrouter.OpenRouterRetryableError, match="status_429"):
        _openrouter_client().messages_create_text(
            model="vendor/model", max_tokens=24, messages=[]
        )

    class BrokenConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            raise OSError("offline")

        def close(self):
            pass

    monkeypatch.setattr(openrouter.http.client, "HTTPSConnection", BrokenConnection)
    with pytest.raises(openrouter.OpenRouterRetryableError, match="transport_failure"):
        _openrouter_client().messages_create_text(
            model="vendor/model", max_tokens=24, messages=[]
        )


def test_openrouter_json_call_remains_strict_and_requests_json_mode(monkeypatch):
    from x_monitor.openrouter import OpenRouterPermanentError

    sent = _fake_openrouter_connection(
        monkeypatch, _openrouter_payload(content='{"broken":')
    )

    with pytest.raises(OpenRouterPermanentError, match="content_invalid"):
        _openrouter_client().messages_create(
            model="vendor/model", max_tokens=24, messages=[]
        )

    assert sent[0]["response_format"] == {"type": "json_object"}


def _fake_anthropic_connection(monkeypatch, payload: object, *, status: int = 200):
    import http.client

    sent: list[dict] = []

    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, _method, _path, body=None, headers=None):
            sent.append(json.loads(body))

        def getresponse(self):
            return _Response(status, payload)

        def close(self):
            pass

    monkeypatch.setattr(http.client, "HTTPSConnection", Connection)
    return sent


def _anthropic_payload(*, content: object, stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg-plain-1",
        "model": "provider-model",
        "stop_reason": stop_reason,
        "content": [{"type": "text", "text": content}],
        "usage": {"input_tokens": 6, "output_tokens": 3, "total_tokens": 9},
    }


def _anthropic_client():
    from x_monitor.attribution import AnthropicClaudeClient

    return AnthropicClaudeClient(
        api_key="test-key", base_url="https://provider.invalid/anthropic"
    )


def test_anthropic_raw_text_preserves_literal_formatting_and_usage(monkeypatch):
    literal = '  ```\n"literal translation"\n```\n'
    sent = _fake_anthropic_connection(
        monkeypatch, _anthropic_payload(content=literal)
    )

    response = _anthropic_client().messages_create_text(
        model="provider-model", max_tokens=24, messages=[]
    )

    assert response.text == literal
    assert response.provider_usage["total_tokens"] == 9
    assert sent[0]["model"] == "provider-model"


def test_anthropic_raw_text_rejects_rate_and_transport_failures(monkeypatch):
    from x_monitor import attribution

    _fake_anthropic_connection(monkeypatch, {"error": "limited"}, status=429)
    with pytest.raises(
        attribution.AnthropicCompatibleRetryableError, match="status_429"
    ):
        _anthropic_client().messages_create_text(
            model="provider-model", max_tokens=24, messages=[]
        )

    import http.client

    class BrokenConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            raise OSError("offline")

        def close(self):
            pass

    monkeypatch.setattr(http.client, "HTTPSConnection", BrokenConnection)
    with pytest.raises(
        attribution.AnthropicCompatibleRetryableError, match="transport_failure"
    ):
        _anthropic_client().messages_create_text(
            model="provider-model", max_tokens=24, messages=[]
        )


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (_anthropic_payload(content="partial", stop_reason="max_tokens"), "incomplete"),
        (_anthropic_payload(content=""), "content_missing"),
        (_anthropic_payload(content=[]), "content_missing"),
    ],
)
def test_anthropic_raw_text_rejects_incomplete_or_empty_content_with_usage(monkeypatch, payload, error):
    from x_monitor.attribution import AnthropicCompatiblePermanentError

    _fake_anthropic_connection(monkeypatch, payload)

    with pytest.raises(AnthropicCompatiblePermanentError, match=error) as caught:
        _anthropic_client().messages_create_text(
            model="provider-model", max_tokens=24, messages=[]
        )

    assert caught.value.provider_usage["provider_request_id"] == "msg-plain-1"
    assert caught.value.provider_usage["total_tokens"] == 9
