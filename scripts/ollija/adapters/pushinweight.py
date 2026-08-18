from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import ProjectConfig
from .base import AuthorityObservation


def _short_hostname(value: str) -> str:
    return value.strip().lower().split(".", 1)[0]


def _repository_slug(value: str) -> str:
    normalized = value.strip()
    normalized = re.sub(r"^git@github\.com:", "", normalized)
    normalized = re.sub(r"^https?://github\.com/", "", normalized)
    return normalized.removesuffix(".git").strip("/").lower()


@dataclass(frozen=True, slots=True)
class PushinWeightAdapter:
    config: ProjectConfig
    name: str = "pushinweight"

    def __post_init__(self) -> None:
        if self.config.adapter != self.name:
            raise ValueError(
                f"Project selects adapter {self.config.adapter!r}, not {self.name!r}"
            )

    def assess_authority(
        self,
        *,
        hostname: str,
        repository_root: Path,
        repository_slug: str,
        registered_worktree: bool = True,
        common_git_directory: Path | None = None,
    ) -> AuthorityObservation:
        actual_host = _short_hostname(hostname)
        canonical_host = _short_hostname(self.config.authority.canonical_host)
        forbidden_hosts = {
            _short_hostname(item) for item in self.config.authority.forbidden_hosts
        }
        actual_root = repository_root.expanduser().resolve()
        expected_root = self.config.authority.repository_root
        actual_slug = _repository_slug(repository_slug)
        expected_slug = _repository_slug(self.config.authority.repository_slug)
        worktree_root = (
            expected_root / self.config.authority.release_worktree_path
        ).resolve()
        common_git = (
            common_git_directory.expanduser().resolve()
            if common_git_directory is not None
            else None
        )
        canonical_git = (expected_root / ".git").resolve()
        is_canonical = actual_root == expected_root
        is_allowed_worktree = (
            actual_root != worktree_root
            and actual_root.is_relative_to(worktree_root)
            and registered_worktree
            and common_git == canonical_git
        )

        reasons: list[str] = []
        if actual_host in forbidden_hosts:
            reasons.append("forbidden_host")
        if actual_host != canonical_host:
            reasons.append("host_mismatch")
        if not is_canonical and not is_allowed_worktree:
            reasons.append("repository_root_mismatch")
        if actual_slug != expected_slug:
            reasons.append("repository_slug_mismatch")

        return AuthorityObservation(
            hostname=actual_host,
            repository_root=actual_root,
            repository_slug=actual_slug,
            mutation_allowed=not reasons,
            reason_codes=tuple(reasons),
        )
