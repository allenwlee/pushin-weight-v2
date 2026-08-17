from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .git import CommandRunner, SubprocessRunner
from .tasks import TaskRegistry, TaskSnapshot


class ProcessControlError(ValueError):
    """A process could not be proven to belong to the selected task."""


_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    pgid: int
    birth: str
    command: str


def supervisor_session_name(task_id: str, generation: int) -> str:
    if not _TASK_ID.fullmatch(task_id) or generation < 1:
        raise ProcessControlError("task_identity_invalid")
    safe_task = task_id.replace(".", "_")
    return f"ollija-{safe_task}-g{generation}"


def start_detached_supervisor(
    *,
    registry_path: Path,
    task_id: str,
    generation: int,
    python_executable: Path,
    workspace: Path,
    runner: CommandRunner | None = None,
) -> str:
    session = supervisor_session_name(task_id, generation)
    active_runner = runner or SubprocessRunner()
    existing = active_runner.run(
        ("tmux", "has-session", "-t", f"={session}"),
        cwd=workspace,
        timeout=5,
    )
    if existing.returncode == 0:
        return session
    if existing.returncode not in {1}:
        raise ProcessControlError("tmux_status_unavailable")
    command = (
        "tmux",
        "new-session",
        "-d",
        "-s",
        session,
        str(python_executable),
        "-m",
        "scripts.ollija.supervisor",
        "--registry",
        str(registry_path),
        "--task",
        task_id,
        "--generation",
        str(generation),
    )
    started = active_runner.run(command, cwd=workspace, timeout=10)
    if started.returncode != 0:
        raise ProcessControlError("tmux_supervisor_start_failed")
    return session


def observe_process(pid: int) -> ProcessIdentity | None:
    if pid < 2:
        return None
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "pid=,pgid=,lstart=,command="],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    fields = completed.stdout.strip().split(None, 7)
    if len(fields) < 8:
        raise ProcessControlError("process_identity_unparseable")
    return ProcessIdentity(
        pid=int(fields[0]),
        pgid=int(fields[1]),
        birth=" ".join(fields[2:7]),
        command=fields[7],
    )


def _group_alive(pgid: int) -> bool:
    completed = subprocess.run(
        ["ps", "-ax", "-o", "pgid=,stat="],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if completed.returncode != 0:
        raise ProcessControlError("process_group_status_unavailable")
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == str(pgid) and not fields[1].startswith("Z"):
            return True
    return False


def terminate_owned_process(
    *,
    pid: int,
    pgid: int,
    process_birth: str,
    timeout: float = 5,
) -> None:
    observed = observe_process(pid)
    if observed is None:
        return
    if (
        observed.pid != pid
        or observed.pgid != pgid
        or observed.birth != process_birth
        or pid != pgid
    ):
        raise ProcessControlError("task_process_identity_mismatch")
    os.killpg(pgid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while _group_alive(pgid) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _group_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            if _group_alive(pgid):
                raise ProcessControlError("task_process_signal_denied") from exc
            return
        kill_deadline = time.monotonic() + 2
        while _group_alive(pgid) and time.monotonic() < kill_deadline:
            time.sleep(0.05)
    if _group_alive(pgid):
        raise ProcessControlError("task_process_stop_timeout")


def stop_task_processes(
    registry: TaskRegistry,
    task_id: str,
    generation: int,
) -> TaskSnapshot:
    """Seal cancellation before sending any process signal."""

    stopped = registry.cancel(task_id, generation)
    if stopped.state != "cancelled":
        return stopped
    attempt = registry.current_attempt(task_id, generation)
    if (
        attempt is None
        or attempt.pid is None
        or attempt.pgid is None
        or attempt.process_birth is None
    ):
        return stopped
    terminate_owned_process(
        pid=attempt.pid,
        pgid=attempt.pgid,
        process_birth=attempt.process_birth,
    )
    return stopped
