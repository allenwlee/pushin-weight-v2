---
title: Sync x.com list → DB → yaml (brand-account graph)
date: 2026-07-09
type: feat
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
status: ready
---

# Goal Capsule

Restore yaml ↔ DB ↔ list parity for the brand-account graph. Today:

- `data/accounts/<brand>.yaml` files drift behind the DB — 27 confirmed list handles already exist in `brands_accounts` but their yaml entries are stale or missing.
- 10 list handles are NOT in the DB at all — list has them but no brand-attribution row.
- 9 DB rows reference handles NOT on the list — operator-curated additions outside the list workflow.
- 7 `brands_companies` rows are missing — sibling brands (`chatglm`, `sensenova`, `step`, `kwaiyii`, `wenxin`, `seed`) and the frontier `doubao` have no company mapping, so the operator's "every account belongs to every brand in the same company" cascade cannot fire for them.
- 3 migration-030 rename-duplicate yamls (`xiaomi_mimo.yaml`, `nvidia_nemo.yaml`, `sakana.yaml`) sit on disk unused.

Authority hierarchy (highest first): **DB → list → yaml**. The DB `brands_accounts` table is the operational source of truth (it's what `x_monitor/list_drift.py` and the post-fetch attribution read). The list `2067062923525275922` is the operator-curated set of accounts to monitor. The yaml files are operator-facing documentation that must mirror DB. After this plan: yaml ↔ DB are synced; list has 10 new entries; missing `brands_companies` rows are filled.

Stop conditions:
- All 5 units pass verification.
- DB→yaml regen is idempotent: a second run produces no diff.
- probe_filter_yield.py keeps/n_results vs baseline (`data/2026-07-08T065743Z-filter_yield_baseline.csv`) does not regress for any B-call group.

# Origin / source of truth

- Reconciliation note: `docs/notes/2026-07-09-list-yaml-reconciliation.md` (commit eec0934)
- Reconciliation methodology: 56 list handles (scraped via `/tmp/scrape_list_members_v3.js`) vs 16 yaml handles (extracted from `data/accounts/*.yaml`)
- DB state verified via `sqlite3 data/x_monitoring.db` queries against `brands_accounts`, `accounts`, `brands`, `companies`, `brands_companies`

# Product Contract

## Problem frame

The brand-account graph has three persistent stores that have drifted apart:

1. **List** (`x.com/i/lists/2067062923525275922/members`) — operator-curated "official and staff accounts of the open-weight models we've collected thus far." 56 handles.
2. **DB** (`brands_accounts` + `accounts`) — the operational source of truth used by post-fetch attribution and the dashboard. 65 distinct handles (45 of the 56 list handles are already here, plus 9 staff additions outside the list workflow, plus 11 non-list entries).
3. **YAML** (`data/accounts/<brand>.yaml`) — operator-facing documentation. 16 handles, mostly stale placeholders from migration-030 brand renames.

The drift creates three failure modes:

- New list handles don't surface in `scripts/post_fetch_smoketest.py` (Call A list-fan-in works because the list is queried live, but operator visibility into "what does Call A actually fetch" depends on yaml).
- The yaml's stale `handle:` values (e.g., `Llama`, `QwenLM`, `MoonshotAI`) point at accounts that aren't on the list, so the operator can't tell from yaml which accounts are actually being monitored.
- The 10 list-not-in-DB handles are silently dropped from Call A on the next cycle (Call A reads from list, but post-fetch attribution needs `brands_accounts` rows to credit the post to a brand).

## Requirements

- **R1.** All 56 list handles have at least one `brands_accounts` row (currently 45/56; gap = 10).
- **R2.** Every yaml `accounts[].handle` and `staff[].handle` matches a row in `brands_accounts` (currently broken for 9 yaml handles that don't match any DB row).
- **R3.** The 9 DB-not-on-list handles get an explicit operator disposition per-handle (keep-as-staff, keep-as-official, drop).
- **R4.** The 7 missing `brands_companies` rows are filled so the company→brand cascade resolves for all 20 enabled_models brands.
- **R5.** The 3 migration-030 rename-duplicate yamls are removed (operator-confirmed: no production code references them).
- **R6.** A regeneration script exists that produces yamls from the DB idempotently, so future drift is recoverable.
- **R7.** No regression in `scripts/probe_filter_yield.py` keeps/n_results vs the baseline CSV (`data/2026-07-08T065743Z-filter_yield_baseline.csv`).

## Scope boundaries

In scope:

- DB→yaml regeneration script (`scripts/regenerate_accounts_yaml.py`)
- Migration 033: insert 10 list-not-in-DB accounts + 7 missing brands_companies rows + cascade brands_accounts rows via company ownership
- Removal of 3 unused migration-030 duplicate yamls
- Verification: pytest + probe_filter_yield.py + new yaml/DB parity test

Out of scope (deferred to other plans):

- **Call B group rebalancing** (plan 005 from the 2026-07-08-004 follow-up). U1's regen does NOT change `config.yaml::call_b_groups`.
- **brand_keywords backfill** (plan 005, item 4). New handles may surface new gaps, but U1 doesn't fix them.
- **TwitterApiClient pagination** (plan 005, item 5). U1 doesn't change query shape.
- **min_faves=0 everywhere** (plan 005, item 3). U1 doesn't change query filters.
- **C2 spec for ERNIE** (plan 005, item 2). U1 doesn't change `call_c_specs`.
- **`Meituan_LongCat` brand enablement** — operator left this blank in the per-handle disposition table. Defer to a future plan that handles new-brand enablement.

## Actors

- **Operator** — runs the regeneration script, reviews the 9 DB-not-on-list disposition table, makes per-handle decisions.
- **Implementation agent** (`/ce-work` executor) — writes migration 033, the regen script, and the verification test.

## Key flows

- **F1. List → DB sync.** Operator curates list → operator runs regen → U3 inserts the missing 10 accounts into `accounts` + `brands_accounts` via the company cascade. Flow: yaml regeneration (U1) runs AFTER U3 lands, so yaml reflects the final DB state.
- **F2. DB → yaml regen.** Operator (or cron) runs `scripts/regenerate_accounts_yaml.py` → script queries `brands_accounts` grouped by brand_id → for each enabled_models brand, emits `data/accounts/<brand>.yaml`. Flow is idempotent: re-running produces byte-identical output.

## Acceptance examples

- **AE1.** After U1 lands, `diff <(python3 scripts/regenerate_accounts_yaml.py --emit /tmp/regen) data/accounts/` produces no output (regen output matches committed yamls).
- **AE2.** After U3 lands, `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands_accounts WHERE accounts_id IN (SELECT id FROM accounts WHERE LOWER(handle) IN ('bytedanceoss', 'carolglms', 'doubaoai', 'hailuo_ai', 'liulicheng10', 'mertunsal2020', 'stepfunai', 'xuanmingzhangai', 'zrdianjiao', 'chujiezheng'))"` returns ≥10.
- **AE3.** After U4 lands, `ls data/accounts/*.yaml | wc -l` returns 20 (one per enabled_models brand) — not 23.

# Planning Contract

## Key Technical Decisions

### KTD1: DB is the source of truth; yaml is regenerated from DB

The yaml files are documentation. The DB is the operational source of truth for post-fetch attribution and list drift detection. Hand-editing yamls to match the DB is the wrong approach — new DB entries would still drift yaml forward. Therefore U1 adds a regen script and treats yamls as build artifacts.

### KTD2: Regen preserves existing yaml fields

The current yamls carry operator-curated `display_name`, `verified`, `notes` annotations on 16 handles. The regen must preserve these by **reading the existing yaml before regenerating** and merging the operator-curated fields with the DB rows (DB has handle + role; yaml has display_name + verified + notes). The merge rule: DB is authoritative for `handle` and `role`; existing yaml is authoritative for `display_name`, `verified`, `notes`. New handles (in DB but not in existing yaml) get empty `display_name`, `verified=false`, `notes=""`.

### KTD3: One yaml per `enabled_models` brand, not per DB brand

The DB has 28 brand nicknames; `config.yaml::enabled_models` has 20. The 8 extras are siblings (`chatglm`, `sensenova`, `step`, `kwaiyii`, `wenxin`), frontiers (`seed`, `gpt`, `claude`, `gemini`, `gemma`, `grok`), and sentinels (`_unattributed`, `test_brand`). Regen emits one yaml per enabled_models brand; multi-brand DB rows (e.g., `kling_ai` on `kuaishou + kwaiyii`) are assigned to the FIRST enabled_models match (`kling_ai` → `kuaishou.yaml`). The non-enabled_models brand rows remain in the DB (used for attribution) but have no yaml file. The operator explicitly chose this scope (rejected Option B: regen all 28 DB brands; rejected Option C: add siblings to enabled_models first).

### KTD4: U3 is a single migration (033) plus a one-shot seed script

The 10 list-not-in-DB handles need:

1. 10 `accounts` rows (INSERT OR IGNORE on author_id — handles are unique by `author_id` not `handle`).
2. 10+ `brands_accounts` rows (one per company-owned brand; some handles map to 2 brands via the cascade, e.g., `doubaoai` → doubao + seed once the missing brands_companies row is filled).
3. 7 `brands_companies` rows (the missing sibling-brand mappings).
4. `author_id` values for the 10 handles need to come from the x.com API or operator-provided.

The plan adds migration 033 for #3 and uses a one-shot script for #1, #2, #4 because `author_id` lookup is best-effort via the API at seed time. The script is idempotent: re-running produces no diff after the first successful run.

### KTD5: Migration 033 is the canonical place to insert brands_companies rows

The 7 missing brands_companies rows are a known data gap, not a runtime concern. They go in migration 033, not in a separate utility. The migration is idempotent (`INSERT OR IGNORE`) so re-running is safe.

### KTD6: The 3 migration-030 duplicate yamls are removed with `git rm`, not renamed

Confirmed via `grep -rn "xiaomi_mimo\|nvidia_nemo\|sakana\.yaml" x_monitor/ scripts/ --include="*.py"` that no production code references these filenames. The only references are in `tests/test_migration_030_brand_rename.py` which checks the rename path (unaffected by file deletion — the test exercises the migration SQL, not the file existence). `git rm` is the right tool.

### KTD7: No `migrations/*.sql` changes affect the schema image

This plan adds migration 033 (data-only inserts; no CREATE/ALTER). Therefore `scripts/build_schema_image.sh` regeneration is NOT required (per `x-monitoring/CLAUDE.md` rules).

## Assumptions

- A1. The 10 list-not-in-DB handles' x.com `author_id` values can be fetched via the TwitterAPI.io user-lookup endpoint at seed time. If a lookup fails, the handle can still be inserted with `author_id = handle` (placeholder) and reconciled later.
- A2. The 9 DB-not-on-list handles can stay as staff entries (operator's default disposition). Operator may override per-handle.
- A3. `data/accounts/<brand>.yaml` files are NOT loaded by the runtime directly — production code reads from DB via `x_monitor/store.py`. The yaml files are operator-facing. (Verified by reading `x_monitor/accounts.py::load_accounts` — it does load yaml, but only at test/dev time, not in the post-fetch pipeline. The plan does NOT remove `load_accounts`; it just keeps yamls in sync with the DB.)
- A4. The probe_filter_yield.py baseline (`data/2026-07-08T065743Z-filter_yield_baseline.csv`) reflects the state BEFORE any of this plan's changes; comparisons are valid.

## Deferred to implementation

- Exact `display_name`, `verified`, `notes` values for the 10 newly-added handles (operator-curated, surfaced in U3's per-handle resolution table).
- Per-handle disposition for the 9 DB-not-on-list handles (operator-decide, surfaced in U2's table).
- Whether the regeneration script should be exposed as a CLI subcommand of `python3 -m x_monitor` or as a standalone script.

## Sequencing

1. **U5 first** (verification harness) — pytest + new yaml/DB parity test. Without these, we can't prove the plan worked.
2. **U2 second** (DB-not-on-list disposition table) — operator-decide per-handle before U1 regen runs.
3. **U4 third** (delete migration-030 duplicate yamls) — clean state before U1 regen.
4. **U3 fourth** (DB seed for 10 list-not-in-DB handles + 7 brands_companies rows) — DB must be final before U1 regen.
5. **U1 last** (regen script + run) — produces final yaml state.

# Implementation Units

## U1. DB → yaml regeneration script

**Goal:** Write `scripts/regenerate_accounts_yaml.py` that queries `brands_accounts` and emits `data/accounts/<brand>.yaml` for each `enabled_models` brand, preserving operator-curated `display_name`/`verified`/`notes` from existing yamls.

**Files:**

- `x-monitoring/scripts/regenerate_accounts_yaml.py` (create)
- `x-monitoring/data/accounts/*.yaml` (regenerated; no manual edits)
- `x-monitoring/tests/test_regenerate_accounts_yaml.py` (create; 5 tests minimum)
- `~/.claude/skills/custom-claude-skills/...` (no skill doc update needed — this is a maintenance script, not a user-facing workflow)

**Approach:**

The script reads `config.yaml::enabled_models` to determine which brand yamls to emit. For each brand:

1. Query `accounts` JOIN `brands_accounts` JOIN `roles` WHERE `brands.nickname = <brand>` ORDER BY `roles.key` (official first, then staff, then developer/employee).
2. Read the existing `data/accounts/<brand>.yaml` if it exists.
3. Merge: DB-authoritative for `handle` + `role`; existing-yaml-authoritative for `display_name` + `verified` + `notes`.
4. Emit yaml with `accounts:` and `staff:[]` sections following the existing schema (see `data/accounts/mimo.yaml` for the canonical shape).
5. Multi-brand DB rows (e.g., `kling_ai` on `kuaishou + kwaiyii`): assign to the first `enabled_models` match.
6. Idempotency: re-running on an already-regenerated state produces byte-identical output.

The script accepts `--emit <dir>` (default: `data/accounts/`) and `--brand <brand>` (default: all enabled_models). Use PyYAML for serialization; preserve key order; do not insert trailing whitespace.

**Patterns to follow:**

- `x-monitor` script conventions: shebang `#!/usr/bin/env python3`, `from __future__ import annotations`, top-level docstring with "Why" and "How to apply" notes.
- `x_monitor/store.py::read_companies()` (line 2441) — pattern for reading a registry table.
- `x_monitor/store.py::_company_int_id()` (line 2159) — pattern for slug→id lookup.
- `data/accounts/mimo.yaml` — canonical yaml shape (handle, display_name, role, verified, notes).

**Test scenarios:**

- Happy path: with a 3-brand test DB, run script, assert 3 yaml files emitted with correct `accounts:` lists.
- Idempotency: run twice, assert byte-identical output (`diff -q` or file hash).
- Multi-brand row assignment: a handle in `brands_accounts` for both `kuaishou` and `kwaiyii` (with `kuaishou` in `enabled_models` and `kwaiyii` NOT in `enabled_models`) ends up in `kuaishou.yaml`.
- Existing-yaml preservation: pre-existing `display_name` on `MiniMax_AI` survives a regen.
- New-handle insertion: a DB handle with no existing yaml entry gets `display_name=""`, `verified=false`, `notes=""`.

**Verification:**

- `python3 x-monitoring/scripts/regenerate_accounts_yaml.py --emit /tmp/regen-yamls/`
- `diff -r /tmp/regen-yamls/ x-monitoring/data/accounts/` → no output (regen matches committed state after U3 lands)
- `python3 -m pytest x-monitoring/tests/test_regenerate_accounts_yaml.py -v` → 5 tests pass

**Dependencies:** U5 (verification harness), U2 (operator disposition), U4 (cleanup), U3 (DB seed).

## U2. Investigate 9 DB-not-on-list handles

**Goal:** Produce a per-handle resolution table the operator fills in, deciding keep-as-staff vs. drop for each of the 9 handles currently in `brands_accounts` but not on the list `2067062923525275922`.

**Files:**

- `docs/notes/2026-07-09-list-yaml-reconciliation.md` (append a new section "DB-not-on-list handle dispositions")
- No code changes

**Approach:**

The 9 handles (per `sqlite3` query against `brands_accounts`):

| Handle | DB brand | DB role | Operator disposition (TBD) |
|---|---|---|---|
| `alexandr_wang` | llama | staff | TBD |
| `byteplusglobal` | doubao | official | TBD |
| `echojuliett` | upstage | staff | TBD |
| `eileental` | stepfun | staff | TBD |
| `honglaklee` | exaone | staff | TBD |
| `louszbd` | glm | staff | TBD |
| `robbyant_brain` | inclusionai | official | TBD |
| `shunyuyao12` | hunyuan | staff | TBD |
| `sophiamyang` | mistral | staff | TBD |

(Plus 9 more at brand_id 28, 23, 24, 25, 26, 27 — chatglm/sensenova/step/kwaiyii/wenxin sibling rows — but those are dual-brand entries from the company cascade and are out of scope for U2's per-handle decision; they stay in DB and don't get a yaml file since their brand is not in `enabled_models`.)

The reconciliation note gets an appended table with a `[operator-decision]` column. Operator fills in: `keep-as-staff` / `drop-from-DB` / `keep-as-official` / `move-to-list`.

**Resolution status (2026-07-09, operator-confirmed):**

After a lowercased recheck of the 9 plan-listed handles, all 9 were found to be on the list (case-mismatches or underscore-placement differences that the original eyeball pass missed) and were reclassified into Bucket 3a / 3b of the reconciliation note. The actual DB-not-on-list surface area is **3 handles** (`cara_catowner`, `skylermiao7`, `victorsuortiz`) — also resolved in U2's appended "Disposition table" section.

A **separate disposition table** was added under Bucket 3c (`### 3c. Uncertain — operator decision (~22)`) to capture the operator's curated brand + role decisions for the 20 list-handles that couldn't be confidently attributed to a brand in `enabled_models` from the eyeball pass. Resolution per the operator's 2026-07-09 disposition (`## Summary table` in the note):

| handle | brand | official/staff |
|---|---|---|
| `alexandr_wang` | `llama` | staff |
| `BytePlusGlobal` | `seed` | official |
| `CunxiangWang` | `glm` | staff |
| `echojuliett` | `upstage` | staff |
| `EileenTal` | `stepfun` | staff |
| `liulicheng10` | `stepfun` | staff |
| `louszbd` | `glm` | staff |
| `Meituan_LongCat` | — *(not in table 6)* | official |
| `mertunsal2020` | `mistral` | staff |
| `PaddlePaddle` | `ernie` | official |
| `robbyant_brain` | — *(not in table 6)* | official |
| `ShunyuYao12` | — *(bio insufficient)* | staff *(personal handle; brand unknown)* |
| `sophiamyang` | `mistral` | staff |
| `Stefania_druga` | `sakana_ai` | staff |
| `xiong_hui_chen` | `qwen` | staff |
| `xuanmingzhangai` | `qwen` | staff |
| `Zai_org` | `glm` | official |
| `ZhihuFrontier` | — *(not in table 6)* | official |
| `ZixuanLi_` | `glm` | staff |
| `zRdianjiao` | `glm` | staff |

**Operational consequence:** the 16 handles with a non-blank brand (`alexandr_wang`, `BytePlusGlobal`, …, `zRdianjiao`) get a `brands_accounts` row inserted via U3's seed script — they are NOT list-only handles. The 4 handles marked "— *(not in table 6)*" or "— *(bio insufficient)*" (`Meituan_LongCat`, `robbyant_brain`, `ZhihuFrontier`, `ShunyuYao12`) stay on the x.com list but get NO DB row — they are operator-curated industry people-of-interest or personal handles with insufficient brand evidence.

This means **U3's DEFAULT_SEED must be regenerated to include these 16 handles in addition to the original 10 list-not-in-DB handles**, for a total of 26 seed triples. The seed script (`scripts/seed_list_handles_to_db.py`) needs a new `--input` YAML or DEFAULT_SEED extension; the operator's `--no-api` placeholder path remains the auth-fallback (display_name stays blank per `seed_list_handles_to_db.py:237`).

**Test scenarios:** None (docs-only unit for the disposition table itself).

**Verification:**

- The reconciliation note is updated and committed (operator commits via their workflow).
- The 3 TBD rows in the DB-not-on-list disposition table are filled in.
- The 3c Summary table is filled in (operator action, not implementation).
- U3's `DEFAULT_SEED` is regenerated to include the 16 newly-resolved handles from 3c (operator + implementation agent).

**Dependencies:** U3 (the regenerated `DEFAULT_SEED` depends on U2's disposition table being filled in).

## U3. Seed 10 list-not-in-DB handles + 7 missing brands_companies rows

**Goal:** Insert the 10 list handles that are missing from the DB, plus fill the 7 missing `brands_companies` rows, via migration 033 + a one-shot seed script.

**Files:**

- `x-monitoring/x_monitor/migrations/033_seed_list_handles_and_sibling_brands_companies.sql` (create)
- `x-monitoring/scripts/seed_list_handles_to_db.py` (create; handles `author_id` lookup + brand_accounts cascade)
- `x-monitoring/tests/test_seed_list_handles_to_db.py` (create; 4 tests minimum)

**Approach:**

**Migration 033** (data-only inserts, idempotent via INSERT OR IGNORE):

```sql
-- Section 1: brands_companies rows for sibling brands (operator-confirmed 2026-07-09)
INSERT OR IGNORE INTO brands_companies (brand_id, company_id) VALUES
  ((SELECT id FROM brands    WHERE nickname='doubao'),
   (SELECT id FROM companies WHERE nickname='bytedance')),
  ((SELECT id FROM brands    WHERE nickname='seed'),
   (SELECT id FROM companies WHERE nickname='bytedance')),
  ((SELECT id FROM brands    WHERE nickname='chatglm'),
   (SELECT id FROM companies WHERE nickname='zhipu')),
  ((SELECT id FROM brands    WHERE nickname='sensenova'),
   (SELECT id FROM companies WHERE nickname='sensetime')),
  ((SELECT id FROM brands    WHERE nickname='step'),
   (SELECT id FROM companies WHERE nickname='stepfun_inc')),
  ((SELECT id FROM brands    WHERE nickname='kwaiyii'),
   (SELECT id FROM companies WHERE nickname='kuaishou_co')),
  ((SELECT id FROM brands    WHERE nickname='wenxin'),
   (SELECT id FROM companies WHERE nickname='baidu'));
```

**Seed script** (`scripts/seed_list_handles_to_db.py`):

Accepts a YAML or CLI table of `(handle, company_nickname, role)` triples. For each:

1. Look up x.com `author_id` via TwitterAPI.io `/2/users/by/username/<handle>` (best-effort; fall back to `author_id = handle` placeholder if lookup fails).
2. INSERT OR IGNORE INTO accounts (author_id, handle, display_name, first_seen_at).
3. For each `brand_id` linked to the company via `brands_companies`, INSERT OR IGNORE INTO brands_accounts.

The script is **idempotent**: re-running after a successful run produces no changes (UNIQUE constraints on `accounts.author_id` and `brands_accounts.(brand_id, accounts_id)` enforce this).

The 10 handles + company + role (operator-confirmed 2026-07-09):

| Handle | Company | Role |
|---|---|---|
| `bytedanceoss` | bytedance | official |
| `carolglms` | zhipu | staff |
| `chujiezheng` | alibaba | staff |
| `doubaoai` | bytedance | official |
| `hailuo_ai` | minimax | official |
| `liulicheng10` | stepfun_inc | staff |
| `mertunsal2020` | mistral_ai | staff |
| `stepfunai` | stepfun_inc | official |
| `xuanmingzhangai` | alibaba | staff |
| `zrdianjiao` | zhipu | staff |

(`meituan_longcat` excluded — operator left blank; defer to a future new-brand-enablement plan.)

After the seed script runs, the company cascade will produce these `brands_accounts` rows:
- `doubaoai` → doubao + seed (2 brands)
- All others → 1 brand

Total new `brands_accounts` rows: 11.

**U2 dependency (2026-07-09 update):** U3's seed script also needs to seed the 16 handles from the reconciliation note's 3c Summary table that have non-blank brand assignments. The 4 handles marked "— *(not in table 6)*" / "— *(bio insufficient)*" (`Meituan_LongCat`, `robbyant_brain`, `ZhihuFrontier`, `ShunyuYao12`) stay on the x.com list but get NO DB row.

The 16 U3-extended handles + company + role (per the 3c Summary table):

| Handle | Company | Role |
|---|---|---|
| `alexandr_wang` | *(none — llama has no brands_companies row)* | staff |
| `BytePlusGlobal` | bytedance | official |
| `CunxiangWang` | zhipu | staff |
| `echojuliett` | *(none — upstage has no brands_companies row)* | staff |
| `EileenTal` | stepfun_inc | staff |
| `liulicheng10` | stepfun_inc | staff |
| `louszbd` | zhipu | staff |
| `mertunsal2020` | mistral_ai | staff |
| `PaddlePaddle` | baidu | official |
| `sophiamyang` | mistral_ai | staff |
| `Stefania_druga` | *(none — sakana_ai has no brands_companies row)* | staff |
| `xiong_hui_chen` | alibaba | staff |
| `xuanmingzhangai` | alibaba | staff |
| `Zai_org` | zhipu | official |
| `ZixuanLi_` | zhipu | staff |
| `zRdianjiao` | zhipu | staff |

**Note on missing companies:** 3 of the 16 handles (`alexandr_wang`, `echojuliett`, `Stefania_druga`) target brands that have no `brands_companies` row in the live DB (verified 2026-07-09). Per the seed script's design (`seed_list_handles_to_db.py:283-284`), the account row is inserted but the `brands_accounts` cascade produces 0 rows + a warning. Either:
- (a) operator adds the missing brands_companies rows via a new migration 034 (one row per missing brand: `meta→llama`, `upstage_inc→upstage`, `sakana→sakana_ai`), then re-runs U3 — preferred, closes the gap
- (b) operator accepts the warning and the 3 handles stay account-only (yaml regen will surface them as `staff:` entries with no parent-brand cascade)

After the seed script runs the combined 26-triple DEFAULT_SEED, the company cascade will produce these `brands_accounts` rows (estimated):
- `doubaoai` → doubao + seed (2 brands; cascade uses bytedance → doubao + seed via migration 033's brands_companies rows)
- `BytePlusGlobal` → seed (1 brand)
- All others with a company → 1 brand
- 3 handles without a company → 0 brands_accounts rows + warning

**Total new `brands_accounts` rows: ~24 (was 11 in the original 10-triple plan).** Some handles may overlap with existing rows (e.g. `louszbd`, `sophiamyang`, `xuanmingzhangai`, `zRdianjiao`, `mertunsal2020`, `liulicheng10` already appear in the original 10); the script's `INSERT OR IGNORE` makes re-runs safe.

**Patterns to follow:**

- `x-monitor` migration file structure (see `032_seed_frontier_companies_brands_accounts.sql` for the most recent precedent).
- `x_monitor/store.py` for read/write patterns.
- Migration 032 Section 4 (accounts INSERT) and Section 5 (brands_accounts INSERT) for the exact column shape.

**Test scenarios:**

- Happy path: run script with 3 handles, assert 3 new `accounts` rows + N new `brands_accounts` rows (where N = sum of company-owned brand counts).
- Idempotency: run script twice, assert total row counts unchanged on second run.
- Missing brand_company: a handle whose company has no `brands_companies` rows produces zero `brands_accounts` rows (script should warn, not error).
- `author_id` lookup fallback: when the API lookup fails, the script inserts with `author_id = handle` (placeholder), not raising.

**Verification:**

- `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands_accounts WHERE accounts_id IN (SELECT id FROM accounts WHERE LOWER(handle) IN ('bytedanceoss', 'carolglms', 'doubaoai', 'hailuo_ai', 'liulicheng10', 'mertunsal2020', 'stepfunai', 'xuanmingzhangai', 'zrdianjiao', 'chujiezheng'))"` → ≥10
- `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands_companies"` → 22 (was 15)
- `python3 -m pytest tests/test_seed_list_handles_to_db.py -v` → 4 tests pass

**Dependencies:** U5 (verification harness).

## U4. Remove 3 migration-030 duplicate yamls

**Goal:** Delete `xiaomi_mimo.yaml`, `nvidia_nemo.yaml`, `sakana.yaml` (the 3 yamls left over from the migration-030 brand renames that point at the same handles as `mimo.yaml`, `nemo_megatron.yaml`, `sakana_ai.yaml` respectively).

**Files:**

- `x-monitoring/data/accounts/xiaomi_mimo.yaml` (delete)
- `x-monitoring/data/accounts/nvidia_nemo.yaml` (delete)
- `x-monitoring/data/accounts/sakana.yaml` (delete)

**Approach:**

```
git rm x-monitoring/data/accounts/xiaomi_mimo.yaml
git rm x-monitoring/data/accounts/nvidia_nemo.yaml
git rm x-monitoring/data/accounts/sakana.yaml
```

Pre-flight check (must run before deletion):
- `grep -rn "xiaomi_mimo\|nvidia_nemo\|sakana\.yaml" x_monitor/ scripts/ --include="*.py"` → only `tests/test_migration_030_brand_rename.py` references the old slugs (and only in the rename-path test, which doesn't check file existence).
- `ls data/accounts/ | wc -l` → was 23; after deletion → 20.

**Test scenarios:**

- `git status` shows 3 deleted files, no other changes.
- `find data/accounts -name "*.yaml" | wc -l` returns 20.
- `grep -l "xiaomi_mimo\|nvidia_nemo" data/accounts/*.yaml` returns nothing.

**Verification:**

- `ls data/accounts/*.yaml | wc -l` → 20
- `git diff --stat` shows only the 3 deletions

**Dependencies:** None (independent cleanup).

## U5. Verification harness — yaml/DB parity + probe regression

**Goal:** Add a pytest that asserts yaml ↔ DB parity for every enabled_models brand, plus a regression test that re-runs `scripts/probe_filter_yield.py` and asserts no B-call group dropped below the baseline CSV.

**Files:**

- `x-monitoring/tests/test_yaml_db_parity.py` (create; 3 tests minimum)
- `x-monitoring/tests/test_probe_filter_yield_no_regression.py` (create; 1 test, gated on live API key availability — similar to existing live-only test in `tests/test_probe_filter_yield.py`)

**Approach:**

`test_yaml_db_parity.py`:

For each `enabled_models` brand:
1. Load `data/accounts/<brand>.yaml`.
2. Query `accounts` JOIN `brands_accounts` WHERE `brands.nickname = <brand>`.
3. Assert that every yaml `handle:` appears in the DB query (yaml ↛ DB leak — yaml has handles the DB doesn't know about).
4. Assert that the union of yaml `accounts[].handle` and yaml `staff[].handle` covers all DB rows for that brand EXCEPT handles explicitly flagged as `[expected-missing]` in the yaml (a future feature; for now, full coverage).

`test_probe_filter_yield_no_regression.py`:

Gated on `os.environ.get("XMON_PROBE_KEY")` (matches existing live-only test pattern). Reads the baseline CSV at `data/2026-07-08T065743Z-filter_yield_baseline.csv`, runs the probe for each B-call group, asserts `kept/n_results >= 0.8 * baseline_kept/baseline_n_results` (allowing 20% degradation from natural variance; tighter thresholds would flag false regressions from organic post-flow variation).

**Test scenarios:**

- Parity test: 20 brands × 1 query each = 20 brand-level parity assertions.
- Idempotency assertion: re-running U1's regen script then the parity test must pass (no drift).
- Probe regression test: live, gated on env var.

**Verification:**

- `python3 -m pytest tests/test_yaml_db_parity.py -v` → 3+ tests pass
- (Manual) `python3 -m scripts.probe_filter_yield --calls B1,B2,B3` (with live key) → no group regressed vs baseline

**Dependencies:** None (test infrastructure only).

# Verification Contract

## Repo-specific test commands

```bash
# Per-unit verification
python3 -m pytest tests/test_regenerate_accounts_yaml.py -v        # U1
# (U2 is docs-only — operator reviews the reconciliation note)
python3 -m pytest tests/test_seed_list_handles_to_db.py -v          # U3
# (U4 is git rm — no pytest)
python3 -m pytest tests/test_yaml_db_parity.py -v                    # U5

# Whole-plan verification (after all units land)
python3 -m pytest tests/ -v                                         # all tests
python3 scripts/regenerate_accounts_yaml.py                          # idempotency check
diff -r <(python3 scripts/regenerate_accounts_yaml.py --emit /tmp/x) data/accounts/  # no output
```

## Quality gates

- All pytest tests pass.
- Regen script is idempotent (re-run produces no diff).
- Migration 033 applies cleanly on a fresh DB (verified via `scripts/migrate.sh --dryrun` or equivalent).
- No `data/accounts/*.yaml` file references a handle not in `brands_accounts` (yaml ↛ DB leak).
- All 56 list handles have at least one `brands_accounts` row, **except for the 4 list-only handles** (`Meituan_LongCat`, `robbyant_brain`, `ZhihuFrontier`, `ShunyuYao12`) that are operator-curated as people-of-interest / personal handles with insufficient brand evidence per the 3c Summary table.
- `enabled_models` count = 20; `data/accounts/*.yaml` count = 20 (no duplicates from migration-030 left over).
- U3's expanded DEFAULT_SEED has 26 triples (10 original list-not-in-DB + 16 from 3c) and inserts ~24 new `brands_accounts` rows after the company cascade.

# Definition of Done

- All 5 units complete with verification passing.
- Plan numbered `2026-07-09-001` committed in `docs/plans/`.
- Migration 033 applied to `data/x_monitoring.db` (operator's manual apply, or via CI pipeline).
- `data/accounts/*.yaml` regenerated and committed.
- 3 migration-030 duplicate yamls removed via `git rm`.
- Reconciliation note's "DB-not-on-list handle dispositions" section filled in by operator.
- Reconciliation note's 3c Summary table filled in by operator (20 handles resolved: 16 get brands_accounts rows, 4 stay list-only).
- U3's `DEFAULT_SEED` regenerated to include 26 triples (10 + 16 from 3c).
- Optional: migration 034 to add missing brands_companies rows for `meta→llama`, `upstage_inc→upstage`, `sakana→sakana_ai` so the 3c handles without a company (`alexandr_wang`, `echojuliett`, `Stefania_druga`) get the cascade row.
- No regression in `scripts/probe_filter_yield.py` keeps/n_results vs baseline CSV.
- All future PRs that touch `brands_accounts` or `data/accounts/*.yaml` are caught by the new yaml/DB parity test.

# Appendix

## Source queries used

```sql
-- List of 56 list handles, lowercased
-- (scraped via /tmp/scrape_list_members_v3.js, normalized)

-- List of 16 yaml handles
-- (extracted from data/accounts/*.yaml, lowercased)

-- Diff: 7 in-both, 49 list-only, 9 yaml-only (lowercased, dedup)

-- 45 of 56 list handles already in brands_accounts
SELECT DISTINCT LOWER(a.handle)
FROM brands_accounts b
JOIN accounts a ON a.id = b.accounts_id
WHERE LOWER(a.handle) IN (...list handles...);

-- 11 list handles NOT in brands_accounts
comm -23 <(echo "$list_handles_lc") <(echo "$db_handles_lc");

-- 9 DB rows NOT on the list (excluding sibling-brand rows from non-enabled_models brands)
-- (computed by negative-set query)

-- 7 missing brands_companies rows (operator-confirmed mapping)
SELECT b.nickname, c.nickname AS should_own
FROM brands b
LEFT JOIN brands_companies bc ON bc.brand_id = b.id
LEFT JOIN companies c ON c.id = bc.company_id
WHERE b.nickname IN ('doubao','seed','chatglm','sensenova','step','kwaiyii','wenxin')
  AND bc.company_id IS NULL;
```

## Plan cross-references

- Plan 2026-07-08-004 — closed; baseline CSV at `data/2026-07-08T065743Z-filter_yield_baseline.csv`.
- Plan 2026-07-06-002 — pushin-weight migration; contains the pushin-weight company/brand slug aliases that informed the missing-row analysis.
- Plan 2026-06-18-195234 — original company-brand-account model; the table schema in this plan derives from that plan's design.
- Migration 030 — left the 3 duplicate yamls (U4 removes them).
- Migration 032 — recent frontier seed; this plan's seed pattern follows its structure.
- Memory `brand-keywords-migration-030-gap.md` — related but separate concern; the brand_keywords backfill is out of scope here (deferred to plan 005).
- Reconciliation note: `docs/notes/2026-07-09-list-yaml-reconciliation.md` (commit eec0934).

## Out-of-scope deferrals (per plan 005 from 2026-07-08-004)

- Call B group rebalancing
- brand_keywords backfill
- TwitterApiClient pagination
- min_faves=0 everywhere
- C2 spec for ERNIE
- `Meituan_LongCat` brand enablement