from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.ollija.processes import (
    observe_process,
    start_detached_supervisor,
    stop_task_processes,
    supervisor_session_name,
)
from scripts.ollija.tasks import TaskRegistry, TaskSnapshot
from tests.ollija.test_tasks import _grant

REPO_ROOT = Path(__file__).resolve().parents[2]
FAKE_AGENT = Path(__file__).parent / "fixtures" / "fake_agent.py"


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _repository(
    tmp_path: Path,
    *,
    agent_mode: str,
) -> tuple[Path, TaskRegistry, TaskSnapshot]:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    shutil.copytree(
        REPO_ROOT / "scripts",
        workspace / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(REPO_ROOT / ".gitignore", workspace / ".gitignore")
    output = workspace / "feature.txt"
    counter = tmp_path / "counter"
    driver_registry = workspace / "scripts" / "ollija" / "agents" / "registry.py"
    original_registry = driver_registry.read_text(encoding="utf-8")
    production_return = "    return launch_for_attempt(task, attempt).argv"
    assert original_registry.count(production_return) == 1
    fake_return = (
        "    return (\n"
        f"        {sys.executable!r},\n"
        f"        {str(FAKE_AGENT)!r},\n"
        f"        '--mode', {agent_mode!r},\n"
        f"        '--counter', {str(counter)!r},\n"
        f"        '--output', {str(output)!r},\n"
        "    )"
    )
    driver_registry.write_text(
        original_registry.replace(production_return, fake_return),
        encoding="utf-8",
    )
    _git(workspace, "init", "-b", "feat/e2e")
    _git(workspace, "config", "user.name", "Ollija Test")
    _git(workspace, "config", "user.email", "ollija@example.invalid")
    grant = _grant(workspace, task_id="e2e-task")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "task source")
    starting_sha = _git(workspace, "rev-parse", "HEAD")
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(
        replace(
            grant,
            branch="feat/e2e",
            starting_sha=starting_sha,
            verification_argv=(
                (
                    sys.executable,
                    "-c",
                    "from pathlib import Path; assert Path('feature.txt').is_file()",
                ),
            ),
        )
    )
    return workspace, registry, armed


def _configure_isolated_tmux(
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    socket_root = Path(tempfile.mkdtemp(prefix="ollija-tmux-", dir="/tmp"))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setenv("TMUX_TMPDIR", str(socket_root))
    return socket_root


def _wait_for_task(
    registry: TaskRegistry,
    task_id: str,
    states: set[str],
    *,
    timeout: float = 20,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = registry.get(task_id)
        if current.state in states:
            return current
        time.sleep(0.05)
    pytest.fail(f"task {task_id} did not reach {sorted(states)}")


def _kill_session(session: str, workspace: Path) -> None:
    subprocess.run(
        ["tmux", "kill-session", "-t", f"={session}"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is required")
def test_detached_task_crashes_once_then_ollija_commits_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, registry, armed = _repository(tmp_path, agent_mode="crash-once-edit")
    socket_root = _configure_isolated_tmux(monkeypatch)
    session = supervisor_session_name(armed.task_id, armed.generation)
    try:
        launched = start_detached_supervisor(
            registry_path=registry.path,
            task_id=armed.task_id,
            generation=armed.generation,
            python_executable=Path(sys.executable),
            workspace=workspace,
        )

        assert launched == session
        result = _wait_for_task(registry, armed.task_id, {"succeeded", "paused"})

        assert result.state == "succeeded"
        assert result.restarts_used == 1
        assert result.outcome_sha == _git(workspace, "rev-parse", "HEAD")
        assert result.outcome_sha != armed.starting_sha
        assert _git(workspace, "status", "--porcelain") == ""
        assert _git(workspace, "show", "--format=", "--name-only", "HEAD") == "feature.txt"
        assert registry.current_attempt(armed.task_id, armed.generation).attempt == 2
    finally:
        _kill_session(session, workspace)
        shutil.rmtree(socket_root, ignore_errors=True)


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is required")
def test_detached_stop_preserves_dirty_work_and_never_restarts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, registry, armed = _repository(tmp_path, agent_mode="edit-sleep")
    output = workspace / "feature.txt"
    socket_root = _configure_isolated_tmux(monkeypatch)
    session = supervisor_session_name(armed.task_id, armed.generation)
    try:
        start_detached_supervisor(
            registry_path=registry.path,
            task_id=armed.task_id,
            generation=armed.generation,
            python_executable=Path(sys.executable),
            workspace=workspace,
        )
        _wait_for_task(registry, armed.task_id, {"running"})
        deadline = time.monotonic() + 10
        while not output.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert output.is_file()
        attempt = registry.current_attempt(armed.task_id, armed.generation)
        assert attempt is not None
        observed = observe_process(attempt.pid or -1)
        assert observed is not None
        assert (observed.pid, observed.pgid, observed.birth) == (
            attempt.pid,
            attempt.pgid,
            attempt.process_birth,
        )

        stopped = stop_task_processes(
            registry,
            armed.task_id,
            armed.generation,
        )
        time.sleep(0.2)

        assert stopped.state == "cancelled"
        assert registry.get(armed.task_id).state == "cancelled"
        assert registry.current_attempt(armed.task_id, armed.generation).attempt == 1
        assert output.is_file()
        assert "feature.txt" in _git(workspace, "status", "--porcelain")
    finally:
        _kill_session(session, workspace)
        shutil.rmtree(socket_root, ignore_errors=True)
