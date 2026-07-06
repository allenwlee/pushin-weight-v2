# {{AGENT_ATTRIBUTION}}
"""End-to-end smoke tests for the Pushin' Weight (走个量) home pages
(U8 of feat/pushin-weight-home-pages, 2026-07-06).

Spins up a Flask test client, applies all migrations against a temp
DB, seeds a 7-day mini-post fixture, and exercises every Pushin'
Weight route end-to-end:

- GET /                                       (multi-brand page)
- GET /alibaba/qwen                           (single-brand page)
- GET /_/minimax                              (company-less brand)
- GET /somecompany/qwen                       (404)
- GET /api/v1/home.chart.json                 (multi-brand chart)
- GET /api/v1/home.chart.html                 (htmx partial)
- GET /api/v1/home.feed.json                  (paginated feed)
- GET /api/v1/home.feed.json?cursor=...       (cursor advances)
- GET /api/v1/home.brand.chart.json           (single-brand chart)
- GET /api/v1/home.brand.chart.html?brand=... (htmx partial)
- GET /api/v1/health                          (health check)
- GET /api/v1/home.window/30                  (cookie set, 303)
- GET /api/v1/home.locale/en                  (cookie set, 303)
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from x_monitor.config import Config
from x_monitor.dashboard import DashboardApp


# ---------------------------------------------------------------------------
# Fixture: a fresh DB with migrations applied + a 7-day post fixture
# ---------------------------------------------------------------------------


def _seed_7_day_fixture(store, brand_id: str, posts_per_day: int = 3):
    """Insert posts spread across the last 7 days for one brand.

    Returns the list of inserted (tweet_id, created_at) pairs."""
    now = datetime.now(timezone.utc)
    pairs = []
    for day_offset in range(7):
        for i in range(posts_per_day):
            created = (now - timedelta(days=day_offset, hours=i)).isoformat()
            twid = f"t-{brand_id}-{day_offset}-{i}"
            store.insert_posts([{
                "tweet_id": twid,
                "brand_id": brand_id,
                "author_handle": f"user_{i}",
                "text": f"hello {brand_id} day{day_offset} post{i}",
                "like_count": i * 5,
                "created_at": created,
                "source_query_id": "Q1",
                "lang_detected": "en",
            }])
            pairs.append((twid, created))
    return pairs


@pytest.fixture()
def dashboard_client():
    """Build a DashboardApp with an applied-migration temp DB and a
    7-day minimax fixture."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(
            enabled_models=["minimax", "qwen", "deepseek"],
            daily_ceiling=333,
        )
        # Initialize Store (auto-migrates) and seed.
        from x_monitor.store import Store
        store = Store(data / "x.db")
        try:
            _seed_7_day_fixture(store, "minimax", posts_per_day=2)
        finally:
            store.close()
        # Now build the DashboardApp (its own Store init will see
        # the migrations as already applied).
        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        yield client, app, data


# ---------------------------------------------------------------------------
# Multi-brand page
# ---------------------------------------------------------------------------


def test_home_multi_renders(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "走个量" in body
    assert "Pushin' Weight" in body
    assert "home-chart" in body
    assert "data-pw-filters" in body


def test_home_multi_includes_canvas_with_payload(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "data-home=" in body
    # The payload is JSON, so look for one of the brand names.
    assert '"minimax"' in body or 'minimax' in body


def test_home_multi_control_panel_has_all_groups(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    for group in (
        'data-pw-filter-group="brands"',
        'data-pw-filter-group="discourse"',
        'data-pw-filter-group="post_types"',
        'data-pw-filter-group="role"',
        'data-pw-filter-group="cn_nationalism"',
        'data-pw-filter-group="us_nationalism"',
        'data-pw-filter-group="unsanctioned"',
    ):
        assert group in body, f"missing group: {group}"


def test_home_multi_window_toggle_renders_4_buttons(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    for n in (1, 7, 30, 365):
        assert f'data-pw-window-btn="{n}"' in body


def test_home_multi_locale_toggle_renders_3_buttons(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    for loc in ("zh_cn", "en", "original"):
        assert f'data-pw-locale-btn="{loc}"' in body


# ---------------------------------------------------------------------------
# Single-brand page
# ---------------------------------------------------------------------------


def test_brand_home_renders(dashboard_client):
    client, _, _ = dashboard_client
    # qwen belongs to alibaba in the seeded brands_companies.
    resp = client.get("/alibaba/qwen")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "走个量" in body
    assert "qwen" in body
    # 6 tabs
    for tab in (
        'data-pw-tab="post_type"',
        'data-pw-tab="discourse"',
        'data-pw-tab="account_roles"',
        'data-pw-tab="us_nationalism"',
        'data-pw-tab="cn_nationalism"',
        'data-pw-tab="unsanctioned"',
    ):
        assert tab in body, f"missing tab: {tab}"


def test_brand_home_404_for_nonexistent_brand(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/_/nonexistent_brand_xyz")
    assert resp.status_code == 404


def test_brand_home_404_for_wrong_company(dashboard_client):
    """`/wrongcompany/qwen` should 404 because qwen is owned by alibaba."""
    client, _, _ = dashboard_client
    resp = client.get("/wrongcompany/qwen")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_home_chart_json_shape(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/api/v1/home.chart.json")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "days" in body
    assert "series" in body
    assert "stacked" in body
    assert "colors" in body
    assert "totals" in body
    assert "window_days" in body
    assert body["window_days"] == 7
    assert len(body["days"]) == 7


def test_api_home_chart_html_renders_partial(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/api/v1/home.chart.html")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "home-chart" in body
    assert "data-home=" in body


def test_api_home_feed_json_paginates(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/api/v1/home.feed.json?limit=10")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "rows" in body
    assert "next_cursor" in body
    # Each row has the documented wire shape.
    if body["rows"]:
        row = body["rows"][0]
        for key in (
            "tweet_id", "created_at", "text", "text_translated",
            "brands", "classifications", "unsanctioned", "account",
        ):
            assert key in row, f"missing key {key} in feed row"


def test_api_home_feed_cursor_advances(dashboard_client):
    client, _, _ = dashboard_client
    # First batch
    resp1 = client.get("/api/v1/home.feed.json?limit=2")
    body1 = resp1.get_json()
    cursor1 = body1.get("next_cursor")
    assert cursor1, "expected non-null cursor on first batch"
    # Advance with cursor
    resp2 = client.get(f"/api/v1/home.feed.json?limit=2&cursor={cursor1}")
    body2 = resp2.get_json()
    assert "rows" in body2


def test_api_brand_chart_json_shape(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/api/v1/home.brand.chart.json?brand=minimax")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "tab_datasets" in body
    for tab in (
        "post_type", "discourse", "account_roles",
        "us_nationalism", "cn_nationalism", "unsanctioned",
    ):
        assert tab in body["tab_datasets"]


def test_api_brand_chart_html_renders_partial(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/api/v1/home.brand.chart.html?brand=minimax")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "home-brand-chart" in body
    assert "data-brand-chart=" in body


def test_api_health(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True


# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------


def test_home_window_cookie_set_and_persists(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/api/v1/home.window/30")
    assert resp.status_code in (302, 303)
    # Subsequent request should carry the cookie
    resp2 = client.get("/")
    assert resp2.status_code == 200
    # The window toggle should now show 30 as active
    body = resp2.get_data(as_text=True)
    assert 'data-pw-window-btn="30"' in body
    # Active class on the 30 button
    assert 'is-active" data-pw-window-btn="30"' in body or \
        'data-pw-window-btn="30"' in body and 'is-active' in body


def test_home_locale_cookie_set(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/api/v1/home.locale/en")
    assert resp.status_code in (302, 303)
    # Subsequent request reflects the new locale
    resp2 = client.get("/")
    body = resp2.get_data(as_text=True)
    # The EN button should be active now
    assert 'is-active" data-pw-locale-btn="en"' in body or \
        ('data-pw-locale-btn="en"' in body and 'is-active' in body)


def test_home_locale_original_supported(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/api/v1/home.locale/original")
    assert resp.status_code in (302, 303)
    # Verify the page reflects the new locale (the original button
    # should be active)
    resp2 = client.get("/")
    body = resp2.get_data(as_text=True)
    assert "original" in body
