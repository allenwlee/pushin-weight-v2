"""Frozen scalar projections; no document, stored copy, or write privilege."""


def iso_date(expression):
    return (
        f"CASE WHEN {expression} ~ '^\u005cd{{4}}-\u005cd{{2}}-\u005cd{{2}}$' "
        f"AND pg_input_is_valid({expression}, 'date') THEN ({expression})::date END"
    )


VIEWS = {
    "benchmark_observation_provenance": f"""
        SELECT o.id,
            o.source_metadata->>'history_basis' = 'reconstructed_current_relationships'
                AS reconstructed,
            o.source_metadata->'secondary_source' = 'true'::jsonb AS secondary_source,
            {iso_date("o.source_metadata->>'archive_snapshot_date'")} AS archive_snapshot_date,
            {iso_date("o.source_metadata->>'reconstruction_date'")} AS reconstruction_date,
            o.source_metadata->'publication_complete' = 'true'::jsonb AS publication_complete,
            o.source_metadata->>'period_status' = 'partial' AS partial,
            r.source_metadata->>'ingestion_mode' = 'direct' AS direct
        FROM collection_observations o
        JOIN collection_runs r ON r.id=o.run_id
        JOIN collection_jobs j ON j.id=r.job_id
        WHERE j.purpose='metric'
    """,
    "benchmark_publication_dates": f"""
        SELECT r.id AS run_id, {iso_date('d.value')} AS publication_date
        FROM collection_runs r
        JOIN collection_jobs j ON j.id=r.job_id
        CROSS JOIN LATERAL jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(r.source_metadata->'publication_dates')='array'
                THEN r.source_metadata->'publication_dates' ELSE '[]'::jsonb END
        ) d(value)
        WHERE j.purpose='metric' AND j.source_id='arena'
            AND r.status IN ('success','partial')
    """,
    "benchmark_endpoint_revisions": f"""
        SELECT r.id AS run_id, m.id AS mapping_id, m.external_identifier,
            {iso_date('ref.key')} AS period_date,
            CASE WHEN ref.value ~ '^[0-9]+$' AND pg_input_is_valid(ref.value,'bigint')
                THEN ref.value::bigint END AS observation_id,
            CASE WHEN pg_input_is_valid(c.value->>'updated_at','timestamptz')
                THEN (c.value->>'updated_at')::timestamptz END AS updated_at,
            CASE WHEN c.value->>'body_sha256' ~ '^[0-9a-f]{{64}}$'
                THEN c.value->>'body_sha256' END AS body_sha256,
            c.value->>'revision_anomaly'='same_update_different_body' AS conflicting_revision
        FROM collection_runs r
        JOIN collection_jobs j ON j.id=r.job_id
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(r.source_metadata->'endpoint_checks')='array'
                THEN r.source_metadata->'endpoint_checks' ELSE '[]'::jsonb END
        ) c(value)
        CROSS JOIN LATERAL jsonb_each_text(
            CASE WHEN jsonb_typeof(c.value->'row_references')='object'
                THEN c.value->'row_references' ELSE '{{}}'::jsonb END
        ) ref
        JOIN source_subject_mappings m ON m.external_identifier=c.value->>'source_identifier'
            AND m.source_id='opencode' AND m.contract_id=j.contract_id AND m.purpose='metric'
        WHERE j.purpose='metric' AND j.source_id='opencode'
            AND r.status IN ('success','partial') AND c.value->>'status'='ok'
    """,
}


def install(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'")
        for name, query in VIEWS.items():
            cursor.execute(f"CREATE VIEW {name} WITH (security_barrier=true) AS {query}")


def validate_view(cursor, schema, name):
    """Grant only the exact reviewed query, never a same-named raw-data view."""
    from psycopg import sql

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
