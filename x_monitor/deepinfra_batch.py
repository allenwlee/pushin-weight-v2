"""Bounded DeepInfra batch transport; callers own durable admission and retries.

Files contain the canonical chat request bodies. This module never creates
prompts, retries a submission, sleeps, or counts polling as model inference.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from itertools import chain
from typing import Any

import requests

SERVER_MAX_REQUESTS = 50_000
SERVER_MAX_FILE_BYTES = 200_000_000
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class BatchProtocolError(ValueError):
    """A local envelope or received result violates the bounded contract."""


class BatchTransportError(RuntimeError):
    """Transport failed; a submission may have reached the provider."""


class BatchHTTPError(RuntimeError):
    def __init__(self, status: int, retry_after: str | None = None):
        super().__init__(f"deepinfra_batch_http_{status}")
        self.status = status
        self.retryable = status in {408, 425, 429} or 500 <= status <= 599
        self.retry_after_seconds = 60
        if retry_after:
            try:
                seconds = int(retry_after)
            except (TypeError, ValueError):
                try:
                    when = parsedate_to_datetime(retry_after)
                    seconds = int((when - datetime.now(UTC)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    seconds = 60
            self.retry_after_seconds = max(1, seconds)


def encode_requests(
    rows: Iterable[tuple[str, dict[str, Any]]],
    *,
    max_requests: int = 2_000,
    max_bytes: int = 16 * 1024 * 1024,
) -> bytes:
    if (
        not 1 <= max_requests <= SERVER_MAX_REQUESTS
        or not 1 <= max_bytes <= SERVER_MAX_FILE_BYTES
    ):
        raise BatchProtocolError("batch_limit_invalid")
    output = bytearray()
    identities: set[str] = set()
    model = None
    for identity, body in rows:
        if (
            not isinstance(identity, str)
            or not _SAFE_ID.fullmatch(identity)
            or identity in identities
        ):
            raise BatchProtocolError("batch_request_identity_invalid")
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("model"), str)
            or not body["model"]
        ):
            raise BatchProtocolError("batch_request_model_missing")
        model = model or body["model"]
        if model != body["model"]:
            raise BatchProtocolError("batch_mixed_models")
        identities.add(identity)
        if len(identities) > max_requests:
            raise BatchProtocolError("batch_request_limit")
        encoded = (
            json.dumps(
                {
                    "custom_id": identity,
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": body,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
            + b"\n"
        )
        if len(output) + len(encoded) > max_bytes:
            raise BatchProtocolError("batch_file_limit")
        output.extend(encoded)
    if not identities:
        raise BatchProtocolError("batch_empty")
    return bytes(output)


def decode_outputs(
    chunks: Iterable[bytes], *, max_line_bytes: int = 4 * 1024 * 1024
) -> Iterator[dict[str, Any]]:
    """Parse a streamed result without retaining the output file in memory."""
    buffer = bytearray()
    count = 0
    for chunk in chain(chunks, [b"\n"]):
        buffer.extend(chunk)
        while b"\n" in buffer:
            line, _, remaining = buffer.partition(b"\n")
            buffer = bytearray(remaining)
            if not line.strip():
                continue
            if len(line) > max_line_bytes:
                raise BatchProtocolError("batch_result_line_limit")
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError) as exc:
                raise BatchProtocolError("batch_result_json_invalid") from exc
            if not isinstance(row, dict):
                raise BatchProtocolError("batch_result_shape_invalid")
            count += 1
            if count > SERVER_MAX_REQUESTS:
                raise BatchProtocolError("batch_result_count_limit")
            yield row
        if len(buffer) > max_line_bytes:
            raise BatchProtocolError("batch_result_line_limit")


class DeepInfraBatchClient:
    """Every control HTTP start requires the caller's durable admission callback."""

    def __init__(
        self,
        *,
        api_key: str,
        before_request: Callable[[str, str], None],
        session: Any = None,
    ):
        if not api_key or not callable(before_request):
            raise BatchProtocolError("batch_credentials_or_admission_missing")
        self._key = api_key
        self._before_request = before_request
        self._session = session or requests.Session()
        self._owns_session = session is None

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    @contextmanager
    def _request(self, method: str, path: str, **kwargs: Any):
        self._before_request(method, path)
        try:
            response = self._session.request(
                method,
                "https://api.deepinfra.com/v1/openai" + path,
                headers={"Authorization": "Bearer " + self._key},
                timeout=(10, 60),
                stream=True,
                **kwargs,
            )
        except requests.RequestException:
            raise BatchTransportError("deepinfra_batch_transport_ambiguous") from None
        try:
            if not 200 <= response.status_code < 300:
                raise BatchHTTPError(
                    response.status_code, response.headers.get("Retry-After")
                )
            yield response
        finally:
            response.close()

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        with self._request(method, path, **kwargs) as response:
            body = bytearray()
            try:
                for chunk in response.iter_content(64 * 1024):
                    body.extend(chunk)
                    if len(body) > 1024 * 1024:
                        raise BatchProtocolError("batch_metadata_limit")
            except requests.RequestException:
                raise BatchTransportError(
                    "deepinfra_batch_response_interrupted"
                ) from None
            try:
                value = json.loads(body)
            except (ValueError, UnicodeError):
                raise BatchProtocolError("batch_metadata_invalid") from None
            if not isinstance(value, dict):
                raise BatchProtocolError("batch_metadata_shape_invalid")
            return value

    @staticmethod
    def _id(value: str) -> str:
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise BatchProtocolError("batch_provider_id_invalid")
        return value

    def upload(self, content: bytes) -> dict[str, Any]:
        if not content or len(content) > SERVER_MAX_FILE_BYTES:
            raise BatchProtocolError("batch_file_limit")
        return self._json(
            "POST",
            "/files",
            data={"purpose": "batch"},
            files={
                "file": ("requests.jsonl", content, "application/jsonl"),
            },
        )

    def submit(self, file_id: str, *, identity: str) -> dict[str, Any]:
        return self._json(
            "POST",
            "/batches",
            json={
                "input_file_id": self._id(file_id),
                "endpoint": "/v1/chat/completions",
                "completion_window": "24h",
                "metadata": {"request_identity": self._id(identity)},
            },
        )

    def retrieve(self, batch_id: str) -> dict[str, Any]:
        return self._json("GET", "/batches/" + self._id(batch_id))

    def list_batches(self, *, after: str | None = None) -> dict[str, Any]:
        params = {"limit": 20}
        if after:
            params["after"] = self._id(after)
        return self._json("GET", "/batches", params=params)

    def outputs(self, file_id: str) -> Iterator[dict[str, Any]]:
        with self._request(
            "GET", "/files/" + self._id(file_id) + "/content"
        ) as response:
            try:
                yield from decode_outputs(response.iter_content(64 * 1024))
            except requests.RequestException:
                raise BatchTransportError(
                    "deepinfra_batch_output_interrupted"
                ) from None
