"""One PostgreSQL advisory writer lock for every harvest entrypoint."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connections

_CONTEXT_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")
_CONTENTION_COUNTS: dict[tuple[int, int], int] = {}
_COUNTS_LOCK = threading.Lock()


@dataclass(frozen=True)
class WriterLockContention:
    """Typed, redacted seam consumed by the later summary/alert unit."""

    kind: str
    environment: str
    execution_mode: str
    entrypoint: str
    run_id: str
    owner_backend_pid: int | None
    owner_context: str
    consecutive_count: int
    alert_required: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "environment": self.environment,
            "execution_mode": self.execution_mode,
            "entrypoint": self.entrypoint,
            "run_id": self.run_id,
            "owner_backend_pid": self.owner_backend_pid,
            "owner_context": self.owner_context,
            "consecutive_count": self.consecutive_count,
            "alert_required": self.alert_required,
        }


@dataclass(frozen=True)
class WriterLockLease:
    acquired: bool
    environment: str
    execution_mode: str
    entrypoint: str
    run_id: str
    backend_pid: int | None
    contention: WriterLockContention | None = None


def _lock_keys(environment: str) -> tuple[int, int, int, int]:
    digest = hashlib.sha256(
        f"pushinweight:harvest-writer:{environment}".encode()
    ).digest()
    unsigned = (
        int.from_bytes(digest[:4], "big"),
        int.from_bytes(digest[4:8], "big"),
    )
    signed = tuple(value - 2**32 if value >= 2**31 else value for value in unsigned)
    return signed[0], signed[1], unsigned[0], unsigned[1]


def _safe_context(execution_mode: str, entrypoint: str, run_id: str) -> str:
    raw = f"harvest:{execution_mode}:{entrypoint}:{run_id}"
    return _CONTEXT_SAFE.sub("_", raw)[:63]


def _owner_context(cursor, class_id: int, object_id: int) -> tuple[int | None, str]:
    cursor.execute(
        """
        SELECT activity.pid, activity.application_name
          FROM pg_locks AS held
          JOIN pg_stat_activity AS activity ON activity.pid = held.pid
         WHERE held.locktype = 'advisory'
           AND held.granted
           AND held.objsubid = 2
           AND held.classid::bigint = %s
           AND held.objid::bigint = %s
         ORDER BY activity.pid
         LIMIT 1
        """,
        [class_id, object_id],
    )
    row = cursor.fetchone()
    if row is None:
        return None, "unknown"
    return int(row[0]), str(row[1] or "unknown")


@contextmanager
def harvest_writer_lock(
    *,
    execution_mode: str,
    entrypoint: str,
    run_id: str | None = None,
    environment: str | None = None,
    using: str = "default",
    contention_alert_threshold: int = 1,
    on_contention: Callable[[WriterLockContention], None] | None = None,
) -> Iterator[WriterLockLease]:
    """Try the shared session lock once; never wait, steal, or use SQLite.

    The lock is session-scoped so PostgreSQL releases it automatically if the
    owner process or database connection dies. Contention performs only
    read-only owner inspection and invokes a typed callback for later summary
    and alert handling. Render starts cron runs in fresh processes, so the
    default alerts on the first observed contention; the in-process count is
    diagnostic context only and is never relied on for durable detection.
    """

    database = connections[using]
    if database.vendor != "postgresql":
        raise ImproperlyConfigured(
            "the harvest writer lock requires PostgreSQL; SQLite cannot prove "
            "single-flight behavior"
        )

    environment = (
        environment
        or os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT")
        or os.environ.get("RENDER_GIT_BRANCH")
        or str(database.settings_dict.get("NAME") or "default")
    )
    run_id = run_id or uuid.uuid4().hex
    signed_class, signed_object, class_id, object_id = _lock_keys(environment)
    lock_identity = (class_id, object_id)
    application_name = _safe_context(execution_mode, entrypoint, run_id)

    database.ensure_connection()
    previous_application_name = ""
    acquired = False
    backend_pid: int | None = None
    with database.cursor() as cursor:
        cursor.execute("SHOW application_name")
        previous_application_name = str(cursor.fetchone()[0] or "")
        cursor.execute(
            "SELECT set_config('application_name', %s, false)", [application_name]
        )
        cursor.execute("SELECT pg_backend_pid()")
        backend_pid = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s, %s)",
            [signed_class, signed_object],
        )
        acquired = bool(cursor.fetchone()[0])

        if not acquired:
            owner_pid, owner_context = _owner_context(cursor, class_id, object_id)
            with _COUNTS_LOCK:
                count = _CONTENTION_COUNTS.get(lock_identity, 0) + 1
                _CONTENTION_COUNTS[lock_identity] = count
            contention = WriterLockContention(
                kind="writer_lock_contended",
                environment=environment,
                execution_mode=execution_mode,
                entrypoint=entrypoint,
                run_id=run_id,
                owner_backend_pid=owner_pid,
                owner_context=owner_context,
                consecutive_count=count,
                alert_required=count >= contention_alert_threshold,
            )
            cursor.execute(
                "SELECT set_config('application_name', %s, false)",
                [previous_application_name],
            )
            if on_contention is not None:
                on_contention(contention)
            yield WriterLockLease(
                acquired=False,
                environment=environment,
                execution_mode=execution_mode,
                entrypoint=entrypoint,
                run_id=run_id,
                backend_pid=backend_pid,
                contention=contention,
            )
            return

    with _COUNTS_LOCK:
        _CONTENTION_COUNTS.pop(lock_identity, None)

    try:
        yield WriterLockLease(
            acquired=True,
            environment=environment,
            execution_mode=execution_mode,
            entrypoint=entrypoint,
            run_id=run_id,
            backend_pid=backend_pid,
        )
    finally:
        # A closed/broken connection already released the session lock. Do not
        # reconnect merely to unlock: that would target a different backend.
        if acquired and database.connection is not None:
            try:
                with database.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(%s, %s)",
                        [signed_class, signed_object],
                    )
                    cursor.execute(
                        "SELECT set_config('application_name', %s, false)",
                        [previous_application_name],
                    )
            except DatabaseError:
                database.close()
