"""One PostgreSQL advisory writer lock for every harvest entrypoint."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connections

_CONTEXT_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")
_CONTENTION_COUNTS: dict[tuple[int, int], int] = {}
_COUNTS_LOCK = threading.Lock()
_BACKGROUND_WRITER: ContextVar[tuple[str, int, int] | None] = ContextVar(
    "harvest_background_writer", default=None,
)
logger = logging.getLogger(__name__)


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
    waited_seconds: float = 0.0


def background_writer_identity() -> tuple[str, int, int] | None:
    return _BACKGROUND_WRITER.get()


def backfill_yield_requested(identity: tuple[str, int, int] | None = None) -> bool:
    """Stop starting paid background work while PostgreSQL queues live work.

    Only the owning background execution checks this seam. The current request
    may finish and checkpoint under its existing lock; no writer is preempted.
    PostgreSQL's queue prevents the next background page from barging ahead.
    """
    active = identity or background_writer_identity()
    if active is None:
        return False
    using, class_id, object_id = active
    with connections[using].cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_locks AS waiting
                JOIN pg_stat_activity AS activity ON activity.pid = waiting.pid
                WHERE waiting.locktype = 'advisory' AND NOT waiting.granted
                  AND waiting.objsubid = 2 AND waiting.classid::bigint = %s
                  AND waiting.objid::bigint = %s
                  AND activity.application_name LIKE 'harvest:live:%%'
            )
            """,
            [class_id, object_id],
        )
        return bool(cursor.fetchone()[0])


def _lock_keys(environment: str, lock_scope: str = "harvest-writer") -> tuple[int, int, int, int]:
    digest = hashlib.sha256(
        f"pushinweight:{lock_scope}:{environment}".encode()
    ).digest()
    unsigned = (
        int.from_bytes(digest[:4], "big"),
        int.from_bytes(digest[4:8], "big"),
    )
    signed = tuple(value - 2**32 if value >= 2**31 else value for value in unsigned)
    return signed[0], signed[1], unsigned[0], unsigned[1]


def _safe_context(execution_mode: str, entrypoint: str, run_id: str, lock_scope: str = "harvest-writer") -> str:
    prefix = "harvest" if lock_scope == "harvest-writer" else lock_scope
    raw = f"{prefix}:{execution_mode}:{entrypoint}:{run_id}"
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
    lock_scope: str = "harvest-writer",
    using: str = "default",
    contention_alert_threshold: int = 1,
    on_contention: Callable[[WriterLockContention], None] | None = None,
    wait_for_backfill_seconds: float = 0,
) -> Iterator[WriterLockLease]:
    """Keep one writer; scheduled live work may queue behind a backfill page.

    The lock is session-scoped so PostgreSQL releases it automatically if the
    owner process or database connection dies. Contention performs only
    read-only owner inspection and invokes a typed callback for later summary
    and alert handling. Render starts cron runs in fresh processes, so the
    default alerts on the first observed contention; the in-process count is
    diagnostic context only and is never relied on for durable detection.
    Waiting is opt-in, limited to 120 seconds, and only behind a positively
    identified backfill owner. Live/live and other writers remain nonblocking.
    """

    if not math.isfinite(wait_for_backfill_seconds) or not 0 <= wait_for_backfill_seconds <= 120:
        raise ValueError("backfill writer wait must be between 0 and 120 seconds")
    if wait_for_backfill_seconds and (execution_mode != "live" or lock_scope != "harvest-writer"):
        raise ValueError("only the live harvest writer may wait for backfill")

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
    signed_class, signed_object, class_id, object_id = _lock_keys(environment, lock_scope)
    lock_identity = (class_id, object_id)
    application_name = _safe_context(execution_mode, entrypoint, run_id, lock_scope)

    database.ensure_connection()
    owner_connection = database.connection
    previous_application_name = ""
    previous_lock_timeout: str | None = None
    acquired = False
    waited_seconds = 0.0
    timed_out = False
    background_token = None
    backend_pid: int | None = None
    try:
        with database.cursor() as cursor:
            cursor.execute("SHOW application_name")
            previous_application_name = str(cursor.fetchone()[0] or "")
            cursor.execute("SELECT set_config('application_name', %s, false)", [application_name])
            cursor.execute("SELECT pg_backend_pid()")
            backend_pid = int(cursor.fetchone()[0])
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [signed_class, signed_object])
            acquired = bool(cursor.fetchone()[0])
            owner_pid, owner_context = (None, "unknown")
            if not acquired:
                owner_pid, owner_context = _owner_context(cursor, class_id, object_id)
            if not acquired and wait_for_backfill_seconds and owner_pid is None:
                # The last historical page can release between the failed try
                # and inspection. An empty owner must not discard the live tick.
                cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [signed_class, signed_object])
                acquired = bool(cursor.fetchone()[0])
                if not acquired:
                    owner_pid, owner_context = _owner_context(cursor, class_id, object_id)
            if not acquired and wait_for_backfill_seconds and owner_context.startswith("harvest:backfill:"):
                cursor.execute("SHOW lock_timeout")
                previous_lock_timeout = str(cursor.fetchone()[0])
                cursor.execute("SELECT set_config('lock_timeout', %s, false)",
                               [f"{max(1, int(wait_for_backfill_seconds * 1000))}ms"])
                logger.info("Live harvest waiting for backfill writer: owner=%s", owner_context)
                started = time.monotonic()
                try:
                    # Unlike polling, a queued PostgreSQL lock request prevents
                    # newly arriving background pages from reacquiring first.
                    cursor.execute("SELECT pg_advisory_lock(%s, %s)", [signed_class, signed_object])
                    acquired = True
                except DatabaseError as exc:
                    cause = exc.__cause__
                    code = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
                    if code != "55P03":
                        raise
                    timed_out = True
                finally:
                    waited_seconds = time.monotonic() - started
                    cursor.execute("SELECT set_config('lock_timeout', %s, false)", [previous_lock_timeout])
            if not acquired:
                owner_pid, owner_context = _owner_context(cursor, class_id, object_id)

        if not acquired:
            with _COUNTS_LOCK:
                count = _CONTENTION_COUNTS.get(lock_identity, 0) + 1
                _CONTENTION_COUNTS[lock_identity] = count
            contention = WriterLockContention(
                kind="writer_lock_wait_timeout" if timed_out else "writer_lock_contended",
                environment=environment,
                execution_mode=execution_mode,
                entrypoint=entrypoint,
                run_id=run_id,
                owner_backend_pid=owner_pid,
                owner_context=owner_context,
                consecutive_count=count,
                alert_required=count >= contention_alert_threshold,
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
                waited_seconds=waited_seconds,
            )
            return

        with _COUNTS_LOCK:
            _CONTENTION_COUNTS.pop(lock_identity, None)

        if execution_mode == "backfill" and lock_scope == "harvest-writer":
            background_token = _BACKGROUND_WRITER.set((using, class_id, object_id))
        yield WriterLockLease(
            acquired=True,
            environment=environment,
            execution_mode=execution_mode,
            entrypoint=entrypoint,
            run_id=run_id,
            backend_pid=backend_pid,
            waited_seconds=waited_seconds,
        )
    finally:
        if background_token is not None:
            _BACKGROUND_WRITER.reset(background_token)
        # A closed/broken connection already released the session lock. Do not
        # reconnect merely to unlock: that would target a different backend.
        if database.connection is owner_connection and owner_connection is not None:
            try:
                with database.cursor() as cursor:
                    if acquired:
                        cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [signed_class, signed_object])
                    cursor.execute(
                        "SELECT set_config('application_name', %s, false)",
                        [previous_application_name],
                    )
            except DatabaseError:
                database.close()
