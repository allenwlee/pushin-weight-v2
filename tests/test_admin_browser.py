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
    def test_frozen_run_has_separate_membership_scoped_tabs(self):
        from datetime import timedelta

        from core.models import OfficialCompanyAttempt
        from core.official_company_accounts import POLICY_VERSION
        from core.official_company_requalification import initialize_cohort
        from tests.test_official_company_requalification import manifest, state

        fresh, awaiting, pending, previous, outside, uncertain, rejected, failed, excluded = [state(97801 + n) for n in range(9)]
        previous.decision = {"outcome": "accepted"}
        previous.save()
        initialize_cohort(manifest([fresh, awaiting, pending, previous, uncertain, rejected, failed, excluded]))
        for s in [fresh, previous, outside]:
            OfficialCompanyAttempt.objects.create(
                state=s, evidence_hash=s.evidence_hash, claim_token=f"frozen-browser-{s.pk}",
                status="completed", model="test-model", policy_version=POLICY_VERSION, reserved_usd=0,
                decision={"outcome": "accepted", "development_type": "agent",
                          "organization_name": "New Agent Company", "rationale": "Own agent development."},
            )
        awaiting.status = "retry_due"
        awaiting.last_error = "TimeoutError"
        awaiting.next_attempt_at = timezone.now() + timedelta(minutes=15)
        awaiting.save()
        OfficialCompanyAttempt.objects.create(
            state=awaiting, evidence_hash=awaiting.evidence_hash, claim_token="frozen-browser-retry",
            status="failed", error_code="TimeoutError", model="test-model",
            policy_version=POLICY_VERSION, reserved_usd=0,
        )
        for s, outcome in [(uncertain, "review_needed"), (rejected, "rejected")]:
            OfficialCompanyAttempt.objects.create(
                state=s, evidence_hash=s.evidence_hash, claim_token=f"frozen-other-{s.pk}",
                status="completed", model="test-model", policy_version=POLICY_VERSION, reserved_usd=0,
                decision={"outcome": outcome, "rationale": "Insufficient development evidence."},
            )
        failed.status = "review_needed"
        failed.save()
        OfficialCompanyAttempt.objects.create(
            state=failed, evidence_hash=failed.evidence_hash, claim_token="frozen-terminal",
            status="failed", error_code="ValueError", model="test-model",
            policy_version=POLICY_VERSION, reserved_usd=0,
        )
        import json

        from core.models import OfficialCompanyScan
        scan = OfficialCompanyScan.objects.get()
        cursor = json.loads(scan.cursor)
        cursor["excluded"][str(excluded.pk)] = "changed_evidence"
        scan.cursor = json.dumps(cursor)
        scan.save()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                for locale, title in [("en", "Frozen account run"), ("zh_hans", "固定账号扫描"), ("ja", "固定アカウントの再評価")]:
                    response = page.goto(self.live_server_url + "/admin/official-accounts/frozen-run?locale=" + locale)
                    self.assertEqual(response.status, 200)
                    self.assertTrue(page.get_by_role("heading", name=title, exact=True).is_visible())
                    self.assertEqual(page.locator('[data-frozen-tab]').count(), 3)
                    for tab, expected in [("newly", fresh), ("awaiting", awaiting), ("pending", pending)]:
                        page.locator(f'[data-frozen-tab="{tab}"]').click()
                        self.assertEqual(page.locator('[data-frozen-tab][aria-current="page"]').get_attribute('data-frozen-tab'), tab)
                        self.assertEqual(page.locator('[data-frozen-account]').count(), 1)
                        self.assertTrue(page.locator(f'[data-frozen-account="{expected.account_id}"]').is_visible())
                        self.assertIn("locale=" + locale, page.url)
                    for category, expected in [("previous", previous), ("uncertain", uncertain), ("rejected", rejected), ("failed", failed), ("excluded", excluded)]:
                        page.locator(f'[data-frozen-category="{category}"]').click()
                        self.assertEqual(page.locator('[data-frozen-category][aria-current="page"]').get_attribute('data-frozen-category'), category)
                        self.assertEqual(page.locator('[data-frozen-account]').count(), 1)
                        self.assertTrue(page.locator(f'[data-frozen-account="{expected.account_id}"]').is_visible())
                        self.assertIn("locale=" + locale, page.url)
                        if category == "failed":
                            self.assertTrue(page.get_by_text("ValueError", exact=True).is_visible())
                    page.set_viewport_size({"width": 390, "height": 844})
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
                    page.screenshot(path=str(Path(__file__).resolve().parents[1] / f".pytest-tmp/frozen-run-{locale}.png"), full_page=True)
                    page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(self.live_server_url + "/admin")
                self.assertTrue(page.locator('[data-frozen-run-link]').is_visible())
                self.assertLess(page.locator('[data-frozen-run-link]').bounding_box()['y'], 160)
                page.locator('[data-frozen-run-link]').focus()
                page.keyboard.press('Enter')
                page.wait_for_url('**/admin/official-accounts/frozen-run?**')
                page.goto(self.live_server_url + '/admin/official-accounts/frozen-run?locale=en')
                page.locator('[name=q]').fill(fresh.account.handle)
                page.get_by_role('button', name='Search', exact=True).click()
                self.assertEqual(page.locator('[data-frozen-account]').count(), 1)
                self.assertEqual(page.locator('[data-frozen-tab-count="newly"]').inner_text(), '1')
                page.locator('[name=q]').fill(outside.account.handle)
                page.get_by_role('button', name='Search', exact=True).click()
                self.assertEqual(page.locator('[data-frozen-account]').count(), 0)
            finally:
                browser.close()

    def test_qualification_rerun_progress_uses_fixed_cohort(self):
        from core.models import OfficialCompanyAttempt
        from core.official_company_accounts import POLICY_VERSION
        from core.official_company_requalification import initialize_cohort
        from tests.test_official_company_requalification import manifest, state

        a, b = state(97901), state(97902)
        initialize_cohort(manifest([a, b]))
        OfficialCompanyAttempt.objects.create(
            state=a, evidence_hash=a.evidence_hash, claim_token="rerun-browser", status="completed",
            model="test-model", policy_version=POLICY_VERSION, reserved_usd=0,
            decision={"outcome": "accepted", "development_type": "agent", "organization_name": "Agent Company"},
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                for locale in ["en", "zh_hans", "ja"]:
                    page.goto(self.live_server_url + "/admin?locale=" + locale)
                    self.assertTrue(page.locator('#qualification-rerun').is_visible())
                    for key, expected in [("population", "2"), ("completed", "1"), ("qualified", "1"), ("newly_qualified", "1"), ("agent", "1"), ("harness", "0")]:
                        self.assertEqual(page.locator(f'[data-rerun-count="{key}"]').inner_text(), expected)
                    page.set_viewport_size({"width": 390, "height": 844})
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
                    shot = Path(__file__).resolve().parents[1] / f".pytest-tmp/admin-rerun-{locale}.png"
                    shot.parent.mkdir(exist_ok=True)
                    page.screenshot(path=str(shot), full_page=True)
                    page.set_viewport_size({"width": 1440, "height": 1000})
            finally:
                browser.close()

    def test_failed_and_tracked_tabs_do_not_mix_with_company_review(self):
        from core.models import BrandAccount, OfficialCompanyAttempt, Role
        from core.official_company_candidates import CANDIDATE_POLICY

        states = {}
        for number, handle, error in [
            (97201, "ordinary_review", "human_review_required"),
            (97202, "invalid_eval", "ValueError"),
            (97203, "provider_failed", "DeepInfraPermanentError"),
            (97204, "tracked_company", "already_tracked"),
        ]:
            state = OfficialCompanyAccountState.objects.create(
                account=Account.objects.create(author_id=str(number), handle=handle),
                status="review_needed", evidence_hash="a" * 64,
                candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY,
                last_error=error, model="test-model",
                decision={"organization_name": handle},
            )
            states[number] = state
            if number != 97204:
                OfficialCompanyAttempt.objects.create(
                    state=state, evidence_hash=state.evidence_hash,
                    claim_token=str(number), policy_version="test", model="test-model",
                    status="completed" if number == 97201 else "failed", reserved_usd=0,
                    error_code="" if number == 97201 else error,
                )
        role, _ = Role.objects.get_or_create(key="official")
        for name in ["tracked_alpha", "tracked_beta"]:
            BrandAccount.objects.create(
                account=states[97204].account,
                brand=Brand.objects.create(nickname=name), role=role,
            )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                for locale, failed_label, tracked_label in [
                    ("en", "Failed evaluations", "Already tracked"),
                    ("zh_hans", "评估失败", "已追踪"),
                    ("ja", "評価失敗", "追跡済み"),
                ]:
                    page.goto(self.live_server_url + "/admin?accounts_tab=review&locale=" + locale)
                    self.assertTrue(page.locator('[data-admin-candidate="97201"]').is_visible())
                    for number in [97202, 97203, 97204]:
                        self.assertEqual(page.locator(f'[data-admin-candidate="{number}"]').count(), 0)
                    self.assertIn(failed_label, page.locator('[data-account-tab="failed"]').inner_text())
                    self.assertIn(tracked_label, page.locator('[data-account-tab="tracked"]').inner_text())
                    page.locator('[data-account-tab="failed"]').focus()
                    page.keyboard.press("Enter")
                    page.wait_for_url("**accounts_tab=failed**")
                    self.assertEqual(page.locator('[data-account-tab="failed"]').get_attribute("aria-current"), "page")
                    self.assertEqual(page.locator('[data-candidate-count="failed_evaluations"]').inner_text(), "2")
                    self.assertEqual(page.locator('select[name="candidate_status"]').count(), 0)
                    for number, error in [(97202, "ValueError"), (97203, "DeepInfraPermanentError")]:
                        row = page.locator(f'[data-admin-candidate="{number}"]')
                        self.assertTrue(row.is_visible())
                        row.locator("summary").click()
                        self.assertTrue(row.get_by_text(error, exact=True).is_visible())
                    page.locator('input[name="candidate_q"]').fill("invalid_eval")
                    page.locator('button[type="submit"]').first.click()
                    self.assertTrue(page.locator('[data-admin-candidate="97202"]').is_visible())
                    self.assertEqual(page.locator('[data-admin-candidate="97203"]').count(), 0)
                    page.locator('input[name="candidate_q"]').fill("")
                    page.locator('button[type="submit"]').first.click()
                    page.locator('[data-account-tab="tracked"]').click()
                    self.assertTrue(page.locator('[data-admin-candidate="97204"]').is_visible())
                    self.assertEqual(page.locator('[data-candidate-count="already_tracked"]').inner_text(), "1")
                    self.assertEqual(page.locator('[data-admin-candidate="97202"]').count(), 0)
                    self.assertTrue(page.get_by_text("tracked_alpha, tracked_beta").is_visible())
                    page.set_viewport_size({"width": 390, "height": 844})
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
                    shot = Path(__file__).resolve().parents[1] / f".pytest-tmp/admin-tracked-{locale}.png"
                    shot.parent.mkdir(exist_ok=True)
                    page.screenshot(path=str(shot), full_page=True)
                    page.locator('[data-account-tab="failed"]').click()
                    page.screenshot(path=str(shot.with_name(f"admin-failed-{locale}.png")), full_page=True)
                    page.set_viewport_size({"width": 1440, "height": 1000})
            finally:
                browser.close()

    def test_official_found_and_review_tabs_separate_accounts(self):
        from core.official_company_candidates import CANDIDATE_POLICY

        for identifier, handle, status, model in [
            ("97101", "verified_lab", "registered", "test-model"),
            ("97102", "review_lab", "review_needed", "test-model"),
            ("97103", "settled_lab", "accepted", "owner-attestation"),
            ("97104", "waiting_lab", "pending", ""),
            ("97105", "historical_add", "rejected", "test-model"),
            ("97106", "unsettled_accept", "accepted", "test-model"),
        ]:
            state = OfficialCompanyAccountState.objects.create(
                account=Account.objects.create(author_id=identifier, handle=handle),
                status=status, model=model, evidence_hash="a" * 64,
                candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY,
                decision={"outcome": "accepted", "organization_name": handle,
                          "rationale": "Stored evidence for " + handle},
            )
            if identifier == "97105":
                OfficialCompanyListIntent.objects.create(
                    account=state.account, state=state, evidence_hash=state.evidence_hash,
                    list_id=2067062923525275922, status="suppressed",
                    add_acknowledged_at=timezone.now(),
                )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                page.goto(self.live_server_url + "/admin?locale=en")
                shot = Path(__file__).resolve().parents[1] / ".pytest-tmp/admin-tabs.png"
                shot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
                self.assertTrue(page.locator('[data-account-tab="found"]').is_visible())
                self.assertEqual(page.locator('[data-account-tab="found"]').get_attribute("aria-current"), "page")
                self.assertTrue(page.locator('[data-admin-account="97101"]').is_visible())
                self.assertEqual(page.locator('[data-admin-account="97101"] small').inner_text(), "97101")
                self.assertTrue(page.locator('[data-admin-account="97103"]').is_visible())
                self.assertEqual(page.locator('[data-admin-count="found"]').inner_text(), "2")
                self.assertEqual(page.locator('[data-admin-account="97102"]').count(), 0)
                self.assertEqual(page.locator('[data-admin-account="97105"]').count(), 0)
                page.locator('[data-account-tab="review"]').focus()
                page.keyboard.press("Enter")
                page.wait_for_url("**accounts_tab=review**")
                self.assertTrue(page.locator('[data-admin-candidate="97102"]').is_visible())
                self.assertTrue(page.locator('[data-admin-candidate="97106"]').is_visible())
                self.assertEqual(page.locator('[data-admin-account="97101"]').count(), 0)
                self.assertEqual(page.locator('select[name="candidate_status"]').count(), 0)
                page.get_by_label("Search candidates").fill("review_lab")
                page.get_by_role("button", name="Apply filters").click()
                self.assertEqual(page.locator('[data-account-tab="review"]').get_attribute("aria-current"), "page")
                self.assertTrue(page.locator('[data-admin-candidate="97102"]').is_visible())
                self.assertEqual(page.locator('[data-admin-candidate="97106"]').count(), 0)
                page.get_by_label("Search candidates").fill("")
                page.get_by_role("button", name="Apply filters").click()
                page.locator('[data-account-tab="history"]').click()
                self.assertTrue(page.locator('[data-admin-account="97105"]').is_visible())
                page.locator('[data-account-tab="queue"]').click()
                self.assertTrue(page.locator('[data-admin-candidate="97104"]').is_visible())
                for locale, found, review in [
                    ("en", "Official accounts found", "Review needed"),
                    ("zh_hans", "已发现官方账号", "需审核"),
                    ("ja", "発見した公式アカウント", "要確認"),
                ]:
                    page.goto(self.live_server_url + "/admin?locale=" + locale)
                    self.assertIn(found, page.locator('[data-account-tab="found"]').inner_text())
                    self.assertIn(review, page.locator('[data-account-tab="review"]').inner_text())
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.locator('[data-account-tab="review"]').click()
                    self.assertTrue(page.locator('[data-admin-candidate="97102"]').is_visible())
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
                    page.screenshot(path=str(shot.with_name("admin-tabs-review-" + locale + ".png")), full_page=True)
                    page.locator('[data-account-tab="found"]').click()
                    self.assertTrue(page.locator('[data-admin-account="97101"]').is_visible())
                self.assertEqual(page.locator('[data-admin-account="97101"] small').inner_text(), "97101")
                page.goto(self.live_server_url + "/admin?locale=en")
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.screenshot(path=str(shot), full_page=True)
            finally:
                browser.close()

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
        from core.official_company_candidates import CANDIDATE_POLICY

        account = Account.objects.create(author_id="884", handle="candidate_lab")
        OfficialCompanyAccountState.objects.create(
            account=account, status="review_needed", evidence_hash="a" * 64,
            candidate_priority=1, candidate_policy_version=CANDIDATE_POLICY,
            last_error="human_review_required",
            decision={"outcome": "accepted", "organization_name": "Candidate Lab",
                      "rationale": "Candidate evidence requiring owner review."},
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                response = page.goto(self.live_server_url + "/admin?locale=en")
                self.assertEqual(response.status, 200)
                self.assertEqual(page.locator('[data-admin-count="found"]').inner_text(), "0")
                self.assertEqual(page.locator('[data-admin-count="registered"]').inner_text(), "0")
                page.locator('[data-account-tab="review"]').click()
                row = page.locator('[data-admin-candidate="884"]')
                self.assertTrue(row.is_visible())
                self.assertTrue(row.get_by_text("Needs human review", exact=True).is_visible())
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
                page.goto(self.live_server_url + "/admin?locale=en")
                self.assertTrue(page.locator('[data-admin-account="92103"]').get_by_text("Add acknowledged", exact=True).is_visible())
                self.assertEqual(page.locator('[data-admin-account="92103"]').get_by_role("link", name="examplelab/speech", exact=True).first.get_attribute("href"), "https://huggingface.co/examplelab/speech")
                page.locator('[data-account-tab="queue"]').click()
                page.get_by_label("Candidate status").select_option("hf_verified")
                page.get_by_role("button", name="Apply filters").click()
                queue = page.locator("#candidate-queue")
                self.assertEqual(queue.locator('[data-candidate-count="hf_verified"]').inner_text(), "1")
                self.assertEqual(queue.locator('[data-candidate-count="review_needed"]').inner_text(), "0")
                row = queue.locator('[data-admin-candidate="92103"]')
                self.assertTrue(row.get_by_text("Registered", exact=True).is_visible())
                self.assertEqual(row.get_by_role("link", name="examplelab/speech").get_attribute("href"), "https://huggingface.co/examplelab/speech")
                page.locator('[data-account-tab="found"]').click()
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
        BrandAccount.objects.create(account=Account.x.get(author_id="92101"), brand=Brand.objects.create(nickname="known_model"), role=role)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = self._context(browser).new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(self.live_server_url + "/admin?accounts_tab=queue&locale=en")
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
                    page.goto(self.live_server_url + "/admin?accounts_tab=queue&locale=" + locale)
                    self.assertTrue(page.get_by_role("heading", name=title, exact=True).is_visible())
                page.goto(self.live_server_url + "/admin?accounts_tab=queue&locale=en")
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
