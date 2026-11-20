"""Real Chromium checks for release discovery and the shared local control API."""

import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import DatabaseError, connection
from django.test import override_settings
from playwright.sync_api import sync_playwright

from core.event_dossiers import add_claim, attach_source, create_dossier, identity_key
from core.models import (
    Brand,
    BrandCompany,
    Company,
    CompanyLabel,
    Post,
    Product,
    ProductType,
)
from monitor import pulse_control
from tests.test_pulse_readers import (
    historical_product,
    pending_release,
    reviewed_release,
)
from tests.test_pulse_views import identity_evidence_release, saved_category_release

pytestmark = pytest.mark.requires_postgres


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class PulseBrowserTests(StaticLiveServerTestCase):
    def test_pulse_uses_general_shell_and_light_cards(self):
        event = pending_release("browser-general-style", "Cedar Preview")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                self.assertEqual(page.goto(self.live_server_url + "/pulse?locale=en").status, 200)
                self.assertTrue(page.locator(".general-shell .masthead").is_visible())
                self.assertTrue(page.locator("#left-navigation").is_visible())
                card = page.locator(f'[data-pulse-event="{event.pk}"]')
                self.assertTrue(card.is_visible())
                self.assertEqual(card.evaluate("el => getComputedStyle(el).backgroundColor"), "rgb(255, 255, 255)")
                self.assertTrue(page.locator("body").evaluate("el => el.classList.contains('js-enabled')"))
                page.locator('.header-settings [data-pref="lang"][data-value="ja"]').click()
                self.assertTrue(page.get_by_role("heading", name="リリースの発見", exact=True).is_visible())
                page.set_viewport_size({"width": 390, "height": 900})
                toggle = page.locator(".mobile-nav-toggle")
                self.assertTrue(toggle.is_visible())
                toggle.click()
                self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
                self.assertTrue(page.locator("#left-navigation").is_visible())
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_saved_category_stays_reported_with_pending_product_identity(self):
        events = {
            "reported": saved_category_release("browser-category-reported", ["model-llm"]),
            "conflicting": saved_category_release("browser-category-conflicting", ["model-llm", "agent"]),
            "incomplete": saved_category_release("browser-category-incomplete", ["invalid-category"]),
        }
        localized = {
            "en": ("Reported category: Language model", "Product identity pending", "Category pending", "Sources report different categories: Agent / Language model.", "Category evidence is incomplete."),
            "zh_hans": ("来源报告的类别：语言模型", "产品身份待确认", "类别待确认", "来源报告了不同的类别：智能体 / 语言模型。", "类别证据不完整。"),
            "ja": ("報告された分類: 言語モデル", "製品の同一性は未確定", "分類未確定", "情報源ごとに報告された分類が異なります: エージェント / 言語モデル。", "分類の根拠が不完全です。"),
        }
        artifacts = Path(settings.BASE_DIR) / ".local/pulse-p3"
        artifacts.mkdir(exist_ok=True, parents=True)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                for width in (1440, 390):
                    page.set_viewport_size({"width": width, "height": 900})
                    for locale, labels in localized.items():
                        response = page.goto(self.live_server_url + "/pulse?locale=" + locale)
                        self.assertEqual(response.status, 200)
                        self.assertEqual(page.locator("[data-pulse-event]").count(), 3)
                        reported, identity_pending, category_pending, conflict, incomplete = labels
                        for state, event in events.items():
                            card = page.locator(f'[data-pulse-event="{event.pk}"]')
                            category = card.get_by_text(reported if state == "reported" else category_pending, exact=True)
                            self.assertTrue(category.is_visible())
                            self.assertGreater(category.bounding_box()["height"], 0)
                            self.assertTrue(card.get_by_text(identity_pending, exact=True).is_visible())
                            self.assertEqual(card.get_by_text(conflict, exact=True).count(), int(state == "conflicting"))
                            self.assertEqual(card.get_by_text(incomplete, exact=True).count(), int(state == "incomplete"))
                            if state == "conflicting":
                                self.assertTrue(card.get_by_text(conflict, exact=True).is_visible())
                            if state == "incomplete":
                                self.assertTrue(card.get_by_text(incomplete, exact=True).is_visible())
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
                    page.screenshot(path=str(artifacts / f"pulse-category-{width}.png"), full_page=True)
            finally:
                browser.close()

    def test_pending_resolved_dates_locales_and_source_navigation(self):
        pending = pending_release("browser-pending", "Cedar Preview")
        reviewed = reviewed_release("browser-review")
        unnamed = create_dossier(event_kind="product_release", identity_key=identity_key("browser", "unnamed"))
        brand = Brand.objects.create(nickname="browser-brand", display_name="Cedar Labs")
        company = Company.objects.create(nickname="browser-company")
        CompanyLabel.objects.create(company=company, locale_id="und", label="Cedar Research")
        BrandCompany.objects.create(brand=brand, company=company)
        for code in ("model-llm", "model-other", "agent", "harness", "other"):
            category, _ = ProductType.objects.get_or_create(code=code)
            product = Product.objects.create(display_name=code, product_type=category, brand=brand)
            reviewed_release("browser-" + code, product=product)
        identity_events = {kind: identity_evidence_release(kind) for kind in ("rejected", "lineage", "reported")}
        legacy_product = historical_product(display_name="Legacy product")
        legacy = reviewed_release("browser-legacy", product=legacy_product)
        identity_labels = {
            "en": ("Product identity pending", "Reported product identity — awaiting review", "Legacy category: model"),
            "zh_hans": ("产品身份待确认", "来源报告的产品身份 — 等待审核", "旧版类别：model"),
            "ja": ("製品の同一性は未確定", "情報源が報告した製品の同一性 — レビュー待ち", "旧分類: model"),
        }
        source = pending.sources.get()
        add_claim(source.pk, claim_kind="source_stated_release", scope_key="historical-date",
                  assertion_text="Released on the stated day", source_excerpt="Released on 2025-04-03",
                  extraction_version="browser-test", effective_precision="day", effective_date=date(2025, 4, 3))
        later = Post.objects.create(tweet_id="browser-later", text="A later discussion")
        attach_source(pending.pk, post_id=later.pk)
        artifacts = Path(settings.BASE_DIR) / ".local/pulse-p3"
        artifacts.mkdir(exist_ok=True, parents=True)
        timings = []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                for width in (1440, 390):
                    page.set_viewport_size({"width": width, "height": 900})
                    for locale, title in (("en", "Release discoveries"), ("zh_hans", "发布动态"), ("ja", "リリースの発見")):
                        response = page.goto(self.live_server_url + "/pulse?locale=" + locale)
                        self.assertEqual(response.status, 200)
                        self.assertTrue(page.get_by_role("heading", name=title, exact=True).is_visible())
                        self.assertEqual(page.locator("[data-pulse-event]").count(), 12)
                        self.assertEqual(page.get_by_text("Cedar Labs", exact=False).count(), 5)
                        self.assertEqual(page.get_by_text("Cedar Research", exact=False).count(), 5)
                        for event in (pending, reviewed, unnamed):
                            self.assertEqual(page.locator(f'[data-pulse-event="{event.pk}"]').count(), 1)
                        pending_label, reported_label, legacy_label = identity_labels[locale]
                        for kind, event in identity_events.items():
                            card = page.locator(f'[data-pulse-event="{event.pk}"]')
                            marker = card.get_by_text(reported_label if kind == "reported" else pending_label, exact=True)
                            self.assertTrue(marker.is_visible())
                            self.assertGreater(marker.bounding_box()["height"], 0)
                            if kind == "reported":
                                self.assertTrue(card.get_by_role("heading", name="Reported product", exact=True).is_visible())
                            else:
                                self.assertNotIn("Reported product", card.inner_text())
                                self.assertNotIn("Reported publisher", card.inner_text())
                                self.assertNotIn("Reported owner", card.inner_text())
                        self.assertTrue(page.locator(f'[data-pulse-event="{legacy.pk}"]').get_by_text(legacy_label, exact=True).is_visible())
                        self.assertIn("2025-04-03", page.locator(f'[data-pulse-event="{pending.pk}"]').inner_text())
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
                        self.assertEqual(page.locator('link[href="/static/pulse.css"]').count(), 1)
                        self.assertEqual(page.request.get(self.live_server_url + "/static/pulse.css").status, 200)
                        self.assertNotIn("PI-U", page.locator("body").inner_text())
                        timings.append({"width": width, "locale": locale, "duration_ms": page.evaluate("performance.getEntriesByType('navigation')[0].duration")})
                    page.screenshot(path=str(artifacts / f"pulse-{width}.png"), full_page=True)
                page.goto(self.live_server_url + f"/pulse/{pending.pk}/sources?locale=en")
                self.assertEqual(page.locator("[data-pulse-source]").count(), 2)
                post_link = page.locator(f'a[href="/posts/{later.pk}/?locale=en"]')
                self.assertTrue(post_link.is_visible())
                post_link.click()
                self.assertIn("A later discussion", page.locator("body").inner_text())
                self.assertEqual(errors, [])
            finally:
                browser.close()
        (artifacts / "browser-timings.json").write_text(json.dumps(timings, indent=2) + "\n")

    def test_empty_discoveries_and_reader_failure_have_distinct_visible_states(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                response = page.goto(self.live_server_url + "/pulse?locale=en")
                self.assertEqual(response.status, 200)
                empty = page.get_by_role("heading", name="No release discoveries yet", exact=True)
                self.assertTrue(empty.is_visible())
                self.assertGreater(empty.bounding_box()["height"], 0)
                self.assertEqual(page.get_by_role("alert").count(), 0)
                with patch("monitor.pulse_views.release_page", side_effect=DatabaseError("private fixture details")):
                    response = page.goto(self.live_server_url + "/pulse?locale=en")
                self.assertEqual(response.status, 503)
                alert = page.get_by_role("alert")
                self.assertTrue(alert.is_visible())
                self.assertGreater(alert.bounding_box()["height"], 0)
                self.assertIn("Release discoveries are temporarily unavailable", alert.inner_text())
                self.assertEqual(page.get_by_role("heading", name="No release discoveries yet", exact=True).count(), 0)
                self.assertNotIn("private fixture details", page.locator("body").inner_text())
            finally:
                browser.close()

    def test_pagination_uses_real_links_and_preserves_all_related_posts(self):
        events = [pending_release(f"browser-page-{i}") for i in range(28)]
        for i in range(27):
            post = Post.objects.create(tweet_id=f"browser-source-{i}", text="Later source")
            attach_source(events[0].pk, post_id=post.pk)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.goto(self.live_server_url + "/pulse?locale=en")
                first = page.locator("[data-pulse-event]").evaluate_all("els=>els.map(el=>el.dataset.pulseEvent)")
                self.assertEqual(len(first), 25)
                def add_discovery():
                    try:
                        pending_release("browser-new-between-pages")
                    finally:
                        connection.close()

                with ThreadPoolExecutor(max_workers=1) as executor:
                    executor.submit(add_discovery).result(timeout=10)
                page.locator("[data-pulse-next]").click()
                second = page.locator("[data-pulse-event]").evaluate_all("els=>els.map(el=>el.dataset.pulseEvent)")
                self.assertEqual(set(first + second), {str(event.pk) for event in events})
                self.assertEqual(len(first + second), 28)
                page.goto(self.live_server_url + f"/pulse/{events[0].pk}/sources?locale=en")
                self.assertEqual(page.locator("[data-pulse-source]").count(), 25)
                page.locator("[data-pulse-next]").click()
                self.assertEqual(page.locator("[data-pulse-source]").count(), 3)
            finally:
                browser.close()

    def test_processing_diagnostic_locales_preserve_custom_text(self):
        user = get_user_model().objects.create_user(username="diagnostic-browser-staff", is_staff=True)
        self.client.force_login(user)
        custom = "Operator note <script>window.unexpected=true</script>"
        with tempfile.TemporaryDirectory(prefix="pulse-diagnostic-") as directory, override_settings(PULSE_CONTROL_DIRECTORY=directory):
            pulse_control.initialize(directory=directory, state="running", actor="fixture", reason="Locale fixture")
            for stage, code in (("identity", "identity_processing_error"), ("classification", "classification_timeout")):
                pulse_control.record_diagnostic(stage=stage, code=code, message="Pulse processing needs investigation.")
            pulse_control.record_diagnostic(stage="identity", code="identity_processing_error", message=custom)
            before = (Path(directory) / "pulse-control.json").read_bytes()
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    context = browser.new_context(viewport={"width": 390, "height": 844})
                    context.add_cookies([{"name": settings.SESSION_COOKIE_NAME, "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value, "url": self.live_server_url}])
                    page = context.new_page()
                    for locale, language, message in (
                        ("en", "en", "Pulse processing needs investigation."),
                        ("zh_hans", "zh-hans", "Pulse 处理需要调查。"),
                        ("ja", "ja", "Pulse の処理状況を調査する必要があります。"),
                    ):
                        response = page.goto(self.live_server_url + "/admin?locale=" + locale)
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers["content-language"], language)
                        diagnostics = page.locator("[data-pulse-diagnostic]")
                        self.assertEqual(diagnostics.count(), 3)
                        messages = diagnostics.get_by_text(message, exact=True)
                        self.assertEqual(messages.count(), 2)
                        for index in range(2):
                            self.assertTrue(messages.nth(index).is_visible())
                            self.assertGreater(messages.nth(index).bounding_box()["height"], 0)
                        self.assertTrue(diagnostics.get_by_text(custom, exact=True).is_visible())
                        self.assertIsNone(page.evaluate("window.unexpected"))
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
                    artifacts = Path(settings.BASE_DIR) / ".local/pulse-p3"
                    artifacts.mkdir(exist_ok=True, parents=True)
                    page.screenshot(path=str(artifacts / "admin-diagnostics-ja.png"), full_page=True)
                finally:
                    browser.close()
            self.assertEqual((Path(directory) / "pulse-control.json").read_bytes(), before)

    def test_lineage_diagnostics_explain_pending_states_in_each_locale(self):
        user = get_user_model().objects.create_user(username="lineage-browser-staff", is_staff=True)
        self.client.force_login(user)
        codes = ("lineage_wakeup_budget_blocked", "lineage_wakeup_invalid_evidence", "lineage_nonx_pending")
        messages = {
            "en": ("Lineage recovery paused after reaching its processing limit.", "Some lineage evidence is invalid and needs investigation.", "Some non-X lineage evidence is pending; automatic recovery is not available yet."),
            "zh_hans": ("谱系恢复已达到处理上限并暂停。", "部分谱系证据无效，需要调查。", "部分非 X 谱系证据仍在等待处理；自动恢复尚不可用。"),
            "ja": ("系譜の復旧は処理上限に達したため一時停止しました。", "一部の系譜の証拠が無効なため、調査が必要です。", "X 以外の一部の系譜の証拠は処理待ちです。自動復旧はまだ利用できません。"),
        }
        with tempfile.TemporaryDirectory(prefix="pulse-lineage-") as directory, override_settings(PULSE_CONTROL_DIRECTORY=directory):
            pulse_control.initialize(directory=directory, state="running", actor="fixture", reason="Locale fixture")
            from monitor.pulse_processing import report_error

            for code in codes:
                report_error(stage="identity", code=code)
            pulse_control.record_diagnostic(stage="identity", code=codes[0], message="Custom operator note")
            before = (Path(directory) / "pulse-control.json").read_bytes()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    context = browser.new_context(viewport={"width": 390, "height": 844})
                    context.add_cookies([{"name": settings.SESSION_COOKIE_NAME, "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value, "url": self.live_server_url}])
                    page = context.new_page()
                    for locale, expected in messages.items():
                        response = page.goto(self.live_server_url + "/admin?locale=" + locale)
                        self.assertEqual(response.status, 200)
                        diagnostics = page.locator("[data-pulse-diagnostic]")
                        self.assertEqual(diagnostics.count(), 4)
                        for message in expected:
                            match = diagnostics.get_by_text(message, exact=True)
                            self.assertEqual(match.count(), 1)
                            self.assertTrue(match.is_visible())
                            self.assertGreater(match.bounding_box()["height"], 0)
                        self.assertTrue(diagnostics.get_by_text("Custom operator note", exact=True).is_visible())
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
                finally:
                    browser.close()
            self.assertEqual((Path(directory) / "pulse-control.json").read_bytes(), before)

    def test_real_control_request_acknowledgement_and_resume_across_processes(self):
        user = get_user_model().objects.create_user(username="pulse-browser-owner", is_staff=True)
        self.client.force_login(user)
        with tempfile.TemporaryDirectory(prefix="pulse-browser-") as directory, override_settings(PULSE_CONTROL_DIRECTORY=directory):
            pulse_control.initialize(directory=directory, state="running", actor="fixture", reason="Local integration test")
            pulse_control.acknowledge(1, boundary="local fixture boundary")
            pulse_control.record_diagnostic(stage="identity", code="review_needed", message="Review <script>window.unexpected=true</script>", observed=2, expected=1, references={"post_id": "legacy/imported-id"})
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    context = browser.new_context(viewport={"width": 390, "height": 844})
                    context.add_cookies([{"name": settings.SESSION_COOKIE_NAME, "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value, "url": self.live_server_url}])
                    page = context.new_page()
                    response = page.goto(self.live_server_url + "/admin?locale=en#pulse-control")
                    self.assertEqual(response.status, 200)
                    self.assertEqual(page.locator("[data-pulse-control-status]").get_attribute("data-pulse-control-status"), "running")
                    self.assertIsNone(page.evaluate("window.unexpected"))
                    diagnostic = page.locator("[data-pulse-diagnostic]")
                    self.assertTrue(diagnostic.get_by_text("Review <script>window.unexpected=true</script>", exact=True).is_visible())
                    self.assertEqual(diagnostic.get_by_role("link", name="Stored post", exact=True).count(), 0)
                    diagnostic.locator("summary").click()
                    self.assertTrue(diagnostic.locator("pre").is_visible())
                    self.assertIn("legacy/imported-id", diagnostic.locator("pre").inner_text())
                    page.locator('#pulse-control textarea[name="reason"]').fill("Investigate a candidate")
                    page.get_by_role("button", name="Request stop", exact=True).click()
                    self.assertEqual(page.locator("[data-pulse-control-status]").get_attribute("data-pulse-control-status"), "stop_requested")
                    self.assertEqual(page.locator("[data-pulse-ack-revision]").inner_text(), "1")
                    subprocess.run([sys.executable, "-c", "from monitor.pulse_control import acknowledge; import sys; acknowledge(2, boundary='separate local process', directory=sys.argv[1])", directory], cwd=settings.BASE_DIR, check=True, timeout=10)
                    page.reload()
                    self.assertEqual(page.locator("[data-pulse-control-status]").get_attribute("data-pulse-control-status"), "stopped")
                    page.locator('#pulse-control textarea[name="reason"]').fill("Continue after review")
                    page.get_by_role("button", name="Request resume", exact=True).click()
                    self.assertEqual(page.locator("[data-pulse-control-status]").get_attribute("data-pulse-control-status"), "resume_requested")
                    subprocess.run([sys.executable, "-c", "from monitor.pulse_control import acknowledge; import sys; acknowledge(3, boundary='restarted local process', directory=sys.argv[1])", directory], cwd=settings.BASE_DIR, check=True, timeout=10)
                    page.reload()
                    self.assertEqual(page.locator("[data-pulse-control-status]").get_attribute("data-pulse-control-status"), "running")
                    self.assertFalse(page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
                    page.screenshot(path=str(Path(settings.BASE_DIR) / ".local/pulse-p3/admin-mobile.png"), full_page=True)
                finally:
                    browser.close()
