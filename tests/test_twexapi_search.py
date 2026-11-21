"""Search fallback contract using a sanitized, recorded TwexAPI page."""
import json
from pathlib import Path

import pytest
import requests


@pytest.fixture(autouse=True)
def fake_twex_transport(monkeypatch):
    from x_monitor.x_client import XClient

    monkeypatch.setattr(XClient, "_twex_transport", lambda self, url, params, headers:
                        requests.post(url, json=params, headers=headers, timeout=self.search_timeout_s))


def test_recorded_twexapi_page_maps_to_existing_normalized_tweets():
    from x_monitor.x_client import twexapi_search_page

    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    page = twexapi_search_page(body, max_results=20)
    original = body["data"][0]
    assert len(page.items) == 2
    assert page.items[0]["id"] == str(original["tweet_id"])
    assert page.items[0]["text"] == original["full_text"]
    assert page.items[0]["author_handle"] == original["user"]["screen_name"]
    assert page.items[0]["like_count"] == original["favorite_count"]
    assert page.has_more and page.next_cursor == "fixture-cursor"


def test_tweet_mapper_preserves_nested_quote_and_metrics():
    from x_monitor.x_client import twexapi_search_page

    tweet = {"tweet_id": "1", "full_text": "outer", "created_at": "Sat Nov 21 11:28:00 +0000 2026", "favorite_count": 3,
             "user": {"id": "10", "screen_name": "outer"}, "is_quote_status": True,
             "quote": {"tweet_id": "2", "full_text": "quoted", "user": {"id": "20", "screen_name": "inner"}}}
    result = twexapi_search_page({"code": 200, "data": [tweet], "has_next_page": False}, max_results=20).items[0]
    assert result["quoted_status_id"] == "2"
    assert result["quoted_text"] == "quoted"
    assert result["quoted_author_handle"] == "inner"
    assert result["like_count"] == 3


def test_open_breaker_routes_search_only_to_twexapi(monkeypatch):
    from x_monitor.x_client import XClient

    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    body.update(has_next_page=False, next_cursor=None)

    class Circuit:
        def observe_query(self, query, *, nonempty, now): return False
        def primary_permitted(self, now): return False
        def acquire_fallback(self, now, lease): return 0
        def fallback_owned(self, now): return True
        def release_fallback(self, now, interval): pass

    class Response:
        status_code = 200
        content = json.dumps(body).encode()
        headers = {}
        text = ""
        def json(self): return body

    captured = []
    monkeypatch.setattr("x_monitor.x_client.requests.post", lambda url, **kw: captured.append((url, kw)) or Response())
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=Circuit())
    posts, truncated = client.run_search("DeepSeek", max_results=20, since_time=100, until_time=200)
    assert len(posts) == 2 and not truncated
    assert captured[0][1]["json"]["searchTerms"] == ["DeepSeek since_time:100 until_time:200"]
    assert client._request_log[-1]["provider"] == "twexapi"


def test_fallback_cursor_is_tagged_and_never_sent_to_primary(monkeypatch):
    from x_monitor.x_client import XClient

    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    class Circuit:
        def observe_query(self, query, *, nonempty, now): return False
        def primary_permitted(self, now): return False
        def acquire_fallback(self, now, lease): return 0
        def fallback_owned(self, now): return True
        def release_fallback(self, now, interval): pass
    class Response:
        status_code = 200
        content = json.dumps(body).encode()
        headers = {}
        def json(self): return body
    sent = []
    monkeypatch.setattr("x_monitor.x_client.requests.post", lambda url, **kw: sent.append(kw["json"]) or Response())
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=Circuit())
    page = next(client.run_search_pages("DeepSeek", max_results=2, cursor="twexapi:previous"))
    assert sent[0]["next_cursor"] == "previous"
    assert page.next_cursor == "twexapi:fixture-cursor"


def test_empty_legitimate_primary_page_does_not_open_breaker(monkeypatch):
    from x_monitor.x_client import XClient

    class Circuit:
        def __init__(self): self.failures = 0
        def primary_permitted(self, now): return True
        def record_success(self, now): pass
        def record_failure(self, now): self.failures += 1
        def observe_query(self, query, *, nonempty, now): return False
        def is_probe(self): return False
    circuit = Circuit()
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=circuit)
    monkeypatch.setattr(client, "_get", lambda *a, **k: {"tweets": [], "has_next_page": False})
    posts, incomplete = client.run_search("niche query")
    assert posts == [] and not incomplete and circuit.failures == 0


def test_raw_receipt_search_returns_original_twexapi_bytes(monkeypatch):
    from x_monitor.x_client import XClient

    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    raw = json.dumps(body).encode()
    class Circuit:
        def observe_query(self, query, *, nonempty, now): return False
        def primary_permitted(self, now): return False
        def acquire_fallback(self, now, lease): return 0
        def fallback_owned(self, now): return True
        def release_fallback(self, now, interval): pass
    class Response:
        status_code = 200
        content = raw
        headers = {}
        def json(self): return body
    monkeypatch.setattr("x_monitor.x_client.requests.post", lambda *a, **k: Response())
    def forbid_primary(*args, **kwargs):
        raise AssertionError("unexpected primary provider call")
    monkeypatch.setattr("x_monitor.x_client.requests.get", forbid_primary)
    captured = []
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=Circuit())
    receipt, result, normalized, _, _ = client.run_search_page_with_raw("DeepSeek", since_time=100, until_time=200, receipt_sink=captured.append)
    assert receipt == raw and captured == [raw]
    assert result == body
    assert normalized[0]["id"] == str(body["data"][0]["tweet_id"])


def test_failures_open_circuit_then_next_search_uses_fallback(monkeypatch):
    import pytest
    from x_monitor.x_client import XClient, XClientServerError

    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    body.update(has_next_page=False, next_cursor=None)
    class Circuit:
        def observe_query(self, query, *, nonempty, now): return False
        def __init__(self): self.failures = 0
        def primary_permitted(self, now): return self.failures < 2
        def record_failure(self, now): self.failures += 1
        def record_success(self, now): self.failures = 0
        def acquire_fallback(self, now, lease): return 0
        def fallback_owned(self, now): return True
        def release_fallback(self, now, interval): pass
    class Response:
        status_code = 200
        content = json.dumps(body).encode()
        headers = {}
        def json(self): return body
    circuit = Circuit()
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=circuit)
    calls = []
    def primary(*args, **kwargs):
        calls.append(args)
        raise XClientServerError("503")
    monkeypatch.setattr(client, "_get", primary)
    monkeypatch.setattr("x_monitor.x_client.requests.post", lambda *a, **k: Response())
    for _ in range(2):
        with pytest.raises(XClientServerError): client.run_search("DeepSeek")
    posts, _ = client.run_search("DeepSeek")
    assert len(calls) == 2 and len(posts) == 2


def test_empty_page_with_continuation_counts_as_failure(monkeypatch):
    import pytest
    from x_monitor.x_client import XClient, XClientServerError
    class Circuit:
        def __init__(self): self.failures = 0
        def primary_permitted(self, now): return True
        def record_failure(self, now): self.failures += 1
        def record_success(self, now): pass
    circuit = Circuit()
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=circuit)
    monkeypatch.setattr(client, "_get", lambda *a, **k: {"tweets": [], "has_next_page": True, "next_cursor": "next"})
    with pytest.raises(XClientServerError): client.run_search("DeepSeek")
    assert circuit.failures == 1


def test_forced_twexapi_search_never_calls_primary(monkeypatch):
    from x_monitor.x_client import XClient

    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    body.update(has_next_page=False, next_cursor=None)
    class Circuit:
        def observe_query(self, query, *, nonempty, now): return False
        def primary_permitted(self, now): raise AssertionError("forced fallback must not probe primary")
        def acquire_fallback(self, now, lease): return 0
        def fallback_owned(self, now): return True
        def release_fallback(self, now, interval): pass
    class Response:
        status_code = 200
        content = json.dumps(body).encode()
        headers = {}
        def json(self): return body
    monkeypatch.setattr("x_monitor.x_client.requests.post", lambda *a, **k: Response())
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=Circuit(), force_twexapi=True)
    assert len(client.run_search("DeepSeek")[0]) == 2


def test_backfill_force_option_requires_collect_only():
    from monitor.management.commands.run_backfill import Command

    parser = Command().create_parser("manage.py", "run_backfill")
    options = parser.parse_args(["--twexapi-only", "--phase", "collect", "--since", "2026-11-21T13:00:00+09:00", "--until", "2026-11-21T14:00:00+09:00"])
    assert options.twexapi_only and options.phase == "collect"


def test_twexapi_rate_limit_waits_before_one_retry(monkeypatch):
    from x_monitor.x_client import XClient

    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    body.update(has_next_page=False, next_cursor=None)
    class Circuit:
        def observe_query(self, query, *, nonempty, now): return False
        def primary_permitted(self, now): return False
        def acquire_fallback(self, now, lease): return 0
        def fallback_owned(self, now): return True
        def release_fallback(self, now, interval): pass
    class Response:
        content = json.dumps(body).encode()
        def __init__(self, status): self.status_code = status; self.headers = {"Retry-After": "6"}
        def json(self): return body
    responses = iter([Response(429), Response(200)])
    waits = []
    monkeypatch.setattr("x_monitor.x_client.requests.post", lambda *a, **k: next(responses))
    monkeypatch.setattr("x_monitor.x_client.time.sleep", waits.append)
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=Circuit())
    assert len(client.run_search("DeepSeek")[0]) == 2
    assert waits == [6]


def test_empty_twexapi_continuation_stops_without_looping(monkeypatch):
    from x_monitor.x_client import XClient
    class Circuit:
        def observe_query(self, query, *, nonempty, now): return False
        def primary_permitted(self, now): return False
        def acquire_fallback(self, now, lease): return 0
        def fallback_owned(self, now): return True
        def release_fallback(self, now, interval): pass
    calls = []
    first = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    responses = [first, {"code": 200, "msg": "ok", "data": [], "has_next_page": True, "next_cursor": "again"}]
    class Response:
        status_code = 200
        headers = {}
        def __init__(self, body): self.body = body; self.content = json.dumps(body).encode()
        def json(self): return self.body
    def send(*args, **kwargs):
        calls.append(kwargs["json"])
        return Response(responses.pop(0))
    monkeypatch.setattr("x_monitor.x_client.requests.post", send)
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=Circuit())
    posts, incomplete = client.run_search("DeepSeek", max_results=50)
    assert len(posts) == 2 and incomplete
    assert len(calls) == 2


def test_missing_fallback_key_preserves_primary_defaults(monkeypatch):
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
    from x_monitor.x_client import XClient

    monkeypatch.delenv("TWEXAPI_API_KEY", raising=False)
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "fixture")
    monkeypatch.setenv("TWITTERAPI_SEARCH_TIMEOUT_SECONDS", "not-a-number")
    client = XClient.from_env(TwitterApiCredentialPurpose.SCHEDULED)
    assert client.twexapi_key is None and client.circuit is None
    assert client.timeout_s == 60 and client.max_retries == 2


def test_untyped_legacy_cursor_never_goes_to_twexapi(monkeypatch):
    from x_monitor.x_client import XClient
    class Circuit:
        def observe_query(self, query, *, nonempty, now): return False
        def primary_permitted(self, now): return True
        def record_success(self, now): pass
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=Circuit())
    seen = []
    monkeypatch.setattr(client, "_get", lambda path, params, **kw: seen.append(params) or {"tweets": [{"id": "1", "text": "ok"}], "has_next_page": False})
    monkeypatch.setattr("x_monitor.x_client.requests.post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("unexpected fallback")))
    page = next(client.run_search_pages("DeepSeek", cursor="primary-cursor"))
    assert page.items[0]["id"] == "1" and seen[0]["cursor"] == "primary-cursor"


def test_recorded_tweet_preserves_links_and_media():
    from x_monitor.x_client import twexapi_search_page

    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    item = body["data"][0]
    item["urls"] = ["https://example.org/article"]
    item["hashtags"] = ["AI"]
    item["media"] = [{"type": "photo", "media_url": "https://pbs.twimg.com/media/example.jpg"}]
    result = twexapi_search_page(body).items[0]
    assert result["entities"]["urls"][0]["expanded_url"] == "https://example.org/article"
    assert result["entities"]["hashtags"][0]["text"] == "AI"
    assert result["extended_entities"]["media"][0]["media_url_https"] == "https://pbs.twimg.com/media/example.jpg"


def test_first_page_empty_with_prior_nonempty_evidence_counts_as_failure(monkeypatch):
    import pytest
    from x_monitor.x_client import XClient, XClientServerError
    class Circuit:
        def __init__(self): self.failures = 0
        def primary_permitted(self, now): return True
        def observe_query(self, query, *, nonempty, now): return True
        def is_probe(self): return False
        def record_failure(self, now): self.failures += 1
        def record_success(self, now): raise AssertionError("must not certify outage response")
    circuit = Circuit()
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=circuit)
    monkeypatch.setattr(client, "_get", lambda *a, **k: {"tweets": [], "has_next_page": False})
    with pytest.raises(XClientServerError): client.run_search("DeepSeek")
    assert circuit.failures == 1


def test_twexapi_author_profile_website_and_verification_are_preserved():
    from x_monitor.x_client import twexapi_search_page
    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    item = body["data"][0]
    item["user"].update(description="We build AI models", urls=[{"url": "https://t.co/a", "expanded_url": "https://example.org"}],
                        is_verified=True, is_blue_verified=False, verified_type="business")
    result = twexapi_search_page(body).items[0]
    assert result["author_profile_bio"]["entities"]["url"]["urls"][0]["expanded_url"] == "https://example.org"
    assert result["author_verified"] is True
    assert result["author_is_blue_verified"] is False
    assert result["author_verified_type"] == "business"


def test_scheduled_lineage_records_twex_endpoint_and_cursor():
    from core.x_cycle_lineage import ScheduledCycleLineage
    from x_monitor.x_client import XClient

    lineage = object.__new__(ScheduledCycleLineage)
    captured = []
    lineage.begin_exchange = lambda scope_id, **kwargs: captured.append((scope_id, kwargs))
    client = XClient(api_key="primary")
    lineage.bind_api(client, 123)
    client.on_exchange_start("https://api.twexapi.io/twitter/advanced_search/page", {"next_cursor": "abc"})
    assert captured == [(123, {"endpoint_url": "https://api.twexapi.io/twitter/advanced_search/page", "params": {"next_cursor": "abc"}})]


def test_raw_twex_empty_known_busy_query_is_unresolved(monkeypatch):
    import pytest
    from x_monitor.x_client import XClient, XClientServerError

    class Circuit:
        def primary_permitted(self, now): return False
        def observe_query(self, *args, **kwargs): return True
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=Circuit())
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: (b'{}', {"data": [], "has_next_page": False}))
    with pytest.raises(XClientServerError):
        client.run_search_page_with_raw("DeepSeek", since_time=100, until_time=200)


def test_twex_backfill_uses_serial_client_and_refuses_incompatible_prefetch():
    import pytest
    from django.core.management.base import CommandError
    from monitor.backfill_collection import _select_prefetch

    options = {"workers": 2}
    assert not _select_prefetch(direct_staging=False, has_prefetch=False, collection_options=options, force_twexapi=True)
    assert _select_prefetch(direct_staging=False, has_prefetch=False, collection_options=options, force_twexapi=False)
    for direct, existing in [(True, False), (False, True)]:
        with pytest.raises(CommandError):
            _select_prefetch(direct_staging=direct, has_prefetch=existing, collection_options=options, force_twexapi=True)


def test_twex_positive_pages_feed_empty_page_guard(monkeypatch):
    from x_monitor.x_client import XClient, XClientServerError

    class Circuit:
        def __init__(self): self.count = 0
        def observe_query(self, query, *, nonempty, now):
            if nonempty: self.count += 1
            return self.count >= 3
    circuit = Circuit()
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=circuit, force_twexapi=True)
    responses = iter([{"code": 200, "data": [{"tweet_id": str(i), "user": {}}]} for i in range(3)] +
                     [{"code": 200, "data": []}])
    monkeypatch.setattr(client, "_twex_search_with_retry", lambda *a, **kw: next(responses))
    for i in range(3):
        assert client.run_search("busy", since_time=i, until_time=i + 1)[0]
    with pytest.raises(XClientServerError):
        client.run_search("busy", since_time=4, until_time=5)


def test_rate_limit_shared_cooldown_even_when_retries_disabled(monkeypatch):
    from x_monitor.x_client import XClient, XClientRateLimitError
    class Circuit:
        def acquire_fallback(self, now, lease): return 0
        def fallback_owned(self, now): return True
        def release_fallback(self, now, interval): self.interval = interval
    class Response:
        status_code = 429
        headers = {"Retry-After": "45"}
        content = b'{}'
    circuit = Circuit()
    monkeypatch.setattr("x_monitor.x_client.requests.post", lambda *a, **kw: Response())
    client = XClient(api_key="primary", twexapi_key="secondary", circuit=circuit, max_retries=0)
    with pytest.raises(XClientRateLimitError) as exc:
        client._twex_search_with_retry("busy", None)
    assert exc.value.retry_after_seconds == circuit.interval == 45


@pytest.mark.parametrize("status,exception_name", [(401, "XClientAuthError"), (429, "XClientRateLimitError"), (503, "XClientServerError")])
def test_twex_status_preserves_shared_error_contract(monkeypatch, status, exception_name):
    import x_monitor.x_client as module
    class Circuit:
        def acquire_fallback(self, now, lease): return 0
        def fallback_owned(self, now): return True
        def release_fallback(self, now, interval): pass
    class Response:
        status_code = status
        headers = {}
        content = b'{}'
    monkeypatch.setattr("x_monitor.x_client.requests.post", lambda *a, **kw: Response())
    client = module.XClient(api_key="primary", twexapi_key="secondary", circuit=Circuit(), max_retries=0)
    with pytest.raises(getattr(module, exception_name)) as exc:
        client._twex_search("query", None)
    assert exc.value.response_status_code == status
