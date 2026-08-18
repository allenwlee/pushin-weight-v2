from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.ollija.config import load_project_config
from scripts.ollija.git import CommandOutcome
from scripts.ollija.worktrees import (
    WorktreeError,
    guard_worktree,
    is_release_worktree,
    move_worktree,
    release_worktree_location,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class InteractiveInput(io.StringIO):
    def isatty(self) -> bool:
        return True


class FakeRunner:
    def __init__(self, *outcomes: CommandOutcome) -> None:
        self.outcomes = list(outcomes)
        self.commands: list[tuple[str, ...]] = []

    def run(
        self, args: list[str] | tuple[str, ...], *, cwd: Path, timeout: float = 10
    ) -> CommandOutcome:
        self.commands.append(tuple(args))
        return self.outcomes.pop(0)


def _config(tmp_path: Path):
    config = load_project_config(REPO_ROOT)
    return replace(
        config,
        root=tmp_path,
        authority=replace(config.authority, repository_root=tmp_path),
    )


def test_release_worktree_location_has_human_label_and_repo_relative_path() -> None:
    location = release_worktree_location(load_project_config(REPO_ROOT))

    assert location.label == "Ollija release worktree area"
    assert location.relative_path == ".worktrees"
    assert location.path == REPO_ROOT / ".worktrees"


def test_paths_inside_release_worktree_area_are_eligible(tmp_path: Path) -> None:
    config = _config(tmp_path)
    inside = tmp_path / ".worktrees" / "feature"
    outside = tmp_path / "worktrees" / "feature"

    assert is_release_worktree(config, inside)
    assert not is_release_worktree(config, outside)


def test_declining_outside_worktree_move_leaves_it_as_is(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "outside-feature"
    runner = FakeRunner(
        CommandOutcome(0, f"{source}\n", ""),
    )
    output = io.StringIO()

    result = guard_worktree(
        config,
        cwd=source,
        input_stream=InteractiveInput("n\n"),
        output_stream=output,
        runner=runner,
    )

    assert result == source
    assert "Ollija release worktree area (.worktrees/)" in output.getvalue()
    assert "Move to the release worktree area? [y/N]" in output.getvalue()
    assert len(runner.commands) == 1


def test_noninteractive_outside_worktree_requires_owner_confirmation(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "outside-feature"
    runner = FakeRunner(CommandOutcome(0, f"{source}\n", ""))

    with pytest.raises(
        WorktreeError, match="outside_release_worktree_requires_owner_confirmation"
    ):
        guard_worktree(
            config,
            cwd=source,
            input_stream=io.StringIO(),
            output_stream=io.StringIO(),
            runner=runner,
        )


def test_explicit_owner_decision_can_leave_noninteractive_worktree_as_is(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    source = tmp_path / "outside-feature"
    runner = FakeRunner(CommandOutcome(0, f"{source}\n", ""))

    result = guard_worktree(
        config,
        cwd=source,
        input_stream=io.StringIO(),
        output_stream=io.StringIO(),
        runner=runner,
        leave_as_is=True,
    )

    assert result == source


def test_move_uses_git_worktree_move_without_rewriting_history(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "outside-feature"
    runner = FakeRunner(CommandOutcome(0, "", ""))

    destination = move_worktree(config, source=source, runner=runner)

    assert destination == tmp_path / ".worktrees" / "outside-feature"
    assert runner.commands == [
        ("git", "worktree", "move", str(source), str(destination))
    ]
