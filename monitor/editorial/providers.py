"""Model-neutral JSON calls with explicit routing and conservative price reservations."""

import json
import os
from decimal import Decimal

from x_monitor.provider_http import https_request

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
    if route.reasoning:
        if "openrouter.ai" in route.endpoint:
            body["reasoning"] = {"effort": route.reasoning}
        else:
            body["reasoning_effort"] = route.reasoning
    if "openrouter.ai" in route.endpoint:
        body["provider"] = {"allow_fallbacks": False, "require_parameters": True}
    return body


def json_call(assessment, stage, route, request, cfg, *, transport=None):
    transport = transport or https_request
    body = request_payload(route, request)
    encoded = json.dumps(body, ensure_ascii=False).encode()
    if len(encoded) > cfg.max_packet_bytes + 30000:
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

    def send():
        status, raw = transport(route.endpoint, key, body, timeout=90)
        if not 200 <= status < 300:
            raise ValueError(f"provider_http_{status}")
        decoded = json.loads(raw)
        if decoded.get("model") != route.model:
            raise ValueError("served model mismatch")
        choices = decoded.get("choices", [])
        if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
            raise ValueError("incomplete model response")
        result = json.loads(choices[0]["message"]["content"])
        if not isinstance(result, dict):
            raise TypeError("object response required")
        usage = decoded.get("usage", {})
        kept = {
            k: usage[k]
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            if type(usage.get(k)) is int and usage[k] >= 0
        }
        return {"data": result, "usage": kept, "model": decoded["model"]}

    return call_once(assessment, stage, "text", ceiling, cfg, send)
