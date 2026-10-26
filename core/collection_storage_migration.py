"""Bounded evidence copy for retired collection JSON columns.

The archive contains PostgreSQL's JSONB text representation, not provider wire
bytes. It is retained evidence; operational reads must use typed owners.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from core.benchmark_metric_timing import native_date
from core.models import (
    CollectionAttempt,
    CollectionObservation,
    CollectionRun,
    CollectionScopeRareHit,
    CollectionScopeRun,
    RareTypeSearchHit,
)

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


@dataclass(frozen=True)
class RareHitMembershipBatch:
    last_id: int
    scanned: int
    inserted: int


@dataclass(frozen=True)
class RequestUseBatch:
    last_id: int
    scanned: int
    inserted: int


@dataclass(frozen=True)
class InvocationBatch:
    last_id: UUID | None
    scanned: int
    inserted: int


@dataclass(frozen=True)
class MetricRequestBatch:
    last_id: UUID | None
    scanned: int
    updated: int


def project_metric_request_coordinates_batch(
    *, after_id: UUID | None = None, batch_size: int = 200,
    verify_only: bool = False,
) -> MetricRequestBatch:
    """Copy legacy metric date/cursor options into their existing scope fields."""
    from core.benchmark_metric_store import (
        metric_request_coordinates,
        save_metric_request_coordinates,
    )

    if after_id is not None and not isinstance(after_id, UUID):
        raise ValueError("after_id must be a UUID")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        runs = list(
            CollectionRun.objects.select_for_update()
            .select_related("job")
            .exclude(request_params={})
            .filter(pk__gt=after_id or UUID(int=0))
            .order_by("pk")[:batch_size]
        )
        updated = 0
        for run in runs:
            if run.job.purpose != "metric" or run.job.contract_id is None:
                raise ValueError("metric request options lack their contract owner")
            coordinates = metric_request_coordinates(run.request_params)
            scope = run.scopes.filter(
                scope_kind="metric_fetch", scope_key="source",
            ).first()
            if scope is not None and scope.ownership != {
                "contract_id": str(run.job.contract_id)
            }:
                raise ValueError("metric request scope owner differs from its job")
            if scope is not None and all(
                getattr(scope, field) == value for field, value in coordinates.items()
            ):
                continue
            if verify_only:
                raise ValueError("metric request coordinates are not fully projected")
            save_metric_request_coordinates(run, coordinates)
            updated += 1
        return MetricRequestBatch(
            runs[-1].pk if runs else after_id, len(runs), updated,
        )


def project_run_invocations_batch(
    *, after_id: UUID | None = None, batch_size: int = 200,
    verify_only: bool = False,
) -> InvocationBatch:
    """Recover attempts from ordered legacy run receipts.

    The original invocation string remains in the immutable run archive.
    Its existing job-qualified digest is the operational idempotency key;
    historical receipts without a finish clock retain an unknown outcome.
    Direct archived-catalog runs have a different receipt shape and retain
    their known request counts, limits and finish clocks.
    """
    from core.measurement_taxonomy import digest

    if after_id is not None and not isinstance(after_id, UUID):
        raise ValueError("after_id must be a UUID")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        runs = list(
            CollectionRun.objects.select_for_update()
            .select_related("job")
            .exclude(invocations=[])
            .filter(pk__gt=after_id or UUID(int=0))
            .order_by("pk")[:batch_size]
        )
        if not runs:
            return InvocationBatch(after_id, 0, 0)
        existing = {}
        for attempt in CollectionAttempt.objects.select_for_update().filter(
            run_id__in=[run.pk for run in runs]
        ):
            existing[(attempt.run_id, attempt.ordinal)] = attempt
        missing = []
        for run in runs:
            for ordinal, receipt in enumerate(run.invocations, start=1):
                attempt = existing.pop((run.pk, ordinal), None)
                if run.job.operation == "archived_run":
                    values = _archived_invocation_values(receipt)
                    if attempt is not None:
                        if (
                            attempt.started_at is None
                            or abs((attempt.started_at - values["started_at"]).total_seconds()) > 60
                            or attempt.outcome != values["outcome"]
                            or attempt.actual_requests != values["actual_requests"]
                        ):
                            raise ValueError("historical attempt differs from invocation receipt")
                        continue
                    if verify_only:
                        raise ValueError("missing historical attempt")
                    missing.append(CollectionAttempt(
                        run=run,
                        attempt_key=digest(["archived-catalog-invocation-v1", str(run.pk), ordinal]),
                        ordinal=ordinal,
                        imported_at=timezone.now(),
                        **values,
                    ))
                    continue
                if type(receipt) is not dict or set(receipt) != {"invocation_id", "started_at"}:
                    raise ValueError("unsupported historical invocation receipt")
                identity = receipt["invocation_id"]
                if type(identity) is not str or not 0 < len(identity) <= 256:
                    raise ValueError("invalid historical invocation identity")
                started_at = _historical_timestamp(receipt["started_at"])
                attempt_key = digest({"job": str(run.job_id), "invocation": identity})
                if attempt is None:
                    if verify_only:
                        raise ValueError("missing historical attempt")
                    missing.append(CollectionAttempt(
                        run=run, attempt_key=attempt_key, ordinal=ordinal,
                        started_at=started_at, outcome="legacy_unknown",
                        imported_at=timezone.now(),
                    ))
                elif attempt.attempt_key != attempt_key or attempt.started_at != started_at:
                    raise ValueError("historical attempt differs from invocation receipt")
        operation_by_run = {run.pk: run.job.operation for run in runs}
        if any(operation_by_run[run_id] != "archived_run" for run_id, _ in existing):
            raise ValueError("typed attempt has no historical invocation receipt")
        CollectionAttempt.objects.bulk_create(missing, batch_size=500)
        return InvocationBatch(runs[-1].pk, len(runs), len(missing))


def _historical_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("invalid historical invocation clock") from None
    if timezone.is_naive(parsed):
        raise ValueError("invalid historical invocation clock")
    return parsed


def _archived_invocation_values(receipt):
    required = {"started_at", "requests", "max_requests", "max_models", "outcome"}
    allowed = required | {
        "ended_at", "retries", "last_request", "max_seconds",
        "max_response_bytes", "max_total_bytes",
    }
    if type(receipt) is not dict or not required <= set(receipt) or set(receipt) - allowed:
        raise ValueError("unsupported archived invocation receipt")
    requests = receipt["requests"]
    maximum = receipt["max_requests"]
    items = receipt["max_models"]
    seconds = receipt.get("max_seconds")
    total_bytes = receipt.get("max_total_bytes")
    if (
        type(requests) is not int or requests < 0
        or type(maximum) is not int or maximum <= 0
        or (maximum > 2_147_483_647 and maximum != 2**63 - 1)
        or (items is not None and (type(items) is not int or items <= 0))
        or (seconds is not None and (type(seconds) is not int or seconds <= 0))
        or (total_bytes is not None and (type(total_bytes) is not int or total_bytes <= 0))
    ):
        raise ValueError("invalid archived invocation accounting")
    outcome = receipt["outcome"]
    if type(outcome) is not str or outcome not in {
        "complete", "partial", "interrupted", "running", "failed",
    }:
        raise ValueError("invalid archived invocation outcome")
    started_at = _historical_timestamp(receipt["started_at"])
    finished_at = (
        _historical_timestamp(receipt["ended_at"])
        if receipt.get("ended_at") else None
    )
    if finished_at is not None and finished_at < started_at:
        raise ValueError("invalid archived invocation finish clock")
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "outcome": "success" if outcome == "complete" else outcome,
        "actual_requests": requests,
        # The old sys.maxsize sentinel means no cap, not a real reservation.
        # Its exact spelling remains in the run's immutable evidence archive.
        "reserved_requests": None if maximum == 2**63 - 1 else maximum,
        "effective_items": items,
        "effective_seconds": seconds,
        "reserved_bytes": total_bytes,
        "accounting_complete": False,
    }


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


def project_scope_rare_hits_batch(
    *, after_id: int = 0, batch_size: int = 200
) -> RareHitMembershipBatch:
    """Copy exact scope↔rare-hit pairs; one hit may occur in several scopes."""
    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute(
            "SELECT id FROM collection_scope_runs WHERE id>%s "
            "AND EXISTS (SELECT 1 FROM jsonb_array_elements(envelopes) e "
            "WHERE e ? 'rare_hit_ids') "
            "ORDER BY id LIMIT %s FOR UPDATE",
            [after_id, batch_size],
        )
        ids = [row[0] for row in cursor.fetchall()]
        if not ids:
            return RareHitMembershipBatch(after_id, 0, 0)
        scopes = list(
            CollectionScopeRun.objects.filter(pk__in=ids).select_related("run")
        )
        expected = set()
        for scope in scopes:
            if scope.scope_kind != "x_query":
                raise ValueError("rare hit belongs to a non-X scope")
            for envelope in scope.envelopes:
                if "rare_hit_ids" not in envelope:
                    continue
                hits = envelope["rare_hit_ids"]
                if not isinstance(hits, list) or any(type(hit) is not int or hit <= 0 for hit in hits):
                    raise ValueError("invalid historical rare hit IDs")
                expected.update((scope.pk, hit) for hit in hits)
        hit_rows = {
            hit.pk: hit
            for hit in RareTypeSearchHit.objects.filter(
                pk__in={hit_id for _, hit_id in expected}
            ).select_related("run")
        }
        if len(hit_rows) != len({hit_id for _, hit_id in expected}):
            raise ValueError("historical rare hit is missing")
        job_by_scope = {scope.pk: scope.run.job_id for scope in scopes}
        if any(
            not hit_rows[hit_id].run.lane.startswith(f"bf:{job_by_scope[scope_id]}:")
            for scope_id, hit_id in expected
        ):
            raise ValueError("historical rare hit belongs to another job")
        existing = set(
            CollectionScopeRareHit.objects.filter(scope_run_id__in=ids)
            .values_list("scope_run_id", "rare_hit_id")
        )
        if existing - expected:
            raise ValueError("typed rare hit association exceeds saved scope evidence")
        missing = expected - existing
        CollectionScopeRareHit.objects.bulk_create(
            [CollectionScopeRareHit(scope_run_id=scope_id, rare_hit_id=hit_id)
             for scope_id, hit_id in sorted(missing)],
            batch_size=500,
        )
        return RareHitMembershipBatch(ids[-1], len(ids), len(missing))


def scope_rare_hit_mismatch_counts() -> tuple[int, int]:
    """Compare full historical membership pairs in both directions."""
    with connection.cursor() as cursor:
        cursor.execute(
            "WITH expected AS ("
            "SELECT DISTINCT s.id AS scope_run_id, hit.value::bigint AS rare_hit_id "
            "FROM collection_scope_runs s "
            "CROSS JOIN LATERAL jsonb_array_elements(s.envelopes) e "
            "CROSS JOIN LATERAL jsonb_array_elements_text(e->'rare_hit_ids') hit(value) "
            "WHERE e ? 'rare_hit_ids'), "
            "missing AS (SELECT * FROM expected EXCEPT SELECT scope_run_id,rare_hit_id "
            "FROM collection_scope_rare_hits), "
            "extra AS (SELECT scope_run_id,rare_hit_id FROM collection_scope_rare_hits "
            "EXCEPT SELECT * FROM expected) "
            "SELECT (SELECT count(*) FROM missing),(SELECT count(*) FROM extra)"
        )
        return tuple(cursor.fetchone())


def project_scope_request_uses_batch(
    *, after_id: int = 0, batch_size: int = 200
) -> RequestUseBatch:
    """Copy page-use order and clock without pretending a reused reply is new HTTP."""
    from core.collection_state import record_scope_request_uses

    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute(
            "SELECT id FROM collection_scope_runs WHERE id>%s "
            "AND EXISTS (SELECT 1 FROM jsonb_array_elements(envelopes) e "
            "WHERE e ? 'prefetch_request_id') "
            "ORDER BY id LIMIT %s FOR UPDATE",
            [after_id, batch_size],
        )
        ids = [row[0] for row in cursor.fetchall()]
        if not ids:
            return RequestUseBatch(after_id, 0, 0)
        scopes = list(
            CollectionScopeRun.objects.filter(pk__in=ids)
            .select_related("run")
            .order_by("pk")
        )
        inserted = 0
        for scope in scopes:
            if scope.scope_kind != "x_query":
                raise ValueError("prefetch page belongs to a non-X scope")
            inserted += record_scope_request_uses(scope, scope.envelopes)
        return RequestUseBatch(ids[-1], len(ids), inserted)


def scope_request_use_mismatch_counts() -> tuple[int, int]:
    """Compare every old page-use order/time with typed links both ways."""
    with connection.cursor() as cursor:
        cursor.execute(
            "WITH expected AS ("
            "SELECT s.id AS scope_run_id, (e.value->>'prefetch_request_id')::uuid AS request_id, "
            "(e.ordinal - 1)::integer AS ordinal, "
            "(e.value->>'observed_at')::timestamptz AS observed_at "
            "FROM collection_scope_runs s "
            "CROSS JOIN LATERAL jsonb_array_elements(s.envelopes) "
            "WITH ORDINALITY AS e(value,ordinal) "
            "WHERE e.value ? 'prefetch_request_id'), "
            "missing AS (SELECT * FROM expected EXCEPT "
            "SELECT scope_run_id,request_id,ordinal,observed_at FROM collection_scope_request_uses), "
            "extra AS (SELECT scope_run_id,request_id,ordinal,observed_at "
            "FROM collection_scope_request_uses EXCEPT SELECT * FROM expected) "
            "SELECT (SELECT count(*) FROM missing),(SELECT count(*) FROM extra)"
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
