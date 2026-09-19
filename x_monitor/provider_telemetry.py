"""Safe, best-effort provider transport telemetry."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4


class ProviderResponse(dict):
    """A dict-compatible parsed response retaining provider metadata."""

    def __init__(self, value: Mapping[str, Any], *, usage: Any = None):
        super().__init__(value)
        self.provider_usage = usage


@dataclass(frozen=True)
class ProviderTextResponse:
    """Literal provider text with the same usage attachment as JSON responses."""

    text: str
    provider_usage: Any = None


def provider_host_class(client_or_url: Any) -> str:
    """Return an allowlisted provider label without exposing a host or URL."""
    try:
        base_url = client_or_url if isinstance(client_or_url, str) else getattr(
            client_or_url, "_base_url", None
        )
        if base_url is None:
            base_url = getattr(
                getattr(client_or_url, "_client", None), "base_url", None
            )
        hostname = (urlparse(str(base_url or "")).hostname or "").casefold()
    except Exception:  # noqa: BLE001 - telemetry must not affect enrichment
        return "unknown"
    return {
        "api.deepseek.com": "deepseek",
        "api.deepinfra.com": "deepinfra",
        "api.minimax.io": "minimax",
        "api.anthropic.com": "anthropic",
        "openrouter.ai": "openrouter",
        "api.openrouter.ai": "openrouter",
    }.get(hostname, "unknown")


def _read(value: Any, *names: str) -> int | None:
    for name in names:
        item = value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)
        if item is None:
            continue
        # Provider counters are non-negative integer values.  ``int(True)``
        # and ``int(1.5)`` are both misleading telemetry, so reject them
        # instead of silently manufacturing a count.
        if isinstance(item, bool):
            return None
        if isinstance(item, int):
            return item if item >= 0 else None
        if isinstance(item, str) and re.fullmatch(r"\s*\d+\s*", item):
            return int(item)
        return None
    return None


def _read_cost(value: Any) -> float | None:
    item = value.get("cost_usd") if isinstance(value, Mapping) else getattr(value, "cost_usd", None)
    if isinstance(item, bool) or item is None:
        return None
    try:
        cost = float(item)
    except (TypeError, ValueError):
        return None
    return cost if cost >= 0 else None


def _read_request_id(value: Any) -> str | None:
    item = value.get("provider_request_id") if isinstance(value, Mapping) else getattr(value, "provider_request_id", None)
    if not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", item):
        return None
    return item


def normalize_usage(value: Any) -> dict[str, int | float | str | None]:
    """Normalize reported usage; never infer totals from overlapping fields."""
    if value is None:
        return {key: None for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens", "total_tokens", "cost_usd", "provider_request_id")}
    return {
        "input_tokens": _read(value, "input_tokens", "input"),
        "output_tokens": _read(value, "output_tokens", "output"),
        "cache_read_input_tokens": _read(value, "cache_read_input_tokens", "cache_read_tokens", "cache_read"),
        "cache_creation_input_tokens": _read(value, "cache_creation_input_tokens", "cache_creation_tokens", "cache_creation"),
        "reasoning_tokens": _read(value, "reasoning_tokens", "reasoning"),
        "total_tokens": _read(value, "total_tokens", "total"),
        "cost_usd": _read_cost(value),
        "provider_request_id": _read_request_id(value),
    }


_CONTEXT_KEYS = frozenset(
    {
        "stage",
        "run_id",
        "call_id",
        "batch_key",
        "request_identity",
        "provider_host_class",
        "batch_size",
    }
)


def emit_attempt(logger: logging.Logger, *, role: str, model: str | None, attempt: int, outcome: str, started: float, response: Any = None, error: Exception | None = None, prompt: str = "", attempt_kind: str | None = None, **context: Any) -> None:
    """Emit metadata only. Logging must never affect enrichment."""
    try:
        safe_context = {
            key: value
            for key, value in context.items()
            if key in _CONTEXT_KEYS and value is not None
        }
        event = {
            "event_id": str(uuid4()), "timestamp": datetime.now(UTC).isoformat(),
            "role": role, "stage": safe_context.pop("stage", role), "run_id": safe_context.pop("run_id", None),
            "model": model, "provider_host_class": safe_context.pop("provider_host_class", "unknown"),
            "prompt_identity": hashlib.sha256(prompt.encode()).hexdigest()[:16] if prompt else None,
            "batch_size": safe_context.pop("batch_size", None), "attempt": attempt,
            "attempt_kind": attempt_kind,
            "outcome": outcome, "elapsed_ms": max(0, round((time.monotonic() - started) * 1000)),
            "error_type": type(error).__name__ if error else None,
            "usage": normalize_usage(
                getattr(response, "provider_usage", None)
                if getattr(response, "provider_usage", None) is not None
                else getattr(error, "provider_usage", None)
            ),
            "usage_source": "provider" if (
                getattr(response, "provider_usage", None) is not None
                or getattr(error, "provider_usage", None) is not None
            ) else "missing",
            **safe_context,
        }
        logger.info(
            json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
            extra={"provider_transport_event": event},
        )
    except Exception:  # noqa: BLE001, S110 - telemetry must not affect enrichment
        pass
