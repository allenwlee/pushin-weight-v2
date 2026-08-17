from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from .incidents import record_task_incident
from .processes import observe_process
from .tasks import (
    AttemptSnapshot,
    TaskConflict,
    TaskRegistry,
    TaskSnapshot,
    TaskValidationError,
)

CommandFactory = Callable[[TaskSnapshot, AttemptSnapshot], Sequence[str]]
ReadyHandler = Callable[[TaskRegistry, str, int], None]


def _pause(
    registry: TaskRegistry,
    task_id: str,
    generation: int,
    *,
    code: str,
    phase: str,
    attempt: AttemptSnapshot | None = None,
) -> TaskSnapshot:
    snapshot = registry.pause(task_id, generation, failure_code=code)
    record_task_incident(
        registry,
        snapshot,
        phase=phase,
        attempt=attempt,
    )
    return snapshot


def _log_path(registry: TaskRegistry, task_id: str) -> Path:
    return registry.path.parent / "logs" / "tasks" / f"{task_id}.log"


def _append_event(registry: TaskRegistry, task_id: str, event: str, **details: object) -> None:
    path = _log_path(registry, task_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.exists() and path.stat().st_size >= 60_000:
        path.write_text("", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(json.dumps({"event": event, **details}, sort_keys=True) + "\n")


def _observe_started_process(pid: int, timeout: float = 1) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        identity = observe_process(pid)
        if identity is not None:
            return identity
        time.sleep(0.01)
    raise TaskConflict("child_process_identity_unavailable")


def run_supervisor(
    registry: TaskRegistry,
    task_id: str,
    generation: int,
    *,
    command_factory: CommandFactory,
    on_ready: ReadyHandler,
    after_attempt: Callable[[], None] | None = None,
) -> TaskSnapshot:
    while True:
        try:
            task = registry.verify_source(task_id, generation)
        except (TaskConflict, TaskValidationError) as exc:
            if str(exc) not in {"task_source_drift", "task_source_missing"}:
                raise
            return _pause(
                registry,
                task_id,
                generation,
                code="task_source_drift",
                phase="supervisor.source",
            )
        attempt = registry.start_attempt(
            task_id,
            generation,
            driver_session_id=task.agent_session_id,
        )
        command = tuple(str(item) for item in command_factory(task, attempt))
        if not command or any(not item for item in command):
            return _pause(
                registry,
                task_id,
                generation,
                code="agent_command_invalid",
                phase="agent.command",
                attempt=attempt,
            )
        _append_event(registry, task_id, "attempt_started", attempt=attempt.attempt)
        try:
            process = subprocess.Popen(
                command,
                cwd=task.workspace,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return _pause(
                registry,
                task_id,
                generation,
                code="agent_launch_failed",
                phase="agent.launch",
                attempt=attempt,
            )
        try:
            identity = _observe_started_process(process.pid)
        except TaskConflict:
            process.terminate()
            process.wait(timeout=5)
            return _pause(
                registry,
                task_id,
                generation,
                code="child_process_identity_unavailable",
                phase="supervisor.process_identity",
                attempt=attempt,
            )
        registry.record_process(
            task_id,
            generation,
            attempt.attempt,
            pid=identity.pid,
            pgid=identity.pgid,
            process_birth=identity.birth,
        )
        exit_code = process.wait()
        classification = "completed" if exit_code == 0 else "unexpected_exit"
        registry.finish_attempt(
            task_id,
            generation,
            attempt.attempt,
            exit_code=exit_code,
            classification=classification,
        )
        _append_event(
            registry,
            task_id,
            "attempt_finished",
            attempt=attempt.attempt,
            exit_code=exit_code,
        )
        if after_attempt is not None:
            after_attempt()
        current = registry.get(task_id)
        if current.state == "cancelled":
            return current
        if exit_code == 0:
            try:
                on_ready(registry, task_id, generation)
            except Exception:  # noqa: BLE001 - contain arbitrary checkpoint adapters
                return _pause(
                    registry,
                    task_id,
                    generation,
                    code="checkpoint_unhandled",
                    phase="checkpoint.unhandled",
                    attempt=registry.current_attempt(task_id, generation),
                )
            return registry.get(task_id)
        try:
            retry = registry.consume_restart(task_id, generation)
        except TaskConflict:
            return registry.get(task_id)
        if retry.state != "restarting":
            record_task_incident(
                registry,
                retry,
                phase="agent.restart",
                attempt=registry.current_attempt(task_id, generation),
            )
            return retry


def reconcile_missing_supervisor(
    registry: TaskRegistry,
    task_id: str,
    generation: int,
    *,
    process_alive: Callable[[AttemptSnapshot], bool],
) -> str:
    current = registry.get(task_id)
    if current.generation != generation:
        raise TaskConflict("stale_generation")
    if current.state in {"succeeded", "failed", "cancelled", "lost", "paused"}:
        return current.state
    attempt = registry.current_attempt(task_id, generation)
    if attempt is not None and process_alive(attempt):
        return "owned_child_alive"
    lost = registry.mark_lost(task_id, generation)
    record_task_incident(
        registry,
        lost,
        phase="supervisor.reconcile",
        attempt=attempt,
    )
    return lost.state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.ollija.supervisor")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--generation", type=int, required=True)
    args = parser.parse_args(argv)
    registry = TaskRegistry(args.registry)
    try:
        from .agents.registry import command_for_attempt
        from .checkpoint import checkpoint_task
    except ImportError:
        _pause(
            registry,
            args.task,
            args.generation,
            code="supervisor_driver_unavailable",
            phase="supervisor.import",
        )
        return 2
    result = run_supervisor(
        registry,
        args.task,
        args.generation,
        command_factory=command_for_attempt,
        on_ready=checkpoint_task,
    )
    return 0 if result.state == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
