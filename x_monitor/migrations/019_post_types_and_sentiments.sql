-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 019: post_types + sentiments taxonomy.
--
-- Plan: docs/plans/2026-06-24-163000-replace-legacy-signals-with-post-types-and-sentiments.md
-- Unit 9 of 9.
--
-- The legacy 6-signal taxonomy (release, community_question, criticism,
-- commenter_capture, praise, other) bundled post TYPE and SENTIMENT
-- into one enum. This migration introduces the cleaner separation:
--
--   post_type_keys (4)  -- what KIND of post it is
--     buzz_releases, hands_on_usage, performance_comparisons,
--     feedback_questions
--   sentiment_keys (4)  -- the VALENCE of the post
--     positive, negative, neutral, mixed
--
-- Scope (the deliberately minimal version):
--   1. CREATE new post_type_keys + post_type_labels tables (INTEGER id
--      PK + UNIQUE key, mirroring the post-U8 convention; signals and
--      roles got this treatment in migration 018).
--   2. CREATE new sentiment_keys + sentiment_labels tables (same shape).
--   3. ADD two new nullable TEXT columns to posts_brands_signals:
--      post_type + sentiment. Both are FK-validated against their
--      respective *_keys tables (ON DELETE RESTRICT). The existing
--      signal_id column is LEFT IN PLACE — backward-compat with the
--      Store API and all consumers (treemap, dashboard, etc.).
--   4. Backfill post_type + sentiment for existing rows from the
--      legacy signal_id using a documented heuristic mapping.
--   5. Add indexes covering the new columns.
--
-- Out of scope (deliberately deferred to follow-up migrations):
--   - Drop signal_id column from posts_brands_signals (requires
--     updating all consumers: treemap, dashboard, run.py, classifier).
--   - Drop signal_keys + signal_labels tables (same reason).
--   - Reclassify existing rows via the LLM (the backfill is a static
--     mapping; a future migration can re-run with the LLM classifier
--     for higher fidelity).
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- 1. post_type_keys + post_type_labels (INTEGER id PK, UNIQUE key)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS post_type_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

INSERT OR IGNORE INTO post_type_keys (key, created_at)
    VALUES
        ('buzz_releases',           '2026-06-24T00:00:00+00:00'),
        ('hands_on_usage',          '2026-06-24T00:00:00+00:00'),
        ('performance_comparisons', '2026-06-24T00:00:00+00:00'),
        ('feedback_questions',      '2026-06-24T00:00:00+00:00');

CREATE TABLE IF NOT EXISTS post_type_labels (
    key     TEXT NOT NULL,
    lang    TEXT NOT NULL,
    label   TEXT NOT NULL,
    PRIMARY KEY (key, lang),
    FOREIGN KEY (key) REFERENCES post_type_keys(key) ON DELETE CASCADE
);

INSERT OR IGNORE INTO post_type_labels (key, lang, label) VALUES
    ('buzz_releases',           'en',    'Buzz & Releases'),
    ('buzz_releases',           'zh_cn', '发布与热度'),
    ('hands_on_usage',          'en',    'Hands-on Usage'),
    ('hands_on_usage',          'zh_cn', '实际使用体验'),
    ('performance_comparisons', 'en',    'Performance & Comparisons'),
    ('performance_comparisons', 'zh_cn', '性能与对比'),
    ('feedback_questions',      'en',    'Feedback & Questions'),
    ('feedback_questions',      'zh_cn', '问题与建议');

-- ===========================================================================
-- 2. sentiment_keys + sentiment_labels (same shape)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS sentiment_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

INSERT OR IGNORE INTO sentiment_keys (key, created_at)
    VALUES
        ('positive', '2026-06-24T00:00:00+00:00'),
        ('negative', '2026-06-24T00:00:00+00:00'),
        ('neutral',  '2026-06-24T00:00:00+00:00'),
        ('mixed',    '2026-06-24T00:00:00+00:00');

CREATE TABLE IF NOT EXISTS sentiment_labels (
    key     TEXT NOT NULL,
    lang    TEXT NOT NULL,
    label   TEXT NOT NULL,
    PRIMARY KEY (key, lang),
    FOREIGN KEY (key) REFERENCES sentiment_keys(key) ON DELETE CASCADE
);

INSERT OR IGNORE INTO sentiment_labels (key, lang, label) VALUES
    ('positive', 'en',    'Positive'),
    ('positive', 'zh_cn', '正面'),
    ('negative', 'en',    'Negative'),
    ('negative', 'zh_cn', '负面'),
    ('neutral',  'en',    'Neutral'),
    ('neutral',  'zh_cn', '中性'),
    ('mixed',    'en',    'Mixed'),
    ('mixed',    'zh_cn', '混合');

-- ===========================================================================
-- 3. Add post_type + sentiment columns to posts_brands_signals
-- ===========================================================================

DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_signal_id;

CREATE TABLE posts_brands_signals_new (
    post_id    TEXT NOT NULL,
    brand_id   TEXT NOT NULL,
    signal_id  TEXT,                         -- legacy; nullable for new rows
    post_type  TEXT,                         -- FK → post_type_keys.key
    sentiment  TEXT,                         -- FK → sentiment_keys.key
    PRIMARY KEY (post_id, brand_id),
    FOREIGN KEY (post_id)   REFERENCES posts(tweet_id)           ON DELETE CASCADE,
    FOREIGN KEY (brand_id)  REFERENCES brands(brand_id)          ON DELETE SET NULL,
    FOREIGN KEY (signal_id) REFERENCES signals(key)              ON DELETE RESTRICT,
    FOREIGN KEY (post_type) REFERENCES post_type_keys(key)       ON DELETE RESTRICT,
    FOREIGN KEY (sentiment) REFERENCES sentiment_keys(key)       ON DELETE RESTRICT,
    CHECK (brand_id <> '_unattributed')
);

INSERT INTO posts_brands_signals_new (post_id, brand_id, signal_id)
    SELECT post_id, brand_id, signal_id
    FROM posts_brands_signals;

DROP TABLE posts_brands_signals;
ALTER TABLE posts_brands_signals_new RENAME TO posts_brands_signals;

-- ===========================================================================
-- 4. Backfill: heuristic signal_id → (post_type, sentiment) mapping
-- ===========================================================================

-- The mapping is the canonical translation from the legacy 6-bucket
-- taxonomy to the new post_type × sentiment decomposition. The
-- classifier pipeline (a follow-up unit) will reclassify rows with the
-- LLM once this column scaffolding is in place; this backfill only
-- applies to rows that existed pre-migration 019.
UPDATE posts_brands_signals SET
    post_type = CASE signal_id
        WHEN 'release'             THEN 'buzz_releases'
        WHEN 'praise'              THEN 'buzz_releases'
        WHEN 'commenter_capture'   THEN 'hands_on_usage'
        WHEN 'community_question'  THEN 'feedback_questions'
        WHEN 'criticism'           THEN 'feedback_questions'
        WHEN 'other'               THEN 'hands_on_usage'
        ELSE 'hands_on_usage'  -- defensive fallback
    END,
    sentiment = CASE signal_id
        WHEN 'praise'              THEN 'positive'
        WHEN 'criticism'           THEN 'negative'
        WHEN 'community_question'  THEN 'neutral'
        WHEN 'release'             THEN 'neutral'
        WHEN 'commenter_capture'   THEN 'neutral'
        WHEN 'other'               THEN 'neutral'
        ELSE 'neutral'  -- defensive fallback
    END
WHERE post_type IS NULL OR sentiment IS NULL;

-- ===========================================================================
-- 5. Indexes (covering the new columns + the rebuilt brand_id+signal_id)
-- ===========================================================================

CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_signal_id
    ON posts_brands_signals(brand_id, signal_id);

CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_post_type
    ON posts_brands_signals(brand_id, post_type);

CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_sentiment
    ON posts_brands_signals(brand_id, sentiment);

COMMIT;
