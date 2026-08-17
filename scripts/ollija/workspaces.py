from __future__ import annotations

import re
from pathlib import Path

from .config import ProjectConfig
from .git import GitObservation


class WorkspaceError(ValueError):
    """The requested task workspace is outside Ollija's authority boundary."""


_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")


def task_worktree_path(config: ProjectConfig, branch: str) -> Path:
    if (
        not _BRANCH.fullmatch(branch)
        or ".." in Path(branch).parts
        or branch.startswith("/")
        or branch.endswith("/")
        or "//" in branch
        or branch in {config.git.production_branch, config.git.staging_branch}
    ):
        raise WorkspaceError("task_branch_invalid")
    target = (config.authority.repository_root / ".worktrees" / branch).resolve()
    hierarchy = (config.authority.repository_root / ".worktrees").resolve()
    if target == hierarchy or not target.is_relative_to(hierarchy):
        raise WorkspaceError("task_worktree_outside_hierarchy")
    return target


def prepare_runtime_links(config: ProjectConfig) -> Path:
    """Attach ignored runtime dependencies without copying them into a worktree."""

    canonical = config.canonical_virtualenv
    python = canonical / "bin" / "python"
    if not python.is_file() or not python.stat().st_mode & 0o111:
        raise WorkspaceError("canonical_virtualenv_missing")
    if not canonical.is_relative_to(config.authority.repository_root):
        raise WorkspaceError("canonical_virtualenv_outside_authority")

    link = config.root / ".venv"
    if link.exists() or link.is_symlink():
        try:
            if link.resolve(strict=True) != canonical:
                raise WorkspaceError("workspace_virtualenv_mismatch")
        except OSError as exc:
            raise WorkspaceError("workspace_virtualenv_mismatch") from exc
        return link

    link.symlink_to(canonical, target_is_directory=True)
    return link


def validate_task_workspace(
    config: ProjectConfig, observation: GitObservation
) -> Path:
    if observation.detached:
        raise WorkspaceError("task_workspace_detached")
    if not observation.registered_worktree:
        raise WorkspaceError("task_workspace_unregistered")
    if observation.dirty_paths:
        raise WorkspaceError("task_workspace_dirty")
    if not observation.branch:
        raise WorkspaceError("task_branch_invalid")
    expected = task_worktree_path(config, observation.branch)
    if observation.repository_root.resolve() != expected:
        raise WorkspaceError("task_worktree_location_invalid")
    if observation.common_git_directory != (
        config.authority.repository_root / ".git"
    ).resolve():
        raise WorkspaceError("task_worktree_repository_mismatch")
    if config.root.resolve() != observation.repository_root.resolve():
        raise WorkspaceError("task_workspace_config_mismatch")
    return expected
