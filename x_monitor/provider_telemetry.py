"""Safe, best-effort provider transport telemetry."""
from __future__ import annotations

import logging
import time
from typing import Any, Mapping


class ProviderResponse(dict):
    """A dict-compatible parsed response retaining provider metadata."""

    def __init__(self, value: Mapping[str, Any], *, usage: Any = None):
        super().__init__(value)
        self.provider_usage = usage


def _read(value: Any, *names: str) -> int | None:
    for name in names:
        item = value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)
        if item is None:
            continue
        try:
            return int(item)
        except (TypeError, ValueError):
            return None
    return None


def normalize_usage(value: Any) -> dict[str, int | None]:
    """Normalize reported usage; never infer totals from overlapping fields."""
    if value is None:
        return {key: None for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens", "total_tokens")}
    return {
        "input_tokens": _read(value, "input_tokens", "input"),
        "output_tokens": _read(value, "output_tokens", "output"),
        "cache_read_input_tokens": _read(value, "cache_read_input_tokens", "cache_read_tokens", "cache_read"),
        "cache_creation_input_tokens": _read(value, "cache_creation_input_tokens", "cache_creation_tokens", "cache_creation"),
        "reasoning_tokens": _read(value, "reasoning_tokens", "reasoning"),
        "total_tokens": _read(value, "total_tokens", "total"),
    }


def emit_attempt(logger: logging.Logger, *, role: str, model: str | None, attempt: int, outcome: str, started: float, response: Any = None, error: Exception | None = None, **context: Any) -> None:
    """Emit metadata only. Logging must never affect enrichment."""
    try:
        logger.info("provider_transport_attempt", extra={"provider_transport_event": {
            "role": role, "model": model, "attempt": attempt,
            "outcome": outcome, "elapsed_ms": max(0, round((time.monotonic() - started) * 1000)),
            "error_type": type(error).__name__ if error else None,
            "usage": normalize_usage(getattr(response, "provider_usage", None)),
            **{key: value for key, value in context.items() if value is not None},
        }})
    except Exception:
        pass
