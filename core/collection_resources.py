"""Typed nonnumeric source facts and per-measurement timing explanations."""

from datetime import UTC, datetime

from core.benchmark_metric_timing import aware_instant, native_date
from core.measurement_taxonomy import digest
from core.models import (
    CollectionMetricGap,
    CollectionObservation,
    CollectionObservationInput,
    CollectionResourceSnapshot,
    SourceMetric,
)


def metric_time_provenance(definition, point, basis):
    """Keep explanations with the value; preserve the approved dates unchanged."""
    basis = basis or {}
    unknowns = basis.get("unknowns", {})
    fields = {
        "reported_time_policy": basis.get("policy"),
        "provenance_precision": basis.get("precision"),
    }
    if definition.measurement_kind == "state":
        if point.get("as_of_at") is not None or point.get("as_of_date") is not None:
            fields["as_of_basis"] = basis.get("basis", "adapter_supplied")
        else:
            fields["as_of_unknown_reason"] = unknowns.get(
                "as_of", unknowns.get("end", "adapter_did_not_supply_as_of")
            )
    else:
        for side in ("start", "end"):
            if point.get("window_" + side + "_at") is not None:
                fields["window_" + side + "_basis"] = basis.get(
                    "start_basis" if side == "start" else "basis", "adapter_supplied"
                )
            else:
                fields["window_" + side + "_unknown_reason"] = unknowns.get(
                    side, "adapter_did_not_supply_" + side
                )
    return fields


def _clock(value):
    if value is None:
        return None, None, "unknown"
    try:
        if isinstance(value, str) and len(value) == 10:
            return None, native_date(value), "date"
        if type(value) in {int, float}:
            return datetime.fromtimestamp(value, UTC), None, "instant"
        return aware_instant(value), None, "instant"
    except (ValueError, TypeError, OverflowError, OSError):
        return None, None, "unknown"


def snapshot_resource(observation):
    """Project current supported facts; retain unused provider fields in capture."""
    raw = observation.listing
    if not isinstance(raw, dict) or observation.post_id:
        return None
    kind = observation.dimensions.get("kind", observation.source_subject_kind)
    if kind in {"publication_row", "publication_window"}:
        return None
    created = raw.get("createdAt", raw.get("created_at", raw.get("created")))
    modified = raw.get("lastModified", raw.get("updated_at"))
    created_at, created_date, created_precision = _clock(created)
    modified_at, modified_date, modified_precision = _clock(modified)
    commit = raw.get("commit") if isinstance(raw.get("commit"), dict) else {}
    author = commit.get("author") or {}
    committer = commit.get("committer") or {}
    change = observation.source_metadata.get("file_changes", {})
    gated = raw.get("gated")
    if type(gated) is bool:
        gated = "gated" if gated else "public"
    values = {
        "resource_kind": kind,
        "native_identifier": observation.source_identifier,
        "native_stable_id": str(raw["id"])
        if observation.run.job.source_id == "github" and raw.get("id") is not None
        else None,
        "publisher_account_id": _snapshot_publisher(observation, raw),
        "display_name": raw.get("name", raw.get("full_name")),
        "provider_created_at": created_at,
        "provider_created_date": created_date,
        "provider_created_precision": created_precision,
        "provider_created_unknown_reason": (
            "field_not_supplied" if created is None else "invalid_provider_value"
        )
        if created_precision == "unknown"
        else None,
        "provider_modified_at": modified_at,
        "provider_modified_date": modified_date,
        "provider_modified_precision": modified_precision,
        "provider_modified_unknown_reason": (
            "field_not_supplied" if modified is None else "invalid_provider_value"
        )
        if modified_precision == "unknown"
        else None,
        "authored_at": _clock(author.get("date"))[0],
        "committed_at": _clock(committer.get("date"))[0],
        "revision": raw.get("sha"),
        "tree_revision": (commit.get("tree") or {}).get("sha"),
        "is_private": raw.get("private") if type(raw.get("private")) is bool else None,
        "gated_status": gated if isinstance(gated, str) else None,
        "is_disabled": raw.get("disabled")
        if type(raw.get("disabled")) is bool
        else None,
        "pipeline_tag": raw.get("pipeline_tag"),
        "library_name": raw.get("library_name"),
        "file_change_kind": change.get("kind"),
        "file_comparison_basis": change.get("comparison_basis"),
    }
    snapshot, _ = CollectionResourceSnapshot.objects.get_or_create(
        observation=observation, defaults=values
    )
    return snapshot


def _snapshot_publisher(observation, raw):
    """Use native ownership when supplied; never turn a conflicting owner into a match."""
    from core.models import Account

    job = observation.run.job
    native = None
    if job.source_id == "github" and isinstance(raw.get("owner"), dict):
        native = raw["owner"].get("id")
    elif job.source_id == "hf":
        native = raw.get("author")
        identifier = raw.get("id")
        if not native and isinstance(identifier, str) and "/" in identifier:
            native = identifier.split("/", 1)[0]
    if native is not None:
        identifier = str(native).casefold() if job.source_id == "hf" else str(native)
        return (
            Account.objects.filter(
                data_source_id=job.source_id,
                normalized_identifier=identifier,
            )
            .values_list("pk", flat=True)
            .first()
        )
    if job.owner_account_id and job.owner_account.data_source_id == job.source_id:
        return job.owner_account_id
    if observation.mapping_id and observation.mapping.publisher_account_id:
        publisher = observation.mapping.publisher_account
        if publisher.data_source_id == job.source_id:
            return publisher.pk
    return None


def observation_fact_values(observation):
    metadata, dimensions = observation.source_metadata, observation.dimensions
    values = {
        "observation_kind": dimensions.get("kind"),
        "projection_kind": metadata.get("projection_kind"),
        "definition_sha256": metadata.get("definitions_sha256"),
        "mapping_sha256": metadata.get("publisher_mapping_hash"),
        "config_key": dimensions.get("config"),
        "category_key": dimensions.get("category"),
        "provider_revision": metadata.get("revision"),
        "period_status": metadata.get("period_status"),
        "payload_sha256": digest(observation.listing),
        "historical_visibility_proven": metadata.get(
            "historical_public_visibility_proven"
        ),
    }
    for field in ("source_record_date", "archive_snapshot_date"):
        if metadata.get(field):
            instant, day, precision = _clock(metadata[field])
            if field == "source_record_date" and precision == "instant":
                values["source_record_at"] = instant
            elif day is not None:
                values[field] = day
    if metadata.get("original_retrieved_at"):
        values["original_retrieved_at"] = aware_instant(
            metadata["original_retrieved_at"]
        )
    if "coordinate" in dimensions:
        coordinate = dimensions["coordinate"]
        values["coordinate_key"] = (
            coordinate if isinstance(coordinate, str) else digest(coordinate)
        )
    return values


def project_observation_facts(observation):
    values = observation_fact_values(observation)
    inputs = list(
        observation.inputs.order_by(
            "input_role",
            "input_request_id",
            "input_observation_id",
            "row_locator",
        ).values(
            "input_role",
            "input_request_id",
            "input_observation_id",
            "row_locator",
            "input_sha256",
        )
    )
    if inputs:
        for edge in inputs:
            if edge["input_request_id"] is not None:
                edge["input_request_id"] = str(edge["input_request_id"])
        values["input_set_sha256"] = digest(inputs)
    for field, value in values.items():
        setattr(observation, field, value)
    observation.save(update_fields=list(values))
    return snapshot_resource(observation)


def attach_numeric_evidence(
    run, observations, prepared, *, reused_ids=(), supplemented_ids=()
):
    """Project lineage and selected metric gaps in batches inside the writer fence.

    The old adapter dictionaries are transient inputs. Typed records own their
    identities, missing-counter decisions and provenance before JSON retirement.
    Existing snapshots stay immutable on replay.
    """
    from core.measurement_taxonomy import require

    reused_ids = set(reused_ids)
    supplemented_ids = set(supplemented_ids)
    pairs = [
        pair
        for pair in zip(observations, prepared, strict=True)
        if pair[0].pk not in reused_ids or pair[0].pk in supplemented_ids
    ]
    if not pairs:
        return
    origin_ids = {
        data["source_metadata"]["origin_observation_id"]
        for _, (data, _) in pairs
        if data["source_metadata"].get("origin_observation_id") is not None
    }
    origins = (
        CollectionObservation.objects.filter(pk__in=origin_ids)
        .select_related("run__job")
        .in_bulk()
    )
    require(len(origins) == len(origin_ids), "missing numeric evidence input")
    configuration = run.job.contract.source_configuration[run.job.source_id]
    definitions = list(
        SourceMetric.objects.filter(
            pk__in=[d["id"] for d in configuration["definitions"]]
        )
    )
    inputs, gaps, changed, fields = [], [], [], set()
    for observation, (data, values) in pairs:
        metadata = data["source_metadata"]
        origin_id = metadata.get("origin_observation_id")
        origin = origins.get(origin_id)
        if origin is not None:
            require(
                origin.run.job.source_id == run.job.source_id,
                "numeric evidence source mismatch",
            )
            inputs.append(
                CollectionObservationInput(
                    observation=observation,
                    input_observation=origin,
                    input_role="numeric_supplement"
                    if observation.pk in reused_ids
                    else "numeric_projection",
                    input_sha256=origin.observation_key,
                )
            )
        present = {v["source_metric"].pk for v in values}
        if observation.pk in reused_ids:
            CollectionMetricGap.objects.filter(
                observation=observation, source_metric_id__in=present
            ).delete()
            continue
        facts = observation_fact_values(observation)
        if origin:
            facts["payload_sha256"] = (
                metadata.get("source_payload_sha256") or origin.payload_sha256
            )
            facts["input_set_sha256"] = digest([origin.pk, origin.observation_key])
        for name, value in facts.items():
            setattr(observation, name, value)
        fields.update(facts)
        changed.append(observation)
        rejected = {r["metric"] for r in metadata.get("metric_rejections", [])}
        kind = data["source_subject_kind"]
        asset = data.get("dimensions", {}).get("asset_id") is not None
        for definition in definitions:
            if definition.pk in present:
                continue
            grain = definition.definition_metadata.get("resource_grain")
            if not grain and run.job.source_id == "hf":
                grain = (
                    "account" if definition.metric_key == "followers" else "repository"
                )
            actual_grain = (
                "account"
                if kind == "account"
                else "release_asset"
                if asset
                else "repository"
            )
            if grain and grain != actual_grain:
                continue
            if (
                metadata.get("history_basis") == "reconstructed_current_relationships"
                and definition.metric_key not in {"likes", "followers"}
            ):
                continue
            selected_fields = (
                origin.source_metadata.get("numeric_fields") if origin else None
            )
            if (
                selected_fields is not None
                and definition.definition_metadata.get("wire_field")
                not in selected_fields
            ):
                continue
            gaps.append(
                CollectionMetricGap(
                    observation=observation,
                    source_metric=definition,
                    reason_code="invalid_metric_value"
                    if definition.metric_key in rejected
                    else "selected_field_not_returned",
                    recoverable=False,
                    first_confirmed_at=observation.observed_at,
                    last_confirmed_at=observation.observed_at,
                )
            )
    if changed:
        CollectionObservation.objects.bulk_update(
            changed, sorted(fields), batch_size=500
        )
    CollectionObservationInput.objects.bulk_create(
        inputs, ignore_conflicts=True, batch_size=1000
    )
    CollectionMetricGap.objects.bulk_create(
        gaps, ignore_conflicts=True, batch_size=1000
    )
    if supplemented_ids:
        # New optional counters can extend a publication, while original capture
        # clocks, primary payload and existing value provenance remain unchanged.
        references = {}
        for owner_id, input_id, fingerprint, role in (
            CollectionObservationInput.objects.filter(
                observation_id__in=supplemented_ids
            )
            .order_by("input_observation_id", "input_role")
            .values_list(
                "observation_id", "input_observation_id", "input_sha256", "input_role"
            )
        ):
            references.setdefault(owner_id, []).append([input_id, fingerprint, role])
        for owner_id, members in references.items():
            CollectionObservation.objects.filter(pk=owner_id).update(
                input_set_sha256=digest(members)
            )
