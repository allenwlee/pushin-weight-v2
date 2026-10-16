BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='30s'; SET LOCAL lock_timeout='2s'; SET LOCAL TIME ZONE 'UTC';
WITH gaps(id,since,until) AS (VALUES (1,'2026-08-01T07:45:46.366015+00:00'::timestamptz,'2026-08-02T03:45:56.979881+00:00'::timestamptz),(2,'2026-08-03T04:54:19.260817+00:00'::timestamptz,'2026-08-04T04:30:27.259565+00:00'::timestamptz),(3,'2026-08-05T16:24:04.665832+00:00'::timestamptz,'2026-08-06T07:01:19.711208+00:00'::timestamptz),(4,'2026-08-06T07:02:58.405921+00:00'::timestamptz,'2026-08-06T08:45:40.479781+00:00'::timestamptz),(5,'2026-08-06T08:45:46.642507+00:00'::timestamptz,'2026-08-06T12:01:19.648366+00:00'::timestamptz),(6,'2026-08-08T04:30:53.913717+00:00'::timestamptz,'2026-08-10T05:15:19.499647+00:00'::timestamptz),(7,'2026-08-13T05:45:55.328254+00:00'::timestamptz,'2026-08-13T07:00:52.166804+00:00'::timestamptz),(8,'2026-08-16T02:30:50.559251+00:00'::timestamptz,'2026-08-17T06:01:32.073302+00:00'::timestamptz),(9,'2026-08-27T03:31:06.744532+00:00'::timestamptz,'2026-08-27T06:00:57.379203+00:00'::timestamptz)), counts AS (
SELECT g.id,g.since,g.until,extract(epoch FROM g.until-g.since)/3600 AS gap_hours,
count(p.tweet_id) AS stored_posts_created_inside_gap,
count(p.tweet_id) FILTER (WHERE p.fetched_at >= g.until) AS inserted_after_gap,
count(p.tweet_id) FILTER (WHERE p.fetched_at >= g.until AND p.fetched_at < g.until+interval '48 hours') AS inserted_first_48h_after_gap,
(SELECT count(DISTINCT b.brand_id) FROM posts q JOIN posts_brands b ON b.post_id=q.tweet_id WHERE q.created_at>=g.since AND q.created_at<g.until) AS brands_present
FROM gaps g LEFT JOIN posts p ON p.created_at>=g.since AND p.created_at<g.until
GROUP BY g.id,g.since,g.until)
SELECT jsonb_build_object('snapshot_at',now(),'transaction_read_only',current_setting('transaction_read_only'),'gap_counts',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM counts c)); COMMIT;
