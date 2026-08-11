"""Real-ORM, root-route fidelity characterization against the v22 mockup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.test import Client

from tests.mockup_spec import load_spec
from tests.shell_diff import (
    assert_data_shape,
    first_authored_difference,
    validate_allowlist,
)
from tests.v22_support import (
    PostgreSQLV22TestCase,
    fixture_from_oracle,
    seed_real_home_orm,
)

pytestmark = pytest.mark.requires_postgres

ALLOWLIST = Path(__file__).with_name("golden") / "v22_shell_allowlist.json"
VIEWPORT = "desktop"


class HomeV22MockupDiffTests(PostgreSQLV22TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.fixture = fixture_from_oracle()
        seed_real_home_orm(cls.fixture)

    def _render(self, locale: str) -> str:
        # Exercise the production locale route/cookie contract.  A query
        # parameter only characterizes a request override and can leave the
        # browser's persisted locale behavior untested.
        response = self.client.post(f"/locale/{locale}/", HTTP_REFERER="/")
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200, response.content[:500].decode("utf-8", errors="replace"))
        return response.content.decode("utf-8")

    def test_allowlist_requires_narrow_reviewed_entries(self):
        assert validate_allowlist(json.loads(ALLOWLIST.read_text(encoding="utf-8"))) == []
        with self.assertRaisesRegex(AssertionError, "selector, region, and rationale"):
            validate_allowlist({"entries": [{"selector": ".x"}]})
        with self.assertRaisesRegex(AssertionError, "broad wildcard"):
            validate_allowlist({"entries": [{"selector": "*", "region": "topbar", "rationale": "no"}]})

    def test_root_route_matches_authored_shell_or_reports_first_difference(self):
        spec = load_spec()
        allowlist = validate_allowlist(json.loads(ALLOWLIST.read_text(encoding="utf-8")))
        for locale in ("zh_cn", "en", "original"):
            with self.subTest(locale=locale):
                rendered = self._render(locale)
                assert_data_shape(spec, self.fixture, rendered, locale=locale, viewport=VIEWPORT)
                difference = first_authored_difference(spec, rendered, locale=locale, viewport=VIEWPORT, allowlist=allowlist)
                self.assertIsNone(difference, difference.report(locale=locale, viewport=VIEWPORT, oracle_source=str(spec.source)) if difference else "")

    def test_chart_runtime_projections_do_not_hide_unknown_shell_children(self):
        """Only the live chart, its legend, and status may differ from the mockup."""
        spec = load_spec()
        rendered = self._render("en")

        known_projection = first_authored_difference(
            spec,
            rendered,
            locale="en",
            viewport=VIEWPORT,
            allowlist=[],
        )
        self.assertIsNone(
            known_projection,
            known_projection.report(
                locale="en",
                viewport=VIEWPORT,
                oracle_source=str(spec.source),
            ) if known_projection else "",
        )

        marker = '<section class="home-chart-wrap"'
        self.assertIn(marker, rendered)
        mutated = rendered.replace(
            marker,
            '<section class="home-chart-wrap"><aside class="unknown-shell-child"></aside></section><section class="home-chart-wrap"',
            1,
        )
        difference = first_authored_difference(
            spec,
            mutated,
            locale="en",
            viewport=VIEWPORT,
            allowlist=[],
        )
        self.assertIsNotNone(difference)
        self.assertEqual(difference.region, "chart")
        self.assertEqual(difference.category, "ordered-children")

    def test_locale_and_window_setters_require_post_and_safe_redirects(self):
        self.assertEqual(self.client.get("/locale/en/").status_code, 405)
        locale = self.client.post("/locale/en/", HTTP_REFERER="https://example.invalid/")
        self.assertEqual(locale.status_code, 302)
        self.assertEqual(locale["Location"], "/")
        window = self.client.post("/window/7/", HTTP_REFERER="http://127.0.0.1/")
        self.assertEqual(window.status_code, 302)
        self.assertEqual(window["Location"], "http://127.0.0.1/")

    def test_root_shell_and_its_runtime_endpoints_are_public(self):
        anonymous = Client(HTTP_HOST="127.0.0.1")
        root = anonymous.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertIn("csrftoken", anonymous.cookies)
        self.assertEqual(anonymous.get("/feed/").status_code, 200)
        self.assertEqual(anonymous.get("/chart.html").status_code, 200)
        self.assertEqual(anonymous.post("/locale/en/", HTTP_REFERER="http://127.0.0.1/").status_code, 302)
        self.assertEqual(anonymous.post("/window/7/", HTTP_REFERER="http://127.0.0.1/").status_code, 302)
        self.assertEqual(anonymous.get("/internal/").status_code, 302)

    def test_chart_partial_has_no_execution_comment_or_rendered_note(self):
        """Regression pin: chart implementation notes must never reach users."""
        repo_root = Path(__file__).resolve().parents[1]
        product_sources = (
            repo_root / "monitor/templates/monitor/home.html",
            repo_root / "monitor/templates/monitor/home_internal.html",
            repo_root / "monitor/templates/monitor/_home_chart.html",
            repo_root / "monitor/static/pw-chart.js",
            repo_root / "monitor/static/pw-brand-chart.js",
        )
        for source_path in product_sources:
            with self.subTest(source=str(source_path.relative_to(repo_root))):
                source = source_path.read_text(encoding="utf-8")
                self.assertNotIn("{{AGENT_ATTRIBUTION}}", source)
                if source_path.name == "_home_chart.html":
                    self.assertNotIn(
                        "{#",
                        source,
                        "Public chart markup must not contain Django execution comments.",
                    )

        rendered = self._render("en")
        internal = self.client.get("/internal/")
        self.assertEqual(internal.status_code, 200)
        for output in (rendered, internal.content.decode("utf-8")):
            self.assertNotIn("{{AGENT_ATTRIBUTION}}", output)
            self.assertNotIn("The root shell retains the authored mockup", output)
            self.assertNotIn("pw-chart.js redraws these fallback paths", output)
