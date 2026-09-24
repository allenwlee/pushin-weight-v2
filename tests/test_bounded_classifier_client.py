"""Physical-call budget regressions for the cycle's guarded LLM client."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from typing import Any

import pytest

from monitor.cycle import _BoundedClassifierClient
from x_monitor.attribution import LLMCallBudgetExhausted
from x_monitor.provider_telemetry import ProviderTextResponse


class _MixedDelegate:
    request_identity = "provider=deepseek;profile=literal"
    request_profile = "literal_v2"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.lock = Lock()

    def _record(self, kind: str) -> None:
        with self.lock:
            self.calls.append(kind)

    def messages_create(self, **_kwargs: Any) -> dict[str, bool]:
        self._record("json")
        return {"ok": True}

    def messages_create_text(self, **kwargs: Any) -> ProviderTextResponse:
        self._record("text")
        if kwargs.get("fail"):
            raise ValueError("delegate failure")
        return ProviderTextResponse("raw", {})


def test_raw_and_json_calls_share_cap_reservations_and_delegate_identity():
    delegate = _MixedDelegate()
    bounded = _BoundedClassifierClient(
        delegate, maximum_calls=3, pause_seconds=0
    )
    content_token, brand_token = bounded.reserve_pair(attempts_per_role=1) or (
        None,
        None,
    )

    assert bounded.request_identity == delegate.request_identity
    assert bounded.request_profile == delegate.request_profile
    assert bounded.messages_create_text().text == "raw"
    assert bounded.messages_create(
        _classifier_reservation=content_token
    ) == {"ok": True}
    assert bounded.messages_create_text(
        _classifier_reservation=brand_token
    ).text == "raw"
    with pytest.raises(LLMCallBudgetExhausted):
        bounded.messages_create_text()

    assert bounded.calls == 3
    assert delegate.calls == ["text", "json", "text"]


def test_failed_raw_delegate_call_consumes_a_physical_call_slot():
    delegate = _MixedDelegate()
    bounded = _BoundedClassifierClient(
        delegate, maximum_calls=1, pause_seconds=0
    )

    with pytest.raises(ValueError, match="delegate failure"):
        bounded.messages_create_text(fail=True)
    with pytest.raises(LLMCallBudgetExhausted):
        bounded.messages_create()

    assert bounded.calls == 1
    assert delegate.calls == ["text"]


def test_concurrent_raw_and_json_calls_cannot_exceed_shared_cap():
    delegate = _MixedDelegate()
    bounded = _BoundedClassifierClient(
        delegate, maximum_calls=3, pause_seconds=0
    )
    barrier = Barrier(8)

    def call(index: int) -> str:
        barrier.wait()
        try:
            if index % 2:
                bounded.messages_create_text()
            else:
                bounded.messages_create()
        except LLMCallBudgetExhausted:
            return "exhausted"
        return "called"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(call, range(8)))

    assert outcomes.count("called") == 3
    assert outcomes.count("exhausted") == 5
    assert bounded.calls == 3
    assert len(delegate.calls) == 3


def test_raw_and_json_calls_share_start_rate_spacing():
    delegate = _MixedDelegate()
    now = [10.0]
    sleeps: list[float] = []

    def monotonic() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    bounded = _BoundedClassifierClient(
        delegate,
        maximum_calls=None,
        pause_seconds=1,
        monotonic=monotonic,
        sleep=sleep,
    )

    bounded.messages_create()
    bounded.messages_create_text()

    assert sleeps == [1.0]
    assert delegate.calls == ["json", "text"]
