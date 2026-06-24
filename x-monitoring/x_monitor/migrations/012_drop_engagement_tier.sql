-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 012: drop engagement_tier_keys + engagement_tier_labels.
--
-- The 3-tier (low/medium/high) account classification was never wired
-- into production code. Migration 008 added the i18n enum + FK
-- conversion on `accounts.engagement_tier` per the spec at the time,
-- but no production path actually USES the tier — neither the
-- dashboard, the treemap, the reattribute flow, nor any analytics
-- query reads it. The seeded values are dead weight.
--
-- The replacement lives in the control layer (not the DB): a
-- "rank accounts by followers + engagement" query is a control-layer
-- concern, computed on a fresh follower/engagement metric that doesn't
-- fit the discrete-enum shape of an i18n table. This migration
-- removes the DB artifacts; the control-layer query is tracked
-- separately and lands in a follow-up plan.
--
-- Drop order (foreign-key safe):
--   1. engagement_tier_labels (child of keys; drop first)
--   2. engagement_tier_keys   (parent)
--   3. accounts.engagement_tier column + FK (rebuild accounts)
--
-- The accounts table rebuild follows the SQLite pattern established
-- in migration 008 (no ALTER TABLE DROP CONSTRAINT support; per
-- https://www.sqlite.org/lang_altertable.html). The CHECK constraints
-- (none on accounts post-migration-008) and backfill partial indexes
-- on bio_en / bio_zh_cn must survive the rebuild.
--
-- The accounts row data is fully copied: every column EXCEPT
-- engagement_tier is preserved. Existing rows had engagement_tier =
-- 'low' / 'medium' / 'high' (the only seeded values) so the drop
-- loses no information operators cared about.
--
-- Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
-- Unit 2 of 9 (R2).
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Drop the i18n label table (child first to avoid FK error)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS engagement_tier_labels;

-- ---------------------------------------------------------------------------
-- 2. Drop the i18n keys table (parent)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS engagement_tier_keys;

-- ---------------------------------------------------------------------------
-- 3. Rebuild accounts without the engagement_tier column + FK
-- ---------------------------------------------------------------------------
CREATE TABLE accounts_new (
    author_id            TEXT PRIMARY KEY,
    handle               TEXT NOT NULL,
    display_name         TEXT,
    bio                  TEXT,
    bio_fetched_at       TEXT,
    verified             INTEGER NOT NULL DEFAULT 0,
    bio_contains_brand   INTEGER NOT NULL DEFAULT 0,
    first_seen_at        TEXT,
    last_seen_at         TEXT,
    source_query_ids     TEXT,
    notes                TEXT,
    bio_en               TEXT,
    bio_zh_cn            TEXT
);

INSERT INTO accounts_new (
    author_id, handle, display_name, bio, bio_fetched_at,
    verified, bio_contains_brand,
    first_seen_at, last_seen_at, source_query_ids, notes,
    bio_en, bio_zh_cn
)
SELECT
    author_id, handle, display_name, bio, bio_fetched_at,
    verified, bio_contains_brand,
    first_seen_at, last_seen_at, source_query_ids, notes,
    bio_en, bio_zh_cn
FROM accounts;

DROP TABLE accounts;

ALTER TABLE accounts_new RENAME TO accounts;

-- Restore backfill partial indexes on the rebuilt accounts table.
CREATE INDEX IF NOT EXISTS idx_accounts_bio_en_backfill
    ON accounts(author_id)
    WHERE bio_en IS NULL;

CREATE INDEX IF NOT EXISTS idx_accounts_bio_zh_cn_backfill
    ON accounts(author_id)
    WHERE bio_zh_cn IS NULL;

COMMIT;
