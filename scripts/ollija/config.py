from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import PROJECT_CONTRACT_VERSION
from .redaction import UnsafeOutputError, assert_safe_value


class ConfigError(ValueError):
    """An actionable project-contract error."""


DEFAULT_RELEASE_WORKTREE_LABEL = "Ollija release worktree area"
DEFAULT_RELEASE_WORKTREE_PATH = Path(".worktrees")


@dataclass(frozen=True, slots=True)
class AuthorityConfig:
    canonical_host: str
    forbidden_hosts: tuple[str, ...]
    repository_root: Path
    repository_slug: str
    release_worktree_label: str = DEFAULT_RELEASE_WORKTREE_LABEL
    release_worktree_path: Path = DEFAULT_RELEASE_WORKTREE_PATH


@dataclass(frozen=True, slots=True)
class GitConfig:
    staging_branch: str
    production_branch: str


@dataclass(frozen=True, slots=True)
class StateConfig:
    directory: Path
    retention_days: int


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    root: Path
    path: Path
    schema_version: int
    adapter: str
    authority: AuthorityConfig
    git: GitConfig
    state: StateConfig
    versioning: Mapping[str, Any]
    environments: Mapping[str, Any]
    database_safety: Mapping[str, Any]
    verification: Mapping[str, Any]
    ui_impact: Mapping[str, Any]
    bridgewright: Mapping[str, Any]
    tooling: Mapping[str, Any]

    @property
    def state_root(self) -> Path:
        """One shared state root, independent of the active worktree."""

        return (self.authority.repository_root / self.state.directory).resolve()

    @property
    def canonical_virtualenv(self) -> Path:
        return (self.authority.repository_root / ".venv").resolve()


_REQUIRED_TOP_LEVEL = {
    "schema_version",
    "adapter",
    "authority",
    "git",
    "versioning",
    "state",
    "environments",
    "database_safety",
    "verification",
    "ui_impact",
    "bridgewright",
    "tooling",
}


def _find_contract(start: Path) -> Path:
    resolved = start.expanduser().resolve()
    if resolved.is_file():
        if resolved.name == "project.yaml" and resolved.parent.name == ".ollija":
            return resolved
        resolved = resolved.parent

    for directory in (resolved, *resolved.parents):
        candidate = directory / ".ollija" / "project.yaml"
        if candidate.is_file():
            return candidate
    raise ConfigError(
        f"No .ollija/project.yaml found from {start}. "
        "Run from the authoritative repository checkout."
    )


def _mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise ConfigError(f"Project contract field {key!r} must be a mapping")
    return value


def _string(raw: Mapping[str, Any], key: str, *, parent: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Project contract field {parent}.{key} must be a string")
    return value.strip()


def load_project_config(start: str | Path = ".") -> ProjectConfig:
    path = _find_contract(Path(start))
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc

    if not isinstance(loaded, Mapping):
        raise ConfigError(f"{path} must contain a YAML mapping")
    raw = dict(loaded)

    try:
        assert_safe_value(raw, location="project contract")
    except UnsafeOutputError as exc:
        raise ConfigError(str(exc)) from exc

    version = raw.get("schema_version")
    if version != PROJECT_CONTRACT_VERSION:
        raise ConfigError(
            f"Unsupported project contract version {version!r}; "
            f"this ollija supports version {PROJECT_CONTRACT_VERSION}."
        )

    missing = sorted(_REQUIRED_TOP_LEVEL - raw.keys())
    unknown = sorted(raw.keys() - _REQUIRED_TOP_LEVEL)
    if missing:
        raise ConfigError("Project contract is missing: " + ", ".join(missing))
    if unknown:
        raise ConfigError("Project contract has unknown fields: " + ", ".join(unknown))

    authority = _mapping(raw, "authority")
    git = _mapping(raw, "git")
    state = _mapping(raw, "state")
    forbidden = authority.get("forbidden_hosts")
    if not isinstance(forbidden, list) or not all(
        isinstance(item, str) and item for item in forbidden
    ):
        raise ConfigError("Project contract field authority.forbidden_hosts must be a list")

    retention_days = state.get("retention_days")
    if not isinstance(retention_days, int) or retention_days < 1:
        raise ConfigError("Project contract field state.retention_days must be positive")

    repository_root = Path(_string(authority, "repository_root", parent="authority"))
    state_directory = Path(_string(state, "directory", parent="state"))
    release_worktree_label = authority.get(
        "release_worktree_label", DEFAULT_RELEASE_WORKTREE_LABEL
    )
    raw_release_worktree_path = authority.get(
        "release_worktree_path", DEFAULT_RELEASE_WORKTREE_PATH.as_posix()
    )
    if not isinstance(release_worktree_label, str) or not release_worktree_label.strip():
        raise ConfigError(
            "Project contract field authority.release_worktree_label must be a string"
        )
    if (
        not isinstance(raw_release_worktree_path, str)
        or not raw_release_worktree_path.strip()
    ):
        raise ConfigError(
            "Project contract field authority.release_worktree_path must be a string"
        )
    release_worktree_path = Path(raw_release_worktree_path)
    if release_worktree_path.is_absolute() or ".." in release_worktree_path.parts:
        raise ConfigError(
            "authority.release_worktree_path must be a repository-relative path"
        )
    if not repository_root.is_absolute():
        raise ConfigError("authority.repository_root must be absolute")
    # The selected checkout owns source files and Git operations. Durable
    # Ollija state remains anchored separately by ``state_root`` below, so a
    # linked release worktree can be evaluated without reading a different
    # checkout's ledger or code.
    root = path.parent.parent.resolve()
    if state_directory.is_absolute() or ".." in state_directory.parts:
        raise ConfigError("state.directory must be a repository-relative path")

    environments = _mapping(raw, "environments")
    for required_environment in ("local", "staging", "production"):
        if not isinstance(environments.get(required_environment), Mapping):
            raise ConfigError(
                f"Project contract requires environments.{required_environment}"
            )

    return ProjectConfig(
        root=root,
        path=path,
        schema_version=version,
        adapter=_string(raw, "adapter", parent="project"),
        authority=AuthorityConfig(
            canonical_host=_string(authority, "canonical_host", parent="authority"),
            forbidden_hosts=tuple(forbidden),
            repository_root=repository_root.resolve(),
            repository_slug=_string(authority, "repository_slug", parent="authority"),
            release_worktree_label=release_worktree_label.strip(),
            release_worktree_path=release_worktree_path,
        ),
        git=GitConfig(
            staging_branch=_string(git, "staging_branch", parent="git"),
            production_branch=_string(git, "production_branch", parent="git"),
        ),
        state=StateConfig(
            directory=state_directory,
            retention_days=retention_days,
        ),
        versioning=_mapping(raw, "versioning"),
        environments=environments,
        database_safety=_mapping(raw, "database_safety"),
        verification=_mapping(raw, "verification"),
        ui_impact=_mapping(raw, "ui_impact"),
        bridgewright=_mapping(raw, "bridgewright"),
        tooling=_mapping(raw, "tooling"),
    )
