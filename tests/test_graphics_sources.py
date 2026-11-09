"""Offline tests for graphics reference discovery and shared transport."""
import hashlib
from io import BytesIO

import pytest
from PIL import Image

from monitor.editorial import graphics_sources


def png_bytes():
    output = BytesIO()
    Image.new('RGB', (2, 2), 'red').save(output, format='PNG')
    return output.getvalue()


def test_search_fallback_without_provider():
    result = graphics_sources.collect_sources({'queries': ['cover']}, search=None)
    assert result['assets'] == []
    assert result['evidence']['search_status'] == 'unavailable'
    assert result['evidence']['queries'] == ['cover']


def test_actual_reference_preserves_urls_credit_bytes_and_hash():
    png = png_bytes()
    discovery = {'queries': ['the red cover']}
    search = lambda _: {'provider': 'fixture', 'queries': [{'query': 'the red cover', 'results': [{'url': 'https://source.test/old', 'title': 'The Red Cover'}]}]}
    def fetch(url, max_bytes, deadline):
        if url.endswith('/old'):
            return (b'<title>The Red Cover</title><meta name="author" content="A Creator"><main><img alt="The Red Cover" src="/cover.png"></main>', 'https://source.test/book/red', 'text/html')
        return png, 'https://cdn.test/real.png', 'image/png'
    result = graphics_sources.collect_sources(discovery, search=search, fetch=fetch)
    asset = result['assets'][0]
    assert asset['data'] == png
    assert asset['sha256'] == hashlib.sha256(png).hexdigest()
    assert asset['requested_page_url'] == 'https://source.test/old'
    assert asset['page_url'] == 'https://source.test/book/red'
    assert asset['requested_image_url'] == 'https://source.test/cover.png'
    assert asset['source_url'] == 'https://cdn.test/real.png'
    assert asset['credit'] == 'Page author: A Creator; image creator unconfirmed'
    assert asset['role'] == 'source_artwork'
    assert asset['credit_status'] == 'incomplete'  # page author is evidence, not proven image creator
    import json
    json.dumps(result['evidence'])


def test_transport_pins_address_and_retains_redirect_metadata(monkeypatch):
    from core.staff_assets import public_fetch
    monkeypatch.setattr(public_fetch, 'public_addresses', lambda url: (__import__('urllib.parse', fromlist=['urlsplit']).urlsplit(url), 443, ['93.184.216.34']))
    calls = []
    class Response:
        def __init__(self, status, headers, data=b''):
            self.status, self.headers, self.data = status, headers, data
        def stream(self, *args, **kwargs):
            yield self.data
        def close(self):
            pass
    responses = iter([Response(302, {'Location': 'https://cdn.test/a'}), Response(200, {'Content-Type': 'image/png'}, b'abc')])
    class Pool:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def request(self, *args, **kwargs):
            return next(responses)
        def close(self):
            pass
    monkeypatch.setattr(public_fetch.urllib3, 'HTTPSConnectionPool', Pool)
    result = public_fetch.fetch_public_response('https://source.test/page', max_bytes=10)
    assert result == (b'abc', 'https://cdn.test/a', 'image/png')
    assert [call['host'] for call in calls] == ['93.184.216.34'] * 2
    assert [call['assert_hostname'] for call in calls] == ['source.test', 'cdn.test']
    assert all(call['cert_reqs'] == 'CERT_REQUIRED' and call['retries'] is False for call in calls)


def test_existing_fetch_public_returns_exact_bytes_and_uses_shared_transport(monkeypatch):
    from core.staff_assets import media

    captured = {}
    def fetch(url, **kwargs):
        captured.update(url=url, **kwargs)
        return b'original-bytes', 'https://cdn.test/final', 'image/png'
    monkeypatch.setattr(media, 'fetch_public_response', fetch)
    assert media.fetch_public('https://source.test/one', max_bytes=77) == b'original-bytes'
    assert captured == {'url': 'https://source.test/one', 'max_bytes': 77, 'resolver': media.public_addresses}


def test_public_transport_rejects_private_redirect(monkeypatch):
    import socket

    from core.staff_assets import public_fetch

    monkeypatch.setattr(public_fetch.socket, 'getaddrinfo', lambda host, *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34' if host == 'source.test' else '127.0.0.1', 443))
    ])
    class Response:
        status = 302
        def __init__(self):
            self.headers = {'Location': 'https://internal.test/secret'}
        def close(self):
            pass
    class Pool:
        def __init__(self, **kwargs):
            pass
        def request(self, *args, **kwargs):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(public_fetch.urllib3, 'HTTPSConnectionPool', Pool)
    with pytest.raises(ValueError, match='Non-public'):
        public_fetch.fetch_public_response('https://source.test/page')


def test_failed_search_is_recorded_and_does_not_fetch():
    def unavailable(_):
        raise TimeoutError('search timeout')
    def unexpected(*args):
        pytest.fail('fetch must not run')
    result = graphics_sources.collect_sources({'queries': ['cover']}, search=unavailable, fetch=unexpected)
    assert result['assets'] == []
    assert result['evidence']['search_status'] == 'unavailable'
    assert result['evidence']['search_error'] == 'TimeoutError'


def test_only_four_search_results_are_fetched_and_query_order_is_interleaved():
    queries = ['a', 'b']
    search = lambda _: {'queries': [
        {'query': 'a', 'results': [{'url': f'https://a.test/{i}', 'title': 'A'} for i in range(6)]},
        {'query': 'b', 'results': [{'url': f'https://b.test/{i}', 'title': 'B'} for i in range(6)]},
    ]}
    def fetch(url, max_bytes, deadline):
        raise TimeoutError('unavailable')
    result = graphics_sources.collect_sources({'queries': queries}, search=search, fetch=fetch)
    evidence = result['evidence']
    assert [item['query'] for item in evidence['selected_pages']] == ['a', 'b', 'a', 'b']
    assert evidence['pages_fetched'] == 4
    assert all(record['state'] == 'failed' for record in evidence['retrieval_records'])
    assert result['assets'] == []
