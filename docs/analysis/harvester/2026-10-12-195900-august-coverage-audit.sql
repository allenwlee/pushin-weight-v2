BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '45s';
SET LOCAL lock_timeout = '2s';
SET LOCAL TIME ZONE 'UTC';
WITH
zones(zone) AS (VALUES ('UTC'::text), ('Asia/Tokyo'::text)),
posted AS MATERIALIZED (
  SELECT tweet_id, created_at, fetched_at, source_query_id,
         text_en IS NOT NULL AND text_en <> '' AS has_en,
         text_zh_cn IS NOT NULL AND text_zh_cn <> '' AS has_zh,
         EXISTS (SELECT 1 FROM posts_brands pb WHERE pb.post_id = p.tweet_id) AS attributed
  FROM posts p
  WHERE created_at >= '2026-07-24T15:00:00Z'::timestamptz
    AND created_at < '2026-09-08T00:00:00Z'::timestamptz
),
days AS (
  SELECT z.zone, d::date AS day
  FROM zones z CROSS JOIN generate_series('2026-07-25'::timestamp,
       '2026-09-07'::timestamp, '1 day') d
),
daily_counts AS (
  SELECT z.zone, (p.created_at AT TIME ZONE z.zone)::date AS day,
         count(*) AS posts,
         count(*) FILTER (WHERE attributed) AS attributed_posts,
         count(*) FILTER (WHERE has_en) AS translated_en,
         count(*) FILTER (WHERE has_zh) AS translated_zh,
         count(*) FILTER (WHERE fetched_at <= created_at + interval '24 hours') AS inserted_within_24h,
         count(*) FILTER (WHERE fetched_at > created_at + interval '24 hours') AS inserted_after_24h,
         count(DISTINCT date_trunc('hour', created_at AT TIME ZONE z.zone)) AS populated_hours
  FROM posted p CROSS JOIN zones z GROUP BY 1, 2
),
daily AS (
  SELECT d.zone, d.day, coalesce(c.posts,0) AS posts,
         coalesce(c.attributed_posts,0) AS attributed_posts,
         coalesce(c.translated_en,0) AS translated_en,
         coalesce(c.translated_zh,0) AS translated_zh,
         coalesce(c.inserted_within_24h,0) AS inserted_within_24h,
         coalesce(c.inserted_after_24h,0) AS inserted_after_24h,
         coalesce(c.populated_hours,0) AS populated_hours
  FROM days d LEFT JOIN daily_counts c USING (zone,day)
),
hour_counts AS (
  SELECT z.zone, date_trunc('hour', created_at AT TIME ZONE z.zone) AS hour,
         count(*) AS posts, count(*) FILTER (WHERE attributed) AS attributed_posts
  FROM posted p CROSS JOIN zones z GROUP BY 1, 2
),
hours AS (
  SELECT z.zone, h AS hour, coalesce(c.posts,0) AS posts,
         coalesce(c.attributed_posts,0) AS attributed_posts
  FROM zones z CROSS JOIN generate_series('2026-08-01'::timestamp,
       '2026-08-31T23:00:00'::timestamp, '1 hour') h
  LEFT JOIN hour_counts c ON c.zone=z.zone AND c.hour=h
),
ingested AS MATERIALIZED (
  SELECT tweet_id, fetched_at, created_at, source_query_id
  FROM posts
  WHERE fetched_at >= '2026-07-25T00:00:00Z'::timestamptz
    AND fetched_at < '2026-09-08T00:00:00Z'::timestamptz
),
ingest_hours AS (
  SELECT date_trunc('hour', fetched_at) AS hour, count(*) AS posts,
         count(*) FILTER (WHERE created_at < fetched_at - interval '24 hours') AS historical_posts
  FROM ingested GROUP BY 1
),
ingest_gaps AS (
  SELECT lag(fetched_at) OVER (ORDER BY fetched_at) AS previous_insert,
         fetched_at AS next_insert
  FROM (SELECT DISTINCT fetched_at FROM ingested) i
),
creation_gaps AS (
  SELECT lag(created_at) OVER (ORDER BY created_at) AS previous_post,
         created_at AS next_post
  FROM (SELECT DISTINCT created_at FROM posted) p
),
brand_daily AS (
  SELECT z.zone, (p.created_at AT TIME ZONE z.zone)::date AS day, pb.brand_id,
         count(*) AS posts
  FROM posted p JOIN posts_brands pb ON pb.post_id=p.tweet_id CROSS JOIN zones z
  WHERE (p.created_at AT TIME ZONE z.zone)::date BETWEEN '2026-08-01' AND '2026-08-31'
  GROUP BY 1,2,3
),
source_daily AS (
  SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
         coalesce(source_query_id,'(null)') AS source_query_id, count(*) AS posts
  FROM posted WHERE created_at >= '2026-08-01T00:00:00Z' AND created_at < '2026-09-01T00:00:00Z'
  GROUP BY 1,2
)
SELECT jsonb_build_object(
  'metadata', jsonb_build_object('snapshot_at',now(),'database',current_database(),
      'transaction_read_only',current_setting('transaction_read_only'),
      'year',2026,'month',8,'code_review_sha','f43b2904',
      'null_created_at_total',(SELECT count(*) FROM posts WHERE created_at IS NULL)),
  'daily',(SELECT jsonb_agg(to_jsonb(d) ORDER BY zone,day) FROM daily d),
  'hourly',(SELECT jsonb_agg(to_jsonb(h) ORDER BY zone,hour) FROM hours h),
  'ingest_hourly_utc',(SELECT jsonb_agg(to_jsonb(i) ORDER BY hour) FROM ingest_hours i),
  'ingest_gaps_utc',(SELECT coalesce(jsonb_agg(to_jsonb(g) ORDER BY previous_insert),'[]'::jsonb)
    FROM (SELECT previous_insert,next_insert,extract(epoch FROM next_insert-previous_insert)/3600 AS hours
      FROM ingest_gaps WHERE next_insert-previous_insert >= interval '1 hour'
        AND previous_insert < '2026-09-01T00:00:00Z' AND next_insert > '2026-08-01T00:00:00Z') g),
  'creation_gaps_utc',(SELECT coalesce(jsonb_agg(to_jsonb(g) ORDER BY previous_post),'[]'::jsonb)
    FROM (SELECT previous_post,next_post,extract(epoch FROM next_post-previous_post)/3600 AS hours
      FROM creation_gaps WHERE next_post-previous_post >= interval '1 hour'
        AND previous_post < '2026-09-01T00:00:00Z' AND next_post > '2026-08-01T00:00:00Z') g),
  'brand_daily',(SELECT jsonb_agg(to_jsonb(b) ORDER BY zone,day,brand_id) FROM brand_daily b),
  'source_daily_utc',(SELECT jsonb_agg(to_jsonb(s) ORDER BY day,source_query_id) FROM source_daily s),
  'backlog_august',(SELECT coalesce(jsonb_agg(to_jsonb(b) ORDER BY original_since,call_id),'[]'::jsonb)
    FROM (SELECT id,brand_id,call_id,state,reason_code,original_since,original_until,
        remaining_since,remaining_until,attempts,first_seen_at,last_seen_at,quarantine_reason
      FROM harvest_backlog_windows WHERE original_since < '2026-09-01T00:00:00Z'
        AND original_until > '2026-08-01T00:00:00Z') b)
);
COMMIT;
