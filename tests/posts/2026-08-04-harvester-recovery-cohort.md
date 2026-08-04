---
title: Harvester recovery cohort — post-402-credit-topup ingest
generated_at_jst: 2026-08-04-13:48:00
generated_at_utc: 2026-08-04 04:47:13+00
database: pushinweight_shadow (Render prod, oregon-postgres)
window_column: posts.created_at
window: [2026-08-04 03:47:00+00, 2026-08-04 04:47:00+00)
cohort_size: 190
mode: read-only
---

# 2026-08-04 Harvester recovery cohort

This is the cohort of posts that landed after the TwitterAPI credit topup cleared
the 402 credit-exhaustion bug that had stalled the cron.

## Summary

| Metric | Value |
| --- | --- |
| Total posts in window | **190** |
| Total brand-attribution rows (`posts_brands`) | **232** |
| Posts with >=1 brand | 190 (100% — 0 orphans) |
| Brand attributions per post | 1.22 avg |
| `created_at` range (tweet timestamp) | Aug 4, 2026, 12:47:33 PM JST → Aug 4, 2026, 1:41:21 PM JST |
| `fetched_at` range (ingest timestamp) | Aug 4, 2026, 1:30:27 PM JST → Aug 4, 2026, 1:47:10 PM JST |
| Distinct authors (`author_handle`) | 165 |
| Distinct authors (`author_id`) | 167 |
| First tweet_id (min) | 2084486370270265372 |
| Last tweet_id (max) | 2084499909622014069 |
| Distinct `source_query_id` | 0 (column is NULL for the whole cohort) |
| Signal rows (`posts_brands_signals`) | 220 rows over 178 posts (15 posts unclassified) |
| Discourse rows (`posts_brands_discourse`) | 134 rows over 117 posts (76 posts have no discourse row) |

### Notes on the window

- `posts.created_at` is the **tweet authorship timestamp**, not ingest time.
  `posts.fetched_at` is the ingest timestamp. The task specified `created_at`,
  so this report is on the `created_at` window; the `fetched_at` distribution is
  included below for the operational picture.
- Because the window is relative to a moving `NOW()`, the count drifted from 185
  to 190 during the session. The window here is **pinned to absolute timestamps**
  so the report is reproducible.
- There is no `cycle_id` column on `posts`. The nearest proxy is `source_query_id`,
  which is NULL for every row in this cohort. The ingest batching is visible
  instead via `fetched_at` clustering (see below).

### Ingest batching (`fetched_at`, per minute)

| Minute (UTC) | Posts |
| --- | --- |
| 2026-08-04 04:30 | 2 |
| 2026-08-04 04:31 | 11 |
| 2026-08-04 04:32 | **165** |
| 2026-08-04 04:44 | 5 |
| 2026-08-04 04:46 | 6 |
| 2026-08-04 04:47 | 4 |

One large recovery burst at 04:32 (165 posts) — the backlog drain right after the
credit topup — followed by a normal trickle.

## Brand breakdown

Unique posts per brand (`posts_brands` joined to `posts`). A post can carry
multiple brands, so the column sums to 232 > 190.

| Brand | Unique posts |
| --- | --- |
| deepseek | 107 |
| qwen | 52 |
| minimax | 46 |
| glm | 10 |
| llama | 8 |
| hunyuan | 4 |
| ernie | 2 |
| mistral | 2 |
| doubao | 1 |
| **Total attributions** | **232** |

DeepSeek dominates at 56% of posts; the top three (deepseek, qwen, minimax)
account for 205 of the 232 attributions (88%).

## Post type breakdown

Unique posts per `post_type_key` (`posts_brands_signals`). 178 of 190 posts have
at least one signal row; 15 posts have none.

| Post type | Unique posts |
| --- | --- |
| hands_on_usage | 64 |
| performance_comparisons | 47 |
| feedback_questions | 25 |
| buzz_releases | 22 |
| advertising_marketing | 19 |
| event_announcement | 3 |

## Discourse role breakdown

Unique posts per `discourse_key` (`posts_brands_discourse`). Only 117 of 190
posts carry a discourse row — discourse classification is sparser than post-type.

| Discourse role | Unique posts |
| --- | --- |
| genuine_hype | 75 |
| advertising-marketing | 20 |
| fud | 8 |
| dunk_yingyang | 6 |
| absurdist_meme | 4 |
| sarcasm | 2 |
| cope | 1 |
| distillation_accusation | 1 |
| self_deprecation | 1 |

`genuine_hype` is 64% of all classified posts. Negative-valence roles
(fud, dunk_yingyang, cope, distillation_accusation) total 16.

## Lang_detected breakdown

Unique posts per `posts.lang_detected`, NULL included as its own row.

| lang_detected | Unique posts |
| --- | --- |
| (NULL) | 79 |
| en | 68 |
| zh-hans | 19 |
| ja | 14 |
| ko | 4 |
| es | 3 |
| pt | 3 |
| id | 2 |
| fr | 1 |
| **Total** | **190** |

42% of the cohort has no detected language — the language-detection pass has not
caught up with the recovery burst yet. Of the 111 detected, English is 61%.

## Methodology

All queries were read-only `SELECT`s run over SSH to `fuchitalee`, against the
Render prod Postgres `pushinweight_shadow`, with `psql -t -A -F"|"` for
machine-parseable output. No rows were modified.

Connection:

```
PGPASSWORD=... psql -h dpg-d9koekqjobas73fvjqng-a.oregon-postgres.render.com \
  -U pushinweight_shadow -d pushinweight_shadow -t -A -F"|"
```

Schema source of truth: `/Users/fuchitalee/development/pushin-weight-v2/core/models.py`
(`Post` -> `posts`, `PostBrand` -> `posts_brands`, `PostBrandSignal` ->
`posts_brands_signals`, `PostBrandDiscourse` -> `posts_brands_discourse`).

The window is pinned to absolute timestamps rather than `NOW() - INTERVAL 1 hour`
so the numbers reproduce exactly:

```sql
-- shorthand used below
-- WINDOW: created_at >= TIMESTAMPTZ '2026-08-04 03:47:00+00'
--     AND created_at <  TIMESTAMPTZ '2026-08-04 04:47:00+00'
```

### Headline

```sql
SELECT COUNT(*), MIN(created_at), MAX(created_at),
       MIN(fetched_at), MAX(fetched_at),
       COUNT(DISTINCT author_handle), COUNT(DISTINCT author_id),
       COUNT(DISTINCT source_query_id),
       MIN(tweet_id), MAX(tweet_id)
FROM posts
WHERE created_at >= TIMESTAMPTZ '2026-08-04 03:47:00+00'
  AND created_at <  TIMESTAMPTZ '2026-08-04 04:47:00+00';
```

### Brand-attribution totals

```sql
SELECT COUNT(*) AS attribution_rows, COUNT(DISTINCT pb.post_id) AS posts
FROM posts_brands pb
JOIN posts p ON p.tweet_id = pb.post_id
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 03:47:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 04:47:00+00';
```

### (a) Brand breakdown

```sql
SELECT pb.brand_id, COUNT(DISTINCT pb.post_id) AS posts
FROM posts_brands pb
JOIN posts p ON p.tweet_id = pb.post_id
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 03:47:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 04:47:00+00'
GROUP BY 1 ORDER BY 2 DESC, 1;
```

### (b) Post type breakdown

```sql
SELECT s.post_type_key, COUNT(DISTINCT s.post_id) AS posts
FROM posts_brands_signals s
JOIN posts p ON p.tweet_id = s.post_id
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 03:47:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 04:47:00+00'
GROUP BY 1 ORDER BY 2 DESC, 1;
```

### (c) Discourse role breakdown

```sql
SELECT d.discourse_key, COUNT(DISTINCT d.post_id) AS posts
FROM posts_brands_discourse d
JOIN posts p ON p.tweet_id = d.post_id
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 03:47:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 04:47:00+00'
GROUP BY 1 ORDER BY 2 DESC, 1;
```

### (d) lang_detected breakdown

```sql
SELECT COALESCE(lang_detected, '(NULL)') AS lang,
       COUNT(DISTINCT tweet_id) AS posts
FROM posts
WHERE created_at >= TIMESTAMPTZ '2026-08-04 03:47:00+00'
  AND created_at <  TIMESTAMPTZ '2026-08-04 04:47:00+00'
GROUP BY 1 ORDER BY 2 DESC, 1;
```

### Coverage gaps

```sql
SELECT
  COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM posts_brands b            WHERE b.post_id = p.tweet_id)) AS no_brand,
  COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM posts_brands_signals s    WHERE s.post_id = p.tweet_id)) AS no_signal,
  COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM posts_brands_discourse d  WHERE d.post_id = p.tweet_id)) AS no_discourse
FROM posts p
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 03:47:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 04:47:00+00';
```

### Ingest batching

```sql
SELECT date_trunc('minute', fetched_at) AS minute, COUNT(*)
FROM posts p
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 03:47:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 04:47:00+00'
GROUP BY 1 ORDER BY 1;
```
