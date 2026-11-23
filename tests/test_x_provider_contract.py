"""The provider order is an explicit, validated operator choice."""
import pytest


def test_default_provider_order():
    from x_monitor.x_data_provider import parse_provider_order
    assert parse_provider_order(None) == ("twitterapi", "twexapi")


def test_reversed_provider_order():
    from x_monitor.x_data_provider import parse_provider_order
    assert parse_provider_order("twexapi,twitterapi") == ("twexapi", "twitterapi")


@pytest.mark.parametrize("value", ["", "twexapi,twexapi", "twitterapi,unknown", ",twitterapi"])
def test_invalid_provider_order_rejected(value):
    from x_monitor.x_data_provider import parse_provider_order
    with pytest.raises(ValueError):
        parse_provider_order(value)


def test_reversed_order_search_uses_twex_first_and_twitter_when_open(monkeypatch):
    from x_monitor.x_client import XClient

    class Circuit:
        def __init__(self, permitted): self.permitted = permitted
        def primary_permitted(self, now): return self.permitted
        def observe_query(self, *a, **kw): return False
        def is_probe(self): return False
        def record_success(self, now): pass
        def record_failure(self, now): pass
    primary = Circuit(True)
    twex = Circuit(True)
    client = XClient(api_key="primary", twexapi_key="second", circuit=primary,
                     twex_circuit=twex, provider_order=("twexapi", "twitterapi"))
    calls = []
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: calls.append("twexapi") or {"code": 200, "data": [], "has_next_page": False})
    monkeypatch.setattr(client, "_get", lambda *a, **kw: calls.append("twitterapi") or {"tweets": [], "has_next_page": False})
    client.run_search("query")
    twex.permitted = False
    client.run_search("query")
    assert calls == ["twexapi", "twitterapi"]


def test_reversed_twex_failure_opens_only_its_circuit(monkeypatch):
    from x_monitor.x_client import XClient, XClientServerError
    class Circuit:
        def __init__(self): self.failures = 0
        def primary_permitted(self, now): return self.failures == 0
        def record_failure(self, now): self.failures += 1
        def record_success(self, now): pass
        def observe_query(self, *a, **kw): return False
        def is_probe(self): return False
    primary, twex = Circuit(), Circuit()
    client = XClient(api_key="primary", twexapi_key="second", circuit=primary,
                     twex_circuit=twex, provider_order=("twexapi", "twitterapi"))
    def fail(*a, **kw): raise XClientServerError("outage")
    monkeypatch.setattr(client, "_twex_search_with_retry", fail)
    monkeypatch.setattr(client, "_get", lambda *a, **kw: {"tweets": [], "has_next_page": False})
    with pytest.raises(XClientServerError): client.run_search("query")
    assert twex.failures == 1 and primary.failures == 0
    assert client.run_search("query")[0] == []


def test_environment_order_and_missing_key_validation(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient

    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "primary")
    monkeypatch.setenv("TWEXAPI_API_KEY", "fallback")
    monkeypatch.setenv("X_DATA_PROVIDER_ORDER", "twexapi,twitterapi")
    client = XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)
    assert client.provider_order == ("twexapi", "twitterapi:scheduled")
    assert client.circuit.provider == "twitterapi" and client.twex_circuit.provider == "twexapi"
    monkeypatch.delenv("TWEXAPI_API_KEY")
    assert XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED).api_key == "primary"
    monkeypatch.delenv("X_DATA_PROVIDER_ORDER")
    monkeypatch.delenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", raising=False)
    client = XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)
    assert client.circuit is None and client.timeout_s == 60 and client.max_retries == 2


@pytest.mark.parametrize("provider", ["twitterapi", "twexapi"])
def test_search_adapters_share_normalized_contract(provider):
    import json
    from pathlib import Path
    from x_monitor.x_data_provider import TwitterAPIProvider, TwexAPIProvider

    if provider == "twitterapi":
        adapter = TwitterAPIProvider(None)
        response = json.loads((Path(__file__).parent / "fixtures/twitterapi/search-page.json").read_text())
        tweet = response["tweets"][0]
        expected = (str(tweet["id"]), tweet["text"], tweet["author"]["userName"])
    else:
        adapter = TwexAPIProvider(None)
        response = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
        tweet = response["data"][0]
        expected = (str(tweet["tweet_id"]), tweet["full_text"], tweet["user"]["screen_name"])
    page = adapter.normalize_page(response, page_number=1, max_results=20)
    assert (page.items[0]["id"], page.items[0]["text"], page.items[0]["author_handle"]) == expected
    assert page.has_more and page.next_cursor


def test_twex_only_order_does_not_require_twitter_credential(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient
    monkeypatch.delenv("TWITTERAPI_IO_SCHEDULED_API_KEY", raising=False)
    monkeypatch.setenv("TWEXAPI_API_KEY", "twex")
    monkeypatch.setenv("X_DATA_PROVIDER_ORDER", "twexapi")
    client = XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)
    assert client.provider_order == ("twexapi",)
    with pytest.raises(RuntimeError, match="TwitterAPI"):
        client.user_info("sample")


@pytest.mark.parametrize("cursor", ["legacy-twitter-cursor", "twexapi:twex-cursor"])
def test_provider_cursor_is_held_while_its_circuit_is_open(monkeypatch, cursor):
    from x_monitor.x_client import XClient, XClientServerError
    class OpenCircuit:
        def primary_permitted(self, now): return False
    client = XClient(api_key="primary", twexapi_key="second", circuit=OpenCircuit(),
                     twex_circuit=OpenCircuit(), provider_order=("twexapi", "twitterapi"))
    monkeypatch.setattr(client, "_get", lambda *a, **kw: pytest.fail("unexpected TwitterAPI call"))
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: pytest.fail("unexpected Twex call"))
    with pytest.raises(XClientServerError, match="cursor held"):
        next(client.run_search_pages("query", cursor=cursor))


def test_twex_health_is_shared_between_scheduled_and_on_demand(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "scheduled")
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "ondemand")
    monkeypatch.setenv("TWEXAPI_API_KEY", "shared")
    scheduled = XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)
    ondemand = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    assert scheduled.twex_circuit.purpose == ondemand.twex_circuit.purpose
    assert scheduled.circuit.purpose != ondemand.circuit.purpose


@pytest.mark.parametrize("provider", ["twitterapi", "twexapi"])
def test_both_search_adapters_reject_bad_result_and_preserve_invalid_continuation(provider):
    from x_monitor.x_data_provider import TwitterAPIProvider, TwexAPIProvider
    adapter = TwitterAPIProvider(None) if provider == "twitterapi" else TwexAPIProvider(None)
    invalid = {"tweets": "bad"} if provider == "twitterapi" else {"code": 200, "data": "bad"}
    with pytest.raises((TypeError, ValueError)):
        adapter.normalize_page(invalid, page_number=1, max_results=20)
    empty = {"tweets": [], "has_next_page": True} if provider == "twitterapi" else {"code": 200, "data": [], "has_next_page": True}
    assert adapter.normalize_page(empty, page_number=1, max_results=20).continuation_invalid


def test_credential_order_names_and_defaults():
    from x_monitor.x_data_provider import parse_provider_order
    assert parse_provider_order("twitterapi:scheduled,twitterapi:on_demand,twexapi") == (
        "twitterapi:scheduled", "twitterapi:on_demand", "twexapi")


def test_two_twitter_keys_are_distinct_circuit_entries(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "scheduled-fixture")
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "ondemand-fixture")
    monkeypatch.setenv("TWEXAPI_API_KEY", "twex-fixture")
    monkeypatch.delenv("X_DATA_PROVIDER_ORDER", raising=False)
    client = XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)
    assert client.provider_order == ("twitterapi:scheduled", "twitterapi:on_demand", "twexapi")
    assert client.provider_circuits["twitterapi:scheduled"].purpose != client.provider_circuits["twitterapi:on_demand"].purpose


def _two_key_client(monkeypatch, *, duplicate=False):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient
    class Circuit:
        def __init__(self, purpose, **kwargs): self.failed = False; self.purpose = purpose
        def primary_permitted(self, now): return not self.failed
        def record_failure(self, now): self.failed = True
        def record_success(self, now): pass
        def observe_query(self, *args, **kwargs): return False
        def is_probe(self): return False
    monkeypatch.setattr("x_monitor.search_provider_circuit.SearchProviderCircuit", Circuit)
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "fixture-scheduled")
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-scheduled" if duplicate else "fixture-ondemand")
    monkeypatch.setenv("TWEXAPI_API_KEY", "fixture-twex")
    monkeypatch.delenv("X_DATA_PROVIDER_ORDER", raising=False)
    return XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)


def test_scheduled_503_falls_through_to_on_demand(monkeypatch):
    from x_monitor.x_client import XClientServerError
    client = _two_key_client(monkeypatch)
    calls = []
    def fake_get(*args, **kwargs):
        calls.append(kwargs["credential"])
        if calls[-1] == "fixture-scheduled": raise XClientServerError("503")
        return {"tweets": [], "has_next_page": False}
    monkeypatch.setattr(client, "_get", fake_get)
    assert client.run_search("Qwen") == ([], False)
    assert calls == ["fixture-scheduled", "fixture-ondemand"]


def test_two_twitter_failures_fall_through_to_twex(monkeypatch):
    from x_monitor.x_client import XClientServerError
    client = _two_key_client(monkeypatch)
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs["credential"])
        raise XClientServerError("503")
    monkeypatch.setattr(client, "_get", fail)
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: calls.append("twex") or {"code": 200, "data": [], "has_next_page": False})
    assert client.run_search("Qwen") == ([], False)
    assert calls == ["fixture-scheduled", "fixture-ondemand", "twex"]


def test_same_twitter_key_is_not_retried_as_second_credential(monkeypatch):
    client = _two_key_client(monkeypatch, duplicate=True)
    assert client.provider_order == ("twitterapi:scheduled", "twexapi")


def test_twex_busy_503_trips_its_search_circuit(monkeypatch):
    from x_monitor.x_client import XClientServerError
    client = _two_key_client(monkeypatch)
    class Response:
        status_code = 503
        headers = {}
        content = b'{"code":503,"msg":"Service is busy"}'
    monkeypatch.setattr(client, "_twex_transport", lambda *args: Response())
    monkeypatch.setattr(client.circuit, "acquire_fallback", lambda *args: 0, raising=False)
    monkeypatch.setattr(client.circuit, "fallback_owned", lambda *args: True, raising=False)
    monkeypatch.setattr(client.circuit, "release_fallback", lambda *args: None, raising=False)
    with pytest.raises(XClientServerError):
        client._twex_guarded_search("Qwen", None)
    assert client.twex_circuit.failed is True


def test_on_demand_prefers_its_key_then_scheduled(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "scheduled")
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "on-demand")
    monkeypatch.setenv("TWEXAPI_API_KEY", "twex")
    monkeypatch.delenv("X_DATA_PROVIDER_ORDER", raising=False)
    client = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    assert client.provider_order == ("twitterapi:on_demand", "twitterapi:scheduled", "twexapi")


def test_duplicate_key_failure_goes_directly_to_twex(monkeypatch):
    from x_monitor.x_client import XClientServerError
    client = _two_key_client(monkeypatch, duplicate=True)
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs["credential"])
        raise XClientServerError("503")
    monkeypatch.setattr(client, "_get", fail)
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: calls.append("twex") or {"code": 200, "data": [], "has_next_page": False})
    assert client.run_search("Qwen") == ([], False)
    assert calls == ["fixture-scheduled", "twex"]




def test_raw_receipt_uses_on_demand_after_scheduled_circuit_opens(monkeypatch):
    from x_monitor.x_client import XClientServerError
    client = _two_key_client(monkeypatch)
    calls = []
    def fake_get(*args, **kwargs):
        calls.append(kwargs["credential"])
        if calls[-1] == "fixture-scheduled": raise XClientServerError("503")
        return b'{"tweets":[]}', {"tweets": [], "has_next_page": False}
    monkeypatch.setattr(client, "_get", fake_get)
    with pytest.raises(XClientServerError):
        client.run_search_page_with_raw("Qwen", since_time=1, until_time=2)
    raw, _, items, _, _ = client.run_search_page_with_raw("Qwen", since_time=1, until_time=2)
    assert raw == b'{"tweets":[]}' and items == []
    assert calls == ["fixture-scheduled", "fixture-ondemand"]


def test_scheduled_auth_failure_uses_distinct_fallback(monkeypatch):
    from x_monitor.x_client import XClientAuthError
    client = _two_key_client(monkeypatch)
    calls = []
    def request(*args, **kwargs):
        calls.append(kwargs["credential"])
        if calls[-1] == "fixture-scheduled": raise XClientAuthError("401")
        return {"tweets": [], "has_next_page": False}
    monkeypatch.setattr(client, "_get", request)
    assert client.run_search("Qwen") == ([], False)
    assert calls == ["fixture-scheduled", "fixture-ondemand"]


def test_manual_search_uses_on_demand_then_scheduled(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient, XClientServerError
    client = _two_key_client(monkeypatch)
    client = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    calls = []
    def request(*args, **kwargs):
        calls.append(kwargs["credential"])
        if calls[-1] == "fixture-ondemand": raise XClientServerError("503")
        return {"tweets": [], "has_next_page": False}
    monkeypatch.setattr(client, "_get", request)
    assert client.run_search("Qwen") == ([], False)
    assert calls == ["fixture-ondemand", "fixture-scheduled"]


def test_same_physical_key_shares_breaker_across_scheduled_and_manual(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient
    client = _two_key_client(monkeypatch, duplicate=True)
    manual = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    assert client.provider_circuits["twitterapi:scheduled"].purpose == manual.provider_circuits["twitterapi:on_demand"].purpose


def test_global_scheduled_order_becomes_manual_first_for_backfill(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-on")
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "fixture-scheduled")
    monkeypatch.setenv("TWEXAPI_API_KEY", "fixture-twex")
    monkeypatch.setenv("X_DATA_PROVIDER_ORDER", "twitterapi:scheduled,twitterapi:on_demand,twexapi")
    client = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    assert client.provider_order == ("twitterapi:on_demand", "twitterapi:scheduled", "twexapi")


def test_fallback_does_not_start_after_search_deadline(monkeypatch):
    from x_monitor.x_client import XClientServerError
    client = _two_key_client(monkeypatch)
    calls = []
    admissions = iter([True, False])
    def fail(*args, **kwargs):
        calls.append(kwargs["credential"])
        raise XClientServerError("503")
    monkeypatch.setattr(client, "_get", fail)
    with pytest.raises(TimeoutError, match="deadline"):
        next(client._iter_search_pages("Qwen", 20, can_start_page=lambda: next(admissions)))
    assert calls == ["fixture-scheduled"]
