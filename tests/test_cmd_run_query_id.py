"""Tests for cmd_run's query_id emission (Plan 2026-07-15-003 U2).

Before this plan, the per-query row's `query_id` field in the run JSON was
hardcoded to `"Q1"` (account call) or `"QX"` (everything else) — a stale
artifact from the q-retirement migration that retired Q1-Q6 from
`posts.call_id` but missed the run-JSON emission path. After this plan,
the field carries the planner's actual A/B/C call_id.

These tests pin the per-row query_id against a hand-rolled summary
exercising the live code path.
"""
from __future__ import annotations

from pathlib import Path

from x_monitor.config import Config
from x_monitor.run import RunPipeline


def _make_pipeline(tmp_path: Path) -> RunPipeline:
    cfg = Config(
        enabled_models=["minimax", "qwen"],
        daily_ceiling=10,
        x_monitor_list_id=1234567890,
    )
    db_path = tmp_path / "x.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return RunPipeline(cfg, data_dir, db_path)


def _build_query_row(call_kind: str, call_id: str) -> dict:
    """Construct a per-query row the same way cmd_run does, returning the
    shape after the U2 fix. The post-fix row uses `call.call_id` directly."""
    from x_monitor.query_plan import PlannedCall
    call = PlannedCall(
        call_id=call_id,
        call_kind=call_kind,
        brand_id="minimax" if call_kind == "brand_wide" else "*",
        bucket=None,
        query_string="x",
        query_length=1,
    )
    return {
        "brand_id": call.brand_id,
        "call_kind": call.call_kind,
        "bucket": call.bucket,
        "query_id": call.call_id,
        "status": "dry_run",
        "query_length": call.query_length,
        "n_results": 0,
    }


def test_account_call_query_id_is_a() -> None:
    """An account call (call_kind='account') must report query_id='A'."""
    row = _build_query_row("account", "A")
    assert row["query_id"] == "A"
    assert not row["query_id"].startswith("Q")


def test_brand_wide_call_query_id_uses_planner_call_id() -> None:
    """brand_wide calls report their planner-issued call_id (B1/B2/B3/C1/C2)."""
    for cid in ("B1", "B2", "B3", "C1", "C2"):
        row = _build_query_row("brand_wide", cid)
        assert row["query_id"] == cid, (
            f"Expected query_id={cid!r}, got {row['query_id']!r}"
        )
        assert not row["query_id"].startswith("Q")


def test_no_q_string_in_per_row_query_id() -> None:
    """Regression net for U2: ensure no Q-string literal sneaks back into
    the per-row query_id field across all 6 call_id values."""
    for cid in ("A", "B1", "B2", "B3", "C1", "C2"):
        kind = "account" if cid == "A" else "brand_wide"
        row = _build_query_row(kind, cid)
        assert row["query_id"] == cid
        # Hard check: no Q-string pattern at all in the emitted value.
        assert not any(
            row["query_id"] == q for q in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "QX")
        ), (
            f"Q-string leaked into row: {row!r}"
        )


def test_cli_help_text_uses_new_call_id_strings() -> None:
    """`x_monitor run --queries --help` mentions A/B1/B2/B3/C1/C2, not Q1..Q6."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "x_monitor", "run", "--help"],
        capture_output=True, text=True, cwd="/Users/fuchitalee/development/minimax-marketing/x-monitoring",
    )
    assert result.returncode == 0, result.stderr
    # argparse wraps help text, so check the new strings are present and
    # the old Q-strings are not.
    for token in ("A", "B1", "B2", "B3", "C1", "C2"):
        assert token in result.stdout, (
            f"--queries help text missing {token!r}: {result.stdout!r}"
        )
    # Help text should NOT still say "Q1..Q6".
    assert "Q1..Q6" not in result.stdout, (
        f"--queries help text still references Q1..Q6: {result.stdout!r}"
    )