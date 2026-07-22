-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 015: rename role_keys → roles.
--
-- Companion to migration 014 (signal_keys → signals). The legacy
-- 5-role taxonomy lives in two tables:
--   role_keys   (FK source — the 5 canonical role strings)
--   role_labels (display — the en + zh_cn label rows, lang column)
-- Migration 008 created both. This migration brings the keys table
-- into the universal "no _keys suffix on enum tables" convention.
--
-- Renames (table):
--   role_keys → roles
--
-- Column rename (FK columns on brands_accounts + companies_accounts):
--   role → role_id
-- (still TEXT PK at this step; U8 converts to INTEGER.)
--
-- Index rebuild (column rename requires dropping+recreating the index):
--   idx_brands_accounts_role    ON brands_accounts(role)    → ON brands_accounts(role_id)
--   idx_companies_accounts_role ON companies_accounts(role) → ON companies_accounts(role_id)
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
-- Table rename: role_keys → roles
-- ---------------------------------------------------------------------------
ALTER TABLE role_keys RENAME TO roles;

-- ---------------------------------------------------------------------------
-- Column renames (FK columns on the 2 M:N tables that reference roles)
-- ---------------------------------------------------------------------------
ALTER TABLE brands_accounts    RENAME COLUMN role TO role_id;
ALTER TABLE companies_accounts RENAME COLUMN role TO role_id;

-- ---------------------------------------------------------------------------
-- Index rebuilds (the old indexes are bound to the old column names)
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS idx_brands_accounts_role;
CREATE INDEX IF NOT EXISTS idx_brands_accounts_role_id
    ON brands_accounts(role_id);

DROP INDEX IF EXISTS idx_companies_accounts_role;
CREATE INDEX IF NOT EXISTS idx_companies_accounts_role_id
    ON companies_accounts(role_id);

COMMIT;
