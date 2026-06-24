-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 013: rename post_mentions → posts_brands_mentions.
--
-- The 5 M:N tables were renamed to plural-plural form in migration 010
-- (post_brands → posts_brands, post_brand_signals → posts_brands_signals,
-- brand_accounts → brands_accounts, brand_companies → brands_companies,
-- company_accounts → companies_accounts). This migration brings the
-- 1:N provenance table into the same naming convention:
--   post_mentions → posts_brands_mentions
-- (posts × brands × mentions, with source as a 3rd dimension).
--
-- Renames (table):
--   post_mentions  →  posts_brands_mentions
--
-- Renames (indexes, follow table name + suffix):
--   idx_post_mentions_brand_source_recent → idx_posts_brands_mentions_brand_source_recent
--   idx_post_mentions_post                → idx_posts_brands_mentions_post
--
-- Renames (Store API method):
--   insert_post_mentions  →  insert_posts_brands_mentions
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
-- Table rename
-- ---------------------------------------------------------------------------
ALTER TABLE post_mentions RENAME TO posts_brands_mentions;

-- ---------------------------------------------------------------------------
-- Index renames (drop old, create new on the renamed table)
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS idx_post_mentions_brand_source_recent;
CREATE INDEX IF NOT EXISTS idx_posts_brands_mentions_brand_source_recent
    ON posts_brands_mentions(brand_id, source, mentioned_at DESC);

DROP INDEX IF EXISTS idx_post_mentions_post;
CREATE INDEX IF NOT EXISTS idx_posts_brands_mentions_post
    ON posts_brands_mentions(post_id);

COMMIT;
