from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config import ProjectConfig


@dataclass(frozen=True, slots=True)
class AuthorityObservation:
    hostname: str
    repository_root: Path
    repository_slug: str
    mutation_allowed: bool
    reason_codes: tuple[str, ...] = ()


class ProjectAdapter(Protocol):
    """Narrow project-specific seam intended for future extraction."""

    name: str
    config: ProjectConfig

    def assess_authority(
        self,
        *,
        hostname: str,
        repository_root: Path,
        repository_slug: str,
    ) -> AuthorityObservation: ...
