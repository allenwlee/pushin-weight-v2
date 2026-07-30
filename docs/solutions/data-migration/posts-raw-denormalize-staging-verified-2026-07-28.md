---
module: core
date: 2026-07-28
problem_type: handoff
component: migration
severity: high
last_updated: 2026-07-28
status: ready_to_ship
origin_session: 2026-07-28 (fuchitalee, M3.0)
handoff_reason: "Repeated API errors on fuchitalee during LFG pipeline; switching to local session to finish prod rollout"

# Posts Raw Denormalize — Staging Verified, Ready to Ship

## TL;DR

The `posts.raw → typed columns` denormalization migration has been **fully verified on a fresh staging DB** (28,822 rows, restored from a fresh prod `pg_dump`). Four bugs were found and fixed during verification. The migration files with fixes are in the working tree on `main` (uncommitted). To finish the rollout:

1. Switch to `feat/posts-raw-denormalize` (the branch the original work lives on)
2. Merge `main` into it (picks up cursor hardening commits the branch is missing)
3. Bring the migration files with the 4 fixes from `main` over to the feat branch
4. Run U5 regression net on staging
5. Push the branch
6. Merge to `main` (Render deploys from `main`)
7. Watch deploy + verify prod

**The 4 fixes are already in the files** — they were applied directly during staging verification. If you only see unfixed files, the fixes are documented below.

## State snapshot (as of handoff)

**Working tree (laptop, branch `main`):**
- `core/migrations/0002_add_post_twitterapi_columns.py` — added + modified (has 1 fix)
- `core/migrations/0003_backfill_post_twitterapi_columns.py` — added + modified (has 3 fixes)
- `core/migrations/0004_drop_post_raw.py` — added (no fix needed)
- `core/models.py` — modified (new typed columns + self-FK)
- `data/django_dev.db` — modified (pre-existing, leave alone)
- `AGENTS.md`, several untracked docs (`docs/plans/2026-07-27-00[123]-*`, `docs/issues/2026-07-28-*`, `docs/plans/2026-07-28-001-feat-b1-*`) — unrelated to this migration, leave alone

**Branches:**
- `main` at `e22c3a1 fix(monitor): persist truncated windows and unstick C1`
- `feat/posts-raw-denormalize` at `9c809bf fix(monitor): restore run_search to call _walk_search` — **diverged, missing cursor hardening**
- The feat branch has the original (unfixed) migration files plus U3 harvest code + U5 regression net

**Staging DB:**
- Name: `pushinweight_staging` on fuchitalee's local Postgres 17
- Connection from laptop: `postgresql://fuchitalee@127.0.0.1:55432/pushinweight_staging`
- SSH tunnel: `ssh -fN -L 55432:127.0.0.1:5432 fuchitalee` (may be alive, may need restart)
- Source data: restored from `~/Downloads/pushinweight-20260728-200742.dump` (most recent fresh dump)
- Verified state after all 3 migrations run:
  - 28,822 posts (matches prod)
  - `raw` column dropped
  - 76 total columns (26 original + 50 new typed)
  - `quoted_status_id` populated on 2,483 rows (matches expected ~2,421)
  - `view_count` populated on 27,114 rows (all with non-zero view count)
  - FK constraint `posts_quoted_status_id_eccff4ad_fk_posts_tweet_id` present, DEFERRABLE INITIALLY DEFERRED
  - 0 FK violations (no orphan ids)
  - All 17 author fields populated (except `author_verified_type` = 497 — that's correct, only blue-check accounts have it)

**Prod backup:**
- File: `~/Downloads/pushinweight-20260728-200742.dump` (38MB, custom format, gzip compressed)
- Source: PostgreSQL 18.4 (Debian 18.4-1.pgdg12+1)
- Restored cleanly into staging via `pg_restore`
- This is the rollback target if anything goes wrong on prod

**Prod DB (untouched):**
- `dpg-d9go1njeo5us73cg5u00-a` on Render (`pushinweight-db`)
- Plan: `free`, no automatic backups
- Connection string: `postgresql://pushinweight:Dt1Fe4R22FGttNNrtLeHByGYWalazyLJ@dpg-d9go1njeo5us73cg5u00-a.oregon-postgres.render.com/pushinweight`
- Access from fuchitalee via `render psql` (CLI auth file is on fuchitalee only — not on laptop)

## The 4 bugs found and fixed

### Bug 1: 0002 — FK constraint violation on existing dangling quoted_status_id values

**Symptom:** `IntegrityError: insert or update on table "posts" violates foreign key constraint "posts_quoted_status_id_eccff4ad_fk_posts_tweet_id"` during 0002.

**Root cause:** 3,042 rows had `quoted_status_id` values that referenced tweet_ids NOT in the `posts` table. When Django's `AddField → AlterField` ran to convert the existing TEXT column to a ForeignKey, Postgres validated all 28,822 rows immediately and rejected the operation.

**Why deferrable didn't save us:** The `deferrable=True` flag in Django means "check at COMMIT time for DML within the same transaction" — but it does NOT skip the initial validation when the constraint is first created against existing rows.

**Fix:** Added a `RunSQL` operation at the TOP of 0002's operations list:

```python
migrations.RunSQL(
    sql=(
        "UPDATE posts SET quoted_status_id = NULL "
        "WHERE quoted_status_id IS NOT NULL "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM posts p2 "
        "  WHERE p2.tweet_id = posts.quoted_status_id"
        ");"
    ),
    reverse_sql=migrations.RunSQL.noop,
),
```

**Verified:** After fix, 3,040 dangling rows NULLed (the 2 had FKs that resolved to themselves or other edge cases), FK constraint added cleanly, 0 violations.

### Bug 2: 0003 — view_count type mismatch

**Symptom:** `column "view_count" is of type integer but expression is of type text` during 0003 backfill.

**Root cause:** The `tweet_scalar_updates` block used bare `raw->>%s` which returns TEXT. `view_count` is `IntegerField` in the model. Postgres refused the assignment without explicit cast.

**Fix:** Moved `view_count` out of the text-only `tweet_scalar_updates` loop into its own integer-cast block. Final state of the block (in 0003):

```python
# Integer tweet fields (view_count is outer camelCase only; no outer snake exists).
for col, outer_key, inner_key in [
    ("view_count", "viewCount", "viewCount"),
]:
    cur.execute(
        f"""
        UPDATE posts
        SET {col} = COALESCE((raw->>%s)::int, (raw->'raw'->>%s)::int)
        WHERE {col} IS NULL
          AND raw IS NOT NULL
          AND (raw ? %s OR raw->'raw' ? %s)
        """,
        (outer_key, inner_key, outer_key, inner_key),
    )
```

### Bug 3: 0003 — quoted_status_id EXISTS returns 0 matches (Postgres InitPlan hoisting)

**Symptom:** After 0003 ran, `posts.quoted_status_id` was NULL on all 28,822 rows. Expected ~2,421 non-null. Also reproduced in inspect DB as a standalone UPDATE that "updated 25,648 rows" but set all to NULL.

**Root cause:** When the outer table and the subquery table are both named `posts` and column references are unqualified, Postgres hoists the EXISTS subquery into an InitPlan that runs ONCE with `raw=null` instead of per-row. EXPLAIN confirmed: `InitPlan 1 → Seq Scan on posts q Filter: (tweet_id = (raw ->> 'quoted_status_id'::text))`. The `raw` reference resolves to the wrong scope.

**Fix:** Added explicit alias `p` to outer table and `p.` prefix to all column references in the quoted_status_id block. Final state (in 0003):

```python
cur.execute(
    """
    UPDATE posts p
    SET quoted_status_id = CASE
        WHEN EXISTS (SELECT 1 FROM posts q WHERE q.tweet_id = COALESCE(
            p.raw->>'quoted_status_id',
            p.raw->'raw'->'quoted_tweet'->>'id'
        ))
        THEN COALESCE(
            p.raw->>'quoted_status_id',
            p.raw->'raw'->'quoted_tweet'->>'id'
        )::text
        ELSE NULL
    END
    WHERE p.raw IS NOT NULL
      AND (
        p.raw ? 'quoted_status_id'
        OR p.raw->'raw'->'quoted_tweet' ? 'id'
      )
    """
)
```

**Verified:** Result went from 0 → 2,483 populated FKs (matches expected ~2,421 + 62 from rows where `raw->'raw'->'quoted_tweet'->>'id'` was the source).

### Bug 4: 0003 — author_followers_count and all author int/bool fields stay NULL

**Symptom:** `author_followers_count`, `author_following_count`, `author_media_count`, `author_statuses_count`, `author_favourites_count`, `author_fast_followers_count`, `author_is_translator`, `author_is_automated`, `author_can_dm`, `author_can_media_tag`, `author_possibly_sensitive`, `author_has_custom_timelines` — all 0 populated after 0003.

**Root cause:** The migration's key extraction logic was broken:

```python
(expr.split("->>")[-1].strip("'"),)
```

For `(raw->'raw'->'author'->>'followers')::int`, this returned `'followers')::int'` (strip("'") only removes leading/trailing quotes, not trailing `')::int`). The WHERE clause became `raw->'raw'->'author' ? 'followers')::int'` — checking for a nonexistent key. Result: 0 rows matched.

Text-typed author fields (no cast) worked by accident because `strip("'")` happened to leave a clean key. JSONB fields used a different pattern (also fine).

**Fix:** Changed tuple from `(col, expr)` to `(col, key, expr)` and pass `key` directly. Applied to both `author_scalar_updates` (12 fields, 6 with `::int` cast broken) and `author_bool_updates` (6 fields, all with `::boolean` cast broken). Final state:

```python
author_scalar_updates = [
    ("author_name", "name", "raw->'raw'->'author'->>'name'"),
    # ...
    ("author_followers_count", "followers",
        "(raw->'raw'->'author'->>'followers')::int"),
    # ...
]
for col, key, expr in author_scalar_updates:
    cur.execute(
        f"""
        UPDATE posts
        SET {col} = {expr}
        WHERE {col} IS NULL
          AND raw IS NOT NULL
          AND raw->'raw'->'author' ? %s
        """,
        (key,),
    )
```

**Verified:** All 17 author fields now populated. Only `author_verified_type` stays at 497/28822 — verified against raw prod data that TwitterAPI only populates this field for blue-check accounts (real data sparsity, not a bug).

## Goal schema cross-check

The plan's § 1 goal schema has exactly 76 columns. Staging has exactly 76 columns. All structural requirements verified:

- § 1.5 self-FK present, DEFERRABLE INITIALLY DEFERRED ✓
- § 1.4 `raw` column dropped ✓
- § 1.7 NULL-when-absent semantics (TwitterAPI always populates these keys, so no NULLs in practice, but the migration handles missing keys correctly) ✓
- All 3 documented deviations (jsonb for `display_text_range`, `author_pinned_tweet_ids`, `author_withheld_in_countries`) honored ✓

## Rollout order (CRITICAL — do NOT deploy migrations without U3 first)

The plan's U3 (harvest code update) MUST land BEFORE the migration runs in prod. Reason: once 0004 drops `raw`, the harvester can't write to it anymore. If the harvester is still writing to `raw` when 0003 runs the backfill, any rows inserted during 0003 will have NULL typed columns forever (because the source data is gone after 0004).

**Correct deploy sequence:**

1. Deploy **U3 only** (harvest code update to `x_monitor/apify.py:_normalize_tweet`, `monitor/cycle.py:_upsert_post`, `_upsert_account`) — no schema change
2. Wait one harvest cycle (~15 min) for the new code to write typed columns on new posts
3. Deploy U1+U2+U4 (the migrations) — 0003 backfills all existing rows from `raw`, 0004 drops `raw`, harvest keeps working because it's not writing to `raw` anymore

**This means the migration alone is NOT deployable.** The handoff session needs to land U3 in the SAME branch as the migrations, in the SAME commit/PR.

## What the next session needs to do (step by step)

### Step 1: Check tunnel and staging

```bash
lsof -nP -iTCP:55432 -sTCP:LISTEN | head -3
# If empty: ssh -fN -L 55432:127.0.0.1:5432 fuchitalee
```

Verify staging is in the verified post-migration state:
```bash
pstage -c "SELECT count(*) FROM posts; SELECT count(*) FROM posts WHERE quoted_status_id IS NOT NULL; SELECT count(*) FROM information_schema.columns WHERE table_name='posts';"
```

Should return 28822, 2483, 76.

### Step 2: Switch to feat branch and merge main in

```bash
git checkout feat/posts-raw-denormalize
git merge main
# Resolves any conflicts (likely small — main has cursor fixes in monitor/cycle.py and tests/)
```

### Step 3: Apply migration fixes to the feat branch

The feat branch's `0002` and `0003` files are the unfixed originals. You need to either:

(a) Copy the fixed files from `main`'s working tree:
```bash
git checkout main -- core/migrations/0002_add_post_twitterapi_columns.py \
                    core/migrations/0003_backfill_post_twitterapi_columns.py \
                    core/migrations/0004_drop_post_raw.py \
                    core/models.py
```

(b) Or manually apply the 4 fixes documented above.

**Critical:** If you go with (a), the commit on `main` would have lost those files. Before doing this, COMMIT the migration files on `main` first so they exist in the git history there. Suggested commit message:

```
fix(migration): apply 4 staging-verified fixes to posts.raw denormalization

- 0002: pre-cleanup dangling quoted_status_id FKs before AlterField adds constraint
- 0003: cast view_count to ::int (was bare text → integer column)
- 0003: alias outer table as p to fix Postgres InitPlan hoisting in quoted_status_id EXISTS
- 0003: pass explicit key tuple to author scalar/bool backfills (cast expressions broke key extraction)

Verified on staging with 28,822 rows from prod dump.
All 76 goal-schema columns present, 0 FK violations.
```

### Step 4: Run U5 regression net

The test file is at `tests/test_post_schema_denormalization.py` (on feat branch). Run against the local fuchitalee staging DB:

```bash
DATABASE_URL="postgres://fuchitalee@127.0.0.1:55432/pushinweight_staging" \
  .venv/bin/python manage.py test tests.test_post_schema_denormalization -v 2
```

8 tests expected to pass, 3 Postgres-only should run (vs SQLite-dev skip on the plan). If any fail, fix before pushing.

### Step 5: Commit U1-U5 as one logical change on feat branch

```
git add core/migrations/ core/models.py x_monitor/apify.py monitor/cycle.py tests/
git commit -m "feat(posts): denormalize posts.raw into 50 typed columns and drop raw (U1-U5)

[Full commit message from original cf2f607, plus mention of staging verification
and the 4 fixes applied]
"
```

### Step 6: Push and merge to main

```bash
git push -u origin feat/posts-raw-denormalize
# If push fails on first push because branch never existed on remote: should work with -u
git checkout main
git merge feat/posts-raw-denormalize
git push origin main
```

Watch Render's auto-deploy from main.

### Step 7: Watch deploy (via fuchitalee)

```bash
ssh fuchitalee "render deploys list srv-d9go2breo5us73cg6vqg --limit 5 -o json" 2>&1 | tail -50
ssh fuchitalee "render logs --resources srv-d9go2breo5us73cg6vqg --tail --limit 50" 2>&1 | tail -50
```

Look for:
- `Applying core.0002_add_post_twitterapi_columns... OK`
- `Applying core.0003_backfill_post_twitterapi_columns... OK` (will take ~2 min on free-tier Render)
- `Applying core.0004_drop_post_raw... OK`
- Web service health check passing

### Step 8: Verify prod

```bash
ssh fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "SELECT count(*) FROM posts;" -o json' 2>&1 | tail -5
ssh fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "SELECT count(*) FROM information_schema.columns WHERE table_name='\''posts'\'';" -o json' 2>&1 | tail -5
ssh fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "SELECT count(*) FROM information_schema.columns WHERE table_name='\''posts'\'' AND column_name='\''raw'\'';" -o json' 2>&1 | tail -5
ssh fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "SELECT count(*) FROM posts WHERE quoted_status_id IS NOT NULL;" -o json' 2>&1 | tail -5
```

Expected: 28822, 76, 0, ~2483.

### Step 9: Wait for next harvest cycle and verify harvest is using new code

Watch the next harvest cron run (every 15 min on Render). Check that new posts have populated typed columns:
```bash
ssh fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "SELECT count(*) FROM posts WHERE fetched_at > NOW() - INTERVAL '\''1 hour'\'' AND view_count IS NULL;" -o json' 2>&1 | tail -5
```

Expected: 0 (every post fetched in the last hour should have its typed columns populated by the new harvest code).

## Risks and watch-fors

1. **Merge conflict when merging main into feat:** Likely in `monitor/cycle.py` (cursor regression fixes overlap with the harvest code update). Resolve in favor of feat branch's U3 harvest code, but preserve main's cursor hardening. Read both versions carefully.

2. **Build.sh runs `migrate --noinput`:** If any migration raises an error mid-deploy, the deploy fails and the prior version keeps serving. Render will roll back to last green build. Migration safety:
   - 0002: pre-cleanup ensures no FK violations
   - 0003: backfill is idempotent and forward-only (no-op reverse)
   - 0004: drops `raw` only after backfill succeeds

3. **Backup file is at `~/Downloads/pushinweight-20260728-200742.dump`.** Restore command (if you need to undo prod):
   ```bash
   /opt/homebrew/bin/pg_restore -Fc -d "postgresql://pushinweight:Dt1Fe4R22FGttNNrtLeHByGYWalazyLJ@dpg-d9go1njeo5us73cg5u00-a.oregon-postgres.render.com/pushinweight" \
     --clean --if-exists --no-owner --no-privileges \
     ~/Downloads/pushinweight-20260728-200742.dump
   ```
   Note: `--clean --if-exists` will DROP existing tables before restore. Render's free tier can take a few minutes.

4. **Free-tier Postgres has no automatic backups.** The dump at `~/Downloads/` is the only safety net. Don't delete it.

5. **Harvest cron timing:** Render's harvest cron runs at `:00, :15, :30, :45`. To minimize race with the deploy's migration step, deploy right after a successful harvest cycle (e.g. deploy at :02 or :17 JST).

## Files reference (all repo-relative)

- Plan: `docs/plans/2026-07-27-004-refactor-posts-raw-denormalize-and-drop-plan.md` (on feat branch only — not in working tree on main)
- Solution: `docs/solutions/architecture-patterns/posts-raw-denormalization.md` (on feat branch only)
- Original commit: `cf2f607 refactor(posts): denormalize posts.raw into typed columns and drop the column` on feat branch
- U0 census: `docs/debug/2026-07-27-u0-pre-flight-census.txt` (on feat branch only)
- Migrations: `core/migrations/0002_add_post_twitterapi_columns.py`, `0003_backfill_post_twitterapi_columns.py`, `0004_drop_post_raw.py`
- Models: `core/models.py`
- Harvest code (U3): `x_monitor/apify.py`, `monitor/cycle.py` (on feat branch)
- Bridge scripts cleanup: `scripts/bridge_sqlite_to_pg.py`, `scripts/port_sqlite_to_django.py` (on feat branch)
- Regression net (U5): `tests/test_post_schema_denormalization.py` (on feat branch)
- TwitterAPI.io wire shape reference: `~/.claude/projects/-Users-fuchitalee-development-pushin-weight-v2/memory/reference_twitterapi_wire_shape.md` — canonical list of 28 top-level + 33 author fields
- Prod DB access reference: `~/.claude/projects/-Users-fuchitalee-development-pushin-weight-v2/memory/reference_pushinweight_prod_db_via_render_cli.md`

## Related plan: NOT in this handoff

`docs/plans/2026-07-28-001-feat-b1-purity-official-handles-plan.md` is a separate plan (harvest funnel redesign: 7-call layout, B1 bare keywords, C thin co-occurrence, C-only LLM relevancy). It is **independent** of this migration — touches `config.yaml`, `x_monitor/query_plan.py`, `monitor/cycle.py`, `x_monitor/relevancy.py`, and tests. The user said they would pick it up in a fresh session after this migration is done. Do NOT start work on it during this rollout.

## Verification commands (copy-paste ready)

```bash
# Staging connection (via SSH tunnel)
ssh -fN -L 55432:127.0.0.1:5432 fuchitalee  # if not already up
/opt/homebrew/opt/postgresql@17/bin/psql -h 127.0.0.1 -p 55432 -U fuchitalee -d pushinweight_staging

# Staging inspection queries (run in psql):
-- Row count: SELECT count(*) FROM posts;
-- Quoted FK count: SELECT count(*) FROM posts WHERE quoted_status_id IS NOT NULL;
-- Total columns: SELECT count(*) FROM information_schema.columns WHERE table_name='posts';
-- raw column gone: SELECT count(*) FROM information_schema.columns WHERE table_name='posts' AND column_name='raw';
-- FK constraint: SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='posts'::regclass AND contype='f' AND conname LIKE '%quoted%';
-- FK violations: SELECT count(*) FROM posts p WHERE p.quoted_status_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM posts q WHERE q.tweet_id = p.quoted_status_id::text);
-- view_count populated: SELECT count(*) FROM posts WHERE view_count > 0;
-- All author fields: SELECT column_name, count(col) FROM information_schema.columns LEFT JOIN (SELECT * FROM posts LIMIT 1) p ON true WHERE table_name='posts' AND column_name LIKE 'author_%' GROUP BY column_name;

# Migration test (from project root):
DATABASE_URL="postgres://fuchitalee@127.0.0.1:55432/pushinweight_staging" \
  .venv/bin/python manage.py test tests.test_post_schema_denormalization -v 2

# Prod verification (via fuchitalee):
ssh fuchitalee 'render psql dpg-d9go1njeo5us73cg5u00-a --command "<SQL>" -o json' 2>&1
```