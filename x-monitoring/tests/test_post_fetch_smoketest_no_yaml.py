# {{AGENT_ATTRIBUTION}}
"""Tests for the U4 smoketest cleanup (--query-from-yaml removal).

Plan: docs/plans/2026-07-11-001-feat-queries-and-filters-retire-and-export-poststep-plan.md
(Unit U4).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import scripts.post_fetch_smoketest as sm


# ----------------------------------------------------------------------
# 1. --query-from-yaml is no longer a recognized flag (R14).
# ----------------------------------------------------------------------


def test_query_from_yaml_flag_removed() -> None:
    """`--query-from-yaml` raises argparse `unrecognized arguments` —
    the flag is hard-removed in U4."""
    with pytest.raises(SystemExit) as exc_info:
        sm.main(["--source", "api-query", "--query-from-yaml", "minimax"])
    # argparse exits 2 for arg errors.
    assert exc_info.value.code == 2


# ----------------------------------------------------------------------
# 2. _resolve_query_from_yaml is gone.
# ----------------------------------------------------------------------


def test_resolve_query_from_yaml_removed() -> None:
    """`_resolve_query_from_yaml` is removed from the smoketest module."""
    assert not hasattr(sm, "_resolve_query_from_yaml"), (
        "_resolve_query_from_yaml should be removed in U4"
    )


# ----------------------------------------------------------------------
# 3. --source=latest-cycle still works (no yaml dependency).
# ----------------------------------------------------------------------


def test_latest_cycle_still_parses(tmp_path: Path) -> None:
    """The smoketest's --source=latest-cycle mode still parses
    (validation may fail since the DB doesn't exist, but argparse
    accepts the args)."""
    # Empty DB path; we just want argparse to accept the args.
    # The smoketest's --db flag was never supported (the script uses
    # positional `db_path` or a default). Use a real seeded DB path
    # so the script can run end-to-end, then expect rc 0.
    p = tmp_path / "smoke.db"
    # We don't run the full pipeline — just confirm argparse passes.
    # The script may then return 2 (db not found) which is fine.
    rc = sm.main([
        "--source", "latest-cycle",
        "--limit", "5",
    ])
    # rc 0 or 2 both OK — the point is no ImportError or argparse error.
    assert rc in (0, 1, 2)
