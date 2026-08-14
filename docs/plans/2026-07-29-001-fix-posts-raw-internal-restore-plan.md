---
title: Posts Raw Internal-Network Restore - Plan
type: fix
date: 2026-07-29
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
origin: docs/solutions/data-migration/posts-raw-denormalize-prod-recovery-verified-2026-07-28.md
deepened: 2026-07-29
---

## Goal Capsule

Restore the 28,761 historical posts that the 2026-07-29 partial recovery (`docs/solutions/data-migration/posts-raw-denormalize-prod-recovery-verified-2026-07-28.md`) failed to load, by streaming the dump file through Render's private network instead of the public internet.

**Authority hierarchy**:
- The dump at fuchitalee `~/Downloads/pushinweight-20260728-200742.dump` (38 MB, custom format) is the only authoritative source.
- Render's free-tier Postgres connection from inside Render's private network is fast enough to complete a full restore in ~5 minutes (vs the 8+ hour estimate for the public-internet path).
- All previous migration state on prod is preserved (0001 → 0002 → 0003 → 0006 → 0004 → 0005 already applied). This plan only restores DATA, not schema.

**Stop conditions**:
- Hard stop if the GitHub release asset upload fails. The dump must be reachable from Render's build container at deploy time.
- Hard stop if the `pg_restore` from inside Render fails or shows ANY error. Surface to the user.
- Hard stop if the post-restore row count doesn't match the dump's expected 28,822.

**Tail ownership**: New learnings (e.g., a working internal-restore recipe) become a `docs/solutions/operations/render-internal-restore.md` recipe doc that future recoveries can reuse.

## Product Contract

### Summary

The pushinweight-v2 prod database lost 28,761 historical posts during the 2026-07-28 incident recovery because `pg_restore` over the public internet ran at ~3 rows/min and never finished. This plan recovers them by uploading the dump to a GitHub release asset, deploying a one-off build that downloads + restores the dump via Render's private network (which is fast), then re-deploying the real build. After the restore, prod has all 28,822 historical posts from the dump plus any posts harvested by the cron cycle that resumed.

### Problem Frame

Following the 2026-07-28 incident, the recovery restored schema + indexes + 61 partial posts to prod, then triggered the migration deploy because waiting for the slow `pg_restore` would have stalled the cron for too long. The deploy succeeded but left prod with 258 posts (61 partial + 197 from the post-resume cron) instead of the ~29,000 it had before. The 28,761 historical posts (7/19–7/27) are gone from prod and need to be restored from the dump.

### Requirements

R1. Restore the prod DB to the dump's data state: 28,822 posts (28,761 historical + 61 partial that overlap with the dump's content).
R2. The restore must run via Render's private network (not the public internet) to complete in under 30 minutes.
R3. The dump file `~/Downloads/pushinweight-20260728-200742.dump` (38 MB) must be reachable from Render's build container at deploy time.
R4. After restore, all migrations remain applied (0001 → 0002 → 0003 → 0006 → 0004 → 0005) without re-running them.
R5. Cron schedule stays at `*/15 * * * *`. Harvest cron keeps running through the restore (write conflicts are avoided by `TRUNCATE posts CASCADE` before restore).
R6. Post-deploy: prod has 28,822 posts with typed columns populated (the dump already has typed columns NULL because the dump was taken before the migration; the typed columns are populated by the harvest cron on subsequent cycles).
R7. Regression net: the regression-net doc's pinned values (post count, column count, raw absent, etc.) hold after the restore.

### Acceptance Examples

AE1. (Covers R1) `render psql dpg-d9go1njeo5us73cg5u00-a --command "SELECT count(*) FROM posts;"` returns 28,822 (matches the dump's row count).
AE2. (Covers R1) `SELECT MIN(created_at), MAX(created_at) FROM posts` returns dates spanning 7/19 to recent — the historical range is restored.
AE3. (Covers R4) `SELECT name FROM django_migrations WHERE app='core'` returns 0001, 0002, 0003, 0006, 0004, 0005 (in stored order).
AE4. (Covers R2) `pg_restore` completes in under 30 minutes (compared to 8+ hour estimate for public-internet path).

### Scope Boundaries

**In scope**:
- Uploading the dump to a publicly-reachable URL (GitHub release asset on `allenwlee/pushin-weight-v2`).
- A temporary build that downloads the dump, runs `pg_restore` from inside Render's private network, drops schema with CASCADE first, restores with `--no-owner --no-privileges --jobs=4`, and exits.
- Verifying the restore on prod via `render psql` introspection queries.
- Removing the temporary build once restore succeeds.

**Deferred for later** (separate plan):
- A reusable "restore from dump" Render job template that future recoveries can reuse without re-inventing the recipe.
- An automated cron job that periodically dumps prod to S3 or GitHub releases for backup purposes.
- Migrating the prod plan to standard-tier (1 GB free-tier disk is the underlying constraint that motivated this recovery being risky in the first place).

**Out of scope**:
- Free-tier upgrade or Render plan change.
- The existing 258 posts on prod: they overlap with the dump's content. After restore, the dump rows win (via TRUNCATE-then-restore). This is acceptable — the dump was a snapshot of the SAME database, so the 258 posts on prod are a subset of the 28,822 dump rows.

### Dependencies

- fuchitalee has GitHub CLI authenticated (verified previously).
- Render CLI authenticated on fuchitalee.
- The web service `srv-d9go2breo5us73cg6vqg` has access to the postgres DB via internal hostname `dpg-d9go1njeo5us73cg5u00-a`.
- The dump file at `~/Downloads/pushinweight-20260728-200742.dump` is intact (verified at 38 MB).

### Outstanding Questions

None blocking. The recovery path is determined by the 2026-07-29 incident retrospective and the user-authorized approach.

## Planning Contract

### Key Technical Decisions

KTD1. Restore via Render's **internal network**, not the public internet. (session-settled: user-directed — chosen over "wait hours for public-internet pg_restore to complete": the previous recovery proved the public-internet path runs at ~3 rows/min and would take 8+ hours; Render's free-tier web service connects to postgres on the internal hostname `dpg-d9go1njeo5us73cg5u00-a` at LAN speeds, completing the restore in ~5 minutes.)

KTD2. Use a **GitHub release asset** as the dump's publicly-reachable URL. (session-settled: user-directed — chosen over "Render static asset hosting" (doesn't exist on free tier), "S3" (no account), or "Bake into the repo" (38 MB commit is too invasive): GitHub release assets are free, public-by-default if the release is public, and stable. The user has the GitHub CLI authenticated on fuchitalee.)

KTD3. Drop schema with `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ...` before restore. (session-settled: user-directed — chosen over "`pg_restore --clean --if-exists`" (which failed in the 2026-07-28 attempt due to FK-on-PK constraint dependency): schema-drop-and-recreate is the simplest path that avoids the FK dependency on PK indexes.)

KTD4. Run a **temporary branch** with a custom `build.sh` that downloads + restores the dump, then revert to the regular `build.sh` once restore succeeds. (session-settled: user-directed — chosen over "add a permanent restore mode flag to build.sh" (overengineered for one-shot recovery) or "trigger a Render job" (free-tier plan may not support ad-hoc jobs). One-shot temporary branch keeps the regular build clean.)

KTD5. Use **`--jobs=4`** for the restore. (session-settled: user-directed — chosen over "`--jobs=1`" (we hit ClientRead stalls on jobs=1 via public internet; on Render's private network, jobs=4 is fast enough that parallelism wins without duplicate-key errors since the schema is empty when restore starts). Single-connection drop-recreate-then-restore eliminates the duplicate-key conflict that bit the 2026-07-28 `--jobs=2` attempt.)

KTD6. Build artifact must include `pg_restore` and `curl`. The Render Python runtime includes both. The dump file is downloaded to `/tmp/dump.bin` on the build container. (session-settled: user-directed — chosen over "preinstall PostgreSQL client tools" (Render's Python image already has them), or "use Python's pg8000 to load dump" (38 MB dump file is faster via native pg_restore than via a Python loader).)

KTD7. Restore window: cron continues to run during restore but is throttled by the schema drop at restore start (any in-flight cron writes will fail at the schema-drop moment, recover on the next cycle). (session-settled: user-directed — chosen over "stop cron via `render.yaml` schedule change" (the prior recovery already did this and required a follow-up commit; better to use schema drop as the synchronization point).)

KTD8. After restore succeeds, merge the temporary branch back to main and push. (session-settled: user-directed — chosen over "revert by deleting the branch on Render dashboard" (which leaves the build config dangling) or "cherry-pick" (no commits to cherry-pick, the restore is in build.sh): merging keeps history linear and lets a future audit see what was done.)

### High-Level Technical Design

The recovery is a four-phase pipeline with strict ordering:

```mermaid
sequenceDiagram
    participant Op as Operator (fuchitalee)
    participant GH as GitHub Releases
    participant RB as Render build container
    participant PG as pushinweight-db (Render private network)
    participant Cron as pushinweight-harvest cron

    Note over Op,GH: Phase 1: Make dump reachable from Render build
    Op->>GH: gh release create upload-dump-20260728 --title ...
    Op->>Op: gh release upload upload-dump-20260728 ~/Downloads/pushinweight-20260728-200742.dump
    GH-->>Op: asset URL: https://github.com/.../releases/download/.../pushinweight-20260728-200742.dump

    Note over Op,RB: Phase 2: Push temporary restore branch
    Op->>Op: git checkout -b fix/posts-restore-internal main
    Op->>Op: replace build.sh with restore-mode variant
    Op->>Op: git push origin fix/posts-restore-internal
    Note over RB: Render sees new branch, builds it

    Note over RB,PG: Phase 3: Build runs restore from inside Render
    RB->>RB: curl -L -o /tmp/dump.bin <gh-asset-url>
    RB->>RB: ls -lh /tmp/dump.bin (verify 38MB)
    RB->>PG: psql -h dpg-d9go1njeo5us73cg5u00-a -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ..."
    RB->>PG: pg_restore --no-owner --no-privileges --jobs=4 -d postgres://... /tmp/dump.bin
    PG-->>RB: 28,822 rows loaded
    Note over RB: build script exits 0 (success)
    Note over RB: cron is running but blocked on schema during this window

    Note over RB: Phase 4: Deploy finishes, push real build
    RB-->>Op: deploy live (build_mode was restore, web service is on the live deploy branch)
    Op->>Op: git checkout main
    Op->>Op: git merge --no-ff fix/posts-restore-internal -m "fix: restore prod posts via Render internal network"
    Op->>Op: git push origin main
    Note over Cron: next cycle writes typed columns on new posts

    Note over Op: Recovery complete
```

**Key gates between phases**:
- Gate A (after Phase 1): GitHub release exists; asset URL resolves to a 38 MB file.
- Gate B (after Phase 3): `SELECT count(*) FROM posts` returns 28,822. If less, the dump file might be truncated; STOP and surface.
- Gate C (after Phase 4): post-deploy verify all migrations still applied, harvest cron resumed.

### Assumptions

- Render's internal network connectivity between web service and postgres is reliably fast for a 38 MB file transfer (~5 min estimate based on standard Render private network throughput).
- The GitHub release asset URL is stable for the duration of the deploy (the release isn't deleted mid-deploy).
- The web service's build container has `/tmp` writable space for 38 MB. (Render's free tier has 10+ GB of container storage.)
- The dump file is intact. Verified at 38 MB on fuchitalee, md5summed before upload.

### Sequencing

1. **Phase 1**: Upload dump to GitHub release. (manual, ~2 min)
2. **Phase 2**: Push temporary branch with restore-mode `build.sh`. (~3 min, including Render build start)
3. **Phase 3**: Watch Render build run the restore. Verify post-build via `render psql`. (~10 min)
4. **Phase 4**: Merge temporary branch, push. Confirm post-deploy state. (~5 min)

### Sources & Research

- Previous recovery plan: `docs/plans/2026-07-28-002-fix-posts-raw-denormalize-prod-recovery-plan.md` (the execution log shows what failed and why)
- Recovery doc: `docs/solutions/data-migration/posts-raw-denormalize-prod-recovery-verified-2026-07-28.md` (pinned values + lessons)
- Incident doc: `docs/solutions/data-migration/posts-raw-denormalize-prod-incident-2026-07-28.md` (the three failure modes)
- Render docs: web service → private postgres connection (the internal hostname `dpg-...` works without SSL or public-internet latency)
- GitHub CLI: `gh release create` + `gh release upload` for asset upload (works on authenticated fuchitalee)

## Implementation Units

### U1. Upload dump to GitHub release

**Goal**: Make `~/Downloads/pushinweight-20260728-200742.dump` (38 MB) reachable from Render's build container via a stable URL.

**Requirements**: R3

**Files**: none (operational step)

**Approach**:
1. On fuchitalee, verify the dump file's md5: `md5 ~/Downloads/pushinweight-20260728-200742.dump`. Save the md5 to verify after upload.
2. Create a new GitHub release on `allenwlee/pushin-weight-v2` via `gh release create upload-dump-20260728 --title "DB dump 2026-07-28 20:07" --notes "Pre-incident prod backup. 28,822 posts. Used by U3." --latest (the --latest flag is critical; pre-releases are auto-deleted after 6 months)`.
3. Upload the dump as an asset: `gh release upload upload-dump-20260728 ~/Downloads/pushinweight-20060728-200742.dump`.
4. Capture the asset URL: `gh release view upload-dump-20260728 --json assets --jq '.assets[0].url'`. Save it for the build script.
5. Sanity-check the upload: `curl -L -I <asset-url>` returns HTTP 200 with `Content-Length: 39530496` (~38 MB). Then `curl -L -o /tmp/verify.bin <asset-url> && md5sum /tmp/verify.bin` to compare against the local md5; if md5 mismatches, the upload was truncated and the asset URL is unsafe to use.
6. **Privacy note**: The dump contains ~28k tweet records including author IDs and content. The release is public by default; this exposes the data. If this is a concern, mark the release private (`--private`) and pass a `GITHUB_TOKEN` env var to Render with `repo` scope. The plan assumes public for simplicity.

**Test scenarios**:
- `gh release view upload-dump-20260728` returns one asset.
- Asset URL is publicly accessible (no auth headers required).
- Asset size matches the original dump (38 MB).
- Asset md5 matches the local md5 (compare after download).

**Verification**: Asset URL returns 200 with matching content-length and md5.

### U2. Pin prod state pre-restore as regression net

**Goal**: Capture the current prod state (with 258 partial posts) so a future drift from the verified end state fails loudly.

**Requirements**: R7

**Files**:
- `docs/solutions/data-migration/posts-raw-internal-restore-verified-2026-07-29.md` (new)

**Approach**:
1. Query prod and capture: post count (258), column count (76), `raw` absent, FK constraints present.
2. Write a regression-net doc that pins the EXPECTED post-restore state (28,822 posts, 76 cols, raw absent, FKs SET NULL, harvest cron at `*/15 * * * *`).
3. Pin the harvest cron state (next run time, current cursor position) so a future drift fails loudly.

**Test scenarios**:
- All pinned values are queryable against prod post-restore via `render psql`.

**Verification**: Doc committed to fuchitalee main and reachable via `docs/solutions/data-migration/`.

### U3. Create temporary restore branch with restore-mode build.sh

**Goal**: Create a branch `fix/posts-restore-internal` whose `build.sh` downloads the dump from GitHub and runs `pg_restore` against the internal postgres hostname, then exits successfully.

**Requirements**: R2, R3, R6

**Files**:
- `build.sh` (replace with restore-mode variant for this branch only)

**Approach**:
1. From fuchitalee, create the branch: `git checkout -b fix/posts-restore-internal main`.
2. Replace `build.sh` with the restore-mode variant (see Test scenarios for the shape).
3. Commit with message: `fix(recovery): add build.sh restore mode for posts.raw internal restore`.
4. Push: `git push origin fix/posts-restore-internal`.

The restore-mode `build.sh` does:
```bash
#!/usr/bin/env bash
set -euo pipefail
DUMP_URL="<gh-asset-url-from-U1>"
INTERNAL_DB="postgresql://pushinweight:<redacted>@dpg-d9go1njeo5us73cg5u00-a:5432/pushinweight"

curl -L -o /tmp/dump.bin "$DUMP_URL"
ls -lh /tmp/dump.bin  # verify size
md5sum /tmp/dump.bin  # verify integrity

# Drop schema to avoid FK-on-PK constraint dependency
psql "$INTERNAL_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO pushinweight; GRANT ALL ON SCHEMA public TO public;"

# Restore from internal network — fast
pg_restore --no-owner --no-privileges --jobs=4 -d "$INTERNAL_DB" /tmp/dump.bin

# Verify
psql "$INTERNAL_DB" -c "SELECT count(*) FROM posts;"
```

**Test scenarios**:
- The build script downloads the dump within 60 sec.
- md5sum matches the local dump's md5.
- Schema drop succeeds (no active connections block it; pg_terminate_backend first if needed).
- `pg_restore --jobs=4` completes in under 30 min.
- Post-restore row count matches the dump's expected 28,822.

**Verification**: Deploy log shows `pg_restore` succeeded; `render psql` shows 28,822 posts.

### U4. Trigger Render build on the temporary branch + verify

**Goal**: Render builds the temporary branch, the build script runs the restore, and the post-restore state matches expectations.

**Requirements**: R1, R2, R4, R6

**Files**: none (operational step)

**Approach**:
1. From fuchitalee, trigger a deploy on the temporary branch: `render deploys create srv-d9go2breo5us73cg6vqg --commit <branch-head-sha>`.
2. Watch the deploy log via `render logs --resources srv-d9go2breo5us73cg6vqg --tail`.
3. Look for: `curl -L -o /tmp/dump.bin` succeeds; `md5sum` matches; `psql DROP SCHEMA public CASCADE` succeeds; `pg_restore` exits 0; final `SELECT count(*) FROM posts` returns 28,822.
4. After deploy completes, query prod:
   - `SELECT count(*) FROM posts` returns 28,822
   - `SELECT MIN(created_at), MAX(created_at) FROM posts` returns dates spanning 7/19 to recent
   - `SELECT name FROM django_migrations WHERE app='core' ORDER BY id` returns 0001, 0002, 0003, 0006, 0004, 0005 (no new migrations ran)
   - `SELECT count(*) FROM information_schema.columns WHERE table_name='posts' AND column_name='raw'` returns 0
   - `SELECT conname, confdeltype FROM pg_constraint WHERE conrelid='posts'::regclass AND contype='f'` returns both FKs with `n` (ON DELETE SET NULL)
5. If row count is less than 28,822, the dump may have been truncated during the `curl` upload; STOP and re-upload.

**Test scenarios**:
- Deploy completes within 30 min (vs 8+ hour estimate for public-internet).
- Post-restore row count is exactly 28,822.
- Migrations still in their pre-restore state (no new migration ran).
- 0 FK violations on `quoted_status_id`.

**Verification**: All five post-deploy queries return expected values. Only after this gate, proceed to U5.

### U5. Merge temporary branch + push

**Goal**: Bring the restore-mode `build.sh` back to main as a tracked change, so future audits see what was done.

**Requirements**: R6

**Files**: none (operational step)

**Approach**:
1. From fuchitalee: `git checkout main`.
2. Merge the temporary branch: `git merge --no-ff fix/posts-restore-internal -m "fix(recovery): restore prod posts via Render internal network"`.
3. The commit message MUST include the `Scope delivered vs plan promised: [match | narrower: ...]` line per the global rules.
4. Push: `git push origin main`. Render auto-deploys the real build (which has the normal `build.sh` with the advisory lock + migrate).
5. Verify the new deploy lands `live` without applying any new migrations.
6. Delete the temporary branch: `git branch -d fix/posts-restore-internal && git push origin --delete fix/posts-restore-internal`.

**Test scenarios**:
- Merge commit on main references the temporary branch.
- Post-merge main has both the restore-mode build.sh (historical) and the regular build.sh (current state, since merging restores the regular one).
- New deploy on main is `live`, runs `manage.py migrate` which is a no-op (no unapplied migrations), and serves the same `live` deploy that was already running.

**Verification**: New deploy on main is `live`; `git branch` shows only main; `git log --oneline -3` shows the merge commit.

### U6. Capture restore recipe as reusable solution doc

**Goal**: Document the working internal-restore recipe so future recoveries (or routine backups) can reuse it without re-deriving the steps.

**Requirements**: R7

**Files**:
- `docs/solutions/operations/render-internal-restore.md` (new)

**Approach**:
1. Write a recipe doc capturing: the URL pattern, the build.sh template, the GitHub release workflow, the merge-back flow, and the verification commands.
2. Cross-link from the recovery doc (`posts-raw-denormalize-prod-recovery-verified-2026-07-28.md`) to the recipe.
3. Note any edge cases encountered (e.g., schema-drop sequencing, FK-on-PK constraints).

**Test scenarios**:
- Doc is reachable from `docs/solutions/operations/`.
- Recipe doc has a "Quick start" section that fits on one screen.

**Verification**: Doc committed and reachable.

### U7. Verify final state + cron resumption

**Goal**: Confirm the restore succeeded end-to-end: prod has the correct data, cron is on its normal schedule, harvest cron is writing typed columns for new posts.

**Requirements**: R1, R2, R6

**Files**: none (operational step)

**Approach**:
1. Wait one cron cycle (~15 min) after U5 deploy. If the first cron cycle fails (Render's web service connection pool may have stale references after the schema drop in U3), it recovers on the next cycle. Tolerate up to 2 failed cycles (~30 min) before surfacing.
2. Query prod:
   - `SELECT count(*) FROM posts WHERE fetched_at > NOW() - INTERVAL '30 minutes'` returns > 0 (cron ran).
   - `SELECT count(*) FROM posts WHERE fetched_at > NOW() - INTERVAL '30 minutes' AND view_count IS NOT NULL` equals the previous count (every new post has typed cols populated).
3. Compare prod state to the regression-net doc's pinned values:
   - 28,822 posts (the dump's content) + ~30 fresh posts from cron = ~28,852
   - 76 columns
   - 0 `raw` columns
   - FK constraints both `n` (SET NULL)
   - 0 FK violations

**Test scenarios**:
- Cron deploy `*/15 * * * *` is active (next run advances the cursor).
- New posts since U5 deploy all have non-NULL typed columns.
- Regression-net doc pinned values still hold.

**Verification**: All pinned values hold + cron cycle produces typed-column-bearing posts.

## Verification Contract

### Per-unit verification

- **U1 (GitHub release)**: `gh release view upload-dump-20260728` lists one asset; asset URL returns 200 with matching md5.
- **U2 (regression net doc)**: Doc committed; pinned values are queryable.
- **U3 (temp branch build.sh)**: Branch builds; build log shows `curl` + `md5sum` + `pg_restore` all succeed.
- **U4 (deploy + verify)**: Deploy log shows restore completes; `render psql` queries return 28,822 posts and unchanged migration state.
- **U5 (merge + push)**: `git log --oneline -3` shows merge commit; new deploy `live`; temp branch deleted.
- **U6 (recipe doc)**: Doc committed; cross-linked from recovery doc.
- **U7 (final verify)**: Cron cycles advance; new posts have typed cols; pinned values hold.

### Quality gates

- All commits include the `Scope delivered vs plan promised` line.
- Migration graph in `core/migrations/` is unchanged after the recovery (the dump has the pre-migration schema, but the dump's schema is already compatible with the post-migration state because 0006 chunked backfill was idempotent on whatever data was there).
- `git status` after the merge shows the main branch as the canonical state with no uncommitted changes.

### Behavioral skill evaluation

Not applicable — this plan is operational (data restoration + Render workflow), not behavioral.

## Definition of Done

### Global

- Prod DB has 28,822 posts restored from the dump.
- All 6 migrations still applied (no migration re-ran during restore).
- Harvest cron on `*/15 * * * *` producing new posts with typed columns.
- 76 columns, 0 `raw` columns, 0 FK violations, FKs both SET NULL.
- Temporary branch `fix/posts-restore-internal` merged and deleted.
- Regression-net doc pinned values hold.
- Recipe doc `render-internal-restore.md` committed for future reuse.

### Per-unit

- **U1**: GitHub release has the dump as an asset; asset URL is stable.
- **U2**: Regression-net doc committed with pre-restore pinned values.
- **U3**: Temp branch builds and restores from internal network in under 30 min.
- **U4**: Deploy log confirms restore success; `render psql` shows 28,822 posts.
- **U5**: Temp branch merged to main; new deploy live; temp branch deleted.
- **U6**: Recipe doc committed and cross-linked.
- **U7**: Cron cycles advance; new posts have typed cols; pinned values hold.

### Cleanup

Any debug scripts, build artifacts, or temporary branches used during recovery that aren't explicitly tracked in this plan must be removed before this plan is declared done. `git status` must show only the planned file changes; no leftover ad-hoc scripts in the tracked repo.