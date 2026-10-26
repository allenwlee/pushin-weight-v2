"""Read only chart facts projected from retained collection evidence."""

from django.db import connection
from django.db.models.expressions import RawSQL


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


def hydrate_observations(observations):
    """Attach a bounded safe dictionary in memory, never a persisted JSON copy."""
    from collections import defaultdict

    by_id = defaultdict(list)
    for observation in observations:
        by_id[observation.pk].append(observation)
    if not by_id:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,reconstructed,secondary_source,archive_snapshot_date,"
            "reconstruction_date,publication_complete,partial,direct "
            "FROM benchmark_observation_provenance WHERE id=ANY(%s)", [list(by_id)],
        )
        rows = cursor.fetchall()
    for key, reconstructed, secondary, archived, rebuilt, complete, partial, direct in rows:
        metadata = {"secondary_source": secondary, "publication_complete": complete}
        if reconstructed:
            metadata["history_basis"] = "reconstructed_current_relationships"
        if archived:
            metadata["archive_snapshot_date"] = archived.isoformat()
        if rebuilt:
            metadata["reconstruction_date"] = rebuilt.isoformat()
        metadata["period_status"] = (
            None if partial is None else "partial" if partial else "completed"
        )
        for observation in by_id[key]:
            observation.source_metadata = metadata
            observation.run.source_metadata = {
                "ingestion_mode": None if direct is None else "direct" if direct else "historical_import",
            }
    if len(rows) != len(by_id):
        raise ValueError("Missing canonical benchmark provenance")


def observation_dimensions(observation):
    """Render source coordinates from the retained typed observation facts."""
    source = observation.run.job.source_id
    dimensions = {}
    if observation.config_key is not None:
        dimensions["config"] = observation.config_key
    if observation.category_key is not None:
        dimensions["category"] = observation.category_key
    if source in {"openrouter", "opencode"} and observation.source_record_date:
        dimensions["date"] = observation.source_record_date.isoformat()
    return dimensions


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
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT ON (p.external_identifier,p.period_date) "
            "p.external_identifier,p.period_date,p.observation_id,p.run_id,"
            "p.updated_at,p.body_sha256,p.conflicting_revision "
            "FROM benchmark_endpoint_revisions p JOIN collection_runs r ON r.id=p.run_id "
            "JOIN collection_jobs j ON j.id=r.job_id "
            "WHERE j.contract_id=%s AND p.mapping_id=ANY(%s::uuid[]) "
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
