from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from scripts.ollija.checkpoint import (
    ReleaseObservation,
    checkpoint_task,
    run_production_tail,
)
from scripts.ollija.incidents import IncidentStore
from scripts.ollija.tasks import TaskRegistry
from tests.ollija.change_ledger_helpers import LEDGER_TEXT, write_ledger
from tests.ollija.test_tasks import _grant


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
    endpoint: str = "commit",
    verification_exit: int = 0,
    with_ledger: bool = False,
    no_test_reason: str | None = None,
):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "feat/task-1")
    _git(root, "config", "user.name", "Ollija Test")
    _git(root, "config", "user.email", "ollija@example.invalid")
    source = root / "docs" / "plans" / "task.md"
    source.parent.mkdir(parents=True)
    source.write_text("Implement the task.\n", encoding="utf-8")
    if with_ledger:
        write_ledger(root)
    _git(root, "add", "--all")
    _git(root, "commit", "-m", "initial")
    starting_sha = _git(root, "rev-parse", "HEAD")
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    grant = replace(
        _grant(root),
        starting_sha=starting_sha,
        endpoint=endpoint,
        verification_argv=()
        if no_test_reason is not None
        else ((sys.executable, "-c", f"raise SystemExit({verification_exit})"),),
        no_test_reason=no_test_reason,
    )
    armed = registry.arm(grant)
    registry.mark_running(armed.task_id, armed.generation)
    return root, registry, armed


def test_ollija_runs_gates_and_creates_commit_from_agent_diff(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path)
    (root / "feature.txt").write_text("ready\n", encoding="utf-8")

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "succeeded"
    assert result.outcome_sha == _git(root, "rev-parse", "HEAD")
    assert result.outcome_sha != armed.starting_sha
    assert _git(root, "status", "--porcelain") == ""
    assert _git(root, "show", "--format=", "--name-only", "HEAD") == "feature.txt"


def test_failing_gate_preserves_uncommitted_diff(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path, verification_exit=7)
    (root / "feature.txt").write_text("ready\n", encoding="utf-8")

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "paused"
    assert result.failure_code == "verification_failed"
    assert _git(root, "rev-parse", "HEAD") == armed.starting_sha
    assert "feature.txt" in _git(root, "status", "--porcelain")
    incidents = IncidentStore(registry.path.parent).for_task(armed.task_id)
    assert incidents[-1].phase == "checkpoint.verify"
    assert incidents[-1].routes == ("ce-debug", "ce-compound")


def test_zero_exit_without_task_diff_is_incomplete(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path)

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "paused"
    assert result.failure_code == "task_diff_missing"
    assert _git(root, "rev-parse", "HEAD") == armed.starting_sha


def test_ollija_change_without_ledger_pauses_and_preserves_diff(
    tmp_path: Path,
) -> None:
    root, registry, armed = _repository(tmp_path)
    implementation = root / "scripts" / "ollija" / "example.py"
    implementation.parent.mkdir(parents=True)
    implementation.write_text("ENFORCED = True\n", encoding="utf-8")

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "paused"
    assert result.failure_code == "ollija_change_ledger_missing"
    assert _git(root, "rev-parse", "HEAD") == armed.starting_sha
    assert "scripts/ollija/example.py" in _git(
        root,
        "status",
        "--porcelain",
        "--untracked-files=all",
    )


def test_ollija_change_with_ledger_can_reach_checkpoint(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path)
    implementation = root / "scripts" / "ollija" / "example.py"
    implementation.parent.mkdir(parents=True)
    implementation.write_text("ENFORCED = True\n", encoding="utf-8")
    write_ledger(root)

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "succeeded"
    assert _git(root, "status", "--porcelain") == ""
    assert _git(root, "show", "--format=", "--name-only", "HEAD").splitlines() == [
        "docs/ollija/CHANGES.md",
        "scripts/ollija/example.py",
    ]


def test_no_test_reason_allows_documentation_only_diff(tmp_path: Path) -> None:
    root, registry, armed = _repository(
        tmp_path,
        no_test_reason="documentation-only change",
    )
    note = root / "docs" / "ollija" / "operator-note.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("Documented behavior.\n", encoding="utf-8")

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "succeeded"


def test_no_test_reason_rejects_behavior_diff(tmp_path: Path) -> None:
    root, registry, armed = _repository(
        tmp_path,
        with_ledger=True,
        no_test_reason="documentation-only change",
    )
    implementation = root / "scripts" / "ollija" / "example.py"
    implementation.parent.mkdir(parents=True, exist_ok=True)
    implementation.write_text("ENFORCED = True\n", encoding="utf-8")
    write_ledger(
        root,
        LEDGER_TEXT
        + "\n"
        + """

## 2026-08-18 — Behavior change

Type: Fix

Problem: Behavior changed without verification.

New behavior: The changed behavior is tested.

Proof: `pytest tests/ollija`

Release impact: No production effect.
""",
    )

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "paused"
    assert result.failure_code == "verification_required_for_behavior_change"


def test_production_tail_pause_preserves_checkpoint_sha(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path, endpoint="production")
    (root / "feature.txt").write_text("ready\n", encoding="utf-8")

    def failing_tail(registry, task_id, generation, *, outcome_sha):
        assert outcome_sha == _git(root, "rev-parse", "HEAD")
        return registry.pause(task_id, generation, failure_code="tail_failed")

    result = checkpoint_task(
        registry,
        armed.task_id,
        armed.generation,
        production_tail=failing_tail,
    )

    assert result.state == "paused"
    assert result.outcome_sha == _git(root, "rev-parse", "HEAD")


def test_checkpoint_requires_entry_newer_than_task_start(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path, with_ledger=True)
    implementation = root / "scripts" / "ollija" / "example.py"
    implementation.parent.mkdir(parents=True)
    implementation.write_text("ENFORCED = True\n", encoding="utf-8")
    write_ledger(root, LEDGER_TEXT.replace("This concise", "This short"))

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "paused"
    assert result.failure_code == "ollija_change_ledger_invalid"
    assert _git(root, "rev-parse", "HEAD") == armed.starting_sha


def test_agent_created_commit_is_paused_and_never_adopted(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path)
    (root / "feature.txt").write_text("agent committed\n", encoding="utf-8")
    _git(root, "add", "feature.txt")
    _git(root, "commit", "-m", "agent commit")

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "paused"
    assert result.failure_code == "agent_advanced_branch"
    assert result.outcome_sha is None


def test_changed_task_source_pauses_and_preserves_diff(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path)
    source = root / armed.source_path
    source.write_text("Changed task authority.\n", encoding="utf-8")
    (root / "feature.txt").write_text("ready\n", encoding="utf-8")

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "paused"
    assert result.failure_code == "task_source_drift"
    assert _git(root, "rev-parse", "HEAD") == armed.starting_sha
    assert "feature.txt" in _git(root, "status", "--porcelain")


def test_missing_task_source_pauses_without_committing(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path)
    (root / armed.source_path).unlink()
    (root / "feature.txt").write_text("ready\n", encoding="utf-8")

    result = checkpoint_task(registry, armed.task_id, armed.generation)

    assert result.state == "paused"
    assert result.failure_code == "task_source_drift"
    assert _git(root, "rev-parse", "HEAD") == armed.starting_sha


class _ReleaseExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.states = iter(
            [
                "candidate",
                "local_refreshed",
                "ready_to_stage",
                "staged",
                "staged",
                "approved",
                "releasing",
                "verified",
            ]
        )

    def __call__(self, command: tuple[str, ...]) -> ReleaseObservation:
        self.calls.append(command)
        if command == ("status",):
            return ReleaseObservation("ok", next(self.states), "b" * 40)
        return ReleaseObservation("ok", "ok", "b" * 40)


def test_production_tail_waits_for_approval_then_continues_green_steps(
    tmp_path: Path,
) -> None:
    _root, registry, armed = _repository(tmp_path, endpoint="production")
    registry.mark_committing(armed.task_id, armed.generation)
    executor = _ReleaseExecutor()
    sleeps: list[float] = []

    result = run_production_tail(
        registry,
        armed.task_id,
        armed.generation,
        outcome_sha="b" * 40,
        executor=executor,
        sleep=lambda seconds: sleeps.append(seconds),
    )

    assert result.state == "succeeded"
    assert ("refresh-local",) in executor.calls
    assert ("refresh-staging",) in executor.calls
    assert ("stage",) in executor.calls
    assert ("assess-ui",) in executor.calls
    assert ("release",) in executor.calls
    assert ("verify-production",) in executor.calls
    assert sleeps == [10]


def test_commit_endpoint_never_calls_production_tail(tmp_path: Path) -> None:
    root, registry, armed = _repository(tmp_path)
    (root / "feature.txt").write_text("ready\n", encoding="utf-8")

    result = checkpoint_task(
        registry,
        armed.task_id,
        armed.generation,
        production_tail=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("production tail must not run")
        ),
    )

    assert result.state == "succeeded"


def test_live_but_unsealed_production_resumes_verification_not_release(
    tmp_path: Path,
) -> None:
    _root, registry, armed = _repository(tmp_path, endpoint="production")
    registry.mark_committing(armed.task_id, armed.generation)
    calls: list[tuple[str, ...]] = []
    states = iter(("releasing", "verified"))

    def executor(command: tuple[str, ...]) -> ReleaseObservation:
        calls.append(command)
        if command == ("status",):
            return ReleaseObservation("ok", next(states), "b" * 40)
        return ReleaseObservation("ok", "ok", "b" * 40)

    result = run_production_tail(
        registry,
        armed.task_id,
        armed.generation,
        outcome_sha="b" * 40,
        executor=executor,
        sleep=lambda _seconds: None,
    )

    assert result.state == "succeeded"
    assert ("verify-production",) in calls
    assert ("release",) not in calls


def test_production_tail_freezes_idle_checkpoint_before_refresh(
    tmp_path: Path,
) -> None:
    _root, registry, armed = _repository(tmp_path, endpoint="production")
    registry.mark_committing(armed.task_id, armed.generation)
    calls: list[tuple[str, ...]] = []
    states = iter(("idle", "verified"))

    def executor(command: tuple[str, ...]) -> ReleaseObservation:
        calls.append(command)
        state = next(states) if command == ("status",) else "ok"
        return ReleaseObservation("ok", state, "b" * 40)

    result = run_production_tail(
        registry,
        armed.task_id,
        armed.generation,
        outcome_sha="b" * 40,
        executor=executor,
        sleep=lambda _seconds: None,
    )

    assert result.state == "succeeded"
    assert calls[:3] == [("status",), ("start",), ("status",)]


def test_production_tail_refuses_a_different_active_candidate(tmp_path: Path) -> None:
    _root, registry, armed = _repository(tmp_path, endpoint="production")
    registry.mark_committing(armed.task_id, armed.generation)
    calls: list[tuple[str, ...]] = []

    def executor(command: tuple[str, ...]) -> ReleaseObservation:
        calls.append(command)
        return ReleaseObservation("ok", "approved", "c" * 40)

    result = run_production_tail(
        registry,
        armed.task_id,
        armed.generation,
        outcome_sha="b" * 40,
        executor=executor,
        sleep=lambda _seconds: None,
    )

    assert result.state == "paused"
    assert result.failure_code == "release_tail_candidate_mismatch"
    assert calls == [("status",)]
