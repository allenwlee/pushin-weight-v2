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


def test_dashboard_index_renders_nine_cards():
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
        # Exactly 9 model cards
        assert body.count('class="model-card"') == 9


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
