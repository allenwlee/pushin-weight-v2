"""Real route, template, assets, and browser interaction for the each dashboard."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright

from core.models import Brand
from monitor.views import _clear_home_pulse_cache
from tests.ui_assurance.local_preview import load_pinned_assets
from tests.v22_support import fixture_from_oracle, seed_real_home_orm

pytestmark = pytest.mark.requires_postgres


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardEachBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        seed_real_home_orm(fixture_from_oracle())
        from django.utils import timezone

        from tests.test_chart_harvest_coverage import record_harvest

        now = timezone.now()
        record_harvest(now, finished_at=now, staggered=False)
        Brand.objects.create(nickname="untracked-demo", display_name="Untracked Demo")
        _clear_home_pulse_cache()

    def test_tabs_and_pulse_keep_one_brand_with_visible_stacked_chart(self):
        assets = load_pinned_assets()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900}, timezone_id="Asia/Tokyo"
                )
                context.route(
                    "https://unpkg.com/htmx.org@1.9.10",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/javascript",
                        body=assets["/__bridgewright_assets/htmx-1.9.10.js"],
                    ),
                )
                context.route(
                    "https://unpkg.com/chart.js@4.4.0",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/javascript",
                        body=assets["/__bridgewright_assets/chart-4.4.0.js"],
                    ),
                )
                page = context.new_page()
                errors = []
                initial_chart_requests = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: initial_chart_requests.append(request.url)
                        if "/dashboard/each/chart/" in request.url else None)
                response = page.goto(
                    f"{self.live_server_url}/dashboard/each?brand=minimax&locale=en",
                    wait_until="networkidle",
                )
                self.assertEqual(response.status, 200)
                self.assertEqual(len(initial_chart_requests), 1)
                self.assertEqual(
                    page.locator('[data-pw-pulse-entry="untracked-demo"]').count(), 0
                )
                self.assertEqual(
                    page.locator('[data-pw-pulse-entry][aria-pressed="true"]').count(),
                    1,
                )
                self.assertEqual(
                    page.locator(
                        '[data-pw-pulse-entry][aria-pressed="true"]'
                    ).get_attribute("data-pw-pulse-entry"),
                    "minimax",
                )
                self.assertEqual(
                    page.locator("[data-pw-feed]").get_attribute("data-pw-brand-scope"),
                    "minimax",
                )
                self.assertEqual(
                    page.locator("[data-pw-each-chart]").get_attribute(
                        "data-counting-unit"
                    ),
                    "posts",
                )
                self.assertGreater(
                    page.locator("[data-each-canvas]").bounding_box()["width"], 100
                )
                self.assertGreater(
                    page.locator("[data-each-canvas]").bounding_box()["height"], 100
                )
                self.assertTrue(
                    page.evaluate(
                        "Chart.getChart(document.querySelector('[data-each-canvas]')).data.datasets.every(dataset => dataset.fill === 'stack')"
                    )
                )
                self.assertEqual(page.get_by_role("tab", name="Product").count(), 1)
                self.assertTrue(page.locator('[data-each-mode="percent"]').is_checked())
                self.assertTrue(page.evaluate("""() => {
                  const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
                  const columns = chart.data.labels.map((_, index) =>
                    chart.data.datasets.reduce((sum, dataset) => sum + (dataset.data[index] || 0), 0));
                  return chart.options.scales.y.max === 100 &&
                    columns.some(total => Math.abs(total - 100) < 0.001) &&
                    columns.every(total => total === 0 || Math.abs(total - 100) < 0.001);
                }"""))
                chart_requests = []
                page.on("request", lambda request: chart_requests.append(request.url)
                        if "/dashboard/each/chart/" in request.url else None)
                page.locator('[data-each-mode="volume"]').check()
                self.assertTrue(page.evaluate("""() => {
                  const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
                  return chart.options.scales.y.max === undefined &&
                    chart.data.datasets.every(dataset => dataset.data.every(value => Number.isInteger(value)));
                }"""))
                page.locator('[data-each-mode="percent"]').check()
                self.assertEqual(chart_requests, [])
                first_shot = (
                    Path(__file__).resolve().parents[1]
                    / ".pytest-tmp"
                    / "dashboard-each-initial.png"
                )
                first_shot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(first_shot), full_page=True)
                page.locator('[data-each-tab="post_types"]').click()
                page.wait_for_function(
                    "document.querySelector('[data-pw-each-chart]').dataset.countingUnit === 'label_assignments'"
                )
                self.assertTrue(page.locator('[data-each-mode="percent"]').is_checked())
                self.assertTrue(page.evaluate("""() => {
                  const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
                  return chart.options.scales.y.max === 100 &&
                    chart.data.labels.every((_, index) => {
                      const total = chart.data.datasets.reduce(
                        (sum, dataset) => sum + (dataset.data[index] || 0), 0);
                      return total === 0 || Math.abs(total - 100) < 0.001;
                    });
                }"""))
                self.assertEqual(
                    page.locator('[data-each-tab][aria-selected="true"]').count(), 1
                )
                page.locator('[data-pw-pulse-entry="qwen"]').click()
                page.wait_for_function(
                    "document.querySelector('[data-pw-each-chart]').dataset.selectedBrand === 'qwen'"
                )
                self.assertEqual(
                    page.locator("[data-pw-feed]").get_attribute("data-pw-brand-scope"),
                    "qwen",
                )
                self.assertEqual(
                    page.locator('[data-pw-pulse-entry][aria-pressed="true"]').count(),
                    1,
                )
                self.assertEqual(
                    page.locator('[data-each-tab="post_types"]').get_attribute(
                        "aria-selected"
                    ),
                    "true",
                )
                self.assertIn("tab=post_types", page.url)
                with page.expect_navigation():
                    page.locator('[data-pw-window-btn="7"]').click()
                self.assertEqual(
                    page.locator('[data-each-tab="post_types"]').get_attribute(
                        "aria-selected"
                    ),
                    "true",
                )
                self.assertEqual(
                    page.locator(
                        '[data-pw-pulse-entry][aria-pressed="true"]'
                    ).get_attribute("data-pw-pulse-entry"),
                    "qwen",
                )
                shot = (
                    Path(__file__).resolve().parents[1]
                    / ".pytest-tmp"
                    / "dashboard-each-desktop.png"
                )
                shot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                self.assertLessEqual(
                    page.evaluate("document.documentElement.scrollWidth"), 390
                )
                self.assertGreater(
                    page.locator("[data-each-canvas]").bounding_box()["width"], 100
                )
                with page.expect_navigation():
                    page.locator('[data-pw-locale-btn="ja"]').click()
                self.assertEqual(page.locator("body").get_attribute("data-pw-locale"), "ja")
                self.assertEqual(page.get_by_role("radio", name="全体に占める割合").count(), 1)
                self.assertEqual(page.get_by_role("tab", name="製品").count(), 1)
                self.assertEqual(
                    page.locator('[data-each-tab="post_types"]').get_attribute("aria-selected"),
                    "true",
                )
                self.assertEqual(
                    page.locator('[data-pw-pulse-entry][aria-pressed="true"]').get_attribute("data-pw-pulse-entry"),
                    "qwen",
                )
                with page.expect_navigation():
                    page.locator('[data-pw-locale-btn="zh_cn"]').click()
                self.assertEqual(page.get_by_role("radio", name="占总量百分比").count(), 1)
                self.assertEqual(page.get_by_role("tab", name="产品").count(), 1)
                page.evaluate(
                    """() => {
                      const nativeFetch = window.fetch.bind(window);
                      window.__pendingEach = [];
                      window.fetch = (url, options) => {
                        if (!String(url).includes('/dashboard/each/chart/')) {
                          return nativeFetch(url, options);
                        }
                        return new Promise((resolve, reject) => {
                          nativeFetch(url, {credentials: 'same-origin'})
                            .then(response => window.__pendingEach.push({
                              brand: new URL(String(url), location.href).searchParams.get('brand'),
                              resolve: () => resolve(response)
                            }))
                            .catch(reject);
                        });
                      };
                      document.querySelector('[data-pw-pulse-entry="deepseek"]').click();
                      document.querySelector('[data-pw-pulse-entry="minimax"]').click();
                    }"""
                )
                page.wait_for_function("window.__pendingEach.length === 2")
                page.evaluate("window.__pendingEach.find(item => item.brand === 'minimax').resolve()")
                page.wait_for_function(
                    "document.querySelector('[data-pw-each-chart]').dataset.selectedBrand === 'minimax'"
                )
                page.evaluate("window.__pendingEach.find(item => item.brand === 'deepseek').resolve()")
                page.wait_for_timeout(100)
                self.assertEqual(
                    page.locator("[data-pw-each-chart]").get_attribute("data-selected-brand"),
                    "minimax",
                )
                self.assertEqual(
                    page.locator("[data-pw-feed]").get_attribute("data-pw-brand-scope"),
                    "minimax",
                )
                self.assertEqual(errors, [])
                context.close()
            finally:
                browser.close()


EACH_CHART_STATE = """() => {
  const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
  const x = chart.scales.x;
  const y = chart.scales.y;
  return {
    tab: document.querySelector('[data-each-tab][aria-selected="true"]').dataset.eachTab,
    yPosition: y.options.position,
    yBorder: y.options.border.display,
    gridDash: y.options.border.dash,
    yMax: chart.options.scales.y.max ?? null,
    tooltip: chart.options.plugins.tooltip.enabled !== false,
    datasets: chart.data.datasets.map((dataset) => ({
      label: dataset.label,
      color: String(dataset.borderColor).toLowerCase(),
      borderWidth: dataset.borderWidth,
      pointRadius: dataset.pointRadius,
      monotone: dataset.cubicInterpolationMode,
    })),
    labels: chart.data.labels.length,
    lastTick: x.ticks.length ? x.ticks[x.ticks.length - 1].value : null,
    tickCount: x.ticks.length,
    legend: [...document.querySelectorAll('[data-each-legend] > *')].map((node) => node.textContent.trim()),
  };
}"""

FIXED_COLORS = {
    "#cbd5e1": ("Unclassified", "Undetected"),
    "#000000": ("Neutral", "Other", "No assigned topic", "No product signal"),
}


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardEachGeneralStyleBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        seed_real_home_orm(fixture_from_oracle())
        from django.utils import timezone

        from tests.test_chart_harvest_coverage import record_harvest

        now = timezone.now()
        record_harvest(now, finished_at=now, staggered=False)
        _clear_home_pulse_cache()

    def _context(self, browser):
        from tests.general_style_browser import open_page

        return open_page(browser, self.live_server_url).context

    def _wait_for_chart(self, page, tab=None):
        page.wait_for_function(
            """tab => {
              const canvas = document.querySelector('[data-each-canvas]');
              const chart = canvas && window.Chart && Chart.getChart(canvas);
              const selected = document.querySelector('[data-each-tab][aria-selected="true"]');
              return Boolean(chart && chart.data.datasets.length && (!tab || selected.dataset.eachTab === tab));
            }""",
            arg=tab,
        )

    def test_every_tab_uses_the_shared_axis_and_area_style(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._context(browser)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(
                    f"{self.live_server_url}/dashboard/each?brand=deepseek&locale=en&window=7",
                    wait_until="networkidle",
                )
                tabs = page.locator("[data-each-tab]")
                labels = [text.strip() for text in tabs.all_inner_texts()]
                self.assertIn("Language", labels)
                self.assertIn("3rd Party Brand Promotions", labels)
                for index in range(tabs.count()):
                    tab = tabs.nth(index).get_attribute("data-each-tab")
                    with self.subTest(tab=tab):
                        tabs.nth(index).click()
                        self._wait_for_chart(page, tab)
                        state = page.evaluate(EACH_CHART_STATE)
                        self.assertEqual(state["yPosition"], "right")
                        self.assertIs(state["yBorder"], False)
                        self.assertEqual(state["gridDash"], [1, 3])
                        self.assertTrue(state["tooltip"], "the category tooltip stays")
                        for dataset in state["datasets"]:
                            self.assertEqual(dataset["borderWidth"], 1, dataset)
                            self.assertEqual(dataset["pointRadius"], 0, dataset)
                            self.assertEqual(dataset["monotone"], "monotone", dataset)
                            self.assertTrue(dataset["label"][:1].isupper(), dataset)
                            for color, names in FIXED_COLORS.items():
                                if dataset["label"] in names:
                                    self.assertEqual(dataset["color"], color, dataset)
                        self.assertTrue(all(text[:1].isupper() for text in state["legend"] if text), state["legend"])
                        # Percent mode caps the stack at 100; volume mode leaves it open.
                        self.assertEqual(state["yMax"], 100)
                        page.locator('[data-each-mode="volume"]').check()
                        self.assertIsNone(page.evaluate(EACH_CHART_STATE)["yMax"])
                        page.locator('[data-each-mode="percent"]').check()

                # The category tooltip still appears on hover.
                tabs.first.click()
                self._wait_for_chart(page)
                point = page.evaluate(
                    """() => {
                      const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
                      const rect = chart.canvas.getBoundingClientRect();
                      const last = chart.getDatasetMeta(0).data.at(-1);
                      return {x: rect.left + last.x - 2, y: rect.top + (chart.chartArea.top + chart.chartArea.bottom) / 2};
                    }"""
                )
                page.mouse.move(point["x"], point["y"])
                page.wait_for_function(
                    "() => Chart.getChart(document.querySelector('[data-each-canvas]')).tooltip.opacity > 0"
                )
                self.assertEqual(errors, [])
                context.close()
            finally:
                browser.close()

    def test_newest_tick_is_kept_in_every_window_and_language(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._context(browser)
                page = context.new_page()
                fetched = []
                page.on(
                    "response",
                    lambda response: fetched.append(response.json())
                    if "/dashboard/each/chart/" in response.url and response.status == 200
                    else None,
                )
                for locale in ("en", "zh_cn"):
                    for window in (1, 7, 30, 365):
                        with self.subTest(locale=locale, window=window):
                            fetched.clear()
                            page.goto(
                                f"{self.live_server_url}/dashboard/each?brand=deepseek&locale={locale}&window={window}",
                                wait_until="networkidle",
                            )
                            self._wait_for_chart(page)
                            state = page.evaluate(EACH_CHART_STATE)
                            days = (
                                fetched[-1]["days"]
                                if fetched
                                else page.evaluate(
                                    "() => JSON.parse(document.getElementById('each-initial-chart').textContent).days"
                                )
                            )
                            self.assertEqual(len(days), state["labels"])
                            # Date axes end on the latest day; the 365-day axis labels month
                            # starts, so its newest tick is the latest month start.
                            newest = (
                                max(index for index, day in enumerate(days) if day.endswith("-01"))
                                if window == 365
                                else len(days) - 1
                            )
                            self.assertEqual(state["lastTick"], newest)
                            self.assertGreaterEqual(state["tickCount"], 2)
                            if window == 1:
                                self.assertLessEqual(state["tickCount"], 8)
                context.close()
            finally:
                browser.close()

    def test_tab_labels_are_localized(self):
        expected = {
            "zh_cn": ("语言", "第三方品牌推广"),
            "ja": ("言語", "サードパーティのブランドプロモーション"),
        }
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._context(browser)
                page = context.new_page()
                for locale, labels in expected.items():
                    page.goto(
                        f"{self.live_server_url}/dashboard/each?brand=deepseek&locale={locale}",
                        wait_until="networkidle",
                    )
                    texts = [text.strip() for text in page.locator("[data-each-tab]").all_inner_texts()]
                    for label in labels:
                        self.assertIn(label, texts)
                context.close()
            finally:
                browser.close()
