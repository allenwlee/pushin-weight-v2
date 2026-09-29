"""Scheduled User About cannot start HTTP without a full request window."""

import asyncio

from monitor.twitterapi.user_about import FetchSelection, fetch_user_about_batch
from monitor.twitterapi.user_about_service import fetch_apply_user_about_batch


def test_request_is_not_sent_when_safe_window_cannot_fit(monkeypatch):
    class NoHttpSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            raise AssertionError("HTTP must not start without a safe window")

    monkeypatch.setattr(
        "monitor.twitterapi.user_about.aiohttp.ClientSession",
        lambda **kwargs: NoHttpSession(),
    )
    batch = asyncio.run(
        fetch_user_about_batch(
            [FetchSelection(author_id="101", handle="sample")],
            api_key="test-key",
            rate_qps=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=11,
            min_request_window_seconds=12,
        )
    )

    assert batch.attempts == 0
    assert batch.projected_credits == 0
    assert batch.outcomes == []
    assert batch.stop_reason == "deadline_envelope"


def test_safe_window_is_rechecked_after_pace_gate(monkeypatch):
    class NoHttpSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            raise AssertionError("HTTP must not start after the window shrinks")

    monkeypatch.setattr(
        "monitor.twitterapi.user_about.aiohttp.ClientSession",
        lambda **kwargs: NoHttpSession(),
    )
    ticks = iter([0, 0, 0, 5])

    def clock():
        return next(ticks, 5)
    batch = asyncio.run(
        fetch_user_about_batch(
            [FetchSelection(author_id="102", handle="sample")],
            api_key="test-key",
            rate_qps=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=15,
            min_request_window_seconds=12,
            clock=clock,
        )
    )

    assert batch.attempts == 0
    assert batch.stop_reason == "deadline_envelope"


def test_slow_claim_acquisition_uses_the_same_wall_budget(monkeypatch):
    claimed = []
    released = []
    ticks = iter((0.0, 0.0, 8.0, 8.0))

    def clock():
        return next(ticks, 8.0)

    def fake_claim(**kwargs):
        claimed.append(kwargs["author_id"])
        return object()

    def fake_settle(**kwargs):
        released.append((kwargs["author_id"], kwargs["outcome"]))
        return None

    async def forbidden_fetch(*args, **kwargs):
        raise AssertionError("claim acquisition exhausted the request envelope")

    monkeypatch.setattr(
        "monitor.twitterapi.user_about_service.claim_account", fake_claim
    )
    monkeypatch.setattr(
        "monitor.twitterapi.user_about_service.settle_outcome", fake_settle
    )
    result = fetch_apply_user_about_batch(
        [FetchSelection(author_id="101", handle="sample")],
        api_key="test-key", rate_qps=1, concurrency=1,
        max_attempts=1, max_credits=18, max_wall_seconds=10,
        min_request_window_seconds=5, fetcher=forbidden_fetch, clock=clock,
    )

    assert claimed == ["101"]
    assert released == [("101", None)]
    assert result.batch.attempts == 0
    assert result.batch.stop_reason == "deadline_envelope"
    assert result.batch.wall_seconds == 8.0


def test_manual_apply_requires_claim_schema_before_credential_resolution():
    from monitor.management.commands.backfill_account_based_in import (
        REQUIRED_MIGRATIONS,
    )

    assert "0059_account_user_about_and_muse" in REQUIRED_MIGRATIONS
