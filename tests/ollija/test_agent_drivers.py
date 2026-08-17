from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.ollija.agents.base import task_prompt
from scripts.ollija.agents.claude import ClaudeDriver
from scripts.ollija.agents.codex import CodexDriver
from scripts.ollija.agents.registry import AgentDriverError, driver_for, launch_for_attempt
from scripts.ollija.git import CommandOutcome
from scripts.ollija.tasks import TaskRegistry
from tests.ollija.test_tasks import _grant


class _Runner:
    def __init__(self, outcomes: list[CommandOutcome]) -> None:
        self.outcomes = outcomes
        self.commands: list[tuple[str, ...]] = []

    def run(self, args, *, cwd: Path, timeout: float = 10):
        self.commands.append(tuple(args))
        return self.outcomes.pop(0)


def test_codex_and_claude_receive_same_completion_contract(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    codex_task = registry.arm(_grant(workspace, task_id="codex-task"))
    registry.cancel(codex_task.task_id, codex_task.generation)
    claude_task = registry.arm(
        replace(_grant(workspace, task_id="claude-task"), agent_kind="claude")
    )

    assert task_prompt(codex_task) == task_prompt(claude_task).replace(
        "claude-task", "codex-task"
    )
    prompt = task_prompt(codex_task)
    assert "Do not stage, commit, push, release, or deploy" in prompt
    assert codex_task.source_path in prompt
    assert str(codex_task.workspace) not in prompt


def test_codex_driver_builds_no_shell_argv_and_probes_auth(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    task = registry.arm(_grant(workspace))
    runner = _Runner(
        [
            CommandOutcome(0, "codex-cli 0.147.0\n", ""),
            CommandOutcome(0, "Logged in using ChatGPT\n", ""),
        ]
    )
    driver = CodexDriver(executable=Path("/opt/bin/codex"), runner=runner)

    probe = driver.probe(workspace)
    launch = driver.launch(task, attempt=1)

    assert probe.available is True
    assert probe.version == "0.147.0"
    assert launch.argv[:8] == (
        "/opt/bin/codex",
        "exec",
        "--json",
        "--sandbox",
        "workspace-write",
        "--approve-for-me",
        "-C",
        str(workspace),
    )
    assert launch.argv[-1] == task_prompt(task)
    assert launch.session_id is None
    assert launch.supports_resume is False


def test_claude_driver_uses_stable_task_session_and_exact_resume(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    task = registry.arm(replace(_grant(workspace), agent_kind="claude"))
    runner = _Runner(
        [
            CommandOutcome(0, "2.1.187 (Claude Code)\n", ""),
            CommandOutcome(0, json.dumps({"loggedIn": True}), ""),
        ]
    )
    driver = ClaudeDriver(executable=Path("/opt/bin/claude"), runner=runner)

    probe = driver.probe(workspace)
    first = driver.launch(task, attempt=1)
    resumed = driver.launch(task, attempt=2)

    assert probe.available is True
    assert first.session_id is not None
    assert "--session-id" in first.argv
    assert resumed.session_id == first.session_id
    assert "--resume" in resumed.argv
    assert "--session-id" not in resumed.argv
    assert resumed.argv[-1] == task_prompt(task)


def test_unavailable_auth_and_unsupported_agent_never_fall_through(
    tmp_path: Path,
) -> None:
    runner = _Runner(
        [
            CommandOutcome(0, "codex-cli 0.147.0\n", ""),
            CommandOutcome(1, "", "not logged in"),
        ]
    )
    probe = CodexDriver(Path("codex"), runner).probe(tmp_path)
    assert probe.available is False
    assert probe.reason == "agent_auth_unavailable"

    old = CodexDriver(
        Path("codex"),
        _Runner([CommandOutcome(0, "codex-cli 0.1.0\n", "")]),
    ).probe(tmp_path)
    assert old.available is False
    assert old.reason == "agent_version_unsupported"

    with pytest.raises(AgentDriverError, match="unsupported"):
        driver_for("openclaw")


def test_registry_launch_uses_task_agent_without_vendor_fallback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    task = registry.arm(_grant(workspace))
    attempt = registry.start_attempt(task.task_id, task.generation)

    launch = launch_for_attempt(
        task,
        attempt,
        drivers={"codex": CodexDriver(Path("/opt/bin/codex"), _Runner([]))},
    )

    assert launch.argv[0] == "/opt/bin/codex"
    assert "claude" not in launch.argv
