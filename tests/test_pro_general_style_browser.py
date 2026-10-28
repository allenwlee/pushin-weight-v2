"""General visual system on the homepage: colors, fonts, layout and flags.

Values are the approved prototype's final computed values
(docs/iterations/2026-10-28-183433-general-style-bridgewright-target.md).
"""

from __future__ import annotations

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright

from tests.general_style_browser import (
    DESKTOP,
    LOCALES,
    PHONE,
    TABLET,
    goto_home,
    horizontal_overflow,
    open_page,
)
from tests.test_chart_harvest_coverage import record_harvest
from tests.test_home_v22_browser import V22_BROWSER_TEST_STORAGES
from tests.v22_support import seed_v22_metadata_regression_orm

pytestmark = pytest.mark.requires_postgres

BRONZE = ("rgb(139, 106, 62)", "rgb(110, 81, 48)")

STYLE_STATE = """() => {
  const style = (selector) => {
    const element = document.querySelector(selector);
    return element ? getComputedStyle(element) : null;
  };
  const box = (selector) => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return {x: rect.x, y: rect.y, width: rect.width, height: rect.height, right: rect.right};
  };
  // A headline title only renders with a narrative; probe its rule directly.
  const strip = document.querySelector('.headline-strip');
  strip.insertAdjacentHTML('beforeend',
    '<div class="headline-item" data-test-probe><h3 class="headline-item-title">Probe</h3></div>');
  const headlineFont = getComputedStyle(strip.querySelector('[data-test-probe] h3')).fontFamily;
  strip.querySelector('[data-test-probe]').remove();
  const colors = new Set();
  for (const element of document.querySelectorAll('body *')) {
    const computed = getComputedStyle(element);
    colors.add(computed.color);
    colors.add(computed.backgroundColor);
    colors.add(computed.borderTopColor);
    colors.add(computed.fill);
  }
  return {
    shell: style('.app-shell').backgroundColor,
    masthead: style('.topbar').backgroundColor,
    mastheadBox: box('.topbar'),
    panelRadius: style('.pw-panel.pw-activity').borderTopLeftRadius,
    panelBorder: style('.pw-panel.pw-activity').borderTopColor,
    panelBackground: style('.pw-panel.pw-activity').backgroundColor,
    bodyFont: style('body').fontFamily,
    headlineFont,
    wordmark: {
      style: style('.pw-wordmark').fontStyle,
      size: style('.pw-wordmark').fontSize,
      transform: style('.pw-wordmark').textTransform,
      pushinWeight: style('.pw-wm-pushin').fontWeight,
      pushinTracking: style('.pw-wm-pushin').letterSpacing,
      weightWeight: style('.pw-wm-weight').fontWeight,
      weightTracking: style('.pw-wm-weight').letterSpacing,
    },
    stateColor: style('.headline-strip .headline-state')?.color ?? null,
    colors: [...colors],
    chart: box('.pw-panel.pw-activity'),
    summary: box('.headline-strip'),
    feed: box('.feed-strip'),
    viewport: innerWidth,
  };
}"""


@override_settings(STORAGES=V22_BROWSER_TEST_STORAGES, SECURE_SSL_REDIRECT=False)
class ProGeneralStyleBrowserTests(StaticLiveServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        seed_v22_metadata_regression_orm()
        from django.utils import timezone

        now = timezone.now()
        record_harvest(now, finished_at=now, staggered=False)

    def test_desktop_tokens_fonts_and_wordmark_match_the_prototype(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                page = run.page
                fonts = []
                run.context.on(
                    "response",
                    lambda response: fonts.append(response.url) if "/static/fonts/" in response.url else None,
                )
                goto_home(run, self.live_server_url, "locale=en")
                page.evaluate("() => document.fonts.ready")
                state = page.evaluate(STYLE_STATE)
                self.assertEqual(state["shell"], "rgb(240, 242, 245)")
                self.assertEqual(state["masthead"], "rgb(255, 255, 255)")
                self.assertLessEqual(state["mastheadBox"]["x"], 48.5)
                self.assertAlmostEqual(state["mastheadBox"]["right"], state["viewport"], delta=0.5)
                self.assertEqual(state["panelRadius"], "18px")
                self.assertEqual(state["panelBorder"], "rgb(220, 228, 252)")
                self.assertEqual(state["panelBackground"], "rgb(255, 255, 255)")
                self.assertTrue(state["bodyFont"].startswith('"DM Sans"'), state["bodyFont"])
                self.assertTrue(state["headlineFont"].startswith("Newsreader"), state["headlineFont"])
                self.assertEqual(
                    state["wordmark"],
                    {
                        "style": "italic",
                        "size": "15px",
                        "transform": "uppercase",
                        "pushinWeight": "500",
                        "pushinTracking": "0.9px",
                        "weightWeight": "800",
                        "weightTracking": "normal",
                    },
                )
                self.assertEqual(state["stateColor"], "rgb(104, 117, 137)")
                for bronze in BRONZE:
                    self.assertNotIn(bronze, state["colors"])
                # Desktop: summary beside the chart, feed below both.
                self.assertLess(state["summary"]["x"], state["chart"]["x"])
                self.assertLess(state["chart"]["y"] + state["chart"]["height"], state["feed"]["y"] + 1)
                # Self-hosted fonts only: the italic wordmark face loads from /static/fonts/.
                self.assertTrue(page.evaluate("() => document.fonts.check('italic 800 15px \"DM Sans\"')"))
                self.assertTrue(any("dm-sans-latin-standard-italic" in url for url in fonts), fonts)
                self.assertEqual(run.external, [])
                self.assertEqual(run.errors, [])
                run.context.close()
            finally:
                browser.close()

    def test_layout_order_and_overflow_at_each_breakpoint(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for viewport in (TABLET, PHONE):
                    for locale in LOCALES:
                        with self.subTest(viewport=viewport, locale=locale):
                            run = open_page(browser, self.live_server_url, viewport=viewport)
                            page = run.page
                            goto_home(run, self.live_server_url, f"locale={locale}")
                            state = page.evaluate(STYLE_STATE)
                            # 960px and below: chart, then summary, then feed.
                            self.assertLess(state["chart"]["y"], state["summary"]["y"])
                            self.assertLess(state["summary"]["y"], state["feed"]["y"])
                            self.assertEqual(horizontal_overflow(page), 0)
                            if viewport == PHONE:
                                self.assertFalse(page.locator("#pw-rail").is_visible())
                                columns = page.evaluate(
                                    """() => new Set([...document.querySelectorAll('[data-pw-feed-row]')]
                                      .slice(0, 6).map((row) => Math.round(row.getBoundingClientRect().x))).size"""
                                )
                                self.assertEqual(columns, 1)
                            self.assertEqual(run.external, [])
                            run.context.close()
            finally:
                browser.close()

    def test_glyph_colors_flags_and_dropdowns(self) -> None:
        from core.models import Account
        from tests.geolocation_factory import feed_places

        places = feed_places()
        Account.objects.filter(author_id="v22-metadata-account-000").update(
            based_in_location=places["US"]
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                page = run.page
                goto_home(run, self.live_server_url, "locale=en")
                amber = page.evaluate(
                    """() => [...document.querySelectorAll(
                         '.feed-signals .tone-mixed, .feed-row .account-role.role-official')]
                       .map((node) => getComputedStyle(node).color)"""
                )
                self.assertTrue(amber, "fixture renders a mixed or official glyph")
                self.assertEqual(set(amber), {"rgb(217, 119, 6)"})

                flag_styles = """selector => [...document.querySelectorAll(selector)].map((node) => ({
                  filter: getComputedStyle(node).filter, transform: getComputedStyle(node).transform,
                }))"""
                geopolitical = page.locator('.filter-pill[data-group="geopolitical_modes"]')
                geopolitical.locator(".title").click()
                page.locator(".filter-dropdown.is-portaled").wait_for(state="visible")
                dropdown_flags = page.evaluate(flag_styles, ".filter-dropdown.is-portaled svg.country-flag")
                geopolitical.locator(".title").click()
                feed_flags = page.evaluate(flag_styles, ".feed-row .account-country-flag")
                self.assertTrue(feed_flags)
                self.assertEqual(len(dropdown_flags), 2)
                for flag in feed_flags + dropdown_flags:
                    self.assertIn("drop-shadow", flag["filter"])
                    self.assertTrue(flag["transform"].startswith("matrix(0.844"), flag)

                # A selected trending chip keeps every delta readable on its tint.
                for kind, color in (("new", "rgb(10, 138, 92)"), ("flat", "rgb(104, 117, 137)")):
                    chip = page.locator(f'[data-pw-pulse-entry]:has(.delta.{kind})').first
                    with page.expect_response(lambda response: "/chart.html?" in response.url):
                        chip.click()
                    self.assertEqual(chip.get_attribute("aria-pressed"), "true")
                    self.assertEqual(chip.locator(".delta").evaluate("node => getComputedStyle(node).color"), color)
                    with page.expect_response(lambda response: "/chart.html?" in response.url):
                        chip.click()

                # Sentiment: an option without a glyph keeps the 16px glyph space.
                sentiment = page.locator('.filter-pill[data-group="sentiment"]')
                sentiment.locator(".title").click()
                dropdown = page.locator(".filter-dropdown.is-portaled")
                dropdown.wait_for(state="visible")
                box = dropdown.bounding_box()
                self.assertGreater(box["width"], 0)
                self.assertGreater(box["height"], 0)
                lefts = dropdown.locator("label").evaluate_all(
                    """labels => labels.map((label) => ({
                         icon: Boolean(label.querySelector('[data-pw-semantic-icon] svg')),
                         left: Math.round(label.querySelector('.filter-option-text').getBoundingClientRect().left
                           - label.getBoundingClientRect().left),
                       }))"""
                )
                self.assertTrue(any(entry["icon"] for entry in lefts))
                self.assertTrue(any(not entry["icon"] for entry in lefts), lefts)
                self.assertEqual(len({entry["left"] for entry in lefts}), 1, lefts)
                dropdown.locator(".dd-grid").click(position={"x": 2, "y": 2})
                self.assertTrue(dropdown.is_visible(), "an interior click keeps the dropdown open")
                page.locator("#pw-activity-head").click()
                page.wait_for_function(
                    "() => !document.querySelector('.filter-dropdown.is-portaled')"
                    " || getComputedStyle(document.querySelector('.filter-dropdown.is-portaled')).display === 'none'"
                )
                self.assertEqual(run.errors, [])
                run.context.close()
            finally:
                browser.close()
