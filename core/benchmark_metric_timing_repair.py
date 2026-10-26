"""Bounded timing-only correction using the same resolver as normal ingestion."""

from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime

from django.db import connection, transaction
from django.db.models import Q

from core.benchmark_metric_store import TIME_FIELDS, native_rows, value_times
from core.benchmark_metric_timing import (
    POLICY,
    aware_instant,
    catalog_origins,
    native_origin,
    reported_times,
    timing_storage,
)
from core.collection_capture import observation_object_documents, read_document
from core.collection_corrections import (
    TIME_BASIS_FIELDS,
    correction_head,
    record_timing_correction,
)
from core.collection_resources import metric_time_provenance
from core.measurement_taxonomy import digest, require
from core.models import CollectionObservation, MetricValue, SourceMetric

REPAIR_KEY = "timing_correction_v1"
LOCK_KEY = 0x473354494D4531
FIELDS = (*TIME_FIELDS, "temporal_status", "source_timezone")


def _update_locked_batch(model, rows, names):
    """Write already-locked rows without constructing thousands of CASE nodes."""
    if not rows:
        return
    require(len(rows) <= 1000, "timing update exceeds batch bound")
    fields = [model._meta.pk, *(model._meta.get_field(name) for name in names)]
    quote = connection.ops.quote_name
    columns = [quote(field.column) for field in fields]
    placeholders = (
        "(" + ",".join("%s::" + field.db_type(connection) for field in fields) + ")"
    )
    assignments = ",".join(f"{column}=patch.{column}" for column in columns[1:])
    parameters = [
        field.get_db_prep_save(getattr(row, field.attname), connection)
        for row in rows
        for field in fields
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {quote(model._meta.db_table)} AS target SET {assignments} "
            f"FROM (VALUES {','.join([placeholders] * len(rows))}) "
            f"AS patch ({','.join(columns)}) "
            f"WHERE target.{columns[0]}=patch.{columns[0]}",
            parameters,
        )
        require(cursor.rowcount == len(rows), "timing update row count mismatch")


def serial_fields(fields):
    return {
        key: value.isoformat() if isinstance(value, (date, datetime)) else value
        for key, value in fields.items()
    }


def _correction_state(correction, side):
    return serial_fields(
        {
            field: (
                getattr(correction, side + "_source_timezone_reference_id") or "unknown"
            )
            if field == "source_timezone"
            else getattr(correction, side + "_" + field)
            for field in FIELDS
        }
    )


@contextmanager
def repair_lock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_KEY])
        acquired = cursor.fetchone()[0]
    require(acquired, "metric timing correction is already running")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])


def candidate_values(cutoff, after=0, rollback=False):
    values = MetricValue.objects.filter(id__gt=after, id__lte=cutoff)
    if rollback:
        # Bound the primary-key page before inspecting correction heads and
        # archived markers; never scan the evidence corpus to find a page.
        return values
    source_ids = defaultdict(list)
    for pk, source in SourceMetric.objects.filter(
        source_id__in=["hf", "github", "opencode"]
    ).values_list("pk", "source_id"):
        source_ids[source].append(pk)
    return values.filter(
        Q(
            source_metric_id__in=source_ids["hf"] + source_ids["github"],
            temporal_status="unknown",
        )
        | Q(
            source_metric_id__in=source_ids["opencode"],
            window_start_at__isnull=False,
            window_end_at__isnull=True,
        )
    )


def _archived_observation(observation):
    """Explicit maintenance evidence; never read the retired live JSON columns."""
    if observation.legacy_archive_id is None:
        return None
    archive = observation.legacy_archive
    if archive.capture_kind != "legacy_snapshot":
        return None
    document = read_document(archive)
    require(
        isinstance(document, dict)
        and all(
            isinstance(document.get(key), dict)
            for key in ("listing", "dimensions", "source_metadata")
        ),
        "invalid retained timing evidence",
    )
    return document


def _repair_evidence(observation, archived, payload_rows):
    """Replay only this observation's immutable source, never a newer capture."""
    metadata = archived["source_metadata"] if archived else {}
    raw = archived["listing"] if archived else {}
    links = list(
        observation.inputs.filter(input_role="numeric_projection").select_related(
            "input_observation__run__job"
        )
    )
    require(len(links) <= 1, "ambiguous primary timing evidence")
    if links:
        link = links[0]
        origin = link.input_observation
        require(
            origin is not None
            and origin.run.job.source_id == observation.run.job.source_id
            and origin.source_identifier == observation.source_identifier
            and link.input_sha256 == origin.observation_key,
            "timing evidence origin changed",
        )
        require(
            metadata.get("origin_observation_id", origin.pk) == origin.pk,
            "archived timing origin differs from typed input",
        )
        source_archive = _archived_observation(origin)
        if source_archive is not None:
            raw = source_archive["listing"]
            if archived is None:
                metadata = source_archive["source_metadata"]
        else:
            # Never enter the helper's historical live-column fallback.
            require(
                origin.projection_kind
                in {
                    "github-catalog-object-v1",
                    "hf-native-history-v1",
                    "hf-archive-row-v1",
                }
                or origin.legacy_archive_id is not None
                or origin.observation_kind == "hf_catalog_listing",
                "timing origin has no captured source object",
            )
            raw, _, source_metadata = observation_object_documents(origin)
            if archived is None:
                metadata = source_metadata
        created = native_origin(raw)
    elif archived is not None:
        require(
            not metadata.get("origin_observation_id"),
            "historical timing origin needs typed input projection",
        )
        created = native_origin(raw)
    else:
        run = observation.run
        require(
            run.payload_archive_id is not None,
            "timing repair requires retained source evidence",
        )
        if run.pk not in payload_rows:
            payload = read_document(run.payload_archive)
            require(
                digest(payload) == run.payload_sha256,
                "timing source payload hash changed",
            )
            selected = {}
            for row in native_rows(run.job.source_id, payload):
                meta = row.get("source_metadata", {})
                key = digest(
                    [
                        row["source_subject_kind"],
                        row.get("identifier_scope", ""),
                        row["source_identifier"],
                        row.get("dimensions", {}),
                        row.get("published_at"),
                        row.get("published_date"),
                        meta.get("archive_snapshot_date"),
                        meta.get("reconstruction_date"),
                        meta.get("history_basis"),
                        meta.get("immutable_revision"),
                    ]
                )
                require(
                    key not in selected or selected[key] == row,
                    "conflicting retained timing rows",
                )
                selected[key] = row
            payload_rows[run.pk] = selected
        row = payload_rows[run.pk].get(observation.observation_key)
        require(row is not None, "timing observation absent from retained source")
        metadata = row.get("source_metadata", {})
        created = row.get("native_created_at")
    # Import/correction time must never become the original capture time.
    metadata = dict(metadata)
    if observation.original_retrieved_at is not None:
        require(
            not metadata.get("original_retrieved_at")
            or aware_instant(metadata["original_retrieved_at"])
            == observation.original_retrieved_at,
            "timing capture clock changed",
        )
        metadata["original_retrieved_at"] = observation.original_retrieved_at
    for field in ("archive_snapshot_date", "period_status"):
        value = getattr(observation, field)
        if value is not None:
            expected = value.isoformat() if isinstance(value, date) else value
            require(
                metadata.get(field, expected) == expected,
                "timing source coordinate changed: " + field,
            )
            metadata[field] = expected
    return {
        "source_metadata": metadata,
        "observed_at": observation.observed_at,
        "published_date": observation.published_date,
        "published_at": observation.published_at,
    }, created


def _rollback_point(target, basis, definition):
    """Restore the validator's reported-date explanation from typed provenance."""
    point = dict(target)
    if target["temporal_status"] == "date_only":
        reported = {"policy": basis["reported_time_policy"]}
        if definition.source_id == "hf":
            reported["normalization"] = "UTC_report_day_exclusive_next_midnight"
        elif definition.source_id == "opencode":
            reported.update(basis=basis["window_end_basis"], partial=True)
        point["_reported_time"] = reported
    return point


def repair_batch(*, cutoff, after=0, batch_size=250, apply=False, rollback=False):
    """Typed before-images and timing changes commit together; archives stay immutable."""
    require(
        type(batch_size) is int and 1 <= batch_size <= 1000,
        "invalid correction batch size",
    )
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '1s'")
            cursor.execute("SET LOCAL statement_timeout = '15s'")
            cursor.execute("SET LOCAL work_mem = '4MB'")
            cursor.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        ids = list(
            candidate_values(cutoff, after, rollback)
            .order_by("id")
            .values_list("id", flat=True)[:batch_size]
        )
        result = {
            "after_value_id": max(ids, default=after),
            "scanned_values": len(ids),
            "changed_values": 0,
            "metadata_updates": 0,
            "correction_records": 0,
            "reasons": {},
            "conflicts": 0,
            "deferred_values": 0,
        }
        if not ids:
            return result
        observation_ids = (
            MetricValue.objects.filter(pk__in=ids)
            .values_list("observation_id", flat=True)
            .distinct()
        )
        observations = (
            CollectionObservation.objects.filter(pk__in=observation_ids)
            .only(
                "id",
                "run_id",
                "observation_key",
                "source_identifier",
                "legacy_archive_id",
                "observed_at",
                "published_date",
                "published_at",
                "original_retrieved_at",
                "archive_snapshot_date",
                "period_status",
            )
            .order_by("pk")
        )
        if apply:
            observations = observations.select_for_update()
        observations = {o.pk: o for o in observations}
        values = (
            MetricValue.objects.filter(pk__in=ids)
            .select_related("source_metric")
            .order_by("pk")
        )
        if apply:
            values = values.select_for_update(of=("self",))
        grouped = defaultdict(list)
        for value in values:
            grouped[value.observation_id].append(value)
        origins = (
            catalog_origins([o.source_identifier for o in observations.values()])
            if not rollback
            else {}
        )
        reasons, changed_values, payload_rows = Counter(), [], {}
        for pk, selected in grouped.items():
            observation = observations[pk]
            archived = _archived_observation(observation)
            markers = (
                archived["source_metadata"].get(REPAIR_KEY, {}) if archived else {}
            )
            context = None
            for value in selected:
                previous_basis = {
                    name: getattr(value, name) for name in TIME_BASIS_FIELDS
                }
                previous = serial_fields(
                    {
                        field: (value.source_timezone_reference_id or "unknown")
                        if field == "source_timezone"
                        else getattr(value, field)
                        for field in FIELDS
                    }
                )
                recorded = correction_head(
                    observation, metric_value=value, kind="timing"
                )
                require(
                    str(value.pk) not in markers or recorded is not None,
                    "legacy timing marker must be imported before repair or rollback",
                )
                repaired = (
                    recorded
                    and recorded.policy_version == POLICY
                    and recorded.reason_code
                    in {
                        "reported_time_repair",
                        "historical_reported_time_repair",
                    }
                )
                if recorded:
                    if previous != _correction_state(recorded, "after") or any(
                        previous_basis[name] != getattr(recorded, "after_" + name)
                        for name in TIME_BASIS_FIELDS
                    ):
                        result["conflicts"] += 1
                        reasons["timing_changed_after_correction"] += 1
                        continue
                    if repaired and not rollback:
                        continue
                    if (
                        rollback
                        and recorded.policy_version == POLICY
                        and recorded.reason_code == "reported_time_rollback"
                    ):
                        continue
                    if (
                        not repaired
                        and recorded.reason_code != "reported_time_rollback"
                    ):
                        result["conflicts"] += 1
                        reasons["timing_changed_after_correction"] += 1
                        continue
                if rollback:
                    if not repaired:
                        continue
                    target = _correction_state(recorded, "before")
                    target_basis = {
                        name: getattr(recorded, "before_" + name)
                        for name in TIME_BASIS_FIELDS
                    }
                    point = _rollback_point(target, target_basis, value.source_metric)
                else:
                    if context is None:
                        context, created = _repair_evidence(
                            observation, archived, payload_rows
                        )
                    point, basis = reported_times(
                        value.source_metric,
                        previous,
                        context,
                        native_created=created,
                        catalog_created=origins.get(
                            observation.source_identifier.casefold()
                        ),
                    )
                    if basis is None:
                        continue
                    unknowns = basis.get("unknowns", {})
                    reasons.update(
                        f"{component}:{reason}"
                        for component, reason in unknowns.items()
                    )
                    if "start" in unknowns or "end" in unknowns:
                        result["deferred_values"] += 1
                    target = serial_fields(value_times(value.source_metric, point))
                    projected = metric_time_provenance(
                        value.source_metric, point, basis
                    )
                    target_basis = {
                        name: projected.get(name) for name in TIME_BASIS_FIELDS
                    }
                    if target == previous and target_basis == previous_basis:
                        continue
                validated = value_times(value.source_metric, point)
                result["correction_records"] += 1
                if apply:
                    record_timing_correction(
                        value,
                        before={**previous, **previous_basis},
                        after={**target, **target_basis},
                        policy=POLICY,
                        reason="reported_time_rollback"
                        if rollback
                        else "reported_time_repair",
                    )
                    for field, instant in {
                        **timing_storage(validated),
                        **target_basis,
                    }.items():
                        setattr(value, field, instant)
                    changed_values.append(value)
                if target != previous:
                    result["changed_values"] += 1
        if apply:
            _update_locked_batch(
                MetricValue,
                changed_values,
                (
                    *TIME_FIELDS,
                    "temporal_status",
                    "source_timezone_reference",
                    *TIME_BASIS_FIELDS,
                ),
            )
        result["reasons"] = dict(reasons)
        return result
