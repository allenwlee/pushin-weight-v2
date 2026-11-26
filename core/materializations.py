"""Publication lifecycle for code-defined, time-bounded derived datasets.

Definitions are application code, never SQL or relation names supplied by a
request. Data and invalidation remain owned by each dataset's native migration.
This state is mutable; saved research/article evidence keeps its own identity.
"""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from django.db import DatabaseError, connection, transaction
from django.db.backends.utils import CursorWrapper

HISTORY_CLEAN_SQL = (
    "(source_generation = published_generation OR dirty_since >= cutoff)"
)
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_TIMEOUT = re.compile(r"^[1-9][0-9]*(?:ms|s|min)$")
_WORK_MEM = re.compile(r"^[1-9][0-9]*(?:kB|MB|GB)$")
_DATASET_KEY = re.compile(r"^[a-z][a-z0-9_.-]*\.v[1-9][0-9]*$")
# The refresh is scheduled during the harvest window. Retry without waiting
# on source locks until the harvester has a chance to finish its write batch.
_ONLINE_BARRIER_ATTEMPTS = 361
_ONLINE_BARRIER_RETRY_SECONDS = 1


@dataclass(frozen=True)
class MaterializationDefinition:
    dataset_key: str
    relation: str
    source_tables: tuple[str, ...]
    lock_id: int
    cutoff_sql: str
    refresh_timeout: str = "120s"
    advance_barrier: bool = False
    bootstrap_timeout: str | None = None
    refresh_work_mem: str | None = None
    online_refresh: bool = False
    online_barrier_attempts: int | None = None
    online_capability: str | None = None
    online_dirty_ids_capability: str | None = None

    def __post_init__(self) -> None:
        if len(self.dataset_key) > 160 or not _DATASET_KEY.fullmatch(self.dataset_key):
            raise ValueError("Materialization requires a versioned dataset key")
        if not self.source_tables or not all(
            _IDENTIFIER.fullmatch(name) for name in (self.relation, *self.source_tables)
        ):
            raise ValueError("Materialization requires explicit local relation names")
        if not _TIMEOUT.fullmatch(self.refresh_timeout):
            raise ValueError("Materialization requires a positive explicit timeout")
        if self.bootstrap_timeout is not None and not _TIMEOUT.fullmatch(self.bootstrap_timeout):
            raise ValueError("Materialization requires a positive explicit bootstrap timeout")
        if self.refresh_work_mem is not None and not _WORK_MEM.fullmatch(self.refresh_work_mem):
            raise ValueError("Materialization requires positive explicit work_mem units")
        if self.online_barrier_attempts is not None and self.online_barrier_attempts < 1:
            raise ValueError("Materialization requires a positive barrier attempt count")
        if self.online_capability is not None and (
            not self.online_refresh or not _IDENTIFIER.fullmatch(self.online_capability)
        ):
            raise ValueError("Online capability must be an explicit local function name")
        if self.online_dirty_ids_capability is not None and (
            not self.online_refresh or not _IDENTIFIER.fullmatch(self.online_dirty_ids_capability)
        ):
            raise ValueError("Dirty ID capability must be an explicit local function name")


def sqlstate(error: BaseException) -> str | None:
    return getattr(error.__cause__, "sqlstate", None)


def is_populated(cursor: CursorWrapper, definition: MaterializationDefinition) -> bool:
    cursor.execute(
        "SELECT relispopulated FROM pg_class "
        "WHERE oid = to_regclass(%s) AND relkind = 'm'",
        [definition.relation],
    )
    row = cursor.fetchone()
    return bool(row and row[0])


class _SourceChanged(Exception):
    pass


def _initialize(definition: MaterializationDefinition) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM materialization_state WHERE dataset_key = %s",
            [definition.dataset_key],
        )
        if cursor.fetchone():
            return True
    if connection.in_atomic_block:
        raise RuntimeError(
            "Missing materialization state must initialize outside a transaction"
        )
    # A source writer may have invalidated before this row existed. Commit the
    # short writer barrier before counting; readers meanwhile use exact source.
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [definition.lock_id])
        if not cursor.fetchone()[0]:
            return False
        cursor.execute("SET LOCAL lock_timeout = '2s'")
        tables = ", ".join(
            connection.ops.quote_name(t) for t in definition.source_tables
        )
        cursor.execute(f"LOCK TABLE {tables} IN SHARE ROW EXCLUSIVE MODE NOWAIT")
        cursor.execute(
            "INSERT INTO materialization_state (dataset_key, source_generation) "
            "VALUES (%s, 0) ON CONFLICT DO NOTHING",
            [definition.dataset_key],
        )
    return True


def _prepare_advance(
    definition: MaterializationDefinition,
) -> tuple[bool, datetime | None]:
    """Drain in-flight writers without holding any source lock while counting.

    Freeze the target before the barrier. A refresh starting across UTC midnight
    must not silently advance to a newer cutoff than the barrier actually proved.
    Same-cutoff publication also needs the barrier: a child writer may still
    observe a parent's old recent date while a correction moves it into history.
    """
    if not definition.advance_barrier:
        return True, None
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT cutoff, {definition.cutoff_sql} FROM materialization_state "
            "WHERE dataset_key = %s",
            [definition.dataset_key],
        )
        state = cursor.fetchone()
    if state is None:
        return False, None
    _cutoff, target = state
    if connection.in_atomic_block:
        raise RuntimeError("The advance barrier must commit before refresh counting")
    tables = ", ".join(
        connection.ops.quote_name(table) for table in definition.source_tables
    )
    for attempt in range(10):
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(f"LOCK TABLE {tables} IN SHARE MODE NOWAIT")
            return True, target
        except DatabaseError as error:
            if sqlstate(error) != "55P03":
                raise
        if attempt < 9:
            time.sleep(0.2)
    return False, None


@contextmanager
def _refresh_settings(cursor, definition, populated):
    cursor.execute("SELECT current_setting('statement_timeout'),current_setting('work_mem')")
    previous_timeout, previous_memory = cursor.fetchone()
    timeout = (
        definition.bootstrap_timeout
        if not populated and definition.bootstrap_timeout is not None
        else definition.refresh_timeout
    )
    cursor.execute("SELECT set_config('statement_timeout', %s, true)", [timeout])
    if definition.refresh_work_mem is not None:
        cursor.execute("SELECT set_config('work_mem', %s, true)", [definition.refresh_work_mem])
    # On exceptions the surrounding atomic transaction/savepoint restores
    # settings; cleanup SQL in an aborted transaction would mask the error.
    yield
    cursor.execute("SELECT set_config('statement_timeout', %s, true)", [previous_timeout])
    if definition.refresh_work_mem is not None:
        cursor.execute("SELECT set_config('work_mem', %s, true)", [previous_memory])


def refresh_materialization(
    definition: MaterializationDefinition,
    *,
    force: bool = False,
) -> dict[str, str | int]:
    """Atomically rebuild/publish one dataset, independently of other datasets."""
    if definition.online_refresh and not connection.in_atomic_block:
        return _refresh_materialization_online(definition, force=force)
    try:
        if not _initialize(definition):
            return {"status": "busy"}
        ready, barrier_target = _prepare_advance(definition)
        if not ready:
            return {"status": "busy"}
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [definition.lock_id])
            if not cursor.fetchone()[0]:
                return {"status": "busy"}
            cursor.execute("SET LOCAL lock_timeout = '2s'")
            populated = is_populated(cursor, definition)
            with _refresh_settings(cursor, definition, populated):
                target_sql = (
                    "%s::timestamptz" if barrier_target is not None else definition.cutoff_sql
                )
                parameters = (
                    [barrier_target, definition.dataset_key]
                    if barrier_target is not None else [definition.dataset_key]
                )
                cursor.execute(
                    f"SELECT source_generation, {HISTORY_CLEAN_SQL}, cutoff, "
                    f"{target_sql} FROM materialization_state WHERE dataset_key = %s",
                    parameters,
                )
                state = cursor.fetchone()
                if state is None:
                    return {"status": "unavailable"}
                generation, clean, cutoff, target = state
                # Another process may have advanced farther after our preflight.
                if barrier_target is not None and cutoff is not None and cutoff > target:
                    return {"status": "busy"}
                if populated and clean and cutoff == target and not force:
                    return {"status": "skipped", "cutoff": cutoff.isoformat()}
                cursor.execute(
                    "REFRESH MATERIALIZED VIEW "
                    + ("CONCURRENTLY " if populated else "")
                    + connection.ops.quote_name(definition.relation)
                )
                cursor.execute(
                    "UPDATE materialization_state SET published_generation = %s, "
                    "cutoff = %s, refreshed_at = clock_timestamp(), dirty_since = NULL "
                    "WHERE dataset_key = %s AND source_generation = %s",
                    [generation, target, definition.dataset_key, generation],
                )
                if cursor.rowcount != 1:
                    raise _SourceChanged
                return {
                    "status": "refreshed",
                    "cutoff": target.isoformat(),
                    "generation": generation,
                }
    except _SourceChanged:
        return {"status": "changed"}
    except DatabaseError as error:
        if sqlstate(error) == "55P03":
            return {"status": "busy"}
        raise


def _refresh_materialization_online(
    definition: MaterializationDefinition, *, force: bool,
) -> dict[str, str | int]:
    """Publish a snapshot while preserving invalidations from active writers."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [definition.lock_id])
        if not cursor.fetchone()[0]:
            return {"status": "busy"}

    marker_set = False
    try:
        track_dirty_ids = False
        if definition.online_capability:
            # The migration's reverse path takes this same lock before
            # removing the capability and restoring older trigger functions.
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regprocedure(%s) IS NOT NULL", [definition.online_capability + "()"])
                if not cursor.fetchone()[0]:
                    return {"status": "unavailable"}
        if definition.online_dirty_ids_capability:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regprocedure(%s) IS NOT NULL", [definition.online_dirty_ids_capability + "()"])
                track_dirty_ids = cursor.fetchone()[0]
        if not _initialize(definition):
            return {"status": "busy"}
        # Freeze the view cutoff before the short source-writer barrier.
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {definition.cutoff_sql} FROM materialization_state "
                "WHERE dataset_key = %s",
                [definition.dataset_key],
            )
            state = cursor.fetchone()
        if state is None:
            return {"status": "unavailable"}
        barrier_target = state[0]
        tables = ", ".join(
            connection.ops.quote_name(table) for table in definition.source_tables
        )

        # The marker and the writer barrier must commit together. A writer
        # starting after this commit will see the marker in its trigger.
        attempts = definition.online_barrier_attempts or _ONLINE_BARRIER_ATTEMPTS
        for attempt in range(attempts):
            try:
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(f"LOCK TABLE {tables} IN SHARE MODE NOWAIT")
                    populated = is_populated(cursor, definition)
                    cursor.execute(
                        f"SELECT source_generation, {HISTORY_CLEAN_SQL}, cutoff "
                        + (", dirty_post_ids IS NOT NULL " if track_dirty_ids else ", TRUE ")
                        + "FROM materialization_state WHERE dataset_key = %s FOR UPDATE NOWAIT",
                        [definition.dataset_key],
                    )
                    state = cursor.fetchone()
                    if state is None:
                        return {"status": "unavailable"}
                    generation, clean, cutoff, tracked = state
                    target = barrier_target
                    if cutoff is not None and cutoff > target:
                        return {"status": "busy"}
                    if populated and clean and cutoff == target and tracked and not force:
                        # A crashed refresher may have left its marker behind.
                        cursor.execute(
                            "UPDATE materialization_state SET refresh_generation = NULL, "
                            "refresh_dirty_since = NULL "
                            + (", refresh_dirty_post_ids = NULL " if track_dirty_ids else "")
                            + "WHERE dataset_key = %s",
                            [definition.dataset_key],
                        )
                        return {"status": "skipped", "cutoff": cutoff.isoformat()}
                    cursor.execute(
                        "UPDATE materialization_state SET refresh_generation = %s, "
                        "refresh_dirty_since = NULL "
                        + (", refresh_dirty_post_ids = ARRAY[]::text[] " if track_dirty_ids else "")
                        + "WHERE dataset_key = %s",
                        [generation, definition.dataset_key],
                    )
                break
            except DatabaseError as error:
                if sqlstate(error) != "55P03":
                    raise
                if attempt == attempts - 1:
                    return {"status": "busy"}
                time.sleep(_ONLINE_BARRIER_RETRY_SECONDS)
        marker_set = True

        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '2s'")
            with _refresh_settings(cursor, definition, populated):
                cursor.execute(
                    "REFRESH MATERIALIZED VIEW "
                    + ("CONCURRENTLY " if populated else "")
                    + connection.ops.quote_name(definition.relation)
                )
                cursor.execute(
                    "UPDATE materialization_state SET published_generation = refresh_generation, "
                    "cutoff = %s, refreshed_at = clock_timestamp(), "
                    "dirty_since = refresh_dirty_since, refresh_generation = NULL, "
                    "refresh_dirty_since = NULL "
                    + (", dirty_post_ids = refresh_dirty_post_ids, refresh_dirty_post_ids = NULL " if track_dirty_ids else "")
                    + "WHERE dataset_key = %s "
                    "AND refresh_generation = %s "
                    "AND (source_generation = refresh_generation OR refresh_dirty_since IS NOT NULL)",
                    [target, definition.dataset_key, generation],
                )
                if cursor.rowcount != 1:
                    raise _SourceChanged
        marker_set = False
        return {"status": "refreshed", "cutoff": target.isoformat(), "generation": generation}
    except _SourceChanged:
        return {"status": "changed"}
    except DatabaseError as error:
        if sqlstate(error) == "55P03":
            return {"status": "busy"}
        raise
    finally:
        try:
            if marker_set:
                # The view refresh rolled back. Keep the original dirty
                # boundary, including every source write made meanwhile.
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE materialization_state SET refresh_generation = NULL, "
                        "refresh_dirty_since = NULL "
                        + (", refresh_dirty_post_ids = NULL " if track_dirty_ids else "")
                        + "WHERE dataset_key = %s "
                        "AND refresh_generation = %s",
                        [definition.dataset_key, generation],
                    )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [definition.lock_id])
