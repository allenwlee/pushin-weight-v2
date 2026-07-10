-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 034: backfill brand_keywords for the 13 brands
-- that have zero entries in the live DB.
--
-- Plan: docs/plans/2026-07-10-001-feat-brand-keywords-backfill-plan.md
--
-- Background:
-- The probe_filter_yield script's `_kept_after_filter` (and any
-- production code that uses the same index) reads brand tokens from
-- `brand_keywords` via `store.read_brand_keywords()`. As of 2026-07-10
-- the table covers 8 of 20+ brands (deepseek, glm, inclusionai, llama,
-- minimax, moonshot_kimi, qwen, xiaomi_mimo). The 13 brands in
-- `enabled_models` listed below have zero entries, which makes the
-- probe return 0 kept for posts that clearly mention those brands
-- (e.g., a post with "Upstage" or "NeMo" in the body).
--
-- This migration is data-only: every row is an INSERT OR IGNORE.
-- Source is `data/queries/<brand>.yaml` Q2 paren groups (the
-- operator-curated source of truth), parsed via
-- `x_monitor.query_plan.parse_brand_tokens`. The static SQL below
-- is a snapshot of that parser's output at the time of writing.
--
-- Why both this migration AND a script (scripts/backfill_brand_keywords.py):
-- - This migration is the deterministic apply path — runs from
--   `store.apply_migrations`, useful for fresh DBs and CI seeding.
-- - The script is the dynamic path — picks up new tokens as yaml
--   files evolve, works against any DB. Operators who add a new
--   brand's yaml just rerun the script.
--
-- Future drift between yaml and this static migration is a known cost;
-- the script is the source of truth going forward.
--
-- Idempotency: every INSERT is INSERT OR IGNORE. The
-- brand_keywords.(brand_id, pattern) PK enforces uniqueness
-- across re-applies.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- doubao
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('doubao', 'Doubao', 0, datetime('now')),
    ('doubao', '豆包', 0, datetime('now')),
    ('doubao', 'Seed', 0, datetime('now')),
    ('doubao', '字节', 0, datetime('now')),
    ('doubao', 'ByteDance', 0, datetime('now')),
    ('doubao', 'Seed-VL', 0, datetime('now')),
    ('doubao', 'Seed-1.5', 0, datetime('now')),
    ('doubao', '豆包大模型', 0, datetime('now'));

-- ernie
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('ernie', 'ERNIE', 0, datetime('now')),
    ('ernie', '文心一言', 0, datetime('now'));

-- exaone
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('exaone', 'EXAONE', 0, datetime('now')),
    ('exaone', 'LG AI', 0, datetime('now')),
    ('exaone', 'LG EXAONE', 0, datetime('now'));

-- hunyuan
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('hunyuan', 'Hunyuan', 0, datetime('now')),
    ('hunyuan', '混元', 0, datetime('now')),
    ('hunyuan', '腾讯混元', 0, datetime('now'));

-- kuaishou
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('kuaishou', 'KwaiYii', 0, datetime('now')),
    ('kuaishou', '快意', 0, datetime('now')),
    ('kuaishou', 'KwaiYii LLM', 0, datetime('now')),
    ('kuaishou', 'Kuaishou', 0, datetime('now'));

-- mimo  (post-migration-030 rename; xiaomi_mimo is the legacy brand
-- and is already covered by existing entries)
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('mimo', 'MiMo', 0, datetime('now')),
    ('mimo', 'Xiaomi MiMo', 0, datetime('now')),
    ('mimo', '小米 MiMo', 0, datetime('now')),
    ('mimo', 'MiMo-V2.5-Pro', 0, datetime('now')),
    ('mimo', 'MiMo-V2.5', 0, datetime('now')),
    ('mimo', 'MiMo Code', 0, datetime('now')),
    ('mimo', 'MiMo-7B', 0, datetime('now')),
    ('mimo', 'MiMo-VL', 0, datetime('now')),
    ('mimo', '小米', 0, datetime('now'));

-- mistral
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('mistral', 'Mistral', 0, datetime('now')),
    ('mistral', 'Mixtral', 0, datetime('now'));

-- nemo_megatron
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('nemo_megatron', 'NeMo', 0, datetime('now')),
    ('nemo_megatron', 'Megatron', 0, datetime('now')),
    ('nemo_megatron', 'NVIDIA NeMo', 0, datetime('now')),
    ('nemo_megatron', 'Megatron-LM', 0, datetime('now'));

-- sakana_ai
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('sakana_ai', 'Sakana', 0, datetime('now')),
    ('sakana_ai', 'Sakana AI', 0, datetime('now')),
    ('sakana_ai', 'Sakana Labs', 0, datetime('now')),
    ('sakana_ai', 'サカナAI', 0, datetime('now'));

-- sensechat
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('sensechat', 'SenseChat', 0, datetime('now')),
    ('sensechat', 'SenseNova', 0, datetime('now')),
    ('sensechat', 'SenseTime', 0, datetime('now')),
    ('sensechat', '商汤', 0, datetime('now')),
    ('sensechat', '日日新', 0, datetime('now'));

-- stepfun
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('stepfun', 'StepFun', 0, datetime('now')),
    ('stepfun', '阶跃星辰', 0, datetime('now'));

-- upstage
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('upstage', 'Upstage', 0, datetime('now')),
    ('upstage', 'Solar', 0, datetime('now')),
    ('upstage', 'Solar Pro', 0, datetime('now')),
    ('upstage', 'Solar Mini', 0, datetime('now')),
    ('upstage', 'Solar Pro 3', 0, datetime('now')),
    ('upstage', 'Solar Pro 2', 0, datetime('now')),
    ('upstage', 'Solar Open', 0, datetime('now'));

-- yi
INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('yi', 'Yi', 0, datetime('now')),
    ('yi', '01.AI', 0, datetime('now')),
    ('yi', '零一万物', 0, datetime('now')),
    ('yi', 'Yi LLM', 0, datetime('now')),
    ('yi', 'Yi-VL', 0, datetime('now')),
    ('yi', 'Yi-Coder', 0, datetime('now')),
    ('yi', 'Yi-Large', 0, datetime('now'));

COMMIT;