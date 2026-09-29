"""Real route, template, assets, and browser interaction for the each dashboard."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright

from monitor.views import _clear_home_pulse_cache
from tests.ui_assurance.local_preview import load_pinned_assets
from tests.v22_support import fixture_from_oracle, seed_real_home_orm

pytestmark = pytest.mark.requires_postgres


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardEachBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        seed_real_home_orm(fixture_from_oracle())
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
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(
                    f"{self.live_server_url}/dashboard/each?brand=minimax&locale=en",
                    wait_until="networkidle",
                )
                self.assertEqual(response.status, 200)
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
                self.assertEqual(
                    page.locator('[data-each-tab="post_types"]').get_attribute("aria-selected"),
                    "true",
                )
                self.assertEqual(
                    page.locator('[data-pw-pulse-entry][aria-pressed="true"]').get_attribute("data-pw-pulse-entry"),
                    "qwen",
                )
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
