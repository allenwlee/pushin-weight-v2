"""Deterministic picture regression for the homepage chrome.

The goldens were recaptured for the General-style homepage
(docs/iterations/2026-10-28-183433-general-style-bridgewright-target.md), which
supersedes the icon-only Cyber-Quan delta. Its prechange-to-candidate icon
comparison is retired; ``prechange-*.png`` and ``mask-*.png`` remain only as the
evidence recorded by docs/iterations/2026-08-28-134649-cyber-quan-icons-bridgewright-target.md.
Recapture with ``CYBER_QUAN_CAPTURE_ONLY=candidate``.
"""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import BrowserContext, Page, sync_playwright

from monitor.views import _clear_home_pulse_cache
from tests.test_home_v22_browser import (
    _HOME_CHART_BRAND_PRIORITY,
    V22_BROWSER_TEST_STORAGES,
    _freeze_clock,
)
from tests.v22_support import seed_v22_metadata_regression_orm

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = ROOT / "tests/golden/bridgewright/cyber-quan"
FIXED_NOW = datetime(2026, 8, 10, 12, 34, tzinfo=UTC)
STATES = (
    ("desktop-en", {"width": 1440, "height": 960}, "en"),
    ("mobile-zh-cn", {"width": 390, "height": 844}, "zh_cn"),
)


def _outside_mask_report(
    page: Page,
    before: bytes,
    after: bytes,
    mask: bytes,
) -> dict[str, object]:
    def encode(value: bytes) -> str:
        return "data:image/png;base64," + base64.b64encode(value).decode("ascii")

    return page.evaluate(
        """async ({before, after, mask}) => {
          const decode = source => new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = reject;
            image.src = source;
          });
          const [left, right, allowed] = await Promise.all(
            [before, after, mask].map(decode)
          );
          if (left.width !== right.width || left.height !== right.height ||
              left.width !== allowed.width || left.height !== allowed.height) {
            return {outside_changed: -1, outside_fraction: 1};
          }
          const canvas = document.createElement('canvas');
          canvas.width = left.width;
          canvas.height = left.height;
          const context = canvas.getContext('2d', {willReadFrequently: true});
          const pixels = image => {
            context.clearRect(0, 0, canvas.width, canvas.height);
            context.drawImage(image, 0, 0);
            return context.getImageData(0, 0, canvas.width, canvas.height).data;
          };
          const a = pixels(left);
          const b = pixels(right);
          const m = pixels(allowed);
          let outsideChanged = 0;
          let outsidePixels = 0;
          let minX = left.width;
          let minY = left.height;
          let maxX = -1;
          let maxY = -1;
          const bands = new Map();
          const samples = [];
          for (let index = 0; index < a.length; index += 4) {
            const isAllowed = m[index] > 127 || m[index + 1] > 127 || m[index + 2] > 127;
            if (isAllowed) continue;
            outsidePixels += 1;
            if (Math.max(
              Math.abs(a[index] - b[index]),
              Math.abs(a[index + 1] - b[index + 1]),
              Math.abs(a[index + 2] - b[index + 2])
            ) > 16) {
              outsideChanged += 1;
              const pixel = index / 4;
              const x = pixel % left.width;
              const y = Math.floor(pixel / left.width);
              minX = Math.min(minX, x);
              minY = Math.min(minY, y);
              maxX = Math.max(maxX, x);
              maxY = Math.max(maxY, y);
              if (samples.length < 50) samples.push([x, y]);
              const key = `${Math.floor(x / 8) * 8},${Math.floor(y / 8) * 8}`;
              bands.set(key, (bands.get(key) || 0) + 1);
            }
          }
          return {
            outside_changed: outsideChanged,
            outside_fraction: outsidePixels ? outsideChanged / outsidePixels : 0,
            bounds: outsideChanged ? [minX, minY, maxX, maxY] : null,
            samples,
            bands: [...bands.entries()]
              .sort((leftBand, rightBand) => rightBand[1] - leftBand[1])
              .slice(0, 30)
          };
        }""",
        {
            "before": encode(before),
            "after": encode(after),
            "mask": encode(mask),
        },
    )


def _data_surface_mask(page: Page) -> bytes:
    """Mask the data-driven surfaces; the static chrome around them is compared."""
    data_url = page.evaluate(
        """() => {
          const canvas = document.createElement('canvas');
          canvas.width = innerWidth;
          canvas.height = innerHeight;
          const context = canvas.getContext('2d');
          context.fillStyle = '#000';
          context.fillRect(0, 0, canvas.width, canvas.height);
          context.fillStyle = '#fff';
          const paint = (node, pad = 3, leadingWidth = null) => {
            const rect = node.getBoundingClientRect();
            const width = leadingWidth == null ? rect.width : Math.min(rect.width, leadingWidth);
            context.fillRect(
              Math.floor(rect.left - pad),
              Math.floor(rect.top - pad),
              Math.ceil(width + pad * 2),
              Math.ceil(rect.height + pad * 2)
            );
          };
          // Pulse inventory, activation-gated taxonomy filters, the animated
          // chart, narratives and feed rows follow live fixture data.
          document.querySelectorAll('.pulse-bar-wrap, .filter-bar, .home-chart-wrap, .headline-strip, .feed-strip')
            .forEach(node => paint(node));
          // Chromium rasterizes the selected clock choice's two-pixel rounded
          // leading edge inconsistently; this is a raster seam, not a surface.
          document.querySelectorAll('.tz-choice.is-selected')
            .forEach(node => paint(node, 0, 2));
          return canvas.toDataURL('image/png');
        }"""
    )
    return base64.b64decode(data_url.split(",", 1)[1])


@override_settings(STORAGES=V22_BROWSER_TEST_STORAGES)
class CyberQuanVisualRegressionTests(StaticLiveServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        tracking = patch(
            "monitor.views._tracked_home_brand_nicknames",
            return_value=_HOME_CHART_BRAND_PRIORITY + (
                "dots", "anthropic", "google_deepmind", "openai", "spacexai",
                "pulse_up", "pulse_down", "pulse_flat", "pulse_new", "pulse_absent",
            ),
        )
        tracking.start()
        self.addCleanup(tracking.stop)
        self.clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        seed_v22_metadata_regression_orm()
        _clear_home_pulse_cache()

    def _context(self, browser: object, viewport: dict[str, int]) -> BrowserContext:
        context = browser.new_context(viewport=viewport, timezone_id="Asia/Tokyo")
        _freeze_clock(context)
        return context

    def test_candidate_matches_reviewed_goldens(self) -> None:
        capture_kind = os.environ.get("CYBER_QUAN_CAPTURE_ONLY") or None
        self.assertIn(capture_kind, (None, "candidate"))
        capture_root = Path(os.environ.get("CYBER_QUAN_CAPTURE_DIR", GOLDEN_ROOT))

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for stem, viewport, locale in STATES:
                    with self.subTest(stem=stem):
                        context = self._context(browser, viewport)
                        page_errors: list[str] = []
                        page = context.new_page()
                        page.on("pageerror", lambda error: page_errors.append(str(error)))
                        try:
                            page.goto(f"{self.live_server_url}/?locale={locale}", wait_until="networkidle")
                            actual = page.screenshot()
                            self.assertEqual(page_errors, [])
                            if capture_kind:
                                capture_root.mkdir(parents=True, exist_ok=True)
                                (capture_root / f"{stem}.png").write_bytes(actual)
                                continue

                            candidate_path = GOLDEN_ROOT / f"{stem}.png"
                            candidate_report = _outside_mask_report(
                                page, candidate_path.read_bytes(), actual, _data_surface_mask(page)
                            )
                            self.assertEqual(
                                candidate_report["outside_changed"],
                                0,
                                f"drift escaped the data-driven feed, headline and chart surfaces relative to {candidate_path}: {candidate_report}",
                            )
                        finally:
                            context.close()
            finally:
                browser.close()
