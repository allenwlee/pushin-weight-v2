---
date: 2026-08-13
source_sha: 4626dd0103ba78728c05c709a2de1902b807e486
scope: headline-trend-narrative-u0
data_policy: aggregate-only-no-post-text
---

# Headline trend narrative implementation baseline

This is the refreshed analytical-expansion evidence required by U0 of
`2026-08-12-121455-feat-v22-headline-trend-narratives.md`. It records the
measured state only; it does not enable a worker, enqueue a task, call an LLM,
alter harvesting, or change a Render resource.

## Workspace and migration slot

- Isolated worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/v22-headline-trend-narratives`
- Branch: `feat/v22-headline-trend-narratives`
- Fresh implementation base: `origin/main@4626dd0103ba78728c05c709a2de1902b807e486`.
  A refetch on 2026-08-13 returned the same immutable SHA.
- Current migration leaf in Git and production:
  `core.0013_trend_narrative_version`; production applied it at
  `2026-08-12 10:31:21.97742+00`.
- Allocated expansion migration: `core.0014_expand_trend_narrative`. Applied
  migration `0013` remains immutable. Quiescence and contraction numbers are
  deliberately allocated only immediately before their separate releases.
- The implementation worktree was clean before U0. The dirty primary checkout
  status digest was
  `3c1bfebd473ff4fd6c388d4163c31dbf48429b8c6278c0bc608050ebabb292fc`
  and its tracked binary diff digest was
  `9b945848f497e1c0361ee6fece99993ed8a8f51c5ddf8cf98bf6ca94ec686720`;
  U0 did not alter it.
- Active worktrees were inventoried. None owns a migration after `0013` or has
  unmerged commits on the clean headline feature branch. Existing dirty UI
  work remains isolated in the primary and V22 parity worktrees.

## Render release manifest

Observed read-only with Render CLI on 2026-08-13. Credentials and secret
values were not inspected or recorded. Live deployed commits, region, repo,
auto-deploy mode, and service commands were recorded so the candidate can be
reconciled without applying it.

| Resource | ID | Type/state/region | Repo/branch/SHA | Command or schedule | Auto-deploy | Env/broker/queue identity | Ownership conclusion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `pushinweight-harvest` | `crn-d9gv94o4n6ts739tqaug` | cron / active / oregon | `allenwlee/pushin-weight-v2`, `main@4626dd0` | `python manage.py run_cycle`, `*/15 * * * *` | commit | owned headline broker; `trend-narratives`; enqueue revision `enqueue-v1` in Blueprint | Sole active scheduler |
| `pushinweight-web` | `srv-d9go2breo5us73cg6vqg` | web / active / oregon | `allenwlee/pushin-weight-v2`, `main@4626dd0` | `gunicorn project.wsgi:application --log-file -` | commit | serving revision `dsv4-live-v1`; serving on; enqueue/provider off in this process | Serving path only |
| `pushinweight-headlines` | `srv-d9ufj4e417fc73d93g20` | worker / active / oregon | `allenwlee/pushin-weight-v2`, `main@4626dd0` | Celery worker; queue `trend-narratives`; concurrency/prefetch one; no beat | commit | `pushinweight-headlines-broker`; provider revision `dsv4-canary-v1`; provider on in this process | Sole headline consumer |
| `pushinweight-headlines-broker` | `red-d9u4mie417fc73fo5kk0` | Key Value / available / oregon | n/a | no scheduler; no-eviction; journal-snapshot | n/a | owned headline transport namespace | Sole headline broker |
| `pushinweight-worker` | `srv-d9go2breo5us73cg6vr0` | worker / suspended / oregon | `allenwlee/pushin-weight-v2`, `main@2630e0e` | generic Celery worker, concurrency one | commit | legacy/default queue; no headline namespace | Legacy; do not reactivate |
| `pushinweight-beat` | `srv-d9go2breo5us73cg6vrg` | worker / suspended / oregon | `allenwlee/pushin-weight-v2`, `main@2630e0e` | `celery -A project beat -l INFO` | commit | legacy scheduler; no headline namespace | Legacy; do not reactivate |
| `pushinweight-db-shadow` | `dpg-d9koekqjobas73fvjqng-a` | PostgreSQL 18 / active / oregon | n/a | n/a | n/a | `DATABASE_URL` secret not recorded | Current application database |

The live resource owner is the Push in Weight Render workspace. One active
15-minute scheduler, zero active beat services, one active headline-only
consumer, and one owned broker are present. `scrolls-redis` and the unrelated
`pushinweight-redis` PostgreSQL resource are not part of this feature. The web,
cron, and headline worker report live deploys at `4626dd0`. Expansion rollout
must first disable provider/enqueue controls and drain the queue; this U0 run
made no control or resource change.

The production ledger currently has 21 rows, four current rows, IDs `1..21`,
and a 256 KiB base relation. `trend_narrative_versions` is a table; neither
`trend_narratives` nor `trend_narrative_subjects` exists yet.

## Harvester external-call baseline

`plan_calls_for_cycle(load_config(config.yaml))` produces exactly seven search
lines in the current code: `A`, `B1`, `C1`, `C2`, `C3`, `B2`, and `B3`.
The one-shot metrics refresh is enabled with a cap of 200 tweet IDs per cycle.
The narrative feature must not add, repeat, or reorder any TwitterAPI request;
its only harvest-path change is one isolated post-completion dispatch attempt.

The latest committed cost fixture (`tests/harvester_costs/2026-08-10-162500-ae1-smoke.md`)
records seven search lines plus one metrics line, 3,915 credits total for its
sample cycle. That fixture is a comparator, not a claim that every current
cycle has the same result volume. The ignored local `data/runs` directory is
stale and is not used as current production evidence.

The current planner also emits the pre-existing warning that `doubao`,
`kuaishou`, and `sensechat` occur in both B and C configuration. That condition
is part of the before-ledger and is not changed by this feature.

## Aggregate-only analytical calibration

The production aggregate was anchored at `2026-08-13 06:41:00+00`. It selected
only timestamps, brand keys, counts, classifications, engagement totals, and
distinct author counts; it did not select or emit post text, URLs, handles, or
account content. The 365-day range contains 81,706 distinct posts and 95,960
distinct post-brand pairs. The earliest eligible association is
`2025-01-15 09:47:50+00`.

| Window | Fine resolution | Highest observed peak-to-median examples | Whole-window support examples |
| --- | --- | --- | --- |
| `1d` | 15 minutes | DeepSeek `179/160`, ratio `5.04`; Qwen `43/36`, `4.10`; MiniMax `26/24`, `2.60` | DeepSeek `4,386/3,088`; Qwen `1,191/957`; MiniMax `978/739` |
| `7d` | 1 hour | DeepSeek `631/513`, ratio `7.17`; Llama `24/19`, `6.00`; MiniMax `109/92`, `2.79` | DeepSeek `15,262/8,948`; MiniMax `6,292/3,399`; Qwen `5,745/3,735` |
| `30d` | 1 day | MiniMax `2,118/1,415`, ratio `14.17`; DeepSeek `5,182/3,496`, `7.46`; Qwen `1,940/1,453`, `5.91` | DeepSeek `40,265/19,712`; Qwen `16,448/9,128`; MiniMax `13,637/6,617` |
| `365d` | 1 day | DeepSeek `5,182/3,496`; MiniMax `2,118/1,415`; Qwen `1,940/1,453`; zero-filled medians are zero because collection is sparse before July | DeepSeek `41,854/20,409`; Qwen `17,311/9,553`; MiniMax `14,275/6,936` |

The earliest associated non-sentinel post is dated 2025-01-15, so the current
literal R5 earliest-post coverage formula reports full 365-day coverage. The
365-day half distribution is nevertheless sharply asymmetric; this reinforces
the need for exact eligibility and momentum rules rather than an LLM-inferred
story. Fixture coverage must still pin the below-75-percent and exact-75-percent
branches.

The frozen analytical defaults are: 20 selected posts, 10 selected authors,
comparison coverage at least `0.75`, episode peak at least `3.0×` the
zero-filled fine-bucket median with denominator floor one, episode peak support
of at least 20 posts and 10 authors, adjacent qualifying buckets merged, and at
most three episodes per candidate. The absolute support gates are mandatory:
the 365-day zero-filled median is commonly zero, so a ratio by itself is not
evidence of an exceptional episode.

At the same anchor, metrics coverage is `0%` for the selected `1d`, `7d`, and
`30d` ranges and `4.79%` for `365d`; 5,043 post-brand pairs have a recorded
refresh and 639,686 observed interactions. This is the expected censored-data
case for implementation: missing refreshes are unknown, never zero, and no
engagement projection is permitted. Signal/discourse/nationalism availability
is sufficient to exercise the metadata families (for `30d`: 71,558 signal
pairs, 45,229 discourse pairs, and 45,228 pairs on each nationalism axis).

The versioned qualitative release packets live in
`tests/fixtures/trend_narrative_co_dominance_v1.json`. They freeze two strong
brands in one family, two strong brands in different families, one strong plus
one merely notable brand, and a low-prior-coverage two-strong case. Expected
selection is two, two, one, and two candidates respectively.

The aggregate-only 365-day query used the `idx_posts_created_at` index,
materialized 95,960 post-brand rows, and completed in 1.746 seconds on
production PostgreSQL 18, below the 30-second gate. U1/U11 must preserve a
fixed set-based query count and re-run the complete snapshot timing after the
new implementation exists.

The implemented U1/U11 pipeline was then benchmarked read-only at the latest
available timestamp on a disposable, current-schema clone of the local
historical corpus (28,822 posts and 35,625 post-brand pairs). The complete
`365d` `REPEATABLE READ READ ONLY` snapshot finished in 6.476 seconds with six
shortlisted candidates and 22 bounded evidence records. Canonical persistence
JSON measured 227,977 UTF-8 bytes and the fine-array-free provider projection
measured 89,321 bytes, inside the 30-second, 256 KiB, and 128 KiB gates. The
benchmark clone was dropped after measurement; its 28,822-post source database
was unchanged. Focused tests separately pin the fixed eight analysis statements
for both one- and two-brand eligible universes, preventing candidate-count N+1
growth.

## Verification environment

PostgreSQL 17.9 is available locally through the `fuchitalee` role. The
disposable test configuration is
`DATABASE_URL=postgresql://fuchitalee@localhost/pushinweight_test`. The existing
headline baseline ran 102 focused tests, including 64 PostgreSQL-required
tests, with `executed=64 skipped=0 errors=0` in 5.06 seconds. The current cost
fixture remains 3,915 credits: seven search lines plus one 174-ID metrics line.
Verification must continue using the explicit disposable URL and must never
point pytest at production.

After U1/U11 implementation, the focused fact, candidate, configuration, and
task suites pass 67 tests. PostgreSQL-required accounting reports
`executed=66 skipped=0 errors=0`; changed-code Ruff and `git diff --check` also
pass. Repository-wide Ruff still reports 1,360 pre-existing findings outside
this feature scope and was not mechanically rewritten.

## Expansion-migration verification and rollback contract

Migration `0014_expand_trend_narrative` is an atomic expand step. It renames
the physical parent table to `trend_narratives`, leaves a simple writable
compatibility view at `trend_narrative_versions`, adds canonical output and
provenance columns, and creates `trend_narrative_subjects`. It does not rewrite
legacy parent rows or backfill normalized subjects. Runtime compatibility
accessors continue to read the legacy Chinese/model/snapshot columns until a
schema-two publication writes canonical state. No production migration was
run during implementation.

Capture the following read-only pre-migration evidence after provider and
enqueue controls are off and the headline queue is empty:

```sql
SELECT COUNT(*) AS rows,
       COUNT(*) FILTER (WHERE is_current) AS current_rows,
       MIN(id) AS min_id,
       MAX(id) AS max_id
FROM trend_narrative_versions;

SELECT window_days, status, COUNT(*)
FROM trend_narrative_versions
GROUP BY window_days, status
ORDER BY window_days, status;
```

After the migration, verify relation identity, parent preservation, and the
absence of unexpected canonical writes with:

```sql
SELECT relname, relkind
FROM pg_class
WHERE relname IN (
  'trend_narratives',
  'trend_narrative_versions',
  'trend_narrative_subjects'
)
ORDER BY relname;

SELECT COUNT(*) AS rows,
       COUNT(*) FILTER (WHERE is_current) AS current_rows,
       MIN(id) AS min_id,
       MAX(id) AS max_id,
       COUNT(*) FILTER (
         WHERE output_schema_version <> 1
            OR body_zh_cn IS NOT NULL
            OR llm_model_name IS NOT NULL
            OR observations_en <> '[]'::jsonb
            OR observations_zh_cn <> '[]'::jsonb
            OR selected_candidate_ids <> '[]'::jsonb
            OR claims <> '[]'::jsonb
       ) AS unexpected_canonical_rows
FROM trend_narratives;

SELECT COUNT(*) AS subjects,
       COUNT(DISTINCT trend_narrative_id) AS narratives_with_subjects
FROM trend_narrative_subjects;

SELECT COUNT(*) AS invalid_subject_positions
FROM trend_narrative_subjects
WHERE position NOT IN (0, 1);
```

The expected catalog result is parent and subject relations with `relkind =
'r'` and the legacy name with `relkind = 'v'`. Parent row count, current count,
and ID bounds must match the pre-migration values; unexpected canonical rows,
subjects, narratives with subjects, and invalid positions must all be zero
while controls remain off. The historical migration-0013 ORM
smoke test must still perform `SELECT`, `INSERT ... RETURNING`, `UPDATE`, and
`DELETE` through the compatibility view.

Operational rollback is code/config rollback with the expanded schema and
data left in place. Migration reversal is allowed only before any schema-two
publication, canonical-only write, or normalized subject exists. A reverse
guard runs before destructive operations and refuses reversal when canonical
output, failure counters, or any normalized subject exists. If that
guard refuses, stop: do not drop the subject table or compatibility view, and
restore the prior application revision against the expanded schema.

The local PostgreSQL migration suite proves fresh installation, migration 0013
to 0014 with parent preservation and no legacy-row rewrite, historical-ORM writes through
the view, subject constraints and `SET NULL` snapshots, and refusal before a
destructive reverse. Together with lifecycle/projection/status tests, this
checkpoint executes 39 tests with 39 passing and zero required-PostgreSQL
skips or errors.

Final post-review verification on 2026-08-13 expanded this evidence to 190
focused tests with 118 required PostgreSQL tests, zero skips, and zero errors.
The complete V22 browser file passed 22 tests plus six subtests; the shared
JavaScript runtime passed 42 focused assertions. `makemigrations --check`,
changed-feature Ruff, `git diff --check`, the literal-prompt equality check,
and `render blueprints validate render.yaml` also passed. No production
migration, Render sync, provider request, commit, or push occurred during this
verification.

The repository-wide suite remains independently non-green before feature test
execution because three unrelated baseline files fail collection (two stale
imports and one indentation error). A fourth unrelated configuration test
still expects retired Q1-Q6 call IDs while current source uses A/B/C IDs. These
pre-existing failures were not changed to make this feature appear green.
