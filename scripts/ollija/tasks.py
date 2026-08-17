from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .redaction import UnsafeOutputError, assert_safe_value

TASK_SCHEMA_VERSION = 1
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SHA = re.compile(r"[0-9a-f]{40,64}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled", "lost", "paused"})
_ACTIVE_STATES = frozenset(
    {"armed", "running", "restarting", "committing", "awaiting_approval", "releasing"}
)


class TaskError(ValueError):
    """Base error for durable task control."""


class TaskValidationError(TaskError):
    """Task input or registry storage is unsafe."""


class TaskConflict(TaskError):
    """A stale process or terminal state rejected a transition."""


@dataclass(frozen=True, slots=True)
class TaskGrant:
    task_id: str
    parent_task_id: str | None
    source_path: str
    source_digest: str
    workspace: Path
    branch: str
    starting_sha: str
    agent_kind: str
    agent_version: str
    agent_session_id: str | None
    origin_host: str
    origin_terminal: str
    execution_host: str
    endpoint: str
    verification_argv: tuple[tuple[str, ...], ...]
    no_test_reason: str | None
    restart_budget: int = 1


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task_id: str
    parent_task_id: str | None
    generation: int
    state: str
    source_path: str
    source_digest: str
    workspace: str
    branch: str
    starting_sha: str
    agent_kind: str
    agent_version: str
    agent_session_id: str | None
    origin_host: str
    origin_terminal: str
    execution_host: str
    endpoint: str
    verification_argv: tuple[tuple[str, ...], ...]
    no_test_reason: str | None
    restart_budget: int
    restarts_used: int
    created_at: str
    updated_at: str
    outcome_sha: str | None
    failure_code: str | None

    def to_dict(self) -> dict[str, object]:
        body = asdict(self)
        body["verification_argv"] = [list(command) for command in self.verification_argv]
        assert_safe_value(body, location="task status")
        return body


@dataclass(frozen=True, slots=True)
class AttemptSnapshot:
    task_id: str
    generation: int
    attempt: int
    state: str
    pid: int | None
    pgid: int | None
    process_birth: str | None
    driver_session_id: str | None
    started_at: str
    heartbeat_at: str
    ended_at: str | None
    exit_code: int | None
    exit_classification: str | None

    def to_dict(self) -> dict[str, object]:
        body = asdict(self)
        assert_safe_value(body, location="task attempt")
        return body


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def digest_task_source(workspace: Path, source_path: str) -> str:
    root = workspace.expanduser().resolve()
    relative = Path(source_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise TaskValidationError("task_source_path_invalid")
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise TaskValidationError("task_source_missing")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _validate_grant(grant: TaskGrant) -> None:
    if not _TASK_ID.fullmatch(grant.task_id):
        raise TaskValidationError("task_id_invalid")
    if grant.parent_task_id is not None and not _TASK_ID.fullmatch(grant.parent_task_id):
        raise TaskValidationError("parent_task_id_invalid")
    if grant.parent_task_id == grant.task_id:
        raise TaskValidationError("parent_task_self")
    source = Path(grant.source_path)
    if source.is_absolute() or ".." in source.parts or not source.parts:
        raise TaskValidationError("task_source_path_invalid")
    if not _DIGEST.fullmatch(grant.source_digest):
        raise TaskValidationError("task_source_digest_invalid")
    if not grant.workspace.is_absolute():
        raise TaskValidationError("task_workspace_not_absolute")
    if not grant.branch or len(grant.branch) > 200:
        raise TaskValidationError("task_branch_invalid")
    if not _SHA.fullmatch(grant.starting_sha):
        raise TaskValidationError("task_starting_sha_invalid")
    if grant.agent_kind not in {"codex", "claude"}:
        raise TaskValidationError("task_agent_unsupported")
    if grant.endpoint not in {"commit", "production"}:
        raise TaskValidationError("task_endpoint_invalid")
    if grant.restart_budget not in {0, 1}:
        raise TaskValidationError("restart_budget_invalid")
    has_commands = bool(grant.verification_argv)
    has_reason = bool(grant.no_test_reason and grant.no_test_reason.strip())
    if has_commands == has_reason:
        raise TaskValidationError("verification_contract_invalid")
    if has_reason and len(grant.no_test_reason or "") > 200:
        raise TaskValidationError("verification_contract_invalid")
    for command in grant.verification_argv:
        if not command or len(command) > 64 or any(not item or len(item) > 2048 for item in command):
            raise TaskValidationError("verification_contract_invalid")
    try:
        assert_safe_value(
            {
                "task_id": grant.task_id,
                "parent_task_id": grant.parent_task_id,
                "source_path": grant.source_path,
                "source_digest": grant.source_digest,
                "workspace": str(grant.workspace),
                "branch": grant.branch,
                "starting_sha": grant.starting_sha,
                "agent_kind": grant.agent_kind,
                "agent_version": grant.agent_version,
                "agent_session_id": grant.agent_session_id,
                "origin_host": grant.origin_host,
                "origin_terminal": grant.origin_terminal,
                "execution_host": grant.execution_host,
                "endpoint": grant.endpoint,
                "verification_argv": grant.verification_argv,
                "no_test_reason": grant.no_test_reason,
            },
            location="task metadata",
        )
    except UnsafeOutputError as exc:
        raise TaskValidationError("unsafe_task_metadata") from exc


class TaskRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().absolute()
        self._prepare_parent()
        self._initialize()

    @classmethod
    def open_if_exists(cls, path: Path) -> TaskRegistry | None:
        candidate = path.expanduser().absolute()
        if not candidate.is_file():
            return None
        return cls(candidate)

    def _prepare_parent(self) -> None:
        parent = self.path.parent
        current = parent
        while not current.exists() and current != current.parent:
            current = current.parent
        probe = parent
        while probe != current:
            if probe.is_symlink():
                raise TaskValidationError("registry_parent_symlink")
            probe = probe.parent
        if current.is_symlink() or parent.is_symlink():
            raise TaskValidationError("registry_parent_symlink")
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent.chmod(0o700)

    def _connect(self, *, initialization: bool = False) -> sqlite3.Connection:
        timeout = 2.0 if initialization else 0.25
        connection = sqlite3.connect(self.path, timeout=timeout, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {2000 if initialization else 250}")
        return connection

    def _initialize(self) -> None:
        try:
            with self._connect(initialization=True) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("BEGIN EXCLUSIVE")
                try:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)"
                    )
                    row = connection.execute("SELECT version FROM schema_meta").fetchone()
                    if row is None:
                        connection.execute(
                            "INSERT INTO schema_meta(version) VALUES (?)",
                            (TASK_SCHEMA_VERSION,),
                        )
                    elif int(row["version"]) != TASK_SCHEMA_VERSION:
                        raise TaskValidationError("task_schema_unsupported")
                    self._create_schema(connection)
                    connection.execute("COMMIT")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
        except sqlite3.Error as exc:
            raise TaskValidationError("task_registry_unavailable") from exc
        self.path.chmod(0o600)

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                parent_task_id TEXT REFERENCES tasks(task_id),
                source_path TEXT NOT NULL,
                workspace TEXT NOT NULL,
                branch TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS generations (
                task_id TEXT NOT NULL REFERENCES tasks(task_id),
                generation INTEGER NOT NULL,
                state TEXT NOT NULL,
                source_digest TEXT NOT NULL,
                starting_sha TEXT NOT NULL,
                agent_kind TEXT NOT NULL,
                agent_version TEXT NOT NULL,
                agent_session_id TEXT,
                origin_host TEXT NOT NULL,
                origin_terminal TEXT NOT NULL,
                execution_host TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                verification_json TEXT NOT NULL,
                no_test_reason TEXT,
                restart_budget INTEGER NOT NULL,
                restarts_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                outcome_sha TEXT,
                failure_code TEXT,
                PRIMARY KEY(task_id, generation)
            )""",
            """CREATE TABLE IF NOT EXISTS attempts (
                task_id TEXT NOT NULL,
                generation INTEGER NOT NULL,
                attempt INTEGER NOT NULL,
                state TEXT NOT NULL,
                pid INTEGER,
                pgid INTEGER,
                process_birth TEXT,
                driver_session_id TEXT,
                started_at TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                ended_at TEXT,
                exit_code INTEGER,
                exit_classification TEXT,
                PRIMARY KEY(task_id, generation, attempt),
                FOREIGN KEY(task_id, generation)
                    REFERENCES generations(task_id, generation)
            )""",
        )
        for statement in statements:
            connection.execute(statement)

    @property
    def schema_version(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT version FROM schema_meta").fetchone()
        return int(row["version"])

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except sqlite3.OperationalError as exc:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise TaskConflict("task_registry_busy") from exc
        except BaseException:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> TaskSnapshot:
        commands = json.loads(str(row["verification_json"]))
        return TaskSnapshot(
            task_id=str(row["task_id"]),
            parent_task_id=row["parent_task_id"],
            generation=int(row["generation"]),
            state=str(row["state"]),
            source_path=str(row["source_path"]),
            source_digest=str(row["source_digest"]),
            workspace=str(row["workspace"]),
            branch=str(row["branch"]),
            starting_sha=str(row["starting_sha"]),
            agent_kind=str(row["agent_kind"]),
            agent_version=str(row["agent_version"]),
            agent_session_id=row["agent_session_id"],
            origin_host=str(row["origin_host"]),
            origin_terminal=str(row["origin_terminal"]),
            execution_host=str(row["execution_host"]),
            endpoint=str(row["endpoint"]),
            verification_argv=tuple(tuple(str(item) for item in command) for command in commands),
            no_test_reason=row["no_test_reason"],
            restart_budget=int(row["restart_budget"]),
            restarts_used=int(row["restarts_used"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            outcome_sha=row["outcome_sha"],
            failure_code=row["failure_code"],
        )

    @staticmethod
    def _select_generation(
        connection: sqlite3.Connection, task_id: str, generation: int | None = None
    ) -> sqlite3.Row | None:
        generation_clause = (
            "g.generation = ?"
            if generation is not None
            else "g.generation = (SELECT MAX(g2.generation) FROM generations g2 WHERE g2.task_id = t.task_id)"
        )
        parameters: Sequence[object] = (
            (task_id, generation) if generation is not None else (task_id,)
        )
        return connection.execute(
            f"""
            SELECT t.task_id, t.parent_task_id, t.source_path, t.workspace, t.branch,
                   g.*
              FROM tasks t
              JOIN generations g ON g.task_id = t.task_id
             WHERE t.task_id = ? AND {generation_clause}
            """,
            parameters,
        ).fetchone()

    def arm(self, grant: TaskGrant) -> TaskSnapshot:
        _validate_grant(grant)
        now = _timestamp()
        with self._transaction() as connection:
            if grant.parent_task_id is not None:
                parent = connection.execute(
                    "SELECT 1 FROM tasks WHERE task_id = ?", (grant.parent_task_id,)
                ).fetchone()
                if parent is None:
                    raise TaskValidationError("parent_task_missing")
            task = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (grant.task_id,)
            ).fetchone()
            current_generation = 0
            if task is None:
                connection.execute(
                    """INSERT INTO tasks(
                           task_id, parent_task_id, source_path, workspace, branch, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        grant.task_id,
                        grant.parent_task_id,
                        grant.source_path,
                        str(grant.workspace.resolve()),
                        grant.branch,
                        now,
                    ),
                )
            else:
                current = self._select_generation(connection, grant.task_id)
                if current is not None:
                    current_generation = int(current["generation"])
                    if str(current["state"]) not in _TERMINAL_STATES:
                        raise TaskConflict("task_generation_active")
                stable = (
                    task["parent_task_id"],
                    str(task["source_path"]),
                    str(task["workspace"]),
                    str(task["branch"]),
                )
                requested = (
                    grant.parent_task_id,
                    grant.source_path,
                    str(grant.workspace.resolve()),
                    grant.branch,
                )
                if stable != requested:
                    raise TaskConflict("task_identity_changed")
            generation = current_generation + 1
            verification_json = json.dumps(
                [list(command) for command in grant.verification_argv],
                separators=(",", ":"),
            )
            connection.execute(
                """INSERT INTO generations(
                       task_id, generation, state, source_digest, starting_sha,
                       agent_kind, agent_version, agent_session_id, origin_host,
                       origin_terminal, execution_host, endpoint, verification_json,
                       no_test_reason, restart_budget, created_at, updated_at
                   ) VALUES (?, ?, 'armed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    grant.task_id,
                    generation,
                    grant.source_digest,
                    grant.starting_sha,
                    grant.agent_kind,
                    grant.agent_version,
                    grant.agent_session_id,
                    grant.origin_host,
                    grant.origin_terminal,
                    grant.execution_host,
                    grant.endpoint,
                    verification_json,
                    grant.no_test_reason,
                    grant.restart_budget,
                    now,
                    now,
                ),
            )
            row = self._select_generation(connection, grant.task_id, generation)
            assert row is not None
            return self._snapshot(row)

    def get(self, task_id: str) -> TaskSnapshot:
        with self._connect() as connection:
            row = self._select_generation(connection, task_id)
        if row is None:
            raise TaskValidationError("task_missing")
        return self._snapshot(row)

    def get_generation(self, task_id: str, generation: int) -> TaskSnapshot:
        with self._connect() as connection:
            row = self._select_generation(connection, task_id, generation)
        if row is None:
            raise TaskValidationError("task_generation_missing")
        return self._snapshot(row)

    def list_tasks(self) -> tuple[TaskSnapshot, ...]:
        with self._connect() as connection:
            ids = connection.execute("SELECT task_id FROM tasks ORDER BY task_id").fetchall()
            rows = [self._select_generation(connection, str(item["task_id"])) for item in ids]
        return tuple(self._snapshot(row) for row in rows if row is not None)

    @staticmethod
    def _require_current(
        connection: sqlite3.Connection, task_id: str, generation: int
    ) -> sqlite3.Row:
        current = TaskRegistry._select_generation(connection, task_id)
        if current is None:
            raise TaskValidationError("task_missing")
        if int(current["generation"]) != generation:
            raise TaskConflict("stale_generation")
        return current

    def _set_state(
        self,
        task_id: str,
        generation: int,
        state: str,
        *,
        allowed: frozenset[str],
        outcome_sha: str | None = None,
        failure_code: str | None = None,
    ) -> TaskSnapshot:
        now = _timestamp()
        with self._transaction() as connection:
            current = self._require_current(connection, task_id, generation)
            current_state = str(current["state"])
            if current_state in _TERMINAL_STATES:
                raise TaskConflict("task_generation_terminal")
            if current_state not in allowed:
                raise TaskConflict(f"task_transition_invalid:{current_state}:{state}")
            connection.execute(
                """UPDATE generations
                      SET state = ?, updated_at = ?, outcome_sha = ?, failure_code = ?
                    WHERE task_id = ? AND generation = ?""",
                (state, now, outcome_sha, failure_code, task_id, generation),
            )
            row = self._select_generation(connection, task_id, generation)
            assert row is not None
            return self._snapshot(row)

    def mark_running(self, task_id: str, generation: int) -> TaskSnapshot:
        return self._set_state(
            task_id,
            generation,
            "running",
            allowed=frozenset({"armed", "restarting", "running"}),
        )

    def mark_committing(self, task_id: str, generation: int) -> TaskSnapshot:
        return self._set_state(
            task_id,
            generation,
            "committing",
            allowed=frozenset({"running", "committing"}),
        )

    def mark_awaiting_approval(
        self, task_id: str, generation: int
    ) -> TaskSnapshot:
        return self._set_state(
            task_id,
            generation,
            "awaiting_approval",
            allowed=frozenset({"committing", "awaiting_approval"}),
        )

    def mark_releasing(self, task_id: str, generation: int) -> TaskSnapshot:
        return self._set_state(
            task_id,
            generation,
            "releasing",
            allowed=frozenset({"committing", "awaiting_approval", "releasing"}),
        )

    def complete(self, task_id: str, generation: int, *, outcome_sha: str) -> TaskSnapshot:
        if not _SHA.fullmatch(outcome_sha):
            raise TaskValidationError("task_outcome_sha_invalid")
        return self._set_state(
            task_id,
            generation,
            "succeeded",
            allowed=frozenset({"running", "committing", "releasing"}),
            outcome_sha=outcome_sha,
        )

    def pause(self, task_id: str, generation: int, *, failure_code: str) -> TaskSnapshot:
        return self._set_state(
            task_id,
            generation,
            "paused",
            allowed=_ACTIVE_STATES,
            failure_code=failure_code,
        )

    def mark_lost(self, task_id: str, generation: int) -> TaskSnapshot:
        return self._set_state(
            task_id,
            generation,
            "lost",
            allowed=_ACTIVE_STATES,
            failure_code="supervisor_lost",
        )

    def consume_restart(self, task_id: str, generation: int) -> TaskSnapshot:
        now = _timestamp()
        with self._transaction() as connection:
            current = self._require_current(connection, task_id, generation)
            state = str(current["state"])
            if state in _TERMINAL_STATES:
                raise TaskConflict("task_generation_terminal")
            if state != "running":
                raise TaskConflict("restart_state_invalid")
            used = int(current["restarts_used"])
            budget = int(current["restart_budget"])
            if used >= budget:
                next_state = "paused"
                failure_code = "restart_budget_exhausted"
                next_used = used
            else:
                next_state = "restarting"
                failure_code = None
                next_used = used + 1
            connection.execute(
                """UPDATE generations
                      SET state = ?, restarts_used = ?, failure_code = ?, updated_at = ?
                    WHERE task_id = ? AND generation = ?""",
                (next_state, next_used, failure_code, now, task_id, generation),
            )
            row = self._select_generation(connection, task_id, generation)
            assert row is not None
            return self._snapshot(row)

    def cancel(self, task_id: str, generation: int) -> TaskSnapshot:
        now = _timestamp()
        with self._transaction() as connection:
            current = self._require_current(connection, task_id, generation)
            if str(current["state"]) in _TERMINAL_STATES:
                return self._snapshot(current)
            connection.execute(
                """UPDATE generations SET state = 'cancelled', updated_at = ?
                    WHERE task_id = ? AND generation = ?""",
                (now, task_id, generation),
            )
            row = self._select_generation(connection, task_id, generation)
            assert row is not None
            return self._snapshot(row)

    def record_agent_session(
        self, task_id: str, generation: int, session_id: str
    ) -> TaskSnapshot:
        if not session_id or len(session_id) > 200:
            raise TaskValidationError("agent_session_identity_invalid")
        now = _timestamp()
        with self._transaction() as connection:
            current = self._require_current(connection, task_id, generation)
            if str(current["state"]) in _TERMINAL_STATES:
                raise TaskConflict("task_generation_terminal")
            connection.execute(
                """UPDATE generations SET agent_session_id = ?, updated_at = ?
                    WHERE task_id = ? AND generation = ?""",
                (session_id, now, task_id, generation),
            )
            row = self._select_generation(connection, task_id, generation)
            assert row is not None
            return self._snapshot(row)

    def verify_source(self, task_id: str, generation: int) -> TaskSnapshot:
        snapshot = self.get_generation(task_id, generation)
        current = digest_task_source(Path(snapshot.workspace), snapshot.source_path)
        if current != snapshot.source_digest:
            raise TaskConflict("task_source_drift")
        return snapshot

    def start_attempt(
        self,
        task_id: str,
        generation: int,
        *,
        driver_session_id: str | None = None,
    ) -> AttemptSnapshot:
        now = _timestamp()
        with self._transaction() as connection:
            current = self._require_current(connection, task_id, generation)
            if str(current["state"]) not in {"armed", "restarting"}:
                raise TaskConflict("attempt_start_invalid")
            row = connection.execute(
                "SELECT COALESCE(MAX(attempt), 0) AS current FROM attempts WHERE task_id = ? AND generation = ?",
                (task_id, generation),
            ).fetchone()
            attempt = int(row["current"]) + 1
            connection.execute(
                """INSERT INTO attempts(
                       task_id, generation, attempt, state, driver_session_id,
                       started_at, heartbeat_at
                   ) VALUES (?, ?, ?, 'starting', ?, ?, ?)""",
                (task_id, generation, attempt, driver_session_id, now, now),
            )
            connection.execute(
                "UPDATE generations SET state = 'running', updated_at = ? WHERE task_id = ? AND generation = ?",
                (now, task_id, generation),
            )
            return self._attempt(connection, task_id, generation, attempt)

    @staticmethod
    def _attempt(
        connection: sqlite3.Connection, task_id: str, generation: int, attempt: int
    ) -> AttemptSnapshot:
        row = connection.execute(
            "SELECT * FROM attempts WHERE task_id = ? AND generation = ? AND attempt = ?",
            (task_id, generation, attempt),
        ).fetchone()
        if row is None:
            raise TaskValidationError("task_attempt_missing")
        return AttemptSnapshot(
            task_id=str(row["task_id"]),
            generation=int(row["generation"]),
            attempt=int(row["attempt"]),
            state=str(row["state"]),
            pid=row["pid"],
            pgid=row["pgid"],
            process_birth=row["process_birth"],
            driver_session_id=row["driver_session_id"],
            started_at=str(row["started_at"]),
            heartbeat_at=str(row["heartbeat_at"]),
            ended_at=row["ended_at"],
            exit_code=row["exit_code"],
            exit_classification=row["exit_classification"],
        )

    def record_process(
        self,
        task_id: str,
        generation: int,
        attempt: int,
        *,
        pid: int,
        pgid: int,
        process_birth: str,
    ) -> AttemptSnapshot:
        if pid < 2 or pgid < 2 or not process_birth or len(process_birth) > 100:
            raise TaskValidationError("task_process_identity_invalid")
        with self._transaction() as connection:
            self._require_current(connection, task_id, generation)
            connection.execute(
                """UPDATE attempts
                      SET state = 'running', pid = ?, pgid = ?, process_birth = ?
                    WHERE task_id = ? AND generation = ? AND attempt = ?""",
                (pid, pgid, process_birth, task_id, generation, attempt),
            )
            return self._attempt(connection, task_id, generation, attempt)

    def current_attempt(self, task_id: str, generation: int) -> AttemptSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT MAX(attempt) AS attempt FROM attempts
                    WHERE task_id = ? AND generation = ?""",
                (task_id, generation),
            ).fetchone()
            if row is None or row["attempt"] is None:
                return None
            return self._attempt(connection, task_id, generation, int(row["attempt"]))

    def heartbeat(
        self, task_id: str, generation: int, attempt: int
    ) -> AttemptSnapshot:
        now = _timestamp()
        with self._transaction() as connection:
            current = self._require_current(connection, task_id, generation)
            if str(current["state"]) != "running":
                raise TaskConflict("heartbeat_state_invalid")
            connection.execute(
                """UPDATE attempts SET heartbeat_at = ?
                    WHERE task_id = ? AND generation = ? AND attempt = ?""",
                (now, task_id, generation, attempt),
            )
            connection.execute(
                """UPDATE generations SET updated_at = ?
                    WHERE task_id = ? AND generation = ?""",
                (now, task_id, generation),
            )
            return self._attempt(connection, task_id, generation, attempt)

    def finish_attempt(
        self,
        task_id: str,
        generation: int,
        attempt: int,
        *,
        exit_code: int,
        classification: str,
    ) -> AttemptSnapshot:
        now = _timestamp()
        with self._transaction() as connection:
            self._require_current(connection, task_id, generation)
            connection.execute(
                """UPDATE attempts
                      SET state = 'finished', ended_at = ?, heartbeat_at = ?,
                          exit_code = ?, exit_classification = ?
                    WHERE task_id = ? AND generation = ? AND attempt = ?""",
                (now, now, exit_code, classification, task_id, generation, attempt),
            )
            return self._attempt(connection, task_id, generation, attempt)
