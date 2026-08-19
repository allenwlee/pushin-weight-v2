"""Real-browser regression net for the standalone V23 interaction mockup."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
MOCKUP = REPO_ROOT / "docs" / "ideation" / "mockups" / "v23.html"
TIME_24H = re.compile(r"^\d{2}:\d{2}$")


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def _serve_mockup() -> Iterator[str]:
    assert MOCKUP.is_file(), f"V23 mockup is missing: {MOCKUP}"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(_QuietStaticHandler, directory=str(MOCKUP.parent)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{MOCKUP.name}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _locale_boxes(page: Page) -> list[dict[str, float]]:
    return page.locator("[data-pw-locale-btn]").evaluate_all(
        """buttons => buttons.map(button => {
          const rect = button.getBoundingClientRect();
          return {width: rect.width, height: rect.height};
        })"""
    )


def _visible_chart_brands(page: Page) -> set[str]:
    return set(
        page.locator(".home-chart polyline[data-brand]:visible").evaluate_all(
            "lines => lines.map(line => line.dataset.brand)"
        )
    )


def _visible_feed_brand_sets(page: Page) -> list[set[str]]:
    values = page.locator(".feed-row[data-brands]:visible").evaluate_all(
        "rows => rows.map(row => row.dataset.brands)"
    )
    return [{brand for brand in value.split(",") if brand} for value in values]


def _assert_locale_geometry_is_stable(page: Page) -> None:
    zh_boxes = _locale_boxes(page)
    page.locator('[data-pw-locale-btn="en"]').click()
    page.wait_for_timeout(50)
    en_boxes = _locale_boxes(page)
    assert len(zh_boxes) == len(en_boxes) == 3
    for zh_box, en_box in zip(zh_boxes, en_boxes, strict=True):
        assert abs(zh_box["width"] - en_box["width"]) < 0.01
        assert abs(zh_box["height"] - en_box["height"]) < 0.01


def test_v23_controls_are_stable_and_filter_chart_and_feed() -> None:
    """Pin all four requested V23 differentiators through Chromium."""
    with _serve_mockup() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page_errors: list[str] = []
            failed_requests: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on(
                "requestfailed",
                lambda request: failed_requests.append(
                    f"{request.url}: {request.failure}"
                ),
            )
            response = page.goto(url, wait_until="networkidle")
            assert response is not None and response.ok
            assert page.locator("body").get_attribute("data-pw-variant") == "v23"

            _assert_locale_geometry_is_stable(page)

            window_background = page.locator("[data-window].is-active").evaluate(
                "element => getComputedStyle(element).backgroundColor"
            )
            kimi = page.locator('.pulse-chip[data-brand="kimi"]')
            deepseek = page.locator('.pulse-chip[data-brand="deepseek"]')

            kimi.click()
            assert kimi.get_attribute("aria-pressed") == "true"
            assert kimi.evaluate(
                "element => getComputedStyle(element).backgroundColor"
            ) == window_background
            assert _visible_chart_brands(page) == {"kimi"}
            kimi_rows = _visible_feed_brand_sets(page)
            assert kimi_rows and all("kimi" in brands for brands in kimi_rows)

            deepseek.click()
            assert kimi.get_attribute("aria-pressed") == "true"
            assert deepseek.get_attribute("aria-pressed") == "true"
            assert _visible_chart_brands(page) == {"kimi", "deepseek"}
            combined_rows = _visible_feed_brand_sets(page)
            assert any("kimi" in brands for brands in combined_rows)
            assert any("deepseek" in brands for brands in combined_rows)
            assert all(brands & {"kimi", "deepseek"} for brands in combined_rows)

            kimi.click()
            assert kimi.get_attribute("aria-pressed") == "false"
            assert _visible_chart_brands(page) == {"deepseek"}
            deepseek.click()
            assert _visible_chart_brands(page) == {
                "kimi",
                "deepseek",
                "minimax",
                "qwen",
                "ernie",
                "glm",
                "solar",
            }
            assert page.locator(".feed-row[data-brands]:visible").count() == page.locator(
                ".feed-row[data-brands]"
            ).count()

            controls_before = page.locator(".topbar-controls").bounding_box()
            pill_before = page.locator("[data-tz-widget]").bounding_box()
            assert controls_before and pill_before
            assert page.locator("[data-tz-widget]").get_attribute("data-tz-active") == "local"
            local_time = page.locator("[data-tz-local-time]").inner_text()
            ca_time = page.locator("[data-tz-ca-time]").inner_text()
            assert TIME_24H.fullmatch(local_time)
            assert TIME_24H.fullmatch(ca_time)
            assert page.locator('[data-tz-choice="local"]').evaluate(
                "element => getComputedStyle(element).backgroundColor"
            ) == window_background
            feed_stamp_before = page.locator("[data-ts-abs]").first.inner_text()

            page.locator("[data-tz-widget]").click()
            assert page.locator("[data-tz-widget]").get_attribute("data-tz-active") == "ca"
            assert page.locator('[data-tz-choice="ca"]').evaluate(
                "element => getComputedStyle(element).backgroundColor"
            ) == window_background
            assert page.locator('[data-tz-choice="local"]').evaluate(
                "element => getComputedStyle(element).backgroundColor"
            ) != window_background
            feed_stamp_after = page.locator("[data-ts-abs]").first.inner_text()
            assert feed_stamp_after != feed_stamp_before and "CA" in feed_stamp_after

            controls_after = page.locator(".topbar-controls").bounding_box()
            pill_after = page.locator("[data-tz-widget]").bounding_box()
            assert controls_after and pill_after
            assert abs(controls_before["width"] - controls_after["width"]) < 0.01
            assert abs(pill_before["width"] - pill_after["width"]) < 0.01
            assert abs(pill_before["height"] - pill_after["height"]) < 0.01
            assert page.locator(".topbar-controls").evaluate(
                "element => element.scrollWidth <= element.clientWidth + 1"
            )

            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile_errors: list[str] = []
            mobile.on("pageerror", lambda error: mobile_errors.append(str(error)))
            mobile_response = mobile.goto(url, wait_until="networkidle")
            assert mobile_response is not None and mobile_response.ok
            _assert_locale_geometry_is_stable(mobile)
            assert mobile.locator("[data-tz-local-time]").is_visible()
            assert mobile.locator("[data-tz-ca-time]").is_visible()
            assert mobile.locator(".topbar-controls").evaluate(
                "element => element.scrollWidth <= element.clientWidth + 1"
            )
            assert mobile.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth + 1"
            )

            assert page_errors == []
            assert mobile_errors == []
            assert failed_requests == []
        finally:
            browser.close()


def test_v23_source_contains_no_agent_execution_notes() -> None:
    source = MOCKUP.read_text(encoding="utf-8")
    assert "{{AGENT_ATTRIBUTION}}" not in source
    assert "Bridgewright" not in source
    assert "regression net" not in source.lower()
