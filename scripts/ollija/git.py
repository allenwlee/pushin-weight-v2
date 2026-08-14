from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .adapters.base import AuthorityObservation
from .config import ProjectConfig


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        timeout: float = 10,
    ) -> CommandOutcome: ...


class SubprocessRunner:
    def run(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        timeout: float = 10,
    ) -> CommandOutcome:
        try:
            completed = subprocess.run(
                list(args),
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return CommandOutcome(127, "", "command unavailable")
        except subprocess.TimeoutExpired:
            return CommandOutcome(124, "", "command timed out")
        return CommandOutcome(
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )


@dataclass(frozen=True, slots=True)
class GitObservation:
    repository_root: Path
    head_sha: str | None
    branch: str | None
    detached: bool
    registered_worktree: bool
    dirty_paths: tuple[str, ...]
    production_sha: str | None
    staging_sha: str | None
    branch_relationship: str
    remote_reachable: bool
    repository_slug: str = ""


@dataclass(frozen=True, slots=True)
class MutationDecision:
    allowed: bool
    reason_codes: tuple[str, ...]


def _git(
    runner: CommandRunner,
    cwd: Path,
    *args: str,
    timeout: float = 10,
) -> CommandOutcome:
    return runner.run(("git", *args), cwd=cwd, timeout=timeout)


def _branch_relationship(
    runner: CommandRunner,
    cwd: Path,
    production_sha: str | None,
    staging_sha: str | None,
) -> str:
    if not production_sha or not staging_sha:
        return "unknown"
    if production_sha == staging_sha:
        return "equal"
    production_is_ancestor = _git(
        runner, cwd, "merge-base", "--is-ancestor", production_sha, staging_sha
    ).returncode
    staging_is_ancestor = _git(
        runner, cwd, "merge-base", "--is-ancestor", staging_sha, production_sha
    ).returncode
    if production_is_ancestor == 0:
        return "staging_ahead"
    if staging_is_ancestor == 0:
        return "production_ahead"
    if production_is_ancestor == 1 and staging_is_ancestor == 1:
        return "diverged"
    return "unknown"


def _dirty_paths(porcelain: str) -> tuple[str, ...]:
    paths: list[str] = []
    for entry in porcelain.split("\0"):
        if not entry:
            continue
        path = entry[3:] if len(entry) > 3 else entry
        paths.append(path)
    return tuple(sorted(set(paths)))


def _remote_heads(output: str) -> dict[str, str]:
    heads: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 2 or not fields[1].startswith("refs/heads/"):
            continue
        heads[fields[1].removeprefix("refs/heads/")] = fields[0]
    return heads


def observe_git(
    config: ProjectConfig,
    *,
    cwd: Path,
    runner: CommandRunner,
) -> GitObservation:
    root_result = _git(runner, cwd, "rev-parse", "--show-toplevel")
    if root_result.returncode != 0:
        return GitObservation(
            repository_root=cwd.resolve(),
            head_sha=None,
            branch=None,
            detached=True,
            registered_worktree=False,
            dirty_paths=(),
            production_sha=None,
            staging_sha=None,
            branch_relationship="unknown",
            remote_reachable=False,
        )

    root = Path(root_result.stdout.strip()).resolve()
    head_result = _git(runner, root, "rev-parse", "HEAD")
    branch_result = _git(runner, root, "symbolic-ref", "--quiet", "--short", "HEAD")
    status_result = _git(runner, root, "status", "--porcelain=v1", "-z")
    worktree_result = _git(runner, root, "worktree", "list", "--porcelain")
    remote_result = _git(runner, root, "remote", "get-url", "origin")
    heads_result = _git(
        runner,
        root,
        "ls-remote",
        "--heads",
        "origin",
        config.git.production_branch,
        config.git.staging_branch,
        timeout=15,
    )

    registered_roots = {
        Path(line.removeprefix("worktree ")).resolve()
        for line in worktree_result.stdout.splitlines()
        if line.startswith("worktree ")
    }
    remote_reachable = heads_result.returncode == 0
    heads = _remote_heads(heads_result.stdout) if remote_reachable else {}
    production_sha = heads.get(config.git.production_branch)
    staging_sha = heads.get(config.git.staging_branch)

    return GitObservation(
        repository_root=root,
        head_sha=head_result.stdout.strip() if head_result.returncode == 0 else None,
        branch=branch_result.stdout.strip() if branch_result.returncode == 0 else None,
        detached=branch_result.returncode != 0,
        registered_worktree=root in registered_roots,
        dirty_paths=(
            _dirty_paths(status_result.stdout) if status_result.returncode == 0 else ()
        ),
        production_sha=production_sha,
        staging_sha=staging_sha,
        branch_relationship=_branch_relationship(
            runner, root, production_sha, staging_sha
        ),
        remote_reachable=remote_reachable,
        repository_slug=(
            remote_result.stdout.strip() if remote_result.returncode == 0 else ""
        ),
    )


def mutation_preflight(
    authority: AuthorityObservation,
    git: GitObservation,
    *,
    operation: str,
) -> MutationDecision:
    reasons = list(authority.reason_codes)
    if git.detached:
        reasons.append("detached_head")
    if not git.registered_worktree:
        reasons.append("unregistered_worktree")
    if git.dirty_paths:
        reasons.append("dirty_tree")
    if not git.remote_reachable:
        reasons.append("git_remote_unreachable")

    if operation == "release":
        if git.branch_relationship == "diverged":
            reasons.append("production_staging_diverged")
        elif git.branch_relationship == "production_ahead":
            reasons.append("production_moved")
        elif git.branch_relationship not in {"equal", "staging_ahead"}:
            reasons.append("branch_ancestry_unknown")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return MutationDecision(not unique_reasons, unique_reasons)
