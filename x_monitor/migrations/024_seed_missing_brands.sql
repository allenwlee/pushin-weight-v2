-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 024: seed the 9 v1.7 brands missing from the brands table.
--
-- Plan: docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md
-- Unit 3 of 6 (U3 — Resolve llama/yi FK-violation noise; operator-scoped
-- to register all 9 missing brands in one migration, not just llama/yi).
--
-- Background:
-- Migration 004 (the original company/brand/account model) seeded the
-- `brands` table with the 11 v1.6 brands (minimax, qwen, deepseek, glm,
-- xiaomi_mimo, moonshot_kimi, inclusionai, mistral, stepfun, ernie,
-- hunyuan). The 2026-06-25 v1.7 batch added 9 more brands to
-- `enabled_models` (llama, nvidia_nemo, doubao, yi, sensechat, exaone,
-- kuaishou, sakana, upstage) but never registered them in `brands`.
--
-- `compile_keyword_index` in x_monitor/run.py auto-seeds every
-- `enabled_models` entry as a body-keyword pattern, so the post-fetch
-- brand attribution can match `Llama` / `Doubao` / etc. in tweet text
-- and emit a brand_id. That brand_id has no row in `brands`, so the FK
-- constraint on `posts_brands.brand_id REFERENCES brands(id)` rejects
-- the write and the pipeline logs:
--
--   insert_posts: dropping posts_brands row for
--   brand_id='llama'/'yi'/'doubao'/... not in brands table
--
-- This migration backfills those 9 brands. display_name values mirror
-- the canonical English brand name used by the brand's vendor; the
-- account-handle column shows what the operator will see in the
-- dashboard. accent_color is a placeholder that an operator can tune
-- later via a follow-up seed update (no UI today).
--
-- Why we use INSERT OR IGNORE (and not ON CONFLICT DO NOTHING with a
-- partial index): the brands table has UNIQUE on `nickname` (the
-- migration 020 rebuild kept the original v1.6 uniqueness on the slug
-- column, now `nickname` post-023). INSERT OR IGNORE skips rows whose
-- nickname already exists, making the migration idempotent — re-applying
-- is a no-op, and it is safe against the (unlikely) case where a
-- future migration has already seeded any of these rows.
--
-- Why we do NOT add a separate FK reference or a sentinel row: the FK
-- is on `posts_brands.brand_id REFERENCES brands(id)`, which already
-- exists. We just need rows in `brands`. `_unattributed` (the sentinel
-- row id=1, is_sentinel=1) is left untouched.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- ===========================================================================
-- Backfill the 9 v1.7 brands. INSERT OR IGNORE is the idempotency guard;
-- re-applying the migration (e.g. on a DB whose 024 was already recorded
-- but someone wiped and re-ran) is safe.
-- ===========================================================================

INSERT OR IGNORE INTO brands (nickname, display_name, accent_color,
                              is_sentinel, created_at,
                              display_name_en, display_name_zh_cn) VALUES
    -- llama: Meta's open-weights LLM line. "Llama" + "Code Llama" + "Muse Spark"
    -- appear in data/queries/llama.yaml Q1; "Meta Llama" + "Llama 3/4" in Call C.
    ('llama',        'Meta Llama',          '#1877f2', 0, datetime('now'),
     'Meta Llama',   NULL),

    -- nvidia_nemo: NVIDIA NeMo (and Megatron). Single-token search risk
    -- ("NeMo" alone is short) is mitigated by data/filters/nvidia_nemo.yaml.
    ('nvidia_nemo',  'NVIDIA NeMo',         '#76b900', 0, datetime('now'),
     'NVIDIA NeMo',  NULL),

    -- doubao: ByteDance Doubao. Chinese: 豆包. Seeds display_name_zh_cn.
    ('doubao',       'ByteDance Doubao',    '#000000', 0, datetime('now'),
     'ByteDance Doubao', '豆包'),

    -- yi: 01.AI Yi. Chinese: 零一万物. Tokens overlap with common nouns
    -- ("yi" alone is noisy); the post-fetch filter handles it.
    ('yi',           '01.AI Yi',            '#7c3aed', 0, datetime('now'),
     '01.AI Yi',     '零一万物'),

    -- sensechat: SenseTime SenseChat (formerly 商汤日日新).
    ('sensechat',    'SenseTime SenseChat', '#ff6b00', 0, datetime('now'),
     'SenseTime SenseChat', '商汤日日新'),

    -- exaone: LG AI Research EXAONE.
    ('exaone',       'LG EXAONE',           '#a50034', 0, datetime('now'),
     'LG EXAONE',    NULL),

    -- kuaishou: Kuaishou KwaiYii (快意). display_name_zh_cn uses the
    -- brand-name token ("KwaiYii") rather than the parent company name
    -- ("Kuaishou") because the search query targets the model line.
    ('kuaishou',     'Kuaishou KwaiYii',    '#ff4906', 0, datetime('now'),
     'Kuaishou KwaiYii', '快意'),

    -- sakana: Sakana AI (Japanese: サカナAI). Tokens: "Sakana",
    -- "Sakana AI", "Sakana Labs", "サカナAI".
    ('sakana',       'Sakana AI',           '#1e40af', 0, datetime('now'),
     'Sakana AI',    'サカナAI'),

    -- upstage: Upstage Solar. Korean: 업스테이지. The Call C spec
    -- already uses "업스테이지" as a token (see config.yaml call_c_specs
    -- upstage entry, added 2026-06-25).
    ('upstage',      'Upstage Solar',       '#22c55e', 0, datetime('now'),
     'Upstage Solar', '업스테이지');

COMMIT;