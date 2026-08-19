from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.ollija.cli import build_parser, main

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_help_exposes_only_annotate_plan() -> None:
    help_text = build_parser().format_help()

    assert "annotate-plan" in help_text
    for retired in ("status", "doctor", "go", "stop", "stage", "release", "worktree"):
        assert retired not in help_text


def test_wrapper_and_python_module_reach_the_same_command(tmp_path: Path) -> None:
    from tests.ollija.test_plan_discovery import write_repository

    root = write_repository(tmp_path, branch="feat/wrapper")
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    wrapper = subprocess.run(
        [str(REPO_ROOT / "bin" / "ollija"), "annotate-plan"],
        cwd=root,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    module = subprocess.run(
        [sys.executable, "-m", "scripts.ollija", "annotate-plan"],
        cwd=root,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )

    assert wrapper.returncode == module.returncode == 0
    assert json.loads(wrapper.stdout)["plan_path"] == json.loads(module.stdout)["plan_path"]
    assert json.loads(module.stdout)["result"] == "unchanged"
