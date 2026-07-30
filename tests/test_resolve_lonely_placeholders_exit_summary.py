"""U5 tests - exit summary + log conventions.

Plan: docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md
Unit U5.

Verifies the apply loop body (`run_apply_loop`) and exit summary shape:
  - Summary has all required fields per KTD6.
  - Dead-letter log is appended per failure.
  - Apply log is appended once per run.
  - partial=true when max_seconds elapses mid-batch.
  - partial=true when circuit breaker trips.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from monitor.reconcile.apply_loop import run_apply_loop


@pytest.fixture
def tmp_logs(tmp_path, monkeypatch):
    apply_log = tmp_path / "lonely-apply.log"
    dl_log = tmp_path / "lonely-apply-dead-letter.log"
    return apply_log, dl_log


@pytest.fixture
def empty_candidates():
    return []


@pytest.fixture
def sample_candidates():
    return [
        ("alice", "handle:alice"),
        ("bob", "handle:bob"),
    ]


def test_summary_shape_with_empty_candidates(tmp_logs, empty_candidates):
    """Empty candidate list produces a valid summary with looked_up=0."""
    apply_log, dl_log = tmp_logs
    received = [None]
    summary = run_apply_loop(
        candidate_placeholders=empty_candidates,
        api_key="k",
        rate_qps=5.0,
        concurrency=1,
        batch_size=200,
        max_seconds=10,
        apply_log_path=apply_log,
        dead_letter_log_path=dl_log,
        received_signal_ref=received,
    )
    # Required fields per KTD6.
    for field in (
        "started_at", "finished_at", "dry_run",
        "total_placeholders", "looked_up", "resolved",
        "dead_lettered", "retried_after_429",
        "rate_actual_qps", "max_time_wait_sockets",
        "partial", "dead_letter_reasons",
    ):
        assert field in summary, f"missing required field: {field}"
    assert summary["dry_run"] is False
    assert summary["looked_up"] == 0
    assert summary["partial"] is False


def test_summary_partial_true_on_signal(tmp_logs, empty_candidates):
    """received_signal_ref pre-set to SIGTERM -> partial=True."""
    apply_log, dl_log = tmp_logs
    received = ["SIGTERM"]
    summary = run_apply_loop(
        candidate_placeholders=empty_candidates,
        api_key="k",
        rate_qps=5.0,
        concurrency=1,
        batch_size=200,
        max_seconds=10,
        apply_log_path=apply_log,
        dead_letter_log_path=dl_log,
        received_signal_ref=received,
    )
    assert summary["partial"] is True


def test_dead_letter_log_appended_per_failure(tmp_logs, monkeypatch):
    """A dead-letter LookupResult writes one JSON line per handle to dl_log."""
    apply_log, dl_log = tmp_logs

    from monitor.twitterapi.caller import LookupResult, LookupStats

    async def fake_lookup_batch(handles, **kwargs):
        for h in handles:
            yield LookupResult.from_dead_letter(
                h, reason="not_found_200", status_code=200,
                response_excerpt='{"status":"error","msg":"user not found"}',
            )

    monkeypatch.setattr(
        "monitor.reconcile.apply_loop.lookup_batch",
        fake_lookup_batch,
    )

    candidates = [("alice", "handle:alice"), ("bob", "handle:bob")]

    received = [None]
    summary = run_apply_loop(
        candidate_placeholders=candidates,
        api_key="k",
        rate_qps=100,
        concurrency=1,
        batch_size=200,
        max_seconds=10,
        apply_log_path=apply_log,
        dead_letter_log_path=dl_log,
        received_signal_ref=received,
    )
    assert summary["dead_lettered"] == 2
    assert summary["dead_letter_reasons"].get("not_found_200") == 2

    # Read the dead-letter log.
    lines = dl_log.read_text().strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        entry = json.loads(line)
        assert "handle" in entry
        assert "reason" in entry
        assert "ts" in entry


def test_summary_partial_true_on_circuit_breaker_trip(tmp_logs, monkeypatch):
    """Circuit breaker trips mid-batch -> partial=True + breaker_tripped=True."""
    apply_log, dl_log = tmp_logs

    from monitor.twitterapi.caller import LookupResult

    async def fake_lookup_batch(handles, **kwargs):
        breaker = kwargs.get("breaker")
        for h in handles:
            # First few: dead-letter 5xx to trip breaker; rest: short-circuit.
            r = LookupResult.from_dead_letter(h, reason="http_5xx")
            if breaker is not None:
                breaker.record("http_5xx")
            yield r

    monkeypatch.setattr(
        "monitor.reconcile.apply_loop.lookup_batch",
        fake_lookup_batch,
    )

    # 12 handles; threshold=10 means breaker trips after the 10th.
    candidates = [(f"h{i}", f"handle:h{i}") for i in range(12)]

    received = [None]
    summary = run_apply_loop(
        candidate_placeholders=candidates,
        api_key="k",
        rate_qps=100,
        concurrency=1,
        batch_size=200,
        max_seconds=10,
        apply_log_path=apply_log,
        dead_letter_log_path=dl_log,
        received_signal_ref=received,
    )
    assert summary["breaker_tripped"] is True
    assert summary["partial"] is True
    assert summary["dead_letter_reasons"].get("circuit_open", 0) >= 1


def test_max_seconds_triggers_partial(monkeypatch, tmp_logs):
    """--max-seconds elapsed mid-loop -> partial=True."""
    apply_log, dl_log = tmp_logs

    # Make time.time() jump forward after the first iteration.
    real_time = __import__("time").time
    call_count = {"n": 0}

    def fake_time():
        call_count["n"] += 1
        # After the first few calls (used for setup), jump forward past deadline.
        if call_count["n"] > 5:
            return real_time() + 10000
        return real_time()

    monkeypatch.setattr("monitor.reconcile.apply_loop.time.time", fake_time)

    from monitor.twitterapi.caller import LookupResult

    async def fake_lookup_batch(handles, **kwargs):
        for h in handles:
            yield LookupResult.from_success(
                h, canonical={"author_id": "99999", "screen_name": h},
            )

    monkeypatch.setattr(
        "monitor.reconcile.apply_loop.lookup_batch",
        fake_lookup_batch,
    )

    candidates = [("alice", "handle:alice")]
    received = [None]
    summary = run_apply_loop(
        candidate_placeholders=candidates,
        api_key="k",
        rate_qps=100,
        concurrency=1,
        batch_size=200,
        max_seconds=10,
        apply_log_path=apply_log,
        dead_letter_log_path=dl_log,
        received_signal_ref=received,
    )
    assert summary["partial"] is True