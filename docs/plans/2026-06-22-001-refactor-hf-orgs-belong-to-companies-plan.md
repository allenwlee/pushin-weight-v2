---
title: HF orgs belong to companies, not brands
type: refactor
status: active
date: 2026-06-22
origin: docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md
---

# HF orgs belong to companies, not brands

## Overview

The HF-products crawler (PR #6, branch `feat/hf-products-crawler`) currently models HuggingFace orgs as an M:N edge between **brands** and HF namespaces (`brand_hf_orgs`). The cleaner model: HF orgs are an attribute of the **corporate parent** (the company), and **brands** are an operator-curated product-line grouping that may span multiple HF orgs (e.g. `inclusionai` curates Ring/Ling/Ming series under separate HF namespaces but treats them as one brand).

This refactor replaces `brand_hf_orgs` (M:N brands↔HF-orgs) with `hf_orgs` (1:N companies→HF-orgs) and changes `products.hf_org` (TEXT) to `products.hf_org_id` (TEXT FK → `hf_orgs.id`). The crawl entry-point switches from "for each brand, find its HF orgs" to "for each brand, look up its company via `brand_companies`, then find HF orgs for that company". The 11-row seed migrates from per-brand to per-company.

This refactor lands on the worktree DB BEFORE PR #6 merges, so production never sees `brand_hf_orgs`.

## Problem Frame

### Why the current model is wrong

`brand_hf_orgs` was designed when "brand" and "company" were treated as roughly synonymous — the curated seed had one row per brand, and the HF namespace happened to match. But:

- **Multi-org brands.** Inclusion AI curates three product lines (Ring, Ling, Ming) but those live under separate HF namespaces. Under the current model, either the operator forces all three under one HF org (lossy) or creates three brands (operator-curated product lines get fragmented).
- **Multi-brand companies.** Baidu's HF namespace (`baidu`) hosts ERNIE today, but Baidu may publish other model families under sibling HF namespaces later. The current M:N edge would force a brand to claim another brand's HF org.
- **Discovery is ambiguous.** `resolve_hf_orgs` searches HF using `brand.display_name`. If the brand name is "Inclusion AI" but the HF orgs are `inclusionai`, `InclusionAI-Ring`, `InclusionAI-Ling`, the operator has to manually wire each one to the brand. With a company→HF-orgs edge, the operator only wires the company.

### Why the new model is right

- **HF namespaces are corporate.** HuggingFace is a corporate identity (`deepseek-ai` belongs to DeepSeek Co, `MiniMaxAI` belongs to MiniMax). The corporate parent is the natural owner.
- **Brands are operator-curated.** A brand is "what we call this product line in our analytics". It is a marketing/aggregation axis, not a real-world entity with exclusive ownership of any HF namespace.
- **`brand_companies` already exists.** The M:N brand↔company edge (migration 004) gives us the path brand → company for free. The new `hf_orgs` table hangs off `companies`, so brand → company → HF orgs is a clean two-hop.

## Requirements Trace

- **R1.** `hf_orgs` is a real table (FK target), 1:N from `companies`. `confirmed` and `discovered_via` semantics preserved.
- **R2.** `brand_hf_orgs` table is removed; all references replaced by the new path.
- **R3.** `products.hf_org_id` is a TEXT FK to `hf_orgs.id` with `ON DELETE SET NULL` (preserve model identity even if an org is dropped).
- **R4.** The HF crawler resolves a brand to HF orgs via `brand_companies.brand_id → companies.company_id → hf_orgs.company_id`. Brands without a `brand_companies` edge (currently 1: `_unattributed` sentinel) get no HF coverage.
- **R5.** The 11-row curated seed is rewritten: per-company (10 rows: alibaba→Qwen, baidu→baidu, tencent→tencent, moonshot→moonshotai, zhipu→THUDM, xiaomi→XiaomiMiMo, mistral_ai→mistralai, inclusion_ai→inclusionAI, deepseek_co→deepseek-ai, stepfun_inc→stepfun-ai). One additional seed row for any future multi-org company is acceptable.
- **R6.** Discovery (`x_monitor.hf_products.resolve_hf_orgs`): searches HF using `companies.display_name` (not `brand.display_name`); persists candidates to `hf_orgs` with `confirmed=0`.
- **R7.** All existing tests pass after rewrite; new test coverage for the company→HF-orgs path.
- **R8.** Live smoke test against real HF (e.g. `alibaba → Qwen`) confirms the rewritten crawler produces the same product set as the prior MiniMax smoke test.

## Scope Boundaries

- **Out of scope:** extending the HF crawler to datasets/spaces (already deferred from the original plan).
- **Out of scope:** changing `brand_companies` shape or the `_unattributed` sentinel.
- **Out of scope:** migrating existing production data — `brand_hf_orgs` never reached production.
- **Out of scope:** renaming `hf_orgs.id` to anything other than the HF namespace string itself (e.g. `MiniMaxAI`). The PK is the namespace; no surrogate integer.
- **Out of scope:** any change to the `_unattributed` brand's behavior — it has no `brand_companies` edge, so it never appears in HF coverage.

## Context & Research

### Relevant code and patterns

- `x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql` — `brand_companies` table (PK `(brand_id, company_id)`, FK to both, `ownership_pct`). Shape template for any new edge table.
- `x-monitoring/x_monitor/migrations/005_quoted_text.sql` and `006_quote_capture_tracking.sql` — examples of additive migrations; `005_products.sql` (worktree only) needs replacement.
- `worktrees/hf-products/x-monitoring/x_monitor/migrations/005_products.sql` — current migration to be rewritten. Drop `brand_hf_orgs` table, drop its seed rows, change `products.hf_org` → `products.hf_org_id` FK.
- `worktrees/hf-products/x-monitoring/x_monitor/store.py` lines 939–1020 — `read_brand_hf_orgs`, `upsert_brand_hf_org`, `upsert_product`. Replace the first two; modify the third.
- `worktrees/hf-products/x-monitoring/x_monitor/hf_products.py` lines 50–100 — `resolve_hf_orgs`. Rewrite to take `company_id` + `display_name` (not `brand_id` + `display_name`).
- `worktrees/hf-products/x-monitoring/x_monitor/__main__.py` lines 736–770 — `cmd_hf_products`. The argparser already uses `--companies`; clarify the docstring to mean company_ids.

### Institutional learnings

- The existing `x_monitoring.db` (production, 36 MB, 4,191 posts) has migrations 1–6 applied and **does not** have `brand_hf_orgs` or `products`. Both are worktree-only.
- `brand_hf_orgs` had four non-FK columns (`is_primary`, `confirmed`, `discovered_via`, `added_at`) which made it a real associative entity. The replacement `hf_orgs` table keeps the same three non-FK columns (`confirmed`, `discovered_via`, `added_at`); `is_primary` is **dropped** because with one company owning multiple HF orgs, "primary" loses meaning (HF orgs of the same company are equally canonical).
- Per memory `feedback_parallel_subagents_ximports.md`, multi-area refactors benefit from explicit cross-import contracts. This refactor changes four files; the implementer should mentally verify the contract before each unit: `hf_orgs.id` is the canonical PK string, and `products.hf_org_id` always references it.

### External references

- HuggingFace Hub REST API: `/api/organizations` returns `[{name, ...}]`; `name` is the canonical namespace (e.g. `MiniMaxAI`, `deepseek-ai`, `Qwen`). This is what goes into `hf_orgs.id`.
- HuggingFace model list: `/api/models?author={hf_org}` returns models owned by that namespace. Authoring namespace matches `hf_orgs.id` exactly.

## Key Technical Decisions

- **`hf_orgs` is a dedicated table, not a JSON column on `companies`.** Provides referential integrity (FK from `products.hf_org_id`), queryable indexes, and matches the project's pattern of M:N edge tables.
- **1:N from companies (not M:N).** A given HF namespace can only belong to one corporate parent. The seed currently has no namespace shared across companies; if that ever happens, it's a data-quality bug worth flagging, not a normal case.
- **`products.hf_org_id` is TEXT FK with `ON DELETE SET NULL`.** Preserves model identity (`repo_id` survives) when an HF org is dropped. Mirrors the existing `products.brand_id` `SET NULL` semantics.
- **No `is_primary` on `hf_orgs`.** With one company owning the org, all rows for that company are equally "primary"; `is_primary` was only meaningful in the M:N brand context (one brand per HF org was canonical). Drop it from the new schema.
- **Discovery uses `companies.display_name`.** `resolve_hf_orgs` calls `hf_client.search_organizations(company.display_name)` instead of the brand name. Rationale: HF namespaces are corporate; searching by brand gives noise.
- **`_unattributed` brand is naturally excluded.** The sentinel has no `brand_companies` row, so it never enters the crawler. No special-case code needed.

## Open Questions

### Resolved during planning

- **Edge shape:** dedicated `hf_orgs` table (1:N from companies). [User answer.]
- **FK promotion:** `products.hf_org_id` becomes a real FK. [User answer.]
- **Seed strategy:** re-seed from `brand_companies` (use the existing brand→company edge as the lookup path). [User answer.]
- **Deprecation timing:** replace on worktree BEFORE PR #6 merges. [User answer.]

### Deferred to implementation

- **Exact seed row counts per company.** Most companies have one HF org; if a company needs two (e.g. `inclusion_ai → inclusionAI, InclusionAI-Ring`), the seed is a list. The implementer should verify the HF Hub `/api/organizations` endpoint returns the expected namespaces before finalizing the seed.
- **Whether `hf_orgs.confirmed` should be a column or a CHECK.** `confirmed=0` rows are runtime candidates. Stays as INT (matches `brand_hf_orgs` precedent) — not deferred, but worth flagging for test coverage.
- **`x_monitor.store` import order.** When `hf_orgs` is referenced from `store.upsert_product`, the FK target table must exist before the migration runs. The migration's order: CREATE `hf_orgs` → ALTER `products` → seed. This is a sequencing constraint, not an open question — but the implementer should confirm with `pragma foreign_keys = ON`.

## High-Level Technical Design

> *Directional guidance for review, not implementation specification. The implementing agent should treat this as context, not code to reproduce.*

### Data model (before vs after)

```
BEFORE                                  AFTER
──────                                  ─────
companies                               companies
  └─ brand_companies  (M:N)               └─ brand_companies  (M:N)
       └─ brands                            └─ brands
            └─ brand_hf_orgs (M:N)               │
                 └─ hf_orgs (TEXT)               └─ hf_orgs (NEW, 1:N)
                                                   └─ products.hf_org_id (FK)
                                                        └─ products
```

The `hf_orgs` table hangs off `companies` directly. `brands` are reached via `brand_companies` (already exists). `products` has two FK columns: `brand_id` → `brands` (unchanged), `hf_org_id` → `hf_orgs` (new, replaces TEXT).

### Migration shape (replacement for 005_products.sql)

The new `005_products.sql`:

```
1. CREATE hf_orgs (id TEXT PK, company_id TEXT FK CASCADE, confirmed INT,
                  discovered_via TEXT, added_at TEXT)
2. CREATE idx_hf_orgs_company (company_id)
3. CREATE products (... hf_org_id TEXT FK → hf_orgs(id) ON DELETE SET NULL ...)
4. CREATE idx_products_hf_org_id (hf_org_id)
5. CREATE idx_products_brand (brand_id)  -- already in original
6. INSERT OR IGNORE hf_orgs with 10 per-company seed rows
```

`brand_hf_orgs` is not created at all. The `products` table renames `hf_org` → `hf_org_id` and adds the FK.

### Crawler flow

```
cmd_hf_products(args, paths):
  for company_id in args.companies:
    brands = SELECT brand_id FROM brand_companies WHERE company_id = ?
    for brand_id in brands:
      hf_org_rows = read_hf_orgs_for_company(company_id, confirmed_only=True)
      for hf_org_row in hf_org_rows:
        collect_products_for_org(brand_id, hf_org_row.id)
```

The CLI flag `--companies` was already a list of identifiers; the docstring will be clarified to mean company_ids. The crawl is per-company (the natural unit of HF coverage); each company yields 1..N HF orgs; each HF org yields 0..N products; each product is attributed to one of that company's brands (since brands are operators-curated groupings within the company).

## Implementation Units

- [ ] **Unit 1: Rewrite migration 005_products.sql**

**Goal:** Drop `brand_hf_orgs`, add `hf_orgs` (1:N from companies), rename `products.hf_org` to `products.hf_org_id` with FK, update the seed.

**Requirements:** R1, R2, R3, R5

**Dependencies:** None (first unit; nothing depends on it yet)

**Files:**
- Modify: `worktrees/hf-products/x-monitoring/x_monitor/migrations/005_products.sql`

**Approach:**
- Re-author the file as if it were new. Replace the `brand_hf_orgs` `CREATE TABLE` and its `INSERT OR IGNORE` seed with a new `hf_orgs` table. Change `products.hf_org TEXT NOT NULL` to `products.hf_org_id TEXT` (drop NOT NULL since SET NULL) with `FOREIGN KEY(hf_org_id) REFERENCES hf_orgs(id) ON DELETE SET NULL`. Update `idx_products_hf_org` to `idx_products_hf_org_id` on `(hf_org_id)`.
- Seed: 10 rows mapping `company_id → hf_org_id`. Each row sets `confirmed=1, is_primary=0` (dropped), `discovered_via='curated', added_at='2026-06-22T...'`. Mapping table:

  | company_id | hf_org_id |
  |---|---|
  | alibaba | Qwen |
  | baidu | baidu |
  | tencent | tencent |
  | moonshot | moonshotai |
  | zhipu | THUDM |
  | xiaomi | XiaomiMiMo |
  | mistral_ai | mistralai |
  | inclusion_ai | inclusionAI |
  | deepseek_co | deepseek-ai |
  | stepfun_inc | stepfun-ai |

- The migration must remain idempotent (`CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE`) so re-running on the worktree DB after a schema drift is safe.
- `PRAGMA foreign_keys = ON` is set by `Store` before migration runs, so the FK enforcement is on.

**Execution note:** Test the migration on a fresh DB and on the existing worktree DB. Existing `products` rows have `hf_org` set; the column rename must preserve those values.

**Test scenarios:**
- Happy path: fresh DB → migration 005 applies → `hf_orgs` has 10 rows, `products` table exists with `hf_org_id` FK column, `brand_hf_orgs` does not exist.
- Edge case: re-running migration on a DB that already has it → no duplicates, no errors (idempotent).
- Edge case: existing `products` rows survive the column rename (data preserved).
- Error path: try to INSERT a `products` row with `hf_org_id = 'nonexistent-org'` — must fail at the FK.

**Verification:** After running `python -m x_monitor --db <fresh> migrate`, the schema is:
- `\d hf_orgs` shows `(id TEXT PK, company_id TEXT FK CASCADE, confirmed, discovered_via, added_at)` with 10 seed rows.
- `\d products` shows `hf_org_id TEXT` (no NOT NULL) with FK to `hf_orgs(id)`.
- `\d brand_hf_orgs` returns "no such table".

- [ ] **Unit 2: Rewrite store.py methods for hf_orgs**

**Goal:** Replace `read_brand_hf_orgs` and `upsert_brand_hf_org` with company-centric versions.

**Requirements:** R1, R4, R6

**Dependencies:** Unit 1 (migration must exist)

**Files:**
- Modify: `worktrees/hf-products/x-monitoring/x_monitor/store.py`

**Approach:**
- Delete `read_brand_hf_orgs(brand_id, *, confirmed_only=True)`.
- Add `read_hf_orgs(company_id, *, confirmed_only=True)` returning `list[dict]` with keys `{id, company_id, confirmed, discovered_via, added_at}`. Sort by `id ASC` for determinism.
- Delete `upsert_brand_hf_org(brand_id, hf_org, *, confirmed=0, is_primary=0, discovered_via="search")`.
- Add `upsert_hf_org(hf_org_id, company_id, *, confirmed=0, discovered_via="search")` with `INSERT ... ON CONFLICT(id) DO UPDATE SET confirmed = MAX(...)` (preserve `confirmed=1` if either side asserts it; preserve `discovered_via='curated'` if existing row has it).
- Modify `upsert_product` to accept `hf_org_id` instead of `hf_org`. Update the `cols` and `mutable` lists accordingly. The FK constraint catches a bad `hf_org_id` at INSERT.

**Patterns to follow:**
- `upsert_brand_companies` in the same file (look around line 800) for the upsert SQL pattern. The new `upsert_hf_org` mirrors its structure with the `ON CONFLICT ... DO UPDATE SET` clause.
- `read_brand_companies(brand_id, ...)` (around line 800) for the read pattern with the `confirmed_only` filter.

**Test scenarios:**
- Happy path: insert `hf_orgs` row, `read_hf_orgs(company_id, confirmed_only=True)` returns it; `confirmed_only=False` returns it plus unconfirmed candidates.
- Happy path: `upsert_hf_org(...)` with `confirmed=1` is idempotent — calling twice leaves `confirmed=1`.
- Edge case: `upsert_hf_org(..., confirmed=0)` on an existing `confirmed=1` row does NOT demote (the MAX-of-confirmed logic).
- Edge case: `upsert_hf_org(..., discovered_via='search:x')` on an existing row with `discovered_via='curated'` preserves `'curated'`.
- Error path: `upsert_hf_org(id='x', company_id='nonexistent')` raises an `IntegrityError` (FK violation).

**Verification:** New tests in `test_hf_products.py` (the existing `test_read_brand_hf_orgs_*` and `test_upsert_brand_hf_org_*` tests get renamed to `test_read_hf_orgs_*` and `test_upsert_hf_org_*`).

- [ ] **Unit 3: Rewrite hf_products.py resolve_hf_orgs + collect_all**

**Goal:** Change the crawler to look up HF orgs via companies, not brands.

**Requirements:** R4, R6

**Dependencies:** Units 1, 2

**Files:**
- Modify: `worktrees/hf-products/x-monitoring/x_monitor/hf_products.py`

**Approach:**
- Rewrite `resolve_hf_orgs(company_id, display_name, store, *, client=None, persist=True)`. The signature loses `brand_id` and gains `company_id`. The function:
  1. Reads `store.read_hf_orgs(company_id, confirmed_only=True)`. If non-empty, return them.
  2. If `persist=False`, return `[]`.
  3. Otherwise call `hf_client.search_organizations(display_name, client=client)`; for each candidate, call `store.upsert_hf_org(name, company_id, confirmed=0, discovered_via=f"search:{display_name}")`. Return `[]` (candidates are flagged, not scraped).
- Rewrite the outer loop in `collect_all` to iterate companies, then for each company iterate its brands (via `store.read_brand_companies(company_id)`), and for each (brand, hf_org) pair call `collect_products_for_org(brand_id, hf_org_row["id"])`.
- Update `_model_to_product_row` to accept `hf_org_id` (the resolved hf_orgs row's id) and stamp it on every product row instead of the prior `hf_org` TEXT.
- The CLI's `--companies` flag now means **company_ids**, not brand_ids. Update the docstring on `cmd_hf_products` accordingly.

**Execution note:** This unit changes the public contract of `resolve_hf_orgs`. The implementer should also update any module-level imports / re-exports in `x_monitor/__init__.py`.

**Test scenarios:**
- Happy path: `resolve_hf_orgs('alibaba', 'Alibaba', store)` returns the seeded `Qwen` row (1 confirmed org).
- Happy path: brand-with-multiple-hf-orgs — `inclusion_ai` returns `[inclusionAI]`; if a second org is added, returns both.
- Happy path: a brand whose company has zero HF coverage → `resolve_hf_orgs` searches and persists candidates with `confirmed=0`.
- Edge case: brand with no `brand_companies` row (`_unattributed`) → resolve_hf_orgs is never called for it (the outer `collect_all` loop skips it).
- Edge case: `persist=False` (CLI `--dry-run`) → no `search_organizations` call, no writes.
- Integration: end-to-end `collect_all` with `--companies alibaba` on a real HF API call returns ≥1 product for `Qwen/...` models.

**Verification:** `python -m x_monitor hf-products --companies alibaba --dry-run` prints the resolved HF orgs without writing. Then `python -m x_monitor hf-products --companies alibaba` (no `--dry-run`) writes ≥1 product row.

- [ ] **Unit 4: Update tests for the new schema**

**Goal:** Every test that referenced `brand_hf_orgs`, `brand_id` arguments, or `hf_org` TEXT columns is updated to the new shape.

**Requirements:** R7

**Dependencies:** Units 1–3

**Files:**
- Modify: `worktrees/hf-products/x-monitoring/tests/test_migration_005_products.py`
- Modify: `worktrees/hf-products/x-monitoring/tests/test_hf_products.py`
- Modify: `worktrees/hf-products/x-monitoring/tests/test_store.py` (the `products` row-construction tests)
- Modify: `worktrees/hf-products/x-monitoring/tests/test_hf_cli.py`

**Approach:**
- `test_migration_005_products.py`: rename docstring; assert `hf_orgs` exists with the expected columns; assert `brand_hf_orgs` does NOT exist; update seed count assertions (10 rows for `hf_orgs` instead of 11 for `brand_hf_orgs`); assert `products.hf_org_id` column exists with FK to `hf_orgs.id`.
- `test_hf_products.py`: rename `test_read_brand_hf_orgs_*` and `test_upsert_brand_hf_org_*` to `test_read_hf_orgs_*` and `test_upsert_hf_org_*`. Update argument signatures (`brand_id` → `company_id`). Add new tests for the `inclusion_ai` multi-org case (one row, can extend to two if the seed has them).
- `test_store.py`: update `upsert_product` tests to pass `hf_org_id` instead of `hf_org` in row dicts. Update migration 005 test data.
- `test_hf_cli.py`: update CLI assertions for the new JSON output shape (the result dict now keys by company_id, with brand_id nested inside each company).

**Test scenarios:** (per-file)
- Migration: see Unit 1.
- Store: see Unit 2.
- Crawler: see Unit 3.
- CLI: `--companies alibaba` produces a JSON result with key `"alibaba"` containing nested brand/hf_org arrays.

**Verification:** `pytest tests/ -q` from the worktree `.venv` reports ≥305 passing (current is 297; expect +8 from new tests, -0 from removed tests).

- [ ] **Unit 5: Live smoke test**

**Goal:** Run the rewritten crawler against a real HF org to confirm end-to-end behavior.

**Requirements:** R8

**Dependencies:** Units 1–4

**Files:**
- Create: `minimax-hf-products-v2.json` (artifact, not committed)

**Approach:**
- Run `python -m x_monitor hf-products --companies alibaba` on the worktree DB.
- Verify the result JSON contains ≥1 `Qwen/...` product.
- Re-run the same command and verify the same products are upserted (no duplicates).
- Run `--companies baidu` and verify `baidu/ERNIE` appears.
- Optionally run `--companies inclusion_ai` and confirm `InclusionAI/...` products land under the `inclusionai` brand.

**Test scenarios:**
- Happy path: `alibaba` → ≥1 product from `Qwen/...` namespace.
- Idempotency: second run produces `upserted > 0, inserted = 0`.
- Edge case: a brand with no `brand_companies` row is silently skipped (no error).
- Integration: end-to-end timing <60s for one company with ≤30 products.

**Verification:** The crawler returns a `result["alibaba"]` dict containing `"products": [{"repo_id": "Qwen/Qwen2.5-...", ...}, ...]` with the `brand_id: "qwen"` field on each.

- [ ] **Unit 6: Update schema documentation**

**Goal:** Reflect the new schema in `docs/reference/2026-06-18-145000-x-monitoring-db-schema.md`.

**Requirements:** Documentation parity with the rewritten schema (no behavior change, but the doc must match reality).

**Dependencies:** Units 1–3

**Files:**
- Modify: `docs/reference/2026-06-18-145000-x-monitoring-db-schema.md` (the "Pending (worktree-only) tables" section)
- Modify: `docs/reference/minimax-hf-products-2026-06-22.md` (the report) — re-generate if needed

**Approach:**
- Rename the `brand_hf_orgs` section to `hf_orgs`, retitle the seed table, add the FK target note, drop the `is_primary` row from the column list.
- Update the `products` section: rename `hf_org` to `hf_org_id`, update the FK annotation.
- Update the ER overview if the diagram still references `brand_hf_orgs` (it currently does in a side panel — replace with `hf_orgs`).
- Update the migration-history footnote to mention "company-owned HF orgs" rather than "M:N brand↔HF-orgs".

**Test scenarios:** (none — pure doc work; verified by reading)

**Verification:** The doc renders the new table name, new FK, and the seed row count matches the migration.

## System-Wide Impact

- **Interaction graph:** `cmd_hf_products` (CLI) → `hf_products.collect_all` → `hf_products.resolve_hf_orgs` → `store.read_hf_orgs` / `store.upsert_hf_org` → `hf_client.search_organizations`. Every link in the chain changes signature; verify each before committing.
- **Error propagation:** `IntegrityError` from a bad `hf_org_id` in `upsert_product` propagates up to `collect_products_for_org`'s per-model try/except — already isolated, so a single bad product is skipped, not the whole org. Confirm the implementer keeps that boundary intact.
- **State lifecycle risks:** `PRAGMA foreign_keys = ON` must be set before the migration runs; otherwise the FK on `products.hf_org_id` is created but never enforced. Confirm by running a smoke `INSERT INTO products (..., hf_org_id='bogus', ...)` after migration and observing `IntegrityError`.
- **API surface parity:** The public functions changed are `resolve_hf_orgs` (signature change) and the store methods (rename + arg change). Any caller outside `x_monitor` that imports these gets a clean `ImportError` on stale function names — no silent breakage.
- **Integration coverage:** Unit 5 (live smoke) is the integration scenario; mocks alone prove the new logic but not that the FK is actually enforced by SQLite with `PRAGMA foreign_keys = ON`.
- **Unchanged invariants:** `products.brand_id` semantics unchanged; `brand_companies` unchanged; `_unattributed` sentinel behavior unchanged; `products.repo_id` PK unchanged; all HF Hub REST API calls unchanged; `hf_type` CHECK unchanged.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Existing worktree DB has `brand_hf_orgs` data; new migration fails on re-apply | Med | Med | Migration drops nothing. The new schema is additive. Re-running `migrate` on an existing DB with `brand_hf_orgs` leaves the old table intact (orphaned). Manual cleanup: `DROP TABLE brand_hf_orgs;` once after first apply. |
| Seed HF namespace strings don't match what HF Hub actually returns | Low | High | Live smoke in Unit 5 catches this. If `baidu → baidu` returns 0 models on HF, fix the seed to `baidu/ERNIE` or wherever the models actually live. |
| `resolve_hf_orgs` is called with `brand_id` somewhere we missed | Med | Med | Unit 4 tests + a grep for `resolve_hf_orgs(` catches it. |
| `_unattributed` brand is silently dropped (no `brand_companies` edge) | Low | Low | Intentional — sentinel rows aren't real brands and shouldn't be scraped. Confirmed acceptable. |
| The FK target `hf_orgs.id` is the namespace string; renaming a namespace on HF breaks history | Low | Med | Same risk as `author_handle` renames on X — accepted industry pattern. `products.hf_org_id ON DELETE SET NULL` preserves the product row but nulls the link. |
| Test count regression (some old tests deleted without replacement) | Low | Low | Net target: ≥305 tests. Track count in PR description. |

## Documentation / Operational Notes

- **Schema doc update** (Unit 6) keeps `docs/reference/2026-06-18-145000-x-monitoring-db-schema.md` accurate.
- **Plan update:** mark this plan `status: completed` once PR #6 merges.
- **Operator runbook:** `scripts/run_hf_products.sh` does not change. The HF_TOKEN env var is unchanged. The CLI flag `--companies` continues to work, but now means `company_id` (was loosely "brand_id or display name").
- **Migration safety:** `005_products.sql` (worktree) is the migration. It is purely additive (CREATE IF NOT EXISTS + INSERT OR IGNORE) and idempotent. If a developer has previously applied the old version on the worktree DB, the old `brand_hf_orgs` table is orphaned but harmless until manually dropped. No data is lost.
- **Post-merge:** once PR #6 lands, production gets the new schema directly. The old `brand_hf_orgs` never reaches production.

## Sources & References

- **Origin document:** [docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md](2026-06-21-001-feat-hf-products-crawler-plan.md) — the prior HF-products plan, whose Unit 2 (`brand_hf_orgs`) is being reshaped.
- **Related code:** [worktrees/hf-products/x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql](../../worktrees/hf-products/x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql) — `brand_companies` table template (used as the shape reference for `hf_orgs`).
- **Related code:** [worktrees/hf-products/x-monitoring/x_monitor/store.py](../../worktrees/hf-products/x-monitoring/x_monitor/store.py) — `upsert_brand_companies` and `read_brand_companies` are the templates for the new `upsert_hf_org` / `read_hf_orgs`.
- **Related code:** [worktrees/hf-products/x-monitoring/x_monitor/hf_products.py](../../worktrees/hf-products/x-monitoring/x_monitor/hf_products.py) — `resolve_hf_orgs` and `collect_all` to be rewritten.
- **External docs:** [HuggingFace Hub REST API](https://huggingface.co/docs/hub/api) — `/api/organizations`, `/api/models?author={org}`.
- **PR target:** PR #6 (`feat/hf-products-crawler`), to be amended before merge.
