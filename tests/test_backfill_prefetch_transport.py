"""Bounded transport has no database work; parsing stays shared with harvest."""
from datetime import UTC, datetime

import pytest

from x_monitor.apify import search_page_from_response


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

    from x_monitor.apify import TwitterApiClient

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
    client = TwitterApiClient(api_key="fixture", max_retries=0, max_response_bytes=1024)
    try:
        start = time.monotonic()
        with pytest.raises(requests.Timeout):
            client._get_bounded(f"http://127.0.0.1:{server.server_port}/", {}, 0.2)
        assert time.monotonic() - start < 0.6
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
