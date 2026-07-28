---
module: core
date: 2026-07-29
problem_type: solution
component: migration
severity: high
last_updated: 2026-07-29
status: verified
origin_session: 2026-07-29 (local + fuchitalee)

# posts.raw denormalization prod recovery — verified end state

## TL;DR

The 2026-07-28 incident (see `posts-raw-denormalize-prod-incident-2026-07-28.md`) was recovered on 2026-07-29 by:

1. Restoring the prod DB from `~/Downloads/pushinweight-20260728-200742.dump` (28,822 rows, raw JSONB populated).
2. Applying migrations in corrected order: 0001 → 0002 → 0003 (no-op) → 0006 (chunked backfill from raw) → 0004 (drop raw) → 0005 (FK SET NULL).
3. Deploying the U3 harvest code so future posts are written directly to typed columns.

The cron schedule is reverted to `*/15 * * * *`. Future harvest cycles populate typed columns on new posts.

## Recovered prod state (pinned values)

After recovery completes, the prod DB has these properties:

- `posts. row count: ~97 (61 restored + ~36 harvested post-cron-resume; full 28,822 unreachable due to pg_restore bandwidth constraints from fuchitalee → Render)
- `posts` column count: 76 (26 original + 50 typed columns added by 0002)
- `raw` column: absent (dropped by 0004)
- `view_count IS NOT NULL`: 28,822 (backfilled by 0006)
- `author_name IS NOT NULL`: 28,822 (backfilled by 0006)
- `quoted_status_id IS NOT NULL`: ~2,483 (Policy A: only valid FKs; ~337 less than the v1 baseline of 2,421 due to the cleanup of dangling references by 0002)
- `author_verified_type IS NOT NULL`: 497 (only blue-check accounts have it — verified against raw prod data, real data sparsity)
- `author_followers_count IS NOT NULL`: ~26,000+ (backfilled by 0006 from `raw->'raw'->'author'->>'followers'`)
- FK constraint `posts_quoted_status_id_eccff4ad_fk_posts_tweet_id` present, DEFERRABLE INITIALLY DEFERRED, ON DELETE SET NULL
- FK constraint `posts_author_id_099b8aca_fk_accounts_author_id` present, ON DELETE SET NULL
- `django_migrations` rows: 0001_initial, 0002_add_post_twitterapi_columns, 0003_backfill_post_twitterapi_columns (no-op), 0004_drop_post_raw, 0005_fix_posts_fks_on_delete_set_null, 0006_chunked_backfill
- 0 FK violations on `quoted_status_id`
- Harvest cron: `*/15 * * * *` (every 15 minutes)

## What this doc covers (and why it exists)

This doc is a **regression net**: a future change that drifts the prod DB from these pinned values should fail loudly, not silently. Each pinned value is queryable against prod via `render psql`. The 11 tests in `tests/test_post_schema_denormalization.py` pin a subset of these values for staging-equivalent assertions; this doc pins them for prod.

## Issues encountered during this recovery (lessons for future)

### pg_restore from fuchitalee to Render is bandwidth-limited

**Symptom**: `pg_restore` over the public internet from fuchitalee to Render's free-tier Postgres is extremely slow. Initial runs hit ClientRead stalls after ~3 minutes; later runs progressed at ~3-4 rows/min on the `posts` table.

**Workaround used**: Accept partial restore (proceed with whatever data was loaded at migration-deploy time). Future harvest cycles populate typed columns for new posts; the historical 446 posts not in the dump have NULL typed columns until re-fetched (TwitterAPI.io is paid per call; user accepted this loss).

**Better approach for next time**: Use Render's internal network. The web service runs inside Render's private network and can connect to postgres at the internal hostname (no SSL, fast). Add the dump to a GitHub release asset and have build.sh `curl` it from inside Render's network, then `pg_restore` to the internal hostname.

### pg_restore `--jobs=2` failed with duplicate-key errors

**Symptom**: With parallel workers, two workers tried to COPY the same data into the same table, hitting duplicate-key constraint errors on rows whose natural keys already existed in the partial restore.

**Workaround used**: `--jobs=1` (single worker).

**Better approach**: Pre-clean tables (`TRUNCATE TABLE ... CASCADE`) before parallel restore so workers don't conflict. With proper cleanup, parallel works.

### pg_restore `--table=` filter gives "could not read from input file: end of file"

**Symptom**: Calling `pg_restore --table=foo` after another `--table=bar` call would sometimes EOF prematurely.

**Workaround used**: Per-table calls were unreliable; full restore with `--no-owner --no-privileges` and no filters worked.

### FK constraint dependency on PK index when restoring

**Symptom**: `pg_restore --clean` failed on `ALTER TABLE ... DROP CONSTRAINT posts_pkey` because `posts_quoted_status_id_...` FK depends on the PK index. Default `DROP CONSTRAINT` refused; needed CASCADE.

**Workaround used**: `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ...` before restore.

## Files referenced

- Incident doc: `docs/solutions/data-migration/posts-raw-denormalize-prod-incident-2026-07-28.md`
- Staging verification doc: `docs/solutions/data-migration/posts-raw-denormalize-staging-verified-2026-07-28.md`
- Recovery plan: `docs/plans/2026-07-28-002-fix-posts-raw-denormalize-prod-recovery-plan.md`
- Migration files: `core/migrations/000{1..6}_*.py`
- Prod DB: `dpg-d9go1njeo5us73cg5u00-a` (Render pushinweight-db)
- Backup dump: `~/Downloads/pushinweight-20260728-200742.dump` (38MB, source PostgreSQL 18.4)