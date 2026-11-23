"""Real browser coverage for the dedicated General-styled Chatter page."""

import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright

from core.models import OriginalContentText
from tests.test_chatter_chain import chain_config
from tests.test_chatter_pool_readers import published

pytestmark = pytest.mark.requires_postgres
ARTIFACTS = Path(__file__).resolve().parents[1] / ".ollija/tmp/chatter-page-browser"


@override_settings(
    SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"]
)
class ChatterPageBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ORIGINAL_CONTENT_STORAGE": "shared"})
        self.env.start()
        self.addCleanup(self.env.stop)
        cfg = chain_config().model_copy(update={"public_enabled": True})
        self.config = patch(
            "monitor.editorial.views.load_editorial_config", return_value=cfg
        )
        self.config.start()
        self.addCleanup(self.config.stop)
        self.text = published("rest", "990801")
        self.text.headline = "A lab joke becomes the day's talking point"
        self.text.secondary = "Researchers join in after a playful exchange."
        self.text.body = "A saved report follows a funny community exchange.\n\nThe story remains linked to its sources."
        self.text.save(update_fields=["headline", "secondary", "body"])
        self.source_count = self.text.sources.count()
        OriginalContentText.objects.filter(pk=self.text.pk).update(
            created_at=datetime(2026, 11, 19, 1, tzinfo=UTC)
        )
        ARTIFACTS.mkdir(parents=True, exist_ok=True)

    def test_chatter_uses_real_general_shell(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                response = page.goto(
                    self.live_server_url + "/chatter/?lang=en", wait_until="networkidle"
                )
                self.assertEqual(response.status, 200)
                self.assertTrue(page.locator(".masthead .pw-wordmark").is_visible())
                self.assertTrue(
                    page.locator(
                        '[data-edition-id="' + str(self.text.public_id) + '"]'
                    ).is_visible()
                )
            finally:
                browser.close()

    def test_chatter_layout_controls_and_sources_in_all_locales(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                for width, height in ((1440, 900), (390, 844)):
                    for locale in ("en", "ja", "zh-cn"):
                        with self.subTest(width=width, locale=locale):
                            context = browser.new_context(
                                viewport={"width": width, "height": height},
                                timezone_id="Asia/Tokyo",
                            )
                            errors, failed, external, feed_requests = [], [], [], []
                            context.on(
                                "response",
                                lambda response, failed=failed: (
                                    failed.append(response.url)
                                    if response.status >= 400
                                    else None
                                ),
                            )
                            context.on(
                                "request",
                                lambda request, external=external: (
                                    external.append(request.url)
                                    if not request.url.startswith(self.live_server_url)
                                    else None
                                ),
                            )
                            context.on(
                                "request",
                                lambda request, feed_requests=feed_requests: (
                                    feed_requests.append(request.url)
                                    if "/general/feed/" in request.url
                                    else None
                                ),
                            )
                            page = context.new_page()
                            page.on(
                                "pageerror",
                                lambda error, errors=errors: errors.append(str(error)),
                            )
                            response = page.goto(
                                f"{self.live_server_url}/chatter/?lang={locale}&source_lang=en&edition_lang=en",
                                wait_until="networkidle",
                            )
                            self.assertEqual(response.status, 200)
                            self.assertEqual(
                                page.locator("html").get_attribute("lang"), locale
                            )
                            self.assertEqual(
                                page.locator(".masthead .pw-wordmark").inner_text(),
                                "PUSHINWEIGHT",
                            )
                            self.assertEqual(
                                page.locator(".editorial-story").count(), 1
                            )
                            self.assertTrue(
                                page.locator(".editorial-story").is_visible()
                            )
                            self.assertIn(
                                self.text.headline,
                                page.locator(".editorial-headline").inner_text(),
                            )
                            self.assertEqual(
                                page.evaluate(
                                    "getComputedStyle(document.body).backgroundColor"
                                ),
                                "rgb(240, 242, 245)",
                            )
                            self.assertEqual(
                                page.evaluate(
                                    "getComputedStyle(document.querySelector('.general-shell > header')).backgroundColor"
                                ),
                                "rgb(255, 255, 255)",
                            )
                            self.assertEqual(
                                page.evaluate(
                                    "document.documentElement.scrollWidth - document.documentElement.clientWidth"
                                ),
                                0,
                            )
                            self.assertIn(
                                "Newsreader",
                                page.locator(".editorial-headline").evaluate(
                                    "node => getComputedStyle(node).fontFamily"
                                ),
                            )
                            sources = page.locator(".archive-list .editorial-sources")
                            sources.locator("summary").click()
                            self.assertTrue(sources.locator("ol").is_visible())
                            self.assertEqual(
                                sources.locator("ol a").count(), self.source_count
                            )
                            sources.locator("summary").click()
                            before = page.locator("[data-published-at]").inner_text()
                            if width <= 700:
                                page.locator(".mobile-nav-toggle").click()
                                self.assertEqual(
                                    page.locator("body").get_attribute("data-nav"),
                                    "mobile-open",
                                )
                                page.locator("#general-settings > summary").click()
                                controls = page.locator(".settings-drawer")
                            else:
                                page.locator(".left-nav > .nav-toggle").click()
                                self.assertEqual(
                                    page.locator("body").get_attribute("data-nav"),
                                    "expanded",
                                )
                                controls = page.locator(".header-settings")
                            controls.locator(
                                '[data-pref="timezone"][data-value="ca"]'
                            ).click()
                            self.assertNotEqual(
                                page.locator("[data-published-at]").inner_text(), before
                            )
                            self.assertIn("timezone=ca", page.url)
                            self.assertIn("/chatter/", page.url)
                            controls.locator(
                                '[data-pref="timezone"][data-value="local"]'
                            ).click()
                            self.assertEqual(
                                page.locator("[data-published-at]").inner_text(), before
                            )
                            if width <= 700:
                                page.keyboard.press("Escape")
                                self.assertEqual(
                                    page.locator("body").get_attribute("data-nav"),
                                    "rail",
                                )
                            if locale == "en":
                                page.screenshot(
                                    path=str(ARTIFACTS / f"chatter-{width}.png"),
                                    full_page=True,
                                )
                            self.assertEqual(errors, [])
                            self.assertEqual(failed, [])
                            self.assertEqual(external, [])
                            self.assertEqual(feed_requests, [])
                            context.close()
            finally:
                browser.close()

    def test_chatter_without_javascript_keeps_timestamp_and_page_links(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                context = browser.new_context(java_script_enabled=False)
                page = context.new_page()
                page.goto(
                    self.live_server_url + "/chatter/?lang=en", wait_until="networkidle"
                )
                self.assertEqual(
                    page.locator("time[data-published-at]").inner_text(),
                    "2026-11-19 10:00 JST",
                )
                for link in page.locator(".header-settings [data-pref]").all():
                    self.assertTrue(link.get_attribute("href").startswith("/chatter/?"))
                self.assertTrue(page.locator(".editorial-story").is_visible())
            finally:
                browser.close()

    def test_pagination_preserves_changed_preferences_and_language_resets_cursor(self):
        for number in range(20):
            published("rest", str(991000 + number))
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(
                    self.live_server_url + "/chatter/?lang=en&timezone=local",
                    wait_until="networkidle",
                )
                page.locator(
                    '.header-settings [data-pref="timezone"][data-value="ca"]'
                ).click()
                page.locator("[data-chatter-next]").click()
                page.wait_for_load_state("networkidle")
                self.assertIn("cursor=", page.url)
                self.assertIn("timezone=ca", page.url)
                self.assertEqual(page.locator(".editorial-story").count(), 1)
                page.locator(
                    '.header-settings [data-pref="lang"][data-value="ja"]'
                ).click()
                page.wait_for_load_state("networkidle")
                self.assertNotIn("cursor=", page.url)
                self.assertEqual(page.locator("html").get_attribute("lang"), "ja")
                self.assertEqual(
                    page.locator(".empty-feed").inner_text(),
                    "公開された記事はまだありません。",
                )
            finally:
                browser.close()

    def test_pool_submission_keeps_current_page_preferences(self):
        from urllib.parse import parse_qs, urlsplit

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                for route in ("/chatter/", "/general/"):
                    with self.subTest(route=route):
                        context = browser.new_context(
                            viewport={"width": 1440, "height": 900}
                        )
                        page = context.new_page()
                        page.goto(
                            self.live_server_url
                            + route
                            + "?lang=en&timezone=local&weights=open&audience=human",
                            wait_until="networkidle",
                        )
                        page.locator(
                            '.header-settings [data-pref="timezone"][data-value="ca"]'
                        ).click()
                        page.locator(
                            '.primary-settings [data-pref="weights"][data-value="open"]'
                        ).click()
                        if route == "/chatter/":
                            page.locator(
                                '.primary-settings [data-pref="audience"][data-value="agent"]'
                            ).click()
                        pool = page.locator("#chatter .chatter-pools")
                        pool.locator('[name="group"]').select_option("giant")
                        pool.locator('button[type="submit"]').click()
                        page.wait_for_load_state("networkidle")
                        selected = parse_qs(urlsplit(page.url).query)
                        self.assertEqual(selected["timezone"], ["ca"])
                        self.assertEqual(selected["weights"], ["none"])
                        self.assertEqual(
                            selected["audience"],
                            ["agent" if route == "/chatter/" else "human"],
                        )
                        self.assertEqual(selected["group"], ["giant"])
                        self.assertEqual(
                            pool.locator('[name="source_lang"]').input_value(), "en"
                        )
                        self.assertEqual(
                            pool.locator('[name="edition_lang"]').input_value(), "en"
                        )
                        context.close()
            finally:
                browser.close()
