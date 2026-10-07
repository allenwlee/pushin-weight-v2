"""The real anonymous story route must display the count and every source link."""

import os

import pytest
from playwright.sync_api import sync_playwright

from monitor.editorial.config import EditorialConfig
from tests.test_editorial_views import edition

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def browser_settings(settings):
    settings.SECURE_SSL_REDIRECT = False
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]


def test_story_source_count_and_complete_links(live_server, monkeypatch):
    monkeypatch.setattr(
        "monitor.editorial.views.load_editorial_config",
        lambda: EditorialConfig(public_enabled=True),
    )
    urls = ["https://x.com/i/status/1", "https://x.com/i/status/2"]
    item = edition(
        evidence={
            "sources": [
                {"id": str(i + 1), "url": url, "author_handle": "same_account"}
                for i, url in enumerate(urls)
            ]
        }
    )
    with sync_playwright() as pw:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        browser = pw.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )
        page = browser.new_page(
            viewport={"width": 390, "height": 844},
            extra_http_headers={"X-Forwarded-Proto": "https"},
        )
        for locale in ("en", "zh-cn", "ja"):
            response = page.goto(
                f"{live_server.url}/stories/{item.story_id}/?lang={locale}"
            )
            assert response.status == 200
            sources = page.locator(".source-attribution")
            assert sources.count() == 1
            assert sources.is_visible()
            expected = {"en": "2 posts", "zh-cn": "2 条帖子", "ja": "2 件の投稿"}
            assert expected[locale] in sources.inner_text()
            assert (
                sources.locator("a").evaluate_all("els => els.map(el => el.href)")
                == urls
            )
            assert sources.bounding_box()["width"] > 0
            assert page.locator("h1").inner_text() == item.headline
        browser.close()
