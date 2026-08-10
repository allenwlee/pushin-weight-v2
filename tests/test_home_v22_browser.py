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

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client
from playwright.sync_api import BrowserContext, Page, sync_playwright

from tests.mockup_spec import DEFAULT_SOURCE, MockupSpec, load_spec
from tests.shell_diff import AUTHORED_REGIONS, parse_rendered_html, select_one
from tests.v22_support import (
    V22_TEST_USER_EMAIL,
    fixture_from_oracle,
    seed_real_home_orm,
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


class HomeV22BrowserTests(StaticLiveServerTestCase):
    """Root-route, real-PostgreSQL browser proof for v22's visible shell."""

    def setUp(self) -> None:
        """Rebuild browser-visible fixtures after TransactionTestCase flushes."""
        super().setUp()
        self.fixture = fixture_from_oracle()
        seed_real_home_orm(self.fixture)
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

    def _authenticated_context(
        self, browser, cookies: list[dict[str, str]], viewport: dict[str, int]
    ) -> BrowserContext:
        context = browser.new_context(viewport=viewport, timezone_id="Asia/Tokyo")
        _freeze_clock(context)
        context.add_cookies(cookies)
        return context

    def test_zh_hans_renders_chinese_chrome_in_browser(self) -> None:
        """The Django ``zh_hans`` alias keeps v22 chrome Chinese after JS initializes."""
        cookies = self._authenticated_cookies("zh_hans")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._authenticated_context(browser, cookies, VIEWPORTS["desktop"])
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

    def test_fixture_root_route_matches_mockup_in_browser(self) -> None:
        spec = load_spec()
        artifacts = _artifact_dir()
        reports: list[dict[str, object]] = []
        # Django's synchronous test client cannot run inside Playwright's
        # sync bridge event loop, so mint the ordinary test-user cookies first.
        cookies_by_locale = {locale: self._authenticated_cookies(locale) for locale in LOCALES}

        with serve_mockup_over_http() as mockup_url, sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for viewport_name, viewport in VIEWPORTS.items():
                    for locale in LOCALES:
                        context = self._authenticated_context(browser, cookies_by_locale[locale], viewport)
                        page = context.new_page()
                        reference = context.new_page()
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
                            initial_feed_stamp = feed_stamp.text_content()
                            initial_time = tz.locator("[data-tz-time]").text_content()
                            self.assertRegex(initial_time or "", r"^\d{2}:\d{2}$")
                            self.assertNotEqual(initial_time, "00:00", "timezone runtime left its authored placeholder unchanged")
                            tz.click()
                            page.wait_for_function("() => window.__pwTz?.mode === 'ca'")
                            self.assertEqual(tz.get_attribute("data-tz-active"), "ca")
                            self.assertIn("CA", tz.inner_text())
                            self.assertNotEqual(feed_stamp.text_content(), initial_feed_stamp)

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
