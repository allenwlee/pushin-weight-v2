-- OpenAI and Anthropic size report input for one backfill CollectionJob (plan U8, KTD11).
-- Read only: the transaction is opened read only and rolled back. Only SELECT runs.
-- Placeholders are filled only by scripts/backfill_size_report.py:
--   job_id             the test CollectionJob, validated as a canonical UUID
--   include_collection TRUE for the full report, FALSE for the spend watch (R24)
-- Scope rows are duplicated onto every CollectionRun of a resumed job, so scopes
-- are read from one run only: the job last success, else its latest completed run.
-- Requests, observations, staff relevance receipts and model requests belong to
-- their own runs and are read across every run of the job.
-- Output: one row with one text column, size_report_input, holding a JSON document.
BEGIN TRANSACTION READ ONLY;
WITH job AS (
    SELECT j.id, j.job_key, j.state, j.mode, j.purpose, j.instruction_version,
           j.last_success_id, j.last_attempt_id,
           j.definition -> 'scope' -> 'route_metadata' AS route_metadata
    FROM collection_jobs AS j
    WHERE j.id = '{{job_id}}'::uuid
),
runs AS (
    SELECT r.id, r.status, r.started_at, r.completed_at, r.continuation_of_id, r.report
    FROM collection_runs AS r
    JOIN job ON r.job_id = job.id
),
report_run AS (
    SELECT COALESCE(
        (SELECT job.last_success_id FROM job),
        (SELECT runs.id FROM runs
         WHERE runs.completed_at IS NOT NULL
         ORDER BY runs.completed_at DESC, runs.started_at DESC
         LIMIT 1)
    ) AS id
),
scopes AS (
    SELECT s.id, s.run_id, s.scope_kind, s.scope_key, s.outcome, s.execution_state,
           s.coverage_state, s.error_code, s.enumeration_complete, s.raw_count, s.envelopes
    FROM collection_scope_runs AS s
    WHERE {{include_collection}}
      AND s.run_id = (SELECT report_run.id FROM report_run)
),
kept_ids AS (
    SELECT DISTINCT pid.value AS post_id
    FROM scopes
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(scopes.envelopes) = 'array'
             THEN scopes.envelopes ELSE '[]'::jsonb END
    ) AS env(value)
    CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE WHEN jsonb_typeof(env.value -> 'post_ids') = 'array'
             THEN env.value -> 'post_ids' ELSE '[]'::jsonb END
    ) AS pid(value)
),
observed AS (
    SELECT DISTINCT o.post_id
    FROM collection_observations AS o
    JOIN runs ON o.run_id = runs.id
    WHERE {{include_collection}}
      AND o.post_id IS NOT NULL
),
tagged AS (
    SELECT pb.post_id, pb.brand_id
    FROM posts_brands AS pb
    WHERE {{include_collection}}
      AND pb.post_id IN (
          SELECT kept_ids.post_id FROM kept_ids
          UNION
          SELECT observed.post_id FROM observed
      )
),
requests AS (
    SELECT q.id, q.ordinal, q.request_category, q.transport_outcome, q.http_status,
           q.error_code, q.cursor_before, q.started_at, q.received_at, q.accounting_complete,
           sr.scope_key, sr.run_id AS scope_run_run_id, a.run_id AS attempt_run_id,
           attempt_run.report -> 'staging_responses' -> (q.id::text) AS receipt
    FROM collection_requests AS q
    JOIN collection_attempts AS a ON q.attempt_id = a.id
    JOIN runs AS attempt_run ON a.run_id = attempt_run.id
    JOIN collection_scope_runs AS sr ON q.scope_run_id = sr.id
    WHERE {{include_collection}}
),
model_requests AS (
    SELECT c.id, c.stage, c.state, c.model, c.member_post_ids,
           c.reserved_usd::text AS reserved_usd, c.actual_usd::text AS actual_usd,
           c.error_code, c.reserved_at, c.completed_at,
           c.provenance -> 'context' ->> 'operation' AS operation,
           c.provenance -> 'context' ->> 'role' AS role
    FROM original_content_calls AS c
    JOIN provider_batches AS b ON c.provider_batch_id = b.id
    JOIN job ON b.source_collection_job_id = job.id
)
SELECT jsonb_build_object(
    'format', 'oai-anthropic-size-input/v1',
    'database', current_database(),
    'generated_at', now(),
    'include_collection', {{include_collection}},
    'job', (SELECT to_jsonb(job) FROM job),
    'report_run_id', (SELECT report_run.id FROM report_run),
    'runs', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'id', runs.id,
            'status', runs.status,
            'started_at', runs.started_at,
            'completed_at', runs.completed_at,
            'continuation_of_id', runs.continuation_of_id,
            'staff_relevance', (
                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'identity', receipt.key,
                    'status', receipt.value ->> 'status'
                )), '[]'::jsonb)
                FROM jsonb_each(
                    CASE WHEN jsonb_typeof(runs.report -> 'staff_relevance') = 'object'
                         THEN runs.report -> 'staff_relevance' ELSE '{}'::jsonb END
                ) AS receipt
            ),
            'model_responses', (
                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'status', response.value ->> 'status',
                    'cost_usd', response.value -> 'usage' ->> 'cost_usd'
                )), '[]'::jsonb)
                FROM jsonb_array_elements(
                    CASE WHEN jsonb_typeof(runs.report -> 'model_responses') = 'array'
                         THEN runs.report -> 'model_responses' ELSE '[]'::jsonb END
                ) AS response
            )
        ) ORDER BY runs.started_at, runs.id), '[]'::jsonb)
        FROM runs
    ),
    'scopes', (
        SELECT COALESCE(jsonb_agg(to_jsonb(scopes) ORDER BY scopes.scope_key), '[]'::jsonb)
        FROM scopes
    ),
    'requests', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'id', requests.id,
            'ordinal', requests.ordinal,
            'request_category', requests.request_category,
            'transport_outcome', requests.transport_outcome,
            'http_status', requests.http_status,
            'error_code', requests.error_code,
            'cursor_before', requests.cursor_before,
            'started_at', requests.started_at,
            'received_at', requests.received_at,
            'accounting_complete', requests.accounting_complete,
            'scope_key', requests.scope_key,
            'scope_run_run_id', requests.scope_run_run_id,
            'attempt_run_id', requests.attempt_run_id,
            'receipt', CASE WHEN requests.receipt IS NULL THEN NULL ELSE jsonb_build_object(
                'raw_count', requests.receipt -> 'raw_count',
                'body_lost', requests.receipt -> 'body_lost',
                'has_body_hash', (requests.receipt ->> 'body_sha256') IS NOT NULL
            ) END
        ) ORDER BY requests.started_at, requests.id), '[]'::jsonb)
        FROM requests
    ),
    'calls', (
        SELECT COALESCE(jsonb_agg(to_jsonb(model_requests)
                                  ORDER BY model_requests.reserved_at, model_requests.id), '[]'::jsonb)
        FROM model_requests
    ),
    'observed_post_ids', (
        SELECT COALESCE(jsonb_agg(observed.post_id ORDER BY observed.post_id), '[]'::jsonb)
        FROM observed
    ),
    'post_brands', (
        SELECT COALESCE(jsonb_agg(jsonb_build_array(tagged.post_id, tagged.brand_id)
                                  ORDER BY tagged.post_id, tagged.brand_id), '[]'::jsonb)
        FROM tagged
    ),
    'brands', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'nickname', b.nickname,
            'is_sentinel', b.is_sentinel
        ) ORDER BY b.nickname), '[]'::jsonb)
        FROM brands AS b
    ),
    'table_sizes', (
        SELECT COALESCE(jsonb_object_agg(c.relname::text, pg_total_relation_size(c.oid)), '{}'::jsonb)
        FROM pg_class AS c
        JOIN pg_namespace AS n ON c.relnamespace = n.oid
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'm')
    ),
    'database_bytes', pg_database_size(current_database())
)::text AS size_report_input;
ROLLBACK;
