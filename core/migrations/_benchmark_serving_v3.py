"""Frozen benchmark projections using only typed collection facts.

Install at the RG6 reader cutover after the historical copy is verified. Keeping
this definition separate preserves the already-applied v1/v2 migrations.
"""

from psycopg import sql

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
        SELECT DISTINCT o.run_id, o.published_date AS publication_date
        FROM collection_observations o
        JOIN collection_runs r ON r.id=o.run_id
        JOIN collection_jobs j ON j.id=r.job_id
        WHERE j.purpose='metric' AND j.source_id='arena'
            AND r.status IN ('success','partial')
            AND o.observation_kind='publication_marker'
            AND o.publication_complete=true
    """,
    "benchmark_endpoint_revisions": """
        SELECT marker.run_id, referenced.mapping_id,
            mapping.external_identifier, referenced.source_record_date AS period_date,
            referenced.id AS observation_id, marker.source_record_at AS updated_at,
            CASE WHEN marker.payload_sha256 ~ '^[0-9a-f]{64}$'
                THEN marker.payload_sha256::text END AS body_sha256,
            marker.revision_conflict AS conflicting_revision
        FROM collection_observations marker
        JOIN collection_observation_inputs input
            ON input.observation_id=marker.id
            AND input.input_role='endpoint_revision_row'
        JOIN collection_observations referenced
            ON referenced.id=input.input_observation_id
        JOIN source_subject_mappings mapping ON mapping.id=referenced.mapping_id
        JOIN collection_runs r ON r.id=marker.run_id
        JOIN collection_jobs j ON j.id=r.job_id
        JOIN collection_runs referenced_run ON referenced_run.id=referenced.run_id
        JOIN collection_jobs referenced_job ON referenced_job.id=referenced_run.job_id
        WHERE j.purpose='metric' AND j.source_id='opencode'
            AND r.status IN ('success','partial')
            AND marker.observation_kind='endpoint_check' AND marker.status='ok'
            AND mapping.source_id='opencode' AND mapping.purpose='metric'
            AND mapping.contract_id=j.contract_id
            AND marker.mapping_id=mapping.id
            AND marker.source_identifier=mapping.external_identifier
            AND referenced.source_identifier=mapping.external_identifier
            AND referenced.status='ok'
            AND referenced_job.source_id='opencode' AND referenced_job.purpose='metric'
            AND referenced_job.contract_id=j.contract_id
            AND referenced_run.status IN ('success','partial')
            AND input.row_locator=referenced.source_record_date::text
    """,
}


def install(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'")
        for name, query in VIEWS.items():
            cursor.execute(f"CREATE OR REPLACE VIEW {name} WITH (security_barrier=true) AS {query}")


def validate_view(cursor, schema, name):
    """Require the exact reviewed scalar projection before granting access."""
    cursor.execute("CREATE TEMP VIEW pw_expected_benchmark_projection AS " + VIEWS[name])
    try:
        cursor.execute(
            "SELECT pg_get_viewdef(%s::regclass)=pg_get_viewdef('pg_temp.pw_expected_benchmark_projection'::regclass) "
            "AND 'security_barrier=true'=ANY(reloptions) FROM pg_class WHERE oid=%s::regclass",
            [f"{schema}.{name}", f"{schema}.{name}"],
        )
        if cursor.fetchone() != (True,):
            raise ValueError("Unreviewed benchmark serving projection: " + name)
    finally:
        cursor.execute(sql.SQL("DROP VIEW pg_temp.{}").format(sql.Identifier("pw_expected_benchmark_projection")))
