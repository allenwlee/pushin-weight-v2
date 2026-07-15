"""Tests for the classify_batch_pragmatics_full limits probe.

Plan: docs/plans/2026-07-15-001-feat-classify-batch-limits-probe-plan.md

These tests cover U1 (scaffolding + synthetic-tweet builder + status
classifier + timeout + dry-run + missing-credential guard). U2 sweep
tests and U3 JSON-output tests live further down in this file.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROBE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROBE_DIR.parents[3]  # scripts/probes/<name>/test_probe.py -> repo root
PROBE_MODULE = "scripts.probes.classify_batch_limits.probe"


def _import_probe():
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.probes.classify_batch_limits import probe
    return probe


# --- U1 tests (8) ---------------------------------------------------------


def test_build_synthetic_tweets_default_size():
    probe = _import_probe()
    tweets = probe._build_synthetic_tweets(n=10, brand_ids=["minimax", "qwen"], rng_seed=1)
    assert len(tweets) == 10
    for t in tweets:
        assert "tweet_id" in t and "text" in t and "brand_ids" in t
        assert 1 <= len(t["brand_ids"]) <= 3


def test_build_synthetic_tweets_text_length():
    probe = _import_probe()
    tweets = probe._build_synthetic_tweets(n=1, brand_ids=["minimax"], text_len=2000, rng_seed=2)
    assert len(tweets[0]["text"]) == 2000


def test_classify_status_unterminated_string():
    probe = _import_probe()
    exc = ValueError('Unterminated string starting at: line 1 column 3831 (char 3831)')
    assert probe._classify_status(exc) == "unterminated_json"


def test_classify_status_ssl_hang_pattern():
    probe = _import_probe()
    # Build an exception whose repr contains the SDK read symbol.
    try:
        raise RuntimeError("_ssl__SSLSocket_read: read stalled")
    except RuntimeError as e:
        assert probe._classify_status(e) == "ssl_hang"


def test_classify_status_429_rate_limit():
    probe = _import_probe()
    exc = RuntimeError("anthropic.APIStatusError: 429 rate_limit_exceeded")
    assert probe._classify_status(exc) == "rate_limited"


def test_classify_status_success_when_no_exc():
    probe = _import_probe()
    assert probe._classify_status(None, response={"results": []}) == "success"


def test_print_table_emits_header_and_rows(capsys):
    probe = _import_probe()
    probe._print_table(["k", "v"], [["1", "ok"], ["2", "ok"]])
    out = capsys.readouterr().out
    assert "k" in out and "v" in out
    assert "1" in out and "2" in out
    # separator line present
    assert "-+-" in out


def test_verdict_line_names_smallest_failing_value():
    probe = _import_probe()
    rows = [
        {"value": "1", "status": "success"},
        {"value": "5", "status": "success"},
        {"value": "10", "status": "ssl_hang"},
    ]
    assert probe._verdict_line("batch_size", rows) == "limit hit: batch_size=10 -> ssl_hang"
    assert probe._verdict_line("batch_size", [{"value": "1", "status": "success"}]) is None
    # dry_run rows are NOT failures — verdict suppressed
    assert probe._verdict_line(
        "batch_size",
        [{"value": "1", "status": "dry_run"}, {"value": "5", "status": "dry_run"}],
    ) is None


# --- U2 tests (7 sweep tests) ---------------------------------------------


def test_sweep_batch_size_emits_nine_rows_in_dry_run():
    probe = _import_probe()
    rows = probe.sweep_batch_size(
        client=None, base_batch_size=20, timeout=1.0,
        brand_ids=["minimax"], dry_run=True,
    )
    assert len(rows) == len(probe.BATCH_SIZE_VALUES)
    assert [r["value"] for r in rows] == [str(v) for v in probe.BATCH_SIZE_VALUES]
    assert all(r["status"] == "dry_run" for r in rows)


def test_sweep_max_tokens_uses_production_batch_size_in_dry_run():
    probe = _import_probe()
    rows = probe.sweep_max_tokens(
        client=None, base_batch_size=20, timeout=1.0,
        brand_ids=["minimax"], dry_run=True,
    )
    assert len(rows) == len(probe.MAX_TOKENS_VALUES)
    assert [r["value"] for r in rows] == [str(v) for v in probe.MAX_TOKENS_VALUES]


def test_sweep_input_tokens_text_length_varies_in_dry_run():
    probe = _import_probe()
    rows = probe.sweep_input_tokens(
        client=None, base_batch_size=20, timeout=1.0,
        brand_ids=["minimax"], dry_run=True,
    )
    assert len(rows) == len(probe.INPUT_TOKEN_VALUES)
    # input_tokens should scale with the configured text length
    token_counts = [r["input_tokens"] for r in rows]
    assert all(t2 > t1 for t1, t2 in zip(token_counts, token_counts[1:]))


def test_sweep_cache_state_fires_three_calls_in_dry_run():
    probe = _import_probe()
    rows = probe.sweep_cache_state(
        client=None, base_batch_size=20, timeout=1.0,
        brand_ids=["minimax"], dry_run=True,
    )
    assert len(rows) == 3
    assert [r["value"] for r in rows] == ["call_1", "call_2", "call_3"]


def test_sweep_rpm_dry_run_rows_carry_target_rpm():
    probe = _import_probe()
    rows = probe.sweep_rpm(
        client=None, base_batch_size=20, timeout=1.0,
        brand_ids=["minimax"], dry_run=True,
    )
    assert [r["value"] for r in rows] == [str(v) for v in probe.RPM_VALUES]
    assert all(r["status"] == "dry_run" for r in rows)


def test_sweep_concurrency_dry_run_rows_carry_max_workers():
    probe = _import_probe()
    rows = probe.sweep_concurrency(
        client=None, base_batch_size=20, timeout=1.0,
        brand_ids=["minimax"], dry_run=True,
    )
    assert [r["value"] for r in rows] == [str(v) for v in probe.CONCURRENCY_VALUES]
    assert all(r["status"] == "dry_run" for r in rows)


def test_fake_client_in_flight_counter_tracks_concurrency():
    """Pin the FakeClaudeClient's in-flight tracking so the A6 sweep
    can read in_flight_max and verify the thread-pool actually ran
    N calls in parallel."""
    probe = _import_probe()
    # Reset class-level counters
    probe._FakeClient.in_flight = 0  # type: ignore[attr-defined]
    probe._FakeClient.in_flight_max = 0  # type: ignore[attr-defined]

    # The fake's in_flight_max is incremented per call; a sequential
    # invocation should report in_flight_max == 1.
    fc = probe._FakeClient()
    fc.messages_create(model="x", max_tokens=10, messages=[])
    fc.messages_create(model="x", max_tokens=10, messages=[])
    assert fc.in_flight_max == 1


# --- U3 tests (4) ---------------------------------------------------------


def test_axes_subset_parser_rejects_unknown_axis():
    probe = _import_probe()
    with pytest.raises(SystemExit):
        probe._parse_axes("batch_size,bogus_axis")


def test_axes_subset_parser_accepts_valid_subset():
    probe = _import_probe()
    assert probe._parse_axes("batch_size,max_tokens") == ["batch_size", "max_tokens"]
    assert probe._parse_axes("concurrency") == ["concurrency"]


def test_dry_run_emits_valid_json(tmp_path, monkeypatch):
    """The probe writes data/runs/probe_<utc>.json in dry-run mode."""
    import re as _re
    probe = _import_probe()
    monkeypatch.chdir(tmp_path)
    rc = probe.main(["--dry-run", "--axes=batch_size"])
    assert rc == 0
    runs = list((tmp_path / "data" / "runs").glob("probe_*.json"))
    assert len(runs) == 1
    payload = json.loads(runs[0].read_text())
    assert payload["axes_run"] == ["batch_size"]
    assert payload["verdict"] is None  # all dry_run → suppressed
    assert "batch_size" in payload["rows"]
    assert _re.match(r"probe_\d{8}T\d{6}Z\.json", runs[0].name)


def test_missing_api_key_exits_with_clear_message(tmp_path, monkeypatch, capsys):
    """With no ANTHROPIC_API_KEY and no --dry-run, the probe exits 2."""
    probe = _import_probe()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        probe.main(["--axes=batch_size"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err


def test_fire_one_batch_surfaces_on_batch_error(monkeypatch):
    """When the batched LLM call fails but per-post fallback returns
    a valid list, _fire_one_batch must classify as `unterminated_json`
    (or similar), not `success`. Regression test for the live
    batch_size sweep that masked real failures.

    Strategy: monkeypatch classify_batch_pragmatics_full so it fires
    on_batch_error with an Unterminated-string exception, then returns
    a valid list (the per-post fallback shape)."""
    probe = _import_probe()

    fake_exc = ValueError(
        'Unterminated string starting at: line 1 column 3345 (char 3344)'
    )
    fake_response = [{"by_brand": {}, "unsanctioned_flags": []}]

    def _fake_classify(tweets, brand_registry, anthropic_client, **kwargs):
        on_err = kwargs.get("on_batch_error")
        if on_err is not None:
            on_err(tweets, fake_exc)
        return fake_response

    # Patch the function imported into probe's namespace.
    import x_monitor.attribution as _attr
    monkeypatch.setattr(_attr, "classify_batch_pragmatics_full", _fake_classify)

    fc = probe._FakeClient()
    result = probe._fire_one_batch(
        tweets=[{"tweet_id": "t1", "text": "x", "brand_ids": ["minimax"]}],
        max_tokens=1024, timeout=5.0, client=fc,
    )
    assert result["status"] == "unterminated_json"
    assert result["batch_error"] is fake_exc
    assert result["exc"] is fake_exc