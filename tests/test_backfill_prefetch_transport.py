"""Bounded transport has no database work; parsing stays shared with harvest."""
from datetime import UTC, datetime

import pytest

from x_monitor.x_client import search_page_from_response


@pytest.mark.parametrize("tweets,more,cursor,expected", [
    ([], True, "next", True),
    ([{"id": "1", "text": "Qwen"}], True, "next", True),
    ([], False, "unused", False),
])
def test_captured_page_preserves_provider_continuation(tweets, more, cursor, expected):
    page = search_page_from_response(
        {"tweets": tweets, "has_next_page": more, "next_cursor": cursor},
        received_at=datetime.now(UTC), received_monotonic=1.0,
    )
    assert page.has_more is expected
    assert page.raw_post_ids == tuple(row["id"] for row in tweets)


def test_captured_page_rejects_provider_error():
    with pytest.raises(ValueError, match="provider error"):
        search_page_from_response({"error": "failed", "tweets": []})


@pytest.mark.parametrize("options", [
    {"concurrency": 0}, {"concurrency": 21}, {"concurrency": True},
    {"starts_per_second": 0}, {"starts_per_second": float("nan")},
    {"unknown": 1},
])
def test_execution_preferences_fail_before_any_transport(options):
    from monitor.backfill_prefetch import PrefetchOptions
    with pytest.raises(ValueError):
        PrefetchOptions.parse(options)


@pytest.mark.parametrize("slow_part", ["headers", "body"])
def test_total_http_deadline_stops_trickling_server(slow_part):
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import requests

    from x_monitor.x_client import XClient

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            try:
                if slow_part == "headers":
                    self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Trickle: ")
                else:
                    self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: 30\r\n\r\n")
                self.wfile.flush()
                for _ in range(30):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.03)
                if slow_part == "headers":
                    self.wfile.write(b"\r\nContent-Length: 2\r\n\r\n{}")
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = XClient(api_key="fixture", max_retries=0, max_response_bytes=1024)
    try:
        start = time.monotonic()
        with pytest.raises(requests.Timeout):
            client._get_bounded(f"http://127.0.0.1:{server.server_port}/", {}, 0.2)
        assert time.monotonic() - start < 0.6
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_captured_twex_page_normalizes_and_tags_cursor():
    import json
    from pathlib import Path
    from types import SimpleNamespace
    from monitor.backfill_prefetch import CapturedPage
    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    request = SimpleNamespace(endpoint_url="https://api.twexapi.io/twitter/advanced_search/page", received_at=None,
                              request_config="x:twexapi")
    page = next(CapturedPage(request, {}, False, body=body).pages())
    assert page.items[0]["id"] == str(body["data"][0]["tweet_id"])
    assert page.next_cursor == "twexapi:fixture-cursor"


def test_twex_prefetch_accounts_one_physical_call_and_raw_receipt(monkeypatch):
    import json
    from pathlib import Path
    from monitor.backfill_prefetch import PrefetchRoute, fetch_page
    from x_monitor.x_client import XClient
    body = json.loads((Path(__file__).parent / "fixtures/twexapi/search-page.json").read_text())
    raw = json.dumps(body).encode()
    class Response:
        status_code = 200
        headers = {}
        content = raw
        def json(self): return body
    calls = []
    monkeypatch.setattr(XClient, "_bounded_request", lambda self, method, url, timeout, **kw: calls.append((method, url, kw["payload"])) or Response())
    result = fetch_page(PrefetchRoute("twexapi", "fixture-secret"), {"query": "Qwen", "cursor": "abc"}, max_bytes=100000, timeout=30)
    assert result.error is None and result.response["raw_results"] == len(body["data"])
    assert calls == [("POST", "https://api.twexapi.io/twitter/advanced_search/page", {"searchTerms": ["Qwen"], "sortBy": "Latest", "next_cursor": "abc"})]
    assert result.body == Response.content


def test_known_busy_prefetch_empty_is_unresolved_not_a_success(monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from monitor.backfill_prefetch import Prefetcher, PrefetchRoute, TransportResult
    class Circuit:
        def observe_query(self, query, *, nonempty, now): return True
        def is_probe(self): return False
    controller = object.__new__(Prefetcher)
    controller.routes = {7: PrefetchRoute("twitterapi:on_demand", "fixture")}
    controller.router = SimpleNamespace(provider_circuits={"twitterapi:on_demand": Circuit()})
    request = SimpleNamespace(pk=7, cursor_before=None, scope_run=object())
    monkeypatch.setattr("monitor.backfill_prefetch._params", lambda scope: {"query": "Qwen"})
    result = TransportResult(b'{"tweets":[]}', {"status_code": 200, "raw_results": 0}, None, datetime.now(UTC), 0.1)
    assessed = controller._assess_route_result(request, result)
    assert assessed.error == "XClientServerError"
