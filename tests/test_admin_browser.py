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
                        "No official accounts have been found yet.", exact=True
                    ).is_visible()
                )
                shot = (
                    Path(__file__).resolve().parents[1] / ".pytest-tmp/admin-empty.png"
                )
                shot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
            finally:
                browser.close()

    def test_model_positive_without_list_intent_is_visible_for_review(self):
        account = Account.objects.create(author_id="884", handle="candidate_lab")
        OfficialCompanyAccountState.objects.create(
            account=account,
            status="review_needed",
            evidence_hash="a" * 64,
            last_error="human_review_required",
            decision={
                "outcome": "accepted",
                "organization_name": "Candidate Lab",
                "rationale": "Candidate evidence requiring owner review.",
            },
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                response = page.goto(self.live_server_url + "/admin?locale=en")
                self.assertEqual(response.status, 200)
                row = page.locator('[data-admin-account="884"]')
                self.assertTrue(row.is_visible())
                self.assertTrue(row.get_by_text("review_needed", exact=True).is_visible())
                self.assertEqual(page.locator('[data-admin-count="found"]').inner_text(), "1")
                self.assertEqual(page.locator('[data-admin-count="registered"]').inner_text(), "0")
                page.set_viewport_size({"width": 390, "height": 844})
                self.assertTrue(row.is_visible())
                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
                shot = Path(__file__).resolve().parents[1] / ".pytest-tmp/admin-human-review.png"
                shot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
            finally:
                browser.close()

    def test_hf_approved_account_and_list_history_are_visible(self):
        from unittest.mock import Mock, patch

        import httpx

        from core.official_company_accounts import enqueue_account, register_account
        from core.official_company_candidates import CANDIDATE_POLICY
        from core.official_company_hf import verify, verify_review_candidates
        from core.official_company_lists import sync_intents
        from tests.test_official_company_hf import transport
        from x_monitor.config import OfficialCompanyConfig

        state = enqueue_account(Account.objects.create(author_id="92103", handle="examplelab", bio="We develop our own speech models."))
        state.status = "review_needed"
        state.candidate_policy_version = CANDIDATE_POLICY
        state.last_error = "ValueError"
        state.save()
        route, _ = transport()
        def public_verifier(evidence, decision, **kwargs):
            with httpx.Client(transport=route) as client:
                return verify(evidence, decision, client=client, **kwargs)
        env_patch = patch.dict("os.environ", {"PUSHINWEIGHT_OFFICIAL_COMPANY_HF_SIGNING_KEY": "isolated-browser-key"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        with patch("core.official_company_hf.verify", public_verifier):
            self.assertEqual(verify_review_candidates(limit=1)["approved"], 1)
        cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True, list_sync_enabled=True)
        self.assertIsNotNone(register_account(state.pk, cfg=cfg))
        provider = Mock()
        provider.members.return_value = (set(), True)
        sync_intents(cfg=cfg, client=provider)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                page.goto(self.live_server_url + "/admin?locale=en&candidate_status=hf_verified")
                queue = page.locator("#candidate-queue")
                self.assertEqual(queue.locator('[data-candidate-count="hf_verified"]').inner_text(), "1")
                self.assertEqual(queue.locator('[data-candidate-count="review_needed"]').inner_text(), "0")
                row = queue.locator('[data-admin-candidate="92103"]')
                self.assertTrue(row.get_by_text("Registered", exact=True).is_visible())
                self.assertEqual(row.get_by_role("link", name="examplelab/speech").get_attribute("href"), "https://huggingface.co/examplelab/speech")
                self.assertTrue(page.locator('[data-admin-account="92103"]').get_by_text("Add acknowledged", exact=True).is_visible())
                shot = Path(__file__).resolve().parents[1] / ".pytest-tmp/admin-hf-verified.png"
                shot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
            finally:
                browser.close()

    def test_candidate_queue_tracks_waiting_and_rejected_accounts(self):
        from core.models import Brand, BrandAccount, Role
        from core.official_company_candidates import CANDIDATE_POLICY

        for identifier, handle, status, priority in [
            ("92101", "waiting_lab", "pending", 1),
            ("92102", "rejected_company", "rejected", 2),
        ]:
            OfficialCompanyAccountState.objects.create(
                account=Account.objects.create(author_id=identifier, handle=handle),
                evidence_hash="e" * 64, status=status,
                candidate_priority=priority, candidate_policy_version=CANDIDATE_POLICY,
                decision={"outcome": "rejected", "rationale": "No model development evidence."}
                if status == "rejected" else {},
            )
        role, _ = Role.objects.get_or_create(key="official")
        BrandAccount.objects.create(account_id="92101", brand=Brand.objects.create(nickname="known_model"), role=role)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(self.live_server_url + "/admin?locale=en")
                queue = page.locator("#candidate-queue")
                self.assertTrue(queue.is_visible())
                self.assertTrue(queue.get_by_text("@waiting_lab", exact=True).is_visible())
                self.assertTrue(queue.get_by_text("@rejected_company", exact=True).is_visible())
                self.assertEqual(queue.locator('[data-candidate-count="selected"]').inner_text(), "2")
                self.assertEqual(queue.locator('[data-candidate-count="llm_evaluated"]').inner_text(), "0")
                self.assertEqual(queue.locator('[data-candidate-count="already_tracked"]').inner_text(), "1")
                self.assertTrue(queue.get_by_text("Tracked brands: known_model", exact=True).is_visible())
                queue.get_by_label("Candidate status").select_option("already_tracked")
                queue.get_by_role("button", name="Apply filters").click()
                queue = page.locator("#candidate-queue")
                self.assertTrue(queue.get_by_text("@waiting_lab", exact=True).is_visible())
                self.assertEqual(queue.get_by_text("@rejected_company", exact=True).count(), 0)
                queue.get_by_label("Candidate status").select_option("rejected")
                queue.get_by_role("button", name="Apply filters").click()
                queue = page.locator("#candidate-queue")
                self.assertFalse(queue.get_by_text("@waiting_lab", exact=True).count())
                self.assertTrue(queue.get_by_text("@rejected_company", exact=True).is_visible())
                for locale, title in [("zh_hans", "候选账号队列"), ("ja", "候補アカウントの待機列")]:
                    page.goto(self.live_server_url + "/admin?locale=" + locale)
                    self.assertTrue(page.get_by_role("heading", name=title, exact=True).is_visible())
                page.goto(self.live_server_url + "/admin?locale=en")
                page.set_viewport_size({"width": 390, "height": 844})
                self.assertTrue(page.locator("#candidate-queue").is_visible())
                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
                shot = Path(__file__).resolve().parents[1] / ".pytest-tmp/admin-candidate-queue.png"
                shot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
                self.assertEqual(errors, [])
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
