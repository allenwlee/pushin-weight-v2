"""Model-neutral JSON calls with explicit routing and conservative price reservations."""

import hashlib
import http.client
import json
import os
import re
from decimal import Decimal, InvalidOperation
from time import monotonic

from x_monitor.deepinfra import DeepInfraChatCompletionsClient, DeepInfraPermanentError
from x_monitor.provider_http import https_request

from .contracts import ProviderReplyError, digest
from .grounding import normalize_reply, restore_sources
from .persistence import call_once


def request_payload(route, request):
    images = request.get("images", [])
    if request.get("visual_essential") and not route.vision:
        raise ValueError("essential image requires vision route")
    content = request["user"]
    if images and route.vision:
        content = [{"type": "text", "text": content}] + [
            {"type": "image_url", "image_url": {"url": url}} for url in images
        ]
    body = {
        "model": route.model,
        "max_tokens": route.max_output_tokens,
        "messages": [
            {"role": "system", "content": request["system"]},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    if route.endpoint == "https://api.openai.com/v1/chat/completions":
        body["max_completion_tokens"] = body.pop("max_tokens")
        # Match the standard-rate reservation even if the project default changes.
        body["service_tier"] = "default"
    if route.request_profile:
        # Request construction is offline; this placeholder is never sent.
        client = DeepInfraChatCompletionsClient(
            api_key="request-construction-only",
            model=route.model,
            request_profile=route.request_profile,
        )
        return client.build_request(
            max_tokens=route.max_output_tokens,
            messages=body["messages"],
            reasoning_effort=route.reasoning,
            response_schema=request.get("response_schema"),
        )
    if route.reasoning:
        if "openrouter.ai" in route.endpoint:
            body["reasoning"] = {"effort": route.reasoning}
        else:
            body["reasoning_effort"] = route.reasoning
    if "openrouter.ai" in route.endpoint:
        body["provider"] = {
            "allow_fallbacks": False,
            "require_parameters": True,
            "max_price": {
                "prompt": route.input_usd_per_million,
                "completion": route.output_usd_per_million,
            },
        }
    return body


def response_diagnostics(decoded):
    """Keep bounded receipt fields, never model content or arbitrary error text."""
    usage = decoded.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    kept = {
        key: usage[key]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if type(usage.get(key)) is int and usage[key] >= 0
    }
    details = usage.get("completion_tokens_details")
    details = details if isinstance(details, dict) else {}
    reasoning = details.get("reasoning_tokens", usage.get("reasoning_tokens"))
    if type(reasoning) is int and reasoning >= 0:
        kept["reasoning_tokens"] = reasoning
    try:
        cost = Decimal(str(usage.get("estimated_cost")))
        if cost.is_finite() and 0 <= cost <= 1_000_000:
            kept["estimated_cost"] = str(cost)
    except (InvalidOperation, ValueError):
        pass
    result = {"usage": kept}
    if decoded.get("service_tier") in ("priority", "standard", "default", "flex"):
        result["service_tier"] = decoded["service_tier"]
    request_id = decoded.get("id")
    if isinstance(request_id, str) and re.fullmatch(
        r"[a-zA-Z0-9_.:-]{1,200}", request_id
    ):
        result["provider_request_id"] = request_id
    return result


def json_call(assessment, stage, route, request, cfg, *, transport=None):
    transport = transport or https_request
    body = request_payload(route, request)
    encoded = json.dumps(body, ensure_ascii=False).encode()
    schema_bytes = len(
        json.dumps(request.get("response_schema", {}), ensure_ascii=False).encode()
    )
    if schema_bytes > cfg.max_schema_bytes:
        raise ValueError("provider schema cap exceeded")
    if len(encoded) > cfg.max_packet_bytes + cfg.max_schema_bytes + 30000:
        raise ValueError("provider input cap exceeded")
    # UTF-8 byte count conservatively bounds textual tokens, plus framing and image reserve.
    input_bound = (
        len(encoded)
        + 1024
        + (
            len(request.get("images", [])) * route.image_token_ceiling
            if route.vision
            else 0
        )
    )
    ceiling = (
        Decimal(input_bound) * Decimal(str(route.input_usd_per_million))
        + Decimal(route.max_output_tokens) * Decimal(str(route.output_usd_per_million))
    ) / Decimal(1_000_000)
    key = os.environ.get(route.key_env, "")
    if not key:
        raise ValueError("configured provider credential missing")

    diagnostics = {
        "request_sha256": hashlib.sha256(encoded).hexdigest(),
        "request_profile": route.request_profile,
        "timeout_seconds": route.timeout_seconds,
    }

    def receive():
        try:
            status, raw = transport(
                route.endpoint, key, body, timeout=route.timeout_seconds
            )
        except ValueError as exc:
            raise ProviderReplyError("provider_transport_invalid", diagnostics) from exc
        diagnostics["http_status"] = status
        if not 200 <= status < 300:
            raise ProviderReplyError(f"provider_http_{status}", diagnostics)
        try:
            decoded = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ProviderReplyError("invalid_provider_json", diagnostics) from exc
        if not isinstance(decoded, dict):
            raise ProviderReplyError("malformed_provider_response", diagnostics)
        diagnostics.update(response_diagnostics(decoded))
        kept = diagnostics["usage"]
        diagnostics["model_matches_config"] = decoded.get("model") == route.model
        if decoded.get("model") != route.model:
            raise ProviderReplyError("served_model_mismatch", diagnostics)
        choices = decoded.get("choices", [])
        if (
            not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(choices[0], dict)
        ):
            raise ProviderReplyError("malformed_provider_response", diagnostics)
        reason = choices[0].get("finish_reason")
        diagnostics["finish_reason"] = (
            reason
            if reason in ("stop", "length", "content_filter", "tool_calls", "error")
            else "other"
        )
        if reason != "stop":
            raise ProviderReplyError("incomplete_model_response", diagnostics)
        if route.request_profile:
            client = DeepInfraChatCompletionsClient(
                api_key=key, model=route.model, request_profile=route.request_profile
            )
            try:
                result = dict(client.parse_response(decoded))
            except DeepInfraPermanentError as exc:
                raise ProviderReplyError(str(exc), diagnostics) from exc
        else:
            try:
                result = json.loads(choices[0]["message"]["content"])
            except (ValueError, TypeError, KeyError) as exc:
                raise ProviderReplyError("invalid_model_json", diagnostics) from exc
        if not isinstance(result, dict):
            raise ProviderReplyError("non_object_model_response", diagnostics)
        if "source_bindings" in request:
            try:
                result = normalize_reply(
                    result, request, editor=stage.startswith("editor")
                )
            except (ValueError, TypeError) as exc:
                diagnostics["validation_code"] = str(exc).replace(" ", "_")
                raise ProviderReplyError("invalid_source_support", diagnostics) from exc
        elif "source_ids" in request:
            entries = (
                result.get("events", []) if stage.startswith("editor") else [result]
            )
            if not isinstance(entries, list) or any(
                not isinstance(entry, dict) for entry in entries
            ):
                raise ProviderReplyError("malformed_model_entries", diagnostics)
            if any(
                not entry.get("source_check")
                for entry in entries
                if not stage.startswith("editor")
                or entry.get("chatter")
                or entry.get("pulse")
            ):
                raise ProviderReplyError("missing_source_check", diagnostics)
            result = restore_sources(result, request["source_ids"])
        return {
            "data": result,
            "usage": kept,
            "model": decoded["model"],
            "diagnostics": diagnostics,
        }

    def send():
        started = monotonic()
        try:
            return receive()
        except (TimeoutError, OSError, http.client.HTTPException) as exc:
            code = (
                "provider_timeout"
                if isinstance(exc, TimeoutError)
                else "provider_transport_failure"
            )
            raise ProviderReplyError(code, diagnostics) from exc
        finally:
            diagnostics["elapsed_seconds"] = round(monotonic() - started, 3)

    from urllib.parse import urlsplit

    return call_once(
        assessment,
        stage,
        "text",
        ceiling,
        cfg,
        send,
        request_metadata={
            "request_hash": hashlib.sha256(encoded).hexdigest(),
            "request_packet": body,
            "provider": urlsplit(route.endpoint).hostname,
            "model": route.model,
            "workflow_version": digest(
                [cfg.model_dump(mode="json"), request.get("packet_version", "legacy")]
            ),
            "rates": {
                "input_usd_per_million": route.input_usd_per_million,
                "output_usd_per_million": route.output_usd_per_million,
            },
        },
    )
