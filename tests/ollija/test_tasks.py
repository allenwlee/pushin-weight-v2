from __future__ import annotations

import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.ollija.tasks import (
    TaskConflict,
    TaskGrant,
    TaskRegistry,
    TaskValidationError,
    digest_task_source,
)


def _grant(workspace: Path, *, task_id: str = "task-1", parent: str | None = None):
    source = workspace / "docs" / "plans" / "task.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        source.write_text("Implement the task.\n", encoding="utf-8")
    return TaskGrant(
        task_id=task_id,
        parent_task_id=parent,
        source_path="docs/plans/task.md",
        source_digest=digest_task_source(workspace, "docs/plans/task.md"),
        workspace=workspace,
        branch="feat/task-1",
        starting_sha="a" * 40,
        agent_kind="codex",
        agent_version="0.147.0",
        agent_session_id=None,
        origin_host="allenwlee",
        origin_terminal="vscode-remote",
        execution_host="fuchitalee",
        endpoint="commit",
        verification_argv=(("pytest", "tests/ollija/test_tasks.py"),),
        no_test_reason=None,
        restart_budget=1,
    )


def test_registry_reopens_one_generation_with_owner_only_permissions(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = tmp_path / "state" / "tasks.sqlite3"

    first = TaskRegistry(path).arm(_grant(workspace))
    reopened = TaskRegistry(path).get("task-1")

    assert first == reopened
    assert reopened.generation == 1
    assert reopened.restart_budget == 1
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_concurrent_initialization_leaves_one_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "state" / "tasks.sqlite3"

    with ThreadPoolExecutor(max_workers=4) as pool:
        versions = list(pool.map(lambda _index: TaskRegistry(path).schema_version, range(8)))

    assert versions == [1] * 8


def test_locked_registry_write_fails_bounded_instead_of_hanging(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = tmp_path / "state" / "tasks.sqlite3"
    registry = TaskRegistry(path)
    lock = sqlite3.connect(path, isolation_level=None)
    lock.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(TaskConflict, match="task_registry_busy"):
            registry.arm(_grant(workspace))
    finally:
        lock.execute("ROLLBACK")
        lock.close()


def test_cancellation_wins_against_late_success_and_restart(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))
    registry.mark_running(armed.task_id, armed.generation)

    cancelled = registry.cancel(armed.task_id, armed.generation)

    assert cancelled.state == "cancelled"
    with pytest.raises(TaskConflict, match="terminal"):
        registry.complete(armed.task_id, armed.generation, outcome_sha="b" * 40)
    with pytest.raises(TaskConflict, match="terminal"):
        registry.consume_restart(armed.task_id, armed.generation)


def test_success_first_makes_later_stop_truthful(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))
    registry.mark_running(armed.task_id, armed.generation)
    complete = registry.complete(armed.task_id, armed.generation, outcome_sha="b" * 40)

    stopped = registry.cancel(armed.task_id, armed.generation)

    assert complete.state == "succeeded"
    assert stopped.state == "succeeded"
    assert stopped.outcome_sha == "b" * 40


def test_restart_budget_is_consumed_once_then_pauses(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))
    registry.mark_running(armed.task_id, armed.generation)

    retrying = registry.consume_restart(armed.task_id, armed.generation)
    registry.mark_running(armed.task_id, armed.generation)
    exhausted = registry.consume_restart(armed.task_id, armed.generation)

    assert retrying.state == "restarting"
    assert retrying.restarts_used == 1
    assert exhausted.state == "paused"
    assert exhausted.failure_code == "restart_budget_exhausted"


def test_attempt_process_identity_and_exit_are_durable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = tmp_path / "state" / "tasks.sqlite3"
    registry = TaskRegistry(path)
    armed = registry.arm(_grant(workspace))

    attempt = registry.start_attempt(
        armed.task_id, armed.generation, driver_session_id="session-1"
    )
    running = registry.record_process(
        armed.task_id,
        armed.generation,
        attempt.attempt,
        pid=1234,
        pgid=1234,
        process_birth="Mon Aug 17 12:00:00 2026",
    )
    finished = registry.finish_attempt(
        armed.task_id,
        armed.generation,
        attempt.attempt,
        exit_code=7,
        classification="unexpected_exit",
    )
    reopened = TaskRegistry(path).current_attempt(armed.task_id, armed.generation)

    assert running.pid == running.pgid == 1234
    assert finished.exit_classification == "unexpected_exit"
    assert reopened == finished


def test_cancellation_rejects_process_identity_recorded_after_stop(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))
    attempt = registry.start_attempt(armed.task_id, armed.generation)

    registry.cancel(armed.task_id, armed.generation)

    with pytest.raises(TaskConflict, match="process_record_state_invalid"):
        registry.record_process(
            armed.task_id,
            armed.generation,
            attempt.attempt,
            pid=1234,
            pgid=1234,
            process_birth="Mon Aug 17 12:00:00 2026",
        )
    stored = registry.current_attempt(armed.task_id, armed.generation)
    assert stored is not None
    assert stored.state == "starting"
    assert stored.pid is None


def test_rearm_creates_new_generation_without_erasing_cancelled_history(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    first = registry.arm(_grant(workspace))
    registry.cancel(first.task_id, first.generation)

    second = registry.arm(replace(_grant(workspace), starting_sha="b" * 40))

    assert second.generation == 2
    assert second.state == "armed"
    assert registry.get_generation("task-1", 1).state == "cancelled"


def test_stale_generation_cannot_mutate_new_generation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    first = registry.arm(_grant(workspace))
    registry.cancel(first.task_id, first.generation)
    registry.arm(replace(_grant(workspace), starting_sha="b" * 40))

    with pytest.raises(TaskConflict, match="stale_generation"):
        registry.mark_running("task-1", 1)


def test_task_source_drift_blocks_generation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(workspace))
    (workspace / armed.source_path).write_text("Changed task.\n", encoding="utf-8")

    with pytest.raises(TaskConflict, match="task_source_drift"):
        registry.verify_source(armed.task_id, armed.generation)


def test_parent_link_is_projected_and_invalid_parent_is_atomic(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    registry.arm(_grant(workspace, task_id="parent"))

    child = registry.arm(_grant(workspace, task_id="child", parent="parent"))

    assert child.parent_task_id == "parent"
    with pytest.raises(TaskValidationError, match="parent_task_missing"):
        registry.arm(_grant(workspace, task_id="orphan", parent="missing"))
    with pytest.raises(TaskValidationError, match="parent_task_self"):
        registry.arm(_grant(workspace, task_id="self", parent="self"))
    assert {item.task_id for item in registry.list_tasks()} == {"parent", "child"}


def test_safe_projection_omits_task_body_and_rejects_credentials(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    snapshot = registry.arm(_grant(workspace))

    rendered = snapshot.to_dict()

    assert "Implement the task" not in str(rendered)
    assert "source_digest" in rendered
    unsafe = replace(_grant(workspace, task_id="unsafe"), origin_terminal="sk-" + "x" * 24)
    with pytest.raises(TaskValidationError, match="unsafe_task_metadata"):
        registry.arm(unsafe)


def test_verification_contract_requires_commands_or_bounded_no_test_reason(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")

    with pytest.raises(TaskValidationError, match="verification_contract_invalid"):
        registry.arm(
            replace(_grant(workspace), verification_argv=(), no_test_reason=None)
        )

    docs = registry.arm(
        replace(
            _grant(workspace, task_id="docs"),
            verification_argv=(),
            no_test_reason="documentation-only change",
        )
    )
    assert docs.no_test_reason == "documentation-only change"


def test_database_directory_does_not_follow_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    state = tmp_path / "state"
    state.symlink_to(outside, target_is_directory=True)

    with pytest.raises(TaskValidationError, match="registry_parent_symlink"):
        TaskRegistry(state / "tasks.sqlite3")
    assert list(outside.iterdir()) == []
