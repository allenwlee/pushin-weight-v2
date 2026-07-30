documents/research/2026-07-30-180000-phase-2-partial-final-report.md
# Phase 2 Reconciliation — Final Report

_Date: 2026-07-30 (JST) · Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md · Target: pushin-weight-v2 on fuchitalee_

## Final State

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| `dup_groups` (handle duplicate groups) | 2,142 | **29** | -2,113 |
| `posts_at_placeholder` | 20,079 | **13,667** | -6,412 |
| `apa_at_placeholder` | 6,803 | **4,780** | -2,023 |
| `brands_at_placeholder` | 95 | **15** | -80 |
| `integer_author_ids` | 5,776 | **6,356** | +580 |
| `total_accounts` | 19,284 | **17,059** | -2,225 |
| `placeholder_rows` | 10,991 | **10,681** | -310 |
| `unique_index` (`uniq_accounts_handle_lower`) | absent | **absent** | U12 deferred |

**Plan delivery: PARTIAL.** U12 (unique index) cannot ship because 10,681 lonely placeholders remain (with 9,694 unique handles). All other phase-2 work achieved within scope bounds.

## What Shipped

- **U0 / U16**: Verified pg_dump captured (md5 `b239a84573319acf2cbb1b0337f3adab`, 366 TOC entries, 28,822 posts / 19,284 accounts snapshot). Cron pause verified: 3 services + 1 cron `suspended`.
- **U1–U8 (hybrid funnel)**: 7-call layout (A, B1, B2, B3, C1, C2, C3) with bare-keywords B1, `@handle` OR-groups B2/B3, thin-co C with 5-term minimal allowlist, binary LLM relevancy gate for C-tier attribution, anomaly metrics in cycle summary. U1 regression net pins surface state (55 passed / 3 errors in 1.39s on `pushinweight_test`).
- **U10 / U11 (residual reconciliation)**: 69 residual duplicate groups → **40 merged, 29 dead-lettered (TwitterAPI 404)**. 150 posts + 3 APAs repointed, 46 placeholder rows deleted. The 29 dead-letters are KTD12 cases (handles that don't exist on X even with retry).
- **U10 / U14 (regression net)**: Pinned AFTER-state values for all 10 metrics.
- **U15 (source-plan deprecation)**: Both `2026-07-28-001-feat-b1-purity-official-handles-plan.md` and `2026-07-30-001-fix-accounts-handle-duplicates-reconciliation-plan.md` carry `deprecated: true` frontmatter + deprecation banner.
- **Phase 2 partial (lonely placeholders)**: 226 of 10,908 lonely placeholders resolved via aiohttp parallel pre-pass. 10,681 remaining are DEFERRED.

## Bugs Surfaced and Fixed

### 1. brands_accounts_pkey collision (Phase 1)
Live harvest inserts `(brand_id, canonical_accounts_id)` before the placeholder row. The repoint step tried to UPDATE the placeholder's row to the canonical integer, which collided with the existing canonical row. **Fix**: pre-pass DELETE in `_repoint_fk` removes placeholder rows whose canonical integer already exists for the same brand_id. TDD: 2 unit tests pin the pre-pass short-circuit path.

### 2. TwitterAPI 404 vs 200 with empty data
The docs/README in `docs/research/twitterapi_docs/` confirm: TwitterAPI returns HTTP 200 with `{"status":"error","msg":"user not found","data":null}` for nonexistent users. The apply code was using a single skip-reason "TwitterAPI lookup failed/404" for both genuine 404s and 200-not-found. **Fix**: distinct messages in the final JSON summary; the apply logic doesn't care about the distinction.

### 3. TwitterAPI rejects Python-urllib User-Agent with 403
`urllib.request.Request` sends `User-Agent: Python-urllib/3.x` by default; TwitterAPI responds 403. Confirmed via the upstream docs (each endpoint spec is at `https://docs.twitterapi.io/<endpoint>.md`). **Fix**: send `User-Agent: curl/7.84.0` in `_twitterapi_lookup`.

### 4. ThreadPoolExecutor serializes on the GIL
Tested 8-worker ThreadPoolExecutor for TwitterAPI bulk lookups; got ~1 req/sec instead of expected 200 QPS. Probed via `sample` — main thread blocked in `lock_PyThread_acquire_lock`. **Fix**: rewrote pre-pass to use `aiohttp` + `TCPConnector(limit=100)`. TwitterAPI supports 200 QPS per client (per `docs/research/twitterapi_docs/endpoint/introduction.md`).

### 5. Pre-pass canonical INSERT created KTD10 conflicts
The v4 and v5 aiohttp pre-pass implementations inserted canonical rows via `INSERT ... ON CONFLICT (author_id) DO NOTHING` before the apply loop ran. The existing `accounts` table had placeholder rows with the same handle, so the insert created new duplicate groups (587 in v4, 408 in v5). **Fix**: removed the pre-pass INSERT entirely. The apply loop's `_ensure_canonical_account_row` already handles the right KTD10 semantics, and the insert happens inside the same transaction as the placeholder DELETE, so the intermediate double-row state is invisible to concurrent readers.

### 6. fuchitalee ephemeral port exhaustion
The 100-thread aiohttp TCPConnector exhausted `fuchitalee`'s ephemeral port range (49,152–65,535, 16,384 ports). 13,952 sockets in TIME_WAIT. The host has `tcp.msl=15000ms` (15s) but the TIME_WAIT count was stuck. The Mac side has 0 TIME_WAIT. **Mitigation**: stopped the v6 apply after 226 lonely placeholders were resolved; the remaining apply work is DEFERRED.

## Files Changed

```
chore(repo): gitignore .worktrees/ for isolation
feat(harvest): hybrid funnel (B1 bare + C thin co + C-only LLM)
feat(migration): primary purity seed + merge migration
feat(reconcile): dry-run + apply command + unique index migration
test(reconcile): regression net + dry-run/apply tests
docs(plan+audit): combined hybrid-funnel + reconcile plan + ops docs
feat(reconcile): LLM relevancy gate + hybrid funnel tests
chore(repo): gitignore .worktrees/ for isolation
feat(reconcile): --lonely-only flag for Phase 2 handle-unique placeholders
fix(reconcile): pre-pass DELETE for brands_accounts + retry TwitterAPI 404s + 2 unit tests
perf(reconcile): reduce inter-group sleep to 0.25s
test(reconcile): U14 AFTER-state regression net (Phase 2 partial)
feat(reconcile): parallel pre-pass + User-Agent fix + canonical-insert
fix(reconcile): remove pre-pass canonical INSERT
scripts(cleanup): undo pre-pass KTD10-conflict damage from aiohttp batch insert
scripts(cleanup): bulk-revert pre-pass canonical inserts
scripts(cleanup): v6 +1 dup group revert (1084560526020132864)
```

## Deferred Work

- **Resolve the remaining 10,681 lonely placeholders.** Trigger: ≥24 hours of clean TwitterAPI auth. Run `manage.py reconcile_account_duplicates --apply --lonely-only --workers 100` (uses aiohttp). When complete, re-run U11 dry-run + apply to confirm 0 dup groups, then run U12 migration.
- **Re-resolve the 29 dead-lettered residual dup groups.** Trigger: ≥24 hours of clean TwitterAPI 200 responses. The handles referenced in `~/residual-apply-v2.log` (e.g., `DoubaoAI`, `EileenTal`, `KahaSe33`) return 200 in smoke probes but 404 during the apply; the dead-letter rate is suspected to be a stealth rate limit.
- **U12 (unique index).** Run `manage.py migrate` after the above two items are done. Migration precheck refuses until dup_groups = 0.
- **U16 resume leg.** Operator must un-suspend the cron + workers via the Render dashboard after U12 + a clean harvest cycle are verified. Documented in `docs/operations/pause-and-resume-harvest-cron.md`.

## Cleanup Scripts (Permanent)

The pre-pass bug (item 5) caused multiple rollback rounds. Two cleanup scripts are committed for future use:

- `scripts/u_cleanup_prepass_damage.py` — bulk-revert pre-pass canonical inserts when the KTD10 conflict bug fires. Reads recent integer rows (first_seen_at > 2026-07-30T11:15), identifies those in dup groups, repoints FK rows to the existing canonical, and DELETEs the bad row.
- `scripts/u_cleanup_prepass_drift.py` — same as above but for the +1 dup group drift that v6 slipped through.

Run any cleanup with: `DATABASE_URL=postgres://...pushinweight_shadow... uv run --with django python manage.py shell < scripts/u_cleanup_prepass_drift.py`.

## Commit Graph

```
c209b7a test(reconcile): U14 AFTER-state regression net (Phase 2 partial)
a068d99 scripts(cleanup): v6 +1 dup group revert (1084560526020132864)
dc11985 scripts(cleanup): bulk-revert pre-pass canonical inserts
3879a42 fix(reconcile): remove pre-pass canonical INSERT
ef728d0 scripts(cleanup): undo pre-pass KTD10-conflict damage from aiohttp batch insert
b2ec18f feat(reconcile): parallel pre-pass + User-Agent fix + canonical-insert
183b1f6 perf(reconcile): reduce inter-group sleep to 0.25s
ffe9310 test(reconcile): U14 AFTER-state regression net + drift detector
8bc8062 fix(reconcile): pre-pass DELETE for brands_accounts + retry TwitterAPI 404s
44ca4a4 feat(reconcile): --lonely-only flag for Phase 2 handle-unique placeholders
c84b8ea feat(harvest): LLM relevancy gate + hybrid funnel tests
57a68ab docs(plan+audit): combined hybrid-funnel + reconcile plan + ops docs
7034397 test(reconcile): regression net + dry-run/apply tests
7ed95ea feat(reconcile): dry-run + apply command + unique index migration
202b54b feat(migration): primary purity seed + merge migration
3817d57 feat(harvest): hybrid funnel (B1 bare + C thin co + C-only LLM)
ddba830 chore(repo): gitignore .worktrees/ for isolation
```

All on `feat/phase-2-reconcile-residual-and-lonely` branch. Not yet pushed to remote — the operator should review the workspace state before pushing.
