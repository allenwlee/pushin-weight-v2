---
module: ops
date: 2026-07-29
problem_type: recipe
component: render-postgres
severity: critical
last_updated: 2026-07-29
status: verified-once
origin_session: 2026-07-29 (fuchitalee, M3.0)
origin_issue: docs/issues/2026-07-29-internal-restore-failed-pg-restore-eof.md
origin_plan: docs/plans/2026-07-29-002-fix-zero-downtime-prod-db-ops-plan.md

---

# Render Postgres — shadow-restore + cutover recipe

## TL;DR

A reusable procedure for any massive prod DB op on Render Postgres
(full restore, denormalize, chunked backfill): load into a non-serving
**shadow** instance, verify, then cut over with a seconds-long flip.
The old "DROP SCHEMA public CASCADE then pg_restore" pattern is
forbidden — it has caused **two** 0-table prod incidents in this repo
(see plan 2026-07-29-002 for the causal chain).

## When to use this recipe

- Full `pg_restore` from a dump into prod
- Multi-hour migration that touches ≥10k rows
- Any op that would otherwise risk an irrecoverable window where live
  `public` is gone but the replacement is unverified
- Plan upgrade of Render Postgres (create new instance, cut over, drop old)

## When NOT to use this recipe

- Schema changes touching <10k rows: just `manage.py migrate` with
  the existing advisory-lock `build.sh` is fine
- Routine `manage.py loaddata` / `dumpdata` round-trips
- Anything that fits in a single advisory-lock'd web deploy

## Prerequisites

- Render Postgres free-tier is hostile to dual-copy and long backfills.
  **Upgrade to at least `basic_1gb` before any restore.** Symptoms that
  force an upgrade:
  - Free disk < `2×(expanded dump size) + 500 MB WAL`
  - 0003-style "single multi-hour txn" migration projected to exceed
    the free-tier disk (this repo hit the wall at ~806 MB / 1 GB)
  - Need a second DB instance for true blue-green (recommended)
- Cron paused before load+cutover (change schedule to `"0 0 31 2 *"`
  in `render.yaml`, deploy, then revert after recovery verified). See
  the decision documented in plan 2026-07-29-002 §U0.
- md5-pinned dump file on fuchitalee. Verify md5 *before* any schema work.
  Note: `scp` from fuchitalee to the operator host is **not** a viable transport for
  dumps > 5 MB — fuchitalee's home router has a ~1400-byte PMTU blackhole on long
  HTTPS writes. Use the recipe in `docs/solutions/data-migration/restore-large-pg-dump-to-render-via-s3-multipart.md`
  (S3 multipart + SSH + Render internal path) to get the dump into Render's network.
- IP allowlist on the shadow DB opened to wherever the restore job runs
  (`0.0.0.0/0` matches prod; tighten after recovery).

## Procedure

### 1. Preflight (≤5 minutes)

```bash
# prod state
render postgres get <prod-db-name> --output json
render psql <prod-db-name> -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
render psql <prod-db-name> -c "SELECT schemaname, count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') GROUP BY schemaname;"

# dump integrity
md5 <dump-file>
pg_restore -l <dump-file> | tail
```

Write the decision to the plan's execution log:

```
tier=basic_1gb (or upgraded)
path=second_db (preferred) | dual_schema (fallback)
expected_posts_count=<from dump TOC or staging-verified doc>
expected_md5=<md5>
```

### 2. Provision shadow

**Preferred — second DB instance:**

```bash
render postgres create \
  --name <prod-db-name>-shadow \
  --plan basic_1gb \
  --region oregon \
  --version 18 \
  --ip-allow-list "cidr=0.0.0.0/0,description=everywhere" \
  --confirm
```

Note: `--disk-size-gb 1` is **silently raised to 15 GB** on creation;
shrinking later is rejected. Cost is ~$7/mo compute + disk. Don't try
to fight it.

**Fallback — dual schema on one instance:**

```sql
-- Run via render psql on the prod instance. Live public untouched.
CREATE SCHEMA shadow;
GRANT ALL ON SCHEMA shadow TO <db_user>;
```

### 2.5 Transfer the dump into Render's network

This step is **not** as simple as `scp` or `aws s3 cp` from fuchitalee.
Fuchitalee's home router silently drops large outgoing packets (>1400-byte payload)
on long-lived HTTPS writes, so single PUTs of 40 MB+ to any cloud storage stall
at ~12 MB before the TCP socket enters `CloseWait`. Repeating the bad assumption
costs 3-4 hours of public-internet `pg_restore` at 3-4 rows/sec. The recommended
path is documented in full at
`docs/solutions/data-migration/restore-large-pg-dump-to-render-via-s3-multipart.md`.
Summary:

1. **Upload to S3 with boto3 multipart, 5 MB parts, dualstack endpoint**:
   `https://s3.dualstack.us-west-2.amazonaws.com`. Each part is small enough
   that the home router's PMTU doesn't trigger packet drops. The dualstack
   endpoint adds IPv6 as a fallback path if IPv4 stalls.
2. Generate a **1-hour presigned URL** with `aws s3 presign`.
3. **SSH directly to the Render service** (bypasses the dashboard's reconnecting
   WebSocket shell):
   `ssh -o StrictHostKeyChecking=accept-new <service-id>@ssh.oregon.render.com`.
4. From inside Render: `curl -fsSL -o /tmp/dump.bin "<presigned-url>"` then
   `md5sum /tmp/dump.bin` to verify (Render's egress is data-center, no NAT timeout).
5. Continue with section 3 below (`pg_restore` against the internal DB hostname).

**Why this works**: fuchitalee's home router can't deliver 40 MB in a single
HTTPS write, but it CAN deliver many short writes. Render's egress is a
data-center NIC with no NAT timeout, so the fetch from inside Render succeeds
where the same fetch from fuchitalee would have stalled. The dashboard shell
tab is a separate Render WebSocket pool from the API/CLI SSH path; the SSH
login works even when the dashboard is reconnecting.

### 3. Restore into shadow

**Tooling:** `scripts/ops/shadow_restore.sh` (env-driven, no secrets in
repo). Replaces the failed restore-mode `build.sh` pattern.

```bash
# From operator shell (Render shell or SSH to a service that can
# reach the internal DB hostname). NEVER from web build.sh.
SHADOW_DATABASE_URL="postgresql://<user>:<pwd>@<shadow-host>:5432/<shadow-db>" \
DUMP_PATH="/tmp/pushinweight-<timestamp>.dump" \
EXPECTED_MD5="<md5 from preflight>" \
./scripts/ops/shadow_restore.sh
```

The script enforces, in order:

1. md5 of `DUMP_PATH` matches `EXPECTED_MD5` (else exit 1)
2. Shadow `posts` table does not already exist (refuse to clobber)
3. `pg_restore --no-owner --no-privileges --jobs=1` (no `--clean`,
   no `DROP SCHEMA`)
4. `SELECT count(*) FROM posts` == `EXPECTED_POSTS_COUNT` (else exit 1)

If restore fails partway, **shadow is partial but live is untouched**.
Drop shadow schema / instance and try again.

### 4. Migrations on shadow only (if dump is pre-migration)

```bash
# In Render shell on the shadow DB. NEVER apply this order on live
# if live already has drop-source migrations applied.
python manage.py migrate --noinput
```

For the `posts.raw → typed columns` denormalization path, the order is:
`0001 → 0002 → 0003(no-op) → 0006(chunked backfill with autocommit) →
0004(drop raw) → 0005(FK SET NULL)`. See `docs/solutions/data-migration/
posts-raw-denormalize-staging-verified-2026-07-28.md`.

### 5. Cutover (seconds)

**Path A — second DB instance (preferred):**

1. Set `DATABASE_URL` on `pushinweight-web`, `pushinweight-worker`,
   `pushinweight-beat`, and `pushinweight-harvest` to the shadow URL.
2. Trigger a redeploy (or wait for the next auto-deploy).
3. Smoke: `render psql <shadow-db> -c "SELECT count(*) FROM posts;"`
4. Smoke: web returns 200, feed loads.

> **Cutover verification (post-deploy)**: After step 1 sets `DATABASE_URL` on the new live DB instance, verify on the dashboard that each dependent service's `DATABASE_URL` env var actually resolved to the new connection string. Render's blueprint sync from `fromDatabase` in render.yaml is not reliable on a previously-deployed service — the running service may keep the old `DATABASE_URL` even after the new deploy. If the build fails because `migrate` couldn't connect to the OLD DB hostname, that means the env var stayed stale. Manually override `DATABASE_URL` on each service via the dashboard. Watch the first 30 minutes of `/feed/` and `/accounts/login/` for 502s after every cutover.

**Path B — atomic schema rename (single instance, advanced):**

```sql
BEGIN;
  ALTER SCHEMA public RENAME TO public_old;
  ALTER SCHEMA shadow  RENAME TO public;
COMMIT;
-- Adjust grants + search_path if needed
-- App pools may need a reconnect
```

### 6. Verify + hold + cleanup

- Wait at least **one full harvest cycle** (~30 minutes with `*/15`
  cron) on the new live DB with no errors.
- `render psql <old-db>` count == `0` for user tables (or stop polling).
- Drop old DB (`render postgres delete <old-db-name> --confirm`).
- Revert cron schedule from `"0 0 31 2 *"` back to `*/15` in
  `render.yaml`, push.
- Update the relevant docs/solutions/ with verified pins.
- Close the originating issue.

## Forbidden patterns

- ❌ `DROP SCHEMA public CASCADE` before a verified restore exists elsewhere
- ❌ `pg_restore --clean` against live (same failure class)
- ❌ Multi-GB `pg_restore` or multi-hour migrate inside web `build.sh`
- ❌ Multi-hour migration in a single Postgres txn on free-tier disk
- ❌ `--jobs=4` on free/starter before a dry-run proves it stable
- ❌ Restoring an md5-unpinned dump (verify first, restore second)
- ❌ Auto-deploy branches carrying restore-mode `build.sh` (the
  failed `fix/posts-restore-internal` had this exact problem)

## Verification contract

Before cutover, all must be true:

- [ ] md5 of dump matches the pin in the docs/solutions/ doc
- [ ] `pg_restore` exit code 0 on shadow
- [ ] Shadow `SELECT count(*) FROM posts` matches expected count
- [ ] Shadow migrations applied (if dump is pre-migration) in safe order
- [ ] No `DROP SCHEMA public` in any committed `build.sh` on main
- [ ] Cron paused before load, will resume after cutover

After cutover, all must be true:

- [ ] Web + worker + beat + cron running against new live DB
- [ ] `/feed` loads, harvest runs once without error
- [ ] Old DB dropped after ≥1 green harvest cycle
- [ ] `render.yaml` cron schedule restored to operational value
- [ ] Originating issue closed with verified pin doc link
- [ ] After deploy: `render deploys list` shows the latest deploy 'Live' AND a quick `curl -I https://<service-url>/accounts/login/` returns 200 (not 502). If you see 502 immediately after cutover, the env var stayed stale.

## Sources

- Plan: `docs/plans/2026-07-29-002-fix-zero-downtime-prod-db-ops-plan.md`
- Incident: `docs/solutions/data-migration/posts-raw-denormalize-prod-incident-2026-07-28.md`
- Recovery: `docs/solutions/data-migration/posts-raw-denormalize-prod-recovery-verified-2026-07-28.md`
- Failed branch that motivated this recipe: `fix/posts-restore-internal` (deleted 2026-07-29)
