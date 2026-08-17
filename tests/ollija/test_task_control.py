from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.ollija.adapters.base import AuthorityObservation
from scripts.ollija.agents.base import AgentProbe
from scripts.ollija.config import (
    AuthorityConfig,
    GitConfig,
    ProjectConfig,
    StateConfig,
)
from scripts.ollija.git import CommandOutcome, GitObservation
from scripts.ollija.incidents import record_task_incident
from scripts.ollija.results import CommandResult, NextAction
from scripts.ollija.status import StatusFacts
from scripts.ollija.task_control import (
    GoRequest,
    TaskControlError,
    build_task_status_result,
    go_task,
    task_registry_path,
    with_task_status,
)
from scripts.ollija.tasks import TaskRegistry
from scripts.ollija.workspaces import WorkspaceError


class _Runner:
    def __init__(self, outcome: CommandOutcome) -> None:
        self.outcome = outcome
        self.commands: list[tuple[str, ...]] = []

    def run(self, args, *, cwd: Path, timeout: float = 10):
        self.commands.append(tuple(args))
        return self.outcome


class _Driver:
    kind = "codex"

    def probe(self, workspace: Path) -> AgentProbe:
        return AgentProbe("codex", True, "0.147.0")


def _config(canonical: Path, workspace: Path) -> ProjectConfig:
    return ProjectConfig(
        root=workspace,
        path=workspace / ".ollija" / "project.yaml",
        schema_version=1,
        adapter="pushinweight",
        authority=AuthorityConfig(
            canonical_host="fuchitalee",
            forbidden_hosts=("allenwlee",),
            repository_root=canonical,
            repository_slug="allenwlee/pushin-weight-v2",
        ),
        git=GitConfig(staging_branch="staging", production_branch="main"),
        state=StateConfig(Path(".ollija/state"), 30),
        versioning={},
        environments={},
        database_safety={},
        verification={},
        ui_impact={},
        bridgewright={},
        tooling={},
    )


def _facts(canonical: Path, workspace: Path) -> StatusFacts:
    return StatusFacts(
        authority=AuthorityObservation(
            hostname="fuchitalee",
            repository_root=workspace,
            repository_slug="allenwlee/pushin-weight-v2",
            mutation_allowed=True,
        ),
        git=GitObservation(
            repository_root=workspace,
            head_sha="a" * 40,
            branch="feat/example",
            detached=False,
            registered_worktree=True,
            dirty_paths=(),
            production_sha="a" * 40,
            staging_sha="a" * 40,
            branch_relationship="equal",
            remote_reachable=True,
            repository_slug="allenwlee/pushin-weight-v2",
            common_git_directory=canonical / ".git",
        ),
        lifecycle_state="idle",
        package_version="0.2.0b1",
        checks=(),
    )


def _setup(tmp_path: Path):
    canonical = tmp_path / "repo"
    workspace = canonical / ".worktrees" / "feat" / "example"
    workspace.mkdir(parents=True)
    (canonical / ".git").mkdir()
    python = canonical / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    python.chmod(0o700)
    source = workspace / "docs" / "plans" / "task.md"
    source.parent.mkdir(parents=True)
    source.write_text("Do the work.\n", encoding="utf-8")
    return canonical, workspace


def test_go_arms_exact_workspace_and_launches_one_supervisor(tmp_path: Path) -> None:
    canonical, workspace = _setup(tmp_path)
    launched: list[dict[str, object]] = []

    snapshot = go_task(
        _config(canonical, workspace),
        _facts(canonical, workspace),
        GoRequest(
            task_id="task-1",
            parent_task_id=None,
            source_path="docs/plans/task.md",
            agent_kind="codex",
            endpoint="commit",
            verification_argv=(("pytest", "tests/ollija"),),
            no_test_reason=None,
        ),
        runner=_Runner(CommandOutcome(0, "docs/plans/task.md\n", "")),
        driver=_Driver(),
        launcher=lambda **kwargs: launched.append(kwargs) or "ollija-task-1-g1",
        origin_host="allenwlee",
        origin_terminal="vscode-remote",
        execution_host="fuchitalee",
    )

    assert snapshot.state == "armed"
    assert snapshot.origin_host == "allenwlee"
    assert snapshot.workspace == str(workspace)
    assert len(launched) == 1
    assert launched[0]["workspace"] == workspace
    assert (workspace / ".venv").resolve() == canonical / ".venv"


def test_go_rejects_untracked_source_and_duplicate_active_task(tmp_path: Path) -> None:
    canonical, workspace = _setup(tmp_path)
    config = _config(canonical, workspace)
    facts = _facts(canonical, workspace)
    request = GoRequest(
        task_id="task-1",
        parent_task_id=None,
        source_path="docs/plans/task.md",
        agent_kind="codex",
        endpoint="commit",
        verification_argv=(("pytest",),),
        no_test_reason=None,
    )
    with pytest.raises(TaskControlError, match="task_source_untracked"):
        go_task(
            config,
            facts,
            request,
            runner=_Runner(CommandOutcome(1, "", "missing")),
            driver=_Driver(),
            launcher=lambda **_kwargs: "unused",
        )

    kwargs = {
        "runner": _Runner(CommandOutcome(0, "docs/plans/task.md\n", "")),
        "driver": _Driver(),
        "launcher": lambda **_kwargs: "session",
    }
    go_task(config, facts, request, **kwargs)
    with pytest.raises(Exception, match="active"):
        go_task(config, facts, request, **kwargs)


def test_only_same_terminal_task_can_rearm_its_preserved_dirty_diff(
    tmp_path: Path,
) -> None:
    canonical, workspace = _setup(tmp_path)
    config = _config(canonical, workspace)
    facts = _facts(canonical, workspace)
    request = GoRequest(
        task_id="task-1",
        parent_task_id=None,
        source_path="docs/plans/task.md",
        agent_kind="codex",
        endpoint="commit",
        verification_argv=(("pytest",),),
        no_test_reason=None,
    )
    kwargs = {
        "runner": _Runner(CommandOutcome(0, "docs/plans/task.md\n", "")),
        "driver": _Driver(),
        "launcher": lambda **_kwargs: "session",
    }
    first = go_task(config, facts, request, **kwargs)
    registry = TaskRegistry(task_registry_path(config))
    registry.pause(first.task_id, first.generation, failure_code="verification_failed")
    dirty_facts = StatusFacts(
        authority=facts.authority,
        git=replace(facts.git, dirty_paths=("feature.py",)),
        lifecycle_state=facts.lifecycle_state,
        package_version=facts.package_version,
        checks=facts.checks,
    )

    recovered = go_task(config, dirty_facts, request, **kwargs)

    assert recovered.generation == 2
    assert recovered.state == "armed"

    fresh = replace(request, task_id="task-2")
    with pytest.raises(WorkspaceError, match="dirty"):
        go_task(config, dirty_facts, fresh, **kwargs)


def test_task_status_is_read_only_and_reports_one_next_action(tmp_path: Path) -> None:
    canonical, workspace = _setup(tmp_path)
    config = _config(canonical, workspace)

    empty = build_task_status_result(config, task_id=None)
    assert empty.status == "ok"
    assert empty.state == "idle"
    assert not config.state_root.exists()

    go_task(
        config,
        _facts(canonical, workspace),
        GoRequest(
            task_id="task-1",
            parent_task_id=None,
            source_path="docs/plans/task.md",
            agent_kind="codex",
            endpoint="commit",
            verification_argv=(("pytest",),),
            no_test_reason=None,
        ),
        runner=_Runner(CommandOutcome(0, "", "")),
        driver=_Driver(),
        launcher=lambda **_kwargs: "session",
    )
    result = build_task_status_result(config, task_id="task-1")

    assert result.status == "ok"
    assert result.state == "armed"
    assert result.next_action is not None
    assert result.next_action.command == "ollija task-status task-1"
    assert result.details["task"]["restart_budget"] == 1

    combined = with_task_status(
        CommandResult(
            command="status",
            status="blocked",
            state="blocked",
            summary="release workflow is dirty",
            next_action=NextAction("ollija doctor", "clean the release tree"),
        ),
        config,
    )
    assert combined.status == "ok"
    assert combined.state == "armed"
    assert combined.next_action.command == "ollija task-status task-1"
    assert combined.details["release_state"] == "blocked"


def test_canonical_checkout_and_worktree_share_task_history(tmp_path: Path) -> None:
    canonical, workspace = _setup(tmp_path)
    worktree_config = _config(canonical, workspace)
    root_config = _config(canonical, canonical)
    go_task(
        worktree_config,
        _facts(canonical, workspace),
        GoRequest(
            task_id="task-1",
            parent_task_id=None,
            source_path="docs/plans/task.md",
            agent_kind="codex",
            endpoint="commit",
            verification_argv=(("pytest",),),
            no_test_reason=None,
        ),
        runner=_Runner(CommandOutcome(0, "docs/plans/task.md\n", "")),
        driver=_Driver(),
        launcher=lambda **_kwargs: "session",
    )

    assert task_registry_path(worktree_config) == task_registry_path(root_config)
    root_view = build_task_status_result(root_config, task_id="task-1")
    assert root_view.state == "armed"
    assert root_view.details["task"]["workspace"] == str(workspace)


def test_paused_task_status_routes_failure_and_projects_safe_incident(
    tmp_path: Path,
) -> None:
    canonical, workspace = _setup(tmp_path)
    config = _config(canonical, workspace)
    go_task(
        config,
        _facts(canonical, workspace),
        GoRequest(
            task_id="task-1",
            parent_task_id=None,
            source_path="docs/plans/task.md",
            agent_kind="codex",
            endpoint="commit",
            verification_argv=(("pytest",),),
            no_test_reason=None,
        ),
        runner=_Runner(CommandOutcome(0, "", "")),
        driver=_Driver(),
        launcher=lambda **_kwargs: "session",
    )
    registry = TaskRegistry(task_registry_path(config))
    paused = registry.pause(
        "task-1",
        1,
        failure_code="verification_failed",
    )
    record_task_incident(
        registry,
        paused,
        phase="checkpoint.verify",
    )

    result = build_task_status_result(config, task_id="task-1")

    assert result.next_action is not None
    assert result.next_action.command == "ce-debug"
    assert result.details["incidents"][0]["routes"] == [
        "ce-debug",
        "ce-compound",
    ]
