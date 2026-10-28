"""Per-post brand logo row above the sentiment signals, server and client rendered."""

from __future__ import annotations

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from playwright.sync_api import Page, sync_playwright

from core.brand_presentation import brand_logo_urls
from core.models import Brand
from tests.general_style_browser import DESKTOP, PHONE, open_page
from tests.test_chart_harvest_coverage import record_harvest
from tests.test_home_v22_browser import V22_BROWSER_TEST_STORAGES
from tests.v22_support import seed_v22_metadata_regression_orm

pytestmark = pytest.mark.requires_postgres

LOGO_ROW = """tweetId => {
  const row = document.querySelector(`[data-pw-feed-row][data-tweet-id="${tweetId}"]`);
  const logos = row && row.querySelector('.feed-signals [data-sig-brands]');
  if (!logos) return null;
  const sentiment = row.querySelector('.feed-signals .sig-sentiment');
  return {
    html: logos.outerHTML.replace(/ aria-expanded="(true|false)"/g, ''),
    beforeSentiment: Boolean(sentiment) &&
      Boolean(logos.compareDocumentPosition(sentiment) & Node.DOCUMENT_POSITION_FOLLOWING),
    buttons: [...logos.querySelectorAll('button.pw-post-brand')].map((button) => {
      const image = button.querySelector('img');
      const box = (image || button).getBoundingClientRect();
      return {
        label: button.getAttribute('aria-label'),
        inspection: button.dataset.pwInspection,
        src: image ? image.getAttribute('src') : null,
        alt: image ? image.getAttribute('alt') : null,
        text: image ? '' : button.textContent.trim(),
        width: box.width,
        loaded: image ? image.naturalWidth > 0 : null,
      };
    }),
  };
}"""


@override_settings(STORAGES=V22_BROWSER_TEST_STORAGES, SECURE_SSL_REDIRECT=False)
class FeedBrandLogosBrowserTests(StaticLiveServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fixture = seed_v22_metadata_regression_orm()
        Brand.objects.filter(nickname="deepseek").update(display_name_zh_cn="深度求索")
        now = timezone.now()
        record_harvest(now, finished_at=now, staggered=False)
        self.logos = brand_logo_urls()

    def _two_brand_row(self, page: Page) -> str:
        return page.evaluate(
            """() => [...document.querySelectorAll('[data-pw-feed-row]')].find(
                 (row) => row.querySelectorAll('[data-sig-brands] button').length === 2).dataset.tweetId"""
        )

    def test_server_and_client_rows_render_the_same_logo_row(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale, names in (
                    ("en", ["Kimi", "DeepSeek"]),
                    ("zh_cn", ["Kimi", "深度求索"]),
                    ("ja", ["Kimi", "DeepSeek"]),
                ):
                    with self.subTest(locale=locale):
                        run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                        page = run.page
                        page.goto(f"{self.live_server_url}/?locale={locale}", wait_until="networkidle")
                        tweet_id = self._two_brand_row(page)
                        server = page.evaluate(LOGO_ROW, tweet_id)
                        self.assertTrue(server["beforeSentiment"])
                        self.assertEqual([button["label"] for button in server["buttons"]], names)
                        self.assertEqual([button["inspection"] for button in server["buttons"]], names)
                        self.assertEqual(
                            [button["src"] for button in server["buttons"]],
                            [self.logos["moonshot_kimi"], self.logos["deepseek"]],
                        )
                        for button in server["buttons"]:
                            self.assertEqual(button["alt"], "")
                            self.assertGreater(button["width"], 0)
                            self.assertTrue(button["loaded"], button)

                        old_row = page.locator(f'[data-tweet-id="{tweet_id}"]').element_handle()
                        with page.expect_response(lambda response: "/feed/?" in response.url and response.status == 200):
                            page.evaluate(
                                """() => document.dispatchEvent(new CustomEvent('pw:filter-change',
                                     {detail: {filters: window.pwFilter.get()}}))"""
                            )
                        page.wait_for_function("row => !row.isConnected", arg=old_row)
                        page.locator(f'[data-tweet-id="{tweet_id}"]').wait_for()
                        client = page.evaluate(LOGO_ROW, tweet_id)
                        self.assertEqual(client["html"], server["html"])
                        self.assertTrue(client["beforeSentiment"])
                        self.assertEqual(run.errors, [])
                        run.context.close()
            finally:
                browser.close()

    def test_logo_name_opens_by_hover_tap_and_keyboard(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale, expected in (("en", "DeepSeek"), ("zh_cn", "深度求索")):
                    with self.subTest(locale=locale):
                        run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                        page = run.page
                        page.goto(f"{self.live_server_url}/?locale={locale}", wait_until="networkidle")
                        tweet_id = self._two_brand_row(page)
                        logo = page.locator(
                            f'[data-tweet-id="{tweet_id}"] [data-sig-brands] button[aria-label="{expected}"]'
                        )
                        popover = page.locator("#pw-feed-inspection-popover")
                        logo.hover()
                        self.assertTrue(popover.is_visible())
                        self.assertEqual(popover.locator(".inspection-words").inner_text(), expected)
                        page.mouse.move(2, 2)
                        logo.focus()
                        page.keyboard.press("Enter")
                        self.assertTrue(popover.is_visible())
                        self.assertEqual(popover.locator(".inspection-words").inner_text(), expected)
                        self.assertEqual(logo.get_attribute("aria-expanded"), "true")
                        page.keyboard.press("Escape")
                        self.assertFalse(popover.is_visible())
                        run.context.close()

                run = open_page(browser, self.live_server_url, viewport=PHONE, touch=True)
                page = run.page
                page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                tweet_id = self._two_brand_row(page)
                logo = page.locator(f'[data-tweet-id="{tweet_id}"] [data-sig-brands] button[aria-label="Kimi"]')
                logo.scroll_into_view_if_needed()
                box = logo.bounding_box()
                page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                popover = page.locator("#pw-feed-inspection-popover")
                self.assertTrue(popover.is_visible())
                self.assertEqual(popover.locator(".inspection-words").inner_text(), "Kimi")
                self.assertEqual(run.errors, [])
                run.context.close()
            finally:
                browser.close()
