"""Regression net for one bounded enrichment-attempt deadline."""

from __future__ import annotations

from typing import Any

import pytest

from x_monitor.config import EnrichmentAttemptDeadline


class AdvancingFailureClient:
    def __init__(self, clock: list[float], *, advance_to: float):
        self.clock = clock
        self.advance_to = advance_to
        self.calls: list[dict[str, Any]] = []

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        self.clock[0] = self.advance_to
        raise TimeoutError("provider stalled")


def test_translator_stops_retrying_when_shared_attempt_deadline_expires():
    from x_monitor.translator import _call_with_retry

    clock = [0.0]
    deadline = EnrichmentAttemptDeadline(
        deadline_at=45.0,
        request_timeout_seconds=45,
        monotonic=lambda: clock[0],
    )
    client = AdvancingFailureClient(clock, advance_to=45.0)

    with pytest.raises(TimeoutError, match="enrichment_attempt_deadline_exhausted"):
        _call_with_retry(client, "prompt", n_tweets=1, deadline=deadline)

    assert len(client.calls) == 1
    assert client.calls[0]["timeout"] == 45.0


def test_classifier_does_not_start_per_post_fallback_after_deadline():
    from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full

    clock = [0.0]
    deadline = EnrichmentAttemptDeadline(
        deadline_at=45.0,
        request_timeout_seconds=45,
        monotonic=lambda: clock[0],
    )
    client = AdvancingFailureClient(clock, advance_to=45.0)
    tweets = [
        {"tweet_id": "1", "text": "MiniMax update", "brand_ids": ["minimax"]},
        {"tweet_id": "2", "text": "DeepSeek update", "brand_ids": ["deepseek"]},
    ]
    brands = [
        BrandRow("minimax", "MiniMax", "#000000", False),
        BrandRow("deepseek", "DeepSeek", "#000000", False),
    ]

    with pytest.raises(TimeoutError, match="enrichment_attempt_deadline_exhausted"):
        classify_batch_pragmatics_full(
            tweets,
            brands,
            client,
            deadline=deadline,
        )

    assert len(client.calls) == 1
    assert client.calls[0]["timeout"] == 45.0


def test_request_timeout_uses_only_remaining_attempt_budget():
    clock = [40.0]
    deadline = EnrichmentAttemptDeadline(
        deadline_at=45.0,
        request_timeout_seconds=45,
        monotonic=lambda: clock[0],
    )

    assert deadline.request_timeout() == 5.0
    clock[0] = 45.0
    assert deadline.expired()
    assert deadline.request_timeout() == 0.0
