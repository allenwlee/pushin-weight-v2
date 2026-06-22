-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 009: HuggingFace products catalog + brand→HF-org mapping.
--
-- Originally written as migration 005 on a fresh-from-main branch; renumbered
-- to 009 at rebase time (2026-06-23) because main had just received migrations
-- 005_quoted_text.sql + 006_quote_capture_tracking.sql (quote-tweets branch) and
-- 007_i18n_locale_columns.sql + 008_enum_i18n_lookup_tables.sql (i18n branch).
--
-- Adds two additive tables (no existing data is touched):
--   brand_hf_orgs  M:N edge between brands and their HuggingFace orgs/usernames.
--                  `confirmed` = 1 for curated/operator-confirmed orgs (scraped);
--                  `confirmed` = 0 for runtime-discovered candidates (flagged for
--                  review, NOT scraped until promoted).
--   products       one row per HF model. brands 1:N products.
--                  wide scalar columns + JSON columns + a verbatim raw_json
--                  payload so columns can be added later without re-scraping.
--
-- Plan: docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md
--
-- _migrations ledger is updated by Store._apply_migration AFTER this script's
-- COMMIT. Do NOT add an INSERT INTO _migrations here.
--
-- Forward-only and idempotent: CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE.

BEGIN;

-- ===========================================================================
-- 1. brand_hf_orgs — M:N edge brands ↔ HuggingFace orgs/usernames.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS brand_hf_orgs (
    brand_id        TEXT NOT NULL,
    hf_org          TEXT NOT NULL,                  -- HF namespace, e.g. "deepseek-ai"
    is_primary      INTEGER NOT NULL DEFAULT 0,     -- 1 = primary org for the brand
    confirmed       INTEGER NOT NULL DEFAULT 0,     -- 1 = curated/confirmed (scraped); 0 = discovered candidate (review)
    discovered_via  TEXT NOT NULL DEFAULT 'curated',-- 'curated' | 'search:<query>'
    added_at        TEXT NOT NULL,
    PRIMARY KEY (brand_id, hf_org),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_brand_hf_orgs_brand
    ON brand_hf_orgs(brand_id);

-- ===========================================================================
-- 2. products — one row per HuggingFace model (brands 1:N products).
-- ===========================================================================

CREATE TABLE IF NOT EXISTS products (
    repo_id            TEXT PRIMARY KEY,             -- HF model id, e.g. "deepseek-ai/DeepSeek-V3"
    brand_id           TEXT,                         -- FK brands.brand_id (nullable: SET NULL on brand delete)
    hf_org             TEXT NOT NULL,                -- authoring namespace, e.g. "deepseek-ai"
    hf_type            TEXT NOT NULL DEFAULT 'model'
                         CHECK (hf_type IN ('model','dataset','space')),
    display_name       TEXT,                         -- repo name part (after the '/')
    author             TEXT,
    sha                TEXT,
    private            INTEGER,                      -- 0/1
    gated              TEXT,                         -- 'auto' | 'manual' | 'false' | NULL
    disabled           INTEGER,                      -- 0/1
    pipeline_tag       TEXT,
    library_name       TEXT,
    downloads          INTEGER,                      -- 30-day
    downloads_all_time INTEGER,
    download_velocity  REAL,                         -- downloads_per_day
    likes              INTEGER,
    trending_score     REAL,
    paperswithcode_id  TEXT,
    created_at         TEXT,                         -- HF ISO-8601
    last_modified      TEXT,                         -- HF ISO-8601
    tags_json          TEXT,                         -- JSON array
    siblings_json      TEXT,                         -- JSON array of {rfilename[, size]}
    card_data_json     TEXT,                         -- JSON: license/language/base_model/…
    config_json        TEXT,                         -- JSON: architectures/model_type
    spaces_json        TEXT,                         -- JSON array of dependent spaces
    raw_json           TEXT,                         -- full ModelInfo payload (never lose data)
    collected_at       TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_products_brand
    ON products(brand_id);

CREATE INDEX IF NOT EXISTS idx_products_hf_org
    ON products(hf_org);

-- ===========================================================================
-- 3. Seed curated brand→HF-org mapping (confirmed=1, is_primary=1).
--    Operator-verifiable defaults; the Unit-3 sanity gate validates each org on
--    first run and a wrong guess fails loudly (not silently).
-- ===========================================================================

INSERT OR IGNORE INTO brand_hf_orgs (brand_id, hf_org, is_primary, confirmed, discovered_via, added_at) VALUES
    ('minimax',       'MiniMaxAI',    1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('qwen',          'Qwen',         1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('deepseek',      'deepseek-ai',  1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('glm',           'THUDM',        1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('xiaomi_mimo',   'XiaomiMiMo',   1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('moonshot_kimi', 'moonshotai',   1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('inclusionai',   'inclusionAI',  1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('mistral',       'mistralai',    1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('stepfun',       'stepfun-ai',   1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('ernie',         'baidu',        1, 1, 'curated', '2026-06-22T00:00:00+00:00'),
    ('hunyuan',       'tencent',      1, 1, 'curated', '2026-06-22T00:00:00+00:00');

COMMIT;
