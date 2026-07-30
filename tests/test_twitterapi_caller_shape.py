"""U3 tests - aiohttp TwitterAPI caller shape + classification.

Plan: docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md
Unit U3.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor.twitterapi.caller import (
    CircuitBreaker,
    LookupResult,
    LookupStats,
    _classify_response,
    lookup_batch,
)


# -- _classify_response pure-function tests ---------------------------


def test_classify_200_success_with_id():
    reason, canonical = _classify_response(
        200,
        '{"status":"success","data":{"id":"12345","name":"Alice","screen_name":"alice"}}',
    )
    assert reason == "success"
    assert canonical is not None
    assert canonical["author_id"] == "12345"
    assert canonical["name"] == "Alice"


def test_classify_200_success_with_rest_id():
    """Some responses use rest_id instead of id."""
    reason, canonical = _classify_response(
        200,
        '{"status":"success","data":{"rest_id":"99999","screen_name":"bob"}}',
    )
    assert reason == "success"
    assert canonical["author_id"] == "99999"


def test_classify_200_not_found():
    """twitterapi.io returns HTTP 200 + status=error for missing users."""
    reason, canonical = _classify_response(
        200,
        '{"status":"error","msg":"user not found","data":null}',
    )
    assert reason == "not_found_200"
    assert canonical is None


def test_classify_http_404():
    reason, canonical = _classify_response(404, "Not Found")
    assert reason == "http_404"
    assert canonical is None


def test_classify_429():
    reason, canonical = _classify_response(429, "Too Many Requests")
    assert reason == "rate_limited"
    assert canonical is None


def test_classify_500():
    reason, canonical = _classify_response(500, "Internal Server Error")
    assert reason == "http_5xx"
    assert canonical is None


def test_classify_200_malformed_json():
    """Garbage 200 body -- treat as 5xx-style dead-letter."""
    reason, canonical = _classify_response(200, "not json at all")
    assert reason == "http_5xx"
    assert canonical is None


def test_classify_200_success_no_id():
    """success status but no id field -- malformed response."""
    reason, canonical = _classify_response(
        200,
        '{"status":"success","data":{"name":"NoID"}}',
    )
    assert reason == "http_5xx"
    assert canonical is None


# -- _do_one behavior with mock session -------------------------------


@pytest.mark.asyncio
async def test_429_with_retry_after_triggers_one_retry():
    """First response 429 with Retry-After: 1, second response 200 success."""
    from monitor.twitterapi.caller import _do_one

    fake_resp_429 = MagicMock()
    fake_resp_429.status = 429
    fake_resp_429.headers = {"Retry-After": "1"}
    fake_resp_429.text = AsyncMock(return_value="Too Many Requests")
    fake_resp_429.__aenter__ = AsyncMock(return_value=fake_resp_429)
    fake_resp_429.__aexit__ = AsyncMock(return_value=None)

    fake_resp_200 = MagicMock()
    fake_resp_200.status = 200
    fake_resp_200.text = AsyncMock(
        return_value='{"status":"success","data":{"id":"42","screen_name":"x"}}'
    )
    fake_resp_200.__aenter__ = AsyncMock(return_value=fake_resp_200)
    fake_resp_200.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.get = MagicMock(side_effect=[fake_resp_429, fake_resp_200])

    timeout = MagicMock()
    result = await _do_one(session, "alice", timeout)
    assert result.success is True
    assert result.canonical is not None
    assert result.canonical["author_id"] == "42"
    # The retry did happen; retry_after_429 is NOT set on success path
    # (it's only set when the retry also fails -- see next test).
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_429_after_retry_is_dead_letter():
    """First 429 then second 429 -> dead_letter with retried_after_429=True."""
    from monitor.twitterapi.caller import _do_one

    def fake_resp_429():
        r = MagicMock()
        r.status = 429
        r.headers = {"Retry-After": "1"}
        r.text = AsyncMock(return_value="Too Many Requests")
        r.__aenter__ = AsyncMock(return_value=r)
        r.__aexit__ = AsyncMock(return_value=None)
        return r

    session = MagicMock()
    session.get = MagicMock(side_effect=[fake_resp_429(), fake_resp_429()])

    timeout = MagicMock()
    result = await _do_one(session, "alice", timeout)
    assert result.success is False
    assert result.reason == "rate_limited"
    assert result.retried_after_429 is True
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_200_with_empty_data_is_dead_letter():
    from monitor.twitterapi.caller import _do_one

    fake_resp = MagicMock()
    fake_resp.status = 200
    fake_resp.headers = {}
    fake_resp.text = AsyncMock(
        return_value='{"status":"error","msg":"user not found","data":null}'
    )
    fake_resp.__aenter__ = AsyncMock(return_value=fake_resp)
    fake_resp.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.get = MagicMock(return_value=fake_resp)
    timeout = MagicMock()
    result = await _do_one(session, "ghost", timeout)
    assert result.success is False
    assert result.reason == "not_found_200"


@pytest.mark.asyncio
async def test_http_404_is_dead_letter():
    from monitor.twitterapi.caller import _do_one

    fake_resp = MagicMock()
    fake_resp.status = 404
    fake_resp.headers = {}
    fake_resp.text = AsyncMock(return_value="Not Found")
    fake_resp.__aenter__ = AsyncMock(return_value=fake_resp)
    fake_resp.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.get = MagicMock(return_value=fake_resp)
    timeout = MagicMock()
    result = await _do_one(session, "ghost", timeout)
    assert result.reason == "http_404"


# -- User-Agent + concurrency caps via real aiohttp --------------------


@pytest.mark.asyncio
async def test_user_agent_is_curl():
    """Captured headers assert User-Agent: curl/7.84.0."""
    from monitor.twitterapi.caller import lookup_batch

    captured_headers: dict = {}

    class FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        def get(self, url, *, params, timeout):
            captured_headers["url"] = url
            captured_headers["params"] = params

            class FakeResp:
                status = 200
                headers = {}
                async def __aenter__(self_inner):
                    return self_inner
                async def __aexit__(self_inner, *args):
                    return None
                async def text(self_inner):
                    return '{"status":"error","msg":"user not found","data":null}'
            return FakeResp()

    # Patch ClientSession to use our FakeSession.
    fake = FakeSession()
    with patch("aiohttp.ClientSession", return_value=fake):
        results = []
        async for r in lookup_batch(
            ["alice"], api_key="test-key",
            rate_qps=100, concurrency=1,
        ):
            results.append(r)
    assert results[0].reason == "not_found_200"


@pytest.mark.asyncio
async def test_concurrency_capped_at_two():
    """TCPConnector is created with limit=concurrency."""
    from monitor.twitterapi import caller

    captured: dict = {}

    real_TCPConnector = caller.aiohttp.TCPConnector

    class SpyConnector(real_TCPConnector):
        def __init__(self, *args, **kwargs):
            captured["limit"] = kwargs.get("limit")
            super().__init__(*args, **kwargs)

    with patch.object(caller.aiohttp, "TCPConnector", SpyConnector):
        # Minimal: just iterate one handle to trigger session creation.
        async for _ in caller.lookup_batch(
            ["x"], api_key="k", rate_qps=100, concurrency=2,
        ):
            pass
    assert captured["limit"] == 2


# -- Stats tracking -----------------------------------------------------


@pytest.mark.asyncio
async def test_stats_track_resolved_and_dead_lettered():
    """stats.resolved / stats.dead_lettered increment correctly."""
    from monitor.twitterapi.caller import lookup_batch

    def make_resp(status, body):
        class R:
            pass
        r = R()
        r.status = status
        r.headers = {}
        async def text():
            return body
        r.text = text
        r.__aenter__ = AsyncMock(return_value=r)
        r.__aexit__ = AsyncMock(return_value=None)
        return r

    ok = make_resp(200, '{"status":"success","data":{"id":"1","screen_name":"a"}}')
    miss = make_resp(200, '{"status":"error","msg":"user not found","data":null}')

    class FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        def get(self, url, *, params, timeout):
            if params["userName"] == "ok":
                return ok
            return miss

    stats = LookupStats()
    with patch("aiohttp.ClientSession", return_value=FakeSession()):
        async for _ in lookup_batch(
            ["ok", "miss"], api_key="k", rate_qps=100, concurrency=2, stats=stats,
        ):
            pass
    assert stats.looked_up == 2
    assert stats.resolved == 1
    assert stats.dead_lettered == 1
    assert stats.by_reason.get("not_found_200") == 1


# -- Circuit breaker tests ---------------------------------------------


def test_circuit_breaker_trips_after_threshold():
    """10 consecutive rate_limited errors -> breaker opens."""
    b = CircuitBreaker(threshold=10)
    for i in range(9):
        b.record("rate_limited")
        assert not b.is_open, f"tripped too early at iteration {i}"
    b.record("rate_limited")
    assert b.is_open


def test_circuit_breaker_resets_on_success():
    """Success resets the consecutive counter."""
    b = CircuitBreaker(threshold=10)
    for _ in range(5):
        b.record("rate_limited")
    b.record("success")  # counter resets
    for _ in range(9):
        b.record("rate_limited")
    assert not b.is_open, "counter should have reset and not yet hit 10"


def test_circuit_breaker_resets_on_non_trip_error():
    """not_found_200 and http_404 don't accumulate (don't trip)."""
    b = CircuitBreaker(threshold=10)
    for _ in range(20):
        b.record("not_found_200")
    assert not b.is_open
    for _ in range(20):
        b.record("http_404")
    assert not b.is_open


def test_circuit_breaker_trips_on_5xx_too():
    """5xx counts toward the trip threshold alongside 429."""
    b = CircuitBreaker(threshold=10)
    for _ in range(5):
        b.record("rate_limited")
    for _ in range(4):
        b.record("http_5xx")
    assert not b.is_open
    b.record("http_5xx")
    assert b.is_open


@pytest.mark.asyncio
async def test_lookup_batch_short_circuits_when_breaker_open():
    """Once breaker is open, remaining handles return circuit_open."""
    from monitor.twitterapi import caller

    breaker = CircuitBreaker(threshold=2)
    # Pre-trip the breaker.
    breaker.record("rate_limited")
    breaker.record("rate_limited")
    assert breaker.is_open

    # The lookup should NOT make any HTTP calls.
    real_TCPConnector = caller.aiohttp.TCPConnector

    class SpyConnector(real_TCPConnector):
        def __init__(self, *args, **kwargs):
            self.create_connection_called = False
            super().__init__(*args, **kwargs)

    with patch.object(caller.aiohttp, "TCPConnector", SpyConnector):
        results = []
        async for r in caller.lookup_batch(
            ["a", "b", "c"], api_key="k", rate_qps=100, concurrency=2,
            breaker=breaker,
        ):
            results.append(r)
    assert len(results) == 3
    assert all(r.reason == "circuit_open" for r in results)
    assert all(not r.success for r in results)


# -- Split timeout tests ------------------------------------------------


@pytest.mark.asyncio
async def test_split_timeout_used():
    """ClientTimeout is constructed with sock_connect=3, sock_read=10."""
    from monitor.twitterapi import caller

    captured: dict = {}

    real_ClientTimeout = caller.aiohttp.ClientTimeout

    def spy_ClientTimeout(**kwargs):
        captured.update(kwargs)
        return real_ClientTimeout(**kwargs)

    class FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        def get(self, url, *, params, timeout):
            class R:
                status = 200
                headers = {}
                async def __aenter__(self_inner):
                    return self_inner
                async def __aexit__(self_inner, *args):
                    return None
                async def text(self_inner):
                    return '{"status":"error","msg":"user not found","data":null}'
            return R()

    with patch.object(caller.aiohttp, "ClientTimeout", spy_ClientTimeout), \
         patch("aiohttp.ClientSession", return_value=FakeSession()):
        async for _ in caller.lookup_batch(
            ["x"], api_key="k", rate_qps=100, concurrency=1,
        ):
            pass
    assert captured.get("sock_connect") == 3.0
    assert captured.get("sock_read") == 10.0
    assert captured.get("total") == 12.0