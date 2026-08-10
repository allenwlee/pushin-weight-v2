"""Focused unit tests for the credential-free parts of the deployed smoke harness."""

from __future__ import annotations

import pytest

from scripts import smoke_v22_homepage as smoke

ROOT_HTML = """
<html><head>
  <link href="/static/home-v20.css?v=stack2" rel="stylesheet">
  <script src="/static/pw-filter-store.js" defer></script>
  <script src="/static/pw-filter-pills.js" defer></script>
  <script src="/static/pw-chart.js" defer></script>
  <script src="/static/pw-feed.js" defer></script>
  <script src="/static/pw-tz.js" defer></script>
  <script src="/static/pw-locale-toggle.js" defer></script>
  <script src="https://cdn.example.invalid/chart.js" defer></script>
</head><body data-pw-shell="v20">
  <section data-pw-chart></section>
  <section data-pw-feed></section>
  <button data-tz-widget><span data-tz-time>00:00</span></button>
</body></html>
"""


def test_expected_root_shell_has_no_missing_hooks_or_assets() -> None:
    assert smoke.missing_shell_hooks(ROOT_HTML) == []
    assert smoke.required_asset_urls(ROOT_HTML, "https://app.example/") == {
        "home-v20.css": "https://app.example/static/home-v20.css?v=stack2",
        "pw-filter-store.js": "https://app.example/static/pw-filter-store.js",
        "pw-filter-pills.js": "https://app.example/static/pw-filter-pills.js",
        "pw-chart.js": "https://app.example/static/pw-chart.js",
        "pw-feed.js": "https://app.example/static/pw-feed.js",
        "pw-tz.js": "https://app.example/static/pw-tz.js",
        "pw-locale-toggle.js": "https://app.example/static/pw-locale-toggle.js",
    }


def test_manifest_hashed_static_asset_is_checked_as_its_logical_asset() -> None:
    html = ROOT_HTML.replace("/static/home-v20.css", "/static/home-v20.123abc.css")
    assert smoke.required_asset_urls(html, "https://app.example/")["home-v20.css"] == (
        "https://app.example/static/home-v20.123abc.css?v=stack2"
    )


def test_missing_hook_and_cross_origin_asset_are_detected() -> None:
    html = ROOT_HTML.replace("data-pw-feed", "data-pw-not-feed").replace(
        'src="/static/pw-tz.js"', 'src="https://cdn.example.invalid/pw-tz.js"'
    )
    assert smoke.missing_shell_hooks(html) == ["feed entry point"]
    assert "pw-tz.js" not in smoke.required_asset_urls(html, "https://app.example/")


def test_cookie_parser_keeps_cookie_values_out_of_diagnostics() -> None:
    cookies = smoke._cookies_from_header("Cookie: sessionid=opaque-value; csrftoken=another-value")
    assert [cookie["name"] for cookie in cookies] == ["sessionid", "csrftoken"]
    with pytest.raises(ValueError, match="cookie header"):
        smoke._cookies_from_header("")
