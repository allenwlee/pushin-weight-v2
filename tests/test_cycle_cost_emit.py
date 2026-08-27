"""Tests for scripts.harvest_cost.emit (plan 2026-08-10-003 U3)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from monitor.harvest_summary import (
    HARVEST_COHORT_PREFIX,
    HARVEST_SUMMARY_PREFIX,
    parse_cohort_line,
    parse_summary_line,
)
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


def test_finalize_logs_one_canonical_redacted_envelope(tmp_path: Path, caplog):
    summary = {
        "run_id": "emit-1",
        "status": "completed",
        "calls": [{"call_id": "A", "n_results": 1}],
        "totals": {"n_results": 1, "n_calls_run": 1},
    }
    with caplog.at_level("INFO"):
        path = finalize_and_persist(summary, runs_dir=tmp_path)

    assert path is not None
    lines = [record.message for record in caplog.records if HARVEST_SUMMARY_PREFIX in record.message]
    assert len(lines) == 1
    assert lines[0].startswith(HARVEST_SUMMARY_PREFIX)


def test_finalize_logs_one_correlated_cohort_for_nonempty_cycle(tmp_path, caplog):
    summary = {
        "run_id": "emit-cohort",
        "status": "completed",
        "totals": {"n_results": 1, "n_inserted": 1, "n_calls_run": 1},
        "post_fetch": {
            "n_enrichment_claimed": 1,
            "n_enrichment_claimed_current_cycle": 1,
            "n_enrichment_claimed_carryover": 0,
            "n_enrichment_succeeded": 1,
            "n_enrichment_succeeded_current_cycle": 1,
            "n_enrichment_succeeded_carryover": 0,
            "n_enrichment_pending": 0,
            "n_enrichment_pending_current_cycle": 0,
            "n_enrichment_pending_carryover": 0,
            "n_enrichment_failed": 0,
            "n_enrichment_failed_current_cycle": 0,
            "n_enrichment_failed_carryover": 0,
            "inserted_post_ids": ["100"],
            "enrichment_current_cycle_post_ids": ["100"],
            "enrichment_carryover_post_ids": [],
            "enrichment_state_facts": [
                {
                    "post_id": "100",
                    "lane": "current_cycle",
                    "translation_status": "succeeded",
                    "classification_status": "succeeded",
                    "output_complete": True,
                }
            ],
        },
    }
    with caplog.at_level("INFO"):
        finalize_and_persist(summary, runs_dir=tmp_path)

    summary_lines = [
        record.message
        for record in caplog.records
        if record.message.startswith(HARVEST_SUMMARY_PREFIX)
    ]
    cohort_lines = [
        record.message
        for record in caplog.records
        if record.message.startswith(HARVEST_COHORT_PREFIX)
    ]
    assert len(summary_lines) == 1
    assert len(cohort_lines) == 1
    envelope = parse_summary_line(summary_lines[0])
    receipt = parse_cohort_line(cohort_lines[0], summary_envelope=envelope)
    assert receipt["summary_hash"] == envelope["hash"]


def test_finalize_does_not_log_cohort_for_zero_insert_cycle(tmp_path, caplog):
    with caplog.at_level("INFO"):
        finalize_and_persist(
            {"run_id": "emit-empty", "totals": {"n_inserted": 0}},
            runs_dir=tmp_path,
        )

    assert not any(
        record.message.startswith(HARVEST_COHORT_PREFIX)
        for record in caplog.records
    )


def test_persisted_summary_drops_raw_errors_and_query_payloads(tmp_path: Path):
    summary = {
        "run_id": "emit-redacted",
        "status": "degraded",
        "calls": [{
            "call_id": "A",
            "n_results": 1,
            "query_string": "postgresql://user:password@example/db",
            "relevancy_degraded": ["provider body: secret-value"],
        }],
        "errors": ["Authorization: Bearer fake-token"],
        "degraded": {"provider": "postgresql://user:password@example/db"},
        "totals": {"n_results": 1, "n_calls_run": 1},
    }
    path = finalize_and_persist(summary, runs_dir=tmp_path)
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "postgresql://" not in text
    assert "fake-token" not in text
    assert "provider body" not in text


def test_cycle_py_calls_finalize_and_persist():
    """Structural: shipped cycle path wires emit helper."""
    src = Path(__file__).resolve().parent.parent / "monitor" / "cycle.py"
    text = src.read_text(encoding="utf-8")
    assert "finalize_and_persist" in text
    assert "scripts.harvest_cost.emit" in text or "harvest_cost.emit" in text
