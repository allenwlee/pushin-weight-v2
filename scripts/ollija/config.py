from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from . import PROJECT_CONTRACT_VERSION


class ConfigError(ValueError):
    """An actionable error in the tracked annotation contract."""


@dataclass(frozen=True, slots=True)
class AuthorityConfig:
    canonical_host: str
    repository_root: Path
    repository_slug: str
    release_worktree_label: str
    release_worktree_path: Path

    @property
    def release_worktree_area(self) -> Path:
        return (self.repository_root / self.release_worktree_path).resolve()


@dataclass(frozen=True, slots=True)
class PlansConfig:
    directory: Path


@dataclass(frozen=True, slots=True)
class GitConfig:
    remote: str
    staging_branch: str
    production_branch: str


@dataclass(frozen=True, slots=True)
class EnvironmentConfig:
    blueprint: Path
    url: str
    service: str


@dataclass(frozen=True, slots=True)
class DeliveryConfig:
    template: Path
    test_commands: tuple[str, ...]
    code_failure_route: str
    infra_failure_route: str


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """The small, tracked input contract for deterministic plan annotation."""

    root: Path
    path: Path
    schema_version: int
    authority: AuthorityConfig
    plans: PlansConfig
    git: GitConfig
    environments: Mapping[str, EnvironmentConfig]
    delivery: DeliveryConfig

    @property
    def template_path(self) -> Path:
        """The template in this checkout, validated against the authority root."""

        return (self.root / self.delivery.template).resolve()


_REQUIRED_TOP_LEVEL = {"schema_version", "authority", "plans", "git", "environments", "delivery"}


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
        "Run from a checkout containing the tracked annotation contract."
    )


def _mapping(raw: Mapping[str, Any], key: str, *, parent: str = "project") -> Mapping[str, Any]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise ConfigError(f"Project contract field {parent}.{key} must be a mapping")
    return value


def _string(raw: Mapping[str, Any], key: str, *, parent: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise ConfigError(f"Project contract field {parent}.{key} must be a non-empty line")
    return value.strip()


def _relative_path(raw: Mapping[str, Any], key: str, *, parent: str, root: Path) -> Path:
    value = Path(_string(raw, key, parent=parent))
    if value.is_absolute() or ".." in value.parts or value == Path("."):
        raise ConfigError(
            f"Project contract field {parent}.{key} must be a repository-relative path"
        )
    resolved = (root / value).resolve()
    if not resolved.is_relative_to(root):
        raise ConfigError(
            f"Project contract field {parent}.{key} must resolve inside authority.repository_root"
        )
    return value


def _url(raw: Mapping[str, Any], key: str, *, parent: str) -> str:
    value = _string(raw, key, parent=parent)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}:
        raise ConfigError(f"Project contract field {parent}.{key} must be an HTTPS base URL")
    return value.rstrip("/")


def _branch(raw: Mapping[str, Any], key: str, *, parent: str) -> str:
    value = _string(raw, key, parent=parent)
    path = Path(value)
    if value.startswith("/") or ".." in path.parts or value.endswith("/") or "//" in value:
        raise ConfigError(f"Project contract field {parent}.{key} must be a branch name")
    return value


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise ConfigError(f"{path} must contain a YAML mapping")
    return loaded


def load_project_config(start: str | Path = ".") -> ProjectConfig:
    path = _find_contract(Path(start))
    raw = dict(_load_yaml(path))

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

    authority_raw = _mapping(raw, "authority")
    repository_root = Path(_string(authority_raw, "repository_root", parent="authority"))
    if not repository_root.is_absolute():
        raise ConfigError("authority.repository_root must be absolute")
    repository_root = repository_root.resolve()
    authority = AuthorityConfig(
        canonical_host=_string(authority_raw, "canonical_host", parent="authority"),
        repository_root=repository_root,
        repository_slug=_string(authority_raw, "repository_slug", parent="authority"),
        release_worktree_label=_string(
            authority_raw, "release_worktree_label", parent="authority"
        ),
        release_worktree_path=_relative_path(
            authority_raw,
            "release_worktree_path",
            parent="authority",
            root=repository_root,
        ),
    )

    plans_raw = _mapping(raw, "plans")
    plans = PlansConfig(
        directory=_relative_path(plans_raw, "directory", parent="plans", root=repository_root)
    )

    git_raw = _mapping(raw, "git")
    git = GitConfig(
        remote=_string(git_raw, "remote", parent="git"),
        staging_branch=_branch(git_raw, "staging_branch", parent="git"),
        production_branch=_branch(git_raw, "production_branch", parent="git"),
    )
    if git.staging_branch == git.production_branch:
        raise ConfigError("git.staging_branch and git.production_branch must differ")

    environments_raw = _mapping(raw, "environments")
    environments: dict[str, EnvironmentConfig] = {}
    for name in ("staging", "production"):
        environment = _mapping(environments_raw, name, parent="environments")
        environments[name] = EnvironmentConfig(
            blueprint=_relative_path(
                environment, "blueprint", parent=f"environments.{name}", root=repository_root
            ),
            url=_url(environment, "url", parent=f"environments.{name}"),
            service=_string(environment, "service", parent=f"environments.{name}"),
        )
    unknown_environments = sorted(set(environments_raw) - set(environments))
    if unknown_environments:
        raise ConfigError("Project contract has unknown environments: " + ", ".join(unknown_environments))

    delivery_raw = _mapping(raw, "delivery")
    template = _relative_path(
        delivery_raw, "template", parent="delivery", root=repository_root
    )
    commands = delivery_raw.get("test_commands")
    if not isinstance(commands, list) or not commands or not all(
        isinstance(command, str) and command.strip() and "\n" not in command
        for command in commands
    ):
        raise ConfigError("Project contract field delivery.test_commands must be a non-empty list")
    delivery = DeliveryConfig(
        template=template,
        test_commands=tuple(command.strip() for command in commands),
        code_failure_route=_string(delivery_raw, "code_failure_route", parent="delivery"),
        infra_failure_route=_string(delivery_raw, "infra_failure_route", parent="delivery"),
    )
    unknown_delivery = sorted(
        set(delivery_raw)
        - {"template", "test_commands", "code_failure_route", "infra_failure_route"}
    )
    if unknown_delivery:
        raise ConfigError("Project contract has unknown delivery fields: " + ", ".join(unknown_delivery))

    root = path.parent.parent.resolve()
    template_path = (root / delivery.template).resolve()
    if not template_path.is_file():
        raise ConfigError(f"Configured delivery template is missing: {template_path}")

    return ProjectConfig(
        root=root,
        path=path,
        schema_version=version,
        authority=authority,
        plans=plans,
        git=git,
        environments=environments,
        delivery=delivery,
    )
