BEGIN TRANSACTION READ ONLY;
-- OpenAI and Anthropic size test preflight input from xbackfiller (plan U7).
-- Read only: the transaction is opened read only and rolled back. Only SELECT runs.
-- The placeholder is filled only by scripts/backfill_size_preflight.py:
--   july_job_id  the paused July CollectionJob, validated as a canonical UUID
-- The three Twitter list IDs are the main list and the OpenAI and Anthropic lab
-- lists (config.yaml x_monitor_list_id and scripts/backfill_size_seed.py LAB_LISTS).
-- Output: one row with one text column, preflight_input, holding a JSON document.
WITH july AS (
    SELECT j.id, j.job_key, j.state, j.mode, j.source_id, j.definition_sha256,
           j.active_run_id, j.last_attempt_id, j.last_success_id, j.next_due_at, j.updated_at,
           (SELECT count(*)
            FROM jsonb_object_keys(
                CASE WHEN jsonb_typeof(j.definition -> 'scope' -> 'author_scope' -> 'contexts') = 'object'
                     THEN j.definition -> 'scope' -> 'author_scope' -> 'contexts' ELSE '{}'::jsonb END
            ) AS context_author) AS author_contexts
    FROM collection_jobs AS j
    WHERE j.id = '{{july_job_id}}'::uuid
),
july_runs AS (
    SELECT r.id, r.status
    FROM collection_runs AS r
    JOIN july ON r.job_id = july.id
),
running AS (
    SELECT r.id AS run_id, j.id AS job_id, j.job_key, j.state AS job_state,
           r.started_at, r.lease_expires_at, r.updated_at
    FROM collection_runs AS r
    JOIN collection_jobs AS j ON r.job_id = j.id
    WHERE j.source_id = 'x' AND j.mode = 'historical' AND r.status = 'running'
),
ready_jobs AS (
    SELECT j.id, j.job_key, j.next_due_at, j.updated_at
    FROM collection_jobs AS j
    WHERE j.source_id = 'x' AND j.mode = 'historical' AND j.state = 'ready'
)
SELECT jsonb_build_object(
    'format', 'oai-anthropic-size-preflight/v1',
    'database', current_database(),
    'session_user', session_user,
    'current_user', current_user,
    'transaction_read_only', current_setting('transaction_read_only'),
    'generated_at', now(),
    'july', jsonb_build_object(
        'job', (SELECT to_jsonb(july) FROM july),
        'run_count', (SELECT count(*) FROM july_runs),
        'runs_by_status', (
            SELECT COALESCE(jsonb_object_agg(counted.status, counted.runs), '{}'::jsonb)
            FROM (SELECT july_runs.status, count(*) AS runs FROM july_runs GROUP BY july_runs.status) AS counted
        ),
        'scope_rows', (
            SELECT count(*)
            FROM collection_scope_runs AS s
            JOIN july_runs ON s.run_id = july_runs.id
        )
    ),
    'running_historical_runs', (
        SELECT COALESCE(jsonb_agg(to_jsonb(running) ORDER BY running.started_at, running.run_id), '[]'::jsonb)
        FROM running
    ),
    'ready_historical_jobs', (
        SELECT COALESCE(jsonb_agg(to_jsonb(ready_jobs) ORDER BY ready_jobs.job_key), '[]'::jsonb)
        FROM ready_jobs
    ),
    'advisory_locks', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'pid', l.pid, 'classid', l.classid, 'objid', l.objid, 'objsubid', l.objsubid,
            'granted', l.granted, 'mode', l.mode
        ) ORDER BY l.pid, l.classid, l.objid), '[]'::jsonb)
        FROM pg_locks AS l
        WHERE l.locktype = 'advisory' AND l.pid IS DISTINCT FROM pg_backend_pid()
    ),
    'brands', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'nickname', b.nickname, 'is_sentinel', b.is_sentinel
        ) ORDER BY b.nickname), '[]'::jsonb)
        FROM brands AS b
        WHERE b.nickname IN ('openai', 'anthropic')
    ),
    'brand_keywords', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'brand', k.brand_id, 'pattern', k.pattern, 'is_regex', k.is_regex
        ) ORDER BY k.brand_id, k.pattern), '[]'::jsonb)
        FROM brand_keywords AS k
        WHERE k.brand_id IN ('openai', 'anthropic')
    ),
    'list_memberships', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'list_id', m.list_id::text, 'author_id', a.author_id
        ) ORDER BY m.list_id, a.author_id), '[]'::jsonb)
        FROM twitter_list_memberships AS m
        JOIN accounts AS a ON m.account_key = a.account_key
        WHERE m.active
          AND m.list_id IN (2067062923525275922, 2067500935769895374, 2067501173402460553)
    ),
    'table_sizes', (
        SELECT COALESCE(jsonb_object_agg(c.relname::text, pg_total_relation_size(c.oid)), '{}'::jsonb)
        FROM pg_class AS c
        JOIN pg_namespace AS n ON c.relnamespace = n.oid
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'm')
    ),
    'database_bytes', pg_database_size(current_database())
)::text AS preflight_input;
ROLLBACK;
