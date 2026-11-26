"""Rebuildable homepage counts. Source rows remain the correctness fallback."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

from django.db import DatabaseError, connection, transaction
from django.db.backends.utils import CursorWrapper

from core.materializations import (
    HISTORY_CLEAN_SQL,
    MaterializationDefinition,
    is_populated,
    refresh_materialization,
)
from core.materializations import (
    sqlstate as _sqlstate,
)

REFRESH_LOCK = 726_514_093
_RECOVERABLE = {"42P01", "55000", "55P03", "57014"}
_HISTORY_CLEAN = HISTORY_CLEAN_SQL
HOME_COUNTS = MaterializationDefinition(
    dataset_key="home.brand_time_counts.v1",
    relation="home_brand_time_counts",
    source_tables=(
        "brands",
        "posts",
        "posts_brands",
        "posts_unsanctioned_flags",
        "posts_untracked_brand_promotions",
    ),
    lock_id=REFRESH_LOCK,
    cutoff_sql="date_trunc('day', transaction_timestamp(), 'UTC')",
    online_refresh=True,
)


def utc_day(at: datetime) -> datetime:
    return at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _populated(cursor: CursorWrapper) -> bool:
    return is_populated(cursor, HOME_COUNTS)


@contextmanager
def pulse_count_deadline(deadline: float):
    """Limit every statement in an attempt to the remaining Pulse allowance."""
    remaining_ms = int((deadline - monotonic()) * 1000)
    if remaining_ms <= 0:
        raise DatabaseError("Pulse count deadline expired")
    if connection.vendor != "postgresql":
        yield
        return
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('statement_timeout'), setting::bigint "
            "FROM pg_settings WHERE name='statement_timeout'"
        )
        previous, previous_ms = cursor.fetchone()
        def enforce_deadline(execute, sql, params, many, context):
            # PostgreSQL must be allowed to roll back an aborted savepoint
            # before any further SET or SELECT can run on the connection.
            if sql.lstrip().upper().startswith(("SAVEPOINT ", "RELEASE SAVEPOINT ", "ROLLBACK TO SAVEPOINT ")):
                return execute(sql, params, many, context)
            remaining_ms = int((deadline - monotonic()) * 1000)
            if remaining_ms <= 0:
                raise DatabaseError("Pulse count deadline expired")
            limit_ms = min(remaining_ms, previous_ms) if previous_ms else remaining_ms
            execute("SELECT set_config('statement_timeout', %s, true)", [f"{limit_ms}ms"], False, context)
            return execute(sql, params, many, context)

        # On error the surrounding transaction/savepoint restores the setting.
        with connection.execute_wrapper(enforce_deadline):
            yield
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", [previous])


def refresh_home_counts() -> dict[str, str | int]:
    return refresh_materialization(HOME_COUNTS)


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

    Reuse the unchanged prefix and recount the first dirty bucket onward live.
    Return None without a usable publication, distinct from an empty result.
    Comparisons count partial first/midpoint buckets from source, keeping their
    rolling boundaries exact. Daily chart callers validate local midnights.
    """
    if connection.vendor != "postgresql":
        return None
    day = utc_day(end)
    if midpoint is None and start < day and start.timestamp() % 900:
        return None
    first_bucket = datetime.fromtimestamp(start.timestamp() // 900 * 900, UTC)
    saved_start = first_bucket + timedelta(minutes=15) if first_bucket < start else start
    split_start = (
        datetime.fromtimestamp(midpoint.timestamp() // 900 * 900, UTC)
        if midpoint is not None else start
    )
    split_end = (
        split_start + timedelta(minutes=15)
        if midpoint is not None and split_start < midpoint else split_start
    )
    # Writers track the earliest old/new timestamp affected by a count change.
    # Discard its entire quarter hour so saved and live rows cannot overlap.
    # Unknown/global invalidation still falls back to the exact source query.
    health_sql = f"""
        SELECT boundary FROM (
            SELECT least(
                cutoff, %s::timestamptz,
                CASE WHEN source_generation = published_generation THEN cutoff
                ELSE date_bin('15 minutes', dirty_since,
                              TIMESTAMPTZ '2000-01-01 00:00:00+00') END
            ) AS boundary, {_HISTORY_CLEAN} AS clean
            FROM materialization_state
            WHERE dataset_key = %s AND cutoff >= %s
            AND published_generation IS NOT NULL
            AND (source_generation = published_generation OR dirty_since IS NOT NULL)
        ) publication WHERE clean OR boundary > TIMESTAMPTZ '0001-01-01 00:00:00+00'
    """
    health_params = [day, HOME_COUNTS.dataset_key, day]
    try:
        # A catalog/lifecycle preflight avoids taking a read lock on an initially
        # unpopulated view while its first ordinary REFRESH is running.
        with transaction.atomic(), connection.cursor() as cursor:
            if not _populated(cursor):
                return None
            cursor.execute(
                f"WITH health AS ({health_sql}) SELECT boundary FROM health",
                health_params,
            )
            publication = cursor.fetchone()
            if not publication:
                return None
            boundary = publication[0]
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
            # Give PostgreSQL a bounded timestamp scan for each uncovered range.
            # A full rolling-window predicate can drive the join from every post-brand link.
            live_ranges = [(max(start, boundary), end)]
            if saved_start != start:
                live_ranges.append((start, min(saved_start, end)))
            saved_edge_sql = ""
            saved_edge_params = []
            if split_start != split_end:
                saved_edge_sql = "AND NOT (bucket_start >= %s AND bucket_start < %s)"
                saved_edge_params = [split_start, split_end]
                live_ranges.append((max(start, split_start), min(split_end, end)))
            live_range_sql = " OR ".join(
                "(p.created_at >= %s AND p.created_at < %s)" for _ in live_ranges
            )
            live_range_params = [timestamp for interval in live_ranges for timestamp in interval]
            # Keep the time-bounded posts as the driver even for short tails;
            # a brand-first plan can scan all links and probe the large posts table.
            # Recheck the publication boundary in the count statement's MVCC snapshot: an
            # earlier concurrent correction forces the exact-source fallback.
            cursor.execute(
                f"""
                WITH health AS (
                    SELECT boundary FROM ({health_sql}) publication
                    WHERE boundary >= %s
                ), counts AS (
                    SELECT brand_id, bucket_start, post_count AS n
                    FROM home_brand_time_counts, health
                    WHERE brand_id = ANY(%s::varchar[] COLLATE case_insensitive)
                    AND bucket_start >= %s AND bucket_start < %s
                    {saved_edge_sql}
                    {flag_sql}
                    UNION ALL
                    SELECT b.nickname, p.created_at, 1::bigint
                    FROM health, posts p
                    CROSS JOIN LATERAL (
                        SELECT brand_id FROM posts_brands
                        WHERE post_id = p.tweet_id
                        OFFSET 0
                    ) pb
                    JOIN brands b ON b.nickname = pb.brand_id
                    LEFT JOIN posts_unsanctioned_flags f ON f.post_id = p.tweet_id
                    LEFT JOIN posts_untracked_brand_promotions u ON u.post_id = p.tweet_id
                    WHERE b.nickname = ANY(%s::varchar[] COLLATE case_insensitive)
                    AND ({live_range_sql})
                    {raw_flag_sql}
                ), grouped AS (
                    SELECT brand_id, {group_sql} AS bucket, sum(n)::bigint AS count
                    FROM counts GROUP BY brand_id, bucket
                )
                SELECT EXISTS(SELECT 1 FROM health), g.brand_id, g.bucket, g.count
                FROM (VALUES (1)) seed(n) LEFT JOIN grouped g ON TRUE
                """,
                [
                    *health_params,
                    boundary,
                    brand_ids,
                    saved_start,
                    min(boundary, end),
                    *saved_edge_params,
                    brand_ids,
                    *live_range_params,
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
                "FROM materialization_state WHERE dataset_key = %s",
                [HOME_COUNTS.dataset_key],
            )
            row = cursor.fetchone()
            return tuple(row) if row else None
    except DatabaseError as error:
        if _sqlstate(error) in _RECOVERABLE:
            return None
        raise
