"""Shared browser setup for the General-style homepage, General and /dashboard/each tests.

Chart.js and htmx load from unpkg in production; these helpers serve the pinned,
hash-checked copies instead so a run needs no network, and they record every
request that leaves the live server so a test can prove no third-party origin
(such as Google Fonts) is contacted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import patch

from django.utils import timezone
from playwright.sync_api import Browser, BrowserContext, Page

from monitor.views import _HOME_CHART_BRAND_PRIORITY, _clear_home_pulse_cache
from tests.test_chart_harvest_coverage import record_harvest
from tests.ui_assurance.local_preview import PINNED_ASSETS, load_pinned_assets
from tests.v22_support import fixture_from_oracle, seed_real_home_orm

DESKTOP = {"width": 1440, "height": 960}
LAPTOP = {"width": 1100, "height": 900}
TABLET = {"width": 960, "height": 900}
PHONE = {"width": 390, "height": 844}
LOCALES = ("en", "zh_cn", "ja")

WAIT_FOR_HOME_CHART = """() => {
  const canvas = document.querySelector('[data-pw-chart] canvas.home-chart');
  const chart = canvas && window.Chart && Chart.getChart(canvas);
  return Boolean(chart && chart.chartArea && chart.chartArea.width > 0);
}"""


def seed_general_style_home(test_case, *, harvested_at=None) -> None:
    """Seed the deterministic v22 fixture with a completed harvest (default: now)."""
    seed_real_home_orm(fixture_from_oracle())
    harvested_at = harvested_at or timezone.now()
    record_harvest(harvested_at, finished_at=harvested_at, staggered=False)
    tracking = patch(
        "monitor.views._tracked_home_brand_nicknames",
        return_value=_HOME_CHART_BRAND_PRIORITY,
    )
    tracking.start()
    test_case.addCleanup(tracking.stop)
    _clear_home_pulse_cache()


@dataclass
class BrowserRun:
    context: BrowserContext
    page: Page
    errors: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)


def _fulfill(body: bytes):
    return lambda route: route.fulfill(
        status=200, content_type="application/javascript", body=body
    )


def open_page(
    browser: Browser,
    live_server_url: str,
    *,
    viewport: dict[str, int] = DESKTOP,
    reduced_motion: str | None = None,
    touch: bool = False,
) -> BrowserRun:
    """A context that serves the pinned scripts and records outside requests."""
    options: dict[str, object] = {"viewport": viewport, "timezone_id": "Asia/Tokyo"}
    if reduced_motion:
        options["reduced_motion"] = reduced_motion
    if touch:
        options.update(has_touch=True, is_mobile=True)
    context = browser.new_context(**options)
    assets = load_pinned_assets()
    for asset in PINNED_ASSETS:
        context.route(asset.source_url, _fulfill(assets[asset.local_path]))
    pinned = {asset.source_url for asset in PINNED_ASSETS}
    run = BrowserRun(context=context, page=context.new_page())
    context.on(
        "request",
        lambda request: run.external.append(request.url)
        if not request.url.startswith(live_server_url)
        and request.url not in pinned
        and not request.url.startswith(("data:", "blob:"))
        else None,
    )
    run.page.on("pageerror", lambda error: run.errors.append(str(error)))
    return run


def goto_home(run: BrowserRun, live_server_url: str, query: str = "locale=en") -> None:
    response = run.page.goto(f"{live_server_url}/?{query}", wait_until="networkidle")
    assert response is not None and response.status == 200, response
    run.page.wait_for_function(WAIT_FOR_HOME_CHART)


def horizontal_overflow(page: Page) -> float:
    return page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
