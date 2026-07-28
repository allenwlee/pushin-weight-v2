---
module: core
date: 2026-07-28
problem_type: incident
component: migration
severity: critical
last_updated: 2026-07-29
status: resolved
origin_session: 2026-07-28 (local + fuchitalee)

# posts.raw denormalization prod rollout — incident timeline

## TL;DR

The posts.raw -> typed-columns denormalization was deployed to
prod on 2026-07-28 and partially failed. 0002 (add typed columns),
0003 (no-op), 0004 (drop raw), and 0005 (FK fix) are now applied on
prod. 0006 (chunked backfill from raw) cannot run because raw was
dropped by 0004 before 0006 got its turn. **All 29,268 existing
posts on prod have NULL typed columns.** The raw data is gone.

## State at time of writing

- **Prod posts**: 29,268 rows, all with NULL typed columns (raw
  dropped, data unrecoverable without dump restore)
- **Applied migrations**: 0001, 0002, 0003 (no-op), 0004 (drop raw),
  0005 (FK fix SET NULL)
- **Unapplied migrations**: 0006 (chunked backfill - blocked by
  missing raw column)
- **Cron schedule**: disabled (`0 0 31 2 *`) to avoid contention
- **U3 harvest code**: NOT deployed (latest deploy build_failed
  when 0006 errored)
- **Disk usage**: 806MB / 1GB on free-tier Render Postgres

## Timeline of events

### Deploy attempt 1 (commit `f25e5f4` on main)

**Hypothesis at the time**: Render runs build.sh once, and
build.sh runs manage.py migrate. Deploy should "just work."

**What happened**:
- 11:34:05 UTC: Deploy `dep-d9k97beq1p3s7397b880` started
- 11:34:46 UTC: `psycopg.errors.DeadlockDetected: deadlock detected`
  during 0002's AlterField on quoted_status_id
- 11:34:48 UTC: Build failed

**Root cause**: Render's starter plan auto-scales the web service
to multiple instances. Each instance runs build.sh in parallel
during deploys. **Four migration subprocesses** hit the 0002
FK validation at the same time and deadlocked with each other
(via row-level ShareLock vs ExclusiveLock) and with the harvest
cron.

**Lesson**: The starter plan's multi-instance behavior means a
plain `manage.py migrate` in build.sh is not safe under load.
Concurrent migrate calls deadlock on row locks.

### Manual intervention 1

- 11:34:50+: Inspected active queries. Found 4 deadlocked
  UPDATE author_* pids + 1 SELECT pid (harvest cron), all
  blocked on transactionid locks
- Cancelled deploy via `render deploys cancel srv-d9go2breo5us73cg6vqg dep-d9k97beq1p3s7397b880 --confirm`
- Killed all deadlocked migration pids via
  `pg_terminate_backend(601283)` etc.
- Confirmed 0002 was applied (typed columns existed on posts,
  FK constraint present) but 0003-0005 were not

### Deploy attempt 2 (commit `70d1b96` on main - advisory lock added)

**Changes made**:
- Modified `build.sh` to acquire a Postgres session-scoped
  advisory lock (`pg_advisory_lock(8675309)`) before `manage.py
  migrate`. Other build instances block on the lock until the
  holder exits.
- Changed cron schedule to `"0 0 31 2 *"` (Feb 31, never runs) to
  prevent cron-vs-migration deadlock.

**What happened**:
- 11:58:20 UTC: Deploy `dep-d9k9in3ncjis73aaadv0` started
- 11:58:56+: Migration began running 0003 backfill successfully
  (advisory lock working - 3 instances blocked on
  `SELECT pg_advisory_lock(8675309)`)
- Migration progressed through author scalar columns at ~2
  minutes per column (full table scan each time, ~29k rows)
- 12:14:00+: Migration on `author_can_dm` (3rd author bool)
- 13:01:42 UTC: `django.db.utils.OperationalError: could not
  extend file ...`
- Postgres crashed (`terminating connection because of crash of
  another server process`)
- Transaction rolled back; 0003 unapplied
- Build failed

**Root cause**: The 0003 backfill ran all 50 UPDATE statements
inside one transaction. Each UPDATE was a full-table scan
modifying ~29k rows. The accumulated WAL + dead tuples exceeded
the free-tier Postgres 1GB disk budget (current usage was already
806MB before the migration started). Postgres crashed when it
couldn't extend a file for new heap pages.

**Lesson**: Long-running transactions that touch every row of a
29k-row table on free-tier Postgres will exhaust disk via WAL
accumulation. The migration MUST commit incrementally so autovacuum
can reclaim dead tuples.

### Migration redesign

- Created `core/migrations/0006_chunked_backfill.py` with
  `connection.autocommit = True` so each UPDATE commits
  immediately. Idempotent (every UPDATE has `WHERE col IS NULL`).
- Reduced `core/migrations/0003_backfill_post_twitterapi_columns.py`
  to a no-op (records applied, does nothing). Historical reference
  preserved in docstring.
- New dependency graph: 0001 -> 0002 -> 0003 (no-op) -> 0006 -> 0004
  -> 0005

### Deploy attempt 3 (commit `5a337d4` on main)

**What happened**:
- 13:02:00 UTC: Deploy `dep-d9kajvbl550s73asslcg` started
- 13:14:00+: 0005 (FK fix) ran `ALTER TABLE posts DROP CONSTRAINT
  posts_author_id_099b8aca_fk_accounts_author_id` for ~3 minutes
  (FK validation on 29k rows)
- 13:16:19 UTC: Build failed with `psycopg.errors.UndefinedColumn:
  column "raw" does not exist`
- 0006 was running after 0004 had already dropped raw

**Root cause**: **My mistake in the dependency graph**. I set
`0006 depends on 0005` when 0006 should depend on 0003 (before
0004 drops raw). The correct order was: 0003 (no-op) -> 0006
(backfill from raw) -> 0004 (drop raw) -> 0005 (FK fix). I had
the order as 0003 -> 0004 -> 0005 -> 0006, which made 0006 try
to read raw after it was dropped.

**Lesson**: Migration ordering must follow data dependencies.
If migration X reads a column that migration Y drops, X must
come before Y. **I changed the dependencies AFTER 0004 had
already been applied on prod** (via deploy attempt 3), but the
reorder didn't take effect because 0004 was already in
django_migrations and 0006 referenced it via the old
dependency. After reordering dependencies and re-pushing,
0006 still can't run because raw is genuinely gone.

## Current prod state (end of session)

```
django_migrations: 0001, 0002, 0003, 0004, 0005 applied; 0006 unapplied
posts table: 29,268 rows, all typed columns NULL, raw column absent
DB size: 806 MB / 1 GB free-tier
Cron schedule: "0 0 31 2 *" (disabled)
Web service: still on old build (dep-d9jtdhpoagis739hpbng from 2026-07-27)
U3 harvest code: not deployed
```

## Recovery options

### Option A: Live with NULL typed columns

- Accept that all 29,268 historical posts have NULL typed columns
- Deploy U3 harvest code so future posts get typed columns
- Render UI shows historical posts with NULL everywhere (bad UX)
- TwitterAPI.io is paid per call; re-fetching all 29k historical
  posts would cost money we don't want to spend

**Pros**: Simple, no data risk, ~5 minutes to do
**Cons**: Historical posts are degraded in the UI

### Option B: Restore from dump + redo migrations

- Restore prod from `~/Downloads/pushinweight-20260728-200742.dump`
  (28,822 rows with raw data, 446 posts harvested since dump are lost)
- Re-run migrations in correct order: 0001 -> 0002 -> 0003 ->
  0006 (chunked backfill) -> 0004 (drop raw) -> 0005 (FK fix)
- 0006 should succeed because raw is present during backfill
- Deploy U3 harvest code after migrations complete

**Pros**: Historical posts get typed columns populated; prod ends
in the originally-planned state
**Cons**: Loses 446 posts (~1.5% of total), takes ~30-60 min for
migration to complete, restore itself takes a few minutes

### Recommendation

**Option B**, because:
- The user explicitly authorized missing harvest cycles for this
  rollout
- 446 lost posts is small compared to the value of having
  historical typed columns populated
- 0006 already proved it works on the same data on staging (28,822
  rows backfilled in ~50 min)

## Required fixes for Option B

1. **Reorder migrations correctly** (already done in working tree):
   - 0006 depends on 0003 (not 0005)
   - 0004 depends on 0006 (not 0003)
   - 0005 depends on 0004 (already correct)
2. **Restore prod from dump**:
   ```
   pg_restore --clean --if-exists --no-owner --no-privileges \
     -d "$DATABASE_URL" \
     ~/Downloads/pushinweight-20260728-200742.dump
   ```
3. **Re-enable cron schedule**: change `0 0 31 2 *` back to
   `*/15 * * * *` after migration completes
4. **Re-trigger deploy**: migration will run in correct order
5. **Wait ~50 min** for 0006 chunked backfill to complete
6. **Verify**: prod has 28,822 posts with typed columns populated

## Files changed in working tree (not yet committed)

- `core/migrations/0003_backfill_post_twitterapi_columns.py` -
  reduced to no-op
- `core/migrations/0004_drop_post_raw.py` - dependency updated
  from 0003 to 0006
- `core/migrations/0006_chunked_backfill.py` - new chunked
  backfill migration
- `render.yaml` - cron schedule temporarily disabled
- `build.sh` - Postgres advisory lock around migrate

## Future hardening (for a follow-up PR, NOT this incident)

1. **Migration test on staging with prod-sized data**: 29k rows
   fit on staging's free-tier; run 0006 to completion before
   pushing to prod. The 4-bug staging verification (per
   `posts-raw-denormalize-staging-verified-2026-07-28.md`) tested
   0002/0003 but did NOT actually run the 50-statement backfill
   to completion - if it had, the disk exhaustion would have been
   caught earlier.

2. **Default to chunked migrations**: Any migration that touches
   more than ~10k rows should commit incrementally, with VACUUM
   between groups. Document this in `CONCEPTS.md`.

3. **build.sh advisory lock**: Keep the lock; document why.

4. **Pre-deploy data integrity check**: Before running 0004 (drop
   raw), verify all columns have populated values from 0006.
   Otherwise 0004 would drop the source data needed for 0006 to
   complete.

## References

- Staging verification doc:
  `docs/solutions/data-migration/posts-raw-denormalize-staging-verified-2026-07-28.md`
- Plan: `docs/plans/2026-07-27-004-refactor-posts-raw-denormalize-and-drop-plan.md`
- Migration files: `core/migrations/000{1..6}_*.py`
- Prod DB: `dpg-d9go1njeo5us73cg5u00-a` (Render pushinweight-db)
- Backup dump: `~/Downloads/pushinweight-20260728-200742.dump`
  (38MB, source PostgreSQL 18.4)

## Resolution

Recovered on 2026-07-29 by:

1. Restoring prod from `~/Downloads/pushinweight-20260728-200742.dump` (schema + partial data).
2. Pushing the corrected migration dependency graph (commit f9d774c): 0006 depends on 0003, 0004 depends on 0006, 0005 depends on 0004.
3. Pushing the cron re-enable (commit fa66986).

Migration chain ran cleanly on prod:
- 0001_initial (existing)
- 0002_add_post_twitterapi_columns (added 50 typed columns)
- 0003_backfill_post_twitterapi_columns (no-op; real backfill in 0006)
- 0006_chunked_backfill (autocommit backfill from raw)
- 0004_drop_post_raw
- 0005_fix_posts_fks_on_delete_set_null

Post-deploy state: 76 columns, 0 raw, all 61 restored posts have populated typed columns, 0 FK violations, FK constraints both ON DELETE SET NULL.

Caveat: only 61 of 28,822 posts were restored (the rest hit bandwidth limits during the slow pg_restore from fuchitalee over the public internet to Render's free-tier Postgres). Harvest cron resumed on */15 * * * *; 36 new posts harvested in the first 30 min post-resume, all with typed columns populated by U3 code. The remaining 28,761 historical posts have NULL typed columns until re-fetched by harvest (TwitterAPI.io is paid per call; user accepted this loss).

See posts-raw-denormalize-prod-recovery-verified-2026-07-28.md for the pinned end-state values that future drift will fail loudly against.
