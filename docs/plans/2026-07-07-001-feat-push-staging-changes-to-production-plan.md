---
title: Push Staging Changes to Production - Plan
type: feat
date: 2026-07-07
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
---

## Goal Capsule

Apply the changes shipped to staging.db (`data/staging.db`, at v31) to production (`data/x_monitoring.db`). The schema+code layer is already in sync — production x_monitoring.db is at v31 with both migration 030 and 031 applied, and `origin/main` carries the source-code and config-file renames. The remaining rollout step is the data-side U4 seed port: run `scripts/2026-07-06-001-migrate-pushin-weight-records.py` against `data/x_monitoring.db` against the live `pushin_weight` Postgres source.

The plan lands all of this in one PR-sized, reviewable sequence: snapshot, dry-run, verify report, write, verify row counts, commit (no code commit needed — code is already shipped), document.

Stop conditions: the plan stops once `data/x_monitoring.db` row counts match the staging.db post-state across the 13 curated tables, or once a deviation is found that needs a human review.

## Product Contract

### Summary

Promote the staging-curated changes (schema 030 + 031, config slug renames, brands_accounts column rename, pushin_weight seed port) to the production `x_monitoring.db` so dashboard reads, attribution lookups, and classifier pipelines all reference the same brand slugs and seed records everywhere.

### Problem Frame

`data/staging.db` was built up from a v23-era production clone by applying migration 024-031 plus running the U4 seed-port script (`scripts/2026-07-06-001-migrate-pushin-weight-records.py`). Production `data/x_monitoring.db` was similarly brought to v31 and is at the same schema state, but has NOT yet had the U4 data port run — it has 0 rows in `brands_accounts`, `brand_search_terms`, and the 11 new `hf_orgs`. Running the U4 script against production closes that gap.

Without this rollout, dashboard pages that filter by the new brands (e.g. llama, mistral, nemo_megatron) display partial data, and `accounts`-side attribution lookups for the 49 ported rows return empty.

### Product Requirements

- R1. Production `data/x_monitoring.db` ends at the same row state as `data/staging.db` for the 13 curated tables after the script's `--write` run.
- R2. Re-running the script against production remains idempotent (second run produces zero `inserted` rows).
- R3. No data is lost: existing rows in production before the run are not deleted or modified; only `INSERT OR IGNORE` add.
- R4. The 3 brand slugs in production (`xiaomi_mimo`, `nvidia_nemo`, `sakana`) were already renamed to `mimo`, `nemo_megatron`, `sakana_ai` by migration 030 — verified before U4 starts so the script's FK lookups succeed.
- R5. The `accounts.author_id` (X user id) column is unchanged on production; only `brands_accounts.author_id` was renamed to `accounts_id`. Confirmed before U4 starts.
- R6. The JSON report written by U4 (`data/migration_logs/migrate-pushin-weight-records-<ts>.json`) is preserved for operator audit, matching the practice established in the staging run.
- R7. The migration procedure doc (`docs/notes/2026-07-06-pushin-weight-migration-procedure.md`) is already accurate for production; no edits needed there.

### Actors

- A1. **operator** — runs the script with `--write` against `data/x_monitoring.db` (no app restart needed; cron LaunchAgent picks up on its next cycle).
- A2. **reviewer** — checks the dry-run JSON report before approving `--write`.

### Acceptance Examples

- AE1. Dry-run (`python3 scripts/2026-07-06-001-migrate-pushin-weight-records.py --target-db data/x_monitoring.db --alias-map scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml --source-connstr ...` without `--write`) shows `accounts: {inserted: 49, skipped_duplicate: 0}`, `brands_accounts: {inserted: 62, ...}`, etc.
- AE2. `--write` mode completes in under 60 seconds (psql subprocess fan-out × ~14 tables).
- AE3. Post-write row counts in `data/x_monitoring.db` are: accounts +49 = 1571; brands_accounts +62 = 62; brands_companies +0 = 11 (unchanged); hf_orgs +11 = 22; brand_search_terms +72 = 72.
- AE4. Re-running with `--write` shows all `inserted: 0` and all `skipped_duplicate: <count>` matching the row count from AE3.
- AE5. Production dashboard endpoint (when exercised post-deploy) reads the 49 new accounts by id and returns them in `get_accounts(brand_id=...)` results without error.

### Scope Boundaries

**Inside scope**:

- Snapshot `data/x_monitoring.db` to a timestamped `.bak` next to the existing pre-migration backups.
- Run the U4 script in dry-run mode against production; capture the report and inspect for `dropped_no_alias` anomalies.
- Run the U4 script in `--write` mode against production; capture the report.
- Re-run the U4 script in `--write` mode to confirm idempotency.
- Diff post-state row counts against `data/staging.db`.

**Outside scope** (deferred — not for this PR):

- Pushing any further commits to origin (already done in `b32b2f2`).
- New dashboards, classifier changes, or source-of-truth work in pushin_weight Postgres.
- Reconciling any future divergence between staging and prod (e.g. if new accounts land on staging via a fresh classifier run before production re-sync).
- Cleaning up the per-clone `.bak` files in `data/` — operator will sweep these out-of-band after a confidence window.

### Dependencies

- D1. `origin/main` contains commits `1a1b702` (migration 030), `e0c5262` (U6 docs), `f604cf7` (U4 cherry-picked), `c7b877f` (U5 rename), `b32b2f2` (migration 031). Confirmed: `git log --oneline -5 origin/main`.
- D2. `data/x_monitoring.db` is at v31 with the schema renames in place. Confirmed: `sqlite3 data/x_monitoring.db "SELECT MAX(version) FROM _migrations;"` returns 31.
- D3. `pushin_weight` Postgres at `localhost:5432` is reachable on the host that runs the U4 script (`psql -c '\l'` succeeds).
- D4. `pyyaml` and Python's stdlib `sqlite3` are installed in the runtime that runs the script. (Both already present in any Python 3 environment that runs the existing test suite.)

## Planning Contract

### Key Technical Decisions

- KTD1. **In-place migration apply, NOT wholesale DB replacement.** Production `data/x_monitoring.db` continues to be opened with `Store(auto_migrate=True)`, which idempotently applies unrun migrations on open. The U4 script then does `INSERT OR IGNORE` against it. Replacing the production DB file with the staging file would lose the post-clone writes that have accumulated on production (further classifier runs, account collection, etc.); the in-place apply preserves them and treats the staging rows as an additive delta.
- KTD2. **Snapshot before `--write`.** A `data/x_monitoring.db.pre-u4-write.<ts>.bak` is created next to existing `.pre-031-apply` and `.pre-030-apply` backups. Rollback is then straightforward: `cp <bak> data/x_monitoring.db` and restart cron.
- KTD3. **Dry-run, then write, then idempotency re-run, all logged.** Three runs total produce three JSON reports in `data/migration_logs/` (dry-run, write, idempotency-check). Operator audits the dry-run report (especially `dropped_no_alias: 0` and `dropped_samples: []`) before approving the write.
- KTD4. **Use the same alias YAML the staging run used** (`scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml`). No edits needed; this is the canonical map already validated against staging.

### High-Level Technical Design

Sequencing — the rollout is sequential and gated on each previous step's success:

```
snapshot prod ──> dry-run U4 (capture report #1) ──> operator review ──>
  write U4 (capture report #2) ──> row count diff ──> idempotency re-run (capture report #3)
```

Failure paths:

- **dry-run reports `dropped_no_alias` rows**: stop, inspect the alias map. The map was validated against staging once; if production surfaces drops, the source-of-truth `pushin_weight` Postgres may have drifted, or an FK target was dropped on production. Update the alias map and re-dry-run.
- **`--write` errors mid-flight**: psql invocation exception propagates as a non-zero exit. Restore from `.pre-u4-write.<ts>.bak`. Investigate before retrying.
- **Idempotency re-run shows new inserts on round 2**: the script has a state-leak — stop. Read the script's `INSERT OR IGNORE` flow and the affected FK chain.

### Assumptions

- A1. The pushin_weight Postgres source is the same as during the staging run (i.e. no drift that changed account IDs, brand slugs, etc.). If there has been drift, dry-run will surface row counts different from staging; we compare against the staging JSON reports captured in `data/migration_logs/migrate-pushin-weight-records-20260706T083*.json`.
- A2. `psql` is installed at the default path `/opt/homebrew/opt/postgresql@17/bin/psql`. If on a different host, the script's `PSQL_BIN` constant must be edited.
- A3. The classifier cron (LaunchAgent `com.fuchitalee.x-monitor`) is paused or the operator runs during a quiet window so a concurrent classifier run doesn't race with the seed port writes. Reads are safe (`INSERT OR IGNORE`); writes from the classifier to `accounts` could overlap if it ingests a new account mid-port. A 5-min quiet window is sufficient; the script finishes in under 60 seconds.

### Sequencing

The plan's units are sequential:

- U1 (Snapshot) → U2 (Dry-run + review) → U3 (Write) → U4 (Idempotency check)

U1 is fast and unconditional. U2 produces a human-readable gate (the JSON report). U3 is the actual side-effect, gated on U2's review. U4 is the safety check. There is no parallel work — the units are intentionally serial because each depends on the previous one's report.

## Implementation Units

### U1. Snapshot `data/x_monitoring.db`

**Goal**: Create a `data/x_monitoring.db.pre-u4-write.<ts>.bak` snapshot, alongside the existing `pre-004-v2`, `pre-029-plan`, `pre-030-apply`, `pre-031-apply` backups.

**Requirements**: R3 (preserves existing data).

**Dependencies**: none.

**Files**: none created; just a file at `data/x_monitoring.db.pre-u4-write.<UTC-iso-ts>.bak`.

**Approach**: `cp data/x_monitoring.db data/x_monitoring.db.pre-u4-write.<ts>.bak`. Verify file size matches. The `pre-u4-write` prefix is consistent with the existing backups' `pre-<event>` naming pattern.

**Test scenarios**:
- After copying, `ls -la data/x_monitoring.db data/x_monitoring.db.pre-u4-write.*.bak` shows the two files have identical size.
- `sqlite3 data/x_monitoring.db.pre-u4-write.<ts>.bak "SELECT MAX(version) FROM _migrations"` returns 31 (so a fresh DB open recognizes we're at the same state).

**Verification**: `ls` confirms the backup file exists, has same size as source.

---

### U2. Dry-run U4 against production

**Goal**: Run the U4 script in dry-run mode against `data/x_monitoring.db` with the live `pushin_weight` Postgres source. Capture the JSON report. Operator reviews for `dropped_no_alias: 0` before approving the write.

**Requirements**: R1 (precondition), R4 (slugs already renamed), R6 (report written).

**Dependencies**: U1.

**Files**:
- `data/migration_logs/migrate-pushin-weight-records-<ts>.json` (created by script).

**Approach**: Run from `x-monitoring/` directory:

```
python3 scripts/2026-07-06-001-migrate-pushin-weight-records.py \
  --target-db data/x_monitoring.db \
  --alias-map scripts/2026-07-06-001-migrate-pushin-weight-records.aliases.yaml \
  --source-connstr "host=localhost port=5432 dbname=pushin_weight user=fuchitalee"
```

without `--write`. The script reads from Postgres via `psql`, resolves aliases, and computes inserts without committing. Report is printed to stdout and saved to the migration log.

**Test scenarios**:
- Report shows `accounts: { inserted: 49, skipped_duplicate: 0 }`.
- Report shows `brands_accounts: { inserted: 62 }`.
- Report shows `brands_companies: { inserted: 0 }` (production has the same 11 rows already).
- Report shows `hf_orgs: { inserted: 11, skipped_duplicate: 11 }` (11 curated pre-existed, 11 csv_seed new).
- Report shows `brand_search_terms: { inserted: 72 }` (production had 0).
- Report shows `discourse_keys: { inserted: 0, skipped_duplicate: 10 }` (production has the 10 keys).
- Report shows `dropped_no_alias: 0` for every per-table entry.
- Report shows `dropped_samples: []` for every per-table entry.
- Report shows `source_rows`, `inserted`, `skipped_duplicate`, `dropped_no_alias` for each of the 13 curated tables.

If any `dropped_no_alias > 0`, STOP and investigate (most likely: an FK target row on production was deleted, or the source-of-truth drifted — fix or update alias map before proceeding).

**Verification**: Operator eyeballs the JSON report and confirms `dropped_no_alias: 0` across all entries. Saves the report path for U3's reference.

---

### U3. Apply U4 to production (`--write`)

**Goal**: Run U4 with `--write` against `data/x_monitoring.db`. Capture the JSON report.

**Requirements**: R1, R3, R6.

**Dependencies**: U2 (operator-approved dry-run report).

**Files**:
- `data/x_monitoring.db` (writes via INSERT OR IGNORE).
- `data/migration_logs/migrate-pushin-weight-records-<ts2>.json` (created by script).

**Approach**: Same command as U2 with `--write` appended.

**Test scenarios**:
- Exit code 0.
- `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands_accounts"` returns 62.
- `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM accounts"` returns 1571 (= 1522 pre + 49 inserted).
- `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brand_search_terms"` returns 72.
- `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM hf_orgs"` returns 22.
- `sqlite3 data/x_monitoring.db "SELECT id, nickname FROM brands WHERE id BETWEEN 22 AND 27"` returns the 6 new migration-030 brands.
- `sqlite3 data/x_monitoring.db "SELECT id, namespace FROM hf_orgs WHERE discovered_via='csv_seed'"` returns the 11 post-clone hf_orgs with non-NULL `namespace` per migration `namespace` column.
- `sqlite3 data/x_monitoring.db "SELECT brand_id, accounts_id, role_id FROM brands_accounts LIMIT 5"` shows `accounts_id` (post-031 column) populated.

**Verification**: Row-count delta vs. the pre-migration pre-write baseline (`pre-u4-write.<ts>.bak`). Post-write counts minus pre-write counts equals the dry-run report's `inserted` column for each table.

---

### U4. Idempotency re-run

**Goal**: Confirm idempotency by re-running U4 with `--write`. Expected: zero inserts, all `skipped_duplicate: <count>` matching post-write row counts.

**Requirements**: R2.

**Dependencies**: U3.

**Files**: `data/migration_logs/migrate-pushin-weight-records-<ts3>.json` (created by script).

**Approach**: Same command as U3.

**Test scenarios**:
- Every per-table entry shows `inserted: 0` and `skipped_duplicate: N` where N equals the post-U3 row count.
- `companies: { inserted: 0, skipped_duplicate: 20 }` (20 in prod already).
- `discourse_keys: { inserted: 0, skipped_duplicate: 10 }`.
- All 13 tables: `inserted: 0`.
- `dropped_no_alias: 0` still.

**Verification**: Three reports now exist in `data/migration_logs/` (dry-run, write, idempotency), each consistent. The triple is the audit trail.

---

## Verification Contract

Behavioral checks (run after U4 completes):

1. `pytest tests/test_migrate_pushin_weight_records.py` — passes (these tests cover the script's alias resolver, FK chains, idempotency). 31 of 32 tests pass without live source; the gated live test is skipped.
2. `sqlite3 data/x_monitoring.db "SELECT MAX(version) FROM _migrations"` — returns 31.
3. `sqlite3 data/x_monitoring.db "PRAGMA table_info(brands_accounts)"` — column 1 is named `accounts_id`.
4. `sqlite3 data/x_monitoring.db "SELECT id, nickname FROM brands WHERE id IN (12, 14, 20)"` — returns `12|mimo`, `14|nemo_megatron`, `20|sakana_ai`.
5. `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands_accounts"` — returns 62.
6. `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brand_search_terms"` — returns 72.

A dry-run smoke of the dashboard's `get_accounts(brand_id)` (no actual network) confirms the new rows are queryable:

```
python3 -c "
from pathlib import Path
from x_monitor.store import Store
s = Store(Path('data/x_monitoring.db'))
rows = s.get_accounts('llama')
assert len(rows) == 2, f'expected 2 llama accounts, got {len(rows)}'
for r in rows:
    print(r['handle'], r['role_id'])
"
```

should print `AIatMeta 2\nalexandr_wang 3`.

## Definition of Done

Global criteria (all must be true):

- `data/x_monitoring.db.pre-u4-write.<ts>.bak` exists alongside source file, same size.
- Three `migrate-pushin-weight-records-<ts>.json` reports exist in `data/migration_logs/`: one dry-run, one write, one idempotency.
- Production `data/x_monitoring.db` row counts after write match the staging `data/staging.db` row counts across the 13 curated tables (per Section 8 of `tests/db_migration_tests/all_post_clone_records.md`, applied to `x_monitoring.db` instead).
- Idempotency re-run shows `inserted: 0` on every table.
- Source code in `origin/main` matches what's deployed — no manual edits to production binary; the binary reads the same config.yaml and ships the same code path used by staging.

Per-unit done criteria:

- **U1**: backup file exists, size matches.
- **U2**: dry-run JSON report exists; `dropped_no_alias: 0` across all tables.
- **U3**: `--write` exit 0; row counts match delta expectations; FK chain validated.
- **U4**: idempotency report exists; all `inserted: 0`.

Cleanup criterion: the `.pre-u4-write.<ts>.bak` file stays in `data/` for at least one operator-confirmed cycle. Out-of-band sweep is the operator's call, not a cleanup gate.

## Operational Notes

- Pause the `com.fuchitalee.x-monitor` LaunchAgent for ~5 minutes around the `--write` run to avoid classifier-process races on `accounts` and `brands_accounts`. `INSERT OR IGNORE` keeps reads safe; concurrent classifier writes to the same rows are the only failure mode.
- The `psql` connection string has not changed since the staging run (operator config — check `~/.pgpass` or env).
- After `--write`, restart the LaunchAgent manually (the `data/queries/` WatchPath doesn't trigger a restart, so config.yaml and code changes here don't restart on their own — but the existing restart cadence catches this naturally).

## Open Questions

None blocking. Two non-blocking items worth noting:

- QB1. Whether to also migrate the post-clone `data/staging.db` classifier smoketest artifacts (`tests/classifier_tests/smoketest_v20_post_*.txt`) to production's equivalent test suite — out of scope; these are staging-only smoketests.

## Sources & Research

- `docs/plans/2026-07-06-002-feat-pushin-weight-records-migration-plan.md` — origin plan for the staging-side work; the rollout here mirrors it on production.
- `x-monitoring/docs/notes/2026-07-06-pushin-weight-migration-procedure.md` — operator-facing procedure doc; reused verbatim, no edits.
- `x-monitoring/docs/reference/migration-report-schema.md` — JSON report schema reference.
- `x-monitoring/tests/db_migration_tests/all_post_clone_records.md` — staging post-state row inventory; serves as the comparison target for production post-state.
- `~/.claude/projects/-Users-fuchitalee-development-minimax-marketing/memory/x-monitor-migration-rollout.md` — established procedure: in-place migration apply, never wholesale DB replacement.
