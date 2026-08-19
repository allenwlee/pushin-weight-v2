"""Real-browser regression net for the standalone V24 mockup."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
MOCKUP_DIR = REPO_ROOT / "docs" / "ideation" / "mockups"
V23_MOCKUP = MOCKUP_DIR / "v23.html"
V24_MOCKUP = MOCKUP_DIR / "v24.html"
V24_ONLY_CSS = """  .topbar-controls .window-toggle:not(.locale-toggle) button {
    width: 32px;
    flex: 0 0 32px;
    padding-inline: 0;
  }
"""
V24_ONLY_DESKTOP_CSS = """  body.desktop-shell .topbar .window-toggle:not(.locale-toggle) button {
    width: 52px;
    flex-basis: 52px;
    padding-inline: 0;
  }
"""


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def _serve_mockup() -> Iterator[str]:
    assert V24_MOCKUP.is_file(), f"V24 mockup is missing: {V24_MOCKUP}"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(_QuietStaticHandler, directory=str(MOCKUP_DIR)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{V24_MOCKUP.name}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _window_state(page: Page) -> tuple[list[str], list[dict[str, float]]]:
    buttons = page.locator("button[data-window]")
    labels = [label.strip() for label in buttons.all_inner_texts()]
    boxes = buttons.evaluate_all(
        """elements => elements.map(element => {
          const rect = element.getBoundingClientRect();
          return {width: rect.width, height: rect.height};
        })"""
    )
    return labels, boxes


def _assert_same_boxes(
    expected: list[dict[str, float]], actual: list[dict[str, float]]
) -> None:
    assert len(expected) == len(actual) == 4
    for expected_box, actual_box in zip(expected, actual, strict=True):
        assert abs(expected_box["width"] - actual_box["width"]) < 0.01
        assert abs(expected_box["height"] - actual_box["height"]) < 0.01


def _assert_window_geometry(page: Page) -> None:
    zh_labels, zh_boxes = _window_state(page)
    assert zh_labels == ["1天", "7天", "30天", "365天"]
    assert len({round(box["width"], 2) for box in zh_boxes}) == 1

    page.locator('[data-pw-locale-btn="en"]').click()
    page.wait_for_timeout(50)
    en_labels, en_boxes = _window_state(page)
    assert en_labels == ["1d", "7d", "30d", "365d"]
    _assert_same_boxes(zh_boxes, en_boxes)

    page.locator('[data-pw-locale-btn="original"]').click()
    page.wait_for_timeout(50)
    original_labels, original_boxes = _window_state(page)
    assert original_labels == ["1d", "7d", "30d", "365d"]
    _assert_same_boxes(zh_boxes, original_boxes)

    controls = page.locator(".topbar-controls")
    assert controls.evaluate("element => element.scrollWidth <= element.clientWidth + 1")


def _check_viewport(browser: Browser, url: str, width: int, height: int) -> list[str]:
    page = browser.new_page(viewport={"width": width, "height": height})
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    response = page.goto(url, wait_until="networkidle")
    assert response is not None and response.ok
    assert page.locator("body").get_attribute("data-pw-variant") == "v24"
    _assert_window_geometry(page)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    page.close()
    return page_errors


def test_v24_window_buttons_keep_exact_geometry_across_locales() -> None:
    """Pin equal sizing, new labels, and topbar fit through Chromium."""
    with _serve_mockup() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            assert _check_viewport(browser, url, 1440, 1000) == []
            assert _check_viewport(browser, url, 390, 844) == []
        finally:
            browser.close()


def test_v24_changes_only_the_requested_window_control() -> None:
    """Keep V23 byte-for-byte recoverable after normalizing V24-only edits."""
    v23_source = V23_MOCKUP.read_text(encoding="utf-8")
    v24_source = V24_MOCKUP.read_text(encoding="utf-8")
    normalized = v24_source.replace(V24_ONLY_CSS, "")
    normalized = normalized.replace(V24_ONLY_DESKTOP_CSS, "")
    normalized = normalized.replace('data-pw-variant="v24"', 'data-pw-variant="v23"')
    normalized = normalized.replace("version: 'v24'", "version: 'v23'")
    normalized = normalized.replace(
        'data-label-en="1d" data-label-zh="1天">1天',
        'data-label-en="24h" data-label-zh="24小时">24小时',
    )
    assert normalized == v23_source


def test_v24_source_contains_no_agent_execution_notes() -> None:
    source = V24_MOCKUP.read_text(encoding="utf-8")
    assert "{{AGENT_ATTRIBUTION}}" not in source
    assert "Bridgewright" not in source
    assert "regression net" not in source.lower()
