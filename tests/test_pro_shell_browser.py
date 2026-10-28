"""Rail, masthead labels and headings shared by the homepage and /dashboard/each."""

from __future__ import annotations

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import Page, sync_playwright

from tests.general_style_browser import (
    DESKTOP,
    LOCALES,
    PHONE,
    goto_home,
    horizontal_overflow,
    open_page,
    seed_general_style_home,
)

pytestmark = pytest.mark.requires_postgres

CHROME = {
    "en": {
        "rail": ["General", "Trending", "Posts by brand", "Trend summary", "Latest", "Pro"],
        "settings": ["Language", "Window", "Clock"],
        "chart": "Posts by brand",
        "feed": "Latest in window",
        "filters": "Filters",
        "general_lang": "en",
    },
    "zh_cn": {
        "rail": ["概览", "热门模型", "各品牌帖子", "趋势摘要", "最新", "专业版"],
        "settings": ["语言", "时间窗口", "时钟"],
        "chart": "各品牌帖子",
        "feed": "本窗口最新",
        "filters": "筛选",
        "general_lang": "zh-cn",
    },
    "ja": {
        "rail": ["概要", "注目モデル", "ブランド別投稿", "トレンド要約", "最新", "プロ"],
        "settings": ["言語", "期間", "時計"],
        "chart": "ブランド別投稿",
        "feed": "この期間の最新投稿",
        "filters": "絞り込み",
        "general_lang": "ja",
    },
}

CHROME_STATE = """() => ({
  title: document.title,
  rail: [...document.querySelectorAll('#pw-rail nav a .pw-rail-label')].map((node) => node.textContent.trim()),
  generalHref: document.querySelector('#pw-rail nav a').getAttribute('href'),
  settings: [...document.querySelectorAll('.topbar .pw-setting-label')].map((node) => node.textContent.trim()),
  chart: document.querySelector('#pw-activity-head h2')?.textContent.trim() ?? null,
  feed: document.querySelector('[data-pw-feed-title]')?.textContent.trim() ?? null,
  filters: document.querySelector('.pw-filter-label')?.textContent.trim() ?? null,
  mastheadText: document.querySelector('.topbar').innerText,
  wordmark: document.querySelector('.app-name .pw-wordmark').innerText,
  appLabel: document.querySelector('h1.app-name').getAttribute('aria-label'),
  drawerLabel: document.querySelector('[data-pw-rail-toggle] .pw-rail-label').textContent.trim(),
  markBox: (() => {
    const box = document.querySelector('.app-name .app-mark').getBoundingClientRect();
    return [box.width, box.height];
  })(),
  railMarkBox: (() => {
    const box = document.querySelector('#pw-rail nav a .pw-rail-icon').getBoundingClientRect();
    return [box.width, box.height];
  })(),
})"""


@override_settings(SECURE_SSL_REDIRECT=False)
class ProShellBrowserTests(StaticLiveServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        seed_general_style_home(self)

    def _assert_chrome(self, page: Page, locale: str, *, homepage: bool) -> None:
        state = page.evaluate(CHROME_STATE)
        expected = CHROME[locale]
        self.assertEqual(state["title"], "PUSHINWEIGHT")
        self.assertEqual(state["rail"], expected["rail"])
        self.assertEqual(state["generalHref"], f"/general/?lang={expected['general_lang']}")
        self.assertEqual(state["settings"], expected["settings"])
        self.assertEqual(state["wordmark"], "PUSHINWEIGHT")
        self.assertEqual(state["appLabel"], "PUSHINWEIGHT")
        self.assertEqual(state["drawerLabel"], "PUSHINWEIGHT")
        self.assertNotIn("走个量", state["mastheadText"])
        self.assertNotIn("Prototype", state["mastheadText"])
        self.assertTrue(all(size > 0 for size in state["markBox"]), state["markBox"])
        self.assertTrue(all(size > 0 for size in state["railMarkBox"]), state["railMarkBox"])
        if homepage:
            self.assertEqual(state["chart"], expected["chart"])
            self.assertEqual(state["feed"], expected["feed"])
            self.assertEqual(state["filters"], expected["filters"])

    def test_chrome_is_localized_on_load_and_after_a_locale_switch(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale in LOCALES:
                    with self.subTest(locale=locale):
                        run = open_page(browser, self.live_server_url)
                        page = run.page
                        goto_home(run, self.live_server_url, f"locale={locale}")
                        self._assert_chrome(page, locale, homepage=True)
                        target = "ja" if locale != "ja" else "en"
                        with page.expect_navigation(wait_until="networkidle"):
                            page.locator(f'[data-pw-locale-btn="{target}"]').click()
                        self._assert_chrome(page, target, homepage=True)
                        response = page.goto(
                            f"{self.live_server_url}/dashboard/each?brand=deepseek&locale={locale}",
                            wait_until="networkidle",
                        )
                        self.assertEqual(response.status, 200)
                        self._assert_chrome(page, locale, homepage=False)
                        self.assertEqual(run.errors, [])
                        self.assertEqual(run.external, [])
                        run.context.close()
            finally:
                browser.close()

    def test_desktop_rail_expands_and_collapses(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url, viewport=DESKTOP)
                page = run.page
                goto_home(run, self.live_server_url, "locale=en")
                rail = page.locator("#pw-rail")
                toggle = page.locator("[data-pw-rail-toggle]")
                collapsed = rail.bounding_box()["width"]
                self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                self.assertFalse(page.locator("#pw-rail nav a .pw-rail-label").first.is_visible())
                toggle.click()
                page.wait_for_function(
                    "() => document.getElementById('pw-rail').getBoundingClientRect().width > 200"
                )
                self.assertEqual(page.locator("body").get_attribute("data-pw-nav"), "expanded")
                self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
                self.assertTrue(page.locator("#pw-rail nav a .pw-rail-label").first.is_visible())
                main_left = page.locator(".topbar").bounding_box()["x"]
                self.assertGreaterEqual(main_left, rail.bounding_box()["width"] - 0.5)
                toggle.click()
                page.wait_for_function(
                    f"() => document.getElementById('pw-rail').getBoundingClientRect().width <= {collapsed + 0.5}"
                )
                self.assertIsNone(page.locator("body").get_attribute("data-pw-nav"))
                self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                # Window, clock and locale controls still work beside the rail.
                with page.expect_response(lambda response: "/chart.html?" in response.url):
                    page.locator('[data-pw-window-btn="7"]').click()
                page.locator("[data-tz-widget]").click()
                page.wait_for_function("() => window.__pwTz?.mode === 'ca'")
                self.assertEqual(horizontal_overflow(page), 0)
                self.assertEqual(run.errors, [])
                run.context.close()
            finally:
                browser.close()

    def test_phone_drawer_opens_and_closes_every_way(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for path in ("/?locale=en", "/dashboard/each?brand=deepseek&locale=en"):
                    with self.subTest(path=path):
                        run = open_page(browser, self.live_server_url, viewport=PHONE)
                        page = run.page
                        page.goto(f"{self.live_server_url}{path}", wait_until="networkidle")
                        opener = page.locator("[data-pw-rail-open]")
                        backdrop = page.locator("[data-pw-rail-close]")
                        self.assertTrue(opener.is_visible())
                        self.assertFalse(page.locator("#pw-rail").is_visible())
                        self.assertEqual(horizontal_overflow(page), 0)

                        def open_drawer(page=page, opener=opener, backdrop=backdrop) -> None:
                            opener.click()
                            page.wait_for_function(
                                "() => document.getElementById('pw-rail').getBoundingClientRect().left >= -0.5"
                            )
                            self.assertEqual(opener.get_attribute("aria-expanded"), "true")
                            self.assertTrue(backdrop.is_visible())
                            self.assertEqual(
                                page.evaluate("() => document.activeElement.closest('#pw-rail nav') !== null"),
                                True,
                            )

                        def assert_closed(
                            *, focus_returns: bool = True, page=page, opener=opener, backdrop=backdrop
                        ) -> None:
                            page.wait_for_function(
                                "() => document.body.getAttribute('data-pw-nav') === null"
                            )
                            self.assertEqual(opener.get_attribute("aria-expanded"), "false")
                            self.assertFalse(backdrop.is_visible())
                            if focus_returns:
                                self.assertEqual(
                                    page.evaluate("() => document.activeElement.hasAttribute('data-pw-rail-open')"),
                                    True,
                                )

                        open_drawer()
                        backdrop.click(position={"x": 370, "y": 400})
                        assert_closed()
                        open_drawer()
                        page.keyboard.press("Escape")
                        assert_closed()
                        if path.startswith("/?"):
                            # A section link closes the drawer and leaves the page at that section.
                            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                            open_drawer()
                            page.locator('#pw-rail nav a[href="#pw-trending"]').click()
                            assert_closed(focus_returns=False)
                            page.wait_for_timeout(300)
                            top = page.evaluate(
                                "() => document.getElementById('pw-trending').getBoundingClientRect().top"
                            )
                            self.assertGreaterEqual(top, -1)
                            self.assertLess(top, 200)
                        self.assertEqual(horizontal_overflow(page), 0)
                        self.assertEqual(run.errors, [])
                        run.context.close()
            finally:
                browser.close()
