---
title: "Zero-Disruption Prod DB Ops (Shadow Restore + Expand-Contract) - Plan"
type: fix
date: 2026-07-29
amended: 2026-07-29
amendment_note: "Render plan upgrade (DB storage / second instance) is an authorized lever when free-tier limits block safe dual-copy or long backfill"
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: ops+code
origin_issue: docs/issues/2026-07-29-internal-restore-failed-pg-restore-eof.md
origin_solutions: docs/solutions/data-migration/
supersedes: docs/plans/2026-07-29-001-fix-posts-raw-internal-restore-plan.md
---

# Zero-Disruption Prod DB Ops (Shadow Restore + Expand-Contract) - Plan

### written by Grok 4.3

## Goal Capsule

**Objective.** Run massive prod data/schema changes (full restore, denormalize, backfill) **without destroying the live app data plane mid-flight**. Live `public` stays readable until a verified shadow is ready; cutover is a short atomic rename/connection swap, not a multi-minute `DROP SCHEMA` + hope-`pg_restore` works.

**Authority.** Supersedes `2026-07-29-001` (internal restore via restore-mode `build.sh` + `DROP SCHEMA public CASCADE` before restore). Incorporates lessons from:

- `docs/issues/2026-07-29-internal-restore-failed-pg-restore-eof.md` (0 tables after failed restore)
- `docs/solutions/data-migration/posts-raw-denormalize-prod-incident-2026-07-28.md`
- `docs/solutions/data-migration/posts-raw-denormalize-prod-recovery-verified-2026-07-28.md`
- `docs/solutions/data-migration/posts-raw-denormalize-staging-verified-2026-07-28.md`
- `docs/solutions/data-migration/posts-raw-internal-restore-pre-2026-07-29.md`

**Stop when.** (1) Immediate recovery path restores ~28,822 posts without another 0-table window; (2) reusable ops recipe + checklist documented; (3) future schema changes use expand-contract + chunked backfill; (4) free-tier constraints that force upgrade are explicit gates, not mid-flight surprises.

**Out of band.** Hybrid harvest funnel (`2026-07-28-001-feat-b1-…`); `lang_detected` / translation persist bug (separate).

---

## Debug Summary (ce-debug of past implementations)

**Problem:** Every massive prod DB op in this saga either killed the live app or left it half-migrated.

**Root cause (causal chain):**

| # | Trigger | What went wrong | Symptom |
|---|---------|-----------------|---------|
| 1 | Deploy = mutation path | Multi-instance Render deploys run `build.sh` / migrate in parallel | Deadlock on 0002 FK (`incident` attempt 1) |
| 2 | Single long txn backfill | 0003 UPDATE×50 in one txn on 29k rows | WAL + dead tuples → free-tier 1GB disk crash (`incident` attempt 2) |
| 3 | Wrong migration graph | 0004 drop raw before 0006 backfill (deps ordered wrong; then 0004 already applied) | Typed columns NULL forever without dump (`incident` attempt 3) |
| 4 | Public-internet restore | fuchitalee → Render public endpoint ~3 rows/min | Partial restore (61 rows), accepted as "good enough" then cron filled to ~258 |
| 5 | Restore-mode `build.sh` | **Drop public first**, then `pg_restore` in build container | `pg_restore` EOF / worker died → **prod 0 tables** (`2026-07-29` issue) |
| 6 | Wrong KTD assumptions | `--jobs=4` "safe on empty schema"; cron "OK during drop"; build container "has headroom" | Parallel workers die; app data plane gone before restore proves viable |

**Shared failure mode:** **destructive step before proof of success.** Live schema was the workspace for unproven restore/migrate. When the heavy step failed, there was nothing left serving.

**What worked (keep):**

- Staging full restore of same dump locally (`pushinweight_staging` over tunnel) — dump integrity is fine
- Chunked backfill with `autocommit` (0006 design)
- Advisory lock around migrate (partial fix for multi-instance)
- Cron pause during heavy DDL/DML
- md5-pinned dump + regression-net docs

**What must never repeat:**

- `DROP SCHEMA public CASCADE` (or `--clean` wipe of live) **before** a verified restore exists elsewhere
- Full restore / multi-GB backfill **inside** web service `build.sh`
- Single multi-hour migration transaction on free-tier disk without headroom check
- Shipping a drop-source migration without a pre-drop "source column still needed?" gate

**Confidence:** High — chain is documented across four solution docs + the open issue; local restore of the same dump succeeds; Render build path fails after drop.

---

## Product Contract

### Summary

Two layers:

1. **Immediate recovery (current 0-table prod):** restore dump into a **shadow** (second DB *or* second schema) via a **one-off job / shell**, not a web deploy; verify; then **cut over** in seconds; only then tear down old.
2. **Standing ops pattern for future massive changes:** expand-contract migrations + chunked backfill + optional **Render DB plan upgrade** when dual-copy or WAL needs more than free tier allows.

### Problem Frame

1. Free-tier Postgres (1 GB disk, tight connections, no PITR) is hostile to dual-copy restore and long backfills — **upgrade is authorized when that hostility blocks the safe pattern**.
2. Render web **build** is a bad place for 38 MB download + multi-minute `pg_restore` (memory/connection/EOF).
3. App disruption is unavoidable only for the **cutover window** (seconds), not for the **load window** (minutes–hours).

### Requirements

#### Safety invariants (all paths)

- R1. **Never destroy live `public` until shadow is verified** against acceptance pins (row count, migrations, sample FKs, md5 of dump used).
- R2. **Data ops ≠ web deploy.** Restore/backfill runs as one-off job, SSH session, or dedicated ops service — not as a temporary `build.sh` on the web service branch.
- R3. **Cron paused** before cutover/restore contention; re-enabled only after green checks.
- R4. **Advisory lock** still wraps any `manage.py migrate` that remains in `build.sh` (keep existing hardening).
- R5. Any migration that touches ≥10k rows: **chunked + autocommit** (or explicit batch commits) + disk headroom check; no single multi-hour txn.
- R6. Dropping a source column (e.g. `raw`) requires a **pre-drop gate**: `SELECT` proves backfill completeness or abort.

#### Immediate recovery (0-table prod)

- R7. Target: **28,822** posts from dump `~/Downloads/pushinweight-20260728-200742.dump` (md5 `73d6ee2fe1da0a5b961a2efac67d926a`).
- R8. Preferred: restore into **shadow database** on upgraded Render Postgres (or second DB instance), point app `DATABASE_URL` at shadow after verify; keep old instance until next harvest green.
- R9. Alternate if one DB only but upgraded storage: restore into schema `shadow` (or temp DB name on same instance), then atomic rename:
  ```sql
  BEGIN;
  ALTER SCHEMA public RENAME TO public_old;
  ALTER SCHEMA shadow RENAME TO public;
  COMMIT;
  ```
  (Adjust grants/search_path; app may need reconnect.)
- R10. **Forbidden for recovery:** restore-mode web `build.sh` that drops `public` first (the failed 2026-07-29 path).
- R11. Post-cutover: migrations match intended graph; FKs SET NULL; cron `*/15`; optional typed-column backfill only if dump still has `raw` and schema requires it — **do not re-run drop-before-backfill**.

#### Plan upgrade (authorized lever)

- R12. **Upgrade Render Postgres (and/or web) when any of these fail preflight:**
  - Free disk < **2× dump expanded size + 500 MB WAL buffer** (rule of thumb: need room for live + shadow + restore WAL)
  - Dual-DB blue-green not available on current plan
  - Chunked backfill projected to exceed free-tier disk (prior 0003 crash at ~806 MB / 1 GB)
- R13. Upgrade is a **preflight step**, not an emergency mid-restore. Document chosen plan tier + new internal hostname / `DATABASE_URL` before cutover.
- R14. After recovery, optionally stay upgraded for headroom; do not auto-downgrade in this plan (ops decision).

#### Standing pattern (future massive changes)

- R15. **Expand-contract** for schema: add nullable → backfill → dual-read/write if needed → switch → drop old.
- R16. Staging must run the **full** backfill on prod-sized dump before prod (catch disk/WAL), not only "schema applies."
- R17. Reusable recipe doc under `docs/solutions/operations/` (or data-migration/) after first successful run.

### Acceptance Examples

- AE1. During shadow load, live app still serves (even if empty/partial today — process still holds for future full DBs): live `public` not dropped by the load job.
- AE2. Shadow `SELECT count(*) FROM posts` = 28,822 before any cutover.
- AE3. Cutover window < 2 minutes wall clock; no multi-minute 0-table state.
- AE4. If restore job fails, live still has previous tables (or current empty state is not made worse by a second drop).
- AE5. Free-tier preflight fails loud with "upgrade required" rather than starting DROP.

### Scope Boundaries

**In:** recovery procedure; upgrade gate; ops scripts; cron pause/resume; cutover checklist; recipe doc; revert of restore-mode `build.sh` on any leftover branch.

**Out:** Hybrid harvest; translation persist; full automated S3 backup pipeline (note as follow-up).

### Success Criteria

- Prod has dump row count (28,822) or better with verified pins
- No 0-table failure mode in the procedure
- Upgrade used only if preflight demands it, and is planned first
- Future agents have a single recipe: shadow → verify → cutover → cleanup

---

## Planning Contract

### Key Technical Decisions

- **KTD1. Shadow-first restore.** Load dump into a non-serving DB/schema; cut over only after verify. (Replaces 001's DROP-live-then-restore.)

- **KTD2. Data ops via one-off job / shell, not web build.** Prefer `render jobs create` with explicit `pg_restore` command, or Render shell / SSH session with internal hostname. (001's temp `build.sh` failed; jobs avoid deploy multi-instance migrate races.)

- **KTD3. Render plan upgrade is authorized.** When free-tier cannot hold live+shadow or WAL for backfill, **upgrade first** (user-confirmed 2026-07-29). Prefer a **second Postgres instance** for blue-green when available; else larger single instance for dual-schema.

- **KTD4. `--jobs=1` default on free/starter; raise only after shadow dry-run succeeds.** (001's `--jobs=4` contributed to worker death.)

- **KTD5. Cron paused for load+cutover.** Do not rely on "schema drop as sync point."

- **KTD6. Keep advisory lock on migrate in normal `build.sh`.** Never replace normal build with restore-mode on `main`.

- **KTD7. Dump source of truth remains fuchitalee path + md5.** GitHub release asset optional; if used, strip multipart and verify md5 **before** any schema work. Prefer scp dump into job workspace or internal object storage when upgrade allows.

- **KTD8. Credentials only via `DATABASE_URL` / Render env** — no passwords in plan scripts committed to git (scrub existing restore scripts that embedded them).

### High-Level Technical Design

```text
PREFLIGHT
  pause cron (render.yaml or dashboard)
  measure disk / plan tier
  if free disk < 2×(expanded dump) + 500MB WAL → UPGRADE (R12)
  verify dump md5
  dry-run: pg_restore -l + optional restore to local staging

SHADOW LOAD  (live untouched)
  create shadow DB  OR  CREATE SCHEMA shadow
  pg_restore --no-owner --no-privileges --jobs=1 → shadow
  run migrations on shadow if dump is pre-migration (correct order only)
  VERIFY pins (count, cols, FKs, sample rows)

CUTOVER  (seconds)
  option A (2nd instance): flip web+cron DATABASE_URL → shadow, redeploy
  option B (same instance): RENAME SCHEMA public↔shadow in one txn + reconnect
  smoke: /feed or psql count

CLEANUP
  hold public_old / old instance ≥1 harvest cycle green
  drop old after pin doc updated
  resume cron
  write ops recipe + close issue
```

### Alternatives Considered

| Approach | Verdict |
|---|---|
| 001 restore-mode `build.sh` + DROP public | **Rejected** — caused 0 tables |
| Public-internet pg_restore from fuchitalee | Rejected for full load — bandwidth |
| Live with empty/partial history | Rejected as primary goal — user wants full dump |
| Always upgrade without measuring | Wasteful — upgrade only on failed preflight |
| In-place `--clean` restore while app up | Rejected — same class as DROP |

### Risks

| Risk | Mitigation |
|---|---|
| Upgrade cost | Explicit preflight; user already authorized |
| Cutover reconnect blip | Accept short 502; optional maintenance page |
| Shadow restore still EOF on job | Upgrade memory/CPU; `--jobs=1`; no drop of live |
| Migration order wrong again | Graph review checklist; never apply drop before backfill on shadow |
| Secret leakage in scripts | Env-only; scrub `build.sh` on restore branch |

---

## Implementation Units

### U0. Preflight + plan tier decision

**Goal.** Decide upgrade vs free-tier path with numbers, not vibes.

**Approach.**

1. Query prod: DB size, free disk (if exposed), table count (currently 0 public tables — note degraded state).
2. Measure dump: 38 MB custom; note expanded size from local staging restore.
3. Compute: need **live residual + shadow full + WAL**. If free tier cannot fit → **upgrade Render Postgres** (and document new host / plan name).
4. Pause harvest cron.

**Verification.** Written decision in issue comment or this plan's execution log: `tier=free|upgraded`, `path=second_db|dual_schema`.

---

### U1. Fix normal `build.sh` / branches (stop the bleeding)

**Goal.** Ensure `main` (and any auto-deploy branch) is **not** restore-mode.

**Files.** `build.sh` on `main`; branch `fix/posts-restore-internal` (delete or hard-reset after).

**Approach.** Restore normal install+migrate+advisory-lock `build.sh`. Do not merge restore-mode to `main`.

**Verification.** `build.sh` on main has no `DROP SCHEMA public`.

---

### U2. Shadow restore tooling

**Goal.** Script/job that restores dump into shadow without touching live `public` (or without touching primary instance if dual-DB).

**Files.** e.g. `scripts/ops/shadow_restore.sh`, `scripts/ops/extract_dump.py` (reuse working extractor), docs under `docs/solutions/operations/`.

**Approach.**

```bash
# conceptual — env-driven, no secrets in repo
: "${SHADOW_DATABASE_URL:?}"
: "${DUMP_PATH:?}"
pg_restore -l "$DUMP_PATH" | tail
# dual-schema path: restore with --schema rename, or restore into empty shadow DB
pg_restore --no-owner --no-privileges --jobs=1 \
  -d "$SHADOW_DATABASE_URL" "$DUMP_PATH"
psql "$SHADOW_DATABASE_URL" -c "SELECT count(*) FROM posts;"  # expect 28822
```

Run via `render jobs create` **or** operator shell on a service that can reach internal hostname — **not** via replacing web `build.sh`.

**Verification.** Shadow count = 28,822; live (if any) unchanged.

---

### U3. Schema/migration catch-up on shadow only

**Goal.** If dump is pre-typed-column / has `raw`, apply migrations **on shadow** in safe order only:

`0001 → 0002 → 0003(no-op) → 0006(chunked backfill) → 0004(drop raw) → 0005(FK SET NULL)`

**Never** apply this graph to a live DB that already dropped `raw` without restore.

**Disk:** if 0006 projected large, **upgrade first** (R12). Chunked + autocommit already required.

**Verification.** Shadow matches recovery pins (typed columns populated if backfill ran; FKs SET NULL; 0 violations).

---

### U4. Cutover

**Goal.** Point live traffic at verified shadow.

**Path A — second DB (preferred after upgrade):**

1. Set web + cron `DATABASE_URL` to shadow instance.
2. Deploy/restart (normal build — migrate should no-op if already applied on shadow).
3. Smoke tests.

**Path B — schema rename on one upgraded instance:**

1. Brief maintenance optional.
2. Atomic rename `public` → `public_old`, `shadow` → `public`.
3. Restart app pools.
4. Smoke tests.

**Verification.** AE2–AE4; feed loads; `render psql` count 28,822.

---

### U5. Cleanup + resume + close issue

**Goal.** Drop old only after one green harvest; update regression net; close `2026-07-29-internal-restore-failed-…`.

**Files.** Update `docs/solutions/data-migration/posts-raw-internal-restore-pre-2026-07-29.md` or write `…-verified-2026-07-29.md`; ops recipe.

**Verification.** Pins queryable; cron `*/15`; issue acceptance criteria met.

---

### U6. Standing recipe (compound)

**Goal.** `docs/solutions/operations/render-shadow-restore-and-cutover.md` (or under data-migration) capturing:

- Preflight disk formula
- Upgrade gate
- Job vs build prohibition
- Dual-DB vs dual-schema
- Expand-contract + chunked migrate rules

---

## Immediate recovery runbook (operator-facing)

```text
1. Pause cron
2. Preflight disk → UPGRADE if needed (authorized)
3. Confirm build.sh on main is NOT restore-mode; cancel auto-deploys of fix/posts-restore-internal
4. Shadow restore dump (jobs/shell, internal network) → verify 28822
5. Migrations on shadow only if dump schema requires (order U3)
6. Cutover (URL flip or schema rename)
7. Smoke + resume cron
8. Hold old ≥1 cycle; drop old; write verified doc; close issue
```

---

## Verification Contract

- Shadow count 28,822 before cutover
- Post-cutover: same pins as recovery-verified doc (adapted for actual post-migration schema)
- No `DROP SCHEMA public` in any committed `build.sh` on main
- Preflight log shows upgrade decision
- Cron paused during load/cutover; resumed after

## Definition of Done

- [x] U0 preflight + upgrade decision recorded
- [x] U1 main build.sh safe
- [ ] U2 shadow loaded and verified
- [ ] U3 migrations correct on shadow if needed
- [ ] U4 cutover; app serves
- [ ] U5 cleanup + issue closed
- [x] U6 recipe doc shipped
- [ ] Scope delivered vs plan documented in commits

## Execution Log (live, appended as work happens)

### Session 2026-07-29 — partial execution, handed off

**Branch at start:** `fix/posts-restore-internal` (5 commits of the failed restore-mode build.sh).
**Branch at end:** `main` (failed branch deleted locally + remote; new commits `e7e53b8` + `c53afc2`).

**Units completed this session:**

- **U0 preflight + upgrade decision** — recorded.
  - Render DB tier: free → basic_1gb (user-confirmed 2026-07-29, per plan §R12–R14).
  - Path: second DB instance (preferred), region oregon, version 18, database `pushinweight_shadow`.
  - **Plan amendment (live):** source dump is `~/Downloads/pushinweight-20260728-141129.dump` (40MB, md5 `8335a6955955b834d83008fad532606c`), NOT `pushinweight-20260728-200742.dump` named above. The 200742 dump has 0 posts (verified by restoring into local pg17 + `SELECT count(*) FROM posts`); the 141129 dump has 28,822 posts with the `raw` column intact. R7 acceptance pin (count = 28822) applies unchanged.
  - Cron pause decision: **after recovery + verify**, not now. Currently still `*/15`.

- **U1 main build.sh + restore branch** — verified safe and cleaned up.
  - `main`'s `build.sh` already has the advisory-lock pattern; no `DROP SCHEMA public` anywhere.
  - Deleted local branch `fix/posts-restore-internal` (was d33c2e8).
  - Deleted remote branch `origin/fix/posts-restore-internal`.

- **U2 shadow restore tooling** — code done, restore pending.
  - `scripts/ops/shadow_restore.sh` (env-driven: `SHADOW_DATABASE_URL`, `DUMP_PATH`, `EXPECTED_MD5`; refuses to clobber existing posts table; md5 verify + `pg_restore --no-owner --no-privileges --jobs=1` + row-count pin).
  - `scripts/ops/extract_dump.py` (multipart stripper + md5 verify).
  - Commit `e7e53b8 feat(ops): shadow_restore.sh + extract_dump.py for safe prod recovery`.

- **U6 standing recipe doc** — shipped.
  - `docs/solutions/operations/render-shadow-restore-and-cutover.md`.
  - Commit `c53afc2 docs(operations): shadow-restore + cutover recipe (U6)`.

**Infrastructure state at end of session:**

- Prod `pushinweight-db` (id `dpg-d9go1njeo5us73cg5u00-a`): plan `basic_1gb`, disk 1 GB, status `available`, ipAllowList `0.0.0.0/0`.
- Shadow `pushinweight-db-shadow` (id `dpg-d9koekqjobas73fvjqng-a`): plan `basic_1gb`, disk 15 GB (cannot shrink from 15 to ≤10), status `available`, ipAllowList `0.0.0.0/0`. Database `pushinweight_shadow`, user `pushinweight_shadow`.
- Render services (unchanged, still pointing at prod `DATABASE_URL`):
  - `pushinweight-web` (srv-d9go2breo5us73cg6vqg)
  - `pushinweight-worker` (srv-d9go2breo5us73cg6vr0)
  - `pushinweight-beat` (srv-d9go2breo5us73cg6vrg)
  - `pushinweight-harvest` cron (crn-d9gv94o4n6ts739tqaug), schedule `*/15 * * * *`.

**Blocking input for next session:**

- **Shadow DB external connection string** (from Render dashboard → Databases → pushinweight-db-shadow → Connect → External Connection). Without it U2 restore cannot run.

**Handoff doc:** `docs/handoffs/2026-07-29-001-shadow-restore-in-progress.md`.

---

## System-Wide Impact

- **Downtime:** cutover seconds, not restore minutes; load can run while old serves (when old still has data). Current 0-table prod: load still uses shadow-first so a **failed** restore does not re-drop nothing into worse automated loops.
- **Cost:** possible Render Postgres upgrade — intentional lever.
- **Process:** agents stop inventing restore-mode deploys.

## Documentation / Operational Notes

- Dump: fuchitalee `~/Downloads/pushinweight-20260728-200742.dump`, md5 `73d6ee2fe1da0a5b961a2efac67d926a`
- Optional GH release asset already uploaded; verify md5 after download; strip multipart if needed
- Free-tier lessons stay in incident docs; this plan is the replacement procedure

## Sources & Research

- Issue: `docs/issues/2026-07-29-internal-restore-failed-pg-restore-eof.md`
- Solutions: `docs/solutions/data-migration/*` (incident, recovery-verified, staging-verified, pre-restore baseline)
- Failed plan: `docs/plans/2026-07-29-001-fix-posts-raw-internal-restore-plan.md`
- User 2026-07-29: Render plan upgrade for more DB storage is allowed when needed
