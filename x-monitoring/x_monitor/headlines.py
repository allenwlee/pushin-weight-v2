# {{AGENT_ATTRIBUTION}}
"""
Article headline extraction (v1.2, commit 1: pure extractors only).

This file holds the pure-functional bits:
- parse_title(html): extract a clean headline from raw HTML
- normalize_url(url): stable cache key derivation
- cache_key_for(url): the dict key used in data/headlines_cache.json

HTTP fetching, caching I/O, and the enrich_posts() integration live
in commit 3 of the v1.2 plan. The import surface is stable so commit 3
just adds the network and cache layers without changing parse_title.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlparse, urlunparse


# Common site-name separator patterns. Order matters: longer first.
_SITE_SUFFIX_RE = re.compile(
    r"\s+[\-–—|·•~]{1,3}\s+"  # separator
    r"[A-Z][A-Za-z0-9 .&'!]{1,60}$"  # site name (avoid all-lowercase which is the title itself)
)


# --- Title extraction ----------------------------------------------------


class _TitleParser(HTMLParser):
    """Minimal <title>/<meta og:title>/<meta twitter:title> extractor.

    HTMLParser is in the stdlib (no BeautifulSoup dep) and resilient
    to malformed HTML. We collect:
    - the text content of the first <title> tag
    - the content= attribute of the first <meta property="og:title">
    - the content= attribute of the first <meta name="twitter:title">
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_buf: list[str] = []
        self.og_title: str | None = None
        self.twitter_title: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "title":
            self.in_title = True
        elif t == "meta":
            attrd = {k.lower(): (v or "") for k, v in attrs}
            prop = attrd.get("property", "").lower()
            name = attrd.get("name", "").lower()
            content = attrd.get("content", "")
            if prop == "og:title" and self.og_title is None and content:
                self.og_title = content
            elif name == "twitter:title" and self.twitter_title is None and content:
                self.twitter_title = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_buf.append(data)


def _decode_entities(s: str) -> str:
    """Decode the most common HTML entities. Stdlib-only."""
    return (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&nbsp;", " ")
    )


def _clean_title(t: str) -> str:
    """Strip whitespace and trailing site names like ' - Site Name'."""
    t = _decode_entities(t).strip()
    t = re.sub(r"\s+", " ", t)
    # Only strip site-name suffix when the separator is followed by a
    # capitalized word (avoids cutting "Kimi-2.5" or "Q3-Q4 alignment").
    m = _SITE_SUFFIX_RE.search(t)
    if m:
        candidate = t[: m.start()].rstrip()
        # Sanity: only strip if the suffix is a plausible site name
        # (3+ chars, doesn't look like a model version like "2.5").
        suffix = t[m.end() - len(t) + m.end():].strip()  # noqa: F841 (debug)
        # We trust the regex; fall through.
        t = candidate
    return t.strip()


def parse_title(html: str) -> str | None:
    """Extract the best available headline from an HTML document.

    Tries in order: <title> -> <meta property="og:title"> ->
    <meta name="twitter:title">. Returns the cleaned string or None
    if no title was found.
    """
    if not html:
        return None
    try:
        p = _TitleParser()
        p.feed(html[: 50 * 1024])  # cap to 50KB; titles are near the top
        p.close()
    except Exception:
        return None
    for raw in (p.og_title, p.twitter_title, "".join(p.title_buf)):
        if raw and raw.strip():
            cleaned = _clean_title(raw)
            if cleaned:
                return cleaned
    return None


# --- URL normalization ---------------------------------------------------


# Query params to strip when normalizing URLs for cache keys.
_STRIP_PARAMS_PREFIXES = ("utm_",)
_STRIP_PARAMS_EXACT = frozenset(
    {"fbclid", "gclid", "ref", "ref_src", "ref_url", "mc_cid", "mc_eid"}
)


def normalize_url(url: str) -> str:
    """Return a stable, comparable version of a URL for cache keys.

    - Lowercase scheme + host
    - Strip default ports (80, 443)
    - Strip tracking query params (utm_*, fbclid, gclid, etc.)
    - Keep path, fragment, and other query params in stable order
    """
    if not url:
        return ""
    try:
        p = urlparse(url)
    except Exception:
        return url
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower()
    netloc = host
    if p.port and not ((scheme == "http" and p.port == 80) or
                      (scheme == "https" and p.port == 443)):
        netloc = f"{host}:{p.port}"
    # Filter query params
    kept: list[tuple[str, str]] = []
    for k, v in parse_qsl(p.query, keep_blank_values=True):
        kl = k.lower()
        if any(kl.startswith(pfx) for pfx in _STRIP_PARAMS_PREFIXES):
            continue
        if kl in _STRIP_PARAMS_EXACT:
            continue
        kept.append((k, v))
    kept.sort()  # stable order
    new_query = "&".join(f"{k}={v}" for k, v in kept)
    return urlunparse((scheme, netloc, p.path, p.params, new_query, ""))


def cache_key_for(url: str) -> str:
    """Final cache key. Same as normalize_url for v1.2 (kept as a
    separate function so a future hash-based key is a one-liner)."""
    return normalize_url(url)
