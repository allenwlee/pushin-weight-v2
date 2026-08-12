"""Browser fidelity net for the fixture-backed v22 root route.

This is deliberately not a screenshot baseline: the canonical mockup is served
over HTTP beside Django's static live server and remains the comparison source.
Reports and paired PNGs are retained outside the checkout for review.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from playwright.sync_api import BrowserContext, Page, sync_playwright

from core.models import Post
from monitor.views import _clear_home_pulse_cache
from tests.mockup_spec import DEFAULT_SOURCE, MockupSpec, load_spec
from tests.shell_diff import AUTHORED_REGIONS, parse_rendered_html, select_one
from tests.v22_support import (
    V22_TEST_USER_EMAIL,
    fixture_from_oracle,
    seed_real_home_orm,
    seed_v22_metadata_regression_orm,
)

pytestmark = pytest.mark.requires_postgres

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 960},
    "mobile": {"width": 390, "height": 844},
}
LOCALES = ("zh_cn", "en", "original")
REGION_SELECTORS = dict(AUTHORED_REGIONS)
STYLE_PROPERTIES = ("display", "boxSizing", "fontFamily", "lineHeight")
# The threshold is intentionally below a wholly unrelated frame.  It is not a
# checked-in image baseline: every run compares fresh captures to the mockup.
# Initial reports against the canonical fixture landed at 0.25 (desktop) and
# 0.40 (mobile).  0.45 leaves rendering tolerance without accepting a new
# frame or a materially rearranged shell.
MAX_CHANGED_PIXEL_FRACTION = 0.45
PIXEL_DELTA = 32
DEFAULT_BROWSER_ARTIFACT_RETENTION = 10
V22_BROWSER_TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def serve_mockup_over_http() -> Iterator[str]:
    """Expose the authored source to Chromium without a ``file://`` escape."""
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(_QuietStaticHandler, directory=str(DEFAULT_SOURCE.parent)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{DEFAULT_SOURCE.name}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _prune_default_artifact_runs(root: Path, *, keep: int) -> None:
    """Best-effort cleanup that never removes the report being written."""
    runs = sorted(
        (path for path in root.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    stale_runs = runs[:-keep] if keep else runs
    for run in stale_runs:
        shutil.rmtree(run, ignore_errors=True)


def _artifact_dir() -> Path:
    configured = os.environ.get("V22_BROWSER_REPORT_DIR")
    root = Path(configured) if configured else Path.home() / ".pytest-v22-browser-artifacts"
    root.mkdir(parents=True, exist_ok=True)
    if not configured:
        _prune_default_artifact_runs(root, keep=DEFAULT_BROWSER_ARTIFACT_RETENTION - 1)
    path = root / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path.mkdir(exist_ok=True)
    return path


def test_default_browser_artifact_retention_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default report root remains inspectable without growing forever."""
    monkeypatch.delenv("V22_BROWSER_REPORT_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    root = tmp_path / ".pytest-v22-browser-artifacts"
    for index in range(10):
        (root / f"old-{index}").mkdir(parents=True)

    artifact_dir = _artifact_dir()

    assert artifact_dir.is_dir()
    assert len([path for path in root.iterdir() if path.is_dir()]) <= DEFAULT_BROWSER_ARTIFACT_RETENTION


def test_configured_browser_artifact_dir_is_not_pruned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit report directory retains every artifact for its owner."""
    root = tmp_path / "operator-reports"
    for index in range(DEFAULT_BROWSER_ARTIFACT_RETENTION):
        (root / f"old-{index}").mkdir(parents=True)
    monkeypatch.setenv("V22_BROWSER_REPORT_DIR", str(root))

    artifact_dir = _artifact_dir()

    assert artifact_dir.is_dir()
    assert len([path for path in root.iterdir() if path.is_dir()]) == DEFAULT_BROWSER_ARTIFACT_RETENTION + 1


def _freeze_clock(context: BrowserContext) -> None:
    """Make the initial timezone widget value deterministic and non-placeholder."""
    context.add_init_script(
        """
        (() => {
          const NativeDate = Date;
          const fixed = Date.UTC(2026, 7, 10, 12, 34, 0);
          class FixedDate extends NativeDate {
            constructor(...args) { super(...(args.length ? args : [fixed])); }
            static now() { return fixed; }
          }
          FixedDate.parse = NativeDate.parse;
          FixedDate.UTC = NativeDate.UTC;
          window.Date = FixedDate;
        })();
        """
    )


def _cookie_payload(client: Client, base_url: str) -> list[dict[str, str]]:
    return [
        {"name": name, "value": morsel.value, "url": base_url}
        for name, morsel in client.cookies.items()
    ]


def _computed_styles(page: Page) -> dict[str, dict[str, str]]:
    return page.evaluate(
        """({selectors, properties}) => Object.fromEntries(
          Object.entries(selectors).map(([region, selector]) => {
            const element = document.querySelector(selector);
            if (!element) return [region, null];
            const style = getComputedStyle(element);
            return [region, Object.fromEntries(properties.map((name) => [name, style[name]]))];
          })
        )""",
        {"selectors": REGION_SELECTORS, "properties": STYLE_PROPERTIES},
    )


def _relative_geometry(page: Page, root_selector: str) -> dict[str, dict[str, float]]:
    return page.evaluate(
        """({rootSelector, selectors}) => {
          const root = document.querySelector(rootSelector)?.getBoundingClientRect();
          if (!root || !root.width || !root.height) return {__root_missing__: true};
          const normal = (value) => Math.round(value * 10000) / 10000;
          const entry = (selector) => {
            const rect = document.querySelector(selector)?.getBoundingClientRect();
            if (!rect) return null;
            return {
              x: normal((rect.left - root.left) / root.width),
              y: normal((rect.top - root.top) / root.height),
              width: normal(rect.width / root.width),
              height: normal(rect.height / root.height),
            };
          };
          return Object.fromEntries(Object.entries(selectors).map(([region, selector]) => [region, entry(selector)]));
        }""",
        {"rootSelector": root_selector, "selectors": REGION_SELECTORS},
    )


def _pixel_report(page: Page, actual: bytes, reference: bytes) -> dict[str, float | int]:
    """Compare PNGs in Chromium, avoiding a Pillow/ImageMagick test dependency."""
    return page.evaluate(
        """async ({actual, reference, delta}) => {
          const decode = (source) => new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = reject;
            image.src = source;
          });
          const [left, right] = await Promise.all([decode(actual), decode(reference)]);
          if (left.width !== right.width || left.height !== right.height) {
            return {width: left.width, height: left.height, reference_width: right.width,
                    reference_height: right.height, changed_fraction: 1, mean_channel_delta: 255};
          }
          const canvas = document.createElement('canvas');
          canvas.width = left.width;
          canvas.height = left.height;
          const context = canvas.getContext('2d', {willReadFrequently: true});
          context.drawImage(left, 0, 0);
          const leftPixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
          context.clearRect(0, 0, canvas.width, canvas.height);
          context.drawImage(right, 0, 0);
          const rightPixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
          let changed = 0;
          let sum = 0;
          for (let index = 0; index < leftPixels.length; index += 4) {
            const distance = Math.max(
              Math.abs(leftPixels[index] - rightPixels[index]),
              Math.abs(leftPixels[index + 1] - rightPixels[index + 1]),
              Math.abs(leftPixels[index + 2] - rightPixels[index + 2])
            );
            sum += distance;
            if (distance > delta) changed += 1;
          }
          const pixels = leftPixels.length / 4;
          return {width: canvas.width, height: canvas.height, reference_width: canvas.width,
                  reference_height: canvas.height, changed_fraction: changed / pixels,
                  mean_channel_delta: sum / pixels};
        }""",
        {
            "actual": "data:image/png;base64," + base64.b64encode(actual).decode("ascii"),
            "reference": "data:image/png;base64," + base64.b64encode(reference).decode("ascii"),
            "delta": PIXEL_DELTA,
        },
    )


def _assert_parser_regions(page: Page, spec: MockupSpec, *, locale: str, viewport: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    rendered = parse_rendered_html(page.content())
    for region, selector in REGION_SELECTORS.items():
        count = page.locator(selector).count()
        counts[region] = count
        assert count == 1, (
            "v22 browser DOM mismatch: "
            f"region={region!r}; selector={selector!r}; count={count}; "
            f"locale={locale!r}; viewport={viewport!r}; oracle_source={str(spec.source)!r}"
        )
        # Reuse the oracle-aware parser diagnostic rather than treating a
        # browser selector alone as proof that the authored node is valid.
        select_one(
            rendered,
            selector=selector,
            locale=locale,
            viewport=viewport,
            oracle_source=str(spec.source),
        )
    return counts


@override_settings(STORAGES=V22_BROWSER_TEST_STORAGES)
class HomeV22BrowserTests(StaticLiveServerTestCase):
    """Root-route, real-PostgreSQL browser proof for v22's visible shell."""

    def setUp(self) -> None:
        """Rebuild browser-visible fixtures after TransactionTestCase flushes."""
        super().setUp()
        self.fixture = fixture_from_oracle()
        seed_real_home_orm(self.fixture)
        _clear_home_pulse_cache()
        from core.models import Post, PostEnrichmentState

        pending_post = Post.objects.order_by("-created_at").first()
        self.assertIsNotNone(pending_post)
        PostEnrichmentState.objects.create(post=pending_post)
        from django.contrib.auth import get_user_model

        self.browser_user = get_user_model().objects.create_user(
            username="v22-browser-verifier",
            email=V22_TEST_USER_EMAIL,
            password="v22-browser-test-only-password",
        )

    def _authenticated_cookies(self, locale: str) -> list[dict[str, str]]:
        client = Client(HTTP_HOST="localhost")
        client.force_login(self.browser_user)
        response = client.post(f"/locale/{locale}/", HTTP_REFERER="/")
        self.assertEqual(response.status_code, 302)
        return _cookie_payload(client, self.live_server_url)

    def _anonymous_cookies(self, locale: str) -> list[dict[str, str]]:
        client = Client(HTTP_HOST="localhost")
        response = client.post(f"/locale/{locale}/", HTTP_REFERER="/")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", client.session)
        self.assertEqual(client.get("/internal/").status_code, 302)
        return _cookie_payload(client, self.live_server_url)

    def _context_with_cookies(
        self, browser, cookies: list[dict[str, str]], viewport: dict[str, int]
    ) -> BrowserContext:
        context = browser.new_context(viewport=viewport, timezone_id="Asia/Tokyo")
        _freeze_clock(context)
        context.add_cookies(cookies)
        return context

    def test_zh_hans_renders_chinese_chrome_in_browser(self) -> None:
        """The Django ``zh_hans`` alias keeps v22 chrome Chinese after JS initializes."""
        cookies = self._anonymous_cookies("zh_hans")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._context_with_cookies(browser, cookies, VIEWPORTS["desktop"])
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.wait_for_function("() => window.__pwTz && window.pwApplyChrome")
                    self.assertEqual(page.locator("body").get_attribute("data-pw-locale"), "zh_hans")
                    self.assertEqual(page.locator("nav.locale-toggle").get_attribute("aria-label"), "显示语言")
                    self.assertEqual(page.locator("[data-pw-locale-btn='zh_cn']").inner_text(), "中文")
                    self.assertEqual(page.locator("[data-pw-locale-btn='zh_cn']").get_attribute("class"), "is-active")
                    self.assertEqual(page.locator("[data-tz-zone]").inner_text(), "本地")
                finally:
                    context.close()
            finally:
                browser.close()

    def test_mobile_click_activation_opens_brand_dropdown(self) -> None:
        """A semantic mobile click opens a visible, durable Brands menu."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    **playwright.devices["iPhone 13"],
                    timezone_id="Asia/Tokyo",
                )
                _freeze_clock(context)
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                page.on(
                    "console",
                    lambda message: console_errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    page.wait_for_function("() => window.pwFilter")
                    pill = page.locator('[data-group="brands"]')
                    dropdown = pill.locator(".filter-dropdown")

                    pill.dispatch_event("click")

                    self.assertEqual(pill.get_attribute("aria-expanded"), "true")
                    self.assertTrue(dropdown.is_visible())
                    box = dropdown.bounding_box()
                    self.assertIsNotNone(box)
                    self.assertGreater(box["width"], 0)
                    self.assertGreater(box["height"], 0)
                    self.assertGreaterEqual(box["x"], 0)
                    self.assertLessEqual(box["x"] + box["width"], VIEWPORTS["mobile"]["width"] + 1)

                    pill.locator('[data-lens="closed"]').click()
                    self.assertEqual(pill.get_attribute("aria-expanded"), "true")
                    self.assertTrue(dropdown.is_visible())

                    page.locator("h1.app-name").dispatch_event("pointerdown")
                    self.assertEqual(pill.get_attribute("aria-expanded"), "false")
                    self.assertFalse(dropdown.is_visible())
                    self.assertEqual(console_errors, [])
                    self.assertEqual(page_errors, [])
                finally:
                    context.close()
            finally:
                browser.close()

    def test_mobile_locale_toggle_stays_inside_title_row(self) -> None:
        """Locale controls stay within their containing title row on mobile."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale in ("en", "zh_hans"):
                    with self.subTest(locale=locale):
                        context = browser.new_context(
                            **playwright.devices["iPhone 13"],
                            timezone_id="Asia/Tokyo",
                        )
                        _freeze_clock(context)
                        page = context.new_page()
                        try:
                            page.goto(
                                f"{self.live_server_url}/?locale={locale}",
                                wait_until="networkidle",
                            )
                            boxes = page.evaluate(
                                """() => {
                                  const row = document.querySelector('.topbar-title-row').getBoundingClientRect();
                                  const appName = document.querySelector('h1.app-name').getBoundingClientRect();
                                  const locale = document.querySelector('.locale-toggle').getBoundingClientRect();
                                  return {
                                    row: {left: row.left, right: row.right, width: row.width},
                                    appName: {left: appName.left, right: appName.right, width: appName.width},
                                    locale: {left: locale.left, right: locale.right, width: locale.width},
                                    viewport: innerWidth,
                                  };
                                }"""
                            )
                            self.assertGreater(boxes["appName"]["width"], 0)
                            self.assertGreaterEqual(
                                boxes["appName"]["left"],
                                boxes["row"]["left"] - 0.5,
                            )
                            self.assertGreater(boxes["locale"]["width"], 0)
                            self.assertGreaterEqual(
                                boxes["locale"]["left"],
                                boxes["row"]["left"] - 0.5,
                            )
                            self.assertLessEqual(
                                boxes["locale"]["right"],
                                boxes["row"]["right"] + 0.5,
                            )
                            self.assertLessEqual(
                                boxes["locale"]["right"],
                                boxes["viewport"] + 0.5,
                            )
                        finally:
                            context.close()
            finally:
                browser.close()

    def test_anonymous_chart_is_live_canvas_and_window_refetch_is_atomic(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(viewport=VIEWPORTS["desktop"], timezone_id="Asia/Tokyo")
                _freeze_clock(context)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.wait_for_function(
                        "() => { const c = document.querySelector('canvas.home-chart'); return c && window.Chart?.getChart(c); }"
                    )
                    self.assertEqual(page.locator("svg.home-chart").count(), 0)
                    canvas = page.locator("canvas.home-chart")
                    self.assertEqual(canvas.count(), 1)
                    box = canvas.bounding_box()
                    self.assertIsNotNone(box)
                    self.assertGreater(box["width"], 0)
                    self.assertGreater(box["height"], 0)
                    runtime = page.evaluate(
                        """() => {
                          const canvas = document.querySelector('canvas.home-chart');
                          const chart = Chart.getChart(canvas);
                          const context = canvas.getContext('2d', {willReadFrequently: true});
                          const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
                          let painted = 0;
                          for (let index = 3; index < pixels.length; index += 4) painted += pixels[index] > 0 ? 1 : 0;
                          return {
                            datasets: chart.data.datasets.filter((dataset) => dataset._isTotalLine).length,
                            payloadSeries: Object.keys(JSON.parse(canvas.dataset.home).series).length,
                            painted,
                            hidden: chart.data.datasets.map((dataset) => Boolean(dataset.hidden)),
                          };
                        }"""
                    )
                    self.assertEqual(runtime["datasets"], runtime["payloadSeries"])
                    self.assertGreater(runtime["painted"], 0)
                    initial_legend = page.locator("[data-pw-chart-legend]")
                    self.assertEqual(initial_legend.count(), 1)
                    self.assertEqual(initial_legend.locator("span").count(), runtime["payloadSeries"])

                    canvas.hover(position={"x": box["width"] / 2, "y": box["height"] / 2})
                    after_hover = page.evaluate(
                        "() => Chart.getChart(document.querySelector('canvas.home-chart')).data.datasets.map((dataset) => Boolean(dataset.hidden))"
                    )
                    self.assertEqual(after_hover, runtime["hidden"], "hover must not hide a series")

                    with page.expect_response(lambda response: "/chart.html?" in response.url) as response_info:
                        page.locator("[data-pw-window-btn='7']").click()
                    response = response_info.value
                    self.assertEqual(response.status, 200)
                    self.assertNotIn("renderer=", response.url)
                    page.wait_for_function(
                        "() => JSON.parse(document.querySelector('canvas.home-chart').dataset.home).window_days === 7 && document.querySelector('[data-pw-pulse]').dataset.pwWindow === '7'"
                    )
                    projection = page.evaluate(
                        """() => ({
                          chart: JSON.parse(document.querySelector('canvas.home-chart').dataset.home),
                          pulseWindow: Number(document.querySelector('[data-pw-pulse]').dataset.pwWindow),
                          pulseComputedAt: document.querySelector('[data-pw-pulse]').dataset.pwComputedAt,
                          pulseCount: document.querySelectorAll('[data-pw-pulse-entry]').length,
                        })"""
                    )
                    self.assertEqual(projection["chart"]["window_days"], projection["pulseWindow"])
                    self.assertEqual(projection["chart"]["computed_at"], projection["pulseComputedAt"])
                    self.assertLessEqual(projection["pulseCount"], 8)
                    refreshed_legend = page.locator("[data-pw-chart-legend]")
                    self.assertEqual(
                        refreshed_legend.count(),
                        1,
                        "the payload-backed V22 legend must survive an atomic chart refresh",
                    )
                    self.assertEqual(
                        refreshed_legend.locator("span").count(),
                        len(projection["chart"]["series"]),
                    )
                finally:
                    context.close()
            finally:
                browser.close()

    def test_anonymous_filters_window_and_pulse_share_one_request_state(self) -> None:
        """One V22 action emits one immutable state to feed and chart."""

        def request_state(url: str) -> tuple[dict[str, object], int]:
            query = parse_qs(urlparse(url).query)
            self.assertEqual(len(query.get("filters", [])), 1, f"missing filters query: {url}")
            self.assertEqual(len(query.get("window", [])), 1, f"missing explicit window query: {url}")
            return json.loads(query["filters"][0]), int(query["window"][0])

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(viewport=VIEWPORTS["desktop"], timezone_id="Asia/Tokyo")
                _freeze_clock(context)
                page = context.new_page()
                requests: list[str] = []
                page.on(
                    "request",
                    lambda request: requests.append(request.url)
                    if "/feed/?" in request.url or "/chart.html?" in request.url
                    else None,
                )

                def act(action) -> tuple[object, object]:
                    before_feed = len([url for url in requests if "/feed/?" in url])
                    before_chart = len([url for url in requests if "/chart.html?" in url])
                    with page.expect_response(lambda response: "/feed/?" in response.url) as feed_info:
                        with page.expect_response(lambda response: "/chart.html?" in response.url) as chart_info:
                            action()
                    feed_response = feed_info.value
                    chart_response = chart_info.value
                    self.assertEqual(feed_response.status, 200)
                    self.assertEqual(chart_response.status, 200)
                    page.wait_for_timeout(75)
                    self.assertEqual(
                        len([url for url in requests if "/feed/?" in url]) - before_feed,
                        1,
                        "one store event must start one feed request",
                    )
                    self.assertEqual(
                        len([url for url in requests if "/chart.html?" in url]) - before_chart,
                        1,
                        "one store event must start one chart request",
                    )
                    feed_state = request_state(feed_response.url)
                    chart_state = request_state(chart_response.url)
                    self.assertEqual(feed_state, chart_state)
                    return feed_response, chart_response

                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    page.wait_for_function(
                        "() => window.pwFilter && document.querySelector('[data-pw-pulse-entry]')"
                    )

                    for selector in (
                        '[data-tier-grid="open"] input[data-pw-filter-group="brands"]',
                        '[data-tier-grid="closed"] input[data-pw-filter-group="brands"]',
                        '[data-group="discourse"] input[data-pw-filter-group="discourse"]',
                        '[data-group="role"] input[data-pw-filter-group="role"]',
                        '[data-group="lang"] input[data-pw-filter-group="lang"]',
                        '[data-group="sentiment"] input[data-pw-filter-group="sentiment"]',
                        '[data-tier-grid="us"] input[data-pw-filter-group="us_nationalism"]',
                        '[data-tier-grid="cn"] input[data-pw-filter-group="cn_nationalism"]',
                        '[data-group="unsanctioned"] input[data-pw-filter-group="unsanctioned"]',
                    ):
                        self.assertGreater(page.locator(selector).count(), 0, f"selector matched zero controls: {selector}")

                    unsanctioned_pill = page.locator('[data-group="unsanctioned"]')
                    unsanctioned_pill.press("Enter")
                    unsanctioned = page.locator(
                        '[data-group="unsanctioned"] input[data-pw-filter-group="unsanctioned"]'
                    )
                    self.assertFalse(unsanctioned.is_checked())
                    feed_response, chart_response = act(unsanctioned.check)
                    filters, _ = request_state(feed_response.url)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().unsanctioned"), "only")
                    self.assertEqual(filters["unsanctioned"], "only")
                    chart_filters, _ = request_state(chart_response.url)
                    self.assertEqual(chart_filters["unsanctioned"], "only")

                    feed_response, chart_response = act(unsanctioned.uncheck)
                    filters, _ = request_state(feed_response.url)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().unsanctioned"), "off")
                    self.assertEqual(filters["unsanctioned"], "off")
                    chart_filters, _ = request_state(chart_response.url)
                    self.assertEqual(chart_filters["unsanctioned"], "off")

                    brands_pill = page.locator('[data-group="brands"]')
                    brands_pill.press("Enter")
                    dropdown = brands_pill.locator(".filter-dropdown")
                    self.assertTrue(dropdown.is_visible())
                    box = dropdown.bounding_box()
                    self.assertIsNotNone(box)
                    self.assertGreater(box["width"], 0)
                    self.assertGreater(box["height"], 0)
                    self.assertGreaterEqual(box["x"], 0)
                    self.assertLessEqual(box["x"] + box["width"], VIEWPORTS["desktop"]["width"] + 1)

                    open_grid = brands_pill.locator('[data-tier-grid="open"]')
                    act(brands_pill.locator('[data-dd-action="clear"][data-dd-scope="visible"]').click)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), [])
                    self.assertEqual(open_grid.locator('input:checked').count(), 0)
                    act(brands_pill.locator('[data-dd-action="all"][data-dd-scope="visible"]').click)
                    open_selection = page.evaluate("() => window.pwFilter.get().brands")
                    self.assertIsInstance(open_selection, list)
                    self.assertIn("qwen", open_selection)
                    self.assertNotIn("anthropic", open_selection)
                    brands_pill.press("Escape")

                    nationalism_pill = page.locator('[data-group="nationalism"]')
                    nationalism_pill.press("Enter")
                    nationalism_pill.locator('[data-lens="cn"]').click()
                    act(nationalism_pill.locator('[data-dd-action="clear"][data-dd-scope="visible"]').click)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().cn_nationalism"), [])
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().us_nationalism"), "__all__")
                    act(nationalism_pill.locator('[data-dd-action="all"][data-dd-scope="visible"]').click)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().cn_nationalism"), "__all__")
                    nationalism_pill.press("Escape")

                    sentiment_pill = page.locator('[data-group="sentiment"]')
                    sentiment_pill.press("Enter")
                    positive = sentiment_pill.locator('input[value="positive"]')
                    self.assertTrue(positive.is_checked())
                    feed_response, _ = act(positive.uncheck)
                    filters, window = request_state(feed_response.url)
                    self.assertEqual(window, 1)
                    self.assertNotEqual(filters.get("sentiment"), "__all__")
                    self.assertNotIn("positive", filters["sentiment"])
                    feed_payload = feed_response.json()
                    page.wait_for_function(
                        "() => JSON.parse(document.querySelector('canvas.home-chart').dataset.home).applied_filters.sentiment"
                    )
                    chart_payload = page.evaluate(
                        "() => JSON.parse(document.querySelector('canvas.home-chart').dataset.home)"
                    )
                    self.assertEqual(
                        sum(chart_payload["totals"].values()),
                        len(feed_payload["rows"]),
                        "fixture feed IDs and chart totals must change together",
                    )

                    pulse = page.locator("[data-pw-pulse-entry]").first
                    self.assertEqual(pulse.evaluate("element => element.parentElement.tagName"), "LI")
                    self.assertEqual(pulse.get_attribute("aria-pressed"), "false")
                    self.assertRegex(pulse.get_attribute("aria-label") or "", r".+, (up|down|flat) \d+ percent|.+, NEW")
                    nickname = pulse.get_attribute("data-pw-pulse-entry")

                    act(pulse.click)
                    page.wait_for_function(
                        "nickname => JSON.stringify(window.pwFilter.get().brands) === JSON.stringify([nickname])",
                        arg=nickname,
                    )
                    self.assertEqual(page.locator(f'[data-pw-pulse-entry="{nickname}"]').get_attribute("aria-pressed"), "true")
                    checked_brands = page.locator('[data-pw-filter-group="brands"]:checked')
                    self.assertEqual(checked_brands.count(), 1)
                    self.assertEqual(checked_brands.first.get_attribute("value"), nickname)

                    act(lambda: page.locator(f'[data-pw-pulse-entry="{nickname}"]').press("Enter"))
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), "__all__")
                    self.assertEqual(page.locator(f'[data-pw-pulse-entry="{nickname}"]').get_attribute("aria-pressed"), "false")
                    self.assertEqual(
                        page.locator('[data-pw-filter-group="brands"]:checked').count(),
                        page.locator('[data-pw-filter-group="brands"]').count(),
                    )

                    act(lambda: page.locator(f'[data-pw-pulse-entry="{nickname}"]').press("Space"))
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), [nickname])
                    act(lambda: page.locator(f'[data-pw-pulse-entry="{nickname}"]').click())
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), "__all__")

                    feed_response, _ = act(page.locator("[data-pw-window-btn='7']").click)
                    filters, window = request_state(feed_response.url)
                    self.assertEqual(filters["window"], 7)
                    self.assertEqual(window, 7)
                    page.wait_for_function(
                        "() => JSON.parse(document.querySelector('canvas.home-chart').dataset.home).window_days === 7"
                    )
                finally:
                    context.close()
            finally:
                browser.close()

    def test_internal_window_button_retains_legacy_post_and_reload(self) -> None:
        cookies = self._authenticated_cookies("en")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._context_with_cookies(browser, cookies, VIEWPORTS["desktop"])
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/internal/", wait_until="networkidle")
                    self.assertEqual(page.locator("#control-panel").count(), 1)
                    with page.expect_navigation(wait_until="networkidle"):
                        page.locator("[data-pw-window-btn='7']").click()
                    self.assertEqual(page.locator("body").get_attribute("data-pw-window"), "7")
                    self.assertEqual(page.locator("#control-panel").count(), 1)
                finally:
                    context.close()
            finally:
                browser.close()

    def test_fixture_root_route_matches_mockup_in_browser(self) -> None:
        spec = load_spec()
        artifacts = _artifact_dir()
        reports: list[dict[str, object]] = []
        # Django's synchronous test client cannot run inside Playwright's sync
        # bridge event loop, so mint anonymous locale/CSRF cookies first. The
        # helper proves the session has no authenticated user and /internal/
        # still redirects before this visual flow exercises the public root.
        cookies_by_locale = {locale: self._anonymous_cookies(locale) for locale in LOCALES}

        with serve_mockup_over_http() as mockup_url, sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for viewport_name, viewport in VIEWPORTS.items():
                    for locale in LOCALES:
                        context = self._context_with_cookies(browser, cookies_by_locale[locale], viewport)
                        page = context.new_page()
                        reference = context.new_page()
                        console_errors: list[str] = []
                        page_errors: list[str] = []
                        local_asset_responses: dict[str, int] = {}
                        page.on(
                            "console",
                            lambda message: console_errors.append(message.text)
                            if message.type == "error"
                            else None,
                        )
                        page.on("pageerror", lambda error: page_errors.append(str(error)))
                        page.on(
                            "response",
                            lambda response: local_asset_responses.__setitem__(response.url, response.status)
                            if urlparse(response.url).path.startswith("/static/")
                            else None,
                        )
                        try:
                            page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                            reference.goto(mockup_url, wait_until="networkidle")
                            reference.evaluate(
                                """({locale, chrome}) => {
                                  const dict = chrome[locale];
                                  const useZh = locale === 'zh_cn';
                                  document.body.setAttribute('data-pw-locale', locale);
                                  document.querySelectorAll('[data-i18n]').forEach((element) => {
                                    const value = dict[element.getAttribute('data-i18n')];
                                    if (value != null) element.textContent = value;
                                  });
                                  const localeNav = document.querySelector('.locale-toggle');
                                  if (localeNav) {
                                    localeNav.setAttribute('aria-label', dict.locale_aria);
                                    localeNav.querySelectorAll('[data-pw-locale-btn]').forEach((button) => {
                                      button.textContent = button.getAttribute(useZh ? 'data-label-zh' : 'data-label-en') || button.textContent;
                                    });
                                  }
                                  document.querySelectorAll('.window-toggle:not(.locale-toggle)').forEach((nav) => {
                                    nav.setAttribute('aria-label', dict.window_aria);
                                    nav.querySelectorAll('button').forEach((button) => {
                                      button.textContent = button.getAttribute(useZh ? 'data-label-zh' : 'data-label-en') || button.textContent;
                                    });
                                  });
                                  const timezone = document.querySelector('[data-tz-widget]');
                                  if (timezone) timezone.setAttribute('title', dict.tz_title);
                                }""",
                                {"locale": locale, "chrome": spec.chrome},
                            )
                            page.wait_for_function(
                                """() => window.__pwTz && document.querySelector('[data-tz-time]')?.textContent !== '00:00'"""
                            )

                            dom_counts = _assert_parser_regions(page, spec, locale=locale, viewport=viewport_name)
                            actual_styles = _computed_styles(page)
                            reference_styles = _computed_styles(reference)
                            self.assertEqual(
                                actual_styles["topbar"]["display"], reference_styles["topbar"]["display"],
                                f"v22 computed-style mismatch: region='topbar'; property='display'; locale={locale!r}; viewport={viewport_name!r}; oracle_source={str(spec.source)!r}",
                            )
                            self.assertEqual(
                                actual_styles["timezone"]["display"], reference_styles["timezone"]["display"],
                                f"v22 computed-style mismatch: region='timezone'; property='display'; locale={locale!r}; viewport={viewport_name!r}; oracle_source={str(spec.source)!r}",
                            )

                            actual_geometry = _relative_geometry(page, ".app-shell")
                            reference_geometry = _relative_geometry(reference, ".phone")
                            self.assertFalse(actual_geometry.get("__root_missing__"), "Django app-shell landmark missing")
                            self.assertFalse(reference_geometry.get("__root_missing__"), "Mockup phone landmark missing")
                            # These relationships survive changing fixture copy and catch
                            # shell layout regressions more reliably than absolute pixels.
                            self.assertAlmostEqual(actual_geometry["topbar"]["x"], actual_geometry["filters"]["x"], delta=0.02)
                            self.assertAlmostEqual(actual_geometry["topbar"]["width"], actual_geometry["filters"]["width"], delta=0.02)
                            if viewport_name == "desktop":
                                self.assertLess(actual_geometry["chart"]["x"], actual_geometry["feed"]["x"])
                            else:
                                self.assertLess(actual_geometry["chart"]["y"], actual_geometry["feed"]["y"])

                            tz = page.locator("[data-tz-widget]")
                            feed_stamp = page.locator(".feed-row[data-created-at-iso] .ts-abs").first
                            pending_row = page.locator(
                                ".feed-row[data-enrichment-status='pending']"
                            ).first
                            pending_signal = pending_row.locator(
                                ".enrichment-status-pending[role='status']"
                            )
                            self.assertEqual(pending_signal.count(), 1)
                            self.assertTrue(pending_signal.is_visible())
                            self.assertNotEqual((pending_signal.inner_text() or "").strip(), "")
                            self.assertEqual(
                                page.locator(
                                    ".feed-row[data-enrichment-status='succeeded'] "
                                    ".enrichment-status"
                                ).count(),
                                0,
                            )
                            initial_feed_stamp = feed_stamp.text_content()
                            initial_time = tz.locator("[data-tz-time]").text_content()
                            self.assertRegex(initial_time or "", r"^\d{2}:\d{2}$")
                            self.assertNotEqual(initial_time, "00:00", "timezone runtime left its authored placeholder unchanged")
                            tz.click()
                            page.wait_for_function("() => window.__pwTz?.mode === 'ca'")
                            self.assertEqual(tz.get_attribute("data-tz-active"), "ca")
                            self.assertIn("CA", tz.inner_text())
                            self.assertNotEqual(feed_stamp.text_content(), initial_feed_stamp)

                            local_assets = page.evaluate(
                                """() => [...document.querySelectorAll('link[href], script[src]')]
                                  .map((node) => new URL(node.href || node.src, location.href).href)
                                  .filter((url) => new URL(url).origin === location.origin)"""
                            )
                            self.assertGreater(len(local_assets), 0, "anonymous root referenced zero local assets")
                            for asset_url in local_assets:
                                self.assertIn(asset_url, local_asset_responses, f"local asset emitted no response: {asset_url}")
                                self.assertLess(
                                    local_asset_responses[asset_url],
                                    400,
                                    f"local asset failed: url={asset_url}; status={local_asset_responses[asset_url]}",
                                )
                            self.assertEqual(page_errors, [], f"candidate page errors: {page_errors}")
                            self.assertEqual(console_errors, [], f"candidate console errors: {console_errors}")

                            actual_png = page.screenshot()
                            reference_png = reference.screenshot()
                            stem = f"{viewport_name}-{locale}"
                            (artifacts / f"{stem}-django.png").write_bytes(actual_png)
                            (artifacts / f"{stem}-mockup.png").write_bytes(reference_png)
                            pixels = _pixel_report(page, actual_png, reference_png)
                            report = {
                                "locale": locale,
                                "viewport": viewport_name,
                                "django_url": self.live_server_url,
                                "mockup_url": mockup_url,
                                "dom_counts": dom_counts,
                                "computed_styles": {"django": actual_styles, "mockup": reference_styles},
                                "geometry": {"django": actual_geometry, "mockup": reference_geometry},
                                "timezone": {"initial": initial_time, "after_toggle": tz.inner_text()},
                                "screenshot": pixels,
                            }
                            (artifacts / f"{stem}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                            reports.append(report)
                            self.assertLessEqual(
                                float(pixels["changed_fraction"]),
                                MAX_CHANGED_PIXEL_FRACTION,
                                f"v22 screenshot threshold exceeded; report={artifacts / f'{stem}.json'}; "
                                f"changed_fraction={pixels['changed_fraction']}; threshold={MAX_CHANGED_PIXEL_FRACTION}",
                            )
                        finally:
                            context.close()
            finally:
                browser.close()

        summary = artifacts / "summary.json"
        summary.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(len(reports), len(VIEWPORTS) * len(LOCALES), f"missing browser reports; artifacts={artifacts}")


@override_settings(STORAGES=V22_BROWSER_TEST_STORAGES)
class HomeV22MetadataParityBrowserTests(StaticLiveServerTestCase):
    """Anonymous, real-ORM proof for metadata received after feed hydration."""

    def setUp(self) -> None:
        super().setUp()
        self.fixture = seed_v22_metadata_regression_orm()
        _clear_home_pulse_cache()

    def _anonymous_context(self, browser: object) -> BrowserContext:
        context = browser.new_context(viewport=VIEWPORTS["desktop"], timezone_id="Asia/Tokyo")
        _freeze_clock(context)
        return context

    def _feed_payload(self, **query: object) -> dict[str, object]:
        response = Client(HTTP_HOST="localhost").get("/feed/?" + urlencode(query))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _assert_row_contract(self, row: dict[str, object], *, tweet_id: str, tint: str) -> None:
        self.assertEqual(row["tweet_id"], tweet_id)
        self.assertEqual(row["tint_class"], tint)
        for key in (
            "text",
            "text_original",
            "text_translated",
            "text_en",
            "text_zh_cn",
            "account",
            "engagement_pretty",
            "avatar_initials",
            "avatar_color",
            "meta_text",
            "ts_abs_text",
            "classifications",
            "sentiment_keys",
            "post_type_keys",
            "nat_cn",
            "nat_us",
            "unsanctioned",
        ):
            self.assertIn(key, row)
        self.assertEqual(row["account"]["handle"], "v22metadata000")
        self.assertEqual(row["sentiment_keys"], ["positive", "mixed"])
        self.assertEqual(row["post_type_keys"], ["buzz_releases", "hands_on_usage"])
        self.assertEqual(row["nat_cn"], "pro")
        self.assertEqual(row["nat_us"], "mild_pro")
        self.assertIn("genuine_hype", str(row["classifications"]))
        self.assertTrue(row["engagement_pretty"]["followers"])

    def _assert_visible_metadata(self, page: Page, tweet_id: str, tint: str) -> None:
        row = page.locator(f".feed-row[data-tweet-id='{tweet_id}']")
        self.assertEqual(row.count(), 1, f"missing rendered row {tweet_id}")
        self.assertEqual(row.get_attribute("data-tint"), tint)
        shell = row.locator(".feed-row-shell")
        self.assertTrue(shell.evaluate("element => element.classList.contains('" + tint + "')"))
        for selector in ("[data-sig-sentiment]", "[data-sig-post-type]", "[data-sig-nat]"):
            marker = row.locator(selector)
            self.assertTrue(marker.is_visible(), f"marker is hidden: {selector}")
            box = marker.bounding_box()
            self.assertIsNotNone(box, f"marker has no geometry: {selector}")
            self.assertGreater(box["width"], 0, f"marker has zero width: {selector}")
            self.assertGreater(box["height"], 0, f"marker has zero height: {selector}")
            self.assertTrue((marker.text_content() or "").strip(), f"marker is blank: {selector}")

    def test_exact_ae11_pulse_projection_is_visible_and_accessible(self) -> None:
        """The deterministic integrated fixture reaches the browser unchanged."""
        expected = self.fixture["pulse_expectations"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    page.wait_for_function(
                        "nickname => Boolean(document.querySelector(`[data-pw-pulse-entry='${nickname}']`))",
                        arg="pulse_up",
                    )
                    projection = page.evaluate(
                        """() => {
                          const bar = document.querySelector('[data-pw-pulse]');
                          const rows = [...bar.querySelectorAll(':scope > li')];
                          const entries = [...bar.querySelectorAll('[data-pw-pulse-entry]')];
                          const details = Object.fromEntries(entries.map((button) => {
                            const delta = button.querySelector('.delta');
                            const rawGlyph = getComputedStyle(delta, '::before').content;
                            const glyph = rawGlyph === 'none'
                              ? ''
                              : rawGlyph.replace(/^['\"]|['\"]$/g, '').trim();
                            const rect = button.getBoundingClientRect();
                            return [button.dataset.pwPulseEntry, {
                              text: delta.textContent.trim(),
                              glyph,
                              aria: button.getAttribute('aria-label'),
                              pressed: button.getAttribute('aria-pressed'),
                              width: rect.width,
                              height: rect.height,
                            }];
                          }));
                          return {
                            order: entries.map((button) => button.dataset.pwPulseEntry),
                            details,
                            listItems: rows.length,
                            buttons: bar.querySelectorAll('button').length,
                            window: bar.dataset.pwWindow,
                            computedAt: bar.dataset.pwComputedAt,
                          };
                        }"""
                    )

                    self.assertEqual(projection["order"], expected["order"])
                    self.assertEqual(projection["listItems"], len(expected["order"]))
                    self.assertEqual(projection["buttons"], len(expected["order"]))
                    self.assertEqual(projection["window"], "1")
                    self.assertRegex(projection["computedAt"], r"^\d{4}-\d{2}-\d{2}T")
                    for nickname, values in expected["details"].items():
                        with self.subTest(nickname=nickname):
                            actual = projection["details"][nickname]
                            self.assertEqual(actual["text"], values["text"])
                            self.assertEqual(actual["glyph"], values["glyph"])
                            self.assertEqual(actual["aria"], values["aria"])
                            self.assertEqual(actual["pressed"], "false")
                            self.assertGreater(actual["width"], 0)
                            self.assertGreater(actual["height"], 0)
                finally:
                    context.close()
            finally:
                browser.close()

    def test_anonymous_feed_fixture_has_a_page_two_target(self) -> None:
        anonymous = Client(HTTP_HOST="localhost")
        root = anonymous.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertIn(self.fixture["replacement_id"].encode(), root.content)

        payload = self._feed_payload(limit=50)
        self.assertEqual(len(payload["rows"]), 50)
        self.assertTrue(payload["next_cursor"])
        first = payload["rows"][0]
        self._assert_row_contract(
            first,
            tweet_id=self.fixture["replacement_id"],
            tint="tint-pos-mixed",
        )

        second_page = self._feed_payload(limit=50, cursor=payload["next_cursor"])
        self.assertEqual([row["tweet_id"] for row in second_page["rows"]], [self.fixture["page_two_id"]])
        self.assertEqual(second_page["rows"][0]["tint_class"], "tint-neg-mixed")

        all_rows = self._feed_payload(limit=50, filters=json.dumps({"unsanctioned": "any"}))
        flagged = next(row for row in all_rows["rows"] if row["unsanctioned"])
        self.assertIn("unsanctioned", flagged)
        self.assertTrue(flagged["unsanctioned"])

    def test_brand_scope_changes_display_tint_without_losing_classifications(self) -> None:
        target = self.fixture["brand_scope_id"]

        def matching_row(payload: dict[str, object]) -> dict[str, object] | None:
            return next(
                (row for row in payload["rows"] if row["tweet_id"] == target),
                None,
            )

        all_row = matching_row(self._feed_payload(limit=50))
        self.assertIsNotNone(all_row)
        self.assertEqual(all_row["sentiment_keys"], ["positive", "negative"])
        self.assertEqual(all_row["tint_class"], "tint-pos-neg")
        complete_classifications = all_row["classifications"]

        minimax_row = matching_row(
            self._feed_payload(limit=50, filters=json.dumps({"brands": ["minimax"]}))
        )
        self.assertIsNotNone(minimax_row)
        self.assertEqual(minimax_row["sentiment_keys"], ["positive"])
        self.assertEqual(minimax_row["tint_class"], "tint-positive")
        self.assertEqual(minimax_row["classifications"], complete_classifications)

        kimi_row = matching_row(
            self._feed_payload(limit=50, filters=json.dumps({"brands": ["moonshot_kimi"]}))
        )
        self.assertIsNotNone(kimi_row)
        self.assertEqual(kimi_row["sentiment_keys"], ["negative"])
        self.assertEqual(kimi_row["tint_class"], "tint-negative")
        self.assertEqual(kimi_row["classifications"], complete_classifications)

        reset_row = matching_row(
            self._feed_payload(limit=50, filters=json.dumps({"brands": "__all__"}))
        )
        self.assertEqual(reset_row["sentiment_keys"], ["positive", "negative"])
        self.assertEqual(reset_row["tint_class"], "tint-pos-neg")
        self.assertEqual(reset_row["classifications"], complete_classifications)

        excluded = matching_row(
            self._feed_payload(limit=50, filters=json.dumps({"brands": ["qwen"]}))
        )
        self.assertIsNone(excluded, "a non-associated brand must exclude the row")

    def test_feed_metadata_projection_has_a_bounded_query_count(self) -> None:
        with CaptureQueriesContext(connection) as full_queries:
            full_payload = self._feed_payload(
                limit=50,
                filters=json.dumps({"unsanctioned": "any"}),
            )
        self.assertEqual(len(full_payload["rows"]), 50)

        Post.objects.exclude(tweet_id=self.fixture["brand_scope_id"]).delete()
        with CaptureQueriesContext(connection) as single_queries:
            single_payload = self._feed_payload(
                limit=50,
                filters=json.dumps({"unsanctioned": "any"}),
            )
        self.assertEqual(len(single_payload["rows"]), 1)
        self.assertEqual(
            len(full_queries),
            len(single_queries),
            "metadata query shape must stay constant from one to 52 enriched rows",
        )
        self.assertLessEqual(
            len(full_queries),
            30,
            "52 enriched rows must use bounded bulk metadata queries, not per-row lookups",
        )

    def test_anonymous_browser_refetch_and_page_two_append_paint_metadata(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.wait_for_function("() => window.pwFilter && document.querySelector('[data-pw-feed-body]')")
                    self._assert_visible_metadata(page, self.fixture["replacement_id"], "tint-pos-mixed")

                    with page.expect_response(lambda response: "/feed/?" in response.url and response.status == 200):
                        page.evaluate("() => document.dispatchEvent(new CustomEvent('pw:locale-change'))")
                    page.locator(f".feed-row[data-tweet-id='{self.fixture['replacement_id']}']").wait_for()
                    self._assert_visible_metadata(page, self.fixture["replacement_id"], "tint-pos-mixed")

                    sentinel = page.locator("[data-pw-feed-sentinel]")
                    with page.expect_response(lambda response: "/feed/?" in response.url and response.status == 200):
                        sentinel.scroll_into_view_if_needed()
                    page.locator(f".feed-row[data-tweet-id='{self.fixture['page_two_id']}']").wait_for()
                    self._assert_visible_metadata(page, self.fixture["page_two_id"], "tint-neg-mixed")
                finally:
                    context.close()
            finally:
                browser.close()

    def test_browser_keeps_server_tint_when_response_marker_data_conflicts(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    intercepted = {"done": False}

                    def retain_server_tint(route) -> None:
                        response = route.fetch()
                        payload = response.json()
                        if not intercepted["done"] and payload.get("rows"):
                            payload["rows"][0]["sentiment_keys"] = ["negative"]
                            payload["rows"][0]["tint_class"] = "tint-pos-mixed"
                            intercepted["done"] = True
                        route.fulfill(response=response, json=payload)

                    page.route("**/feed/**", retain_server_tint)
                    with page.expect_response(lambda response: "/feed/?" in response.url and response.status == 200):
                        page.evaluate("() => document.dispatchEvent(new CustomEvent('pw:locale-change'))")
                    row = page.locator(f".feed-row[data-tweet-id='{self.fixture['replacement_id']}']")
                    row.wait_for()
                    self.assertEqual(row.get_attribute("data-sentiments"), "negative")
                    self.assertTrue(row.locator(".feed-row-shell").evaluate("element => element.classList.contains('tint-pos-mixed')"))
                    self.assertEqual(row.locator("[data-sig-sentiment]").text_content(), "🙁")
                    self.assertTrue(intercepted["done"])
                finally:
                    context.close()
            finally:
                browser.close()

    def test_browser_brand_scope_transitions_gradient_to_solids_and_back(self) -> None:
        target = self.fixture["brand_scope_id"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    target_row = page.locator(f".feed-row[data-tweet-id='{target}']")
                    target_row.wait_for()
                    self.assertTrue(
                        target_row.locator(".feed-row-shell").evaluate(
                            "element => element.classList.contains('tint-pos-neg')"
                        )
                    )

                    complete_classifications = None
                    for brands, expected_tint, expected_sentiments in (
                        (["minimax"], "tint-positive", "positive"),
                        (["moonshot_kimi"], "tint-negative", "negative"),
                        ("__all__", "tint-pos-neg", "positive,negative"),
                    ):
                        with page.expect_response(
                            lambda response: "/feed/?" in response.url and response.status == 200
                        ) as response_info:
                            page.evaluate("brands => window.pwFilter.set('brands', brands)", brands)
                        payload = response_info.value.json()
                        payload_row = next(row for row in payload["rows"] if row["tweet_id"] == target)
                        if complete_classifications is None:
                            complete_classifications = payload_row["classifications"]
                        self.assertEqual(payload_row["classifications"], complete_classifications)
                        target_row = page.locator(f".feed-row[data-tweet-id='{target}']")
                        target_row.wait_for()
                        self.assertEqual(target_row.get_attribute("data-sentiments"), expected_sentiments)
                        self.assertEqual(target_row.get_attribute("data-tint"), expected_tint)
                        self.assertTrue(
                            target_row.locator(".feed-row-shell").evaluate(
                                "(element, tint) => element.classList.contains(tint)",
                                expected_tint,
                            )
                        )
                finally:
                    context.close()
            finally:
                browser.close()

    def test_valid_empty_renders_localized_state_and_then_recovers(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    with page.expect_response(
                        lambda response: "/feed/?" in response.url and response.status == 200
                    ) as empty_response:
                        page.evaluate("() => window.pwFilter.set('brands', ['qwen'])")
                    self.assertEqual(empty_response.value.json()["rows"], [])
                    page.locator("[data-pw-feed-body] .muted-cell").wait_for()
                    self.assertEqual(
                        page.locator("[data-pw-feed-body] .muted-cell").inner_text(),
                        "no posts in window",
                    )
                    self.assertEqual(page.locator(".feed-row[data-pw-feed-row]").count(), 0)

                    with page.expect_response(
                        lambda response: "/feed/?" in response.url and response.status == 200
                    ):
                        page.evaluate("() => window.pwFilter.set('brands', ['moonshot_kimi'])")
                    page.locator(
                        f".feed-row[data-tweet-id='{self.fixture['replacement_id']}']"
                    ).wait_for()
                finally:
                    context.close()
            finally:
                browser.close()

    def test_stale_page_two_cannot_append_after_new_filter_replacement(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.evaluate(
                        """
                        () => {
                          const realFetch = window.fetch.bind(window);
                          const row = (id, tint, sentiment) => ({
                            tweet_id: id,
                            created_at: '2026-08-11T01:00:00+00:00',
                            created_at_iso: '2026-08-11T01:00:00+00:00',
                            text: id,
                            text_original: id,
                            text_translated: id,
                            text_en: id,
                            account: {handle: '@u4race'},
                            classifications: {},
                            sentiment_keys: [sentiment],
                            post_type_keys: [],
                            nat_cn: '',
                            nat_us: '',
                            tint_class: tint,
                          });
                          const response = (payload, status = 200) => Promise.resolve(new Response(
                            JSON.stringify(payload),
                            {status, headers: {'Content-Type': 'application/json'}}
                          ));
                          window.__u4OldStarted = false;
                          window.fetch = (input, options) => {
                            const url = new URL(String(input), window.location.origin);
                            if (url.pathname !== '/feed/') return realFetch(input, options);
                            const filters = JSON.parse(url.searchParams.get('filters') || '{}');
                            const brand = Array.isArray(filters.brands) ? filters.brands[0] : '';
                            if (url.searchParams.get('cursor') && !window.__u4OldStarted) {
                              window.__u4OldStarted = true;
                              return new Promise((resolve) => {
                                window.__u4ResolveOld = () => resolve(new Response(JSON.stringify({
                                  rows: [row('race-old-page', 'tint-negative', 'negative')],
                                  next_cursor: 'old-cursor',
                                  has_more: true,
                                }), {status: 200, headers: {'Content-Type': 'application/json'}}));
                              });
                            }
                            if (brand === 'qwen') return response({
                              rows: [row('race-new-filter', 'tint-positive', 'positive')],
                              next_cursor: null,
                              has_more: false,
                            });
                            if (brand === 'deepseek') return response({
                              rows: [row('race-retry', 'tint-mixed', 'mixed')],
                              next_cursor: null,
                              has_more: false,
                            });
                            return realFetch(input, options);
                          };
                        }
                        """
                    )
                    page.locator("[data-pw-feed-sentinel]").scroll_into_view_if_needed()
                    page.wait_for_function("() => window.__u4OldStarted")
                    page.evaluate(
                        """
                        () => document.dispatchEvent(new CustomEvent('pw:filter-change', {
                          detail: {filters: {...window.pwFilter.get(), brands: ['qwen']}}
                        }))
                        """
                    )
                    page.locator(".feed-row[data-tweet-id='race-new-filter']").wait_for()
                    page.evaluate("() => window.__u4ResolveOld()")
                    page.wait_for_timeout(100)
                    self.assertEqual(page.locator(".feed-row[data-tweet-id='race-old-page']").count(), 0)
                    self.assertEqual(page.locator(".feed-row[data-tweet-id='race-new-filter']").count(), 1)

                    page.evaluate(
                        """
                        () => document.dispatchEvent(new CustomEvent('pw:filter-change', {
                          detail: {filters: {...window.pwFilter.get(), brands: ['deepseek']}}
                        }))
                        """
                    )
                    page.locator(".feed-row[data-tweet-id='race-retry']").wait_for()
                finally:
                    context.close()
            finally:
                browser.close()

    def test_failed_and_malformed_replacements_preserve_rows_and_retry(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    current_id = self.fixture["replacement_id"]
                    page.locator(f".feed-row[data-tweet-id='{current_id}']").wait_for()
                    page.evaluate(
                        """
                        () => {
                          const realFetch = window.fetch.bind(window);
                          const row = (id) => ({
                            tweet_id: id,
                            created_at: '2026-08-11T01:00:00+00:00',
                            created_at_iso: '2026-08-11T01:00:00+00:00',
                            text: id,
                            text_original: id,
                            text_translated: id,
                            text_en: id,
                            account: {handle: '@u4retry'},
                            classifications: {},
                            sentiment_keys: ['positive'],
                            post_type_keys: [],
                            nat_cn: '',
                            nat_us: '',
                            tint_class: 'tint-positive',
                          });
                          window.__u4FailureMode = null;
                          window.__u4RecoveryId = 'recovered';
                          window.fetch = (input, options) => {
                            const url = new URL(String(input), window.location.origin);
                            if (url.pathname !== '/feed/') return realFetch(input, options);
                            if (window.__u4FailureMode === 'http') {
                              return Promise.resolve(new Response('server failed', {status: 500}));
                            }
                            if (window.__u4FailureMode === 'malformed') {
                              return Promise.resolve(new Response(JSON.stringify({rows: null}), {
                                status: 200,
                                headers: {'Content-Type': 'application/json'},
                              }));
                            }
                            if (window.__u4FailureMode === 'network') {
                              return Promise.reject(new TypeError('offline'));
                            }
                            return Promise.resolve(new Response(JSON.stringify({
                              rows: [row(window.__u4RecoveryId)],
                              next_cursor: null,
                              has_more: false,
                            }), {status: 200, headers: {'Content-Type': 'application/json'}}));
                          };
                        }
                        """
                    )

                    for mode in ("http", "malformed", "network"):
                        page.evaluate("mode => { window.__u4FailureMode = mode; }", mode)
                        page.evaluate(
                            """
                            mode => document.dispatchEvent(new CustomEvent('pw:filter-change', {
                              detail: {filters: {...window.pwFilter.get(), brands: [mode]}}
                            }))
                            """,
                            mode,
                        )
                        page.wait_for_function(
                            """
                            () => {
                              const status = document.querySelector('[data-pw-feed-status]');
                              return status && !status.hidden && /refresh failed/i.test(status.textContent || '');
                            }
                            """
                        )
                        self.assertEqual(page.locator(f".feed-row[data-tweet-id='{current_id}']").count(), 1)

                        recovered_id = f"recovered-{mode}"
                        page.evaluate(
                            "([id]) => { window.__u4FailureMode = null; window.__u4RecoveryId = id; }",
                            [recovered_id],
                        )
                        page.evaluate(
                            """
                            () => document.dispatchEvent(new CustomEvent('pw:filter-change', {
                              detail: {filters: {...window.pwFilter.get(), brands: ['minimax']}}
                            }))
                            """
                        )
                        page.locator(f".feed-row[data-tweet-id='{recovered_id}']").wait_for()
                        self.assertTrue(page.locator("[data-pw-feed-status]").is_hidden())
                        current_id = recovered_id
                finally:
                    context.close()
            finally:
                browser.close()

    def test_periodic_refresh_uses_the_shared_metadata_hydrator(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                context.add_init_script(
                    """
                    (() => {
                      const realSetInterval = window.setInterval.bind(window);
                      const realClearInterval = window.clearInterval.bind(window);
                      window.__u4MinuteCallbacks = [];
                      window.setInterval = (fn, delay, ...args) => {
                        if (delay === 60000) {
                          window.__u4MinuteCallbacks.push(fn);
                          return -window.__u4MinuteCallbacks.length;
                        }
                        return realSetInterval(fn, delay, ...args);
                      };
                      window.clearInterval = (id) => id < 0 ? undefined : realClearInterval(id);
                    })();
                    """
                )
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    callback_names = page.evaluate("() => window.__u4MinuteCallbacks.map(fn => fn.name)")
                    self.assertIn(
                        "refreshFirstPage",
                        callback_names,
                        "the feed interval must schedule its named shared refresh path",
                    )
                    page.evaluate(
                        """
                        () => {
                          const realFetch = window.fetch.bind(window);
                          window.fetch = (input, options) => {
                            const url = new URL(String(input), window.location.origin);
                            if (url.pathname !== '/feed/') return realFetch(input, options);
                            return Promise.resolve(new Response(JSON.stringify({
                              rows: [{
                                tweet_id: 'periodic-refresh-row',
                                created_at: '2026-08-11T01:00:00+00:00',
                                created_at_iso: '2026-08-11T01:00:00+00:00',
                                text: 'periodic refresh',
                                text_original: 'periodic refresh',
                                text_translated: 'periodic refresh',
                                text_en: 'periodic refresh',
                                account: {handle: '@u4refresh'},
                                classifications: {},
                                sentiment_keys: ['negative', 'mixed'],
                                post_type_keys: ['hands_on_usage'],
                                nat_cn: 'pro',
                                nat_us: 'mild_pro',
                                tint_class: 'tint-neg-mixed',
                              }],
                              next_cursor: null,
                              has_more: false,
                            }), {status: 200, headers: {'Content-Type': 'application/json'}}));
                          };
                          window.__u4MinuteCallbacks.find(fn => fn.name === 'refreshFirstPage')();
                        }
                        """
                    )
                    refreshed = page.locator(".feed-row[data-tweet-id='periodic-refresh-row']")
                    refreshed.wait_for()
                    self.assertEqual(refreshed.get_attribute("data-tint"), "tint-neg-mixed")
                    self.assertEqual(refreshed.locator("[data-sig-sentiment]").text_content(), "🙁😐")
                    self.assertEqual(refreshed.locator("[data-sig-post-type]").text_content(), "🤚")
                    self.assertTrue((refreshed.locator("[data-sig-nat]").text_content() or "").strip())
                finally:
                    context.close()
            finally:
                browser.close()
