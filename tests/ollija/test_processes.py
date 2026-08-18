from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.ollija.git import CommandOutcome
from scripts.ollija.processes import (
    ProcessControlError,
    observe_process,
    start_detached_supervisor,
    stop_task_processes,
    supervisor_session_name,
)
from scripts.ollija.tasks import TaskRegistry
from tests.ollija.test_tasks import _grant

FAKE_AGENT = Path(__file__).parent / "fixtures" / "fake_agent.py"


class _Runner:
    def __init__(self, outcomes: list[CommandOutcome]) -> None:
        self.outcomes = outcomes
        self.commands: list[tuple[str, ...]] = []

    def run(self, args, *, cwd: Path, timeout: float = 10):
        self.commands.append(tuple(args))
        return self.outcomes.pop(0)


def _wait_for(path: Path, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.exists()


def test_tmux_launch_uses_fixed_tokens_and_rejects_metacharacters(tmp_path: Path) -> None:
    runner = _Runner([CommandOutcome(1, "", "missing"), CommandOutcome(0, "", "")])

    session = start_detached_supervisor(
        registry_path=tmp_path / "tasks.sqlite3",
        task_id="task-1",
        generation=2,
        python_executable=Path(sys.executable),
        workspace=tmp_path,
        runner=runner,
    )

    assert session == "ollija-task-1-g2"
    assert runner.commands[1] == (
        "tmux",
        "new-session",
        "-d",
        "-s",
        "ollija-task-1-g2",
        sys.executable,
        "-m",
        "scripts.ollija.supervisor",
        "--registry",
        str(tmp_path / "tasks.sqlite3"),
        "--task",
        "task-1",
        "--generation",
        "2",
    )
    with pytest.raises(ProcessControlError, match="task_identity_invalid"):
        start_detached_supervisor(
            registry_path=tmp_path / "tasks.sqlite3",
            task_id="task;touch-bad",
            generation=1,
            python_executable=Path(sys.executable),
            workspace=tmp_path,
            runner=_Runner([]),
        )


def test_tmux_session_names_preserve_distinct_task_ids() -> None:
    assert supervisor_session_name("release.1", 1) != supervisor_session_name(
        "release_1", 1
    )


def test_stop_commits_cancellation_then_kills_only_owned_process_group(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))
    attempt = registry.start_attempt(armed.task_id, armed.generation)
    pids = tmp_path / "pids"
    owned = subprocess.Popen(
        [sys.executable, str(FAKE_AGENT), "--mode", "tree", "--pids", str(pids)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    unrelated = subprocess.Popen(
        [sys.executable, str(FAKE_AGENT), "--mode", "sleep"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for(pids)
        identity = observe_process(owned.pid)
        assert identity is not None
        registry.record_process(
            armed.task_id,
            armed.generation,
            attempt.attempt,
            pid=identity.pid,
            pgid=identity.pgid,
            process_birth=identity.birth,
        )

        runner = _Runner([CommandOutcome(1, "", "missing")])
        stopped = stop_task_processes(
            registry,
            armed.task_id,
            armed.generation,
            runner=runner,
        )

        assert stopped.state == "cancelled"
        owned.wait(timeout=5)
        assert observe_process(unrelated.pid) is not None
        assert runner.commands == [
            ("tmux", "kill-session", "-t", "=ollija-task-1-g1")
        ]
    finally:
        if owned.poll() is None:
            os.killpg(owned.pid, 9)
            owned.wait(timeout=5)
        if unrelated.poll() is None:
            os.killpg(unrelated.pid, 9)
            unrelated.wait(timeout=5)


def test_stop_terminates_exact_supervisor_before_process_is_recorded(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))
    registry.start_attempt(armed.task_id, armed.generation)
    runner = _Runner([CommandOutcome(0, "", "")])

    stopped = stop_task_processes(
        registry,
        armed.task_id,
        armed.generation,
        runner=runner,
    )

    assert stopped.state == "cancelled"
    assert runner.commands == [
        ("tmux", "kill-session", "-t", "=ollija-task-1-g1")
    ]
