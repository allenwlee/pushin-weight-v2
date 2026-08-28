"""Browser fidelity net for the fixture-backed public root route.

This is deliberately not a screenshot baseline: the canonical mockup is served
over HTTP beside Django's static live server and remains the comparison source.
Reports and paired PNGs are retained outside the checkout for review.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from playwright.sync_api import BrowserContext, Page, sync_playwright

from core.models import Post
from monitor.views import MODEL_DISPLAY_NAMES, _clear_home_pulse_cache
from tests.mockup_spec import DEFAULT_SOURCE, MockupSpec, load_spec
from tests.shell_diff import AUTHORED_REGIONS, parse_rendered_html, select_one
from tests.v22_support import (
    V22_TEST_USER_EMAIL,
    fixture_from_oracle,
    seed_real_home_orm,
    seed_v22_metadata_regression_orm,
)

pytestmark = pytest.mark.requires_postgres

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 960},
    "mobile": {"width": 390, "height": 844},
}
LOCALES = ("zh_cn", "en", "original")
REGION_SELECTORS = dict(AUTHORED_REGIONS)
STYLE_PROPERTIES = ("display", "boxSizing", "fontFamily", "lineHeight")
# The threshold is intentionally below a wholly unrelated frame.  It is not a
# checked-in image baseline: every run compares fresh captures to the mockup.
# Initial reports against the canonical fixture landed at 0.25 (desktop) and
# 0.40 (mobile).  0.45 leaves rendering tolerance without accepting a new
# frame or a materially rearranged shell.
MAX_CHANGED_PIXEL_FRACTION = 0.45
PIXEL_DELTA = 32
DEFAULT_BROWSER_ARTIFACT_RETENTION = 10
V22_BROWSER_TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def serve_mockup_over_http() -> Iterator[str]:
    """Expose the authored source to Chromium without a ``file://`` escape."""
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(_QuietStaticHandler, directory=str(DEFAULT_SOURCE.parent)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{DEFAULT_SOURCE.name}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _prune_default_artifact_runs(root: Path, *, keep: int) -> None:
    """Best-effort cleanup that never removes the report being written."""
    runs = sorted(
        (path for path in root.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    stale_runs = runs[:-keep] if keep else runs
    for run in stale_runs:
        shutil.rmtree(run, ignore_errors=True)


def _artifact_dir() -> Path:
    configured = os.environ.get("V22_BROWSER_REPORT_DIR")
    root = Path(configured) if configured else Path.home() / ".pytest-v22-browser-artifacts"
    root.mkdir(parents=True, exist_ok=True)
    if not configured:
        _prune_default_artifact_runs(root, keep=DEFAULT_BROWSER_ARTIFACT_RETENTION - 1)
    path = root / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path.mkdir(exist_ok=True)
    return path


def test_default_browser_artifact_retention_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default report root remains inspectable without growing forever."""
    monkeypatch.delenv("V22_BROWSER_REPORT_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    root = tmp_path / ".pytest-v22-browser-artifacts"
    for index in range(10):
        (root / f"old-{index}").mkdir(parents=True)

    artifact_dir = _artifact_dir()

    assert artifact_dir.is_dir()
    assert len([path for path in root.iterdir() if path.is_dir()]) <= DEFAULT_BROWSER_ARTIFACT_RETENTION


def test_configured_browser_artifact_dir_is_not_pruned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit report directory retains every artifact for its owner."""
    root = tmp_path / "operator-reports"
    for index in range(DEFAULT_BROWSER_ARTIFACT_RETENTION):
        (root / f"old-{index}").mkdir(parents=True)
    monkeypatch.setenv("V22_BROWSER_REPORT_DIR", str(root))

    artifact_dir = _artifact_dir()

    assert artifact_dir.is_dir()
    assert len([path for path in root.iterdir() if path.is_dir()]) == DEFAULT_BROWSER_ARTIFACT_RETENTION + 1


def _freeze_clock(context: BrowserContext) -> None:
    """Make the initial timezone widget value deterministic and non-placeholder."""
    context.add_init_script(
        """
        (() => {
          const NativeDate = Date;
          const fixed = Date.UTC(2026, 7, 10, 12, 34, 0);
          class FixedDate extends NativeDate {
            constructor(...args) { super(...(args.length ? args : [fixed])); }
            static now() { return fixed; }
          }
          FixedDate.parse = NativeDate.parse;
          FixedDate.UTC = NativeDate.UTC;
          window.Date = FixedDate;
        })();
        """
    )


def _cookie_payload(client: Client, base_url: str) -> list[dict[str, str]]:
    return [
        {"name": name, "value": morsel.value, "url": base_url}
        for name, morsel in client.cookies.items()
    ]


def _computed_styles(page: Page) -> dict[str, dict[str, str]]:
    return page.evaluate(
        """({selectors, properties}) => Object.fromEntries(
          Object.entries(selectors).map(([region, selector]) => {
            const element = document.querySelector(selector);
            if (!element) return [region, null];
            const style = getComputedStyle(element);
            return [region, Object.fromEntries(properties.map((name) => [name, style[name]]))];
          })
        )""",
        {"selectors": REGION_SELECTORS, "properties": STYLE_PROPERTIES},
    )


def _relative_geometry(page: Page, root_selector: str) -> dict[str, dict[str, float]]:
    return page.evaluate(
        """({rootSelector, selectors}) => {
          const root = document.querySelector(rootSelector)?.getBoundingClientRect();
          if (!root || !root.width || !root.height) return {__root_missing__: true};
          const normal = (value) => Math.round(value * 10000) / 10000;
          const entry = (selector) => {
            const rect = document.querySelector(selector)?.getBoundingClientRect();
            if (!rect) return null;
            return {
              x: normal((rect.left - root.left) / root.width),
              y: normal((rect.top - root.top) / root.height),
              width: normal(rect.width / root.width),
              height: normal(rect.height / root.height),
            };
          };
          return Object.fromEntries(Object.entries(selectors).map(([region, selector]) => [region, entry(selector)]));
        }""",
        {"rootSelector": root_selector, "selectors": REGION_SELECTORS},
    )


def _pixel_report(page: Page, actual: bytes, reference: bytes) -> dict[str, float | int]:
    """Compare PNGs in Chromium, avoiding a Pillow/ImageMagick test dependency."""
    return page.evaluate(
        """async ({actual, reference, delta}) => {
          const decode = (source) => new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = reject;
            image.src = source;
          });
          const [left, right] = await Promise.all([decode(actual), decode(reference)]);
          if (left.width !== right.width || left.height !== right.height) {
            return {width: left.width, height: left.height, reference_width: right.width,
                    reference_height: right.height, changed_fraction: 1, mean_channel_delta: 255};
          }
          const canvas = document.createElement('canvas');
          canvas.width = left.width;
          canvas.height = left.height;
          const context = canvas.getContext('2d', {willReadFrequently: true});
          context.drawImage(left, 0, 0);
          const leftPixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
          context.clearRect(0, 0, canvas.width, canvas.height);
          context.drawImage(right, 0, 0);
          const rightPixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
          let changed = 0;
          let sum = 0;
          for (let index = 0; index < leftPixels.length; index += 4) {
            const distance = Math.max(
              Math.abs(leftPixels[index] - rightPixels[index]),
              Math.abs(leftPixels[index + 1] - rightPixels[index + 1]),
              Math.abs(leftPixels[index + 2] - rightPixels[index + 2])
            );
            sum += distance;
            if (distance > delta) changed += 1;
          }
          const pixels = leftPixels.length / 4;
          return {width: canvas.width, height: canvas.height, reference_width: canvas.width,
                  reference_height: canvas.height, changed_fraction: changed / pixels,
                  mean_channel_delta: sum / pixels};
        }""",
        {
            "actual": "data:image/png;base64," + base64.b64encode(actual).decode("ascii"),
            "reference": "data:image/png;base64," + base64.b64encode(reference).decode("ascii"),
            "delta": PIXEL_DELTA,
        },
    )


def _assert_parser_regions(page: Page, spec: MockupSpec, *, locale: str, viewport: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    rendered = parse_rendered_html(page.content())
    for region, selector in REGION_SELECTORS.items():
        count = page.locator(selector).count()
        counts[region] = count
        assert count == 1, (
            "v22 browser DOM mismatch: "
            f"region={region!r}; selector={selector!r}; count={count}; "
            f"locale={locale!r}; viewport={viewport!r}; oracle_source={str(spec.source)!r}"
        )
        # Reuse the oracle-aware parser diagnostic rather than treating a
        # browser selector alone as proof that the authored node is valid.
        select_one(
            rendered,
            selector=selector,
            locale=locale,
            viewport=viewport,
            oracle_source=str(spec.source),
        )
    return counts


def _why_first_browser_snapshot(
    *,
    window_days: int,
    brand_key: str,
    display_name: str,
    volume_change: str,
    selected_posts: int,
    prior_posts: int,
    include_mix: bool,
    as_of: datetime,
) -> dict[str, object]:
    """Closed synthetic facts for rendered schema-three browser proof."""
    evidence = [
        {
            "evidence_id": f"{brand_key}_{window_days}_downloads",
            "source_cluster_id": f"{brand_key}_{window_days}_source_one",
            "theme_cluster_id": "downloads_and_intelligence",
            "author_group_id": f"{brand_key}_{window_days}_author_one",
            "excerpt": (
                f"A user reported downloading {display_name} more often and "
                "described improved intelligence in hands-on work."
            ),
            "roles": ["recurring_theme"],
            "source_flags": {
                "official": False,
                "post_kind": "source_post",
                "metrics_observed": True,
                "occurrence_source": "original_post",
            },
            "post_type_keys": ["hands_on"],
            "discourse_keys": ["technical_analysis"],
            "sentiment_keys": ["positive"],
        },
        {
            "evidence_id": f"{brand_key}_{window_days}_release",
            "source_cluster_id": f"{brand_key}_{window_days}_source_two",
            "theme_cluster_id": "downloads_and_intelligence",
            "author_group_id": f"{brand_key}_{window_days}_author_two",
            "excerpt": (
                f"A separate post discussed {display_name}'s latest model release "
                "and reported more downloads after trying it."
            ),
            "roles": ["recurring_theme"],
            "source_flags": {
                "official": False,
                "post_kind": "source_post",
                "metrics_observed": True,
                "occurrence_source": "original_post",
            },
            "post_type_keys": ["hands_on"],
            "discourse_keys": ["technical_analysis"],
            "sentiment_keys": ["positive"],
        },
    ]
    metadata = {
        "selected_coverage_ratio": "1.000000",
        "prior_coverage_ratio": "1.000000",
        "labels": [],
    }
    post_type = dict(metadata)
    sentiment = dict(metadata)
    if include_mix:
        post_type["labels"] = [
            {
                "key": "hands_on",
                "selected_count": 16,
                "prior_count": 10,
                "selected_basis_count": selected_posts,
                "prior_basis_count": prior_posts,
                "brand_change_pp": "6.000000",
            }
        ]
        sentiment["labels"] = [
            {
                "key": "positive",
                "selected_count": 30,
                "prior_count": 20,
                "selected_basis_count": selected_posts,
                "prior_basis_count": prior_posts,
                "brand_change_pp": "10.000000",
            }
        ]
    candidate_id = f"{brand_key}:full_window"
    candidate = {
        "candidate_id": candidate_id,
        "brand_key": brand_key,
        "display_name_en": display_name,
        "display_name_zh_cn": display_name,
        "kind": "full_window",
        "start_at": (as_of - timedelta(days=window_days)).isoformat(),
        "end_at": as_of.isoformat(),
        "signals": [{"family": "post_type" if include_mix else "volume", "rank": 1}],
        "family_facts": {
            "volume": {
                "selected_count": selected_posts,
                "selected_authors": 40,
                "prior_count": prior_posts,
                "prior_authors": 35,
                "change_pct": volume_change,
                "comparison_state": "available",
            },
            "engagement": {
                "selected": {"eligible_count": selected_posts, "intensity": "5.0"},
                "prior": {"eligible_count": prior_posts, "intensity": "5.0"},
                "intensity_change_pct": "0.000000",
            },
            "post_type": post_type,
            "discourse": metadata,
            "sentiment": sentiment,
            "china_nationalism": metadata,
            "us_nationalism": metadata,
        },
        "metadata_trajectories": {},
        "episodes": [],
        "series": {
            "coarse": {
                "post_counts": [selected_posts // 2, selected_posts - selected_posts // 2],
                "author_counts": [20, 20],
                "engagement": {
                    "eligible_counts": [selected_posts // 2, selected_posts - selected_posts // 2],
                    "missing_counts": [0, 0],
                    "coverage_ratios": ["1.000000", "1.000000"],
                    "interactions": [100, 100],
                    "intensities": ["5.000000", "5.000000"],
                    "concentrations": ["0.200000", "0.200000"],
                    "post_kinds": {},
                },
            }
        },
        "evidence_allocation": {"role": "lead", "selected_count": 2},
        "evidence_support": {
            "official_source_count": 0,
            "distinct_author_group_count": 2,
            "distinct_source_cluster_count": 2,
            "event_claim_may_be_supported": True,
            "evidence_only_entity_may_be_supported": False,
        },
        "evidence": evidence,
    }
    return {
        "snapshot_schema_version": 1,
        "window_days": window_days,
        "as_of": as_of.isoformat(),
        "coverage": {
            "selected": {"state": "sufficient", "ratio": "1.000000"},
            "prior": {"state": "sufficient", "ratio": "1.000000"},
        },
        "unresolved_backlog_intervals": [],
        "comparison_suppressed_reasons": [],
        "comparison_allowed": True,
        "thresholds": {"minimum_coverage": "0.750000"},
        "evidence_policy": {"version": "browser-why-first-v1"},
        "series_axis": {"coarse": {"bucket_count": 2, "bucket_seconds": 3600}},
        "selection": {"candidate_count": 1},
        "candidates": [candidate],
    }


@override_settings(STORAGES=V22_BROWSER_TEST_STORAGES)
class HomeV22BrowserTests(StaticLiveServerTestCase):
    """Root-route, real-PostgreSQL browser proof for the visible shell."""

    def setUp(self) -> None:
        """Rebuild browser-visible fixtures after TransactionTestCase flushes."""
        super().setUp()
        self.fixture = fixture_from_oracle()
        seed_real_home_orm(self.fixture)
        _clear_home_pulse_cache()
        from django.contrib.auth import get_user_model

        self.browser_user = get_user_model().objects.create_user(
            username="v22-browser-verifier",
            email=V22_TEST_USER_EMAIL,
            password="v22-browser-test-only-password",
        )

    def _authenticated_cookies(self, locale: str) -> list[dict[str, str]]:
        client = Client(HTTP_HOST="localhost")
        client.force_login(self.browser_user)
        response = client.post(f"/locale/{locale}/", HTTP_REFERER="/")
        self.assertEqual(response.status_code, 302)
        return _cookie_payload(client, self.live_server_url)

    def _anonymous_cookies(self, locale: str) -> list[dict[str, str]]:
        client = Client(HTTP_HOST="localhost")
        response = client.post(f"/locale/{locale}/", HTTP_REFERER="/")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", client.session)
        self.assertEqual(client.get("/internal/").status_code, 302)
        return _cookie_payload(client, self.live_server_url)

    def _context_with_cookies(
        self, browser, cookies: list[dict[str, str]], viewport: dict[str, int]
    ) -> BrowserContext:
        context = browser.new_context(viewport=viewport, timezone_id="Asia/Tokyo")
        _freeze_clock(context)
        context.add_cookies(cookies)
        return context

    def _publish_why_first_browser_narrative(
        self,
        *,
        snapshot: dict[str, object],
        body_en: str,
        body_zh_cn: str,
        families: list[str],
        quantitative_fact_keys: list[tuple[str, str]],
        explanation_type: str,
        evidence_ids: list[str],
    ) -> None:
        from core.models import Brand
        from monitor.trend_narrative_candidates import project_provider_packet
        from monitor.trend_narrative_lifecycle import (
            mark_transport_completed,
            mark_transport_started,
            publish_generation,
            reserve_generation,
        )

        candidate = snapshot["candidates"][0]
        brand_key = candidate["brand_key"]
        display_name = candidate["display_name_en"]
        Brand.objects.update_or_create(
            nickname=brand_key,
            defaults={
                "display_name": display_name,
                "display_name_en": display_name,
                "display_name_zh_cn": display_name,
            },
        )
        facts = {
            (fact["family"], fact["metric"]): fact["fact_id"]
            for fact in project_provider_packet(snapshot)["candidates"][0][
                "quantitative_facts"
            ]
        }
        fact_ids = [facts[key] for key in quantitative_fact_keys]
        as_of = datetime.fromisoformat(snapshot["as_of"])
        window_days = snapshot["window_days"]
        candidate_id = candidate["candidate_id"]
        owner = f"browser-why-first-{window_days}"
        row = reserve_generation(
            source_cycle_id=owner,
            window_days=window_days,
            facts_as_of=as_of,
            semantic_fingerprint=f"{window_days:064x}",
            generation_facts=snapshot,
            publication_epoch=10,
            prompt_version="headline-v10-why-first-quantitative-color",
            provider="deepseek",
            provider_host="api.deepseek.com",
            llm_model_name="deepseek-v4-pro",
            owner=owner,
            now=as_of,
            lease_seconds=90,
            output_schema_version=3,
        )
        self.assertIsNotNone(row)
        self.assertTrue(
            mark_transport_started(
                row.pk,
                owner=owner,
                fence=row.claim_fence,
                now=as_of,
            )
        )
        self.assertTrue(
            mark_transport_completed(
                row.pk,
                owner=owner,
                fence=row.claim_fence,
                now=as_of + timedelta(milliseconds=250),
            )
        )
        claim = {
            "observation_index": -1,
            "candidate_ids": [candidate_id],
            "families": families,
            "evidence_ids": evidence_ids,
            "quantitative_fact_ids": fact_ids,
            "event_anchor": "latest model release" if window_days == 1 else "",
            "explanation_type": explanation_type,
            "evidence_confidence": (
                "recurring_independent" if evidence_ids else "aggregate_only"
            ),
        }
        self.assertTrue(
            publish_generation(
                row.pk,
                owner=owner,
                fence=row.claim_fence,
                body_en=body_en,
                body_zh_cn=body_zh_cn,
                output_hash=(str(window_days)[-1] or "0") * 64,
                input_tokens=500,
                output_tokens=120,
                latency_ms=250,
                now=as_of + timedelta(seconds=1),
                observations_en=[],
                observations_zh_cn=[],
                selected_candidate_ids=[candidate_id],
                claims=[claim],
                subjects=[
                    {
                        "position": 0,
                        "support_type": "measured_candidate",
                        "entity_type": "brand",
                        "identity_type": "brand",
                        "canonical_key_snapshot": brand_key,
                        "name_en_snapshot": display_name,
                        "name_zh_cn_snapshot": display_name,
                        "candidate_id": candidate_id,
                        "evidence_ids": [],
                    }
                ],
            )
        )

    def test_zh_hans_renders_chinese_chrome_in_browser(self) -> None:
        """The Django ``zh_hans`` alias keeps v22 chrome Chinese after JS initializes."""
        cookies = self._anonymous_cookies("zh_hans")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._context_with_cookies(browser, cookies, VIEWPORTS["desktop"])
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.wait_for_function("() => window.__pwTz && window.pwApplyChrome")
                    self.assertEqual(page.locator("body").get_attribute("data-pw-locale"), "zh_hans")
                    self.assertEqual(page.locator("nav.locale-toggle").get_attribute("aria-label"), "显示语言")
                    self.assertEqual(page.locator("[data-pw-locale-btn='zh_cn']").inner_text(), "中文")
                    self.assertEqual(page.locator("[data-pw-locale-btn='zh_cn']").get_attribute("class"), "is-active")
                    self.assertEqual(page.locator("[data-tz-zone]").inner_text(), "本地")
                finally:
                    context.close()
            finally:
                browser.close()

    def test_mobile_touchend_fallback_opens_brand_dropdown(self) -> None:
        """An iOS touch with no synthetic click still opens Brands."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    **playwright.devices["iPhone 13"],
                    timezone_id="Asia/Tokyo",
                )
                _freeze_clock(context)
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                page.on(
                    "console",
                    lambda message: console_errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    page.wait_for_function("() => window.pwFilter")
                    pill = page.locator('[data-group="brands"]')

                    pill.dispatch_event("touchend")
                    page.wait_for_timeout(150)

                    self.assertEqual(pill.get_attribute("aria-expanded"), "true")
                    dropdown = page.locator("body > .filter-dropdown.is-portaled")
                    self.assertEqual(dropdown.count(), 1)
                    self.assertTrue(dropdown.is_visible())
                    box = dropdown.bounding_box()
                    self.assertIsNotNone(box)
                    self.assertGreater(box["width"], 0)
                    self.assertGreater(box["height"], 0)
                    self.assertGreaterEqual(box["x"], 0)
                    self.assertLessEqual(box["x"] + box["width"], VIEWPORTS["mobile"]["width"] + 1)

                    # A physical iOS tap may activate through the fallback and
                    # still deliver a delayed synthetic click. That click must
                    # not close the menu that the fallback just opened.
                    pill.dispatch_event("click")
                    self.assertEqual(pill.get_attribute("aria-expanded"), "true")
                    self.assertTrue(dropdown.is_visible())

                    dropdown.locator('[data-lens="closed"]').click()
                    self.assertEqual(pill.get_attribute("aria-expanded"), "true")
                    self.assertTrue(dropdown.is_visible())

                    page.locator("h1.app-name").dispatch_event("pointerdown")
                    self.assertEqual(pill.get_attribute("aria-expanded"), "false")
                    self.assertFalse(dropdown.is_visible())

                    pill.dispatch_event("click")
                    self.assertEqual(pill.get_attribute("aria-expanded"), "true")
                    self.assertTrue(dropdown.is_visible())
                    self.assertEqual(console_errors, [])
                    self.assertEqual(page_errors, [])
                finally:
                    context.close()
            finally:
                browser.close()

    def test_mobile_locale_toggle_stays_inside_title_row(self) -> None:
        """Locale controls stay within their containing title row on mobile."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale in ("en", "zh_hans"):
                    with self.subTest(locale=locale):
                        device = {
                            **playwright.devices["iPhone 13"],
                            "viewport": {"width": 320, "height": 844},
                        }
                        context = browser.new_context(
                            **device,
                            timezone_id="Asia/Tokyo",
                        )
                        _freeze_clock(context)
                        page = context.new_page()
                        try:
                            page.goto(
                                f"{self.live_server_url}/?locale={locale}",
                                wait_until="networkidle",
                            )
                            page.add_style_tag(
                                content="""
                                  body.desktop-shell .topbar-title-row .locale-toggle button {
                                    font-size: 26px !important;
                                  }
                                """
                            )
                            boxes = page.evaluate(
                                """() => {
                                  const rectFor = (element) => {
                                    const rect = element.getBoundingClientRect();
                                    return {left: rect.left, right: rect.right, width: rect.width, height: rect.height};
                                  };
                                  const row = document.querySelector('.topbar-title-row').getBoundingClientRect();
                                  const appName = document.querySelector('h1.app-name').getBoundingClientRect();
                                  const locale = document.querySelector('.locale-toggle').getBoundingClientRect();
                                  const topbar = document.querySelector('.topbar').getBoundingClientRect();
                                  const controls = document.querySelector('.topbar-controls');
                                  const timeWindow = controls.querySelector('.window-toggle');
                                  const timezone = controls.querySelector('.tz-pill');
                                  return {
                                    row: {left: row.left, right: row.right, width: row.width},
                                    appName: {left: appName.left, right: appName.right, width: appName.width},
                                    locale: {left: locale.left, right: locale.right, width: locale.width},
                                    topbar: {left: topbar.left, right: topbar.right},
                                    controls: rectFor(controls),
                                    timeWindow: rectFor(timeWindow),
                                    timezone: rectFor(timezone),
                                    localeLabels: [...document.querySelectorAll('.locale-toggle button')].map((button) => ({
                                      button: rectFor(button),
                                      overflow: getComputedStyle(button).overflow,
                                      textOverflow: getComputedStyle(button).textOverflow,
                                    })),
                                    viewport: innerWidth,
                                  };
                                }"""
                            )
                            self.assertGreater(boxes["appName"]["width"], 0)
                            self.assertGreaterEqual(
                                boxes["appName"]["left"],
                                boxes["row"]["left"] - 0.5,
                            )
                            self.assertGreater(boxes["locale"]["width"], 0)
                            self.assertGreaterEqual(
                                boxes["locale"]["left"],
                                boxes["row"]["left"] - 0.5,
                            )
                            self.assertLessEqual(
                                boxes["locale"]["right"],
                                boxes["row"]["right"] + 0.5,
                            )
                            self.assertLessEqual(
                                boxes["locale"]["right"],
                                boxes["viewport"] + 0.5,
                            )
                            for control_name in ("controls", "timeWindow", "timezone"):
                                self.assertGreater(boxes[control_name]["width"], 0)
                                self.assertGreaterEqual(
                                    boxes[control_name]["left"],
                                    boxes["topbar"]["left"] - 0.5,
                                )
                                self.assertLessEqual(
                                    boxes[control_name]["right"],
                                    boxes["topbar"]["right"] + 0.5,
                                )
                                self.assertLessEqual(
                                    boxes[control_name]["right"],
                                    boxes["viewport"] + 0.5,
                                )
                            for label in boxes["localeLabels"]:
                                self.assertGreater(label["button"]["width"], 0)
                                self.assertEqual(label["overflow"], "hidden")
                                self.assertEqual(label["textOverflow"], "ellipsis")
                        finally:
                            context.close()
            finally:
                browser.close()

    def test_anonymous_chart_is_live_canvas_and_window_refetch_is_atomic(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(viewport=VIEWPORTS["desktop"], timezone_id="Asia/Tokyo")
                _freeze_clock(context)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.wait_for_function(
                        "() => { const c = document.querySelector('canvas.home-chart'); return c && window.Chart?.getChart(c); }"
                    )
                    self.assertEqual(page.locator("svg.home-chart").count(), 0)
                    canvas = page.locator("canvas.home-chart")
                    self.assertEqual(canvas.count(), 1)
                    box = canvas.bounding_box()
                    self.assertIsNotNone(box)
                    self.assertGreater(box["width"], 0)
                    self.assertGreater(box["height"], 0)
                    runtime = page.evaluate(
                        """() => {
                          const canvas = document.querySelector('canvas.home-chart');
                          const chart = Chart.getChart(canvas);
                          const context = canvas.getContext('2d', {willReadFrequently: true});
                          const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
                          let painted = 0;
                          for (let index = 3; index < pixels.length; index += 4) painted += pixels[index] > 0 ? 1 : 0;
                          return {
                            datasets: chart.data.datasets.filter((dataset) => dataset._isTotalLine).length,
                            payloadSeries: Object.keys(JSON.parse(canvas.dataset.home).series).length,
                            painted,
                            hidden: chart.data.datasets.map((dataset) => Boolean(dataset.hidden)),
                          };
                        }"""
                    )
                    self.assertEqual(runtime["datasets"], runtime["payloadSeries"])
                    self.assertGreater(runtime["painted"], 0)
                    initial_legend = page.locator("[data-pw-chart-legend]")
                    self.assertEqual(initial_legend.count(), 1)
                    self.assertEqual(initial_legend.locator("span").count(), runtime["payloadSeries"])

                    canvas.hover(position={"x": box["width"] / 2, "y": box["height"] / 2})
                    after_hover = page.evaluate(
                        "() => Chart.getChart(document.querySelector('canvas.home-chart')).data.datasets.map((dataset) => Boolean(dataset.hidden))"
                    )
                    self.assertEqual(after_hover, runtime["hidden"], "hover must not hide a series")

                    with page.expect_response(lambda response: "/chart.html?" in response.url) as response_info:
                        page.locator("[data-pw-window-btn='7']").click()
                    response = response_info.value
                    self.assertEqual(response.status, 200)
                    self.assertNotIn("renderer=", response.url)
                    page.wait_for_function(
                        "() => JSON.parse(document.querySelector('canvas.home-chart').dataset.home).window_days === 7 && document.querySelector('[data-pw-pulse]').dataset.pwWindow === '7'"
                    )
                    projection = page.evaluate(
                        """() => ({
                          chart: JSON.parse(document.querySelector('canvas.home-chart').dataset.home),
                          pulseWindow: Number(document.querySelector('[data-pw-pulse]').dataset.pwWindow),
                          pulseComputedAt: document.querySelector('[data-pw-pulse]').dataset.pwComputedAt,
                          pulseCount: document.querySelectorAll('[data-pw-pulse-entry]').length,
                        })"""
                    )
                    self.assertEqual(projection["chart"]["window_days"], projection["pulseWindow"])
                    self.assertEqual(projection["chart"]["computed_at"], projection["pulseComputedAt"])
                    self.assertEqual(
                        projection["pulseCount"],
                        len(MODEL_DISPLAY_NAMES),
                    )
                    refreshed_legend = page.locator("[data-pw-chart-legend]")
                    self.assertEqual(
                        refreshed_legend.count(),
                        1,
                        "the payload-backed V22 legend must survive an atomic chart refresh",
                    )
                    self.assertEqual(
                        refreshed_legend.locator("span").count(),
                        len(projection["chart"]["series"]),
                    )
                    voice_shape = page.evaluate(
                        """() => {
                          const root = document.querySelector('[data-pw-headline-voice-entries]');
                          const children = [...(root?.children || [])];
                          const links = children.filter((node) => node.matches('a.voice-chip'));
                          const separators = children.filter((node) => node.matches('span.voice-separator'));
                          return {
                            links: links.length,
                            separators: separators.length,
                            adjacentLinks: children.some((node, index) =>
                              node.matches('a.voice-chip') && children[index + 1]?.matches('a.voice-chip')
                            ),
                          };
                        }"""
                    )
                    self.assertEqual(
                        voice_shape["separators"],
                        max(voice_shape["links"] - 1, 0),
                        "client refresh preserves readable Top Voices separators",
                    )
                    self.assertFalse(
                        voice_shape["adjacentLinks"],
                        "client refresh never concatenates adjacent voice links",
                    )
                finally:
                    context.close()
            finally:
                browser.close()

    def test_one_day_chart_uses_dual_time_axes_and_full_width(self) -> None:
        """The production canvas exposes the owner-approved 1d geometry contract."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for viewport in (
                    VIEWPORTS["desktop"],
                    VIEWPORTS["mobile"],
                    {"width": 320, "height": 844},
                ):
                    with self.subTest(viewport=viewport):
                        context = browser.new_context(
                            viewport=viewport,
                            timezone_id="Asia/Tokyo",
                        )
                        page = context.new_page()
                        console_errors: list[str] = []
                        page_errors: list[str] = []
                        page.on(
                            "console",
                            lambda message, errors=console_errors: errors.append(
                                message.text
                            )
                            if message.type == "error"
                            else None,
                        )
                        page.on(
                            "pageerror",
                            lambda error, errors=page_errors: errors.append(str(error)),
                        )
                        try:
                            page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                            page.wait_for_function(
                                "() => { const c = document.querySelector('canvas.home-chart'); return c && window.Chart?.getChart(c); }"
                            )
                            runtime = page.evaluate(
                                """() => {
                                  const region = document.querySelector('section.home-chart-wrap');
                                  const canvas = region.querySelector('canvas.home-chart');
                                  const chart = Chart.getChart(canvas);
                                  const payload = JSON.parse(canvas.dataset.home);
                                  const regionBox = region.getBoundingClientRect();
                                  const canvasBox = canvas.getBoundingClientRect();
                                  const totals = chart.data.datasets.filter((dataset) => dataset._isTotalLine);
                                  const totalMeta = chart.getDatasetMeta(chart.data.datasets.indexOf(totals[0]));
                                  const pulseOrder = payload.pulse.entries
                                    .map((entry) => entry.nickname)
                                    .filter((nickname) => Object.hasOwn(payload.series, nickname));
                                  const chartOnly = Object.keys(payload.series)
                                    .filter((nickname) => !pulseOrder.includes(nickname));
                                  const firstHour = new Date(payload.days[0]);
                                  firstHour.setMinutes(0, 0, 0);
                                  firstHour.setHours(firstHour.getHours() + 1);
                                  const instants = Array.from(
                                    {length: 24},
                                    (_, index) => new Date(firstHour.getTime() + index * 60 * 60 * 1000)
                                  );
                                  const californiaHour = new Intl.DateTimeFormat('en-US', {
                                    timeZone: 'America/Los_Angeles',
                                    hour: 'numeric',
                                    hourCycle: 'h23',
                                  });
                                  const tickLabels = (scale) => scale.ticks.map((tick) => String(tick.label));
                                  return {
                                    scaleKeys: Object.keys(chart.scales).sort(),
                                    localPosition: chart.scales.x?.position,
                                    comparisonPosition: chart.scales.xComparison?.position,
                                    localTop: chart.scales.x?.top,
                                    localBottom: chart.scales.x?.bottom,
                                    comparisonTop: chart.scales.xComparison?.top,
                                    localLabels: chart.scales.x ? tickLabels(chart.scales.x) : [],
                                    comparisonLabels: chart.scales.xComparison
                                      ? tickLabels(chart.scales.xComparison)
                                      : [],
                                    expectedLocal: instants.map((instant) => {
                                      const hour = instant.getHours();
                                      return hour % 2 === 0 ? `${hour}:00` : '';
                                    }),
                                    expectedCalifornia: instants.map((instant) => {
                                      const hour = Number(californiaHour.format(instant));
                                      return hour % 2 === 0 ? `${hour}:00` : '';
                                    }),
                                    localColor: chart.scales.x?.options.ticks.color,
                                    defaultColor: Chart.defaults.color,
                                    comparisonColor: chart.scales.xComparison?.options.ticks.color,
                                    localTitle: chart.scales.x?.options.title.text,
                                    comparisonTitle: chart.scales.xComparison?.options.title.text,
                                    localTitleDisplay: chart.scales.x?.options.title.display,
                                    comparisonTitleDisplay: chart.scales.xComparison?.options.title.display,
                                    localDrawTicks: chart.scales.x?.options.grid.drawTicks,
                                    comparisonDrawTicks: chart.scales.xComparison?.options.grid.drawTicks,
                                    comparisonGridDisplay: chart.scales.xComparison?.options.grid.display,
                                    timezoneLabelPlugin: chart.config.plugins.some(
                                      (plugin) => plugin.id === 'pwTimezoneRowLabels'
                                    ),
                                    alignedTickPixels: chart.scales.x.ticks.every(
                                      (_, index) => Math.abs(
                                        chart.scales.x.getPixelForTick(index) -
                                        chart.scales.xComparison.getPixelForTick(index)
                                      ) <= 0.5
                                    ),
                                    localBorder: chart.scales.x?.options.border.display,
                                    comparisonBorder: chart.scales.xComparison?.options.border.display,
                                    legendOrder: [...region.querySelectorAll('[data-pw-chart-legend] [data-pw-chart-brand]')]
                                      .map((node) => node.dataset.pwChartBrand),
                                    expectedLegendOrder: pulseOrder.concat(chartOnly),
                                    plotWidthRatio: (chart.chartArea.right - chart.chartArea.left) / canvasBox.width,
                                    firstPointOffset: Math.abs(totalMeta.data[0].x - chart.chartArea.left),
                                    lastPointOffset: Math.abs(totalMeta.data.at(-1).x - chart.chartArea.right),
                                    canvasLeftInset: canvasBox.left - regionBox.left,
                                    yTitle: chart.scales.y?.options.title.text,
                                    overflow: document.documentElement.scrollWidth > innerWidth,
                                  };
                                }"""
                            )
                            self.assertEqual(runtime["scaleKeys"], ["x", "xComparison", "y"])
                            self.assertEqual(runtime["localPosition"], "bottom")
                            self.assertEqual(runtime["comparisonPosition"], "bottom")
                            self.assertLess(runtime["localTop"], runtime["comparisonTop"])
                            self.assertLessEqual(
                                abs(runtime["localBottom"] - runtime["comparisonTop"]),
                                1,
                            )
                            self.assertEqual(runtime["localLabels"], runtime["expectedLocal"])
                            self.assertEqual(
                                runtime["comparisonLabels"],
                                runtime["expectedCalifornia"],
                            )
                            self.assertEqual(len(runtime["localLabels"]), 24)
                            self.assertEqual(len(runtime["comparisonLabels"]), 24)
                            self.assertEqual(runtime["localColor"], runtime["defaultColor"])
                            self.assertEqual(
                                runtime["comparisonColor"].replace(" ", ""),
                                "rgba(251,191,36,0.45)",
                            )
                            self.assertEqual(runtime["localTitle"], "local")
                            self.assertEqual(runtime["comparisonTitle"], "CA")
                            self.assertFalse(runtime["localTitleDisplay"])
                            self.assertFalse(runtime["comparisonTitleDisplay"])
                            self.assertTrue(runtime["timezoneLabelPlugin"])
                            self.assertTrue(runtime["localDrawTicks"])
                            self.assertFalse(runtime["comparisonDrawTicks"])
                            self.assertFalse(runtime["comparisonGridDisplay"])
                            self.assertTrue(runtime["alignedTickPixels"])
                            self.assertTrue(runtime["localBorder"])
                            self.assertFalse(runtime["comparisonBorder"])
                            self.assertEqual(
                                runtime["legendOrder"],
                                runtime["expectedLegendOrder"],
                            )
                            self.assertGreaterEqual(runtime["plotWidthRatio"], 0.85)
                            self.assertLessEqual(runtime["firstPointOffset"], 1)
                            self.assertLessEqual(runtime["lastPointOffset"], 1)
                            self.assertLessEqual(runtime["canvasLeftInset"], 2)
                            self.assertEqual(runtime["yTitle"], "posts / 5min")
                            self.assertFalse(runtime["overflow"])
                            self.assertEqual(console_errors, [])
                            self.assertEqual(page_errors, [])

                            with page.expect_response(
                                lambda response: "/chart.html?" in response.url
                            ) as response_info:
                                page.locator("[data-pw-window-btn='7']").click()
                            self.assertEqual(response_info.value.status, 200)
                            page.wait_for_function(
                                "() => JSON.parse(document.querySelector('canvas.home-chart').dataset.home).window_days === 7"
                            )
                            self.assertEqual(
                                page.evaluate(
                                    "() => Object.keys(Chart.getChart(document.querySelector('canvas.home-chart')).scales).sort()"
                                ),
                                ["x", "y"],
                            )
                        finally:
                            context.close()
            finally:
                browser.close()

    def test_long_window_switches_commit_before_the_client_timeout(self) -> None:
        """Cold and warm 30d/365d responses keep the atomic projection usable."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    viewport=VIEWPORTS["desktop"],
                    timezone_id="Asia/Tokyo",
                )
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                page.on(
                    "console",
                    lambda message: console_errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    page.wait_for_function("() => window.pwFilter")
                    timings: dict[int, list[float]] = {30: [], 365: []}
                    for window_days in (30, 365, 30, 365):
                        started_at = page.evaluate("performance.now()")
                        with page.expect_response(
                            lambda response: "/chart.html?" in response.url
                        ) as response_info:
                            page.locator(
                                f"[data-pw-window-btn='{window_days}']"
                            ).click()
                        self.assertEqual(response_info.value.status, 200)
                        page.wait_for_function(
                            "windowDays => { const canvas = document.querySelector('canvas.home-chart'); const payload = JSON.parse(canvas.dataset.home); return payload.window_days === windowDays && document.querySelector('[data-pw-pulse]').dataset.pwWindow === String(windowDays); }",
                            arg=window_days,
                        )
                        elapsed_seconds = (
                            page.evaluate("performance.now()") - started_at
                        ) / 1000
                        timings[window_days].append(elapsed_seconds)
                        self.assertLess(elapsed_seconds, 12)
                        self.assertEqual(
                            page.locator("section.home-chart-wrap").get_attribute(
                                "data-pw-refresh-failed"
                            ),
                            "false",
                        )

                    self.assertLess(timings[30][1], 2)
                    self.assertLess(timings[365][1], 2)
                    self.assertEqual(console_errors, [])
                    self.assertEqual(page_errors, [])
                finally:
                    context.close()
            finally:
                browser.close()

    def test_one_day_california_axis_keeps_fall_back_hours_in_browser(self) -> None:
        """The production refresh path renders 24 real instants across CA DST."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    viewport=VIEWPORTS["desktop"],
                    timezone_id="Asia/Tokyo",
                )
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                page.on(
                    "console",
                    lambda message: console_errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    page.wait_for_function("() => window.pwFilter")
                    fixture_computed_at = "2026-11-01T12:34:00+00:00"
                    page.evaluate(
                        """fixtureComputedAt => {
                          const canvas = document.querySelector('canvas.home-chart');
                          const payload = JSON.parse(canvas.dataset.home);
                          const end = Date.parse(fixtureComputedAt);
                          payload.days = Array.from(
                            {length: 288},
                            (_, index) => new Date(end - (288 - index) * 5 * 60 * 1000).toISOString()
                          );
                          Object.keys(payload.series).forEach((brand) => {
                            payload.series[brand] = payload.days.map(() => 1);
                          });
                          payload.computed_at = fixtureComputedAt;
                          payload.fetched_at = fixtureComputedAt;
                          [payload.pulse, payload.trend_narrative, payload.top_voices]
                            .forEach((projection) => { projection.computed_at = fixtureComputedAt; });
                          const replacement = document.createElement('canvas');
                          replacement.className = 'home-chart';
                          replacement.setAttribute('data-home', JSON.stringify(payload));
                          const html = replacement.outerHTML +
                            '<p class="chart-state" data-pw-chart-status hidden></p>';
                          window.fetch = () => Promise.resolve({
                            ok: true,
                            text: () => Promise.resolve(html),
                          });
                          document.dispatchEvent(new CustomEvent('pw:filter-change', {
                            detail: {filters: {window: 1}},
                          }));
                        }""",
                        fixture_computed_at,
                    )
                    page.wait_for_function(
                        "computedAt => JSON.parse(document.querySelector('canvas.home-chart').dataset.home).computed_at === computedAt",
                        arg=fixture_computed_at,
                    )
                    california_axis = page.evaluate(
                        """() => {
                          const canvas = document.querySelector('canvas.home-chart');
                          const chart = Chart.getChart(canvas);
                          const formatter = new Intl.DateTimeFormat('en-US', {
                            timeZone: 'America/Los_Angeles',
                            hour: 'numeric',
                            hourCycle: 'h23',
                          });
                          const ticks = chart.scales.xComparison.ticks;
                          const firstHour = new Date(chart.data.labels[0]);
                          firstHour.setMinutes(0, 0, 0);
                          firstHour.setHours(firstHour.getHours() + 1);
                          const hours = ticks.map((_, index) => Number(
                            formatter.format(new Date(
                              firstHour.getTime() + index * 60 * 60 * 1000
                            ))
                          ));
                          return {
                            labels: ticks.map((tick) => String(tick.label)),
                            hours,
                          };
                        }"""
                    )
                    self.assertEqual(len(california_axis["labels"]), 24)
                    self.assertEqual(california_axis["hours"].count(1), 2)
                    self.assertEqual(
                        california_axis["labels"],
                        [
                            f"{hour}:00" if hour % 2 == 0 else ""
                            for hour in california_axis["hours"]
                        ],
                    )
                    self.assertEqual(console_errors, [])
                    self.assertEqual(page_errors, [])
                finally:
                    context.close()
            finally:
                browser.close()

    def test_top_voices_refresh_keeps_separator_parity_on_mobile(self) -> None:
        """Client-rendered Top Voices remain readable at the narrow V22 width."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(viewport=VIEWPORTS["mobile"], timezone_id="Asia/Tokyo")
                _freeze_clock(context)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    page.wait_for_function("() => window.pwFilter")
                    with page.expect_response(lambda response: "/chart.html?" in response.url) as response_info:
                        page.locator("[data-pw-window-btn='7']").click()
                    self.assertEqual(response_info.value.status, 200)
                    page.wait_for_function(
                        "() => document.querySelector('[data-pw-headline-voice-entries]')"
                    )
                    voice_shape = page.evaluate(
                        """() => {
                          const root = document.querySelector('[data-pw-headline-voice-entries]');
                          const children = [...(root?.children || [])];
                          const links = children.filter((node) => node.matches('a.voice-chip'));
                          const separators = children.filter((node) => node.matches('span.voice-separator'));
                          const box = root?.getBoundingClientRect();
                          return {
                            links: links.length,
                            separators: separators.length,
                            adjacentLinks: children.some((node, index) =>
                              node.matches('a.voice-chip') && children[index + 1]?.matches('a.voice-chip')
                            ),
                            width: box?.width || 0,
                            height: box?.height || 0,
                            overflow: document.documentElement.scrollWidth > innerWidth,
                          };
                        }"""
                    )
                    self.assertEqual(voice_shape["separators"], max(voice_shape["links"] - 1, 0))
                    self.assertFalse(voice_shape["adjacentLinks"])
                    self.assertGreater(voice_shape["width"], 0)
                    self.assertGreater(voice_shape["height"], 0)
                    self.assertFalse(voice_shape["overflow"])
                finally:
                    context.close()
            finally:
                browser.close()

    def test_schema_two_headline_renders_two_subjects_without_duplicate_anchor(
        self,
    ) -> None:
        """The real V22 template composes its anchor and body exactly once."""
        from core.models import Brand
        from monitor.trend_narrative_lifecycle import (
            mark_transport_completed,
            mark_transport_started,
            publish_generation,
            reserve_generation,
        )
        from x_monitor.config import HeadlineNarrativeConfig

        as_of = datetime.now(UTC)
        for key, name in (("minimax", "MiniMax"), ("deepseek", "DeepSeek")):
            Brand.objects.update_or_create(
                nickname=key,
                defaults={
                    "display_name": name,
                    "display_name_en": name,
                    "display_name_zh_cn": name,
                },
            )
        candidate_ids = ["minimax:full_window", "deepseek:episode:one"]
        snapshot = {
            "snapshot_schema_version": 1,
            "window_days": 1,
            "as_of": as_of.isoformat(),
            "coverage": {"state": "sufficient", "ratio": "1.000000"},
            "candidates": [
                {"candidate_id": candidate_id, "evidence": []}
                for candidate_id in candidate_ids
            ],
        }
        row = reserve_generation(
            source_cycle_id="browser-schema-two",
            window_days=1,
            facts_as_of=as_of,
            semantic_fingerprint="e" * 64,
            generation_facts=snapshot,
            publication_epoch=5,
            prompt_version="headline-v5-analytical",
            provider="deepseek",
            provider_host="api.deepseek.com",
            llm_model_name="deepseek-v4-pro",
            owner="browser-worker",
            now=as_of,
            lease_seconds=90,
            output_schema_version=2,
        )
        self.assertIsNotNone(row)
        self.assertTrue(
            mark_transport_started(
                row.pk,
                owner="browser-worker",
                fence=row.claim_fence,
                now=as_of,
            )
        )
        self.assertTrue(
            mark_transport_completed(
                row.pk,
                owner="browser-worker",
                fence=row.claim_fence,
                now=as_of + timedelta(milliseconds=500),
            )
        )
        subjects = [
            {
                "position": position,
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "identity_type": "brand",
                "canonical_key_snapshot": key,
                "name_en_snapshot": name,
                "name_zh_cn_snapshot": name,
                "candidate_id": candidate_ids[position],
                "evidence_ids": [],
            }
            for position, (key, name) in enumerate(
                (("minimax", "MiniMax"), ("deepseek", "DeepSeek"))
            )
        ]
        self.assertTrue(
            publish_generation(
                row.pk,
                owner="browser-worker",
                fence=row.claim_fence,
                body_en=(
                    "MiniMax and DeepSeek both break into unusually sustained attention."
                ),
                body_zh_cn="MiniMax 与 DeepSeek 均进入异常且持续的高关注状态。",
                output_hash="f" * 64,
                input_tokens=100,
                output_tokens=40,
                latency_ms=200,
                now=as_of + timedelta(seconds=1),
                observations_en=["Both trajectories rise and then hold."],
                observations_zh_cn=["两条走势均在上升后保持稳定。"],
                selected_candidate_ids=candidate_ids,
                claims=[
                    {
                        "observation_index": -1,
                        "candidate_ids": candidate_ids,
                        "families": ["volume"],
                        "evidence_ids": [],
                    },
                    {
                        "observation_index": 0,
                        "candidate_ids": candidate_ids,
                        "families": ["volume"],
                        "evidence_ids": [],
                    }
                ],
                subjects=subjects,
            )
        )

        config = HeadlineNarrativeConfig(
            serving_enabled=True,
            activation_state="owner_override",
        )
        with (
            patch(
                "monitor.trend_narrative_projection._load_config",
                return_value=config,
            ),
            sync_playwright() as playwright,
        ):
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    viewport=VIEWPORTS["desktop"],
                    timezone_id="Asia/Tokyo",
                )
                _freeze_clock(context)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    headline_body = page.locator("[data-pw-headline] .body")
                    rendered = " ".join(headline_body.inner_text().split())
                    self.assertEqual(rendered.count("MiniMax"), 1)
                    self.assertEqual(rendered.count("DeepSeek"), 1)
                    self.assertEqual(
                        headline_body.locator("[data-pw-headline-brand]").count(),
                        1,
                    )
                    self.assertEqual(
                        headline_body.locator("[data-pw-headline-brand]").get_attribute(
                            "href"
                        ),
                        "/brands/minimax/",
                    )
                    observations = page.locator(
                        "[data-pw-headline-observations] > li"
                    )
                    self.assertEqual(observations.count(), 1)
                    self.assertEqual(
                        observations.first.inner_text(),
                        "Both trajectories rise and then hold.",
                    )
                    observation_shape = observations.first.bounding_box()
                    self.assertIsNotNone(observation_shape)
                    self.assertGreater(observation_shape["width"], 0)
                    self.assertGreater(observation_shape["height"], 0)
                    payload = page.evaluate(
                        """() => JSON.parse(
                          document.querySelector('canvas.home-chart').dataset.home
                        ).trend_narrative"""
                    )
                    self.assertEqual(payload["schema_version"], 2)
                    self.assertEqual(len(payload["subjects"]), 2)
                    self.assertEqual(
                        payload["observations"],
                        ["Both trajectories rise and then hold."],
                    )
                    self.assertNotIn("claims", payload)
                    self.assertNotIn("evidence_ids", json.dumps(payload))
                    page.evaluate(
                        """() => {
                          const list = document.querySelector('[data-pw-headline-observations]');
                          list.firstElementChild.textContent = 'stale browser copy';
                        }"""
                    )
                    page.locator('[data-group="sentiment"]').press("Enter")
                    with page.expect_response(
                        lambda response: "/chart.html?" in response.url
                    ) as chart_info:
                        page.locator(
                            'body > .filter-dropdown.is-portaled input[value="positive"]'
                        ).uncheck()
                    self.assertIn(
                        "Both trajectories rise and then hold.",
                        chart_info.value.text(),
                    )
                    page.wait_for_function(
                        """() => document.querySelector(
                          '[data-pw-headline-observations] > li'
                        ).textContent === 'Both trajectories rise and then hold.'"""
                    )

                    page.goto(
                        f"{self.live_server_url}/?locale=zh_hans",
                        wait_until="networkidle",
                    )
                    zh_observations = page.locator(
                        "[data-pw-headline-observations] > li"
                    )
                    self.assertEqual(zh_observations.count(), 1)
                    self.assertEqual(
                        zh_observations.first.inner_text(),
                        "两条走势均在上升后保持稳定。",
                    )
                    zh_shape = zh_observations.first.bounding_box()
                    self.assertIsNotNone(zh_shape)
                    self.assertGreater(zh_shape["width"], 0)
                    self.assertGreater(zh_shape["height"], 0)
                finally:
                    context.close()
            finally:
                browser.close()

    def test_no_story_headline_is_bilingual_after_atomic_dom_replacement(
        self,
    ) -> None:
        """A newer empty check replaces stale story DOM in both locales."""
        from monitor.trend_narrative_lifecycle import record_no_call_check
        from x_monitor.config import HeadlineNarrativeConfig

        checked_at = datetime.now(UTC)
        for window_days in (1, 7):
            facts = {
                "snapshot_schema_version": 1,
                "window_days": window_days,
                "as_of": checked_at.isoformat(),
                "coverage": {
                    "selected": {
                        "state": "sufficient",
                        "ratio": "1.000000",
                    },
                    "prior": {
                        "state": "sufficient",
                        "ratio": "1.000000",
                    },
                },
                "candidates": [],
            }
            self.assertIsNotNone(
                record_no_call_check(
                    source_cycle_id=f"browser-no-story-{window_days}",
                    window_days=window_days,
                    facts_as_of=checked_at,
                    semantic_fingerprint=str(window_days) * 64,
                    facts=facts,
                    checked_at=checked_at,
                    status="checked",
                    reason_code="insufficient_data",
                )
            )

        config = HeadlineNarrativeConfig(
            serving_enabled=True,
            activation_state="owner_override",
        )
        with (
            patch(
                "monitor.trend_narrative_projection._load_config",
                return_value=config,
            ),
            sync_playwright() as playwright,
        ):
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    viewport=VIEWPORTS["desktop"],
                    timezone_id="Asia/Tokyo",
                )
                _freeze_clock(context)
                page = context.new_page()
                try:
                    expected_en = (
                        "No clear conversation story emerged in this window."
                    )
                    page.goto(
                        f"{self.live_server_url}/?locale=en",
                        wait_until="networkidle",
                    )
                    headline = page.locator("[data-pw-headline]")
                    body = headline.locator("[data-pw-headline-body]")
                    self.assertEqual(body.inner_text(), expected_en)
                    self.assertEqual(
                        headline.locator("[data-pw-headline-brand]").count(),
                        0,
                    )
                    shape = body.bounding_box()
                    self.assertIsNotNone(shape)
                    self.assertGreater(shape["width"], 0)
                    self.assertGreater(shape["height"], 0)

                    body.evaluate(
                        "node => { node.textContent = 'stale browser story'; }"
                    )
                    with page.expect_response(
                        lambda response: "/chart.html?" in response.url
                    ):
                        page.locator("[data-pw-window-btn='7']").click()
                    page.wait_for_function(
                        """expected => document.querySelector(
                          '[data-pw-headline-body]'
                        )?.textContent === expected""",
                        arg=expected_en,
                    )
                    self.assertTrue(
                        headline.locator(
                            "[data-pw-headline-observations]"
                        ).is_hidden()
                    )
                    payload = page.evaluate(
                        """() => JSON.parse(
                          document.querySelector('canvas.home-chart').dataset.home
                        ).trend_narrative"""
                    )
                    self.assertEqual(payload["schema_version"], 2)
                    self.assertEqual(payload["window_days"], 7)
                    self.assertEqual(payload["body"], expected_en)
                    self.assertEqual(payload["subjects"], [])

                    page.goto(
                        f"{self.live_server_url}/?locale=zh_hans",
                        wait_until="networkidle",
                    )
                    expected_zh = "这一时间段内没有出现明确的讨论主题。"
                    zh_body = page.locator("[data-pw-headline-body]")
                    self.assertEqual(zh_body.inner_text(), expected_zh)
                    zh_shape = zh_body.bounding_box()
                    self.assertIsNotNone(zh_shape)
                    self.assertGreater(zh_shape["width"], 0)
                    self.assertGreater(zh_shape["height"], 0)
                finally:
                    context.close()
            finally:
                browser.close()

    def test_why_first_flat_mix_and_quiet_leader_render_after_replacement(
        self,
    ) -> None:
        """Readers see grounded why, numeric color, and candid quiet wording."""
        from x_monitor.config import HeadlineNarrativeConfig

        as_of = datetime.now(UTC)
        release_en = (
            "DeepSeek users reported more downloads and improved intelligence "
            "after its latest model release; hands-on posts increased 60%, "
            "positive sentiment increased 50%, and post volume rose 50%."
        )
        release_zh = (
            "DeepSeek 最新模型发布后，用户称下载次数增加且智能表现提升；"
            "实际使用类帖子增加60%，正面情绪增加50%，帖子量增加50%。"
        )
        flat_en = (
            "DeepSeek users reported more downloads and improved intelligence; "
            "hands-on posts increased 60%, while overall post volume remained "
            "flat at 0% and positive sentiment increased 50%."
        )
        flat_zh = (
            "DeepSeek 用户称下载更频繁且智能表现提升；实际使用类帖子增加60%，"
            "总体帖子量保持在0%，正面情绪增加50%。"
        )
        quiet_en = (
            "In a mostly unremarkable week, MiniMax led with a small 0.1% rise "
            "in post volume."
        )
        quiet_zh = "在整体平淡的一周中，MiniMax 以帖子量小幅增加0.1%居首。"

        self._publish_why_first_browser_narrative(
            snapshot=_why_first_browser_snapshot(
                window_days=1,
                brand_key="deepseek",
                display_name="DeepSeek",
                volume_change="50.000000",
                selected_posts=150,
                prior_posts=100,
                include_mix=True,
                as_of=as_of,
            ),
            body_en=release_en,
            body_zh_cn=release_zh,
            families=["evidence", "post_type", "sentiment", "volume"],
            quantitative_fact_keys=[
                ("post_type", "count_change_pct"),
                ("sentiment", "count_change_pct"),
                ("volume", "change_pct"),
            ],
            explanation_type="recurring_content",
            evidence_ids=["deepseek_1_downloads", "deepseek_1_release"],
        )
        self._publish_why_first_browser_narrative(
            snapshot=_why_first_browser_snapshot(
                window_days=7,
                brand_key="deepseek",
                display_name="DeepSeek",
                volume_change="0.000000",
                selected_posts=100,
                prior_posts=100,
                include_mix=True,
                as_of=as_of,
            ),
            body_en=flat_en,
            body_zh_cn=flat_zh,
            families=["evidence", "post_type", "sentiment", "volume"],
            quantitative_fact_keys=[
                ("post_type", "count_change_pct"),
                ("volume", "change_pct"),
                ("sentiment", "count_change_pct"),
            ],
            explanation_type="structured_mix",
            evidence_ids=["deepseek_7_downloads", "deepseek_7_release"],
        )
        self._publish_why_first_browser_narrative(
            snapshot=_why_first_browser_snapshot(
                window_days=30,
                brand_key="minimax",
                display_name="MiniMax",
                volume_change="0.100000",
                selected_posts=1_001,
                prior_posts=1_000,
                include_mix=False,
                as_of=as_of,
            ),
            body_en=quiet_en,
            body_zh_cn=quiet_zh,
            families=["volume"],
            quantitative_fact_keys=[("volume", "change_pct")],
            explanation_type="quiet_relative_leader",
            evidence_ids=[],
        )

        def normalized(page, selector="[data-pw-headline] .body"):
            return " ".join(page.locator(selector).inner_text().split())

        config = HeadlineNarrativeConfig(
            serving_enabled=True,
            activation_state="owner_override",
        )
        cookies = self._authenticated_cookies("en")
        with (
            patch(
                "monitor.trend_narrative_projection._load_config",
                return_value=config,
            ),
            sync_playwright() as playwright,
        ):
            browser = playwright.chromium.launch()
            try:
                context = self._context_with_cookies(
                    browser,
                    cookies,
                    VIEWPORTS["desktop"],
                )
                page = context.new_page()
                try:
                    response = page.goto(self.live_server_url, wait_until="networkidle")
                    self.assertIsNotNone(response)
                    self.assertTrue(
                        response.headers.get("content-language", "en").startswith("en")
                    )
                    self.assertEqual(normalized(page), release_en)
                    self.assertGreater(
                        page.locator("[data-pw-headline-body]").bounding_box()["height"],
                        0,
                    )

                    for window_days, expected in ((7, flat_en), (30, quiet_en)):
                        page.locator("[data-pw-headline-body]").evaluate(
                            "node => { node.textContent = 'stale headline'; }"
                        )
                        with page.expect_response(
                            lambda result: "/chart.html?" in result.url
                        ):
                            page.locator(
                                f"[data-pw-window-btn='{window_days}']"
                            ).click()
                        page.wait_for_function(
                            """() => !document.querySelector(
                              '[data-pw-headline] .body'
                            )?.innerText.includes('stale headline')""",
                        )
                        self.assertEqual(normalized(page), expected)
                        if window_days == 7:
                            rendered_flat = normalized(page)
                            self.assertNotIn("release", rendered_flat.casefold())
                            self.assertLess(
                                rendered_flat.index("downloads"),
                                rendered_flat.index("60%"),
                            )

                    self.assertNotRegex(
                        normalized(page).casefold(),
                        r"surge|soar|momentum|breakout|remarkable rise",
                    )
                    payload = page.evaluate(
                        """() => JSON.parse(
                          document.querySelector('canvas.home-chart').dataset.home
                        ).trend_narrative"""
                    )
                    self.assertEqual(payload["schema_version"], 2)
                    self.assertNotIn("claims", payload)
                    self.assertNotIn("evidence_ids", json.dumps(payload))

                    with page.expect_navigation(wait_until="networkidle") as navigation:
                        page.locator("[data-pw-locale-btn='zh_cn']").click()
                    self.assertTrue(
                        navigation.value.headers.get("content-language", "").startswith(
                            "zh"
                        )
                    )
                    self.assertEqual(normalized(page), quiet_zh)
                    self.assertEqual(
                        page.locator("[data-pw-window-btn].is-active").get_attribute(
                            "data-pw-window-btn"
                        ),
                        "30",
                    )

                    for window_days, expected in ((7, flat_zh), (30, quiet_zh)):
                        with page.expect_response(
                            lambda result: "/chart.html?" in result.url
                        ):
                            page.locator(
                                f"[data-pw-window-btn='{window_days}']"
                            ).click()
                        page.wait_for_function(
                            """windowDays => document.querySelector(
                              '[data-pw-headline]'
                            )?.getAttribute('data-pw-window') === String(windowDays)""",
                            arg=window_days,
                        )
                        self.assertEqual(normalized(page), expected)
                        if window_days == 7:
                            rendered_flat = normalized(page)
                            self.assertNotIn("发布", rendered_flat)
                            self.assertLess(
                                rendered_flat.index("下载"),
                                rendered_flat.index("60%"),
                            )
                finally:
                    context.close()
            finally:
                browser.close()

    def test_pending_activation_blocks_raw_enabled_headline_in_browser(
        self,
    ) -> None:
        """Requested serving stays visibly disabled until activation resolves."""
        from x_monitor.config import HeadlineNarrativeConfig

        config = HeadlineNarrativeConfig(
            serving_enabled=True,
            activation_state="pending",
        )
        cookies = self._authenticated_cookies("en")
        with (
            patch(
                "monitor.trend_narrative_projection._load_config",
                return_value=config,
            ),
            sync_playwright() as playwright,
        ):
            browser = playwright.chromium.launch()
            try:
                context = self._context_with_cookies(
                    browser,
                    cookies,
                    VIEWPORTS["desktop"],
                )
                page = context.new_page()
                try:
                    response = page.goto(
                        self.live_server_url,
                        wait_until="networkidle",
                    )
                    self.assertIsNotNone(response)
                    self.assertEqual(response.status, 200)
                    state = page.locator("[data-pw-headline-state]")
                    body = page.locator("[data-pw-headline-body]")
                    self.assertEqual(state.inner_text(), "DISABLED")
                    self.assertEqual(body.inner_text(), "Trend summary is unavailable.")
                    for visible in (state, body):
                        shape = visible.bounding_box()
                        self.assertIsNotNone(shape)
                        self.assertGreater(shape["width"], 0)
                        self.assertGreater(shape["height"], 0)
                finally:
                    context.close()
            finally:
                browser.close()

    def test_per_brand_narratives_render_bilingually_as_semantic_cards(self) -> None:
        """The active DTO v3 paints two readable cards on desktop and mobile."""
        from core.models import Brand, BrandTrendNarrative, TrendNarrativeRun
        from monitor.trend_narrative_lifecycle import (
            activate_trend_narrative_run,
            prepare_brand_trend_narrative,
        )
        from x_monitor.config import HeadlineNarrativeConfig

        now = datetime.now(UTC)
        brands = []
        for key, name in (("deepseek", "DeepSeek"), ("minimax", "MiniMax")):
            brand, _ = Brand.objects.update_or_create(
                nickname=key,
                defaults={
                    "display_name": name,
                    "display_name_en": name,
                    "display_name_zh_cn": name,
                },
            )
            brands.append(brand)
        run = TrendNarrativeRun.objects.create(
            source_cycle_id="browser-u6-per-brand",
            window_days=1,
            facts_as_of=now,
            packet_schema_version=3,
            snapshot={"private": True},
            brand_manifest=[brand.nickname for brand in brands],
            batch_manifest=[[brand.nickname for brand in brands]],
            internal_order=[brand.nickname for brand in brands],
        )
        copy = (
            (
                brands[0],
                now - timedelta(minutes=5),
                "DeepSeek discussion rose after developers shared hands-on tests.",
                "Users highlighted faster local inference and steadier coding output.",
                "开发者分享上手测试后，DeepSeek讨论量上升。",
                "用户重点提到更快的本地推理和更稳定的代码输出。",
            ),
            (
                brands[1],
                now - timedelta(hours=2),
                "MiniMax conversation stayed flat while usage questions gained share.",
                "Posts focused on deployment setup rather than a new release.",
                "MiniMax讨论量基本持平，但使用问题的占比上升。",
                "帖子主要讨论部署设置，而非新版本发布。",
            ),
        )
        for brand, verified_at, headline_en, secondary_en, headline_zh, secondary_zh in copy:
            prepare_brand_trend_narrative(
                run=run,
                brand_key=brand.nickname,
                brand_name_en=brand.display_name_en,
                brand_name_zh_cn=brand.display_name_zh_cn,
                status=BrandTrendNarrative.Status.APPROVED,
                attempted_at=verified_at,
                verified_at=verified_at,
                headline_en=headline_en,
                headline_zh_cn=headline_zh,
                secondary_en=secondary_en,
                secondary_zh_cn=secondary_zh,
                critic_decision=BrandTrendNarrative.CriticDecision.APPROVE,
                narrative_kind=BrandTrendNarrative.NarrativeKind.CONTENT_SHIFT,
                confidence=BrandTrendNarrative.Confidence.HIGH,
            )
        self.assertTrue(activate_trend_narrative_run(run.pk, now=now))
        _clear_home_pulse_cache()

        config = HeadlineNarrativeConfig(
            serving_enabled=True,
            activation_state="owner_override",
            publication_source="prefer_per_brand",
            legacy_fallback_enabled=False,
        )
        artifact_dir = _artifact_dir()
        cases = (
            (
                "en",
                self._anonymous_cookies("en"),
                VIEWPORTS["desktop"],
                "DeepSeek discussion rose after developers shared hands-on tests.",
                "Stale · last verified 2 hr ago",
            ),
            (
                "zh_hans",
                self._anonymous_cookies("zh_hans"),
                VIEWPORTS["mobile"],
                "开发者分享上手测试后，DeepSeek讨论量上升。",
                "过期 · 上次验证于2小时前",
            ),
        )
        with (
            patch(
                "monitor.trend_narrative_projection._load_config",
                return_value=config,
            ),
            sync_playwright() as playwright,
        ):
            browser = playwright.chromium.launch()
            try:
                for locale, cookies, viewport, first_headline, stale_label in cases:
                    with self.subTest(locale=locale, viewport=viewport):
                        context = self._context_with_cookies(
                            browser,
                            cookies,
                            viewport,
                        )
                        page = context.new_page()
                        try:
                            response = page.goto(
                                self.live_server_url,
                                wait_until="networkidle",
                            )
                            self.assertIsNotNone(response)
                            self.assertEqual(response.status, 200)
                            cards = page.locator("article[data-pw-headline-item]")
                            self.assertEqual(cards.count(), 2)
                            self.assertEqual(
                                cards.nth(0).locator("h2").evaluate(
                                    """element => Array.from(element.childNodes)
                                      .filter(node => node.nodeType === Node.TEXT_NODE)
                                      .map(node => node.textContent).join('').trim()"""
                                ),
                                first_headline,
                            )
                            self.assertEqual(
                                cards.nth(1)
                                .locator("[data-pw-headline-item-state]")
                                .inner_text(),
                                stale_label,
                            )
                            stale_state = cards.nth(1).locator(
                                "[data-pw-headline-item-state]"
                            )
                            absolute = stale_state.get_attribute("title")
                            self.assertIsNotNone(absolute)
                            self.assertIn("UTC", absolute)
                            self.assertIn(
                                absolute,
                                stale_state.get_attribute("aria-label"),
                            )
                            self.assertTrue(
                                page.locator("[data-pw-headline-legacy]").is_hidden()
                            )
                            detail = cards.nth(0).locator("[data-pw-headline-detail]")
                            secondary = cards.nth(0).locator(
                                "[data-pw-headline-item-secondary]"
                            )
                            self.assertTrue(secondary.is_hidden())
                            self.assertEqual(detail.get_attribute("aria-expanded"), "false")
                            expected_detail = "详情" if locale == "zh_hans" else "detail"
                            expected_hide = "收起" if locale == "zh_hans" else "hide"
                            self.assertEqual(detail.inner_text(), expected_detail)
                            detail.click()
                            self.assertTrue(secondary.is_visible())
                            self.assertEqual(detail.get_attribute("aria-expanded"), "true")
                            self.assertEqual(
                                secondary.locator("[data-pw-headline-hide]").inner_text(),
                                expected_hide,
                            )
                            secondary.locator("[data-pw-headline-hide]").click()
                            self.assertTrue(secondary.is_hidden())
                            self.assertEqual(detail.get_attribute("aria-expanded"), "false")
                            self.assertTrue(detail.evaluate("node => document.activeElement === node"))
                            detail.click()
                            secondary.click()
                            self.assertTrue(secondary.is_hidden())
                            self.assertEqual(detail.get_attribute("aria-expanded"), "false")
                            detail.click()
                            secondary.locator(
                                "[data-pw-headline-secondary-copy]"
                            ).press("Enter")
                            self.assertTrue(secondary.is_hidden())
                            self.assertTrue(detail.evaluate("node => document.activeElement === node"))
                            detail.click()
                            with page.expect_response(
                                lambda response: "/chart.html" in response.url
                                and response.status == 200
                            ):
                                page.evaluate(
                                    "() => document.dispatchEvent(new CustomEvent('pw:filter-change'))"
                                )
                            refreshed_secondary = cards.nth(0).locator(
                                "[data-pw-headline-item-secondary]"
                            )
                            self.assertTrue(refreshed_secondary.is_hidden())
                            self.assertEqual(
                                cards.nth(0)
                                .locator("[data-pw-headline-detail]")
                                .get_attribute("aria-expanded"),
                                "false",
                            )
                            for index in range(2):
                                bounds = cards.nth(index).bounding_box()
                                self.assertIsNotNone(bounds)
                                self.assertGreater(bounds["width"], 0)
                                self.assertGreater(bounds["height"], 0)
                                self.assertLessEqual(
                                    bounds["x"] + bounds["width"],
                                    viewport["width"] + 1,
                                )
                            page.locator("[data-pw-headline]").screenshot(
                                path=str(artifact_dir / f"per-brand-{locale}.png")
                            )
                        finally:
                            context.close()
            finally:
                browser.close()

    def test_anonymous_filters_window_and_pulse_share_one_request_state(self) -> None:
        """One V22 action emits one immutable state to feed and chart."""

        def request_state(url: str) -> tuple[dict[str, object], int]:
            query = parse_qs(urlparse(url).query)
            self.assertEqual(len(query.get("filters", [])), 1, f"missing filters query: {url}")
            self.assertEqual(len(query.get("window", [])), 1, f"missing explicit window query: {url}")
            return json.loads(query["filters"][0]), int(query["window"][0])

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(viewport=VIEWPORTS["desktop"], timezone_id="Asia/Tokyo")
                _freeze_clock(context)
                page = context.new_page()
                requests: list[str] = []
                page.on(
                    "request",
                    lambda request: requests.append(request.url)
                    if "/feed/?" in request.url or "/chart.html?" in request.url
                    else None,
                )

                def act(action) -> tuple[object, object]:
                    before_feed = len([url for url in requests if "/feed/?" in url])
                    before_chart = len([url for url in requests if "/chart.html?" in url])
                    with page.expect_response(lambda response: "/feed/?" in response.url) as feed_info:
                        with page.expect_response(lambda response: "/chart.html?" in response.url) as chart_info:
                            action()
                    feed_response = feed_info.value
                    chart_response = chart_info.value
                    self.assertEqual(feed_response.status, 200)
                    self.assertEqual(chart_response.status, 200)
                    page.wait_for_timeout(75)
                    self.assertEqual(
                        len([url for url in requests if "/feed/?" in url]) - before_feed,
                        1,
                        "one store event must start one feed request",
                    )
                    self.assertEqual(
                        len([url for url in requests if "/chart.html?" in url]) - before_chart,
                        1,
                        "one store event must start one chart request",
                    )
                    feed_state = request_state(feed_response.url)
                    chart_state = request_state(chart_response.url)
                    self.assertEqual(feed_state, chart_state)
                    return feed_response, chart_response

                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    page.wait_for_function(
                        "() => window.pwFilter && document.querySelector('[data-pw-pulse-entry]')"
                    )

                    for selector in (
                        '[data-tier-grid="open"] input[data-pw-filter-group="brands"]',
                        '[data-tier-grid="closed"] input[data-pw-filter-group="brands"]',
                        '[data-group="post_types"] input[data-pw-filter-group="post_types"]',
                        '[data-group="discourse"] input[data-pw-filter-group="discourse"]',
                        '[data-group="role"] input[data-pw-filter-group="role"]',
                        '[data-group="lang"] input[data-pw-filter-group="lang"]',
                        '[data-group="sentiment"] input[data-pw-filter-group="sentiment"]',
                        '[data-tier-grid="us"] input[data-pw-filter-group="us_nationalism"]',
                        '[data-tier-grid="cn"] input[data-pw-filter-group="cn_nationalism"]',
                        '[data-group="unsanctioned"] input[data-pw-filter-group="unsanctioned"]',
                    ):
                        self.assertGreater(page.locator(selector).count(), 0, f"selector matched zero controls: {selector}")

                    unsanctioned_pill = page.locator('[data-group="unsanctioned"]')
                    unsanctioned_pill.press("Enter")
                    dropdown = page.locator("body > .filter-dropdown.is-portaled")
                    unsanctioned = dropdown.locator(
                        'input[data-pw-filter-group="unsanctioned"]'
                    )
                    self.assertFalse(unsanctioned.is_checked())
                    feed_response, chart_response = act(unsanctioned.check)
                    filters, _ = request_state(feed_response.url)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().unsanctioned"), "only")
                    self.assertEqual(filters["unsanctioned"], "only")
                    chart_filters, _ = request_state(chart_response.url)
                    self.assertEqual(chart_filters["unsanctioned"], "only")

                    feed_response, chart_response = act(unsanctioned.uncheck)
                    filters, _ = request_state(feed_response.url)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().unsanctioned"), "off")
                    self.assertEqual(filters["unsanctioned"], "off")
                    chart_filters, _ = request_state(chart_response.url)
                    self.assertEqual(chart_filters["unsanctioned"], "off")

                    brands_pill = page.locator('[data-group="brands"]')
                    brands_pill.press("Enter")
                    self.assertTrue(dropdown.is_visible())
                    box = dropdown.bounding_box()
                    self.assertIsNotNone(box)
                    self.assertGreater(box["width"], 0)
                    self.assertGreater(box["height"], 0)
                    self.assertGreaterEqual(box["x"], 0)
                    self.assertLessEqual(box["x"] + box["width"], VIEWPORTS["desktop"]["width"] + 1)

                    open_grid = dropdown.locator('[data-tier-grid="open"]')
                    act(dropdown.locator('[data-dd-action="clear"][data-dd-scope="visible"]').click)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), [])
                    self.assertEqual(open_grid.locator('input:checked').count(), 0)
                    act(dropdown.locator('[data-dd-action="all"][data-dd-scope="visible"]').click)
                    open_selection = page.evaluate("() => window.pwFilter.get().brands")
                    self.assertIsInstance(open_selection, list)
                    self.assertIn("qwen", open_selection)
                    self.assertNotIn("anthropic", open_selection)
                    brands_pill.press("Escape")

                    nationalism_pill = page.locator('[data-group="nationalism"]')
                    nationalism_pill.press("Enter")
                    dropdown.locator('[data-lens="cn"]').click()
                    act(dropdown.locator('[data-dd-action="clear"][data-dd-scope="visible"]').click)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().cn_nationalism"), [])
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().us_nationalism"), "__all__")
                    act(dropdown.locator('[data-dd-action="all"][data-dd-scope="visible"]').click)
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().cn_nationalism"), "__all__")
                    nationalism_pill.press("Escape")

                    sentiment_pill = page.locator('[data-group="sentiment"]')
                    sentiment_pill.press("Enter")
                    positive = dropdown.locator('input[value="positive"]')
                    self.assertTrue(positive.is_checked())
                    feed_response, _ = act(positive.uncheck)
                    filters, window = request_state(feed_response.url)
                    self.assertEqual(window, 1)
                    self.assertNotEqual(filters.get("sentiment"), "__all__")
                    self.assertNotIn("positive", filters["sentiment"])
                    feed_payload = feed_response.json()
                    page.wait_for_function(
                        "() => JSON.parse(document.querySelector('canvas.home-chart').dataset.home).applied_filters.sentiment"
                    )
                    chart_payload = page.evaluate(
                        "() => JSON.parse(document.querySelector('canvas.home-chart').dataset.home)"
                    )
                    self.assertEqual(
                        sum(chart_payload["totals"].values()),
                        len(feed_payload["rows"]),
                        "fixture feed IDs and chart totals must change together",
                    )

                    pulse = page.locator("[data-pw-pulse-entry]").first
                    self.assertEqual(pulse.evaluate("element => element.parentElement.tagName"), "LI")
                    self.assertEqual(pulse.get_attribute("aria-pressed"), "false")
                    self.assertRegex(pulse.get_attribute("aria-label") or "", r".+, (up|down|flat) \d+ percent|.+, NEW")
                    nickname = pulse.get_attribute("data-pw-pulse-entry")

                    act(pulse.click)
                    page.wait_for_function(
                        "nickname => JSON.stringify(window.pwFilter.get().brands) === JSON.stringify([nickname])",
                        arg=nickname,
                    )
                    self.assertEqual(page.locator(f'[data-pw-pulse-entry="{nickname}"]').get_attribute("aria-pressed"), "true")
                    checked_brands = page.locator('[data-pw-filter-group="brands"]:checked')
                    self.assertEqual(checked_brands.count(), 1)
                    self.assertEqual(checked_brands.first.get_attribute("value"), nickname)

                    act(lambda: page.locator(f'[data-pw-pulse-entry="{nickname}"]').press("Enter"))
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), "__all__")
                    self.assertEqual(page.locator(f'[data-pw-pulse-entry="{nickname}"]').get_attribute("aria-pressed"), "false")
                    self.assertEqual(
                        page.locator('[data-pw-filter-group="brands"]:checked').count(),
                        page.locator('[data-pw-filter-group="brands"]').count(),
                    )

                    act(lambda: page.locator(f'[data-pw-pulse-entry="{nickname}"]').press("Space"))
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), [nickname])
                    act(lambda: page.locator(f'[data-pw-pulse-entry="{nickname}"]').click())
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), "__all__")

                    feed_response, _ = act(page.locator("[data-pw-window-btn='7']").click)
                    filters, window = request_state(feed_response.url)
                    self.assertEqual(filters["window"], 7)
                    self.assertEqual(window, 7)
                    page.wait_for_function(
                        "() => JSON.parse(document.querySelector('canvas.home-chart').dataset.home).window_days === 7"
                    )
                finally:
                    context.close()
            finally:
                browser.close()

    def test_v24_locale_and_window_controls_keep_geometry_and_copy(self) -> None:
        """V24 control labels change without moving or resizing the controls."""
        cookies_by_locale = {
            locale: self._anonymous_cookies(locale) for locale in LOCALES
        }
        expected_labels = {
            "en": ["1d", "7d", "30d", "365d"],
            "zh_cn": ["1天", "7天", "30天", "365天"],
            "original": ["1d", "7d", "30d", "365d"],
        }
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for viewport_name, viewport in {
                    "desktop": VIEWPORTS["desktop"],
                    "compressed-520": {"width": 520, "height": 844},
                    "mobile-393": {"width": 393, "height": 852},
                    "mobile-320": {"width": 320, "height": 844},
                }.items():
                    baseline = None
                    for locale in LOCALES:
                        with self.subTest(viewport=viewport_name, locale=locale):
                            context = self._context_with_cookies(
                                browser, cookies_by_locale[locale], viewport
                            )
                            page = context.new_page()
                            try:
                                page.goto(
                                    f"{self.live_server_url}/",
                                    wait_until="networkidle",
                                )
                                page.wait_for_function("() => window.__pwTz")
                                geometry = page.evaluate(
                                    """() => {
                                      const rect = (element) => {
                                        const box = element.getBoundingClientRect();
                                        return {x: box.x, y: box.y, top: box.top, left: box.left, width: box.width, height: box.height, right: box.right, bottom: box.bottom};
                                      };
                                      const controls = document.querySelector('.topbar-controls');
                                      const appName = document.querySelector('.app-name');
                                      const zhTitle = appName.querySelector('.zh');
                                      const enTitle = appName.querySelector('.en');
                                      return {
                                        controls: rect(controls),
                                        locale: [...document.querySelectorAll('[data-pw-locale-btn]')].map(rect),
                                        windows: [...document.querySelectorAll('[data-pw-window-btn]')].map(rect),
                                        timezone: rect(document.querySelector('[data-tz-widget]')),
                                        title: {
                                          app: rect(appName),
                                          zh: rect(zhTitle),
                                          en: rect(enTitle),
                                          lines: [...enTitle.querySelectorAll('.en-line')].map((line) => ({...rect(line), text: line.textContent})),
                                        },
                                      };
                                    }"""
                                )
                                locale_widths = [
                                    item["width"] for item in geometry["locale"]
                                ]
                                window_widths = [
                                    item["width"] for item in geometry["windows"]
                                ]
                                self.assertLessEqual(
                                    max(locale_widths) - min(locale_widths), 0.5
                                )
                                self.assertLessEqual(
                                    max(window_widths) - min(window_widths), 0.5
                                )
                                self.assertLessEqual(
                                    geometry["timezone"]["right"],
                                    geometry["controls"]["right"] + 0.5,
                                )
                                self.assertGreaterEqual(
                                    geometry["windows"][0]["left"],
                                    geometry["controls"]["left"] - 0.5,
                                )
                                self.assertLessEqual(
                                    geometry["windows"][-1]["right"],
                                    geometry["timezone"]["left"] + 0.5,
                                )
                                self.assertEqual(
                                    page.locator("[data-pw-window-btn]").all_inner_texts(),
                                    expected_labels[locale],
                                )
                                self.assertEqual(page.locator(".pulse-bar-head").count(), 0)
                                self.assertGreater(
                                    page.locator("[data-pw-pulse-entry]").count(), 0
                                )
                                self.assertEqual(
                                    [line["text"] for line in geometry["title"]["lines"]],
                                    ["Pushin'", "Weight"],
                                )
                                self.assertGreater(
                                    geometry["title"]["lines"][1]["y"],
                                    geometry["title"]["lines"][0]["y"],
                                )
                                self.assertGreaterEqual(
                                    geometry["title"]["en"]["left"],
                                    geometry["title"]["app"]["left"] - 0.5,
                                )
                                self.assertLessEqual(
                                    geometry["title"]["en"]["right"],
                                    geometry["title"]["app"]["right"] + 0.5,
                                )
                                self.assertLessEqual(
                                    geometry["title"]["en"]["height"],
                                    geometry["title"]["zh"]["height"] + 1,
                                )
                                signature = {
                                    "controls": geometry["controls"],
                                    "locale": geometry["locale"],
                                    "windows": geometry["windows"],
                                    "timezone": geometry["timezone"],
                                }
                                if baseline is None:
                                    baseline = signature
                                else:
                                    for group in ("locale", "windows"):
                                        for actual, expected in zip(
                                            signature[group], baseline[group], strict=True
                                        ):
                                            self.assertAlmostEqual(
                                                actual["width"], expected["width"], delta=0.5
                                            )
                                            self.assertAlmostEqual(
                                                actual["height"], expected["height"], delta=0.5
                                            )
                                    for key in ("width", "height"):
                                        self.assertAlmostEqual(
                                            signature["timezone"][key],
                                            baseline["timezone"][key],
                                            delta=0.5,
                                        )
                            finally:
                                context.close()
            finally:
                browser.close()

    def test_home_preferences_survive_locale_navigation_reload_and_new_page(self) -> None:
        """Last-used homepage state is restored before chart/feed refresh."""
        cookies = self._anonymous_cookies("en")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._context_with_cookies(
                    browser,
                    cookies,
                    VIEWPORTS["desktop"],
                )
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.wait_for_function("() => window.pwFilter && window.__pwTz")

                    with page.expect_response(lambda response: "/chart.html?" in response.url):
                        page.locator("[data-pw-window-btn='30']").click()
                    page.evaluate("() => window.pwFilter.set('brands', ['qwen'])")
                    page.locator("[data-tz-widget]").click()
                    page.locator('[data-group="brands"]').click()
                    page.locator('body > .filter-dropdown [data-lens="closed"]').click()

                    with page.expect_navigation(wait_until="networkidle"):
                        page.locator('[data-pw-locale-btn="zh_cn"]').click()
                    page.wait_for_function(
                        "() => window.pwFilter && window.__pwTz && "
                        "JSON.parse(document.querySelector('canvas.home-chart').dataset.home).window_days === 30"
                    )

                    state = page.evaluate(
                        """() => ({
                          filters: window.pwFilter.get(),
                          preferences: window.pwFilter.getPreferences(),
                          timezone: window.__pwTz.mode,
                          locale: document.body.dataset.pwLocale,
                          brandLens: document.querySelector('[data-lens-pair="open,closed"] .dd-lens-body')?.dataset.activeLens,
                          storageKeys: Object.keys(localStorage).filter((key) => key.startsWith('pushinweight.home.preferences.v1:')),
                        })"""
                    )
                    self.assertEqual(state["filters"]["window"], 30)
                    self.assertEqual(state["filters"]["brands"], ["qwen"])
                    self.assertEqual(state["timezone"], "ca")
                    self.assertEqual(state["locale"], "zh_cn")
                    self.assertEqual(state["brandLens"], "closed")
                    self.assertEqual(state["preferences"]["version"], 1)
                    self.assertEqual(len(state["storageKeys"]), 1)

                    runtime_requests: list[str] = []
                    page.on(
                        "request",
                        lambda request: runtime_requests.append(request.url)
                        if "/chart.html?" in request.url or "/feed/?" in request.url
                        else None,
                    )
                    page.reload(wait_until="networkidle")
                    page.wait_for_function(
                        "() => window.pwFilter?.get().window === 30 && window.__pwTz?.mode === 'ca'"
                    )
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), ["qwen"])
                    for endpoint in ("/chart.html?", "/feed/?"):
                        first_request = next(
                            url for url in runtime_requests if endpoint in url
                        )
                        query = parse_qs(urlparse(first_request).query)
                        first_filters = json.loads(query["filters"][0])
                        self.assertEqual(first_filters["window"], 30)
                        self.assertEqual(first_filters["brands"], ["qwen"])
                        self.assertEqual(query["locale"], ["zh_cn"])

                    override = json.dumps({"brands": ["minimax"], "window": 7})
                    page.goto(
                        f"{self.live_server_url}/?{urlencode({'filters': override})}",
                        wait_until="networkidle",
                    )
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), ["minimax"])
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().window"), 7)
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.wait_for_function("() => window.pwFilter?.get().window === 30")
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().brands"), ["qwen"])

                    next_page = context.new_page()
                    try:
                        next_page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                        next_page.wait_for_function(
                            "() => window.pwFilter?.get().window === 30 && window.__pwTz?.mode === 'ca'"
                        )
                        self.assertEqual(
                            next_page.evaluate("() => window.pwFilter.get().brands"),
                            ["qwen"],
                        )
                    finally:
                        next_page.close()

                    # A URL locale is a transient override. Choosing a locale
                    # consumes that override instead of redirecting back into it.
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    self.assertEqual(page.locator('[data-pw-locale-btn].is-active').inner_text(), "en")
                    with page.expect_navigation(wait_until="networkidle"):
                        page.locator('[data-pw-locale-btn="zh_cn"]').click()
                    self.assertNotIn("locale=", page.url)
                    self.assertEqual(page.locator('[data-pw-locale-btn].is-active').inner_text(), "中文")
                finally:
                    context.close()
            finally:
                browser.close()

    def test_locale_only_restore_refetches_data_and_invalid_storage_falls_back(self) -> None:
        cookies = self._anonymous_cookies("en")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._context_with_cookies(
                    browser, cookies, VIEWPORTS["desktop"]
                )
                page = context.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    storage_key = page.evaluate("() => window.pwFilter.storageKey")
                    preferences = page.evaluate("() => window.pwFilter.getPreferences()")
                    preferences["locale"] = "zh_cn"
                    page.evaluate(
                        "([key, value]) => localStorage.setItem(key, JSON.stringify(value))",
                        [storage_key, preferences],
                    )

                    runtime_requests: list[str] = []
                    page.on(
                        "request",
                        lambda request: runtime_requests.append(request.url)
                        if "/chart.html?" in request.url or "/feed/?" in request.url
                        else None,
                    )
                    page.reload(wait_until="networkidle")
                    page.wait_for_function(
                        "() => document.body.dataset.pwLocale === 'zh_cn'"
                    )
                    for endpoint in ("/chart.html?", "/feed/?"):
                        request_url = next(
                            url for url in runtime_requests if endpoint in url
                        )
                        self.assertEqual(
                            parse_qs(urlparse(request_url).query)["locale"],
                            ["zh_cn"],
                        )

                    invalid = {
                        **preferences,
                        "locale": "not-a-locale",
                        "window": 999,
                        "timezone": "mars",
                        "filters": {
                            **preferences["filters"],
                            "brands": ["removed-model"],
                            "window": 999,
                        },
                    }
                    page.evaluate(
                        "([key, value]) => localStorage.setItem(key, JSON.stringify(value))",
                        [storage_key, invalid],
                    )
                    page.reload(wait_until="networkidle")
                    fallback = page.evaluate(
                        "() => ({filters: window.pwFilter.get(), preferences: window.pwFilter.getPreferences(), locale: document.body.dataset.pwLocale, timezone: window.__pwTz.mode})"
                    )
                    self.assertEqual(fallback["filters"]["window"], 1)
                    self.assertIn("qwen", fallback["filters"]["brands"])
                    self.assertEqual(fallback["locale"], "en")
                    self.assertEqual(fallback["timezone"], "local")

                    page.evaluate(
                        "key => localStorage.setItem(key, '{malformed')", storage_key
                    )
                    page.reload(wait_until="networkidle")
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().window"), 1)

                    stale = {**preferences, "version": 0, "window": 365}
                    page.evaluate(
                        "([key, value]) => localStorage.setItem(key, JSON.stringify(value))",
                        [storage_key, stale],
                    )
                    page.reload(wait_until="networkidle")
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().window"), 1)

                    page.add_init_script(
                        "Storage.prototype.getItem = function () { throw new Error('storage unavailable'); }; "
                        "Storage.prototype.setItem = function () { throw new Error('storage unavailable'); };"
                    )
                    page.reload(wait_until="networkidle")
                    self.assertEqual(page.evaluate("() => window.pwFilter.get().window"), 1)
                    self.assertEqual(errors, [])
                finally:
                    context.close()
            finally:
                browser.close()

    def test_v24_pulse_chips_multiselect_the_live_chart_and_feed(self) -> None:
        """Pulse toggles send one shared brand union without replacing renderers."""

        def response_filters(response) -> dict[str, object]:
            query = parse_qs(urlparse(response.url).query)
            return json.loads(query["filters"][0])

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    viewport=VIEWPORTS["desktop"], timezone_id="Asia/Tokyo"
                )
                _freeze_clock(context)
                page = context.new_page()
                try:
                    page.goto(
                        f"{self.live_server_url}/?locale=en",
                        wait_until="networkidle",
                    )
                    page.wait_for_function(
                        "() => window.pwFilter && document.querySelectorAll('[data-pw-pulse-entry]').length >= 2"
                    )
                    nicknames = page.locator(
                        "[data-pw-pulse-entry]"
                    ).evaluate_all(
                        "buttons => buttons.slice(0, 2).map(button => button.dataset.pwPulseEntry)"
                    )
                    self.assertEqual(len(nicknames), 2)

                    def toggle(nickname: str) -> tuple[dict[str, object], dict[str, object]]:
                        with page.expect_response(
                            lambda response: "/feed/?" in response.url
                        ) as feed_info, page.expect_response(
                            lambda response: "/chart.html?" in response.url
                        ) as chart_info:
                            page.locator(
                                f'[data-pw-pulse-entry="{nickname}"]'
                            ).click()
                        self.assertEqual(feed_info.value.status, 200)
                        self.assertEqual(chart_info.value.status, 200)
                        return (
                            response_filters(feed_info.value),
                            response_filters(chart_info.value),
                        )

                    first_feed, first_chart = toggle(nicknames[0])
                    self.assertEqual(first_feed, first_chart)
                    self.assertEqual(first_feed["brands"], [nicknames[0]])

                    second_feed, second_chart = toggle(nicknames[1])
                    self.assertEqual(second_feed, second_chart)
                    self.assertEqual(
                        set(second_feed["brands"]), set(nicknames)
                    )
                    for nickname in nicknames:
                        self.assertEqual(
                            page.locator(
                                f'[data-pw-pulse-entry="{nickname}"]'
                            ).get_attribute("aria-pressed"),
                            "true",
                        )
                    selected_background = page.locator(
                        f'[data-pw-pulse-entry="{nicknames[0]}"]'
                    ).evaluate("element => getComputedStyle(element).backgroundColor")
                    active_window_background = page.locator(
                        "[data-pw-window-btn].is-active"
                    ).evaluate("element => getComputedStyle(element).backgroundColor")
                    self.assertEqual(selected_background, active_window_background)
                    selected_edge = page.locator(
                        f'[data-pw-pulse-entry="{nicknames[1]}"]'
                    ).evaluate(
                        """element => {
                          const probe = document.createElement('span');
                          probe.style.color = getComputedStyle(element).getPropertyValue('--chip-color');
                          document.body.appendChild(probe);
                          const expected = getComputedStyle(probe).color;
                          probe.remove();
                          return {
                            expected,
                            actual: getComputedStyle(element).borderLeftColor,
                          };
                        }"""
                    )
                    self.assertEqual(selected_edge["actual"], selected_edge["expected"])

                    chart_runtime = page.evaluate(
                        """() => {
                          const canvas = document.querySelector('canvas.home-chart');
                          const chart = window.Chart && Chart.getChart(canvas);
                          return {
                            canvasCount: document.querySelectorAll('canvas.home-chart').length,
                            mockupSvgCount: document.querySelectorAll('svg.home-chart').length,
                            liveDatasetCount: chart ? chart.data.datasets.length : 0,
                            payloadSeriesCount: Object.keys(JSON.parse(canvas.dataset.home).series).length,
                            feedRegionCount: document.querySelectorAll('[data-pw-feed]').length,
                          };
                        }"""
                    )
                    self.assertEqual(chart_runtime["canvasCount"], 1)
                    self.assertEqual(chart_runtime["mockupSvgCount"], 0)
                    self.assertGreater(chart_runtime["liveDatasetCount"], 0)
                    self.assertEqual(chart_runtime["payloadSeriesCount"], 2)
                    self.assertEqual(chart_runtime["feedRegionCount"], 1)

                    remaining_feed, remaining_chart = toggle(nicknames[0])
                    self.assertEqual(remaining_feed, remaining_chart)
                    self.assertEqual(remaining_feed["brands"], [nicknames[1]])
                    all_feed, all_chart = toggle(nicknames[1])
                    self.assertEqual(all_feed, all_chart)
                    self.assertEqual(all_feed["brands"], "__all__")
                finally:
                    context.close()
            finally:
                browser.close()

    def test_v24_timezone_pill_keeps_both_clocks_and_geometry(self) -> None:
        """The split pill toggles selection while feed timestamps follow it."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for viewport_name, viewport in {
                    "desktop": VIEWPORTS["desktop"],
                    "mobile-320": {"width": 320, "height": 844},
                }.items():
                    with self.subTest(viewport=viewport_name):
                        context = browser.new_context(
                            viewport=viewport, timezone_id="Asia/Tokyo"
                        )
                        _freeze_clock(context)
                        page = context.new_page()
                        try:
                            page.goto(
                                f"{self.live_server_url}/?locale=en",
                                wait_until="networkidle",
                            )
                            page.wait_for_function("() => window.__pwTz")
                            pill = page.locator("[data-tz-widget]")
                            local_choice = pill.locator(
                                '[data-tz-choice="local"]'
                            )
                            ca_choice = pill.locator('[data-tz-choice="ca"]')
                            self.assertEqual(local_choice.count(), 1)
                            self.assertEqual(ca_choice.count(), 1)
                            self.assertRegex(
                                pill.locator("[data-tz-local-time]").inner_text(),
                                r"^\d{2}:\d{2}$",
                            )
                            self.assertRegex(
                                pill.locator("[data-tz-ca-time]").inner_text(),
                                r"^\d{2}:\d{2}$",
                            )
                            self.assertTrue(local_choice.evaluate("element => element.classList.contains('is-selected')"))
                            self.assertFalse(ca_choice.evaluate("element => element.classList.contains('is-selected')"))
                            initial_pill = pill.bounding_box()
                            initial_controls = page.locator(
                                ".topbar-controls"
                            ).bounding_box()
                            initial_stamp = page.locator(
                                ".feed-row[data-created-at-iso] .ts-abs"
                            ).first.inner_text()

                            pill.click()
                            page.wait_for_function(
                                "() => window.__pwTz?.mode === 'ca'"
                            )
                            self.assertFalse(local_choice.evaluate("element => element.classList.contains('is-selected')"))
                            self.assertTrue(ca_choice.evaluate("element => element.classList.contains('is-selected')"))
                            self.assertEqual(pill.bounding_box(), initial_pill)
                            self.assertEqual(
                                page.locator(".topbar-controls").bounding_box(),
                                initial_controls,
                            )
                            self.assertNotEqual(
                                page.locator(
                                    ".feed-row[data-created-at-iso] .ts-abs"
                                ).first.inner_text(),
                                initial_stamp,
                            )
                            axis_colors = page.evaluate(
                                """() => {
                                  const chart = Chart.getChart(document.querySelector('canvas.home-chart'));
                                  return {
                                    local: chart.scales.x.options.ticks.color,
                                    comparison: chart.scales.xComparison.options.ticks.color,
                                  };
                                }"""
                            )
                            self.assertEqual(
                                axis_colors["local"].replace(" ", ""),
                                "rgba(102,102,102,0.55)",
                            )
                            self.assertEqual(
                                axis_colors["comparison"].replace(" ", ""),
                                "rgba(251,191,36,1)",
                            )
                        finally:
                            context.close()
            finally:
                browser.close()

    def test_california_browser_compares_against_localized_beijing_time(self) -> None:
        """California-local browsers get the Beijing comparison contract."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for locale, expected_local, expected_title in (
                    ("en", "local", "Beijing"),
                    ("zh_hans", "本地", "北京"),
                ):
                    with self.subTest(locale=locale):
                        context = browser.new_context(
                            viewport=VIEWPORTS["desktop"],
                            timezone_id="America/Los_Angeles",
                        )
                        page = context.new_page()
                        try:
                            page.goto(
                                f"{self.live_server_url}/?locale={locale}",
                                wait_until="networkidle",
                            )
                            page.wait_for_function("() => window.__pwTz")
                            pill = page.locator("[data-tz-widget]")
                            icon = pill.locator("[data-tz-comparison-icon]")
                            self.assertEqual(
                                pill.get_attribute("data-tz-comparison"),
                                "beijing",
                            )
                            self.assertTrue(
                                icon.evaluate("element => element.classList.contains('tz-bj-icon')")
                            )
                            self.assertEqual(
                                icon.locator("use").get_attribute("href"),
                                "#icon-beijing",
                            )
                            self.assertEqual(icon.get_attribute("aria-label"), expected_title)
                            chart_state = page.evaluate(
                                """() => {
                                  const canvas = document.querySelector('canvas.home-chart');
                                  const chart = Chart.getChart(canvas);
                                  const payload = JSON.parse(canvas.dataset.home);
                                  const firstHour = new Date(payload.days[0]);
                                  firstHour.setMinutes(0, 0, 0);
                                  firstHour.setHours(firstHour.getHours() + 1);
                                  const formatter = new Intl.DateTimeFormat('en-US', {
                                    timeZone: 'Asia/Shanghai',
                                    hour: 'numeric',
                                    hourCycle: 'h23',
                                  });
                                  const expected = Array.from({length: 24}, (_, index) => {
                                    const instant = new Date(firstHour.getTime() + index * 60 * 60 * 1000);
                                    const hour = Number(formatter.format(instant));
                                    return hour % 2 === 0 ? `${hour}:00` : '';
                                  });
                                  return {
                                    timezone: window.__pwTz.getComparison().timezone,
                                    localTitle: chart.scales.x.options.title.text,
                                    title: chart.scales.xComparison.options.title.text,
                                    labels: chart.scales.xComparison.ticks.map((tick) => String(tick.label)),
                                    expected,
                                  };
                                }"""
                            )
                            self.assertEqual(chart_state["timezone"], "Asia/Shanghai")
                            self.assertEqual(chart_state["localTitle"], expected_local)
                            self.assertEqual(chart_state["title"], expected_title)
                            self.assertEqual(len(chart_state["labels"]), 24)
                            self.assertEqual(chart_state["labels"], chart_state["expected"])
                        finally:
                            context.close()
            finally:
                browser.close()

    def test_internal_window_button_retains_legacy_post_and_reload(self) -> None:
        cookies = self._authenticated_cookies("en")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._context_with_cookies(browser, cookies, VIEWPORTS["desktop"])
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/internal/", wait_until="networkidle")
                    self.assertEqual(page.locator("#control-panel").count(), 1)
                    with page.expect_navigation(wait_until="networkidle"):
                        page.locator("[data-pw-window-btn='7']").click()
                    self.assertEqual(page.locator("body").get_attribute("data-pw-window"), "7")
                    self.assertEqual(page.locator("#control-panel").count(), 1)
                finally:
                    context.close()
            finally:
                browser.close()

    def test_fixture_root_route_matches_mockup_in_browser(self) -> None:
        spec = load_spec()
        artifacts = _artifact_dir()
        reports: list[dict[str, object]] = []
        # Django's synchronous test client cannot run inside Playwright's sync
        # bridge event loop, so mint anonymous locale/CSRF cookies first. The
        # helper proves the session has no authenticated user and /internal/
        # still redirects before this visual flow exercises the public root.
        cookies_by_locale = {locale: self._anonymous_cookies(locale) for locale in LOCALES}

        with serve_mockup_over_http() as mockup_url, sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for viewport_name, viewport in VIEWPORTS.items():
                    for locale in LOCALES:
                        context = self._context_with_cookies(browser, cookies_by_locale[locale], viewport)
                        page = context.new_page()
                        reference = context.new_page()
                        console_errors: list[str] = []
                        page_errors: list[str] = []
                        local_asset_responses: dict[str, int] = {}
                        page.on(
                            "console",
                            lambda message: console_errors.append(message.text)
                            if message.type == "error"
                            else None,
                        )
                        page.on("pageerror", lambda error: page_errors.append(str(error)))
                        page.on(
                            "response",
                            lambda response: local_asset_responses.__setitem__(response.url, response.status)
                            if urlparse(response.url).path.startswith("/static/")
                            else None,
                        )
                        try:
                            page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                            reference.goto(mockup_url, wait_until="networkidle")
                            reference.evaluate(
                                """({locale, chrome}) => {
                                  const dict = chrome[locale];
                                  const useZh = locale === 'zh_cn';
                                  document.body.setAttribute('data-pw-locale', locale);
                                  document.querySelectorAll('[data-i18n]').forEach((element) => {
                                    const value = dict[element.getAttribute('data-i18n')];
                                    if (value != null) element.textContent = value;
                                  });
                                  const localeNav = document.querySelector('.locale-toggle');
                                  if (localeNav) {
                                    localeNav.setAttribute('aria-label', dict.locale_aria);
                                    localeNav.querySelectorAll('[data-pw-locale-btn]').forEach((button) => {
                                      button.textContent = button.getAttribute(useZh ? 'data-label-zh' : 'data-label-en') || button.textContent;
                                    });
                                  }
                                  document.querySelectorAll('.window-toggle:not(.locale-toggle)').forEach((nav) => {
                                    nav.setAttribute('aria-label', dict.window_aria);
                                    nav.querySelectorAll('button').forEach((button) => {
                                      button.textContent = button.getAttribute(useZh ? 'data-label-zh' : 'data-label-en') || button.textContent;
                                    });
                                  });
                                  const timezone = document.querySelector('[data-tz-widget]');
                                  if (timezone) timezone.setAttribute('title', dict.tz_title);
                                }""",
                                {"locale": locale, "chrome": spec.chrome},
                            )
                            page.wait_for_function(
                                """() => window.__pwTz && document.querySelector('[data-tz-time]')?.textContent !== '00:00'"""
                            )

                            dom_counts = _assert_parser_regions(page, spec, locale=locale, viewport=viewport_name)
                            actual_styles = _computed_styles(page)
                            reference_styles = _computed_styles(reference)
                            self.assertEqual(
                                actual_styles["topbar"]["display"], reference_styles["topbar"]["display"],
                                f"v22 computed-style mismatch: region='topbar'; property='display'; locale={locale!r}; viewport={viewport_name!r}; oracle_source={str(spec.source)!r}",
                            )
                            self.assertEqual(
                                actual_styles["timezone"]["display"],
                                "grid",
                                f"V24 split-timezone layout missing: locale={locale!r}; viewport={viewport_name!r}",
                            )

                            actual_geometry = _relative_geometry(page, ".app-shell")
                            reference_geometry = _relative_geometry(reference, ".phone")
                            self.assertFalse(actual_geometry.get("__root_missing__"), "Django app-shell landmark missing")
                            self.assertFalse(reference_geometry.get("__root_missing__"), "Mockup phone landmark missing")
                            # These relationships survive changing fixture copy and catch
                            # shell layout regressions more reliably than absolute pixels.
                            self.assertAlmostEqual(actual_geometry["topbar"]["x"], actual_geometry["filters"]["x"], delta=0.02)
                            self.assertAlmostEqual(actual_geometry["topbar"]["width"], actual_geometry["filters"]["width"], delta=0.02)
                            if viewport_name == "desktop":
                                self.assertLess(actual_geometry["chart"]["x"], actual_geometry["feed"]["x"])
                            else:
                                self.assertLess(actual_geometry["chart"]["y"], actual_geometry["feed"]["y"])

                            tz = page.locator("[data-tz-widget]")
                            feed_stamp = page.locator(".feed-row[data-created-at-iso] .ts-abs").first
                            self.assertEqual(
                                page.locator(".feed-row .enrichment-status").count(),
                                0,
                            )
                            initial_feed_stamp = feed_stamp.text_content()
                            initial_time = tz.locator("[data-tz-time]").text_content()
                            self.assertRegex(initial_time or "", r"^\d{2}:\d{2}$")
                            self.assertNotEqual(initial_time, "00:00", "timezone runtime left its authored placeholder unchanged")
                            tz.click()
                            page.wait_for_function("() => window.__pwTz?.mode === 'ca'")
                            self.assertEqual(tz.get_attribute("data-tz-active"), "ca")
                            self.assertTrue(tz.get_attribute("aria-label"))
                            self.assertEqual(
                                tz.locator("[data-tz-comparison-icon] use").get_attribute("href"),
                                "#icon-california",
                            )
                            self.assertNotEqual(feed_stamp.text_content(), initial_feed_stamp)

                            local_assets = page.evaluate(
                                """() => [...document.querySelectorAll('link[href], script[src]')]
                                  .map((node) => new URL(node.href || node.src, location.href).href)
                                  .filter((url) => new URL(url).origin === location.origin)"""
                            )
                            self.assertGreater(len(local_assets), 0, "anonymous root referenced zero local assets")
                            for asset_url in local_assets:
                                self.assertIn(asset_url, local_asset_responses, f"local asset emitted no response: {asset_url}")
                                self.assertLess(
                                    local_asset_responses[asset_url],
                                    400,
                                    f"local asset failed: url={asset_url}; status={local_asset_responses[asset_url]}",
                                )
                            self.assertEqual(page_errors, [], f"candidate page errors: {page_errors}")
                            self.assertEqual(console_errors, [], f"candidate console errors: {console_errors}")

                            actual_png = page.screenshot()
                            reference_png = reference.screenshot()
                            stem = f"{viewport_name}-{locale}"
                            (artifacts / f"{stem}-django.png").write_bytes(actual_png)
                            (artifacts / f"{stem}-mockup.png").write_bytes(reference_png)
                            pixels = _pixel_report(page, actual_png, reference_png)
                            report = {
                                "locale": locale,
                                "viewport": viewport_name,
                                "django_url": self.live_server_url,
                                "mockup_url": mockup_url,
                                "dom_counts": dom_counts,
                                "computed_styles": {"django": actual_styles, "mockup": reference_styles},
                                "geometry": {"django": actual_geometry, "mockup": reference_geometry},
                                "timezone": {"initial": initial_time, "after_toggle": tz.inner_text()},
                                "screenshot": pixels,
                            }
                            (artifacts / f"{stem}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                            reports.append(report)
                            self.assertLessEqual(
                                float(pixels["changed_fraction"]),
                                MAX_CHANGED_PIXEL_FRACTION,
                                f"v22 screenshot threshold exceeded; report={artifacts / f'{stem}.json'}; "
                                f"changed_fraction={pixels['changed_fraction']}; threshold={MAX_CHANGED_PIXEL_FRACTION}",
                            )
                        finally:
                            context.close()
            finally:
                browser.close()

        summary = artifacts / "summary.json"
        summary.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(len(reports), len(VIEWPORTS) * len(LOCALES), f"missing browser reports; artifacts={artifacts}")


@override_settings(STORAGES=V22_BROWSER_TEST_STORAGES)
class HomeV22MetadataParityBrowserTests(StaticLiveServerTestCase):
    """Anonymous, real-ORM proof for metadata received after feed hydration."""

    def setUp(self) -> None:
        super().setUp()
        self.fixture = seed_v22_metadata_regression_orm()
        _clear_home_pulse_cache()

    def _anonymous_context(self, browser: object) -> BrowserContext:
        context = browser.new_context(viewport=VIEWPORTS["desktop"], timezone_id="Asia/Tokyo")
        _freeze_clock(context)
        return context

    def _feed_payload(self, **query: object) -> dict[str, object]:
        response = Client(HTTP_HOST="localhost").get("/feed/?" + urlencode(query))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _assert_row_contract(self, row: dict[str, object], *, tweet_id: str, tint: str) -> None:
        self.assertEqual(row["tweet_id"], tweet_id)
        self.assertEqual(row["tint_class"], tint)
        for key in (
            "text",
            "text_original",
            "text_translated",
            "text_en",
            "text_zh_cn",
            "commentary_en",
            "commentary_zh_cn",
            "account",
            "engagement_pretty",
            "follower_bin",
            "followers_count",
            "followers_label",
            "meta_text",
            "ts_abs_text",
            "classifications",
            "sentiment_keys",
            "post_type_keys",
            "nat_cn",
            "nat_us",
            "unsanctioned",
        ):
            self.assertIn(key, row)
        self.assertEqual(row["account"]["handle"], "v22metadata000")
        self.assertEqual(row["account"]["display_name"], "V22 Metadata Account 000")
        self.assertEqual(row["account"]["role"], "official")
        self.assertEqual(row["account"]["role_label"], "官方")
        self.assertEqual(row["sentiment_keys"], ["positive", "mixed"])
        self.assertEqual(row["post_type_keys"], ["buzz_releases", "hands_on_usage"])
        self.assertEqual(row["nat_cn"], "pro")
        self.assertEqual(row["nat_us"], "mild_pro")
        self.assertIn("genuine_hype", str(row["classifications"]))
        self.assertTrue(row["engagement_pretty"]["followers"])

    def _assert_visible_metadata(self, page: Page, tweet_id: str, tint: str) -> None:
        row = page.locator(f".feed-row[data-tweet-id='{tweet_id}']")
        self.assertEqual(row.count(), 1, f"missing rendered row {tweet_id}")
        self.assertEqual(row.get_attribute("data-tint"), tint)
        shell = row.locator(".feed-row-shell")
        self.assertTrue(shell.evaluate("element => element.classList.contains('" + tint + "')"))
        lead = row.locator(".follower-lead")
        magnitude = lead.locator(".follower-magnitude")
        glyph = lead.locator(".follower-glyph")
        count = lead.locator(".follower-count")
        self.assertEqual(lead.count(), 1)
        self.assertEqual(glyph.count(), 1)
        self.assertIn("followers", magnitude.get_attribute("aria-label") or "")
        self.assertGreater(glyph.bounding_box()["width"], 0)
        self.assertTrue((count.inner_text() or "").strip())
        account_link = row.locator(".feed-handle-link")
        self.assertTrue(account_link.inner_text().startswith("V22 Metadata Account "))
        self.assertRegex(account_link.get_attribute("href") or "", r"/v22metadata\d{3}$")
        if tweet_id == self.fixture["replacement_id"]:
            role = lead.locator(".account-role.role-official")
            self.assertEqual(role.count(), 1)
            self.assertEqual(role.locator("use").get_attribute("href"), "#icon-role-badge")
            locale = page.locator("body").get_attribute("data-pw-locale") or "en"
            self.assertEqual(
                role.get_attribute("aria-label"),
                "官方" if locale.startswith("zh") else "Official",
            )
        for selector in ("[data-sig-sentiment]", "[data-sig-post-type]", "[data-sig-nat]"):
            marker = row.locator(selector)
            self.assertTrue(marker.is_visible(), f"marker is hidden: {selector}")
            box = marker.bounding_box()
            self.assertIsNotNone(box, f"marker has no geometry: {selector}")
            self.assertGreater(box["width"], 0, f"marker has zero width: {selector}")
            self.assertGreater(box["height"], 0, f"marker has zero height: {selector}")
            self.assertGreater(marker.locator("use").count(), 0, f"marker has no symbol: {selector}")

    def test_cyber_quan_symbols_cover_the_public_surface_without_layout_errors(self) -> None:
        expected_symbols = {
            "mark-quiet",
            "icon-heart", "icon-reply", "icon-repost",
            "icon-rise", "icon-flat", "icon-fall",
            "icon-followers-1", "icon-followers-2", "icon-followers-3", "icon-followers-4",
            "icon-role-badge",
            "icon-sentiment", "icon-sentiment-neutral", "icon-sentiment-negative", "icon-sentiment-mixed",
            "icon-hands-on-hammer", "icon-compare", "icon-announce", "icon-question",
            "icon-marketing", "icon-event", "icon-discourse", "icon-nationalism",
            "icon-unsanctioned", "icon-caret", "icon-star",
            "icon-sunrise", "icon-day", "icon-dusk", "icon-night",
            "icon-california", "icon-beijing",
        }
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for viewport, locale in ((VIEWPORTS["desktop"], "en"), (VIEWPORTS["mobile"], "zh_cn"), ({"width": 320, "height": 700}, "en")):
                    with self.subTest(viewport=viewport, locale=locale):
                        context = browser.new_context(viewport=viewport, timezone_id="Asia/Tokyo")
                        _freeze_clock(context)
                        page_errors: list[str] = []
                        console_errors: list[str] = []
                        page = context.new_page()
                        page.on("pageerror", lambda error: page_errors.append(str(error)))
                        page.on(
                            "console",
                            lambda message: console_errors.append(message.text)
                            if message.type == "error" and "favicon.ico" not in message.text
                            else None,
                        )
                        try:
                            page.goto(f"{self.live_server_url}/?locale={locale}", wait_until="networkidle")
                            page.wait_for_function("() => window.pwIcon && window.__pwTz")

                            self.assertEqual(
                                set(page.locator(".pw-icon-sprite symbol").evaluate_all(
                                    "nodes => nodes.map(node => node.id)"
                                )),
                                expected_symbols,
                            )
                            broken_uses = page.locator("svg.pw-icon use").evaluate_all(
                                """nodes => nodes.map(node => node.getAttribute('href'))
                                  .filter(href => !href || !document.querySelector(href))"""
                            )
                            self.assertEqual(broken_uses, [])
                            self.assertEqual(
                                page.locator(".app-name > .app-mark use").get_attribute("href"),
                                "#mark-quiet",
                            )
                            self.assertEqual(
                                page.locator(".app-name").evaluate(
                                    "node => [...node.children].map(child => child.classList[0])"
                                ),
                                ["pw-icon", "zh", "en"],
                            )
                            self.assertEqual(page.locator(".filter-pill .carat use").count(), 8)
                            self.assertEqual(
                                page.locator(".filter-pill .carat use").evaluate_all(
                                    "nodes => [...new Set(nodes.map(node => node.getAttribute('href')))]"
                                ),
                                ["#icon-caret"],
                            )
                            self.assertEqual(
                                page.locator("[data-tz-comparison-icon] use").get_attribute("href"),
                                "#icon-california",
                            )
                            self.assertGreater(page.locator(".headline-voices use[href='#icon-star']").count(), 0)
                            self.assertGreater(page.locator(".engagement use[href='#icon-heart']").count(), 0)
                            self.assertGreater(page.locator(".engagement use[href='#icon-repost']").count(), 0)
                            self.assertGreater(page.locator(".engagement use[href='#icon-reply']").count(), 0)
                            semantic_slots = page.locator("[data-pw-semantic-icon] svg")
                            self.assertGreater(semantic_slots.count(), 20)
                            self.assertEqual(
                                page.locator(
                                    '[data-pw-semantic-family="sentiment"]'
                                    '[data-pw-semantic-key="negative"] use'
                                ).first.get_attribute("href"),
                                "#icon-sentiment-negative",
                            )
                            self.assertEqual(
                                page.locator(
                                    '[data-pw-semantic-family="role"]'
                                    '[data-pw-semantic-key="staff"] use'
                                ).get_attribute("href"),
                                "#icon-role-badge",
                            )
                            self.assertEqual(
                                page.locator('[data-group="lang"] [data-pw-semantic-icon]').count(),
                                0,
                            )
                            sentiment_pill = page.locator('[data-group="sentiment"]')
                            sentiment_pill.click()
                            visible_sentiment_icons = page.locator(
                                '[data-pw-semantic-family="sentiment"] svg:visible'
                            )
                            self.assertEqual(visible_sentiment_icons.count(), 4)
                            self.assertTrue(visible_sentiment_icons.evaluate_all(
                                "nodes => nodes.every(node => node.getBoundingClientRect().width > 0 && node.getBoundingClientRect().height > 0)"
                            ))
                            page.locator('[data-group="role"]').click()
                            visible_role_icons = page.locator(
                                '[data-pw-semantic-family="role"] svg:visible'
                            )
                            self.assertEqual(visible_role_icons.count(), 3)
                            self.assertTrue(visible_role_icons.evaluate_all(
                                "nodes => nodes.every(node => node.getBoundingClientRect().width > 0 && node.getBoundingClientRect().height > 0)"
                            ))

                            direction_symbols = {"up": "#icon-rise", "down": "#icon-fall", "flat": "#icon-flat"}
                            for direction, symbol in direction_symbols.items():
                                deltas = page.locator(f".pulse-chip .delta.{direction}")
                                if deltas.count():
                                    self.assertEqual(
                                        deltas.locator("use").evaluate_all(
                                            "nodes => [...new Set(nodes.map(node => node.getAttribute('href')))]"
                                        ),
                                        [symbol],
                                    )

                            rows = page.locator(".feed-row[data-pw-feed-row]")
                            self.assertGreater(rows.count(), 3)
                            follower_projection = rows.evaluate_all(
                                """rows => Object.fromEntries(rows.slice(0, 12).map(row => [
                                  [...row.querySelector('.follower-lead').classList]
                                    .find(name => name.startsWith('follower-bin-')),
                                  row.querySelector('.follower-glyph use')?.getAttribute('href')
                                ]))"""
                            )
                            follower_symbols = {
                                "follower-bin-0-1k": "#icon-followers-1",
                                "follower-bin-1k-10k": "#icon-followers-2",
                                "follower-bin-10k-50k": "#icon-followers-3",
                                "follower-bin-50k-plus": "#icon-followers-4",
                            }
                            self.assertGreaterEqual(len(follower_projection), 3)
                            self.assertTrue(all(
                                follower_symbols[follower_bin] == symbol
                                for follower_bin, symbol in follower_projection.items()
                            ))
                            official_roles = page.locator(".account-role.role-official")
                            self.assertGreater(official_roles.count(), 0)
                            self.assertEqual(
                                official_roles.first.locator("use").get_attribute("href"),
                                "#icon-role-badge",
                            )
                            first_head = rows.first.locator(".head")
                            first_link = first_head.locator(".feed-handle-link")
                            self.assertEqual(first_link.get_attribute("title"), first_link.inner_text())
                            self.assertEqual(first_link.evaluate("node => getComputedStyle(node).textOverflow"), "ellipsis")
                            self.assertLessEqual(
                                first_head.evaluate("node => node.scrollHeight"),
                                first_head.evaluate("node => node.clientHeight") + 1,
                            )
                            self.assertFalse(page.evaluate("() => document.documentElement.scrollWidth > innerWidth"))
                            self.assertEqual(page_errors, [])
                            self.assertEqual(console_errors, [])
                        finally:
                            context.close()
            finally:
                browser.close()

    def test_locale_text_cycle_and_row_link_targets_are_independent(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(
                        f"{self.live_server_url}/?locale=zh_hans",
                        wait_until="networkidle",
                    )
                    page.wait_for_function("() => window.pwFilter && window.pwApplyChrome")

                    page.evaluate("window.pwApplyChrome('en')")
                    self.assertEqual(
                        page.locator("[data-pw-locale-btn].is-active").all_inner_texts(),
                        ["en"],
                    )
                    page.evaluate("window.pwApplyChrome('original')")
                    self.assertEqual(
                        page.locator("[data-pw-locale-btn].is-active").all_inner_texts(),
                        ["original"],
                    )
                    page.evaluate("window.pwApplyChrome('zh_cn')")

                    row = page.locator(".feed-row[data-pw-feed-row]").first
                    text = row.locator(".text[data-text-cycle]")
                    self.assertEqual(text.get_attribute("data-layer-key"), "synthesis")
                    self.assertIn("综合", text.inner_text())
                    text.evaluate(
                        """element => {
                          element.setAttribute('data-literal-cn', '直译内容 '.repeat(80));
                          element.setAttribute('data-text-source', 'original source '.repeat(180));
                        }"""
                    )
                    default_height = row.evaluate("element => element.getBoundingClientRect().height")
                    text.click()
                    self.assertEqual(text.get_attribute("data-layer-key"), "literal_cn")
                    self.assertIn("直译", text.inner_text())
                    text.click()
                    self.assertEqual(text.get_attribute("data-layer-key"), "source")
                    self.assertIn("原文", text.inner_text())
                    expanded_height = row.evaluate("element => element.getBoundingClientRect().height")
                    self.assertLessEqual(expanded_height, default_height * 3 + 1)
                    self.assertTrue(text.evaluate("element => element.classList.contains('is-expanded')"))
                    text.click()
                    self.assertEqual(text.get_attribute("data-layer-key"), "synthesis")

                    page.locator(".feed-strip > h3").click()
                    self.assertFalse(text.evaluate("element => element.classList.contains('is-expanded')"))

                    page.evaluate(
                        """() => {
                          window.__pwOpenedUrls = [];
                          window.open = (url) => {
                            window.__pwOpenedUrls.push(url);
                            return { opener: null };
                          };
                        }"""
                    )
                    row.locator(".feed-row-shell").dispatch_event("click")
                    self.assertEqual(
                        page.evaluate("window.__pwOpenedUrls.length"),
                        1,
                    )
                    self.assertRegex(
                        page.evaluate("window.__pwOpenedUrls[0]"),
                        r"^https://x\.com/i/web/status/",
                    )

                    text.dispatch_event("click")
                    row.locator(".feed-handle-link").evaluate(
                        "element => element.addEventListener('click', event => event.preventDefault(), {once: true})"
                    )
                    row.locator(".feed-handle-link").dispatch_event("click")
                    row.locator(".handle").dispatch_event("click")
                    row.locator(".feed-signals").dispatch_event("click")
                    self.assertEqual(page.evaluate("window.__pwOpenedUrls.length"), 1)

                    with page.expect_response(lambda response: "/feed/?" in response.url):
                        page.evaluate("window.pwFilter.set('sentiment', '__all__')")
                    refreshed_text = page.locator(
                        ".feed-row[data-pw-feed-row] .text[data-text-cycle]"
                    ).first
                    self.assertEqual(
                        refreshed_text.get_attribute("data-layer-key"),
                        "synthesis",
                    )
                    refreshed_text.click()
                    self.assertEqual(
                        refreshed_text.get_attribute("data-layer-key"),
                        "literal_cn",
                    )
                finally:
                    context.close()
            finally:
                browser.close()

    def test_canonical_twenty_model_pulse_is_visible_and_accessible(self) -> None:
        """Every canonical enabled model reaches the browser, including zeroes."""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    page.wait_for_function(
                        "nickname => Boolean(document.querySelector(`[data-pw-pulse-entry='${nickname}']`))",
                        arg="upstage",
                    )
                    projection = page.evaluate(
                        """() => {
                          const bar = document.querySelector('[data-pw-pulse]');
                          const rows = [...bar.querySelectorAll(':scope > li')];
                          const entries = [...bar.querySelectorAll('[data-pw-pulse-entry]')];
                          const details = Object.fromEntries(entries.map((button) => {
                            const delta = button.querySelector('.delta');
                            const symbol = delta.querySelector('use')?.getAttribute('href') || '';
                            const rect = button.getBoundingClientRect();
                            return [button.dataset.pwPulseEntry, {
                              text: delta.textContent.trim(),
                              symbol,
                              aria: button.getAttribute('aria-label'),
                              pressed: button.getAttribute('aria-pressed'),
                              width: rect.width,
                              height: rect.height,
                            }];
                          }));
                          return {
                            order: entries.map((button) => button.dataset.pwPulseEntry),
                            details,
                            listItems: rows.length,
                            buttons: bar.querySelectorAll('button').length,
                            window: bar.dataset.pwWindow,
                            computedAt: bar.dataset.pwComputedAt,
                            overflowX: getComputedStyle(bar).overflowX,
                            scrollbarWidth: getComputedStyle(bar).scrollbarWidth,
                            webkitScrollbarDisplay: getComputedStyle(bar, '::-webkit-scrollbar').display,
                            overflows: bar.scrollWidth > bar.clientWidth,
                            reachesLast: (() => {
                              bar.scrollLeft = bar.scrollWidth;
                              const barBox = bar.getBoundingClientRect();
                              const lastBox = entries.at(-1).getBoundingClientRect();
                              return lastBox.right <= barBox.right + 1 && lastBox.left >= barBox.left - 1;
                            })(),
                          };
                        }"""
                    )

                    self.assertEqual(projection["order"], list(MODEL_DISPLAY_NAMES))
                    self.assertEqual(projection["listItems"], 20)
                    self.assertEqual(projection["buttons"], 20)
                    self.assertEqual(projection["window"], "1")
                    self.assertRegex(projection["computedAt"], r"^\d{4}-\d{2}-\d{2}T")
                    self.assertEqual(projection["overflowX"], "auto")
                    self.assertTrue(projection["overflows"])
                    self.assertNotEqual(projection["scrollbarWidth"], "none")
                    self.assertNotEqual(projection["webkitScrollbarDisplay"], "none")
                    self.assertTrue(projection["reachesLast"])
                    zero = projection["details"]["upstage"]
                    self.assertEqual(zero["text"], "0%")
                    self.assertEqual(zero["symbol"], "#icon-flat")
                    self.assertIn("flat 0 percent", zero["aria"])
                    for nickname in MODEL_DISPLAY_NAMES:
                        with self.subTest(nickname=nickname):
                            actual = projection["details"][nickname]
                            self.assertEqual(actual["pressed"], "false")
                            self.assertGreater(actual["width"], 0)
                            self.assertGreater(actual["height"], 0)
                    page.locator('[data-group="brands"]').click()
                    dropdown = page.locator("body > .filter-dropdown.is-portaled")
                    open_models = dropdown.locator(
                        '[data-tier-grid="open"] [data-pw-filter-group="brands"]'
                    ).evaluate_all("inputs => inputs.map(input => input.value)")
                    closed_models = dropdown.locator(
                        '[data-tier-grid="closed"] [data-pw-filter-group="brands"]'
                    ).evaluate_all("inputs => inputs.map(input => input.value)")
                    self.assertEqual(closed_models, ["gemini", "gpt", "claude", "grok"])
                    self.assertTrue(set(open_models).isdisjoint(closed_models))
                finally:
                    context.close()
            finally:
                browser.close()

    def test_mobile_pulse_remains_touch_scrollable_without_desktop_scrollbar(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    viewport={"width": 390, "height": 844},
                    timezone_id="Asia/Tokyo",
                )
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    pulse = page.locator("[data-pw-pulse]")
                    mobile_overflow = pulse.evaluate(
                        """bar => ({
                          overflowX: getComputedStyle(bar).overflowX,
                          scrollbarWidth: getComputedStyle(bar).scrollbarWidth,
                          webkitScrollbarDisplay: getComputedStyle(bar, '::-webkit-scrollbar').display,
                          overflows: bar.scrollWidth > bar.clientWidth,
                        })"""
                    )
                    self.assertEqual(mobile_overflow["overflowX"], "auto")
                    self.assertTrue(mobile_overflow["overflows"])
                    self.assertEqual(mobile_overflow["scrollbarWidth"], "none")
                    self.assertEqual(mobile_overflow["webkitScrollbarDisplay"], "none")
                finally:
                    context.close()
            finally:
                browser.close()

    def test_anonymous_feed_fixture_has_a_page_two_target(self) -> None:
        anonymous = Client(HTTP_HOST="localhost")
        root = anonymous.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertIn(self.fixture["replacement_id"].encode(), root.content)

        payload = self._feed_payload(limit=50)
        self.assertEqual(len(payload["rows"]), 50)
        self.assertTrue(payload["next_cursor"])
        first = payload["rows"][0]
        self._assert_row_contract(
            first,
            tweet_id=self.fixture["replacement_id"],
            tint="tint-pos-mixed",
        )

        second_page = self._feed_payload(limit=50, cursor=payload["next_cursor"])
        self.assertEqual([row["tweet_id"] for row in second_page["rows"]], [self.fixture["page_two_id"]])
        self.assertEqual(second_page["rows"][0]["tint_class"], "tint-neg-mixed")

        all_rows = self._feed_payload(limit=50, filters=json.dumps({"unsanctioned": "any"}))
        flagged = next(row for row in all_rows["rows"] if row["unsanctioned"])
        self.assertIn("unsanctioned", flagged)
        self.assertTrue(flagged["unsanctioned"])

    def test_follower_lead_keeps_feed_bodies_aligned_across_all_bins(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    geometry = page.locator(".feed-row[data-pw-feed-row]").evaluate_all(
                        """rows => rows.slice(0, 12).map((row) => {
                          const lead = row.querySelector('.follower-lead');
                          const glyph = row.querySelector('.follower-glyph .follower-icon');
                          const body = row.querySelector('.feed-main > .body');
                          return {
                            bin: [...lead.classList].find(name => name.startsWith('follower-bin-')),
                            leadWidth: lead.getBoundingClientRect().width,
                            bodyLeft: body.getBoundingClientRect().left,
                            glyphSize: glyph.getBoundingClientRect().width,
                            glyphSymbol: glyph.querySelector('use')?.getAttribute('href'),
                            count: row.querySelector('.follower-count').textContent.trim(),
                          };
                        })"""
                    )
                    self.assertGreaterEqual(len(geometry), 4)
                    self.assertEqual(len({row["leadWidth"] for row in geometry}), 1)
                    self.assertEqual(len({row["bodyLeft"] for row in geometry}), 1)
                    expected = {
                        "follower-bin-0-1k": (12, "#icon-followers-1"),
                        "follower-bin-1k-10k": (15, "#icon-followers-2"),
                        "follower-bin-10k-50k": (19, "#icon-followers-3"),
                        "follower-bin-50k-plus": (22, "#icon-followers-4"),
                    }
                    self.assertGreaterEqual(len({row["bin"] for row in geometry}), 3)
                    self.assertTrue(all(
                        (row["glyphSize"], row["glyphSymbol"]) == expected[row["bin"]]
                        for row in geometry
                    ))
                    self.assertTrue(all(row["count"] for row in geometry))
                finally:
                    context.close()
            finally:
                browser.close()

    def test_brand_scope_changes_display_tint_without_losing_classifications(self) -> None:
        target = self.fixture["brand_scope_id"]

        def matching_row(payload: dict[str, object]) -> dict[str, object] | None:
            return next(
                (row for row in payload["rows"] if row["tweet_id"] == target),
                None,
            )

        all_row = matching_row(self._feed_payload(limit=50))
        self.assertIsNotNone(all_row)
        self.assertEqual(all_row["sentiment_keys"], ["positive", "negative"])
        self.assertEqual(all_row["tint_class"], "tint-pos-neg")
        complete_classifications = all_row["classifications"]

        minimax_row = matching_row(
            self._feed_payload(limit=50, filters=json.dumps({"brands": ["minimax"]}))
        )
        self.assertIsNotNone(minimax_row)
        self.assertEqual(minimax_row["sentiment_keys"], ["positive"])
        self.assertEqual(minimax_row["tint_class"], "tint-positive")
        self.assertEqual(minimax_row["classifications"], complete_classifications)

        kimi_row = matching_row(
            self._feed_payload(limit=50, filters=json.dumps({"brands": ["moonshot_kimi"]}))
        )
        self.assertIsNotNone(kimi_row)
        self.assertEqual(kimi_row["sentiment_keys"], ["negative"])
        self.assertEqual(kimi_row["tint_class"], "tint-negative")
        self.assertEqual(kimi_row["classifications"], complete_classifications)

        reset_row = matching_row(
            self._feed_payload(limit=50, filters=json.dumps({"brands": "__all__"}))
        )
        self.assertEqual(reset_row["sentiment_keys"], ["positive", "negative"])
        self.assertEqual(reset_row["tint_class"], "tint-pos-neg")
        self.assertEqual(reset_row["classifications"], complete_classifications)

        excluded = matching_row(
            self._feed_payload(limit=50, filters=json.dumps({"brands": ["qwen"]}))
        )
        self.assertIsNone(excluded, "a non-associated brand must exclude the row")

    def test_feed_metadata_projection_has_a_bounded_query_count(self) -> None:
        with CaptureQueriesContext(connection) as full_queries:
            full_payload = self._feed_payload(
                limit=50,
                filters=json.dumps({"unsanctioned": "any"}),
            )
        self.assertEqual(len(full_payload["rows"]), 50)

        Post.objects.exclude(tweet_id=self.fixture["brand_scope_id"]).delete()
        with CaptureQueriesContext(connection) as single_queries:
            single_payload = self._feed_payload(
                limit=50,
                filters=json.dumps({"unsanctioned": "any"}),
            )
        self.assertEqual(len(single_payload["rows"]), 1)
        self.assertEqual(
            len(full_queries),
            len(single_queries),
            "metadata query shape must stay constant from one to 52 enriched rows",
        )
        self.assertLessEqual(
            len(full_queries),
            30,
            "52 enriched rows must use bounded bulk metadata queries, not per-row lookups",
        )

    def test_feed_eligibility_query_keeps_request_latency_and_roundtrips_bounded(
        self,
    ) -> None:
        from contextlib import nullcontext
        from statistics import median
        from time import monotonic

        from django.db.models import Prefetch
        from django.utils import timezone

        from core.models import PostBrand
        from monitor.views import _get_feed_posts

        Post.objects.filter(tweet_id__startswith="v22-pulse-").delete()

        def baseline_get_feed_posts(
            window_days: int | None = None,
            brand_nickname: str | None = None,
            limit: int = 50,
        ):
            cutoff = (
                timezone.now() - timedelta(days=window_days)
                if window_days
                else None
            )
            queryset = Post.objects.select_related("author").prefetch_related(
                Prefetch(
                    "brands",
                    queryset=PostBrand.objects.select_related("brand"),
                )
            )
            if cutoff:
                queryset = queryset.filter(created_at__gte=cutoff)
            if brand_nickname:
                queryset = queryset.filter(
                    brands__brand__nickname=brand_nickname
                ).distinct()
            return queryset.order_by("-created_at")[:limit]

        client = Client(HTTP_HOST="localhost")

        def request_sample(*, baseline: bool) -> tuple[float, int]:
            patch_context = (
                patch(
                    "monitor.views._get_feed_posts",
                    side_effect=baseline_get_feed_posts,
                )
                if baseline
                else nullcontext()
            )
            with patch_context:
                started = monotonic()
                with CaptureQueriesContext(connection) as queries:
                    response = client.get("/feed/?limit=50")
                elapsed = monotonic() - started
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["rows"]), 50)
            return elapsed, len(queries)

        request_sample(baseline=True)
        request_sample(baseline=False)
        baseline_samples = [request_sample(baseline=True) for _ in range(5)]
        candidate_samples = [request_sample(baseline=False) for _ in range(5)]
        baseline_times = [elapsed for elapsed, _ in baseline_samples]
        candidate_times = [elapsed for elapsed, _ in candidate_samples]
        baseline_roundtrips = [count for _, count in baseline_samples]
        candidate_roundtrips = [count for _, count in candidate_samples]
        baseline_median = median(baseline_times)
        candidate_median = median(candidate_times)
        allowed_median = baseline_median + max(baseline_median * 0.25, 0.05)
        baseline_plan = baseline_get_feed_posts(limit=500).explain()
        candidate_plan = _get_feed_posts(limit=500).explain()

        print(
            "FEED_ELIGIBILITY_BENCHMARK "
            + json.dumps(
                {
                    "baseline_seconds": baseline_times,
                    "candidate_seconds": candidate_times,
                    "baseline_median_seconds": baseline_median,
                    "candidate_median_seconds": candidate_median,
                    "allowed_median_seconds": allowed_median,
                    "baseline_roundtrips": baseline_roundtrips,
                    "candidate_roundtrips": candidate_roundtrips,
                    "baseline_plan": baseline_plan,
                    "candidate_plan": candidate_plan,
                },
                sort_keys=True,
            )
        )
        self.assertTrue(baseline_plan.strip())
        self.assertTrue(candidate_plan.strip())
        self.assertEqual(candidate_roundtrips, baseline_roundtrips)
        self.assertLessEqual(candidate_median, allowed_median)
        self.assertTrue(all(elapsed < 2 for elapsed in candidate_times))

    def test_anonymous_browser_refetch_and_page_two_append_paint_metadata(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.wait_for_function("() => window.pwFilter && document.querySelector('[data-pw-feed-body]')")
                    self._assert_visible_metadata(page, self.fixture["replacement_id"], "tint-pos-mixed")

                    with page.expect_response(lambda response: "/feed/?" in response.url and response.status == 200):
                        page.evaluate("() => document.dispatchEvent(new CustomEvent('pw:locale-change'))")
                    page.locator(f".feed-row[data-tweet-id='{self.fixture['replacement_id']}']").wait_for()
                    self._assert_visible_metadata(page, self.fixture["replacement_id"], "tint-pos-mixed")

                    sentinel = page.locator("[data-pw-feed-sentinel]")
                    with page.expect_response(lambda response: "/feed/?" in response.url and response.status == 200):
                        sentinel.scroll_into_view_if_needed()
                    page.locator(f".feed-row[data-tweet-id='{self.fixture['page_two_id']}']").wait_for()
                    self._assert_visible_metadata(page, self.fixture["page_two_id"], "tint-neg-mixed")
                finally:
                    context.close()
            finally:
                browser.close()

    def test_browser_keeps_server_tint_when_response_marker_data_conflicts(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    intercepted = {"done": False}

                    def retain_server_tint(route) -> None:
                        response = route.fetch()
                        payload = response.json()
                        if not intercepted["done"] and payload.get("rows"):
                            payload["rows"][0]["sentiment_keys"] = ["negative"]
                            payload["rows"][0]["tint_class"] = "tint-pos-mixed"
                            intercepted["done"] = True
                        route.fulfill(response=response, json=payload)

                    page.route("**/feed/**", retain_server_tint)
                    with page.expect_response(lambda response: "/feed/?" in response.url and response.status == 200):
                        page.evaluate("() => document.dispatchEvent(new CustomEvent('pw:locale-change'))")
                    row = page.locator(f".feed-row[data-tweet-id='{self.fixture['replacement_id']}']")
                    row.wait_for()
                    self.assertEqual(row.get_attribute("data-sentiments"), "negative")
                    self.assertTrue(row.locator(".feed-row-shell").evaluate("element => element.classList.contains('tint-pos-mixed')"))
                    self.assertEqual(
                        row.locator("[data-sig-sentiment] use").get_attribute("href"),
                        "#icon-sentiment-negative",
                    )
                    self.assertTrue(intercepted["done"])
                finally:
                    context.close()
            finally:
                browser.close()

    def test_browser_brand_scope_transitions_gradient_to_solids_and_back(self) -> None:
        target = self.fixture["brand_scope_id"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    target_row = page.locator(f".feed-row[data-tweet-id='{target}']")
                    target_row.wait_for()
                    self.assertTrue(
                        target_row.locator(".feed-row-shell").evaluate(
                            "element => element.classList.contains('tint-pos-neg')"
                        )
                    )

                    complete_classifications = None
                    for brands, expected_tint, expected_sentiments in (
                        (["minimax"], "tint-positive", "positive"),
                        (["moonshot_kimi"], "tint-negative", "negative"),
                        ("__all__", "tint-pos-neg", "positive,negative"),
                    ):
                        with page.expect_response(
                            lambda response: "/feed/?" in response.url and response.status == 200
                        ) as response_info:
                            page.evaluate("brands => window.pwFilter.set('brands', brands)", brands)
                        payload = response_info.value.json()
                        payload_row = next(row for row in payload["rows"] if row["tweet_id"] == target)
                        if complete_classifications is None:
                            complete_classifications = payload_row["classifications"]
                        self.assertEqual(payload_row["classifications"], complete_classifications)
                        target_row = page.locator(f".feed-row[data-tweet-id='{target}']")
                        target_row.wait_for()
                        self.assertEqual(target_row.get_attribute("data-sentiments"), expected_sentiments)
                        self.assertEqual(target_row.get_attribute("data-tint"), expected_tint)
                        self.assertTrue(
                            target_row.locator(".feed-row-shell").evaluate(
                                "(element, tint) => element.classList.contains(tint)",
                                expected_tint,
                            )
                        )
                finally:
                    context.close()
            finally:
                browser.close()

    def test_valid_empty_renders_localized_state_and_then_recovers(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    with page.expect_response(
                        lambda response: "/feed/?" in response.url and response.status == 200
                    ) as empty_response:
                        page.evaluate("() => window.pwFilter.set('brands', ['qwen'])")
                    self.assertEqual(empty_response.value.json()["rows"], [])
                    page.locator("[data-pw-feed-body] .muted-cell").wait_for()
                    self.assertEqual(
                        page.locator("[data-pw-feed-body] .muted-cell").inner_text(),
                        "no posts in window",
                    )
                    self.assertEqual(page.locator(".feed-row[data-pw-feed-row]").count(), 0)

                    with page.expect_response(
                        lambda response: "/feed/?" in response.url and response.status == 200
                    ):
                        page.evaluate("() => window.pwFilter.set('brands', ['moonshot_kimi'])")
                    page.locator(
                        f".feed-row[data-tweet-id='{self.fixture['replacement_id']}']"
                    ).wait_for()
                finally:
                    context.close()
            finally:
                browser.close()

    def test_stale_page_two_cannot_append_after_new_filter_replacement(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                    page.evaluate(
                        """
                        () => {
                          const realFetch = window.fetch.bind(window);
                          const row = (id, tint, sentiment) => ({
                            tweet_id: id,
                            created_at: '2026-08-11T01:00:00+00:00',
                            created_at_iso: '2026-08-11T01:00:00+00:00',
                            text: id,
                            text_original: id,
                            text_translated: id,
                            text_en: id,
                            account: {handle: '@u4race'},
                            classifications: {},
                            sentiment_keys: [sentiment],
                            post_type_keys: [],
                            nat_cn: '',
                            nat_us: '',
                            tint_class: tint,
                          });
                          const response = (payload, status = 200) => Promise.resolve(new Response(
                            JSON.stringify(payload),
                            {status, headers: {'Content-Type': 'application/json'}}
                          ));
                          window.__u4OldStarted = false;
                          window.fetch = (input, options) => {
                            const url = new URL(String(input), window.location.origin);
                            if (url.pathname !== '/feed/') return realFetch(input, options);
                            const filters = JSON.parse(url.searchParams.get('filters') || '{}');
                            const brand = Array.isArray(filters.brands) ? filters.brands[0] : '';
                            if (url.searchParams.get('cursor') && !window.__u4OldStarted) {
                              window.__u4OldStarted = true;
                              return new Promise((resolve) => {
                                window.__u4ResolveOld = () => resolve(new Response(JSON.stringify({
                                  rows: [row('race-old-page', 'tint-negative', 'negative')],
                                  next_cursor: 'old-cursor',
                                  has_more: true,
                                }), {status: 200, headers: {'Content-Type': 'application/json'}}));
                              });
                            }
                            if (brand === 'qwen') return response({
                              rows: [row('race-new-filter', 'tint-positive', 'positive')],
                              next_cursor: null,
                              has_more: false,
                            });
                            if (brand === 'deepseek') return response({
                              rows: [row('race-retry', 'tint-mixed', 'mixed')],
                              next_cursor: null,
                              has_more: false,
                            });
                            return realFetch(input, options);
                          };
                        }
                        """
                    )
                    page.locator("[data-pw-feed-sentinel]").scroll_into_view_if_needed()
                    page.wait_for_function("() => window.__u4OldStarted")
                    page.evaluate(
                        """
                        () => document.dispatchEvent(new CustomEvent('pw:filter-change', {
                          detail: {filters: {...window.pwFilter.get(), brands: ['qwen']}}
                        }))
                        """
                    )
                    page.locator(".feed-row[data-tweet-id='race-new-filter']").wait_for()
                    page.evaluate("() => window.__u4ResolveOld()")
                    page.wait_for_timeout(100)
                    self.assertEqual(page.locator(".feed-row[data-tweet-id='race-old-page']").count(), 0)
                    self.assertEqual(page.locator(".feed-row[data-tweet-id='race-new-filter']").count(), 1)

                    page.evaluate(
                        """
                        () => document.dispatchEvent(new CustomEvent('pw:filter-change', {
                          detail: {filters: {...window.pwFilter.get(), brands: ['deepseek']}}
                        }))
                        """
                    )
                    page.locator(".feed-row[data-tweet-id='race-retry']").wait_for()
                finally:
                    context.close()
            finally:
                browser.close()

    def test_failed_and_malformed_replacements_preserve_rows_and_retry(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    current_id = self.fixture["replacement_id"]
                    page.locator(f".feed-row[data-tweet-id='{current_id}']").wait_for()
                    page.evaluate(
                        """
                        () => {
                          const realFetch = window.fetch.bind(window);
                          const row = (id) => ({
                            tweet_id: id,
                            created_at: '2026-08-11T01:00:00+00:00',
                            created_at_iso: '2026-08-11T01:00:00+00:00',
                            text: id,
                            text_original: id,
                            text_translated: id,
                            text_en: id,
                            account: {handle: '@u4retry'},
                            classifications: {},
                            sentiment_keys: ['positive'],
                            post_type_keys: [],
                            nat_cn: '',
                            nat_us: '',
                            tint_class: 'tint-positive',
                          });
                          window.__u4FailureMode = null;
                          window.__u4RecoveryId = 'recovered';
                          window.fetch = (input, options) => {
                            const url = new URL(String(input), window.location.origin);
                            if (url.pathname !== '/feed/') return realFetch(input, options);
                            if (window.__u4FailureMode === 'http') {
                              return Promise.resolve(new Response('server failed', {status: 500}));
                            }
                            if (window.__u4FailureMode === 'malformed') {
                              return Promise.resolve(new Response(JSON.stringify({rows: null}), {
                                status: 200,
                                headers: {'Content-Type': 'application/json'},
                              }));
                            }
                            if (window.__u4FailureMode === 'network') {
                              return Promise.reject(new TypeError('offline'));
                            }
                            return Promise.resolve(new Response(JSON.stringify({
                              rows: [row(window.__u4RecoveryId)],
                              next_cursor: null,
                              has_more: false,
                            }), {status: 200, headers: {'Content-Type': 'application/json'}}));
                          };
                        }
                        """
                    )

                    for mode in ("http", "malformed", "network"):
                        page.evaluate("mode => { window.__u4FailureMode = mode; }", mode)
                        page.evaluate(
                            """
                            mode => document.dispatchEvent(new CustomEvent('pw:filter-change', {
                              detail: {filters: {...window.pwFilter.get(), brands: [mode]}}
                            }))
                            """,
                            mode,
                        )
                        page.wait_for_function(
                            """
                            () => {
                              const status = document.querySelector('[data-pw-feed-status]');
                              return status && !status.hidden && /refresh failed/i.test(status.textContent || '');
                            }
                            """
                        )
                        self.assertEqual(page.locator(f".feed-row[data-tweet-id='{current_id}']").count(), 1)

                        recovered_id = f"recovered-{mode}"
                        page.evaluate(
                            "([id]) => { window.__u4FailureMode = null; window.__u4RecoveryId = id; }",
                            [recovered_id],
                        )
                        page.evaluate(
                            """
                            () => document.dispatchEvent(new CustomEvent('pw:filter-change', {
                              detail: {filters: {...window.pwFilter.get(), brands: ['minimax']}}
                            }))
                            """
                        )
                        page.locator(f".feed-row[data-tweet-id='{recovered_id}']").wait_for()
                        self.assertTrue(page.locator("[data-pw-feed-status]").is_hidden())
                        current_id = recovered_id
                finally:
                    context.close()
            finally:
                browser.close()

    def test_terminal_completion_reveals_the_exact_hidden_row_on_first_page_refresh(self) -> None:
        from core.models import PostEnrichmentState

        ordered_posts = list(Post.objects.order_by("-created_at")[:3])
        pending_post = ordered_posts[0]
        failed_post = ordered_posts[1]
        expected_fill = ordered_posts[2]
        PostEnrichmentState.objects.create(post=pending_post)
        PostEnrichmentState.objects.create(
            post=failed_post,
            translation_status=PostEnrichmentState.Status.FAILED,
            classification_status=PostEnrichmentState.Status.SUCCEEDED,
        )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                context.add_init_script(
                    """
                    (() => {
                      const realSetInterval = window.setInterval.bind(window);
                      const realClearInterval = window.clearInterval.bind(window);
                      window.__feedEligibilityMinuteCallbacks = [];
                      window.__feedEligibilityIntervalDelays = [];
                      window.setInterval = (fn, delay, ...args) => {
                        window.__feedEligibilityIntervalDelays.push(delay);
                        if (delay === 60000) {
                          window.__feedEligibilityMinuteCallbacks.push(fn);
                          return -window.__feedEligibilityMinuteCallbacks.length;
                        }
                        return realSetInterval(fn, delay, ...args);
                      };
                      window.clearInterval = (id) => id < 0 ? undefined : realClearInterval(id);
                    })();
                    """
                )
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    self.assertEqual(
                        page.locator(
                            f".feed-row[data-tweet-id='{pending_post.tweet_id}']"
                        ).count(),
                        0,
                    )
                    self.assertEqual(
                        page.locator(
                            f".feed-row[data-tweet-id='{failed_post.tweet_id}']"
                        ).count(),
                        0,
                    )
                    self.assertEqual(
                        page.locator(
                            f".feed-row[data-tweet-id='{expected_fill.tweet_id}']"
                        ).count(),
                        1,
                    )
                    first_page = page.evaluate(
                        """async () => {
                          const response = await fetch('/feed/?limit=1');
                          if (!response.ok) throw new Error(`feed status ${response.status}`);
                          return response.json();
                        }"""
                    )
                    self.assertEqual(
                        [row["tweet_id"] for row in first_page["rows"]],
                        [expected_fill.tweet_id],
                    )
                    callback_names = page.evaluate(
                        "() => window.__feedEligibilityMinuteCallbacks.map(fn => fn.name)"
                    )
                    self.assertIn("refreshFirstPage", callback_names)
                    self.assertIn(
                        60000,
                        page.evaluate(
                            "() => window.__feedEligibilityIntervalDelays"
                        ),
                    )

                    update_results: list[int] = []

                    def mark_terminal_complete() -> None:
                        from django.db import close_old_connections

                        close_old_connections()
                        try:
                            update_results.append(
                                PostEnrichmentState.objects.filter(
                                    post_id=pending_post.tweet_id
                                ).update(
                                    translation_status=PostEnrichmentState.Status.SUCCEEDED,
                                    classification_status=PostEnrichmentState.Status.SUCCEEDED,
                                )
                            )
                        finally:
                            close_old_connections()

                    update_thread = threading.Thread(target=mark_terminal_complete)
                    update_thread.start()
                    update_thread.join(timeout=5)
                    self.assertFalse(update_thread.is_alive())
                    self.assertEqual(update_results, [1])

                    with page.expect_response(
                        lambda response: "/feed/?" in response.url
                        and response.status == 200
                    ):
                        page.evaluate(
                            """async () => {
                              const refresh = window.__feedEligibilityMinuteCallbacks.find(
                                fn => fn.name === 'refreshFirstPage'
                              );
                              await refresh();
                            }"""
                        )
                    revealed = page.locator(
                        f".feed-row[data-tweet-id='{pending_post.tweet_id}']"
                    )
                    revealed.wait_for()
                    self.assertTrue(revealed.is_visible())
                    box = revealed.bounding_box()
                    self.assertIsNotNone(box)
                    self.assertGreater(box["width"], 0)
                    self.assertGreater(box["height"], 0)
                    self.assertEqual(
                        revealed.get_attribute("data-enrichment-status"), "succeeded"
                    )
                    self.assertEqual(revealed.locator(".enrichment-status").count(), 0)
                    self.assertEqual(
                        page.locator(
                            f".feed-row[data-tweet-id='{failed_post.tweet_id}']"
                        ).count(),
                        0,
                    )
                finally:
                    context.close()
            finally:
                browser.close()

    def test_periodic_refresh_uses_the_shared_metadata_hydrator(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = self._anonymous_context(browser)
                context.add_init_script(
                    """
                    (() => {
                      const realSetInterval = window.setInterval.bind(window);
                      const realClearInterval = window.clearInterval.bind(window);
                      window.__u4MinuteCallbacks = [];
                      window.setInterval = (fn, delay, ...args) => {
                        if (delay === 60000) {
                          window.__u4MinuteCallbacks.push(fn);
                          return -window.__u4MinuteCallbacks.length;
                        }
                        return realSetInterval(fn, delay, ...args);
                      };
                      window.clearInterval = (id) => id < 0 ? undefined : realClearInterval(id);
                    })();
                    """
                )
                page = context.new_page()
                try:
                    page.goto(f"{self.live_server_url}/?locale=en", wait_until="networkidle")
                    callback_names = page.evaluate("() => window.__u4MinuteCallbacks.map(fn => fn.name)")
                    self.assertIn(
                        "refreshFirstPage",
                        callback_names,
                        "the feed interval must schedule its named shared refresh path",
                    )
                    page.evaluate(
                        """
                        () => {
                          const realFetch = window.fetch.bind(window);
                          window.fetch = (input, options) => {
                            const url = new URL(String(input), window.location.origin);
                            if (url.pathname !== '/feed/') return realFetch(input, options);
                            return Promise.resolve(new Response(JSON.stringify({
                              rows: [{
                                tweet_id: 'periodic-refresh-row',
                                created_at: '2026-08-11T01:00:00+00:00',
                                created_at_iso: '2026-08-11T01:00:00+00:00',
                                text: 'periodic refresh',
                                text_original: 'periodic refresh',
                                text_translated: 'periodic refresh',
                                text_en: 'periodic refresh',
                                account: {handle: '@u4refresh'},
                                classifications: {},
                                sentiment_keys: ['negative', 'mixed'],
                                post_type_keys: ['hands_on_usage'],
                                nat_cn: 'pro',
                                nat_us: 'mild_pro',
                                tint_class: 'tint-neg-mixed',
                              }],
                              next_cursor: null,
                              has_more: false,
                            }), {status: 200, headers: {'Content-Type': 'application/json'}}));
                          };
                          window.__u4MinuteCallbacks.find(fn => fn.name === 'refreshFirstPage')();
                        }
                        """
                    )
                    refreshed = page.locator(".feed-row[data-tweet-id='periodic-refresh-row']")
                    refreshed.wait_for()
                    self.assertEqual(refreshed.get_attribute("data-tint"), "tint-neg-mixed")
                    self.assertEqual(
                        refreshed.locator("[data-sig-sentiment] use").evaluate_all(
                            "nodes => nodes.map(node => node.getAttribute('href'))"
                        ),
                        ["#icon-sentiment-negative", "#icon-sentiment-mixed"],
                    )
                    self.assertEqual(
                        refreshed.locator("[data-sig-post-type] use").get_attribute("href"),
                        "#icon-hands-on-hammer",
                    )
                    self.assertTrue((refreshed.locator("[data-sig-nat]").text_content() or "").strip())
                finally:
                    context.close()
            finally:
                browser.close()
