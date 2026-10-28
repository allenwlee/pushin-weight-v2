"""Brand focus, pinning, touch taps, count labels and beacons on the homepage chart.

The canvas drawing calls are recorded during one ``chart.draw()`` so the tests
can read what was painted (line alpha, label text, beacon positions, any
tooltip box) instead of guessing from pixels.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from playwright.sync_api import Page, sync_playwright

from core.models import Post, PostBrand
from monitor.views import _clear_home_pulse_cache

from tests.general_style_browser import (
    DESKTOP,
    PHONE,
    goto_home,
    open_page,
    seed_general_style_home,
)

pytestmark = pytest.mark.requires_postgres

# In-page helpers: chart geometry, recorded drawing calls and focus state.
PAGE_HELPERS = r"""
window.__pwTest = {
  chart() {
    return Chart.getChart(document.querySelector('[data-pw-chart] canvas.home-chart'));
  },
  brandOf(dataset) {
    const match = /^([a-z0-9_]+)/i.exec(String(dataset.label || ''));
    return match ? match[1].toLowerCase() : null;
  },
  lines() {
    const chart = this.chart();
    return chart.data.datasets.map((dataset, index) => ({dataset, index}))
      .filter(({dataset, index}) => dataset._isTotalLine && chart.isDatasetVisible(index))
      .map(({dataset, index}) => ({
        brand: this.brandOf(dataset),
        color: String(dataset.borderColor).toLowerCase(),
        index,
        points: chart.getDatasetMeta(index).data
          .filter((p) => p && !p.skip && Number.isFinite(p.x) && Number.isFinite(p.y))
          .map((p) => ({x: p.x, y: p.y})),
      }));
  },
  distanceToLine(points, x, y) {
    let best = Infinity;
    for (let j = 0; j < points.length; j++) {
      const a = points[j], b = points[j + 1] || a;
      const vx = b.x - a.x, vy = b.y - a.y, length = vx * vx + vy * vy;
      const t = length ? Math.max(0, Math.min(1, ((x - a.x) * vx + (y - a.y) * vy) / length)) : 0;
      best = Math.min(best, Math.hypot(a.x + t * vx - x, a.y + t * vy - y));
    }
    return best;
  },
  // A segment of one line whose 5px and 12px offsets sit far from every other line.
  isolatedSegment() {
    const lines = this.lines();
    const area = this.chart().chartArea;
    let best = null;
    for (const line of lines) {
      for (let j = 0; j + 1 < line.points.length; j++) {
        const a = line.points[j], b = line.points[j + 1];
        const length = Math.hypot(b.x - a.x, b.y - a.y);
        if (length < 8) continue;
        const mid = {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
        for (const sign of [1, -1]) {
          const normal = {x: sign * -(b.y - a.y) / length, y: sign * (b.x - a.x) / length};
          const far = {x: mid.x + normal.x * 12, y: mid.y + normal.y * 12};
          if (far.y < area.top + 2 || far.y > area.bottom - 2) continue;
          const clearance = Math.min(...lines.filter((other) => other.brand !== line.brand)
            .map((other) => Math.min(
              this.distanceToLine(other.points, mid.x, mid.y),
              this.distanceToLine(other.points, far.x, far.y))));
          const ownFar = this.distanceToLine(line.points, far.x, far.y);
          if (ownFar < 10) continue;
          if (!best || clearance > best.clearance) best = {brand: line.brand, mid, normal, clearance};
        }
      }
    }
    return best;
  },
  // A point inside the plot area at least 24px from every line.
  blankPoint() {
    const area = this.chart().chartArea;
    const lines = this.lines();
    for (let y = area.top + 6; y < area.bottom; y += 6) {
      for (let x = area.left + 6; x < area.right; x += 6) {
        if (lines.every((line) => this.distanceToLine(line.points, x, y) > 24)) return {x, y};
      }
    }
    return null;
  },
  canvasOrigin() {
    const rect = this.chart().canvas.getBoundingClientRect();
    return {x: rect.left, y: rect.top};
  },
  record() {
    const chart = this.chart();
    const ctx = chart.ctx;
    const calls = {strokes: [], fills: [], texts: []};
    let path = [];
    const wrap = (name, handler) => {
      const original = ctx[name];
      ctx[name] = function (...args) { handler(args); return original.apply(this, args); };
      return () => { ctx[name] = original; };
    };
    const restores = [
      wrap('beginPath', () => { path = []; }),
      wrap('moveTo', ([x, y]) => path.push({x, y})),
      wrap('lineTo', ([x, y]) => path.push({x, y})),
      wrap('arc', ([x, y]) => path.push({x, y})),
      wrap('stroke', () => calls.strokes.push({
        style: String(ctx.strokeStyle).toLowerCase(), alpha: ctx.globalAlpha, dash: ctx.getLineDash(),
      })),
      wrap('fill', () => {
        const xs = path.map((p) => p.x), ys = path.map((p) => p.y);
        calls.fills.push({
          style: String(ctx.fillStyle).toLowerCase(), alpha: ctx.globalAlpha,
          center: path.length
            ? {x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2}
            : null,
        });
      }),
      wrap('fillText', ([text, x, y]) => calls.texts.push({
        text: String(text), x, y, style: String(ctx.fillStyle).toLowerCase(),
        width: ctx.measureText(String(text)).width,
      })),
    ];
    try { chart.draw(); } finally { restores.forEach((restore) => restore()); }
    return calls;
  },
  legendState() {
    // Settle the legend's opacity transitions before reading computed values.
    document.getAnimations().forEach((animation) => {
      if (animation.transitionProperty) animation.finish();
    });
    return [...document.querySelectorAll('[data-pw-chart] [data-pw-chart-legend] [data-pw-chart-brand]')]
      .map((button) => ({
        brand: button.dataset.pwChartBrand,
        focus: button.classList.contains('pw-legend-focus'),
        dim: button.classList.contains('pw-legend-dim'),
        pressed: button.getAttribute('aria-pressed'),
        opacity: getComputedStyle(button).opacity,
        weight: getComputedStyle(button).fontWeight,
      }));
  },
  focused() {
    const focused = this.legendState().filter((entry) => entry.focus);
    return focused.length ? focused[0].brand : null;
  },
  pinned() {
    const pinned = this.legendState().filter((entry) => entry.pressed === 'true');
    return pinned.length ? pinned[0].brand : null;
  },
};
"""


def _install_helpers(page: Page) -> None:
    page.evaluate(PAGE_HELPERS)


def _line_alphas(page: Page) -> dict[str, list[float]]:
    """Stroke alpha per brand color from one recorded draw."""
    return page.evaluate(
        """() => {
          const colors = Object.fromEntries(__pwTest.lines().map((line) => [line.color, line.brand]));
          const result = {};
          for (const stroke of __pwTest.record().strokes) {
            const brand = colors[stroke.style];
            if (brand) (result[brand] = result[brand] || []).push(stroke.alpha);
          }
          return result;
        }"""
    )


def _assert_focus_painted(test: StaticLiveServerTestCase, page: Page, brand: str) -> None:
    alphas = _line_alphas(page)
    test.assertTrue(alphas, "no brand line strokes were recorded")
    for other, values in alphas.items():
        expected = 1 if other == brand else 0.24
        test.assertTrue(
            all(abs(value - expected) < 0.01 for value in values),
            f"{other} drew at {values}, expected {expected} while {brand} is focused",
        )
    legend = page.evaluate("() => __pwTest.legendState()")
    for entry in legend:
        if entry["brand"] == brand:
            test.assertTrue(entry["focus"])
            test.assertEqual(entry["opacity"], "1")
            test.assertGreaterEqual(int(entry["weight"]), 600)
        else:
            test.assertTrue(entry["dim"], entry)
            test.assertEqual(entry["opacity"], "0.56")


def _assert_idle(test: StaticLiveServerTestCase, page: Page) -> None:
    for brand, values in _line_alphas(page).items():
        test.assertTrue(all(abs(value - 1) < 0.01 for value in values), (brand, values))
    for entry in page.evaluate("() => __pwTest.legendState()"):
        test.assertFalse(entry["focus"] or entry["dim"], entry)


@override_settings(SECURE_SSL_REDIRECT=False)
class HomeChartFocusBrowserTests(StaticLiveServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        seed_general_style_home(self)
        # The fixture's lines all sit on zero before today; give Qwen a distinct
        # zig-zag on earlier days so a pointer can land near one line only.
        now = timezone.now()
        for days_ago, count in ((4, 10), (3, 3), (2, 8)):
            for index in range(count):
                post = Post.objects.create(
                    tweet_id=f"focus-qwen-{days_ago}-{index}",
                    text="Qwen focus evidence",
                    created_at=now - timedelta(days=days_ago, minutes=index),
                )
                PostBrand.objects.create(post=post, brand_id="qwen")
        _clear_home_pulse_cache()

    def _mouse_to(self, page: Page, point: dict[str, float]) -> None:
        origin = page.evaluate("() => __pwTest.canvasOrigin()")
        page.mouse.move(origin["x"] + point["x"], origin["y"] + point["y"])

    def test_hover_keyboard_and_pinned_click_focus_one_brand(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                page = run.page
                goto_home(run, self.live_server_url, "locale=en&window=7")
                _install_helpers(page)
                self.assertIs(
                    page.evaluate("() => __pwTest.chart().options.plugins.tooltip.enabled"),
                    False,
                )
                _assert_idle(self, page)
                legend = page.locator("[data-pw-chart] [data-pw-chart-legend] [data-pw-chart-brand]")
                brands = legend.evaluate_all("buttons => buttons.map(b => b.dataset.pwChartBrand)")
                self.assertGreaterEqual(len(brands), 3)
                first, second = brands[0], brands[1]

                # Legend hover focuses; the counts draw in the line color.
                legend.nth(0).hover()
                _assert_focus_painted(self, page, first)
                texts = page.evaluate(
                    """brand => {
                      const line = __pwTest.lines().find((entry) => entry.brand === brand);
                      return {color: line.color, points: line.points.length,
                              texts: __pwTest.record().texts.filter((t) => t.style === line.color)};
                    }""",
                    first,
                )
                self.assertTrue(texts["texts"], "focused brand drew no count labels")
                self.assertTrue(all(t["text"].isdigit() for t in texts["texts"]))
                # Seven daily points are far apart, so every point carries a label.
                self.assertEqual(len(texts["texts"]), texts["points"])
                page.mouse.move(2, 2)
                _assert_idle(self, page)

                # Within 8px of a line (between points) focuses it; 12px away does not.
                segment = page.evaluate("() => __pwTest.isolatedSegment()")
                self.assertIsNotNone(segment)
                self.assertGreater(segment["clearance"], 16, segment)
                near = {
                    "x": segment["mid"]["x"] + segment["normal"]["x"] * 5,
                    "y": segment["mid"]["y"] + segment["normal"]["y"] * 5,
                }
                far = {
                    "x": segment["mid"]["x"] + segment["normal"]["x"] * 12,
                    "y": segment["mid"]["y"] + segment["normal"]["y"] * 12,
                }
                self._mouse_to(page, near)
                self.assertEqual(page.evaluate("() => __pwTest.focused()"), segment["brand"])
                _assert_focus_painted(self, page, segment["brand"])
                self._mouse_to(page, far)
                self.assertIsNone(page.evaluate("() => __pwTest.focused()"))

                # Keyboard: focus previews, Enter pins, Space unpins, Escape releases.
                legend.nth(1).focus()
                self.assertEqual(page.evaluate("() => __pwTest.focused()"), second)
                page.keyboard.press("Enter")
                self.assertEqual(page.evaluate("() => __pwTest.pinned()"), second)
                page.keyboard.press("Space")
                self.assertIsNone(page.evaluate("() => __pwTest.pinned()"))
                page.keyboard.press("Enter")
                self.assertEqual(page.evaluate("() => __pwTest.pinned()"), second)
                page.keyboard.press("Escape")
                self.assertIsNone(page.evaluate("() => __pwTest.pinned()"))
                # Tab moves the preview to the next entry; leaving the legend clears it.
                page.keyboard.press("Tab")
                self.assertEqual(page.evaluate("() => __pwTest.focused()"), brands[2])
                page.mouse.move(2, 2)
                page.locator('[data-pw-window-btn="7"]').focus()
                self.assertIsNone(page.evaluate("() => __pwTest.focused()"))
                _assert_idle(self, page)

                # Desktop click pins; hover previews another brand, then the pin returns.
                legend.nth(0).click()
                page.mouse.move(2, 2)
                self.assertEqual(page.evaluate("() => __pwTest.pinned()"), first)
                _assert_focus_painted(self, page, first)
                legend.nth(1).hover()
                self.assertEqual(page.evaluate("() => __pwTest.focused()"), second)
                page.mouse.move(2, 2)
                self.assertEqual(page.evaluate("() => __pwTest.focused()"), first)

                # A click on blank plot area releases the pin.
                blank = page.evaluate("() => __pwTest.blankPoint()")
                self.assertIsNotNone(blank)
                origin = page.evaluate("() => __pwTest.canvasOrigin()")
                page.mouse.click(origin["x"] + blank["x"], origin["y"] + blank["y"])
                self.assertIsNone(page.evaluate("() => __pwTest.pinned()"))
                _assert_idle(self, page)

                # A click on blank page area outside the chart releases it too.
                legend.nth(0).click()
                self.assertEqual(page.evaluate("() => __pwTest.pinned()"), first)
                page.locator("#pw-activity-head").click()
                self.assertIsNone(page.evaluate("() => __pwTest.pinned()"))
                self.assertEqual(run.errors, [])
                run.context.close()
            finally:
                browser.close()

    def test_pin_survives_refresh_and_clears_when_a_filter_removes_the_brand(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                page = run.page
                goto_home(run, self.live_server_url, "locale=en&window=7")
                _install_helpers(page)
                legend = page.locator("[data-pw-chart] [data-pw-chart-legend] [data-pw-chart-brand]")
                brands = legend.evaluate_all("buttons => buttons.map(b => b.dataset.pwChartBrand)")
                pinned, other = brands[1], brands[0]
                legend.nth(1).click()
                legend.nth(1).focus()
                self.assertEqual(page.evaluate("() => __pwTest.pinned()"), pinned)

                # Covers AE1: the 60-second refresh replaces the chart; the pin stays.
                page.evaluate("() => { window.__pwPriorChart = __pwTest.chart(); }")
                with page.expect_response(lambda response: "/chart.html?" in response.url):
                    page.evaluate(
                        """() => document.dispatchEvent(new CustomEvent('pw:filter-change',
                             {detail: {filters: window.pwFilter.get()}}))"""
                    )
                page.wait_for_function(
                    "() => __pwTest.chart() && __pwTest.chart() !== window.__pwPriorChart"
                )
                self.assertEqual(page.evaluate("() => __pwTest.pinned()"), pinned)
                _assert_focus_painted(self, page, pinned)
                self.assertEqual(
                    page.evaluate("() => document.activeElement.dataset.pwChartBrand || null"),
                    pinned,
                    "keyboard focus returns to the same legend entry after the refresh",
                )

                # Covers AE2: a filter limited to another brand removes the pinned one.
                # It is applied without a click, because any click outside the chart
                # releases a pin on its own and would hide a missing reconciliation.
                with page.expect_response(lambda response: "/chart.html?" in response.url):
                    page.evaluate(
                        """brand => document.dispatchEvent(new CustomEvent('pw:filter-change',
                             {detail: {filters: {...window.pwFilter.get(), brands: [brand]}}}))""",
                        other,
                    )
                page.wait_for_function(
                    """brand => !Object.keys(JSON.parse(
                         document.querySelector('[data-pw-chart] canvas.home-chart').dataset.home
                       ).series).includes(brand)""",
                    arg=pinned,
                )
                page.mouse.move(2, 2)
                self.assertIsNone(page.evaluate("() => __pwTest.pinned()"))
                _assert_idle(self, page)
                self.assertEqual(run.errors, [])
                run.context.close()
            finally:
                browser.close()

    def test_touch_taps_toggle_focus_without_a_hover_flash(self) -> None:
        """Covers AE6."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url, viewport=PHONE, touch=True)
                page = run.page
                goto_home(run, self.live_server_url, "locale=en&window=7")
                _install_helpers(page)
                page.locator("[data-pw-chart]").scroll_into_view_if_needed()
                page.evaluate(
                    """() => {
                      window.__pwFocusLog = [];
                      const legend = document.querySelector('[data-pw-chart] [data-pw-chart-legend]');
                      new MutationObserver(() => window.__pwFocusLog.push(__pwTest.focused()))
                        .observe(legend, {attributes: true, subtree: true, attributeFilter: ['class']});
                    }"""
                )
                segment = page.evaluate("() => __pwTest.isolatedSegment()")
                self.assertIsNotNone(segment)
                origin = page.evaluate("() => __pwTest.canvasOrigin()")
                tap_x = origin["x"] + segment["mid"]["x"] + segment["normal"]["x"] * 4
                tap_y = origin["y"] + segment["mid"]["y"] + segment["normal"]["y"] * 4

                page.touchscreen.tap(tap_x, tap_y)
                self.assertEqual(page.evaluate("() => __pwTest.focused()"), segment["brand"])
                _assert_focus_painted(self, page, segment["brand"])
                log = page.evaluate("() => window.__pwFocusLog")
                self.assertTrue(
                    all(entry in (None, segment["brand"]) for entry in log), log
                )
                self.assertIsNone(page.evaluate("() => __pwTest.pinned()"))

                page.touchscreen.tap(tap_x, tap_y)
                self.assertIsNone(page.evaluate("() => __pwTest.focused()"))

                legend = page.locator("[data-pw-chart] [data-pw-chart-legend] [data-pw-chart-brand]")
                target = legend.nth(2)
                target_brand = target.get_attribute("data-pw-chart-brand")
                box = target.bounding_box()
                self.assertIsNotNone(box)
                page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                self.assertEqual(page.evaluate("() => __pwTest.focused()"), target_brand)

                # A tap elsewhere on the page clears it.
                heading = page.locator("#pw-activity-head").bounding_box()
                page.touchscreen.tap(heading["x"] + 4, heading["y"] + heading["height"] / 2)
                self.assertIsNone(page.evaluate("() => __pwTest.focused()"))
                self.assertEqual(run.errors, [])
                run.context.close()
            finally:
                browser.close()

    def test_beacons_mark_every_latest_slot_in_each_language(self) -> None:
        """Covers AE3, including a zero latest bucket on the 1-day chart."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale in ("en", "zh_cn", "ja"):
                    run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                    page = run.page
                    goto_home(run, self.live_server_url, f"locale={locale}&window=1")
                    _install_helpers(page)
                    report = page.evaluate(
                        """() => {
                          const chart = __pwTest.chart();
                          const calls = __pwTest.record();
                          return chart.data.datasets.map((dataset, index) => ({dataset, index}))
                            .filter(({dataset, index}) => dataset._isTotalLine && chart.isDatasetVisible(index))
                            .map(({dataset, index}) => {
                              const last = dataset.data.length - 1;
                              const value = Number(dataset.data[last]);
                              const zero = !Number.isFinite(value) || value === 0;
                              const expected = {
                                x: chart.scales.x.getPixelForValue(last),
                                y: chart.scales.y.getPixelForValue(zero ? 0 : value),
                              };
                              const color = String(dataset.borderColor).toLowerCase();
                              const beacons = calls.fills.filter((fill) => fill.style === color && fill.center &&
                                Math.hypot(fill.center.x - expected.x, fill.center.y - expected.y) < 3);
                              return {brand: __pwTest.brandOf(dataset), zero, beacons: beacons.length,
                                      tooltip: calls.fills.some((fill) => fill.style === 'rgba(0, 0, 0, 0.8)')};
                            });
                        }"""
                    )
                    self.assertTrue(report, locale)
                    for entry in report:
                        self.assertEqual(entry["beacons"], 1, (locale, entry))
                        self.assertFalse(entry["tooltip"], (locale, entry))
                    self.assertTrue(
                        any(entry["zero"] for entry in report),
                        f"{locale}: the fixture must include a brand whose latest bucket is empty",
                    )
                    self.assertEqual(run.errors, [], locale)
                    run.context.close()
            finally:
                browser.close()

    def test_one_day_count_labels_never_overlap(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                page = run.page
                goto_home(run, self.live_server_url, "locale=en&window=1")
                _install_helpers(page)
                busiest = page.evaluate(
                    "() => __pwTest.lines().sort((a, b) => b.points.length - a.points.length)[0].brand"
                )
                page.locator(
                    f'[data-pw-chart] [data-pw-chart-legend] [data-pw-chart-brand="{busiest}"]'
                ).hover()
                labels = page.evaluate(
                    """brand => {
                      const line = __pwTest.lines().find((entry) => entry.brand === brand);
                      return __pwTest.record().texts.filter((t) => t.style === line.color)
                        .sort((a, b) => a.x - b.x);
                    }""",
                    busiest,
                )
                self.assertTrue(labels)
                for left, right in zip(labels, labels[1:]):
                    self.assertLessEqual(left["x"] + left["width"] / 2, right["x"] - right["width"] / 2)
                run.context.close()
            finally:
                browser.close()

    def test_reduced_motion_and_offscreen_charts_run_no_redraw_loop(self) -> None:
        count_draws = """async () => {
          const chart = __pwTest.chart();
          window.__pwDraws = 0;
          const original = chart.draw;
          chart.draw = function (...args) { window.__pwDraws++; return original.apply(this, args); };
          await new Promise((resolve) => setTimeout(resolve, 700));
          chart.draw = original;
          return window.__pwDraws;
        }"""
        swatch_animations = """brand => {
          const button = document.querySelector(
            `[data-pw-chart] [data-pw-chart-legend] [data-pw-chart-brand="${brand}"]`);
          const ping = button && button.querySelector('.pw-swatch-ping');
          return ping ? ping.getAnimations().filter((a) => a.playState === 'running').length : -1;
        }"""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                page = run.page
                goto_home(run, self.live_server_url, "locale=en&window=7")
                _install_helpers(page)
                self.assertGreaterEqual(page.evaluate(count_draws), 5, "beacons animate on screen")
                legend = page.locator("[data-pw-chart] [data-pw-chart-legend] [data-pw-chart-brand]")
                brand = legend.nth(0).get_attribute("data-pw-chart-brand")
                legend.nth(0).hover()
                self.assertGreaterEqual(page.evaluate(swatch_animations, brand), 1)
                page.mouse.move(2, 2)

                # Push the chart below the fold with a spacer above the page.
                page.evaluate(
                    """() => {
                      document.body.insertAdjacentHTML(
                        'afterbegin', '<div data-test-spacer style="height:4000px"></div>');
                      window.scrollTo(0, 0);
                    }"""
                )
                page.wait_for_function(
                    "() => document.querySelector('[data-pw-chart]').getBoundingClientRect().top > innerHeight"
                )
                page.wait_for_timeout(100)
                self.assertEqual(page.evaluate(count_draws), 0, "no frames while scrolled away")
                page.evaluate("() => document.querySelector('[data-test-spacer]').remove()")
                page.wait_for_function(
                    "() => document.querySelector('[data-pw-chart]').getBoundingClientRect().top < innerHeight"
                )
                self.assertGreaterEqual(page.evaluate(count_draws), 5, "frames resume on screen")
                page.evaluate(
                    "() => Object.defineProperty(document, 'hidden', {configurable: true, get: () => true})"
                )
                self.assertEqual(page.evaluate(count_draws), 0, "no frames while the tab is hidden")
                run.context.close()

                run = open_page(
                    browser, self.live_server_url, viewport=DESKTOP, reduced_motion="reduce"
                )
                page = run.page
                goto_home(run, self.live_server_url, "locale=en&window=7")
                _install_helpers(page)
                self.assertEqual(page.evaluate(count_draws), 0)
                beacons = page.evaluate(
                    """() => {
                      const calls = __pwTest.record();
                      return __pwTest.lines().map((line) => calls.fills.filter(
                        (fill) => fill.style === line.color).length);
                    }"""
                )
                self.assertTrue(beacons)
                self.assertTrue(all(count == 1 for count in beacons), beacons)
                legend = page.locator("[data-pw-chart] [data-pw-chart-legend] [data-pw-chart-brand]")
                legend.nth(0).hover()
                self.assertEqual(page.evaluate(swatch_animations, brand), 0)
                self.assertEqual(run.errors, [])
                run.context.close()
            finally:
                browser.close()
