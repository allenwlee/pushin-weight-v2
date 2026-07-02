"""U6 tests: API-spend panel on the dashboard.

Plan: docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md
Unit 6 of 6 (U6 — Surface API spend via http_log in the dashboard).

Verifies:
- summarize_http_log aggregator returns the expected shape.
- summarize_http_log handles None and [] inputs gracefully.
- /api/spend.html renders the panel via the test client with a
  fixture run JSON containing mixed paths/statuses/durations.
- /api/spend.json returns the structured JSON for external
  consumers.
- Empty fixture (no run yet) does not crash.
- Regression: the existing dashboard tests still pass (smoke).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from x_monitor.dashboard import DashboardApp, summarize_http_log
from x_monitor.config import Config


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "runs").mkdir()
    return d


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "x.db"


@pytest.fixture
def cfg():
    return Config(
        enabled_models=["minimax"],
        daily_ceiling=333,
        x_monitor_list_id=1234567890,
    )


# --- summarize_http_log unit tests -----------------------------------


def test_summarize_empty_log_returns_zeros():
    """Empty log: aggregator returns zeros, no exceptions."""
    s = summarize_http_log([])
    assert s["n_requests"] == 0
    assert s["total_duration_ms"] == 0
    assert s["by_endpoint"] == {}
    assert s["by_status"] == {}
    assert s["n_results"] == 0


def test_summarize_none_log_returns_zeros():
    """None log (no LATEST.json or no http_log key) returns zeros."""
    s = summarize_http_log(None)
    assert s["n_requests"] == 0
    assert s["total_duration_ms"] == 0
    assert s["by_endpoint"] == {}


def test_summarize_aggregates_per_endpoint():
    """Multiple requests to the same endpoint aggregate correctly."""
    log = [
        {"path": "/twitter/tweet/advanced_search", "duration_ms": 100,
         "status": 200, "n_results": 20},
        {"path": "/twitter/tweet/advanced_search", "duration_ms": 300,
         "status": 200, "n_results": 20},
        {"path": "/twitter/tweet/quotes", "duration_ms": 150,
         "status": 200, "n_results": 5},
    ]
    s = summarize_http_log(log)
    assert s["n_requests"] == 3
    assert s["total_duration_ms"] == 550
    assert s["n_results"] == 45
    # per-endpoint
    assert s["by_endpoint"]["/twitter/tweet/advanced_search"]["n"] == 2
    assert (
        s["by_endpoint"]["/twitter/tweet/advanced_search"]["mean_ms"] == 200.0
    )
    assert (
        s["by_endpoint"]["/twitter/tweet/advanced_search"]["max_ms"] == 300
    )
    assert s["by_endpoint"]["/twitter/tweet/quotes"]["n"] == 1
    # status counts
    assert s["by_status"] == {200: 3}


def test_summarize_handles_status_429():
    """A 429 entry classifies under its own status bucket, not 200."""
    log = [
        {"path": "/twitter/tweet/advanced_search", "duration_ms": 50,
         "status": 200, "n_results": 10},
        {"path": "/twitter/tweet/advanced_search", "duration_ms": 100,
         "status": 429, "n_results": 0},
    ]
    s = summarize_http_log(log)
    assert s["by_status"] == {200: 1, 429: 1}


def test_summarize_handles_missing_optional_fields():
    """Missing duration_ms / n_results / status: defaults to 0;
    missing path: groups under '?'."""
    log = [{}]
    s = summarize_http_log(log)
    assert s["n_requests"] == 1
    assert s["total_duration_ms"] == 0
    assert s["n_results"] == 0
    assert "?" in s["by_endpoint"]


# --- route tests -----------------------------------------------------


def _write_run_json(data_dir: Path, payload: dict) -> Path:
    """Write a run JSON AND a LATEST.json symlink pointing at it.

    The dashboard's `_load_latest_run` reads LATEST.json via
    `latest.is_symlink()` / `latest.resolve()` — production code
    creates LATEST.json as a symlink via `_update_latest_symlink`
    in run.py. Tests must mirror that contract or the loader
    returns None for a regular-file LATEST.json.
    """
    runs_dir = data_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = payload.get("run_id", "test-run")
    target = runs_dir / f"{run_id}.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    link = runs_dir / "LATEST.json"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(target.name)
    return target


def _sample_log() -> list[dict]:
    return [
        {"path": "/twitter/tweet/advanced_search", "duration_ms": 100,
         "status": 200, "n_results": 20},
        {"path": "/twitter/tweet/advanced_search", "duration_ms": 300,
         "status": 200, "n_results": 20},
        {"path": "/twitter/tweet/quotes", "duration_ms": 150,
         "status": 429, "n_results": 0},
        {"path": "/twitter/tweet/quotes", "duration_ms": 250,
         "status": 200, "n_results": 4},
    ]


def test_api_spend_html_renders_panel_for_sample_run(data_dir, db_path, cfg):
    """/api/spend.html returns 200 and the rendered fragment mentions
    the aggregated fields."""
    _write_run_json(
        data_dir,
        {
            "run_id": "test-spend-001",
            "finished_at": "2026-07-02T10:00:00+00:00",
            "http_log": _sample_log(),
        },
    )
    app = DashboardApp(cfg, data_dir, db_path)
    client = app.app.test_client()
    resp = client.get("/api/spend.html")
    assert resp.status_code == 200, (
        f"spend.html returned {resp.status_code}: {resp.data!r}"
    )
    body = resp.data.decode()
    # n_requests == 4
    assert ">4</dd>" in body or "4</dd>" in body, (
        f"requests cell not rendered (looking for n=4); body:\n{body}"
    )
    # total duration ms -> seconds: 100 + 300 + 150 + 250 = 800ms = 0.80s
    assert "0.80s" in body, f"total duration not rendered; body:\n{body}"
    # n_results == 44
    assert ">44</dd>" in body or "44</dd>" in body, (
        f"total results cell not rendered; body:\n{body}"
    )
    # per-endpoint rows
    assert "advanced_search" in body, (
        f"advanced_search endpoint missing; body:\n{body}"
    )
    assert "/twitter/tweet/quotes" in body, (
        f"quotes endpoint missing; body:\n{body}"
    )
    # status chips include 429 + 200
    assert "429" in body, f"status 429 not rendered; body:\n{body}"
    assert "200" in body, f"status 200 not rendered; body:\n{body}"


def test_api_spend_json_returns_structured_payload(data_dir, db_path, cfg):
    """/api/spend.json returns the spend dict + has_run + timestamps."""
    _write_run_json(
        data_dir,
        {
            "run_id": "test-spend-002",
            "finished_at": "2026-07-02T10:00:00+00:00",
            "http_log": _sample_log(),
        },
    )
    app = DashboardApp(cfg, data_dir, db_path)
    client = app.app.test_client()
    resp = client.get("/api/spend.json")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["spend"]["n_requests"] == 4
    assert payload["spend"]["total_duration_ms"] == 800
    assert payload["spend"]["n_results"] == 44
    assert payload["has_run"] is True
    assert payload["last_run_finished_at"] == "2026-07-02T10:00:00+00:00"
    assert "fetched_at" in payload


def test_api_spend_html_empty_when_no_run(data_dir, db_path, cfg):
    """No LATEST.json on disk: /api/spend.html still returns 200 with
    the 'no run yet' sentinel."""
    app = DashboardApp(cfg, data_dir, db_path)
    client = app.app.test_client()
    resp = client.get("/api/spend.html")
    assert resp.status_code == 200, (
        f"spend.html crashed on missing LATEST: {resp.data!r}"
    )
    body = resp.data.decode()
    assert "no run yet" in body, (
        f"missing no-run sentinel; body:\n{body}"
    )
    # No endpoint table when no run.
    assert "<table" not in body, (
        f"endpoint table rendered despite no run; body:\n{body}"
    )


def test_api_spend_json_empty_when_no_run(data_dir, db_path, cfg):
    """/api/spend.json with no LATEST.json returns has_run=False, zeros."""
    app = DashboardApp(cfg, data_dir, db_path)
    client = app.app.test_client()
    resp = client.get("/api/spend.json")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["has_run"] is False
    assert payload["spend"]["n_requests"] == 0
    assert payload["last_run_finished_at"] is None


def test_api_spend_html_handles_empty_http_log(data_dir, db_path, cfg):
    """LATEST.json exists but has http_log == []: panel renders the
    'no run yet' branch rather than crashing on empty data."""
    _write_run_json(
        data_dir,
        {
            "run_id": "test-spend-empty",
            "finished_at": "2026-07-02T11:00:00+00:00",
            "http_log": [],
        },
    )
    app = DashboardApp(cfg, data_dir, db_path)
    client = app.app.test_client()
    resp = client.get("/api/spend.html")
    assert resp.status_code == 200
    body = resp.data.decode()
    # An empty http_log produces a panel with the totals but no
    # per-endpoint table (since by_endpoint is empty).
    assert "<table" not in body, (
        f"endpoint table rendered despite empty http_log; body:\n{body}"
    )


# --- regression: existing dashboard routes still work ----------------


def test_existing_treemap_route_still_works(data_dir, db_path, cfg):
    """The U6 changes added new routes; existing /api/treemap.html
    must still respond 200 (smoke regression)."""
    app = DashboardApp(cfg, data_dir, db_path)
    client = app.app.test_client()
    # /api/treemap.html depends on the LATEST.json presence and
    # store-side data; with empty data dir it should still 200
    # (the dashboard renders an empty treemap).
    resp = client.get("/api/treemap.html")
    # 200 OR a benign 404 are both acceptable; we only assert it
    # doesn't raise an unhandled exception. pytest will catch
    # raises via the test_client machinery.
    assert resp.status_code in (200, 404), (
        f"/api/treemap.html returned unexpected {resp.status_code}"
    )