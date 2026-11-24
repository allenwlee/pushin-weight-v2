from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright


@pytest.mark.parametrize("blueprint", ["render.yaml", "render-staging.yaml"])
def test_web_service_can_serve_a_stylesheet_while_a_request_waits(blueprint):
    services = yaml.safe_load(Path(blueprint).read_text())["services"]
    web, = (service for service in services if service["type"] == "web")
    environment = {entry["key"]: entry.get("value") for entry in web["envVars"] if "key" in entry}
    assert int(environment.get("WEB_CONCURRENCY", 1)) >= 2


@pytest.mark.requires_postgres
@override_settings(SECURE_SSL_REDIRECT=False)
class ReaderStylesheetTests(StaticLiveServerTestCase):
    def test_transient_stylesheet_errors_recover_without_a_page_reload(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for path, filename in (("/", "home-v20"), ("/chatter/", "general"), ("/pulse", "pulse")):
                with self.subTest(path=path):
                    page = browser.new_page()
                    attempts = []
                    documents = []

                    def handle(route):
                        if urlsplit(route.request.url).netloc != urlsplit(self.live_server_url).netloc:
                            route.abort()
                            return
                        if route.request.resource_type == "document":
                            documents.append(route.request.url)
                        name = urlsplit(route.request.url).path.rsplit("/", 1)[-1]
                        if name.split(".")[0] == filename and name.endswith(".css"):
                            attempts.append(route.request.url)
                            if len(attempts) <= 2:
                                route.fulfill(status=502, body="Bad Gateway")
                                return
                        route.continue_()

                    page.route("**/*", handle)
                    try:
                        page.goto(self.live_server_url + path, wait_until="domcontentloaded")
                        page.wait_for_function(
                            """name => Array.from(document.styleSheets).some(sheet =>
                                sheet.href && new URL(sheet.href).pathname.split('/').pop().split('.')[0] === name
                                && sheet.cssRules.length > 0)""",
                            arg=filename, timeout=7000,
                        )
                        self.assertEqual(len(attempts), 3)
                        self.assertEqual(documents, [self.live_server_url + path])
                    finally:
                        page.close()
            browser.close()
