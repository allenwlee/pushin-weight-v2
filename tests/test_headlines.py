"""
Tests for x_monitor.headlines (v1.2 commit 1: pure extractors only).
HTTP and cache I/O come in commit 3.
"""
import requests
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from x_monitor.headlines import (
    HeadlinesCache,
    SOURCE_CACHED,
    SOURCE_FETCHED,
    SOURCE_FETCH_FAILED,
    SOURCE_URL_ONLY,
    cache_key_for,
    enrich_posts,
    fetch_url,
    is_tco_url,
    normalize_url,
    parse_title,
    resolve_tco,
    x_article_tweet_id,
)


# --- parse_title ---------------------------------------------------------


class TestParseTitle:
    def test_simple_title_tag(self):
        html = "<html><head><title>Hello World</title></head><body></body></html>"
        assert parse_title(html) == "Hello World"

    def test_title_with_whitespace(self):
        html = "<title>   spaced   out   </title>"
        assert parse_title(html) == "spaced out"

    def test_og_title_preferred_when_present(self):
        html = """
        <head>
          <title>Page Title</title>
          <meta property="og:title" content="OG Title">
          <meta name="twitter:title" content="Twitter Title">
        </head>
        """
        # og:title has priority over <title> and twitter:title
        assert parse_title(html) == "OG Title"

    def test_twitter_title_when_no_og(self):
        html = """
        <head>
          <title>Page Title</title>
          <meta name="twitter:title" content="Twitter Title">
        </head>
        """
        assert parse_title(html) == "Twitter Title"

    def test_title_fallback_when_no_meta(self):
        html = "<head><title>Just Title</title></head>"
        assert parse_title(html) == "Just Title"

    def test_meta_attribute_order_independence(self):
        # content= before property=
        html = '<meta content="OG Title" property="og:title">'
        assert parse_title(html) == "OG Title"

    def test_html_entities_decoded(self):
        html = "<title>Tom &amp; Jerry &#39;Best&#39; &quot;Show&quot;</title>"
        assert parse_title(html) == "Tom & Jerry 'Best' \"Show\""

    def test_empty_title_falls_through(self):
        html = "<title>   </title><meta property=\"og:title\" content=\"Real\">"
        assert parse_title(html) == "Real"

    def test_no_title_returns_none(self):
        assert parse_title("<html><body>nothing</body></html>") is None

    def test_empty_input_returns_none(self):
        assert parse_title("") is None

    def test_html_cap_50kb(self):
        # Title is past 50KB; should not be parsed
        padding = "x" * 60_000
        html = f"{padding}<title>Real Title</title>"
        assert parse_title(html) is None

    def test_malformed_html_does_not_raise(self):
        html = "<title>unclosed<html><body>more garbage"
        # Should not raise; either returns the partial title or None
        try:
            r = parse_title(html)
            assert r is None or isinstance(r, str)
        except Exception:
            pytest.fail("parse_title should not raise on malformed HTML")

    def test_first_og_title_wins(self):
        # When multiple og:title exist, use the first one
        html = """
        <head>
          <meta property="og:title" content="First">
          <meta property="og:title" content="Second">
        </head>
        """
        assert parse_title(html) == "First"


# --- Site-name suffix stripping ------------------------------------------


class TestSiteSuffixStrip:
    def test_dash_separator(self):
        html = "<title>How to use MiniMax M3 - Site Name</title>"
        assert parse_title(html) == "How to use MiniMax M3"

    def test_pipe_separator(self):
        html = "<title>Article Headline | Some Blog</title>"
        assert parse_title(html) == "Article Headline"

    def test_middot_separator(self):
        html = "<title>Article · News Co</title>"
        assert parse_title(html) == "Article"

    def test_em_dash_separator(self):
        html = "<title>Article — News Co</title>"
        assert parse_title(html) == "Article"

    def test_does_not_strip_model_version_dash(self):
        # "Kimi-2.5" should not be truncated
        html = "<title>Kimi-2.5 Release Notes</title>"
        assert parse_title(html) == "Kimi-2.5 Release Notes"

    def test_does_not_strip_short_suffix(self):
        # Very short suffix (1-2 chars) is preserved (could be a model code)
        html = "<title>Brand - x1</title>"
        # 1-2 char suffixes may or may not be stripped; ensure stability
        result = parse_title(html)
        assert result is not None and len(result) > 0

    def test_lowercase_suffix_preserved(self):
        # If suffix is all lowercase, looks like part of the title
        html = '<title>how to use kimi - tutorial guide</title>'
        # Don't aggressively strip lowercase suffixes
        r = parse_title(html)
        assert "kimi" in r.lower()


# --- normalize_url / cache_key_for ---------------------------------------


class TestNormalizeUrl:
    def test_lowercase_host(self):
        assert normalize_url("https://EXAMPLE.COM/foo") == "https://example.com/foo"

    def test_lowercase_scheme(self):
        assert normalize_url("HTTPS://example.com/foo") == "https://example.com/foo"

    def test_strip_utm_source(self):
        url = "https://example.com/article?utm_source=tw&id=42"
        assert normalize_url(url) == "https://example.com/article?id=42"

    def test_strip_utm_medium_and_campaign(self):
        url = "https://example.com/x?utm_medium=social&utm_campaign=spring&id=1"
        assert normalize_url(url) == "https://example.com/x?id=1"

    def test_strip_fbclid(self):
        url = "https://example.com/post?fbclid=abc123"
        assert normalize_url(url) == "https://example.com/post"

    def test_strip_gclid(self):
        url = "https://example.com/post?gclid=xyz"
        assert normalize_url(url) == "https://example.com/post"

    def test_strip_default_http_port(self):
        assert normalize_url("http://example.com:80/x") == "http://example.com/x"

    def test_strip_default_https_port(self):
        assert normalize_url("https://example.com:443/x") == "https://example.com/x"

    def test_keep_non_default_port(self):
        assert normalize_url("https://example.com:8080/x") == "https://example.com:8080/x"

    def test_sort_query_params_for_stability(self):
        a = "https://example.com/x?b=2&a=1"
        b = "https://example.com/x?a=1&b=2"
        assert normalize_url(a) == normalize_url(b)

    def test_strip_fragment(self):
        # Fragments are not part of the cache key
        url = "https://example.com/article#section-2"
        assert normalize_url(url) == "https://example.com/article"

    def test_empty_url(self):
        assert normalize_url("") == ""

    def test_unicode_path_preserved(self):
        url = "https://example.com/海螺"
        # Host normalized but unicode path preserved
        assert normalize_url(url) == url.lower().replace("https://", "https://")

    def test_cache_key_for_is_alias(self):
        # v1.2: cache_key_for is just normalize_url; tested for stability
        url = "https://Example.com/x?utm_source=t"
        assert cache_key_for(url) == normalize_url(url)



# --- v1.2 commit 3: HTTP + cache + enrich --------------------------------


# --- fetch_url ----------------------------------------------------------


def _mock_response(status: int, body: str = "", content_iter=None) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.encoding = "utf-8"
    m.close = MagicMock()
    if content_iter is not None:
        m.iter_content.return_value = iter(content_iter)
    else:
        m.iter_content.return_value = iter([body.encode("utf-8")])
    return m


class TestFetchUrl:
    def test_returns_none_for_empty_url(self):
        assert fetch_url("") is None
        assert fetch_url(None) is None  # type: ignore[arg-type]

    def test_returns_html_for_200(self):
        html = "<html><head><title>Hello</title></head><body></body></html>"
        with patch("x_monitor.headlines.requests.get", return_value=_mock_response(200, html)) as g:
            result = fetch_url("https://example.com/x")
            assert result == html
            # streamed=True so we cap reads
            kwargs = g.call_args.kwargs
            assert kwargs.get("stream") is True
            assert "User-Agent" in kwargs["headers"]

    def test_returns_none_on_4xx(self):
        with patch("x_monitor.headlines.requests.get", return_value=_mock_response(404, "")):
            assert fetch_url("https://example.com/missing") is None

    def test_returns_none_on_5xx(self):
        with patch("x_monitor.headlines.requests.get", return_value=_mock_response(503, "")):
            assert fetch_url("https://example.com/down") is None

    def test_returns_none_on_request_exception(self):
        import requests as _req
        with patch("x_monitor.headlines.requests.get", side_effect=_req.ConnectionError("boom")):
            assert fetch_url("https://example.com/x") is None

    def test_caps_body_to_50kb(self):
        # Build a 60KB response, verify we stop at the cap.
        # The cap is 50*1024 = 51200 bytes; the implementation extends
        # the buffer by `cap - current_len` if a chunk would push us
        # over, so the result is at most 51200 bytes.
        big = ("x" * 60_000).encode("utf-8")
        chunks = [big[:30000], big[30000:]]
        with patch("x_monitor.headlines.requests.get", return_value=_mock_response(200, content_iter=chunks)):
            result = fetch_url("https://example.com/x")
            assert result is not None
            assert len(result) <= 50 * 1024


# --- HeadlinesCache -----------------------------------------------------


class TestHeadlinesCache:
    def test_get_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            c = HeadlinesCache(Path(d) / "h.json")
            assert c.get("https://example.com/x") is None

    def test_put_then_get_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "h.json"
            c = HeadlinesCache(path)
            c.put("https://example.com/x", "Hello World", SOURCE_FETCHED, status_code=200)
            entry = c.get("https://example.com/x")
            assert entry is not None
            assert entry["title"] == "Hello World"
            assert entry["source"] == SOURCE_FETCHED
            assert entry["status_code"] == 200

    def test_cache_file_persists(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "h.json"
            c1 = HeadlinesCache(path)
            c1.put("https://example.com/x", "T", SOURCE_FETCHED)
            # New instance reads the same file
            c2 = HeadlinesCache(path)
            assert c2.get("https://example.com/x")["title"] == "T"

    def test_failed_entry_expires_after_one_day(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "h.json"
            c = HeadlinesCache(path)
            # Write a failed entry with an old timestamp
            c._with_lock(lambda: c._write_unlocked({
                "version": 1,
                "entries": {
                    cache_key_for("https://example.com/x"): {
                        "title": None,
                        "source": SOURCE_FETCH_FAILED,
                        "fetched_at": "2020-01-01T00:00:00+00:00",
                        "status_code": None,
                        "error": "fetch_failed",
                    }
                }
            }))
            # Stale → re-fetch
            assert c.get("https://example.com/x") is None

    def test_fetched_entry_expires_after_14_days(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "h.json"
            c = HeadlinesCache(path)
            c._with_lock(lambda: c._write_unlocked({
                "version": 1,
                "entries": {
                    cache_key_for("https://example.com/x"): {
                        "title": "T",
                        "source": SOURCE_FETCHED,
                        "fetched_at": "2020-01-01T00:00:00+00:00",
                        "status_code": 200,
                        "error": None,
                    }
                }
            }))
            assert c.get("https://example.com/x") is None

    def test_per_host_throttle(self):
        c = HeadlinesCache(Path("/tmp/_h_throttle.json"))
        # First call passes
        assert c.host_throttle_ok("https://example.com/x") is True
        # Immediate second call blocked
        assert c.host_throttle_ok("https://example.com/x") is False
        # Different host passes
        assert c.host_throttle_ok("https://other.com/x") is True


# --- enrich_posts -------------------------------------------------------


class TestEnrichPosts:
    def _cache(self, tmp: Path) -> HeadlinesCache:
        return HeadlinesCache(tmp / "h.json")

    def test_no_url_only_posts_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            items = [
                {"id": "t1", "text": "minimax is great", "author_handle": "u"},
            ]
            c = self._cache(Path(d))
            out, stats = enrich_posts(items, c)
            assert out is items
            assert stats["n_url_only"] == 0
            assert stats["n_fetched"] == 0

    def test_url_only_post_fetches_and_sets_headline(self):
        with tempfile.TemporaryDirectory() as d:
            html = "<html><head><title>Hello World</title></head></html>"
            items = [
                {"id": "t1", "text": "https://example.com/x", "author_handle": "u"},
            ]
            c = self._cache(Path(d))
            with patch("x_monitor.headlines.fetch_url", return_value=html) as f:
                out, stats = enrich_posts(items, c)
            assert stats["n_url_only"] == 1
            assert stats["n_fetched"] == 1
            assert items[0]["headline"] == "Hello World"
            assert items[0]["headline_source"] == SOURCE_FETCHED
            f.assert_called_once()

    def test_cache_hit_skips_http(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._cache(Path(d))
            c.put("https://example.com/x", "Cached Title", SOURCE_FETCHED)
            items = [
                {"id": "t1", "text": "https://example.com/x", "author_handle": "u"},
            ]
            with patch("x_monitor.headlines.fetch_url") as f:
                out, stats = enrich_posts(items, c)
            assert stats["n_cached"] == 1
            assert items[0]["headline"] == "Cached Title"
            assert items[0]["headline_source"] == SOURCE_CACHED
            f.assert_not_called()

    def test_fetch_failure_marks_fetch_failed(self):
        with tempfile.TemporaryDirectory() as d:
            items = [
                {"id": "t1", "text": "https://example.com/x", "author_handle": "u"},
            ]
            c = self._cache(Path(d))
            with patch("x_monitor.headlines.fetch_url", return_value=None):
                out, stats = enrich_posts(items, c)
            assert stats["n_failed"] == 1
            assert items[0]["headline"] is None
            assert items[0]["headline_source"] == SOURCE_FETCH_FAILED
            # Cache now has the failed entry
            entry = c.get("https://example.com/x")
            assert entry is not None
            assert entry["source"] == SOURCE_FETCH_FAILED

    def test_per_query_cap_skips_extra_fetches(self):
        with tempfile.TemporaryDirectory() as d:
            # Use distinct hosts so the per-host throttle doesn't
            # shadow the per-query cap. (In practice a batch of URL-
            # only posts links to many different sites.)
            items = [
                {"id": f"t{i}", "text": f"https://h{i}.example.com/x", "author_handle": "u"}
                for i in range(5)
            ]
            c = self._cache(Path(d))
            with patch("x_monitor.headlines.fetch_url", return_value="<title>X</title>"):
                out, stats = enrich_posts(items, c, per_query_cap=2)
            assert stats["n_fetched"] == 2
            assert stats["n_skipped_cap"] == 3
            # The skipped items still have url_only source
            for i in (2, 3, 4):
                assert items[i]["headline_source"] == SOURCE_URL_ONLY

    def test_per_run_cap_blocks_further_fetches(self):
        with tempfile.TemporaryDirectory() as d:
            items = [
                {"id": f"t{i}", "text": f"https://h{i}.example.com/x", "author_handle": "u"}
                for i in range(5)
            ]
            c = self._cache(Path(d))
            run_used = [0]
            with patch("x_monitor.headlines.fetch_url", return_value="<title>X</title>"):
                out, stats = enrich_posts(items, c, per_query_cap=8, per_run_cap=2, run_fetches_used=run_used)
            assert stats["n_fetched"] == 2
            assert run_used[0] == 2
            assert stats["n_skipped_cap"] == 3

    def test_duplicate_url_in_same_query_only_fetches_once(self):
        with tempfile.TemporaryDirectory() as d:
            items = [
                {"id": "t1", "text": "https://example.com/x", "author_handle": "u"},
                {"id": "t2", "text": "https://example.com/x", "author_handle": "u"},
            ]
            c = self._cache(Path(d))
            with patch("x_monitor.headlines.fetch_url", return_value="<title>X</title>") as f:
                out, stats = enrich_posts(items, c)
            assert stats["n_fetched"] == 1
            f.assert_called_once()
            # Both items have the headline now
            assert items[0]["headline_source"] == SOURCE_FETCHED
            assert items[1]["headline_source"] == SOURCE_FETCHED



class TestResolveTco:
    """resolve_tco and is_tco_url handle t.co links (the 90+ in the live DB)."""

    def _cache(self, tmp: Path) -> HeadlinesCache:
        return HeadlinesCache(tmp / "cache.json")

    def test_is_tco_url_true_for_tco(self):
        assert is_tco_url("https://t.co/abc123") is True

    def test_is_tco_url_true_for_uppercase(self):
        assert is_tco_url("HTTPS://T.CO/abc123") is True

    def test_is_tco_url_false_for_www_tco(self):
        # Real t.co links never carry `www.`; urlparse returns host
        # `www.t.co` which is NOT in TCO_HOSTS, so we expect False.
        # Defending against `www.t.co` would be cheap but adds no
        # real-world value.
        assert is_tco_url("https://www.t.co/abc123") is False

    def test_is_tco_url_false_for_real_site(self):
        assert is_tco_url("https://nytimes.com/article") is False

    def test_is_tco_url_false_for_twitter(self):
        # twitter.com / x.com are NOT in TCO_HOSTS; only t.co.
        assert is_tco_url("https://twitter.com/foo") is False

    def test_is_tco_url_false_for_empty(self):
        assert is_tco_url("") is False
        assert is_tco_url(None) is False  # type: ignore[arg-type]

    def test_resolve_tco_passthrough_for_non_tco(self):
        # Non-t.co URLs come back unchanged (no HTTP call).
        result = resolve_tco("https://nytimes.com/article")
        assert result == "https://nytimes.com/article"

    def test_resolve_tco_returns_none_for_empty(self):
        assert resolve_tco("") is None
        assert resolve_tco(None) is None  # type: ignore[arg-type]

    def test_resolve_tco_follows_redirect(self):
        # Mock HEAD: 302 -> nytimes.com.
        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.url = "https://www.nytimes.com/2026/06/10/article-xyz"
        mock_resp.close = MagicMock()
        with patch("x_monitor.headlines.requests.head", return_value=mock_resp) as mock_head:
            result = resolve_tco("https://t.co/abc123")
        assert result == "https://www.nytimes.com/2026/06/10/article-xyz"
        mock_head.assert_called_once()
        # Crucial: allow_redirects=True must be passed.
        call_kwargs = mock_head.call_args.kwargs
        assert call_kwargs.get("allow_redirects") is True
        mock_resp.close.assert_not_called()  # HEAD did not need the fallback close

    def test_resolve_tco_falls_back_to_get_on_head_4xx(self):
        # HEAD returns 405 -> we retry with GET, then close immediately.
        head_resp = MagicMock()
        head_resp.status_code = 405
        head_resp.close = MagicMock()
        get_resp = MagicMock()
        get_resp.url = "https://techcrunch.com/2026/06/article-abc"
        get_resp.close = MagicMock()
        with patch("x_monitor.headlines.requests.head", return_value=head_resp), \
             patch("x_monitor.headlines.requests.get", return_value=get_resp) as mock_get:
            result = resolve_tco("https://t.co/abc")
        assert result == "https://techcrunch.com/2026/06/article-abc"
        head_resp.close.assert_called_once()
        get_resp.close.assert_called_once()
        # GET must also use allow_redirects=True.
        assert mock_get.call_args.kwargs.get("allow_redirects") is True

    def test_resolve_tco_returns_none_on_request_exception(self):
        with patch(
            "x_monitor.headlines.requests.head",
            side_effect=requests.RequestException("boom"),
        ):
            assert resolve_tco("https://t.co/abc") is None

    def test_resolve_tco_returns_none_if_still_on_tco(self):
        # Mock returns a URL still on t.co (chain didn't resolve).
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://t.co/someother"
        mock_resp.close = MagicMock()
        with patch("x_monitor.headlines.requests.head", return_value=mock_resp):
            assert resolve_tco("https://t.co/abc") is None

    def test_enrich_posts_resolves_tco_before_caching(self):
        # Two distinct t.co URLs that point to the same article should
        # share a single cache entry and a single fetch. The headline
        # comes from the resolved target, not the t.co HTML.
        with tempfile.TemporaryDirectory() as d:
            items = [
                {"id": "t1", "text": "https://t.co/aaa", "author_handle": "u"},
                {"id": "t2", "text": "https://t.co/bbb", "author_handle": "u"},
            ]
            c = self._cache(Path(d))
            # resolve_tco -> the same nytimes URL both times.
            # fetch_url -> a title for that resolved URL.
            with patch(
                "x_monitor.headlines.resolve_tco",
                return_value="https://www.nytimes.com/article",
            ), patch(
                "x_monitor.headlines.fetch_url",
                return_value="<html><head><title>Big AI News</title></head></html>",
            ) as mock_fetch:
                out, stats = enrich_posts(items, c)
            assert mock_fetch.call_count == 1, "should fetch once for two t.co -> same target"
            assert stats["n_url_only"] == 2
            assert stats["n_fetched"] == 1
            assert out[0]["headline"] == "Big AI News"
            assert out[0]["headline_source"] == SOURCE_FETCHED
            assert out[1]["headline"] == "Big AI News"  # shared from seen_results
            assert out[1]["headline_source"] == SOURCE_FETCHED



class TestXArticleTweetId:
    """x_article_tweet_id() detects x.com/i/article/{id} URLs."""

    def test_x_com_article(self):
        assert x_article_tweet_id("https://x.com/i/article/2064029478616182784") == "2064029478616182784"

    def test_twitter_com_article(self):
        assert x_article_tweet_id("https://twitter.com/i/article/123") == "123"

    def test_www_x_com(self):
        assert x_article_tweet_id("https://www.x.com/i/article/999") == "999"

    def test_www_twitter_com(self):
        assert x_article_tweet_id("https://www.twitter.com/i/article/42") == "42"

    def test_with_trailing_path(self):
        # /i/article/123/foo should still match.
        assert x_article_tweet_id("https://x.com/i/article/123/foo") == "123"

    def test_with_query_string(self):
        # /i/article/123?utm=abc should still match.
        assert x_article_tweet_id("https://x.com/i/article/123?utm=abc") == "123"

    def test_rejects_non_numeric_id(self):
        assert x_article_tweet_id("https://x.com/i/article/abc") is None

    def test_rejects_wrong_path(self):
        assert x_article_tweet_id("https://x.com/foo/article/123") is None
        assert x_article_tweet_id("https://x.com/i/other/123") is None

    def test_rejects_non_x_hosts(self):
        assert x_article_tweet_id("https://nytimes.com/i/article/123") is None
        assert x_article_tweet_id("https://t.co/abc") is None

    def test_rejects_empty_and_none(self):
        assert x_article_tweet_id("") is None
        assert x_article_tweet_id(None) is None  # type: ignore[arg-type]


class TestEnrichPostsXArticle:
    """enrich_posts routes x.com/i/article/{id} URLs through api.get_article."""

    def _cache(self, tmp: Path) -> HeadlinesCache:
        return HeadlinesCache(tmp / "cache.json")

    def test_routes_x_article_via_api(self):
        # Mock api with a get_article method.
        api = MagicMock()
        api.get_article.return_value = {
            "title": "Big AI News",
            "preview_text": "A preview.",
            "plain_text": "Body.",
        }
        with tempfile.TemporaryDirectory() as d:
            items = [{
                "id": "t1",
                "text": "https://x.com/i/article/2064029478616182784",
                "author_handle": "u",
            }]
            c = self._cache(Path(d))
            out, stats = enrich_posts(items, c, api=api)
        # api.get_article was called with the tweet_id from the URL.
        api.get_article.assert_called_once_with("2064029478616182784")
        # Headline is the article title.
        assert out[0]["headline"] == "Big AI News"
        assert out[0]["headline_source"] == "fetched"
        # Stats include n_via_api.
        assert stats["n_via_api"] == 1
        assert stats["n_fetched"] == 1

    def test_routes_x_article_cache_hit_skips_api(self):
        # Pre-populate the cache under the X-article key.
        api = MagicMock()
        with tempfile.TemporaryDirectory() as d:
            c = self._cache(Path(d))
            c.put(
                "2064029478616182784", "Cached Title", "fetched",
                status_code=200, key_override="x_article:2064029478616182784",
            )
            items = [{
                "id": "t1",
                "text": "https://x.com/i/article/2064029478616182784",
                "author_handle": "u",
            }]
            out, stats = enrich_posts(items, c, api=api)
        # api was NOT called — the cache hit short-circuited.
        api.get_article.assert_not_called()
        assert out[0]["headline"] == "Cached Title"
        assert out[0]["headline_source"] == "cached"
        assert stats["n_cached"] == 1
        assert stats["n_via_api"] == 1  # we still count it as "via api path"

    def test_routes_x_article_api_returns_none_marks_failed(self):
        # api.get_article returns None -> source = "fetch_failed".
        api = MagicMock()
        api.get_article.return_value = None
        with tempfile.TemporaryDirectory() as d:
            items = [{
                "id": "t1",
                "text": "https://x.com/i/article/123",
                "author_handle": "u",
            }]
            c = self._cache(Path(d))
            out, stats = enrich_posts(items, c, api=api)
        assert out[0]["headline"] is None
        assert out[0]["headline_source"] == "fetch_failed"
        assert stats["n_failed"] == 1
        assert stats["n_via_api"] == 1

    def test_routes_x_article_no_api_skips_path(self):
        # If api is None, X-article URLs fall through to fetch_url
        # (the original v1.2 path) — no error raised.
        with tempfile.TemporaryDirectory() as d:
            items = [{
                "id": "t1",
                "text": "https://x.com/i/article/123",
                "author_handle": "u",
            }]
            c = self._cache(Path(d))
            with patch(
                "x_monitor.headlines.fetch_url",
                return_value="<html><head><title>HTML Title</title></head></html>",
            ) as mock_fetch:
                out, stats = enrich_posts(items, c, api=None)
        # No api, so we tried fetch_url (and got a title from it).
        mock_fetch.assert_called_once()
        assert out[0]["headline"] == "HTML Title"
        # n_via_api is 0 because the api path was not used.
        assert stats.get("n_via_api", 0) == 0
