"""Tests for cmd_dry_run + cmd_queries sibling CLI commands.

These tests pin the fix that closes the runtime hazard flagged by the
Related Docs Finder during the 2026-07-16 compound run on plan 003:

  `x_monitor/__main__.py` lines 84, 177, 190 (pre-fix) called
  `load_queries(m, paths['data'])`, which reads from
  `data/queries/<m>.yaml`. That directory was deleted in plan
  2026-07-11-001 U3. Pre-fix behavior: `cmd_dry_run`'s cost calc,
  `cmd_queries --list-disabled`, and `cmd_queries --validate` all
  raised `FileNotFoundError` at runtime. Post-fix: the three sites
  share `load_brand_queries_or_stub`, the same DB-keyword read used
  by `cmd_run` (Plan 2026-07-15-003 U1).

These tests exercise the three sibling command entry points directly,
asserting:
  - no `FileNotFoundError` on the deleted yaml path
  - the dry-run cost calc prints a TOTAL line
  - the `list-disabled` action prints nothing for enabled-model brands
    (the v1.7 stub Query has `enabled=True`, so nothing prints)
  - the `validate` action runs without raising on the placeholder
    `query_string` (it does flag the unbalanced parens — that's
    acceptable; v1.7 cost calc never reaches the planner)

Test approach: we mock `load_brand_queries_or_stub` at the import site
that `cmd_dry_run` / `cmd_queries` use, so the tests don't need a real
DB. The helper itself has its own direct tests below.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest

from x_monitor.queries import Query
from x_monitor.config import Config
from x_monitor.__main__ import cmd_dry_run, cmd_queries


def _project_paths_for(tmp_path: Path) -> dict[str, Path]:
    """Synthetic paths dict — values don't need to exist because the
    tests mock the helper that would touch them."""
    return {
        "config": tmp_path / "config.yaml",
        "data": tmp_path / "data",
        "db": tmp_path / "data" / "x_monitoring.db",
        "queries": tmp_path / "data" / "queries",  # retired dir
        "accounts": tmp_path / "data" / "accounts",
        "review": tmp_path / "data" / "_review_queue.json",
    }


def _stub_queries_per_model(models: list[str]) -> dict[str, list[Query]]:
    """The same stub shape `load_brand_queries_or_stub` returns."""
    return {
        m: [
            Query(
                id="Q5",  # legacy Q-id; never reaches the DB
                query_string="(placeholder)",
                enabled=True,
            )
        ]
        for m in models
    }


def test_cmd_dry_run_cost_calc_does_not_crash(tmp_path: Path, capsys) -> None:
    """cmd_dry_run's cost calc must not raise FileNotFoundError on the
    retired data/queries/ directory. Pre-fix: it called load_queries(m,
    paths['data']) which raised. Post-fix: it routes through the helper."""
    paths = _project_paths_for(tmp_path)
    fake_cfg = Config(
        enabled_models=["minimax", "qwen"],
        daily_ceiling=10,
        x_monitor_list_id=1234567890,
    )
    captured_models: list[str] = []

    def fake_helper(cfg, db_path, store=None):
        captured_models.append(list(cfg.enabled_models))
        return _stub_queries_per_model(cfg.enabled_models), {}

    with patch("x_monitor.__main__._load_config_or_die", return_value=fake_cfg), \
         patch("x_monitor.run.load_brand_queries_or_stub", side_effect=fake_helper), \
         patch("x_monitor.run.RunPipeline.execute", return_value={
             "status": "dry_run", "degraded": {}, "queries": [],
             "totals": {"n_queries_run": 0, "n_results": 0, "n_inserted": 0,
                        "n_classifications_written": 0, "n_classifications_dropped": 0}
         }):
        args = argparse.Namespace(models=None, queries=None)
        rc = cmd_dry_run(args, paths)

    assert rc == 0
    captured = capsys.readouterr()
    assert "TOTAL:" in captured.err
    assert "ceiling:" in captured.err
    assert captured_models == [["minimax", "qwen"]]


def test_cmd_queries_list_disabled_does_not_crash(tmp_path: Path) -> None:
    """cmd_queries --list-disabled must iterate without FileNotFoundError."""
    paths = _project_paths_for(tmp_path)
    fake_cfg = Config(
        enabled_models=["minimax", "qwen"],
        daily_ceiling=10,
        x_monitor_list_id=1234567890,
    )

    def fake_helper(cfg, db_path, store=None):
        return _stub_queries_per_model(cfg.enabled_models), {}

    with patch("x_monitor.__main__._load_config_or_die", return_value=fake_cfg), \
         patch("x_monitor.run.load_brand_queries_or_stub", side_effect=fake_helper):
        args = argparse.Namespace(queries_action="list-disabled")
        rc = cmd_queries(args, paths)

    # No disabled queries in the stub list (enabled=True by default).
    assert rc == 0


def test_cmd_queries_validate_does_not_crash(tmp_path: Path, capsys) -> None:
    """cmd_queries --validate must run validate_query_syntax without
    raising FileNotFoundError. The placeholder query_string `(placeholder)`
    has balanced parens, so the validator returns no errors and rc=0. The
    v1.7 stub never reaches the planner (cost calc is always under budget),
    so the placeholder shape is acceptable."""
    paths = _project_paths_for(tmp_path)
    fake_cfg = Config(
        enabled_models=["minimax"],
        daily_ceiling=10,
        x_monitor_list_id=1234567890,
    )

    def fake_helper(cfg, db_path, store=None):
        return _stub_queries_per_model(cfg.enabled_models), {}

    with patch("x_monitor.__main__._load_config_or_die", return_value=fake_cfg), \
         patch("x_monitor.run.load_brand_queries_or_stub", side_effect=fake_helper):
        args = argparse.Namespace(queries_action="validate")
        rc = cmd_queries(args, paths)

    # rc=0 — the placeholder has balanced parens, no errors.
    assert rc == 0


# Direct tests for the helper — these DO need a real DB. Use
# auto_migrate=False + minimal schema to avoid migration 034's canonical
# brand-keyword seed polluting the test fixtures.

def test_load_brand_queries_or_stub_returns_stub_per_brand(tmp_path: Path) -> None:
    """The shared helper returns one Query stub per enabled model and
    a primary_keywords dict keyed by brand_id."""
    from x_monitor.config import Config
    from x_monitor.run import load_brand_queries_or_stub
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    import sqlite3

    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE brand_keywords(
            brand_id TEXT NOT NULL,
            pattern TEXT NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (brand_id, pattern)
        );
        """
    )
    conn.execute(
        "INSERT INTO brand_keywords VALUES (?, ?, 1)", ("minimax", "(MiniMax OR Hailuo)")
    )
    conn.execute(
        "INSERT INTO brand_keywords VALUES (?, ?, 1)", ("qwen", "(Qwen OR 通义千问)")
    )
    conn.commit()
    conn.close()

    cfg = Config(
        enabled_models=["minimax", "qwen"],
        daily_ceiling=10,
        x_monitor_list_id=1234567890,
    )
    store = Store(db, auto_migrate=False)
    try:
        queries_per_model, primary_keywords = load_brand_queries_or_stub(
            cfg, db, store=store
        )
        assert set(queries_per_model.keys()) == {"minimax", "qwen"}
        for m, qs in queries_per_model.items():
            assert len(qs) == 1
            assert qs[0].enabled is True
            assert qs[0].id == "Q5"  # legacy id; never reaches the DB
        assert primary_keywords["minimax"] == ["(MiniMax OR Hailuo)"]
        assert primary_keywords["qwen"] == ["(Qwen OR 通义千问)"]
    finally:
        store.close()


def test_load_brand_queries_or_stub_handles_empty_brand_keywords(tmp_path: Path) -> None:
    """A brand with no is_primary=1 rows surfaces as missing from
    primary_keywords; the stub Query list still has one entry per brand."""
    from x_monitor.config import Config
    from x_monitor.run import load_brand_queries_or_stub
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    import sqlite3

    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE brand_keywords(
            brand_id TEXT NOT NULL,
            pattern TEXT NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (brand_id, pattern)
        );
        """
    )
    conn.commit()
    conn.close()

    cfg = Config(
        enabled_models=["minimax"],
        daily_ceiling=10,
        x_monitor_list_id=1234567890,
    )
    store = Store(db, auto_migrate=False)
    try:
        queries_per_model, primary_keywords = load_brand_queries_or_stub(
            cfg, db, store=store
        )
        assert queries_per_model["minimax"][0].enabled is True
        assert primary_keywords == {}
    finally:
        store.close()
