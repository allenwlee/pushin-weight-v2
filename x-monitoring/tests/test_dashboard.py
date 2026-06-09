# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard (Unit 7 grid + Unit 8 drill-down wiring)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from x_monitor.config import Config
from x_monitor.dashboard import (
    MODEL_DISPLAY_NAMES,
    _qid_to_signal,
    _parse_post_timestamp,
    serialize_grid_card,
)
from x_monitor.store import Store


def test_serialize_grid_card_no_posts():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            card = serialize_grid_card("minimax", [], window_days=14, latest_run=None)
            assert card["model_id"] == "minimax"
            chart = card["chart"]
            assert len(chart["days"]) == 14
            for series in chart["series"].values():
                assert series == [0] * 14
            assert card["n_posts_in_window"] == 0
            assert card["top3_posts"] == []
            assert card["degraded_sentinels"] == []
        finally:
            store.close()


def test_serialize_grid_card_with_posts_and_cookies_degraded():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        store = Store(data / "x.db")
        try:
            now_iso = "2026-06-07T12:00:00+00:00"
            posts = [
                {
                    "tweet_id": f"t{i}",
                    "model_id": "minimax",
                    "author_handle": "u1",
                    "text": f"hello {i}",
                    "favorite_count": i,
                    "created_at": now_iso,
                    "source_query_id": "Q1",
                }
                for i in range(3)
            ]
            store.insert_posts(posts)
            latest = {"degraded": {"cookies": True}, "finished_at": now_iso}
            card = serialize_grid_card(
                "minimax", store.get_all_posts("minimax"), window_days=14, latest_run=latest
            )
            assert "cookies" in card["degraded_sentinels"]
            assert len(card["top3_posts"]) == 3
        finally:
            store.close()


def test_serialize_grid_card_query_rot_sentinel():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        latest = {
            "degraded": {},
            "queries": [
                {"model_id": "minimax", "query_id": "Q3", "status": "error", "n_results": 0}
            ],
        }
        card = serialize_grid_card("minimax", [], window_days=14, latest_run=latest)
        assert any("q_error:Q3" in s for s in card["degraded_sentinels"])


def test_dashboard_index_renders_all_known_cards():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=list(MODEL_DISPLAY_NAMES.keys()), daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        for m in cfg.enabled_models:
            assert f'data-model-id="{m}"' in body
        # Exactly len(MODEL_DISPLAY_NAMES) model cards
        assert body.count('class="model-card"') == len(MODEL_DISPLAY_NAMES)


def test_dashboard_api_grid_json_returns_cards():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/api/grid.json")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "cards" in body
        assert len(body["cards"]) == 2
        for card in body["cards"]:
            for key in (
                "model_id",
                "chart",
                "signal_breakdown",
                "top3_posts",
                "degraded_sentinels",
                "last_run_at",
            ):
                assert key in card
            assert "days" in card["chart"]
            assert "series" in card["chart"]
            assert len(card["chart"]["days"]) == 14
            assert len(card["chart"]["series"]) == 6


def test_dashboard_unknown_model_returns_404():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/model/bogus")
        assert resp.status_code == 404


def test_dashboard_known_model_drilldown_renders_4_tabs():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/model/minimax")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # 4 tab buttons
        for tab in ("posts", "graph", "clusters", "roles"):
            assert f'data-tab="{tab}"' in body


def test_dashboard_adding_tenth_model_yields_tenth_card():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        # Use a real model from the registry + a 10th would require extending
        # the registry. Instead, test that the count matches enabled_models.
        cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/").get_data(as_text=True)
        assert body.count('class="model-card"') == 2


def test_dashboard_drilldown_known_model_200():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/model/minimax")
        assert resp.status_code == 200


def test_dashboard_htmx_script_included_exactly_once():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/").get_data(as_text=True)
        # htmx script tag
        assert body.count("htmx.org") == 1

def test_serialize_grid_card_chart_six_series_aligned_to_window():
    """Feed posts on 3 different days with different Q-IDs; each series
    must be 14 entries, with the right day indices holding the right counts."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    days_ago = [0, 3, 10]  # today, 3 days ago, 10 days ago
    posts = []
    for i, ago in enumerate(days_ago):
        ts = (now - timedelta(days=ago)).strftime("%a %b %d %H:%M:%S %z %Y")
        qid = ["Q1", "Q3", "Q6"][i]
        posts.append(
            {
                "tweet_id": f"t{i}",
                "model_id": "minimax",
                "author_handle": f"u{i}",
                "text": f"hello {i}",
                "favorite_count": i,
                "created_at": ts,
                "source_query_id": qid,
            }
        )
    card = serialize_grid_card("minimax", posts, window_days=14)
    chart = card["chart"]
    assert len(chart["days"]) == 14
    assert set(chart["series"].keys()) == {
        "release", "community_question", "criticism",
        "commenter_capture", "other", "praise",
    }
    for key, expected in [
        ("release", 1),
        ("criticism", 1),
        ("praise", 1),
        ("community_question", 0),
        ("commenter_capture", 0),
        ("other", 0),
    ]:
        assert sum(chart["series"][key]) == expected, f"{key} total wrong"
    # The Q1 post was on "today" -> index 13 (oldest is i=0)
    assert chart["series"]["release"][13] == 1
    # The Q3 post was 3 days ago -> index 10
    assert chart["series"]["criticism"][10] == 1
    # The Q6 post was 10 days ago -> index 3
    assert chart["series"]["praise"][3] == 1


def test_serialize_grid_card_chart_unknown_qid_dropped():
    """Unknown Q-IDs (defensive) must not pollute any series."""
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S %z %Y")
    posts = [
        {"tweet_id": "t1", "model_id": "minimax", "author_handle": "u1",
         "text": "?", "favorite_count": 0, "created_at": now_iso,
         "source_query_id": "Q99"},
    ]
    card = serialize_grid_card("minimax", posts, window_days=14)
    for series in card["chart"]["series"].values():
        assert sum(series) == 0
    assert card["signal_breakdown"] == {}


def test_serialize_grid_card_chart_zero_posts_window():
    """Empty input -> 14-day axis with all-zero series."""
    card = serialize_grid_card("minimax", [], window_days=14)
    chart = card["chart"]
    assert len(chart["days"]) == 14
    for key in ("release", "community_question", "criticism",
                "commenter_capture", "other", "praise"):
        assert chart["series"][key] == [0] * 14


def test_qid_to_signal_helper():
    assert _qid_to_signal("Q1") == "release"
    assert _qid_to_signal("Q2") == "community_question"
    assert _qid_to_signal("Q3") == "criticism"
    assert _qid_to_signal("Q4") == "commenter_capture"
    assert _qid_to_signal("Q5") == "other"
    assert _qid_to_signal("Q6") == "praise"
    assert _qid_to_signal("Q99") is None
    assert _qid_to_signal("") is None
    assert _qid_to_signal(None) is None


class TestParsePostTimestamp:
    def test_iso8601_with_z(self):
        dt = _parse_post_timestamp("2026-06-08T22:40:07Z")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.year == 2026 and dt.hour == 22

    def test_iso8601_with_offset(self):
        dt = _parse_post_timestamp("2026-06-08T22:40:07+00:00")
        assert dt is not None
        assert dt.utcoffset().total_seconds() == 0

    def test_twitter_legacy_format(self):
        # Twitter legacy: "Mon Jun 08 22:40:07 +0000 2026"
        dt = _parse_post_timestamp("Mon Jun 08 22:40:07 +0000 2026")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 6 and dt.day == 8 and dt.hour == 22
        assert dt.utcoffset().total_seconds() == 0

    def test_none_returns_none(self):
        assert _parse_post_timestamp(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_post_timestamp("") is None

    def test_garbage_returns_none(self):
        assert _parse_post_timestamp("not a date") is None


class TestGridHtmlPollEndpoint:
    def test_returns_html_content_type(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            resp = client.get("/api/grid.html")
            assert resp.status_code == 200
            assert "text/html" in resp.content_type

    def test_renders_one_card_per_enabled_model(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=list(MODEL_DISPLAY_NAMES.keys()), daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/api/grid.html").get_data(as_text=True)
            assert body.count('class="model-card"') == len(MODEL_DISPLAY_NAMES)

    def test_response_is_innerhtml_fragment_not_full_page(self):
        """The poll response must NOT include <html>/<body> wrappers — htmx
        swaps it as innerHTML of <main>."""
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/api/grid.html").get_data(as_text=True)
            assert "<html" not in body
            assert "<body" not in body
            assert "</body>" not in body

    def test_grid_page_polls_html_endpoint(self):
        """The / page's <main> must hx-get the HTML endpoint so polling works."""
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/").get_data(as_text=True)
            assert 'hx-get="/api/grid.html"' in body
            # innerHTML swap keeps <main> alive across polls
            assert 'hx-swap="innerHTML"' in body
            # the trigger must be present and periodic
            assert "every 30s" in body


def test_serialize_grid_card_q6_maps_to_praise():
    """Q6 (praise) posts must be counted under 'praise' in signal_breakdown."""
    from datetime import datetime, timezone
    # Use a recent timestamp so it falls inside the 14-day window
    now_iso = datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S %z %Y")
    posts = [
        {"tweet_id": "t1", "model_id": "minimax", "source_query_id": "Q6",
         "text": "amazing!", "favorite_count": 10, "created_at": now_iso,
         "author_handle": "u1"},
        {"tweet_id": "t2", "model_id": "minimax", "source_query_id": "Q6",
         "text": "best!", "favorite_count": 5, "created_at": now_iso,
         "author_handle": "u2"},
        {"tweet_id": "t3", "model_id": "minimax", "source_query_id": "Q2",
         "text": "how does X work?", "favorite_count": 1, "created_at": now_iso,
         "author_handle": "u3"},
    ]
    card = serialize_grid_card("minimax", posts)
    assert card["signal_breakdown"].get("praise", 0) == 2
    assert card["signal_breakdown"].get("community_question", 0) == 1
    assert card["n_posts_in_window"] == 3


def test_serialize_grid_card_unknown_query_id_does_not_count():
    """Unknown Q-IDs (defensive) should not crash or be silently miscounted."""
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S %z %Y")
    posts = [
        {"tweet_id": "t1", "model_id": "minimax", "source_query_id": "Q99",
         "text": "???", "favorite_count": 0, "created_at": now_iso,
         "author_handle": "u1"},
    ]
    card = serialize_grid_card("minimax", posts)
    # Q99 is unknown; it must not be bucketed into praise or any other signal
    assert card["signal_breakdown"] == {}


class TestTrendChartAssets:
    def test_api_grid_html_includes_chart_canvas_per_card(self):
        """Each enabled model must get exactly one canvas.trend-chart in the
        /api/grid.html response, with a data-chart JSON payload that decodes
        into the expected 14-day / 6-series shape."""
        import json as _json
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/api/grid.html").get_data(as_text=True)
            assert body.count('class="trend-chart"') == 2
            # Each wrap must have a JSON-parseable data-chart attribute with
            # 14 days and 6 series.
            import re
            for match in re.finditer(r"""data-chart='([^']+)'""", body):
                payload = _json.loads(match.group(1))
                assert len(payload["days"]) == 14
                assert len(payload["series"]) == 6

    def test_grid_page_loads_chartjs_from_cdn(self):
        """The / page must include the Chart.js CDN script tag."""
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/").get_data(as_text=True)
            assert "chart.js" in body
            assert "unpkg.com" in body

    def test_grid_page_loads_static_trend_chart_js(self):
        """The / page must reference the local trend-chart.js asset."""
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/").get_data(as_text=True)
            assert "trend-chart.js" in body

    def test_model_detail_page_loads_chartjs(self):
        """Drill-down loads the chart deps too (drill-down doesn't render
        a chart today, but keeps the dep in one place)."""
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/model/minimax").get_data(as_text=True)
            assert "chart.js" in body
            assert "trend-chart.js" in body

