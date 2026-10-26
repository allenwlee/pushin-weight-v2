"""Import historical timing corrections without inventing their recorded time."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from django.db import connection, transaction
from django.utils import timezone

from core.benchmark_metric_timing import TIME_FIELDS, aware_instant
from core.collection_capture import observation_object_documents
from core.measurement_taxonomy import digest
from core.models import (
    Actor,
    CollectionCorrection,
    CollectionObservation,
    MetricValue,
    TimeZone,
)


@dataclass(frozen=True)
class CorrectionImportBatch:
    last_observation_id: int
    scanned_observations: int
    selected_corrections: int
    inserted_corrections: int


def _state(document):
    required = {*TIME_FIELDS, "temporal_status", "source_timezone"}
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("historical correction time state has unexpected fields")
    result = {}
    for field in TIME_FIELDS:
        value = document[field]
        if value is None:
            result[field] = None
        elif field.endswith("_date"):
            result[field] = date.fromisoformat(value)
        else:
            result[field] = aware_instant(value)
    result["temporal_status"] = document["temporal_status"]
    result["source_timezone"] = document["source_timezone"]
    return result


def _basis_fields(basis, state, side):
    if basis is None:
        return {}
    if not isinstance(basis, dict):
        raise TypeError("historical correction basis must be an object")
    unknowns = basis.get("unknowns", {})
    if not isinstance(unknowns, dict):
        raise TypeError("historical correction unknowns must be an object")
    prefix = side + "_"
    fields = {
        prefix + "reported_time_policy": basis.get("policy"),
        prefix + "provenance_precision": basis.get("precision"),
        prefix + "as_of_basis": basis.get("basis")
        if state["as_of_at"] is not None or state["as_of_date"] is not None
        else None,
        prefix + "window_start_basis": basis.get("start_basis")
        if state["window_start_at"] is not None else None,
        prefix + "window_end_basis": basis.get("basis")
        if state["window_end_at"] is not None else None,
        prefix + "as_of_unknown_reason": unknowns.get("as_of"),
        prefix + "window_start_unknown_reason": unknowns.get("start"),
        prefix + "window_end_unknown_reason": unknowns.get("end"),
    }
    return fields


def _current_time_state(value):
    return {
        **{field: getattr(value, field) for field in TIME_FIELDS},
        "temporal_status": value.temporal_status,
        "source_timezone": value.source_timezone_reference_id or "unknown",
    }


def import_legacy_timing_batch(
    *, after_id: int = 0, batch_size: int = 100, verify_only: bool = False
) -> CorrectionImportBatch:
    """Read one bounded owner page and preserve each verified before/after image.

    Historical JSON lacks a reliable correction clock. ``recorded_at`` remains
    NULL while ``imported_at`` records this copy, preserving that distinction.
    Repeating a page accepts identical deterministic roots and refuses drift.
    """
    if type(after_id) is not int or after_id < 0:
        raise ValueError("after_id must be a nonnegative integer")
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be an integer from 1 to 500")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        # Bound the primary-key page before inspecting JSON. Filtering the full
        # table first can choose a full scan/sort for every small batch when
        # PostgreSQL underestimates the historical marker's frequency.
        owner_ids = list(
            CollectionObservation.objects.filter(pk__gt=after_id)
            .order_by("pk").values_list("pk", flat=True)[:batch_size]
        )
        if not owner_ids:
            return CorrectionImportBatch(after_id, 0, 0, 0)
        observations_query = CollectionObservation.objects.filter(
            pk__in=owner_ids,
        ).select_related("legacy_archive")
        if not verify_only:
            observations_query = observations_query.select_for_update(of=("self",))
        observations = list(
            observations_query.only(
                "id", "source_metadata", "legacy_archive__body",
                "legacy_archive__content_sha256",
            ).order_by("pk")
        )
        if not observations:
            return CorrectionImportBatch(owner_ids[-1], len(owner_ids), 0, 0)
        selected = []
        for observation in observations:
            markers = observation_object_documents(observation)[2].get(
                "timing_correction_v1"
            )
            if markers is None:
                continue
            if not isinstance(markers, dict):
                raise TypeError("historical timing corrections must be keyed by value")
            for value_id, marker in markers.items():
                if not str(value_id).isdigit() or not isinstance(marker, dict):
                    raise ValueError("invalid historical timing correction identity")
                selected.append((observation.pk, int(value_id), marker))
        value_ids = {value_id for _, value_id, _ in selected}
        values_query = MetricValue.objects.filter(pk__in=value_ids)
        if not verify_only:
            values_query = values_query.select_for_update()
        values = values_query.in_bulk()
        if len(values) != len(value_ids):
            raise ValueError("historical timing correction refers to a missing value")
        zones = {
            state.get("source_timezone")
            for _, _, marker in selected
            for state in (marker.get("before", {}), marker.get("after", {}))
            if isinstance(state, dict)
            and state.get("source_timezone") not in {None, "unknown"}
        }
        if set(TimeZone.objects.filter(pk__in=zones).values_list("pk", flat=True)) != zones:
            raise ValueError("historical timing correction has an unknown time zone")
        actor = Actor.objects.filter(
            actor_kind=Actor.Kind.SYSTEM,
            actor_key="benchmark_metric_timing_repair",
        ).first()
        if actor is None and not verify_only:
            actor, _ = Actor.objects.get_or_create(
                actor_kind=Actor.Kind.SYSTEM,
                actor_key="benchmark_metric_timing_repair",
                defaults={
                    "id": uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        "pushinweight:actor:system:benchmark_metric_timing_repair",
                    )
                },
            )
        existing = {
            row.metric_value_id: row
            for row in CollectionCorrection.objects.filter(
                metric_value_id__in=value_ids, correction_kind="timing",
                predecessor__isnull=True,
            )
        }
        pending = []
        imported_at = timezone.now()
        for observation_id, value_id, marker in selected:
            value = values[value_id]
            if value.observation_id != observation_id:
                raise ValueError("historical correction value/observation mismatch")
            before = _state(marker.get("before"))
            after = _state(marker.get("after"))
            if _current_time_state(value) != after:
                raise ValueError("historical correction after-image differs from current value")
            policy = marker.get("policy")
            if not isinstance(policy, str) or not policy or len(policy) > 64:
                raise ValueError("historical correction policy is invalid")
            identity = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"pushinweight:rg6:historical-timing:{value_id}:{digest(marker)}",
            )
            fields = {}
            for side, state in (("before", before), ("after", after)):
                fields.update({
                    f"{side}_{field}": state[field]
                    for field in (*TIME_FIELDS, "temporal_status")
                })
                zone = state["source_timezone"]
                fields[f"{side}_source_timezone_reference_id"] = (
                    None if zone in {None, "unknown"} else zone
                )
                fields.update(_basis_fields(marker.get(side + "_basis"), state, side))
            prior = existing.get(value_id)
            if prior is not None:
                if (
                    prior.pk != identity
                    or prior.observation_id != observation_id
                    or actor is None
                    or prior.actor_id != actor.pk
                    or prior.policy_version != policy
                    or prior.reason_code != "historical_reported_time_repair"
                    or prior.recorded_at is not None
                    or prior.recorded_at_precision != "unknown"
                    or any(getattr(prior, key) != expected for key, expected in fields.items())
                ):
                    raise ValueError("typed timing correction conflicts with historical root")
                continue
            if verify_only:
                raise ValueError("historical timing correction has no typed root")
            pending.append(CollectionCorrection(
                id=identity,
                observation_id=observation_id,
                metric_value_id=value_id,
                correction_kind="timing",
                policy_version=policy,
                actor=actor,
                reason_code="historical_reported_time_repair",
                recorded_at=None,
                recorded_at_precision="unknown",
                imported_at=imported_at,
                **fields,
            ))
        if pending:
            CollectionCorrection.objects.bulk_create(pending, batch_size=500)
        return CorrectionImportBatch(
            owner_ids[-1], len(owner_ids), len(selected), len(pending)
        )
