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

import fcntl
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse, urlunparse

import requests

log = logging.getLogger(__name__)


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



# --- t.co redirect resolution (v1.2 commit 3.1) ------------------------


# Hosts that we treat as redirects. t.co is the canonical case; the
# others are intermediate hops the t.co redirector sometimes uses.
TCO_HOSTS: frozenset[str] = frozenset({"t.co"})

# Cap on the number of redirects we'll follow. 5 is enough to handle
# t.co -> tracker -> final article.
_MAX_REDIRECTS = 5


def is_tco_url(url: str) -> bool:
    """True if `url`'s host is in TCO_HOSTS (t.co, etc.)."""
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in TCO_HOSTS


# Hosts that host X-native long-form articles under /i/article/{id}.
# These return HTTP 200 but with login-walled HTML — the only way to
# get a parseable title is via TwitterAPI.io's get_article endpoint.
X_ARTICLE_HOSTS: frozenset[str] = frozenset(
    {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}
)

# Match /i/article/{numeric_id} optionally followed by / or query string.
# Examples that should match:
#   https://x.com/i/article/2064029478616182784
#   https://twitter.com/i/article/123/foo
#   https://x.com/i/article/123?utm=abc
# Examples that should NOT match:
#   https://x.com/foo/article/123    (wrong path)
#   https://x.com/i/article/abc      (non-numeric)
_X_ARTICLE_PATH_RE = re.compile(
    r"^/i/article/(?P<tweet_id>\d+)(?:[/?#].*)?$"
)


def x_article_tweet_id(url: str) -> str | None:
    """Return the tweet_id if `url` is an X-native article, else None.

    The trailing path segment of an x.com/i/article/{id} URL IS the
    tweet_id of the tweet that links to the article. The TwitterAPI.io
    `get_article` endpoint takes that tweet_id and returns the full
    article body.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    if host not in X_ARTICLE_HOSTS:
        return None
    m = _X_ARTICLE_PATH_RE.match(parsed.path or "")
    if not m:
        return None
    return m.group("tweet_id")


def resolve_tco(url: str, *, timeout_s: float = 5.0) -> str | None:
    """Follow t.co (and similar) redirects to discover the real URL.

    Uses a HEAD request with allow_redirects=True; falls back to a
    streaming GET that bails after the first chunk if HEAD returns
    a non-redirect 2xx/4xx (some sites don't accept HEAD).

    Returns the final URL (different host from t.co) or None on any
    error. Returns the input URL unchanged if it doesn't look like a
    t.co link.
    """
    if not url:
        return None
    if not is_tco_url(url):
        return url
    try:
        # HEAD is cheapest. allow_redirects=True follows the chain.
        r = requests.head(
            url,
            timeout=timeout_s,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*"},
            allow_redirects=True,
        )
        # Some sites return 4xx on HEAD. If so, retry with GET (no body).
        if not (200 <= r.status_code < 400):
            r.close()
            r = requests.get(
                url,
                timeout=timeout_s,
                headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*"},
                allow_redirects=True,
                stream=True,
            )
            # Close immediately; we only want the URL, not the body.
            r.close()
        final = r.url
    except requests.RequestException as e:
        log.info("resolve_tco: %s -> %s", url, e)
        return None
    if not final or final == url:
        return None
    # If we still ended up on a t.co host, the chain didn't resolve.
    if is_tco_url(final):
        return None
    return final


# --- HTTP fetching (v1.2 commit 3) ---------------------------------------


# Cap on response body size. Titles are near the top of the document;
# 50KB is enough to capture them while protecting the pipeline from
# the 30MB pages some sites serve.
_MAX_HTML_BYTES = 50 * 1024

# Per-host throttle: minimum seconds between two fetches to the same
# host. Cheap defense against hammering a single origin when 10
# different posts in a batch all link to the same article.
_PER_HOST_MIN_INTERVAL_S = 1.0

# User-Agent. Identify ourselves so site operators can reach out if
# the volume ever becomes a problem.
_USER_AGENT = "x-monitor/1.2 (+https://github.com/allenwlee/minimax-marketing)"


def fetch_url(url: str, *, timeout_s: float = 5.0) -> str | None:
    """GET a URL, cap the body to 50KB, return the decoded text.

    Returns None on any error: timeout, connection, non-2xx, decode,
    or oversized body. We do NOT raise — the caller wants to know
    "did we get a usable HTML chunk?" and a None is the same signal
    as "no" everywhere.
    """
    if not url:
        return None
    try:
        r = requests.get(
            url,
            timeout=timeout_s,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*"},
            allow_redirects=True,
            stream=True,  # so we can bail at _MAX_HTML_BYTES
        )
    except requests.RequestException as e:
        log.info("fetch_url: request failed for %s: %s", url, e)
        return None
    if not (200 <= r.status_code < 300):
        log.info("fetch_url: %s returned %d", url, r.status_code)
        return None
    # Read up to the cap, then close the stream.
    buf = bytearray()
    try:
        for chunk in r.iter_content(chunk_size=4096):
            if not chunk:
                continue
            # Stop BEFORE the next chunk would push us over the cap.
            # This guarantees len(buf) <= _MAX_HTML_BYTES at exit.
            if len(buf) + len(chunk) > _MAX_HTML_BYTES:
                remaining = _MAX_HTML_BYTES - len(buf)
                if remaining > 0:
                    buf.extend(chunk[:remaining])
                break
            buf.extend(chunk)
    except requests.RequestException as e:
        log.info("fetch_url: read failed for %s: %s", url, e)
        return None
    finally:
        try:
            r.close()
        except Exception:
            pass
    try:
        return buf.decode(r.encoding or "utf-8", errors="replace")
    except LookupError:
        return buf.decode("utf-8", errors="replace")


# --- Headlines cache (v1.2 commit 3) ------------------------------------


# Cache file format version. Bump if the on-disk schema changes;
# older versions are loaded then re-written under the new shape.
CACHE_VERSION = 1

# Sources reported in cache entries and on post rows.
SOURCE_FETCHED = "fetched"
SOURCE_CACHED = "cached"
SOURCE_URL_ONLY = "url_only"
SOURCE_FETCH_FAILED = "fetch_failed"

# A successful "fetched" entry is fresh for this many days. After that,
# re-fetch. Kept short so headline drift / link rot is corrected
# automatically without a manual backfill.
_MAX_AGE_DAYS = 14

# 403/timeout (fetch_failed) entries: retry after 1 day so we don't
# keep hammering a Cloudflare-blocked origin.
_FAIL_TTL_DAYS = 1


class HeadlinesCache:
    """JSON-file-backed headline cache. File-locked for concurrent safety.

    Schema (v1):
      {
        "version": 1,
        "entries": {
          "<normalized_url>": {
            "title": "..." | null,
            "source": "fetched" | "cached" | "fetch_failed",
            "fetched_at": "2026-06-10T01:23:45Z",
            "status_code": 200 | null,
            "error": null | "timeout" | "..."
          },
          ...
        }
      }
    """

    def __init__(self, path: Path):
        self.path = path
        self._host_last_fetch: dict[str, float] = {}

    # --- low-level file I/O ----------------------------------------------

    def _lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".lock")

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": CACHE_VERSION, "entries": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": CACHE_VERSION, "entries": {}}
        if not isinstance(data, dict) or "entries" not in data:
            return {"version": CACHE_VERSION, "entries": {}}
        # Future-proof: upgrade older versions by re-writing in current
        # shape. For now only v1 exists, so this is a no-op.
        data.setdefault("version", CACHE_VERSION)
        return data

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def _with_lock(self, fn):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path()
        with open(lock_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    # --- public API -------------------------------------------------------

    def get(self, url: str, *, key_override: str | None = None) -> dict[str, Any] | None:
        """Return the cache entry for `url` (key = normalize_url) or None.

        `key_override` is an escape hatch for callers that want a
        different key (e.g., X-article lookups key on tweet_id, not URL).
        """
        key = key_override or cache_key_for(url)
        if not key:
            return None

        def op() -> dict[str, Any] | None:
            data = self._read_unlocked()
            entry = (data.get("entries") or {}).get(key)
            if not entry:
                return None
            if not self._is_fresh(entry):
                # Stale — let the caller re-fetch.
                return None
            return entry

        return self._with_lock(op)

    def put(
        self,
        url: str,
        title: str | None,
        source: str,
        *,
        status_code: int | None = None,
        error: str | None = None,
        key_override: str | None = None,
    ) -> None:
        """Write a cache entry. Idempotent: re-writing the same key is fine.

        `key_override` mirrors HeadlinesCache.get — lets callers store
        under a custom key (e.g., `x_article:{tweet_id}` for articles).
        """
        key = key_override or cache_key_for(url)
        if not key:
            return

        def op() -> None:
            data = self._read_unlocked()
            data.setdefault("entries", {})
            data["entries"][key] = {
                "title": title,
                "source": source,
                "fetched_at": _now_iso(),
                "status_code": status_code,
                "error": error,
            }
            self._write_unlocked(data)

        self._with_lock(op)

    def _is_fresh(self, entry: dict[str, Any]) -> bool:
        """A fetched/cached entry is fresh for _MAX_AGE_DAYS; failed for
        _FAIL_TTL_DAYS. Missing/invalid timestamp => not fresh."""
        ts = entry.get("fetched_at")
        if not ts:
            return False
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return False
        age = datetime.now(timezone.utc) - when
        if entry.get("source") == SOURCE_FETCH_FAILED:
            return age <= timedelta(days=_FAIL_TTL_DAYS)
        return age <= timedelta(days=_MAX_AGE_DAYS)

    # --- per-host throttle (advisory) ------------------------------------

    def host_throttle_ok(self, url: str) -> bool:
        """True if the per-host throttle window has elapsed.

        Returns True on the first call for a host. Subsequent calls
        within _PER_HOST_MIN_INTERVAL_S return False. This is a
        soft in-process throttle — it does NOT persist across runs.
        """
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return True
        now = time.monotonic()
        last = self._host_last_fetch.get(host, 0.0)
        if now - last < _PER_HOST_MIN_INTERVAL_S:
            return False
        self._host_last_fetch[host] = now
        return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- enrich_posts (v1.2 commit 3) ---------------------------------------


# Per-run and per-query caps on HTTP fetches. Backfill uses larger
# caps; the live pipeline uses the defaults so a long run doesn't
# get stuck on slow origins.
DEFAULT_PER_QUERY_CAP = 8
DEFAULT_PER_RUN_CAP = 50


def _extract_url(text: str) -> str | None:
    """Pull the first http(s) URL out of a post text.

    Returns the URL or None. Used by enrich_posts to identify which
    URL to fetch for URL-only posts.
    """
    if not text:
        return None
    m = re.search(r"https?://\S+", text)
    return m.group(0) if m else None


def _is_url_only(text: str | None) -> bool:
    """True if the post text is essentially just one or more URLs.

    Re-imported here to avoid a circular dep with relevance.py at
    import time. Mirrors the relevance.is_url_only logic exactly.
    """
    if not text:
        return False
    # Strip t.co / http(s) URLs; if nothing remains, it's URL-only.
    stripped = re.sub(r"https?://t\.co/\w+", "", text, flags=re.IGNORECASE)
    stripped = re.sub(r"https?://\S+", "", stripped, flags=re.IGNORECASE)
    return stripped.strip() == ""


def enrich_posts(
    items: list[dict[str, Any]],
    cache: HeadlinesCache,
    *,
    per_query_cap: int = DEFAULT_PER_QUERY_CAP,
    run_fetches_used: list[int] | None = None,
    per_run_cap: int = DEFAULT_PER_RUN_CAP,
    api: Any | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Walk items, find URL-only posts, fetch/cache their headlines.

    Args:
        items: list of normalized post dicts. Mutated in place: each
            URL-only post gets `headline` and `headline_source` set.
        cache: the headlines cache (versioned, file-locked).
        per_query_cap: max number of fetches within this call.
        run_fetches_used: mutable single-element list [int] used as a
            per-run counter. Caller owns it. If the cap is reached
            the remaining URL-only posts get source="url_only" (no
            fetch attempted).
        per_run_cap: max total fetches in the run.

    Returns:
        (items, stats). `items` is the same list, with headline fields
        added. `stats` is {n_url_only, n_fetched, n_cached, n_failed,
        n_skipped_cap, n_via_api}.

    The optional `api` argument is a TwitterApiClient-like object with
    a `.get_article(tweet_id) -> dict | None` method. When the resolved
    URL of a URL-only post is an X-native long-form article
    (x.com/i/article/{id}), the article title is fetched via get_article
    instead of scraping HTML. Cache key for X-articles is the tweet_id.
    """
    stats = {
        "n_url_only": 0,
        "n_fetched": 0,
        "n_cached": 0,
        "n_failed": 0,
        "n_skipped_cap": 0,
        "n_via_api": 0,
    }
    # url -> (headline, source) map for posts seen earlier in this
    # query. Lets us satisfy the "same article twice in one batch"
    # case without a second fetch AND without leaving the second post
    # without a headline_source field.
    seen_results: dict[str, tuple[str | None, str]] = {}
    fetches_in_query = 0
    for item in items:
        text = item.get("text") or ""
        if not _is_url_only(text):
            continue
        stats["n_url_only"] += 1
        url = _extract_url(text)
        if not url:
            item["headline"] = None
            item["headline_source"] = SOURCE_URL_ONLY
            continue
        # If this is a t.co link, resolve it first. The cache key and
        # the fetch target are based on the *resolved* URL, so 145
        # distinct t.co links pointing to the same article all share
        # one cache entry.
        fetch_target = url
        if is_tco_url(url):
            resolved = resolve_tco(url)
            if resolved:
                fetch_target = resolved
            # If resolve_tco failed, fall through and try the t.co URL
            # itself (fetch_url will follow redirects anyway).
        # X-native article routing: if the resolved URL is an
        # x.com/i/article/{id}, use the TwitterAPI.io get_article
        # endpoint (100 credits per call). Cache key is the tweet_id.
        # Bypasses per-host throttle (the API is the throttle, not
        # the network) and the per-query fetch cap (still counted
        # against per_run_cap so we don't blow the budget).
        # Cache key for the resolved URL (computed once for both the
        # X-article branch and the fallthrough HTTP fetch path).
        key = cache_key_for(fetch_target)
        # X-native article routing: if the resolved URL is an
        # x.com/i/article/{id}, use the TwitterAPI.io get_article
        # endpoint (100 credits per call). Cache key is the tweet_id.
        # Bypasses per-host throttle (the API is the throttle, not
        # the network) and the per-query fetch cap (still counted
        # against per_run_cap so we don't blow the budget).
        x_tid = x_article_tweet_id(fetch_target)
        if x_tid is not None and api is not None:
            x_key = f"x_article:{x_tid}"
            # Per-query dedupe for X-articles too.
            if x_key in seen_results:
                headline, source = seen_results[x_key]
                item["headline"] = headline
                item["headline_source"] = source
                continue
            # Per-run cap check (API calls are not free).
            if run_fetches_used is not None and run_fetches_used[0] >= per_run_cap:
                item["headline"] = None
                item["headline_source"] = SOURCE_URL_ONLY
                seen_results[x_key] = (None, SOURCE_URL_ONLY)
                seen_results[key] = (None, SOURCE_URL_ONLY)
                stats["n_skipped_cap"] += 1
                continue
            # Cache check (keyed on tweet_id, not URL).
            hit = cache.get(x_tid, key_override=x_key)
            if hit is not None:
                item["headline"] = hit.get("title")
                item["headline_source"] = SOURCE_CACHED
                seen_results[x_key] = (item["headline"], SOURCE_CACHED)
                seen_results[key] = (item["headline"], SOURCE_CACHED)
                stats["n_cached"] += 1
                # We count this as "via the api path" even though no
                # API call was made (it would have been, on a miss).
                stats["n_via_api"] = stats.get("n_via_api", 0) + 1
                continue
            # Fetch via API.
            try:
                article = api.get_article(x_tid)
            except Exception as e:
                log.info("enrich_posts: get_article(%s) failed: %s", x_tid, e)
                article = None
            fetches_in_query += 1
            if run_fetches_used is not None:
                run_fetches_used[0] += 1
            if article is None:
                cache.put(x_tid, None, SOURCE_FETCH_FAILED, error="api_no_article", key_override=x_key)
                item["headline"] = None
                item["headline_source"] = SOURCE_FETCH_FAILED
                seen_results[x_key] = (None, SOURCE_FETCH_FAILED)
                seen_results[key] = (None, SOURCE_FETCH_FAILED)
                stats["n_failed"] += 1
                stats["n_via_api"] = stats.get("n_via_api", 0) + 1
                continue
            title = article.get("title")
            cache.put(x_tid, title, SOURCE_FETCHED, status_code=200, key_override=x_key)
            source = SOURCE_FETCHED if title else SOURCE_FETCH_FAILED
            item["headline"] = title
            item["headline_source"] = source
            seen_results[x_key] = (title, source)
            seen_results[key] = (title, source)
            if title:
                stats["n_fetched"] += 1
            else:
                stats["n_failed"] += 1
            stats["n_via_api"] = stats.get("n_via_api", 0) + 1
            continue

        # `key` was computed at the top of the loop (above the X-article
        # branch). Per-query dedupe: reuse the result from earlier in this query.
        if key in seen_results:
            headline, source = seen_results[key]
            item["headline"] = headline
            item["headline_source"] = source
            continue
        # Caps: per-query first, then per-run.
        if fetches_in_query >= per_query_cap:
            item["headline"] = None
            item["headline_source"] = SOURCE_URL_ONLY
            seen_results[key] = (None, SOURCE_URL_ONLY)
            stats["n_skipped_cap"] += 1
            continue
        if run_fetches_used is not None and run_fetches_used[0] >= per_run_cap:
            item["headline"] = None
            item["headline_source"] = SOURCE_URL_ONLY
            seen_results[key] = (None, SOURCE_URL_ONLY)
            stats["n_skipped_cap"] += 1
            continue
        # Cache lookup.
        hit = cache.get(fetch_target)
        if hit is not None:
            item["headline"] = hit.get("title")
            item["headline_source"] = SOURCE_CACHED
            seen_results[key] = (item["headline"], SOURCE_CACHED)
            stats["n_cached"] += 1
            continue
        # Per-host throttle: if we just fetched the same host, skip.
        # Keyed on the *resolved* host so 145 t.co links all throttle
        # to one fetch per second on the real origin (nytimes.com, etc).
        if not cache.host_throttle_ok(fetch_target):
            item["headline"] = None
            item["headline_source"] = SOURCE_URL_ONLY
            seen_results[key] = (None, SOURCE_URL_ONLY)
            stats["n_skipped_cap"] += 1
            continue
        # Fetch.
        html = fetch_url(fetch_target)
        fetches_in_query += 1
        if run_fetches_used is not None:
            run_fetches_used[0] += 1
        if html is None:
            cache.put(fetch_target, None, SOURCE_FETCH_FAILED, error="fetch_failed")
            item["headline"] = None
            item["headline_source"] = SOURCE_FETCH_FAILED
            seen_results[key] = (None, SOURCE_FETCH_FAILED)
            stats["n_failed"] += 1
            continue
        title = parse_title(html)
        cache.put(fetch_target, title, SOURCE_FETCHED, status_code=200)
        source = SOURCE_FETCHED if title else SOURCE_FETCH_FAILED
        item["headline"] = title
        item["headline_source"] = source
        seen_results[key] = (title, source)
        if title:
            stats["n_fetched"] += 1
        else:
            stats["n_failed"] += 1
    return items, stats
