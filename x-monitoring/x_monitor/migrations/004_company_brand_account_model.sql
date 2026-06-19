-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 004: company / brand / account / mention model.
--
-- Refactor the schema to reflect the actual domain:
--   companies (corporate parents)
--     1:N brand_companies        M:N edge
--   brands (canonical registry; replaces KNOWN_MODELS frozenset for DB reads)
--     1:N brand_accounts         M:N edge between brands and accounts
--     1:N company_accounts       M:N edge between companies and accounts
--     1:N brand_hashtags         detection registry (R6a)
--     1:N brand_keywords         detection registry (R6b)
--     1:N brand_search_terms     detection registry (R6c)
--   accounts (per-handle; author_id PK)
--     1:N account_post_appearances   (author_id, tweet_id) PK
--   posts (tweet_id PK; no brand column)
--     1:N post_brands            (brand_id, post_id) PK with fractional weight
--     1:N post_mentions          (post_id, brand_id, source) PK, 4 sources
--     1:N post_brand_signals     (post_id, brand_id) PK, per-brand signal
--
-- Plan: docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md
--       (mirror at /tmp/plan-out/2026-06-18-195234-refactor-company-brand-account-model-plan.md)
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.
--
-- Operator prerequisites (NOT included in this SQL; lives in the deploy
-- runbook per the plan's Key Technical Decisions):
--   1. Stop the pipeline worker (launchctl unload).
--   2. Stop the dashboard (lsof -nP -iTCP:5000 -sTCP:LISTEN -t | xargs kill).
--   3. Atomic backup of data/x_monitoring.db with sha256.
--   4. Dryrun on /tmp/x_monitoring.dryrun.db first; only proceed after
--      all post-deploy verification queries pass.

BEGIN;

-- ===========================================================================
-- 1. Companies (corporate parents) and brands (canonical registry)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS companies (
    company_id    TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    hq_country    TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS brands (
    brand_id      TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    accent_color  TEXT NOT NULL DEFAULT '#9ca3af',
    is_sentinel   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

-- M:N edge between brands and companies (Decision 2).
CREATE TABLE IF NOT EXISTS brand_companies (
    brand_id       TEXT NOT NULL,
    company_id     TEXT NOT NULL,
    ownership_pct  REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (brand_id, company_id),
    FOREIGN KEY (brand_id)   REFERENCES brands(brand_id)    ON DELETE CASCADE,
    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
);

-- M:N edge between brands and accounts (Decision 2, Decision 10).
CREATE TABLE IF NOT EXISTS brand_accounts (
    brand_id   TEXT NOT NULL,
    author_id  TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'community',
    added_at   TEXT NOT NULL,
    PRIMARY KEY (brand_id, author_id),
    FOREIGN KEY (brand_id)  REFERENCES brands(brand_id)    ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES accounts(author_id) ON DELETE CASCADE
);

-- M:N edge between companies and accounts.
CREATE TABLE IF NOT EXISTS company_accounts (
    company_id  TEXT NOT NULL,
    author_id   TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'community',
    added_at    TEXT NOT NULL,
    PRIMARY KEY (company_id, author_id),
    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
    FOREIGN KEY (author_id)  REFERENCES accounts(author_id)   ON DELETE CASCADE
);

-- ===========================================================================
-- 2. Post-level attribution tables (R5, R6, R6d)
-- ===========================================================================

-- Multi-brand attribution with fractional weights (Decision 9, Option C).
-- weight = 1.0 / N for a post naming N distinct brands. Single-brand posts
-- get weight = 1.0. Unattributed posts get a sentinel row (brand_id =
-- '_unattributed', weight = 1.0; filtered out by is_sentinel at query time).
CREATE TABLE IF NOT EXISTS post_brands (
    brand_id  TEXT NOT NULL,
    post_id   TEXT NOT NULL,
    weight    REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (brand_id, post_id),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE SET NULL,
    FOREIGN KEY (post_id)  REFERENCES posts(tweet_id)  ON DELETE CASCADE
);

-- Per-mention provenance: how was each brand named on each post?
-- The PK (post_id, brand_id, source) preserves the 4-source decomposition
-- (user_mention, hashtag, body_keyword, search_term). Same brand named via
-- 3 sources produces 3 rows. The dedup key for polarity weight is
-- (post_id, brand_id), enforced on post_brands.
CREATE TABLE IF NOT EXISTS post_mentions (
    post_id       TEXT NOT NULL,
    brand_id      TEXT,                          -- nullable for un-attributed mentions
    source        TEXT NOT NULL,                 -- user_mention | hashtag | body_keyword | search_term
    raw_token     TEXT NOT NULL,                 -- literal matched text: "@MiniMaxAI", "#minimax", "M3.0", "from:minimax OR ..."
    mentioned_at  TEXT NOT NULL,                 -- posts.created_at (ISO-8601 UTC)
    PRIMARY KEY (post_id, brand_id, source),
    FOREIGN KEY (post_id)  REFERENCES posts(tweet_id)   ON DELETE CASCADE,
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id)  ON DELETE SET NULL
);

-- Per-brand signal classification (R6d, Decision 18). Replaces the
-- post-level posts.signal column. A post naming 2 brands with different
-- sentiments writes 2 rows. CHECK constraint excludes the sentinel
-- (Decision 15): _unattributed rows have no meaningful per-brand signal.
CREATE TABLE IF NOT EXISTS post_brand_signals (
    post_id   TEXT NOT NULL,
    brand_id  TEXT NOT NULL,
    signal    TEXT NOT NULL,                     -- release | community_question | criticism | commenter_capture | praise | other
    PRIMARY KEY (post_id, brand_id),
    FOREIGN KEY (post_id)  REFERENCES posts(tweet_id)   ON DELETE CASCADE,
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id)  ON DELETE SET NULL,
    CHECK (brand_id <> '_unattributed')
);

-- ===========================================================================
-- 3. Detection-registry tables (R6a, R6b, R6c)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS brand_hashtags (
    brand_id  TEXT NOT NULL,
    tag       TEXT NOT NULL,                     -- lowercase, no '#' prefix
    added_at  TEXT NOT NULL,
    PRIMARY KEY (brand_id, tag),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS brand_keywords (
    brand_id  TEXT NOT NULL,
    pattern   TEXT NOT NULL,
    is_regex  INTEGER NOT NULL DEFAULT 0,
    added_at  TEXT NOT NULL,
    PRIMARY KEY (brand_id, pattern),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS brand_search_terms (
    brand_id  TEXT NOT NULL,
    term      TEXT NOT NULL,
    added_at  TEXT NOT NULL,
    PRIMARY KEY (brand_id, term),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
);

-- Search-query registry (R6c storage fork). Replaces the soft pointer from
-- posts.source_query_id to data/queries/<id>.json. ON DELETE SET NULL on
-- the FK from posts.source_query_id preserves posts when a query is
-- dropped; the application backfills search_queries before applying the FK.
CREATE TABLE IF NOT EXISTS search_queries (
    query_id           TEXT PRIMARY KEY,
    brand_id           TEXT NOT NULL,
    keywords_json      TEXT NOT NULL,
    plan_calls_run_id  TEXT,
    created_at         TEXT NOT NULL,
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
);

-- ===========================================================================
-- 4. Seed brands from KNOWN_MODELS + MODEL_DISPLAY_NAMES + MODEL_ACCENT_COLORS.
--    `_unattributed` is seeded with is_sentinel = 1 so the treemap and grid
--    filter it out (Decision 15, P0 review fix).
-- ===========================================================================

INSERT INTO brands (brand_id, display_name, accent_color, is_sentinel, created_at) VALUES
    ('minimax',         'MiniMax AI',       '#3b82f6', 0, '2026-06-19T00:00:00+00:00'),
    ('qwen',            'Qwen',             '#f97316', 0, '2026-06-19T00:00:00+00:00'),
    ('deepseek',        'DeepSeek',         '#10b981', 0, '2026-06-19T00:00:00+00:00'),
    ('glm',             'Zhipu GLM',        '#a855f7', 0, '2026-06-19T00:00:00+00:00'),
    ('xiaomi_mimo',     'Xiaomi MiMo',      '#eab308', 0, '2026-06-19T00:00:00+00:00'),
    ('moonshot_kimi',   'Moonshot Kimi',    '#ec4899', 0, '2026-06-19T00:00:00+00:00'),
    ('inclusionai',     'InclusionAI',      '#06b6d4', 0, '2026-06-19T00:00:00+00:00'),
    ('mistral',         'Mistral',          '#facc15', 0, '2026-06-19T00:00:00+00:00'),
    ('stepfun',         'StepFun',          '#22c55e', 0, '2026-06-19T00:00:00+00:00'),
    ('ernie',           'Baidu ERNIE',      '#0ea5e9', 0, '2026-06-19T00:00:00+00:00'),
    ('hunyuan',         'Tencent Hunyuan',  '#ec4899', 0, '2026-06-19T00:00:00+00:00'),
    ('_unattributed',   'Unattributed',     '#6b7280', 1, '2026-06-19T00:00:00+00:00');

-- ===========================================================================
-- 5. Seed companies (6-8 known parents + 4-5 standalones) and brand_companies
-- ===========================================================================

INSERT INTO companies (company_id, display_name, hq_country, created_at) VALUES
    ('alibaba',     'Alibaba',           'CN', '2026-06-19T00:00:00+00:00'),
    ('baidu',       'Baidu',             'CN', '2026-06-19T00:00:00+00:00'),
    ('tencent',     'Tencent',           'CN', '2026-06-19T00:00:00+00:00'),
    ('moonshot',    'Moonshot AI',       'CN', '2026-06-19T00:00:00+00:00'),
    ('zhipu',       'Zhipu AI',          'CN', '2026-06-19T00:00:00+00:00'),
    ('stepfun_inc', 'StepFun Inc',       'CN', '2026-06-19T00:00:00+00:00'),
    ('xiaomi',      'Xiaomi',            'CN', '2026-06-19T00:00:00+00:00'),
    ('mistral_ai',  'Mistral AI',        'FR', '2026-06-19T00:00:00+00:00'),
    ('inclusion_ai','Inclusion AI',      'CN', '2026-06-19T00:00:00+00:00'),
    ('deepseek_co', 'DeepSeek',          'CN', '2026-06-19T00:00:00+00:00');

INSERT INTO brand_companies (brand_id, company_id, ownership_pct) VALUES
    ('qwen',          'alibaba',       1.0),
    ('ernie',         'baidu',         1.0),
    ('hunyuan',       'tencent',       1.0),
    ('moonshot_kimi', 'moonshot',      1.0),
    ('glm',           'zhipu',         1.0),
    ('stepfun',       'stepfun_inc',   1.0),
    ('xiaomi_mimo',   'xiaomi',        1.0),
    ('mistral',       'mistral_ai',    1.0),
    ('inclusionai',   'inclusion_ai',  1.0),
    ('deepseek',      'deepseek_co',   1.0);

-- ===========================================================================
-- 6. Backfill post_brand_signals from old posts.signal + posts.model_id.
--    MUST run BEFORE the DROP COLUMN statements in step 8 — the SELECT
--    references p.model_id and p.signal which step 8 drops (P0 review fix).
-- ===========================================================================

INSERT INTO post_brand_signals (post_id, brand_id, signal)
    SELECT p.tweet_id, p.model_id, p.signal
    FROM posts p
    WHERE p.model_id IS NOT NULL AND p.signal IS NOT NULL;

-- ===========================================================================
-- 7. Backfill lang_detected from existing text_en / text_zh_cn rows so
--    already-translated posts are correctly excluded from the new backfill
--    indexes (Decision 8, P0 review fix). Posts with text_en populated have
--    been translated; their lang_detected must reflect that.
-- ===========================================================================

UPDATE posts SET lang_detected = 'en'
    WHERE text_en IS NOT NULL AND lang_detected IS NULL;

UPDATE posts SET lang_detected = 'zh-CN'
    WHERE text_zh_cn IS NOT NULL AND lang_detected IS NULL;

-- 'und' (BCP-47 undetermined) is treated as eligible for both translations;
-- do not backfill it here (P1 review fix #30).

-- ===========================================================================
-- 8. Drop indexes + columns that reference the old posts shape.
--    Both idx_posts_model_created AND idx_posts_signal_model must be dropped
--    BEFORE the column drops (P1 review fix; original outline missed the
--    second DROP INDEX).
-- ===========================================================================

DROP INDEX IF EXISTS idx_posts_model_created;
DROP INDEX IF EXISTS idx_posts_signal_model;

-- Rename posts.favorite_count to posts.like_count (R9, Decision 3).
-- DROP posts.model_id (R1, Decision 1: posts loses its brand column entirely;
--   attribution moves to post_brands).
-- DROP posts.signal (R6d: signal moves to post_brand_signals).
ALTER TABLE posts RENAME COLUMN favorite_count TO like_count;
ALTER TABLE posts DROP COLUMN model_id;
ALTER TABLE posts DROP COLUMN signal;

-- Drop the old translation backfill indexes; step 13 recreates with the
-- new predicates (Decision 8).
DROP INDEX IF EXISTS idx_posts_text_en_null;
DROP INDEX IF EXISTS idx_posts_text_zh_cn_null;

-- ===========================================================================
-- 9. Drop + recreate account_post_appearances with (author_id, tweet_id) PK
--    (Decision 4: accounts.author_id is the immutable X user id).
-- ===========================================================================

DROP TABLE IF EXISTS account_post_appearances;

CREATE TABLE account_post_appearances (
    author_id    TEXT NOT NULL,
    tweet_id     TEXT NOT NULL,
    role_at_time TEXT,
    PRIMARY KEY (author_id, tweet_id),
    FOREIGN KEY (tweet_id) REFERENCES posts(tweet_id) ON DELETE CASCADE
);

-- ===========================================================================
-- 10. Drop + recreate accounts with author_id PK.
--     Per Decision 10 / P1 review fix #15: the per-account role is dropped
--     because multi-brand accounts make per-account role meaningless; the
--     per-brand role lives in brand_accounts.role. Per R13: bio +
--     bio_fetched_at are added. Per R12: multi_brand_voice is dropped.
--     Per Decision 2: model_id is dropped; brand/account edge is in
--     brand_accounts now.
-- ===========================================================================

DROP TABLE IF EXISTS accounts;

CREATE TABLE accounts (
    author_id            TEXT PRIMARY KEY,
    handle               TEXT NOT NULL,
    display_name         TEXT,
    bio                  TEXT,
    bio_fetched_at       TEXT,
    verified             INTEGER NOT NULL DEFAULT 0,
    bio_contains_brand   INTEGER NOT NULL DEFAULT 0,
    engagement_tier      TEXT NOT NULL DEFAULT 'low',
    first_seen_at        TEXT,
    last_seen_at         TEXT,
    source_query_ids     TEXT,
    notes                TEXT
);

-- ===========================================================================
-- 11. Backfill accounts from posts.author_id.
--     For every distinct (author_id, author_handle) pair, write one accounts
--     row. Posts with NULL author_id are filtered out (logged by the
--     migration loader to data/runs/<ts>/degraded_accounts.json).
--     MUST run BEFORE the brand_accounts / company_accounts INSERTs in
--     step 12 so the FK from brand_accounts.author_id to accounts.author_id
--     can resolve (P0 review fix).
-- ===========================================================================

INSERT INTO accounts (author_id, handle, display_name, verified,
                      bio_contains_brand, engagement_tier,
                      first_seen_at, last_seen_at)
    SELECT author_id, author_handle, NULL, 0, 0, 'low',
           MIN(created_at), MAX(created_at)
    FROM posts
    WHERE author_id IS NOT NULL
    GROUP BY author_id, author_handle;

-- ===========================================================================
-- 12. company_accounts is empty by design (Scope Boundaries: "No new
--     analytics"). The application populates it on the first account_graph
--     pass that joins accounts -> brand_accounts -> brand_companies.
--     brand_accounts is seeded by the application from
--     data/brands/<brand>/accounts.yaml at first run (the migration loader
--     also seeds best-effort, but the application is authoritative).
-- ===========================================================================

-- ===========================================================================
-- 13. Re-create translation backfill indexes with the new predicates.
--     Includes 'und' in both negative-lists (P1 review fix #30): X returns
--     'und' for very short posts; treat as eligible for both translations.
-- ===========================================================================

CREATE INDEX IF NOT EXISTS idx_posts_text_en_backfill
    ON posts(tweet_id)
    WHERE text_en IS NULL
      AND lang_detected IS NOT NULL
      AND lang_detected NOT IN ('en', 'en-US', 'en-GB', 'und');

CREATE INDEX IF NOT EXISTS idx_posts_text_zh_cn_backfill
    ON posts(tweet_id)
    WHERE text_zh_cn IS NULL
      AND lang_detected IS NOT NULL
      AND lang_detected NOT IN ('zh', 'zh-CN', 'zh-Hans', 'zh-Hant', 'und');

-- ===========================================================================
-- 14. Add the post_brands + post_mentions + post_brand_signals indexes.
--     - post_brands (brand_id): single-column index for per-brand scans.
--     - post_brands (brand_id, post_id): supports the polarity JOIN
--       (Decision 18, no IN subquery).
--     - post_mentions (brand_id, source, mentioned_at DESC): source-breakdown
--       card; mentions card sorted by recency.
--     - post_mentions (post_id): per-post mention lookup.
--     - post_brand_signals (brand_id, signal): per-brand polarity aggregation
--       (Appendix A summary promised this; P1 review fix).
--     - post_brand_signals (post_id): per-post signal lookup.
-- ===========================================================================

CREATE INDEX IF NOT EXISTS idx_post_brands_brand
    ON post_brands(brand_id);

CREATE INDEX IF NOT EXISTS idx_post_brands_brand_post
    ON post_brands(brand_id, post_id);

CREATE INDEX IF NOT EXISTS idx_post_mentions_brand_source_recent
    ON post_mentions(brand_id, source, mentioned_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_mentions_post
    ON post_mentions(post_id);

CREATE INDEX IF NOT EXISTS idx_post_brand_signals_brand_signal
    ON post_brand_signals(brand_id, signal);

CREATE INDEX IF NOT EXISTS idx_post_brand_signals_post
    ON post_brand_signals(post_id);

COMMIT;
