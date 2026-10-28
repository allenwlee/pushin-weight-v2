"""Posts-by-brand chart styling, axes and legend on the General-style homepage."""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from playwright.sync_api import sync_playwright

from core.brand_presentation import BRAND_LOGO_FILES
from core.models import Brand
from monitor.harvest_coverage import closed_five_minute_boundary
from monitor.views import _clear_home_pulse_cache
from tests.general_style_browser import (
    DESKTOP,
    PHONE,
    TABLET,
    goto_home,
    open_page,
    seed_general_style_home,
)

pytestmark = pytest.mark.requires_postgres

PW_CHART = Path(__file__).resolve().parents[1] / "monitor/static/pw-chart.js"


def test_brand_style_table_gives_every_tracked_brand_its_own_pair() -> None:
    source = PW_CHART.read_text(encoding="utf-8")
    body = source[source.index("var BRAND_STYLE = {") : source.index("};", source.index("var BRAND_STYLE = {"))]
    pairs = {
        nickname: (dash, shape)
        for nickname, dash, shape in re.findall(r"(\w+): \['(\w+)', '(\w+)'\]", body)
    }
    assert set(pairs) == set(BRAND_LOGO_FILES)
    assert len(set(pairs.values())) == len(pairs), "two brands share a line pattern and shape"
    assert {dash for dash, _shape in pairs.values()} <= {"solid", "dashed", "dotted", "dashdot"}


CHART_STATE = """() => {
  const canvas = document.querySelector('[data-pw-chart] canvas.home-chart');
  const chart = Chart.getChart(canvas);
  const payload = JSON.parse(canvas.dataset.home);
  const lines = chart.data.datasets.map((dataset, index) => ({dataset, index}))
    .filter(({dataset}) => dataset._isTotalLine);
  const last = payload.days.length - 1;
  const x = chart.scales.x;
  const y = chart.scales.y;
  return {
    payload,
    yPosition: y.options.position,
    yBorder: y.options.border.display,
    gridDash: y.options.grid.borderDash || (y.options.border && y.options.border.dash),
    gridColor: y.options.grid.color,
    tooltip: chart.options.plugins.tooltip.enabled,
    datasets: lines.map(({dataset, index}) => ({
      brand: /^([a-z0-9_]+)/i.exec(dataset.label)[1].toLowerCase(),
      monotone: dataset.cubicInterpolationMode,
      pointRadius: dataset.pointRadius,
      dash: dataset.borderDash,
      lastSegmentDash: dataset.segment && dataset.segment.borderDash
        ? dataset.segment.borderDash({p0DataIndex: last - 1, p1DataIndex: last}) : undefined,
      endGap: y.left - chart.getDatasetMeta(index).data[last].x,
    })),
    lastTick: x.ticks.length ? x.ticks[x.ticks.length - 1].label : null,
    canvasBox: canvas.parentElement.getBoundingClientRect().height,
    canvasHeight: canvas.getBoundingClientRect().height,
  };
}"""

LEGEND_STATE = """() => [...document.querySelectorAll(
    '[data-pw-chart] [data-pw-chart-legend] [data-pw-chart-brand]')].map((button) => {
  const swatch = button.querySelector('svg.pw-swatch');
  const logo = button.querySelector('img.pw-legend-logo');
  const box = (element) => element ? element.getBoundingClientRect() : {width: 0, height: 0};
  return {
    brand: button.dataset.pwChartBrand,
    name: button.querySelector('.pw-legend-name').textContent,
    text: button.innerText,
    swatch: [box(swatch).width, box(swatch).height],
    logo: logo ? [box(logo).width, box(logo).height, logo.naturalWidth] : null,
  };
})"""


@override_settings(SECURE_SSL_REDIRECT=False)
class HomeChartStyleBrowserTests(StaticLiveServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        seed_general_style_home(self)
        Brand.objects.filter(nickname="deepseek").update(display_name_zh_cn="深度求索")
        _clear_home_pulse_cache()

    def test_axes_lines_and_legend_follow_the_general_style(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale, viewport, box_height in (
                    ("en", DESKTOP, 300),
                    ("zh_cn", TABLET, 240),
                    ("ja", PHONE, 200),
                ):
                    with self.subTest(locale=locale, viewport=viewport):
                        run = open_page(browser, self.live_server_url, viewport=viewport)
                        page = run.page
                        goto_home(run, self.live_server_url, f"locale={locale}&window=7")
                        state = page.evaluate(CHART_STATE)
                        self.assertEqual(state["yPosition"], "right")
                        self.assertIs(state["yBorder"], False)
                        self.assertEqual(state["gridDash"], [1, 3])
                        self.assertEqual(state["gridColor"].lower(), "#dfe4ec")
                        self.assertIs(state["tooltip"], False)
                        self.assertEqual(state["canvasBox"], box_height)
                        self.assertEqual(state["canvasHeight"], box_height)
                        self.assertTrue(state["datasets"])
                        for dataset in state["datasets"]:
                            self.assertEqual(dataset["monotone"], "monotone", dataset)
                            self.assertEqual(dataset["pointRadius"], 0, dataset)
                            self.assertAlmostEqual(dataset["endGap"], 16, delta=1, msg=dataset)
                            if dataset["dash"]:
                                # A patterned line keeps its own pattern on the partial day.
                                self.assertIsNone(dataset["lastSegmentDash"], dataset)
                            else:
                                self.assertEqual(dataset["lastSegmentDash"], [4, 4], dataset)
                        self.assertTrue(any(not d["dash"] for d in state["datasets"]))
                        self.assertTrue(any(d["dash"] for d in state["datasets"]))

                        legend = page.evaluate(LEGEND_STATE)
                        self.assertEqual(
                            {entry["brand"] for entry in legend},
                            {dataset["brand"] for dataset in state["datasets"]},
                        )
                        names = {entry["brand"]: entry["name"] for entry in legend}
                        self.assertEqual(
                            names["deepseek"], "深度求索" if locale == "zh_cn" else "DeepSeek"
                        )
                        for entry in legend:
                            self.assertNotIn("_", entry["text"], entry)
                            self.assertGreater(entry["swatch"][0], 0, entry)
                            self.assertGreater(entry["swatch"][1], 0, entry)
                            self.assertIsNotNone(entry["logo"], entry)
                            self.assertGreater(entry["logo"][0], 0, entry)
                            self.assertGreater(entry["logo"][2], 0, f"logo did not load: {entry}")
                        self.assertEqual(run.errors, [])
                        self.assertEqual(run.external, [])
                        run.context.close()
            finally:
                browser.close()

    def test_legend_reads_meta_for_the_llama_brand(self) -> None:
        Brand.objects.update_or_create(
            nickname="llama",
            defaults={
                "display_name": "Meta",
                "display_name_en": "Meta",
                "display_name_zh_cn": "Meta",
                "accent_color": "#0668e1",
            },
        )
        from core.models import Post, PostBrand

        post = Post.objects.create(
            tweet_id="style-meta-row",
            text="Meta evidence",
            created_at=timezone.now() - timedelta(hours=2),
        )
        PostBrand.objects.create(post=post, brand_id="llama")
        _clear_home_pulse_cache()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                run = open_page(browser, self.live_server_url)
                goto_home(run, self.live_server_url, "locale=en&window=7")
                legend = run.page.evaluate(LEGEND_STATE)
                meta = [entry for entry in legend if entry["brand"] == "llama"]
                self.assertEqual(len(meta), 1)
                self.assertEqual(meta[0]["name"], "Meta")
                self.assertEqual(legend[0]["brand"], "llama", "Meta leads the legend order")
                run.context.close()
            finally:
                browser.close()


@override_settings(SECURE_SSL_REDIRECT=False)
class HomeChartCoverageAxisBrowserTests(StaticLiveServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.harvested = timezone.now() - timedelta(minutes=47)
        seed_general_style_home(self, harvested_at=self.harvested)

    def test_one_day_axis_ends_at_harvest_coverage_not_request_time(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale, pattern in (("en", r"^\d{1,2}:\d{2}[ap]m$"), ("ja", r"^\d{2}:\d{2}$")):
                    run = open_page(browser, self.live_server_url)
                    page = run.page
                    goto_home(run, self.live_server_url, f"locale={locale}&window=1")
                    state = page.evaluate(CHART_STATE)
                    coverage_end = closed_five_minute_boundary(self.harvested)
                    self.assertEqual(
                        state["payload"]["harvest_coverage"]["chart_end_at"],
                        coverage_end.isoformat(),
                    )
                    expected = page.evaluate(
                        "([end, locale]) => window.pwTime.clockText(new Date(end), locale)",
                        [coverage_end.isoformat(), locale],
                    )
                    self.assertEqual(state["lastTick"], expected)
                    self.assertRegex(state["lastTick"], pattern)
                    run.context.close()
            finally:
                browser.close()
