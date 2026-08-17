from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .agents.base import AgentDriver
from .agents.claude import ClaudeDriver
from .config import ProjectConfig
from .git import CommandRunner
from .incidents import IncidentStore, guidance_for_failure, record_task_incident
from .processes import start_detached_supervisor, stop_task_processes
from .results import CommandResult, NextAction
from .status import StatusFacts
from .tasks import (
    TaskGrant,
    TaskRegistry,
    TaskSnapshot,
    TaskValidationError,
    digest_task_source,
)
from .workspaces import prepare_runtime_links, validate_task_workspace


class TaskControlError(ValueError):
    """A task-control request failed before or during its bounded transition."""


@dataclass(frozen=True, slots=True)
class GoRequest:
    task_id: str
    parent_task_id: str | None
    source_path: str
    agent_kind: str
    endpoint: str
    verification_argv: tuple[tuple[str, ...], ...]
    no_test_reason: str | None


SupervisorLauncher = Callable[..., str]


def task_registry_path(config: ProjectConfig) -> Path:
    return config.state_root / "tasks.sqlite3"


def go_task(
    config: ProjectConfig,
    facts: StatusFacts,
    request: GoRequest,
    *,
    runner: CommandRunner,
    driver: AgentDriver,
    launcher: SupervisorLauncher = start_detached_supervisor,
    origin_host: str = "fuchitalee",
    origin_terminal: str = "unknown",
    execution_host: str = "fuchitalee",
) -> TaskSnapshot:
    if not facts.authority.mutation_allowed:
        raise TaskControlError("task_authority_blocked")
    source = Path(request.source_path)
    if source.is_absolute() or ".." in source.parts:
        raise TaskControlError("task_source_path_invalid")
    source_digest = digest_task_source(
        facts.git.repository_root,
        request.source_path,
    )
    existing_registry = TaskRegistry.open_if_exists(task_registry_path(config))
    prior = None
    if existing_registry is not None:
        try:
            prior = existing_registry.get(request.task_id)
        except TaskValidationError as exc:
            if str(exc) != "task_missing":
                raise
    recoverable = bool(
        prior is not None
        and prior.state in {"paused", "cancelled", "lost", "failed"}
        and prior.workspace == str(facts.git.repository_root.resolve())
        and prior.branch == facts.git.branch
        and prior.source_path == request.source_path
        and prior.source_digest == source_digest
    )
    workspace = validate_task_workspace(
        config,
        facts.git,
        allow_dirty_recovery=recoverable,
    )
    tracked = runner.run(
        ("git", "ls-files", "--error-unmatch", "--", request.source_path),
        cwd=workspace,
        timeout=10,
    )
    if tracked.returncode != 0:
        raise TaskControlError("task_source_untracked")
    if request.agent_kind != driver.kind:
        raise TaskControlError("task_agent_driver_mismatch")
    probe = driver.probe(workspace)
    if not probe.available or probe.version is None:
        raise TaskControlError(probe.reason or "task_agent_unavailable")
    prepare_runtime_links(config)
    registry = existing_registry or TaskRegistry(task_registry_path(config))
    snapshot = registry.arm(
        TaskGrant(
            task_id=request.task_id,
            parent_task_id=request.parent_task_id,
            source_path=request.source_path,
            source_digest=source_digest,
            workspace=workspace,
            branch=str(facts.git.branch),
            starting_sha=str(facts.git.head_sha),
            agent_kind=request.agent_kind,
            agent_version=probe.version,
            agent_session_id=None,
            origin_host=origin_host,
            origin_terminal=origin_terminal,
            execution_host=execution_host,
            endpoint=request.endpoint,
            verification_argv=request.verification_argv,
            no_test_reason=request.no_test_reason,
            restart_budget=1,
        )
    )
    if request.agent_kind == "claude":
        snapshot = registry.record_agent_session(
            snapshot.task_id,
            snapshot.generation,
            ClaudeDriver.session_id(snapshot),
        )
    try:
        launcher(
            registry_path=registry.path,
            task_id=snapshot.task_id,
            generation=snapshot.generation,
            python_executable=config.canonical_virtualenv / "bin" / "python",
            workspace=workspace,
        )
    except Exception as exc:
        paused = registry.pause(
            snapshot.task_id,
            snapshot.generation,
            failure_code="supervisor_launch_failed",
        )
        record_task_incident(
            registry,
            paused,
            phase="supervisor.launch",
        )
        raise TaskControlError("supervisor_launch_failed") from exc
    return registry.get(snapshot.task_id)


def stop_task(config: ProjectConfig, facts: StatusFacts, task_id: str) -> TaskSnapshot:
    if not facts.authority.mutation_allowed:
        raise TaskControlError("task_authority_blocked")
    registry = TaskRegistry.open_if_exists(task_registry_path(config))
    if registry is None:
        raise TaskControlError("task_registry_missing")
    current = registry.get(task_id)
    return stop_task_processes(registry, task_id, current.generation)


def _next_action(task: TaskSnapshot) -> NextAction:
    if task.state in {"armed", "running", "restarting", "committing", "releasing"}:
        return NextAction(
            f"ollija task-status {task.task_id}",
            "Observe this generation; status does not renew its grant.",
        )
    if task.state == "awaiting_approval":
        return NextAction("ollija status", "Complete the reported owner approval.")
    if task.state in {"paused", "lost", "failed"} and task.failure_code:
        guidance = guidance_for_failure(task.failure_code)
        return NextAction(
            guidance.routes[0],
            "Diagnose the preserved failure, then explicitly re-arm with ollija go.",
        )
    if task.state == "cancelled":
        return NextAction(
            "ollija go --help",
            "Inspect preserved work, then explicitly re-arm a new generation.",
        )
    return NextAction("ollija status", "Continue from the verified task outcome.")


def build_task_status_result(
    config: ProjectConfig, *, task_id: str | None
) -> CommandResult:
    registry = TaskRegistry.open_if_exists(task_registry_path(config))
    if registry is None:
        return CommandResult(
            command="task-status",
            status="ok",
            state="idle",
            summary="No Ollija task generations have been armed.",
            next_action=NextAction("ollija go --help", "Arm one bounded task."),
            details={"tasks": []},
        )
    tasks = registry.list_tasks()
    active = tuple(
        task
        for task in tasks
        if task.state not in {"succeeded", "failed", "cancelled", "lost", "paused"}
    )
    selected = (
        registry.get(task_id)
        if task_id
        else max(active or tasks, key=lambda task: task.updated_at, default=None)
    )
    if selected is None:
        return CommandResult(
            command="task-status",
            status="ok",
            state="idle",
            summary="No Ollija task generations have been armed.",
            next_action=NextAction("ollija go --help", "Arm one bounded task."),
            details={"tasks": []},
        )
    attempt = registry.current_attempt(selected.task_id, selected.generation)
    incidents = IncidentStore(registry.path.parent).for_task(selected.task_id)
    return CommandResult(
        command="task-status",
        status="ok",
        state=selected.state,
        summary=(
            f"Task {selected.task_id} generation {selected.generation} "
            f"is {selected.state}."
        ),
        next_action=_next_action(selected),
        details={
            "task": selected.to_dict(),
            "attempt": attempt.to_dict() if attempt else None,
            "incidents": [incident.to_dict() for incident in incidents],
            "tasks": [task.to_dict() for task in tasks],
        },
    )


def task_command_result(command: str, snapshot: TaskSnapshot) -> CommandResult:
    return CommandResult(
        command=command,
        status="ok",
        state=snapshot.state,
        summary=(
            f"Task {snapshot.task_id} generation {snapshot.generation} "
            f"is {snapshot.state}."
        ),
        next_action=_next_action(snapshot),
        details={"task": snapshot.to_dict()},
    )


def with_task_status(base: CommandResult, config: ProjectConfig) -> CommandResult:
    """Add task truth to ordinary status without creating registry state."""

    registry = TaskRegistry.open_if_exists(task_registry_path(config))
    if registry is None:
        return base
    tasks = registry.list_tasks()
    active = max(
        (
            task
            for task in tasks
            if task.state
            in {"armed", "running", "restarting", "committing", "awaiting_approval", "releasing"}
        ),
        key=lambda task: task.updated_at,
        default=None,
    )
    details = {**base.details, "tasks": [task.to_dict() for task in tasks]}
    if active is None:
        return replace(base, details=details)
    attempt = registry.current_attempt(active.task_id, active.generation)
    incidents = IncidentStore(registry.path.parent).for_task(active.task_id)
    details.update(
        {
            "task": active.to_dict(),
            "attempt": attempt.to_dict() if attempt else None,
            "incidents": [incident.to_dict() for incident in incidents],
            "release_state": base.state,
        }
    )
    warnings = base.warnings
    if base.status != "ok":
        warnings = (*warnings, f"release_workflow: {base.summary}")
    return CommandResult(
        command="status",
        status="ok",
        state=active.state,
        summary=(
            f"Task {active.task_id} generation {active.generation} "
            f"is {active.state}."
        ),
        next_action=_next_action(active),
        evidence=base.evidence,
        warnings=warnings,
        details=details,
    )
