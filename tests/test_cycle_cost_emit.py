"""Tests for scripts.harvest_cost.emit (plan 2026-08-10-003 U3)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.harvest_cost.emit import (
    attach_http_log,
    finalize_and_persist,
    persist_cycle_summary,
)


def test_persist_cycle_summary_writes_json(tmp_path: Path):
    summary = {
        "run_id": "20260810T063111_0000-test",
        "finished_at": "2026-08-10T06:37:01+00:00",
        "calls": [{"call_id": "B1", "n_results": 63}],
        "metrics_refresh": {"n_due": 200, "n_refreshed": 174},
        "totals": {"n_results": 63, "n_inserted": 50, "n_calls_run": 1},
    }
    path = persist_cycle_summary(summary, runs_dir=tmp_path)
    assert path is not None and path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == summary["run_id"]
    assert data["calls"][0]["n_results"] == 63
    assert data["metrics_refresh"]["n_refreshed"] == 174


def test_persist_failure_returns_none(tmp_path: Path, monkeypatch):
    # Point runs_dir at a file path so mkdir/write fails
    bad = tmp_path / "not_a_dir"
    bad.write_text("x", encoding="utf-8")
    out = persist_cycle_summary({"run_id": "x"}, runs_dir=bad)
    assert out is None


def test_attach_http_log():
    api = SimpleNamespace(_request_log=[{"path": "/twitter/tweets", "n_results": 2}])
    summary: dict = {}
    attach_http_log(summary, api)
    assert summary["http_log"][0]["n_results"] == 2


def test_finalize_and_persist(tmp_path: Path):
    api = SimpleNamespace(_request_log=[{"path": "/x", "n_results": 1}])
    summary = {
        "run_id": "fin-1",
        "calls": [{"call_id": "A", "n_results": 1}],
        "totals": {"n_results": 1, "n_inserted": 1, "n_calls_run": 1},
    }
    path = finalize_and_persist(summary, api, runs_dir=tmp_path)
    assert path is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "http_log" in data
    assert data["http_log"][0]["n_results"] == 1


def test_cycle_py_calls_finalize_and_persist():
    """Structural: shipped cycle path wires emit helper."""
    src = Path(__file__).resolve().parent.parent / "monitor" / "cycle.py"
    text = src.read_text(encoding="utf-8")
    assert "finalize_and_persist" in text
    assert "scripts.harvest_cost.emit" in text or "harvest_cost.emit" in text
