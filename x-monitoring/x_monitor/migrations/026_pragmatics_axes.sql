-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 026: pragmatics axes — discourse_keys + nationalism_keys
-- + posts_brands_discourse.
--
-- Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
-- (Unit 1 of 8).
--
-- What this migration adds:
--   1. discourse_keys + discourse_labels — the 9-way pragmatic-register
--      vocabulary from docs/research/2026-06-26-v2-x-cn-pragmatics-translation-prompts-en.md
--      §2 (genuine_hype, sarcasm, dunk_yingyang, self_deprecation, cope,
--      fud, distillation_accusation, ai_slop_critique, absurdist_meme).
--      `discourse_keys` is INTENTIONALLY TIGHT — no `other` bucket — see
--      KTD5 in the plan and the pushin_weight reference at
--      `pushin_weight/core/models.py:618-623` (which calls out that
--      post_types / sentiments seed an `other` bucket for LLM-hallucinated
--      keys but discourse does NOT).
--
--   2. nationalism_keys + nationalism_labels — the 6-step scale
--      (none / mild_pro / pro / constructive_critical / anti / mixed)
--      shared across both `china_nationalism` and `us_nationalism` axes
--      per research §4.4. Per-axis label tables are deferred (matches
--      pushin_weight Q2-deferred decision at
--      `pushin_weight/core/models.py:664`).
--
--   3. posts_brands_discourse — per-act pragmatics signal junction.
--      Mirrors `pushin_weight/core/models.py::PostBrandDiscourse`:
--      composite PK `(post_id, brand_id, discourse_key, act_id)` where
--      `act_id` is a smallint allowing N speech-acts per (post × brand).
--      The two `*_nationalism` FKs are nullable during the backfill
--      window — U4's two-pass classifier first writes the discourse_key
--      then backfills nationalism in a second call.
--
-- Conventions (matches the rest of x_monitor's migration set):
--   - INTEGER PKs on enum lookup tables (per migration 018).
--   - INTEGER FK columns on the junction (per migration 020's
--     "string-in, INTEGER-out" Store pattern).
--   - The TEXT `key` / `label` columns are preserved as UNIQUE NOT NULL.
--   - `_unattributed` is blocked at the application layer in the new
--     Store methods (mirrors the post-020 sentinel handling in
--     `insert_posts_brands_signals`).
--   - The migration runner toggles `PRAGMA foreign_keys = OFF` while
--     this script runs (see Store.apply_migrations comment block).
--
-- The hot cycle does NOT depend on this migration being applied — the
-- call site (U4) guards every FK resolution with a `_known_*` check and
-- drops unknown values to the dead-letter log. So this migration can
-- ship in any commit relative to the rest of the post-fetch work.
--
-- _migrations ledger is updated by Store.apply_migrations AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- 1. discourse_keys + discourse_labels
-- ===========================================================================

CREATE TABLE discourse_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

INSERT OR IGNORE INTO discourse_keys (key, created_at) VALUES
    ('genuine_hype',              '2026-07-02T00:00:00+00:00'),
    ('sarcasm',                   '2026-07-02T00:00:00+00:00'),
    ('dunk_yingyang',             '2026-07-02T00:00:00+00:00'),
    ('self_deprecation',          '2026-07-02T00:00:00+00:00'),
    ('cope',                      '2026-07-02T00:00:00+00:00'),
    ('fud',                       '2026-07-02T00:00:00+00:00'),
    ('distillation_accusation',   '2026-07-02T00:00:00+00:00'),
    ('ai_slop_critique',          '2026-07-02T00:00:00+00:00'),
    ('absurdist_meme',            '2026-07-02T00:00:00+00:00');
-- (No `other` bucket — KTD5. Unknown keys coerce to `uncategorized` at
-- the brief renderer rather than being persisted.)

CREATE TABLE discourse_labels (
    key     TEXT NOT NULL,
    lang    TEXT NOT NULL,
    label   TEXT NOT NULL,
    PRIMARY KEY (key, lang),
    FOREIGN KEY (key) REFERENCES discourse_keys(key) ON DELETE CASCADE
);

INSERT OR IGNORE INTO discourse_labels (key, lang, label) VALUES
    ('genuine_hype',              'en',    'Genuine hype'),
    ('genuine_hype',              'zh_cn', '真心夸'),
    ('sarcasm',                   'en',    'Sarcasm / verbal irony'),
    ('sarcasm',                   'zh_cn', '反讽'),
    ('dunk_yingyang',             'en',    'Dunk / 阴阳怪气'),
    ('dunk_yingyang',             'zh_cn', '阴阳怪气 dunk'),
    ('self_deprecation',          'en',    'Self-deprecation'),
    ('self_deprecation',          'zh_cn', '自嘲'),
    ('cope',                      'en',    'Cope / 嘴硬'),
    ('cope',                      'zh_cn', '嘴硬 / 阿 Q'),
    ('fud',                       'en',    'FUD / 唱衰'),
    ('fud',                       'zh_cn', '唱衰 / 泼冷水'),
    ('distillation_accusation',   'en',    'Distillation / 套壳 accusation'),
    ('distillation_accusation',   'zh_cn', '套壳 / 蒸馏指控'),
    ('ai_slop_critique',          'en',    'AI slop critique'),
    ('ai_slop_critique',          'zh_cn', 'AI 整活 / AI 烂梗'),
    ('absurdist_meme',            'en',    'Absurdist meme'),
    ('absurdist_meme',            'zh_cn', '抽象整活');
-- (`uncategorized` is intentionally NOT seeded; the parser coerces
-- unknown keys to the literal string `uncategorized` rather than
-- persisting them.)

-- ===========================================================================
-- 2. nationalism_keys + nationalism_labels
-- ===========================================================================

CREATE TABLE nationalism_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

INSERT OR IGNORE INTO nationalism_keys (key, created_at) VALUES
    ('none',                  '2026-07-02T00:00:00+00:00'),
    ('mild_pro',              '2026-07-02T00:00:00+00:00'),
    ('pro',                   '2026-07-02T00:00:00+00:00'),
    ('constructive_critical', '2026-07-02T00:00:00+00:00'),
    ('anti',                  '2026-07-02T00:00:00+00:00'),
    ('mixed',                 '2026-07-02T00:00:00+00:00');

CREATE TABLE nationalism_labels (
    key     TEXT NOT NULL,
    lang    TEXT NOT NULL,
    label   TEXT NOT NULL,
    PRIMARY KEY (key, lang),
    FOREIGN KEY (key) REFERENCES nationalism_keys(key) ON DELETE CASCADE
);

INSERT OR IGNORE INTO nationalism_labels (key, lang, label) VALUES
    ('none',                  'en',    'None'),
    ('none',                  'zh_cn', '无'),
    ('mild_pro',              'en',    'Mild pro'),
    ('mild_pro',              'zh_cn', '温和亲'),
    ('pro',                   'en',    'Pro'),
    ('pro',                   'zh_cn', '亲'),
    ('constructive_critical', 'en',    'Constructive critical'),
    ('constructive_critical', 'zh_cn', '建设性批评'),
    ('anti',                  'en',    'Anti'),
    ('anti',                  'zh_cn', '反'),
    ('mixed',                 'en',    'Mixed'),
    ('mixed',                 'zh_cn', '混合');

-- ===========================================================================
-- 3. posts_brands_discourse — per-act pragmatics signal junction
-- ===========================================================================
-- Mirrors `pushin_weight/core/models.py::PostBrandDiscourse`:
--   - composite PK (post_id, brand_id, discourse_key, act_id) — supports
--     N speech-acts per (post × brand); v1 always writes `act_id = 1`.
--   - The two `*_nationalism` FKs are nullable during the backfill
--     window (U4 writes discourse_key first, then a follow-up call
--     backfills nationalism).
--   - FK columns store INTEGER ids (FKs to posts.id, brands.id,
--     discourse_keys.id, nationalism_keys.id) — matches migration 020's
--     "string-in, INTEGER-out" Store convention.

CREATE TABLE posts_brands_discourse (
    post_id            INTEGER NOT NULL,
    brand_id           INTEGER NOT NULL,
    discourse_key      INTEGER NOT NULL,
    act_id             INTEGER NOT NULL,
    china_nationalism  INTEGER,
    us_nationalism     INTEGER,
    PRIMARY KEY (post_id, brand_id, discourse_key, act_id),
    FOREIGN KEY (post_id)           REFERENCES posts(id)              ON DELETE CASCADE,
    FOREIGN KEY (brand_id)          REFERENCES brands(id)             ON DELETE SET NULL,
    FOREIGN KEY (discourse_key)     REFERENCES discourse_keys(id)     ON DELETE RESTRICT,
    FOREIGN KEY (china_nationalism) REFERENCES nationalism_keys(id)   ON DELETE RESTRICT,
    FOREIGN KEY (us_nationalism)    REFERENCES nationalism_keys(id)   ON DELETE RESTRICT,
    CHECK (act_id BETWEEN 1 AND 99)
);

CREATE INDEX idx_post_brand_dis_b_dr
    ON posts_brands_discourse(brand_id, discourse_key);

CREATE INDEX idx_post_brand_dis_b_cn_nat
    ON posts_brands_discourse(brand_id, china_nationalism);

CREATE INDEX idx_post_brand_dis_b_us_nat
    ON posts_brands_discourse(brand_id, us_nationalism);

COMMIT;