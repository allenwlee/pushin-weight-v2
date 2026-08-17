from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..git import CommandRunner, SubprocessRunner
from ..tasks import TaskSnapshot
from .base import AgentLaunch, AgentProbe, parse_version, task_prompt, version_at_least


@dataclass(frozen=True, slots=True)
class CodexDriver:
    executable: Path
    runner: CommandRunner
    kind: str = "codex"

    def __init__(
        self, executable: Path, runner: CommandRunner | None = None
    ) -> None:
        object.__setattr__(self, "executable", executable)
        object.__setattr__(self, "runner", runner or SubprocessRunner())
        object.__setattr__(self, "kind", "codex")

    def probe(self, workspace: Path) -> AgentProbe:
        version_result = self.runner.run(
            (str(self.executable), "--version"), cwd=workspace, timeout=10
        )
        version = parse_version(version_result.stdout or version_result.stderr)
        if version_result.returncode != 0 or version is None:
            return AgentProbe(self.kind, False, version, "agent_version_unavailable")
        if not version_at_least(version, (0, 147, 0)):
            return AgentProbe(self.kind, False, version, "agent_version_unsupported")
        auth = self.runner.run(
            (str(self.executable), "login", "status"), cwd=workspace, timeout=15
        )
        if auth.returncode != 0 or "logged in" not in auth.stdout.lower():
            return AgentProbe(self.kind, False, version, "agent_auth_unavailable")
        return AgentProbe(self.kind, True, version)

    def launch(self, task: TaskSnapshot, *, attempt: int) -> AgentLaunch:
        del attempt
        return AgentLaunch(
            kind=self.kind,
            argv=(
                str(self.executable),
                "exec",
                "--json",
                "--sandbox",
                "workspace-write",
                "--approve-for-me",
                "-C",
                task.workspace,
                task_prompt(task),
            ),
            session_id=None,
            supports_resume=False,
        )
