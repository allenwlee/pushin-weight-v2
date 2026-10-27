"""Read only chart facts projected from retained collection evidence."""

from django.db import connection
from django.db.models.expressions import RawSQL

from core.measurement_taxonomy import require


def observation_read_fields(prefix=""):
    """Select the typed facts used by chart and forecast readers during cutover."""
    return tuple(prefix + field for field in (
        "id", "mapping_id", "source_identifier", "observed_at",
        "config_key", "category_key", "source_record_date", "period_status",
        "history_reconstructed", "secondary_source", "publication_complete",
        "archive_snapshot_date", "reconstruction_date", "row_semantic_digest",
        "source_dataset_id", "run__id", "run__completed_at", "run__source_as_of",
        "run__payload_sha256", "run__direct_ingestion", "run__job__source_id",
    ))


def metric_value_read_fields():
    return (
        "id", "source_metric", "integer_value", "float_value", "temporal_status",
        "source_timezone_reference_id", "as_of_at", "as_of_date", "window_start_at",
        "window_end_at", "period_label_date", "as_of_basis", "window_end_basis",
        *observation_read_fields("observation__"),
    )


def observation_ids(predicate, params=(), *, mapping_ids, contract_id, source_id):
    # Predicates are internal constants, never user-provided SQL.
    # OFFSET 0 keeps each scalar projection tied to its already selected owner.
    # Otherwise the planner can scan the entire evidence history for every OR
    # subquery, despite a chart selecting only a few hundred observations.
    mappings = list(mapping_ids) if mapping_ids is not None else None
    return RawSQL(
        "SELECT p.id FROM collection_observations o "
        "JOIN collection_runs r ON r.id=o.run_id JOIN collection_jobs j ON j.id=r.job_id "
        "CROSS JOIN LATERAL (SELECT * FROM benchmark_observation_provenance "
        "WHERE id=o.id OFFSET 0) p WHERE j.contract_id=%s AND j.source_id=%s "
        "AND (%s::uuid[] IS NULL OR o.mapping_id=ANY(%s::uuid[])) AND (" + predicate + ")",
        [contract_id, source_id, mappings, mappings, *params],
    )


def observation_dimensions(observation):
    """Render source coordinates from the retained typed observation facts."""
    source = observation.run.job.source_id
    dimensions = {}
    if source == "arena":
        if observation.config_key is not None:
            dimensions["config"] = observation.config_key
        if observation.category_key is not None:
            dimensions["category"] = observation.category_key
    if source in {"openrouter", "opencode"} and observation.source_record_date:
        dimensions["date"] = observation.source_record_date.isoformat()
    return dimensions


def observation_provenance_metadata(observation):
    """Expose retained publication facts without reading retired documents."""
    metadata = {}
    if observation.period_status is not None:
        metadata["period_status"] = observation.period_status
    if observation.history_reconstructed is True:
        metadata["history_basis"] = "reconstructed_current_relationships"
    if observation.secondary_source is not None:
        metadata["secondary_source"] = observation.secondary_source
    if observation.publication_complete is not None:
        metadata["publication_complete"] = observation.publication_complete
    if observation.archive_snapshot_date is not None:
        metadata["archive_snapshot_date"] = observation.archive_snapshot_date.isoformat()
    if observation.reconstruction_date is not None:
        metadata["reconstruction_date"] = observation.reconstruction_date.isoformat()
    return metadata


def github_asset_metric(definition):
    return (
        definition.definition_metadata.get("resource_grain") == "release_asset"
        or definition.metric_key in {"asset_downloads", "asset_size_bytes"}
    )


def github_asset_coordinates(observation_ids):
    """Follow exact numeric-input and release/asset-parent facts."""
    if not observation_ids:
        return {}
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT metric_input.observation_id, asset.native_stable_id,
                release.native_stable_id
            FROM collection_observation_inputs metric_input
            JOIN collection_observations metric
                ON metric.id=metric_input.observation_id
            JOIN collection_observations asset_observation
                ON asset_observation.id=metric_input.input_observation_id
            JOIN collection_runs asset_run ON asset_run.id=asset_observation.run_id
            JOIN collection_jobs asset_job ON asset_job.id=asset_run.job_id
            JOIN collection_resource_snapshots asset
                ON asset.observation_id=asset_observation.id
            JOIN collection_observation_inputs parent
                ON parent.observation_id=asset_observation.id
                AND parent.input_role='release_asset_parent'
            JOIN collection_observations release_observation
                ON release_observation.id=parent.input_observation_id
            JOIN collection_runs release_run ON release_run.id=release_observation.run_id
            JOIN collection_jobs release_job ON release_job.id=release_run.job_id
            JOIN collection_resource_snapshots release
                ON release.observation_id=release_observation.id
            WHERE metric_input.observation_id=ANY(%s)
                AND metric_input.input_role='numeric_projection'
                AND asset.resource_kind='release_asset'
                AND release.resource_kind='releases'
                AND asset_job.source_id='github' AND asset_job.purpose='catalog'
                AND release_job.source_id='github' AND release_job.purpose='catalog'
                AND asset_observation.source_identifier=metric.source_identifier
                AND release_observation.source_identifier=metric.source_identifier
                AND metric_input.input_sha256=asset_observation.observation_key
                AND parent.input_sha256=release_observation.observation_key
                AND parent.row_locator=release.native_stable_id
        """, [list(observation_ids)])
        rows = cursor.fetchall()
    result = {}
    for observation_id, asset_id, release_id in rows:
        require(
            all(isinstance(value, str) and value.isascii() and value.isdecimal()
                and value.lstrip("0") == value for value in (asset_id, release_id)),
            "GitHub asset identity is not numeric",
        )
        coordinates = {"release_id": int(release_id), "asset_id": int(asset_id)}
        prior = result.setdefault(observation_id, coordinates)
        require(prior == coordinates, "GitHub asset has conflicting parents")
    return result


def publication_runs(contract, lower, upper):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.publication_date,r.id,r.source_as_of,r.completed_at "
            "FROM benchmark_publication_dates p JOIN collection_runs r ON r.id=p.run_id "
            "JOIN collection_jobs j ON j.id=r.job_id WHERE j.contract_id=%s "
            "AND p.publication_date BETWEEN %s AND %s ORDER BY r.id,p.publication_date LIMIT 366001",
            [contract.pk, lower, upper],
        )
        rows = cursor.fetchall()
    if len(rows) > 366000 or len({row[1] for row in rows}) > 1000:
        raise ValueError("publication run budget exceeded")
    return rows


def selected_endpoint_rows(contract, mapping_ids, start, end, cutoff):
    # Keep this validated view lookup correlated to an eligible contract run.
    # Flattening it can expand every endpoint revision before applying the
    # contract filter, even when the chart requests only a few dozen dates.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT ON (p.external_identifier,p.period_date) "
            "p.external_identifier,p.period_date,p.observation_id,p.run_id,"
            "p.updated_at,p.body_sha256,p.conflicting_revision "
            "FROM collection_jobs j JOIN collection_runs r ON r.job_id=j.id "
            "CROSS JOIN LATERAL (SELECT * FROM benchmark_endpoint_revisions p "
            "WHERE p.run_id=r.id OFFSET 0) p "
            "WHERE j.contract_id=%s AND j.source_id='opencode' AND j.purpose='metric' "
            "AND r.status IN ('success','partial') AND p.mapping_id=ANY(%s::uuid[]) "
            "AND p.period_date BETWEEN %s AND %s "
            "AND (%s::timestamptz IS NULL OR (r.completed_at<=%s AND p.updated_at<=%s)) "
            "ORDER BY p.external_identifier,p.period_date,p.updated_at DESC,p.body_sha256 DESC,r.completed_at DESC,r.id DESC LIMIT 36601",
            [contract.pk, list(mapping_ids), start, end, cutoff, cutoff, cutoff],
        )
        rows = cursor.fetchall()
    result = []
    for identifier, day, observation, run, updated, digest, conflict in rows:
        if None in (observation, updated, digest):
            raise ValueError("Invalid retained endpoint provenance")
        check = {"updated_at": updated.isoformat(), "body_sha256": digest}
        if conflict:
            check["revision_anomaly"] = "same_update_different_body"
        result.append((identifier, day.isoformat(), observation, run, check))
    return result
