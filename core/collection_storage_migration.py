"""Bounded evidence copy for retired collection JSON columns.

The archive contains PostgreSQL's JSONB text representation, not provider wire
bytes. It is retained evidence; operational reads must use typed owners.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import connection, transaction

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
