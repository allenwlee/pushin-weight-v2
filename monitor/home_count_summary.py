"""Rebuildable homepage counts. Source rows remain the correctness fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from django.db import DatabaseError, connection, transaction
from django.db.backends.utils import CursorWrapper

# Separate from collection/migration locks. Only maintenance takes this key.
REFRESH_LOCK = 726_514_093
_RECOVERABLE = {"42P01", "55000", "55P03", "57014"}
_HISTORY_CLEAN = "(source_generation = published_generation OR dirty_since >= cutoff)"


def _sqlstate(error: BaseException) -> str | None:
    return getattr(error.__cause__, "sqlstate", None)


def utc_day(at: datetime) -> datetime:
    return at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _populated(cursor: CursorWrapper) -> bool:
    cursor.execute(
        "SELECT relispopulated FROM pg_class "
        "WHERE oid = to_regclass('home_brand_time_counts') AND relkind = 'm'"
    )
    row = cursor.fetchone()
    return bool(row and row[0])


class _SourceChanged(Exception):
    pass


def _initialize_snapshot() -> bool:
    """Repair missing state after previously untracked source writers finish."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM home_count_snapshot WHERE id = 1")
        if cursor.fetchone():
            return True
    if connection.in_atomic_block:
        raise RuntimeError(
            "Missing home count state must be initialized outside a transaction"
        )
    # Commit this short barrier before counting. A pre-existing writer might
    # have run its trigger while no singleton existed. NOWAIT avoids waiting
    # on it or creating a lock-order deadlock; the next maintenance poll retries.
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [REFRESH_LOCK])
        if not cursor.fetchone()[0]:
            return False
        cursor.execute("SET LOCAL lock_timeout = '2s'")
        cursor.execute(
            "LOCK TABLE brands, posts, posts_brands, posts_unsanctioned_flags, "
            "posts_untracked_brand_promotions IN SHARE ROW EXCLUSIVE MODE NOWAIT"
        )
        cursor.execute(
            "INSERT INTO home_count_snapshot (id, source_generation) "
            "VALUES (1, 0) ON CONFLICT DO NOTHING"
        )
    return True


def refresh_home_counts() -> dict[str, str | int]:
    """Publish the view and its cutoff atomically; never lock writers to count."""
    try:
        if not _initialize_snapshot():
            return {"status": "busy"}
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [REFRESH_LOCK])
            if not cursor.fetchone()[0]:
                return {"status": "busy"}
            cursor.execute("SET LOCAL lock_timeout = '2s'")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
            cursor.execute(
                f"SELECT source_generation, {_HISTORY_CLEAN}, cutoff, "
                "date_trunc('day', transaction_timestamp(), 'UTC') "
                "FROM home_count_snapshot WHERE id = 1"
            )
            state = cursor.fetchone()
            if state is None:
                return {"status": "unavailable"}
            generation, clean, cutoff, today = state
            populated = _populated(cursor)
            if populated and clean and cutoff == today:
                return {"status": "skipped", "cutoff": cutoff.isoformat()}
            cursor.execute(
                "REFRESH MATERIALIZED VIEW "
                + ("CONCURRENTLY " if populated else "")
                + "home_brand_time_counts"
            )
            cursor.execute(
                "UPDATE home_count_snapshot SET published_generation = %s, "
                "cutoff = %s, refreshed_at = clock_timestamp(), dirty_since = NULL "
                "WHERE id = 1 AND source_generation = %s",
                [generation, today, generation],
            )
            if cursor.rowcount != 1:
                # Roll back the REFRESH as well as publication. A source
                # commit during counting must never appear clean.
                raise _SourceChanged
            return {
                "status": "refreshed",
                "cutoff": today.isoformat(),
                "generation": generation,
            }
    except _SourceChanged:
        return {"status": "changed"}
    except DatabaseError as error:
        if _sqlstate(error) == "55P03":
            return {"status": "busy"}
        raise


def read_home_counts(
    *,
    start: datetime,
    end: datetime,
    brand_ids: list[str],
    midpoint: datetime | None = None,
    timezone_name: str = "UTC",
    legacy_flag: bool | None = None,
    promotion_flag: bool | None = None,
) -> list[dict[str, Any]] | None:
    """Read one SQL snapshot of valid history plus its exact live tail.

    Return None for unavailable/dirty history, distinct from a valid empty result.
    Bounds before the live UTC day must align with the materialized grain.
    Callers validate every local chart midnight, including DST transitions.
    """
    if connection.vendor != "postgresql":
        return None
    day = utc_day(end)
    if start < day and start.timestamp() % 900:
        return None
    if midpoint is not None and midpoint.timestamp() % 900:
        return None
    try:
        # A catalog/lifecycle preflight avoids taking a read lock on an initially
        # unpopulated view while its first ordinary REFRESH is running.
        with transaction.atomic(), connection.cursor() as cursor:
            if not _populated(cursor):
                return None
            cursor.execute(
                "SELECT 1 FROM home_count_snapshot WHERE id = 1 "
                f"AND {_HISTORY_CLEAN} AND cutoff >= %s",
                [day],
            )
            if not cursor.fetchone():
                return None
            flag_sql = ""
            raw_flag_sql = ""
            for column, alias, value in (
                ("legacy_flag", "f", legacy_flag),
                ("promotion_flag", "u", promotion_flag),
            ):
                if value is not None:
                    flag_sql += f" AND {column} = {'TRUE' if value else 'FALSE'}"
                    raw_flag_sql += (
                        f" AND {alias}.post_id IS {'NOT NULL' if value else 'NULL'}"
                    )
            if midpoint is None:
                group_sql = "(bucket_start AT TIME ZONE %s)::date"
                group_params = [timezone_name]
            else:
                group_sql = "(bucket_start >= %s)"
                group_params = [midpoint]
            # The health row and both count sources share this statement's
            # MVCC snapshot. Never combine preflight metadata with new data.
            cursor.execute(
                f"""
                WITH health AS (
                    SELECT least(cutoff, %s::timestamptz) AS boundary
                    FROM home_count_snapshot WHERE id = 1
                    AND {_HISTORY_CLEAN} AND cutoff >= %s
                ), counts AS (
                    SELECT brand_id, bucket_start, post_count AS n
                    FROM home_brand_time_counts, health
                    WHERE brand_id = ANY(%s::varchar[] COLLATE case_insensitive)
                    AND bucket_start >= %s AND bucket_start < least(boundary, %s)
                    {flag_sql}
                    UNION ALL
                    SELECT b.nickname, p.created_at, 1::bigint
                    FROM health, posts_brands pb
                    JOIN posts p ON p.tweet_id = pb.post_id
                    JOIN brands b ON b.nickname = pb.brand_id
                    LEFT JOIN posts_unsanctioned_flags f ON f.post_id = p.tweet_id
                    LEFT JOIN posts_untracked_brand_promotions u ON u.post_id = p.tweet_id
                    WHERE b.nickname = ANY(%s::varchar[] COLLATE case_insensitive)
                    AND p.created_at >= greatest(%s, boundary) AND p.created_at < %s
                    {raw_flag_sql}
                ), grouped AS (
                    SELECT brand_id, {group_sql} AS bucket, sum(n)::bigint AS count
                    FROM counts GROUP BY brand_id, bucket
                )
                SELECT EXISTS(SELECT 1 FROM health), g.brand_id, g.bucket, g.count
                FROM (VALUES (1)) seed(n) LEFT JOIN grouped g ON TRUE
                """,
                [
                    day,
                    day,
                    brand_ids,
                    start,
                    end,
                    brand_ids,
                    start,
                    end,
                    *group_params,
                ],
            )
            rows = cursor.fetchall()
            if not rows[0][0]:
                return None
            return [
                {"brand_id": brand, "bucket": bucket, "count": count}
                for _, brand, bucket, count in rows
                if brand is not None
            ]
    except DatabaseError as error:
        # Savepoint has exited before the exact-query caller resumes.
        if _sqlstate(error) in _RECOVERABLE:
            return None
        raise


def home_count_cache_token() -> tuple | None:
    """Invalidate in-process caches after publication or a historical correction.

    Current-day changes stay in the existing short cache lifetime; they never
    mark closed-day history dirty. The counter still records them so a write
    spanning midnight cannot escape a concurrent refresh's publication check.
    """
    if connection.vendor != "postgresql":
        return None
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "SELECT published_generation, cutoff, "
                f"{_HISTORY_CLEAN}, "
                "CASE WHEN dirty_since < cutoff THEN source_generation ELSE 0 END "
                "FROM home_count_snapshot WHERE id = 1"
            )
            row = cursor.fetchone()
            return tuple(row) if row else None
    except DatabaseError as error:
        if _sqlstate(error) in _RECOVERABLE:
            return None
        raise
