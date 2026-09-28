# Pending processing-time baseline — 2026-09-28

This is a one-time, read-only production snapshot for pending-sphere copy. It is not a service-level promise and is not recalculated by requests or workers.

- Source: Render `pushinweight-web`'s service-scoped `DATABASE_URL`, verified read-only to point at PostgreSQL `dpg-d9koekqjobas73fvjqng-a` / `pushinweight_shadow`.
- Statement timestamp: `2026-09-28 13:30:24.255634+00`.
- Fixed UTC cutoff: `2026-09-28 13:00:00+00`; half-open 72-hour creation/request window: `[2026-09-25 13:00:00+00, 2026-09-28 13:00:00+00)`.
- Read-only method: one SQL statement on one PostgreSQL MVCC snapshot. There was no TwitterAPI call, model call, or production write.
- Revisions observed: translation `literal-translation-plaintext-v12` / `google/gemma-4-31B-it-turbo`; Stage 1 `stage1-v1` / `stage1-taxonomy-v4` / `stage1-two-role-merge-0731-v5` / `deepseek-ai/DeepSeek-V4-Flash-0731`; synthesis `post-synthesis-gemma4-tagged-v2` / `google/gemma-4-31B-it-turbo`.

| Lifecycle/cohort | Total | Pending | Failed | Cancelled | Successful retries/no-first-attempt | Usable | Other successful exclusions | Mean min | p50 min | p90 min | Nearest-minute mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Translation, all successful current artifacts | 8,566 | 39 | 300 | 0 | 1,425 included | 8,214 | 13 | 109.272 | 3.717 | 483.158 | 109 |
| Translation, first attempt only | 8,566 | 39 | 300 | 0 | 1,425 excluded | 6,789 | 1,438 including retries | 5.289 | 3.272 | 14.522 | 5 |
| Stage 1 analysis, first attempt only | 8,566 | 3 | 249 | 0 | 2,035 excluded | 6,243 | 2,071 including retries | 15.123 | 3.995 | 15.784 | 15 |
| Commentary/synthesis, all successful linked artifacts | 2,202 | 0 | 617 | 0 | 33 included | 1,585 | 0 | 0.622 | 0.391 | 1.138 | 1 |
| Commentary/synthesis, first attempt only | 2,202 | 0 | 617 | 0 | 33 excluded | 1,552 | 33 | 0.607 | 0.386 | 1.108 | 1 |

The translation mean is **not** approximately 4–6 minutes for all completed work. The retry-heavy successful tail raises the arithmetic mean to 109 minutes while the median remains 3.7 minutes. The first-attempt subset averages 5 minutes. Product copy must label a first-attempt average as such; it must not silently present that subset as the mean of all successful work or swap the mean for the median. The owner choice on this tradeoff remains open at the time of this receipt.

Translation duration starts at `post_enrichment_states.created_at` and ends at the linked `post_translation_artifacts.completed_at` where `is_current` and `state='succeeded'`. Successful rows without a current successful artifact, with a negative/missing clock, with an artifact after cutoff, or with an active claim are excluded. First-attempt means `translation_attempts=1`; retry/no-attempt successes are separately disclosed. The snapshot has 8,227 translation-succeeded states, of which 8,214 meet the all-success clock/claim guard.

Stage 1 analysis duration is necessarily an **approximation**: `post_enrichment_states.created_at` to terminal successful `updated_at`, cross-checked against the latest current `posts_brands_classification_states.classified_at` for that post. There is no immutable classification-completed timestamp. The query excludes non-first-attempt/replay candidates, active claims, missing current brand states, negative clocks, later classification evidence, and updates after cutoff. Of 8,314 classification-succeeded states, 2,035 were retry/no-first-attempt and 36 further failed clock/claim/cutoff guards, leaving 6,243. The observed mean of 15 minutes is not an exact classifier service-time estimate.

Commentary is a separate on-demand lifecycle: `post_synthesis_demands.first_requested_at` to its linked current successful `post_synthesis_artifacts.completed_at`. It is not blended with harvester enrichment. The first-attempt subset excludes the 33 successful retry demands. No synthesis requests were pending or cancelled at the fixed cutoff; 617 were failed.

## Reproduction query

Execute this as a single read-only statement against the verified web-associated database. The SQL below is the source of the table above; rerunning later with the same cutoff can differ if a row created before cutoff is subsequently retried or its current artifact changes, because the schema does not retain an immutable as-of history for these mutable statuses.

```sql
WITH t AS (
  SELECT s.post_id, s.created_at, s.translation_status,
         s.translation_attempts, s.claim_owner, a.state artifact_state,
         a.completed_at, extract(epoch FROM a.completed_at-s.created_at)/60.0 minutes
  FROM post_enrichment_states s
  LEFT JOIN post_translation_artifacts a ON a.post_id=s.post_id AND a.is_current
  WHERE s.created_at >= TIMESTAMPTZ '2026-09-25 13:00:00+00'
    AND s.created_at < TIMESTAMPTZ '2026-09-28 13:00:00+00'
), c AS (
  SELECT s.post_id, s.created_at, s.updated_at, s.classification_status,
         s.classification_attempts, s.claim_owner, max(p.classified_at) classified_at,
         count(p.*) brand_states,
         extract(epoch FROM s.updated_at-s.created_at)/60.0 minutes
  FROM post_enrichment_states s
  LEFT JOIN posts_brands_classification_states p ON p.post_id=s.post_id
  WHERE s.created_at >= TIMESTAMPTZ '2026-09-25 13:00:00+00'
    AND s.created_at < TIMESTAMPTZ '2026-09-28 13:00:00+00'
  GROUP BY s.post_id
), d AS (
  SELECT d.id, d.first_requested_at, d.state, d.attempts, d.lease_owner,
         a.state artifact_state, a.is_current, a.completed_at,
         extract(epoch FROM a.completed_at-d.first_requested_at)/60.0 minutes
  FROM post_synthesis_demands d
  LEFT JOIN post_synthesis_artifacts a ON a.id=d.artifact_id
  WHERE d.first_requested_at >= TIMESTAMPTZ '2026-09-25 13:00:00+00'
    AND d.first_requested_at < TIMESTAMPTZ '2026-09-28 13:00:00+00'
), x AS (
  SELECT 'translation_all' lifecycle, minutes, translation_status status,
         translation_attempts attempts,
         (translation_status='succeeded' AND artifact_state='succeeded'
          AND completed_at>=created_at
          AND completed_at<TIMESTAMPTZ '2026-09-28 13:00:00+00'
          AND claim_owner='') usable FROM t
  UNION ALL
  SELECT 'translation_first', minutes, translation_status, translation_attempts,
         (translation_status='succeeded' AND translation_attempts=1
          AND artifact_state='succeeded' AND completed_at>=created_at
          AND completed_at<TIMESTAMPTZ '2026-09-28 13:00:00+00'
          AND claim_owner='') FROM t
  UNION ALL
  SELECT 'classification_first', minutes, classification_status,
         classification_attempts,
         (classification_status='succeeded' AND classification_attempts=1
          AND brand_states>0 AND updated_at>=created_at
          AND updated_at<TIMESTAMPTZ '2026-09-28 13:00:00+00'
          AND classified_at>=created_at
          AND classified_at<=updated_at+INTERVAL '2 seconds'
          AND claim_owner='') FROM c
  UNION ALL
  SELECT 'synthesis_all', minutes, state, attempts,
         (state='succeeded' AND artifact_state='succeeded' AND is_current
          AND completed_at>=first_requested_at
          AND completed_at<TIMESTAMPTZ '2026-09-28 13:00:00+00'
          AND lease_owner='') FROM d
  UNION ALL
  SELECT 'synthesis_first', minutes, state, attempts,
         (state='succeeded' AND attempts=1 AND artifact_state='succeeded'
          AND is_current AND completed_at>=first_requested_at
          AND completed_at<TIMESTAMPTZ '2026-09-28 13:00:00+00'
          AND lease_owner='') FROM d
)
SELECT statement_timestamp() queried_at, lifecycle, count(*) total,
       count(*) FILTER (WHERE status IN ('pending','processing')) pending,
       count(*) FILTER (WHERE status='failed') failed,
       count(*) FILTER (WHERE status='cancelled') cancelled,
       count(*) FILTER (WHERE status='succeeded' AND attempts<>1) succeeded_retries,
       count(*) FILTER (WHERE usable) usable,
       count(*) FILTER (WHERE status='succeeded' AND NOT coalesce(usable,false)) success_excluded,
       round(avg(minutes) FILTER (WHERE usable)::numeric,3) mean_min,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY minutes)
             FILTER (WHERE usable)::numeric,3) p50_min,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY minutes)
             FILTER (WHERE usable)::numeric,3) p90_min
FROM x GROUP BY lifecycle ORDER BY lifecycle;
```
