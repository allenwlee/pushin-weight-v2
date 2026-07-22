-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 027a: taxonomy extension + posts_unsanctioned_flags.
--
-- Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
-- Unit U1a.
--
-- What this migration adds:
--   1. Two new post_type_keys (advertising_marketing, event_announcement)
--      + labels in en / zh_cn. Extends the 4-key taxonomy from migration
--      019 to 6 keys.
--
--   2. One new discourse_key (advertising-marketing) + labels in en /
--      zh_cn. Extends the 9-key vocabulary from migration 026 to 10.
--      NOTE: the key uses a HYPHEN, not an underscore, to match the
--      brainstorm at docs/brainstorms/2026-07-03-140809-...md:113-114.
--      All other discourse_keys use underscores; this intentional
--      inconsistency is documented in the plan's KTD7.
--
--   3. The posts_unsanctioned_flags table — per-post persistence of the
--      LLM-emitted `unsanctioned_flags` array. Allowed flag values:
--      marketing_spam, scam, crypto, unauthorized.
--
--      Shape (per KTD3):
--        post_id  TEXT PRIMARY KEY,          -- FK → posts.tweet_id
--        flags    TEXT NOT NULL,             -- JSON array, e.g. '["scam","crypto"]'
--        flag_set TEXT GENERATED ALWAYS AS
--                  (json_extract(flags, '$')) STORED,  -- indexable lookup
--        evidence TEXT,                      -- sanitized (1 KB cap, no URLs)
--                                            -- enforced at the Store API
--                                            -- layer (U4), not in SQL
--        decided_at TEXT NOT NULL,
--        FK → posts.tweet_id ON DELETE CASCADE
--
--      The `flag_set` generated column requires SQLite 3.31.0+ (March
--      2020). If the host's SQLite is older, the migration apply will
--      fail at CREATE TABLE time and the operator must manually drop
--      the generated column + replace the index with a junction table.
--      The SQLite version is checked by Store.apply_migrations before
--      running the script body.
--
--      The idx_unsanctioned_flag_set index covers dashboard queries
--      like "posts with crypto flag = TRUE". Without it, the dashboard
--      query would full-scan.
--
-- Conventions (matches migration 026 + 019):
--   - INTEGER id PKs on enum lookup tables (per migration 018).
--   - TEXT natural-key PK on the new junction table (per migration 022
--     cleanup; matches posts_brands_signals which was rebuilt by
--     migration 019 with TEXT PKs).
--   - `_unattributed` is blocked at the application layer (mirrors the
--     019 sentinel handling).
--   - The migration runner toggles `PRAGMA foreign_keys = OFF` while
--     this script runs.
--
-- The hot cycle does NOT depend on this migration being applied — the
-- classifier guards every FK resolution with a `_known_*` check and
-- drops unknown values to the dead-letter log. So this migration can
-- ship in any commit relative to the rest of the post-fetch work.
--
-- _migrations ledger is updated by Store.apply_migrations AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- 1. post_type_keys (extend) + post_type_labels (add new rows)
-- ===========================================================================
-- Migration 019 created post_type_keys with `CREATE TABLE IF NOT EXISTS`,
-- so the table already exists; we only INSERT OR IGNORE the new keys.

INSERT OR IGNORE INTO post_type_keys (key, created_at) VALUES
    ('advertising_marketing', '2026-07-03T00:00:00+00:00'),
    ('event_announcement',    '2026-07-03T00:00:00+00:00');

INSERT OR IGNORE INTO post_type_labels (key, lang, label) VALUES
    ('advertising_marketing', 'en',    'Advertising & Marketing'),
    ('advertising_marketing', 'zh_cn', '广告与营销'),
    ('event_announcement',    'en',    'Event / Announcement'),
    ('event_announcement',    'zh_cn', '活动 / 公告');

-- ===========================================================================
-- 2. discourse_keys (extend) + discourse_labels (add new row)
-- ===========================================================================
-- Migration 026 created discourse_keys with a tight 9-key set (no `other`
-- bucket). We add ONE new key: advertising-marketing (hyphenated per KTD7).
-- Unknown keys from the LLM still coerce to `uncategorized` at the brief
-- renderer rather than being persisted.

INSERT OR IGNORE INTO discourse_keys (key, created_at) VALUES
    ('advertising-marketing', '2026-07-03T00:00:00+00:00');

INSERT OR IGNORE INTO discourse_labels (key, lang, label) VALUES
    ('advertising-marketing', 'en',    'Advertising / Marketing speak'),
    ('advertising-marketing', 'zh_cn', '广告 / 营销话术');

-- ===========================================================================
-- 3. posts_unsanctioned_flags — per-post persistent flags table
-- ===========================================================================
-- Stores the LLM-emitted unsanctioned_flags array as JSON TEXT. One row
-- per post_id (PRIMARY KEY). Per-post, not per-brand: a crypto scam is a
-- crypto scam regardless of which brand it mentions. See plan KTD2.
--
-- Security hardening (R14): the Store API layer (U4) enforces:
--   - evidence length cap at 1 KB
--   - control char strip (except \t\n\r)
--   - URL rejection (open-redirect / XSS surface on dashboard render)
-- The constraints are NOT in SQL because TEXT has no length limit in
-- SQLite — the Store layer is the boundary.

CREATE TABLE posts_unsanctioned_flags (
    post_id     TEXT NOT NULL,
    flags       TEXT NOT NULL,
    flag_set    TEXT GENERATED ALWAYS AS (json_extract(flags, '$')) STORED,
    evidence    TEXT,
    decided_at  TEXT NOT NULL,
    PRIMARY KEY (post_id),
    FOREIGN KEY (post_id) REFERENCES posts(tweet_id) ON DELETE CASCADE
);

CREATE INDEX idx_unsanctioned_flag_set
    ON posts_unsanctioned_flags(flag_set);

COMMIT;