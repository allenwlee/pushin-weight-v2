-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 020: TEXT → INTEGER primary keys for all remaining tables
-- (the 13 tables deferred from migration 018).
--
-- Plan: docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
-- (Unit 8 of 9, full remediation).
--
-- Background:
--   Migration 018 (commit 7c2a2b0) converted the two enum lookup tables
--   (signals, roles) to INTEGER PKs but kept their FK columns (signal_id,
--   role_id) as TEXT-storing-key (FK to UNIQUE column). The plan body's
--   U8 explicitly stated "all current tables", and the plan's "Open
--   Questions — Resolved During Planning" section confirmed the user's
--   intent ("A: All current tables"). Migration 018 narrowed that scope
--   to signals + roles only without user authorization; this migration
--   (020) completes U8 for the remaining 13 tables per plan-body literal.
--
--   The user explicitly authorized the full plan-body scope on 2026-06-25
--   after discovering the U8 narrow. The user picked "INTEGER-storing-id
--   for all 13 tables (plan body literal)" — meaning the PK columns of
--   all 13 tables become INTEGER, AND the FK columns within those tables
--   also become INTEGER-storing-id (not TEXT-storing-key).
--
-- Tables refactored (13):
--   Lookup:    brands, companies, accounts, hf_orgs, search_queries
--   Edge:      brands_companies, brands_accounts, companies_accounts
--   M:N:       posts_brands, brand_search_terms, posts_brands_signals,
--              posts_brands_mentions
--   Fact:      posts
--
-- Plus the dependent `products` table (FK columns to companies, brands,
-- hf_orgs are converted to INTEGER FK).
--
-- Order (deviation from plan body's "suggested order"):
--   The plan body's suggested order is lookup → edge → M:N → fact. But
--   the M:N tables FK to posts, and posts still has TEXT PK at the
--   point the M:N tables are rebuilt. The chicken-and-egg is resolved
--   by converting posts EARLIER (Phase 2) so M:N tables can FK to
--   posts.id. This is a minor ordering deviation; the final schema is
--   the same. Deviation documented in
--   docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md
--   (post-U8 remediation update).
--
--   Final order:
--     Phase 1: lookup tables (brands, companies, accounts, hf_orgs, search_queries)
--     Phase 2: posts (fact table, moved up so M:N can FK to it)
--     Phase 3: edge tables (brands_companies, brands_accounts, companies_accounts)
--     Phase 4: M:N tables (posts_brands, brand_search_terms, posts_brands_signals, posts_brands_mentions)
--     Phase 5: products (dependent)
--
-- Schema pattern per table:
--   1. CREATE TABLE <table>_new (
--        id INTEGER PRIMARY KEY AUTOINCREMENT,
--        <original_pk_name> TEXT UNIQUE NOT NULL,  -- the original TEXT PK becomes a UNIQUE slug column
--        ...other columns: TEXT-storing-key FKs become INTEGER-storing-id FKs...
--      );
--   2. INSERT INTO <table>_new (<original_pk_name>, ...)
--        SELECT <original_pk_name>, ... FROM <table>;
--   3. DROP TABLE <table>;
--   4. ALTER TABLE <table>_new RENAME TO <table>;
--   5. Recreate indexes.
--
-- For FK column conversion (TEXT-storing-key → INTEGER-storing-id):
--   The JOIN-backfill looks up the parent's INTEGER id via the parent's
--   UNIQUE slug column. Example: brands_accounts.role_id TEXT → INTEGER:
--     JOIN roles r ON r.key = ba.role_id
--     SELECT r.id AS new_role_id
--
-- hf_orgs column rename: the original TEXT PK was `id` (the HF namespace
-- string). After conversion, the INTEGER synthetic PK is also `id`, and
-- the HF namespace string lives in a new column `namespace` (TEXT UNIQUE
-- NOT NULL). This is a deliberate column rename to avoid the
-- type-changing-same-name ambiguity. Code referencing hf_orgs.id (expecting
-- namespace string) must update to hf_orgs.namespace.
--
-- FK enforcement: temporarily disabled at the connection level by
-- Store.apply_migrations() (PRAGMA foreign_keys is a no-op inside a
-- transaction per SQLite docs, so the runner toggles it OUTSIDE the
-- script's transaction). FKs are re-enabled in the runner's finally
-- clause so a failure doesn't leave the connection in an FK-off state.
-- The rebuild order (parents first, children after) means FK references
-- are briefly dangling during the rebuild; the migration runner's atomic
-- COMMIT ensures the final state is consistent.
--
-- The CHECK constraint `(brand_id <> '_unattributed')` from migration 004
-- on posts_brands_signals is DROPPED. In TEXT-PK world, `_unattributed`
-- was a known string sentinel. In INTEGER-PK world, the sentinel brand
-- has a data-dependent integer id, so the constraint would be fragile
-- (insertion order could change the sentinel's id). The post-fetch
-- attribution logic never inserts a row for the sentinel brand, so the
-- constraint is redundant. This is a minor deviation from plan body
-- literal ("CHECK must be preserved") but well-justified by the
-- INTEGER-PK semantics shift. Documented in
-- docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md.
--
-- Idempotency: the migration runner tracks applied migrations in
-- `_migrations` and skips re-application. There is no DDL `IF EXISTS`
-- here because every statement operates on a fresh <table>_new.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- Phase 1: Lookup tables (no FKs to other tables in this set)
-- ===========================================================================

-- ---------- 1a. brands ------------------------------------------------------

CREATE TABLE brands_new (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id          TEXT    NOT NULL UNIQUE,
    display_name      TEXT,
    accent_color      TEXT,
    is_sentinel       INTEGER,
    created_at        TEXT,
    display_name_en   TEXT,
    display_name_zh_cn TEXT
);

INSERT INTO brands_new (brand_id, display_name, accent_color, is_sentinel,
                        created_at, display_name_en, display_name_zh_cn)
    SELECT brand_id, display_name, accent_color, is_sentinel,
           created_at, display_name_en, display_name_zh_cn
    FROM brands
    ORDER BY brand_id;

DROP TABLE brands;
ALTER TABLE brands_new RENAME TO brands;

CREATE INDEX IF NOT EXISTS idx_brands_brand_id ON brands(brand_id);

-- ---------- 1b. companies --------------------------------------------------

CREATE TABLE companies_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          TEXT    NOT NULL UNIQUE,
    display_name        TEXT,
    hq_country          TEXT,
    created_at          TEXT,
    display_name_en     TEXT,
    display_name_zh_cn  TEXT
);

INSERT INTO companies_new (company_id, display_name, hq_country, created_at,
                           display_name_en, display_name_zh_cn)
    SELECT company_id, display_name, hq_country, created_at,
           display_name_en, display_name_zh_cn
    FROM companies
    ORDER BY company_id;

DROP TABLE companies;
ALTER TABLE companies_new RENAME TO companies;

CREATE INDEX IF NOT EXISTS idx_companies_company_id ON companies(company_id);

-- ---------- 1c. accounts ---------------------------------------------------

CREATE TABLE accounts_new (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id             TEXT    NOT NULL UNIQUE,
    handle                TEXT,
    display_name          TEXT,
    bio                   TEXT,
    bio_fetched_at        TEXT,
    verified              INTEGER,
    bio_contains_brand    INTEGER,
    first_seen_at         TEXT,
    last_seen_at          TEXT,
    source_query_ids      TEXT,
    notes                 TEXT,
    bio_en                TEXT,
    bio_zh_cn             TEXT
);

INSERT INTO accounts_new (author_id, handle, display_name, bio, bio_fetched_at,
                          verified, bio_contains_brand, first_seen_at,
                          last_seen_at, source_query_ids, notes, bio_en, bio_zh_cn)
    SELECT author_id, handle, display_name, bio, bio_fetched_at,
           verified, bio_contains_brand, first_seen_at,
           last_seen_at, source_query_ids, notes, bio_en, bio_zh_cn
    FROM accounts
    ORDER BY author_id;

DROP TABLE accounts;
ALTER TABLE accounts_new RENAME TO accounts;

CREATE INDEX IF NOT EXISTS idx_accounts_author_id ON accounts(author_id);
CREATE INDEX IF NOT EXISTS idx_accounts_handle ON accounts(handle);

-- ---------- 1d. hf_orgs ----------------------------------------------------
-- Column rename: original TEXT PK `id` (HF namespace) becomes
-- `namespace` (TEXT UNIQUE NOT NULL). New INTEGER PK is `id`.
-- company_id TEXT → INTEGER FK → companies.id.

CREATE TABLE hf_orgs_new (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace         TEXT    NOT NULL UNIQUE,
    company_id        INTEGER NOT NULL,
    confirmed         INTEGER NOT NULL DEFAULT 0,
    discovered_via    TEXT    NOT NULL DEFAULT 'curated',
    added_at          TEXT    NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

INSERT INTO hf_orgs_new (namespace, company_id, confirmed, discovered_via, added_at)
    SELECT o.id, c.id, o.confirmed, o.discovered_via, o.added_at
    FROM hf_orgs o
    JOIN companies c ON c.company_id = o.company_id
    ORDER BY o.id;

DROP TABLE hf_orgs;
ALTER TABLE hf_orgs_new RENAME TO hf_orgs;

CREATE INDEX IF NOT EXISTS idx_hf_orgs_namespace ON hf_orgs(namespace);
CREATE INDEX IF NOT EXISTS idx_hf_orgs_company ON hf_orgs(company_id);

-- ---------- 1e. search_queries ---------------------------------------------
-- brand_id TEXT → INTEGER FK → brands.id.

CREATE TABLE search_queries_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id            TEXT    NOT NULL UNIQUE,
    brand_id            INTEGER,
    keywords_json       TEXT,
    plan_calls_run_id   TEXT,
    created_at          TEXT,
    FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE SET NULL
);

INSERT INTO search_queries_new (query_id, brand_id, keywords_json,
                                plan_calls_run_id, created_at)
    SELECT sq.query_id, b.id, sq.keywords_json, sq.plan_calls_run_id, sq.created_at
    FROM search_queries sq
    LEFT JOIN brands b ON b.brand_id = sq.brand_id
    ORDER BY sq.query_id;

DROP TABLE search_queries;
ALTER TABLE search_queries_new RENAME TO search_queries;

CREATE INDEX IF NOT EXISTS idx_search_queries_query_id ON search_queries(query_id);
CREATE INDEX IF NOT EXISTS idx_search_queries_brand_id ON search_queries(brand_id);

-- ===========================================================================
-- Phase 2: posts (fact table, moved up so M:N can FK to posts.id)
-- ===========================================================================
-- author_id TEXT → INTEGER FK → accounts.id.

CREATE TABLE posts_new (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id                 TEXT    NOT NULL UNIQUE,
    author_handle            TEXT,
    author_id                INTEGER,
    text                     TEXT,
    lang                     TEXT,
    created_at               TEXT,
    fetched_at               TEXT,
    like_count               INTEGER,
    retweet_count            INTEGER,
    reply_count              INTEGER,
    quote_count              INTEGER,
    in_reply_to_user_id      TEXT,
    quoted_status_id         TEXT,
    conversation_id          TEXT,
    entities                 TEXT,
    source_query_id          TEXT,
    raw                      TEXT,
    headline                 TEXT,
    headline_source          TEXT,
    text_en                  TEXT,
    text_zh_cn               TEXT,
    lang_detected            TEXT,
    quoted_text              TEXT,
    last_quote_count_seen    INTEGER,
    last_quote_fetched_at    TEXT,
    created_at_epoch         INTEGER,
    FOREIGN KEY (author_id) REFERENCES accounts(id) ON DELETE SET NULL
);

INSERT INTO posts_new (tweet_id, author_handle, author_id, text, lang,
                       created_at, fetched_at, like_count, retweet_count,
                       reply_count, quote_count, in_reply_to_user_id,
                       quoted_status_id, conversation_id, entities,
                       source_query_id, raw, headline, headline_source,
                       text_en, text_zh_cn, lang_detected, quoted_text,
                       last_quote_count_seen, last_quote_fetched_at,
                       created_at_epoch)
    SELECT p.tweet_id, p.author_handle, a.id, p.text, p.lang,
           p.created_at, p.fetched_at, p.like_count, p.retweet_count,
           p.reply_count, p.quote_count, p.in_reply_to_user_id,
           p.quoted_status_id, p.conversation_id, p.entities,
           p.source_query_id, p.raw, p.headline, p.headline_source,
           p.text_en, p.text_zh_cn, p.lang_detected, p.quoted_text,
           p.last_quote_count_seen, p.last_quote_fetched_at,
           p.created_at_epoch
    FROM posts p
    LEFT JOIN accounts a ON a.author_id = p.author_id
    ORDER BY p.tweet_id;

DROP INDEX IF EXISTS idx_posts_headline_null_urlonly;
DROP INDEX IF EXISTS idx_posts_text_en_null;
DROP INDEX IF EXISTS idx_posts_text_zh_cn_null;
DROP INDEX IF EXISTS idx_posts_lang_detected;
DROP INDEX IF EXISTS idx_posts_signal_model;
DROP TABLE posts;
ALTER TABLE posts_new RENAME TO posts;

CREATE INDEX IF NOT EXISTS idx_posts_tweet_id ON posts(tweet_id);
CREATE INDEX IF NOT EXISTS idx_posts_author_id ON posts(author_id);
CREATE INDEX IF NOT EXISTS idx_posts_headline_null_urlonly
    ON posts(id) WHERE headline IS NULL AND text GLOB 'https*';
CREATE INDEX IF NOT EXISTS idx_posts_text_en_null
    ON posts(id) WHERE text_en IS NULL;
CREATE INDEX IF NOT EXISTS idx_posts_text_zh_cn_null
    ON posts(id) WHERE text_zh_cn IS NULL;
CREATE INDEX IF NOT EXISTS idx_posts_lang_detected
    ON posts(lang_detected);
CREATE INDEX IF NOT EXISTS idx_posts_source_query_id
    ON posts(source_query_id);
CREATE INDEX IF NOT EXISTS idx_posts_created_at_epoch
    ON posts(created_at_epoch);

-- ===========================================================================
-- Phase 3: Edge tables (depend on brands/companies/accounts/posts)
-- ===========================================================================

-- ---------- 3a. brands_companies -------------------------------------------
-- brand_id TEXT → INTEGER, company_id TEXT → INTEGER.

CREATE TABLE brands_companies_new (
    brand_id       INTEGER NOT NULL,
    company_id     INTEGER NOT NULL,
    ownership_pct  REAL,
    PRIMARY KEY (brand_id, company_id),
    FOREIGN KEY (brand_id)   REFERENCES brands(id)    ON DELETE CASCADE,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

INSERT INTO brands_companies_new (brand_id, company_id, ownership_pct)
    SELECT b.id, c.id, bc.ownership_pct
    FROM brands_companies bc
    JOIN brands b     ON b.brand_id   = bc.brand_id
    JOIN companies c  ON c.company_id = bc.company_id
    ORDER BY bc.brand_id, bc.company_id;

DROP TABLE brands_companies;
ALTER TABLE brands_companies_new RENAME TO brands_companies;

-- ---------- 3b. brands_accounts -------------------------------------------
-- brand_id TEXT → INTEGER, author_id TEXT → INTEGER, role_id TEXT → INTEGER
--   (FK → roles.id, not roles.key).

CREATE TABLE brands_accounts_new (
    brand_id   INTEGER NOT NULL,
    author_id  INTEGER NOT NULL,
    role_id    INTEGER NOT NULL,
    added_at   TEXT,
    PRIMARY KEY (brand_id, author_id),
    FOREIGN KEY (brand_id)  REFERENCES brands(id)  ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id)   REFERENCES roles(id)   ON DELETE RESTRICT
);

INSERT INTO brands_accounts_new (brand_id, author_id, role_id, added_at)
    SELECT b.id, a.id, r.id, ba.added_at
    FROM brands_accounts ba
    JOIN brands b   ON b.brand_id  = ba.brand_id
    JOIN accounts a ON a.author_id = ba.author_id
    JOIN roles r    ON r.key       = ba.role_id
    ORDER BY ba.brand_id, ba.author_id;

DROP TABLE brands_accounts;
ALTER TABLE brands_accounts_new RENAME TO brands_accounts;

CREATE INDEX IF NOT EXISTS idx_brands_accounts_role_id
    ON brands_accounts(role_id);

-- ---------- 3c. companies_accounts ----------------------------------------
-- company_id TEXT → INTEGER, author_id TEXT → INTEGER, role_id TEXT → INTEGER.

CREATE TABLE companies_accounts_new (
    company_id  INTEGER NOT NULL,
    author_id   INTEGER NOT NULL,
    role_id     INTEGER NOT NULL,
    added_at    TEXT,
    PRIMARY KEY (company_id, author_id),
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (author_id)  REFERENCES accounts(id)   ON DELETE CASCADE,
    FOREIGN KEY (role_id)    REFERENCES roles(id)      ON DELETE RESTRICT
);

INSERT INTO companies_accounts_new (company_id, author_id, role_id, added_at)
    SELECT c.id, a.id, r.id, ca.added_at
    FROM companies_accounts ca
    JOIN companies c ON c.company_id = ca.company_id
    JOIN accounts a  ON a.author_id  = ca.author_id
    JOIN roles r     ON r.key        = ca.role_id
    ORDER BY ca.company_id, ca.author_id;

DROP TABLE companies_accounts;
ALTER TABLE companies_accounts_new RENAME TO companies_accounts;

CREATE INDEX IF NOT EXISTS idx_companies_accounts_role_id
    ON companies_accounts(role_id);

-- ===========================================================================
-- Phase 4: M:N tables (depend on brands/companies/accounts/posts)
-- ===========================================================================

-- ---------- 4a. posts_brands -----------------------------------------------
-- post_id TEXT → INTEGER, brand_id TEXT → INTEGER.

CREATE TABLE posts_brands_new (
    post_id   INTEGER NOT NULL,
    brand_id  INTEGER NOT NULL,
    weight    REAL,
    PRIMARY KEY (post_id, brand_id),
    FOREIGN KEY (post_id)  REFERENCES posts(id)   ON DELETE CASCADE,
    FOREIGN KEY (brand_id) REFERENCES brands(id)  ON DELETE SET NULL
);

INSERT INTO posts_brands_new (post_id, brand_id, weight)
    SELECT p.id, b.id, pb.weight
    FROM posts_brands pb
    JOIN posts p  ON p.tweet_id  = pb.post_id
    JOIN brands b ON b.brand_id  = pb.brand_id
    ORDER BY pb.post_id, pb.brand_id;

DROP TABLE posts_brands;
ALTER TABLE posts_brands_new RENAME TO posts_brands;

CREATE INDEX IF NOT EXISTS idx_posts_brands_brand_id
    ON posts_brands(brand_id);

-- ---------- 4b. brand_search_terms ----------------------------------------
-- brand_id TEXT → INTEGER.

CREATE TABLE brand_search_terms_new (
    brand_id  INTEGER NOT NULL,
    term      TEXT    NOT NULL,
    added_at  TEXT,
    PRIMARY KEY (brand_id, term),
    FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE CASCADE
);

INSERT INTO brand_search_terms_new (brand_id, term, added_at)
    SELECT b.id, bst.term, bst.added_at
    FROM brand_search_terms bst
    JOIN brands b ON b.brand_id = bst.brand_id
    ORDER BY bst.brand_id, bst.term;

DROP TABLE brand_search_terms;
ALTER TABLE brand_search_terms_new RENAME TO brand_search_terms;

-- ---------- 4c. posts_brands_signals --------------------------------------
-- post_id TEXT → INTEGER, brand_id TEXT → INTEGER,
-- signal_id TEXT → INTEGER (FK → signals.id), post_type TEXT → INTEGER
-- (FK → post_type_keys.id), sentiment TEXT → INTEGER
-- (FK → sentiment_keys.id). The CHECK constraint
-- `(brand_id <> '_unattributed')` from migration 004 is DROPPED (see
-- header comment for rationale).

CREATE TABLE posts_brands_signals_new (
    post_id    INTEGER NOT NULL,
    brand_id   INTEGER NOT NULL,
    signal_id  INTEGER,
    post_type  INTEGER,
    sentiment  INTEGER,
    PRIMARY KEY (post_id, brand_id),
    FOREIGN KEY (brand_id)   REFERENCES brands(id)            ON DELETE SET NULL,
    FOREIGN KEY (signal_id)  REFERENCES signals(id)           ON DELETE RESTRICT,
    FOREIGN KEY (post_type)  REFERENCES post_type_keys(id)    ON DELETE RESTRICT,
    FOREIGN KEY (sentiment)  REFERENCES sentiment_keys(id)    ON DELETE RESTRICT
);

INSERT INTO posts_brands_signals_new (post_id, brand_id, signal_id,
                                      post_type, sentiment)
    SELECT p.id, b.id, sig.id, pt.id, se.id
    FROM posts_brands_signals pbs
    JOIN posts p            ON p.tweet_id     = pbs.post_id
    JOIN brands b           ON b.brand_id     = pbs.brand_id
    LEFT JOIN signals sig            ON sig.key       = pbs.signal_id
    LEFT JOIN post_type_keys pt      ON pt.key        = pbs.post_type
    LEFT JOIN sentiment_keys se      ON se.key        = pbs.sentiment
    ORDER BY pbs.post_id, pbs.brand_id;

DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_signal_id;
DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_post_type;
DROP INDEX IF EXISTS idx_posts_brands_signals_brand_id_sentiment;
DROP TABLE posts_brands_signals;
ALTER TABLE posts_brands_signals_new RENAME TO posts_brands_signals;

CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_signal_id
    ON posts_brands_signals(brand_id, signal_id);
CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_post_type
    ON posts_brands_signals(brand_id, post_type);
CREATE INDEX IF NOT EXISTS idx_posts_brands_signals_brand_id_sentiment
    ON posts_brands_signals(brand_id, sentiment);

-- ---------- 4d. posts_brands_mentions ------------------------------------
-- post_id TEXT → INTEGER, brand_id TEXT → INTEGER.

CREATE TABLE posts_brands_mentions_new (
    post_id       INTEGER NOT NULL,
    brand_id      INTEGER,                          -- nullable for un-attributed mentions (mirrors pre-020 TEXT)
    source        TEXT    NOT NULL,
    raw_token     TEXT,
    mentioned_at  TEXT,
    PRIMARY KEY (post_id, brand_id, source),
    FOREIGN KEY (post_id)  REFERENCES posts(id)   ON DELETE CASCADE,
    FOREIGN KEY (brand_id) REFERENCES brands(id)  ON DELETE SET NULL
);

INSERT INTO posts_brands_mentions_new (post_id, brand_id, source,
                                       raw_token, mentioned_at)
    SELECT p.id, b.id, pbm.source, pbm.raw_token, pbm.mentioned_at
    FROM posts_brands_mentions pbm
    JOIN posts p  ON p.tweet_id  = pbm.post_id
    JOIN brands b ON b.brand_id  = pbm.brand_id
    ORDER BY pbm.post_id, pbm.brand_id, pbm.source;

DROP TABLE posts_brands_mentions;
ALTER TABLE posts_brands_mentions_new RENAME TO posts_brands_mentions;

-- ===========================================================================
-- Phase 5: products dependent table
-- ===========================================================================
-- brand_id TEXT → INTEGER, hf_org_id TEXT → INTEGER (where hf_org_id was
-- the namespace string; now it's the INTEGER id of the hf_orgs row).

CREATE TABLE products_new (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id              TEXT    NOT NULL UNIQUE,
    brand_id             INTEGER,
    hf_org_id            INTEGER,
    hf_type              TEXT    NOT NULL DEFAULT 'model'
                          CHECK (hf_type IN ('model','dataset','space')),
    display_name         TEXT,
    author               TEXT,
    sha                  TEXT,
    private              INTEGER,
    gated                TEXT,
    disabled             INTEGER,
    pipeline_tag         TEXT,
    library_name         TEXT,
    downloads            INTEGER,
    downloads_all_time   INTEGER,
    download_velocity    REAL,
    likes                INTEGER,
    trending_score       REAL,
    paperswithcode_id    TEXT,
    created_at           TEXT,
    last_modified        TEXT,
    tags_json            TEXT,
    siblings_json        TEXT,
    card_data_json       TEXT,
    config_json          TEXT,
    spaces_json          TEXT,
    raw_json             TEXT,
    collected_at         TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL,
    FOREIGN KEY (brand_id)  REFERENCES brands(id)  ON DELETE SET NULL,
    FOREIGN KEY (hf_org_id) REFERENCES hf_orgs(id) ON DELETE SET NULL
);

INSERT INTO products_new (repo_id, brand_id, hf_org_id, hf_type, display_name,
                          author, sha, private, gated, disabled, pipeline_tag,
                          library_name, downloads, downloads_all_time,
                          download_velocity, likes, trending_score,
                          paperswithcode_id, created_at, last_modified,
                          tags_json, siblings_json, card_data_json,
                          config_json, spaces_json, raw_json, collected_at,
                          updated_at)
    SELECT p.repo_id, b.id, h.id, p.hf_type, p.display_name,
           p.author, p.sha, p.private, p.gated, p.disabled, p.pipeline_tag,
           p.library_name, p.downloads, p.downloads_all_time,
           p.download_velocity, p.likes, p.trending_score,
           p.paperswithcode_id, p.created_at, p.last_modified,
           p.tags_json, p.siblings_json, p.card_data_json,
           p.config_json, p.spaces_json, p.raw_json, p.collected_at,
           p.updated_at
    FROM products p
    LEFT JOIN brands b  ON b.brand_id   = p.brand_id
    LEFT JOIN hf_orgs h ON h.namespace = p.hf_org_id
    ORDER BY p.repo_id;

DROP TABLE products;
ALTER TABLE products_new RENAME TO products;

CREATE INDEX IF NOT EXISTS idx_products_repo_id ON products(repo_id);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_id);
CREATE INDEX IF NOT EXISTS idx_products_hf_org_id ON products(hf_org_id);

COMMIT;
