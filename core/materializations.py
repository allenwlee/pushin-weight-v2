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
