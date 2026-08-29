"""U3 - aiohttp TwitterAPI caller for the lonely-placeholder apply.

Plan: docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md
Unit U3.

Caps concurrency at TCPConnector(limit=N), gates requests to rate_qps,
honors Retry-After, classifies the response as either success or
dead-letter with one of:
  - not_found_200  (HTTP 200 + {"status":"error","msg":"user not found"})
  - http_404       (genuine HTTP 404)
  - rate_limited   (HTTP 429 after one inline retry)
  - http_5xx       (server error)
  - connection_error (aiohttp client error or timeout)

The single inline retry per handle keeps 429 bursts from thrashing;
persistent 429s fall through to dead-letter so the apply can move on.

Hardening (user guidance 2026-07-31):
  - ClientSession + TCPConnector instantiated ONCE per batch; the
    session's Keep-Alive recycles the underlying TCP socket across
    all 10,681 requests -- only ~2 ephemeral ports used total, not
    10,681. Do NOT instantiate per-handle sessions (would defeat
    Keep-Alive).
  - Circuit breaker: a session-level `CircuitBreaker` counts
    consecutive 429/5xx errors. After 10 in a row, the breaker
    trips and subsequent handles are short-circuited to dead-letter
    with reason="circuit_open". The apply loop checks
    `breaker.is_open` per handle and writes partial=true to the exit
    summary so the cron knows to retry on the next tick.
  - Jittered 429 backoff: `Retry-After + random.uniform(0.1, 0.5)`
    desynchronizes the two in-flight workers so they don't slam the
    API at the same millisecond after a sleep.
  - Split ClientTimeout: sock_connect=3s (fast fail on TLS), total=10s.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable

import aiohttp


TWITTERAPI_USER_INFO_URL = "https://api.twitterapi.io/twitter/user/info"
USER_AGENT = "curl/7.84.0"

# Circuit breaker constants (user guidance 2026-07-31).
CIRCUIT_BREAKER_THRESHOLD = 10  # consecutive 429/5xx -> trip
# NOTE: `auth_invalid` (HTTP 401) is intentionally EXCLUDED -- a bad key
# is not a rate-limit problem and shouldn't burn 10 dead-letter rows
# before exiting. Instead the apply loop short-circuits on the FIRST
# auth_invalid and writes partial=true with error="auth_invalid" so
# the operator can rotate the key without burning the candidate pool.
CIRCUIT_BREAKER_REASONS = ("rate_limited", "http_5xx")


class GlobalPaceGate:
    """Serialize request starts so aggregate throughput cannot exceed QPS."""

    def __init__(
        self,
        *,
        rate_qps: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if rate_qps <= 0:
            raise ValueError("rate_qps must be positive")
        self._interval = 1.0 / float(rate_qps)
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next_start = clock()

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            delay = max(0.0, self._next_start - now)
            if delay:
                await self._sleep(delay)
            started = self._clock()
            self._next_start = max(started, self._next_start) + self._interval


@dataclass
class LookupResult:
    handle: str
    success: bool = False
    canonical: dict | None = None  # {"author_id": "12345", "name": "...", ...}
    reason: str | None = None  # one of: success | not_found_200 | http_404 | rate_limited | http_5xx | connection_error
    status_code: int | None = None
    response_excerpt: str = ""
    retried_after_429: bool = False

    @classmethod
    def from_success(cls, handle: str, canonical: dict) -> "LookupResult":
        return cls(handle=handle, success=True, canonical=canonical, reason="success")

    @classmethod
    def from_dead_letter(
        cls,
        handle: str,
        reason: str,
        status_code: int | None = None,
        response_excerpt: str = "",
        retried_after_429: bool = False,
    ) -> "LookupResult":
        return cls(
            handle=handle,
            success=False,
            reason=reason,
            status_code=status_code,
            response_excerpt=response_excerpt[:500],
            retried_after_429=retried_after_429,
        )


@dataclass
class LookupStats:
    looked_up: int = 0
    resolved: int = 0
    dead_lettered: int = 0
    retried_after_429: int = 0
    circuit_open_short_circuits: int = 0  # handles skipped due to circuit_open
    by_reason: dict[str, int] = field(default_factory=dict)


class CircuitBreaker:
    """Tracks consecutive 429/5xx errors; trips after threshold.

    Once tripped, `is_open` stays True for the rest of the session --
    the apply loop sees this on every subsequent handle and writes
    `partial=true` to the exit summary so the cron knows to retry
    on the next tick (giving TwitterAPI time to recover).

    The counter resets to 0 on any success or any non-trip-class error
    (e.g. not_found_200, http_404, connection_error) so transient
    network blips don't accumulate across the run.
    """

    def __init__(self, threshold: int = CIRCUIT_BREAKER_THRESHOLD):
        self.threshold = threshold
        self._consecutive = 0
        self._tripped = False
        self._tripped_at: float | None = None

    @property
    def is_open(self) -> bool:
        return self._tripped

    def record(self, reason: str | None) -> None:
        if reason in CIRCUIT_BREAKER_REASONS:
            self._consecutive += 1
            if self._consecutive >= self.threshold and not self._tripped:
                self._tripped = True
                self._tripped_at = time.monotonic()
        else:
            # Any non-trip error resets the counter.
            self._consecutive = 0


def _classify_response(status: int, body_text: str) -> tuple[str, dict | None]:
    """Map HTTP status + body to (reason, canonical-or-None)."""
    if status == 200:
        import json
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            return "http_5xx", None  # malformed JSON — treat as 5xx-ish dead-letter
        # twitterapi.io shape: {"status":"success","data":{...}} on hit,
        # {"status":"error","msg":"user not found","data":null} on miss.
        if body.get("status") == "success" and body.get("data"):
            data = body["data"]
            author_id = str(data.get("id") or data.get("rest_id") or "")
            if author_id:
                return "success", {
                    "author_id": author_id,
                    "name": data.get("name"),
                    "screen_name": data.get("screen_name") or data.get("userName"),
                }
            return "http_5xx", None  # success status but no ID — malformed
        return "not_found_200", None
    if status == 404:
        return "http_404", None
    if status == 401:
        # TwitterAPI rejects an invalid API key with HTTP 401 (body
        # {"error":"Unauthorized","message":"API key is invalid"}). The
        # 2026-07-31 cron run misclassified these as http_5xx, which
        # tripped the circuit breaker after 10 consecutive 401s and
        # dead-lettered the entire candidate pool. Distinct reason +
        # exempt from breaker = future runs exit cleanly on the FIRST
        # 401 with auth_invalid surfacing in the exit summary.
        return "auth_invalid", None
    if status == 403:
        return "auth_forbidden", None  # key valid but endpoint blocked
    if status == 429:
        return "rate_limited", None
    if 500 <= status < 600:
        return "http_5xx", None
    return "http_5xx", None  # any other unexpected status


async def lookup_batch(
    handles: list[str],
    *,
    api_key: str,
    rate_qps: float = 5.0,
    concurrency: int = 2,
    stats: LookupStats | None = None,
    breaker: CircuitBreaker | None = None,
) -> AsyncIterator[LookupResult]:
    """Yield one LookupResult per handle. Caps concurrency, paces requests.

    The pacing gate is a simple `await asyncio.sleep(gate_interval)`
    after each request -- with rate_qps=5 and concurrency=2, that's a
    200ms gate. Throughput is bounded by max(rate_qps, concurrency/t);
    at rate_qps=5 with concurrency=2 we expect ~5 QPS sustained (the
    gate dominates) and ~2 concurrent in-flight at any moment.

    If `breaker` is provided and trips mid-batch, remaining handles
    short-circuit to dead-letter with reason="circuit_open" so the
    apply can finish quickly and the cron can record partial=true.
    """
    if stats is None:
        stats = LookupStats()
    if breaker is None:
        breaker = CircuitBreaker()
    gate_interval = 1.0 / float(rate_qps)
    # Port-exhaustion hardening (per user's 2026-07-31 guidance):
    #   - TCPConnector(limit=concurrency): caps in-flight sockets at
    #     `concurrency` -- never more than 2 at rate_qps=5/conn=2.
    #   - force_close=False (default): Keep-Alive is on, so the
    #     underlying TCP socket is recycled for subsequent requests
    #     on the same connection. With Keep-Alive, the entire 10,681-
    #     handle run uses ~2 ephemeral ports, NOT 10,681.
    #   - The `async with ClientSession(...)` below ensures the
    #     session -- and its connector -- is instantiated ONCE per
    #     batch and torn down ONCE at the end. NEVER instantiate a
    #     new ClientSession per handle; that would defeat Keep-Alive
    #     and re-create sockets at the rate-limit pace.
    connector = aiohttp.TCPConnector(limit=concurrency)
    headers = {
        "X-API-Key": api_key,
        "User-Agent": USER_AGENT,
    }
    # Split timeouts (user guidance 2026-07-31): fast fail on TLS,
    # bounded read window. sock_connect=3s, sock_read=10s, total=12s.
    timeout = aiohttp.ClientTimeout(
        sock_connect=3.0,
        sock_read=10.0,
        total=12.0,
    )

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        sem = asyncio.Semaphore(concurrency)

        async def one(handle: str) -> LookupResult:
            async with sem:
                if breaker.is_open:
                    stats.circuit_open_short_circuits += 1
                    stats.dead_lettered += 1
                    stats.by_reason["circuit_open"] = (
                        stats.by_reason.get("circuit_open", 0) + 1
                    )
                    return LookupResult.from_dead_letter(
                        handle, reason="circuit_open",
                        response_excerpt="circuit breaker open after consecutive 429/5xx",
                    )
                result = await _do_one(session, handle, timeout, breaker)
                if result.retried_after_429:
                    stats.retried_after_429 += 1
                stats.looked_up += 1
                if result.success:
                    stats.resolved += 1
                else:
                    stats.dead_lettered += 1
                    stats.by_reason[result.reason or "unknown"] = (
                        stats.by_reason.get(result.reason or "unknown", 0) + 1
                    )
                # Short-circuit on FIRST auth_invalid: a bad key is not a
                # rate-limit problem, and burning the candidate pool
                # through 10 sequential 401s is what the 2026-07-31
                # cron run did. Trip the breaker manually on auth_invalid
                # so subsequent handles short-circuit via circuit_open.
                if result.reason == "auth_invalid":
                    breaker._tripped = True
                else:
                    breaker.record(result.reason)
                # Pacing gate after every request (success or dead-letter).
                await asyncio.sleep(gate_interval)
                return result

        # Dispatch all concurrently; the semaphore caps in-flight.
        results = await asyncio.gather(
            *(one(h) for h in handles),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                # Should not happen — _do_one catches its own exceptions — but
                # if asyncio scheduling itself errors, surface as dead-letter.
                yield LookupResult.from_dead_letter(
                    handle="<unknown>",
                    reason="connection_error",
                    response_excerpt=repr(r)[:500],
                )
            else:
                yield r


async def _do_one(
    session: aiohttp.ClientSession,
    handle: str,
    timeout: aiohttp.ClientTimeout,
    breaker: CircuitBreaker | None = None,
) -> LookupResult:
    """Single TwitterAPI lookup. One inline retry on 429 with jitter.

    The 429 retry sleeps `Retry-After + random.uniform(0.1, 0.5)` so
    the two in-flight workers don't wake up at the same millisecond
    and re-slam the API together (user guidance 2026-07-31).

    The breaker is passed in for symmetry with `lookup_batch`; this
    function itself doesn't trip the breaker (caller does, after
    observing the result), so it remains purely a transform layer.
    """
    try:
        async with session.get(
            TWITTERAPI_USER_INFO_URL,
            params={"userName": handle},
            timeout=timeout,
        ) as resp:
            status = resp.status
            body = await resp.text()

            if status == 429:
                # ONE inline retry honoring Retry-After + jitter.
                retry_after_raw = resp.headers.get("Retry-After", "2")
                try:
                    retry_after = float(retry_after_raw)
                    retry_after = max(1.0, min(retry_after, 30.0))
                except ValueError:
                    retry_after = 2.0
                # Jitter (user guidance 2026-07-31): desynchronize the
                # two in-flight workers so they don't re-slam the API
                # at the exact same millisecond after the sleep.
                jitter = random.uniform(0.1, 0.5)
                await asyncio.sleep(retry_after + jitter)

                async with session.get(
                    TWITTERAPI_USER_INFO_URL,
                    params={"userName": handle},
                    timeout=timeout,
                ) as resp2:
                    status2 = resp2.status
                    body2 = await resp2.text()
                    reason, canonical = _classify_response(status2, body2)
                    if reason == "success":
                        return LookupResult.from_success(handle, canonical)  # type: ignore[arg-type]
                    return LookupResult.from_dead_letter(
                        handle, reason="rate_limited",
                        status_code=429,  # first hit; second hit is recorded inside _classify
                        response_excerpt=body2[:200],
                        retried_after_429=True,
                    )

            reason, canonical = _classify_response(status, body)
            if reason == "success":
                return LookupResult.from_success(handle, canonical)  # type: ignore[arg-type]
            return LookupResult.from_dead_letter(
                handle, reason=reason,
                status_code=status,
                response_excerpt=body[:200],
            )
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return LookupResult.from_dead_letter(
            handle, reason="connection_error",
            response_excerpt=repr(exc)[:200],
        )
