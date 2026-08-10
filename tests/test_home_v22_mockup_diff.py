"""Real-ORM, root-route fidelity characterization against the v22 mockup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
