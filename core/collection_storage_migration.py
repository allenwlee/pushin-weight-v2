"""Bounded evidence copy for retired collection JSON columns.

The archive contains PostgreSQL's JSONB text representation, not provider wire
bytes. It is retained evidence; operational reads must use typed owners.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import connection, transaction

from core.benchmark_metric_timing import native_date
from core.models import CollectionObservation, CollectionRun, CollectionScopeRun

LEGACY_FIELDS = {
    "collection_runs": (
        "request_params", "source_metadata", "raw_payload", "invocations", "report",
    ),
    "collection_scope_runs": ("ownership", "cursor_history", "envelopes"),
    "collection_observations": (
        "dimensions", "source_metadata", "listing", "envelopes", "groups",
    ),
}
ENCODING = "legacy-jsonb-text-v1"


@dataclass(frozen=True)
class ArchiveBatch:
    selected: int
    archived: int
    more_unarchived: bool


@dataclass(frozen=True)
class ProvenanceBatch:
    last_id: int
    scanned: int
    updated: int


@dataclass(frozen=True)
class PublicationBatch:
    last_id: UUID | None
    scanned: int
    inserted: int


@dataclass(frozen=True)
class EndpointBatch:
    last_id: UUID | None
    scanned: int
    inserted: int


@dataclass(frozen=True)
class ScopeBoundsBatch:
    last_id: int
    scanned: int
    updated: int


@dataclass(frozen=True)
class XQueryTargetBatch:
    last_id: int
    scanned: int
    updated: int


@dataclass(frozen=True)
class ProductTargetBatch:
    last_id: int
    scanned: int
    updated: int


PROVENANCE_EXPRESSIONS = {
    "archive_snapshot_date": (
        "CASE WHEN t.source_metadata->>'archive_snapshot_date' ~ "
        "'^[0-9]{4}-[0-9]{2}-[0-9]{2}$' "
        "AND pg_input_is_valid(t.source_metadata->>'archive_snapshot_date','date') "
        "THEN (t.source_metadata->>'archive_snapshot_date')::date END"
    ),
    "period_status": "t.source_metadata->>'period_status'",
    "history_reconstructed": (
        "CASE WHEN t.source_metadata ? 'history_basis' THEN "
        "t.source_metadata->>'history_basis' = "
        "'reconstructed_current_relationships' END"
    ),
    "secondary_source": (
        "CASE WHEN t.source_metadata ? 'secondary_source' THEN "
        "t.source_metadata->'secondary_source' = 'true'::jsonb END"
    ),
    "publication_complete": (
        "CASE WHEN t.source_metadata ? 'publication_complete' THEN "
        "t.source_metadata->'publication_complete' = 'true'::jsonb END"
    ),
    "reconstruction_date": (
        "CASE WHEN t.source_metadata->>'reconstruction_date' ~ "
        "'^[0-9]{4}-[0-9]{2}-[0-9]{2}$' "
        "AND pg_input_is_valid(t.source_metadata->>'reconstruction_date','date') "
        "THEN (t.source_metadata->>'reconstruction_date')::date END"
    ),
}

SCOPE_BOUNDS_VALID = (
    "CASE WHEN t.ownership->>'since_epoch' ~ '^[0-9]{1,12}$' "
    "AND t.ownership->>'until_epoch' ~ '^[0-9]{1,12}$' "
    "THEN (t.ownership->>'since_epoch')::bigint "
    "< (t.ownership->>'until_epoch')::bigint ELSE FALSE END"
)
SCOPE_START = "to_timestamp((t.ownership->>'since_epoch')::double precision)"
SCOPE_END = "to_timestamp((t.ownership->>'until_epoch')::double precision)"


def project_scope_bounds_batch(
    *, after_id: int = 0, batch_size: int = 500
) -> ScopeBoundsBatch:
    """Copy X scope request windows, leaving original query wording untouched."""
    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be an integer from 1 to 1000")
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute(
            "SELECT id FROM collection_scope_runs WHERE scope_kind='x_query' "
            "AND id>%s ORDER BY id LIMIT %s FOR UPDATE",
            [after_id, batch_size],
        )
        ids = [row[0] for row in cursor.fetchall()]
        if not ids:
            return ScopeBoundsBatch(after_id, 0, 0)
        cursor.execute(
            f"SELECT count(*) FROM collection_scope_runs t WHERE t.id=ANY(%s) "
            f"AND NOT ({SCOPE_BOUNDS_VALID})",
            [ids],
        )
        if cursor.fetchone()[0]:
            raise ValueError("X scope has invalid historical request bounds")
        cursor.execute(
            f"UPDATE collection_scope_runs t SET "
            f"requested_start_at={SCOPE_START}, requested_end_at={SCOPE_END} "
            f"WHERE t.id=ANY(%s) AND (t.requested_start_at IS DISTINCT FROM {SCOPE_START} "
            f"OR t.requested_end_at IS DISTINCT FROM {SCOPE_END})",
            [ids],
        )
        return ScopeBoundsBatch(ids[-1], len(ids), cursor.rowcount)


def scope_bounds_mismatch_counts() -> tuple[int, int]:
    """Check all X scopes, including rows changed below a copy cursor."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT count(*) FILTER (WHERE NOT ({SCOPE_BOUNDS_VALID})), "
            f"count(*) FILTER (WHERE CASE WHEN {SCOPE_BOUNDS_VALID} THEN "
            f"t.requested_start_at IS DISTINCT FROM {SCOPE_START} OR "
            f"t.requested_end_at IS DISTINCT FROM {SCOPE_END} ELSE FALSE END) "
            "FROM collection_scope_runs t WHERE t.scope_kind='x_query'"
        )
        return tuple(cursor.fetchone())


def project_x_query_targets_batch(
    *, after_id: int = 0, batch_size: int = 200
) -> XQueryTargetBatch:
    """Pin historical X scope query identity without changing sealed job JSON."""
    from core.collection_state import ensure_x_query_target, x_query_instruction

    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        scopes = list(
            CollectionScopeRun.objects.select_for_update()
            .filter(scope_kind="x_query", pk__gt=after_id)
            .select_related("run__job")
            .order_by("pk")[:batch_size]
        )
        if not scopes:
            return XQueryTargetBatch(after_id, 0, 0)
        targets = {}
        changed = []
        for scope in scopes:
            query, call_id, start, end = x_query_instruction(scope.ownership)
            key = (scope.run.job_id, scope.scope_key)
            if key not in targets:
                targets[key] = ensure_x_query_target(
                    scope.run.job, scope.scope_key,
                    query_text=query, call_id=call_id, start_at=start, end_at=end,
                )
            target = targets[key]
            if scope.job_target_id not in (None, target.pk):
                raise ValueError("historical X scope target pin changed")
            if scope.requested_start_at not in (None, start) or scope.requested_end_at not in (None, end):
                raise ValueError("historical X scope request bounds differ")
            if scope.job_target_id is None or scope.requested_start_at is None or scope.requested_end_at is None:
                scope.job_target = target
                scope.requested_start_at = start
                scope.requested_end_at = end
                changed.append(scope)
        if changed:
            CollectionScopeRun.objects.bulk_update(
                changed, ["job_target", "requested_start_at", "requested_end_at"]
            )
        return XQueryTargetBatch(scopes[-1].pk, len(scopes), len(changed))


def x_query_target_mismatch_counts() -> tuple[int, int]:
    """Verify all X scope pins, including rows changed below a copy cursor."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FILTER (WHERE jsonb_typeof(s.ownership) <> 'object' "
            "OR jsonb_typeof(s.ownership->'call_id') <> 'string' "
            "OR jsonb_typeof(s.ownership->'query') <> 'string' "
            "OR coalesce(s.ownership->>'call_id','')='' "
            "OR coalesce(s.ownership->>'query','')='' "
            "OR s.ownership - 'call_id' - 'query' - 'since_epoch' - 'until_epoch' <> '{}'::jsonb "
            f"OR NOT ({SCOPE_BOUNDS_VALID.replace('t.', 's.')})), "
            "count(*) FILTER (WHERE s.job_target_id IS NULL OR jt.job_id <> r.job_id "
            "OR jt.target_key <> s.scope_key OR jt.target_kind <> 'query' "
            "OR jt.resolution_state <> 'resolved' "
            "OR jt.target_role IS DISTINCT FROM s.ownership->>'call_id' "
            "OR q.query_text IS DISTINCT FROM s.ownership->>'query' "
            "OR jt.requested_start_at IS DISTINCT FROM s.requested_start_at "
            "OR jt.requested_end_at IS DISTINCT FROM s.requested_end_at) "
            "FROM collection_scope_runs s JOIN collection_runs r ON r.id=s.run_id "
            "LEFT JOIN collection_job_targets jt ON jt.id=s.job_target_id "
            "LEFT JOIN search_queries q ON q.id=jt.search_query_id "
            "WHERE s.scope_kind='x_query'"
        )
        return tuple(cursor.fetchone())


def project_product_match_targets_batch(
    *, after_id: int = 0, batch_size: int = 200
) -> ProductTargetBatch:
    """Pin historical product scopes to their frozen selected subjects."""
    from core.collection_matching import ensure_product_match_target

    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        scopes = list(
            CollectionScopeRun.objects.select_for_update()
            .filter(scope_kind="product_match", pk__gt=after_id)
            .select_related("run__job")
            .order_by("pk")[:batch_size]
        )
        if not scopes:
            return ProductTargetBatch(after_id, 0, 0)
        changed = []
        for scope in scopes:
            target = ensure_product_match_target(
                scope.run.job, scope.scope_key, scope.ownership
            )
            if scope.job_target_id not in (None, target.pk):
                raise ValueError("historical product scope target pin changed")
            if scope.job_target_id is None:
                scope.job_target = target
                changed.append(scope)
        if changed:
            CollectionScopeRun.objects.bulk_update(changed, ["job_target"])
        return ProductTargetBatch(scopes[-1].pk, len(scopes), len(changed))


def product_match_target_mismatch_counts() -> tuple[int, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FILTER (WHERE jsonb_typeof(s.ownership) <> 'object' "
            "OR jsonb_typeof(s.ownership->'product_key') <> 'string' "
            "OR jsonb_typeof(s.ownership->'input_sha256') <> 'string' "
            "OR s.ownership - 'product_key' - 'input_sha256' <> '{}'::jsonb), "
            "count(*) FILTER (WHERE s.job_target_id IS NULL "
            "OR jt.job_id <> r.job_id OR jt.target_key <> s.scope_key "
            "OR jt.target_kind <> 'match_candidate' "
            "OR jt.resolution_state <> 'resolved' "
            "OR ms.product_key::text IS DISTINCT FROM s.ownership->>'product_key' "
            "OR jt.selection_sha256 IS DISTINCT FROM s.ownership->>'input_sha256') "
            "FROM collection_scope_runs s JOIN collection_runs r ON r.id=s.run_id "
            "LEFT JOIN collection_job_targets jt ON jt.id=s.job_target_id "
            "LEFT JOIN measurement_subjects ms ON ms.id=jt.subject_id "
            "WHERE s.scope_kind='product_match'"
        )
        return tuple(cursor.fetchone())


def project_benchmark_provenance_batch(
    *, after_id: int = 0, batch_size: int = 500
) -> ProvenanceBatch:
    """Copy one observation ID range; rerunning from zero is safe.

    A final full mismatch sweep must catch changed rows below the last ID.
    """
    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be an integer from 1 to 1000")
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute(
            "SELECT id FROM collection_observations WHERE id > %s "
            "ORDER BY id LIMIT %s",
            [after_id, batch_size],
        )
        ids = [row[0] for row in cursor.fetchall()]
        if not ids:
            return ProvenanceBatch(after_id, 0, 0)
        assignments = ", ".join(
            f"{name} = {expression}"
            for name, expression in PROVENANCE_EXPRESSIONS.items()
        )
        changed = " OR ".join(
            f"t.{name} IS DISTINCT FROM {expression}"
            for name, expression in PROVENANCE_EXPRESSIONS.items()
        )
        cursor.execute(
            f"UPDATE collection_observations t SET {assignments} "
            f"WHERE t.id = ANY(%s) AND ({changed})",
            [ids],
        )
        return ProvenanceBatch(ids[-1], len(ids), cursor.rowcount)


def project_run_ingestion_mode() -> int:
    """Copy the small run-level scalar consumed by benchmark provenance."""
    expression = (
        "CASE WHEN source_metadata ? 'ingestion_mode' THEN "
        "source_metadata->>'ingestion_mode' = 'direct' END"
    )
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute(
            "UPDATE collection_runs SET direct_ingestion = " + expression
            + " WHERE direct_ingestion IS DISTINCT FROM " + expression
        )
        return cursor.rowcount


def project_arena_publication_batch(
    *, after_id: UUID | None = None, batch_size: int = 10,
    verify_only: bool = False,
) -> PublicationBatch:
    """Preserve run-wide publication dates as typed aggregate observations."""
    if after_id is not None and not isinstance(after_id, UUID):
        raise ValueError("after_id must be a UUID or None")
    if type(batch_size) is not int or not 1 <= batch_size <= 50:
        raise ValueError("batch_size must be an integer from 1 to 50")
    from core.benchmark_metric_store import record_arena_publications

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        runs = CollectionRun.objects.filter(
            job__source_id="arena",
            job__purpose="metric",
            status__in=["success", "partial"],
            source_metadata__has_key="publication_dates",
        )
        if after_id is not None:
            runs = runs.filter(pk__gt=after_id)
        if not verify_only:
            runs = runs.select_for_update(of=("self",))
        selected = list(runs.order_by("pk")[:batch_size])
        inserted = 0
        for run in selected:
            native = run.source_metadata["publication_dates"]
            if not isinstance(native, list) or not 0 < len(native) <= 366:
                raise ValueError("invalid Arena publication-date evidence")
            dates = sorted({native_date(day).isoformat() for day in native})
            payload = run.raw_payload
            if not isinstance(payload, dict) or payload.get("coverage") not in {
                "publication_window", "latest_publication_only"
            }:
                raise ValueError("Arena publication coverage evidence is missing")
            if not isinstance(payload.get("rows"), list) or any(
                not isinstance(row, dict) for row in payload["rows"]
            ):
                raise ValueError("Arena publication rows are invalid")
            if any(
                row.get("leaderboard_publish_date") not in dates
                for row in payload["rows"]
            ):
                raise ValueError("Arena publication date excludes a source row")
            markers = list(CollectionObservation.objects.filter(
                run=run, observation_kind="publication_marker"
            ))
            expected_dates = {native_date(day) for day in dates}
            saved_dates = {marker.published_date for marker in markers}
            if saved_dates - expected_dates:
                raise ValueError("Arena publication markers conflict with source evidence")
            if verify_only:
                if saved_dates != expected_dates or len(markers) != len(dates):
                    raise ValueError("Arena publication markers are incomplete")
                for marker in markers:
                    if (
                        marker.source_identifier != "arena:publication"
                        or marker.source_subject_kind != "aggregate"
                        or marker.observed_at != run.observed_at
                        or marker.publication_precision != "date"
                        or marker.publication_complete is not True
                    ):
                        raise ValueError("Arena publication marker disagrees with source")
            else:
                inserted += record_arena_publications(run, dates)
        return PublicationBatch(
            selected[-1].pk if selected else after_id,
            len(selected), inserted,
        )


def project_opencode_endpoint_batch(
    *, after_id: UUID | None = None, batch_size: int = 10,
    verify_only: bool = False,
) -> EndpointBatch:
    """Copy successful endpoint checks and their exact historical row links."""
    if after_id is not None and not isinstance(after_id, UUID):
        raise ValueError("after_id must be a UUID or None")
    if type(batch_size) is not int or not 1 <= batch_size <= 50:
        raise ValueError("batch_size must be an integer from 1 to 50")
    from core.benchmark_opencode import record_endpoint_checks

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        runs = CollectionRun.objects.filter(
            job__source_id="opencode",
            job__purpose="metric",
            status__in=["success", "partial"],
            source_metadata__has_key="endpoint_checks",
        ).select_related("job__contract")
        if after_id is not None:
            runs = runs.filter(pk__gt=after_id)
        if not verify_only:
            runs = runs.select_for_update(of=("self",))
        selected = list(runs.order_by("pk")[:batch_size])
        inserted = 0
        for run in selected:
            checks = run.source_metadata["endpoint_checks"]
            if not isinstance(checks, list) or len(checks) > 100:
                raise ValueError("invalid OpenCode endpoint check evidence")
            inserted += record_endpoint_checks(
                run, checks, run.job.contract, verify_only=verify_only
            )
        return EndpointBatch(
            selected[-1].pk if selected else after_id,
            len(selected), inserted,
        )


def provenance_mismatch_counts() -> tuple[int, int]:
    """Full comparison also catches edits below a previous ID checkpoint."""
    changed = " OR ".join(
        f"t.{name} IS DISTINCT FROM {expression}"
        for name, expression in PROVENANCE_EXPRESSIONS.items()
    )
    run_expression = (
        "CASE WHEN source_metadata ? 'ingestion_mode' THEN "
        "source_metadata->>'ingestion_mode' = 'direct' END"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM collection_runs WHERE direct_ingestion "
            "IS DISTINCT FROM " + run_expression
        )
        runs = cursor.fetchone()[0]
        cursor.execute(
            f"SELECT count(*) FROM collection_observations t WHERE {changed}"
        )
        return runs, cursor.fetchone()[0]


def _document_expression(fields: tuple[str, ...]) -> str:
    # Only the fixed, reviewed table/field manifest above reaches this builder.
    arguments = ", ".join(f"'{field}', t.{field}" for field in fields)
    return f"convert_to(jsonb_build_object({arguments})::text, 'UTF8')"


def archive_legacy_batch(
    table: str, *, batch_size: int = 100, repair_stale: bool = False
) -> ArchiveBatch:
    """Copy one locked batch; a retry can safely continue from NULL pointers.

    Concurrent writers are allowed during this additive phase. A final frozen
    delta comparison must recheck content hashes before any column retirement.
    """
    if table not in LEGACY_FIELDS:
        raise ValueError("unsupported collection owner")
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be an integer from 1 to 1000")
    body = _document_expression(LEGACY_FIELDS[table])
    if repair_stale:
        source = (
            f"{table} t LEFT JOIN collection_evidence_archives a "
            "ON a.id = t.legacy_archive_id"
        )
        needed = f"a.id IS NULL OR a.encoding <> '{ENCODING}' OR a.body <> {body}"
    else:
        source = f"{table} t"
        needed = "t.legacy_archive_id IS NULL"
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute(
            f"SELECT t.id FROM {source} WHERE {needed} "
            "ORDER BY t.id LIMIT %s FOR UPDATE OF t SKIP LOCKED",
            [batch_size],
        )
        ids = [row[0] for row in cursor.fetchall()]
        if not ids:
            cursor.execute(
                f"SELECT EXISTS(SELECT 1 FROM {source} WHERE {needed})"
            )
            return ArchiveBatch(0, 0, cursor.fetchone()[0])
        cursor.execute(
            f"""
            WITH documents AS (
                SELECT {body} AS body FROM {table} t WHERE t.id = ANY(%s)
            )
            INSERT INTO collection_evidence_archives
                (id, content_sha256, encoding, media_type, byte_count,
                 body, capture_kind, created_at)
            SELECT gen_random_uuid(), encode(sha256(body), 'hex'), %s,
                   'application/json', octet_length(body), body,
                   'legacy_snapshot', CURRENT_TIMESTAMP
            FROM (SELECT DISTINCT body FROM documents) unique_documents
            ON CONFLICT (content_sha256, encoding) DO NOTHING
            """,
            [ids, ENCODING],
        )
        cursor.execute(
            f"""
            WITH documents AS (
                SELECT t.id, {body} AS body FROM {table} t
                WHERE t.id = ANY(%s)
            )
            UPDATE {table} t SET legacy_archive_id = a.id
            FROM documents d JOIN collection_evidence_archives a
              ON a.content_sha256 = encode(sha256(d.body), 'hex')
             AND a.encoding = %s AND a.body = d.body
            WHERE t.id = d.id AND t.legacy_archive_id IS DISTINCT FROM a.id
            """,
            [ids, ENCODING],
        )
        archived = cursor.rowcount
        if archived != len(ids):
            raise ValueError("collection archive hash/body mismatch")
        cursor.execute(
            f"SELECT EXISTS(SELECT 1 FROM {source} WHERE {needed})"
        )
        return ArchiveBatch(len(ids), archived, cursor.fetchone()[0])


def stale_legacy_archive_count(table: str) -> int:
    """Compare all copied documents with current JSON before final cutover."""
    if table not in LEGACY_FIELDS:
        raise ValueError("unsupported collection owner")
    body = _document_expression(LEGACY_FIELDS[table])
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT count(*) FROM {table} t
            LEFT JOIN collection_evidence_archives a ON a.id=t.legacy_archive_id
            WHERE a.id IS NULL OR a.encoding <> %s OR a.body <> {body}
            """,
            [ENCODING],
        )
        return cursor.fetchone()[0]
