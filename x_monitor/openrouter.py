"""Narrow OpenRouter chat-completions adapter for the U18 classifier lane.

It deliberately has no Anthropic-compatible fallback.  The configured provider
and data handling policy are part of every request identity.
"""

from __future__ import annotations

import http.client
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .provider_telemetry import ProviderResponse


class OpenRouterRetryableError(RuntimeError):
    """A transport failure for which the identical request may be retried."""


class OpenRouterPermanentError(RuntimeError):
    """A policy, route, or response failure that must not trigger repair."""


@dataclass(frozen=True)
class OpenRouterChatCompletionsClient:
    api_key: str
    model: str
    provider: str
    data_collection: str = "deny"
    max_input_price: float | None = None
    max_output_price: float | None = None
    response_provider: str | None = None
    response_model: str | None = None
    zdr: bool = False
    endpoint_tag: str | None = None
    reasoning_enabled: bool | None = None
    quantizations: list[str] | None = None
    base_url: str = "https://openrouter.ai/api/v1"

    @property
    def _base_url(self) -> str:
        """Expose the endpoint identity to the shared telemetry normalizer."""
        return self.base_url

    @property
    def request_identity(self) -> str:
        """Non-secret identity of the pinned route and data policy."""
        value = f"{self.model}|{self.provider}|{self.data_collection}|{self.max_input_price}|{self.max_output_price}|{self.response_provider}|{self.response_model}|{self.zdr}|{self.endpoint_tag}|{self.reasoning_enabled}|{tuple(self.quantizations or ())}"
        return "openrouter:" + hashlib.sha256(value.encode()).hexdigest()[:16]

    @classmethod
    def from_config(cls, **kwargs: Any) -> OpenRouterChatCompletionsClient | None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            return None
        return cls(api_key=api_key, **kwargs)

    def build_request(self, *, model: str | None = None, max_tokens: int,
                      messages: list[dict[str, Any]], system: str | None = None,
                      temperature: float | None = None, **_ignored: Any) -> dict[str, Any]:
        if self.data_collection not in {"allow", "deny"}:
            raise OpenRouterPermanentError("openrouter_data_collection_invalid")
        if model is not None and model != self.model:
            raise OpenRouterPermanentError("openrouter_model_mismatch")
        request_messages = []
        if system is not None:
            request_messages.append({"role": "system", "content": system})
        request_messages.extend(messages)
        provider: dict[str, Any] = {
            "only": [self.provider],
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": self.data_collection,
            "zdr": self.zdr,
        }
        prices = {
            key: value
            for key, value in (("prompt", self.max_input_price), ("completion", self.max_output_price))
            if value is not None
        }
        if prices:
            # OpenRouter's Chat Completions schema scopes price routing to
            # the provider object, rather than the request root.
            provider["max_price"] = prices
        if self.quantizations is not None:
            if not self.quantizations or any(not isinstance(value, str) or not value for value in self.quantizations):
                raise OpenRouterPermanentError("openrouter_quantizations_invalid")
            provider["quantizations"] = list(self.quantizations)
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": request_messages,
            "response_format": {"type": "json_object"},
            "provider": provider,
        }
        if temperature is not None:
            request["temperature"] = temperature
        if self.reasoning_enabled is not None:
            request["reasoning"] = {"enabled": self.reasoning_enabled}
        return request

    def messages_create(self, **kwargs: Any) -> ProviderResponse:
        request = self.build_request(**kwargs)
        parsed = urlparse(self.base_url.rstrip("/") + "/chat/completions")
        conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                           timeout=kwargs.get("timeout", 60))
        try:
            try:
                conn.request(
                    "POST", parsed.path,
                    body=json.dumps(request).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        # Official response-routing metadata lets us attest
                        # the provider selected for the pinned evaluation.
                        "X-OpenRouter-Metadata": "enabled",
                    },
                )
                response = conn.getresponse()
                body = response.read()
            except (TimeoutError, OSError, http.client.HTTPException) as exc:
                raise OpenRouterRetryableError("openrouter_transport_failure") from exc
        finally:
            conn.close()
        if not 200 <= response.status < 300:
            exc_type = OpenRouterRetryableError if response.status == 429 or response.status >= 500 else OpenRouterPermanentError
            raise exc_type(f"openrouter_http_status_{response.status}")
        try:
            decoded = json.loads(body)
        except (TypeError, ValueError) as exc:
            raise OpenRouterPermanentError("openrouter_response_json_invalid") from exc
        if not isinstance(decoded, dict):
            raise OpenRouterPermanentError("openrouter_response_shape_invalid")
        actual_model = decoded.get("model")
        routing = (
            decoded.get("openrouter_metadata")
            if isinstance(decoded.get("openrouter_metadata"), dict)
            else {}
        )
        endpoints = (
            routing.get("endpoints")
            if isinstance(routing.get("endpoints"), dict)
            else {}
        )
        available = endpoints.get("available") if isinstance(endpoints.get("available"), list) else []
        selected = [
            item for item in available
            if isinstance(item, dict) and item.get("selected") is True
        ]
        actual_provider = selected[0].get("provider") if len(selected) == 1 else None
        routed_model = selected[0].get("model") if len(selected) == 1 else None
        allowed_models = {self.model, *(value for value in (self.response_model,) if value)}
        allowed_providers = {self.provider, *(value for value in (self.response_provider,) if value)}
        # Provider-only routing is a pinned evaluation route, so a missing
        # response identity cannot silently masquerade as the requested model.
        if not isinstance(actual_model, str) or actual_model not in allowed_models:
            raise OpenRouterPermanentError("openrouter_response_model_mismatch")
        if not isinstance(actual_provider, str) or actual_provider not in allowed_providers:
            raise OpenRouterPermanentError("openrouter_response_provider_mismatch")
        if routed_model is not None and routed_model not in allowed_models:
            raise OpenRouterPermanentError("openrouter_response_model_mismatch")
        choices = decoded.get("choices") or []
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        if not isinstance(content, str):
            raise OpenRouterPermanentError("openrouter_response_content_missing")
        try:
            parsed_content = json.loads(content)
        except (TypeError, ValueError) as exc:
            raise OpenRouterPermanentError("openrouter_response_content_invalid") from exc
        if not isinstance(parsed_content, dict):
            raise OpenRouterPermanentError("openrouter_response_content_shape_invalid")
        usage = decoded.get("usage") if isinstance(decoded.get("usage"), dict) else {}
        prompt_details = (
            usage.get("prompt_tokens_details")
            if isinstance(usage.get("prompt_tokens_details"), dict)
            else {}
        )
        completion_details = (
            usage.get("completion_tokens_details")
            if isinstance(usage.get("completion_tokens_details"), dict)
            else {}
        )
        # Keep normalized provider/request identity alongside usage for existing telemetry.
        usage = {
            "input_tokens": usage.get("prompt_tokens", usage.get("input_tokens")),
            "output_tokens": usage.get("completion_tokens", usage.get("output_tokens")),
            "cache_read_input_tokens": prompt_details.get(
                "cached_tokens", usage.get("cached_tokens", usage.get("cache_read_tokens"))
            ),
            "reasoning_tokens": completion_details.get(
                "reasoning_tokens", usage.get("reasoning_tokens")
            ),
            "total_tokens": usage.get("total_tokens"),
            "cost_usd": usage.get("cost"),
            "provider_request_id": decoded.get("id"),
            "provider": actual_provider,
            "model": actual_model or self.model,
            "request_provider": actual_provider or self.provider,
            "request_identity": self.request_identity,
            "data_collection": self.data_collection,
        }
        return ProviderResponse(parsed_content, usage=usage)
