from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path

from ..tasks import AttemptSnapshot, TaskSnapshot
from .base import AgentDriver, AgentLaunch
from .claude import ClaudeDriver
from .codex import CodexDriver


class AgentDriverError(ValueError):
    """The selected agent driver is unavailable; never fall through vendors."""


def driver_for(kind: str) -> AgentDriver:
    if kind not in {"codex", "claude"}:
        raise AgentDriverError("agent_driver_unsupported")
    executable = shutil.which(kind)
    if executable is None:
        raise AgentDriverError(f"{kind}_driver_unavailable")
    if kind == "codex":
        return CodexDriver(Path(executable))
    return ClaudeDriver(Path(executable))


def launch_for_attempt(
    task: TaskSnapshot,
    attempt: AttemptSnapshot,
    *,
    drivers: Mapping[str, AgentDriver] | None = None,
) -> AgentLaunch:
    selected = drivers.get(task.agent_kind) if drivers is not None else driver_for(task.agent_kind)
    if selected is None:
        raise AgentDriverError(f"{task.agent_kind}_driver_unavailable")
    return selected.launch(task, attempt=attempt.attempt)


def command_for_attempt(
    task: TaskSnapshot, attempt: AttemptSnapshot
) -> tuple[str, ...]:
    return launch_for_attempt(task, attempt).argv
