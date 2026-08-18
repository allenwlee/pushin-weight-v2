from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .changes import (
    ChangeLedgerError,
    load_change_ledger_baseline,
    require_ollija_change_ledger,
)
from .git import CommandRunner, SubprocessRunner
from .incidents import record_task_incident
from .tasks import TaskConflict, TaskRegistry, TaskSnapshot, TaskValidationError


class CheckpointError(ValueError):
    """Ollija could not produce or advance a verified checkpoint."""


@dataclass(frozen=True, slots=True)
class ReleaseObservation:
    status: str
    state: str
    candidate_sha: str | None = None


ReleaseExecutor = Callable[[tuple[str, ...]], ReleaseObservation]
ProductionTail = Callable[..., TaskSnapshot]


def _pause(
    registry: TaskRegistry,
    task_id: str,
    generation: int,
    *,
    code: str,
    phase: str,
) -> TaskSnapshot:
    snapshot = registry.pause(task_id, generation, failure_code=code)
    record_task_incident(
        registry,
        snapshot,
        phase=phase,
        attempt=registry.current_attempt(task_id, generation),
    )
    return snapshot


def _run(
    runner: CommandRunner,
    workspace: Path,
    args: tuple[str, ...],
    *,
    timeout: float = 60,
):
    return runner.run(args, cwd=workspace, timeout=timeout)


def _git(
    runner: CommandRunner,
    workspace: Path,
    *args: str,
    timeout: float = 60,
):
    return _run(runner, workspace, ("git", *args), timeout=timeout)


def _changed_paths(runner: CommandRunner, workspace: Path) -> tuple[str, ...]:
    changed = _git(runner, workspace, "diff", "--name-only", "-z", "HEAD")
    untracked = _git(
        runner,
        workspace,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    if changed.returncode != 0 or untracked.returncode != 0:
        raise CheckpointError("task_diff_unavailable")
    paths = {
        item
        for output in (changed.stdout, untracked.stdout)
        for item in output.split("\0")
        if item
    }
    for path in paths:
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise CheckpointError("task_diff_path_invalid")
    return tuple(sorted(paths))


def _documentation_only(paths: tuple[str, ...]) -> bool:
    return bool(paths) and all(
        path.startswith("docs/")
        or ("/" not in path and path.casefold().endswith((".md", ".rst", ".txt")))
        for path in paths
    )


def _default_release_executor(workspace: Path) -> ReleaseExecutor:
    executable = workspace / "bin" / "ollija"

    def execute(command: tuple[str, ...]) -> ReleaseObservation:
        environment = dict(os.environ)
        environment["OLLIJA_RELEASE_ONLY"] = "1"
        completed = subprocess.run(
            [str(executable), *command, "--json"],
            cwd=workspace,
            env=environment,
            text=True,
            capture_output=True,
            timeout=3600,
            check=False,
        )
        try:
            body = json.loads(completed.stdout.strip().splitlines()[-1])
            details = body.get("details")
            git_details = details.get("git") if isinstance(details, dict) else None
            head_sha = git_details.get("head_sha") if isinstance(git_details, dict) else None
            evidence = body.get("evidence")
            candidate_shas = {
                item.get("candidate_sha")
                for item in evidence
                if isinstance(item, dict) and item.get("candidate_sha")
            } if isinstance(evidence, list) else set()
            candidate_sha = head_sha if isinstance(head_sha, str) and head_sha else None
            if candidate_sha is None and len(candidate_shas) == 1:
                candidate_sha = next(iter(candidate_shas))
            return ReleaseObservation(
                str(body["status"]),
                str(body["state"]),
                candidate_sha,
            )
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise CheckpointError("release_command_output_invalid") from exc

    return execute


def _execute_or_pause(
    registry: TaskRegistry,
    task_id: str,
    generation: int,
    executor: ReleaseExecutor,
    command: tuple[str, ...],
) -> TaskSnapshot | None:
    observation = executor(command)
    if observation.status == "ok":
        return None
    return _pause(
        registry,
        task_id,
        generation,
        code=f"release_tail_{command[0]}_failed",
        phase=f"release.{command[0]}",
    )


def run_production_tail(
    registry: TaskRegistry,
    task_id: str,
    generation: int,
    *,
    outcome_sha: str,
    executor: ReleaseExecutor | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> TaskSnapshot:
    task = registry.get_generation(task_id, generation)
    active_executor = executor or _default_release_executor(Path(task.workspace))
    assessment_recorded = False
    while True:
        current = registry.get(task_id)
        if current.state == "cancelled":
            return current
        status = active_executor(("status",))
        if status.status != "ok":
            return _pause(
                registry,
                task_id,
                generation,
                code="release_tail_status_failed",
                phase="release.status",
            )
        if status.candidate_sha != outcome_sha:
            return _pause(
                registry,
                task_id,
                generation,
                code="release_tail_candidate_mismatch",
                phase="release.identity",
            )
        command: tuple[str, ...] | None
        if status.state == "idle":
            command = ("start",)
        elif status.state == "candidate":
            command = ("refresh-local",)
        elif status.state == "local_refreshed":
            command = ("refresh-staging",)
        elif status.state == "ready_to_stage":
            command = ("stage",)
        elif status.state == "staged" and not assessment_recorded:
            command = ("assess-ui",)
            assessment_recorded = True
        elif status.state == "staged":
            registry.mark_awaiting_approval(task_id, generation)
            sleep(10)
            continue
        elif status.state == "approved":
            registry.mark_releasing(task_id, generation)
            command = ("release",)
        elif status.state == "releasing":
            command = ("verify-production",)
        elif status.state == "verified":
            return registry.complete(
                task_id, generation, outcome_sha=outcome_sha
            )
        else:
            return _pause(
                registry,
                task_id,
                generation,
                code=f"release_tail_state_{status.state}",
                phase="release.state",
            )
        failed = _execute_or_pause(
            registry, task_id, generation, active_executor, command
        )
        if failed is not None:
            return failed


def checkpoint_task(
    registry: TaskRegistry,
    task_id: str,
    generation: int,
    *,
    runner: CommandRunner | None = None,
    production_tail: ProductionTail = run_production_tail,
) -> TaskSnapshot:
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
            phase="checkpoint.source",
        )
    workspace = Path(task.workspace)
    active_runner = runner or SubprocessRunner()
    head = _git(active_runner, workspace, "rev-parse", "HEAD")
    if head.returncode != 0:
        return _pause(
            registry,
            task_id,
            generation,
            code="git_head_unavailable",
            phase="checkpoint.git",
        )
    if head.stdout.strip() != task.starting_sha:
        return _pause(
            registry,
            task_id,
            generation,
            code="agent_advanced_branch",
            phase="checkpoint.identity",
        )
    try:
        paths = _changed_paths(active_runner, workspace)
    except CheckpointError as exc:
        return _pause(
            registry,
            task_id,
            generation,
            code=str(exc),
            phase="checkpoint.diff",
        )
    if not paths:
        return _pause(
            registry,
            task_id,
            generation,
            code="task_diff_missing",
            phase="checkpoint.diff",
        )
    if task.no_test_reason and not _documentation_only(paths):
        return _pause(
            registry,
            task_id,
            generation,
            code="verification_required_for_behavior_change",
            phase="checkpoint.verify",
        )
    try:
        baseline_text = load_change_ledger_baseline(
            workspace,
            task.starting_sha,
            runner=active_runner,
        )
        require_ollija_change_ledger(
            workspace,
            paths,
            baseline_text=baseline_text,
        )
    except ChangeLedgerError as exc:
        return _pause(
            registry,
            task_id,
            generation,
            code=str(exc),
            phase="checkpoint.change_ledger",
        )
    for command in task.verification_argv:
        result = _run(active_runner, workspace, command, timeout=3600)
        if result.returncode != 0:
            return _pause(
                registry,
                task_id,
                generation,
                code="verification_failed",
                phase="checkpoint.verify",
            )
    registry.mark_committing(task_id, generation)
    staged = _git(active_runner, workspace, "add", "--all", "--", *paths)
    if staged.returncode != 0:
        return _pause(
            registry,
            task_id,
            generation,
            code="git_stage_failed",
            phase="checkpoint.stage",
        )
    message = f"chore(ollija): complete {task.task_id}"
    committed = _git(
        active_runner,
        workspace,
        "commit",
        "-m",
        message,
        "--",
        *paths,
        timeout=120,
    )
    if committed.returncode != 0:
        return _pause(
            registry,
            task_id,
            generation,
            code="git_commit_failed",
            phase="checkpoint.commit",
        )
    final = _git(active_runner, workspace, "rev-parse", "HEAD")
    status = _git(active_runner, workspace, "status", "--porcelain=v1", "-z")
    outcome_sha = final.stdout.strip()
    if final.returncode != 0 or status.returncode != 0 or status.stdout:
        return _pause(
            registry,
            task_id,
            generation,
            code="checkpoint_not_clean",
            phase="checkpoint.verify",
        )
    if outcome_sha == task.starting_sha:
        return _pause(
            registry,
            task_id,
            generation,
            code="checkpoint_sha_unchanged",
            phase="checkpoint.identity",
        )
    registry.record_checkpoint(task_id, generation, outcome_sha=outcome_sha)
    if task.endpoint == "commit":
        return registry.complete(task_id, generation, outcome_sha=outcome_sha)
    return production_tail(
        registry,
        task_id,
        generation,
        outcome_sha=outcome_sha,
    )
