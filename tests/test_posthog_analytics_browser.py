"""Exercise the real Django pages, authentication and downloaded PostHog SDK."""

import base64
import gzip
import json
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.requires_postgres
SDK_PATH = Path(__file__).resolve().parents[1] / ".pytest-tmp/posthog-sdk/array.js"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)
NORMAL_BROWSER_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {value: false});
if (navigator.userAgentData) {
    Object.defineProperty(Object.getPrototypeOf(navigator.userAgentData), 'brands', {
        get: () => [
            {brand: 'Chromium', version: '146'}, {brand: 'Google Chrome', version: '146'}
        ]
    });
}
"""


def decode_events(request):
    raw = request.post_data_buffer
    if not raw:
        return []
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        form = parse_qs(raw.decode())
        encoded = form["data"][0]
        if form.get("compression") == ["gzip-js"]:
            payload = json.loads(gzip.decompress(base64.b64decode(encoded)))
        else:
            payload = json.loads(encoded)
    if isinstance(payload, list):
        return payload
    return payload.get("batch", [payload])


@override_settings(
    POSTHOG_ENABLED=True,
    POSTHOG_PROJECT_TOKEN="phc_browser_fixture",
    POSTHOG_REGION="us",
    POSTHOG_ENVIRONMENT="test",
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class PostHogBrowserTests(StaticLiveServerTestCase):
    def install_routes(self, context, events, *, blocked=False):
        sdk = SDK_PATH.read_bytes()
        context.route(
            "https://us-assets.i.posthog.com/static/array.js",
            lambda route: (
                route.abort()
                if blocked
                else route.fulfill(content_type="application/javascript", body=sdk)
            ),
        )

        def ingest(route):
            self.assertNotIn("/flags", route.request.url)
            events.extend(decode_events(route.request))
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status":1}',
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "*",
                },
            )

        context.route("https://us.i.posthog.com/**", ingest)

    def visit(self, page, events):
        previous = len([event for event in events if event.get("event") == "$pageview"])
        page.goto(
            self.live_server_url + "/?token=sensitive-value&email=private@example.com",
            wait_until="domcontentloaded",
        )
        page.locator(".app-name").wait_for(state="visible")
        # Pump the actual SDK's background batching without modifying its API.
        for _ in range(25):
            page.wait_for_timeout(200)
            views = [event for event in events if event.get("event") == "$pageview"]
            if len(views) > previous:
                return views[-1]
        state = page.evaluate("""() => ({
            bootstrap: !!document.getElementById('pw-analytics-config'),
            loader: !!document.querySelector('script[src*=\"pw-analytics\"]'),
            sdk: !!window.posthog,
            loaded: window.posthog && window.posthog.__loaded,
            capturing: window.posthog && window.posthog.is_capturing && window.posthog.is_capturing(),
            bot: window.posthog && window.posthog._is_bot(),
            webdriver: navigator.webdriver,
            userAgent: navigator.userAgent,
            brands: navigator.userAgentData && navigator.userAgentData.brands,
            customBlocked: window.posthog && window.posthog.config.custom_blocked_useragents,
            sessionReady: window.posthog && !!window.posthog.sessionPersistence,
            id: window.posthog && window.posthog.get_distinct_id(),
            scripts: Array.from(document.scripts).map(s => s.src).filter(s => s.includes('posthog'))
        })""")
        self.fail(f"The real SDK did not emit a pageview: {state}")

    def test_pageviews_login_account_switch_and_logout(self):
        users = [
            get_user_model().objects.create_user(
                username=f"analytics-{index}", email=f"private-{index}@example.com"
            )
            for index in (1, 2)
        ]
        sessions = []
        for user in users:
            client = Client()
            client.force_login(user)
            sessions.append(client.cookies["sessionid"].value)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            # Exercise ordinary browser traffic while retaining SDK bot filtering.
            context = browser.new_context(user_agent=BROWSER_USER_AGENT)
            context.add_init_script(NORMAL_BROWSER_SCRIPT)
            events = []
            self.install_routes(context, events)
            page = context.new_page()
            anonymous = self.visit(page, events)
            identities = []
            for user, session in zip(users, sessions, strict=True):
                context.add_cookies(
                    [
                        {
                            "name": "sessionid",
                            "value": session,
                            "url": self.live_server_url,
                        }
                    ]
                )
                event = self.visit(page, events)
                identity = event["properties"]["distinct_id"]
                self.assertEqual(identity, f"pushinweight:user:{user.pk}")
                identities.append(identity)
            csrf = next(
                cookie["value"]
                for cookie in context.cookies()
                if cookie["name"] == "csrftoken"
            )
            logout = context.request.post(
                self.live_server_url + "/accounts/logout/",
                headers={"X-CSRFToken": csrf, "Referer": self.live_server_url + "/"},
                max_redirects=0,
            )
            self.assertEqual(logout.status, 302)
            logged_out = self.visit(page, events)
            self.assertNotIn(logged_out["properties"]["distinct_id"], identities)
            self.assertNotEqual(
                logged_out["properties"]["distinct_id"],
                anonymous["properties"]["distinct_id"],
            )
            allowed = {
                "token",
                "distinct_id",
                "$cookieless_mode",
                "$device_id",
                "$user_id",
                "$anon_distinct_id",
                "$session_id",
                "$window_id",
                "$lib",
                "$lib_version",
                "$process_person_profile",
                "$is_identified",
                "environment",
                "channel",
                "is_test",
                "$geoip_disable",
                "$current_url",
                "$pathname",
            }
            for event in events:
                self.assertIn(event["event"], ("$pageview", "$identify"))
                self.assertLessEqual(set(event["properties"]), allowed)
                self.assertNotIn("sensitive-value", json.dumps(event))
                self.assertNotIn("@example.com", json.dumps(event))
            identify = [event for event in events if event["event"] == "$identify"]
            self.assertEqual(len(identify), 2)
            self.assertNotEqual(
                identify[-1]["properties"]["$anon_distinct_id"], identities[0]
            )
            browser.close()

    def test_disabled_preferences_and_blocked_sdk(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for scenario in ("disabled", "dnt", "gpc", "blocked", "bot"):
                with self.subTest(scenario=scenario):
                    context = browser.new_context(
                        user_agent=BROWSER_USER_AGENT,
                        extra_http_headers={"DNT": "1"} if scenario == "dnt" else {},
                    )
                    if scenario != "bot":
                        context.add_init_script(NORMAL_BROWSER_SCRIPT)
                    events = []
                    requests = []
                    self.install_routes(context, events, blocked=scenario == "blocked")
                    context.on(
                        "request",
                        lambda request, collected=requests: (
                            collected.append(request.url)
                            if "posthog.com" in request.url
                            else None
                        ),
                    )
                    if scenario == "gpc":
                        context.add_init_script(
                            "Object.defineProperty(navigator, 'globalPrivacyControl', {value: true});"
                        )
                    page = context.new_page()
                    with override_settings(POSTHOG_ENABLED=scenario != "disabled"):
                        page.goto(self.live_server_url + "/", wait_until="networkidle")
                        page.locator(".app-name").wait_for(state="visible")
                    self.assertEqual(events, [])
                    if scenario not in ("blocked", "bot"):
                        self.assertEqual(requests, [])
                    context.close()
            browser.close()
