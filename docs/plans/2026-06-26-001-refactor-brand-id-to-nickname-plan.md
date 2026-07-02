---
title: "rename brand_id and company_id to nickname across the schema"
type: refactor
status: completed
date: 2026-06-26
shipped-on: 2026-06-26
main-head: d406a52
commits:
  - 3b2a860
  - cee6c5b
  - f845a0a
  - d406a52
---

# rename brand_id and company_id to nickname across the schema

## Overview

Rename the natural-slug TEXT columns `brands.brand_id` → `brands.nickname` and `companies.company_id` → `companies.nickname`, plus every consumer that reads/writes those columns by name. This is the v2.x schema-modernization-batch follow-up: mig 020 promoted the slug to a UNIQUE column but kept the name `brand_id` / `company_id`, which still carries the old v1 "this *is* the primary key" connotation. `nickname` matches the operator's mental model better (it's a short, stable, human-readable slug — not an ID — and is what appears in `data/queries/<brand>.yaml` filenames, `config.yaml::enabled_models`, dashboards, etc.).

This is **column-only**, not a key change. The migration runs on top of the v1 schema (TEXT PK `brands.brand_id` is the PK on prod) AND on the post-020 schema (INTEGER PK `brands.id`, TEXT UNIQUE `brand_id` is the slug). Both branches rename `brand_id` → `nickname`; only the column type tag in the SQL header differs.

## Problem Frame

The operator asks for `brand.brand_id` → `brand.nickname` and `company.company_id` → `company.nickname`. The reason: `brand_id` is no longer the primary key after the schema-modernization batch (it's now a `TEXT UNIQUE NOT NULL` slug on top of `brands.id INTEGER PRIMARY KEY`). Keeping the old name signals "this is the PK" to readers, which is wrong.

Today every consumer in the codebase reads `brand_id` from results (Store API) and writes `brand_id` in INSERTs (callers). Renaming the column is mechanical but the change touches:

- **24 files** in `x_monitor/` (Python + migrations + templates) reference `brand_id` or `company_id` — top consumers are `store.py` (160 hits), `attribution.py` (81), `run.py` (48), `dashboard.py` (42), `treemap.py` (21), `accounts.py` (21), `hf_products.py` (19).
- **20 brand query yamls** in `data/queries/<brand_id>.yaml` — the **filenames** stay as-is (they're filesystem, not SQL).
- **`config.yaml`** uses `enabled_models`, `call_b_groups`, etc. as lists of brand_id strings — those string values stay, only the *Python config-validation message* needs an updated variable name if we rename `brand_id` → `nickname` there.
- **Test fixtures**: 155/155 migration tests + 287 consumer tests reference the old column names. Some are docstring/identifier references (cheap); some are SQL `INSERT/SELECT` clauses (must rewrite).

The rename is structurally simple but **broad in surface area**. Doing it sloppily will break all 287 tests and the dashboard. The plan below ensures each consumer is updated atomically with the migration that introduces the new name.

## Requirements Trace

- **R1.** `brands.brand_id` is renamed to `brands.nickname`; the column type and constraints are preserved (TEXT UNIQUE NOT NULL post-020; TEXT PRIMARY KEY pre-020).
- **R2.** `companies.company_id` is renamed to `companies.nickname`; same preservation rules.
- **R3.** Every FK column in a child table that references the renamed slug column is renamed in lockstep — `brands_companies.brand_id` → `.nickname`, `brands_accounts.brand_id` → `.nickname`, `companies_accounts.company_id` → `.company_nickname`, `search_queries.brand_id` → `.nickname`, `hf_orgs.company_id` → `.company_nickname` (the latter two need disambiguation because they reference a column whose PK is now named `id`).
- **R4.** All Python code that reads `row["brand_id"]` or writes `INSERT ... (brand_id, ...)` is updated to `nickname`. The Store API's public method signatures stay TEXT-slug-in, INTEGER-id-out — no public-API contract changes.
- **R5.** All test files that reference the old column names are updated. Tests must pass on both pre-020 and post-020 schemas (155/155 migration tests + 287 consumer tests).
- **R6.** The two seed scripts (`scripts/2026-06-25-004-populate-brand-search-terms.py`, `scripts/2026-06-25-005-seed-companies-brands-from-csv.py`) are updated to write to the renamed columns.
- **R7.** All yaml config files (`config.yaml`, `data/queries/<brand>.yaml`, `data/accounts/<brand>.yaml`) keep their existing string values (the slugs themselves are NOT renamed — the operator still wants `minimax` not `minimax_nick`); only internal variable names and doc-comments are updated.
- **R8.** Documentation files (`docs/reference/db-schema.md`, `docs/reference/twitterapi-io-calls.md`, `docs/reference/twitterapi-live-queries-by-model.md`) are updated to use the new column names.
- **R9.** A single migration file (`x_monitor/migrations/023_rename_brand_and_company_ids_to_nicknames.sql`) is added; idempotent re-apply is a no-op.

## Scope Boundaries

- **Not in scope:** changing the slug *values* themselves. `brand_id = "minimax"` stays `nickname = "minimax"`. No data migration on values.
- **Not in scope:** renaming `hf_orgs.id` (the namespace column). That was renamed in mig 020 from `id` (TEXT PK) to `namespace` (TEXT UNIQUE) + new `id` (INTEGER PK). Different concept, already done.
- **Not in scope:** renaming `accounts.author_id`. Different concept (the X user id); renaming it to `handle` would conflict with the `accounts.handle` column that already exists.
- **Not in scope:** renaming files in `data/queries/<brand_id>.yaml` — they keep their current names (filesystem stability, no churn for the operator).
- **Not in scope:** any data changes beyond the column rename. No backfills, no transforms.
- **Not in scope:** merging with the v2 schema-modernization batch. This plan **depends on** mig 020 landing first in prod (otherwise the post-020 column type semantics don't apply) but does not deliver mig 020 itself.

## Context & Research

### Relevant Code and Patterns

- **Migration pattern reference:** `x_monitor/migrations/014_rename_signal_keys_to_signals.sql` — rename of `signal_keys` → `signals`. Pattern: `ALTER TABLE old RENAME TO new;` plus recreate indexes that referenced the old name.
- **Migration pattern reference:** `x_monitor/migrations/015_rename_role_keys_to_roles.sql` — same `ALTER TABLE ... RENAME` pattern. Includes FK column renames on `brands_accounts.role` → `role_id` (precedent for renaming FK columns in lockstep).
- **Migration pattern reference:** `x_monitor/migrations/013_rename_post_mentions_to_posts_brands_mentions.sql` — rename of M:N table; precedent for handling composite-PK FK columns.
- **Store API contract (post-020):** "string-in, INTEGER-out" — public methods still accept TEXT slugs, internally look up INTEGER ids via lazy-populated caches (`_brand_id_map`, `_company_id_map`, etc.). The rename only affects the **column name on row dicts returned by SQLite**; the Store's public parameter names (`brand_id: str`) stay. After the rename, `row["nickname"]` is the new way to read a brand's slug.
- **Slug vs id disambiguation:** post-020 has `brands.id` (INTEGER PK) and `brands.brand_id` (TEXT UNIQUE NOT NULL). After this rename: `brands.id` (INTEGER PK) and `brands.nickname` (TEXT UNIQUE NOT NULL). The Store API's `read_brands()` returns rows with both fields. Consumers should use `row["nickname"]` for the slug (was `row["brand_id"]`).
- **Top consumers to update:**
  - `x_monitor/store.py` (160 hits) — every SQL `INSERT/SELECT` statement; many `row["brand_id"]` reads.
  - `x_monitor/attribution.py` (81 hits) — classifier inputs reference brand_id strings.
  - `x_monitor/run.py` (48 hits) — cycle orchestrator reads/writes brand_id throughout.
  - `x_monitor/dashboard.py` (42 hits), `x_monitor/treemap.py` (21 hits) — render code reads `row["brand_id"]`.
  - `x_monitor/accounts.py` (21 hits), `x_monitor/hf_products.py` (19 hits) — narrower surface.

### Institutional Learnings

- **`feedback_no_unauthorized_scope_narrowing.md`** — the 2026-06-25 incident where U8 (INTEGER PK) and U9 (post_types/sentiments) were narrowed without authorization. This plan must NOT silently narrow scope; if a consumer is hard to rename, the plan surfaces it as a blocker, not a "skip for now".
- **`project_x_monitoring_treemap_2026-06-17.md`** — palette naming: when something is a "slug", name it like a slug (`nickname`, `handle`, `slug`), not like a key (`id`). This plan applies that convention.
- **`feedback_worktree_hygiene_x_monitoring.md`** — when this work lands, do it on a worktree branch (not on main or on `docs/u8-remediation-plan-update`).
- **`feedback_fuchitalee_pytest_tmpdir_cleaned.md`** — full pytest suite needs `--basetemp=$HOME/pytest-basetemp-<name>`.

### External References

- **SQLite docs:** `ALTER TABLE ... RENAME COLUMN` (requires SQLite ≥3.25.0; column rename preserves type and constraints). Child-table FK references are NOT auto-rewritten when the *column* is renamed — explicit `RENAME COLUMN` on each FK column is required. https://www.sqlite.org/lang_altertable.html
- **SQLite docs:** `PRAGMA foreign_keys = ON` must be toggled OFF during table rebuilds (same pattern as mig 020, see the migration runner's `apply_migrations()`).

## Key Technical Decisions

- **Decision: Single migration, atomic.** Don't ship separate rename migrations for `brands` and `companies`. One `023_rename_brand_and_company_ids_to_nicknames.sql` does both renames in one transaction so a partial-failure state can't leave the schema half-renamed.
- **Decision: Rename FK columns in lockstep, in the same migration.** Child tables (`brands_companies`, `brands_accounts`, `companies_accounts`, `search_queries`, `hf_orgs`) get their FK columns renamed in the same `BEGIN`/`COMMIT`. The `posts_brands_signals` and `posts_brands_mentions` tables get renamed too (`brand_id` → `nickname`).
- **Decision: `companies.company_id` → `companies.nickname` is fine** because no other table has a `company_id` column that would be ambiguous in plain English. The child-table columns (`hf_orgs.company_id`, `companies_accounts.company_id`) become `company_nickname` to disambiguate from the INTEGER `companies.id` FK (post-020).
- **Decision: Two-pass migration for forward compatibility.** The migration first detects the schema version (`PRAGMA table_info(brands)` → is `brand_id` the PK? Then pre-020; is it `id`? Then post-020). Rename only what exists. Idempotent: re-running is a no-op because the columns are already renamed.
- **Decision: Store API public parameter names stay.** `Store.get_brand(brand_id: str)` keeps the parameter name `brand_id` (it's an interface keyword in the docstring sense). Internal row-dict lookups change to `row["nickname"]`. This preserves backward compatibility for any external caller passing `brand_id=`.
- **Decision: Brand yaml filenames stay.** `data/queries/minimax.yaml` keeps its filename — it's filesystem, not SQL. The operator's muscle memory and existing operator-side scripts depend on these filenames.
- **Decision: `config.yaml::enabled_models` keeps `minimax` as a string.** The list-of-brand-slugs is data, not schema. No changes.
- **Decision: Test file renames are NOT done in this plan.** Migration test files (`test_migration_014_rename_signal_keys.py`, `test_migration_015_rename_role_keys.py`) keep their filenames — the file name reflects the *original* migration it tests, not the current schema. New tests for the new migration are `test_migration_023_rename_brand_and_company_ids_to_nicknames.py`.

## Open Questions

### Resolved During Planning

- **Q: What happens to `brand_id` and `company_id` as Python identifiers?**  
  A: Internal-to-the-function parameter names stay (`brand_id: str` reads naturally as "the brand's slug string"); row-dict lookups change (`row["brand_id"]` → `row["nickname"]`). Doc comments updated.
- **Q: Is there a risk the rename breaks the post-020 INTEGER-PK convention?**  
  A: No. The INTEGER PK on `brands.id` is preserved. We're renaming the natural-slug TEXT column, not the PK.
- **Q: Does `data/queries/<brand_id>.yaml` filename count as "brand_id" usage?**  
  A: No — it's filesystem, not SQL. Out of scope.
- **Q: Are there any x.com API fields named `brand_id` or `company_id`?**  
  A: No. The x.com API doesn't have these. TwitterAPI.io uses query strings + account handles. No external contract risk.
- **Q: Does the dashboard need any change beyond the column reads?**  
  A: The dashboard template (`x_monitor/templates/_model_card.html.j2`) reads `brand.brand_id` (3 hits) — must rename to `brand.nickname`.

### Deferred to Implementation

- **D1: Exact order of rename operations within the migration transaction.**  
  Reason: depends on whether mig 020 has been applied (brands.id is INTEGER PK then, FK columns in child tables are INTEGER-storing-id). The migration must detect via `PRAGMA table_info(brands)` whether to use the pre-020 or post-020 shape, then run the appropriate sequence.
- **D2: Whether `posts_brands_signals.signal_id` rename to `posts_brands_signals.signal_key` is in scope.**  
  Reason: `signal_id` column was dropped in mig 022 (full replacement). It no longer exists post-022. So this rename is moot. **Confirm during implementation** by reading the live schema; the column should not exist. If a fork is found (e.g., a parallel schema without mig 022), surface it.
- **D3: Migration runner idempotency check.**  
  Reason: standard pattern is to check `_migrations` table for `version = 23` before applying. Implementation detail.

## High-Level Technical Design

> *Directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### Migration shape (pre-020 path)

```
BEGIN;

-- Detect: if brands.brand_id does not exist, the rename has already been applied; COMMIT and exit.
-- Otherwise:

-- 1. brands: brand_id (TEXT PK) → nickname (TEXT PK)
ALTER TABLE brands RENAME COLUMN brand_id TO nickname;
CREATE INDEX IF NOT EXISTS idx_brands_nickname ON brands(nickname);

-- 2. companies: company_id (TEXT PK) → nickname (TEXT PK)
ALTER TABLE companies RENAME COLUMN company_id TO nickname;
CREATE INDEX IF NOT EXISTS idx_companies_nickname ON companies(nickname);

-- 3. Child-table FK column renames (pre-020: TEXT-storing-key)
ALTER TABLE brands_companies     RENAME COLUMN brand_id   TO nickname;
ALTER TABLE brands_companies     RENAME COLUMN company_id TO company_nickname;
ALTER TABLE brands_accounts      RENAME COLUMN brand_id   TO nickname;
ALTER TABLE companies_accounts   RENAME COLUMN company_id TO company_nickname;
ALTER TABLE search_queries       RENAME COLUMN brand_id   TO nickname;
ALTER TABLE hf_orgs              RENAME COLUMN company_id TO company_nickname;
ALTER TABLE posts_brands         RENAME COLUMN brand_id   TO nickname;
ALTER TABLE posts_brands_signals RENAME COLUMN brand_id   TO nickname;
ALTER TABLE posts_brands_mentions RENAME COLUMN brand_id TO nickname;

COMMIT;
```

### Migration shape (post-020 path)

Same DDL applies, but the **column types** differ:

- `brands.nickname` (was `brand_id` TEXT PK) is now `TEXT UNIQUE NOT NULL` (INTEGER PK is `brands.id`).
- `brands_companies.nickname` (was `brand_id` TEXT) is now `INTEGER` (FK to `brands.id`).
- The `ALTER TABLE ... RENAME COLUMN` works on either type — SQLite doesn't change type when renaming a column.

### Detection / idempotency

```sql
-- At top of migration, before BEGIN:
SELECT EXISTS(SELECT 1 FROM pragma_table_info('brands') WHERE name='brand_id');
-- If 1 (column exists), proceed with rename. If 0 (already renamed), EXIT.
```

The `_migrations` ledger handles the standard idempotency — the runner skips migration 023 if `version = 23` is already in `_migrations`. The pragma check is the second layer (in case `_migrations` is out of sync).

### Consumer-rewrite shape (Python)

Mechanical: every `row["brand_id"]` becomes `row["nickname"]`; every `INSERT INTO x (..., brand_id, ...)` becomes `INSERT INTO x (..., nickname, ...)`. SQL parameters in `sqlite3` use positional `?`, so Python callers passing `brand_id` as a named dict key still work because the rename only changes the *column name* in the SQL, not the *Python variable name* holding the value.

A practical tip for implementers: `git grep -nE "\bbrand_id\b|\bcompany_id\b"` (with word boundaries) over `x_monitor/` and `tests/` to find every reference. Then mechanical rewrite, with the exception of:
- Filenames (`data/queries/<brand>.yaml`).
- External API strings (TwitterAPI.io query strings use `MiniMax` etc., not `brand_id`).
- Doc comments / changelog entries referring to the *historical* column name (preserved as "renamed from `brand_id` in mig 023" — intentional historical context).

## Implementation Units

- [ ] **Unit 1: Migration 023 + idempotency detection**

**Goal:** Add `x_monitor/migrations/023_rename_brand_and_company_ids_to_nicknames.sql` that detects pre-020 vs post-020 schema and renames the columns atomically.

**Requirements:** R1, R2, R3, R9

**Dependencies:** None (the migration must work on pre-020 prod today; post-020 detection is for the branch where 020 is already applied).

**Files:**
- Create: `x_monitor/migrations/023_rename_brand_and_company_ids_to_nicknames.sql`

**Approach:**
- Use `sqlite_master` / `pragma_table_info('brands')` to detect whether `brand_id` column exists; if not, the migration is a no-op.
- Inside a single `BEGIN; ... COMMIT;`, execute `ALTER TABLE ... RENAME COLUMN` for the parent tables first, then child tables.
- Recreate indexes that referenced the old column names (`idx_brands_brand_id` → `idx_brands_nickname`, `idx_companies_company_id` → `idx_companies_nickname`).
- Migration runner records `version = 23` in `_migrations`.

**Execution note:** Add a defensive `PRAGMA foreign_keys = OFF` at the connection level during the rename, then `PRAGMA foreign_keys = ON` after the `COMMIT`. SQLite's FK enforcement during column renames is permissive but adding the pragma guards against accidental cascade issues on a prod DB where some rows may already have orphaned FK references.

**Test scenarios:**
- **Happy path (pre-020):** Apply migration to a DB at v1–v11. Verify `pragma_table_info('brands')` shows `nickname` not `brand_id`; FK columns in all child tables renamed; `_migrations` records `23`; `SELECT * FROM brands` returns rows with `nickname` populated.
- **Happy path (post-020):** Apply migration to a DB at v1–v22 (worktree branch state). Verify the same — INTEGER PK on `brands.id` preserved, slug column renamed, FK columns renamed, `_migrations` records `23`.
- **Idempotency:** Apply twice on the same DB; second apply is a no-op (no error, no row count changes).
- **FK preservation:** `INSERT INTO brands_companies (nickname, company_nickname, ownership_pct) VALUES (?, ?, ?)` against a real `brands`/`companies` row succeeds; the same INSERT with an invalid nickname is rejected.
- **Round-trip:** Read+write a brand via `Store.get_brand(nickname="minimax")` returns the same row data as before the migration (assuming Store API is updated in Unit 2).
- **Migration runner:** Fresh DB applies migrations 1–23 in order; `_migrations` records all 23 versions including 23.

**Verification:**
- `tests/test_migration_023_rename_brand_and_company_ids_to_nicknames.py` (new file) covers all six scenarios above.
- All pre-existing migration tests (test_migration_011–022) still pass — they reference `brand_id` / `company_id` in their SQL bodies and must be updated to use `nickname` / `company_nickname` to match the new column names. **This is the test-update work that flows into Unit 2.**

---

- [ ] **Unit 2: Update pre-existing migration tests to use the new column names**

**Goal:** Every test in `tests/test_migration_011_*.py` through `test_migration_022_*.py` that does `INSERT INTO brands (brand_id, ...)` or `SELECT brand_id FROM brands` must use the renamed column names. The tests already run *against* a DB that has had the renames applied (post-023), so they must reflect the new shape.

**Requirements:** R5

**Dependencies:** Unit 1 (the migration must exist so the test fixture runs against the new schema).

**Files:**
- Modify: `x_monitor/tests/test_migration_011_rename_locale_to_lang.py` (4 references)
- Modify: `x_monitor/tests/test_migration_012_drop_engagement_tier.py`
- Modify: `x_monitor/tests/test_migration_013_rename_post_mentions_to_posts_brands_mentions.py`
- Modify: `x_monitor/tests/test_migration_014_rename_signal_keys_to_signals.py`
- Modify: `x_monitor/tests/test_migration_015_rename_role_keys_to_roles.py`
- Modify: `x_monitor/tests/test_migration_016_trim_role_values.py`
- Modify: `x_monitor/tests/test_migration_018_integer_primary_keys.py`
- Modify: `x_monitor/tests/test_migration_019_post_types_and_sentiments.py`
- Modify: `x_monitor/tests/test_migration_020_text_to_integer_pks.py`
- Modify: `x_monitor/tests/test_migration_022_kill_signal_id.py`

**Approach:**
- Run `git grep -nE "\bbrand_id\b|\bcompany_id\b" x_monitor/tests/test_migration_*.py` and mechanically rewrite every SQL reference.
- Where a test file's *name* references the original column (e.g., `test_migration_014_rename_signal_keys.py` is still correctly named — it tests the signal_keys → signals rename, which is a separate historical event), do NOT rename the file.
- Update test docstrings and `sqlite_master` assertions (`assert_sql_has_column('brands', 'nickname')` not `'brand_id'`).

**Test scenarios:**
- **Test expectation: none -- this unit updates tests to match Unit 1's schema change; the tests themselves assert behavior that Unit 1's verification already covers.** New unit-specific tests live in `test_migration_023_*.py` (Unit 1).

**Verification:**
- All 155 pre-existing migration tests still pass against a DB that has had migrations 1–23 applied.
- Full sweep: `pytest x_monitor/tests/test_migration_011_*.py x_monitor/tests/test_migration_012_*.py ... x_monitor/tests/test_migration_023_*.py --basetemp=$HOME/pytest-basetemp-mig023 -q` shows 156/156 pass (155 old + 1 new test file).

---

- [ ] **Unit 3: Update Store API + 12 consumer modules to read/write `nickname`**

**Goal:** Every line in `x_monitor/*.py` that does `row["brand_id"]`, `row["company_id"]`, `INSERT INTO ... (brand_id, ...)`, etc., is updated to `nickname` / `company_nickname`. Public Store API method signatures stay (parameter names `brand_id` and `company_id` are not part of the SQL contract).

**Requirements:** R4, R6

**Dependencies:** Unit 1 (so any test that exercises the Store API against a real DB sees the new column names).

**Files:**
- Modify: `x_monitor/store.py` (160 references — by far the largest)
- Modify: `x_monitor/attribution.py` (81)
- Modify: `x_monitor/run.py` (48)
- Modify: `x_monitor/dashboard.py` (42)
- Modify: `x_monitor/treemap.py` (21)
- Modify: `x_monitor/accounts.py` (21)
- Modify: `x_monitor/hf_products.py` (19)
- Modify: `x_monitor/query_rot.py` (12)
- Modify: `x_monitor/reattribute.py` (11)
- Modify: `x_monitor/query_plan.py` (10)
- Modify: `x_monitor/__main__.py` (11)
- Modify: `x_monitor/config.py` (8 — error messages + comments only, not SQL)
- Modify: `x_monitor/intent_classifier.py` (5)
- Modify: `x_monitor/relevance.py` (8)
- Modify: `x_monitor/review.py` (6)
- Modify: `x_monitor/translator.py` (6)
- Modify: `x_monitor/templates/_model_card.html.j2` (3 — Jinja variable reads)
- Modify: `x_monitor/templates/model_detail.html.j2` (4)
- Modify: `scripts/2026-06-25-004-populate-brand-search-terms.py` (the seed script — must write to renamed column)
- Modify: `scripts/2026-06-25-005-seed-companies-brands-from-csv.py` (same)

**Approach:**
- `git grep -nE "\bbrand_id\b|\bcompany_id\b"` over `x_monitor/` produces the candidate list.
- Mechanical rewrite: `row["brand_id"]` → `row["nickname"]`, `INSERT INTO x (..., brand_id, ...)` → `INSERT INTO x (..., nickname, ...)`.
- **Disambiguation rule:** when a child-table FK column needs to be unambiguous from `brands.id` (post-020) or `companies.id`, use `brand_nickname` / `company_nickname`. Applies to `brands_companies`, `brands_accounts`, `companies_accounts`, `posts_brands`, `posts_brands_signals`, `posts_brands_mentions`, `hf_orgs`, `search_queries`.
- Parameter names in Python function signatures stay (`brand_id: str` reads naturally). Only docstrings + comments get updated to "the brand's nickname slug".
- Jinja templates (`_model_card.html.j2`, `model_detail.html.j2`): `{{ brand.brand_id }}` → `{{ brand.nickname }}`. Jinja dict-access syntax applies.

**Test scenarios:**
- **Happy path (round-trip):** `Store.insert_brand({"nickname": "minimax", "display_name": "MiniMax AI", ...})` followed by `Store.get_brand("minimax")` returns the same row.
- **Edge case (slug lookup):** `Store.list_brands()` returns rows with `nickname` populated; downstream `treemap.py` and `dashboard.py` correctly render without `KeyError`.
- **Error path:** Reading `row["brand_id"]` on a post-023 DB raises `KeyError` (since the column is renamed) — these reads should have been updated. Any test that exercises this is itself buggy.
- **Integration (cycle end-to-end):** Run `run.py::RunPipeline.execute` for one cycle with `--limit 5` and confirm posts are inserted with valid `nickname` values on `posts_brands.nickname`, `posts_brands_signals.nickname`, `posts_brands_mentions.nickname`.

**Verification:**
- All 287 pre-existing consumer tests pass against the post-023 DB.
- New `tests/test_store_nickname_column.py` (or extension to `test_store.py`) covers the round-trip + slug lookup + error path.
- `git grep -nE "\bbrand_id\b|\bcompany_id\b" x_monitor/store.py` returns ONLY matches in docstrings/comments/intentional-history references (not in SQL).

---

- [ ] **Unit 4: Update reference docs to reflect the rename**

**Goal:** The three reference docs that describe the schema (`docs/reference/db-schema.md`, `docs/reference/twitterapi-io-calls.md`, `docs/reference/twitterapi-live-queries-by-model.md`) use the new column names.

**Requirements:** R8

**Dependencies:** Unit 1 (so the doc accurately reflects the post-023 state).

**Files:**
- Modify: `docs/reference/db-schema.md`
- Modify: `docs/reference/twitterapi-io-calls.md`
- Modify: `docs/reference/twitterapi-live-queries-by-model.md`

**Approach:**
- Mechanical rewrite: every `brand_id` (in a column-name context) → `nickname`; every `company_id` (column) → `nickname` or `company_nickname` depending on table.
- Preserve historical mentions in migration narratives ("renamed in mig 023 from `brand_id`") as load-bearing context for the reader.
- Same grep-driven approach as Unit 3.

**Test scenarios:**
- **Test expectation: none -- this is a docs update; the verification is a visual diff check by the operator.**

**Verification:**
- `git grep -nE "\bbrand_id\b|\bcompany_id\b" docs/reference/` shows only historical/marker references (not in live column descriptions).
- The new schema image (`docs/reference/images/xmonitor-schema-post-batch.png`) is regenerated in a follow-up commit if it shows column names.

---

## System-Wide Impact

- **Interaction graph:** The rename touches the read path of every query in the codebase (24 files), the write path of every INSERT (callers in `run.py`, `hf_products.py`, `seed scripts`), and the dashboard/treemap render path. Any code that reads a `row["brand_id"]` from a sqlite3.Row will silently start returning `None` if not updated. Failure mode is loud (the test suite catches it).
- **Error propagation:** The migration runs in a transaction; failure rolls back the entire rename. After `COMMIT`, FK enforcement is back ON and any consumer that reads the old column name gets `KeyError` (Python dict semantics). The test suite is the primary safety net.
- **State lifecycle risks:** The migration is idempotent (pragma check + `_migrations` ledger). Re-applying is a no-op. But partial rename state (e.g., `brands.nickname` renamed but child-table FK columns not) would break FK enforcement — that's why the rename is one transaction.
- **API surface parity:** Public Store API parameter names (`brand_id: str`) stay. Internal row-dict reads change. External callers (only `__main__.py` CLI) pass `brand_id=...` to the CLI which maps to internal calls; no CLI flag is renamed. No external API.
- **Integration coverage:** The cycle end-to-end test (Unit 3 integration scenario) exercises the full `run.py → reattribute.py → store.py → dashboard.py` chain. If any layer missed the rename, that test fails.
- **Unchanged invariants:** The slug *values* (`minimax`, `qwen`, etc.) are NOT renamed. `config.yaml::enabled_models` keeps the same string values. `data/queries/<brand>.yaml` filenames are preserved.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Mechanical rewrite misses a `row["brand_id"]` reference | Med | Med (test suite catches it) | Run `git grep` after rewrite; full 287-test sweep must pass |
| Idempotency check on pre-020 vs post-020 shape is wrong | Low | High (corrupts a live DB) | Two layers: `_migrations` ledger + `pragma_table_info` check; defensive `PRAGMA foreign_keys = OFF` during rename |
| `data/queries/<brand_id>.yaml` filenames accidentally renamed | Low | Low (just a revert) | Explicit "out of scope" in the plan + grep for filename-only references |
| Post-022 fork (signal_id column still exists) makes migration path ambiguous | Low | Med | Unit 1 verification checks `pragma_table_info('posts_brands_signals')` for `signal_id` existence and aborts if found; surface to operator |
| Operator runs mig 023 on a prod DB that has unapplied 012-022, breaking the schema | Med | High | Migration header documents the prerequisite chain; pre-flight check in the migration's pragma detector aborts with a clear error if migrations are out of order |

## Documentation / Operational Notes

- The `x_monitor/migrations/023_rename_brand_and_company_ids_to_nicknames.sql` migration header must document:
  - The pre-020 vs post-020 detection (and that both are supported).
  - The `data/queries/<brand>.yaml` filename convention is NOT affected.
  - The slug values are NOT renamed — only the column name.
  - The migration is idempotent (pragma + ledger).
- `docs/reference/db-schema.md` migration ledger table must add the new row.
- The CHANGELOG.md must record the rename with a one-line summary + the same `Scope delivered vs plan promised: MATCH` footer per CLAUDE.md rule 4.

## Sources & References

- **Plan origin:** operator message "rename brand.brand_id to brand.nickname, company.company_id to company.nickname and change dependencies" (2026-06-26).
- **Predecessor plans:** `docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md` (the v2.x INTEGER-PK + signal-kill batch that this rename follows on from); `docs/plans/2026-06-22-001-refactor-hf-orgs-belong-to-companies-plan.md` (the prior `id` → `namespace` rename for hf_orgs).
- **Related code:** `x_monitor/store.py` (Store API), `x_monitor/migrations/004_company_brand_account_model.sql` (origin of the brand/company model), `x_monitor/migrations/014_rename_signal_keys_to_signals.sql` + `015_rename_role_keys_to_roles.sql` (rename pattern reference).
- **External docs:** [SQLite ALTER TABLE RENAME COLUMN](https://www.sqlite.org/lang_altertable.html) (requires SQLite ≥3.25.0; fuchitalee's sqlite3 is 3.50+).
- **Institutional memory:** `feedback_no_unauthorized_scope_narrowing.md` (no silent narrowing), `feedback_worktree_hygiene_x_monitoring.md` (work on a worktree), `feedback_fuchitalee_pytest_tmpdir_cleaned.md` (pytest `--basetemp`).