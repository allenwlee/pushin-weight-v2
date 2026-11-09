"""Bounded Exa search for Graphics source artwork.

The caller must reserve the estimated spend before calling. Prices can change;
this estimate is neither a provider-enforced cap nor a statement of the bill.
"""

import json
from decimal import Decimal
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

# Published Exa auto-search base price, up to ten results, 2026-11-09.
# https://exa.ai/pricing
EXA_SEARCH_ESTIMATE_PER_QUERY_USD = Decimal('0.007')
_MAX_RESULTS = 5
_MAX_RESPONSE_BYTES = 1024 * 1024


def _queries(discovery):
    queries = discovery['queries']
    if not isinstance(queries, list) or len(queries) > 2 or not all(
        isinstance(query, str) and query.strip() for query in queries
    ):
        raise ValueError('Expected at most two non-empty search queries')
    return queries


def estimate_exa_search_usd(discovery):
    return EXA_SEARCH_ESTIMATE_PER_QUERY_USD * len(_queries(discovery))


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(request, timeout):
    opener = build_opener(_RejectRedirects())
    with opener.open(request, timeout=timeout) as response:
        data = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(data) > _MAX_RESPONSE_BYTES:
        raise ValueError('Exa response exceeds size limit')
    return data


def exa_request_json(query):
    """Build the exact JSON bytes that will be reserved and sent."""
    _queries({'queries': [query]})
    return json.dumps({'query': query, 'type': 'auto', 'numResults': _MAX_RESULTS})


def search_exa_query(query, *, api_key, transport=None):
    """Perform one request after the caller has reserved its estimated cost."""
    _queries({'queries': [query]})
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError('Exa API key is unavailable')
    transport = transport or _request
    body = exa_request_json(query).encode()
    request = Request('https://api.exa.ai/search', data=body, headers={
        'Content-Type': 'application/json', 'x-api-key': api_key,
    }, method='POST')
    response = json.loads(transport(request, 15))
    results = response['results']
    if not isinstance(results, list):
        raise TypeError('Invalid Exa search response')
    clean = []
    for item in results[:_MAX_RESULTS]:
        if not isinstance(item, dict) or not isinstance(item.get('url'), str):
            continue
        url = item['url']
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            continue
        title = item.get('title')
        clean.append({'url': url, 'title': title if isinstance(title, str) else ''})
    return {'query': query, 'results': clean}


def search_exa(discovery, *, api_key, transport=None):
    """Search exact G0 queries; callers handle failure as an empty fallback.

    A timeout can still incur charges. Failures are never retried and must not
    release the caller's reservation. Actual billing is unknown here.
    """
    queries = _queries(discovery)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError('Exa API key is unavailable')
    groups = [search_exa_query(query, api_key=api_key, transport=transport) for query in queries]
    return {'provider': 'exa', 'cost_usd': None, 'queries': groups}
