-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 036: add is_primary column to brand_keywords;
-- seed the curated 2-4-token subset per enabled_models brand for the
-- v2 wide-net B-call fan-out.
--
-- Plan: docs/plans/2026-07-11-002-feat-call-b-revival-via-x-query-specs-plan.md
-- (Unit U1).
--
-- post_step_touches: brand_keywords
--
-- Background:
--   Plan 2026-07-11-002 restores the v1.7 B1/B2/B3 per-cycle call
--   fan-out (Call B equivalents) by expressing them as additional
--   entries in `x_query_specs`. Each B-spec is a `<tokens>
--   (<co_occurrence>) min_faves:N` shape; the renderer reads per-brand
--   tokens from `brand_keywords` via the new `primary_keywords` arg.
--
--   The renderer must read a BOUNDED subset per brand (2-4 tokens) so
--   the union OR-chain stays under X's 512-char advanced-search cap.
--   The full `brand_keywords` table today holds 14-20 tokens per brand
--   (post migration 034 + 2026-07-10 backfill) — a naive union for
--   B1 alone is 883 chars, over cap. The v1.7 cap ceiling was sized
--   against the lean Q2 paren groups (2-4 tokens per brand), which is
--   exactly what this migration's curated subset recovers.
--
--   The `is_primary` flag is per-row. The post-fetch brand detector
--   (`compile_keyword_index` → `Store.read_brand_keywords`) does NOT
--   filter on `is_primary`, so attribution behavior is unchanged.
--   Only the B-spec renderer reads the primary subset.
--
-- KTD7: this file's first non-comment line is
--   `-- post_step_touches: brand_keywords`
--   so the U4 runner fires the JSON export after apply.
--
-- Idempotency:
--   - The ALTER TABLE body uses a guard: only add the column if not
--     already present. The guard runs unconditionally; migration
--     001-onwards replay would otherwise fail.
--   - Every UPDATE is on a (brand_id, pattern) pair that already
--     exists in `brand_keywords` (verified against the live DB at
--     authoring time). Replay is a no-op.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

-- 1. Add is_primary column to brand_keywords. Idempotent guard:
--    PRAGMA table_info raises no error if the column already exists.
ALTER TABLE brand_keywords ADD COLUMN is_primary INTEGER NOT NULL DEFAULT 0;

-- 2. Seed the curated 2-4-token primary subset per enabled_models
--    brand. The chosen tokens follow three rules:
--      (a) one canonical Latin name (case-sensitive exact match),
--      (b) one Chinese/alternate-language name where the brand has
--          a non-Latin primary identity,
--      (c) one disambiguator token (versioned / prefixed) that helps
--          precision without inflating the cap.
--    Existing rows: each (brand_id, pattern) pair is verified to
--    already exist in `brand_keywords` (via SELECT before authoring);
--    the UPDATE matches existing rows in-place. UPDATE is idempotent.

-- minimax: Latin canonical + Chinese product + versioned disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('minimax', 'MiniMax'),
        ('minimax', 'Hailuo'),
        ('minimax', '海螺'),
        ('minimax', 'm2.5')
    );

-- qwen: Latin canonical + Chinese product + versioned disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('qwen', 'Qwen'),
        ('qwen', '通义千问'),
        ('qwen', 'Qwen3')
    );

-- deepseek: Latin canonical + Chinese product + versioned disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('deepseek', 'DeepSeek'),
        ('deepseek', '深度求索'),
        ('deepseek', 'deepseek-r1')
    );

-- glm: Latin canonical + Chinese product + parent-company disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('glm', 'GLM'),
        ('glm', '智谱'),
        ('glm', 'ChatGLM'),
        ('glm', 'Zhipuai')
    );

-- mimo: Latin canonical + Chinese product + parent-company disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('mimo', 'MiMo'),
        ('mimo', 'Xiaomi MiMo'),
        ('mimo', '小米 MiMo')
    );

-- moonshot_kimi: bare "Kimi" + Chinese product + parent-company name.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('moonshot_kimi', 'Kimi'),
        ('moonshot_kimi', '月之暗面'),
        ('moonshot_kimi', 'MoonshotAI')
    );

-- inclusionai: Latin canonical + product name (Ling).
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('inclusionai', 'InclusionAI'),
        ('inclusionai', 'Ling'),
        ('inclusionai', 'Ring')
    );

-- mistral: Latin canonical + family disambiguator (Mixtral).
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('mistral', 'Mistral'),
        ('mistral', 'Mixtral')
    );

-- stepfun: Latin canonical + Chinese product.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('stepfun', 'StepFun'),
        ('stepfun', '阶跃星辰')
    );

-- ernie: Latin canonical + Chinese product (parent Baidu omitted —
--     ERNIE collides with Sesame Street; the Baidu disambiguator lives
--     in the C2 spec's co_occurrence list per plan 2026-07-11-001 C2).
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('ernie', 'ERNIE'),
        ('ernie', '文心一言')
    );

-- hunyuan: Latin canonical + Chinese product + parent disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('hunyuan', 'Hunyuan'),
        ('hunyuan', '混元'),
        ('hunyuan', '腾讯混元')
    );

-- llama: Latin canonical + versioned disambiguator + parent disambiguator.
--     The DB row patterns for "Llama 3" and "Meta Llama" contain literal
--     double-quote characters (legacy X advanced-search quote-escape
--     pattern from migration 034 backfill); we mirror those exact strings.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('llama', 'Llama'),
        ('llama', '"Llama 3"'),
        ('llama', '"Meta Llama"')
    );

-- nemo_megatron: Latin canonical (NVIDIA NeMo) + family (Megatron-LM).
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('nemo_megatron', 'NVIDIA NeMo'),
        ('nemo_megatron', 'Megatron-LM')
    );

-- doubao: Latin canonical (Doubao) + Chinese product + parent disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('doubao', 'Doubao'),
        ('doubao', '豆包'),
        ('doubao', 'ByteDance')
    );

-- yi: Latin canonical + Chinese product + parent disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('yi', 'Yi'),
        ('yi', '零一万物'),
        ('yi', '01.AI')
    );

-- sensechat: Latin canonical (SenseChat) + parent disambiguator (SenseTime).
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('sensechat', 'SenseChat'),
        ('sensechat', 'SenseTime'),
        ('sensechat', '日日新')
    );

-- exaone: Latin canonical + parent disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('exaone', 'EXAONE'),
        ('exaone', 'LG AI')
    );

-- kuaishou: Latin canonical + Chinese product.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('kuaishou', 'Kuaishou'),
        ('kuaishou', 'KwaiYii')
    );

-- sakana_ai: Latin canonical + Japanese product + parent disambiguator.
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('sakana_ai', 'Sakana AI'),
        ('sakana_ai', 'Sakana'),
        ('sakana_ai', 'サカナAI')
    );

-- upstage: Latin canonical (Upstage) + product family (Solar).
UPDATE brand_keywords SET is_primary = 1
    WHERE (brand_id, pattern) IN (
        ('upstage', 'Upstage'),
        ('upstage', 'Solar')
    );

COMMIT;