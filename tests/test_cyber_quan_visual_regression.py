"""Deterministic picture regression for the icon-only Cyber-Quan delta."""

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


def _outside_mask_report(page: Page, before: bytes, after: bytes, mask: bytes) -> dict[str, object]:
    encode = lambda value: "data:image/png;base64," + base64.b64encode(value).decode("ascii")
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
        {"before": encode(before), "after": encode(after), "mask": encode(mask)},
    )


def _icon_mask(page: Page) -> bytes:
    data_url = page.evaluate(
        """() => {
          const canvas = document.createElement('canvas');
          canvas.width = innerWidth;
          canvas.height = innerHeight;
          const context = canvas.getContext('2d');
          context.fillStyle = '#000';
          context.fillRect(0, 0, canvas.width, canvas.height);
          context.fillStyle = '#fff';
          const paint = (selector, pad = 3, leadingWidth = null) => {
            document.querySelectorAll(selector).forEach(node => {
              const rect = node.getBoundingClientRect();
              if (rect.bottom < 0 || rect.top > innerHeight) return;
              const width = leadingWidth == null ? rect.width : Math.min(rect.width, leadingWidth);
              context.fillRect(
                Math.floor(rect.left - pad),
                Math.floor(rect.top - pad),
                Math.ceil(width + pad * 2),
                Math.ceil(rect.height + pad * 2)
              );
            });
          };
          paint('.app-name', 3);
          // The selected timezone choice keeps an identical box, but Chromium
          // rasterizes its two-pixel rounded leading edge differently when the
          // emoji text node becomes SVG. Keep that antialias seam explicit.
          paint('.tz-choice.is-selected', 0, 2);
          paint('.tz-emoji, [data-tz-comparison-icon]', 3);
          paint('.pulse-chip .delta', 3);
          paint('.filter-pill .carat', 3);
          paint('.headline-meta', 3, 17);
          paint('.voice-star', 3);
          paint('.follower-glyph', 3);
          paint('.engagement > span', 3, 19);
          paint('.sig-row:not(.is-empty)', 3);
          return canvas.toDataURL('image/png');
        }"""
    )
    return base64.b64decode(data_url.split(",", 1)[1])


def _release_a_mask(page: Page) -> bytes:
    """Mask only later owner-approved feed, headline, and chart surfaces."""
    data_url = page.evaluate(
        """() => {
          const canvas = document.createElement('canvas');
          canvas.width = innerWidth;
          canvas.height = innerHeight;
          const context = canvas.getContext('2d');
          context.fillStyle = '#000';
          context.fillRect(0, 0, canvas.width, canvas.height);
          context.fillStyle = '#fff';
          document.querySelectorAll('.headline-strip, .feed-strip, canvas.home-chart').forEach(node => {
            const rect = node.getBoundingClientRect();
            context.fillRect(
              Math.floor(rect.left - 3),
              Math.floor(rect.top - 3),
              Math.ceil(rect.width + 6),
              Math.ceil(rect.height + 6)
            );
          });
          return canvas.toDataURL('image/png');
        }"""
    )
    return base64.b64decode(data_url.split(",", 1)[1])


@override_settings(STORAGES=V22_BROWSER_TEST_STORAGES)
class CyberQuanVisualRegressionTests(StaticLiveServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        seed_v22_metadata_regression_orm()
        _clear_home_pulse_cache()

    def _context(self, browser: object, viewport: dict[str, int]) -> BrowserContext:
        context = browser.new_context(viewport=viewport, timezone_id="Asia/Tokyo")
        _freeze_clock(context)
        return context

    def test_candidate_matches_reviewed_goldens_and_prechange_diff_masks(self) -> None:
        capture_kind = os.environ.get("CYBER_QUAN_CAPTURE_ONLY") or None
        self.assertIn(capture_kind, (None, "candidate", "prechange"))
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
                                capture_name = f"{stem}.png" if capture_kind == "candidate" else f"{capture_kind}-{stem}.png"
                                (capture_root / capture_name).write_bytes(actual)
                                if capture_kind == "candidate":
                                    (capture_root / f"mask-{stem}.png").write_bytes(_icon_mask(page))
                                continue

                            candidate_path = GOLDEN_ROOT / f"{stem}.png"
                            prechange_path = GOLDEN_ROOT / f"prechange-{stem}.png"
                            mask_path = GOLDEN_ROOT / f"mask-{stem}.png"
                            candidate = candidate_path.read_bytes()
                            candidate_report = _outside_mask_report(
                                page, candidate, actual, _release_a_mask(page)
                            )
                            self.assertEqual(
                                candidate_report["outside_changed"],
                                0,
                                f"Release A drift escaped approved feed/headline surfaces relative to {candidate_path}: {candidate_report}",
                            )
                            mask_report = _outside_mask_report(
                                page,
                                prechange_path.read_bytes(),
                                candidate,
                                mask_path.read_bytes(),
                            )
                            self.assertEqual(
                                mask_report["outside_changed"],
                                0,
                                f"prechange-to-candidate pixels escaped exact icon masks: {mask_report}",
                            )
                        finally:
                            context.close()
            finally:
                browser.close()
