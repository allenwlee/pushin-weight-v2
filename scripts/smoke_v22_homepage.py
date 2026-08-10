#!/usr/bin/env python3
"""Authenticated deployment smoke check for the v22 homepage.

The operator supplies a deployed root URL and a monitored account's cookie at
runtime.  Neither value is persisted or echoed by this script.

Usage:
  V22_SMOKE_URL=https://pushinweight-web.onrender.com/ \\
  V22_SMOKE_COOKIE='sessionid=...' \\
  python scripts/smoke_v22_homepage.py

Pass ``--browser`` (or set ``V22_SMOKE_BROWSER=1``) to also use Playwright to
confirm that the timezone widget replaces its server-rendered placeholder.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookies import CookieError, SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

URL_ENV = "V22_SMOKE_URL"
COOKIE_ENV = "V22_SMOKE_COOKIE"
BROWSER_ENV = "V22_SMOKE_BROWSER"

# These are deliberately the root-page entry points, rather than a copy of
# the full template.  The smoke check should fail on a cutover/login page but
# must not turn mutable production data into a visual golden test.
SHELL_HOOKS = {
    "root shell": ("data-pw-shell", "v20"),
    "chart entry point": ("data-pw-chart", None),
    "feed entry point": ("data-pw-feed", None),
    "timezone widget": ("data-tz-widget", None),
    "timezone time node": ("data-tz-time", None),
}
REQUIRED_ASSETS = (
    "home-v20.css",
    "pw-filter-store.js",
    "pw-filter-pills.js",
    "pw-chart.js",
    "pw-feed.js",
    "pw-tz.js",
    "pw-locale-toggle.js",
)


@dataclass(frozen=True)
class HttpResult:
    """The intentionally small, secret-free HTTP result used in reporting."""

    status: int | None
    body: str
    final_url: str
    content_type: str = ""


class _ShellHookParser(HTMLParser):
    """Collect real element attributes without accepting script/comment text."""

    def __init__(self) -> None:
        super().__init__()
        self.attributes: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.attributes.append(dict(attrs))


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    """Never replay an operator cookie onto another origin after a redirect."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        source = urlsplit(request.full_url)
        target = urlsplit(newurl)
        if (source.scheme, source.netloc) != (target.scheme, target.netloc):
            return None
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class _AssetParser(HTMLParser):
    """Collect local CSS/JS source references without evaluating HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"link", "script"}:
            return
        values = dict(attrs)
        source = values.get("href") if tag == "link" else values.get("src")
        if source:
            self.sources.append(source)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Run the optional Playwright timezone-population check.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20,
        help="Per-request and browser-navigation timeout in seconds (default: 20).",
    )
    return parser.parse_args(argv)


def _truthy(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def _valid_root_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _cookies_from_header(value: str) -> list[dict[str, str]]:
    """Parse a Cookie request header for Playwright, retaining values in memory only."""
    candidate = value.removeprefix("Cookie:").strip()
    jar = SimpleCookie()
    try:
        jar.load(candidate)
    except CookieError as exc:
        raise ValueError("cookie header could not be parsed") from exc
    cookies = [{"name": name, "value": morsel.value} for name, morsel in jar.items()]
    if not cookies:
        raise ValueError("cookie header is empty or invalid")
    return cookies


def missing_shell_hooks(html: str) -> list[str]:
    """Return human-safe labels for required v22 shell entry hooks."""
    parser = _ShellHookParser()
    parser.feed(html)
    parser.close()
    missing = []
    for label, (attribute, expected_value) in SHELL_HOOKS.items():
        if not any(
            attribute in attrs and (expected_value is None or attrs[attribute] == expected_value)
            for attrs in parser.attributes
        ):
            missing.append(label)
    return missing


def _required_asset_name(filename: str) -> str | None:
    """Map an unhashed or WhiteNoise-manifest filename to its logical asset."""
    for asset in REQUIRED_ASSETS:
        stem, extension = asset.rsplit(".", 1)
        if filename == asset or (
            filename.startswith(f"{stem}.") and filename.endswith(f".{extension}")
        ):
            return asset
    return None


def required_asset_urls(html: str, page_url: str) -> dict[str, str]:
    """Map required same-origin asset names to the URLs rendered by the page."""
    parser = _AssetParser()
    parser.feed(html)
    parser.close()
    page_origin = urlsplit(page_url)
    assets: dict[str, str] = {}
    for source in parser.sources:
        resolved = urljoin(page_url, source)
        parsed = urlsplit(resolved)
        if (parsed.scheme, parsed.netloc) != (page_origin.scheme, page_origin.netloc):
            continue
        filename = parsed.path.rsplit("/", 1)[-1]
        required_name = _required_asset_name(filename)
        if required_name:
            assets[required_name] = resolved
    return assets


def _fetch(url: str, cookie_header: str, timeout: float) -> HttpResult:
    """Fetch one URL while ensuring failures never include request credentials."""
    request = Request(
        url,
        headers={
            "Cookie": cookie_header,
            "User-Agent": "pushin-weight-v22-smoke/1.0",
        },
    )
    try:
        with build_opener(_SameOriginRedirectHandler()).open(request, timeout=timeout) as response:  # nosec B310: operator-controlled URL
            return HttpResult(
                status=response.getcode(),
                body=response.read().decode("utf-8", errors="replace"),
                final_url=response.geturl(),
                content_type=response.headers.get_content_type(),
            )
    except HTTPError as exc:
        return HttpResult(status=exc.code, body="", final_url=url)
    except (URLError, OSError, TimeoutError):
        return HttpResult(status=None, body="", final_url=url)


def _browser_timezone_check(
    page_url: str,
    cookies: Iterable[dict[str, str]],
    timeout_seconds: float,
) -> tuple[bool, str]:
    """Check the actual JS state only when the operator opts into Playwright."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "Playwright is not installed"

    parsed = urlsplit(page_url)
    cookie_url = f"{parsed.scheme}://{parsed.netloc}/"
    browser_cookies = [{**cookie, "url": cookie_url} for cookie in cookies]
    timeout_ms = max(1, int(timeout_seconds * 1000))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context()
                try:
                    context.add_cookies(browser_cookies)
                    page = context.new_page()
                    page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_function(
                        """() => {
                          const value = document.querySelector('[data-tz-time]')?.textContent?.trim();
                          return window.__pwTz && /^\\d{2}:\\d{2}$/.test(value || '');
                        }""",
                        timeout=timeout_ms,
                    )
                finally:
                    context.close()
            finally:
                browser.close()
    except (PlaywrightError, PlaywrightTimeoutError, OSError):
        return False, "timezone widget did not populate after browser execution"
    return True, "timezone widget populated after browser execution"


def _print_results(passes: list[str], failures: list[str], skipped: list[str]) -> None:
    print("v22 authenticated homepage smoke")
    for item in passes:
        print(f"PASS  {item}")
    for item in failures:
        print(f"FAIL  {item}")
    for item in skipped:
        print(f"SKIP  {item}")
    print(f"{len(passes)} passed, {len(failures)} failed, {len(skipped)} skipped")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    passes: list[str] = []
    failures: list[str] = []
    skipped: list[str] = []

    page_url = os.environ.get(URL_ENV, "").strip()
    cookie_header = os.environ.get(COOKIE_ENV, "")
    if not page_url:
        failures.append(f"missing {URL_ENV}; no request was sent")
    elif not _valid_root_url(page_url):
        failures.append(f"invalid {URL_ENV}; use an http(s) root URL")
    if not cookie_header:
        failures.append(f"missing {COOKIE_ENV}; no request was sent")

    cookies: list[dict[str, str]] = []
    if cookie_header:
        try:
            cookies = _cookies_from_header(cookie_header)
        except ValueError:
            failures.append(f"invalid {COOKIE_ENV}; no request was sent")

    if failures:
        _print_results(passes, failures, skipped)
        return 1

    root = _fetch(page_url, cookie_header, args.timeout)
    if root.status != 200:
        detail = "request could not be completed" if root.status is None else f"returned {root.status}"
        failures.append(f"authenticated root {detail}; verify the monitored login cookie")
        _print_results(passes, failures, skipped)
        return 1
    passes.append("authenticated root -> 200")

    missing_hooks = missing_shell_hooks(root.body)
    if missing_hooks:
        failures.append("authenticated root missing shell hooks: " + ", ".join(missing_hooks))
    else:
        passes.append("authenticated root contains required shell entry hooks")

    assets = required_asset_urls(root.body, root.final_url)
    for name in REQUIRED_ASSETS:
        asset_url = assets.get(name)
        if not asset_url:
            failures.append(f"required local asset is not referenced by root: {name}")
            continue
        result = _fetch(asset_url, cookie_header, args.timeout)
        expected_type = {"text/css"} if name.endswith(".css") else {"application/javascript", "text/javascript"}
        if result.status == 200 and result.content_type in expected_type:
            passes.append(f"local asset {name} -> 200")
        elif result.status == 200:
            failures.append(f"local asset {name} returned {result.content_type or 'unknown content type'}")
        elif result.status is None:
            failures.append(f"local asset {name} request could not be completed")
        else:
            failures.append(f"local asset {name} -> {result.status} (expected 200)")

    browser_requested = args.browser or _truthy(os.environ.get(BROWSER_ENV))
    if browser_requested:
        ok, message = _browser_timezone_check(root.final_url, cookies, args.timeout)
        (passes if ok else failures).append(message)
    else:
        skipped.append("timezone runtime check (re-run with --browser or V22_SMOKE_BROWSER=1)")

    _print_results(passes, failures, skipped)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
