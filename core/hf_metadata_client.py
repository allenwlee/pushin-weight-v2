"""Public HF metadata only, with one budget for every physical request.

No implicit credentials, SDK retries, repository files, or inference calls.
Responses remain JSON objects so new provider fields survive collection.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

API = "https://huggingface.co/api"
INVENTORY_VERSION = "hf-model-metadata-v1"
REPO_ID = re.compile(
    r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}/[A-Za-z0-9_][A-Za-z0-9._-]{0,95}$"
)
NAMESPACE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$")
EXPAND_FIELDS = (
    "author",
    "baseModels",
    "cardData",
    "childrenModelCount",
    "config",
    "createdAt",
    "disabled",
    "downloads",
    "downloadsAllTime",
    "evalResults",
    "gated",
    "gguf",
    "inference",
    "inferenceProviderMapping",
    "lastModified",
    "library_name",
    "likes",
    "mask_token",
    "model-index",
    "pipeline_tag",
    "private",
    "safetensors",
    "sha",
    "siblings",
    "spaces",
    "tags",
    "transformersInfo",
    "trendingScore",
    "widgetData",
    "usedStorage",
    "resourceGroup",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class MetadataResponse:
    outcome: str
    payload: Any = None
    next_cursor: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)


class HFMetadataClient:
    def __init__(
        self,
        client: httpx.Client,
        *,
        max_requests: int,
        max_seconds: float,
        max_bytes: int = 16 * 1024 * 1024,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        if (
            max_requests < 1
            or not math.isfinite(max_seconds)
            or max_seconds <= 0
            or max_bytes < 1
        ):
            raise ValueError("HF request, time, and size budgets must be positive")
        self.client = client
        self.max_requests = max_requests
        self.max_bytes = max_bytes
        self.sleep = sleep
        self.clock = clock
        self.started = clock()
        self.deadline = self.started + max_seconds
        self.requests = 0
        self.retries = 0
        self.on_attempt = None

    @property
    def stop_reason(self) -> str | None:
        if self.requests >= self.max_requests:
            return "request_cap"
        if self.clock() >= self.deadline:
            return "time_cap"
        return None

    def _get(self, path: str, params: Any = None) -> MetadataResponse:
        attempts: list[dict[str, Any]] = []
        for attempt_number in range(3):
            if reason := self.stop_reason:
                return MetadataResponse(reason, attempts=attempts)
            envelope = {
                "endpoint": f"{API}{path}",
                "parameters": params,
                "attempted_at": utc_now(),
                "http_status": None,
                "outcome": "pending",
                "payload": None,
                "inventory_version": INVENTORY_VERSION,
            }
            self.requests += 1
            self.retries += int(attempt_number > 0)
            if self.on_attempt:
                self.on_attempt(envelope)
            delay = float(2**attempt_number)
            transient = False
            try:
                # Explicit auth=None defeats client-level auth. Never inherit
                # authorization headers even from an injected caller's client.
                request = self.client.build_request(
                    "GET",
                    f"{API}{path}",
                    params=params,
                    headers={"Accept": "application/json"},
                    timeout=min(30.0, max(0.001, self.deadline - self.clock())),
                )
                request.headers.pop("authorization", None)
                request.headers.pop("cookie", None)
                with closing(
                    self.client.send(
                        request, stream=True, auth=None, follow_redirects=False
                    )
                ) as response:
                    envelope["http_status"] = response.status_code
                    if response.status_code == 200:
                        chunks = bytearray()
                        for chunk in response.iter_bytes():
                            if self.clock() >= self.deadline:
                                envelope["outcome"] = "time_cap"
                                break
                            if len(chunks) + len(chunk) > self.max_bytes:
                                envelope["outcome"] = "response_size_cap"
                                break
                            chunks.extend(chunk)
                        else:
                            try:
                                envelope["payload"] = json.loads(chunks)
                                envelope["outcome"] = "ok"
                            except (ValueError, UnicodeDecodeError):
                                envelope["outcome"] = "malformed"
                        envelope["link"] = response.headers.get("link", "")
                    else:
                        envelope["outcome"] = {
                            401: "unauthorized",
                            403: "forbidden",
                            404: "not_found",
                            429: "throttled",
                        }.get(
                            response.status_code,
                            "redirect"
                            if response.is_redirect
                            else f"http_{response.status_code}",
                        )
                        transient = (
                            response.status_code == 429 or response.status_code >= 500
                        )
                        delay = self._retry_delay(
                            response.headers.get("retry-after"), delay
                        )
                        # Retain bounded error evidence too. An HTML error page
                        # is an HTTP failure, not a JSON-success parsing failure.
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            if (
                                len(body) + len(chunk) > self.max_bytes
                                or self.clock() >= self.deadline
                            ):
                                envelope["error_body_truncated"] = True
                                break
                            body.extend(chunk)
                        else:
                            try:
                                envelope["payload"] = json.loads(body)
                            except ValueError:
                                pass
            except httpx.HTTPError:
                envelope["outcome"] = "request_error"
                transient = True
            envelope["observed_at"] = utc_now()
            attempts.append(envelope)
            if not transient or attempt_number == 2:
                return MetadataResponse(
                    str(envelope["outcome"]), envelope["payload"], attempts=attempts
                )
            if reason := self.stop_reason:
                return MetadataResponse(reason, attempts=attempts)
            if delay >= self.deadline - self.clock():
                return MetadataResponse("time_cap", attempts=attempts)
            self.sleep(delay)
        raise AssertionError("unreachable")

    @staticmethod
    def _retry_delay(value: str | None, default: float) -> float:
        if not value:
            return default
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                return max(
                    0.0,
                    (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds(),
                )
            except (ValueError, TypeError, OverflowError):
                return default

    def namespace_info(self, namespace: str) -> MetadataResponse:
        if not NAMESPACE.fullmatch(namespace):
            return MetadataResponse("malformed")
        result = self._get(f"/organizations/{namespace}/overview")
        if result.outcome == "not_found":
            user = self._get(f"/users/{namespace}/overview")
            user.attempts = result.attempts + user.attempts
            result = user
        if result.outcome == "ok":
            payload = result.payload
            name = (
                (
                    payload.get("name")
                    or payload.get("user")
                    or payload.get("organization")
                )
                if isinstance(payload, dict)
                else None
            )
            if not isinstance(name, str) or name.casefold() != namespace.casefold():
                result.outcome = "identity_mismatch"
        return result

    def list_page(
        self, namespace: str, cursor: str | None = None, *, limit: int = 100
    ) -> MetadataResponse:
        if not NAMESPACE.fullmatch(namespace) or not 1 <= limit <= 100:
            return MetadataResponse("malformed")
        params = {
            "author": namespace,
            "full": "true",
            "limit": limit,
            "sort": "lastModified",
            "direction": -1,
        }
        if cursor:
            params["cursor"] = cursor
        result = self._get("/models", params)
        if result.outcome != "ok":
            return result
        if not isinstance(result.payload, list):
            result.outcome = "malformed"
            return result
        for item in result.payload:
            if outcome := self._identity_outcome(item, namespace=namespace):
                result.outcome = outcome
                return result
        link = result.attempts[-1].get("link", "")
        # httpx parses the rel attributes; only the cursor is accepted from the
        # provider URL. All author/filter parameters stay under our control.
        response = httpx.Response(200, headers={"link": link})
        next_link = response.links.get("next")
        if next_link:
            url = urlparse(next_link.get("url", ""))
            values = parse_qs(url.query).get("cursor", [])
            if (
                url.scheme != "https"
                or url.netloc != "huggingface.co"
                or url.path != "/api/models"
                or url.fragment
                or len(values) != 1
                or not values[0]
            ):
                result.outcome = "invalid_continuation"
            else:
                result.next_cursor = values[0]
        elif "next" in link:
            result.outcome = "invalid_continuation"
        return result

    def model_group(self, repo_id: str, group: str) -> MetadataResponse:
        if not REPO_ID.fullmatch(repo_id):
            return MetadataResponse("malformed")
        if group == "detail":
            params = [("blobs", "true"), ("securityStatus", "true")]
        elif group == "expanded":
            params = [("expand", name) for name in EXPAND_FIELDS]
        else:
            raise ValueError("unknown HF metadata group")
        result = self._get(f"/models/{repo_id}", params)
        if group == "expanded" and result.outcome == "http_400":
            fallback = self._get(
                f"/models/{repo_id}",
                [
                    ("expand", name)
                    for name in (
                        "author",
                        "sha",
                        "private",
                        "downloads",
                        "likes",
                        "tags",
                        "cardData",
                    )
                ],
            )
            fallback.attempts = result.attempts + fallback.attempts
            if fallback.outcome == "ok":
                fallback.outcome = (
                    self._identity_outcome(fallback.payload, repo_id=repo_id)
                    or "partial_expansion"
                )
            return fallback
        if result.outcome == "ok":
            result.outcome = (
                self._identity_outcome(result.payload, repo_id=repo_id) or "ok"
            )
        return result

    @staticmethod
    def _identity_outcome(
        payload: Any, *, repo_id: str | None = None, namespace: str | None = None
    ) -> str | None:
        if not isinstance(payload, dict):
            return "malformed"
        returned_id = payload.get("id") or payload.get("modelId")
        if not isinstance(returned_id, str) or not REPO_ID.fullmatch(returned_id):
            return "malformed"
        if repo_id and returned_id.casefold() != repo_id.casefold():
            return "identity_mismatch"
        if (
            namespace
            and returned_id.split("/", 1)[0].casefold() != namespace.casefold()
        ):
            return "identity_mismatch"
        if payload.get("private") is True:
            return "private"
        author = payload.get("author")
        if author is not None and (
            not isinstance(author, str)
            or author.casefold() != returned_id.split("/", 1)[0].casefold()
        ):
            return "identity_mismatch"
        return None
