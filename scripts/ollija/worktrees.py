from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .config import ProjectConfig
from .git import CommandRunner, SubprocessRunner


class WorktreeError(ValueError):
    """A worktree guard or move operation failed safely."""


@dataclass(frozen=True, slots=True)
class WorktreeLocation:
    label: str
    path: Path
    relative_path: str


def release_worktree_location(config: ProjectConfig) -> WorktreeLocation:
    root = config.root.resolve()
    path = (root / config.authority.release_worktree_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WorktreeError("release_worktree_path_outside_repository") from exc
    if path == root:
        raise WorktreeError("release_worktree_path_is_repository_root")
    relative = path.relative_to(root).as_posix()
    return WorktreeLocation(
        label=config.authority.release_worktree_label,
        path=path,
        relative_path=relative,
    )


def is_release_worktree(config: ProjectConfig, path: Path) -> bool:
    location = release_worktree_location(config)
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(location.path)
    except ValueError:
        return False
    return resolved != location.path


def worktree_warning(config: ProjectConfig, path: Path) -> str:
    location = release_worktree_location(config)
    return (
        f"This worktree is outside {location.label} ({location.relative_path}/).\n"
        "It cannot be released by Ollija unless later moved into that area. "
        "Move to the release worktree area? [y/N]"
    )


def _move_destination(config: ProjectConfig, source: Path, name: str | None) -> Path:
    location = release_worktree_location(config)
    chosen = name or source.name
    if not chosen or chosen in {".", ".."} or Path(chosen).name != chosen:
        raise WorktreeError("release_worktree_name_invalid")
    destination = (location.path / chosen).resolve()
    try:
        destination.relative_to(location.path)
    except ValueError as exc:
        raise WorktreeError("release_worktree_destination_invalid") from exc
    if destination.exists():
        raise WorktreeError("release_worktree_destination_exists")
    return destination


def move_worktree(
    config: ProjectConfig,
    *,
    source: Path,
    name: str | None = None,
    runner: CommandRunner | None = None,
) -> Path:
    active_runner = runner or SubprocessRunner()
    source = source.expanduser().resolve()
    if source == config.root.resolve():
        raise WorktreeError("repository_root_cannot_be_moved")
    if is_release_worktree(config, source):
        raise WorktreeError("worktree_already_in_release_worktree_area")
    destination = _move_destination(config, source, name)
    location = release_worktree_location(config)
    location.path.mkdir(parents=True, exist_ok=True)
    result = active_runner.run(
        ("git", "worktree", "move", str(source), str(destination)),
        cwd=config.root,
        timeout=30,
    )
    if result.returncode != 0:
        raise WorktreeError("worktree_move_failed")
    return destination


def install_hook(config: ProjectConfig, *, runner: CommandRunner | None = None) -> str:
    active_runner = runner or SubprocessRunner()
    hook_path = config.root / ".ollija" / "hooks"
    hook_file = hook_path / "post-checkout"
    if not hook_file.is_file():
        raise WorktreeError("worktree_hook_missing")
    configured_path = str(hook_path.resolve())
    result = active_runner.run(
        ("git", "config", "core.hooksPath", configured_path),
        cwd=config.root,
    )
    if result.returncode != 0:
        raise WorktreeError("worktree_hook_install_failed")
    return configured_path


def guard_worktree(
    config: ProjectConfig,
    *,
    cwd: Path,
    input_stream: TextIO,
    output_stream: TextIO,
    runner: CommandRunner | None = None,
    leave_as_is: bool = False,
) -> Path | None:
    active_runner = runner or SubprocessRunner()
    top_result = active_runner.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=cwd,
    )
    if top_result.returncode != 0:
        return None
    top = Path(top_result.stdout.strip()).resolve()
    if top == config.root.resolve() or is_release_worktree(config, top):
        return top

    output_stream.write(worktree_warning(config, top) + " ")
    output_stream.flush()
    if leave_as_is:
        return top
    if not input_stream.isatty():
        raise WorktreeError("outside_release_worktree_requires_owner_confirmation")
    answer = input_stream.readline().strip().lower()
    if answer not in {"y", "yes"}:
        return top
    return move_worktree(config, source=top, runner=active_runner)
