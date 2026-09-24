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
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
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
    **{
        profile: {
            "temperature": 0.2,
            "top_p": 0.95,
            "seed": 42,
            "reasoning_effort": "none",
            "service_tier": "priority",
            "response_format": {"type": "json_object"},
        }
        for profile in ("headline_rank_v1", "headline_editor_v1", "headline_critic_v1")
    },
}


def _closed_object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_REF_SCHEMA = _closed_object({
    "kind": {"type": "string", "enum": ["fact", "evidence", "corpus_signal"]},
    "id": {"type": "string"},
})
_PROPOSITION_SCHEMA = _closed_object({
    "proposition_id": {"type": "string"},
    "output_section": {"type": "string", "enum": ["headline", "secondary"]},
    "claim_en": {"type": "string"},
    "claim_zh_cn": {"type": "string"},
    "claim_ja": {"type": "string"},
    "claim_type": {"type": "string", "enum": ["content_summary", "event", "mix", "quantity", "quote", "sentiment"]},
    "fact_ids": {"type": "array", "items": {"type": "string"}},
    "evidence_ids": {"type": "array", "items": {"type": "string"}},
})
_EVENT_SCHEMA = _closed_object({
    "event_id": {"type": "string"},
    "label_en": {"type": "string"},
    "label_zh_cn": {"type": "string"},
    "label_ja": {"type": "string"},
    "occurred_at": {"type": ["string", "null"]},
    "support_kind": {"type": "string", "enum": ["first_party", "independent_discussion", "first_party_plus_discussion"]},
    "evidence_ids": {"type": "array", "items": {"type": "string"}},
    "proposition_ids": {"type": "array", "items": {"type": "string"}},
})
_NARRATIVE_SCHEMA = _closed_object({
    "brand_key": {"type": "string"},
    "headline_en": {"type": "string"},
    "headline_zh_cn": {"type": "string"},
    "headline_ja": {"type": "string"},
    "secondary_en": {"type": "string"},
    "secondary_zh_cn": {"type": "string"},
    "secondary_ja": {"type": "string"},
    "narrative_kind": {"type": "string", "enum": ["event_led", "content_shift", "mix_shift", "quiet_context"]},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "headline_proposition_ids": {"type": "array", "items": {"type": "string"}},
    "secondary_proposition_ids": {"type": "array", "items": {"type": "string"}},
    "propositions": {"type": "array", "items": _PROPOSITION_SCHEMA},
    "events": {"type": "array", "items": _EVENT_SCHEMA},
})
_HEADLINE_SCHEMAS = {
    "rank": _closed_object({
        "rank_response_schema_version": {"type": "integer", "enum": [1]},
        "packet_hash": {"type": "string"},
        "batch_key": {"type": "string"},
        "ordered_brands": {"type": "array", "items": _closed_object({
            "brand_key": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "reason_refs": {"type": "array", "items": _REF_SCHEMA},
        })},
    }),
    "editor": _closed_object({
        "editor_response_schema_version": {"type": "integer", "enum": [2]},
        "packet_hash": {"type": "string"},
        "batch_key": {"type": "string"},
        "brands": {"type": "array", "items": _NARRATIVE_SCHEMA},
    }),
    "critic": _closed_object({
        "critic_response_schema_version": {"type": "integer", "enum": [2]},
        "packet_hash": {"type": "string"},
        "batch_key": {"type": "string"},
        "decisions": {"type": "array", "items": _closed_object({
            "brand_key": {"type": "string"},
            "decision": {"type": "string", "enum": ["approve", "repair", "hold"]},
            "narrative": {"anyOf": [_NARRATIVE_SCHEMA, {"type": "null"}]},
            "hold_code": {"type": ["string", "null"]},
        })},
    }),
}
for _headline_stage, _headline_schema in _HEADLINE_SCHEMAS.items():
    _PROFILES[f"headline_{_headline_stage}_v2"] = {
        "temperature": 0.2,
        "top_p": 0.95,
        "seed": 42,
        "reasoning_effort": "none",
        "service_tier": "priority",
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": f"headline_{_headline_stage}_v2",
                "strict": True,
                "schema": _headline_schema,
            },
        },
    }

# The finance contract binds every cited aggregate to its exact typed input.
# Existing profiles stay readable for historical receipts and regression cases.
_FINANCE_NARRATIVE_SCHEMA = deepcopy(_NARRATIVE_SCHEMA)
_FINANCE_PROPOSITION_SCHEMA = _FINANCE_NARRATIVE_SCHEMA["properties"]["propositions"]["items"]
_FINANCE_PROPOSITION_SCHEMA["properties"]["measurements"] = {
    "type": "array", "items": _closed_object({
        "fact_id": {"type": "string"}, "value": {"type": "string"},
        "unit": {"type": "string"}, "scope_ref": {"type": "string"},
    }),
}
_FINANCE_PROPOSITION_SCHEMA["required"].append("measurements")
for _headline_stage in ("editor", "critic"):
    _profile = deepcopy(_PROFILES[f"headline_{_headline_stage}_v2"])
    _schema = _profile["response_format"]["json_schema"]
    _schema["name"] = f"headline_{_headline_stage}_v3"
    _properties = _schema["schema"]["properties"]
    _properties[f"{_headline_stage}_response_schema_version"]["enum"] = [3]
    if _headline_stage == "editor":
        _properties["brands"]["items"] = _FINANCE_NARRATIVE_SCHEMA
    else:
        _properties["decisions"]["items"]["properties"]["narrative"]["anyOf"][0] = _FINANCE_NARRATIVE_SCHEMA
    _PROFILES[f"headline_{_headline_stage}_v3"] = _profile
    _bound = deepcopy(_profile)
    _bound["response_format"]["json_schema"]["name"] = f"headline_{_headline_stage}_v4"
    _PROFILES[f"headline_{_headline_stage}_v4"] = _bound


def _bound_headline_format(profile_name: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Constrain each brand's citations without changing the response contract.

    These choices are derived only from our closed input envelope. Always copy
    the template: a shared profile must never retain another request's IDs.
    """
    try:
        content = messages[-1]["content"]
        if not isinstance(content, str):
            raise TypeError("bound request content")
        encoded = (content.split("request_envelope=", 1)[1] if profile_name == "headline_editor_v4"
                   else content.split("\n", 1)[1])
        envelope = json.loads(encoded)
        dossiers = ([bundle["dossier"] for bundle in envelope["review_bundles"]]
                    if "review_bundles" in envelope else envelope["analysis_packet"]["dossiers"])
        if not 1 <= len(dossiers) <= 5:
            raise ValueError("bound brand count")
        result = deepcopy(_PROFILES[profile_name]["response_format"])
        schema = result["json_schema"]["schema"]
        for key in ("packet_hash", "batch_key"):
            schema["properties"][key]["enum"] = [envelope[key]]
        narratives = []
        for dossier in dossiers:
            narrative = deepcopy(_FINANCE_NARRATIVE_SCHEMA)
            props = narrative["properties"]
            props["brand_key"]["enum"] = [dossier["brand_key"]]
            proposition = props["propositions"]["items"]["properties"]
            fact_ids = [fact["fact_id"] for fact in dossier.get("facts", [])]
            evidence_ids = [item["evidence_id"] for item in dossier.get("evidence", [])]
            for target, ids in ((proposition["fact_ids"], fact_ids),
                                (proposition["evidence_ids"], evidence_ids),
                                (props["events"]["items"]["properties"]["evidence_ids"], evidence_ids)):
                if ids:
                    target["items"]["enum"] = ids
                else:
                    target["maxItems"] = 0
            bindings = [_closed_object({key: {"type": "string", "enum": [str(fact[key])]}
                                       for key in ("fact_id", "value", "unit", "scope_ref")})
                        for fact in dossier.get("facts", [])]
            if bindings:
                proposition["measurements"]["items"] = {"anyOf": bindings}
            else:
                proposition["measurements"]["maxItems"] = 0
            # Emit citations and scoped values before prose. The model then
            # composes from selected evidence rather than justifying a headline
            # it already wrote. Key order changes no stored response fields.
            proposition_schema = props["propositions"]["items"]
            proposition_schema["properties"] = {
                key: proposition[key] for key in (
                    "proposition_id", "output_section", "claim_type",
                    "evidence_ids", "fact_ids", "measurements",
                    "claim_en", "claim_zh_cn", "claim_ja",
                )
            }
            proposition_schema["required"] = list(proposition_schema["properties"])
            narrative["properties"] = {
                key: props[key] for key in (
                    "brand_key", "propositions", "headline_proposition_ids",
                    "secondary_proposition_ids", "headline_en", "headline_zh_cn",
                    "headline_ja", "secondary_en", "secondary_zh_cn", "secondary_ja",
                    "narrative_kind", "confidence", "events",
                )
            }
            narrative["required"] = list(narrative["properties"])
            narratives.append(narrative)
        if profile_name == "headline_editor_v4":
            array = schema["properties"]["brands"]
            array["items"] = {"anyOf": narratives}
        else:
            array = schema["properties"]["decisions"]
            decisions = []
            for narrative in narratives:
                decision = deepcopy(array["items"])
                decision["properties"]["brand_key"] = narrative["properties"]["brand_key"]
                decision["properties"]["narrative"]["anyOf"] = [narrative, {"type": "null"}]
                decisions.append(decision)
            array["items"] = {"anyOf": decisions}
        array["minItems"] = array["maxItems"] = len(dossiers)
        return result
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise DeepInfraPermanentError("deepinfra_headline_schema_binding_invalid") from exc


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
        if self.request_profile and self.request_profile.startswith("headline_") and self.model != DEEPSEEK_0731_MODEL:
            raise ValueError("deepinfra_headline_model_mismatch")

    @property
    def _base_url(self) -> str:
        return self._endpoint_url()

    def _endpoint_url(self) -> str:
        value = self.base_url.rstrip("/")
        return value if value.endswith("/chat/completions") else value + "/chat/completions"

    @property
    def request_identity(self) -> str:
        settings = _PROFILES.get(self.request_profile or "", {})
        material = f"{self.model}|DeepInfra|direct|{self.request_profile}|{json.dumps(settings, sort_keys=True)}"
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
        if (
            self.request_profile
            and self.request_profile.startswith("headline_")
            and set(_ignored) - {"timeout"}
        ):
            raise DeepInfraPermanentError("deepinfra_headline_unsupported_option")
        for name, value in (("temperature", temperature), ("top_p", top_p), ("seed", seed), ("reasoning_effort", reasoning_effort)):
            selected = profile.get(name, value)
            if name in profile and value is not None and value != profile[name]:
                raise DeepInfraPermanentError("deepinfra_request_profile_mismatch")
            if selected is not None:
                request[name] = selected
        if self.request_profile and self.request_profile.startswith("headline_"):
            request["service_tier"] = profile["service_tier"]
            request["response_format"] = (
                _bound_headline_format(self.request_profile, messages)
                if self.request_profile in {"headline_editor_v4", "headline_critic_v4"}
                else profile["response_format"]
            )
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
        if self.request_profile and self.request_profile.startswith("headline_"):
            if decoded.get("service_tier") != "priority":
                raise DeepInfraPermanentError("deepinfra_service_tier_mismatch", provider_usage=usage)
            raw = decoded.get("usage")
            if not isinstance(raw, Mapping) or not isinstance(decoded.get("id"), str) or not decoded["id"]:
                raise DeepInfraPermanentError("deepinfra_headline_usage_invalid", provider_usage=usage)
            if any(not isinstance(raw.get(key), int) or isinstance(raw.get(key), bool) or raw[key] < 0 for key in ("prompt_tokens", "completion_tokens")):
                raise DeepInfraPermanentError("deepinfra_headline_usage_invalid", provider_usage=usage)
            try:
                cost = Decimal(str(raw.get("estimated_cost")))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise DeepInfraPermanentError("deepinfra_headline_usage_invalid", provider_usage=usage) from exc
            if not cost.is_finite() or cost < 0 or usage["reasoning_tokens"] not in (0, None):
                raise DeepInfraPermanentError("deepinfra_headline_usage_invalid", provider_usage=usage)
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
