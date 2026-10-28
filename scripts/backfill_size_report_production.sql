-- Production comparison for the OpenAI and Anthropic size report (plan U8, R19, R21).
-- Read only: the transaction is opened read only and rolled back. Only SELECT runs.
-- Placeholders are filled only by scripts/backfill_size_report.py with validated
-- integer Unix epochs:
--   window_start_epoch, window_end_epoch  the test window, 12:00 to 18:00 US Pacific
--   day_start_epoch, day_end_epoch        the US Pacific calendar day holding the window
-- Posts are counted by the search that first saved them (posts.source_query_id),
-- so the report can leave out RARE_EXTRA and the special-events searches.
-- Output: one row with one text column, size_report_production, holding a JSON document.
BEGIN TRANSACTION READ ONLY;
WITH bounds AS (
    SELECT to_timestamp({{window_start_epoch}}) AS window_start,
           to_timestamp({{window_end_epoch}}) AS window_end,
           to_timestamp({{day_start_epoch}}) AS day_start,
           to_timestamp({{day_end_epoch}}) AS day_end
),
saved AS (
    SELECT COALESCE(p.source_query_id, '') AS source_query_id,
           count(*) AS day_count,
           count(*) FILTER (
               WHERE p.created_at >= bounds.window_start AND p.created_at < bounds.window_end
           ) AS window_count
    FROM posts AS p
    CROSS JOIN bounds
    WHERE p.created_at >= bounds.day_start AND p.created_at < bounds.day_end
    GROUP BY COALESCE(p.source_query_id, '')
)
SELECT jsonb_build_object(
    'format', 'oai-anthropic-size-production/v1',
    'database', current_database(),
    'generated_at', now(),
    'window_start_epoch', {{window_start_epoch}},
    'window_end_epoch', {{window_end_epoch}},
    'day_start_epoch', {{day_start_epoch}},
    'day_end_epoch', {{day_end_epoch}},
    'window_posts', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'source_query_id', saved.source_query_id,
            'posts', saved.window_count
        ) ORDER BY saved.source_query_id), '[]'::jsonb)
        FROM saved
        WHERE saved.window_count > 0
    ),
    'day_posts', (
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
            'source_query_id', saved.source_query_id,
            'posts', saved.day_count
        ) ORDER BY saved.source_query_id), '[]'::jsonb)
        FROM saved
    )
)::text AS size_report_production;
ROLLBACK;
