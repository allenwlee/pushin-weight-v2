"""Bounded evidence copy for retired collection JSON columns.

The archive contains PostgreSQL's JSONB text representation, not provider wire
bytes. It is retained evidence; operational reads must use typed owners.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import connection, transaction
from django.db.models import Q
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
class DatasetBatch:
    last_id: UUID | int | None
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
    updated: int


@dataclass(frozen=True)
class MetricRequestBatch:
    last_id: UUID | None
    scanned: int
    updated: int


@dataclass(frozen=True)
class PayloadArchiveBatch:
    last_id: UUID | None
    scanned: int
    archived: int


@dataclass(frozen=True)
class ContinuationBatch:
    last_id: UUID | None
    scanned: int
    updated: int


def project_run_continuations_batch(
    *, after_id: UUID | None = None, batch_size: int = 200,
    verify_only: bool = False,
) -> ContinuationBatch:
    """Copy historical predecessor links without changing the old report."""
    if after_id is not None and not isinstance(after_id, UUID):
        raise ValueError("after_id must be a UUID or None")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        runs = CollectionRun.objects.filter(report__has_key="continued_from")
        if after_id is not None:
            runs = runs.filter(pk__gt=after_id)
        if not verify_only:
            runs = runs.select_for_update(of=("self",))
        selected = list(runs.order_by("pk")[:batch_size])
        updated = 0
        for run in selected:
            try:
                previous_id = UUID(run.report["continued_from"])
            except (TypeError, ValueError, AttributeError):
                raise ValueError("invalid historical predecessor ID") from None
            previous = CollectionRun.objects.filter(pk=previous_id).first()
            if previous is None or previous.pk == run.pk or previous.job_id != run.job_id:
                raise ValueError("historical predecessor has a different run owner")
            seen = {run.pk}
            ancestor = previous
            while ancestor is not None:
                if ancestor.pk in seen:
                    raise ValueError("historical predecessor forms a cycle")
                seen.add(ancestor.pk)
                ancestor = ancestor.continuation_of
            if run.continuation_of_id == previous_id:
                continue
            if run.continuation_of_id is not None:
                raise ValueError("typed predecessor differs from historical report")
            if verify_only:
                raise ValueError("historical predecessor is not projected")
            run.continuation_of_id = previous_id
            run.save(update_fields=["continuation_of"])
            updated += 1
        return ContinuationBatch(
            selected[-1].pk if selected else after_id, len(selected), updated,
        )


def archive_metric_payload_batch(
    *, after_id: UUID | None = None, batch_size: int = 50,
    verify_only: bool = False,
) -> PayloadArchiveBatch:
    """Preserve old parsed metric payloads before retiring the run JSON column."""
    from core.collection_capture import archive_legacy, read_document
    from core.measurement_taxonomy import digest

    if after_id is not None and not isinstance(after_id, UUID):
        raise ValueError("after_id must be a UUID or None")
    if type(batch_size) is not int or not 1 <= batch_size <= 50:
        raise ValueError("batch_size must be an integer from 1 to 50")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        runs = CollectionRun.objects.filter(raw_payload__isnull=False)
        if after_id is not None:
            runs = runs.filter(pk__gt=after_id)
        if not verify_only:
            runs = runs.select_for_update(of=("self",))
        selected = list(runs.order_by("pk")[:batch_size])
        archived = 0
        for run in selected:
            if run.payload_sha256 is not None and digest(run.raw_payload) != run.payload_sha256:
                raise ValueError("metric payload digest differs from saved run hash")
            if run.payload_archive_id is not None:
                if read_document(run.payload_archive) != run.raw_payload:
                    raise ValueError("metric payload archive differs from legacy payload")
            elif verify_only:
                raise ValueError("metric payload archive is missing")
            else:
                run.payload_archive = archive_legacy(run.raw_payload)
                run.save(update_fields=["payload_archive"])
                archived += 1
        return PayloadArchiveBatch(
            selected[-1].pk if selected else after_id, len(selected), archived,
        )


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

    Preserve the original invocation string alongside its existing
    job-qualified digest, which remains the operational idempotency key;
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
            .only("id", "job__operation", "invocations")
            .exclude(invocations=[])
            .filter(pk__gt=after_id or UUID(int=0))
            .order_by("pk")[:batch_size]
        )
        if not runs:
            return InvocationBatch(after_id, 0, 0, 0)
        existing = {}
        for attempt in CollectionAttempt.objects.select_for_update().filter(
            run_id__in=[run.pk for run in runs]
        ):
            existing[(attempt.run_id, attempt.ordinal)] = attempt
        missing = []
        updated = 0
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
                        changed = []
                        for field in (
                            "reserved_requests", "reserved_bytes",
                            "response_byte_limit", "effective_seconds",
                            "effective_items", "retry_count",
                        ):
                            saved, expected = getattr(attempt, field), values[field]
                            if saved == expected:
                                continue
                            if not (
                                saved is None
                                or field == "retry_count" and saved == 0
                            ):
                                raise ValueError("historical attempt limit differs from invocation receipt")
                            if verify_only:
                                raise ValueError("historical attempt limit is not projected")
                            setattr(attempt, field, expected)
                            changed.append(field)
                        # An existing attempt can have its own actual finish
                        # clock; the archived receipt retains the older one.
                        if attempt.finished_at is None and values["finished_at"]:
                            if verify_only:
                                raise ValueError("historical attempt finish is not projected")
                            attempt.finished_at = values["finished_at"]
                            changed.append("finished_at")
                        if changed:
                            attempt.save(update_fields=changed)
                            updated += 1
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
                        source_invocation_id=identity,
                        started_at=started_at, outcome="legacy_unknown",
                        imported_at=timezone.now(),
                    ))
                elif attempt.attempt_key != attempt_key or attempt.started_at != started_at:
                    raise ValueError("historical attempt differs from invocation receipt")
                elif attempt.source_invocation_id != identity:
                    if attempt.source_invocation_id is not None:
                        raise ValueError("historical invocation identity differs from receipt")
                    if verify_only:
                        raise ValueError("historical invocation identity is not projected")
                    attempt.source_invocation_id = identity
                    attempt.save(update_fields=["source_invocation_id"])
                    updated += 1
        operation_by_run = {run.pk: run.job.operation for run in runs}
        if any(operation_by_run[run_id] != "archived_run" for run_id, _ in existing):
            raise ValueError("typed attempt has no historical invocation receipt")
        CollectionAttempt.objects.bulk_create(missing, batch_size=500)
        return InvocationBatch(runs[-1].pk, len(runs), len(missing), updated)


def _historical_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("invalid historical invocation clock") from None
    if timezone.is_naive(parsed):
        raise ValueError("invalid historical invocation clock")
    return parsed


def project_resource_snapshots_batch(
    *, after_id: int = 0, batch_size: int = 100, verify_only: bool = False,
) -> ProvenanceBatch:
    """Retain catalog facts and repair missing fields without overwriting known ones."""
    from core.collection_resources import resource_snapshot_values
    from core.models import CollectionResourceSnapshot

    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 200:
        raise ValueError("batch_size must be an integer from 1 to 200")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        query = CollectionObservation.objects.filter(
            pk__gt=after_id, post__isnull=True, run__job__purpose="catalog",
            run__job__source_id__in=["hf", "github"],
        ).exclude(listing={})
        owners = dict(query.order_by("pk").values_list("pk", "run_id")[:batch_size])
        if not verify_only:
            list(CollectionRun.objects.select_for_update().filter(
                pk__in=set(owners.values()),
            ).order_by("pk").values_list("pk", flat=True))
        query = query.filter(pk__in=owners).select_related(
            "run__job__owner_account", "mapping__publisher_account", "resource_snapshot",
        ).only(
            "pk", "run_id", "post_id", "observation_kind", "source_subject_kind",
            "source_identifier", "listing", "dimensions", "source_metadata", "resource_snapshot",
            "run__job_id", "run__job__source_id", "run__job__owner_account__data_source_id",
            "mapping__publisher_account__data_source_id",
        )
        if not verify_only:
            query = query.select_for_update(of=("self",))
        observations = list(query.order_by("pk"))
        changed = 0
        for observation in observations:
            if observation.run_id != owners[observation.pk]:
                raise ValueError("resource owner moved while locking")
            expected = resource_snapshot_values(observation)
            if expected is None:
                continue
            snapshot = getattr(observation, "resource_snapshot", None)
            if snapshot is None:
                if verify_only:
                    raise ValueError("resource snapshot is not projected")
                CollectionResourceSnapshot.objects.create(observation=observation, **expected)
                changed += 1
                continue
            differences = {}
            for field, value in expected.items():
                current = getattr(snapshot, field)
                if current == value:
                    continue
                if current is not None:
                    raise ValueError("typed resource fact conflicts: " + field)
                if verify_only:
                    raise ValueError("resource fact is not projected: " + field)
                differences[field] = value
            if differences:
                for field, value in differences.items():
                    setattr(snapshot, field, value)
                snapshot.save(update_fields=list(differences))
                changed += 1
        return ProvenanceBatch(
            observations[-1].pk if observations else after_id, len(observations), changed,
        )


def project_publication_coordinates_batch(
    *, after_id: int = 0, batch_size: int = 200, verify_only: bool = False,
) -> ProvenanceBatch:
    """Fill exact publication coordinates; refuse to replace already known facts."""
    from core.collection_resources import publication_coordinate_values

    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        query = CollectionObservation.objects.filter(pk__gt=after_id).filter(
            Q(dimensions__has_any_keys=["date", "period", "revision", "config", "category"])
            | Q(source_metadata__has_any_keys=["revision", "immutable_revision", "numeric_snapshot_identity", "snapshot_identity"])
        )
        owners = dict(query.order_by("pk").values_list("pk", "run_id")[:batch_size])
        if not verify_only:
            list(CollectionRun.objects.select_for_update().filter(
                pk__in=set(owners.values()),
            ).order_by("pk").values_list("pk", flat=True))
        query = query.filter(pk__in=owners).select_related("run__job").only(
            "pk", "run_id", "run__job_id", "run__job__source_id",
            "source_identifier", "source_metadata", "dimensions",
            "provider_revision", "config_key", "category_key", "source_record_date",
        )
        if not verify_only:
            query = query.select_for_update(of=("self",))
        observations = list(query.order_by("pk"))
        changed, fields = [], set()
        for observation in observations:
            if observation.run_id != owners[observation.pk]:
                raise ValueError("publication coordinate owner moved while locking")
            expected = publication_coordinate_values(observation)
            differences = {}
            for field, value in expected.items():
                current = getattr(observation, field)
                if current == value:
                    continue
                if current is not None:
                    raise ValueError("typed publication coordinate conflicts: " + field)
                if verify_only:
                    raise ValueError("publication coordinate is not projected: " + field)
                differences[field] = value
            if differences:
                for field, value in differences.items():
                    setattr(observation, field, value)
                fields.update(differences)
                changed.append(observation)
        if changed:
            CollectionObservation.objects.bulk_update(changed, sorted(fields), batch_size=500)
        return ProvenanceBatch(
            observations[-1].pk if observations else after_id, len(observations), len(changed),
        )


def project_scope_cursors_batch(
    *, after_id: int = 0, batch_size: int = 200, verify_only: bool = False,
) -> ProvenanceBatch:
    """Copy exact ordered checkpoints; they do not imply physical requests."""
    from core.collection_cursors import validate_cursor_history
    from core.models import CollectionScopeCursorReceipt

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
            .only("id", "cursor_history")
            .exclude(cursor_history=[]).filter(pk__gt=after_id)
            .order_by("pk")[:batch_size]
        )
        by_scope = {}
        for row in CollectionScopeCursorReceipt.objects.filter(
            scope_run_id__in=[scope.pk for scope in scopes]
        ).order_by("scope_run_id", "position"):
            by_scope.setdefault(row.scope_run_id, []).append((row.position, row.cursor))
        missing = []
        updated = 0
        for scope in scopes:
            validate_cursor_history(scope.cursor_history)
            expected = list(enumerate(scope.cursor_history, start=1))
            actual = by_scope.get(scope.pk, [])
            if actual != expected[:len(actual)]:
                raise ValueError("typed cursor history differs from legacy checkpoint")
            if actual == expected:
                continue
            if verify_only:
                raise ValueError("scope cursor history is not projected")
            updated += 1
            missing.extend(
                CollectionScopeCursorReceipt(scope_run=scope, position=position, cursor=value)
                for position, value in expected[len(actual):]
            )
        CollectionScopeCursorReceipt.objects.bulk_create(missing, batch_size=500)
        return ProvenanceBatch(scopes[-1].pk if scopes else after_id, len(scopes), updated)


def project_source_datasets_batch(
    owner_kind: str, *, after_id=None, batch_size: int = 200, verify_only: bool = False,
) -> DatasetBatch:
    """Preserve each declared dataset at its run, scope or observation owner."""
    from core.collection_capture import read_document
    from core.collection_datasets import dataset_code
    from core.models import SourceDataset

    owners = {
        "run": (CollectionRun, "source_metadata", "job"),
        "scope": (CollectionScopeRun, "ownership", "run__job"),
        "observation": (CollectionObservation, "source_metadata", "run__job"),
    }
    if owner_kind not in owners:
        raise ValueError("unsupported dataset owner")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    if after_id is not None and not (
        isinstance(after_id, UUID) if owner_kind == "run"
        else type(after_id) is int and after_id >= 0
    ):
        raise ValueError("invalid dataset owner cursor")
    model, metadata_field, job_path = owners[owner_kind]
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        query = model.objects.select_related(job_path)
        fields = ["pk", "source_dataset", metadata_field, job_path + "__source_id"]
        query = query.filter(pk__gt=after_id or (UUID(int=0) if owner_kind == "run" else 0))
        if owner_kind != "run":
            query = query.filter(
                Q(**{metadata_field + "__has_key": "dataset_id"})
                | Q(**{metadata_field + "__publication_provenance__has_key": "dataset_id"})
            )
        else:
            query = query.select_related("source_metadata_archive")
            fields += ["source_metadata_archive__body", "source_metadata_archive__content_sha256"]
        query = query.only(*fields)
        if owner_kind != "run":
            # Match live writers' run-before-scope/observation lock order.
            parents = dict(query.order_by("pk").values_list("pk", "run_id")[:batch_size])
            list(CollectionRun.objects.select_for_update().filter(
                pk__in=set(parents.values()),
            ).order_by("pk").values_list("pk", flat=True))
            query = query.filter(pk__in=parents)
        rows = list(query.select_for_update(of=("self",)).order_by("pk")[:batch_size])
        datasets, changed = {}, []
        for owner in rows:
            if owner_kind != "run" and owner.run_id != parents[owner.pk]:
                raise ValueError("dataset owner moved while acquiring its run lock")
            metadata = getattr(owner, metadata_field)
            code = dataset_code(metadata)
            if owner_kind == "run" and owner.source_metadata_archive_id:
                archived_code = dataset_code(read_document(owner.source_metadata_archive))
                if code is not None and archived_code is not None and code != archived_code:
                    raise ValueError("run dataset differs from its retained source metadata")
                code = code or archived_code
            if code is None:
                continue
            source_id = owner.job.source_id if owner_kind == "run" else owner.run.job.source_id
            key = (source_id, code)
            if key not in datasets:
                dataset = SourceDataset.objects.filter(source_id=source_id, code=code).first()
                if dataset is None:
                    if verify_only:
                        raise ValueError("source dataset identity is not projected")
                    dataset, _ = SourceDataset.objects.get_or_create(source_id=source_id, code=code)
                datasets[key] = dataset
            dataset = datasets[key]
            if owner.source_dataset_id == dataset.pk:
                continue
            if owner.source_dataset_id is not None:
                raise ValueError("typed dataset differs from legacy owner")
            if verify_only:
                raise ValueError("source dataset owner is not projected")
            owner.source_dataset = dataset
            changed.append(owner)
        model.objects.bulk_update(changed, ["source_dataset"], batch_size=500)
        return DatasetBatch(rows[-1].pk if rows else after_id, len(rows), len(changed))


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
    response_byte_limit = receipt.get("max_response_bytes")
    retry_count = receipt.get("retries", 0)
    if (
        type(requests) is not int or requests < 0
        or type(maximum) is not int or maximum <= 0
        or (maximum > 2_147_483_647 and maximum != 2**63 - 1)
        or (items is not None and (type(items) is not int or items <= 0))
        or (seconds is not None and (type(seconds) is not int or seconds <= 0))
        or (total_bytes is not None and (type(total_bytes) is not int or total_bytes <= 0))
        or (response_byte_limit is not None and (type(response_byte_limit) is not int or response_byte_limit <= 0))
        or type(retry_count) is not int or retry_count < 0 or retry_count > requests
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
        "response_byte_limit": response_byte_limit,
        "retry_count": retry_count,
        "accounting_complete": False,
    }


PROVENANCE_EXPRESSIONS = {
    "projection_kind": "t.source_metadata->>'projection_kind'",
    "row_semantic_digest": (
        "CASE WHEN t.source_metadata->>'row_semantic_hash' ~ '^[0-9a-f]{64}$' "
        "THEN decode(t.source_metadata->>'row_semantic_hash', 'hex') END"
    ),
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
# During cutover, writers can supply only typed facts. Missing legacy keys are
# not deletion instructions; present keys (including explicit unknowns) still
# participate in both the historical copy and its final mismatch check.
PROVENANCE_SOURCE_KEYS = {
    "row_semantic_digest": "row_semantic_hash",
    "history_reconstructed": "history_basis",
}
PROVENANCE_EXPRESSIONS = {
    name: (
        f"CASE WHEN t.source_metadata ? '{PROVENANCE_SOURCE_KEYS.get(name, name)}' "
        f"THEN ({expression}) ELSE t.{name} END"
    )
    for name, expression in PROVENANCE_EXPRESSIONS.items()
}
INVALID_ROW_SEMANTIC_HASH = (
    "t.source_metadata ? 'row_semantic_hash' AND NOT "
    "COALESCE(t.source_metadata->>'row_semantic_hash' ~ '^[0-9a-f]{64}$', FALSE)"
)

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


def project_publication_scope_references_batch(
    *, after_id: int = 0, batch_size: int = 100, verify_only: bool = False
) -> ProvenanceBatch:
    """Retain the exact publication and contract behind each selected cohort."""
    from core.measurement_taxonomy import digest
    from core.models import MetricCollectionContract

    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        query = CollectionScopeRun.objects.filter(
            scope_kind="publication_selection", pk__gt=after_id,
        ).only("id", "scope_key", "ownership", "resource_observation", "projection_contract")
        if not verify_only:
            query = query.select_for_update()
        scopes = list(query.order_by("pk")[:batch_size])
        if not scopes:
            return ProvenanceBatch(after_id, 0, 0)
        for scope in scopes:
            owner = scope.ownership
            if (
                not isinstance(owner, dict)
                or set(owner) != {"contract_hash", "publication_observation_id"}
                or type(owner["publication_observation_id"]) is not int
                or not isinstance(owner["contract_hash"], str)
            ):
                raise ValueError("invalid historical publication selection identity")
        contracts = MetricCollectionContract.objects.only("id", "contract_hash").in_bulk(
            {s.ownership["contract_hash"] for s in scopes}, field_name="contract_hash",
        )
        publication_ids = set(CollectionObservation.objects.filter(
            pk__in=[s.ownership["publication_observation_id"] for s in scopes],
        ).values_list("pk", flat=True))
        changed = []
        for scope in scopes:
            contract_hash = scope.ownership["contract_hash"]
            publication_id = scope.ownership["publication_observation_id"]
            contract = contracts.get(contract_hash)
            if (
                contract is None or publication_id not in publication_ids
                or scope.scope_key != digest([publication_id, contract_hash])
            ):
                raise ValueError("historical publication selection reference differs")
            if (
                scope.resource_observation_id not in (None, publication_id)
                or scope.projection_contract_id not in (None, contract.pk)
            ):
                raise ValueError("historical publication selection pin changed")
            if scope.resource_observation_id is None or scope.projection_contract_id is None:
                if verify_only:
                    raise ValueError("historical publication selection has missing typed references")
                scope.resource_observation_id = publication_id
                scope.projection_contract_id = contract.pk
                changed.append(scope)
        if changed:
            CollectionScopeRun.objects.bulk_update(
                changed, ["resource_observation", "projection_contract"],
            )
        return ProvenanceBatch(scopes[-1].pk, len(scopes), len(changed))


def project_publication_runtime_bounds_batch(
    *, after_id: int = 0, batch_size: int = 100, verify_only: bool = False
) -> ScopeBoundsBatch:
    """Preserve a rolling invocation's frozen window, never today's window."""
    from core.benchmark_metric_timing import aware_instant
    from core.models import CollectionJob

    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        query = CollectionScopeRun.objects.filter(
            scope_kind="publication_runtime", pk__gt=after_id,
        ).only(
            "id", "run_id", "scope_key", "ownership", "envelopes",
            "requested_start_at", "requested_end_at",
        )
        if not verify_only:
            query = query.select_for_update()
        scopes = list(query.order_by("pk")[:batch_size])
        if not scopes:
            return ScopeBoundsBatch(after_id, 0, 0)
        run_jobs = dict(CollectionRun.objects.filter(
            pk__in={scope.run_id for scope in scopes},
        ).values_list("pk", "job_id"))
        jobs = CollectionJob.objects.in_bulk(set(run_jobs.values()))
        changed = []
        for scope in scopes:
            job = jobs[run_jobs[scope.run_id]]
            instruction = job.scope
            if (
                job.source_id not in {"arena", "openrouter"}
                or job.operation != "model_history"
                or scope.scope_key != "window"
                or instruction.get("publication_window_policy") != "rolling-completed-days-v1"
                or not instruction.get("cohort_hash")
                or scope.ownership != {
                    "policy": instruction["publication_window_policy"],
                    "cohort_hash": instruction["cohort_hash"],
                }
                or not isinstance(scope.envelopes, list)
                or len(scope.envelopes) != 1
            ):
                raise ValueError("invalid historical publication runtime identity")
            saved = scope.envelopes[0]
            if (
                not isinstance(saved, dict)
                or set(saved) != {"cutoff", "publication_start_at", "acquisition_generation"}
                or saved["acquisition_generation"] != str(scope.run_id)
            ):
                raise ValueError("invalid historical publication runtime window")
            start = aware_instant(saved["publication_start_at"])
            end = aware_instant(saved["cutoff"])
            if start >= end:
                raise ValueError("invalid historical publication runtime bounds")
            if scope.requested_start_at not in (None, start) or scope.requested_end_at not in (None, end):
                raise ValueError("publication runtime has conflicting typed bounds")
            if scope.requested_start_at is None or scope.requested_end_at is None:
                if verify_only:
                    raise ValueError("publication runtime has missing typed bounds")
                scope.requested_start_at, scope.requested_end_at = start, end
                changed.append(scope)
        if changed:
            CollectionScopeRun.objects.bulk_update(
                changed, ["requested_start_at", "requested_end_at"],
            )
        return ScopeBoundsBatch(scopes[-1].pk, len(scopes), len(changed))


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
        cursor.execute(
            f"SELECT count(*) FROM collection_observations t WHERE t.id=ANY(%s) "
            f"AND ({INVALID_ROW_SEMANTIC_HASH})",
            [ids],
        )
        if cursor.fetchone()[0]:
            raise ValueError("invalid historical row semantic SHA-256")
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


def project_metric_time_provenance_batch(
    *, after_id: int = 0, batch_size: int = 250, verify_only: bool = False,
) -> ProvenanceBatch:
    """Fill missing value-owned time explanations without changing measurements.

    A later immutable correction takes precedence over the original JSON basis.
    Missing legacy evidence never clears a typed value. Conflicting typed facts
    or a correction whose after-image no longer matches must be resolved first.
    """
    from core.collection_corrections import TIME_BASIS_FIELDS, TIME_STATE_FIELDS
    from core.collection_resources import metric_time_provenance
    from core.models import CollectionCorrection, MetricValue

    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        ids = list(
            MetricValue.objects.filter(pk__gt=after_id).order_by("pk")
            .values_list("pk", flat=True)[:batch_size]
        )
        if not ids:
            return ProvenanceBatch(after_id, 0, 0)
        # Match the live correction writer's owner-before-value lock order.
        owners = CollectionObservation.objects.filter(
            pk__in=MetricValue.objects.filter(pk__in=ids).values("observation_id")
        ).only("pk", "source_metadata").order_by("pk")
        if not verify_only:
            owners = owners.select_for_update(of=("self",))
        observations = {row.pk: row for row in owners}
        values = MetricValue.objects.filter(pk__in=ids).select_related("source_metric").order_by("pk")
        if not verify_only:
            values = values.select_for_update(of=("self",))
        values = list(values)
        history = CollectionCorrection.objects.filter(
            metric_value_id__in=ids, correction_kind="timing",
        )
        predecessors = history.exclude(predecessor_id=None).values("predecessor_id")
        heads = {}
        for row in history.exclude(pk__in=predecessors):
            if row.metric_value_id in heads:
                raise ValueError("ambiguous timing correction history")
            heads[row.metric_value_id] = row
        changed = []
        for value in values:
            head = heads.get(value.pk)
            if head is not None:
                for field in TIME_STATE_FIELDS:
                    current = value.source_timezone_reference_id if field == "source_timezone" else getattr(value, field)
                    recorded = getattr(head, "after_source_timezone_reference_id" if field == "source_timezone" else "after_" + field)
                    if current != recorded:
                        raise ValueError("timing correction after-image conflicts with current value")
                expected = {field: getattr(head, "after_" + field) for field in TIME_BASIS_FIELDS}
            else:
                report = observations[value.observation_id].source_metadata.get("reported_time", {})
                if not isinstance(report, dict) or not isinstance(report.get("metrics", {}), dict):
                    raise ValueError("historical reported timing must be an object")
                basis = report.get("metrics", {}).get(value.source_metric.metric_key)
                if basis is None:
                    continue
                if not isinstance(basis, dict) or not isinstance(basis.get("unknowns", {}), dict):
                    raise ValueError("historical metric timing basis must be an object")
                expected = dict.fromkeys(TIME_BASIS_FIELDS)
                expected.update(metric_time_provenance(
                    value.source_metric,
                    {field: getattr(value, field) for field in TIME_STATE_FIELDS if field != "source_timezone"},
                    basis,
                ))
            for field, proposed in expected.items():
                if proposed is not None and (
                    not isinstance(proposed, str)
                    or len(proposed) > MetricValue._meta.get_field(field).max_length
                ):
                    raise ValueError("historical metric timing explanation is invalid")
                current = getattr(value, field)
                if current is not None and current != proposed:
                    raise ValueError("typed metric timing explanation conflicts with retained evidence")
            if any(getattr(value, field) != proposed for field, proposed in expected.items()):
                if verify_only:
                    raise ValueError("historical metric timing explanation is not projected")
                for field, proposed in expected.items():
                    setattr(value, field, proposed)
                changed.append(value)
        if changed:
            MetricValue.objects.bulk_update(changed, TIME_BASIS_FIELDS, batch_size=250)
        return ProvenanceBatch(ids[-1], len(ids), len(changed))


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
            + " WHERE source_metadata ? 'ingestion_mode' "
            "AND direct_ingestion IS DISTINCT FROM " + expression
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
        ).filter(
            Q(source_metadata__has_key="publication_dates")
            | Q(source_metadata_archive__isnull=False)
        )
        if after_id is not None:
            runs = runs.filter(pk__gt=after_id)
        if not verify_only:
            runs = runs.select_for_update(of=("self",))
        selected = list(runs.order_by("pk")[:batch_size])
        inserted = 0
        for run in selected:
            from core.collection_capture import read_document

            metadata = (
                read_document(run.source_metadata_archive)
                if run.source_metadata_archive_id is not None else run.source_metadata
            )
            if not isinstance(metadata, dict):
                raise ValueError("Arena source metadata is invalid")
            if "publication_dates" not in metadata:
                continue
            native = metadata["publication_dates"]
            if not isinstance(native, list) or not 0 < len(native) <= 366:
                raise ValueError("invalid Arena publication-date evidence")
            dates = sorted({native_date(day).isoformat() for day in native})
            payload = (
                read_document(run.payload_archive)
                if run.payload_archive_id is not None else run.raw_payload
            )
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
        ).filter(
            Q(source_metadata__has_key="endpoint_checks")
            | Q(source_metadata_archive__isnull=False)
        ).select_related("job__contract")
        if after_id is not None:
            runs = runs.filter(pk__gt=after_id)
        if not verify_only:
            runs = runs.select_for_update(of=("self",))
        selected = list(runs.order_by("pk")[:batch_size])
        inserted = 0
        for run in selected:
            from core.collection_capture import read_document

            metadata = (
                read_document(run.source_metadata_archive)
                if run.source_metadata_archive_id is not None else run.source_metadata
            )
            if not isinstance(metadata, dict):
                raise ValueError("OpenCode source metadata is invalid")
            if "endpoint_checks" not in metadata:
                continue
            checks = metadata["endpoint_checks"]
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
    ) + f" OR ({INVALID_ROW_SEMANTIC_HASH})"
    run_expression = (
        "CASE WHEN source_metadata ? 'ingestion_mode' THEN "
        "source_metadata->>'ingestion_mode' = 'direct' END"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM collection_runs WHERE source_metadata ? 'ingestion_mode' "
            "AND direct_ingestion IS DISTINCT FROM " + run_expression
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


def stale_legacy_archive_count(table: str, *, batch_size: int = 1000) -> int:
    """Compare archived documents in bounded primary-key batches.

    A full-table archive join spills gigabytes of temporary files on staging.
    Each batch instead probes archive primary keys for only its selected rows.
    """
    if table not in LEGACY_FIELDS:
        raise ValueError("unsupported collection owner")
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be an integer from 1 to 1000")
    body = _document_expression(LEGACY_FIELDS[table])
    after_id = None
    stale_total = 0
    while True:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_hashjoin = off")
            cursor.execute("SET LOCAL enable_mergejoin = off")
            cursor.execute("SET LOCAL max_parallel_workers_per_gather = 0")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
            where = "WHERE id > %s" if after_id is not None else ""
            params = ([after_id] if after_id is not None else []) + [batch_size, ENCODING]
            cursor.execute(
                f"""
                WITH selected AS MATERIALIZED (
                    SELECT id FROM {table} {where} ORDER BY id LIMIT %s
                )
                SELECT
                    (SELECT id FROM selected ORDER BY id DESC LIMIT 1),
                    (SELECT count(*) FROM selected),
                    (SELECT count(*) FROM selected s
                     JOIN {table} t ON t.id = s.id
                     LEFT JOIN collection_evidence_archives a
                       ON a.id = t.legacy_archive_id
                     WHERE a.id IS NULL OR a.encoding <> %s
                        OR a.body <> {body})
                """,
                params,
            )
            after_id, selected, stale = cursor.fetchone()
            stale_total += stale
            if selected < batch_size:
                return stale_total
