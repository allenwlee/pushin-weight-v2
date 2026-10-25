"""Frozen typed benchmark projections for the later RG6 view cutover.

This module is intentionally not installed by the additive RG6 migrations.
Install it only after the historical marker and provenance copies are verified.
"""

VIEWS = {
    "benchmark_observation_provenance": """
        SELECT o.id,
            o.history_reconstructed AS reconstructed,
            o.secondary_source,
            o.archive_snapshot_date,
            o.reconstruction_date,
            o.publication_complete,
            o.period_status = 'partial' AS partial,
            r.direct_ingestion AS direct
        FROM collection_observations o
        JOIN collection_runs r ON r.id=o.run_id
        JOIN collection_jobs j ON j.id=r.job_id
        WHERE j.purpose='metric'
    """,
    "benchmark_publication_dates": """
        SELECT o.run_id, o.published_date AS publication_date
        FROM collection_observations o
        JOIN collection_runs r ON r.id=o.run_id
        JOIN collection_jobs j ON j.id=r.job_id
        WHERE j.purpose='metric' AND j.source_id='arena'
            AND r.status IN ('success','partial')
            AND o.observation_kind='publication_marker'
            AND o.source_subject_kind='aggregate'
            AND o.status='ok' AND o.publication_complete IS TRUE
            AND o.published_date IS NOT NULL
    """,
    "benchmark_endpoint_revisions": """
        SELECT marker.run_id, marker.mapping_id, m.external_identifier,
            row.source_record_date AS period_date, row.id AS observation_id,
            marker.source_record_at AS updated_at,
            marker.payload_sha256 AS body_sha256,
            marker.revision_conflict AS conflicting_revision
        FROM collection_observations marker
        JOIN collection_runs r ON r.id=marker.run_id
        JOIN collection_jobs j ON j.id=r.job_id
        JOIN source_subject_mappings m ON m.id=marker.mapping_id
            AND m.contract_id=j.contract_id AND m.source_id='opencode'
            AND m.purpose='metric'
        JOIN collection_observation_inputs link
            ON link.observation_id=marker.id
            AND link.input_role='endpoint_revision_row'
        JOIN collection_observations row ON row.id=link.input_observation_id
            AND row.mapping_id=marker.mapping_id
            AND row.source_identifier=marker.source_identifier
            AND link.row_locator=row.source_record_date::text
        JOIN collection_runs row_run ON row_run.id=row.run_id
        JOIN collection_jobs row_job ON row_job.id=row_run.job_id
            AND row_job.contract_id=j.contract_id
            AND row_job.source_id='opencode' AND row_job.purpose='metric'
        WHERE j.purpose='metric' AND j.source_id='opencode'
            AND r.status IN ('success','partial')
            AND marker.observation_kind='endpoint_check'
            AND marker.status='ok' AND row.status='ok'
    """,
}
