-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 006: i18n locale columns on registry tables.
--
-- Adds per-locale display columns (en + zh_cn) so the dashboard can
-- render registry rows (brand display names, company display names,
-- account bios) in the user's selected locale. Source columns
-- (display_name, bio) are retained as the fallback / canonical
-- English source.
--
-- Pattern: mirror v1.7 migration 003 (text_en / text_zh_cn on posts).
-- Forward-only: existing rows get NULL on the new columns. The
-- dashboard falls back to the source display_name / bio when the
-- locale column is NULL.
--
-- Backfill driver: partial indexes WHERE <col>_<locale> IS NULL. The
-- translator extension (x_monitor.translator.translate_registry_rows)
-- reads these indexes to find rows needing translation.
--
-- Plan: docs/plans/2026-06-23-001-feat-i18n-locale-columns-plan.md
--
-- Sequencing note (D3): this migration is numbered 006 because the
-- HuggingFace products migration 005_products.sql lives on branch
-- feat/hf-products-crawler (unmerged). Renumbering would conflict
-- when that branch merges.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- 1. brands.display_name_en / display_name_zh_cn (R1)
-- ===========================================================================

ALTER TABLE brands ADD COLUMN display_name_en   TEXT;
ALTER TABLE brands ADD COLUMN display_name_zh_cn TEXT;

CREATE INDEX IF NOT EXISTS idx_brands_display_name_en_backfill
    ON brands(brand_id)
    WHERE display_name_en IS NULL;

CREATE INDEX IF NOT EXISTS idx_brands_display_name_zh_cn_backfill
    ON brands(brand_id)
    WHERE display_name_zh_cn IS NULL;

-- ===========================================================================
-- 2. companies.display_name_en / display_name_zh_cn (R1)
-- ===========================================================================

ALTER TABLE companies ADD COLUMN display_name_en   TEXT;
ALTER TABLE companies ADD COLUMN display_name_zh_cn TEXT;

CREATE INDEX IF NOT EXISTS idx_companies_display_name_en_backfill
    ON companies(company_id)
    WHERE display_name_en IS NULL;

CREATE INDEX IF NOT EXISTS idx_companies_display_name_zh_cn_backfill
    ON companies(company_id)
    WHERE display_name_zh_cn IS NULL;

-- ===========================================================================
-- 3. accounts.bio_en / bio_zh_cn (R2)
-- ===========================================================================

ALTER TABLE accounts ADD COLUMN bio_en    TEXT;
ALTER TABLE accounts ADD COLUMN bio_zh_cn TEXT;

CREATE INDEX IF NOT EXISTS idx_accounts_bio_en_backfill
    ON accounts(author_id)
    WHERE bio_en IS NULL;

CREATE INDEX IF NOT EXISTS idx_accounts_bio_zh_cn_backfill
    ON accounts(author_id)
    WHERE bio_zh_cn IS NULL;

COMMIT;