"""Regression coverage for the site favicon and its logo provenance."""

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, override_settings

from monitor import views

LOCKED_LOGO_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "docs/ideation/assets/2026-10-28-183433-locked-line-logo.svg"
)
LOCKED_VIEW_BOX = "90.5 97.0 697.6 930.9"


def _locked_logo_path() -> str:
    root = ElementTree.parse(LOCKED_LOGO_SOURCE).getroot()
    return root.find("{http://www.w3.org/2000/svg}path").attrib["d"]


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
class FaviconTests(SimpleTestCase):
    def _get_public_home(self):
        chart_payload = {
            "top_voices": {"entries": []},
            "trend_narrative": {},
            "pulse": {"entries": [], "window_days": 1, "computed_at": ""},
            "computed_at": "",
        }
        query = SimpleNamespace(values_list=lambda *args, **kwargs: [])
        with ExitStack() as patches:
            patches.enter_context(
                patch("monitor.views._build_brands_context", return_value=[])
            )
            patches.enter_context(
                patch("monitor.views._build_home_chart_payload", return_value=chart_payload)
            )
            patches.enter_context(
                patch("monitor.views._dashboard_filter_entries", return_value={})
            )
            patches.enter_context(
                patch("monitor.views._home_preferences_namespace", return_value="anonymous")
            )
            patches.enter_context(
                patch("monitor.views.SentimentKey.objects.order_by", return_value=query)
            )
            patches.enter_context(
                patch("core.context_processors._get_brands", return_value=[])
            )
            if hasattr(views, "_feed_page_wire"):
                patches.enter_context(
                    patch(
                        "monitor.views._feed_page_wire",
                        return_value=([], None, False, {}),
                    )
                )
            else:
                patches.enter_context(
                    patch("monitor.views._get_feed_posts", return_value=[])
                )
                patches.enter_context(
                    patch(
                        "monitor.views._enrich_posts_with_classifications",
                        return_value=[],
                    )
                )
            return self.client.get("/", secure=True)

    def test_public_home_serves_the_locked_line_logo_as_favicon(self) -> None:
        response = self._get_public_home()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">',
            html=True,
        )

        favicon_path = finders.find("favicon.svg")
        self.assertIsNotNone(favicon_path)
        source = Path(favicon_path).read_text(encoding="utf-8")
        root = ElementTree.fromstring(source)
        self.assertEqual(root.attrib["viewBox"], LOCKED_VIEW_BOX)

        namespace = {"svg": "http://www.w3.org/2000/svg"}
        mark = root.find("svg:path", namespace)
        self.assertIsNone(root.find("svg:rect", namespace))
        self.assertIsNotNone(mark)
        self.assertEqual(mark.attrib["fill"], "none")
        self.assertNotIn("transform", mark.attrib)
        self.assertEqual(mark.attrib["d"], _locked_logo_path())
        # Line weight stays one pixel at the 16px tab-icon size.
        self.assertAlmostEqual(float(mark.attrib["stroke-width"]) / 930.9 * 16, 1.0, places=2)
        self.assertIn("path{stroke:#18212d}", source)
        self.assertIn("@media (prefers-color-scheme:dark){path{stroke:#e8eaed}}", source)
