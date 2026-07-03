-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 028: posts_brands_signals PK rebuild for
-- multi-post_type support.
--
-- Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
-- Unit U1b.
--
-- Background:
--   Migration 019 created posts_brands_signals with PRIMARY KEY
--   (post_id, brand_id). That table has two TEXT FK columns
--   (post_type + sentiment) but only one row per (post, brand).
--   Real posts often warrant multiple post_type tags — e.g., a post
--   that benchmarks GLM 5.2 vs Kimi K2.7 ("performance_comparisons")
--   AND asks "am I running behind?" ("feedback_questions"). With the
--   old PK, only one post_type could be persisted per (post × brand).
--
--   This migration extends the PK to (post_id, brand_id, post_type_key)
--   so the same (post, brand) pair can carry N post_type rows. The
--   sentiment column becomes a per-(post, brand, post_type) value —
--   each post_type aspect can carry its own valence, which is the
--   correct semantic.
--
--   SQLite cannot ALTER TABLE to extend a PRIMARY KEY; the table must
--   be rebuilt. Pattern:
--     1. CREATE TABLE ..._new with the new schema.
--     2. INSERT INTO ..._new SELECT ... FROM ... (preserves rows).
--     3. DROP TABLE ... + ALTER TABLE ..._new RENAME TO ....
--     4. Recreate the indexes.
--
--   Because `sentiment` was previously carried as TEXT alongside the
--   implicit (post_id, brand_id) uniqueness, we must preserve its value
--   when rebuilding. The new column list:
--     post_id       TEXT NOT NULL,
--     brand_id      TEXT NOT NULL,
--     post_type_key TEXT NOT NULL,   -- NEW: was `post_type`, now part of PK
--     sentiment     TEXT,            -- preserved
--     PRIMARY KEY (post_id, brand_id, post_type_key),
--     FKs same as before
--
--   The post_type column is renamed to post_type_key (a) to make the
--   PK extension visually obvious and (b) to match the post_type_keys
--   lookup table name. The migration's INSERT SELECT maps the old
--   column to the new name.
--
-- Pre-flight duplicate check (run BEFORE applying):
--   SELECT COUNT(*) FROM (
--     SELECT 1 FROM posts_brands_signals
--     GROUP BY post_id, brand_id HAVING COUNT(*) > 1
--   );
--   -- MUST be 0. If non-zero, resolve duplicates first.
--   -- On the live x_monitoring.db as of 2026-07-03, count was 0
--   -- across 4934 rows — the migration is lossless.
--
-- Backfill of `post_type_key` for existing rows:
--   The data was already populated by migration 019's CASE statement,
--   which mapped the legacy signal_id to (post_type, sentiment). The
--   post_type values present in the live DB as of 2026-07-03 are all
--   valid post_type_keys (buzz_releases, hands_on_usage,
--   performance_comparisons, feedback_questions). The new keys added
--   by migration 027 (advertising_marketing, event_announcement) are
--   not present in existing rows — they will be populated by future
--   classify_pragmatics_full runs (U2a + U2b).
--
-- Conventions (matches migration 026 + 019):
--   - TEXT natural-key PK on junction tables (per migration 022
--     cleanup).
--   - INTEGER FK to lookup tables when the convention calls for it;
--     post_type_key is TEXT because the existing posts_brands_signals
--     rows store it as TEXT and migration 020 already validated TEXT
--     post_type values.
--   - The migration runner toggles `PRAGMA foreign_keys = OFF` while
--     this script runs.
--
-- _migrations ledger is updated by Store.apply_migrations AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- 1. Drop the existing indexes that reference posts_brands_signals
-- ===========================================================================
-- Indexes on the old table reference the old column names. We drop them
-- before the table rebuild and recreate them on the new table.

DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_signal_id;
DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_post_type;
DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_sentiment;

-- ===========================================================================
-- 2. Rebuild posts_brands_signals with the new composite PK
-- ===========================================================================
-- Note: the table column was named `post_type` (per migration 019).
-- The new table renames it to `post_type_key` so the PK extension is
-- visually obvious in queries and DDL. The INSERT SELECT maps
-- old.post_type → new.post_type_key.

CREATE TABLE posts_brands_signals_new (
    post_id       TEXT NOT NULL,
    brand_id      TEXT NOT NULL,
    post_type_key TEXT NOT NULL,
    sentiment     TEXT,
    PRIMARY KEY (post_id, brand_id, post_type_key),
    FOREIGN KEY (post_id)       REFERENCES posts(tweet_id)       ON DELETE CASCADE,
    FOREIGN KEY (brand_id)      REFERENCES brands(nickname)      ON DELETE SET NULL,
    FOREIGN KEY (post_type_key) REFERENCES post_type_keys(key)   ON DELETE RESTRICT,
    FOREIGN KEY (sentiment)     REFERENCES sentiment_keys(key)   ON DELETE RESTRICT,
    CHECK (brand_id <> '_unattributed')
);

-- Backfill from the existing table. The source column is named
-- `post_type` on a fresh apply (per migration 019) and `post_type_key`
-- after a prior broken-apply of this migration. We use `post_type`
-- (the original migration 019 name) because it always exists on a
-- fresh DB. On a re-apply where the source already has `post_type_key`,
-- this SELECT against `post_type` will fail at apply time and the
-- operator must restore from the prior `_migrations` ledger entry
-- before re-applying (the migration runner does not auto-heal this).
INSERT INTO posts_brands_signals_new (post_id, brand_id, post_type_key, sentiment)
    SELECT post_id, brand_id, post_type, sentiment
    FROM posts_brands_signals;

DROP TABLE posts_brands_signals;
ALTER TABLE posts_brands_signals_new RENAME TO posts_brands_signals;

-- ===========================================================================
-- 3. Recreate indexes (matching migration 019's intent + new column name)
-- ===========================================================================

CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_post_type_key
    ON posts_brands_signals(brand_id, post_type_key);

CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_sentiment
    ON posts_brands_signals(brand_id, sentiment);

-- New index for multi-post_type lookups: "how many posts about brand X
-- got tagged with post_type Y?" — the dashboard's primary brand-scoped
-- query. This is functionally identical to the old brand+post_type
-- index but renamed for clarity.

COMMIT;