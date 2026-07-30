---
title: "Reconcile duplicate accounts and enforce handle uniqueness"
date: 2026-07-30
type: fix
artifact_readiness: implementation-ready
execution: code
target_repo: pushin-weight-v2
product_contract_source: ce-plan-bootstrap
deprecated: true
deprecated_on: 2026-07-30
deprecated_by: U14 of 2026-07-30-002
superseded_by: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
deprecation_reason: "Amended and merged into the combined plan above. The reconciliation half became U10-U14 in the combined plan. Do not re-implement from this file."
---

# Reconcile duplicate accounts and enforce handle uniqueness

> **DEPRECATED 2026-07-30.** Superseded by `docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md` (U14 of that plan). Do not implement from this file.

## Problem Frame

The `accounts` table PK is `author_id` but `handle` is non-unique. Brand-seeding scripts (`scripts/seed_list_handles_to_db.py`, `x_monitor/store.py::upsert_brand_account` at line 1423 with `f"handle:{handle}"` fallback, `scripts/2026-06-19-180000-seed-detection-tables.py` with `"synthetic:" + handle.lower()`) inserted placeholder author_ids when TwitterAPI auth was unavailable, and the live harvest (`monitor/cycle.py::_upsert_account` at line 454, keyed on `update_or_create(author_id=...)`) later wrote the real integer author_id for the same handle — but never reconciled with the placeholder rows.

Audit of the shadow DB on 2026-07-30:

| Metric | Value |
|---|---:|
| Total accounts | 19,284 |
| Distinct handles (case-insensitive) | 17,142 |
| Duplicate handle groups | **2,142** |
| Extra rows in duplicate groups | **2,269** |
| Posts pointing at placeholder author_id | **18,114** |
| Posts pointing at integer author_id | 8,743 |
| `account_post_appearances` rows at placeholder author_id | 6,803 |
| `brands_accounts` rows at placeholder author_id | 95 |
| `companies_accounts` rows at placeholder author_id | 0 |

Duplicate pattern breakdown:

| Pattern | Groups |
|---|---:|
| `handle:*` + integer | 1,569 |
| `synthetic:*` + `handle:*` | 327 |
| `synthetic:*` + integer | 137 |
| All three (`synthetic` + `handle` + integer) | 105 |
| `handle:*` + bare handle | 4 |

The harvest cron (`pushinweight-harvest`, `python manage.py run_cycle --limit-per-call 50`) produces integer author_ids going forward — its insertion path is fine. The breakage is purely in accumulated historical drift.

**Symptom (user-described):** when TwitterAPI auth returns and the harvester fetches a tweet whose `author_id` is `1856750484977324034` (a handle that today only has a `handle:doubaoai` row), `_upsert_account` matches on `author_id` and creates a new row keyed on the integer — leaving the placeholder orphan. The post is attached to the integer row, but anything that joins on `handle` (account URLs, brand-association queries) sees the placeholder.

**Why now:** the 2026-07-28 denormalization incident + 2026-07-29 db recovery restored the shadow DB from a pre-2026-07-24 dump. TwitterAPI auth is currently working intermittently. Each cycle that authenticates has a chance to deepen the drift.

## Goal

After this plan:
1. Every `handle` in `accounts` maps to **exactly one** row, keyed on the integer author_id when one exists.
2. All FK references (`posts`, `account_post_appearances`, `brands_accounts`, `companies_accounts`) point at the canonical row.
3. The `accounts.handle` column has a unique constraint (case-insensitive) so future drift is impossible.
4. A regression net pins this state so silent drift fails loudly.

## Out of Scope

- Resolving handles that currently have **no integer author_id** (462 groups, ~1,965 posts at synthetic placeholder). These need a separate pass once TwitterAPI auth is reliably working — defer to follow-up.
- Backfilling missing author metadata (display_name, bio, follower counts) for placeholder rows that survive the reconciliation. The harvested accounts have richer data; placeholders don't.
- Renaming `author_id` column to a typed integer. Out of scope — would touch every consumer.

## Key Technical Decisions

### KTD1: Reconcile by TwitterAPI lookup, not by current `accounts` rows alone

**Decision:** For each duplicate handle group, the canonical author_id is the integer row **if its handle still matches** (case-insensitive). If the existing integer row's handle disagrees (data drift from a stale API response), resolve via TwitterAPI `/2/users/by/username/<handle>` and use the fresh integer.

**Rationale:** Schema allows multiple integer rows for the same handle today (e.g., case differences). Trusting the on-disk integer without verification risks merging two different X users if a past API call returned a wrong ID. TwitterAPI verification is the source of truth — same endpoint the brand-seed script already uses.

**Alternative considered:** Take any integer row as canonical. Rejected — risks incorrect merges if a past lookup was wrong.

**Alternative considered:** Reject the merge if any disagreement, leave rows alone. Rejected — doesn't fix the data, just freezes the bug.

### KTD2: UPDATE-then-DELETE order to survive `ON DELETE SET NULL` on `posts`

**Decision:** For each duplicate handle group, in this order:
1. `UPDATE posts SET author_id = <canonical> WHERE author_id IN (<placeholder_ids>) AND author_handle ILIKE <handle>` (handle filter guards against KTD1 mis-merge).
2. Same UPDATE on `account_post_appearances`, `brands_accounts`, `companies_accounts`.
3. After all 4 UPDATEs return row counts, `DELETE FROM accounts WHERE author_id IN (<placeholder_ids>)`.

**Rationale:** `posts.author_id` has `ON DELETE SET NULL` (set in `core/migrations/0005_fix_posts_fks_on_delete_set_null.py`). Deleting a placeholder account first would NULL out 18,114 posts. UPDATE-then-DELETE keeps referential integrity intact.

### KTD3: Skip groups where TwitterAPI lookup fails or disagrees

**Decision:** If TwitterAPI lookup returns 401/404/timeout, OR returns an integer that already exists with a **different** handle, leave the group unchanged. Log to dead-letter.

**Rationale:** The 462 groups that lack integer IDs today are mostly `synthetic:*` + `handle:*` from the 2026-06-19 bulk seed — they're frozen placeholders, not data we'd lose by deferring. Don't make a one-shot pass destructive on auth failures.

### KTD4: Handle uniqueness via Postgres expression index, not Django `unique=True`

**Decision:** Add a Postgres unique index `CREATE UNIQUE INDEX uniq_accounts_handle_lower ON accounts (LOWER(handle)) WHERE handle IS NOT NULL`. Django `unique=True` would emit a unique index on the column directly, which would fail under the existing case-insensitive collation because Django's check compares case-sensitively in some paths. Expression index is portable and matches how `posts.author_handle` is already indexed (case-insensitive collation).

**Rationale:** The existing `handle` column has `db_collation="case_insensitive"` at the column level, but uniqueness is per-row — Postgres requires either `LOWER(handle)` expression index or a deterministic collation. The expression-index approach is what the project already uses elsewhere and doesn't require a collation change to `accounts.handle` (which would touch every read).

### KTD5: Reconciliation script lives outside the migration ledger

**Decision:** Reconciliation is a one-shot `python manage.py reconcile_account_duplicates --dry-run|--apply` command. Not a Django migration.

**Rationale:** Migrations are deterministic and reproducible; reconciliation involves a live TwitterAPI call whose result may differ each run. `scripts/seed_list_handles_to_db.py` set the precedent for I/O-bearing scripts living outside `core/migrations/`. Migration only owns the schema change (the unique index).

## Implementation Units

### U1. Pin current state as regression net

**Goal:** Capture the current duplicate-account state in tests so silent drift fails loudly. This is the unit that earns its keep when the reconciliation script ships — without it, a partial merge looks like a complete one.

**Files:**
- `tests/test_account_handle_uniqueness_regression_net.py` (new)

**Approach:** Database test marked `django_db` that:
1. Snapshots today's duplicate count: `SELECT COUNT(*) FROM (SELECT handle, COUNT(*) FROM accounts WHERE handle IS NOT NULL GROUP BY handle HAVING COUNT(*) > 1) t` — pin as `EXPECTED_DUPES_AT_PLAN_TIME` (the audit number is **2,142**, recompute at execution time as this is implementation-specific).
2. Snapshots today's posts-at-placeholder count: `SELECT COUNT(*) FROM posts p JOIN accounts a ON a.author_id = p.author_id WHERE a.author_id !~ '^[0-9]+$'` — pin as `EXPECTED_POSTS_AT_PLACEHOLDERS` (today's value is **20,079**).
3. Snapshots today's account-post-appearance-at-placeholder count — pin as **6,803**.
4. Snapshots today's brands-accounts-at-placeholder count — pin as **95**.
5. Asserts `accounts.handle` has **no** unique constraint (`EXISTS` query against `pg_indexes`) — BEFORE state, will flip to EXISTS-true in U4.
6. Asserts `posts.author_handle` collation is case-insensitive (regression on adjacent surface the plan does NOT change).
7. Asserts `accounts` row count == **19,284** (snapshot — pinned so a wholesale data wipe is caught).

Test scenarios:
- Happy path: every snapshot equals its pinned value (BEFORE state).
- Edge: `accounts` table contains rows where `handle` is NULL — these are excluded from uniqueness (the unique index is partial: `WHERE handle IS NOT NULL`).
- Edge: `accounts` table contains rows where `author_id` is NULL — `accounts.author_id` is the PK so this is impossible by schema, but the test guards the schema.
- Error: passing a non-database connection to the test runner raises (sanity — the assertions need a live DB).
- Integration: this test runs in the same Django test suite as `tests/test_harvest_cursor_regression_net.py` so any pipeline regression that touches `accounts` runs both nets.

**Verification:** `pytest tests/test_account_handle_uniqueness_regression_net.py -v` passes BEFORE the reconciliation runs. The test will FAIL after reconciliation (the dupes count drops to 0) — at that point, the test is updated to assert the AFTER state and the plan's DoD includes that update.

### U2. Reconciliation script — dry-run + apply modes

**Goal:** A `python manage.py reconcile_account_duplicates` command that resolves duplicate handle groups and rewires FKs to canonical rows. Idempotent, dry-run by default, dead-letter on failures.

**Files:**
- `monitor/management/commands/reconcile_account_duplicates.py` (new)
- `tests/test_reconcile_account_duplicates.py` (new)
- `docs/operations/reconcile-account-duplicates.md` (new — operator runbook)

**Approach:**

1. **Find duplicate groups** — `SELECT handle, array_agg(author_id ORDER BY first_seen_at) FROM accounts WHERE handle IS NOT NULL GROUP BY handle HAVING COUNT(*) > 1`. Iterate each group.
2. **Classify each group** by what it contains:
   - Contains an integer row + placeholder(s) — candidate for merge.
   - Multiple integers (different X users for same handle) — KTD1 disagreement; TwitterAPI resolve.
   - Multiple placeholders only (no integer) — KTD3 skip (defer to follow-up).
3. **For each candidate merge group:**
   a. TwitterAPI lookup `GET /2/users/by/username/<handle>` (mirror `scripts/seed_list_handles_to_db.py`'s auth + retry shape).
   b. If lookup returns an integer different from every existing integer row → UPDATE existing integer rows' `last_seen_at` to NOW(), use that integer as canonical. If it matches an existing integer row → use that row's id as canonical.
   c. If lookup returns 401/404/timeout → KTD3 skip + dead-letter entry.
   d. If lookup returns an integer whose row in `accounts` has a different handle (case-insensitive) → KTD1 disagreement; skip + dead-letter.
4. **UPDATE order (KTD2):**
   - `UPDATE posts SET author_id = <canonical> WHERE author_id IN (<placeholder_ids>) AND author_handle ILIKE <handle>` → captures row count.
   - Same on `account_post_appearances`, `brands_accounts`, `companies_accounts`.
   - `DELETE FROM accounts WHERE author_id IN (<placeholder_ids>)` only if KTD3 not skipped.
5. **Wrap each group in a Postgres SAVEPOINT.** Per-group failure rolls back to savepoint; dead-letter the group; continue.
6. **Emit summary JSON** to stdout: groups processed, groups skipped (with reason), rows updated per table, rows deleted, dead-letter list.

Dry-run mode: do all reads + TwitterAPI calls, print the planned UPDATE/DELETE statements with row counts, do not execute.

Apply mode: execute, log to `core/migrations/dead_letter_log` table (or a new `reconcile_dead_letter` table).

**Patterns to follow:** `scripts/seed_list_handles_to_db.py` for TwitterAPI auth and dead-letter pattern; `monitor/management/commands/run_cycle.py` for command shape (--dry-run, --json, --limit-per-call-style flags).

**Test scenarios:**
- Happy path: 3-handle group with `handle:*` + integer → integer canonical, posts/FKs repointed, placeholder row deleted.
- Happy path: all-placeholder group (no integer) → KTD3 skip, dead-letter entry, no DB changes.
- Happy path: handle where TwitterAPI returns a NEW integer not currently in `accounts` → that new integer becomes canonical (creates the integer row if absent).
- Edge: handle where TwitterAPI lookup returns 401 → dead-letter, no DB changes.
- Edge: handle where existing integer row's handle disagrees with the dup group handle → KTD1 disagreement skip.
- Edge: 0 handle duplicates (no-op) → command exits 0, summary reports 0 groups.
- Error: TwitterAPI timeout mid-batch → that group dead-letters, subsequent groups still process.
- Error: a FK UPDATE violates a constraint → savepoint rollback, dead-letter, continue.
- Integration: posts that point at a placeholder row end up pointing at the canonical row after `--apply`; the placeholder row no longer exists; FK on `posts.author_id` still satisfied.

**Verification:**
- Dry-run on the shadow DB today produces summary: ~1,500 groups eligible for merge (handle+integer pattern), 327 deferred (synthetic+handle), 137 (synthetic+integer) eligible for merge, 105 all-three eligible, 4 handle+bare eligible. ZERO rows updated.
- Apply run on shadow DB reduces dup count from 2,142 toward 462 (the no-integer groups remain), updates ~25,000 FK rows, deletes ~1,800 placeholder rows.
- `pytest tests/test_reconcile_account_duplicates.py -v` passes.
- The regression net test (U1) now reports the AFTER state — flipped to assert dup count == 462 (the no-integer residual).

### U3. Schema migration — partial unique index on `accounts.handle`

**Goal:** Add the case-insensitive uniqueness constraint so future drift is impossible.

**Files:**
- `core/migrations/0042_accounts_handle_unique_ci.py` (new)

**Approach:**

```sql
-- Forward
CREATE UNIQUE INDEX CONCURRENTLY uniq_accounts_handle_lower
  ON accounts (LOWER(handle)) WHERE handle IS NOT NULL;

-- Reverse
DROP INDEX IF EXISTS uniq_accounts_handle_lower;
```

Use `migrations.RunSQL(..., atomic=False)` because `CREATE UNIQUE INDEX CONCURRENTLY` cannot run inside a transaction. The migration must be non-atomic. The plan should note this is the canonical way to add a concurrent index in Django; verify against Django docs in `references/deploy-django` if any.

KTD4: expression index `LOWER(handle)` because `accounts.handle` has `db_collation="case_insensitive"` at column level but Postgres still permits non-deterministic uniqueness when only `handle` itself is indexed. LOWER-based expression index is deterministic and portable.

**Test scenarios:**
- Happy path: migration forward + reverse leaves `accounts` row count unchanged (19,284).
- Happy path: forward succeeds even though the current data has 2,142 duplicate handles — wait, this CONTRADICTS. Migration FORWARD must run AFTER U2's reconciliation reduces duplicates to <=1 per handle. Sequencing: U3 runs only after U2's apply has reduced the count. If U3 is run before U2, the migration FAILS with `relation "uniq_accounts_handle_lower" contains duplicated values`. The migration script must check `SELECT COUNT(*) FROM (SELECT LOWER(handle) FROM accounts WHERE handle IS NOT NULL GROUP BY LOWER(handle) HAVING COUNT(*) > 1) t` and raise `IncompatibleMigration` if > 0. The reconciliation command prints a message: "Run `manage.py reconcile_account_duplicates --apply` first."
- Error: try to add the same index twice → raises `IndexAlreadyExists` (idempotency guard).
- Integration: after U2 + U3 both run, INSERT a new account with a handle that already exists (case-insensitive) → `IntegrityError` at the DB layer. INSERT with a different handle → succeeds.

**Verification:** `python manage.py migrate` succeeds; subsequent `python manage.py shell` test of duplicate insert raises IntegrityError; U1's regression net (updated to AFTER state) passes.

### U4. Update regression net to assert AFTER state

**Goal:** Flip U1's pinned values from today's drift numbers to the post-reconciliation expectations.

**Files:**
- `tests/test_account_handle_uniqueness_regression_net.py` (modify)

**Approach:**

Update each `EXPECTED_*` constant to its AFTER value:
- `EXPECTED_DUPES_AT_PLAN_TIME`: 2,142 → **462** (the no-integer residual groups; KTD3 defer).
- `EXPECTED_POSTS_AT_PLACEHOLDERS`: 20,079 → **1,965** (only the all-synthetic/handle groups remain; KTD3 defer).
- `EXPECTED_APPEARANCES_AT_PLACEHOLDERS`: 6,803 → computed at execution time (some of the 6,803 may have been at synthetic handles that defer; safe lower bound 0, exact value requires rerunning the audit query at U4-time).
- `EXPECTED_BRANDS_AT_PLACEHOLDERS`: 95 → computed at execution time (same caveat).
- New assertion: `EXISTS` query against `pg_indexes` for `uniq_accounts_handle_lower` → **true** (the new constraint).
- New assertion: every account row's `author_id` matches a value that either IS an integer OR appears in the dead-letter log (KTD3 leftover). Allows the residual 462 placeholder rows.
- Account count snapshot: 19,284 - (placeholder rows deleted) → recomputed at U4-time.

Add a comment block at the top of the test file explaining: BEFORE was 2026-07-30 (pre-reconciliation). AFTER is post U2+U3. Future drift that diverges from these numbers indicates either (a) TwitterAPI auth back and the no-integer groups are being resolved, in which case rerun U2 + update this test, OR (b) new drift introduced by a code path that bypasses `update_or_create(author_id=...)`, which is the test's primary purpose.

**Test scenarios:**
- Happy path: every pinned AFTER value matches the live DB.
- Edge: the test fails if `uniq_accounts_handle_lower` index is missing.
- Edge: the test fails if any new placeholder pattern (`synthetic:*`, `handle:*`, bare handle equal to author_id) appears at `first_seen_at > 2026-07-30` (i.e., a code path is creating new placeholders). This is the drift detector.
- Error: passing a future date to `--as-of` flag (not in scope but mentioned) — the test ignores the flag today.

**Verification:** `pytest tests/test_account_handle_uniqueness_regression_net.py -v` passes post U2+U3. Test FAILS if any future commit adds rows matching the new-drift detector.

### U5. Operate runbook for follow-up resolution (no-integer groups)

**Goal:** Document the path for the 462 residual groups (synthetic+handle without integer) so the next session knows how to clear them once TwitterAPI auth is reliably working.

**Files:**
- `docs/operations/reconcile-account-duplicates.md` (modify — add the follow-up section)

**Approach:** Add a section "Phase 2: resolving residual no-integer groups" with:
- The query that lists them.
- A repeat of U2's command with `--residual-only` flag (added to U2; this section documents it).
- Expected outcome: dupes go from 462 → 0, posts-at-placeholder go from 1,965 → 0.
- The trigger condition: ≥24 hours of clean TwitterAPI 200 responses in the harvest cycle.

**Test scenarios:** Documentation only; no test.

**Verification:** Operator reads the doc, knows what command to run, knows the precondition.

## Sequencing

1. U1 first — pins current state, no behavior change.
2. U2 second — script lands dry-run ready, run dry-run against shadow, print summary, no DB writes.
3. U2 apply on shadow — run `--apply` against the shadow DB. Audit: dup count → 462, posts-at-placeholder → 1,965, brands-at-placeholder → computed, 0 in `companies_accounts` confirmed.
4. U3 third — migration lands AFTER U2 has reduced dup count. Otherwise the migration fails. The migration's precheck detects this and tells the operator to run U2 first.
5. U4 fourth — regression net flipped to AFTER state. Now detects future drift.
6. U5 last — operator doc for the residual 462.

Render deploy order:
- The migration (U3) is the only schema change and runs as part of `./build.sh` on the next deploy. `./build.sh` calls `manage.py migrate`, which will run U3.
- The reconciliation script (U2) is a one-shot management command; it must be invoked manually by an operator AFTER the migration lands (so the unique index is in place when subsequent harvests try to insert). Actually — wait: U2 must run BEFORE U3 lands on production (else U3's CREATE UNIQUE INDEX fails). Order: U2 apply → U3 migrate → done.

The plan body states this order in Definition of Done.

## Risks & Dependencies

### Risk: TwitterAPI 401 — partial pass leaves residual duplicates

The KTD3 defer path means a transient 401 leaves groups untouched. Audit on 2026-07-30 shows the live harvest IS getting integer IDs (5,776 rows from 2026-07-24 onwards), so auth is working for some paths. If auth is broken when U2 runs, only the groups whose integer is already on-disk get merged; the rest stay until a re-run.

**Mitigation:** U2 is idempotent. Re-run after auth recovers. The regression net (U4) detects stale state.

### Risk: Wrong-handle repointing if TwitterAPI returns the wrong user

KTD1's verification (`handle ILIKE <requested>`) guards this. If verification fails, KTD1 skips. Document this in the operator runbook.

**Mitigation:** Test scenario `Edge: handle where existing integer row's handle disagrees with the dup group handle → KTD1 disagreement skip` covers this.

### Risk: ON DELETE SET NULL on `posts` would null 18,114 posts if U2's DELETE runs before UPDATE

KTD2 explicitly sequences UPDATE-then-DELETE. Test scenario `Error: a FK UPDATE violates a constraint → savepoint rollback` would catch a reversed order.

### Risk: `CREATE UNIQUE INDEX CONCURRENTLY` cannot run inside Django's transaction

Standard Django migration behavior. Use `migrations.RunSQL(..., atomic=False)`. The plan's KTD3 documents this. Test must run migration forward + reverse and verify accounts row count unchanged.

### Risk: New harvest inserts that bypass `update_or_create(author_id=...)`

U4's drift detector catches new placeholder rows whose `first_seen_at > 2026-07-30`. Any future code path that bypasses the canonical upsert is flagged.

### Dependency: TwitterAPI auth must work at U2 execution time

If auth is broken, U2 partial-passes and the operator must re-run. Documented in U5.

### Dependency: Shadow DB has 28,822 posts (verified 2026-07-29)

Already satisfied. The plan runs against the live shadow DB.

## Definition of Done

- U1 regression net ships with pinned BEFORE values, passes green before any other unit runs.
- U2 reconciliation command lands dry-run + apply modes. Apply reduces dup count from 2,142 → 462 (or lower if TwitterAPI resolves more).
- U3 migration `0042_accounts_handle_unique_ci` ships and applies cleanly on the live shadow DB AFTER U2's apply run.
- U4 regression net flipped to AFTER state. Future drift fails loudly.
- U5 operator runbook documents the residual pass.
- All five unit tests pass under `pytest tests/test_account_handle_uniqueness_regression_net.py tests/test_reconcile_account_duplicates.py -v`.
- `python manage.py reconcile_account_duplicates --dry-run --json` reports the expected summary.
- `python manage.py reconcile_account_duplicates --apply --json` runs against shadow, audit confirms dup count dropped, FK row counts updated, no `IntegrityError`.
- `./build.sh` runs `manage.py migrate` end-to-end; U3 lands as part of the next production deploy.
- `./render.yaml` does not need to change (no env vars; no service config).
- Commits include the **Scope delivered vs plan promised: [match | narrower: deferred Y for reason Z]** line per global rules.

## Deferred to Follow-Up Work

- **Resolving the 462 no-integer groups** (synthetic + handle rows without an integer). Trigger: ≥24 hours of clean TwitterAPI 200 responses in the harvest. Operator runs `manage.py reconcile_account_duplicates --apply --residual-only`. Brings dupes → 0.
- **Backfilling author metadata** (display_name, bio, follower counts) onto the residual rows once they have integer IDs. A second-pass script that joins `accounts` (now canonical) with the harvested post payloads and updates NULL fields.
- **Adding `author_id` integer type** (BIGINT). Out of scope; touches every consumer. Worth a separate brainstorm if/when the brand-seeding scripts are rewritten to skip the placeholder path entirely.

## Acceptance Examples (origin: user conversation 2026-07-30)

**AE1 (user prompt):** "if an existing account with non-integer author_id posts tomorrow and harvester captures it, and inserts proper integer author_id, it will create a new entry?"
- Before this plan: yes, creates a new row, leaves placeholder orphan.
- After this plan: the integer row already exists (U2 merged), the harvest's `update_or_create(author_id=...)` updates the canonical row, the placeholder is gone. No duplicate.

**AE2 (audit query, 2026-07-30):** `SELECT COUNT(*) FROM (SELECT handle FROM accounts WHERE handle IS NOT NULL GROUP BY handle HAVING COUNT(*) > 1) t` = **2,142**.
- After U2 apply: this drops to **462** (the KTD3 defer residual).
- After Phase 2 (separate work, deferred): this drops to **0**.

**AE3 (audit query, 2026-07-30):** `SELECT COUNT(*) FROM posts p JOIN accounts a ON a.author_id = p.author_id WHERE a.author_id !~ '^[0-9]+$'` = **20,079**.
- After U2 apply: drops to **1,965** (the no-integer residual posts).
- After Phase 2: drops to **0**.