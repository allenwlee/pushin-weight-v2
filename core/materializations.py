"""Publication lifecycle for code-defined, time-bounded derived datasets.

Definitions are application code, never SQL or relation names supplied by a
request. Data and invalidation remain owned by each dataset's native migration.
This state is mutable; saved research/article evidence keeps its own identity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import DatabaseError, connection, transaction
from django.db.backends.utils import CursorWrapper

HISTORY_CLEAN_SQL = (
    "(source_generation = published_generation OR dirty_since >= cutoff)"
)
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_DATASET_KEY = re.compile(r"^[a-z][a-z0-9_.-]*\.v[1-9][0-9]*$")


@dataclass(frozen=True)
class MaterializationDefinition:
    dataset_key: str
    relation: str
    source_tables: tuple[str, ...]
    lock_id: int
    cutoff_sql: str

    def __post_init__(self) -> None:
        if len(self.dataset_key) > 160 or not _DATASET_KEY.fullmatch(self.dataset_key):
            raise ValueError("Materialization requires a versioned dataset key")
        if not self.source_tables or not all(
            _IDENTIFIER.fullmatch(name) for name in (self.relation, *self.source_tables)
        ):
            raise ValueError("Materialization requires explicit local relation names")


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


def refresh_materialization(
    definition: MaterializationDefinition,
) -> dict[str, str | int]:
    """Atomically rebuild/publish one dataset, independently of other datasets."""
    try:
        if not _initialize(definition):
            return {"status": "busy"}
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [definition.lock_id])
            if not cursor.fetchone()[0]:
                return {"status": "busy"}
            cursor.execute("SET LOCAL lock_timeout = '2s'")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
            cursor.execute(
                f"SELECT source_generation, {HISTORY_CLEAN_SQL}, cutoff, "
                f"{definition.cutoff_sql} FROM materialization_state WHERE dataset_key = %s",
                [definition.dataset_key],
            )
            state = cursor.fetchone()
            if state is None:
                return {"status": "unavailable"}
            generation, clean, cutoff, target = state
            populated = is_populated(cursor, definition)
            if populated and clean and cutoff == target:
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
