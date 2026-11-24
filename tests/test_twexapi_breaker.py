"""Cross-process search health state; local PostgreSQL fixtures only."""
from datetime import timedelta

import pytest
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_circuit_persists_failures_and_half_open_probe_lease():
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    first = SearchProviderCircuit("scheduled", threshold=2, cooldown=60)
    assert first.primary_permitted(now)
    first.record_failure(now)
    second = SearchProviderCircuit("scheduled", threshold=2, cooldown=60)
    assert second.primary_permitted(now)
    second.record_failure(now)
    assert not first.primary_permitted(now + timedelta(seconds=1))
    assert first.primary_permitted(now + timedelta(seconds=61))
    assert not second.primary_permitted(now + timedelta(seconds=61))
    first.record_success(now + timedelta(seconds=62))
    assert second.primary_permitted(now + timedelta(seconds=63))


def test_fallback_pacing_uses_shared_lease_and_actual_completion():
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    scheduled = SearchProviderCircuit("scheduled")
    ondemand = SearchProviderCircuit("on-demand")
    assert scheduled.acquire_fallback(now, 20) == 0
    assert ondemand.acquire_fallback(now + timedelta(seconds=10), 20) > 0
    scheduled.release_fallback(now + timedelta(seconds=12), 6)
    assert ondemand.acquire_fallback(now + timedelta(seconds=17), 20) == 1
    assert ondemand.acquire_fallback(now + timedelta(seconds=18), 20) == 0


def test_expired_probe_cannot_close_newer_probe():
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    old = SearchProviderCircuit("scheduled", threshold=1, cooldown=1, probe_lease=2)
    new = SearchProviderCircuit("scheduled", threshold=1, cooldown=1, probe_lease=2)
    old.record_failure(now)
    assert old.primary_permitted(now + timedelta(seconds=2))
    assert new.primary_permitted(now + timedelta(seconds=5))
    old.record_success(now + timedelta(seconds=5))
    assert not SearchProviderCircuit("scheduled").primary_permitted(now + timedelta(seconds=5))
    new.record_success(now + timedelta(seconds=6))
    assert old.primary_permitted(now + timedelta(seconds=7))


def test_probe_keeps_failures_until_a_complete_search():
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    circuit = SearchProviderCircuit("intermediate-probe", threshold=2, cooldown=1)
    circuit.record_failure(now)
    circuit.record_failure(now)
    assert circuit.primary_permitted(now + timedelta(seconds=2))
    assert not SearchProviderCircuit("intermediate-probe").primary_permitted(now + timedelta(seconds=2))
    circuit.record_failure(now + timedelta(seconds=2))
    assert not circuit.primary_permitted(now + timedelta(seconds=2))
    assert circuit.primary_permitted(now + timedelta(seconds=4))
    circuit.record_success(now + timedelta(seconds=4))
    circuit.record_failure(now + timedelta(seconds=4))
    assert circuit.primary_permitted(now + timedelta(seconds=4))


def test_recovery_probe_renews_its_lease_and_cannot_revive_after_expiry():
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    circuit = SearchProviderCircuit("renew-probe", threshold=1, cooldown=1, probe_lease=10)
    other = SearchProviderCircuit("renew-probe", threshold=1, cooldown=1, probe_lease=10)
    circuit.record_failure(now)
    assert circuit.primary_permitted(now + timedelta(seconds=2))
    assert circuit.renew_probe(now + timedelta(seconds=10))
    assert not other.primary_permitted(now + timedelta(seconds=13))
    assert other.primary_permitted(now + timedelta(seconds=21))
    assert not circuit.renew_probe(now + timedelta(seconds=21))
    assert not circuit.is_probe()


def test_first_page_empty_is_suspicious_only_after_repeated_recent_nonempty_windows():
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    circuit = SearchProviderCircuit("scheduled")
    quiet = "rare lang:ja since_time:100 until_time:200"
    assert not circuit.observe_query(quiet, nonempty=False, now=now)
    for i in range(3):
        assert not circuit.observe_query(f"DeepSeek since_time:{i} until_time:{i + 1}", nonempty=True, now=now)
    assert circuit.observe_query("DeepSeek since_time:5 until_time:6", nonempty=False, now=now)
    assert not circuit.observe_query("DeepSeek since_time:7 until_time:8", nonempty=False, now=now + timedelta(hours=1))


@pytest.mark.parametrize("threshold", [1, 2])
def test_twex_empty_continuation_allows_an_independent_query(monkeypatch, threshold):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    twex = SearchProviderCircuit("isolated-partial", provider="twexapi", endpoint_family="search",
                                 threshold=threshold, cooldown=180)
    history = SearchProviderCircuit("isolated-history")
    client = XClient(api_key="", twexapi_key="fixture", circuit=history, twex_circuit=twex,
                     provider_order=("twexapi",))
    responses = iter([
        {"code": 200, "data": [{"tweet_id": "1", "user": {}}], "has_next_page": True, "next_cursor": "one"},
        {"code": 200, "data": [], "has_next_page": True, "next_cursor": "two"},
        {"code": 200, "data": [{"tweet_id": "2", "user": {}}], "has_next_page": False, "next_cursor": None},
    ])
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *args, **kwargs: next(responses))
    posts, incomplete = client.run_search("first")
    # Owner decision 2026-11-24 (R5/KTD7, TwexAPI only): the first empty page
    # ends the search complete, cursor or not.
    assert len(posts) == 1 and not incomplete
    posts, incomplete = client.run_search("independent")
    assert len(posts) == 1 and not incomplete


def test_scheduled_breaker_threshold_setting_applies_to_both_providers(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient

    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "fake-primary")
    monkeypatch.setenv("TWEXAPI_API_KEY", "fake-twex")
    monkeypatch.setenv("X_DATA_PROVIDER_ORDER", "twexapi,twitterapi:scheduled")
    monkeypatch.setenv("TWEXAPI_BREAKER_FAILURE_THRESHOLD", "2")
    client = XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)
    assert client.twex_circuit.threshold == 2
    assert client.provider_circuits["twitterapi:scheduled"].threshold == 2


@pytest.mark.parametrize("provider", ["twexapi", "twitterapi:scheduled"])
def test_provider_rules_for_live_c2_page_sequence(monkeypatch, provider):
    """Live C2 shape: 20, 7, then an empty page that still offers a cursor.

    Owner decision 2026-11-24 (R5/KTD7): TwexAPI ends there complete.
    TwitterAPI.io end-of-results rules are unchanged (still incomplete), and
    KTD2 makes that a query outcome: it no longer blocks the next keyword.
    """
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    route = SearchProviderCircuit("live-c2", provider=provider, endpoint_family="search", threshold=1)
    client = XClient(api_key="fixture", twexapi_key="fixture", circuit=route, twex_circuit=route,
                     provider_order=(provider,), provider_circuits={provider: route})
    calls = []

    def fetch(query, cursor):
        calls.append((query, cursor))
        count = {None: 20, "second": 7, "third": 0}[cursor] if query == "C2" else 1
        items = [{"id": str(len(calls) * 100 + i)} for i in range(count)]
        return {"code": 200, "data": items, "tweets": items, "has_next_page": query == "C2",
                "next_cursor": {None: "second", "second": "third", "third": "fourth"}[cursor] if query == "C2" else None}

    monkeypatch.setattr(client, "_twex_search_with_retry", lambda q, c, **kw: fetch(q, c))
    monkeypatch.setattr(client, "_get", lambda path, params, **kw: fetch(params["query"], params.get("cursor")))
    posts, incomplete = client.run_search("C2")
    assert len(posts) == 27 and incomplete == (provider != "twexapi")
    assert calls == [("C2", None), ("C2", "second"), ("C2", "third")]
    assert len(client.run_search("B3")[0]) == 1
    assert calls[-1] == ("B3", None)


def test_successfully_bounded_search_resets_previous_failure(monkeypatch):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    circuit = SearchProviderCircuit("bounded-search", provider="twexapi", endpoint_family="search", threshold=2)
    circuit.record_failure(timezone.now())
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("bounded-history"),
                     twex_circuit=circuit, provider_order=("twexapi",))
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *args, **kwargs: {
        "code": 200, "data": [{"tweet_id": "1", "user": {}}], "has_next_page": True, "next_cursor": "next"})
    list(client._iter_search_pages("bounded", 1, max_pages=1))
    circuit.record_failure(timezone.now())
    assert circuit.primary_permitted(timezone.now())


def _twex_response(body, status=200, headers=None):
    import json

    from requests import Response

    response = Response()
    response.status_code = status
    response.headers.update(headers or {})
    response._content = json.dumps(body).encode()
    return response


def test_interrupted_search_releases_recovery_probe(monkeypatch):
    """KTD1: the TwexAPI probe is claimed only after the pacing slot is held
    and is released on every non-route outcome (here the deadline). KTD2:
    with success recorded per valid page, the first valid page closes the
    recovering route instead of holding the probe for the whole walk."""
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    now = timezone.now()
    circuit = SearchProviderCircuit("interrupted", provider="twexapi", endpoint_family="search",
                                    threshold=1, cooldown=0)
    circuit.record_failure(now)
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("interrupted-history"),
                     twex_circuit=circuit, provider_order=("twexapi",), twexapi_interval_s=0.001)
    monkeypatch.setattr(client, "_twex_transport", lambda *a: _twex_response(
        {"code": 200, "data": [{"tweet_id": "1", "user": {}}], "has_next_page": True, "next_cursor": "next"}))
    admissions = []

    def admit():
        admissions.append(True)
        return len(admissions) < 3  # refuse right after the probe is claimed

    with pytest.raises(TimeoutError):
        next(client._iter_search_pages("interrupted", 20, can_start_page=admit))
    row = CircuitRow.objects.get(purpose=circuit.purpose)
    assert row.probe_owner is None and row.open_until is not None
    pages = client._iter_search_pages("interrupted", 20)
    next(pages)
    assert CircuitRow.objects.get(purpose=circuit.purpose).open_until is None
    pages.close()
    other = SearchProviderCircuit("interrupted", provider="twexapi", endpoint_family="search")
    assert other.primary_permitted(timezone.now())


def test_twex_transport_has_wall_clock_and_byte_bounds(monkeypatch):
    from x_monitor.x_client import XClient
    client = XClient(api_key="primary", search_timeout_s=12)
    captured = []
    monkeypatch.setattr(client, "_bounded_request", lambda *args, **kwargs: captured.append((args, kwargs)))
    client._twex_transport("https://api.twexapi.io/test", {"searchTerms": ["x"]}, {})
    assert captured[0][0] == ("POST", "https://api.twexapi.io/test", 12)
    assert captured[0][1]["max_bytes"] == 8 * 1024 * 1024


def test_rate_limit_cooldown_is_shared_between_independent_clients(monkeypatch):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientRateLimitError

    class Response:
        status_code = 429
        headers = {"Retry-After": "45"}
        content = b'{}'

    first = SearchProviderCircuit("scheduled")
    second = SearchProviderCircuit("on-demand")
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=first, max_retries=0)
    monkeypatch.setattr(client, "_twex_transport", lambda *a: Response())
    with pytest.raises(XClientRateLimitError):
        client._twex_search_with_retry("busy", None)
    assert second.acquire_fallback(timezone.now(), 45) > 40


def test_provider_and_endpoint_family_have_independent_circuits():
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    failed = SearchProviderCircuit("scheduled", provider="twitterapi", endpoint_family="search", threshold=1)
    other_family = SearchProviderCircuit("scheduled", provider="twitterapi", endpoint_family="user_info", threshold=1)
    other_provider = SearchProviderCircuit("scheduled", provider="twexapi", endpoint_family="search", threshold=1)
    failed.record_failure(now)
    assert not failed.primary_permitted(now)
    assert other_family.primary_permitted(now)
    assert other_provider.primary_permitted(now)
    assert CircuitRow.objects.get(purpose=failed.purpose).provider == "twitterapi"
    assert CircuitRow.objects.get(purpose=failed.purpose).endpoint_family == "search"


def test_twex_first_falls_back_and_then_probes_recovery(monkeypatch):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientServerError

    twex = SearchProviderCircuit("scheduled", provider="twexapi", endpoint_family="search", threshold=1, cooldown=1)
    primary = SearchProviderCircuit("scheduled", provider="twitterapi", endpoint_family="search", threshold=1, cooldown=1)
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=primary, twex_circuit=twex,
                     provider_order=("twexapi", "twitterapi"))
    calls = []
    def twex_response(*args, **kwargs):
        calls.append("twexapi")
        if calls.count("twexapi") == 1:
            raise XClientServerError("503")
        return {"code": 200, "data": [{"tweet_id": "1", "user": {}}], "has_next_page": False}
    monkeypatch.setattr(client, "_twex_search_with_retry", twex_response)
    monkeypatch.setattr(client, "_get", lambda *a, **kw: calls.append("twitterapi") or {"tweets": [], "has_next_page": False})
    assert client.run_search("example") == ([], False)
    assert calls == ["twexapi", "twitterapi"]
    assert client.run_search("example") == ([], False)
    from core.models import SearchProviderCircuit as CircuitRow
    CircuitRow.objects.filter(purpose=twex.purpose).update(open_until=timezone.now() - timedelta(seconds=1))
    client.run_search("example")
    assert calls == ["twexapi", "twitterapi", "twitterapi", "twexapi"]
    assert CircuitRow.objects.get(purpose=twex.purpose).open_until is None


@pytest.mark.parametrize("provider", ["twitterapi", "twexapi"])
def test_quiet_query_closes_recovery_probe_and_allows_next_search(monkeypatch, provider):
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    now = timezone.now()
    primary = SearchProviderCircuit("scheduled", provider="twitterapi", endpoint_family="search", threshold=1)
    twex = SearchProviderCircuit("scheduled", provider="twexapi", endpoint_family="search", threshold=1)
    selected = primary if provider == "twitterapi" else twex
    selected.record_failure(now - timedelta(minutes=4))
    client = XClient(
        api_key="primary", twexapi_key="secondary", circuit=primary,
        twex_circuit=twex, provider_order=(provider,),
    )
    calls = []
    monkeypatch.setattr(client, "_get", lambda *a, **kw: calls.append("twitterapi") or {
        "tweets": [], "has_next_page": False,
    })
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: calls.append("twexapi") or {
        "code": 200, "data": [], "has_next_page": False,
    })

    assert client.run_search("quiet search") == ([], False)
    assert CircuitRow.objects.get(purpose=selected.purpose).open_until is None
    assert client.run_search("another quiet search") == ([], False)
    assert calls == [provider, provider]


def test_scheduled_failure_never_uses_on_demand_and_circuits_stay_independent(monkeypatch):
    """Owner decision 2026-11-24: scheduled collection never sends the
    on-demand key. With both TwitterAPI.io keys and no TwexAPI key, the
    scheduled client is the single-provider baseline on the scheduled key;
    independent per-credential circuits are pinned on the on-demand client."""
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient, XClientServerError

    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "scheduled-fixture")
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "ondemand-fixture")
    monkeypatch.delenv("TWEXAPI_API_KEY", raising=False)
    monkeypatch.delenv("X_DATA_PROVIDER_ORDER", raising=False)
    scheduled = XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)
    assert scheduled.api_key == "scheduled-fixture" and not scheduled.provider_circuits
    assert (scheduled.timeout_s, scheduled.max_retries) == (60, 2)
    client = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    seen = []
    def fake_get(*args, **kwargs):
        seen.append(kwargs["credential"])
        if seen[-1] == "ondemand-fixture": raise XClientServerError("503")
        return {"tweets": [], "has_next_page": False}
    monkeypatch.setattr(client, "_get", fake_get)
    assert client.run_search("Qwen") == ([], False)
    assert seen == ["ondemand-fixture", "scheduled-fixture"]
    first = CircuitRow.objects.get(purpose=client.provider_circuits["twitterapi:on_demand"].purpose)
    second = CircuitRow.objects.get(purpose=client.provider_circuits["twitterapi:scheduled"].purpose)
    assert first.consecutive_failures == 1 and second.open_until is None


@pytest.mark.parametrize("route", ["twitterapi:scheduled", "twexapi"])
@pytest.mark.parametrize(("tail", "incomplete"), [
    ({"has_next_page": False}, False),
    ({}, True),
    ({"has_next_page": False, "next_cursor": "contradiction"}, True),
    ({"has_next_page": True}, True),
])
def test_routed_continuation_requires_explicit_end(monkeypatch, route, tail, incomplete):
    """TwitterAPI.io keeps its explicit-end rule. Owner decision 2026-11-24
    (R5/KTD7): a TwexAPI empty page ends the search complete whatever its
    tail says. KTD2: the route answered, so it is healthy either way."""
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    circuit = SearchProviderCircuit("terminal-fixture", threshold=1)
    circuit.record_failure(timezone.now() - timedelta(minutes=10))
    client = XClient(api_key="fixture", twexapi_key="fixture", circuit=circuit, twex_circuit=circuit,
                     provider_order=(route,), provider_circuits={route: circuit})
    bodies = iter([{"has_next_page": True, "next_cursor": "page-2"}, tail])
    calls = []

    def fetch(cursor):
        calls.append(cursor)
        items = [{"id": "123"}] if cursor is None else []
        return {"tweets": items, "code": 200, "data": items, **next(bodies)}

    monkeypatch.setattr(client, "_get", lambda path, params, **kw: fetch(params.get("cursor")))
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda query, cursor, **kw: fetch(cursor))
    posts, truncated = client.run_search("Qwen")
    expected = incomplete and route != "twexapi"
    assert ([p["id"] for p in posts], truncated, calls) == (["123"], expected, [None, "page-2"])
    assert circuit.primary_permitted(timezone.now())


def test_twex_recovery_can_dispatch_after_multiple_incomplete_windows(monkeypatch):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    def new_client():
        route = SearchProviderCircuit("resume-fixture", provider="twexapi", endpoint_family="search", threshold=2)
        return XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                       twex_circuit=route, provider_order=("twexapi",))

    client = new_client()
    for _ in range(2):
        client.twex_circuit.record_failure(timezone.now() - timedelta(minutes=10))
    calls = []

    def fetch(self, query, cursor, **kwargs):
        calls.append((query.split()[0], cursor))
        return {"code": 200, "data": [] if cursor else [{"tweet_id": "1"}],
                "has_next_page": True, "next_cursor": "tail" if cursor else "next"}

    monkeypatch.setattr(XClient, "_twex_search_with_retry", fetch)
    # Owner decision 2026-11-24 (R5/KTD7): each walk ends complete at its
    # empty page, and the recovered route keeps dispatching.
    assert not client.run_search("Qwen", since_time=10, until_time=20)[1]
    assert not new_client().run_search("Qwen", since_time=20, until_time=30)[1]
    assert not new_client().run_search("DeepSeek")[1]
    assert not new_client().run_search("B3")[1]
    assert calls == [(q, c) for q in ("Qwen", "Qwen", "DeepSeek", "B3") for c in (None, "next")]


@pytest.mark.parametrize("rate_limited", [False, True])
def test_saved_twex_empty_tail_is_complete_and_keeps_rate_limit(monkeypatch, rate_limited):
    """``run_search_pages(cursor=...)`` is the X post backfill's serial path
    (monitor/cycle.py ``_fetch_backfill_pages``). Owner decision 2026-11-24
    (R5/KTD7) applies there too: an empty TwexAPI page ends the walk
    complete. A valid page resets earlier failures (KTD2) but never clears a
    provider rate limit recorded meanwhile."""
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    now = timezone.now()
    route = SearchProviderCircuit("saved-cursor", provider="twexapi", endpoint_family="search", threshold=2)
    route.record_failure(now)
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                     twex_circuit=route, provider_order=("twexapi",))

    def fetch(query, cursor, **options):
        if rate_limited:
            route.record_rate_limit(now, 45)
        return {"code": 200, "data": [], "has_next_page": True, "next_cursor": "ambiguous"}

    monkeypatch.setattr(client, "_twex_search_with_retry", fetch)
    pages = list(client.run_search_pages("Qwen", cursor="twexapi:saved"))
    assert len(pages) == 1 and not pages[0].items
    assert not pages[0].has_more and pages[0].ended_on_empty_page
    if rate_limited:
        assert not route.primary_permitted(now + timedelta(seconds=44))
        assert route.primary_permitted(now + timedelta(seconds=46))
    else:
        assert route.primary_permitted(now)
        route.record_failure(now)
        assert route.primary_permitted(now)


@pytest.mark.parametrize("next_cursor", ["saved", {"bad": "cursor"}])
def test_invalid_twex_cursor_remains_a_failure(monkeypatch, next_cursor):
    """A malformed (non-string) cursor is an unusable response: a route
    failure. Owner decision 2026-11-24 (R5/KTD7): an empty page that repeats
    the requested cursor is still an empty page, so the walk ends complete."""
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientServerError

    route = SearchProviderCircuit("bad-cursor", threshold=1)
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                     twex_circuit=route, provider_order=("twexapi",))
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: {
        "code": 200, "data": [], "has_next_page": True, "next_cursor": next_cursor})
    if isinstance(next_cursor, str):
        page = next(client.run_search_pages("Qwen", cursor="twexapi:saved"))
        assert not page.has_more and not page.items
        assert route.primary_permitted(timezone.now())
        return
    with pytest.raises(XClientServerError):
        next(client.run_search_pages("Qwen", cursor="twexapi:saved"))
    assert not route.primary_permitted(timezone.now())


def test_forced_raw_receipt_429_keeps_provider_retry_after(monkeypatch):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientRateLimitError

    now = timezone.now()
    route = SearchProviderCircuit("raw-probe", threshold=1, cooldown=1, probe_lease=10)
    route.record_failure(now - timedelta(minutes=1))
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                     twex_circuit=route, provider_order=("twexapi",), force_twexapi=True)

    def throttled(*args, **kwargs):
        error = XClientRateLimitError("429")
        error.retry_after_seconds = 45
        raise error

    monkeypatch.setattr(client, "_twex_search_with_retry", throttled)
    with pytest.raises(XClientRateLimitError):
        client.run_search_page_with_raw("Qwen", since_time=10, until_time=20)
    assert not route.primary_permitted(now + timedelta(seconds=40))
    assert route.primary_permitted(now + timedelta(seconds=46))


def test_quiet_twex_first_page_is_complete_and_heals_the_route(monkeypatch):
    """Owner decision 2026-11-24 (R5/KTD7): an empty TwexAPI first page that
    offers a cursor is a complete, quiet window (was: held). KTD2: the valid
    page resets the route's earlier failure."""
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    route = SearchProviderCircuit("C4", threshold=1)
    route.record_failure(timezone.now() - timedelta(minutes=10))
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                     twex_circuit=route, provider_order=("twexapi",))
    calls = []

    def fetch(query, cursor, **options):
        calls.append((query, cursor))
        if query == "C4":
            return {"code": 200, "data": [], "has_next_page": True, "next_cursor": "opaque"}
        return {"code": 200, "data": [{"id": "23"}], "has_next_page": False}

    monkeypatch.setattr(client, "_twex_search_with_retry", fetch)
    assert client.run_search("C4") == ([], False)
    row = CircuitRow.objects.get(purpose=route.purpose)
    assert row.consecutive_failures == 0 and row.open_until is None and row.probe_owner is None
    assert [item["id"] for item in client.run_search("B3")[0]] == ["23"]
    assert calls == [("C4", None), ("B3", None)]


@pytest.mark.parametrize(("delay", "budget", "waits"), [(6, 15, 8), (6, 2, 0), (60, 90, 8)])
def test_scheduled_keyword_after_real_429_waits_within_its_admission(monkeypatch, delay, budget, waits):
    """KTD1 replaces the once-per-cycle <=30 s wait of b71090c1: a first-page
    429 keeps the route eligible after its reset, so each keyword waits for
    it whenever the caller admits the wait, up to three attempts per call.
    A wait the caller cannot admit sends nothing further."""
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor import x_client
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientRateLimitError, XClientServerError

    route = SearchProviderCircuit("rate-window", threshold=1)
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                     twex_circuit=route, provider_order=("twexapi",))
    sleeps, calls = [], []

    def fetch(query, cursor, **options):
        calls.append(query)
        exc = XClientRateLimitError("busy")
        exc.retry_after_seconds = delay
        raise exc

    def sleep(seconds):
        assert 0 < seconds <= delay
        sleeps.append(seconds)
        CircuitRow.objects.filter(purpose=route.purpose).update(open_until=timezone.now() - timedelta(seconds=1))

    monkeypatch.setattr(client, "_twex_search_with_retry", fetch)
    monkeypatch.setattr(x_client.time, "sleep", sleep)
    for query in ["C2", "B3", "C7"]:
        with pytest.raises((XClientRateLimitError, XClientServerError)):
            client.run_search(query, can_wait_for_rate_limit=lambda seconds: seconds <= budget)
    assert len(sleeps) == waits
    assert calls == ([q for q in ["C2", "B3", "C7"] for _ in range(3)] if waits else ["C2"])


def test_available_fallback_takes_priority_over_waiting(monkeypatch):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientRateLimitError

    twex = SearchProviderCircuit("busy-twex")
    primary = SearchProviderCircuit("healthy-twitterapi")
    client = XClient(api_key="one", twexapi_key="two", circuit=primary, twex_circuit=twex,
                     provider_order=("twexapi", "twitterapi"))
    calls = []

    def limited(*args, **options):
        calls.append("twexapi")
        error = XClientRateLimitError("busy")
        error.retry_after_seconds = 6
        raise error

    def available(*args, **options):
        calls.append("twitterapi")
        return {"tweets": [{"id": "42"}], "has_next_page": False}

    monkeypatch.setattr(client, "_twex_search_with_retry", limited)
    monkeypatch.setattr(client, "_get", available)
    for query in ["C2", "B3"]:
        posts, truncated = client.run_search(query, can_wait_for_rate_limit=lambda delay: pytest.fail("needless wait"))
        assert [item["id"] for item in posts] == ["42"] and not truncated
    assert calls == ["twexapi", "twitterapi", "twitterapi"]


def test_continuation_429_keeps_prefix_and_next_keyword_recovers(monkeypatch):
    """KTD4: a refused continuation is retried twice on the same route and
    cursor (5 s, then 15 s, or the provider's later reset); the prefix is kept
    and the next keyword waits for the route's reset (KTD1)."""
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor import x_client
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientRateLimitError

    route = SearchProviderCircuit("continuation-429")
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                     twex_circuit=route, provider_order=("twexapi",))
    calls = []

    def fetch(query, cursor, **options):
        calls.append((query, cursor))
        if cursor:
            exc = XClientRateLimitError("busy")
            exc.retry_after_seconds = 6
            raise exc
        return {"code": 200, "data": [{"id": query}], "has_next_page": query == "C2",
                "next_cursor": "second" if query == "C2" else None}

    sleeps = []

    def sleep(seconds):
        assert 0 < seconds <= 15
        sleeps.append(seconds)
        CircuitRow.objects.filter(purpose=route.purpose).update(open_until=timezone.now() - timedelta(seconds=1))

    monkeypatch.setattr(client, "_twex_search_with_retry", fetch)
    monkeypatch.setattr(x_client.time, "sleep", sleep)
    for query in ["C2", "B3", "C7"]:
        posts, truncated = client.run_search(query, can_wait_for_rate_limit=lambda seconds: True)
        assert [post["id"] for post in posts] == [query] and truncated == (query == "C2")
    assert calls == [("C2", None), ("C2", "second"), ("C2", "second"), ("C2", "second"),
                     ("B3", None), ("C7", None)]
    assert sleeps[1] == 15 and 5 <= sleeps[0] <= 6


def test_raw_first_page_returns_original_receipt_and_holds_window(monkeypatch):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    route = SearchProviderCircuit("raw-empty", threshold=1)
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                     twex_circuit=route, provider_order=("twexapi",))
    data = {"code": 200, "data": [], "has_next_page": True, "next_cursor": "opaque"}
    raw = b'{"code":200,"data":[],"has_next_page":true,"next_cursor":"opaque"}'
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: (raw, data))
    assert client.run_search_page_with_raw("C4", since_time=10, until_time=20) == (raw, data, [], True, 0)
    assert route.primary_permitted(timezone.now())


# --- U3 (plan 2026-11-24-012909): route-health accounting and cooldown ladder


def _row(circuit):
    from core.models import SearchProviderCircuit as CircuitRow

    return CircuitRow.objects.get(purpose=circuit.purpose)


def test_route_failing_transport_on_every_continuation_still_opens(monkeypatch):
    """Re-added form of the test df0ce924 removed. Success is recorded on
    every valid page (KTD2), yet a route whose continuations always time out
    still opens: the same-route retries (KTD4) are consecutive failures."""
    import requests

    from x_monitor import x_client
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    route = SearchProviderCircuit("continuation-transport", provider="twitterapi",
                                  endpoint_family="search", threshold=2, cooldown=180)
    client = XClient(api_key="fixture", circuit=route, provider_order=("twitterapi:scheduled",),
                     provider_credentials={"twitterapi:scheduled": "fixture"},
                     provider_circuits={"twitterapi:scheduled": route})

    def get(path, params, **kwargs):
        if params.get("cursor"):
            raise requests.Timeout("continuation timed out")
        return {"tweets": [{"id": params["query"]}], "has_next_page": True, "next_cursor": "page-2"}

    monkeypatch.setattr(client, "_get", get)
    monkeypatch.setattr(x_client, "_sleep", lambda seconds: None)
    posts, truncated = client.run_search("Qwen", can_wait_for_rate_limit=lambda seconds: True)
    assert [post["id"] for post in posts] == ["Qwen"] and truncated
    assert _row(route).open_until is not None


def test_one_twex_503_between_valid_pages_does_not_open_at_threshold_two(monkeypatch):
    from x_monitor import x_client
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientServerError

    route = SearchProviderCircuit("single-503", provider="twexapi", endpoint_family="search", threshold=2)
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                     twex_circuit=route, provider_order=("twexapi",))
    answers = iter(["page", "503", "page", "end"])

    def fetch(query, cursor, **options):
        answer = next(answers)
        if answer == "503":
            error = XClientServerError("TwexAPI 5xx: 503")
            error.response_status_code = 503
            raise error
        if answer == "end":
            return {"code": 200, "data": [], "has_next_page": True, "next_cursor": "tail"}
        return {"code": 200, "data": [{"tweet_id": str(cursor)}], "has_next_page": True,
                "next_cursor": f"after-{cursor}"}

    monkeypatch.setattr(client, "_twex_search_with_retry", fetch)
    monkeypatch.setattr(x_client, "_sleep", lambda seconds: None)
    posts, truncated = client.run_search("B1", can_wait_for_rate_limit=lambda seconds: True)
    assert len(posts) == 2 and not truncated
    row = _row(route)
    assert row.open_until is None and row.consecutive_failures == 0


@pytest.mark.parametrize("second_page", ["empty_continuation", "duplicate_only"])
def test_query_outcomes_never_count_against_the_route(monkeypatch, second_page):
    """KTD2: an empty continuation (TwitterAPI.io still incomplete) and a
    duplicate-only page end the query's walk but leave the route's failure
    count untouched."""
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    route = SearchProviderCircuit("query-outcome", provider="twitterapi", endpoint_family="search", threshold=1)
    client = XClient(api_key="fixture", circuit=route, provider_order=("twitterapi:scheduled",),
                     provider_credentials={"twitterapi:scheduled": "fixture"},
                     provider_circuits={"twitterapi:scheduled": route})

    def get(path, params, **kwargs):
        if not params.get("cursor"):
            return {"tweets": [{"id": "1"}], "has_next_page": True, "next_cursor": "page-2"}
        if second_page == "empty_continuation":
            return {"tweets": [], "has_next_page": True, "next_cursor": "page-3"}
        return {"tweets": [{"id": "1"}], "has_next_page": True, "next_cursor": "page-3"}

    monkeypatch.setattr(client, "_get", get)
    posts, truncated = client.run_search("Qwen")
    assert {post["id"] for post in posts} == {"1"} and truncated
    row = _row(route)
    assert row.consecutive_failures == 0 and row.open_until is None


def test_cooldown_ladder_escalates_then_stays_at_the_cap():
    """KTD3: 15, 30, 60, 120, 180 s, then 180 s; never longer than before."""
    from x_monitor.search_provider_circuit import SearchProviderCircuit, cooldown_ladder

    assert cooldown_ladder(180) == (15, 30, 60, 120, 180)
    now = timezone.now()
    route = SearchProviderCircuit("ladder", threshold=2, cooldown=180)
    route.record_failure(now)
    assert _row(route).open_until is None
    periods = []
    clock = now
    for _ in range(6):
        route.record_failure(clock)
        opened = _row(route).open_until
        periods.append(round((opened - clock).total_seconds()))
        clock = opened
        assert route.primary_permitted(clock)  # claim the half-open probe
    assert periods == [15, 30, 60, 120, 180, 180]


def test_old_failures_decay_so_the_next_crossing_opens_for_15_seconds():
    """KTD3 decay: failures older than twice the cap (360 s) no longer count."""
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    route = SearchProviderCircuit("decay", threshold=2, cooldown=180)
    route.record_failure(now)
    CircuitRow.objects.filter(purpose=route.purpose).update(updated_at=now - timedelta(seconds=361))
    route.record_failure(now)
    assert _row(route).open_until is None and _row(route).consecutive_failures == 1
    route.record_failure(now)
    assert round((_row(route).open_until - now).total_seconds()) == 15

    stale = SearchProviderCircuit("decay-open", threshold=2, cooldown=180)
    CircuitRow.objects.create(purpose=stale.purpose, consecutive_failures=7,
                              open_until=now - timedelta(seconds=361))
    assert stale.primary_permitted(now)
    stale.record_failure(now)
    assert round((_row(stale).open_until - now).total_seconds()) == 15


def test_rate_limit_uses_its_reset_and_never_counts_as_a_failure(monkeypatch):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientRateLimitError, XClientServerError

    route = SearchProviderCircuit("throttled", provider="twitterapi", endpoint_family="search", threshold=1)
    client = XClient(api_key="fixture", circuit=route, provider_order=("twitterapi:scheduled",),
                     provider_credentials={"twitterapi:scheduled": "fixture"},
                     provider_circuits={"twitterapi:scheduled": route})

    def limited(path, params, **kwargs):
        error = XClientRateLimitError("429")
        error.retry_after_seconds = 40
        raise error

    monkeypatch.setattr(client, "_get", limited)
    # Without an admitted wait the throttled call ends unsent (KTD1).
    with pytest.raises((XClientRateLimitError, XClientServerError)):
        client.run_search("Qwen")
    row = _row(route)
    assert row.consecutive_failures == 0
    assert 35 <= (row.open_until - timezone.now()).total_seconds() <= 40


def test_probe_success_closes_and_probe_failure_moves_one_ladder_step():
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    route = SearchProviderCircuit("probe-ladder", threshold=1, cooldown=180)
    route.record_failure(now)
    reopened = now + timedelta(seconds=15)
    assert route.primary_permitted(reopened)
    route.record_failure(reopened)
    assert round((_row(route).open_until - reopened).total_seconds()) == 30
    later = reopened + timedelta(seconds=30)
    assert route.primary_permitted(later)
    route.record_success(later)
    row = _row(route)
    assert row.open_until is None and row.consecutive_failures == 0


def test_two_processes_sharing_a_row_see_the_same_open_until():
    from x_monitor.search_provider_circuit import SearchProviderCircuit

    now = timezone.now()
    cron = SearchProviderCircuit("shared-key", provider="twexapi", endpoint_family="search", threshold=2)
    backfill = SearchProviderCircuit("shared-key", provider="twexapi", endpoint_family="search", threshold=2)
    cron.record_failure(now)
    backfill.record_failure(now)
    assert cron.next_eligible_at(now) == backfill.next_eligible_at(now) == _row(cron).open_until
    assert not backfill.primary_permitted(now + timedelta(seconds=1))
    assert cron.next_eligible_at(now + timedelta(seconds=16)) is None
