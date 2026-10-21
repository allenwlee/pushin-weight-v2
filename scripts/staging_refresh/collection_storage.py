"""Scrub disposable execution while retaining the numeric evidence graph."""

from psycopg import sql

OWNED_TABLES = (
    "collection_jobs",
    "collection_runs",
    "collection_scope_runs",
    "collection_job_targets",
    "collection_attempts",
    "collection_requests",
    "collection_observations",
    "collection_observation_inputs",
    "collection_resource_snapshots",
    "collection_metric_gaps",
    "collection_corrections",
)


def purge_relational_collection_runtime(cursor, purpose):
    # These tables exist only in the transaction operating on the non-serving
    # shadow. No temporary state or cleanup runs against production.
    cursor.execute("DROP TABLE IF EXISTS pg_temp.pw_refresh_kept_runs")
    cursor.execute(
        "CREATE TEMP TABLE pw_refresh_kept_runs(id uuid PRIMARY KEY) ON COMMIT DROP"
    )
    cursor.execute(
        f"INSERT INTO pw_refresh_kept_runs SELECT r.id FROM collection_runs r WHERE {purpose}='metric'"
    )
    cursor.execute("""
        INSERT INTO pw_refresh_kept_runs
        SELECT o.run_id FROM collection_observations o WHERE o.id IN (
            SELECT evidence_observation_id FROM collection_job_targets
            UNION SELECT observation_id FROM collection_corrections
        ) ON CONFLICT DO NOTHING
    """)
    # Other owners, including dossier attachments, can refer to observations or
    # runs. Keep their evidence automatically; never delete through those FKs.
    cursor.execute(
        """
        SELECT t.relname,a.attname,d.relname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_class d ON d.oid=c.confrelid
        JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=c.conkey[1]
        WHERE c.contype='f' AND n.nspname='public' AND cardinality(c.conkey)=1
          AND d.relname IN ('collection_runs','collection_observations')
          AND NOT(t.relname=ANY(%s))
    """,
        [list(OWNED_TABLES)],
    )
    references = cursor.fetchall()
    for table, column, destination in references:
        if destination == "collection_runs":
            query = sql.SQL(
                "INSERT INTO pw_refresh_kept_runs SELECT {} FROM {} WHERE {} IS NOT NULL ON CONFLICT DO NOTHING"
            ).format(
                sql.Identifier(column), sql.Identifier(table), sql.Identifier(column)
            )
        else:
            query = sql.SQL(
                "INSERT INTO pw_refresh_kept_runs SELECT o.run_id FROM collection_observations o JOIN {} t ON t.{}=o.id ON CONFLICT DO NOTHING"
            ).format(sql.Identifier(table), sql.Identifier(column))
        cursor.execute(query)
    while True:
        cursor.execute("""
            INSERT INTO pw_refresh_kept_runs
            SELECT referenced FROM (
                SELECT r.continuation_of_id AS referenced FROM collection_runs r JOIN pw_refresh_kept_runs k ON k.id=r.id
                UNION SELECT prior.run_id FROM collection_observation_inputs i
                    JOIN collection_observations o ON o.id=i.observation_id
                    JOIN pw_refresh_kept_runs k ON k.id=o.run_id
                    JOIN collection_observations prior ON prior.id=i.input_observation_id
                UNION SELECT prior.run_id FROM collection_observations o
                    JOIN pw_refresh_kept_runs k ON k.id=o.run_id
                    JOIN collection_observations prior ON prior.id=o.supersedes_observation_id
                UNION SELECT prior.run_id FROM collection_scope_runs s
                    JOIN pw_refresh_kept_runs k ON k.id=s.run_id
                    JOIN collection_observations prior ON prior.id=s.resource_observation_id
                UNION SELECT prior.run_id FROM collection_scope_runs s
                    JOIN pw_refresh_kept_runs k ON k.id=s.run_id
                    JOIN collection_scope_runs prior ON prior.id IN(s.parent_scope_id,s.prerequisite_scope_id)
                UNION SELECT prior.run_id FROM collection_resource_snapshots s
                    JOIN collection_observations o ON o.id=s.observation_id
                    JOIN pw_refresh_kept_runs k ON k.id=o.run_id
                    JOIN collection_observations prior ON prior.id=s.prior_snapshot_id
            ) refs WHERE referenced IS NOT NULL ON CONFLICT DO NOTHING
        """)
        if cursor.rowcount == 0:
            break
    cursor.execute(f"""
        UPDATE collection_jobs SET
            state=CASE WHEN operation IN ('archived_run','legacy_direct') THEN 'completed' ELSE 'paused' END,
            authority_enabled=false, active_run_id=NULL, next_due_at=NULL,next_retry_at=NULL,
            last_attempt_id=CASE WHEN last_attempt_id IN(SELECT r.id FROM collection_runs r WHERE {purpose}='metric') THEN last_attempt_id ELSE NULL END,
            last_success_id=CASE WHEN last_success_id IN(SELECT r.id FROM collection_runs r WHERE {purpose}='metric') THEN last_success_id ELSE NULL END
    """)
    # Pending intents in a copied database have no observable source outcome.
    cursor.execute(
        "UPDATE collection_requests SET transport_outcome='unknown',error_code='shadow_refresh' WHERE transport_outcome='pending'"
    )
    cursor.execute(
        "UPDATE collection_attempts SET outcome='interrupted',stop_reason='shadow_refresh',lease_expires_at=NULL WHERE outcome='running'"
    )
    for table, owner in (
        ("collection_observation_inputs", "observation_id"),
        ("collection_metric_gaps", "observation_id"),
        ("collection_resource_snapshots", "observation_id"),
    ):
        cursor.execute(
            sql.SQL(
                "DELETE FROM {} WHERE {} IN(SELECT id FROM collection_observations WHERE run_id NOT IN(SELECT id FROM pw_refresh_kept_runs))"
            ).format(sql.Identifier(table), sql.Identifier(owner))
        )
    cursor.execute(
        "DELETE FROM collection_requests WHERE attempt_id IN(SELECT id FROM collection_attempts WHERE run_id NOT IN(SELECT id FROM pw_refresh_kept_runs))"
    )
    for table in (
        "collection_attempts",
        "collection_observations",
        "collection_scope_runs",
    ):
        cursor.execute(
            sql.SQL(
                "DELETE FROM {} WHERE run_id NOT IN(SELECT id FROM pw_refresh_kept_runs)"
            ).format(sql.Identifier(table))
        )
    cursor.execute(
        "DELETE FROM collection_runs WHERE id NOT IN(SELECT id FROM pw_refresh_kept_runs)"
    )
    # Retained unfinished evidence is cancelled in the shadow, never published
    # as a successful source collection. Observation/value clocks stay intact.
    cursor.execute(f"""
        UPDATE collection_runs r SET status='aborted',completed_at=CURRENT_TIMESTAMP,
            execution_state='aborted',coverage_state='partial',lease_expires_at=NULL
        WHERE {purpose} IN('catalog','content') AND status IN('pending','running','partial','interrupted')
    """)
