from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..git import CommandRunner, SubprocessRunner
from ..tasks import TaskSnapshot
from .base import AgentLaunch, AgentProbe, task_prompt


def _version(value: str) -> str | None:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+){1,3})", value)
    return match.group(1) if match else None


def _supported(value: str) -> bool:
    parts = tuple(int(item) for item in value.split("."))
    return parts >= (2, 1, 187)


@dataclass(frozen=True, slots=True)
class ClaudeDriver:
    executable: Path
    runner: CommandRunner
    kind: str = "claude"

    def __init__(
        self, executable: Path, runner: CommandRunner | None = None
    ) -> None:
        object.__setattr__(self, "executable", executable)
        object.__setattr__(self, "runner", runner or SubprocessRunner())
        object.__setattr__(self, "kind", "claude")

    @staticmethod
    def session_id(task: TaskSnapshot) -> str:
        identity = f"ollija:{task.task_id}:{task.generation}:{task.workspace}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))

    def probe(self, workspace: Path) -> AgentProbe:
        version_result = self.runner.run(
            (str(self.executable), "--version"), cwd=workspace, timeout=10
        )
        version = _version(version_result.stdout or version_result.stderr)
        if version_result.returncode != 0 or version is None:
            return AgentProbe(self.kind, False, version, "agent_version_unavailable")
        if not _supported(version):
            return AgentProbe(self.kind, False, version, "agent_version_unsupported")
        auth = self.runner.run(
            (str(self.executable), "auth", "status", "--json"),
            cwd=workspace,
            timeout=15,
        )
        try:
            logged_in = json.loads(auth.stdout).get("loggedIn") is True
        except (json.JSONDecodeError, AttributeError):
            logged_in = False
        if auth.returncode != 0 or not logged_in:
            return AgentProbe(self.kind, False, version, "agent_auth_unavailable")
        return AgentProbe(self.kind, True, version)

    def launch(self, task: TaskSnapshot, *, attempt: int) -> AgentLaunch:
        session_id = self.session_id(task)
        session_args = (
            ("--session-id", session_id)
            if attempt == 1
            else ("--resume", session_id)
        )
        return AgentLaunch(
            kind=self.kind,
            argv=(
                str(self.executable),
                "--print",
                "--output-format",
                "json",
                "--permission-mode",
                "auto",
                "--name",
                f"ollija-{task.task_id}",
                *session_args,
                task_prompt(task),
            ),
            session_id=session_id,
            supports_resume=True,
        )
