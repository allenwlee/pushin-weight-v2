"""Owner console exercised through the real server and Chromium."""

from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from playwright.sync_api import sync_playwright

from core.models import (
    Account,
    Brand,
    OfficialCompanyAccountState,
    OfficialCompanyListIntent,
    ProductVerificationProposal,
)
from tests.test_product_review import _proposal

pytestmark = pytest.mark.requires_postgres


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            username="console-owner", email="staff@example.com", is_staff=True
        )
        self.client.force_login(self.user)

    def _context(self, browser):
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
                    "url": self.live_server_url,
                }
            ]
        )
        return context

    def test_old_review_url_redirects_to_empty_console(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                response = page.goto(
                    self.live_server_url + "/product-review/?locale=en"
                )
                self.assertEqual(response.status, 200)
                self.assertIn("/admin", page.url)
                self.assertTrue(
                    page.get_by_role("heading", name="Admin", exact=True).is_visible()
                )
                self.assertTrue(
                    page.get_by_text(
                        "No accounts have been evaluated yet.", exact=True
                    ).is_visible()
                )
                shot = (
                    Path(__file__).resolve().parents[1] / ".pytest-tmp/admin-empty.png"
                )
                shot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
            finally:
                browser.close()

    def test_admin_route_has_discovery_details(self):
        now = timezone.now()
        for identifier, name, requested, acknowledged in [
            ("881", "Speech Lab", now, now),
            ("882", "Existing Lab", None, None),
            ("883", "Readback Lab", now, None),
        ]:
            account = Account.objects.create(
                author_id=identifier, handle="lab" + identifier
            )
            state = OfficialCompanyAccountState.objects.create(
                account=account,
                status="registered",
                evidence_hash="a" * 64,
                decision={
                    "organization_name": name,
                    "model_types": ["speech"],
                    "rationale": "We develop speech models. <script>alert(1)</script>",
                    "claims": {
                        "official_account": [
                            {
                                "source_id": "post:123",
                                "quote": "We develop speech models.",
                            }
                        ]
                    },
                },
            )
            OfficialCompanyListIntent.objects.create(
                account=account,
                state=state,
                evidence_hash="a" * 64,
                list_id=2067062923525275922,
                status="confirmed",
                confirmed_at=now,
                add_requested_at=requested,
                add_acknowledged_at=acknowledged,
            )
        brand = Brand.objects.create(nickname="review_lab", display_name="Review Lab")
        proposal = _proposal("z", brand=brand)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(self.live_server_url + "/admin?locale=en")
                self.assertEqual(response.status, 200)
                self.assertTrue(
                    page.get_by_role("heading", name="Admin", exact=True).is_visible()
                )
                self.assertTrue(
                    page.get_by_role(
                        "heading", name="Official AI accounts", exact=True
                    ).is_visible()
                )
                self.assertEqual(
                    page.locator('[data-admin-count="found"]').inner_text(), "3"
                )
                self.assertEqual(
                    page.locator('[data-admin-count="added"]').inner_text(), "1"
                )
                self.assertTrue(
                    page.get_by_text(
                        "Already present; no add requested", exact=True
                    ).is_visible()
                )
                self.assertTrue(
                    page.get_by_text(
                        "Membership confirmed after add request", exact=True
                    ).is_visible()
                )
                row = page.locator('[data-admin-account="881"]')
                row.locator("details").first.locator("summary").click()
                self.assertTrue(row.get_by_text("post:123", exact=True).is_visible())
                self.assertEqual(page.locator("script").count(), 0)
                self.assertIn("<script>alert(1)</script>", row.inner_text())
                shot = (
                    Path(__file__).resolve().parents[1]
                    / ".pytest-tmp/admin-populated.png"
                )
                page.screenshot(path=str(shot), full_page=True)
                for locale, heading in [
                    ("zh_hans", "官方 AI 账号"),
                    ("ja", "公式 AI アカウント"),
                ]:
                    page.goto(self.live_server_url + "/admin?locale=" + locale)
                    self.assertTrue(
                        page.get_by_role(
                            "heading", name=heading, exact=True
                        ).is_visible()
                    )
                page.set_viewport_size({"width": 390, "height": 844})
                self.assertTrue(
                    page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                )
                page.screenshot(
                    path=str(shot.with_name("admin-mobile.png")), full_page=True
                )
                page.goto(self.live_server_url + "/admin?locale=en")
                page.get_by_role("link", name="Model X").click()
                self.assertIn(f"/admin/products/{proposal.pk}/", page.url)
                page.locator('select[name="brand_id"]').select_option(brand.pk)
                page.locator('select[name="product_type"]').select_option("llm-model")
                page.locator('textarea[name="reason"]').fill(
                    "Owner confirms this model."
                )
                page.get_by_role("button", name="Approve", exact=True).click()
                self.assertEqual(errors, [])
            finally:
                browser.close()
        self.assertEqual(
            ProductVerificationProposal.objects.get(pk=proposal.pk).review_status,
            "approved",
        )
