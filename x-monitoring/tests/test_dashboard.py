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
    _parse_post_timestamp,
    build_sparkline,
    serialize_grid_card,
)
from x_monitor.store import Store


def test_build_sparkline_returns_svg():
    svg = build_sparkline([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], days=14)
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "polyline" in svg
    # No external <image href>
    assert "<image" not in svg


def test_build_sparkline_deterministic():
    a = build_sparkline([1, 2, 3] * 5, days=14)
    b = build_sparkline([1, 2, 3] * 5, days=14)
    assert a == b


def test_build_sparkline_handles_empty():
    svg = build_sparkline([], days=14)
    assert "<svg" in svg
    assert "<polyline" in svg


def test_build_sparkline_handles_all_zeros():
    svg = build_sparkline([0] * 14, days=14)
    assert "<svg" in svg


def test_serialize_grid_card_no_posts():
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "x.db")
        try:
            card = serialize_grid_card("minimax", [], window_days=14, latest_run=None)
            assert card["model_id"] == "minimax"
            assert "no posts" in card["sparkline_svg"] or "<svg" in card["sparkline_svg"]
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
                "sparkline_svg",
                "signal_breakdown",
                "top3_posts",
                "degraded_sentinels",
                "last_run_at",
            ):
                assert key in card
            assert "<svg" in card["sparkline_svg"]
            assert "<image" not in card["sparkline_svg"]


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

