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
    "#8290a7": ("Unclassified", "Undetected"),
    "#25334b": ("Neutral", "Other", "No assigned topic", "No product signal"),
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
              const root = document.querySelector('[data-pw-each-chart]');
              return Boolean(chart && chart.data.datasets.length && (!tab ||
                selected.dataset.eachTab === tab) && root.dataset.committedTab === selected.dataset.eachTab &&
                !root.querySelector('.each-chart-panel').hasAttribute('aria-busy') &&
                !root.querySelector('.each-chart-face').classList.contains('is-turning-in') &&
                !root.querySelector('.each-chart-face').classList.contains('is-turning-out'));
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
                            self.assertEqual(dataset["borderWidth"], 2, dataset)
                            self.assertEqual(dataset["pointRadius"], 0, dataset)
                            self.assertEqual(dataset["monotone"], "monotone", dataset)
                            self.assertEqual(dataset["label"][:1], dataset["label"][:1].upper(), dataset)
                            for color, names in FIXED_COLORS.items():
                                if dataset["label"] in names:
                                    self.assertEqual(dataset["color"], color, dataset)
                        self.assertTrue(all(text[:1] == text[:1].upper() for text in state["legend"] if text), state["legend"])
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

    def test_failed_tab_switch_names_the_retained_chart_in_notice_and_accessible_label(self):
        from tests.general_style_browser import open_page

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale, old_label, requested_label in (
                    ("en", "Sentiment", "Product"),
                    ("zh_cn", "情绪", "产品"),
                    ("ja", "感情", "製品"),
                ):
                    with self.subTest(locale=locale):
                        run = open_page(browser, self.live_server_url, reduced_motion="reduce")
                        page = run.page
                        page.goto(
                            f"{self.live_server_url}/dashboard/each?brand=deepseek&locale={locale}&window=7",
                            wait_until="networkidle",
                        )
                        self._wait_for_chart(page, "sentiment")
                        previous_values = page.evaluate("""() => {
                          const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
                          window.__retainedEachChart = chart;
                          return chart.data.datasets.map(dataset => dataset.data);
                        }""")
                        button = page.locator("[data-each-category]").first
                        pinned = button.get_attribute("data-each-category")
                        button.click()
                        run.context.route(
                            "**/dashboard/each/chart/**",
                            lambda route: route.fulfill(
                                status=503,
                                content_type="application/json",
                                body='{"error":"chart_timeout"}',
                            ),
                        )
                        page.locator('[data-each-tab="product_labels"]').click()
                        page.wait_for_function("""() => {
                          const panel = document.querySelector('.each-chart-panel');
                          const status = document.querySelector('[data-each-status]');
                          return !panel.hasAttribute('aria-busy') && !status.hidden && status.textContent;
                        }""")
                        retained = page.evaluate("""() => {
                          const root = document.querySelector('[data-pw-each-chart]');
                          const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
                          return {
                            sameInstance: chart === window.__retainedEachChart,
                            committedTab: root.dataset.committedTab,
                            requestedTab: document.querySelector('[data-each-tab][aria-selected="true"]').dataset.eachTab,
                            notice: document.querySelector('[data-each-status]').textContent,
                            accessibleLabel: chart.canvas.getAttribute('aria-label'),
                            values: chart.data.datasets.map(dataset => dataset.data),
                            visible: chart.canvas.getBoundingClientRect().width > 0 && chart.canvas.getBoundingClientRect().height > 0
                          };
                        }""")
                        self.assertTrue(retained["sameInstance"])
                        self.assertTrue(retained["visible"])
                        self.assertEqual(retained["committedTab"], "sentiment")
                        self.assertEqual(retained["requestedTab"], "product_labels")
                        self.assertEqual(retained["values"], previous_values)
                        self.assertIn(old_label, retained["notice"])
                        self.assertNotIn(requested_label, retained["notice"])
                        self.assertIn(old_label, retained["accessibleLabel"])
                        self.assertNotIn(requested_label, retained["accessibleLabel"])
                        page.locator('[data-each-mode="volume"]').check()
                        self.assertEqual(
                            page.locator("[data-each-status]").inner_text(), retained["notice"]
                        )
                        self.assertIn(
                            old_label, page.locator("[data-each-canvas]").get_attribute("aria-label")
                        )
                        self.assertEqual(
                            page.locator(f'[data-each-category="{pinned}"]').get_attribute("aria-pressed"),
                            "true",
                        )
                        self.assertEqual(run.errors, [])
                        run.context.close()
            finally:
                browser.close()

    def test_left_legend_matches_stack_and_emphasis_across_tabs_modes_sizes_locales(self):
        import hashlib
        from itertools import permutations

        from tests.ui_assurance.each import (
            EVIDENCE_PATH,
            ROOT,
            RUNTIME_PATH,
            load_each_declaration,
            load_seed_manifest,
            runtime_identity,
            write_each_runtime,
        )

        # A failed or skipped run must never inherit a prior browser proof.
        RUNTIME_PATH.unlink(missing_ok=True)
        EVIDENCE_PATH.unlink(missing_ok=True)
        declaration = load_each_declaration()
        seed = load_seed_manifest()
        self.assertEqual(
            hashlib.sha256((ROOT / seed["base_fixture"]).read_bytes()).hexdigest(),
            seed["base_fixture_sha256"],
        )
        packet = {
            "schema_version": "pushinweight.each-browser/v1",
            "producer": "tests.test_dashboard_each_browser.DashboardEachGeneralStyleBrowserTests.test_left_legend_matches_stack_and_emphasis_across_tabs_modes_sizes_locales",
            "identity": runtime_identity(declaration),
            "cases": [], "errors": [], "external": [], "seed_post_count": 0,
        }
        from tests.each_area_fixture import seed_each_area_orm
        from tests.general_style_browser import open_page

        packet["seed_post_count"] = seed_each_area_orm(seed)
        self.assertEqual(packet["seed_post_count"], sum(seed["counts"]))
        expected_tabs = {
            "sentiment", "post_types", "lang", "role", "audience_topics",
            "geopolitical_modes", "product_labels", "untracked_brand_promotions",
        }
        output = Path(__file__).resolve().parents[1] / ".pytest-tmp"
        output.mkdir(exist_ok=True)
        geometry = """() => {
          const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
          const canvas = chart.canvas.getBoundingClientRect();
          const area = chart.chartArea;
          const buttons = [...document.querySelectorAll('[data-each-category]')];
          return {
            viewportWidth: innerWidth, locale: document.body.dataset.pwLocale,
            tab: document.querySelector('[data-each-tab][aria-selected="true"]').dataset.eachTab,
            mode: document.querySelector('[data-each-mode]:checked').dataset.eachMode,
            keys: chart.data.datasets.map(dataset => dataset.categoryKey),
            labels: chart.data.datasets.map(dataset => dataset.label),
            legend: buttons.map(button => ({
              key: button.dataset.eachCategory, text: button.textContent.trim(),
              top: button.getBoundingClientRect().top,
              bottom: button.getBoundingClientRect().bottom,
              center: (button.getBoundingClientRect().top + button.getBoundingClientRect().bottom) / 2,
              right: button.getBoundingClientRect().right,
              labelClipped: button.querySelector('span').scrollWidth > button.querySelector('span').clientWidth + 1
            })),
            plotTop: canvas.top + area.top, plotBottom: canvas.top + area.bottom,
            plotLeft: canvas.left + area.left, canvasWidth: canvas.width,
            visible: chart.data.datasets.every((_, index) => chart.isDatasetVisible(index)),
            values: chart.data.datasets.map(dataset => dataset.data),
            fills: chart.data.datasets.map(dataset => dataset.backgroundColor),
            pageOverflow: document.documentElement.scrollWidth - innerWidth,
            chartBusy: document.querySelector('.each-chart-panel').hasAttribute('aria-busy')
          };
        }"""
        emphasis_state = """() => {
          const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
          return {
            values: chart.data.datasets.map(dataset => dataset.data),
            visible: chart.data.datasets.every((_, index) => chart.isDatasetVisible(index)),
            fills: chart.data.datasets.map(dataset => dataset.backgroundColor),
            widths: chart.data.datasets.map(dataset => dataset.borderWidth),
            pinned: [...document.querySelectorAll('[data-each-category][aria-pressed="true"]')]
              .map(button => button.dataset.eachCategory)
          };
        }"""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(
                    browser, self.live_server_url,
                    viewport={"width": 1440, "height": 960}, reduced_motion="reduce",
                )
                page = run.page
                received = []
                requests = []
                page.on(
                    "response",
                    lambda response: received.append({"payload": response.json(), "url": response.url})
                    if "/dashboard/each/chart/" in response.url and response.status == 200
                    else None,
                )
                page.on(
                    "request",
                    lambda request: requests.append(request.url),
                )
                for locale in ("en", "zh_cn", "ja"):
                    response = page.goto(
                        f"{self.live_server_url}/dashboard/each?brand=deepseek&locale={locale}&window=7&timezone=Asia%2FTokyo",
                        wait_until="networkidle",
                    )
                    self.assertEqual(response.status, 200)
                    page.evaluate("() => document.fonts.ready")
                    self._wait_for_chart(page, "sentiment")
                    self.assertEqual(page.locator('.feed-row:not([data-synthesis-status="ready"])').count(), 0)
                    tab_keys = page.locator("[data-each-tab]").evaluate_all(
                        "buttons => buttons.map(button => button.dataset.eachTab)"
                    )
                    self.assertEqual(set(tab_keys), expected_tabs)
                    for width in (1440, 390):
                        page.set_viewport_size({"width": width, "height": 960})
                        for tab in tab_keys:
                            selected_tab = page.locator('[data-each-tab][aria-selected="true"]').get_attribute('data-each-tab')
                            if selected_tab != tab:
                                with page.expect_response(lambda response, tab=tab: '/dashboard/each/chart/' in response.url and f'tab={tab}&' in response.url) as requested:
                                    page.locator(f'[data-each-tab="{tab}"]').click()
                                source = requested.value.json()
                                source_url = requested.value.url
                            else:
                                received_source = next(item for item in reversed(received) if item['payload']['tab'] == tab)
                                source = received_source['payload']
                                source_url = received_source['url']
                            self._wait_for_chart(page, tab)
                            self.assertEqual(source["tab"], tab)
                            expected_keys = [entry["key"] for entry in source["entries"]]
                            expected_labels = [entry["label"] for entry in source["entries"]]
                            for mode in ("percent", "volume"):
                                with self.subTest(locale=locale, width=width, tab=tab, mode=mode):
                                    page.locator(f'[data-each-mode="{mode}"]').check()
                                    page.mouse.move(1, 1)
                                    page.wait_for_function(
                                        """() => {
                                          const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
                                          return Math.abs(chart.width - chart.canvas.getBoundingClientRect().width) < 1 &&
                                            Math.abs(chart.height - chart.canvas.getBoundingClientRect().height) < 1;
                                        }"""
                                    )
                                    state = page.evaluate(geometry)
                                    self.assertFalse(state["chartBusy"])
                                    self.assertEqual(state["keys"], expected_keys)
                                    self.assertEqual(state["labels"], expected_labels)
                                    self.assertEqual(
                                        [item["key"] for item in state["legend"]], expected_keys[::-1]
                                    )
                                    self.assertEqual(
                                        [item["text"] for item in state["legend"]], expected_labels[::-1]
                                    )
                                    self.assertTrue(state["visible"])
                                    self.assertGreater(state["canvasWidth"], 100)
                                    self.assertLessEqual(state["pageOverflow"], 0)
                                    entries = state["legend"]
                                    self.assertGreater(len(entries), 1)
                                    for index, entry in enumerate(entries):
                                        expected_center = state["plotTop"] + index * (
                                            state["plotBottom"] - state["plotTop"]
                                        ) / (len(entries) - 1)
                                        self.assertAlmostEqual(
                                            entry["center"], expected_center, delta=1, msg=entry
                                        )
                                        self.assertFalse(entry["labelClipped"], entry)
                                        self.assertLessEqual(entry["right"], state["plotLeft"])
                                        if index:
                                            self.assertLessEqual(
                                                entries[index - 1]["bottom"], entry["top"] + 1,
                                                f"Overlapping legend labels: {entries[index - 1]} / {entry}",
                                            )
                                    if "__unclassified__" in expected_keys:
                                        self.assertEqual(entries[-1]["key"], "__unclassified__")
                                    sums = [
                                        sum(source["series"][key][index] for key in expected_keys)
                                        for index in range(len(source["days"]))
                                    ]
                                    self.assertEqual(len(sums), 7)
                                    self.assertTrue(all(total > 0 for total in sums), sums)
                                    self.assertTrue(all(
                                        sum(source["series"][key][index] > 0 for key in expected_keys) >= 2
                                        for index in range(7)
                                    ), f"A substantive multi-category area must span every day: {tab}")
                                    for index, key in enumerate(expected_keys):
                                        expected_values = [
                                            count if mode == "volume" else (count * 100 / total if total else None)
                                            for count, total in zip(source["series"][key], sums)
                                        ]
                                        self.assertEqual(state["values"][index], expected_values)

                                    # Move the actual pointer over a populated bucket, so Chart.js
                                    # creates its real tooltip through the normal interaction path.
                                    point = page.evaluate(
                                        """() => {
                                          const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
                                          const index = chart.data.labels.findIndex((_, i) =>
                                            chart.data.datasets.some(dataset => Number(dataset.data[i]) > 0));
                                          if (index < 0) return null;
                                          const rect = chart.canvas.getBoundingClientRect();
                                          return {
                                            x: rect.left + Math.max(chart.chartArea.left + 1,
                                              Math.min(chart.chartArea.right - 1, chart.scales.x.getPixelForValue(index))),
                                            y: rect.top + (chart.chartArea.top + chart.chartArea.bottom) / 2
                                          };
                                        }"""
                                    )
                                    self.assertIsNotNone(point, f"No populated tooltip bucket: {tab}")
                                    page.mouse.move(point["x"], point["y"])
                                    page.wait_for_function(
                                        """() => {
                                          const chart = Chart.getChart(document.querySelector('[data-each-canvas]'));
                                          return chart.tooltip.opacity > 0 &&
                                            chart.tooltip.dataPoints.length === chart.data.datasets.length;
                                        }"""
                                    )
                                    tooltip_keys = page.evaluate("""() => Chart.getChart(document.querySelector(
                                      '[data-each-canvas]')).tooltip.dataPoints.map(item => item.dataset.categoryKey)""")
                                    self.assertEqual(tooltip_keys, expected_keys[::-1])
                                    tooltip = page.evaluate("""() => {
                                      const tooltip = Chart.getChart(document.querySelector('[data-each-canvas]')).tooltip;
                                      return {index: tooltip.dataPoints[0].dataIndex,
                                        keys: tooltip.dataPoints.map(item => item.dataset.categoryKey),
                                        body: tooltip.body.map(item => item.lines), footer: tooltip.footer};
                                    }""")
                                    page.mouse.move(1, 1)
                                    request_count = len(requests)
                                    category = "bug" if "bug" in expected_keys else expected_keys[0]
                                    other = next(key for key in expected_keys if key != category)
                                    button = page.locator(f'[data-each-category="{category}"]')
                                    other_button = page.locator(f'[data-each-category="{other}"]')
                                    category_index = expected_keys.index(category)
                                    other_index = expected_keys.index(other)
                                    button.hover()
                                    hovered = page.evaluate(emphasis_state)
                                    self.assertTrue(hovered["fills"][category_index].endswith(",0.48)"))
                                    self.assertTrue(all(
                                        fill.endswith(",0.055)") for index, fill in enumerate(hovered["fills"])
                                        if index != category_index
                                    ))
                                    self.assertEqual(hovered["values"], state["values"])
                                    self.assertTrue(hovered["visible"])
                                    self.assertEqual(hovered["pinned"], [])
                                    page.mouse.move(1, 1)
                                    self.assertTrue(all(
                                        fill.endswith(",0.34)") for fill in page.evaluate(emphasis_state)["fills"]
                                    ))
                                    button.click()
                                    self.assertEqual(button.get_attribute("aria-pressed"), "true")
                                    other_button.hover()
                                    self.assertEqual(page.evaluate(emphasis_state)["widths"][other_index], 2.7)
                                    page.mouse.move(1, 1)
                                    self.assertEqual(page.evaluate(emphasis_state)["widths"][category_index], 2.7)
                                    redraw_mode = "volume" if mode == "percent" else "percent"
                                    page.locator(f'[data-each-mode="{redraw_mode}"]').check()
                                    self.assertEqual(button.get_attribute("aria-pressed"), "true")
                                    page.locator(f'[data-each-mode="{mode}"]').check()
                                    self.assertEqual(button.get_attribute("aria-pressed"), "true")
                                    button.click()
                                    self.assertEqual(button.get_attribute("aria-pressed"), "false")
                                    button.focus()
                                    button.press("Enter")
                                    self.assertTrue(button.evaluate("el => el.matches(':focus-visible')"))
                                    self.assertEqual(button.get_attribute("aria-pressed"), "true")
                                    button.press("Space")
                                    self.assertEqual(button.get_attribute("aria-pressed"), "false")
                                    page.mouse.move(1, 1)
                                    final = page.evaluate(emphasis_state)
                                    self.assertEqual(final["values"], state["values"])
                                    self.assertTrue(final["visible"])
                                    self.assertTrue(all(fill.endswith(",0.34)") for fill in final["fills"]))
                                    self.assertEqual(len(requests), request_count, requests[request_count:])
                                    # Save measured DOM/chart snapshots after real actions. The
                                    # separate Each adapter derives obligations from these traces.
                                    case = {
                                        "locale": locale, "width": width, "tab": tab, "mode": mode,
                                        "url": page.url, "source": source, "source_url": source_url, "geometry": state,
                                        "tooltip_keys": tooltip_keys, "tooltip": tooltip,
                                        "request_count": request_count, "traces": [],
                                    }
                                    def observe(category=category, other=other):
                                        observed = page.evaluate(emphasis_state)
                                        controls = page.evaluate("""() => ({
                                          pin: document.querySelector('[data-each-category][aria-pressed="true"]')?.dataset.eachCategory || null,
                                          hover: [...document.querySelectorAll('[data-each-category]')].find(el => el.matches(':hover'))?.dataset.eachCategory || null,
                                          mode: document.querySelector('[data-each-mode]:checked').dataset.eachMode
                                        })""")
                                        aliases = {None: "none", category: "first", other: "other"}
                                        observed["controls"] = {
                                            "pin": aliases[controls["pin"]],
                                            "hover": aliases[controls["hover"]],
                                            "mode": controls["mode"],
                                        }
                                        observed["request_count"] = len(requests)
                                        return observed

                                    def move_hover(value, button=button, other_button=other_button):
                                        # Re-enter after click/redraw even when the pointer's
                                        # previous coordinates already fall on this button.
                                        page.mouse.move(1, 1)
                                        if value != "none":
                                            (button if value == "first" else other_button).hover()

                                    def apply(action, button=button, other_button=other_button,
                                              observe=observe, move_hover=move_hover):
                                        control, value = action.split(":", 1)
                                        before = observe()["controls"]
                                        if control == "hover":
                                            move_hover(value)
                                        elif control == "pin":
                                            page.mouse.move(1, 1)
                                            if before["pin"] != value:
                                                selected = before["pin"] if value == "none" else value
                                                (button if selected == "first" else other_button).click()
                                            elif value == "none":
                                                button.click()
                                                button.click()
                                            else:
                                                chosen = button if value == "first" else other_button
                                                chosen.click()
                                                chosen.click()
                                            move_hover(before["hover"])
                                        elif control == "mode":
                                            page.locator(f'[data-each-mode="{value}"]').check()
                                            move_hover(before["hover"])
                                        else:
                                            raise AssertionError(action)
                                        return {"action": action, "observed": observe()}

                                    trace = {"initial": observe(), "steps": []}
                                    for pin in ("none", "first", "other"):
                                        trace["steps"].append(apply(f"pin:{pin}"))
                                        for hover in ("none", "first", "other"):
                                            trace["steps"].append(apply(f"hover:{hover}"))
                                    for action in ("hover:none", "pin:none", "pin:first",
                                                   f"mode:{redraw_mode}", f"mode:{mode}", "pin:none"):
                                        trace["steps"].append(apply(action))
                                    case["traces"].append(trace)
                                    if not packet["cases"]:
                                        for actions in permutations(("pin:first", "hover:other", "hover:none")):
                                            apply("hover:none")
                                            apply("pin:none")
                                            ordered = {"initial": observe(), "steps": []}
                                            for action in actions:
                                                ordered["steps"].append(apply(action))
                                            case["traces"].append(ordered)
                                    apply("hover:none")
                                    apply("pin:none")
                                    packet["cases"].append(case)
                                    if locale == "en" and tab == "product_labels" and mode == "percent":
                                        page.locator("[data-pw-each-chart]").screenshot(
                                            path=str(output / f"dashboard-each-b-left-legend-{width}.png"),
                                        )
                                        button.hover()
                                        page.locator("[data-pw-each-chart]").screenshot(
                                            path=str(output / f"dashboard-each-b-bug-emphasis-{width}.png"),
                                        )
                                        page.mouse.move(1, 1)
                self.assertEqual(run.errors, [])
                self.assertEqual(run.external, [])
                packet["errors"] = list(run.errors)
                packet["external"] = list(run.external)
                write_each_runtime(declaration, packet)
                run.context.close()
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
