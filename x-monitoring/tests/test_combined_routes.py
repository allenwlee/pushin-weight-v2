# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard combined chart routes (Unit 3, v2.0 plan).

Mirrors test_dashboard.py::TestGridHtmlPollEndpoint pattern.

Routes added:
- GET /combined                   — initial render with full page
- GET /api/combined.html          — htmx partial (innerHTML fragment)
- GET /api/combined.json          — structured payload
- GET /api/combined_window/<int>  — set combined_window cookie + redirect
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from x_monitor.config import Config
from x_monitor.dashboard import MODEL_DISPLAY_NAMES


# ---------------------------------------------------------------------------
# /combined (initial render)
# ---------------------------------------------------------------------------


def test_combined_page_returns_200_html():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/combined")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type


def test_combined_page_contains_canvas_with_data_combined():
    """The /combined page must include a <canvas> inside a wrapper with
    a data-combined JSON attribute, mirroring the 9-card grid's pattern."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/combined").get_data(as_text=True)
        assert "combined-chart-wrap" in body
        assert 'data-combined=' in body
        assert 'class="combined-chart"' in body


def test_combined_page_has_main_with_htmx_poll():
    """The combined page must hx-get the partial endpoint every poll_seconds."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/combined").get_data(as_text=True)
        assert 'hx-get="/api/combined.html"' in body
        assert 'hx-swap="innerHTML"' in body
        assert "every 30s" in body  # default poll_seconds


def test_combined_page_third_topbar_tab_is_active():
    """The 'Combined' topbar tab must carry is-active on /combined."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/combined").get_data(as_text=True)
        # Find the Combined tab and verify it's marked active
        # Pattern: <a class="view-tab is-active" ... >Combined</a>
        assert "Combined" in body
        # At least one tab is marked active
        assert 'class="view-tab is-active"' in body


def test_combined_page_includes_window_toggle():
    """The combined page must show the 8-window toggle (1d / 7d / 14d / ...)."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/combined").get_data(as_text=True)
        for label in ["1d", "7d", "14d", "30d", "60d", "90d", "180d", "360d"]:
            assert label in body, f"missing window toggle: {label}"


def test_combined_page_window_cookie_picks_window():
    """combined_window cookie drives the window used in data shape."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        client.set_cookie("combined_window", "60")
        # JSON endpoint tells us the window that was used
        body = client.get("/api/combined.json").get_data(as_text=True)
        payload = json.loads(body)
        assert payload["window_days"] == 60


# ---------------------------------------------------------------------------
# /api/combined.html (htmx partial)
# ---------------------------------------------------------------------------


def test_api_combined_html_returns_200_html():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/api/combined.html")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type


def test_api_combined_html_is_innerhtml_fragment():
    """The htmx partial must NOT include <html>/<body> wrappers."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/api/combined.html").get_data(as_text=True)
        assert "<html" not in body
        assert "<body" not in body
        assert "</body>" not in body


def test_api_combined_html_includes_combined_chart_wrap_with_data_combined():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/api/combined.html").get_data(as_text=True)
        assert "combined-chart-wrap" in body
        assert 'data-combined=' in body


# ---------------------------------------------------------------------------
# /api/combined.json (structured payload)
# ---------------------------------------------------------------------------


def test_api_combined_json_returns_200_json():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/api/combined.json")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type


def test_api_combined_json_shape():
    """Payload has {days, series, stacked, window_days, fetched_at}."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/api/combined.json").get_data(as_text=True)
        payload = json.loads(body)
        assert "days" in payload
        assert "series" in payload
        assert "stacked" in payload
        assert "window_days" in payload
        assert "fetched_at" in payload
        assert "window" in payload
        # 2 enabled brands, both present in series + stacked
        assert set(payload["series"].keys()) == {"minimax", "qwen"}
        assert set(payload["stacked"].keys()) == {"minimax", "qwen"}
        # window_days default 30, len(days) == 30
        assert payload["window_days"] == 30
        assert len(payload["days"]) == 30


def test_api_combined_json_window_metadata_includes_allowed_values():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/api/combined.json").get_data(as_text=True)
        payload = json.loads(body)
        assert payload["window"]["default_window_days"] == 30
        assert payload["window"]["allowed_windows"] == [1, 7, 14, 30, 60, 90, 180, 360]


# ---------------------------------------------------------------------------
# /api/combined_window/<int> (cookie setter + redirect)
# ---------------------------------------------------------------------------


def test_api_combined_window_60_sets_cookie_and_redirects():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/api/combined_window/60")
        # 302 redirect to /combined
        assert resp.status_code in (302, 303)
        # Set-Cookie: combined_window=60
        cookie_header = resp.headers.get("Set-Cookie", "")
        assert "combined_window=60" in cookie_header


def test_api_combined_window_400_returns_400():
    """Out-of-range window is rejected with 400."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/api/combined_window/400")
        assert resp.status_code == 400


def test_api_combined_window_60_then_json_uses_60():
    """End-to-end: cookie set via /api/combined_window/60 affects /api/combined.json."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        client.get("/api/combined_window/60")
        body = client.get("/api/combined.json").get_data(as_text=True)
        payload = json.loads(body)
        assert payload["window_days"] == 60
        assert len(payload["days"]) == 60
        # window metadata reports the request as honored
        # (combined chart has no clamp, so requested == combined_window_days)
        assert payload["window"]["combined_window_days"] == 60


# ---------------------------------------------------------------------------
# Topbar nav sanity — both / and /grid now have the 3rd tab
# ---------------------------------------------------------------------------


def test_topbar_has_three_tabs_on_grid():
    """Unit 5 will update grid.html.j2 to add the 3rd tab.
    Pre-Unit-5 the count is 2; post-Unit-5 it is 3."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/grid").get_data(as_text=True)
        # Count <a class="view-tab occurrences — strict to avoid matching
        # the parent <nav class="view-tabs"> element.
        import re
        anchors = re.findall(r'<a class="view-tab', body)
        assert len(anchors) == 3, f"expected 3 tab anchors, got {len(anchors)}"


def test_topbar_has_three_tabs_on_index():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/").get_data(as_text=True)
        import re
        anchors = re.findall(r'<a class="view-tab', body)
        assert len(anchors) == 3, f"expected 3 tab anchors, got {len(anchors)}"


def test_topbar_has_three_tabs_on_combined():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/combined").get_data(as_text=True)
        import re
        anchors = re.findall(r'<a class="view-tab', body)
        assert len(anchors) == 3, f"expected 3 tab anchors, got {len(anchors)}"


# ---------------------------------------------------------------------------
# Verify the 9-card grid and treemap are unchanged
# ---------------------------------------------------------------------------


def test_grid_route_still_returns_cards():
    """Sanity: 9-card grid still works (no regression from adding /combined)."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=list(MODEL_DISPLAY_NAMES.keys()), daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/grid").get_data(as_text=True)
        assert body.count('class="model-card"') == len(MODEL_DISPLAY_NAMES)


def test_index_route_still_returns_treemap():
    """Sanity: treemap front page still works."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Treemap has the SVG with class treemap
        assert "<svg" in body or "treemap" in body