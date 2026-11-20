"""One physical Jev request, using the shared bounded HTTP transport.

Retries and budgets belong to the existing classification caller. This client
preserves usage on invalid answers and never falls back to another provider.
"""

from __future__ import annotations

import http.client
import json
from dataclasses import dataclass, field
from decimal import Decimal

from x_monitor.deepinfra import DEEPSEEK_0731_MODEL
from x_monitor.provider_http import https_request
from x_monitor.provider_telemetry import ProviderResponse

MODEL = "jev-1.14.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
# Verified against https://docs.typesafe.ai/models on 2026-11-17 JST.
INPUT_PRICE_PER_MILLION = Decimal("0.042")
MAX_INPUT_TOKENS = 65_536


class JevRetryableError(RuntimeError):
    """A typed transport/capacity failure; the caller owns bounded retries."""


class JevPermanentError(RuntimeError):
    def __init__(self, code, *, provider_usage=None):
        self.provider_usage = provider_usage
        super().__init__(code)


def request_document(messages, *, model):
    if model != MODEL or not isinstance(messages, list) or len(messages) != 1:
        raise ValueError("jev_request_shape_invalid")
    message = messages[0]
    if not isinstance(message, dict) or message.get("role") != "user" or not isinstance(message.get("content"), str):
        raise ValueError("jev_request_shape_invalid")
    document = json.loads(message["content"])
    if (not isinstance(document, dict) or set(document) != {"model", "state", "questions"}
            or document["model"] != MODEL or not isinstance(document["questions"], dict) or not document["questions"]):
        raise ValueError("jev_request_shape_invalid")
    return document


@dataclass
class JevClassifierClient:
    api_key: str = field(repr=False)
    transport: object = field(default=None, repr=False)
    model: str = field(default=MODEL, init=False)
    _base_url: str = field(default=ENDPOINT, init=False)
    request_identity: str = field(default="typesafe:jev-1.14.0:direct", init=False)

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("typesafe_api_key_missing")

    def messages_create(self, *, messages, model=MODEL, timeout=90, **kwargs):
        try:
            request = request_document(messages, model=model)
        except (ValueError, TypeError) as exc:
            raise JevPermanentError("jev_request_shape_invalid") from exc
        try:
            if self.transport is not None:
                document = self.transport(request, timeout)
            else:
                status, body = https_request(ENDPOINT, self.api_key, request, timeout=timeout)
                if status != 200:
                    error = JevRetryableError if status == 429 or status >= 500 else JevPermanentError
                    raise error(f"jev_http_status_{status}")
                document = json.loads(body)
        except (TimeoutError, OSError, http.client.HTTPException) as exc:
            raise JevRetryableError("jev_transport_failure") from exc
        except ValueError as exc:
            raise JevPermanentError("jev_response_json_invalid") from exc
        if not isinstance(document, dict):
            raise JevPermanentError("jev_response_shape_invalid")
        raw_usage = document.get("usage")
        if not isinstance(raw_usage, dict) or any(type(raw_usage.get(k)) is not int or raw_usage[k] < 0 for k in ("input_tokens", "output_tokens")):
            raise JevPermanentError("jev_usage_missing_or_invalid")
        usage = {**raw_usage, "provider": "TypeSafe", "model": document.get("model"),
                 "request_identity": self.request_identity,
                 "cost_usd": float(Decimal(raw_usage["input_tokens"]) * INPUT_PRICE_PER_MILLION / 1_000_000)}
        if raw_usage["input_tokens"] > MAX_INPUT_TOKENS:
            raise JevPermanentError("jev_usage_exceeds_reserved_bound", provider_usage=usage)
        if document.get("model") != MODEL:
            raise JevPermanentError("jev_response_model_mismatch", provider_usage=usage)
        if not isinstance(document.get("answers"), dict):
            raise JevPermanentError("jev_answers_missing", provider_usage=usage)
        return ProviderResponse(document, usage=usage)


@dataclass
class CompressedClassifierClient:
    extraction: object = field(repr=False)
    classification: JevClassifierClient = field(repr=False)
    release_channels: tuple[str, ...] = ("api", "weights")
    request_profile: str = field(default="compressed8_pulse_v1", init=False)
    model: str = field(default=DEEPSEEK_0731_MODEL, init=False)
    request_identity: str = field(default="compressed8:deepinfra-0731+typesafe-1.14:pulse-v1", init=False)

    @property
    def _base_url(self):
        return self.extraction._base_url

    def messages_create(self, **kwargs):
        model = kwargs.get("model")
        if model == DEEPSEEK_0731_MODEL:
            return self.extraction.messages_create(**kwargs)
        if model == MODEL:
            return self.classification.messages_create(**kwargs)
        raise ValueError("compressed_classifier_model_mismatch")
