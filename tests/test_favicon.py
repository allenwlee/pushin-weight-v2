"""Regression coverage for the site favicon and its logo provenance."""

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, override_settings

from monitor import views

LOGO_PATH = (
    "M11.82 2.35c-3.03.04-4.78 2.08-4.95 5.71L5.6 8.9 4.24 21.17"
    "c2.42.32 5.02.47 7.72.45 2.69-.01 5.34-.19 7.83-.54L18.2 8.82l-1.16-.76"
    "c-.28-3.63-2.2-5.75-5.22-5.71Zm.02 2.26c1.7-.02 2.59 1.13 2.82 3.78"
    "l-5.47.06c.13-2.6.98-3.82 2.65-3.84ZM7.66 10.54l8.59-.09 1.06 8.63"
    "c-1.68.18-3.47.27-5.35.28-1.84.02-3.59-.06-5.24-.22l.94-8.6Z"
)


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
class FaviconTests(SimpleTestCase):
    def _get_public_home(self):
        chart_payload = {
            "top_voices": {"entries": []},
            "trend_narrative": {},
            "pulse": {"entries": [], "window_days": 1, "computed_at": ""},
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

    def test_public_home_serves_transparent_existing_logo_as_favicon(self) -> None:
        response = self._get_public_home()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">',
            html=True,
        )

        favicon_path = finders.find("favicon.svg")
        self.assertIsNotNone(favicon_path)
        root = ElementTree.parse(Path(favicon_path)).getroot()
        self.assertEqual(root.attrib["viewBox"], "4.24 2.3494 15.55 19.2724")

        namespace = {"svg": "http://www.w3.org/2000/svg"}
        mark = root.find("svg:path", namespace)
        self.assertIsNone(root.find("svg:rect", namespace))
        self.assertIsNotNone(mark)
        self.assertEqual(mark.attrib["fill"], "#0b1220")
        self.assertNotIn("transform", mark.attrib)
        self.assertEqual(mark.attrib["d"], LOGO_PATH)
