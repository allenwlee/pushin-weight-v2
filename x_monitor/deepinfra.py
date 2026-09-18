"""Direct DeepInfra OpenAI-compatible chat-completions transport.

This adapter is deliberately independent of the application configuration.  A
factory can supply the API key and model later; the transport owns the request
envelope, response validation, and provider usage receipt so those details do
not get silently changed by a caller or an OpenRouter-specific option.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .provider_telemetry import ProviderResponse, ProviderTextResponse

DEEPINFRA_ENDPOINT = "https://api.deepinfra.com/v1/openai/chat/completions"
DEEPSEEK_0731_MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
GEMMA_4_31B_MODEL = "google/gemma-4-31B-it-turbo"
SUPPORTED_MODELS = frozenset({DEEPSEEK_0731_MODEL, GEMMA_4_31B_MODEL})


class DeepInfraRetryableError(RuntimeError):
    """A transport or provider capacity failure that may be retried."""


class DeepInfraPermanentError(RuntimeError):
    """A request, route, or response failure that must fail closed."""

    def __init__(self, code: str, *, provider_usage: dict[str, Any] | None = None):
        super().__init__(code)
        self.provider_usage = provider_usage


_PROFILES: dict[str, dict[str, Any]] = {
    # These are the settings used by the direct-provider acceptance runs.  No
    # response_format is added: both routes use application-side validation.
    "deepseek_0731": {
        "temperature": 1.0,
        "top_p": 1.0,
        "seed": 42,
        "reasoning_effort": "none",
    },
    "gemma4_31b": {
        "temperature": 0.2,
        "reasoning_effort": "none",
    },
    # The task lanes use distinct prompt/parser profiles while sharing the
    # same direct Gemma transport settings.
    "gemma4_raw_text": {
        "temperature": 0.2,
        "reasoning_effort": "none",
    },
    "gemma4_tagged": {
        "temperature": 0.2,
        "reasoning_effort": "none",
    },
    "gemma4_translation_v1": {
        # The qualifying direct translation run omitted samplers and
        # reasoning controls; keep DeepInfra/Gemma defaults for this lane.
    },
}


def _json_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("deepinfra_response_content_duplicate_key")
        value[key] = item
    return value


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return content
    match = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", stripped, re.DOTALL | re.IGNORECASE)
    if match is None:
        raise ValueError("deepinfra_response_content_fence_invalid")
    return match.group(1)


def _usage(decoded: Mapping[str, Any], *, model: str, request_identity: str) -> dict[str, Any]:
    raw = decoded.get("usage") if isinstance(decoded.get("usage"), Mapping) else {}
    prompt_details = raw.get("prompt_tokens_details") if isinstance(raw.get("prompt_tokens_details"), Mapping) else {}
    completion_details = raw.get("completion_tokens_details") if isinstance(raw.get("completion_tokens_details"), Mapping) else {}
    return {
        "input_tokens": raw.get("prompt_tokens", raw.get("input_tokens")),
        "output_tokens": raw.get("completion_tokens", raw.get("output_tokens")),
        "cache_read_input_tokens": prompt_details.get("cached_tokens", raw.get("cached_tokens", raw.get("cache_read_tokens"))),
        "cache_creation_input_tokens": prompt_details.get("cache_creation_tokens", raw.get("cache_creation_tokens")),
        "reasoning_tokens": completion_details.get("reasoning_tokens", raw.get("reasoning_tokens")),
        "total_tokens": raw.get("total_tokens"),
        "cost_usd": raw.get("estimated_cost", raw.get("cost")),
        "provider_request_id": decoded.get("id"),
        "provider": "DeepInfra",
        "model": decoded.get("model") or model,
        "selected_endpoint": "direct",
        "request_provider": "DeepInfra",
        "request_identity": request_identity,
        "data_collection": "deepinfra-direct",
        "service_tier": decoded.get("service_tier") or "standard",
    }


@dataclass(frozen=True)
class DeepInfraChatCompletionsClient:
    """Small, strict client for the two approved direct DeepInfra models."""

    api_key: str = field(repr=False)
    model: str
    request_profile: str | None = None
    base_url: str = DEEPINFRA_ENDPOINT
    transport: Callable[[dict[str, Any], Any], dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("deepinfra_api_key_missing")
        if self.model not in SUPPORTED_MODELS:
            raise ValueError("deepinfra_model_unsupported")
        if self.base_url.rstrip("/") not in {
            "https://api.deepinfra.com/v1/openai",
            DEEPINFRA_ENDPOINT,
        }:
            raise ValueError("deepinfra_base_url_unsupported")
        if self.request_profile is not None and self.request_profile not in _PROFILES:
            raise ValueError("deepinfra_request_profile_unsupported")

    @property
    def _base_url(self) -> str:
        return self._endpoint_url()

    def _endpoint_url(self) -> str:
        value = self.base_url.rstrip("/")
        return value if value.endswith("/chat/completions") else value + "/chat/completions"

    @property
    def request_identity(self) -> str:
        settings = _PROFILES.get(self.request_profile or "", {})
        material = f"{self.model}|DeepInfra|direct|{self.request_profile}|{sorted(settings.items())}"
        return f"deepinfra:{self.request_profile or 'default'}:{hashlib.sha256(material.encode()).hexdigest()[:16]}"

    @classmethod
    def from_env(cls, *, model: str, request_profile: str | None = None, **kwargs: Any) -> DeepInfraChatCompletionsClient | None:
        api_key = os.environ.get("DEEPINFRA_API_KEY")
        if not api_key:
            return None
        return cls(api_key=api_key, model=model, request_profile=request_profile, **kwargs)

    @classmethod
    def from_config(cls, *, model: str, base_url: str | None = None, request_profile: str | None = None, **kwargs: Any) -> DeepInfraChatCompletionsClient | None:
        """Build only from the direct-provider credential.

        ``base_url`` is accepted so the config factory can pass its common
        provider arguments, but the adapter keeps the direct DeepInfra
        endpoint as the default.  In particular, it never falls back to an
        OpenRouter or Anthropic credential.
        """
        return cls.from_env(
            model=model,
            request_profile=request_profile,
            **({"base_url": base_url} if base_url is not None else {}),
            **kwargs,
        )

    def build_request(
        self,
        *,
        model: str | None = None,
        max_tokens: int,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        seed: int | None = None,
        reasoning_effort: str | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        if model is not None and model != self.model:
            raise DeepInfraPermanentError("deepinfra_model_mismatch")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
            raise DeepInfraPermanentError("deepinfra_max_tokens_invalid")
        if not isinstance(messages, list) or any(not isinstance(item, dict) for item in messages):
            raise DeepInfraPermanentError("deepinfra_messages_invalid")
        request_messages: list[dict[str, Any]] = []
        if system is not None:
            request_messages.append({"role": "system", "content": system})
        request_messages.extend(messages)
        request: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens, "messages": request_messages}
        profile = _PROFILES.get(self.request_profile or "", {})
        for name, value in (("temperature", temperature), ("top_p", top_p), ("seed", seed), ("reasoning_effort", reasoning_effort)):
            selected = profile.get(name, value)
            if name in profile and value is not None and value != profile[name]:
                raise DeepInfraPermanentError("deepinfra_request_profile_mismatch")
            if selected is not None:
                request[name] = selected
        # Deliberately omit response_format, provider, service_tier, thinking,
        # reasoning, and OpenRouter routing controls from the direct envelope.
        return request

    def _send_request(self, request: dict[str, Any], *, timeout: Any) -> dict[str, Any]:
        if self.transport is not None:
            try:
                decoded = self.transport(request, timeout)
                if not isinstance(decoded, dict):
                    raise DeepInfraPermanentError("deepinfra_response_shape_invalid")
                return decoded
            except DeepInfraRetryableError:
                raise
            except DeepInfraPermanentError:
                raise
            except (TimeoutError, OSError) as exc:
                raise DeepInfraRetryableError("deepinfra_transport_failure") from exc
        parsed = urlparse(self._endpoint_url())
        conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=timeout)
        try:
            try:
                conn.request(
                    "POST",
                    parsed.path or "/v1/openai/chat/completions",
                    body=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                )
                response = conn.getresponse()
                body = response.read()
            except (TimeoutError, OSError, http.client.HTTPException) as exc:
                raise DeepInfraRetryableError("deepinfra_transport_failure") from exc
        finally:
            conn.close()
        if not 200 <= response.status < 300:
            exc_type = DeepInfraRetryableError if response.status == 429 or response.status >= 500 else DeepInfraPermanentError
            raise exc_type(f"deepinfra_http_status_{response.status}")
        try:
            decoded = json.loads(body)
        except (TypeError, ValueError) as exc:
            raise DeepInfraPermanentError("deepinfra_response_json_invalid") from exc
        if not isinstance(decoded, dict):
            raise DeepInfraPermanentError("deepinfra_response_shape_invalid")
        return decoded

    def _validated_response(self, decoded: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if not isinstance(decoded, dict):
            raise DeepInfraPermanentError("deepinfra_response_shape_invalid")
        usage = _usage(decoded, model=self.model, request_identity=self.request_identity)
        if decoded.get("model") != self.model:
            raise DeepInfraPermanentError("deepinfra_response_model_mismatch", provider_usage=usage)
        choices = decoded.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise DeepInfraPermanentError("deepinfra_response_choices_invalid", provider_usage=usage)
        choice = choices[0]
        if choice.get("finish_reason") != "stop":
            raise DeepInfraPermanentError("deepinfra_response_incomplete", provider_usage=usage)
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise DeepInfraPermanentError("deepinfra_response_content_missing", provider_usage=usage)
        return usage, content

    def messages_create(self, **kwargs: Any) -> ProviderResponse:
        decoded = self._send_request(self.build_request(**kwargs), timeout=kwargs.get("timeout", 60))
        usage, content = self._validated_response(decoded)
        try:
            parsed = json.loads(_strip_json_fence(content), object_pairs_hook=_json_without_duplicate_keys)
        except (TypeError, ValueError) as exc:
            raise DeepInfraPermanentError("deepinfra_response_content_invalid", provider_usage=usage) from exc
        if not isinstance(parsed, dict):
            raise DeepInfraPermanentError("deepinfra_response_content_shape_invalid", provider_usage=usage)
        return ProviderResponse(parsed, usage=usage)

    def messages_create_text(self, **kwargs: Any) -> ProviderTextResponse:
        decoded = self._send_request(self.build_request(**kwargs), timeout=kwargs.get("timeout", 60))
        usage, content = self._validated_response(decoded)
        return ProviderTextResponse(text=content, provider_usage=usage)
