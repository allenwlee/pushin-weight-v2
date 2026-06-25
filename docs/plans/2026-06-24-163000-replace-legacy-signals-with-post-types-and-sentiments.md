---
title: "Replace Legacy signal_keys with post_types and sentiments"
type: refactor
status: planned
date: 2026-06-24
origin: conversation + taxonomy research + db-schema.md
---

# Replace Legacy signal_keys with post_types and sentiments

### written by Grok 4.3

## Overview

Drop the legacy `signal_keys` / `signal_labels` (and related references) that implement the old 6-signal classification (release, community_question, criticism, commenter_capture, praise, other).

Introduce proper `post_type_keys` / `post_type_labels` and `sentiment_keys` / `sentiment_labels` following the exact i18n lookup table pattern established in migration 008 (`signal_keys`, `role_keys`, `engagement_tier_keys`).

Update the classification storage (currently `posts_brands_signals.signal`) to use the new `post_type` and `sentiment` concepts. This aligns the DB with the simplified 4-bucket taxonomy (with subtypes) + categorical sentiment (Positive/Negative/Neutral/Mixed/Nuanced + optional tone) developed for DevRel use on wide-net brand collections.

The plan keeps the bilingual (en / zh_cn) label support, FK integrity, and per-locale display model.

## Background & Motivation

- Legacy signals were a coarse mix of type + sentiment baked into one enum. They no longer match the desired taxonomy (see `docs/research/2026-06-24-155117-simplified-taxonomy.md` and the fresh wide-net sampling in `2026-06-24-160500-fresh-sampling-methodology.md`).
- Wide-net collection (brand-name mentions only) + post-fetch classification requires clean separation of **Post Type** (what kind of post) from **Sentiment** (valence + nuance).
- Small English X volumes for Chinese models and need for simple DevRel UI drove the 4-bucket design.
- Existing schema conventions (migration 008, `db-schema.md`): enum values live in `*_keys` tables (PK `key`); display in `*_labels` (composite PK `(key, locale)`); FKs from fact tables; `PRAGMA foreign_keys = ON`.
- Sentiment will remain categorical (we keep the simple scale rather than numeric -5..+5).

## Post Types (4 Top-Level Buckets + Subtypes)

Primary navigation / filters. Every classified item gets one primary post_type (multi-label allowed for secondary in app layer).

### 1. Buzz & Releases (发布与热度)
- **Description**: Announcements, model drops, hype, viral shares, third-party amplification, memes about releases. Captures launch buzz and amplification.
- **Subtypes**:
  - Official release: Direct from brand/official accounts (e.g. from: handle announcements).
  - Third-party hype: Reposts, news amplification by others.
  - Viral/meme: Humorous or meme-driven spread.
- **Chinese label**: 发布与热度
- **Examples found** (from 2026-06-24 wide-net sampling):
  - Posts celebrating cost drops and new open-weights releases (e.g. "Zhipu GLM-5.2 shipped MIT-licensed with a 1M-token context" alongside MiniMax M3 compute cuts).
  - Ecosystem announcements and "China pushing frontier" summary posts.

### 2. Hands-on Usage (实际使用体验)
- **Description**: Real demos, agent runs, coding workflows, "I tried X for...", production stories, screenshots/videos. First-person or concrete usage reports.
- **Subtypes**:
  - Positive wins: Successful agentic/coding stories.
  - Mixed/qualified: Works for some things, fails for others.
  - Issues/bugs found: Tool-call problems, frustration in harnesses, production limitations.
- **Chinese label**: 实际使用体验
- **Examples found**:
  - "I tried for 30 minutes to use GLM-5.2 in Cline (VSCode). Maybe good in theory but it is so frustrating to use, with frequent tool call spills into the chat." (Mixed/qualified + issues).
  - DeepSeek usage at WeCom scale for billion daily users (positive production story).
  - "Kimi牛逼！！" in AI repair computer series (positive win).

### 3. Performance & Comparisons (性能与对比)
- **Description**: Benchmarks, leaderboards, head-to-head rankings ("better than Claude/Grok"), technical evals, real-world validation.
- **Subtypes**:
  - Pure benchmark: Score reports, harness results (SWE-bench, coding benchmarks).
  - Real-world validation: "chasing Opus", agent harness comparisons.
  - Direct vs competitor: "GLM-5.2 vs Claude", OSS rankings, "Chinese models catching up".
- **Chinese label**: 性能与对比
- **Examples found**:
  - "GLM-5.2在coding benchmark上追平Opus 4.8这个数据点很关键。" (Pure benchmark + real-world).
  - "OSS model rankings ... #1: GLM 5.2 (39%) #2: MiniMax M3 (22%) #3: Kimi K2.7 Code (21%)" (Direct comparisons).
  - Cost/performance discussions ("Inference cost per million tokens dropped roughly 100x... MiniMax M3 just cut compute another 20x").

### 4. Feedback & Questions (问题与建议)
- **Description**: Direct questions, feature requests, pricing complaints, bug reports, suggestions. Actionable input for DevRel.
- **Subtypes**:
  - How-to/questions: "how do I...?", tutorials implied.
  - Feature requests: "They should add...".
  - Criticisms/complaints: Pricing, usability, "nerfed", ecosystem complaints (e.g. personal users treated poorly).
- **Chinese label**: 问题与建议
- **Examples found**:
  - Doubao monetization discussions ("豆包开始收钱了", "字节吃相难看" vs commercial logic) — criticisms + questions about future pricing.
  - "智谱不缺企业用户，个人用户都是亏本... 把个人用户当猴耍" (Criticisms/complaints about ecosystem).
  - General "how to use harness" questions around GLM-5.2.

**Why these 4 + subtypes?** Keeps UI scannable. Subtypes live inside for drill-down. Data-driven from sampled X posts (English + Chinese discussions around Chinese models).

## Sentiments

Categorical (kept for labeling reliability, UI simplicity, and cultural fit). Separate from post_type. Optional tone flags can be stored alongside or in future extension.

### sentiment_keys

- **positive**: Clear positive valence, praise, success stories, "牛逼", cost wins, strong benchmarks.
  - Examples: Cost 100x drops post; "Kimi牛逼！！"; OSS rankings with Chinese models at top; "agentic maxxing".
- **negative**: Clear negative valence, frustration, "broken", pricing complaints, "翻车", "垃圾".
  - Examples: Limited (in recent samples); older criticism patterns like model "拉垮", harness frustration framed negatively.
- **neutral**: Factual reporting, no strong valence (specs, neutral links, pure announcements without hype/critique).
  - Examples: Straight "GLM-5.2 + 1M context + free tokens" questions without judgment.
- **mixed**: Nuanced — positive on one aspect, negative/weak on another; qualified ("good in theory but...").
  - Examples: "GLM-5.2 in Cline... good in theory but frustrating"; "追平... 实用门槛正在快速降低" (positive progress + implied remaining gaps); Doubao charging debates balancing commercial logic vs user frustration.

**Chinese labels** (for sentiment_labels):
- positive: 正面 / 称赞
- negative: 负面 / 批评
- neutral: 中性
- mixed: 混合 /  nuance (混合 / 细微差别)

**Tone / nuance notes** (optional flag, can be separate column or part of mixed):
- Sarcastic/Ironic (阴阳怪气): Common in Chinese platforms (exaggeration, indirect). Default underlying to negative/mixed. Example patterns: "智谱可以一直牛逼下去，把个人用户当猴耍".
- Direct vs Humorous: Captured in examples where relevant.

## Schema Changes (in keeping with db-schema.md and migration 008 pattern)

### Drop
- `signal_keys`
- `signal_labels`
- FK from `posts_brands_signals.signal`
- Related indexes (`idx_posts_brands_signals_brand_signal` will be updated)
- Any back-compat code for the 6 legacy signals

### Add (mirror exact structure)
```sql
-- post_type_keys
CREATE TABLE post_type_keys (
    key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

-- post_type_labels
CREATE TABLE post_type_labels (
    key TEXT NOT NULL,
    locale TEXT NOT NULL,
    label TEXT NOT NULL,
    PRIMARY KEY (key, locale),
    FOREIGN KEY (key) REFERENCES post_type_keys(key) ON DELETE CASCADE
);

-- sentiment_keys
CREATE TABLE sentiment_keys (
    key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

-- sentiment_labels
CREATE TABLE sentiment_labels (
    key TEXT NOT NULL,
    locale TEXT NOT NULL,
    label TEXT NOT NULL,
    PRIMARY KEY (key, locale),
    FOREIGN KEY (key) REFERENCES sentiment_keys(key) ON DELETE CASCADE
);
```

Update `posts_brands_signals` (or evolve to `posts_brands_classifications` if rename preferred for clarity):
- Replace `signal` column with:
  - `post_type TEXT NOT NULL`  (FK → post_type_keys.key)
  - `sentiment TEXT NOT NULL` (FK → sentiment_keys.key)
- Keep CHECK (brand_id <> _unattributed)
- Update indexes to `idx_posts_brands_classifications_brand_post_type_sentiment` etc.
- Adjust `posts_brands` if additional type weighting needed (but start with signals table for per-brand classification).

Foreign keys added in the rebuild migration:
FOREIGN KEY (post_type) REFERENCES post_type_keys(key) ON DELETE RESTRICT
FOREIGN KEY (sentiment) REFERENCES sentiment_keys(key) ON DELETE RESTRICT

Locale columns and backfill indexes follow the 007/008 pattern for consistency (en / zh_cn).

### Seeding (in migration)
Seed 4 post_type_keys + 8 labels (4 keys × 2 locales) with the full descriptions above embedded as comments or in a companion doc.

Seed 4 sentiment_keys + 8 labels, with descriptions + the "examples found" pulled from 2026-06-24 sampling.

### Migration Number
010_ replace_signal_with_post_types_and_sentiments.sql (after 009)

Steps in migration (like 008):
- CREATE new *_keys and *_labels
- Rebuild posts_brands_signals (add columns, FKs, drop old signal column)
- INSERT seeds with created_at = now
- Backfill existing rows by mapping legacy signals → best post_type + sentiment (use sampling examples + rules)
- Recreate indexes
- Drop signal_* tables

## Backfill & Data Migration
- One-time script (similar to 006 backfills) or in-migration UPDATE using heuristics:
  - "praise" / strong positive language → post_type based on content + sentiment=positive
  - "criticism" → negative or mixed
  - Benchmark-heavy → performance_comparisons + positive/negative
- Preserve history via new columns or audit rows if needed.
- Run `x-monitor` commands or direct SQL for verification.

## Code & App Impact (high level, for follow-up)
- Update `attribution.py` / classifier to emit post_type + sentiment instead of legacy signal.
- `store.py` insert paths, FK enforcement.
- `treemap.py` / polarity / dashboard: switch to new keys + labels (use `(key, locale)` join).
- `relevance.py`, run.py, query filters unchanged (still brand-centric).
- i18n overrides via `data/translations/` supported.
- Tests: update enum seeds, backfill tests, classification tests using the new detailed examples.
- Dashboard: filters now use post_type buckets + sentiment; subtypes as secondary pills or tags.

## Rollout & Verification
- New migration is forward-only.
- After apply: verify counts per post_type/sentiment per brand via SQL.
- Re-run recent wide-net samples through new classifier; compare to legacy.
- Update plans, research docs, and operator runbooks.
- Canary on one model first.

## Risks & Mitigations
- Backfill inaccuracy on old data → mitigate with conservative mapping + review queue for ambiguous.
- Label consistency for new classifier → use detailed descriptions + examples in prompts + human gold set from sampling.
- UI change for DevRel → keep 4-bucket navigation primary; subtypes secondary.
- Locale drift → seed both en/zh_cn from taxonomy docs.

## Next Steps
1. Implement 010 migration + seed with full descriptions/examples.
2. Wire classifier in attribution layer using taxonomy definitions.
3. Update dashboard + metrics queries.
4. Backfill + verification run.
5. Deprecate legacy signal paths.

**Related files**:
- `docs/research/2026-06-24-155117-simplified-taxonomy.md`
- `docs/research/2026-06-24-160500-fresh-sampling-methodology.md`
- `docs/reference/db-schema.md`
- `x_monitor/migrations/008_enum_i18n_lookup_tables.sql` (pattern)
- `x_monitor/attribution.py`, `store.py`, `treemap.py`

---

*Plan generated 2026-06-24 for taxonomy-aligned DB refactor.*
