"""U4 (plan 2026-11-24-012909): every scheduled call reaches a provider.

Production, 2026-11-24 07:30 JST: TwitterAPI.io timed out on both
credentials, TwexAPI answered except for one 503, and then
``_choose_search_provider`` raised "no configured search provider is
available" for 12-13 of the 16 calls while most of the 780 s deadline went
unused. These tests drive the real multi-route ``XClient`` with real
``SearchProviderCircuit`` rows and an injected clock; the cycle-level ones go
through ``CycleRunner.run()`` with all 16 ordinary calls (M18).

KTD references: KTD1 wait for the earliest eligible route, KTD2 route-health
accounting, KTD3 per-cycle failure budget, KTD4 same-route continuation
retry, KTD6 search envelope and reserved tail, KTD7 TwexAPI end of results,
KTD8 backlog-owned failed windows.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
import requests

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner
from x_monitor.config import Config, HarvestConfig, SearchConfig
from x_monitor.query_plan import PlannedCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

CALL_IDS = ["A", *(f"B{n}" for n in range(1, 10)), *(f"C{n}" for n in range(1, 7))]


class Clock:
    """One fake wall clock and monotonic clock; sleeping advances both."""

    def __init__(self, start):
        self.wall = start
        self.mono = 10_000.0
        self.sleeps: list[float] = []

    def now(self):
        return self.wall

    def monotonic(self):
        return self.mono

    def advance(self, seconds):
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds

    def sleep(self, seconds):
        from django.db import connection

        # Never sleep while holding a circuit row lock or any transaction.
        assert not connection.in_atomic_block, "slept inside a database transaction"
        self.sleeps.append(seconds)
        self.advance(seconds)


class Deadline:
    def __init__(self, clock, total):
        self.clock = clock
        self.started = clock.mono
        self.total = total

    def remaining(self):
        return max(self.total - (self.clock.mono - self.started), 0.0)

    def can_start(self, seconds):
        return seconds <= self.remaining()


@pytest.fixture
def clock(monkeypatch):
    from django.utils import timezone as django_timezone

    from x_monitor import x_client

    fake = Clock(django_timezone.now().replace(microsecond=0))
    # raising=False lets this file run against the pre-change client (red-before).
    monkeypatch.setattr(x_client, "_utcnow", fake.now, raising=False)
    monkeypatch.setattr(x_client, "_monotonic", fake.monotonic, raising=False)
    monkeypatch.setattr(x_client, "_sleep", fake.sleep, raising=False)
    monkeypatch.setattr(x_client.time, "sleep", fake.sleep)
    monkeypatch.setattr(django_timezone, "now", fake.now)
    return fake


def _routed_client(*, order=("twitterapi:scheduled", "twexapi"), threshold=2):
    """The client ``XClient.from_env(SCHEDULED)`` builds with both keys."""
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    tapi = SearchProviderCircuit("tapi-fixture-key", provider="twitterapi", endpoint_family="search",
                                 threshold=threshold, cooldown=180)
    twex = SearchProviderCircuit("twex-fixture-key", provider="twexapi", endpoint_family="search",
                                 threshold=threshold, cooldown=180)
    circuits = {"twitterapi:scheduled": tapi} if "twitterapi:scheduled" in order else {}
    return XClient(
        api_key="tapi-fixture", twexapi_key="twex-fixture", circuit=tapi, twex_circuit=twex,
        provider_order=order, provider_credentials={"twitterapi:scheduled": "tapi-fixture"},
        provider_circuits=circuits, twexapi_interval_s=6.0, search_timeout_s=15,
        default_credential_route="twitterapi:scheduled",
    )


def _response(body, status=200, headers=None):
    from requests import Response

    response = Response()
    response.status_code = status
    response.headers.update(headers or {})
    response._content = json.dumps(body).encode()
    return response


def tid(call_id, request_number, n):
    """Numeric post id: call, the call's request number, position on page."""
    index = CALL_IDS.index(call_id) if call_id in CALL_IDS else 90
    return f"{10 + index}{request_number:03d}{n:03d}"


def _twex_items(clock, call_id, request_number, count):
    created = (clock.now() - timedelta(minutes=4)).strftime("%a %b %d %H:%M:%S +0000 %Y")
    return [{"tweet_id": tid(call_id, request_number, n), "full_text": "DeepSeek release",
             "created_at": created, "lang": "en",
             "user": {"id": "author1", "screen_name": "test_author"}} for n in range(count)]


def _tapi_items(clock, call_id, request_number, count):
    return [{"id": tid(call_id, request_number, n), "text": "DeepSeek release", "lang": "en",
             "createdAt": (clock.now() - timedelta(minutes=4)).isoformat(),
             "author": {"id": "author1", "userName": "test_author"}} for n in range(count)]


class TwexScript:
    """Scripted TwexAPI pages per call id; each request costs 1.4 s."""

    def __init__(self, clock, pages, default=("page", 2, None)):
        self.clock = clock
        self.pages = {key: list(value) for key, value in pages.items()}
        self.default = default
        self.requests: list[tuple[str, str | None]] = []

    def __call__(self, url, params, headers):
        call_id = params["searchTerms"][0].split()[0]
        cursor = params.get("next_cursor")
        self.requests.append((call_id, cursor))
        self.clock.advance(1.4)
        queue = self.pages.get(call_id)
        step = queue.pop(0) if queue else self.default
        kind = step[0]
        if kind == "status":
            return _response({"code": step[1]}, status=step[1], headers=step[2] if len(step) > 2 else None)
        _, count, next_cursor = step
        number = len([r for r in self.requests if r[0] == call_id])
        return _response({"code": 200, "msg": "ok", "data": _twex_items(self.clock, call_id, number, count),
                          "has_next_page": next_cursor is not None, "next_cursor": next_cursor})


def _call(call_id):
    return PlannedCall(
        call_id=call_id,
        call_kind="list" if call_id == "A" else "brand_wide",
        brand_id="*" if call_id == "A" else "deepseek",
        bucket=None,
        query_string=call_id,
        query_length=len(call_id),
    )


@pytest.fixture
def scheduled_cycle(monkeypatch, clock, seeded_policy_keywords):
    """Run one scheduled cycle with the given client, deadline and calls."""
    events: list[str] = []

    def run(client, *, total=780.0, call_ids=CALL_IDS, search=None, replay=False):
        calls = [_call(call_id) for call_id in call_ids]
        monkeypatch.setattr(cycle_mod.XClient, "from_env", classmethod(lambda cls, purpose: client))
        monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda *a, **k: list(calls))
        deadline = Deadline(clock, total)
        monkeypatch.setattr(HarvestConfig, "start_deadline", lambda *a, **k: deadline)
        if not replay:
            monkeypatch.setattr(CycleRunner, "_replay_backlog", lambda *a, **k: [])

        def metrics(*args, **kwargs):
            events.append(f"metrics@{deadline.remaining():.0f}")
            return {}

        def post_fetch(self, items, **kwargs):
            events.append("post_fetch")
            return {}

        monkeypatch.setattr("monitor.metrics_refresh.run_metrics_refresh", metrics)
        monkeypatch.setattr(CycleRunner, "_run_post_fetch", post_fetch)
        cfg = Config(enabled_models=["deepseek"], daily_ceiling=100,
                     search=search or SearchConfig(max_results=100, max_pages=10))
        result = CycleRunner(cfg=cfg, cycle_kind="scheduled", _clock=clock.now,
                             _monotonic=clock.monotonic, _collection_window_end=clock.now()).run()
        return result, deadline

    run.events = events
    return run


def _scopes_with_requests():
    from core.models import CollectionScopeRun

    return {
        scope.scope_key: list(scope.requests.order_by("ordinal"))
        for scope in CollectionScopeRun.objects.filter(scope_kind="x_query")
    }


# --- call-chain proofs through CycleRunner.run() ----------------------------


def test_nov24_0730_cascade_every_call_reaches_a_provider(monkeypatch, clock, scheduled_cycle):
    """Nov 24 07:30 sequence: TwitterAPI.io times out on every request,
    TwexAPI serves everything except one 503 on B1's third page, and TwexAPI
    carries one failure over from the previous cycle. On b71090c1 the
    TwitterAPI.io and TwexAPI circuits both open and calls B2..C6 send
    nothing ("no configured search provider is available")."""
    from core.models import CollectionObservationInput, Post
    from core.models import SearchProviderCircuit as CircuitRow

    client = _routed_client()
    CircuitRow.objects.create(purpose=client.twex_circuit.purpose, provider="twexapi",
                              endpoint_family="search", consecutive_failures=1)
    tapi_requests = []

    def tapi_get(url, params=None, headers=None, timeout=None):
        tapi_requests.append(params.get("query", "").split()[0])
        clock.advance(15)
        raise requests.Timeout("TwitterAPI.io search timed out at 15 s")

    monkeypatch.setattr("x_monitor.x_client.requests.get", tapi_get)
    twex = TwexScript(clock, {
        "A": [("page", 3, "A-c1"), ("page", 0, "A-c2")],
        "B1": [("page", 20, "B1-c1"), ("page", 20, "B1-c2"), ("status", 503),
               ("page", 5, "B1-c3"), ("page", 0, "B1-c4")],
    })
    monkeypatch.setattr(client, "_twex_transport", twex)

    result, _deadline = scheduled_cycle(client)

    scopes = _scopes_with_requests()
    assert sorted(scopes) == sorted(CALL_IDS)
    unsent = [call_id for call_id, rows in scopes.items() if not rows]
    assert unsent == [], f"calls sent no request: {unsent}"
    assert {row["call_id"]: row["status"] for row in result["calls"]} == dict.fromkeys(CALL_IDS, "completed")
    stored = set(Post.objects.values_list("tweet_id", flat=True))
    assert {tid("C6", 1, 0), tid("C6", 1, 1), tid("B9", 1, 0)} <= stored
    # KTD3: after three route failures this cycle, TwitterAPI.io is skipped.
    assert len(tapi_requests) <= 3
    # KTD4: B1's refused third page is retried on the same cursor.
    assert [cursor for call_id, cursor in twex.requests if call_id == "B1"] == [
        None, "B1-c1", "B1-c2", "B1-c2", "B1-c3"]
    # Lineage links the retried page's posts to the 200 reply that returned them.
    retried = {tid("B1", 4, n) for n in range(5)} & stored
    assert len(retried) == 5
    links = CollectionObservationInput.objects.filter(observation__post_id__in=retried)
    assert {(row.input_request.http_status, row.input_request.returned_count) for row in links} == {(200, 5)}
    assert all(seconds >= 0 for seconds in clock.sleeps)
    assert run_steps_after_search(scheduled_cycle.events)


def run_steps_after_search(events):
    return "post_fetch" in events and any(event.startswith("metrics@") for event in events)


def test_all_routes_open_for_200_seconds_then_calls_wait_and_send(monkeypatch, clock, scheduled_cycle):
    """KTD1: no route permitted -> sleep until the earliest becomes eligible
    (outside any transaction), charged to the search share."""
    from core.models import SearchProviderCircuit as CircuitRow

    client = _routed_client()
    reopen = clock.now() + timedelta(seconds=200)
    for circuit, provider in ((client.provider_circuits["twitterapi:scheduled"], "twitterapi"),
                              (client.twex_circuit, "twexapi")):
        CircuitRow.objects.create(purpose=circuit.purpose, provider=provider, endpoint_family="search",
                                  consecutive_failures=2, open_until=reopen)
    sent = []

    def tapi_get(url, params=None, headers=None, timeout=None):
        call_id = params["query"].split()[0]
        sent.append(call_id)
        clock.advance(1)
        return _response({"tweets": _tapi_items(clock, call_id, len(sent), 2), "has_next_page": False})

    monkeypatch.setattr("x_monitor.x_client.requests.get", tapi_get)
    monkeypatch.setattr(client, "_twex_transport", lambda *a: pytest.fail("TwitterAPI.io recovered first"))

    result, _deadline = scheduled_cycle(client)

    assert sorted(set(sent)) == sorted(CALL_IDS)
    assert 199 <= sum(clock.sleeps) <= 201
    assert result["calls"][0]["route_wait_ms"] >= 199_000
    assert all(row["status"] == "completed" for row in result["calls"])
    assert run_steps_after_search(scheduled_cycle.events)
    # The steps after search still had their reserved tail.
    metrics_remaining = int(next(e for e in scheduled_cycle.events if e.startswith("metrics@")).split("@")[1])
    assert metrics_remaining >= 188


def test_routes_broken_past_the_tail_end_unsent_and_tail_steps_run(monkeypatch, clock, scheduled_cycle):
    """When no route can reopen before the reserved tail, calls end without
    a request instead of waiting; the cycle ends early, the steps after
    search run, and every failed window is owned by the backlog (KTD8)."""
    from core.models import CallState, HarvestBacklogWindow
    from core.models import SearchProviderCircuit as CircuitRow

    client = _routed_client()
    for circuit, provider in ((client.provider_circuits["twitterapi:scheduled"], "twitterapi"),
                              (client.twex_circuit, "twexapi")):
        CircuitRow.objects.create(purpose=circuit.purpose, provider=provider, endpoint_family="search",
                                  consecutive_failures=6, open_until=clock.now() + timedelta(seconds=2000))
    monkeypatch.setattr("x_monitor.x_client.requests.get", lambda *a, **k: pytest.fail("route is open"))
    monkeypatch.setattr(client, "_twex_transport", lambda *a: pytest.fail("route is open"))

    window_end = clock.now()
    result, deadline = scheduled_cycle(client)

    assert all(not rows for rows in _scopes_with_requests().values())
    assert clock.sleeps == []
    assert deadline.remaining() > 700
    assert run_steps_after_search(scheduled_cycle.events)
    assert {row["status"] for row in result["calls"]} == {"error"}
    assert all(row["cursor_advanced"] for row in result["calls"])
    assert HarvestBacklogWindow.objects.filter(reason_code="search_failed").count() == len(CALL_IDS)
    assert set(CallState.objects.values_list("last_completed_at", flat=True)) == {window_end}


def test_twexapi_only_cycle_sends_every_first_page_before_deep_walks(monkeypatch, clock, scheduled_cycle):
    """KTD6 first-page fairness: with B1 and C1 offering 15 pages each, every
    call still sends its first page; the deep walks stop early and leave a
    backlog residual."""
    from core.models import HarvestBacklogWindow

    client = _routed_client(order=("twexapi",))
    deep = [("page", 20, f"cursor-{n}") for n in range(1, 16)]
    twex = TwexScript(clock, {"B1": list(deep), "C1": list(deep)})
    monkeypatch.setattr(client, "_twex_transport", twex)

    result, _deadline = scheduled_cycle(client, total=450.0, search=SearchConfig(max_results=400, max_pages=20))

    scopes = _scopes_with_requests()
    assert all(scopes[call_id] for call_id in CALL_IDS)
    statuses = {row["call_id"]: row["status"] for row in result["calls"]}
    assert statuses["B1"] == statuses["C1"] == "truncated_replay_queued"
    assert 1 < len(scopes["B1"]) < 15 and len(scopes["C1"]) < 15
    assert HarvestBacklogWindow.objects.filter(call_id__in=["B1", "C1"], reason_code="page_cap").count() == 2
    assert all(statuses[call_id] == "completed" for call_id in CALL_IDS if call_id not in {"B1", "C1"})


def test_twexapi_walk_ending_on_an_empty_page_is_complete_through_run(monkeypatch, clock, scheduled_cycle):
    """U5 / owner decision 2026-11-24 (KTD7): TwexAPI pages 20, 8, then
    0-with-cursor end the call complete, advance the cursor, queue no backlog."""
    from core.models import CallState, CollectionScopeRun, HarvestBacklogWindow

    client = _routed_client(order=("twexapi",))
    twex = TwexScript(clock, {"B1": [("page", 20, "c1"), ("page", 8, "c2"), ("page", 0, "c3")]})
    monkeypatch.setattr(client, "_twex_transport", twex)
    window_end = clock.now()

    result, _ = scheduled_cycle(client, call_ids=["B1"])

    assert result["calls"][0]["status"] == "completed"
    scope = CollectionScopeRun.objects.get(scope_kind="x_query", scope_key="B1")
    assert scope.coverage_state == "complete" and scope.enumeration_complete
    assert CallState.objects.get(call_id="B1").last_completed_at == window_end
    assert not HarvestBacklogWindow.objects.exists()


# --- client-level route selection and retry ---------------------------------


def test_twexapi_429_while_twitterapi_is_open_waits_seconds_not_minutes(monkeypatch, clock):
    from core.models import SearchProviderCircuit as CircuitRow

    client = _routed_client()
    tapi = client.provider_circuits["twitterapi:scheduled"]
    CircuitRow.objects.create(purpose=tapi.purpose, provider="twitterapi", endpoint_family="search",
                              consecutive_failures=6, open_until=clock.now() + timedelta(seconds=180))
    monkeypatch.setattr("x_monitor.x_client.requests.get", lambda *a, **k: pytest.fail("TwitterAPI.io is open"))
    twex = TwexScript(clock, {"C2": [("status", 429), ("page", 1, None)]})
    monkeypatch.setattr(client, "_twex_transport", twex)

    posts, truncated = client.run_search("C2", can_wait_for_rate_limit=lambda seconds: True)

    assert len(posts) == 1 and not truncated
    assert sum(clock.sleeps) <= 10
    assert client.route_wait_seconds <= 6


def test_alternating_twitterapi_timeouts_spend_at_most_three_per_cycle(monkeypatch, clock):
    """KTD3: alternating success and failure never opens the circuit, so the
    process-local budget skips the credential after three route failures."""
    client = _routed_client()
    tapi_calls = []

    def tapi_get(url, params=None, headers=None, timeout=None):
        tapi_calls.append(params["query"])
        if len(tapi_calls) % 2 == 0:
            clock.advance(15)
            raise requests.Timeout("timed out")
        clock.advance(1)
        return _response({"tweets": _tapi_items(clock, "A", len(tapi_calls), 1), "has_next_page": False})

    monkeypatch.setattr("x_monitor.x_client.requests.get", tapi_get)
    twex = TwexScript(clock, {}, default=("page", 1, None))
    monkeypatch.setattr(client, "_twex_transport", twex)

    for n in range(10):
        posts, _ = client.run_search(f"Q{n}", can_wait_for_rate_limit=lambda seconds: True)
        assert len(posts) == 1
    timeouts = len(tapi_calls) // 2
    assert timeouts == 3 and timeouts * 15 <= 45
    assert len(tapi_calls) == 6


def test_unobtained_pacing_slot_records_no_failure_and_holds_no_probe(monkeypatch, clock):
    import uuid

    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    client = _routed_client(order=("twexapi",))
    twex_circuit = client.twex_circuit
    CircuitRow.objects.create(purpose=twex_circuit.purpose, provider="twexapi", endpoint_family="search",
                              consecutive_failures=2, open_until=clock.now() - timedelta(seconds=1))
    CircuitRow.objects.create(purpose="twexapi-global-pacing", fallback_owner=uuid.uuid4(),
                              fallback_lease_until=clock.now() + timedelta(seconds=40))
    failures = []
    original = SearchProviderCircuit.record_failure
    monkeypatch.setattr(SearchProviderCircuit, "record_failure",
                        lambda self, now: failures.append(self.purpose) or original(self, now))
    probe_while_waiting = []
    sleep = clock.sleep

    def watching_sleep(seconds):
        probe_while_waiting.append(CircuitRow.objects.get(purpose=twex_circuit.purpose).probe_owner)
        sleep(seconds)

    from x_monitor import x_client
    monkeypatch.setattr(x_client, "_sleep", watching_sleep)
    seen_probe_at_send = []

    def transport(url, params, headers):
        seen_probe_at_send.append(CircuitRow.objects.get(purpose=twex_circuit.purpose).probe_owner)
        clock.advance(1.4)
        return _response({"code": 200, "data": _twex_items(clock, "C3", 1, 1), "has_next_page": False})

    monkeypatch.setattr(client, "_twex_transport", transport)

    posts, truncated = client.run_search("C3", can_wait_for_rate_limit=lambda seconds: True)

    assert len(posts) == 1 and not truncated
    assert failures == []
    assert set(probe_while_waiting) == {None}
    assert seen_probe_at_send and seen_probe_at_send[0] is not None
    row = CircuitRow.objects.get(purpose=twex_circuit.purpose)
    assert row.open_until is None and row.probe_owner is None


@pytest.mark.parametrize("second_try", ["recovers", "keeps_failing"])
def test_continuation_429_without_retry_after_retries_the_same_cursor(monkeypatch, clock, second_try):
    """KTD4: a refused continuation is retried on the same route and cursor
    after 5 s (TwexAPI 429 without Retry-After) and then 15 s; when both
    retries fail the received posts are kept and the walk ends incomplete."""
    client = _routed_client(order=("twexapi",))
    if second_try == "recovers":
        script = [("page", 2, "c2"), ("status", 429), ("page", 1, None)]
    else:
        script = [("page", 2, "c2"), ("status", 429), ("status", 503), ("status", 503)]
    twex = TwexScript(clock, {"B2": script})
    monkeypatch.setattr(client, "_twex_transport", twex)

    posts, truncated = client.run_search("B2", can_wait_for_rate_limit=lambda seconds: True)

    if second_try == "recovers":
        assert len(posts) == 3 and not truncated
        assert [cursor for _, cursor in twex.requests] == [None, "c2", "c2"]
        assert client.route_wait_seconds == 5
    else:
        assert len(posts) == 2 and truncated
        assert [cursor for _, cursor in twex.requests] == [None, "c2", "c2", "c2"]
        assert client.route_wait_seconds == 5 + 15


def test_continuation_cursor_is_never_sent_to_another_provider(monkeypatch, clock):
    client = _routed_client()
    sent = []

    def tapi_get(url, params=None, headers=None, timeout=None):
        sent.append(params.get("cursor"))
        if params.get("cursor"):
            clock.advance(15)
            raise requests.Timeout("continuation timed out")
        return _response({"tweets": _tapi_items(clock, "B4", 1, 2), "has_next_page": True, "next_cursor": "t2"})

    monkeypatch.setattr("x_monitor.x_client.requests.get", tapi_get)
    monkeypatch.setattr(client, "_twex_transport", lambda *a: pytest.fail("cursor moved to TwexAPI"))

    posts, truncated = client.run_search("B4", can_wait_for_rate_limit=lambda seconds: True)

    assert len(posts) == 2 and truncated
    assert sent == [None, "t2", "t2", "t2"]
