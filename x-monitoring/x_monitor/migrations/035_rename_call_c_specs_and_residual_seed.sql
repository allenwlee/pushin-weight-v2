-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 035: residual-seed brand_keywords from
-- pre-computed yaml Q2 paren groups; create _applied_config_snapshot.
--
-- Plan: docs/plans/2026-07-11-001-feat-queries-and-filters-retire-and-export-poststep-plan.md
-- (Units U1, U4).
--
-- post_step_touches: brand_keywords,x_query_specs
--
-- Background:
--   Plan 2026-07-11-001 retires the per-brand `data/queries/*.yaml`
--   runtime read path (call B's token source) and consolidates onto
--   `brand_keywords` (DB) + `x_query_specs` (config). This migration
--   is the consolidation read: it pre-seeds `brand_keywords` with
--   every (brand, token) pair parsed from the yamls by
--   `x_monitor/migrations/_authoring/seed_residual_keywords.py`
--   (authoring-time only — the runner never invokes it).
--
--   On the live DB (where migration 034 + 2026-07-10 backfill already
--   populated the same surface), every row in the body below is a
--   no-op INSERT OR IGNORE. The seed is included so reviewers see the
--   consolidation explicitly in the same PR, and so fresh DBs seeded
--   via `Store.apply_migrations` end up at the same state without
--   needing to rerun the backfill script.
--
--   The migration also creates `_applied_config_snapshot` for the U4
--   post-step JSON export hash gate.
--
-- KTD7: this file's first non-comment line is
--   `-- post_step_touches: brand_keywords,x_query_specs`
--   so the U4 runner knows to fire the JSON export after apply.
--
-- Idempotency:
--   - Every INSERT is INSERT OR IGNORE.
--   - CREATE TABLE IF NOT EXISTS.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- 1. _applied_config_snapshot — content-hash gate for the U4
--    post-step JSON export. Single-row table; (artifact_name) PK.
CREATE TABLE IF NOT EXISTS _applied_config_snapshot (
    artifact     TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    written_at   TEXT NOT NULL
);

-- 2. Residual seed of brand_keywords from yaml Q2/Q3/Q5/Q6 paren
--    groups. Static SQL produced by
--    `x_monitor/migrations/_authoring/seed_residual_keywords.py`.
--    On the live DB (post migration 034 + backfill) every row is a
--    no-op; on a fresh DB this brings `brand_keywords` up to the
--    operator-curated state captured at authoring time.
--
    -- minimax
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('minimax', 'MiniMax', 0, datetime('now')),
    ('minimax', '海螺', 0, datetime('now')),
    ('minimax', 'Hailuo', 0, datetime('now'));

-- qwen
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('qwen', 'Qwen', 0, datetime('now')),
    ('qwen', '通义千问', 0, datetime('now')),
    ('qwen', '通义', 0, datetime('now')),
    ('qwen', 'Qwen3', 0, datetime('now'));

-- deepseek
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('deepseek', 'DeepSeek', 0, datetime('now')),
    ('deepseek', '深度求索', 0, datetime('now')),
    ('deepseek', '"DeepSeek V4"', 0, datetime('now'));

-- glm
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('glm', 'GLM', 0, datetime('now')),
    ('glm', '智谱', 0, datetime('now')),
    ('glm', 'ChatGLM', 0, datetime('now')),
    ('glm', 'Zhipuai', 0, datetime('now')),
    ('glm', '"GLM-5.2"', 0, datetime('now'));

-- mimo
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('mimo', 'MiMo', 0, datetime('now')),
    ('mimo', 'Xiaomi MiMo', 0, datetime('now')),
    ('mimo', '小米 MiMo', 0, datetime('now')),
    ('mimo', '"MiMo-V2.5-Pro"', 0, datetime('now')),
    ('mimo', '"MiMo-V2.5"', 0, datetime('now')),
    ('mimo', '"MiMo Code"', 0, datetime('now')),
    ('mimo', '"MiMo-7B"', 0, datetime('now')),
    ('mimo', '"MiMo-VL"', 0, datetime('now')),
    ('mimo', '小米', 0, datetime('now'));

-- moonshot_kimi
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('moonshot_kimi', 'Kimi', 0, datetime('now')),
    ('moonshot_kimi', '月之暗面', 0, datetime('now')),
    ('moonshot_kimi', 'MoonshotAI', 0, datetime('now')),
    ('moonshot_kimi', '"Kimi K2"', 0, datetime('now'));

-- inclusionai
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('inclusionai', 'InclusionAI', 0, datetime('now')),
    ('inclusionai', 'Ling', 0, datetime('now')),
    ('inclusionai', 'Ring', 0, datetime('now')),
    ('inclusionai', 'Ming', 0, datetime('now'));

-- mistral
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('mistral', '"Mistral"', 0, datetime('now')),
    ('mistral', '"Mixtral"', 0, datetime('now'));

-- stepfun
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('stepfun', '"StepFun"', 0, datetime('now')),
    ('stepfun', '"阶跃星辰"', 0, datetime('now'));

-- ernie
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('ernie', '"ERNIE"', 0, datetime('now')),
    ('ernie', '"文心一言"', 0, datetime('now'));

-- hunyuan
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('hunyuan', '"Hunyuan"', 0, datetime('now')),
    ('hunyuan', '"混元"', 0, datetime('now')),
    ('hunyuan', '"腾讯混元"', 0, datetime('now'));

-- llama
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('llama', 'Llama', 0, datetime('now')),
    ('llama', '"Llama 3"', 0, datetime('now')),
    ('llama', '"Llama 4"', 0, datetime('now')),
    ('llama', '"Meta Llama"', 0, datetime('now')),
    ('llama', '"Code Llama"', 0, datetime('now')),
    ('llama', '"Muse Spark"', 0, datetime('now')),
    ('llama', '"Llama 3.1"', 0, datetime('now'));

-- nemo_megatron
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('nemo_megatron', 'NeMo', 0, datetime('now')),
    ('nemo_megatron', 'Megatron', 0, datetime('now')),
    ('nemo_megatron', '"NVIDIA NeMo"', 0, datetime('now')),
    ('nemo_megatron', '"Megatron-LM"', 0, datetime('now'));

-- doubao
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('doubao', 'Doubao', 0, datetime('now')),
    ('doubao', '豆包', 0, datetime('now')),
    ('doubao', 'Seed', 0, datetime('now')),
    ('doubao', '字节', 0, datetime('now')),
    ('doubao', 'ByteDance', 0, datetime('now')),
    ('doubao', '"Seed-VL"', 0, datetime('now')),
    ('doubao', '"Seed-1.5"', 0, datetime('now')),
    ('doubao', '"豆包大模型"', 0, datetime('now'));

-- yi
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('yi', 'Yi', 0, datetime('now')),
    ('yi', '"01.AI"', 0, datetime('now')),
    ('yi', '零一万物', 0, datetime('now')),
    ('yi', '"Yi LLM"', 0, datetime('now')),
    ('yi', 'Yi-VL', 0, datetime('now')),
    ('yi', 'Yi-Coder', 0, datetime('now')),
    ('yi', '"Yi-Large"', 0, datetime('now'));

-- sensechat
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('sensechat', 'SenseChat', 0, datetime('now')),
    ('sensechat', 'SenseNova', 0, datetime('now')),
    ('sensechat', 'SenseTime', 0, datetime('now')),
    ('sensechat', '商汤', 0, datetime('now')),
    ('sensechat', '日日新', 0, datetime('now'));

-- exaone
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('exaone', 'EXAONE', 0, datetime('now')),
    ('exaone', '"LG AI"', 0, datetime('now')),
    ('exaone', '"LG EXAONE"', 0, datetime('now'));

-- kuaishou
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('kuaishou', 'KwaiYii', 0, datetime('now')),
    ('kuaishou', '快意', 0, datetime('now')),
    ('kuaishou', '"KwaiYii LLM"', 0, datetime('now')),
    ('kuaishou', 'Kuaishou', 0, datetime('now'));

-- sakana_ai
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('sakana_ai', 'Sakana', 0, datetime('now')),
    ('sakana_ai', '"Sakana AI"', 0, datetime('now')),
    ('sakana_ai', '"Sakana Labs"', 0, datetime('now')),
    ('sakana_ai', '"サカナAI"', 0, datetime('now'));

-- upstage
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('upstage', 'Upstage', 0, datetime('now')),
    ('upstage', 'Solar', 0, datetime('now')),
    ('upstage', '"Solar Pro"', 0, datetime('now')),
    ('upstage', '"Solar Mini"', 0, datetime('now')),
    ('upstage', '"Solar Pro 3"', 0, datetime('now')),
    ('upstage', '"Solar Pro 2"', 0, datetime('now')),
    ('upstage', '"Solar Open"', 0, datetime('now'));

COMMIT;