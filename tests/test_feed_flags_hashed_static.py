"""Scroll-loaded feed rows keep flags under a collectstatic-hashed sprite name (AE4).

Production serves ``country-flags.<hash>.svg``. The client renderer used to
accept only the unhashed name, so rows loaded after the first page lost their
flags while server-rendered rows kept them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from playwright.sync_api import sync_playwright

from core.models import Account
from tests.general_style_browser import DESKTOP, open_page
from tests.geolocation_factory import feed_places
from tests.test_chart_harvest_coverage import record_harvest
from tests.test_home_v22_browser import V22_BROWSER_TEST_STORAGES
from tests.v22_support import seed_v22_metadata_regression_orm

pytestmark = pytest.mark.requires_postgres

SPRITE = Path(__file__).resolve().parents[1] / "monitor/static/country-flags.svg"
HASHED = "/static/country-flags.e1ef2c1d1cff.svg"

FLAG_HREFS = """() => [...document.querySelectorAll('[data-pw-feed-row]')].map((row) => ({
  id: row.dataset.tweetId,
  hrefs: [...row.querySelectorAll('.account-country-flag use')].map((use) => use.getAttribute('href')),
}))"""


@override_settings(STORAGES=V22_BROWSER_TEST_STORAGES, SECURE_SSL_REDIRECT=False)
class FeedFlagsHashedStaticBrowserTests(StaticLiveServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fixture = seed_v22_metadata_regression_orm()
        places = feed_places()
        Account.objects.update(based_in_location=places["US"])
        now = timezone.now()
        record_harvest(now, finished_at=now, staggered=False)

    def test_page_two_rows_render_flags_from_the_hashed_sprite(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                sprite = SPRITE.read_bytes()
                run.context.route(
                    f"{self.live_server_url}{HASHED}",
                    lambda route: route.fulfill(status=200, content_type="image/svg+xml", body=sprite),
                )
                page = run.page
                page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                # Serve the page as production does: the body names the hashed sprite.
                page.evaluate(
                    "url => document.body.setAttribute('data-pw-country-flag-sprite-url', url)", HASHED
                )
                sentinel = page.locator("[data-pw-feed-sentinel]")
                with page.expect_response(lambda response: "/feed/?" in response.url and response.status == 200):
                    sentinel.scroll_into_view_if_needed()
                page_two = self.fixture["page_two_id"]
                page.locator(f'[data-tweet-id="{page_two}"]').wait_for()
                rows = {row["id"]: row["hrefs"] for row in page.evaluate(FLAG_HREFS)}
                self.assertEqual(rows[page_two], [f"{HASHED}#flag-us"])
                appended = [hrefs for tweet_id, hrefs in rows.items() if hrefs and hrefs[0].startswith(HASHED)]
                self.assertGreaterEqual(len(appended), 1)
                self.assertTrue(all(hrefs == [f"{HASHED}#flag-us"] for hrefs in appended), appended)
                flag = page.locator(f'[data-tweet-id="{page_two}"] .account-country-flag')
                box = flag.bounding_box()
                self.assertGreater(box["width"], 0)
                self.assertEqual(run.errors, [])
                run.context.close()
            finally:
                browser.close()
