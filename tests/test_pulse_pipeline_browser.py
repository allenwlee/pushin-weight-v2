"""The actual classifier, dossier writer and public page, with offline answers."""

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright

from tests.test_classified_product_releases import setup_cycle

pytestmark = pytest.mark.requires_postgres


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class PulsePipelineBrowserTests(StaticLiveServerTestCase):
    def test_new_discovery_is_visible_with_category_before_identity_resolves(self):
        with pytest.MonkeyPatch.context() as patch:
            state, runner, transport = setup_cycle(patch)
            state.post.tweet_url = "https://x.com/QwenOfficial/status/1234567890"
            state.post.save(update_fields=["tweet_url"])
            runner._run_post_fetch([], run_id="pulse-browser-integration")
        state.refresh_from_db()
        self.assertEqual(state.classification_status, "succeeded")
        self.assertEqual(len(transport.calls), 2)
        expected_url = state.post.tweet_url
        with sync_playwright() as browser_api:
            browser = browser_api.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                response = page.goto(self.live_server_url + "/pulse?locale=en")
                self.assertEqual(response.status, 200)
                card = page.locator("[data-pulse-event]")
                self.assertEqual(card.count(), 1)
                self.assertTrue(card.get_by_text("Qwen4", exact=True).is_visible())
                self.assertTrue(card.get_by_text("Product identity pending", exact=True).is_visible())
                self.assertTrue(card.get_by_text("Reported category: Language model", exact=True).is_visible())
                card.get_by_role("link", name="Related sources", exact=False).click()
                link = page.get_by_role("link", name="Original source", exact=False)
                self.assertEqual(link.get_attribute("href"), expected_url)
            finally:
                browser.close()
