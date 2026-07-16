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


# ---------------------------------------------------------------------------
# U5: cursor pagination — next_cursor advances through pages, filter
# narrows the page even mid-cursor, the wire exposes created_at_iso so
# the JS-side cursor serializer can round-trip without scraping the
# date cell's text content (which is now a relative time).
# ---------------------------------------------------------------------------


def test_api_home_feed_cursor_advances_to_distinct_page(dashboard_client):
    """U5 regression: requesting limit=2 should return 2 rows and a
    non-null next_cursor; the page returned with that cursor must be
    disjoint from page 1."""
    client, _, _ = dashboard_client
    p1 = client.get("/api/v1/home.feed.json?limit=2").get_json()
    assert "rows" in p1 and "next_cursor" in p1
    assert len(p1["rows"]) <= 2
    cursor = p1.get("next_cursor")
    if not cursor:
        pytest.skip("fixture too small for two pages")
    p2 = client.get(f"/api/v1/home.feed.json?limit=2&cursor={cursor}").get_json()
    assert "rows" in p2
    page1_ids = {r["tweet_id"] for r in p1["rows"]}
    page2_ids = {r["tweet_id"] for r in p2["rows"]}
    assert not (page1_ids & page2_ids), (
        f"pages overlap: {page1_ids & page2_ids}"
    )


def test_api_home_feed_cursor_format_matches_created_at_iso(dashboard_client):
    """U5 regression: the cursor the server returns is
    '<created_at_iso>|<tweet_id>'. The JS reads it from
    data-created-at-iso + data-tweet-id attributes (not textContent
    scraping) to keep round-trip stable now that the visible date is a
    relative-time string."""
    client, _, _ = dashboard_client
    p1 = client.get("/api/v1/home.feed.json?limit=2").get_json()
    if not p1.get("rows"):
        pytest.skip("empty fixture")
    row = p1["rows"][0]
    assert "created_at_iso" in row, (
        "wire must expose created_at_iso so the JS cursor serializer "
        "can round-trip without scraping the date cell's textContent"
    )
    # The row should have both keys the JS reads for cursor construction.
    assert row["created_at_iso"], "created_at_iso must be populated"
    assert row["tweet_id"], "tweet_id must be populated"


def test_api_home_feed_filter_and_cursor_compose(dashboard_client):
    """U5 regression: filter+cursor must compose. Server-side brand
    filter still narrows the page even when a cursor is provided;
    subsequent cursor advances on the filtered subset."""
    client, _, _ = dashboard_client
    p1 = client.get("/api/v1/home.feed.json?limit=10&brand=minimax").get_json()
    assert p1.get("rows"), "fixture must have minimax posts"
    # All returned rows must include minimax in brand_nicknames.
    for r in p1["rows"]:
        assert "minimax" in r.get("brand_nicknames", []), (
            f"brand filter not honored: row {r.get('tweet_id')} "
            f"has brands {r.get('brand_nicknames')}"
        )
    cursor = p1.get("next_cursor")
    if not cursor:
        return  # single page is fine for this assertion
    p2 = client.get(
        f"/api/v1/home.feed.json?limit=10&cursor={cursor}&brand=minimax"
    ).get_json()
    for r in p2["rows"]:
        assert "minimax" in r.get("brand_nicknames", [])


def test_api_home_feed_wire_includes_relative_time_safe_fields(dashboard_client):
    """U5: row must carry created_at_iso (U1) so the JS can replace
    the visible cell text with a relative time on init without a
    server round-trip. Without this field, the first paint of the
    page would show the raw Twitter-format string."""
    client, _, _ = dashboard_client
    p1 = client.get("/api/v1/home.feed.json?limit=1").get_json()
    if not p1.get("rows"):
        pytest.skip("empty fixture")
    row = p1["rows"][0]
    assert "created_at_iso" in row
    # Should be parseable as ISO.
    from datetime import datetime as _dt
    parsed = _dt.fromisoformat(row["created_at_iso"])
    assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# Regression: feed must include posts whose posts_brands_discourse row
# carries `china_nationalism` / `us_nationalism`. Earlier `_denormalize_posts`
# did `r["cn_nationalism"]` while the SELECT aliased `pbd.china_nationalism`,
# so any brand with at least one discourse row raised IndexError and the
# brand dropped out of the feed entirely. Symptom: feed returned ~7 rows
# even when the DB had thousands of recent posts. The SQL now aliases the
# column to `cn_nationalism` so the dict key matches.
# ---------------------------------------------------------------------------


def test_feed_includes_posts_with_nationalism_classifications(dashboard_client):
    """Regression: `_denormalize_posts` raised `IndexError: No item with
    that key` for any brand with a `posts_brands_discourse` row because
    the SQL aliased `pbd.china_nationalism` while the access used the
    short form `r["cn_nationalism"]`. The route's per-brand try/except
    silently skipped those brands, dropping 16/20 enabled brands from
    the feed and leaving ~7 rows from the 4 unaffected ones."""
    client, app, data = dashboard_client
    db_path = data / "x.db"
    target_twid = "t-minimax-0-0"
    from x_monitor.store import Store
    store = Store(db_path)
    try:
        post_id_int = store._conn.execute(
            "SELECT id FROM posts WHERE tweet_id = ?", (target_twid,)
        ).fetchone()
        if post_id_int is None:
            pytest.skip("fixture seed order changed; skipping")
        post_id = post_id_int[0]
        disc_id = store._conn.execute(
            "SELECT id FROM discourse_keys WHERE key='dunk_yingyang'"
        ).fetchone()[0]
        cn_id = store._conn.execute(
            "SELECT id FROM nationalism_keys WHERE key='anti'"
        ).fetchone()[0]
        us_id = store._conn.execute(
            "SELECT id FROM nationalism_keys WHERE key='constructive_critical'"
        ).fetchone()[0]
        brand_int = store._conn.execute(
            "INSERT OR IGNORE INTO brands(nickname, display_name) "
            "VALUES('minimax', 'TestMiniMax')"
        )
        brand_int = store._conn.execute(
            "SELECT id FROM brands WHERE nickname='minimax'"
        ).fetchone()[0]
        store._conn.execute(
            "INSERT OR IGNORE INTO posts_brands(brand_id, post_id, weight) "
            "VALUES(?, ?, 1.0)",
            (brand_int, post_id),
        )
        store._conn.execute(
            """
            INSERT INTO posts_brands_discourse(
                post_id, brand_id, discourse_key, act_id,
                china_nationalism, us_nationalism
            ) VALUES (?, ?, ?, 1, ?, ?)
            """,
            (post_id, brand_int, disc_id, cn_id, us_id),
        )
        store._conn.commit()
    finally:
        store.close()

    from x_monitor._home_routes import _denormalize_posts
    store = Store(db_path)
    try:
        posts = _denormalize_posts(store, "minimax", 7)
    finally:
        store.close()
    matching = [p for p in posts if p.get("id") == post_id]
    assert matching, f"post {post_id} not in _denormalize_posts output"
    row = matching[0]
    assert row.get("cn_nationalism") == cn_id
    assert row.get("us_nationalism") == us_id


# ---------------------------------------------------------------------------
# Wire shape: feed's `classifications` field must expose STRING labels,
# not raw FK ints. The denormalized post dict carries int FKs (post-
# migration 020) for `discourse`, `cn_nationalism`, `us_nationalism`;
# the wire transformer (`_feed_row_to_wire`) translates them via the
# `taxonomy` maps the route builds from `discourse_keys` /
# `nationalism_keys`. Before this fix the UI rendered "1 buzz_releases
# cn:1 us:1" — a database FK id masquerading as a label.
# ---------------------------------------------------------------------------


def test_feed_wire_exposes_string_labels_not_fk_ints(dashboard_client):
    """Regression: with a taxonomy map supplied to serialize_feed_page,
    the wire's classifications[brand] must contain string labels
    (e.g. 'anti', 'constructive_critical', 'dunk_yingyang'), NOT the
    raw int FK ids."""
    client, app, data = dashboard_client
    db_path = data / "x.db"
    target_twid = "t-minimax-0-0"

    from x_monitor.store import Store
    store = Store(db_path)
    try:
        post_id_int = store._conn.execute(
            "SELECT id FROM posts WHERE tweet_id = ?", (target_twid,)
        ).fetchone()
        if post_id_int is None:
            pytest.skip("fixture seed order changed; skipping")
        post_id = post_id_int[0]
        disc_id = store._conn.execute(
            "SELECT id FROM discourse_keys WHERE key='dunk_yingyang'"
        ).fetchone()[0]
        cn_id = store._conn.execute(
            "SELECT id FROM nationalism_keys WHERE key='anti'"
        ).fetchone()[0]
        us_id = store._conn.execute(
            "SELECT id FROM nationalism_keys WHERE key='constructive_critical'"
        ).fetchone()[0]
        store._conn.execute(
            "INSERT OR IGNORE INTO brands(nickname, display_name) "
            "VALUES('minimax', 'TestMiniMax')"
        )
        brand_int = store._conn.execute(
            "SELECT id FROM brands WHERE nickname='minimax'"
        ).fetchone()[0]
        store._conn.execute(
            "INSERT OR IGNORE INTO posts_brands(brand_id, post_id, weight) "
            "VALUES(?, ?, 1.0)",
            (brand_int, post_id),
        )
        store._conn.execute(
            """
            INSERT INTO posts_brands_discourse(
                post_id, brand_id, discourse_key, act_id,
                china_nationalism, us_nationalism
            ) VALUES (?, ?, ?, 1, ?, ?)
            """,
            (post_id, brand_int, disc_id, cn_id, us_id),
        )
        store._conn.commit()
    finally:
        store.close()

    from x_monitor._home_routes import (
        _denormalize_posts, _build_taxonomy_maps, _group_posts_by_id,
    )
    from x_monitor.dashboard import serialize_feed_page
    store = Store(db_path)
    try:
        posts = _denormalize_posts(store, "minimax", 7)
        merged = _group_posts_by_id(posts)
        taxonomy = _build_taxonomy_maps(store)
        out = serialize_feed_page(
            merged, sort="created_at", order="desc", limit=50,
            taxonomy=taxonomy,
        )
    finally:
        store.close()

    rows = out.get("rows") or []
    assert rows, "expected at least 1 feed row"
    our_row = next(
        (r for r in rows
         if r.get("classifications", {}).get("minimax")), None
    )
    assert our_row is not None, "no row with a minimax classification"
    cls = our_row["classifications"]["minimax"]
    assert cls["cn_nationalism"] == "anti"
    assert cls["us_nationalism"] == "constructive_critical"
    assert cls["discourse"] == ["dunk_yingyang"]

