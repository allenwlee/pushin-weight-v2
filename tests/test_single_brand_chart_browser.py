"""Exercise the General URL, real template, chart endpoint and browser controls."""

from threading import Thread
from types import SimpleNamespace
from uuid import UUID
from wsgiref.simple_server import make_server

from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from django.test import override_settings
from playwright.sync_api import sync_playwright

from core import context_processors
from monitor import general_views, single_brand_chart


def test_public_general_pulse_chart_browser(monkeypatch):
    key = UUID("d5278b36-2098-4648-a791-b4b696de0b6c")
    monkeypatch.setattr(single_brand_chart, "_CHART_BUILD_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(context_processors, "_get_brands", lambda *args: [])
    monkeypatch.setattr(
        general_views,
        "selection",
        lambda request: {
            "locale": "en",
            "weights": "open",
            "audience": "human",
            "timezone": "local",
            "brands": [],
        },
    )
    monkeypatch.setattr(general_views, "_settings_links", lambda *args: {})
    monkeypatch.setattr(
        general_views, "_home_preferences_namespace", lambda *args: "browser-test"
    )
    monkeypatch.setattr(
        general_views,
        "general_feed",
        lambda section, **kwargs: {
            "section": section,
            "items": [],
            "next_cursor": None,
        },
    )
    monkeypatch.setattr(general_views, "present_feed", lambda value: value)
    monkeypatch.setattr(
        general_views,
        "editorial_panels",
        lambda *args: {
            "chatter": {
                "track": "chatter",
                "title": "Chatter",
                "status": "empty",
                "items": [],
                "glyph": "icon-discourse",
            },
            "pulse": {
                "track": "pulse",
                "title": "Pulse",
                "status": "empty",
                "items": [],
                "glyph": "icon-rise",
                "framework": {"status": "unavailable"},
            },
        },
    )
    monkeypatch.setattr(
        single_brand_chart,
        "_public_products",
        lambda: SimpleNamespace(
            filter=lambda **kwargs: SimpleNamespace(
                first=lambda: SimpleNamespace(product_key=key)
            )
        ),
    )
    points = [
        {
            "date": f"2026-08-{13 + i:02d}",
            "day": i,
            "raw": value,
            "percent": value,
            "smooth_percent": value,
            "coverage": "missing" if value is None else "observed",
            "source_date": None,
            "carried": False,
        }
        for i, value in enumerate([0, 10, None, 20])
    ]
    line = {
        "key": "discussion:posts",
        "source": "discussion",
        "metric": "posts",
        "label": "Brand posts",
        "unit": "posts",
        "identifier": "test",
        "status": "available",
        "observed_dates": 3,
        "reference": {
            "basis": "complete_week",
            "mean": 10,
            "start": "2026-08-13",
            "end": "2026-08-19",
        },
        "points": points,
    }
    monkeypatch.setattr(
        single_brand_chart,
        "_calculate_chart",
        lambda *args: {
            "product": {
                "key": str(key),
                "label": "Test model",
                "release_date": "2026-08-13",
            },
            "lines": [line],
            "notes": [],
        },
    )
    with override_settings(ALLOWED_HOSTS=["127.0.0.1"], SECURE_SSL_REDIRECT=False):
        server = make_server("127.0.0.1", 0, StaticFilesHandler(get_wsgi_application()))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(
                    f"http://127.0.0.1:{server.server_port}/general/?lang=en",
                    wait_until="networkidle",
                )
                assert response.status == 200
                page.locator("#ce-content:not([hidden])").wait_for(timeout=20000)
                assert page.locator("#ce-title").inner_text() == "Test model"
                assert page.evaluate(
                    "Chart.getChart(document.getElementById('ce-chart')).data.datasets[0].data"
                ) == [0, 10, None, 20]
                page.locator("#ce-legend button").first.click()
                assert (
                    page.locator("#ce-legend button").first.get_attribute(
                        "aria-pressed"
                    )
                    == "false"
                )
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.locator("#ce-chart").bounding_box()["width"] > 0
                page.route(
                    "**/general/chart/products/**",
                    lambda route: route.fulfill(
                        json={
                            "products": [
                                {
                                    "key": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                                    "label": "Another model",
                                }
                            ]
                        }
                    ),
                )
                page.locator("#ce-search").fill("Another")
                page.locator(
                    "#ce-product option[value='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb']"
                ).wait_for(state="attached")
                assert page.locator("#ce-product").input_value() == str(key)
                assert page.locator("#ce-content").is_visible()
                page.evaluate(
                    """payload => {
                  window.fetch = () => new Promise(resolve => {
                    window.finishOldRequest = () => resolve(new Response(JSON.stringify(payload), {status: 200}));
                  });
                }""",
                    {
                        "product": {
                            "key": str(key),
                            "label": "Test model",
                            "release_date": "2026-08-13",
                        },
                        "lines": [line],
                        "notes": [],
                    },
                )
                page.locator("#ce-refresh").click()
                page.evaluate("""() => {
                  const select = document.getElementById('ce-product');
                  select.add(new Option('New model', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'));
                  select.value = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
                  select.dispatchEvent(new Event('change'));
                  window.finishOldRequest();
                }""")
                page.wait_for_timeout(100)
                assert (
                    page.locator("#ce-product").input_value()
                    == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
                )
                assert page.locator("#ce-content").is_hidden()
                assert not errors
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
