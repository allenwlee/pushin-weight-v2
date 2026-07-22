-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 007: enum i18n lookup tables + FK conversion.
--
-- Replaces convention-only TEXT enum columns with FK-validated keys
-- pointing at lookup tables, plus label tables for per-locale rendering.
-- Enum families converted:
--
--   post_brand_signals.signal   (6 keys: release, community_question,
--                                 criticism, commenter_capture, praise,
--                                 other)
--   brand_accounts.role         (5 keys: official, community, researcher,
--                                 press, vendor)
--   company_accounts.role       (same 5 keys)
--   accounts.engagement_tier    (3 keys: low, medium, high)
--
-- Shape (per enum family):
--   <family>_keys  (key TEXT PRIMARY KEY, created_at TEXT NOT NULL)
--                  -- integrity / FK source
--   <family>_labels(key TEXT, locale TEXT, label TEXT,
--                   PRIMARY KEY (key, locale),
--                   FOREIGN KEY (key) REFERENCES <family>_keys(key)
--                                 ON DELETE CASCADE)
--                  -- display lookup, joined by (key, locale) per render
--
-- SQLite FKs cannot target a subset of a composite PK, so the keys and
-- labels are split into two tables. The display layer reads labels;
-- the integrity layer reads keys.
--
-- FK conversion via SQLite table rebuild (no ALTER TABLE DROP
-- CONSTRAINT support; per https://www.sqlite.org/lang_altertable.html).
-- The CHECK (brand_id <> '_unattributed') constraint on
-- post_brand_signals must survive the rebuild (P0 review fix from
-- migration 004 history).
--
-- Best-guess zh-CN seeds (operator may override via
-- data/translations/enum_zh_cn_overrides.json, loaded by Unit 6).
--
-- Plan: docs/plans/2026-06-23-001-feat-i18n-locale-columns-plan.md
-- Unit 2 of 7.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- 1. signal_keys + signal_labels
-- ===========================================================================

CREATE TABLE IF NOT EXISTS signal_keys (
    key         TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL
);

INSERT OR IGNORE INTO signal_keys (key, created_at) VALUES
    ('release',             '2026-06-23T00:00:00+00:00'),
    ('community_question',  '2026-06-23T00:00:00+00:00'),
    ('criticism',           '2026-06-23T00:00:00+00:00'),
    ('commenter_capture',   '2026-06-23T00:00:00+00:00'),
    ('praise',              '2026-06-23T00:00:00+00:00'),
    ('other',               '2026-06-23T00:00:00+00:00');

CREATE TABLE IF NOT EXISTS signal_labels (
    key     TEXT NOT NULL,
    locale  TEXT NOT NULL,
    label   TEXT NOT NULL,
    PRIMARY KEY (key, locale),
    FOREIGN KEY (key) REFERENCES signal_keys(key) ON DELETE CASCADE
);

INSERT OR IGNORE INTO signal_labels (key, locale, label) VALUES
    ('release',             'en',    'Release'),
    ('release',             'zh_cn', '发布'),
    ('community_question',  'en',    'Question'),
    ('community_question',  'zh_cn', '提问'),
    ('criticism',           'en',    'Criticism'),
    ('criticism',           'zh_cn', '批评'),
    ('commenter_capture',   'en',    'Capture'),
    ('commenter_capture',   'zh_cn', '引流'),
    ('praise',              'en',    'Praise'),
    ('praise',              'zh_cn', '称赞'),
    ('other',               'en',    'Other'),
    ('other',               'zh_cn', '其他');

-- ===========================================================================
-- 2. role_keys + role_labels  (5 keys, shared by brand_accounts + company_accounts)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS role_keys (
    key         TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL
);

INSERT OR IGNORE INTO role_keys (key, created_at) VALUES
    ('official',    '2026-06-23T00:00:00+00:00'),
    ('community',   '2026-06-23T00:00:00+00:00'),
    ('researcher',  '2026-06-23T00:00:00+00:00'),
    ('press',       '2026-06-23T00:00:00+00:00'),
    ('vendor',      '2026-06-23T00:00:00+00:00');

CREATE TABLE IF NOT EXISTS role_labels (
    key     TEXT NOT NULL,
    locale  TEXT NOT NULL,
    label   TEXT NOT NULL,
    PRIMARY KEY (key, locale),
    FOREIGN KEY (key) REFERENCES role_keys(key) ON DELETE CASCADE
);

INSERT OR IGNORE INTO role_labels (key, locale, label) VALUES
    ('official',    'en',    'Official'),
    ('official',    'zh_cn', '官方'),
    ('community',   'en',    'Community'),
    ('community',   'zh_cn', '社区'),
    ('researcher',  'en',    'Researcher'),
    ('researcher',  'zh_cn', '研究者'),
    ('press',       'en',    'Press'),
    ('press',       'zh_cn', '媒体'),
    ('vendor',      'en',    'Vendor'),
    ('vendor',      'zh_cn', '厂商');

-- ===========================================================================
-- 3. engagement_tier_keys + engagement_tier_labels
-- ===========================================================================

CREATE TABLE IF NOT EXISTS engagement_tier_keys (
    key         TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL
);

INSERT OR IGNORE INTO engagement_tier_keys (key, created_at) VALUES
    ('low',     '2026-06-23T00:00:00+00:00'),
    ('medium',  '2026-06-23T00:00:00+00:00'),
    ('high',    '2026-06-23T00:00:00+00:00');

CREATE TABLE IF NOT EXISTS engagement_tier_labels (
    key     TEXT NOT NULL,
    locale  TEXT NOT NULL,
    label   TEXT NOT NULL,
    PRIMARY KEY (key, locale),
    FOREIGN KEY (key) REFERENCES engagement_tier_keys(key) ON DELETE CASCADE
);

INSERT OR IGNORE INTO engagement_tier_labels (key, locale, label) VALUES
    ('low',     'en',    'Low'),
    ('low',     'zh_cn', '低'),
    ('medium',  'en',    'Medium'),
    ('medium',  'zh_cn', '中'),
    ('high',    'en',    'High'),
    ('high',    'zh_cn', '高');

-- ===========================================================================
-- 4. FK conversion: post_brand_signals.signal via table rebuild
-- ===========================================================================

DROP INDEX IF EXISTS idx_post_brand_signals_brand_signal;
DROP INDEX IF EXISTS idx_post_brand_signals_post;

CREATE TABLE post_brand_signals_new (
    post_id   TEXT NOT NULL,
    brand_id  TEXT NOT NULL,
    signal    TEXT NOT NULL,
    PRIMARY KEY (post_id, brand_id),
    FOREIGN KEY (post_id)  REFERENCES posts(tweet_id)   ON DELETE CASCADE,
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id)  ON DELETE SET NULL,
    FOREIGN KEY (signal)   REFERENCES signal_keys(key)  ON DELETE RESTRICT,
    CHECK (brand_id <> '_unattributed')
);

INSERT INTO post_brand_signals_new (post_id, brand_id, signal)
    SELECT post_id, brand_id, signal
    FROM post_brand_signals;

DROP TABLE post_brand_signals;

ALTER TABLE post_brand_signals_new RENAME TO post_brand_signals;

CREATE INDEX IF NOT EXISTS idx_post_brand_signals_brand_signal
    ON post_brand_signals(brand_id, signal);

CREATE INDEX IF NOT EXISTS idx_post_brand_signals_post
    ON post_brand_signals(post_id);

-- ===========================================================================
-- 5. FK conversion: brand_accounts.role via table rebuild
-- ===========================================================================

DROP INDEX IF EXISTS idx_brand_accounts_role;

CREATE TABLE brand_accounts_new (
    brand_id   TEXT NOT NULL,
    author_id  TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'community',
    added_at   TEXT NOT NULL,
    PRIMARY KEY (brand_id, author_id),
    FOREIGN KEY (brand_id)  REFERENCES brands(brand_id)    ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES accounts(author_id) ON DELETE CASCADE,
    FOREIGN KEY (role)      REFERENCES role_keys(key)      ON DELETE RESTRICT
);

INSERT INTO brand_accounts_new (brand_id, author_id, role, added_at)
    SELECT brand_id, author_id, role, added_at
    FROM brand_accounts;

DROP TABLE brand_accounts;

ALTER TABLE brand_accounts_new RENAME TO brand_accounts;

CREATE INDEX IF NOT EXISTS idx_brand_accounts_role
    ON brand_accounts(role);

-- ===========================================================================
-- 6. FK conversion: company_accounts.role via table rebuild
-- ===========================================================================

DROP INDEX IF EXISTS idx_company_accounts_role;

CREATE TABLE company_accounts_new (
    company_id  TEXT NOT NULL,
    author_id   TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'community',
    added_at    TEXT NOT NULL,
    PRIMARY KEY (company_id, author_id),
    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
    FOREIGN KEY (author_id)  REFERENCES accounts(author_id)   ON DELETE CASCADE,
    FOREIGN KEY (role)       REFERENCES role_keys(key)        ON DELETE RESTRICT
);

INSERT INTO company_accounts_new (company_id, author_id, role, added_at)
    SELECT company_id, author_id, role, added_at
    FROM company_accounts;

DROP TABLE company_accounts;

ALTER TABLE company_accounts_new RENAME TO company_accounts;

CREATE INDEX IF NOT EXISTS idx_company_accounts_role
    ON company_accounts(role);

-- ===========================================================================
-- 7. FK conversion: accounts.engagement_tier via table rebuild
-- ===========================================================================

CREATE TABLE accounts_new (
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
    notes                TEXT,
    bio_en               TEXT,
    bio_zh_cn            TEXT,
    FOREIGN KEY (engagement_tier) REFERENCES engagement_tier_keys(key)
        ON DELETE RESTRICT
);

INSERT INTO accounts_new (
    author_id, handle, display_name, bio, bio_fetched_at,
    verified, bio_contains_brand, engagement_tier,
    first_seen_at, last_seen_at, source_query_ids, notes,
    bio_en, bio_zh_cn
)
SELECT
    author_id, handle, display_name, bio, bio_fetched_at,
    verified, bio_contains_brand, engagement_tier,
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