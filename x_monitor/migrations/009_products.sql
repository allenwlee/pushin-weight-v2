-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 009: HuggingFace products catalog + company→HF-org mapping.
--
-- Originally written as migration 005 on a fresh-from-main branch; renumbered
-- to 009 at rebase time (2026-06-23) because main had just received migrations
-- 005_quoted_text.sql + 006_quote_capture_tracking.sql (quote-tweets branch) and
-- 007_i18n_locale_columns.sql + 008_enum_i18n_lookup_tables.sql (i18n branch).
--
-- Replaces the earlier brand_hf_orgs design with a company-centric one. A
-- `brand` in x-monitor is an operator-curated product-line grouping (e.g.
-- inclusionai curates Ring/Ling/Ming series as one brand even though they
-- live under separate HF namespaces); an HF namespace is a corporate
-- identity (e.g. "MiniMaxAI" belongs to MiniMax). The M:N brand↔HF-org edge
-- is replaced by a 1:N companies→HF-orgs edge.
--
-- Adds two additive tables:
--
--   hf_orgs        1:N edge companies → HuggingFace orgs/usernames.
--                  `confirmed` = 1 for curated/operator-confirmed orgs (scraped);
--                  `confirmed` = 0 for runtime-discovered candidates (flagged for
--                  review, NOT scraped until promoted).
--   products       one row per HF model. brands 1:N products AND
--                  companies 1:N products (via hf_orgs.hf_org_id).
--                  wide scalar columns + JSON columns + a verbatim raw_json
--                  payload so columns can be added later without re-scraping.
--                  hf_org_id is a FK to hf_orgs.id (nullable, SET NULL on delete)
--                  so model identity (repo_id) survives if a company is dropped.
--
-- Idempotency: every CREATE uses IF NOT EXISTS and every INSERT uses OR IGNORE.
-- Re-running on a fresh DB is safe; re-running on a DB that already has
-- brand_hf_orgs from the prior design is also safe (the brand_hf_orgs table
-- is dropped by the DROP IF EXISTS step at the top).
--
-- Plans:
--   docs/plans/2026-06-22-001-refactor-hf-orgs-belong-to-companies-plan.md
--   docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md (origin)
--
-- _migrations ledger is updated by Store._apply_migration AFTER this script's
-- COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- 0. Cleanup of the prior design (idempotent — IF EXISTS).
--    brand_hf_orgs was the M:N brand↔HF-org edge in the earlier 005 draft; it's
--    replaced by hf_orgs (1:N companies→HF-orgs). Drop on apply.
-- ===========================================================================

DROP TABLE IF EXISTS brand_hf_orgs;
DROP INDEX IF EXISTS idx_brand_hf_orgs_brand;
DROP INDEX IF EXISTS idx_products_hf_org;

-- ===========================================================================
-- 1. hf_orgs — 1:N edge companies → HuggingFace orgs/usernames.
--    PRIMARY KEY is the HF namespace string itself (e.g. "MiniMaxAI"). A
--    given HF namespace belongs to exactly one corporate parent (no M:N
--    edge because HF namespace ownership is corporate, not shared).
-- ===========================================================================

CREATE TABLE IF NOT EXISTS hf_orgs (
    id              TEXT PRIMARY KEY,                -- HF namespace, e.g. "MiniMaxAI", "deepseek-ai"
    company_id      TEXT NOT NULL,                   -- FK companies.company_id (CASCADE — company drop deletes its HF orgs)
    confirmed       INTEGER NOT NULL DEFAULT 0,      -- 1 = curated/confirmed (scraped); 0 = discovered candidate (review)
    discovered_via  TEXT NOT NULL DEFAULT 'curated', -- 'curated' | 'search:<query>'
    added_at        TEXT NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hf_orgs_company
    ON hf_orgs(company_id);

-- ===========================================================================
-- 2. products — one row per HuggingFace model.
--    hf_org_id is a nullable FK to hf_orgs.id (SET NULL on hf_org delete) so
--    model identity (repo_id PK) survives even if the HF org is dropped.
--    brand_id remains a nullable FK to brands (SET NULL on brand delete) —
--    unchanged from the original 005 draft.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS products (
    repo_id            TEXT PRIMARY KEY,             -- HF model id, e.g. "MiniMaxAI/MiniMax-M1"
    brand_id           TEXT,                         -- FK brands.brand_id (SET NULL on brand delete)
    hf_org_id          TEXT,                         -- FK hf_orgs.id (SET NULL on hf_org delete; nullable)
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
    FOREIGN KEY (brand_id)  REFERENCES brands(brand_id)  ON DELETE SET NULL,
    FOREIGN KEY (hf_org_id) REFERENCES hf_orgs(id)       ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_products_brand
    ON products(brand_id);

CREATE INDEX IF NOT EXISTS idx_products_hf_org_id
    ON products(hf_org_id);

-- ===========================================================================
-- 3. Add the missing `minimax` company + brand_companies edge.
--    The original 004 migration seeded 10 companies; `minimax` was a brand
--    without a corporate parent. The new model requires every HF-crawled
--    brand to have a company, so we add it here.
-- ===========================================================================

INSERT OR IGNORE INTO companies (company_id, display_name, hq_country, created_at) VALUES
    ('minimax', 'MiniMax', 'CN', '2026-06-22T18:58:00+00:00');

INSERT OR IGNORE INTO brand_companies (brand_id, company_id, ownership_pct) VALUES
    ('minimax', 'minimax', 1.0);

-- ===========================================================================
-- 4. Seed curated company→HF-org mapping (confirmed=1).
--    11 rows: one HF namespace per company that has a corporate parent. The
--    `_unattributed` brand is intentionally excluded — it has no corporate
--    parent and no HF coverage.
-- ===========================================================================

INSERT OR IGNORE INTO hf_orgs (id, company_id, confirmed, discovered_via, added_at) VALUES
    ('Qwen',         'alibaba',     1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('baidu',        'baidu',       1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('tencent',      'tencent',     1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('moonshotai',   'moonshot',    1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('THUDM',        'zhipu',       1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('XiaomiMiMo',   'xiaomi',      1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('mistralai',    'mistral_ai',  1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('inclusionAI',  'inclusion_ai',1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('deepseek-ai',  'deepseek_co', 1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('stepfun-ai',   'stepfun_inc', 1, 'curated', '2026-06-22T18:58:00+00:00'),
    ('MiniMaxAI',    'minimax',     1, 'curated', '2026-06-22T18:58:00+00:00');

COMMIT;
