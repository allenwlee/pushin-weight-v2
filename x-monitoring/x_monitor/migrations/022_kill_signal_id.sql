-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 022: kill the legacy 6-signal taxonomy.
--
-- Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
-- Unit 9 of 9 (remediation).
--
-- Migration 019 introduced post_type_keys + sentiment_keys as ADDITIVE
-- columns alongside the legacy signal_id (unauthorized narrowing by the
-- implementing agent at commit 4cd62d2 — flagged by the user on
-- 2026-06-25). This migration completes the unit as the plan body
-- originally required: REPLACE, not augment.
--
-- What this migration does:
--   1. Backfill any posts_brands_signals rows that still have NULL
--      post_type or sentiment (defensive — 019's backfill should have
--      covered everything, but a row could slip through if signal_id
--      was NULL).
--   2. Rebuild posts_brands_signals without signal_id; promote
--      post_type and sentiment to NOT NULL with FK to the new *_keys
--      tables.
--   3. Drop the now-unused indexes that referenced signal_id.
--   4. Drop the legacy signals + signal_labels tables.
--
-- The taxonomy shift from 6 buckets to (post_type × sentiment) is a
-- complete replacement: every read of signal_id, every join to signals,
-- every reference to the 6 signal keys (release, community_question,
-- criticism, commenter_capture, praise, other) is removed from the
-- schema and from x_monitor/ consumer code (see commits that land
-- alongside this migration).
--
-- Out of scope (kept intentionally):
--   - The LLM classifier prompt rewrite in attribution.py::build_signal_prompt
--     to ask for (post_type, sentiment) instead of the 6-signal
--     vocabulary — that's a code change, not a schema change.
--   - Reclassifying existing rows with the LLM (the backfill in 019 used
--     a static mapping; a future migration can re-run with the LLM
--     classifier for higher fidelity).
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- 1. Defensive backfill: any row missing post_type or sentiment gets
--    'hands_on_usage' / 'neutral' (the 019 fallback values for NULL
--    signal_id). Should be a no-op on a healthy DB.
-- ===========================================================================

UPDATE posts_brands_signals
SET post_type = 'hands_on_usage'
WHERE post_type IS NULL;

UPDATE posts_brands_signals
SET sentiment = 'neutral'
WHERE sentiment IS NULL;

-- ===========================================================================
-- 2. Rebuild posts_brands_signals: drop signal_id; promote post_type +
--    sentiment to NOT NULL with INTEGER FKs to the new *_keys tables.
-- ===========================================================================

CREATE TABLE posts_brands_signals_new (
    post_id    INTEGER NOT NULL,
    brand_id   INTEGER NOT NULL,
    post_type  INTEGER NOT NULL,
    sentiment  INTEGER NOT NULL,
    PRIMARY KEY (post_id, brand_id),
    FOREIGN KEY (post_id)   REFERENCES posts(id)            ON DELETE CASCADE,
    FOREIGN KEY (brand_id)  REFERENCES brands(id)           ON DELETE SET NULL,
    FOREIGN KEY (post_type) REFERENCES post_type_keys(id)   ON DELETE RESTRICT,
    FOREIGN KEY (sentiment) REFERENCES sentiment_keys(id)   ON DELETE RESTRICT
);

INSERT INTO posts_brands_signals_new (post_id, brand_id, post_type, sentiment)
    SELECT pbs.post_id, pbs.brand_id, pt.id, se.id
    FROM posts_brands_signals pbs
    JOIN post_type_keys pt ON pt.id = pbs.post_type
    JOIN sentiment_keys se ON se.id = pbs.sentiment;

-- Drop the old indexes that reference signal_id, then drop the table.
DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_signal_id;
DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_post_type;
DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_sentiment;
DROP TABLE posts_brands_signals;
ALTER TABLE posts_brands_signals_new RENAME TO posts_brands_signals;

-- Recreate the indexes that survived the kill (no signal_id index).
CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_post_type
    ON posts_brands_signals(brand_id, post_type);
CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_sentiment
    ON posts_brands_signals(brand_id, sentiment);

-- ===========================================================================
-- 3. Drop the legacy signals + signal_labels tables.
--    (U4 renamed signal_keys → signals; this completes the kill.)
-- ===========================================================================

DROP TABLE IF EXISTS signal_labels;
DROP TABLE IF EXISTS signals;

COMMIT;