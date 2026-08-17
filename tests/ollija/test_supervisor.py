from __future__ import annotations

import stat
import sys
from pathlib import Path

from scripts.ollija.incidents import IncidentStore
from scripts.ollija.supervisor import reconcile_missing_supervisor, run_supervisor
from scripts.ollija.tasks import TaskRegistry
from tests.ollija.test_tasks import _grant

FAKE_AGENT = Path(__file__).parent / "fixtures" / "fake_agent.py"


def _ready(registry: TaskRegistry, task_id: str, generation: int) -> None:
    registry.complete(task_id, generation, outcome_sha="b" * 40)


def test_supervisor_restarts_one_crash_then_completes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))
    counter = tmp_path / "counter"

    result = run_supervisor(
        registry,
        armed.task_id,
        armed.generation,
        command_factory=lambda _task, _attempt: (
            sys.executable,
            str(FAKE_AGENT),
            "--mode",
            "crash-once",
            "--counter",
            str(counter),
        ),
        on_ready=_ready,
    )

    assert result.state == "succeeded"
    assert result.restarts_used == 1
    assert registry.current_attempt(armed.task_id, armed.generation).attempt == 2


def test_supervisor_second_crash_pauses_without_third_attempt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))

    result = run_supervisor(
        registry,
        armed.task_id,
        armed.generation,
        command_factory=lambda _task, _attempt: (
            sys.executable,
            str(FAKE_AGENT),
            "--mode",
            "crash",
        ),
        on_ready=_ready,
    )

    assert result.state == "paused"
    assert result.failure_code == "restart_budget_exhausted"
    assert registry.current_attempt(armed.task_id, armed.generation).attempt == 2
    incidents = IncidentStore(registry.path.parent).for_task(armed.task_id)
    assert incidents[-1].phase == "agent.restart"


def test_cancellation_after_exit_prevents_retry(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))

    result = run_supervisor(
        registry,
        armed.task_id,
        armed.generation,
        command_factory=lambda _task, _attempt: (
            sys.executable,
            str(FAKE_AGENT),
            "--mode",
            "crash",
        ),
        on_ready=_ready,
        after_attempt=lambda: registry.cancel(armed.task_id, armed.generation),
    )

    assert result.state == "cancelled"
    assert registry.current_attempt(armed.task_id, armed.generation).attempt == 1


def test_missing_tmux_never_marks_lost_while_owned_child_survives(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))
    registry.start_attempt(armed.task_id, armed.generation)

    assert reconcile_missing_supervisor(
        registry,
        armed.task_id,
        armed.generation,
        process_alive=lambda _attempt: True,
    ) == "owned_child_alive"
    assert registry.get(armed.task_id).state == "running"

    assert reconcile_missing_supervisor(
        registry,
        armed.task_id,
        armed.generation,
        process_alive=lambda _attempt: False,
    ) == "lost"
    assert registry.get(armed.task_id).state == "lost"


def test_supervisor_log_is_private_bounded_and_contains_no_agent_output(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))

    run_supervisor(
        registry,
        armed.task_id,
        armed.generation,
        command_factory=lambda _task, _attempt: (
            sys.executable,
            "-c",
            "print('Implement the task. provider response')",
        ),
        on_ready=_ready,
    )

    log = registry.path.parent / "logs" / "tasks" / "task-1.log"
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    text = log.read_text(encoding="utf-8")
    assert "Implement the task" not in text
    assert "provider response" not in text
    assert log.stat().st_size < 64_000
