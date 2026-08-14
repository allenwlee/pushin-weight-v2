from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from scripts.ollija.cli import emit_result, render_human
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
