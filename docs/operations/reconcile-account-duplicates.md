# Reconcile account duplicates — operator runbook

Append-only log of every pause/resume event. Entries are never edited; corrections are appended.

Per plan `2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md` units U10-U14, this runbook documents how to run the reconciliation and what to expect at each step.

## Quick reference

| Step | Command | Expected outcome |
|------|---------|------------------|
| 1. Audit current state | `python scripts/u9_live_pin.py` | All BEFORE-state pins PASS (2142 dupes, 20079 posts, etc.) |
| 2. Dry-run summary | `manage.py reconcile_account_duplicates --dry-run` | bulk aggregate: ~18K posts + 6.8K APAs to repoint, ~13.5K placeholder accounts to delete |
| 3. Apply reconciliation | `manage.py reconcile_account_duplicates --apply` | duplicates 2142 → 462 (or lower); 0 FK constraints violated |
| 4. Apply unique index migration | Render deploy (./build.sh runs `manage.py migrate`) | migration `0009_accounts_handle_unique_ci` applies; precheck passes |
| 5. Verify AFTER state | `python scripts/u9_live_pin.py` (now passes the AFTER-state assertion if you update it) | dup count ≤ 462 |
| 6. (Phase 2, deferred) | `manage.py reconcile_account_duplicates --apply --residual-only` | residual 462 → 0 once TwitterAPI auth is reliable for ≥24h |

## Service inventory (as of 2026-07-30)

| Item | Value |
|---|---|
| `pushinweight-harvest` cron (`crn-d9gv94o4n6ts739tqaug`) | **suspended** (U16 pause) |
| `pushinweight-beat` (`srv-d9go2breo5us73cg6vrg`) | **suspended** (U16 pause) |
| `pushinweight-worker` (`srv-d9go2breo5us73cg6vr0`) | **suspended** (U16 pause) |
| Production DB (`pushinweight-db-shadow`) | `dpg-d9koekqjobas73fvjqng-a` |
| Render REST API key | `~/.render/cli.yaml` |

## Why pause matters here

Pausing the cron (U16) before reconciliation is critical: any new harvest cycle while the reconciliation is mid-flight will write MORE placeholder rows against the same handles we're trying to dedupe. The reconciliation's per-group SAVEPOINT (KTD11) protects against partial failures, but it can't protect against concurrent writers. U16 + U10 + U11 are sequenced in plan order for exactly this reason.

## Apply path — step by step

1. **Confirm audit numbers match the plan body (audit may have drifted if anything happened since 2026-07-30):**

   ```bash
   DATABASE_URL=postgres://...pushinweight_shadow... \
     python scripts/u9_live_pin.py
   ```

   All ten pins must show "expected N, got N". If any pin has drifted, STOP and investigate — the reconciliation depends on these being accurate for the AFTER-state pins.

2. **Dry-run bulk aggregate (fast — under 60 seconds):**

   ```bash
   DATABASE_URL=postgres://...pushinweight_shadow... \
     manage.py reconcile_account_duplicates --dry-run
   ```

   Expected output:
   ```
   groups_total     = 1811     # groups with ≥1 integer row
   merged (estimate) = 1811
   rows_updated_posts = ~18114
   rows_updated_account_post_appearances = ~6803
   rows_updated_brands_accounts = ~60
   rows_updated_companies_accounts = 0
   rows_deleted_accounts = ~13486
   ```

3. **Dry-run with per-group breakdown (slow — 30+ min for 2K groups; use `--limit 100` to scope):**

   ```bash
   DATABASE_URL=postgres://...pushinweight_shadow... \
     manage.py reconcile_account_duplicates --dry-run --limit 100 --json
   ```

   Inspect the JSON: confirm canonical IDs are real X user IDs (18-19 digit integers), confirm skip reasons are reasonable (TwitterAPI 404 for accounts that don't exist; KTD10 disagreement for mis-merged rows).

4. **Apply the reconciliation:**

   ```bash
   DATABASE_URL=postgres://...pushinweight_shadow... \
     manage.py reconcile_account_duplicates --apply
   ```

   The command wraps each group in a SAVEPOINT (per KTD11). Per-group failures rollback that group only; the rest continue. Total wall-clock time ~30-60 min.

5. **Verify the AFTER state:**

   ```bash
   PGPASSWORD=... psql -c "SELECT count(*) FROM (SELECT handle FROM accounts WHERE handle IS NOT NULL GROUP BY handle HAVING COUNT(*) > 1) t"
   ```

   Expected: **462** (the no-integer residual groups; resolved by Phase 2 below).

   ```bash
   PGPASSWORD=... psql -c "SELECT count(*) FROM posts p JOIN accounts a ON a.author_id = p.author_id WHERE a.author_id !~ '^[0-9]+$'"
   ```

   Expected: **1,965** (the no-integer residual posts).

6. **Deploy to apply the unique-index migration** (`0009_accounts_handle_unique_ci`):

   The next Render deploy runs `./build.sh` → `manage.py migrate` → migration 0009. The migration's precheck confirms dup count is ≤ 1 per handle. **If precheck fails, the deploy aborts with a clear operator message** (no silent breakage).

   Verify after deploy:
   ```bash
   PGPASSWORD=... psql -c "SELECT indexname FROM pg_indexes WHERE indexname = 'uniq_accounts_handle_lower'"
   ```

   Expected: one row.

## Phase 2 — resolving the residual 462 no-integer groups

Trigger condition: ≥24 hours of clean TwitterAPI 200 responses in the harvest cycle (which is currently suspended; Phase 2 requires U15 resume first).

```bash
DATABASE_URL=postgres://...pushinweight_shadow... \
  manage.py reconcile_account_duplicates --apply --residual-only
```

Expected outcome: dupes 462 → 0, posts-at-placeholder 1,965 → 0, account_post_appearances → 0, brands_accounts → 0.

The `--residual-only` flag skips groups that already have an integer row (already handled by Phase 1) and processes only the 462 all-placeholder groups.

## Event log

### 2026-07-30 — Plan start (U9 BEFORE pins verified)

- **Operator**: Claude (per /goal)
- **Audit (live shadow DB)**: 2,142 duplicate handle groups, 20,079 posts at placeholder, 6,803 APAs, 95 brands_accounts, 0 companies_accounts. All BEFORE pins PASS via `scripts/u9_live_pin.py`.
- **U10 reconciliation command**: shipped to `monitor/management/commands/reconcile_account_duplicates.py`. Dry-run validated (1811 merge groups, ~13.5K placeholder accounts to delete). Apply path not yet executed — operator decision needed before U11 deploy.
- **U11 migration**: shipped to `core/migrations/0009_accounts_handle_unique_ci.py`. Precheck verified (refused with "still has 2142 duplicate handle groups" against the current live state, exactly as designed).
- **Next step**: operator decision — apply U10 reconciliation now, then deploy U11 in the next Render deploy?

## Notes for future sessions

The migration's precheck exists specifically to fail LOUDLY before the unique index build fails silently with `contains duplicated values`. This pattern is the inverse of the 2026-07-28 denormalization incident where the failure was silent — every step in U10/U11 must produce a clear operator-facing error or success message, never an ambiguous state.

The apply path is slow (~30-60 min for 2K groups). Run it during low-traffic windows; the cron is paused so there's no harvest contention, but a partial-apply run can leave the DB in a half-reconciled state if interrupted. Always re-run with `--apply` (idempotent) to complete; never `--dry-run` after a partial apply — dry-run doesn't write, so the half-reconciled state persists.

If `--apply` fails partway through, inspect `pg_stat_activity` for a hung cursor and re-run `--apply` (idempotent: groups whose canonical row is already integer and placeholders already deleted are skipped because the duplicate group no longer exists).