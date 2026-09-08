from __future__ import annotations

from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from monitor import views


class PublicHomeWindowCookieTests(SimpleTestCase):
    def _render_home(self, path: str) -> tuple[HttpResponse, dict, object]:
        request = RequestFactory().get(path)
        request.COOKIES[views.HOME_WINDOW_COOKIE] = "365"
        rendered: dict = {}

        def fake_render(_request, _template, context):
            rendered.update(context)
            return HttpResponse("ok")

        chart_payload = {
            "top_voices": {"entries": []},
            "trend_narrative": {},
            "pulse": {"entries": []},
        }
        with (
            patch.object(views, "_resolve_locale", return_value="en"),
            patch.object(views, "_build_brands_context", return_value=[]),
            patch.object(views, "_feed_page_wire", return_value=([], None, False, {})) as feed,
            patch.object(views, "_build_home_chart_payload", return_value=chart_payload),
            patch.object(views.SentimentKey, "objects") as sentiment_objects,
            patch.object(views, "_dashboard_filter_entries", return_value={}),
            patch.object(views, "render", side_effect=fake_render),
        ):
            sentiment_objects.order_by.return_value.values_list.return_value = []
            response = views.home(request)

        return response, rendered, feed

    def test_public_home_ignores_shared_window_cookie_without_erasing_it(self) -> None:
        response, rendered, feed = self._render_home("/")

        self.assertEqual(rendered["home_window_days"], 1)
        self.assertEqual(feed.call_args.kwargs["window_days"], 1)
        self.assertNotIn(views.HOME_WINDOW_COOKIE, response.cookies)

    def test_public_home_keeps_explicit_window_query_authoritative(self) -> None:
        response, rendered, feed = self._render_home("/?window=365")

        self.assertEqual(rendered["home_window_days"], 365)
        self.assertEqual(feed.call_args.kwargs["window_days"], 365)
        self.assertNotIn(views.HOME_WINDOW_COOKIE, response.cookies)

    def test_public_home_keeps_explicit_filter_window_authoritative(self) -> None:
        response, rendered, feed = self._render_home(
            "/?filters=%7B%22window%22%3A30%7D"
        )

        self.assertEqual(rendered["home_window_days"], 30)
        self.assertEqual(feed.call_args.kwargs["window_days"], 30)
        self.assertNotIn(views.HOME_WINDOW_COOKIE, response.cookies)

    def test_legacy_window_resolver_still_honors_cookie_for_other_routes(self) -> None:
        request = RequestFactory().get("/")
        request.COOKIES[views.HOME_WINDOW_COOKIE] = "365"

        self.assertEqual(views._resolve_home_window(request), 365)
