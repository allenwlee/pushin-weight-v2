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
    with pytest.raises(XClientServerError):
        client.run_search("example")
    client.run_search("example")
    from core.models import SearchProviderCircuit as CircuitRow
    CircuitRow.objects.filter(purpose=twex.purpose).update(open_until=timezone.now() - timedelta(seconds=1))
    client.run_search("example")
    assert calls == ["twexapi", "twitterapi", "twexapi"]
    assert CircuitRow.objects.get(purpose=twex.purpose).open_until is None


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
