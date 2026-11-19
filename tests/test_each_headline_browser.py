"""Real rendered Each headline fragments survive delayed and failed responses.

Requests go through the live URL/view/partial. Only their delivery order and
status are controlled. For stale-response cases, the headline transport ignores
abort so the application's generation guard must protect the real DOM itself.
"""
from __future__ import annotations

from contextlib import contextmanager
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from monitor.views import _clear_home_pulse_cache
from tests.general_style_browser import open_page
from tests.test_chart_harvest_coverage import record_harvest
from tests.v22_support import fixture_from_oracle, seed_real_home_orm

pytestmark = pytest.mark.requires_postgres
HEADLINE_PATH = "/api/v2/dashboard/each/headline/"

# Preserve real fetch/Response/JSON behavior and real endpoint rendering while
# simulating a transport whose already-issued response cannot be cancelled.
# Chart requests retain their normal AbortController behavior.
HEADLINE_TRANSPORT = """(() => {
  const original = window.fetch.bind(window);
  window.__eachHeadlineSignals = [];
  window.fetch = function(input, options) {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.pathname !== '/api/v2/dashboard/each/headline/') return original(input, options);
    const record = {brand: url.searchParams.get('brand'), signal: options.signal,
      received: false, bodyRead: false, ok: false, failed: false};
    window.__eachHeadlineSignals.push(record);
    const transportOptions = Object.assign({}, options);
    if (__IGNORE_ABORT__) delete transportOptions.signal;
    return original(input, transportOptions).then(response => {
      record.received = true;
      record.ok = response.ok;
      const read = response.json.bind(response);
      response.json = function() {
        return read().then(body => { record.bodyRead = true; return body; });
      };
      return response;
    }, error => { record.failed = true; throw error; });
  };
})();
"""


def saved_narrative(_window_days, *, selected_brand_keys, **_kwargs):
    """Deterministic saved data, rendered by the application's real partial."""
    brand = selected_brand_keys[0]
    return {
        "schema_version": 3, "window_days": 7,
        "computed_at": timezone.now().isoformat(), "state_label": "Saved fixture",
        "selection": {}, "items": [{
            "brand": {"key": brand, "display_name": brand, "url": ""},
            "state": "ready", "state_label": "Saved fixture", "freshness": {},
            "headline": f"Saved headline for {brand}",
            "secondary": f"Saved detail for {brand}",
        }],
    }


class PendingHeadlines:
    def __init__(self, page):
        self.page = page
        self.pending = []
        page.route(f"**{HEADLINE_PATH}?*", self.hold)

    def hold(self, route):
        # This reaches the actual Django narrow endpoint, including its identity
        # envelope and shared headline partial, before delaying delivery to JS.
        response = route.fetch()
        assert response.status == 200
        body = response.json()
        query = parse_qs(urlparse(route.request.url).query)
        assert body["brand"] == query["brand"][0]
        assert body["window_days"] == 7 and body["locale"] == "en"
        assert "data-pw-headline" in body["html"]
        self.pending.append({"route": route, "response": response, "body": body})

    def wait(self, total):
        # Pump Playwright events without a wall-clock sleep or a second browser.
        expect(self.page.locator("[data-pw-headline-status]")).to_be_visible()
        self.page.wait_for_function("() => true")
        deadline = monotonic() + 5
        while monotonic() < deadline:
            if len(self.pending) == total:
                return self.pending[-1]
            self.page.wait_for_timeout(10)
        raise AssertionError(f"Expected {total} narrow requests, observed {len(self.pending)}")

    def deliver(self, index, *, status=200):
        request = self.pending[index]
        if status == 200:
            request["route"].fulfill(response=request["response"])
        else:
            request["route"].fulfill(status=status, json={"error": "controlled-headline-failure"})
        # Wait until the actual fetch/JSON chain consumed this particular
        # response. An immediate unchanged-DOM assertion could otherwise pass
        # before the obsolete success/failure reached the application handler.
        self.page.wait_for_function("""index => {
          const record = window.__eachHeadlineSignals[index];
          return record && record.received && (!record.ok || record.bodyRead);
        }""", arg=index)
        self.page.evaluate("() => new Promise(resolve => queueMicrotask(resolve))")


@override_settings(SECURE_SSL_REDIRECT=False)
class EachHeadlineRaceBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        seed_real_home_orm(fixture_from_oracle())
        now = timezone.now()
        record_harvest(now, finished_at=now, staggered=False)
        _clear_home_pulse_cache()
        self.headline_projection = patch(
            "monitor.each_headline.project_trend_narrative", side_effect=saved_narrative,
        )
        self.headline_config = patch(
            "monitor.each_headline.load_config", return_value=SimpleNamespace(
                headline_narrative=SimpleNamespace(demand_shaping_enabled=False)),
        )
        self.headline_projection.start()
        self.headline_config.start()
        self.addCleanup(self.headline_projection.stop)
        self.addCleanup(self.headline_config.stop)

    @contextmanager
    def page(self, *, ignore_abort=False, controlled_clock=False):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            run = open_page(browser, self.live_server_url, reduced_motion="reduce")
            page = run.page
            documents = []
            page.on("request", lambda request: documents.append(request.url)
                    if request.resource_type == "document" else None)
            page.add_init_script(HEADLINE_TRANSPORT.replace(
                "__IGNORE_ABORT__", "true" if ignore_abort else "false"))
            if controlled_clock:
                page.clock.install(time=timezone.now())
            try:
                response = page.goto(
                    f"{self.live_server_url}/dashboard/each?brand=deepseek&locale=en&window=7",
                    wait_until="networkidle",
                )
                self.assertIsNotNone(response)
                self.assertEqual(response.status, 200)
                self.wait_chart(page, "deepseek", "sentiment")
                self.assert_headline(page, "deepseek", notice_visible=False)
                pending = PendingHeadlines(page)
                yield page, pending
                self.assertEqual(documents, [response.url], "A narrow refresh requested another full page")
                self.assertEqual(run.errors, [])
                self.assertEqual(run.external, [])
            finally:
                run.context.close()
                browser.close()

    def wait_chart(self, page, brand, tab):
        page.wait_for_function("""({brand, tab}) => {
          const root = document.querySelector('[data-pw-each-chart]');
          const canvas = root.querySelector('[data-each-canvas]');
          const chart = window.Chart && Chart.getChart(canvas);
          return chart && root.dataset.selectedBrand === brand && root.dataset.committedTab === tab &&
            !root.querySelector('.each-chart-panel').hasAttribute('aria-busy') &&
            !root.querySelector('.each-chart-face').classList.contains('is-turning-in') &&
            !root.querySelector('.each-chart-face').classList.contains('is-turning-out');
        }""", arg={"brand": brand, "tab": tab})

    def select(self, page, brand):
        control = page.locator(f'[data-pw-pulse-entry="{brand}"]')
        expect(control).to_have_count(1)
        control.click()
        expect(control).to_have_attribute("aria-pressed", "true")

    def assert_headline(self, page, brand, *, notice_visible):
        expect(page.locator("[data-pw-headline]")).to_have_count(1)
        expect(page.locator("[data-pw-headline-item]")).to_have_count(1)
        expect(page.locator("[data-pw-headline-item]")).to_have_attribute("data-pw-brand-key", brand)
        expect(page.locator("[data-pw-headline-item-title]")).to_contain_text(f"Saved headline for {brand}")
        notice = page.locator("[data-pw-headline-status]")
        if notice_visible:
            expect(notice).to_be_visible()
        else:
            expect(notice).to_be_hidden()
            expect(notice).to_have_text("")

    def assert_old_notice(self, page, brand, *, failed=False):
        notice = page.locator("[data-pw-headline-status]")
        expect(notice).to_be_visible()
        name = {"deepseek": "DeepSeek", "qwen": "Qwen", "minimax": "MiniMax"}[brand]
        expect(notice).to_contain_text(f"Showing previous result ({name}, 7d)")
        expect(notice).to_contain_text("Headline refresh failed" if failed else "Loading")

    def test_latest_success_survives_out_of_order_success_and_tab_change_while_pending(self):
        with self.page(ignore_abort=True) as (page, pending):
            self.select(page, "minimax")
            pending.wait(1)
            self.select(page, "qwen")
            pending.wait(2)
            self.assert_headline(page, "deepseek", notice_visible=True)
            self.assert_old_notice(page, "deepseek")
            self.assertTrue(page.evaluate("() => window.__eachHeadlineSignals[0].signal.aborted"))

            page.locator('[data-each-tab="lang"]').click()
            self.wait_chart(page, "qwen", "lang")
            self.assertEqual(len(pending.pending), 2, "A chart tab requested another headline")
            self.assert_headline(page, "deepseek", notice_visible=True)
            self.assert_old_notice(page, "deepseek")

            pending.deliver(1)
            self.assert_headline(page, "qwen", notice_visible=False)
            pending.deliver(0)
            self.assert_headline(page, "qwen", notice_visible=False)
            self.wait_chart(page, "qwen", "lang")
            self.assertEqual(len(pending.pending), 2)

    def test_obsolete_failure_is_ignored_and_current_failure_retains_latest_saved_fragment(self):
        with self.page(ignore_abort=True) as (page, pending):
            self.select(page, "minimax")
            pending.wait(1)
            self.select(page, "qwen")
            pending.wait(2)
            pending.deliver(1)
            self.assert_headline(page, "qwen", notice_visible=False)
            self.assertTrue(page.evaluate("() => window.__eachHeadlineSignals[0].signal.aborted"))
            pending.deliver(0, status=503)
            self.assert_headline(page, "qwen", notice_visible=False)

            self.select(page, "deepseek")
            pending.wait(3)
            pending.deliver(2, status=503)
            self.assert_headline(page, "qwen", notice_visible=True)
            self.assert_old_notice(page, "qwen", failed=True)
            self.wait_chart(page, "deepseek", "sentiment")
            self.assertEqual(len(pending.pending), 3)

    def test_timeout_retains_saved_fragment_and_new_selection_recovers(self):
        with self.page(controlled_clock=True) as (page, pending):
            self.select(page, "minimax")
            pending.wait(1)
            pending.deliver(0)
            self.assert_headline(page, "minimax", notice_visible=False)
            self.wait_chart(page, "minimax", "sentiment")

            self.select(page, "qwen")
            pending.wait(2)
            self.wait_chart(page, "qwen", "sentiment")
            page.clock.fast_forward(4001)
            self.assert_headline(page, "minimax", notice_visible=True)
            self.assert_old_notice(page, "minimax", failed=True)

            self.select(page, "deepseek")
            pending.wait(3)
            pending.deliver(2)
            self.assert_headline(page, "deepseek", notice_visible=False)
            self.wait_chart(page, "deepseek", "sentiment")
            self.assertEqual(len(pending.pending), 3)
