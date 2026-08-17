from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..tasks import TaskSnapshot


@dataclass(frozen=True, slots=True)
class AgentProbe:
    kind: str
    available: bool
    version: str | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class AgentLaunch:
    kind: str
    argv: tuple[str, ...]
    session_id: str | None
    supports_resume: bool


class AgentDriver(Protocol):
    kind: str

    def probe(self, workspace: Path) -> AgentProbe: ...

    def launch(self, task: TaskSnapshot, *, attempt: int) -> AgentLaunch: ...


def parse_version(value: str) -> str | None:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+){1,3})", value)
    return match.group(1) if match else None


def version_at_least(value: str, minimum: tuple[int, ...]) -> bool:
    return tuple(int(item) for item in value.split(".")) >= minimum


def task_prompt(task: TaskSnapshot) -> str:
    return (
        f"Implement Ollija task {task.task_id}, generation {task.generation}.\n\n"
        f"The authoritative task source is the repo-relative file {task.source_path}. "
        "Read it before changing code and stay within its scope.\n\n"
        "Work only in the current assigned worktree. Do not stage, commit, push, "
        "release, or deploy; Ollija owns verification and the checkpoint commit. "
        "Do not start another agent or worktree. Run focused checks when useful, "
        "leave the complete task diff uncommitted, and exit successfully only when "
        "the diff is ready for Ollija's declared verification gates."
    )
