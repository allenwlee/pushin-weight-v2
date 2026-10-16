"""Prepare and consume batch replies through the existing model callers.

The resolver supplies durable replies or records a request intent. Neither
method can issue synchronous inference. A missing reply yields control using
the existing non-retrying, not-sent execution path.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from typing import Any

from x_monitor.attribution import LLMCallBudgetExhausted
from x_monitor.deepinfra import DeepInfraChatCompletionsClient
from x_monitor.provider_telemetry import ProviderTextResponse


class DeferredRequestPending(LLMCallBudgetExhausted):
    """The request is prepared but its asynchronous reply is unavailable."""


class DeferredInferenceClient:
    deferred_requests = True

    def __init__(
        self,
        delegate: DeepInfraChatCompletionsClient,
        *,
        resolve: Callable[
            [str, dict[str, Any], str, dict[str, Any]], dict[str, Any] | None
        ],
        reply_transport: Callable[[str], str] | None = None,
    ) -> None:
        self._delegate = delegate
        self._resolve = resolve
        self._reply_transport = reply_transport or (lambda identity: "batch")
        self._local = threading.local()

    @property
    def request_profile(self):
        return self._delegate.request_profile

    @property
    def request_identity(self):
        return "batch:" + self._delegate.request_identity

    @property
    def _base_url(self):
        return self._delegate._base_url

    @property
    def model(self):
        return self._delegate.model

    def _reply(self, kind: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        context = kwargs.pop("_batch_context", {})
        if not isinstance(context, dict) or not context.get("post_ids"):
            raise ValueError("batch_request_members_missing")
        body = self._delegate.build_request(**kwargs)
        identity = hashlib.sha256(
            json.dumps(
                {"body": body, "response_kind": kind, "context": context},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        reply = self._resolve(identity, body, kind, context)
        if reply is None:
            raise DeferredRequestPending("asynchronous_model_reply_pending")
        self._local.transport = self._reply_transport(identity)
        return reply

    def messages_create(self, **kwargs: Any):
        result = self._delegate.parse_response(self._reply("json", kwargs))
        result.provider_usage = {
            **result.provider_usage,
            "selected_endpoint": self._local.transport,
            "request_identity": self.request_identity,
            "data_collection": "deepinfra-" + self._local.transport,
            "replayed": True,
        }
        return result

    def messages_create_text(self, **kwargs: Any):
        result = self._delegate.parse_text_response(self._reply("text", kwargs))
        return ProviderTextResponse(
            text=result.text,
            provider_usage={
                **result.provider_usage,
                "selected_endpoint": self._local.transport,
                "request_identity": self.request_identity,
                "data_collection": "deepinfra-" + self._local.transport,
                "replayed": True,
            },
        )
