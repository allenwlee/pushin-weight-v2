from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from scripts.ollija.cli import build_parser, emit_result, render_human
from scripts.ollija.results import CommandResult, EvidenceRef, NextAction

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


def _result() -> CommandResult:
    return CommandResult(
        command="status",
        status="ok",
        state="candidate",
        summary="Candidate is ready to stage.",
        next_action=NextAction("ollija stage", "Deploy this exact candidate."),
        evidence=(EvidenceRef("git_commit", SHA, SHA),),
    )


def test_human_and_json_output_recommend_the_same_action() -> None:
    result = _result()
    human = render_human(result)
    stream = io.StringIO()

    emit_result(result, json_output=True, stream=stream)
    machine = json.loads(stream.getvalue())

    assert "Next: ollija stage" in human
    assert machine["next_action"]["command"] == "ollija stage"


def test_bin_wrapper_resolves_repo_from_root_and_nested_directory() -> None:
    for cwd in (REPO_ROOT, REPO_ROOT / "tests" / "ollija"):
        completed = subprocess.run(
            [str(REPO_ROOT / "bin" / "ollija"), "--help"],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0
        assert "what's next" in completed.stdout.lower()


def test_human_output_redacts_synthetic_error() -> None:
    unsafe = (
        "failed "
        + "postgresql://operator:"
        + "live-value"
        + "@example.invalid/db"
    )
    result = CommandResult(
        command="doctor",
        status="failed",
        state="blocked",
        summary=unsafe,
    )

    rendered = render_human(result)

    assert "live-value" not in rendered
    assert "[REDACTED" in rendered


def test_task_commands_are_discoverable_and_verification_is_structured() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "go",
            "--task",
            "task-1",
            "--source",
            "docs/plans/task.md",
            "--agent",
            "codex",
            "--endpoint",
            "commit",
            "--verify-argv",
            '["pytest","tests/ollija"]',
        ]
    )
    stopped = parser.parse_args(["stop", "task-1"])
    observed = parser.parse_args(["task-status", "task-1", "--json"])
    overridden = parser.parse_args(
        [
            "override",
            "bridgewright",
            "--owner",
            "allenwlee",
            "--reason",
            "adapter defect",
        ]
    )

    assert args.command == "go"
    assert args.verify_argv == ['["pytest","tests/ollija"]']
    assert stopped.command == "stop"
    assert observed.command == "task-status"
    assert observed.json_output is True
    assert overridden.assessment_kind == "bridgewright"
