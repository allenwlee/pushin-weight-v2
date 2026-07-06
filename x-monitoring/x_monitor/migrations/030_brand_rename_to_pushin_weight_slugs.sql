-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 030: pushin_weight brand-rename + new brand/company rows.
--
-- Plan: docs/plans/2026-07-06-002-feat-pushin-weight-records-migration-plan.md
-- Unit 1 of 6 (U1 — Schema rename + new rows; the schema-side piece of the
-- pushin_weight seed migration; U4 is the data-side CLI script).
--
-- Background:
-- The pushin_weight Postgres database (the user's earlier fork of this
-- project, running locally on localhost:5432) uses a different brand
-- slug vocabulary than x_monitoring.db:
--
--   source  →  target (pre-030)
--   mimo    →  xiaomi_mimo
--   nemo_megatron →  nvidia_nemo
--   sakana_ai     →  sakana
--
-- Same accounts, different slugs. This migration aligns the target's
-- `brands.nickname` column with the source's vocabulary so future
-- ports (U4 CLI script) and dashboard lookups can use a single
-- canonical slug per brand.
--
-- Also adds 6 source-only brands (chatglm, sensenova, step, kwaiyii,
-- wenxin, seed — all sibling models of brands already in target) and
-- 9 source-only companies (meta, nvidia, bytedance, sensetime, lg_ai,
-- sakana, kuaishou_co, upstage_co, 01ai). The 9 company slugs use
-- the plan's target-side form (kuaishou_co, upstage_co) rather than
-- the source's bare 'kuaishou' / 'upstage' slugs — the suffix
-- visually distinguishes the company rows from the brand rows
-- (target's brands table also has 'kuaishou' and 'upstage' as
-- model-line brands). The alias YAML (U2) handles the source→target
-- slug mapping for the U4 data port.
--
-- Idempotency: PRAGMA foreign_keys=OFF wraps the rename/update block
-- because the rename touches `brands.nickname`, and child FK columns
-- in posts_brands_*, brand_search_terms, etc. hold INTEGER surrogate
-- ids (per migration 020/023) — not the nickname string. So the
-- rename is safe: surrogate ids are unchanged, all FK references
-- remain valid automatically. Re-enable FKs at the end. INSERT OR
-- IGNORE on the UNIQUE nickname constraint makes the brand and
-- company additions re-application-safe. The UPDATE statements are
-- no-ops on re-apply because the old slug is already gone.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- FKs disabled during the rename block as a safety measure. The child
-- columns (posts_brands_*, brand_search_terms.brand_id, etc.) hold
-- INTEGER surrogate ids, not nickname strings — so the rename is
-- safe with FKs on. The OFF/ON pair is belt-and-suspenders against
-- any future schema change that re-introduces a TEXT FK.
PRAGMA foreign_keys = OFF;

-- ===========================================================================
-- Section 1: brand renames (in-place UPDATE; no row count change)
-- ===========================================================================

UPDATE brands SET nickname = 'mimo'         WHERE nickname = 'xiaomi_mimo';
UPDATE brands SET nickname = 'nemo_megatron' WHERE nickname = 'nvidia_nemo';
UPDATE brands SET nickname = 'sakana_ai'     WHERE nickname = 'sakana';

-- ===========================================================================
-- Section 2: 6 new brand rows
-- accent_color values come from pushin_weight.brands (all placeholder
-- gray #9ca3af; the operator can tune later via a follow-up seed update,
-- mirroring migration 024's note about accent_color being a placeholder).
-- ===========================================================================

INSERT OR IGNORE INTO brands (nickname, display_name, accent_color,
                              is_sentinel, created_at,
                              display_name_en, display_name_zh_cn) VALUES
    -- chatglm: Zhipu's ChatGLM (sibling of glm in target)
    ('chatglm',   'ChatGLM',          '#9ca3af', 0, datetime('now'),
     'ChatGLM',   'ChatGLM'),

    -- sensenova: SenseTime SenseNova (sibling of sensechat in target)
    ('sensenova', 'SenseNova',        '#9ca3af', 0, datetime('now'),
     'SenseNova', '日日新'),

    -- step: Step (sibling of stepfun in target)
    ('step',      'Step',             '#9ca3af', 0, datetime('now'),
     'Step',      'Step'),

    -- kwaiyii: Kuaishou KwaiYii (sibling of kuaishou in target)
    ('kwaiyii',   'KwaiYii',          '#9ca3af', 0, datetime('now'),
     'KwaiYii',   '快意'),

    -- wenxin: Baidu Wenxin / 文小言 (sibling of ernie in target)
    ('wenxin',    'Wenxin / Wenxin',  '#9ca3af', 0, datetime('now'),
     'Wenxin',    '文小言'),

    -- seed: ByteDance Seed (sibling of doubao in target)
    ('seed',      'Seed',             '#9ca3af', 0, datetime('now'),
     'Seed',      'Seed');

-- ===========================================================================
-- Section 3: 9 new company rows
-- display_name + hq_country + display_name_en + display_name_zh_cn values
-- come from pushin_weight.companies. Slug form is the plan's target-side
-- (kuaishou_co, upstage_co) — see file header for rationale.
-- ===========================================================================

INSERT OR IGNORE INTO companies (nickname, display_name, hq_country,
                                 created_at,
                                 display_name_en, display_name_zh_cn) VALUES
    -- meta: Meta (Facebook). US hq.
    ('meta',        'Meta',              'US', datetime('now'),
     'Meta',         'Meta（元）'),

    -- nvidia: NVIDIA. US hq.
    ('nvidia',      'NVIDIA',            'US', datetime('now'),
     'NVIDIA',       '英伟达'),

    -- bytedance: ByteDance (字节跳动). CN hq. Parent of doubao brand.
    ('bytedance',   '字节跳动',          'CN', datetime('now'),
     'ByteDance',    '字节跳动'),

    -- sensetime: SenseTime (商汤科技). CN hq. Parent of sensechat brand.
    ('sensetime',   '商汤科技',          'CN', datetime('now'),
     'SenseTime',    '商汤科技'),

    -- lg_ai: LG AI Research. KR hq. Parent of exaone brand.
    ('lg_ai',       'LG AI연구원',       'KR', datetime('now'),
     'LG AI Research', 'LG AI研究院'),

    -- sakana: Sakana AI (サカナAI). JP hq. Parent of sakana_ai brand.
    ('sakana',      'サカナAI',          'JP', datetime('now'),
     'Sakana AI',    'Sakana AI'),

    -- kuaishou_co: Kuaishou Technology (快手科技). CN hq.
    -- Plan-side target slug; source's slug is 'kuaishou' (see file header).
    ('kuaishou_co', '快手科技',          'CN', datetime('now'),
     'Kuaishou Technology', '快手科技'),

    -- upstage_co: Upstage (업스테이지). KR hq.
    -- Plan-side target slug; source's slug is 'upstage' (see file header).
    ('upstage_co',  '업스테이지',        'KR', datetime('now'),
     'Upstage',     'Upstage'),

    -- 01ai: 零一万物. CN hq. Parent of yi brand.
    ('01ai',        '零一万物',          'CN', datetime('now'),
     '01.AI',       '零一万物');

PRAGMA foreign_keys = ON;

COMMIT;
