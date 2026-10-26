"""Bounded timing-only correction using the same resolver as normal ingestion."""

import copy
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime

from django.db import connection, transaction
from django.db.models import Q

from core.benchmark_metric_store import TIME_FIELDS, value_times
from core.benchmark_metric_timing import (
    POLICY,
    catalog_origins,
    native_origin,
    reported_times,
    timing_storage,
)
from core.collection_corrections import (
    TIME_BASIS_FIELDS,
    correction_head,
    record_timing_correction,
)
from core.collection_resources import metric_time_provenance
from core.measurement_taxonomy import require
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
    return serial_fields({
        field: (getattr(correction, side + "_source_timezone_reference_id") or "unknown")
        if field == "source_timezone" else getattr(correction, side + "_" + field)
        for field in FIELDS
    })


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
        # Inspect markers only after bounding the scalar primary-key page. A
        # metadata join can scan the entire observation corpus before LIMIT.
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


def repair_batch(*, cutoff, after=0, batch_size=250, apply=False, rollback=False):
    """The observation before-image and all timing changes commit together."""
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
            "reasons": {},
            "conflicts": 0,
            "deferred_values": 0,
        }
        if not ids:
            return result
        observation_ids = list(
            MetricValue.objects.filter(pk__in=ids)
            .values_list("observation_id", flat=True)
            .distinct()
        )
        observations = CollectionObservation.objects.filter(
            pk__in=observation_ids
        ).order_by("pk")
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
        values = list(values)
        # Follow only exact retained evidence references, never a newer capture.
        origin_ids = {
            o.source_metadata.get("origin_observation_id")
            for o in observations.values()
        }
        origin_ids = {int(pk) for pk in origin_ids if str(pk).isdigit()}
        native = dict(
            CollectionObservation.objects.filter(pk__in=origin_ids).values_list(
                "id", "listing"
            )
        )
        origins = catalog_origins([o.source_identifier for o in observations.values()])
        grouped = defaultdict(list)
        for value in values:
            grouped[value.observation_id].append(value)
        reasons = Counter()
        changed_values, changed_observations = [], []
        for pk, selected in grouped.items():
            observation = observations[pk]
            metadata = copy.deepcopy(observation.source_metadata)
            context = {
                "source_metadata": metadata,
                "observed_at": observation.observed_at,
                "published_date": observation.published_date,
                "published_at": observation.published_at,
            }
            raw = (
                native.get(metadata.get("origin_observation_id"))
                or observation.listing
                or {}
            )
            for value in selected:
                previous_basis_fields = {name: getattr(value, name) for name in TIME_BASIS_FIELDS}
                previous = serial_fields(
                    {field: (value.source_timezone_reference_id or "unknown")
                     if field == "source_timezone" else getattr(value, field) for field in FIELDS}
                )
                marker = metadata.get(REPAIR_KEY, {}).get(str(value.pk))
                current_basis = (
                    metadata.get("reported_time", {})
                    .get("metrics", {})
                    .get(value.source_metric.metric_key)
                )
                marker_conflict = marker and (
                    previous != marker["after"]
                    or current_basis != marker["after_basis"]
                )
                recorded = correction_head(observation, metric_value=value, kind="timing")
                repaired = recorded and recorded.policy_version == POLICY and recorded.reason_code in {
                    "reported_time_repair", "historical_reported_time_repair",
                }
                if repaired:
                    # The current typed head owns both the time and its explanation.
                    # A retired JSON marker must neither disable rollback nor hide
                    # a later change to either part of the saved after-image.
                    typed_conflict = previous != _correction_state(recorded, "after") or any(
                        previous_basis_fields[name] != getattr(recorded, "after_" + name)
                        for name in TIME_BASIS_FIELDS
                    )
                    if typed_conflict or marker_conflict:
                        result["conflicts"] += 1
                        reasons["timing_changed_after_correction"] += 1
                        continue
                    if not rollback:
                        continue
                elif rollback and recorded:
                    if recorded.policy_version == POLICY and recorded.reason_code == "reported_time_rollback":
                        continue
                    result["conflicts"] += 1
                    reasons["timing_changed_after_correction"] += 1
                    continue
                if rollback:
                    if not repaired and not marker:
                        continue
                    if not repaired and marker_conflict:
                        result["conflicts"] += 1
                        reasons["timing_changed_after_correction"] += 1
                        continue
                    if repaired:
                        target = _correction_state(recorded, "before")
                        point = target
                    else:
                        target = marker["before"]
                        point = {**target, "_reported_time": marker.get("before_basis") or {}}
                    # Maintain an existing old-image receipt during additive rollout;
                    # never recreate legacy storage when only typed history exists.
                    if marker:
                        metric = value.source_metric.metric_key
                        report = metadata.get("reported_time", {}).get("metrics", {})
                        if marker.get("before_basis") is None:
                            report.pop(metric, None)
                        else:
                            report[metric] = marker["before_basis"]
                        if not report:
                            metadata.pop("reported_time", None)
                        del metadata[REPAIR_KEY][str(value.pk)]
                        if not metadata[REPAIR_KEY]:
                            del metadata[REPAIR_KEY]
                    target_basis_fields = {
                        name: getattr(recorded, "before_" + name) for name in TIME_BASIS_FIELDS
                    } if recorded else metric_time_provenance(value.source_metric, point, marker.get("before_basis"))
                else:
                    if marker:
                        if marker_conflict:
                            result["conflicts"] += 1
                            reasons["timing_changed_after_correction"] += 1
                        continue
                    point, basis = reported_times(
                        value.source_metric,
                        previous,
                        context,
                        native_created=native_origin(raw),
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
                    metric = value.source_metric.metric_key
                    before_basis = copy.deepcopy(
                        metadata.get("reported_time", {}).get("metrics", {}).get(metric)
                    )
                    if target == previous and basis == before_basis:
                        continue
                    metadata.setdefault(REPAIR_KEY, {})[str(value.pk)] = {
                        "policy": POLICY,
                        "before": previous,
                        "after": target,
                        "before_basis": before_basis,
                        "after_basis": basis,
                    }
                    metadata.setdefault(
                        "reported_time", {"policy": POLICY, "metrics": {}}
                    )["metrics"][metric] = basis
                    target_basis_fields = metric_time_provenance(value.source_metric, point, basis)
                # The regular validator enforces ranges and precision on rollback too.
                validated = value_times(value.source_metric, point)
                if apply:
                    record_timing_correction(
                        value, before={**previous, **previous_basis_fields},
                        after={**target, **target_basis_fields}, policy=POLICY,
                        reason="reported_time_rollback" if rollback else "reported_time_repair",
                    )
                if target != previous:
                    result["changed_values"] += 1
                if apply and (target != previous or previous_basis_fields != target_basis_fields):
                    for field, instant in {**timing_storage(validated), **target_basis_fields}.items():
                        setattr(value, field, instant)
                    changed_values.append(value)
            if metadata != observation.source_metadata:
                result["metadata_updates"] += 1
                if apply:
                    observation.source_metadata = metadata
                    changed_observations.append(observation)
        if apply:
            _update_locked_batch(MetricValue, changed_values, (
                *TIME_FIELDS, "temporal_status", "source_timezone_reference", *TIME_BASIS_FIELDS,
            ))
            _update_locked_batch(
                CollectionObservation, changed_observations, ["source_metadata"]
            )
        result["reasons"] = dict(reasons)
        return result
