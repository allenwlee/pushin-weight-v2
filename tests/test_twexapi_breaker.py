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
    assert len(posts) == 1 and incomplete
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
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientServerError

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
    assert len(posts) == 27 and incomplete
    assert calls == [("C2", None), ("C2", "second"), ("C2", "third")]
    if provider == "twexapi":
        assert len(client.run_search("B3")[0]) == 1
        assert calls[-1] == ("B3", None)
    else:
        with pytest.raises(XClientServerError, match="no configured"):
            client.run_search("B3")


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


def test_interrupted_search_releases_recovery_probe(monkeypatch):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient

    now = timezone.now()
    circuit = SearchProviderCircuit("interrupted", provider="twexapi", endpoint_family="search",
                                    threshold=1, cooldown=0)
    circuit.record_failure(now)
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("interrupted-history"),
                     twex_circuit=circuit, provider_order=("twexapi",))
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *args, **kwargs: {
        "code": 200, "data": [{"tweet_id": "1", "user": {}}], "has_next_page": True, "next_cursor": "next"})
    pages = client._iter_search_pages("interrupted", 20)
    next(pages)
    other = SearchProviderCircuit("interrupted", provider="twexapi", endpoint_family="search")
    assert not other.primary_permitted(timezone.now())
    pages.close()
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


def test_scheduled_failure_uses_on_demand_and_persists_independent_circuits(monkeypatch):
    from core.models import SearchProviderCircuit as CircuitRow
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient, XClientServerError

    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "scheduled-fixture")
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "ondemand-fixture")
    monkeypatch.delenv("TWEXAPI_API_KEY", raising=False)
    monkeypatch.delenv("X_DATA_PROVIDER_ORDER", raising=False)
    client = XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)
    seen = []
    def fake_get(*args, **kwargs):
        seen.append(kwargs["credential"])
        if seen[-1] == "scheduled-fixture": raise XClientServerError("503")
        return {"tweets": [], "has_next_page": False}
    monkeypatch.setattr(client, "_get", fake_get)
    assert client.run_search("Qwen") == ([], False)
    assert seen == ["scheduled-fixture", "ondemand-fixture"]
    first = CircuitRow.objects.get(purpose=client.provider_circuits["twitterapi:scheduled"].purpose)
    second = CircuitRow.objects.get(purpose=client.provider_circuits["twitterapi:on_demand"].purpose)
    assert first.open_until is not None and second.open_until is None


@pytest.mark.parametrize("route", ["twitterapi:scheduled", "twexapi"])
@pytest.mark.parametrize(("tail", "incomplete"), [
    ({"has_next_page": False}, False),
    ({}, True),
    ({"has_next_page": False, "next_cursor": "contradiction"}, True),
    ({"has_next_page": True}, True),
])
def test_routed_continuation_requires_explicit_end(monkeypatch, route, tail, incomplete):
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
    assert ([p["id"] for p in posts], truncated, calls) == (["123"], incomplete, [None, "page-2"])
    assert circuit.primary_permitted(timezone.now()) == (not incomplete)


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
    assert client.run_search("Qwen", since_time=10, until_time=20)[1]
    assert new_client().run_search("Qwen", since_time=20, until_time=30)[1]
    assert new_client().run_search("DeepSeek")[1]
    assert new_client().run_search("B3")[1]
    assert calls == [(q, c) for q in ("Qwen", "Qwen", "DeepSeek", "B3") for c in (None, "next")]


@pytest.mark.parametrize("rate_limited", [False, True])
def test_saved_twex_empty_tail_preserves_real_failures(monkeypatch, rate_limited):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientServerError

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
    with pytest.raises(XClientServerError, match="empty page"):
        next(client.run_search_pages("Qwen", cursor="twexapi:saved"))
    if rate_limited:
        assert not route.primary_permitted(now + timedelta(seconds=44))
        assert route.primary_permitted(now + timedelta(seconds=46))
    else:
        assert route.primary_permitted(now)
        route.record_failure(now)
        assert not route.primary_permitted(now)


@pytest.mark.parametrize("next_cursor", ["saved", {"bad": "cursor"}])
def test_invalid_twex_cursor_remains_a_failure(monkeypatch, next_cursor):
    from x_monitor.search_provider_circuit import SearchProviderCircuit
    from x_monitor.x_client import XClient, XClientServerError

    route = SearchProviderCircuit("bad-cursor", threshold=1)
    client = XClient(api_key="", twexapi_key="fixture", circuit=SearchProviderCircuit("history"),
                     twex_circuit=route, provider_order=("twexapi",))
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: {
        "code": 200, "data": [], "has_next_page": True, "next_cursor": next_cursor})
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
