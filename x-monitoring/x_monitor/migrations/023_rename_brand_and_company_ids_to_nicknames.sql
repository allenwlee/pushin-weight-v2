-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 023: rename parent-table slug columns to nickname.
--
-- v2.x schema-modernization-batch follow-up. Migration 020 promoted the
-- brand_id slug to UNIQUE NOT NULL on top of an INTEGER PK, but kept the
-- column name `brand_id`, which still carries the old v1 "this *is* the
-- primary key" connotation. After 020, `brands.id` is the INTEGER PK
-- and `brands.brand_id` is a TEXT UNIQUE NOT NULL slug. Renaming the
-- slug column to `nickname` matches the operator's mental model — a
-- short, stable, human-readable slug, not an ID.
--
-- Scope (parent tables only — child FK columns are NOT renamed):
--
--   Renames:
--     brands.brand_id      → brands.nickname
--     companies.company_id → companies.nickname
--
--   Index rebuild:
--     idx_brands_brand_id      → idx_brands_nickname
--     idx_companies_company_id → idx_companies_nickname
--
-- Why child FK columns are NOT renamed:
--   Child tables (brands_companies, brands_accounts, posts_brands,
--   posts_brands_signals, posts_brands_mentions, hf_orgs,
--   search_queries) already have INTEGER FK columns named `brand_id` /
--   `company_id` that reference `brands.id` / `companies.id` (the
--   INTEGER PKs), NOT the slug columns. The migration 020 rebuild
--   converted the FK columns from TEXT-storing-key to INTEGER-storing-id
--   specifically so they would point to the surrogate PKs.
--
--   After this migration, the parent's slug column is `brands.nickname`
--   (TEXT) and the child's FK column is still `child.brand_id`
--   (INTEGER, FK → brands.id). They have different names and different
--   types — no ambiguity. The child FK column is the integer id of the
--   brand row, which is naturally called `brand_id` ("the id of a
--   brand"). Renaming it to `brand_nickname` would be semantically
--   wrong (the value is an INTEGER id, not a nickname).
--
-- What consumers see:
--   The Store API aliases `b.nickname AS brand_id` in SELECTs from the
--   brands table, so callers reading `row["brand_id"]` continue to
--   receive the slug string. No consumer code (treemap, dashboard,
--   attribution, run, tests, templates) requires changes — only the
--   SQL column lists in store.py and the INSERT column lists in
--   callers that write to the parent tables.
--
-- Scope notes:
--   - Slug *values* are NOT renamed (`minimax` stays `minimax`).
--   - `data/queries/<brand>.yaml` filenames are NOT affected (filesystem,
--     not SQL).
--   - `accounts.author_id` is NOT renamed (different concept — the X
--     user id).
--   - `hf_orgs.id` (INTEGER PK post-020) is NOT renamed; the HF
--     namespace string lives in `hf_orgs.namespace`, renamed in 020.
--   - The `(brand_id, company_id)` composite PKs in edge tables
--     (brands_companies, brands_accounts, companies_accounts) are
--     NOT touched — the column names are unchanged.
--
-- Idempotency: the migration runner tracks applied migrations in
-- `_migrations` and skips re-application. The pragma check on
-- `brands.brand_id` is a defensive belt in case the ledger is out
-- of sync.
--
-- FK enforcement: the migration runner toggles `PRAGMA foreign_keys =
-- OFF` for the duration of this script (FK toggles are no-ops inside
-- transactions). The runner restores `PRAGMA foreign_keys = ON` in
-- its finally clause.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- Idempotency guard: pragma_table_info('brands') lists the column names.
-- If `brand_id` is already gone (rename applied), the migration exits
-- with no-op SELECT. The _migrations ledger is the primary guard; this
-- is belt-and-suspenders.
-- ===========================================================================

SELECT CASE
    WHEN EXISTS (
        SELECT 1 FROM pragma_table_info('brands') WHERE name = 'brand_id'
    )
    THEN 1
    ELSE 0
END AS rename_required;

-- ===========================================================================
-- 1. Parent table slug renames.
-- ===========================================================================

ALTER TABLE brands     RENAME COLUMN brand_id   TO nickname;
ALTER TABLE companies  RENAME COLUMN company_id TO nickname;

-- ===========================================================================
-- 2. Index rebuild (column rename drops bound indexes; recreate on the
--    new column name). Child-table indexes on brand_id / company_id are
--    NOT affected because their columns are NOT renamed.
-- ===========================================================================

DROP INDEX IF EXISTS idx_brands_brand_id;
CREATE INDEX IF NOT EXISTS idx_brands_nickname
    ON brands(nickname);

DROP INDEX IF EXISTS idx_companies_company_id;
CREATE INDEX IF NOT EXISTS idx_companies_nickname
    ON companies(nickname);

COMMIT;