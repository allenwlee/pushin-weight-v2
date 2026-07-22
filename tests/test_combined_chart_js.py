# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor combined chart JS module (Unit 4, v2.0 plan).

The x-monitoring codebase tests JS indirectly via the HTML payload
shape (see test_dashboard.py::TestTrendChartAssets). We follow the
same pattern here: verify the script is served, the canvas + wrapper
markup is correct, and the data-combined JSON payload has the shape
the JS expects.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from x_monitor.config import Config


# ---------------------------------------------------------------------------
# Static asset tests
# ---------------------------------------------------------------------------


def test_combined_chart_js_is_served():
    """The combined-chart.js static asset must be served by Flask."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/static/combined-chart.js")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Must declare the IIFE pattern trend-chart.js uses
        assert "(function () {" in body or "(function(){" in body
        # Must reference the 6 signal keys (for the overlay datasets)
        for sig in [
            "release", "community_question", "criticism",
            "commenter_capture", "other", "praise",
        ]:
            assert sig in body, f"missing signal key: {sig}"


def test_combined_chart_js_has_hover_overlay_logic():
    """The JS must implement the onHover overlay toggle.

    Test by string-grep since the codebase doesn't have a JS runtime
    test rig (matches TestTrendChartAssets pattern of static checks).
    """
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/static/combined-chart.js").get_data(as_text=True)
        # Must reference the data attribute name
        assert "data-combined" in body
        # Must implement defensive destroy-before-create
        assert ".destroy()" in body
        # Must have an onHover or interaction handler that toggles datasets
        assert "onHover" in body or "hover" in body.lower()


# ---------------------------------------------------------------------------
# HTML payload shape (data-combined JSON)
# ---------------------------------------------------------------------------


def test_combined_chart_html_data_combined_shape():
    """The /combined page data-combined attribute parses to expected shape."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/combined").get_data(as_text=True)
        # Extract the data-combined JSON from the <main> tag
        match = re.search(r"""data-combined='([^']+)'""", body)
        assert match, "no data-combined attribute on /combined"
        payload = json.loads(match.group(1))
        # JS expects: {days, series, stacked, window_days, fetched_at}
        assert "days" in payload
        assert "series" in payload
        assert "stacked" in payload
        assert "window_days" in payload
        assert "fetched_at" in payload
        # 2 enabled brands
        assert set(payload["series"].keys()) == {"minimax", "qwen"}
        # Each brand in stacked has all 6 signals (the JS builds 11*6=66 overlay datasets)
        for brand in payload["stacked"]:
            assert set(payload["stacked"][brand].keys()) == {
                "release", "community_question", "criticism",
                "commenter_capture", "other", "praise",
            }


def test_combined_chart_partial_data_combined_shape():
    """The htmx partial /api/combined.html also has data-combined JSON."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/api/combined.html").get_data(as_text=True)
        match = re.search(r"""data-combined='([^']+)'""", body)
        assert match, "no data-combined attribute on /api/combined.html"
        payload = json.loads(match.group(1))
        assert "days" in payload
        assert "series" in payload
        assert "stacked" in payload


def test_combined_chart_html_includes_canvas():
    """The /combined page must include the canvas element the JS hooks into."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/combined").get_data(as_text=True)
        assert '<canvas class="combined-chart"' in body


def test_combined_chart_html_loads_combined_chart_js():
    """The combined.html template must <script src=...> the new JS module."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/combined").get_data(as_text=True)
        assert "combined-chart.js" in body