BEGIN READ ONLY; SET LOCAL statement_timeout='20s';
SELECT json_build_object('observed_at',statement_timestamp(),'fetched_before','2026-09-29T06:19:29.636718+00:00',
 'entity_value_types',(SELECT json_agg(x ORDER BY value_type) FROM (
 SELECT CASE WHEN entities IS NULL THEN 'SQL NULL' ELSE coalesce(jsonb_typeof(entities),'unknown') END AS value_type,count(*) AS posts
 FROM posts WHERE fetched_at<'2026-09-29T06:19:29.636718+00:00'
 GROUP BY 1)x)); COMMIT;
