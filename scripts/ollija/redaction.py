from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


class UnsafeOutputError(ValueError):
    """Raised when structured output would expose credential material."""


_SENSITIVE_KEY_PARTS = {
    "api_key",
    "authorization",
    "connection_string",
    "cookie",
    "database_url",
    "password",
    "post_content",
    "private_key",
    "provider_request",
    "provider_response",
    "request_body",
    "response_body",
    "secret",
    "token",
}
_DATABASE_URL = re.compile(r"\b(?:postgres(?:ql)?|redis)://[^\s]+", re.IGNORECASE)
_AUTHORITY_CREDENTIAL = re.compile(
    r"\b[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s@]+@", re.IGNORECASE
)
_API_TOKEN = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def _normalized_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


def assert_safe_value(value: Any, *, location: str = "output") -> None:
    """Reject secret-bearing fields and strings before they reach JSON/logs."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            wrapped = f"_{normalized}_"
            if any(f"_{part}_" in wrapped for part in _SENSITIVE_KEY_PARTS):
                raise UnsafeOutputError(
                    f"{location} contains secret-shaped field {key!r}"
                )
            assert_safe_value(child, location=f"{location}.{key}")
        return

    if isinstance(value, (list, tuple, set, frozenset)):
        for index, child in enumerate(value):
            assert_safe_value(child, location=f"{location}[{index}]")
        return

    if isinstance(value, str) and (
        _DATABASE_URL.search(value)
        or _AUTHORITY_CREDENTIAL.search(value)
        or _API_TOKEN.search(value)
        or _PRIVATE_KEY.search(value)
    ):
        raise UnsafeOutputError(f"{location} contains credential-shaped text")


def redact_text(text: str) -> str:
    """Remove common credential forms from an exception before reporting it."""

    redacted = _DATABASE_URL.sub("[REDACTED_DATABASE_URL]", text)
    redacted = _AUTHORITY_CREDENTIAL.sub("[REDACTED_URL_AUTHORITY]", redacted)
    redacted = _API_TOKEN.sub("[REDACTED]", redacted)
    redacted = _PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", redacted)
    return redacted
