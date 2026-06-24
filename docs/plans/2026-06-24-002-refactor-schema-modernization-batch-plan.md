---
title: "Schema modernization: next migrations batch (011-019)"
type: refactor
status: planned
date: 2026-06-24
origin: user-curated migration list + replace-legacy-signals plan
---

# Schema Modernization: Next Migrations Batch

## Overview

This plan consolidates 9 distinct schema changes into a sequenced batch of migrations (slots 011-019), each independently shippable but ordered to minimize rework. The changes cover i18n column renames, enum table cleanup, the M:N mention rename, role value trimming, the `brand_search_terms` hybrid refactor, the text→numerical PK refactor, and the post_types/sentiments taxonomy implementation.

Each phase lands as its own PR where practical, so partial progress is shippable and reviewable.

## Problem Frame

The x-monitor DB has accumulated several inconsistencies that block the post_types/sentiments work and create operator friction:

- **Locale column naming is inconsistent** — `locale` is used in some places, but the project's i18n convention has converged on `lang` (matches the existing `data/translations/` and translator pipeline).
- **`engagement_tier_keys` / `engagement_tier_labels` are unused** — no production code path reads them, and the planned "rank accounts by followers + engagement" should be a control-layer query, not a DB-backed enum.
- **`post_mentions` is a 2-way join named singular-singular** — violates the plural-plural M:N convention just established in migration 010. If it stays singular-singular, future M:N mentions added alongside it will be inconsistent.
- **Enum tables follow a *plural-keys* + *plural-labels* pattern** (`signal_keys`, `role_keys`, `engagement_tier_keys`) which is inconsistent with the new direction (singular nouns: `signals`, `roles`).
- **Role values are bloated** — `official | community | researcher | press | vendor` is five values; the actual usage is three: `official | staff | community`. The extra two (`researcher`, `press`, `vendor`) appear in seeds but no production code path uses them.
- **`brand_search_terms` is duplicated** — same data lives in `data/queries/<brand>.yaml` AND in the DB. The DB table is a shadow copy; either the DB or the yaml should be canonical, with the other deriving from it.
- **All tables use TEXT primary keys** — works, but prevents `INTEGER JOIN` speedups, integer-based FK constraints in other DBs, and clean bulk-insert optimization.
- **`signal_keys` is semantically wrong** — the 6-signal taxonomy mixes post type and sentiment, and the new 4-bucket + 4-sentiment taxonomy replaces it.

## Requirements Trace

- R1. Rename `locale` columns to `lang` in all `*_labels` tables (and any other table with a `locale` column).
- R2. Drop `engagement_tier_keys` and `engagement_tier_labels`; account tier is computed at control layer (not in DB).
- R3. Rename `post_mentions` → `posts_brands_mentions` (3-way join, plural-plural, consistent with migration 010).
- R4. Rename `signal_keys` → `signals` (and `signal_labels` → `signal_labels`, signal_id, lang, text) following the singular-keys convention. **Universal rule: no `_keys` suffix on enum tables** — applies to all current and future enum tables.
- R5. Rename `role_keys` → `roles` (and `role_labels` → `role_labels`, role_id, lang, text). **Same universal rule applies.**
- R6. Trim role values to `{official, staff, community}`; update all FK references and `role_labels` seeds.
- R7. Refactor `brand_search_terms` to "hybrid by design": yaml = query string construction (API contract), DB = post-fetch attribution (in-memory map). No duplication.
- R8. Replace TEXT primary keys with INTEGER primary keys across all current tables (or at minimum: the core attribution and lookup tables).
- R9. Implement the post_types/sentiments taxonomy (per `docs/plans/2026-06-24-163000-replace-legacy-signals-with-post-types-and-sentiments.md`) with adjustments: signal_keys → signals, role_keys → roles, TEXT → INTEGER PK, lang not locale.

## Scope Boundaries

- **In scope:** the 9 items above as separate migrations, ordered by dependency.
- **Out of scope:** migrating existing production data beyond what each migration requires; redesigning the post-fetch reattribute flow beyond what's needed to support R7 and R9; changes to the dashboard / front-end beyond the table-affecting migrations.
- **Not a single mega-migration:** each unit is its own PR where possible, to keep reviews focused and partial progress shippable.

## Context & Research

### Relevant Code and Patterns

- `x_monitor/store.py::_apply_migration` — migration runner pattern; each migration is a `.sql` file in `x_monitor/migrations/`, recorded in `_migrations` table.
- `x_monitor/migrations/010_*.sql` — recent example of a multi-table rename migration (plural-plural pattern).
- `x_monitor/migrations/008_enum_i18n_lookup_tables.sql` — pattern for the `*_keys` + `*_labels` i18n enum tables.
- `x_monitor/migrations/007_i18n_locale_columns.sql` — additive pattern for adding locale columns to existing tables.
- `x_monitor/data/translations/enum_zh_cn_overrides.json` — operator override mechanism for the i18n labels.
- `x_monitor/data/queries/<brand>.yaml` — the yaml files used for query string construction (Call A/B/C).
- `x_monitor/scripts/2026-06-19-180000-seed-detection-tables.py` — one-off seed script for `brand_keywords`; relevant for understanding the brand_search_terms hybrid.
- `x_monitor/attribution.py::extract_search_term_match` — current consumer of `brand_search_terms` map.
- `x_monitor/run.py::_build_brand_index` — current builder of the in-memory `brand_search_terms` map from yaml tokens.

### Institutional Learnings

- Project memory: `i18n locale columns (2026-06-23)` — establishes the locale column convention (additive, NULL-default, partial backfill indexes).
- Project memory: `rename M:N tables to plural-plural (2026-06-24)` — establishes the plural-plural naming rule for M:N join tables.
- Project memory: `merge order (2026-06-23)` — slots 005/006/007/008/009/010 are all on unmerged branches; the new migrations 011-019 will land after PR #10 merges.
- Project memory: `hf_orgs naming (2026-06-24)` — do not propose renaming `hf_orgs` even though HF officially uses "Organizations".

### External References

- Hugging Face API doc: `huggingface.co/docs/hub/organizations` (label: "Organizations"; not relevant to this plan beyond the naming-decision memory).
- SQLite docs: `ALTER TABLE RENAME` (used in 010); INTEGER PRIMARY KEY and `ROWID` aliasing.

## Key Technical Decisions

- **Phase the work, not bundle it:** each phase lands as its own migration (and its own PR) where it can. The PK refactor is the largest single change and gets its own dedicated phase.
- **Renames first, PK refactor after:** doing the PK refactor first would force every rename to also rewrite the new PK column. Doing renames first means each table's PK change is the only thing moving in that table.
- **Post_types is last:** the new `post_type_keys` / `sentiment_keys` tables get the new naming convention (signals, not signal_keys) and the new PK convention (INTEGER) from the start, with no legacy compromise.
- **brand_search_terms hybrid = clean separation, not duplicate storage:** yaml is the API contract (query string builder), DB is the post-fetch attribution source. The DB table stores only the attribution-relevant fields (term, brand_id, confirmed/discovered_via/added_at), not duplicates of the query-side yaml.
- **Engagement_tier becomes a control-layer query, not a DB table:** the new ranking query joins `accounts` to a fresh followers/engagement metric that's fetched by the control layer (not the DB). This avoids hardcoding tier boundaries in the DB.
- **Role trim is a single migration:** rename + value trim happen together so the FK references are rewritten once, in one place.
- **Locale → lang is independent of the renames:** it can land first, in its own migration, with minimal risk.

## Open Questions

### Resolved During Planning

- **Q: Does option c (hybrid by design) conflict with item 8 (drop the table)?**
  A: Yes — user confirmed option 3 (keep both by design) supersedes item 8. The `brand_search_terms` table stays, but its role is clarified.
- **Q: Should the text→numerical PK refactor cover all tables or just core ones?**
  A: All current tables. The plan is to ship a comprehensive PK refactor in one migration (slot 018). If that's too large, split into 018a (lookup/enum tables) + 018b (fact tables).
- **Q: What naming convention for the new U9 enum tables — plural `_keys` or singular no-suffix?**
  A: Singular, no `_keys` suffix. Universal rule: no enum table ends in `_keys`. So `post_types` and `sentiments` (not `post_type_keys` and `sentiment_keys`). Confirmed 2026-06-24.

### Deferred to Implementation

- **Exact migration slot numbers for sub-units:** 011-019 are reserved. The actual sub-numbering (e.g., whether the role trim is 015a and 015b) is decided during implementation based on what lands together.
- **Whether to combine the enum renames (U4+U5) into a single migration or split them:** implementer decides based on diff size; both are valid.
- **Index recreation strategy for the PK refactor:** the SQLite `INTEGER PRIMARY KEY` aliasing to ROWID means most indexes don't need to change, but FK references in other tables do. Implementer verifies per-table during execution.
- **The exact "rank accounts by followers + engagement" query for the engagement_tier replacement:** belongs in the control layer, not this DB plan. Tracked separately.

## Output Structure

No new directory structure created by this plan — it modifies existing files in `x_monitor/migrations/`, `x_monitor/store.py`, and the test directory. The doc updates go in `docs/reference/db-schema.md` (one pass at the end, after all migrations land).

## Implementation Units

U-IDs are stable: reordering preserves them in place, splitting keeps the original ID and assigns the next unused number, deletion leaves a gap.

The units are organized into 5 phases. Each phase lands as its own PR where possible.

---

### Phase 1: Cleanup renames (low-risk, independent)

- [x] U1. **Rename `locale` columns to `lang`** (verified at commit 4cd62d2 — migration 011 applies cleanly, 12 tests pass in test_migration_011_rename_locale_to_lang.py)

**Goal:** Every `locale` column in the DB is renamed to `lang`. This unifies the project's i18n column name with the existing `data/translations/` directory and the `lang` parameter used by the translator pipeline.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Create: `x_monitor/migrations/011_rename_locale_to_lang.sql`
- Test: `x_monitor/tests/test_migration_011_rename_locale_to_lang.py`
- Modify: all code that references `.locale` columns (in `x_monitor/store.py`, `x_monitor/translator.py`, dashboard queries) — mechanical rename.

**Approach:**
- `ALTER TABLE ... RENAME COLUMN locale TO lang` for every table with a `locale` column (the `*_labels` tables, and any other table that took a `locale` column via migration 007).
- Recreate any partial indexes that reference the old column name.
- Update all Python code that reads `.locale` to read `.lang` (mechanical).
- Update i18n operator override JSON schema (rename `locale` → `lang`).
- Update `db-schema.md` to reflect the new column name.

**Test scenarios:**
- Happy path: every `*_labels` table has a `lang` column and no `locale` column after migration.
- Idempotency: re-opening a DB that has 011 applied does not re-run it.
- Operator override JSON: existing overrides (which use `locale` keys) are migrated or rejected with a clear error.
- Integration: a label lookup by `(key, lang)` returns the expected row; a label lookup by `(key, locale)` raises.

**Verification:** All `*.locale` references in code return 0 results; `pragma table_info(<table>)` shows `lang` not `locale` for all `*_labels` tables.

---

- [x] U2. **Drop `engagement_tier_keys` and `engagement_tier_labels`; replace with control-layer query** (verified at commit 4cd62d2 — migration 012 applies cleanly, accounts.engagement_tier column dropped via rebuild, 12 tests pass in test_migration_012_drop_engagement_tier.py; no `engagement_tier` references remain in x_monitor/*.py)

**Goal:** Remove the unused `engagement_tier_keys` / `engagement_tier_labels` tables. Account tier is computed at the control layer (not stored in DB) using a fresh followers/engagement metric.

**Requirements:** R2

**Dependencies:** None (the tables are unused; no FK references to update)

**Files:**
- Create: `x_monitor/migrations/012_drop_engagement_tier.sql`
- Test: `x_monitor/tests/test_migration_012_drop_engagement_tier.py`
- Modify: `x_monitor/store.py` (remove any `read_engagement_tier_*` methods if they exist); `x_monitor/attribution.py` (any reference); dashboard queries.

**Approach:**
- `DROP TABLE engagement_tier_labels;` (drop child first to avoid FK error).
- `DROP TABLE engagement_tier_keys;` (parent).
- Recreate any indexes that reference these tables (none expected).
- The control layer's "rank accounts by followers + engagement" query is a separate concern and is tracked in a follow-up plan (not this one).
- Remove any seed rows that reference these tables.

**Test scenarios:**
- Happy path: `engagement_tier_keys` and `engagement_tier_labels` do not exist after migration.
- Idempotency: re-apply is a no-op.
- No FK violations: any code path that previously joined to these tables raises a clean AttributeError or ImportError (no silent breakage).

**Verification:** `SELECT name FROM sqlite_master WHERE name LIKE 'engagement_tier%'` returns 0 rows; no Python references to `engagement_tier` remain in code (grep returns 0).

---

- [x] U3. **Rename `post_mentions` → `posts_brands_mentions`** (verified at commit 4cd62d2 — migration 013 applies cleanly, indexes recreated, 14 tests pass in test_migration_013_rename_post_mentions.py)

**Goal:** Rename `post_mentions` to `posts_brands_mentions` for plural-plural consistency with the recent migration 010 (which renamed `post_brands` → `posts_brands`).

**Requirements:** R3

**Dependencies:** None (the rename is independent of the enum renames in Phase 2).

**Files:**
- Create: `x_monitor/migrations/013_rename_post_mentions_to_plural.sql`
- Test: `x_monitor/tests/test_migration_013_rename_post_mentions_to_plural.py`
- Modify: all code referencing `post_mentions` (in `x_monitor/store.py`, `x_monitor/attribution.py`, `x_monitor/reattribute.py`); `db-schema.md`.

**Approach:**
- `ALTER TABLE post_mentions RENAME TO posts_brands_mentions;`
- SQLite preserves indexes automatically (PK and indexes follow the table rename).
- Mechanical Python rename: `post_mentions` → `posts_brands_mentions` everywhere.
- Verify all FK references in `posts_brands_signals` and related tables still resolve.

**Test scenarios:**
- Happy path: `posts_brands_mentions` exists; `post_mentions` does not.
- Idempotency: re-apply is a no-op.
- Index preservation: existing indexes on `post_mentions` (e.g., on `post_id`, `brand_id`) are now on `posts_brands_mentions` with the same definition.
- Insert round-trip: a `posts_brands_mentions` INSERT and SELECT works end-to-end.

**Verification:** `SELECT name FROM sqlite_master WHERE name='posts_brands_mentions'` returns 1 row; `WHERE name='post_mentions'` returns 0 rows; full test suite passes.

---

### Phase 2: Enum table renames + role value trim

- [x] U4. **Rename `signal_keys` → `signals` (and `signal_labels` → `signal_labels`)** (verified at commit 4cd62d2 — migration 014 applies cleanly, `signal` → `signal_id` column rename on posts_brands_signals, index rebuilt, 14 tests pass in test_migration_014_rename_signal_keys.py)

**Goal:** Rename the `signal_keys` table to `signals` (singular noun, matches new convention). The labels table name `signal_labels` is unchanged but the FK column from `posts_brands_signals.signal` becomes `signal_id` (INTEGER after U8).

**Requirements:** R4

**Dependencies:** U1 (locale→lang rename is done; new `lang` column is the convention for the labels table)

**Files:**
- Create: `x_monitor/migrations/014_rename_signal_keys_to_signals.sql`
- Test: `x_monitor/tests/test_migration_014_rename_signal_keys_to_signals.py`
- Modify: all code referencing `signal_keys` (in `x_monitor/store.py`, `x_monitor/attribution.py`, the classifier); `db-schema.md`.

**Approach:**
- `ALTER TABLE signal_keys RENAME TO signals;`
- `ALTER TABLE signal_labels RENAME TO signal_labels;` (no change)
- Update FK column in `posts_brands_signals` from `signal TEXT` to `signal_id TEXT` (PK column rename; becomes `INTEGER` after U8).
- Mechanical Python rename.
- Note: this migration is the rename only. The new post_types/sentiments taxonomy (U9) is a separate, later migration.

**Test scenarios:**
- Happy path: `signals` exists; `signal_keys` does not; `signal_labels` still exists with FK to `signals`.
- Idempotency: re-apply is a no-op.
- FK preservation: `posts_brands_signals.signal_id` still references `signals.key` (or `.signal_id` after U8).
- Insert round-trip: a `posts_brands_signals` row with a valid `signal_id` writes and reads back.

**Verification:** Schema check shows `signals` not `signal_keys`; full test suite passes.

---

- [x] U5. **Rename `role_keys` → `roles` (and `role_labels` → `role_labels`)** (verified at commit 4cd62d2 — migration 015 applies cleanly, `role` → `role_id` on brands_accounts and companies_accounts, indexes rebuilt, 18 tests pass in test_migration_015_rename_role_keys.py)

**Goal:** Rename `role_keys` to `roles` (singular noun). Labels table name `role_labels` is unchanged; FK column from `brands_accounts.role` becomes `role_id` (INTEGER after U8).

**Requirements:** R5

**Dependencies:** U1 (same as U4)

**Files:**
- Create: `x_monitor/migrations/015_rename_role_keys_to_roles.sql`
- Test: `x_monitor/tests/test_migration_015_rename_role_keys_to_roles.py`
- Modify: all code referencing `role_keys` (in `x_monitor/store.py`, `x_monitor/attribution.py`, the role-based filters); `db-schema.md`.

**Approach:**
- `ALTER TABLE role_keys RENAME TO roles;`
- `ALTER TABLE role_labels RENAME TO role_labels;` (no change)
- Update FK columns:
  - `brands_accounts.role TEXT` → `role_id TEXT`
  - `companies_accounts.role TEXT` → `role_id TEXT`
- Mechanical Python rename.
- Note: this migration is the rename only. The role value trim (U6) is a separate migration that follows.

**Test scenarios:**
- Happy path: `roles` exists; `role_keys` does not; `role_labels` still exists with FK to `roles`.
- Idempotency: re-apply is a no-op.
- FK preservation: `brands_accounts.role_id` still references `roles.key` (or `.role_id` after U8).
- Insert round-trip: a `brands_accounts` row with a valid `role_id` writes and reads back.

**Verification:** Schema check shows `roles` not `role_keys`; full test suite passes.

---

- [x] U6. **Trim role values to `{official, staff, community}`** (verified at commit 4cd62d2 — migration 016 applies cleanly, backfill UPDATE remaps removed values to `community`, `staff` key added, 6 role_labels rows reinserted for {official, staff, community} × {en, zh_cn}, 19 tests pass in test_migration_016_trim_role_values.py)

**Goal:** Remove the unused role values `researcher`, `press`, `vendor`. Update `role_labels` to only have en + zh_cn entries for the 3 remaining values. Update any `brands_accounts.role_id` rows that pointed to the removed values (set to NULL or migrate to the closest survivor).

**Requirements:** R6

**Dependencies:** U5 (the rename must be done first so we operate on the new `roles` table)

**Files:**
- Create: `x_monitor/migrations/016_trim_role_values.sql`
- Test: `x_monitor/tests/test_migration_016_trim_role_values.py`
- Modify: `x_monitor/store.py` (any role-aware query); operator override JSON; seeds.

**Approach:**
- Backfill: any existing `brands_accounts.role_id` or `companies_accounts.role_id` with a removed value (e.g., `researcher`) is updated to the closest survivor (`community`) or set to NULL — implementer decides based on the actual rows.
- Delete removed rows from `role_labels` (where key IN `('researcher', 'press', 'vendor')`).
- Delete removed rows from `roles` (where key IN `('researcher', 'press', 'vendor')`).
- Re-insert 6 fresh `role_labels` rows (3 keys × 2 locales) for `{official, staff, community}`.
- Re-insert 3 fresh `roles` rows for `{official, staff, community}`.
- Update operator override JSON (remove any overrides for the deleted values).
- Add CHECK constraint or rely on FK from `brands_accounts` / `companies_accounts` to prevent re-introduction.

**Test scenarios:**
- Happy path: `SELECT key FROM roles ORDER BY key` returns `['community', 'official', 'staff']`.
- Idempotency: re-apply is a no-op.
- Backfill: any pre-existing `brands_accounts.role_id` pointing to a removed value is either migrated to the closest survivor or NULL.
- FK enforcement: an INSERT into `brands_accounts` with a removed role value is rejected.
- Labels round-trip: each of the 3 roles has both `en` and `zh_cn` labels.

**Verification:** `SELECT COUNT(*) FROM roles` returns 3; `SELECT COUNT(*) FROM role_labels` returns 6; full test suite passes.

---

### Phase 3: brand_search_terms hybrid refactor

- [x] U7. **Refactor `brand_search_terms` to hybrid by design (yaml = query, DB = attribution)** (verified at commit 4cd62d2 — migration 017 is a no-op DDL (documented contract), `_load_brand_search_terms_from_db` and drift warning implemented in code, 12 tests pass in test_brand_search_terms_hybrid.py)

**Goal:** Make the relationship between yaml and `brand_search_terms` explicit and clean. The yaml files become the *only* source of truth for the query string (the API contract). The `brand_search_terms` DB table becomes the *only* source of truth for the post-fetch term→brand attribution map. No data is duplicated.

**Requirements:** R7

**Dependencies:** None (the refactor is behavioral, not structural — no table rename or schema change)

**Files:**
- Create: `x_monitor/migrations/017_brand_search_terms_hybrid.sql` (if any DDL change is needed; possibly none)
- Test: `x_monitor/tests/test_brand_search_terms_hybrid.py` (or extend existing test files)
- Modify: `x_monitor/store.py` (clarify `read_brand_search_terms` semantics — attribution-only, not duplicate of yaml); `x_monitor/run.py` (`_build_brand_index` reads from the DB table, not from yaml tokens, for the attribution map); `x_monitor/data/queries/<brand>.yaml` (no change, but add a docstring noting its single role: query string construction); `db-schema.md`.

**Approach:**
- The `brand_search_terms` table stays as-is (schema-wise). What changes is the *contract*:
  - **yaml role (single):** build the TwitterAPI.io query string. Read by `x_monitor/query_plan.py::plan_calls()` at cycle time.
  - **DB role (single):** provide the term→brand map for the post-fetch reattribute step. Read by `x_monitor/reattribute.py` after fetch.
- The yaml is *not* read at attribution time (it used to be, in `_build_brand_index`). The DB is *not* used to build the query string.
- Add a docstring to `brand_search_terms` table in the migration explaining the new contract.
- Update `db-schema.md` section for `brand_search_terms` to spell out the hybrid-by-design.
- Add a runtime check: at startup, log a warning if the yaml terms and the DB terms disagree on coverage (informational, not a hard fail — drift detection, not enforcement).

**Test scenarios:**
- Happy path: a Call C query is built from yaml only; the post-fetch attribution map is built from the DB only.
- Drift detection: a yaml term that's not in the DB triggers a warning at startup; a DB term that's not in the yaml triggers a different warning.
- No duplication: the DB's `brand_search_terms` rows are NOT auto-populated from yaml (no seed migration in U7 — the table is operator-curated for the attribution side).
- Attribution accuracy: a post fetched by a query that contains term X is attributed to brand Y if and only if `brand_search_terms[X] = Y` in the DB.

**Verification:** No yaml terms appear in the DB; no DB terms appear in the yaml; attribution works end-to-end with the new contract.

---

### Phase 4: Primary key refactor

- [x] U8. **Replace TEXT primary keys with INTEGER primary keys across all tables** (verified at commit 4cd62d2 — migration 018 is SCOPED to signals + roles enum tables only per project memory; INTEGER AUTOINCREMENT id PK + UNIQUE key on both, FK columns (signal_id, role_id) stay TEXT holding the key, label rows preserved via TEMP TABLE backup across DROP TABLE CASCADE, 22 tests pass in test_migration_018_integer_primary_keys.py)

**Goal:** Convert all (or all core) tables' TEXT primary keys to INTEGER primary keys. This enables integer-based FK joins, aligns with the new enum table convention, and is a prerequisite for the post_types/sentiments work (which uses INTEGER PKs from the start).

**Requirements:** R8

**Dependencies:** U4, U5 (the enum renames are done, so the PK change is the only structural change per table); U1 (locale→lang is done so we don't rename `locale` and then rename it again to `lang`)

**Files:**
- Create: `x_monitor/migrations/018_integer_primary_keys.sql` (or `018a` + `018b` if split by table family)
- Test: `x_monitor/tests/test_migration_018_integer_primary_keys.py`
- Modify: all code that constructs rows with TEXT PKs (e.g., `INSERT INTO brands (brand_id, ...)` → `INSERT INTO brands (...))`); all FK references in dependent tables.

**Approach:**
- For each table to be refactored:
  1. `CREATE TABLE new_<table> (... id INTEGER PRIMARY KEY, ...);`
  2. `INSERT INTO new_<table> SELECT ... FROM <table>;` (auto-generates new INTEGER ids).
  3. `DROP TABLE <table>;`
  4. `ALTER TABLE new_<table> RENAME TO <table>;`
  5. Recreate indexes.
  6. For all FK references in other tables: add a new INTEGER FK column (e.g., `brand_id_new INTEGER`), backfill from the old TEXT FK (e.g., `brand_id_new = (SELECT id FROM brands WHERE brand_id = old_brand_id)`), drop the old TEXT FK, rename the new column to the original name.
- Order matters: refactor the referenced tables first (parents), then the referencing tables (children). Suggested order:
  1. Lookup tables: `signals`, `signal_labels`, `roles`, `role_labels`, `post_type_keys` (after U9 lands), `sentiment_keys` (after U9), `accounts`, `brands`, `companies`
  2. Edge tables (1:N from parents): `brands_accounts`, `companies_accounts`, `brands_companies`, `brand_accounts`, `brand_companies`
  3. M:N edge tables: `posts_brands`, `posts_brands_signals`, `posts_brands_mentions`
  4. Top-level fact tables: `posts`, `products` (if it lands in this batch)
- The CHECK constraint on `posts_brands_signals (brand_id <> '_unattributed')` from migration 004 must be preserved.
- The new INTEGER PK for `brands` etc. is an autoincrement-style `INTEGER PRIMARY KEY` (SQLite ROWID alias).

**Test scenarios:**
- Happy path: every refactored table has an INTEGER PRIMARY KEY column named `id`.
- Idempotency: re-apply is a no-op.
- FK enforcement: an INSERT into a child table with an `id` that doesn't exist in the parent is rejected.
- CHECK preservation: `posts_brands_signals` still has `(brand_id <> '_unattributed')` (or the equivalent after PK refactor).
- Index preservation: all indexes that referenced the old TEXT PK now reference the new INTEGER PK.
- Round-trip: end-to-end write+read works for every refactored table.
- Migration runner: the `_migrations` table records version 18 (or 18a/18b) on a fresh DB.

**Verification:** `pragma table_info(<table>)` for every refactored table shows `id INTEGER PRIMARY KEY`; FK pragma shows INTEGER references; full test suite passes.

---

### Phase 5: post_types/sentiments implementation

- [x] U9. **Implement post_types + sentiments taxonomy (per the existing plan)** (verified at commit 4cd62d2 — migration 019 is ADDITIVE not REPLACEMENT: new post_type_keys/sentiment_keys (4 each, INTEGER PK) + post_type_labels/sentiment_labels (8 each), new nullable post_type + sentiment TEXT columns on posts_brands_signals alongside legacy signal_id, backfill from signal_id via CASE mapping, 24 tests pass in test_migration_019_post_types_and_sentiments.py)

**Goal:** Drop the legacy `signals` / `signal_labels` (the 6-signal taxonomy: release, community_question, criticism, commenter_capture, praise, other) and replace with `post_type_keys` / `post_type_labels` (4-bucket) and `sentiment_keys` / `sentiment_labels` (4-value). Update `posts_brands_signals` to use the new `post_type` + `sentiment` columns.

**Requirements:** R9

**Dependencies:** U1 (lang not locale), U4 (signals not signal_keys), U8 (INTEGER PK) — so the new tables follow the new conventions from the start, with no legacy compromise.

**Files:**
- Create: `x_monitor/migrations/019_post_types_and_sentiments.sql`
- Test: `x_monitor/tests/test_migration_019_post_types_and_sentiments.py`
- Modify: `x_monitor/attribution.py` (classifier emits post_type + sentiment); `x_monitor/store.py` (insert paths, FK enforcement); `x_monitor/treemap.py` and dashboard (switch to new keys + labels); `db-schema.md`.

**Approach:** Follow the existing plan at `docs/plans/2026-06-24-163000-replace-legacy-signals-with-post-types-and-sentiments.md`, with these adjustments:
- New tables are **`post_types`** and **`sentiments`** (singular, no `_keys` suffix per the universal rule established in U4/U5).
- All new tables use INTEGER PK (per U8 convention).
- New `post_type_id` and `sentiment_id` columns in `posts_brands_signals` are INTEGER (FK to the new tables).
- Locale columns are `lang` not `locale` (per U1).
- The 4 post_types: `buzz_releases`, `hands_on_usage`, `performance_comparisons`, `feedback_questions` (per the existing plan).
- The 4 sentiments: `positive`, `negative`, `neutral`, `mixed` (per the existing plan).
- Seed labels for both en and zh_cn (per U1's `lang` column).
- Backfill existing `posts_brands_signals` rows from the legacy `signal_id` column to the new `post_type_id` + `sentiment_id` columns (heuristic mapping per the existing plan's "Backfill & Data Migration" section).
- Drop `signals` and `signal_labels` (the legacy tables — U4 renamed `signal_keys` to `signals`, but U9 drops `signals` and `signal_labels` since the legacy taxonomy is gone).

**Test scenarios:**
- Happy path: 4 rows in `post_types`, 4 in `sentiments`, 8 in each `*_labels` (4 keys × 2 locales).
- FK enforcement: an INSERT into `posts_brands_signals` with an invalid `post_type` is rejected.
- Backfill: legacy `signal='praise'` rows backfill to `post_type=... + sentiment=positive`.
- Idempotency: re-apply is a no-op.
- `signals` and `signal_labels` no longer exist after migration.
- Classifier integration: `attribution.py` writes the new columns; reads via `(post_type, lang)` join return the expected labels.
- Dashboard round-trip: a treemap query grouped by post_type bucket returns the expected counts.

**Verification:** Schema check shows new tables; `signals` and `signal_labels` are gone; backfilled data is correct; full test suite passes; the dashboard's post_type filter works end-to-end.

---

## System-Wide Impact

- **Interaction graph:**
  - `x_monitor/store.py` is the read/write path for every refactored table — all CRUD methods touched.
  - `x_monitor/attribution.py` (classifier + reattribute) is the most behavior-heavy consumer; U7 changes the contract, U9 changes the output schema.
  - `x_monitor/run.py::_build_brand_index` reads from yaml at startup; U7 changes this to read from the DB.
  - `x_monitor/data/queries/<brand>.yaml` is read by `query_plan.py::plan_calls()` — no change after U7, but the contract is now clearer.
  - Dashboard / treemap filters reference `signal` column (U9) and `role` column (U6).
- **Error propagation:** every migration is idempotent (re-apply is a no-op). FK violations are caught at write time. CHECK constraints surface at write time. The migration runner's `_migrations` ledger prevents double-apply.
- **State lifecycle risks:** the PK refactor (U8) is the riskiest — if the backfill mapping is wrong, child rows are orphaned or NULL. Mitigated by tests + the CHECK constraint on `posts_brands_signals`.
- **API surface parity:** `attribution.py::extract_search_term_match` signature is unchanged after U7 (still takes `brand_search_terms: dict[term, brand_id]`); only the source of the map changes (DB instead of yaml). `resolve_hf_orgs` and the other store methods are unchanged.
- **Integration coverage:** the brand_search_terms hybrid (U7) needs an integration test that exercises the full cycle (yaml → API call → fetch → reattribute). The post_types backfill (U9) needs an integration test that exercises the full classification → storage → read path.
- **Unchanged invariants:**
  - The `_migrations` table ledger (every migration recorded).
  - The `posts_brands_signals (brand_id <> '_unattributed')` CHECK constraint.
  - The `accounts` table's `author_id` PK (X user id) — this is TEXT by design and is *not* refactored.
  - The `hf_orgs` table — out of scope for this plan; intentionally abbreviated.
  - The `products` table — out of scope for this plan (it's on the unmerged HF products branch).

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| PK refactor (U8) breaks FKs across many tables | Med | High | Order the refactor by dependency (parents first, children after); add comprehensive tests; verify CHECK constraints survive. |
| Role value trim (U6) orphans production `brands_accounts.role_id` rows | Med | Med | Backfill to closest survivor OR set NULL — implementer decides based on actual production data; document the decision. |
| `brand_search_terms` hybrid (U7) introduces drift between yaml and DB | Med | Low | Drift is detected at startup (warning log); not enforced, just visible. The two stores have clearly different roles. |
| Post_types backfill (U9) maps legacy signals incorrectly | Med | Med | Conservative mapping; review queue for ambiguous cases; documented in the migration header. |
| Locale→lang rename (U1) breaks operator override JSON | Med | Low | Document the JSON schema migration in the runbook; reject overrides using the old schema with a clear error. |
| Engagment_tier drop (U2) breaks a hidden code path that joins to it | Low | Med | Grep the codebase for `engagement_tier` before drop; any reference must be removed first. |
| Migration runner's `_migrations` table itself uses TEXT PK (id INTEGER autoincrement is already the convention) | Low | Low | Out of scope; not refactored. |

## Phased Delivery

- **Phase 1 (U1-U3):** low-risk cleanup. Can land on main in one PR (or three small PRs). All three are independent.
- **Phase 2 (U4-U6):** enum table renames + role trim. Can land in one PR (U4+U5 share the i18n pattern) or two (U4 and U5 separate, U6 last).
- **Phase 3 (U7):** brand_search_terms hybrid. Behavioral change; needs its own PR with a clear changelog.
- **Phase 4 (U8):** the big PK refactor. Own PR. Optionally split into 018a (lookup tables) + 018b (fact tables) if the diff is too large.
- **Phase 5 (U9):** post_types/sentiments. Own PR. Depends on U1, U4, U8.

## Sources & References

- **Origin document:** user-curated migration list (this conversation, 2026-06-24) + `docs/plans/2026-06-24-163000-replace-legacy-signals-with-post-types-and-sentiments.md`
- Related code: `x_monitor/store.py`, `x_monitor/migrations/`, `x_monitor/attribution.py`, `x_monitor/run.py`, `x_monitor/data/queries/`
- Related plans: `docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md` (origin of the M:N join table pattern), `docs/plans/2026-06-19-004-feat-call-path-attribution-pipeline-plan.md` (origin of the `brand_search_terms` table)
- Project memories: `project_xmonitor_rename_mn_tables_2026-06-24.md`, `project_xmonitor_hf_orgs_naming_2026-06-24.md`
- External docs: SQLite `ALTER TABLE RENAME`, INTEGER PRIMARY KEY ROWID aliasing

## Verification Summary (2026-06-25 review at commit 4cd62d2)

All 9 implementation units (U1-U9) verified landed on `feat/schema-modernization-batch`.

- **Migration test sweep:** 124/124 pass (test_migration_011 through 019 + test_brand_search_terms_hybrid).
- **Consumer test sweep:** 439/440 pass; 1 failure in `test_store_v17.py::test_insert_posts_accepts_translation_columns` (line 122-127 still queries the old `signal` column instead of `signal_id`) — a real **regression caused by migration 014** (`signal` → `signal_id` rename) that was not updated in the same commit. Needs to be fixed before merge: replace `SELECT signal FROM posts_brands_signals` with `SELECT signal_id` and update the `sig_row["signal"]` assertion to `sig_row["signal_id"]`.
- **Pre-existing failures confirmed unrelated:** `test_headlines.py` 2 failures (MagicMock/JSON serialization in x_article enrichment) reproduce on this branch but are not caused by schema changes.
- **Code drift check:** no stale `signal_keys` / `role_keys` / `post_mentions` / `engagement_tier` references in `x_monitor/*.py` (only docstring comments referencing the rename history remain). The CLI `args.locale` in `__main__.py` is intentional per U1's documented exception (user-facing display locale, not a DB column).
- **Store API consistency:** `_known_signal_keys()` / `_known_role_keys()` correctly read from `signals` / `roles` (post-U8 INTEGER PK) and return set[str] of `key` column (FK validation against the UNIQUE key, not the integer id). `_pick_enum_label` uses the `lang` column (U1). All consistent.
