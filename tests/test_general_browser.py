"""Real-route General controls, layout, and response-order regression checks."""

import json
import os
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest
from bridgewright.assurance.engine import assess_evidence, compile_obligations
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import expect, sync_playwright

from core.models import Event, Opportunity, TimeZone
from tests.general_helpers import NOW, classified_post, saved_commentary
from tests.ui_assurance.general import load_general_declaration, write_general_evidence

pytestmark = pytest.mark.requires_postgres
ARTIFACTS = (
    Path(__file__).resolve().parents[1] / ".context/g5-integration-20261008/browser"
)
CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures/general_feed_contract.json").read_text()
)


@override_settings(
    SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"]
)
class GeneralBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        for post_id, category in CONTRACT["sections"].items():
            saved_commentary(classified_post(post_id, category))
        saved_commentary(classified_post(CONTRACT["closed_job"], brand="claude"))
        ARTIFACTS.mkdir(parents=True, exist_ok=True)

    def browser(self, pw):
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        return pw.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )

    def test_populated_calendar_and_free_cards_render_after_timezone_cutover(self):
        TimeZone.objects.get_or_create(code="Asia/Tokyo")
        Event.objects.create(
            brand_id="qwen", source_post_id="6100", title="Timezone workshop",
            organizer_name="Qwen", source_timezone_reference_id="Asia/Tokyo",
            first_seen_at=NOW, last_seen_at=NOW, event_identity="browser-zone-event",
        )
        Opportunity.objects.create(
            brand_id="qwen", source_post_id="6101", sponsor_name="Qwen",
            opportunity_type="free_credits", action_type="apply", benefit_type="credits",
            raw_payload={"source_timezone": "CST"},
            first_seen_at=NOW, last_seen_at=NOW, opportunity_identity="browser-zone-offer",
        )
        with sync_playwright() as pw:
            browser = self.browser(pw)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                for locale in ("en", "zh_hans", "ja"):
                    response = page.goto(f"{self.live_server_url}/general/?lang={locale}")
                    self.assertEqual(response.status, 200)
                    for section, post_id, zone in (
                        ("calendar", "6100", "Asia/Tokyo"),
                        ("free", "6101", "CST"),
                    ):
                        card = page.locator(f'#{section} [data-post-id="{post_id}"]')
                        expect(card).to_be_visible()
                        self.assertGreater(card.bounding_box()["width"], 100)
                        payload = page.request.get(
                            f"{self.live_server_url}/general/feed/?section={section}&lang={locale}"
                        )
                        self.assertEqual(payload.status, 200)
                        self.assertEqual(payload.json()["items"][0]["facts"][0]["timezone"], zone)
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_closed_weights_notice_preserves_the_independent_open_selection(self):
        with sync_playwright() as pw:
            browser = self.browser(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            requests = []
            page.on("request", lambda request: requests.append(request.url))
            for locale, message, width in (
                ("en", "Open Weights Coming Soon!", 1280),
                ("en", "Open Weights Coming Soon!", 390),
                ("zh_hans", "开放权重即将推出！", 1280),
                ("zh_hans", "开放权重即将推出！", 390),
                ("ja", "オープンウェイト、近日公開！", 1280),
                ("ja", "オープンウェイト、近日公開！", 390),
            ):
                page.set_viewport_size({"width": width, "height": 800})
                page.goto(f"{self.live_server_url}/general/?lang={locale}&weights=open")
                opened = page.locator('.primary-settings [data-value="open"]')
                closed = page.locator('.primary-settings [data-value="closed"]')
                notice = page.locator("#weights-coming-soon")
                for location in (".primary-settings", "#general-settings"):
                    if location == "#general-settings":
                        if width == 390:
                            page.locator(".mobile-nav-toggle").click()
                        page.locator("#general-settings summary").click()
                    trigger = page.locator(f'{location} [data-value="closed"]')
                    before_url = page.url
                    before_requests = len(requests)
                    trigger.focus()
                    page.keyboard.press("Space")
                    expect(notice).to_be_visible()
                    popup, anchor = notice.bounding_box(), trigger.bounding_box()
                    gap = min(
                        abs(popup["y"] - anchor["y"] - anchor["height"]),
                        abs(anchor["y"] - popup["y"] - popup["height"]),
                    )
                    assert gap <= 12, "Notice must sit beside the invoking toggle"
                    assert popup["x"] >= 8 and popup["y"] >= 8
                    assert popup["x"] + popup["width"] <= width - 8
                    assert popup["y"] + popup["height"] <= 792
                    expect(notice.locator("p")).to_have_text(message)
                    expect(opened).to_have_attribute("aria-pressed", "true")
                    expect(closed).to_have_attribute("aria-pressed", "true")
                    expect(page.locator('#jobs [data-post-id="6102"]')).to_have_count(1)
                    page.keyboard.press("Escape")
                    expect(notice).not_to_be_visible()
                    expect(closed).to_have_attribute("aria-pressed", "false")
                    expect(opened).to_have_attribute("aria-pressed", "true")
                    expect(trigger).to_be_focused()
                    assert page.url == before_url
                    assert not any(
                        "/general/feed/" in url for url in requests[before_requests:]
                    )
                    if location == "#general-settings" and width == 390:
                        page.keyboard.press("Escape")
                opened.click()
                expect(opened).to_have_attribute("aria-pressed", "false")
                expect(page.locator("#jobs [data-post-id]")).to_have_count(0)
                closed.click()
                expect(notice).to_be_visible()
                notice.locator("button").click()
                expect(opened).to_have_attribute("aria-pressed", "false")
                expect(closed).to_have_attribute("aria-pressed", "false")
                page.reload()
                expect(opened).to_have_attribute("aria-pressed", "false")
                expect(page.locator("#jobs [data-post-id]")).to_have_count(0)
                opened.click()
                expect(page.locator('#jobs [data-post-id="6102"]')).to_have_count(1)
            page.locator(".mobile-nav-toggle").click()
            page.locator("#general-settings summary").click()
            page.locator('#general-settings [data-value="closed"]').click()
            page.set_viewport_size({"width": 1280, "height": 800})
            expect(page.locator("body")).to_have_attribute("data-nav", "rail")
            popup = notice.bounding_box()
            anchor = closed.bounding_box()
            assert abs(popup["y"] - anchor["y"] - anchor["height"]) <= 12
            browser.close()

    def test_geometry_controls_locales_and_mobile_keyboard(self):
        with sync_playwright() as pw:
            browser = self.browser(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(
                f"{self.live_server_url}/general/?lang=en", wait_until="networkidle"
            )
            assert page.locator(".masthead").bounding_box()["y"] == 0
            assert page.locator(".masthead").bounding_box()["height"] == 48.5
            assert page.locator("#jobs .card-link").count() == 1
            rectangles = {}
            for width in (1440, 1280, 900, 390):
                page.set_viewport_size({"width": width, "height": 900})
                for nav_state in ("rail", "expanded"):
                    if (
                        width > 700
                        and page.locator("body").get_attribute("data-nav") != nav_state
                    ):
                        page.locator(".left-nav [data-nav-toggle]").click()
                    page.locator(
                        '.primary-settings [data-pref="audience"][data-value="human"]'
                    ).click()
                    human = page.locator(".panel").evaluate_all(
                        "els => els.map(el => { const r=el.getBoundingClientRect(); return [r.x,r.y,r.width,r.height]; })"
                    )
                    assert len(human) == 6 and all(
                        row[2] > 0 and row[3] > 0 for row in human
                    )
                    page.screenshot(
                        path=str(ARTIFACTS / f"general-{width}-{nav_state}-human.png"),
                        full_page=True,
                    )
                    page.locator(
                        '.primary-settings [data-pref="audience"][data-value="agent"]'
                    ).click()
                    agent = page.locator(".panel").evaluate_all(
                        "els => els.map(el => { const r=el.getBoundingClientRect(); return [r.x,r.y,r.width,r.height]; })"
                    )
                    assert agent == human
                    assert not page.locator("#jobs .human-pane").is_visible()
                    assert page.locator("#jobs .agent-pane").is_visible()
                    assert page.locator("[data-identity-article]").inner_text() == "an"
                    assert not page.evaluate(
                        "document.documentElement.scrollWidth > innerWidth"
                    )
                    page.screenshot(
                        path=str(ARTIFACTS / f"general-{width}-{nav_state}-agent.png"),
                        full_page=True,
                    )
                    rectangles[f"{width}-{nav_state}"] = {
                        "human": human,
                        "agent": agent,
                    }
            page.locator(".mobile-nav-toggle").click()
            assert page.locator(".left-nav").is_visible()
            assert page.locator(".general-shell").evaluate("el => el.inert")
            page.keyboard.press("Escape")
            expect(page.locator(".mobile-nav-toggle")).to_be_focused()
            assert page.locator("body").get_attribute("data-nav") == "rail"
            for locale, title in (
                ("zh-cn", "福利"),
                ("ja", "無料・特典"),
                ("en", "Free stuff"),
            ):
                page.goto(f"{self.live_server_url}/general/?lang={locale}")
                expect(page.locator("#title-free")).to_have_text(title)
                assert not page.evaluate(
                    "document.documentElement.scrollWidth > innerWidth"
                )
            assert errors == []
            (ARTIFACTS / "geometry.json").write_text(json.dumps(rectangles, indent=2))
            browser.close()

    def _latest_weights_response_wins_and_failed_refresh_retains_content(
        self, runtime=None
    ):
        with nullcontext(runtime) if runtime else sync_playwright() as pw:
            browser = self.browser(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(
                f"{self.live_server_url}/general/?lang=en", wait_until="networkidle"
            )
            held = []

            def delay_empty(route):
                if "weights=none" in route.request.url:
                    held.append((route, route.fetch()))
                else:
                    route.continue_()

            page.route("**/general/feed/**", delay_empty)
            page.evaluate("""() => {
              window.AbortController = class { abort() {} };
              window.__generalParsed = 0;
              const fetch = window.fetch;
              window.fetch = async (...args) => {
                const response = await fetch(...args);
                const json = response.json.bind(response);
                response.json = async () => { const value = await json(); window.__generalParsed++; return value; };
                return response;
              };
            }""")
            page.locator(
                '.primary-settings [data-pref="weights"][data-value="open"]'
            ).click()
            expect(page.locator("#jobs")).to_have_attribute("aria-busy", "true")
            page.wait_for_function(
                "document.querySelectorAll('[aria-busy=true]').length === 4"
            )
            for _ in range(100):
                if len(held) == 4:
                    break
                page.wait_for_timeout(20)
            assert len(held) == 4
            page.locator(
                '.primary-settings [data-pref="weights"][data-value="open"]'
            ).click()
            expect(page.locator('#jobs [data-post-id="6102"]')).to_be_visible()
            expect(page.locator("#jobs")).not_to_have_attribute("aria-busy", "true")
            for route, response in held:
                route.fulfill(response=response)
            page.wait_for_function("window.__generalParsed === 8")
            assert page.locator('#jobs [data-post-id="6199"]').count() == 0
            page.unroute("**/general/feed/**")
            page.route(
                "**/general/feed/**",
                lambda route: route.fulfill(status=503, body="Unavailable"),
            )
            page.locator('[data-refresh="jobs"]').click()
            expect(page.locator("#jobs [data-feed-status]")).to_contain_text(
                "Previous results are still shown"
            )
            assert page.locator('#jobs [data-post-id="6102"]').is_visible()
            browser.close()

    def test_countdowns_resume_after_page_restoration(self):
        with patch("monitor.general_views.timezone.now", return_value=NOW), sync_playwright() as pw:
            browser = self.browser(pw)
            page = browser.new_page()
            page.clock.install(time=NOW)
            page.goto(f"{self.live_server_url}/general/?lang=en")
            label = page.locator("#jobs [data-time-label]").first
            expect(label).to_have_text("Just listed 1 hrs ago!")
            page.evaluate(
                "window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}))"
            )
            page.clock.fast_forward(3_601_000)
            expect(label).to_have_text("Just listed 1 hrs ago!")
            page.evaluate(
                "window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))"
            )
            expect(label).to_have_text("Just listed 2 hrs ago!")
            page.clock.fast_forward(3_615_000)
            expect(label).to_have_text("Just listed 3 hrs ago!")
            browser.close()

    def test_signed_in_navigation_logs_out_and_restores_anonymous_preferences(self):
        user = get_user_model().objects.create_user(username="g5-browser-reader")
        self.client.force_login(user)
        with sync_playwright() as pw:
            browser = self.browser(pw)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            context.add_cookies(
                [
                    {
                        "name": "sessionid",
                        "value": self.client.cookies["sessionid"].value,
                        "url": self.live_server_url,
                    }
                ]
            )
            page = context.new_page()
            page.goto(f"{self.live_server_url}/general/?lang=en")
            namespace = page.locator("body").get_attribute("data-preferences-namespace")
            assert namespace.startswith("user-")
            page.locator(
                '.primary-settings [data-pref="weights"][data-value="open"]'
            ).click()
            expect(page.locator("#jobs [data-post-id]")).to_have_count(0)
            page.locator(".left-nav form button").click()
            expect(page.locator("body")).to_have_attribute(
                "data-preferences-namespace", "anonymous"
            )
            expect(page.locator('#jobs [data-post-id="6102"]')).to_be_visible()
            assert page.locator(".left-nav form").count() == 0
            assert page.locator('.left-nav a[href^="/accounts/login/"]').count() == 1
            browser.close()

    def test_continuation_and_navigation_persist_through_reload(self):
        for number in range(22):
            saved_commentary(classified_post(str(7000 + number)))
        with sync_playwright() as pw:
            browser = self.browser(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(f"{self.live_server_url}/general/?lang=en")
            assert page.locator("#jobs [data-post-id]").count() == 20
            page.locator('[data-more="jobs"]').click()
            expect(page.locator("#jobs [data-post-id]")).to_have_count(23)
            ids = page.locator("#jobs [data-post-id]").evaluate_all(
                "rows => rows.map(row => row.dataset.postId)"
            )
            assert len(ids) == len(set(ids))
            expect(page.locator('[data-more="jobs"]')).to_be_hidden()
            page.locator(".left-nav [data-nav-toggle]").click()
            expect(page.locator("body")).to_have_attribute("data-nav", "expanded")
            page.reload()
            expect(page.locator("body")).to_have_attribute("data-nav", "expanded")
            page.locator("#general-settings summary").click()
            page.locator(
                '#general-settings [data-pref="timezone"][data-value="ca"]'
            ).click()
            expect(
                page.locator('.header-settings [data-pref="timezone"][data-value="ca"]')
            ).to_have_attribute("aria-current", "true")
            browser.close()

    def test_declared_controls_and_races_against_the_real_page(self):
        declaration = load_general_declaration()
        results = []
        defaults = {
            control.id: control.initial_value for control in declaration.controls
        }
        with sync_playwright() as pw:
            browser = self.browser(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 800})

            def reset():
                page.goto(
                    f"{self.live_server_url}/general/?lang=en&weights=open&audience=human"
                )
                if page.locator("body").get_attribute("data-nav") != "rail":
                    page.locator(".left-nav [data-nav-toggle]").click()
                return dict(defaults)

            def apply(state, key, value):
                if key == "navigation":
                    if page.locator("body").get_attribute("data-nav") != value:
                        page.locator(".left-nav [data-nav-toggle]").click()
                elif key == "weights":
                    opened = page.locator('.primary-settings [data-value="open"]')
                    if (opened.get_attribute("aria-pressed") == "true") != (
                        value == "open"
                    ):
                        opened.click()
                    expect(page.locator("#jobs")).not_to_have_attribute(
                        "aria-busy", "true"
                    )
                elif key == "pulse_reports":
                    previous_audience = state["audience"]
                    if previous_audience == "agent":
                        page.locator('.primary-settings [data-value="human"]').click()
                    reports = page.locator(".pulse-published-reports")
                    if reports.evaluate("element => element.open") != (value == "open"):
                        reports.locator(":scope > summary").click()
                    if previous_audience == "agent":
                        page.locator('.primary-settings [data-value="agent"]').click()
                else:
                    pref = "lang" if key == "locale" else key
                    locator = page.locator(
                        f'[data-pref="{pref}"][data-value="{value}"]:visible'
                    )
                    if locator.count() == 0:
                        page.locator("#general-settings > summary").click()
                    page.locator(
                        f'[data-pref="{pref}"][data-value="{value}"]:visible'
                    ).first.click()
                    if key == "weights":
                        expect(page.locator("#jobs")).not_to_have_attribute(
                            "aria-busy", "true"
                        )
                    if key == "locale":
                        expect(page.locator("html")).to_have_attribute("lang", value)
                        state["pulse_reports"] = "closed"
                state[key] = value

            def check(state):
                expect(page.locator(".pulse-framework")).to_have_attribute(
                    "data-pulse-status", "unavailable"
                )
                assert page.locator("[data-forecast-value], [data-forecast-probability]").count() == 0
                assert page.locator(".pulse-published-reports").evaluate(
                    "element => element.open"
                ) == (state["pulse_reports"] == "open")
                assert (
                    page.locator("body").get_attribute("data-audience")
                    == state["audience"]
                )
                assert (
                    page.locator("body").get_attribute("data-nav")
                    == state["navigation"]
                )
                assert (
                    page.locator(".left-nav").bounding_box()["width"]
                    == CONTRACT["desktop_nav_width"][state["navigation"]]
                )
                expect(page.locator("#title-free")).to_have_text(
                    CONTRACT["free_titles"][state["locale"]]
                )
                expected_post = CONTRACT["jobs_by_weights"][state["weights"]]
                if expected_post:
                    assert (
                        page.locator(f'#jobs [data-post-id="{expected_post}"]').count()
                        == 1
                    )
                else:
                    assert page.locator("#jobs [data-post-id]").count() == 0
                for key in ("weights", "audience"):
                    choices = page.locator(f'[data-pref="{key}"][aria-current]')
                    expected_values = (
                        []
                        if key == "weights" and state[key] == "none"
                        else [state[key], state[key]]
                    )
                    assert choices.count() == len(expected_values)
                    assert (
                        choices.evaluate_all("els => els.map(el => el.dataset.value)")
                        == expected_values
                    )
                assert not page.evaluate(
                    "document.documentElement.scrollWidth > innerWidth"
                )

            for obligation in compile_obligations(declaration):
                parts = obligation.id.split("/")
                try:
                    state = reset()
                    if parts[0] in {"transition", "inverse"}:
                        apply(state, parts[1], parts[2])
                        check(state)
                        if parts[0] == "inverse":
                            apply(state, parts[1], parts[3])
                            check(state)
                    elif parts[0] in {"tway", "ordered"}:
                        for assignment in parts[2:]:
                            key, value = assignment.split(
                                "=" if parts[0] == "tway" else ":", 1
                            )
                            apply(state, key, value)
                            check(state)
                    elif parts[0] == "race":
                        self._latest_weights_response_wins_and_failed_refresh_retains_content(
                            pw
                        )
                    elif parts[0] == "invariant":
                        if parts[1] == "closed-weights-unavailable":
                            before_url = page.url
                            page.locator(
                                '.primary-settings [data-value="closed"]'
                            ).click()
                            expect(page.locator("#weights-coming-soon p")).to_have_text(
                                "Open Weights Coming Soon!"
                            )
                            expect(
                                page.locator('.primary-settings [data-value="open"]')
                            ).to_have_attribute("aria-pressed", "true")
                            page.locator("#weights-coming-soon button").click()
                            expect(
                                page.locator('.primary-settings [data-value="closed"]')
                            ).to_have_attribute("aria-pressed", "false")
                            assert page.url == before_url
                        check(state)
                    else:
                        raise AssertionError(f"Unhandled obligation: {obligation.id}")
                except Exception:
                    results.append({"obligation_id": obligation.id, "status": "failed"})
                    write_general_evidence(
                        declaration, results, ARTIFACTS / "general-evidence.json"
                    )
                    raise
                results.append({"obligation_id": obligation.id, "status": "passed"})
            browser.close()
        evidence = write_general_evidence(
            declaration, results, ARTIFACTS / "general-evidence.json"
        )
        assessment = assess_evidence(declaration, evidence)
        (ARTIFACTS / "general-assessment.json").write_text(
            assessment.model_dump_json(indent=2)
        )
        assert assessment.status == "clean"
        assert assessment.coverage.passed == len(results)

    def test_post_links_and_baseline_content_work_without_javascript(self):
        with sync_playwright() as pw:
            browser = self.browser(pw)
            page = browser.new_page(java_script_enabled=False)
            page.goto(f"{self.live_server_url}/general/?lang=en")
            link = page.locator("#jobs .card-link")
            assert "commentary=" in link.get_attribute("href")
            link.click()
            assert "/posts/6102/" in page.url
            expect(page.locator("#commentary-title")).to_have_text("Commentary")
            expect(page.locator("#original-title")).to_have_text("Original source")
            assert (
                page.locator('link[rel="canonical"]').get_attribute("href") == page.url
            )
            browser.close()

    def test_published_editorial_sources_and_saved_links_preserve_panel_geometry(self):
        from unittest.mock import patch

        from tests.test_general_editorial import published_story

        publications = {
            locale: {
                track: published_story(track, locale, featured=track == "chatter")
                for track in ("chatter", "pulse")
            }
            for locale in ("en", "zh-cn", "ja")
        }
        source_urls = {
            text.pk: list(
                text.sources.order_by("position").values_list("url_snapshot", flat=True)
            )
            for texts in publications.values()
            for text in texts.values()
        }
        with (
            patch.dict(
                os.environ,
                {
                    "ORIGINAL_CONTENT_STORAGE": "shared",
                    "EDITORIAL_PUBLIC_ENABLED": "true",
                },
            ),
            sync_playwright() as pw,
        ):
            browser = self.browser(pw)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for width in (1280, 390):
                page.set_viewport_size({"width": width, "height": 900})
                for requested, locale in (
                    ("en", "en"),
                    ("zh_hans", "zh-cn"),
                    ("ja", "ja"),
                ):
                    page.goto(
                        f"{self.live_server_url}/general/?lang={requested}&audience=human"
                    )
                    expect(page.locator('#jobs [data-post-id="6102"]')).to_have_count(1)
                    rectangles = page.locator("section.panel").evaluate_all(
                        "els => els.map(e => e.getBoundingClientRect().toJSON())"
                    )
                    assert len(rectangles) == 6
                    expect(page.locator(".pulse-framework")).to_be_visible()
                    expect(page.locator(".pulse-framework")).to_have_attribute(
                        "data-pulse-status", "unavailable"
                    )
                    reports = page.locator(".pulse-published-reports")
                    assert not reports.evaluate("element => element.open")
                    reports.locator(":scope > summary").focus()
                    page.keyboard.press("Enter")
                    assert reports.evaluate("element => element.open")
                    for track, text in publications[locale].items():
                        card = page.locator(
                            f'#{track} [data-edition-id="{text.public_id}"]'
                        )
                        expect(card.locator("h3")).to_have_text(text.headline)
                        expect(card.locator(".editorial-byline")).to_have_text(
                            text.secondary
                        )
                        expect(card.locator(".editorial-body")).to_contain_text(
                            "Final saved paragraph."
                        )
                        sources = card.locator(".editorial-sources")
                        expect(sources).to_have_attribute("data-source-count", "7")
                        sources.locator("summary").click()
                        links = sources.locator("li a")
                        expect(links).to_have_count(7)
                        expected = source_urls[text.pk]
                        assert (
                            links.evaluate_all("els => els.map(e => e.href)")
                            == expected
                        )
                        for link in links.all():
                            expect(link).to_be_visible()
                            assert link.bounding_box()["width"] > 0
                        href = card.locator("h3 a").get_attribute("href")
                        assert str(text.public_id) in href
                        sources.locator("summary").click()
                    page.locator('.primary-settings [data-value="agent"]').click()
                    expect(page.locator("body")).to_have_attribute(
                        "data-audience", "agent"
                    )
                    assert (
                        page.locator("section.panel").evaluate_all(
                            "els => els.map(e => e.getBoundingClientRect().toJSON())"
                        )
                        == rectangles
                    )
                    page.locator('.primary-settings [data-value="human"]').click()
                    assert (
                        page.locator("section.panel").evaluate_all(
                            "els => els.map(e => e.getBoundingClientRect().toJSON())"
                        )
                        == rectangles
                    )
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                    # Follow the exact saved edition from the actual card.
                    page.locator("#pulse .editorial-headline a").first.click()
                    expect(page.locator("h1")).to_have_text(
                        publications[locale]["pulse"].headline
                    )
                    expect(page.locator(".source-attribution a")).to_have_count(7)
            assert errors == []
            browser.close()
