import json
from decimal import Decimal

import pytest

from monitor.editorial.graphics_search import estimate_exa_search_usd, search_exa


def test_search_is_bounded_and_preserves_queries():
    requests = []

    def transport(request, timeout):
        requests.append((request, timeout))
        return json.dumps({'results': [{'url': 'https://example.com/art', 'title': 'Art'}] * 7}).encode()

    discovery = {'queries': ['first', 'second']}
    result = search_exa(discovery, api_key='test-key', transport=transport)
    assert estimate_exa_search_usd(discovery) == Decimal('0.014')
    assert [row['query'] for row in result['queries']] == discovery['queries']
    assert len(result['queries'][0]['results']) == 5
    assert result['provider'] == 'exa'
    assert result['cost_usd'] is None
    assert len(requests) == 2
    for request, timeout in requests:
        assert request.full_url == 'https://api.exa.ai/search'
        assert json.loads(request.data) == {'query': discovery['queries'][requests.index((request, timeout))], 'type': 'auto', 'numResults': 5}
        assert request.get_header('X-api-key') == 'test-key'
        assert timeout > 0


def test_missing_key_and_invalid_query_count_do_not_call_transport():
    def forbidden(*args, **kwargs):
        pytest.fail('transport called')

    with pytest.raises(ValueError):
        search_exa({'queries': ['x']}, api_key='', transport=forbidden)
    with pytest.raises(ValueError):
        search_exa({'queries': ['a', 'b', 'c']}, api_key='key', transport=forbidden)
    assert estimate_exa_search_usd({'queries': []}) == 0


def test_failed_request_is_not_retried():
    calls = []

    def failing(request, timeout):
        calls.append(request)
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        search_exa({'queries': ['one', 'two']}, api_key='key', transport=failing)
    assert len(calls) == 1


def test_invalid_results_are_filtered():
    def transport(request, timeout):
        return json.dumps({'results': [{'url': 'javascript:evil', 'title': 'bad'}, {'url': 'https://good.example/path', 'title': None}, {'url': 'https://user:secret@example.com', 'title': 'bad'}]}).encode()

    result = search_exa({'queries': ['one']}, api_key='key', transport=transport)
    assert result['queries'][0]['results'] == [{'url': 'https://good.example/path', 'title': ''}]


def test_single_query_api_preserves_exact_query():
    from monitor.editorial.graphics_search import search_exa_query

    calls = []

    def transport(request, timeout):
        calls.append(json.loads(request.data))
        return b'{"results": []}'

    assert search_exa_query('  precise query  ', api_key='key', transport=transport) == {
        'query': '  precise query  ', 'results': []
    }
    assert calls == [{'query': '  precise query  ', 'type': 'auto', 'numResults': 5}]


def test_transport_does_not_follow_redirect_or_forward_api_key():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.request import Request

    from monitor.editorial.graphics_search import _request

    forwarded = []

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            forwarded.append(self.headers.get('x-api-key'))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    destination = ThreadingHTTPServer(('127.0.0.1', 0), Destination)

    class Redirect(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(302)
            self.send_header('Location', f'http://127.0.0.1:{destination.server_port}/')
            self.end_headers()

        def log_message(self, *args):
            pass

    origin = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
    threads = [Thread(target=server.serve_forever, daemon=True) for server in (origin, destination)]
    for thread in threads:
        thread.start()
    try:
        request = Request(f'http://127.0.0.1:{origin.server_port}/', data=b'{}', headers={'x-api-key': 'secret'})
        with pytest.raises(HTTPError):
            _request(request, 2)
        assert forwarded == []
    finally:
        for server in (origin, destination):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()
