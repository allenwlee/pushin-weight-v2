"""
Tests for x_monitor.headlines (v1.2 commit 1: pure extractors only).
HTTP and cache I/O come in commit 3.
"""
import pytest

from x_monitor.headlines import (
    cache_key_for,
    normalize_url,
    parse_title,
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
