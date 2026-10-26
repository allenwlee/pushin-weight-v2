"""Transitional typed benchmark views while the old JSON is copied."""

from psycopg import sql

from ._benchmark_serving_v1 import VIEWS as OLD_VIEWS

VIEWS = {
    "benchmark_observation_provenance": """
        SELECT o.id,
            COALESCE(o.history_reconstructed,
                o.source_metadata->>'history_basis' = 'reconstructed_current_relationships') AS reconstructed,
            COALESCE(o.secondary_source,
                o.source_metadata->'secondary_source' = 'true'::jsonb) AS secondary_source,
            COALESCE(o.archive_snapshot_date,
                CASE WHEN o.source_metadata->>'archive_snapshot_date' ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    AND pg_input_is_valid(o.source_metadata->>'archive_snapshot_date','date')
                    THEN (o.source_metadata->>'archive_snapshot_date')::date END) AS archive_snapshot_date,
            COALESCE(o.reconstruction_date,
                CASE WHEN o.source_metadata->>'reconstruction_date' ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    AND pg_input_is_valid(o.source_metadata->>'reconstruction_date','date')
                    THEN (o.source_metadata->>'reconstruction_date')::date END) AS reconstruction_date,
            COALESCE(o.publication_complete,
                o.source_metadata->'publication_complete' = 'true'::jsonb) AS publication_complete,
            COALESCE(o.period_status = 'partial',
                o.source_metadata->>'period_status' = 'partial') AS partial,
            COALESCE(r.direct_ingestion,
                r.source_metadata->>'ingestion_mode' = 'direct') AS direct
        FROM collection_observations o
        JOIN collection_runs r ON r.id=o.run_id
        JOIN collection_jobs j ON j.id=r.job_id
        WHERE j.purpose='metric'
    """,
    "benchmark_publication_dates": f"""
        SELECT o.run_id, o.published_date AS publication_date
        FROM collection_observations o
        JOIN collection_runs r ON r.id=o.run_id
        JOIN collection_jobs j ON j.id=r.job_id
        WHERE j.purpose='metric' AND j.source_id='arena'
            AND r.status IN ('success','partial')
            AND o.observation_kind='publication_marker'
            AND o.publication_complete=true
        UNION
        {OLD_VIEWS['benchmark_publication_dates']}
    """,
    "benchmark_endpoint_revisions": f"""
        WITH typed AS (
            SELECT marker.run_id, referenced.mapping_id,
                mapping.external_identifier, referenced.source_record_date AS period_date,
                referenced.id AS observation_id, marker.source_record_at AS updated_at,
                marker.payload_sha256::text AS body_sha256,
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
            WHERE j.purpose='metric' AND j.source_id='opencode'
                AND r.status IN ('success','partial')
                AND marker.observation_kind='endpoint_check'
        )
        SELECT * FROM typed
        UNION ALL
        SELECT old.* FROM ({OLD_VIEWS['benchmark_endpoint_revisions']}) old
        WHERE NOT EXISTS (
            SELECT 1 FROM typed WHERE typed.run_id=old.run_id
                AND typed.mapping_id=old.mapping_id
                AND typed.period_date=old.period_date
        )
    """,
}


def install(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'")
        for name, query in VIEWS.items():
            cursor.execute(f"CREATE OR REPLACE VIEW {name} WITH (security_barrier=true) AS {query}")


def validate_view(cursor, schema, name):
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
