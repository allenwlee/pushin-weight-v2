# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard (Unit 7 grid + Unit 8 drill-down wiring)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from x_monitor.config import Config
from x_monitor.dashboard import (
    MODEL_DISPLAY_NAMES,
    _qid_to_signal,
    _parse_post_timestamp,
    brand_colorize,
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


def test_dashboard_grid_renders_all_known_cards():
    # Grid moved to /grid in v1.7 (treemap took /).
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=list(MODEL_DISPLAY_NAMES.keys()), daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        resp = client.get("/grid")
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


def test_dashboard_grid_adding_models_yields_matching_card_count():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/grid").get_data(as_text=True)
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


def test_dashboard_grid_htmx_script_included_exactly_once():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        from x_monitor.dashboard import DashboardApp

        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        body = client.get("/grid").get_data(as_text=True)
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
            body = client.get("/grid").get_data(as_text=True)
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
        """The /grid page must include the Chart.js CDN script tag."""
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/grid").get_data(as_text=True)
            assert "chart.js" in body
            assert "unpkg.com" in body

    def test_grid_page_loads_static_trend_chart_js(self):
        """The /grid page must reference the local trend-chart.js asset."""
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/grid").get_data(as_text=True)
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

    def test_grid_html_no_outer_card_link_anchor(self):
        """After refactor: no <a class="card-link"> wrapper. Card body
        navigates via JS click handler (trend-chart.js wireCardClicks),
        top-3 posts are first-class <a> tags."""
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax", "qwen"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/api/grid.html").get_data(as_text=True)
            assert 'class="card-link"' not in body
            # Each card should have a data-href for the JS click handler
            assert body.count('data-href="/model/') == 2

    def test_grid_html_top3_items_are_first_class_anchors(self):
        """Each top-3 <li> must wrap its content in an <a class="top3-link">
        with target='_blank' pointing at the tweet URL."""
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
            from x_monitor.dashboard import DashboardApp

            app = DashboardApp(cfg, data, db_path=data / "x.db")
            client = app.app.test_client()
            body = client.get("/api/grid.html").get_data(as_text=True)
            # Empty top-3 in fresh DB; render the empty-state message
            # but the template structure is still there.
            assert 'class="top3"' in body
            # Even with no posts, the .top3-item class shouldn't appear.
            # Add a post to exercise the per-post anchor path:
            # (Use direct serialize_grid_card instead.)
            from x_monitor.dashboard import serialize_grid_card
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S %z %Y")
            posts = [
                {"tweet_id": "t1", "model_id": "minimax", "author_handle": "u1",
                 "text": "hello", "favorite_count": 7, "created_at": now_iso,
                 "source_query_id": "Q5"},
            ]
            from jinja2 import Environment
            env = Environment(loader=__import__("jinja2").FileSystemLoader(
                str(Path("/Users/fuchitalee/development/minimax-marketing/x-monitoring/x_monitor/templates"))),
            )
            # Register the brand_colorize filter (v1.5) so the standalone
            # template render path works.
            from x_monitor.dashboard import brand_colorize as _bc
            env.filters["brand_colorize"] = _bc
            tpl = env.get_template("_model_card.html.j2")
            rendered = tpl.render(
                card=serialize_grid_card("minimax", posts),
                MODEL_DISPLAY_NAMES={"minimax": "MiniMax AI"},
                MODEL_ACCENT_COLORS={"minimax": "#3b82f6"},
            )
            assert 'class="top3-link"' in rendered
            assert 'target="_blank"' in rendered
            assert 'href="https://x.com/u1/status/t1"' in rendered



def test_serialize_grid_card_top3_exposes_like_count_not_favorite_count():
    """User-facing rename: the top3 dict key is `like_count`, not the raw
    DB column name `favorite_count`. Keeps the DB schema stable while
    exposing a clearer name to templates and the API."""
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S %z %Y")
    posts = [
        {"tweet_id": "t1", "model_id": "minimax", "author_handle": "u1",
         "text": "hi", "favorite_count": 42, "created_at": now_iso,
         "source_query_id": "Q5"},
        {"tweet_id": "t2", "model_id": "minimax", "author_handle": "u2",
         "text": "wow", "favorite_count": 7, "created_at": now_iso,
         "source_query_id": "Q6"},
    ]
    card = serialize_grid_card("minimax", posts)
    # top-3 list has 2 entries here, ranked by like_count desc
    top3 = card["top3_posts"]
    assert len(top3) == 2
    for entry in top3:
        assert "like_count" in entry
        assert "favorite_count" not in entry
    # Ordering check: 42 first, 7 second
    assert top3[0]["like_count"] == 42
    assert top3[1]["like_count"] == 7


def test_trend_chart_js_drops_begin_at_zero():
    """After v1.1: Y-axis uses `suggestedMin: 0` not `beginAtZero: true`,
    so a today=1 / yesterday=6 pair doesn't look like a cliff.
    The literal `beginAtZero: true` should be gone from the JS file."""
    js_path = Path("/Users/fuchitalee/development/minimax-marketing/x-monitoring/x_monitor/static/trend-chart.js")
    body = js_path.read_text()
    assert "beginAtZero: true" not in body, (
        "trend-chart.js still pins Y axis to zero; remove beginAtZero so "
        "low-volume days don't look like cliffs"
    )
    assert "suggestedMin: 0" in body


def test_trend_chart_js_wires_card_click_handler():
    """After card-link refactor: the JS bootstrap installs a click handler
    on .model-card[data-href] so the card body still navigates to the
    drill-down page, while clicks on the per-post .top3-link anchors
    bubble up to the tweet URL instead."""
    js_path = Path("/Users/fuchitalee/development/minimax-marketing/x-monitoring/x_monitor/static/trend-chart.js")
    body = js_path.read_text()
    assert "wireCardClicks" in body, "missing wireCardClicks handler"
    assert "data-href" in body, "missing data-href attribute reference"
    # Per-post anchor clicks must be ignored by the card-level handler
    assert "e.target.closest('a')" in body



# --- v1.2 commit 3: headline display in top3 -----------------------------


def test_top3_includes_headline_when_present():
    from x_monitor.dashboard import serialize_grid_card
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    posts = [
        {
            "tweet_id": "t1",
            "author_handle": "u1",
            "text": "https://t.co/abc",
            "headline": "Real Article Title",
            "headline_source": "fetched",
            "favorite_count": 100,
            "created_at": (now - timedelta(days=1)).isoformat(),
        },
    ]
    card = serialize_grid_card("minimax", posts)
    top3 = card["top3_posts"]
    assert len(top3) == 1
    assert top3[0]["headline"] == "Real Article Title"
    assert top3[0]["headline_source"] == "fetched"
    # display_text prefers headline over text
    assert top3[0]["display_text"] == "Real Article Title"
    # original text preserved for fallback
    assert top3[0]["text"] == "https://t.co/abc"


def test_top3_falls_back_to_text_when_no_headline():
    from x_monitor.dashboard import serialize_grid_card
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    posts = [
        {
            "tweet_id": "t1",
            "author_handle": "u1",
            "text": "minimax M3 is amazing",
            "favorite_count": 50,
            "created_at": (now - timedelta(days=1)).isoformat(),
        },
    ]
    card = serialize_grid_card("minimax", posts)
    top3 = card["top3_posts"]
    assert len(top3) == 1
    assert top3[0]["headline"] is None
    assert top3[0]["display_text"] == "minimax M3 is amazing"


# --- v1.5: dual time windows + brand colorization -----------------------


class TestSerializeGridCardDualWindows:
    """v1.5: serialize_grid_card returns top3_7d / top3_24h / n_posts_7d /
    n_posts_24h alongside the legacy 14-day fields. The 14-day chart logic
    is unchanged."""

    def test_serialize_grid_card_exposes_dual_time_windows(self):
        from datetime import datetime, timedelta, timezone

        now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        posts = [
            # 2h ago -> in 24h, in 7d, in 14d
            {
                "tweet_id": "a", "author_handle": "u1", "text": "hi",
                "favorite_count": 5,
                "created_at": (now - timedelta(hours=2)).isoformat(),
                "source_query_id": "Q5",
            },
            # 3d ago -> in 7d, in 14d, NOT in 24h
            {
                "tweet_id": "b", "author_handle": "u2", "text": "wow",
                "favorite_count": 3,
                "created_at": (now - timedelta(days=3)).isoformat(),
                "source_query_id": "Q6",
            },
            # 10d ago -> in 14d, NOT in 7d, NOT in 24h
            {
                "tweet_id": "c", "author_handle": "u3", "text": "cool",
                "favorite_count": 1,
                "created_at": (now - timedelta(days=10)).isoformat(),
                "source_query_id": "Q1",
            },
            # 30d ago -> NOT in 14d
            {
                "tweet_id": "d", "author_handle": "u4", "text": "old",
                "favorite_count": 99,
                "created_at": (now - timedelta(days=30)).isoformat(),
                "source_query_id": "Q6",
            },
        ]
        card = serialize_grid_card("minimax", posts, now=now)
        assert card["n_posts_7d"] == 2
        assert card["n_posts_24h"] == 1
        assert card["n_posts_in_window"] == 3
        assert len(card["top3_7d"]) == 2
        assert len(card["top3_24h"]) == 1

    def test_serialize_grid_card_dual_windows_preserve_likes_format(self):
        from datetime import datetime, timedelta, timezone

        now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        long_text = "x" * 250
        posts = [
            {
                "tweet_id": "a", "author_handle": "u1", "text": "hi",
                "favorite_count": 5,
                "created_at": (now - timedelta(hours=2)).isoformat(),
                "source_query_id": "Q5",
            },
            {
                "tweet_id": "b", "author_handle": "u2", "text": long_text,
                "favorite_count": 3,
                "created_at": (now - timedelta(days=3)).isoformat(),
                "source_query_id": "Q6",
            },
            {
                "tweet_id": "c", "author_handle": "u3", "text": "truncate me too",
                "favorite_count": 1,
                "created_at": (now - timedelta(days=4)).isoformat(),
                "source_query_id": "Q1",
            },
        ]
        card = serialize_grid_card("minimax", posts, now=now)
        # 7d should contain all three; 24h only the 2h-old one
        assert len(card["top3_7d"]) == 3
        assert len(card["top3_24h"]) == 1
        # Both lists: like_count key, no favorite_count, text truncated
        for entry in card["top3_7d"] + card["top3_24h"]:
            assert "like_count" in entry
            assert "favorite_count" not in entry
        # The long_text entry should be truncated to 200 chars (197 + "...")
        long_entry = next(p for p in card["top3_7d"] if p["tweet_id"] == "b")
        assert len(long_entry["text"]) == 200
        assert long_entry["text"].endswith("...")

    def test_serialize_grid_card_now_param_is_honored(self):
        from datetime import datetime, timezone

        fixed_now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        # 23h before fixed_now -> in 24h window
        ts_23h = "2026-06-09T13:00:00+00:00"
        # 25h before fixed_now -> NOT in 24h window (just outside)
        ts_25h = "2026-06-09T11:00:00+00:00"
        posts = [
            {
                "tweet_id": "a", "author_handle": "u1", "text": "fresh",
                "favorite_count": 1, "created_at": ts_23h, "source_query_id": "Q5",
            },
            {
                "tweet_id": "b", "author_handle": "u2", "text": "stale",
                "favorite_count": 2, "created_at": ts_25h, "source_query_id": "Q5",
            },
        ]
        card = serialize_grid_card("minimax", posts, now=fixed_now)
        assert len(card["top3_24h"]) == 1
        assert card["top3_24h"][0]["tweet_id"] == "a"
        # The 25h-old post is still in 7d though
        assert len(card["top3_7d"]) == 2

    def test_serialize_grid_card_anchors_now_to_latest_run_finished_at(self):
        """When no `now` is passed and `latest_run.finished_at` is set,
        the 24h/7d windows are computed relative to that timestamp, not
        wall-clock. This keeps the 24h column populated when the DB
        hasn't been updated today."""
        from datetime import datetime, timezone

        # Run finished at 2026-06-10 19:28 UTC. Post is 2h before that —
        # inside 24h relative to the run, but 3+ days before today.
        run_finished = "2026-06-10T19:28:05+00:00"
        ts_2h_before_run = "2026-06-10T17:28:05+00:00"
        posts = [{
            "tweet_id": "x", "author_handle": "u1", "text": "recent vs run",
            "favorite_count": 1, "created_at": ts_2h_before_run,
            "source_query_id": "Q5",
        }]
        latest_run = {"finished_at": run_finished}
        card = serialize_grid_card("minimax", posts, latest_run=latest_run)
        # 2h before run_finished is within 24h of run_finished
        assert len(card["top3_24h"]) == 1
        assert card["n_posts_24h"] == 1
        # And in 7d
        assert len(card["top3_7d"]) == 1
        # Without latest_run, the same post is 3+ days before today and
        # the 24h window (relative to wall-clock now) is empty.
        card_stale = serialize_grid_card("minimax", posts)
        assert card_stale["n_posts_24h"] == 0


class TestBrandColorize:
    """v1.5: Jinja filter `brand_colorize` colors model_id matches with
    the brand's accent color, escaping HTML first."""

    def test_brand_colorize_colors_known_brand_with_correct_hex(self):
        # Minimax -> #3b82f6
        out = brand_colorize("I love MiniMax M3")
        assert "color: #3b82f6;" in out
        assert "MiniMax" in out
        # Case-insensitive: lowercase "deepseek" -> #10b981
        out2 = brand_colorize("deepseek is great")
        assert "color: #10b981;" in out2
        assert "deepseek" in out2
        # Word boundary: "glm" attached to letters (no word boundary) must
        # NOT colorize. The standalone "glm" in "algorithm has glm in it"
        # IS a word, so use a string with "glm" glued to letters on at
        # least one side, e.g. "neuralglm" or "glmmodel".
        out3 = brand_colorize("neuralglam uses glmmodel")
        # No <span> tag should appear (no standalone glm token)
        assert "<span" not in out3
        # The full string is returned (with HTML-escape if needed)
        assert "neuralglam uses glmmodel" in out3
        # POSITIVE case: standalone "glm" IS a word, so it DOES colorize.
        # (The plan's original claim that \\bglm\\b wouldn't match inside
        # "algorithm has glm" is wrong — glm is a standalone word there.)
        out4 = brand_colorize("I built a glm model")
        assert "color: #a855f7;" in out4
        assert ">glm</span>" in out4
        # Markup regression: ampersand in input must become exactly one
        # &amp; in output (no &amp;amp;). This is the bug the reviewer
        # found when the return was a plain str (Jinja auto-escaped it).
        out5 = brand_colorize("MiniMax & DeepSeek")
        assert "&amp;" in out5
        assert "&amp;amp;" not in out5

    def test_brand_colorize_escapes_html_in_post_text(self):
        out = brand_colorize("<script>alert(1)</script> Qwen rocks")
        # The script tag must be escaped, not rendered
        assert "<script>" not in out
        assert "&lt;script&gt;" in out
        # "Qwen" should still be colorized to its accent color
        assert "color: #f97316;" in out
        assert "Qwen" in out

    def test_brand_colorize_handles_multiple_brand_mentions(self):
        out = brand_colorize("MiniMax beats DeepSeek at qwen benchmark")
        # Three spans, three distinct accent colors
        assert "color: #3b82f6;" in out   # MiniMax
        assert "color: #10b981;" in out   # DeepSeek
        assert "color: #f97316;" in out   # qwen
        # The surrounding text is intact (not consumed by the regex)
        assert " beats " in out
        assert " at " in out
        assert " benchmark" in out
        # Exactly three <span> tags
        assert out.count("<span") == 3



# --- v1.6 staleness indicator + dashboard.js -----------------------------

class TestStalenessIndicator:
    """The topbar surfaces a last-updated stamp so users can see how
    fresh the data is. Marked .stale after 1h."""

    def _make_client(self, tmp_path, with_runs=True):
        from x_monitor.config import Config
        from x_monitor.dashboard import DashboardApp
        from x_monitor.store import Store

        data = tmp_path / "data"
        data.mkdir()
        db_path = data / "x.db"
        runs_dir = data / "runs"
        if with_runs:
            runs_dir.mkdir()
        store = Store(db_path)
        store.close()
        app = DashboardApp(
            Config(enabled_models=["minimax"], daily_ceiling=333), data, db_path=db_path,
        )
        return app.app.test_client()

    def test_staleness_indicator_present_in_grid(self, tmp_path):
        client = self._make_client(tmp_path)
        r = client.get("/grid")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert 'id="last-run-stamp"' in body
        assert "data-finished-at=" in body
        assert "last updated:" in body

    def test_staleness_indicator_with_finished_at(self, tmp_path):
        from x_monitor.config import Config
        from x_monitor.dashboard import DashboardApp
        from x_monitor.store import Store

        data = tmp_path / "data"
        data.mkdir()
        runs_dir = data / "runs"
        runs_dir.mkdir()
        # DashboardApp expects LATEST.json to be a SYMLINK (production
        # writes it that way via the post-pipeline symlink step). The
        # symlink target holds the actual run summary.
        run_file = runs_dir / "2026-06-16T00-00-00.json"
        run_file.write_text(
            '{"finished_at": "2026-06-16T00:00:00+00:00"}',
            encoding="utf-8",
        )
        (runs_dir / "LATEST.json").symlink_to(run_file)
        store = Store(data / "x.db")
        store.close()
        app = DashboardApp(
            Config(enabled_models=["minimax"], daily_ceiling=333), data, db_path=data / "x.db",
        )
        r = app.app.test_client().get("/grid")
        body = r.get_data(as_text=True)
        assert "2026-06-16T00:00:00" in body
        assert "last updated: 2026-06-16T00:00:00+00:00" in body

    def test_staleness_indicator_when_never_run(self, tmp_path):
        client = self._make_client(tmp_path, with_runs=False)
        r = client.get("/grid")
        body = r.get_data(as_text=True)
        assert "last updated: never" in body

    def test_dashboard_js_served_as_static(self, tmp_path):
        client = self._make_client(tmp_path)
        r = client.get("/static/dashboard.js")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "updateLastRun" in body


# --- v1.7 treemap front page + nav strip + htmx partial -----------------

class TestTreemapRoutes:
    """The treemap front page replaces the grid on / in v1.7. The grid
    itself is preserved at /grid."""

    def test_treemap_root_renders_svg_and_nav(self, tmp_path):
        from x_monitor.config import Config
        from x_monitor.dashboard import DashboardApp

        data = tmp_path / "data"
        data.mkdir()
        app = DashboardApp(
            Config(
                enabled_models=["minimax", "qwen", "deepseek", "glm"],
                daily_ceiling=333,
            ),
            data, db_path=data / "x.db",
        )
        client = app.app.test_client()
        r = client.get("/")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        # Nav strip with both tabs
        assert "view-tabs" in body
        assert 'href="/"' in body
        assert 'href="/grid"' in body
        # Initial render embeds the SVG
        assert '<svg' in body
        assert 'class="treemap"' in body
        # htmx polling on the partial endpoint
        assert 'hx-get="/api/treemap.html"' in body
        assert 'hx-swap="innerHTML"' in body
        # Active tab is Treemap on this page
        assert 'aria-current="page"' in body
        # Legend present
        assert "Polarity" in body or "polarity" in body

    def test_treemap_grid_route_preserved(self, tmp_path):
        from x_monitor.config import Config
        from x_monitor.dashboard import DashboardApp

        data = tmp_path / "data"
        data.mkdir()
        app = DashboardApp(
            Config(enabled_models=["minimax"], daily_ceiling=333),
            data, db_path=data / "x.db",
        )
        client = app.app.test_client()
        r = client.get("/grid")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        # Grid-specific marker (a model-card div per enabled model)
        assert body.count('class="model-card"') == 1
        # Nav strip still present
        assert "view-tabs" in body
        # Active tab is Grid on this page (aria-current on the grid tab)
        assert 'href="/grid"' in body

    def test_api_treemap_html_returns_svg_partial_only(self, tmp_path):
        from x_monitor.config import Config
        from x_monitor.dashboard import DashboardApp

        data = tmp_path / "data"
        data.mkdir()
        app = DashboardApp(
            Config(enabled_models=["minimax", "qwen"], daily_ceiling=333),
            data, db_path=data / "x.db",
        )
        client = app.app.test_client()
        r = client.get("/api/treemap.html")
        assert r.status_code == 200
        # text/html, not application/json
        assert "text/html" in r.headers.get("Content-Type", "")
        body = r.get_data(as_text=True)
        # SVG only, no <main> wrapper (the client keeps the wrapping element)
        assert '<svg' in body
        assert "<main" not in body

    def test_api_treemap_json_has_tiles_and_window(self, tmp_path):
        from x_monitor.config import Config
        from x_monitor.dashboard import DashboardApp

        data = tmp_path / "data"
        data.mkdir()
        app = DashboardApp(
            Config(enabled_models=["minimax", "qwen"], daily_ceiling=333),
            data, db_path=data / "x.db",
        )
        client = app.app.test_client()
        r = client.get("/api/treemap.json")
        assert r.status_code == 200
        body = r.get_json()
        assert "tiles" in body
        assert "fetched_at" in body
        assert "window" in body
        assert body["window"]["treemap_volume_window_days"] == 7
        assert len(body["tiles"]) == 2
        for t in body["tiles"]:
            for key in (
                "model_id", "display_name", "accent_color",
                "area_weight", "polarity_score",
            ):
                assert key in t
        # Sort order: descending area_weight, then display_name
        weights = [t["area_weight"] for t in body["tiles"]]
        assert weights == sorted(weights, reverse=True)

    def test_treemap_tile_count_matches_enabled_models(self, tmp_path):
        from x_monitor.config import Config
        from x_monitor.dashboard import DashboardApp

        data = tmp_path / "data"
        data.mkdir()
        enabled = ["minimax", "qwen", "deepseek"]
        app = DashboardApp(
            Config(enabled_models=enabled, daily_ceiling=333),
            data, db_path=data / "x.db",
        )
        client = app.app.test_client()
        r = client.get("/api/treemap.json")
        body = r.get_json()
        # Tiles are sorted by (-area_weight, display_name) per R13. With no
        # data, the secondary sort is display_name asc — so we just check
        # the set of model_ids is the set of enabled models, not order.
        assert len(body["tiles"]) == len(enabled)
        got = {t["model_id"] for t in body["tiles"]}
        assert got == set(enabled)

    def test_treemap_validates_enabled_models_at_startup(self, tmp_path):
        # An unknown model id in enabled_models should fail at construction
        # time, not silently render a fallback accent at request time.
        from x_monitor.config import Config
        from x_monitor.dashboard import DashboardApp

        data = tmp_path / "data"
        data.mkdir()
        # Tighten from bare Exception so a regression (e.g. accidental
        # KeyError from a typo in _validate_dashboard_config) actually fails.
        with pytest.raises((ValidationError, ValueError)):
            DashboardApp(
                Config(enabled_models=["not_a_real_model"], daily_ceiling=333),
                data, db_path=data / "x.db",
            )

    def test_treemap_tiles_sort_by_area_then_name(self, tmp_path):
        from datetime import datetime, timedelta, timezone
        from x_monitor.config import Config
        from x_monitor.dashboard import DashboardApp
        from x_monitor.store import Store

        data = tmp_path / "data"
        data.mkdir()
        runs_dir = data / "runs"
        runs_dir.mkdir()
        # Anchor "now" to a known timestamp so the posts fall in the
        # current 7-day window.
        anchor = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
        run_file = runs_dir / "2026-06-17T12-00-00.json"
        run_file.write_text(
            f'{{"finished_at": "{anchor.isoformat()}"}}',
            encoding="utf-8",
        )
        (runs_dir / "LATEST.json").symlink_to(run_file)
        db_path = data / "x.db"
        store = Store(db_path)
        # Q1+Q4 counts per model: minimax=10, qwen=5, deepseek=5
        counts = {"minimax": 10, "qwen": 5, "deepseek": 5}
        all_posts = []
        for m, n in counts.items():
            for i in range(n):
                qid = "Q1" if i % 2 == 0 else "Q4"
                all_posts.append(
                    {
                        "tweet_id": f"t_{m}_{i}",
                        "model_id": m,
                        "author_handle": f"u_{i}",
                        "text": "x",
                        "favorite_count": 0,
                        "created_at": (anchor - timedelta(hours=i + 1))
                        .strftime("%a %b %d %H:%M:%S %z %Y"),
                        "source_query_id": qid,
                    }
                )
        store.insert_posts(all_posts)
        store.close()
        app = DashboardApp(
            Config(
                enabled_models=["minimax", "qwen", "deepseek"],
                daily_ceiling=333,
            ),
            data, db_path=db_path,
        )
        client = app.app.test_client()
        r = client.get("/api/treemap.json")
        tiles = r.get_json()["tiles"]
        # minimax first (highest area), then qwen + deepseek tied on area
        assert tiles[0]["model_id"] == "minimax"
        # qwen and deepseek are tied on area=5; sort falls back to
        # display_name asc per R13. Make the intent explicit (don't
        # rely on a coincidental alphabetical match).
        assert tiles[1]["display_name"] == "DeepSeek"
        assert tiles[2]["display_name"] == "Qwen"

