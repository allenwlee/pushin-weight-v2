from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .git import CommandRunner, SubprocessRunner
from .tasks import AttemptSnapshot, TaskRegistry, TaskSnapshot


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
    return f"ollija-{task_id}-g{generation}"


def supervisor_session_exists(
    task_id: str,
    generation: int,
    *,
    workspace: Path,
    runner: CommandRunner | None = None,
) -> bool:
    session = supervisor_session_name(task_id, generation)
    result = (runner or SubprocessRunner()).run(
        ("tmux", "has-session", "-t", f"={session}"),
        cwd=workspace,
        timeout=5,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise ProcessControlError("tmux_status_unavailable")


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
    if supervisor_session_exists(
        task_id,
        generation,
        workspace=workspace,
        runner=active_runner,
    ):
        return session
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


def attempt_process_is_alive(attempt: AttemptSnapshot) -> bool:
    if (
        attempt.pid is None
        or attempt.pgid is None
        or attempt.process_birth is None
    ):
        return False
    observed = observe_process(attempt.pid)
    return bool(
        observed is not None
        and observed.pid == attempt.pid
        and observed.pgid == attempt.pgid
        and observed.birth == attempt.process_birth
        and attempt.pid == attempt.pgid
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
    *,
    runner: CommandRunner | None = None,
) -> TaskSnapshot:
    """Seal cancellation before sending any process signal."""

    stopped = registry.cancel(task_id, generation)
    if stopped.state != "cancelled":
        return stopped
    attempt = registry.current_attempt(task_id, generation)
    process_error: ProcessControlError | None = None
    if (
        attempt is not None
        and attempt.pid is not None
        and attempt.pgid is not None
        and attempt.process_birth is not None
    ):
        try:
            terminate_owned_process(
                pid=attempt.pid,
                pgid=attempt.pgid,
                process_birth=attempt.process_birth,
            )
        except ProcessControlError as exc:
            process_error = exc
    session = supervisor_session_name(task_id, generation)
    closed = (runner or SubprocessRunner()).run(
        ("tmux", "kill-session", "-t", f"={session}"),
        cwd=Path(stopped.workspace),
        timeout=5,
    )
    if closed.returncode not in {0, 1}:
        raise ProcessControlError("tmux_supervisor_stop_failed")
    if process_error is not None:
        raise process_error
    return stopped
