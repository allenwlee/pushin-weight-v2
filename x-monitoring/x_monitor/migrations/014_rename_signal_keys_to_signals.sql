-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 014: rename signal_keys → signals.
--
-- The legacy 6-signal taxonomy lives in two tables:
--   signal_keys   (FK source — the 6 canonical key strings)
--   signal_labels (display — the en + zh_cn label rows, lang column)
-- Migration 008 created both. This migration brings the keys table
-- into the universal "no _keys suffix on enum tables" convention
-- established in the schema modernization plan.
--
-- Renames (table):
--   signal_keys → signals
--
-- Column rename (FK column on posts_brands_signals):
--   signal → signal_id
-- (still TEXT PK at this step; U8 converts to INTEGER.)
--
-- Index rebuild (column rename requires dropping+recreating the index):
--   idx_posts_brands_signals_brand_signal
--     ON posts_brands_signals(brand_id, signal)
--     → ON posts_brands_signals(brand_id, signal_id)
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
-- Table rename: signal_keys → signals
-- ---------------------------------------------------------------------------
ALTER TABLE signal_keys RENAME TO signals;

-- ---------------------------------------------------------------------------
-- Column rename on posts_brands_signals: signal → signal_id
-- ---------------------------------------------------------------------------
ALTER TABLE posts_brands_signals RENAME COLUMN signal TO signal_id;

-- ---------------------------------------------------------------------------
-- Index rebuild (the old index is bound to the old column name)
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS idx_posts_brands_signals_brand_signal;
CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_signal_id
    ON posts_brands_signals(brand_id, signal_id);

COMMIT;
