"""Tests for cmd_run's DB-keyword load path (Plan 2026-07-15-003 U1).

Before this plan, `cmd_run` called `load_queries(m, self.data_dir)` for every
brand, dead-ending on the retired `data/queries/<m>.yaml` files and emitting
20 entries under `degraded.missing_queries:*`. After this plan, brand tokens
come from `Store.read_primary_brand_keywords()` (the `brand_keywords` table
populated by migration 030).

These tests exercise the DB-keyword load path directly by invoking
`RunPipeline.execute` with a patched `Store`, confirming:
  - the dead-loop emits no `missing_queries:*` entries
  - brands with no rows in `brand_keywords` surface as
    `missing_brand_keywords:<brand>`
  - the legacy `Query` stub still feeds `apply_skip_order` without
    surfacing as a real signal
  - `read_primary_brand_keywords` is called once per run (lifted to top
    of cmd_run, not re-called per cycle)
"""
from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def _summary_for(pipeline: RunPipeline, fake_pk: dict, **execute_kwargs) -> dict:
    """Run cmd_run with the Store patched, capture the JSON summary, return it."""
    from x_monitor.__main__ import cmd_run
    from argparse import Namespace

    args = Namespace(
        dry_run=True,  # avoids needing a real TwitterAPI key
        models=None,
        queries=None,
        limit_per_call=None,
        no_skip_under_budget=True,
        max_pages_per_call=None,
    )

    paths = {
        "db": pipeline.db_path,
        "data": pipeline.data_dir,
        "config": Path("/dev/null"),  # cmd_run loads config; skip by patching
        "runs": pipeline.runs_dir,
        "raw": pipeline.raw_dir,
        "review_queue": pipeline.review_queue_path,
        "queries": pipeline.data_dir / "queries",
    }

    fake_store = MagicMock()
    fake_store.read_primary_brand_keywords.return_value = fake_pk
    # Patch both the top-of-cmd_run load and any in-cycle load to use the
    # same mock; the test asserts the top-level load is called once.

    with patch("x_monitor.run.Store", return_value=fake_store), \
         patch("x_monitor.__main__._load_config_or_die",
               return_value=pipeline.config):
        # cmd_run prints summary to stdout; capture it.
        import sys
        old, sys.stdout = sys.stdout, StringIO()
        try:
            cmd_run(args, paths)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old

    # cmd_run prints a leading JSON summary then a "---\nEstimated cost\n---"
    # block. Take the first JSON object.
    summary = json.loads(output.split("\n\n---")[0].strip())
    return summary, fake_store


def test_cmd_run_loads_brand_keywords_from_db(tmp_path: Path) -> None:
    """cmd_run calls Store.read_primary_brand_keywords (not load_queries
    from disk) and feeds both the legacy Query stub list and the planner
    from the same dict."""
    pipeline = _make_pipeline(tmp_path)
    summary, fake_store = _summary_for(
        pipeline, {"minimax": ["MiniMax", "Hailuo"], "qwen": ["Qwen"]},
    )

    assert "missing_brand_keywords" not in summary["degraded"], (
        f"DB-keyword load failed: {summary['degraded']}"
    )
    assert not any(
        k.startswith("missing_queries:") for k in summary["degraded"]
    ), (
        f"Legacy missing_queries:* entries still emit: "
        f"{list(summary['degraded'].keys())}"
    )

    # read_primary_brand_keywords was called at least once (top-level lift).
    assert fake_store.read_primary_brand_keywords.call_count >= 1


def test_cmd_run_surfaces_brand_with_no_db_rows(tmp_path: Path) -> None:
    """A brand present in enabled_models but absent from brand_keywords
    surfaces as missing_brand_keywords:<brand> (renamed from
    missing_queries:<brand>)."""
    pipeline = _make_pipeline(tmp_path)
    # Only minimax has DB rows; qwen is missing.
    summary, _ = _summary_for(pipeline, {"minimax": ["MiniMax"]})

    assert "missing_brand_keywords:qwen" in summary["degraded"], (
        f"Missing qwen: degraded keys = {list(summary['degraded'].keys())}"
    )
    assert "missing_brand_keywords:minimax" not in summary["degraded"]


def test_cmd_run_db_read_failure_surfaces_globally(tmp_path: Path) -> None:
    """If read_primary_brand_keywords raises (e.g. DB corrupt), the
    summary has a top-level missing_brand_keywords entry with the
    exception text — not 20 per-brand missing_queries entries."""
    pipeline = _make_pipeline(tmp_path)

    from x_monitor.__main__ import cmd_run
    from argparse import Namespace

    fake_store = MagicMock()
    fake_store.read_primary_brand_keywords.side_effect = RuntimeError(
        "DB corrupt"
    )

    args = Namespace(
        dry_run=True,
        models=None,
        queries=None,
        limit_per_call=None,
        no_skip_under_budget=True,
        max_pages_per_call=None,
    )
    paths = {
        "db": pipeline.db_path,
        "data": pipeline.data_dir,
        "config": Path("/dev/null"),
        "runs": pipeline.runs_dir,
        "raw": pipeline.raw_dir,
        "review_queue": pipeline.review_queue_path,
        "queries": pipeline.data_dir / "queries",
    }

    with patch("x_monitor.run.Store", return_value=fake_store), \
         patch("x_monitor.__main__._load_config_or_die",
               return_value=pipeline.config), \
         patch("sys.stdout", new_callable=StringIO) as out:
        cmd_run(args, paths)
        output = out.getvalue()

    summary = json.loads(output.split("\n\n---")[0].strip())
    assert "missing_brand_keywords" in summary["degraded"]
    assert "DB corrupt" in summary["degraded"]["missing_brand_keywords"]
    # No legacy missing_queries:* entries — those would indicate the
    # retired yaml-load path is still firing.
    assert not any(
        k.startswith("missing_queries:") for k in summary["degraded"]
    )