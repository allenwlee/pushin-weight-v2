"""File-backed compatibility adapter for shared Graphics source retrieval."""

import json
from pathlib import Path

from core.staff_assets.public_fetch import fetch_public_response, public_addresses
from monitor.editorial.graphics_sources import (  # noqa: F401
    PageImages,
    collect_sources,
    select_image,
    words,
)


def public_url(url):
    public_addresses(url)
    return url


def get(url, limit, deadline):
    return fetch_public_response(url, max_bytes=limit, deadline=deadline)


def fetch_sources(directory, discovery, search_result, fetch=get):
    """Save file-based trial assets while sharing the application retrieval path."""
    directory = Path(directory)
    result = collect_sources(discovery, search=lambda _: search_result, fetch=fetch)
    evidence = result['evidence']
    assets = []
    records = []
    by_ref = {asset['asset_ref']: asset for asset in result['assets']}
    for index, record in enumerate(evidence['retrieval_records'], 1):
        clean = {key: value for key, value in record.items() if key != 'asset'}
        page = result['pages'][index - 1]
        if page is not None:
            (directory / f'source-page-{index}.html').write_bytes(page)
        if 'asset' in record:
            source = by_ref[record['asset']['asset_ref']]
            path = directory / f"fresh-source-{index}.{source['extension']}"
            path.write_bytes(source['data'])
            asset = {key: value for key, value in source.items() if key not in {'data', 'extension'}}
            asset['file'] = str(path)
            clean['asset'] = asset
            assets.append(asset)
        records.append(clean)
    evidence = {**evidence, 'retrieval_records': records}
    for name, value in [
        ('source-assets', assets),
        ('source-fetch-receipts', records),
        ('search-evidence', evidence),
    ]:
        (directory / (name + '.json')).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        )
    return assets
