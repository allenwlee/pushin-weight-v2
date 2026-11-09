"""Bounded, source-aware image retrieval for the local Graphics trial."""

import hashlib
import ipaddress
import json
import socket
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from monitor.editorial.graphics_sources import (  # noqa: F401
    PageImages,
    select_image,
    words,
)


def public_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Source URL must be public HTTP(S) without credentials")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("Unsupported source port")
    addresses = socket.getaddrinfo(
        parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
    )
    if not addresses or any(
        not ipaddress.ip_address(info[4][0]).is_global for info in addresses
    ):
        raise ValueError("Non-public source address")
    return url


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get(url, limit, deadline):
    public_url(url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Reference-fetch deadline exceeded")
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (editorial-reference-review/1.0)"}
    )
    with urllib.request.build_opener(PublicRedirect()).open(
        request, timeout=min(30, remaining)
    ) as response:
        body = response.read(limit + 1)
        final = response.url
        content_type = response.headers.get("Content-Type", "")
    if len(body) > limit:
        raise ValueError("Reference download exceeds byte limit")
    return body, final, content_type


def fetch_sources(directory, discovery, search_result, fetch=get):
    directory = Path(directory)
    queries = discovery["queries"]
    if (
        len(queries) > 2
        or [row["query"] for row in search_result["queries"]] != queries
    ):
        raise ValueError("Search response must match this run’s exact G0 queries")
    # Interleave both queries rather than silently ignoring the second one's results.
    groups = [row.get("results", []) for row in search_result["queries"]]
    selected = []
    seen = set()
    for rank in range(max((len(group) for group in groups), default=0)):
        for query, group in zip(queries, groups):
            if rank >= len(group):
                continue
            item = group[rank]
            url = item["url"]
            if url in seen or urlsplit(url).path.lower().endswith(".pdf"):
                continue
            seen.add(url)
            selected.append({**item, "query": query})
    selected = selected[:4]
    deadline = time.monotonic() + 60

    def retrieve(index, item):
        record = {
            "requested_page_url": item["url"],
            "search_title": item.get("title", ""),
            "query": item["query"],
            "state": "started",
        }
        try:
            raw, final, content_type = fetch(item["url"], 3 * 1024 * 1024, deadline)
            if "html" not in content_type.lower():
                raise ValueError("Search hit is not an HTML source page")
            (directory / f"source-page-{index}.html").write_bytes(raw)
            image_url, title, basis = select_image(
                raw.decode("utf8", "replace"), item["url"], final, item.get("title", "")
            )
            record.update(page_url=final, page_title=title, image_selection_basis=basis)
            if not image_url:
                record["state"] = "unavailable"
                return record
            data, image_final, _ = fetch(image_url, 12 * 1024 * 1024, deadline)
            with Image.open(BytesIO(data)) as image:
                image.load()
                size, fmt = list(image.size), image.format
            extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt)
            if not extension:
                raise ValueError("Unsupported reference-image format")
            path = directory / f"fresh-source-{index}.{extension}"
            path.write_bytes(data)
            asset = {
                "asset_ref": f"source:{index}",
                "role": "source_artwork",
                "file": str(path),
                "sha256": hashlib.sha256(data).hexdigest(),
                "dimensions": size,
                "source_url": image_final,
                "requested_image_url": image_url,
                "requested_page_url": item["url"],
                "page_url": final,
                "title": title,
                "search_title": item.get("title", ""),
                "image_selection_basis": basis,
                "credit": "Creator unknown; source page: " + final,
                "credit_status": "incomplete",
                "credit_gaps": [
                    "Creator/component attribution not established by image retrieval."
                ],
                "retrieval_origin": "fresh G0 query result; actual page title and redirect recorded",
            }
            record.update(state="downloaded", asset=asset)
        except Exception as error:  # noqa: BLE001 -- one bad source must not discard the other sources
            record.update(
                state="failed", error=type(error).__name__ + ": " + str(error)[:300]
            )
        return record

    with ThreadPoolExecutor(max_workers=4) as executor:
        records = list(
            executor.map(lambda pair: retrieve(*pair), enumerate(selected, 1))
        )
    assets = [row["asset"] for row in records if row["state"] == "downloaded"]
    evidence = {
        "queries": queries,
        "provider": search_result.get("provider", "unspecified search adapter"),
        "search_requests": len(queries),
        "selected_pages": selected,
        "empty_queries": [
            row["query"] for row in search_result["queries"] if not row.get("results")
        ],
        "pages_fetched": len(records),
        "images_downloaded": len(assets),
        "no_seeded_cover": True,
        "tool_cost_usd": search_result.get("cost_usd"),
        "retrieval_records": records,
    }
    for name, data in [
        ("source-assets", assets),
        ("source-fetch-receipts", records),
        ("search-evidence", evidence),
    ]:
        (directory / (name + ".json")).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        )
    return assets
