"""Real browser proof for exact fixture-only ping-delay serialization.

This never replaces metrics or the content-shape guard. It uses the real home
route through the opted-in loopback proxy and measures raw document shape.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import Error, expect, sync_playwright

from monitor.views import _clear_home_pulse_cache
from tests.each_performance_fixture import seed_each_performance_orm
from tests.test_each_performance_fixture import require_task_test_database
from tests.ui_assurance.local_preview import LocalPreviewServer, load_pinned_assets

pytestmark = pytest.mark.requires_postgres
BOOTSTRAP = Path(__file__).parent / "fixtures/performance_assurance/ping-delay-bootstrap.js"


@override_settings(SECURE_SSL_REDIRECT=False)
class PerformanceBootstrapBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        require_task_test_database()
        anchor = seed_each_performance_orm()
        clock = patch("django.utils.timezone.now", return_value=anchor)
        clock.start()
        self.addCleanup(clock.stop)
        _clear_home_pulse_cache()

    @contextmanager
    def page(self):
        with LocalPreviewServer(
            assets=load_pinned_assets(),
            upstream_origin=self.live_server_url.replace("localhost", "127.0.0.1"),
            port=0, fixture_bootstrap=BOOTSTRAP.read_bytes(),
        ) as preview, sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(
                viewport={"width": 1440, "height": 960},
                timezone_id="Asia/Tokyo", reduced_motion="no-preference",
            )
            page = context.new_page()
            page.add_init_script("""window.__nativeStyleSetProperty = CSSStyleDeclaration.prototype.setProperty;
              window.__nativePerformanceNow = performance.now;
              window.__nativeSetPropertyDescriptor = Object.getOwnPropertyDescriptor(CSSStyleDeclaration.prototype, 'setProperty');""")
            try:
                self.navigate(page, preview.origin)
                yield page, preview.origin
            finally:
                context.close()
                browser.close()

    def navigate(self, page, origin):
        response = page.goto(origin + "/?locale=en", wait_until="networkidle")
        self.assertIsNotNone(response)
        self.assertEqual(response.status, 200)
        page.evaluate("() => document.fonts.ready")
        page.wait_for_function("""() => {
          const canvas = document.querySelector('[data-pw-chart] canvas.home-chart');
          return canvas && window.Chart && Chart.getChart(canvas) &&
            document.querySelectorAll('[data-pw-chart-legend] [data-pw-chart-brand]').length > 1;
        }""")
        expect(page.locator("[data-pw-performance-fixture-bootstrap]")).to_have_count(1)
        self.assertTrue(page.evaluate("""() => [...document.querySelectorAll(
          '[data-pw-chart-legend] [data-pw-chart-brand]')].every(button =>
            button.style.getPropertyValue('--pw-ping-delay').length === 42)"""))

    def test_exact_numbers_native_css_animation_and_raw_shape_are_preserved(self):
        with self.page() as (page, _origin):
            legend = page.locator('[data-pw-chart-legend] [data-pw-chart-brand]').first
            legend.hover()
            result = page.evaluate("""async () => {
              const button = document.querySelector('[data-pw-chart-legend] [data-pw-chart-brand]');
              const ping = button.querySelector('.pw-swatch-ping');
              const native = window.__nativeStyleSetProperty;
              const style = button.style;
              const samples = ['-257.3000000715256ms', '-246.20000004768372ms', '-0ms', '0ms',
                '+0ms', '-0.000ms', '-2.25e3ms', '-2250ms', '-1.125e+2ms', '-.25ms'];
              const checks = samples.map(value => {
                const nativeReturn = native.call(style, '--pw-ping-delay', value, 'important');
                const expected = getComputedStyle(ping).animationDelay;
                const wrappedReturn = style.setProperty('--pw-ping-delay', value, 'important');
                const padded = style.getPropertyValue('--pw-ping-delay');
                return {value, expected, actual: getComputedStyle(ping).animationDelay,
                  priority: style.getPropertyPriority('--pw-ping-delay'),
                  equalNumber: Object.is(Number(padded.slice(0, -2)), Number(value.slice(0, -2))),
                  length: padded.length, sameReturn: nativeReturn === wrappedReturn,
                  exactSuffix: padded.endsWith(value.replace(/^[+-]?/, ''))};
              });
              const other = document.createElement('div').style;
              const delegated = ['important', ''].map(priority => {
                const before = native.call(other, '--ordinary-property', 'unchanged-value', priority);
                const expected = [other.getPropertyValue('--ordinary-property'), other.getPropertyPriority('--ordinary-property')];
                const after = CSSStyleDeclaration.prototype.setProperty.call(other, '--ordinary-property', 'unchanged-value', priority);
                return {same: JSON.stringify(expected) === JSON.stringify([
                  other.getPropertyValue('--ordinary-property'), other.getPropertyPriority('--ordinary-property')]),
                  sameReturn: before === after};
              });
              const originalDescriptor = window.__nativeSetPropertyDescriptor;
              const descriptor = Object.getOwnPropertyDescriptor(CSSStyleDeclaration.prototype, 'setProperty');
              const sameDescriptor = ['writable', 'enumerable', 'configurable'].every(key => originalDescriptor[key] === descriptor[key]);
              const animation = ping.getAnimations().find(item => item.animationName === 'pw-ping');
              if (!animation) throw new Error('Real CSS ping animation is missing');
              const animationBefore = animation.currentTime;
              const clockBefore = performance.now();
              await new Promise(resolve => setTimeout(resolve, 120));
              const animationAfter = animation.currentTime;
              const clockAfter = performance.now();
              const shape = () => ({dom: document.querySelectorAll('*').length,
                bytes: new TextEncoder().encode(document.documentElement.outerHTML).byteLength});
              style.setProperty('--pw-ping-delay', '-257.3000000715256ms');
              const shortLexeme = shape();
              style.setProperty('--pw-ping-delay', '-246.20000004768372ms');
              const longLexeme = shape();
              const paragraph = document.createElement('p');
              paragraph.textContent = 'Visible content mutation remains measurable.';
              document.body.appendChild(paragraph);
              const addedElement = shape();
              paragraph.firstChild.appendData(' More visible text.');
              const addedText = shape();
              return {checks, delegated, sameDescriptor, clockBefore, clockAfter,
                sameClock: performance.now === window.__nativePerformanceNow,
                animationBefore, animationAfter, shortLexeme, longLexeme, addedElement, addedText,
                visible: paragraph.getBoundingClientRect().width > 0 && paragraph.getBoundingClientRect().height > 0};
            }""")
            for item in result["checks"]:
                self.assertEqual(item["actual"], item["expected"], item)
                self.assertEqual(item["priority"], "important")
                self.assertTrue(item["equalNumber"], item)
                self.assertEqual(item["length"], 42)
                self.assertTrue(item["sameReturn"], item)
                self.assertTrue(item["exactSuffix"], item)
            self.assertTrue(all(item["same"] and item["sameReturn"] for item in result["delegated"]))
            self.assertTrue(result["sameDescriptor"])
            self.assertTrue(result["sameClock"])
            self.assertGreater(result["clockAfter"], result["clockBefore"])
            self.assertGreater(result["animationAfter"], result["animationBefore"])
            self.assertEqual(result["shortLexeme"], result["longLexeme"])
            self.assertGreater(result["addedElement"]["dom"], result["longLexeme"]["dom"])
            self.assertGreater(result["addedElement"]["bytes"], result["longLexeme"]["bytes"])
            self.assertEqual(result["addedText"]["dom"], result["addedElement"]["dom"])
            self.assertGreater(result["addedText"]["bytes"], result["addedElement"]["bytes"])
            self.assertTrue(result["visible"])

    def test_invalid_shape_oversize_and_out_of_range_destroy_the_preview_and_throw(self):
        with self.page() as (page, origin):
            for value in ("auto", "-1s", "1ms", "-2250.0001ms", "-1e309ms", "-" + "0" * 40 + "ms"):
                with self.subTest(value=value):
                    with pytest.raises(Error, match="Fixture ping delay rejected"):
                        page.evaluate("""value => document.querySelector('[data-pw-chart-legend] [data-pw-chart-brand]')
                          .style.setProperty('--pw-ping-delay', value)""", value)
                    self.assertEqual(page.locator("html").count(), 0)
                    self.assertEqual(page.locator(".follower-magnitude.pw-inspection-trigger").count(), 0)
                    self.navigate(page, origin)
