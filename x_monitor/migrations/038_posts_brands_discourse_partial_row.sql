-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 038: relax posts_brands_discourse.discourse_key
-- to NULLable so partial rows can persist nationalism pair when the
-- discourse FK fails (KTD5 dead-letter).
--
-- Plan: docs/plans/2026-07-13-002-feat-classifier-signal-coverage-plan.md
-- (Unit U5).
--
-- post_step_touches: posts_brands_discourse
--
-- Background:
--   Today posts_brands_discourse has `discourse_key INTEGER NOT NULL`
--   and `PRIMARY KEY (post_id, brand_id, discourse_key, act_id)`.
--   When the LLM emits a discourse_key value not in the discourse_keys
--   lookup table, the FK insert fails and the entire row is dropped
--   (the KTD5 dead-letter path at store.py:1767-1783). The
--   china_nationalism and us_nationalism columns live on this same
--   row, so any valid nationalism pair from the LLM is lost too.
--
--   The U3 evidence report shows 12 rows per run hit this path
--   (tweets #5/#8/#11/#12 + their duplicates). For each, the LLM
--   emitted a perfectly valid nationalism pair that we threw away.
--
-- Why this migration exists:
--   Allow `discourse_key` to be NULL so the partial-row write path
--   can persist `(post_id, brand_id, discourse_key=NULL, act_id,
--   china_nationalism, us_nationalism)` when the discourse FK
--   fails. The PRIMARY KEY still includes discourse_key, so two
--   partial rows for the same (post_id, brand_id) would collide on
--   the NULL; we handle that with a sentinel `act_id` — partial
--   rows use act_id=0 (the "KTD5 partial" sentinel; legitimate
--   act_ids are 1..99 per the existing CHECK constraint, which we
--   relax to 0..99).
--
-- Why this is safe:
--   - `discourse_keys` is unchanged (still intentionally tight; KTD5).
--   - Existing rows have non-NULL discourse_key, so the relaxed
--     constraint is backwards-compatible.
--   - The KTD5 dead-letter path still emits the failed
--     discourse_key to data/runs/.../enum_dead_letter.jsonl for
--     human review (the partial-row write runs ALONGSIDE the
--     dead-letter emit, not in place of it).

-- 1. Drop NOT NULL on discourse_key (nullable now).
-- 2. Relax act_id CHECK from 1..99 to 0..99 (0 = KTD5 partial-row
--    sentinel; legitimate act_ids are 1..99).
-- 3. SQLite does not support DROP CONSTRAINT cleanly; the CHECK
--    clause has to be re-declared via table recreation. Do the
--    rename-rebuild dance.

PRAGMA foreign_keys = OFF;
BEGIN;

-- Step 1: rebuild posts_brands_discourse with relaxed constraints.
CREATE TABLE posts_brands_discourse_new (
    post_id            INTEGER NOT NULL,
    brand_id           INTEGER NOT NULL,
    discourse_key      INTEGER,
    act_id             INTEGER NOT NULL,
    china_nationalism  INTEGER,
    us_nationalism     INTEGER,
    PRIMARY KEY (post_id, brand_id, discourse_key, act_id),
    FOREIGN KEY (post_id)           REFERENCES posts(id)              ON DELETE CASCADE,
    FOREIGN KEY (brand_id)          REFERENCES brands(id)             ON DELETE SET NULL,
    FOREIGN KEY (discourse_key)     REFERENCES discourse_keys(id)     ON DELETE RESTRICT,
    FOREIGN KEY (china_nationalism) REFERENCES nationalism_keys(id)   ON DELETE RESTRICT,
    FOREIGN KEY (us_nationalism)    REFERENCES nationalism_keys(id)   ON DELETE RESTRICT,
    CHECK (act_id BETWEEN 0 AND 99)
);

INSERT INTO posts_brands_discourse_new
    SELECT post_id, brand_id, discourse_key, act_id,
           china_nationalism, us_nationalism
    FROM posts_brands_discourse;

DROP TABLE posts_brands_discourse;
ALTER TABLE posts_brands_discourse_new RENAME TO posts_brands_discourse;

-- Step 2: recreate the indexes that the rebuild dropped.
CREATE INDEX idx_post_brand_dis_b_dr
    ON posts_brands_discourse(brand_id, discourse_key);
CREATE INDEX idx_post_brand_dis_b_cn_nat
    ON posts_brands_discourse(brand_id, china_nationalism);
CREATE INDEX idx_post_brand_dis_b_us_nat
    ON posts_brands_discourse(brand_id, us_nationalism);

COMMIT;
PRAGMA foreign_keys = ON;