"""Select source images using evidence from the fetched page."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


class PageImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.meta = {}
        self.title_parts = []
        self.in_title = False
        self.in_main = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "main":
            self.in_main = True
        if tag == "meta":
            self.meta[values.get("property") or values.get("name")] = values.get(
                "content", ""
            )
        if tag == "img":
            self.images.append({**values, "in_main": self.in_main})

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "main":
            self.in_main = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self):
        return self.meta.get("og:title") or " ".join(self.title_parts).strip()


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - {
        "the",
        "and",
        "of",
        "a",
        "an",
        "www",
        "com",
        "https",
        "http",
        "book",
        "books",
        "edition",
        "original",
        "illustration",
        "cover",
        "site",
        "activities",
        "activity",
    }


def select_image(html, requested_url, final_url, requested_title):
    """Never promote a generic index's social card to the requested named artifact."""
    page = PageImages()
    page.feed(html)
    path = urlsplit(final_url).path.rstrip("/")
    if path in {"", "/activities", "/books", "/activity", "/search"}:
        return (
            None,
            page.title,
            "resolved page is a generic index, not the requested artifact",
        )
    target = words(requested_title)
    page_matches = bool(target & words(page.title))
    if not page_matches and requested_url != final_url:
        return (
            None,
            page.title,
            "redirected page title does not identify the requested artifact",
        )
    ranked = []
    for image in page.images:
        source = image.get("data-src") or image.get("src")
        if not source or source.startswith("data:"):
            continue
        label = image.get("alt", "")
        if re.search(r"(?:^|[^a-z])(logo|avatar|icon)(?:[^a-z]|$)", label + " " + source, re.IGNORECASE):
            continue
        overlap = len(target & words(label + " " + source))
        named_cover = "cover" in label.lower() and page_matches
        if overlap or named_cover:
            score = overlap * 10 + int(named_cover) * 3 + int(image["in_main"])
            ranked.append((score, source, "named page image: " + label))
    if ranked:
        _, source, basis = max(ranked, key=lambda item: item[0])
        return urljoin(final_url, source), page.title, basis
    if page_matches and page.meta.get("og:image"):
        return (
            urljoin(final_url, page.meta["og:image"]),
            page.title,
            "page-specific social preview; visual suitability unconfirmed",
        )
    return None, page.title, "no image tied to the named artifact"


def collect_sources(discovery, *, search=None, fetch=None):
    """Collect bounded source-artwork bytes and evidence for the current G0 queries.

    The injected search adapter must return results for exactly those queries. A
    missing or unavailable adapter is a recorded empty fallback. Each result keeps
    the exact original bytes; this function never creates a person attribution.
    """
    import hashlib
    import time
    import warnings
    from concurrent.futures import ThreadPoolExecutor
    from io import BytesIO

    from PIL import Image

    from core.staff_assets.public_fetch import fetch_public_response

    queries = discovery['queries']
    if len(queries) > 2 or not all(isinstance(query, str) for query in queries):
        raise ValueError('At most two search queries are supported')
    evidence = {
        'queries': queries,
        'provider': None,
        'search_requests': 0,
        'search_status': 'not_requested' if not queries else 'unavailable',
        'selected_pages': [],
        'empty_queries': list(queries),
        'pages_fetched': 0,
        'images_downloaded': 0,
        'no_seeded_cover': True,
        'tool_cost_usd': None,
        'retrieval_records': [],
    }
    if not queries or search is None:
        return {'assets': [], 'pages': [], 'evidence': evidence}
    try:
        search_result = search(discovery)
    except Exception as error:  # noqa: BLE001 -- source search failure must not block the story
        evidence['search_error'] = type(error).__name__
        return {'assets': [], 'pages': [], 'evidence': evidence}
    if not isinstance(search_result, dict) or not isinstance(search_result.get('queries'), list):
        raise TypeError('Invalid search result')
    if [row.get('query') for row in search_result['queries']] != queries:
        raise ValueError('Search response must match this run’s exact G0 queries')
    groups = [row.get('results', []) for row in search_result['queries']]
    if not all(isinstance(group, list) for group in groups):
        raise ValueError('Search results must be lists')
    selected, seen = [], set()
    for rank in range(max((len(group) for group in groups), default=0)):
        for query, group in zip(queries, groups):
            if rank >= len(group):
                continue
            item = group[rank]
            url = item['url']
            if url in seen or urlsplit(url).path.lower().endswith('.pdf'):
                continue
            seen.add(url)
            selected.append({**item, 'query': query})
    selected = selected[:4]
    deadline = time.monotonic() + 60
    if fetch is None:
        def fetch(url, max_bytes, deadline):
            return fetch_public_response(url, max_bytes=max_bytes, deadline=deadline)

    def retrieve(pair):
        index, item = pair
        record = {'requested_page_url': item['url'], 'search_title': item.get('title', ''), 'query': item['query'], 'state': 'started'}
        try:
            raw, final, content_type = fetch(item['url'], 3 * 1024 * 1024, deadline)
            if 'html' not in content_type.lower():
                raise ValueError('Search hit is not an HTML source page')
            page_text = raw.decode('utf8', 'replace')
            page = PageImages()
            page.feed(page_text)
            image_url, title, basis = select_image(page_text, item['url'], final, item.get('title', ''))
            record.update(page_url=final, page_title=title, image_selection_basis=basis, page_bytes=raw)
            if not image_url:
                record['state'] = 'unavailable'
                return record
            data, image_final, _ = fetch(image_url, 12 * 1024 * 1024, deadline)
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.width * image.height > 40_000_000:
                        raise ValueError('Source image dimensions exceed limit')
                    image.load()
                    size, fmt = list(image.size), image.format
            extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(fmt)
            if not extension:
                raise ValueError('Unsupported reference-image format')
            page_author = page.meta.get('author') or page.meta.get('dc.creator') or page.meta.get('article:author')
            asset = {
                'asset_ref': f'source:{index}', 'role': 'source_artwork', 'data': data,
                'sha256': hashlib.sha256(data).hexdigest(), 'dimensions': size, 'extension': extension,
                'source_url': image_final, 'requested_image_url': image_url,
                'requested_page_url': item['url'], 'page_url': final,
                'title': title, 'search_title': item.get('title', ''), 'image_selection_basis': basis,
                'credit': f'Page author: {page_author}; image creator unconfirmed' if page_author else 'Creator unknown; source page: ' + final,
                'credit_status': 'incomplete', 'credit_gaps': ['Creator/component attribution not established by image retrieval.'],
                'retrieval_origin': 'fresh G0 query result; actual page title and redirect recorded',
            }
            record.update(state='downloaded', asset=asset)
        except Exception as error:  # noqa: BLE001 -- one source failure cannot discard other sources
            record.update(state='failed', error=type(error).__name__ + ': ' + str(error)[:300])
        return record

    with ThreadPoolExecutor(max_workers=4) as executor:
        records = list(executor.map(retrieve, enumerate(selected, 1)))
    assets = [row['asset'] for row in records if row['state'] == 'downloaded']
    pages = [row.get('page_bytes') for row in records]
    clean_records = []
    for row in records:
        clean = {key: value for key, value in row.items() if key not in {'page_bytes', 'asset'}}
        if 'asset' in row:
            clean['asset'] = {key: value for key, value in row['asset'].items() if key != 'data'}
        clean_records.append(clean)
    evidence.update(
        provider=search_result.get('provider', 'unspecified search adapter'), search_requests=len(queries),
        search_status='completed', selected_pages=selected,
        empty_queries=[row['query'] for row in search_result['queries'] if not row.get('results')],
        pages_fetched=len(records), images_downloaded=len(assets), tool_cost_usd=search_result.get('cost_usd'),
        retrieval_records=clean_records,
    )
    return {'assets': assets, 'pages': pages, 'evidence': evidence}
