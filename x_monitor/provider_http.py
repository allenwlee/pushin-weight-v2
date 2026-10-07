"""One non-retrying, bounded HTTPS transport for explicit provider routes."""

import http.client
import json
from urllib.parse import urlsplit

ALLOWED_HOSTS = frozenset({"api.deepinfra.com", "openrouter.ai", "api.minimax.io"})


def https_request(
    endpoint, api_key, payload, *, timeout=90, method="POST", max_bytes=2_000_000
):
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("unsupported provider endpoint")
    if not api_key:
        raise ValueError("provider credential missing")
    conn = http.client.HTTPSConnection(parsed.hostname, 443, timeout=timeout)
    try:
        conn.request(
            method,
            parsed.path + ("?" + parsed.query if parsed.query else ""),
            body=json.dumps(payload, ensure_ascii=False).encode()
            if payload is not None
            else None,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        response = conn.getresponse()
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("provider response exceeds cap")
        return response.status, body
    finally:
        conn.close()
