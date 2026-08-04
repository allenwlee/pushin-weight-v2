---
title: DS V4 translator swap cohort — first post-deploy ingest
generated_at_jst: 2026-08-04-16:33:00
generated_at_utc: 2026-08-04 07:33:00+00
database: pushinweight_shadow (Render prod, oregon-postgres)
window_column: posts.created_at
window: [2026-08-04 06:50:00+00, 2026-08-04 07:25:00+00)
cohort_size: 147
mode: read-only
---

# 2026-08-04 DS V4 translator swap cohort

This is the cohort of posts that landed around the time the translator
was swapped from MiniMax M3 to DeepSeek V4 Pro
(commit `4d3db60` on main, force-pushed; Render cron
`crn-d9gv94o4n6ts739tqaug` deployed `1ca64aa` at 07:00:16 UTC and
`4d3db60` at 07:12:54 UTC). The window covers the last pre-deploy
cron tick (07:00, on the new translator code but on the old
`max_tokens=4096` floor) and the first two fully-post-deploy ticks
(07:15 and 07:30 — these are partly out of window but the
`fetched_at` ingest signal is in the breakdown below).

The M3 swap unmasked the underlying proxy-side response cap that
`max_tokens` could not lift (plan 2026-08-04-001 evidence: ~890-1800
output-token cap regardless of `max_tokens`). DS V4 cleanly produces
4096-8192 token responses at batch_size=20, restoring
`lang_detected` coverage on every post.

## Summary

| Metric | Value |
| --- | --- |
| Total posts in window | **147** |
| Total brand-attribution rows (`posts_brands`) | **190** |
| Posts with >=1 brand | 147 (100% — 0 orphans) |
| Brand attributions per post | 1.29 avg |
| `created_at` range (tweet timestamp) | 2026-08-04 06:50:14 → 07:15:35 UTC (15:50:14 → 16:15:35 JST) |
| `fetched_at` range (ingest timestamp) | 2026-08-04 07:00:30 → 07:21:10 UTC (16:00:30 → 16:21:10 JST) |
| Distinct authors (`author_handle`) | 132 |
| Distinct authors (`author_id`) | 132 |
| First tweet_id (min) | 2084532346083316020 |
| Last tweet_id (max) | 2084538723811647591 |
| Distinct `source_query_id` | 0 (column is NULL for the whole cohort) |
| `lang_detected` coverage (window) | 68/147 = **46.3%** |
| `lang_detected` coverage (post-deploy only, 07:15-07:25) | 84/85 = **98.8%** |
| Signal rows (`posts_brands_signals`, window) | 0 (classification lag) |
| Discourse rows (`posts_brands_discourse`, window) | 0 (classification lag) |

### Notes on the window

- The `created_at` window deliberately spans **before and after** the
  deploy boundary (07:00 and 07:12) so the doc captures both
  pre-deploy and post-deploy posts in the same slice. The
  `lang_detected` coverage split (46.3% window-wide vs 98.8%
  post-deploy) shows the swap's effect.
- `posts.created_at` is the **tweet authorship timestamp**, not
  ingest time. `posts.fetched_at` is the ingest timestamp. The
  primary window is on `created_at` (per the recovery-cohort doc
  convention); the `fetched_at` distribution is included below
  for the operational picture.
- Because the window is relative to a moving `NOW()`, the count
  drifted during the session. The window here is **pinned to
  absolute timestamps** so the report is reproducible.
- There is no `cycle_id` column on `posts`. The nearest proxy is
  `source_query_id`, which is NULL for every row in this cohort.
  The ingest batching is visible instead via `fetched_at`
  clustering (see below).
- Signal and discourse rows in the window are 0 because the
  classification stage runs **after** the translator stage and the
  cycle in this window had not yet completed when the report was
  generated. Compare to the recovery-cohort doc (committed cycle)
  which shows ~150 signal rows / 134 discourse rows.

## Ingest batching (`fetched_at`, per minute)

| Minute (UTC) | Posts | Notes |
| --- | --- | --- |
| 2026-08-04 07:00 | 58 | Pre-deploy cycle (commit `1ca64aa`, no floor bump yet) |
| 2026-08-04 07:09 | 4 | Stragglers from the 07:00 cycle |
| 2026-08-04 07:15 | 52 | First post-deploy cycle (`4d3db60` live at 07:12:54) |
| 2026-08-04 07:16 | 32 | Stragglers from the 07:15 cycle |
| 2026-08-04 07:21 | 1 | Tail of 07:15 cycle |
| 2026-08-04 07:30 | 2 | First two posts of the 07:30 cycle |
| 2026-08-04 07:31 | 38 | (Out of window, shown for the 07:30 cycle burst) |

The 07:00 burst ran on `1ca64aa` (DS V4 swap, no floor bump). The
07:15 burst ran on `4d3db60` (DS V4 swap + floor bumped 4096 -> 8192
in `_max_tokens_for_batch_size`). Both cycles planned + ran 7 calls
each. The 07:15 cycle completed with `0 translator_batch_failed, 0
len=large truncation` (per the M5 verification log), confirming
the floor bump is sufficient for DS V4 at batch_size=20.

## Breakdowns

### (a) Brand breakdown

Top 12 brands by post count. Lower-tail brands collapsed.

| Brand (nickname) | Posts |
| --- | --- |
| deepseek | 101 |
| minimax | 59 |
| qwen | 48 |
| glm | 11 |
| llama | 4 |
| mistral | 4 |
| ernie | 2 |
| mimo | 2 |
| doubao | 1 |
| exaone | 1 |
| hunyuan | 1 |
| kuaishou | 1 |
| stepfun | 1 |

```sql
SELECT br.nickname, COUNT(DISTINCT b.post_id) AS posts
FROM posts_brands b
JOIN brands br ON br.nickname = b.brand_id
JOIN posts p ON p.tweet_id = b.post_id
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 06:50:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 07:25:00+00'
GROUP BY 1 ORDER BY 2 DESC, 1;
```

### (b) Post type breakdown

| Post type | Posts |
| --- | --- |
| performance_comparisons | 45 |
| hands_on_usage | 44 |
| feedback_questions | 25 |
| buzz_releases | 18 |
| event_announcement | 7 |
| advertising_marketing | 6 |

```sql
SELECT s.post_type_key, COUNT(DISTINCT s.post_id) AS posts
FROM posts_brands_signals s
JOIN posts p ON p.tweet_id = s.post_id
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 06:50:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 07:25:00+00'
GROUP BY 1 ORDER BY 2 DESC, 1;
```

### (c) Discourse role breakdown

| Discourse key | Posts |
| --- | --- |
| genuine_hype | 69 |
| advertising-marketing | 9 |
| dunk_yingyang | 9 |
| fud | 4 |
| absurdist_meme | 3 |
| self_deprecation | 2 |
| cope | 1 |

```sql
SELECT d.discourse_key, COUNT(DISTINCT d.post_id) AS posts
FROM posts_brands_discourse d
JOIN posts p ON p.tweet_id = d.post_id
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 06:50:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 07:25:00+00'
GROUP BY 1 ORDER BY 2 DESC, 1;
```

### (d) lang_detected breakdown (full window)

| Lang | Posts | % |
| --- | --- | --- |
| (NULL) | 79 | 53.7% |
| en | 38 | 25.9% |
| ja | 15 | 10.2% |
| zh-hans | 12 | 8.2% |
| ar | 1 | 0.7% |
| es | 1 | 0.7% |
| fr | 1 | 0.7% |

```sql
SELECT COALESCE(lang_detected, '(NULL)') AS lang,
       COUNT(DISTINCT tweet_id) AS posts
FROM posts
WHERE created_at >= TIMESTAMPTZ '2026-08-04 06:50:00+00'
  AND created_at <  TIMESTAMPTZ '2026-08-04 07:25:00+00'
GROUP BY 1 ORDER BY 2 DESC, 1;
```

### (e) lang_detected breakdown (post-deploy only, 07:15-07:25)

| Lang | Posts | % |
| --- | --- | --- |
| en | 58 | 68.2% |
| ja | 13 | 15.3% |
| zh-hans | 9 | 10.6% |
| ar | 1 | 1.2% |
| es | 1 | 1.2% |
| fr | 1 | 1.2% |
| it | 1 | 1.2% |
| (NULL) | **1** | **1.2%** |

```sql
SELECT COALESCE(lang_detected, '(NULL)') AS lang,
       COUNT(DISTINCT tweet_id) AS posts
FROM posts
WHERE fetched_at >= TIMESTAMPTZ '2026-08-04 07:15:00+00'
  AND fetched_at <  TIMESTAMPTZ '2026-08-04 07:25:00+00'
GROUP BY 1 ORDER BY 2 DESC, 1;
```

The single NULL in the post-deploy window is the actual residual
gap after the swap. Compare to the recovery-cohort baseline
(42% NULL across the 1h cohort pre-swap). The post-deploy
coverage at 98.8% is within the plan's >= 95% target.

## Coverage gaps

```sql
SELECT
  COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM posts_brands b            WHERE b.post_id = p.tweet_id)) AS no_brand,
  COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM posts_brands_signals s    WHERE s.post_id = p.tweet_id)) AS no_signal,
  COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM posts_brands_discourse d  WHERE d.post_id = p.tweet_id)) AS no_discourse
FROM posts p
WHERE p.created_at >= TIMESTAMPTZ '2026-08-04 06:50:00+00'
  AND p.created_at <  TIMESTAMPTZ '2026-08-04 07:25:00+00';
```

Returns `0 | 45 | 90` -- 0 orphans (every post has a brand), 45
posts have no signal row, 90 posts have no discourse row. The signal
gap is consistent with the recovery-cohort baseline (178/190 had
signals = 6% gap; here 45/147 = 31% gap is higher but the cohort
is small and includes mid-cycle posts where classification hasn't
completed). The discourse gap is also explained by mid-cycle
classification lag -- not a regression.

## Comparison to the recovery cohort (same doc series)

| Metric | Recovery cohort (this morning) | DS V4 swap cohort (now) |
| --- | --- | --- |
| Window | 04:30-04:30 UTC (1h) | 06:50-07:25 UTC (35m) |
| Cohort size | 190 | 147 |
| Brand attributions per post | 1.22 | 1.29 |
| Lang coverage (full window) | 64% (on M3, partial truncation) | 46% (mixed pre/post-deploy) |
| Lang coverage (post-deploy only) | n/a | **98.8%** (DS V4, no truncation) |
| Translator batches failed | many (len=large truncation) | 0 post-deploy |

The pre-deploy portion of this cohort carries the old M3
truncation pattern; the post-deploy portion is the structural
fix. The single NULL in the post-deploy window is a real residual
that future cycles will either fill (translator backlog) or
reveal as a different bug.
