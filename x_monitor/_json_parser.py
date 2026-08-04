"""LLM-response JSON parser.

Both AnthropicClaudeClient wrappers (classifier + translator) call into
this helper instead of calling json.loads() directly. The helper uses
json.JSONDecoder().raw_decode() to consume the first valid JSON value
in the LLM's textual response and silently drop anything after it.

BEFORE: json.loads() raised JSONDecodeError when the model returned
valid JSON followed by trailing prose (a common Claude habit), causing
whole batches to be dropped or fall back to {"verdict": "uncertain"}.
The classifier's lang_detected contract was broken in prod 2026-08-04
when 42% of an 1h cohort had lang_detected IS NULL.

AFTER: raw_decode() finds the first valid JSON object regardless of
trailing prose. The caller-specific fallback dict is returned only
when the response has NO valid JSON at all.
"""
from __future__ import annotations

import json as _json
import logging as _logging
from typing import Any


def parse_llm_response(
    raw: str,
    *,
    logger_name: str = "x_monitor._json_parser",
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse the first valid JSON object from `raw`, dropping trailing prose.

    Args:
        raw: the LLM's textual response (concatenated text blocks).
        logger_name: namespace used for the warning logger on parse failure.
        fallback: dict returned when the response contains no valid JSON.
                  Defaults to {"verdict": "uncertain", "reason": "llm_non_json_response"}
                  (the classifier's contract). Pass {"results": []} for the translator.

    Returns:
        The first valid JSON dict in `raw`, or `fallback` on parse failure.
    """
    if fallback is None:
        fallback = {"verdict": "uncertain", "reason": "llm_non_json_response"}

    stripped = _strip_code_fence(raw)

    try:
        obj, _end = _json.JSONDecoder().raw_decode(stripped)
    except _json.JSONDecodeError:
        _logging.getLogger(logger_name).warning(
            "messages_create: LLM returned non-JSON (len=%d): %r",
            len(stripped), stripped[:500],
        )
        return fallback

    if not isinstance(obj, dict):
        _logging.getLogger(logger_name).warning(
            "messages_create: LLM returned non-dict JSON (type=%s): %r",
            type(obj).__name__, stripped[:500],
        )
        return fallback

    return obj


def _strip_code_fence(raw: str) -> str:
    """Drop leading/trailing ```...``` fences if present.

    Mirrors the existing inline rule in x_monitor/attribution.py:2156-2161
    and x_monitor/translator.py:947-952. Only strips a fence pair; if
    the closing fence is missing, only the leading fence is dropped.
    """
    s = raw.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if lines[-1].strip().startswith("```"):
        inner = "\n".join(lines[1:-1])
    else:
        inner = "\n".join(lines[1:])
    return inner.strip()
