# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor CLI (x_monitor.__main__)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from x_monitor.__main__ import build_parser, main


def test_help_lists_subcommands():
    parser = build_parser()
    help_text = parser.format_help()
    for sub in ("run", "dashboard", "review", "migrate", "accounts", "queries", "setup"):
        assert sub in help_text


def test_setup_twitterapi_key_subcommand_registered():
    """The setup wizard now expects a `twitterapi-key` action, not `cookies`."""
    parser = build_parser()
    args = parser.parse_args(["setup", "twitterapi-key"])
    assert args.setup_action == "twitterapi-key"


def test_run_dry_run_exits_zero(tmp_path):
    # Set up a minimal project
    project = tmp_path / "x-monitoring"
    project.mkdir()
    (project / "x_monitor").mkdir()
    (project / "data" / "queries").mkdir(parents=True)
    (project / "data" / "accounts").mkdir(parents=True)
    # config.yaml
    (project / "config.yaml").write_text(
        """
enabled_models: [minimax]
daily_ceiling: 333
""",
        encoding="utf-8",
    )
    # 5-query YAML
    (project / "data" / "queries" / "minimax.yaml").write_text(
        """
queries:
  - id: Q1
    query_string: 'from:MiniMaxAI'
    expected_signal: release
  - id: Q2
    query_string: 'minimax how'
    expected_signal: community_question
  - id: Q3
    query_string: 'minimax broken'
    expected_signal: criticism
  - id: Q4
    query_string: 'to:MiniMaxAI'
    expected_signal: commenter_capture
  - id: Q5
    query_string: 'minimax benchmark'
    expected_signal: other
""",
        encoding="utf-8",
    )
    # Run from the project dir so the CLI's _project_paths() finds config.yaml
    import os
    old = os.getcwd()
    try:
        os.chdir(project)
        rc = main(["run", "--dry-run"])
        assert rc == 0
    finally:
        os.chdir(old)


def test_review_add_and_resolve(tmp_path):
    project = tmp_path / "x-monitoring"
    project.mkdir()
    (project / "x_monitor").mkdir()
    (project / "data").mkdir()
    (project / "config.yaml").write_text(
        "enabled_models: [minimax]\ndaily_ceiling: 100\n",
        encoding="utf-8",
    )
    import os
    old = os.getcwd()
    try:
        os.chdir(project)
        rc1 = main(["review", "add", "--tweet-id", "t1", "--reason", "suspicious_actor", "--model", "minimax"])
        assert rc1 == 0
        rc2 = main(["review", "resolve", "--tweet-id", "t1"])
        assert rc2 == 0
        rq = json.loads((project / "data" / "_review_queue.json").read_text())
        assert rq[0]["status"] == "resolved"
    finally:
        os.chdir(old)


def test_migrate_is_idempotent(tmp_path):
    project = tmp_path / "x-monitoring"
    project.mkdir()
    (project / "x_monitor").mkdir()
    (project / "data").mkdir()
    (project / "config.yaml").write_text(
        "enabled_models: [minimax]\ndaily_ceiling: 100\n",
        encoding="utf-8",
    )
    import os
    old = os.getcwd()
    try:
        os.chdir(project)
        rc = main(["migrate"])
        assert rc == 0
        rc = main(["migrate"])  # idempotent
        assert rc == 0
    finally:
        os.chdir(old)


def test_bootstrap_followers_subcommand_registered():
    parser = build_parser()
    # Parse with `accounts bootstrap-followers --model m --handle h` to ensure
    # the subparser accepts it.
    args = parser.parse_args(["accounts", "bootstrap-followers", "--model", "m", "--handle", "h"])
    assert args.accounts_action == "bootstrap-followers"


def test_queries_validate(tmp_path):
    project = tmp_path / "x-monitoring"
    project.mkdir()
    (project / "x_monitor").mkdir()
    (project / "data" / "queries").mkdir(parents=True)
    (project / "data" / "accounts").mkdir(parents=True)
    (project / "config.yaml").write_text(
        "enabled_models: [minimax]\ndaily_ceiling: 100\n",
        encoding="utf-8",
    )
    (project / "data" / "queries" / "minimax.yaml").write_text(
        """
queries:
  - id: Q1
    query_string: 'from:MiniMaxAI'
    expected_signal: release
  - id: Q2
    query_string: 'minimax how'
    expected_signal: community_question
  - id: Q3
    query_string: '(minimax OR broken'
    expected_signal: criticism
  - id: Q4
    query_string: 'to:MiniMaxAI'
    expected_signal: commenter_capture
  - id: Q5
    query_string: 'minimax benchmark'
    expected_signal: other
""",
        encoding="utf-8",
    )
    import os
    old = os.getcwd()
    try:
        os.chdir(project)
        rc = main(["queries", "validate"])
        # Q3 has unbalanced parens → rc=1
        assert rc == 1
    finally:
        os.chdir(old)


def test_missing_config_in_cwd_falls_back_to_package_root(tmp_path):
    """The CLI resolves cwd-relative first, falling back to the package root
    (where it was installed). When run from the install dir, config.yaml
    is found there."""
    project = tmp_path / "x-monitoring"
    project.mkdir()
    (project / "x_monitor").mkdir()
    import os
    old = os.getcwd()
    try:
        os.chdir(project)
        # Falls back to package root (where the live config.yaml lives)
        # and runs migrate successfully.
        rc = main(["migrate"])
        assert rc == 0
    finally:
        os.chdir(old)
