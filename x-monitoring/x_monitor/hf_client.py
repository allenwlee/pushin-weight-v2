# {{AGENT_ATTRIBUTION}}
"""HuggingFace Hub REST client.

A thin, testable HTTP layer over the HF Hub API. Mechanics (token bearer
auth, retry/backoff, Link-header cursor pagination) are ported from the
top-gun crawler (`hf_direct_discover_scraper.py`, `build_hf_discover_queue.py`)
so x-monitor reuses the proven pattern rather than reinventing it.

All network is behind functions that accept an injectable ``client``
(``httpx.Client`` / MockTransport) so unit tests never hit the network.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any
from urllib.parse import unquote

import httpx

_log = logging.getLogger(__name__)

HF_API_BASE = "https://huggingface.co/api"

# Safety cap on pagination: even a pathological org won't exceed this many pages.
_MAX_PAGES = 1000

# Indirection so tests can collapse retry backoff to a no-op.
_sleep = time.sleep

_default_client_cache: httpx.Client | None = None


def get_hf_token() -> str | None:
    return os.environ.get("HF_TOKEN")


def hf_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    token = get_hf_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _default_client() -> httpx.Client:
    global _default_client_cache
    if _default_client_cache is None:
        _default_client_cache = httpx.Client(timeout=30)
    return _default_client_cache


def _next_cursor(link_header: str) -> str | None:
    """Extract the ``cursor`` value from the ``rel="next"`` Link segment."""
    for part in link_header.split(","):
        if 'rel="next"' in part:
            m = re.search(r"cursor=([^&>]+)", part)
            if m:
                return unquote(m.group(1))
    return None


def hf_get(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    client: httpx.Client | None = None,
    retries: int = 3,
) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    """GET ``{HF_API_BASE}{path}``. Returns ``(data, error_message)``.

    - 404 → ``(None, "not_found")`` immediately (no retry).
    - 403 / non-200 / transport error → exponential backoff retry, then bail.
    - 200 → ``(parsed_json, None)``.
    """
    c = client if client is not None else _default_client()
    url = f"{HF_API_BASE}{path}"
    last_err: str | None = None
    for attempt in range(retries):
        try:
            resp = c.get(url, params=params, headers=hf_headers())
        except httpx.HTTPError as e:
            last_err = f"transport_error: {e}"
            if attempt < retries - 1:
                _sleep(2 ** attempt)
                continue
            return None, last_err

        if resp.status_code == 404:
            return None, "not_found"
        if resp.status_code == 403:
            last_err = "forbidden"
            if attempt < retries - 1:
                _sleep(2 ** attempt)
                continue
            return None, "forbidden"
        if resp.status_code != 200:
            last_err = f"http_{resp.status_code}"
            if attempt < retries - 1:
                _sleep(2 ** attempt)
                continue
            return None, last_err
        return resp.json(), None
    return None, last_err or "retries_exhausted"


def list_models_by_org(
    org: str,
    *,
    full: bool = True,
    limit: int = 100,
    sort: str = "lastModified",
    direction: int = -1,
    max: int | None = None,
    client: httpx.Client | None = None,
    sleep: float = 0.5,
) -> list[dict[str, Any]]:
    """List every model owned by ``org``, following the Link-header cursor.

    ``GET /api/models?author={org}&full=true&limit=…&sort=…&direction=…&cursor=…``
    Paginates until exhausted, a short page, ``max`` reached, the cursor stops
    advancing, or the ``_MAX_PAGES`` safety cap (guards against a misbehaving
    server that repeats the same rel=next cursor).
    """
    c = client if client is not None else _default_client()
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    prev_cursor: str | None = None
    pages = 0
    while pages < _MAX_PAGES:
        pages += 1
        params: dict[str, Any] = {
            "author": org,
            "sort": sort,
            "direction": direction,
            "limit": limit,
            "full": "true" if full else "false",
        }
        if cursor:
            params["cursor"] = cursor
        resp = c.get(f"{HF_API_BASE}/models", params=params, headers=hf_headers())
        if resp.status_code != 200:
            break
        data = resp.json()
        items = data if isinstance(data, list) else data.get("models", [])
        if not items:
            break
        out.extend(items)
        if max is not None and len(out) >= max:
            return out[:max]
        if len(items) < limit:
            break
        cursor = _next_cursor(resp.headers.get("link", ""))
        if not cursor or cursor == prev_cursor:
            break  # no progress → stop (avoids infinite loop on a repeated cursor)
        prev_cursor = cursor
        if sleep:
            _sleep(sleep)
    return out


def get_model(
    repo_id: str,
    *,
    expand: str | list[str] | None = None,
    blobs: bool = False,
    client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    """Full ModelInfo for ``repo_id`` (``GET /api/models/{repo_id}``)."""
    params: dict[str, Any] = {}
    if expand:
        params["expand"] = expand if isinstance(expand, str) else ",".join(expand)
    if blobs:
        params["blobs"] = "true"
    data, _err = hf_get(f"/models/{repo_id}", params=params or None, client=client)
    return data


def search_organizations(
    query: str, *, client: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """Search HF orgs for ``query`` (``GET /api/organizations?search=…``).

    Returns candidate orgs (possibly empty). A failed search (403/5xx/transport)
    is logged as a warning and returns [] — distinct from a genuine empty result
    only in the log; callers should not treat [] as definitive without the log.
    Endpoint shape is [standard] — verify against live HF before relying on
    field names.
    """
    data, err = hf_get("/organizations", params={"search": query}, client=client)
    if err:
        _log.warning("hf_client: org search for %r failed (%s)", query, err)
    if isinstance(data, list):
        return data
    return []


def org_has_models(
    org: str, *, client: httpx.Client | None = None, limit: int = 1
) -> tuple[bool, list[dict[str, Any]]]:
    """Sanity probe: does ``org`` exist and publish ≥1 model?

    Returns ``(ok, sample_models)``. Used by the resolver/collector sanity gate
    so a wrong org fails loudly instead of silently scraping nothing.
    """
    sample = list_models_by_org(org, limit=limit, max=limit, client=client, sleep=0)
    if not sample:
        return False, []
    authors = {m.get("author") for m in sample if m.get("author")}
    ok = org in authors or any(
        m.get("id", "").split("/", 1)[0] == org for m in sample
    )
    return ok, sample
