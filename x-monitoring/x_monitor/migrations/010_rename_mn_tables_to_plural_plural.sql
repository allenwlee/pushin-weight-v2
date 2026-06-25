-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 010: rename M:N join tables to plural-plural form.
--
-- Original DDL is in migration 004 (the 5 M:N tables were created there)
-- and the FK conversions ran in migration 008. This migration does ONLY
-- the rename — no DDL changes, no data changes, no FK changes. After
-- this migration applies, FK references in other tables (e.g.
-- products.brand_id → brands) are unchanged, but the table names and
-- index names of these 5 M:N tables are aligned to the plural-plural
-- convention used by sibling migrations.
--
-- Renames (tables):
--   brand_accounts    → brands_accounts
--   brand_companies   → brands_companies
--   company_accounts  → companies_accounts
--   post_brands       → posts_brands
--   post_brand_signals → posts_brands_signals
--
-- Renames (indexes, follow table name + suffix):
--   idx_post_brands_brand               → idx_posts_brands_brand
--   idx_post_brands_brand_post          → idx_posts_brands_brand_post
--   idx_post_brand_signals_brand_signal → idx_posts_brands_signals_brand_signal
--   idx_post_brand_signals_post         → idx_posts_brands_signals_post
--   idx_brand_accounts_role             → idx_brands_accounts_role
--   idx_company_accounts_role           → idx_companies_accounts_role
--
-- Idempotency: the x-monitor migration runner tracks applied migrations
-- in `_migrations` and skips re-application. This script does not need
-- IF EXISTS guards on the renames themselves — the runner enforces
-- "run once per fresh DB".
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ---------------------------------------------------------------------------
-- Table renames (M:N join tables → plural-plural form)
-- ---------------------------------------------------------------------------
ALTER TABLE brand_accounts    RENAME TO brands_accounts;
ALTER TABLE brand_companies   RENAME TO brands_companies;
ALTER TABLE company_accounts  RENAME TO companies_accounts;
ALTER TABLE post_brands       RENAME TO posts_brands;
ALTER TABLE post_brand_signals RENAME TO posts_brands_signals;

-- ---------------------------------------------------------------------------
-- Index renames (drop old, create new on the renamed table)
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS idx_post_brands_brand;
CREATE INDEX IF NOT EXISTS idx_posts_brands_brand
    ON posts_brands(brand_id);

DROP INDEX IF EXISTS idx_post_brands_brand_post;
CREATE INDEX IF NOT EXISTS idx_posts_brands_brand_post
    ON posts_brands(brand_id, post_id);

DROP INDEX IF EXISTS idx_post_brand_signals_brand_signal;
CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_signal
    ON posts_brands_signals(brand_id, signal);

DROP INDEX IF EXISTS idx_post_brand_signals_post;
CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_post
    ON posts_brands_signals(post_id);

DROP INDEX IF EXISTS idx_brand_accounts_role;
CREATE INDEX IF NOT EXISTS idx_brands_accounts_role
    ON brands_accounts(role);

DROP INDEX IF EXISTS idx_company_accounts_role;
CREATE INDEX IF NOT EXISTS idx_companies_accounts_role
    ON companies_accounts(role);

COMMIT;