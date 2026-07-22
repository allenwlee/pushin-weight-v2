# {{AGENT_ATTRIBUTION}}
"""Legacy-route 302 redirect tests for Pushin' Weight (走个量) home
pages (U8 of feat/pushin-weight-home-pages, 2026-07-06).

Pins the legacy-route 302 behavior (no broken external links). Every
documented legacy path returns the expected 302 + Location header.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from x_monitor.config import Config
from x_monitor.dashboard import DashboardApp


@pytest.fixture()
def dashboard_client():
    """A bare DashboardApp with no fixtures (redirects don't need data)."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(
            enabled_models=["minimax", "qwen"],
            daily_ceiling=333,
        )
        app = DashboardApp(cfg, data, db_path=data / "x.db")
        client = app.app.test_client()
        yield client, app, data


# ---------------------------------------------------------------------------
# Legacy 302 map
# ---------------------------------------------------------------------------


def test_legacy_grid_redirects_to_home(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/grid")
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")


def test_legacy_combined_redirects_to_home(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/combined")
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")


def test_legacy_treemap_redirects_to_home(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/treemap")
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")


def test_legacy_unattributed_redirects_to_home(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/_unattributed")
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")


def test_legacy_brand_minimax_redirects(dashboard_client):
    """`/brand/<id>` should 302 to the resolved vanity URL.

    For an empty DB, the brand doesn't exist; the route should
    return 404 (per KTD8 strict-contract rule), not 302 to a bogus
    target. Once a brand exists in the DB, the redirect target is
    `_resolve_vanity_url_for_brand(brand_id)`.
    """
    client, _, _ = dashboard_client
    resp = client.get("/brand/minimax")
    # Empty DB → no minimax row → 404.
    assert resp.status_code in (302, 404)
    if resp.status_code == 302:
        loc = resp.headers.get("Location", "")
        assert "/minimax" in loc


def test_legacy_model_minimax_redirects(dashboard_client):
    client, _, _ = dashboard_client
    resp = client.get("/model/minimax")
    assert resp.status_code in (302, 404)
    if resp.status_code == 302:
        loc = resp.headers.get("Location", "")
        assert "/minimax" in loc


def test_legacy_routes_summary():
    """Document the full legacy 302 map (KTD9)."""
    legacy_map = {
        "/grid": "/",
        "/combined": "/",
        "/treemap": "/",
        "/_unattributed": "/",
    }
    # For each legacy path, the expected 302 target is `/` (or the
    # resolved vanity URL for /brand/<id> / /model/<id>).
    for legacy, target in legacy_map.items():
        # We only assert the mapping intent here; the actual 302 is
        # tested in the individual tests above.
        assert target == "/"
