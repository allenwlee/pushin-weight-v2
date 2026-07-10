# Lookup Tables

Small, finite, name-only tables that constrain what the classifier (LLM-side)
and the parser (post-process) are allowed to emit. Their rows are referenced
via foreign key from the per-post signal/discourse tables.

**Why this exists.** Whenever a new taxonomy value is added, three places must
move together:

1. The `*_keys` SQL table gets a new row (via a migration).
2. The matching `_VALID_*` constant in `x_monitor/attribution.py` gets the
   new entry — the parser uses this to filter LLM emissions.
3. The classifier prompt's legend (in `build_pragmatics_full_prompt`) lists
   the value so the LLM knows to emit it.

For **brand additions** (covered in §6 below), the same principle applies
across the brand registry: the `brands` SQL table, the `KNOWN_MODELS`
frozenset in `x_monitor/config.py`, the `enabled_models` list in
`x-monitoring/config.yaml`, and the `data/accounts/<brand>.yaml`
file (the curated X-list + staff handles) must all move together.
Per-plan 2026-07-11-001, `data/queries/<brand>.yaml` is retired
(the runtime source for per-brand tokens is now `brand_keywords`,
a SQL table; see §"brand_keywords" below).

This doc is the single place to look up what's currently in the system, what
to add, and what the parser will reject.

**Source of truth.** The `*_keys` and `brands` / `companies` SQL tables in
`x_monitoring.db` are authoritative. The `_VALID_*` Python frozensets in
`attribution.py` and the `KNOWN_MODELS` frozenset in `config.py` are 1:1
mirrors used at parse / validation time. If they ever drift, the migration
is the canonical record; update the Python constant in the same commit.

---

## 1. `post_type_keys` — 6 values

**Referenced by:** `posts_brands_signals.post_type_key`

| id | key | notes |
|---|---|---|
| 1 | `buzz_releases` | hype about a new release / launch |
| 2 | `hands_on_usage` | "I tried it" — actual hands-on. **Also the parser's fallback sentinel** when the LLM emits an unrecognized value. The v12 plan's parser-layer demotion (plan 2026-07-06-001) actively moves posts *out* of this bucket when source-text markers fire. |
| 3 | `performance_comparisons` | benchmark / leaderboard / vs-other-model talk |
| 4 | `feedback_questions` | asking for help, comparisons, or opinions |
| 5 | `advertising_marketing` | salesy / CTA-heavy. U2a, migration 027. **Underscored**, not hyphenated (the discourse twin is hyphenated — see plan KTD7). |
| 6 | `event_announcement` | one-line release / "now live" / launch |

## 2. `sentiment_keys` — 4 values

**Referenced by:** `posts_brands_signals.sentiment_key`

| id | key | notes |
|---|---|---|
| 1 | `positive` | |
| 2 | `negative` | |
| 3 | `neutral` | **Also the parser's fallback sentinel** when the LLM emits an unrecognized sentiment. Like `hands_on_usage`, the value is overloaded. |
| 4 | `mixed` | same brand getting both positive and negative valence (e.g. critique that acknowledges a strength) |

## 3. `discourse_keys` — 10 values

**Referenced by:** `posts_brands_discourse.dr_key`

| id | key | notes |
|---|---|---|
| 1 | `genuine_hype` | straight praise |
| 2 | `sarcasm` | English verbal irony |
| 3 | `dunk_yingyang` | 阴阳怪气 / passive-aggressive dunk |
| 4 | `self_deprecation` | 自嘲 / self-mockery |
| 5 | `cope` | 嘴硬 / stubborn denial |
| 6 | `fud` | 唱衰 / spreading doom |
| 7 | `distillation_accusation` | 套壳 / 蒸馏指控 |
| 8 | `ai_slop_critique` | AI content-garbage accusation |
| 9 | `absurdist_meme` | 抽象整活 / absurdist antics |
| 10 | `advertising-marketing` | salesy / CTA-heavy. U2a, migration 027. **Hyphenated** (not underscored like the post_type twin — see plan KTD7). |

The parser also emits `uncategorized` as a **runtime sentinel** when nothing
matches. It is NOT in this table; it never gets persisted to
`posts_brands_discourse`.

## 4. `nationalism_keys` — 6 values

**Referenced by:** `posts_brands_signals.cn_key`, `posts_brands_signals.us_key`

| id | key | notes |
|---|---|---|
| 1 | `none` | **Also the parser's fallback sentinel.** Default when the LLM emits nothing. |
| 2 | `mild_pro` | sympathetic to the side, but not strongly |
| 3 | `pro` | clearly sympathetic |
| 4 | `constructive_critical` | critical of the side, but in a good-faith way |
| 5 | `anti` | clearly against the side |
| 6 | `mixed` | post has both pro- and anti- valence on the same axis |

Nationalism is an axis about which side of the US-China divide the post
sympathizes with, NOT about generic anti-vendor hostility. Rule 16 in the
classifier prompt (v12 calibration) was added precisely to prevent
"anti-vendor dunk" from being misread as "anti-China" or "anti-US".

## 5. `unsanctioned_flag_keys` — 4 values

**Not queried from prod here** (the migration table doesn't exist yet, or
the values live in the `unsanctioned_flag_keys` SQL table per the
`_VALID_UNSANCTIONED_FLAGS` allow-list in `attribution.py:1018`).

Per `attribution.py`:

| key | notes |
|---|---|
| `marketing_spam` | promotional content with no informational value |
| `scam` | obvious fraud / phishing |
| `crypto` | crypto-shilling, web3 promotion (rule 19) |
| `unauthorized` | impersonation / brand-misuse |

**Note:** this list is enforced as the parser's allow-list, but the
`*_keys` SQL table may not exist yet — values are filtered at parse time
in-memory. Confirm with `SELECT name FROM sqlite_master WHERE name LIKE
'%unsanctioned%';` if a future migration lands the table.

---

## 6. `brands` + `companies` — 20 enabled models (operator-curated registry)

**Source of truth:** the `brands` and `companies` tables in
`x_monitoring.db` (canonical). The `brands_companies` link table joins
them. The `enabled_models` list in `x-monitoring/config.yaml` is the
operator's run-time opt-in subset (subset of all known brands); see
`x_monitor.config.KNOWN_MODELS` (`x_monitor/config.py:18-41`) for the
code-side registry.

This doc lists the **20 brands currently in `enabled_models`**, in the
order they appear in `config.yaml`. Brand ids (`nickname`) are the
canonical handles used in `data/queries/<brand>.yaml`,
`data/accounts/<brand>.yaml`, `data/filters/<brand>.yaml`, and in the
post-`attribute_to_brands` regex routes.

| # | brand_id (`nickname`) | display name (EN / ZH) | parent company | hq | accent color | brand_keywords | spec coverage |
|---:|---|---|---|---|---|---:|---|
| 1  | `minimax`        | MiniMax AI / 海螺 AI          | MiniMax              | CN  | `#3b82f6` | 4  | C1 |
| 2  | `qwen`           | Qwen / 通义千问                | Alibaba              | CN  | `#f97316` | 4  | — |
| 3  | `deepseek`       | DeepSeek / 深度求索             | DeepSeek             | CN  | `#10b981` | 4  | — |
| 4  | `glm`            | Zhipu GLM / 智谱 GLM          | Zhipu AI             | CN  | `#a855f7` | 5  | — |
| 5  | `mimo`           | Xiaomi MiMo / 小米 MiMo        | Xiaomi               | CN  | `#eab308` | 14 | C1 |
| 6  | `moonshot_kimi`  | Moonshot Kimi / 月之暗面 Kimi  | Moonshot AI          | CN  | `#ec4899` | 4  | C1 |
| 7  | `inclusionai`    | InclusionAI / Ling/Ring/Ming   | Inclusion AI         | CN  | `#06b6d4` | 4  | — |
| 8  | `mistral`        | Mistral / Mixtral              | Mistral AI           | FR  | `#facc15` | 4  | — |
| 9  | `stepfun`        | StepFun / 阶跃星辰              | StepFun Inc          | CN  | `#22c55e` | 4  | — |
| 10 | `ernie`          | Baidu ERNIE / 文心一言          | Baidu                | CN  | `#0ea5e9` | 4  | C2 |
| 11 | `hunyuan`        | Tencent Hunyuan / 腾讯混元     | Tencent              | CN  | `#ec4899` | 6  | — |
| 12 | `llama`          | Meta Llama / Llama 3 / 4       | **Meta (unlinked)**  | US  | `#1877f2` | 9  | C1 |
| 13 | `nemo_megatron`  | NVIDIA NeMo / Megatron         | **NVIDIA (unlinked)**| US  | `#76b900` | 6  | — |
| 14 | `doubao`         | ByteDance Doubao / 豆包         | ByteDance            | CN  | `#000000` | 11 | — |
| 15 | `yi`             | 01.AI Yi / 零一万物            | 01.AI                | CN  | `#7c3aed` | 10 | C1 |
| 16 | `sensechat`      | SenseTime SenseChat / 商汤日日新| SenseTime            | CN  | `#ff6b00` | 5  | — |
| 17 | `exaone`         | LG EXAONE / LG AI Research     | **LG AI (unlinked)** | KR  | `#a50034` | 4  | — |
| 18 | `kuaishou`       | Kuaishou KwaiYii / 快意         | Kuaishou Technology  | CN  | `#ff4906` | 5  | — |
| 19 | `sakana_ai`      | Sakana AI / サカナAI           | Sakana AI            | JP  | `#1e40af` | 7  | — |
| 20 | `upstage`        | Upstage Solar / 업스테이지      | Upstage              | KR  | `#22c55e` | 12 | C1 |

**Country breakdown** (from `companies.hq_country`): **15 CN · 2 US · 2 KR · 1 FR · 1 JP.**

**Per-cycle calls** (plan 2026-07-11-002, post-B-revival):
- **Call A — list-based wide net** (`(list:<x_monitor_list_id>) min_faves:1`).
  The curated X-list, configured via `config.yaml.x_monitor_list_id`.
  Fans in everything from list members regardless of brand.
- **Call C1 / C2 (co-occurrence-constrained brand-wide, from
  `config.yaml.x_query_specs`):** C1 covers `mimo, moonshot_kimi,
  yi, upstage, llama` (5 brands; co-occurrence list stands at
  23 OR-terms; emits one extra API call per cycle). C2 covers `ernie`
  (single brand, disambiguated from Sesame Street via the
  co-occurrence AND-filter). C-specs read tokens from `spec.brands`
  (operator-curated, config-side).
- **Call B1 / B2 / B3 (wide-net brand-fan-in, plan 2026-07-11-002
  U3):** B1 covers 8 top-presence brands (`llama, minimax, qwen,
  deepseek, mistral, stepfun, ernie, hunyuan`); B2 covers 7
  Chinese-language brands (`doubao, glm, moonshot_kimi, mimo,
  sensechat, yi, inclusionai`); B3 covers 5 specialized brands
  (`nemo_megatron, exaone, sakana_ai, kuaishou, upstage`). Each
  B-spec is `is_wide_net: true` with an empty `brands:` map; the
  renderer reads per-brand tokens from `brand_keywords.is_primary=1`
  rows via the `primary_keywords` kwarg. Co-occurrence lists are
  shared with C1's 22-term set as a first cut. B1=473 chars,
  B2=470, B3=375 — all under the 512-char cap. Note: `mimo`,
  `moonshot_kimi`, `upstage`, `ernie`, and `llama` are in both
  B-groups AND C1/C2 — they get TWO calls per cycle; the operator
  can prune the duplicates if signal density drops.

The legacy `call_c_specs:` config key remains an alias for
`x_query_specs:` (auto-normalized at load) for v1.7.x compat.

**Per-cycle fan-out is exactly `len(x_query_specs) + 1` = 6 calls
(post-U3: A + C1 + C2 + B1 + B2 + B3).** TwitterAPI credit
consumption roughly doubled from the pre-U3 baseline (3 calls);
the daily `333` ceiling absorbs it.

### Other rows in `brands` not in `enabled_models`

The DB has more brand rows than the 20 listed above. They are present
in the schema but **not** opted-in via `enabled_models`, so they do not
participate in the live query plan:

| brand_id | nickname | display name | source |
|---:|---|---|---|
| 1  | `_unattributed` | Unattributed | sentinel — `is_sentinel=1`; every post falls here until attribution runs |
| 22 | `test_brand`   | Test         | smoketest fixture (`x-monitor/test/`); not a real model |
| 23 | `chatglm`      | ChatGLM      | **migration 030** (2026-07-06) — separate row from `glm` (the parent `zhipu` company already exists) |
| 24 | `sensenova`    | SenseNova    | **migration 030** (2026-07-06) — separate row from `sensechat` |
| 25 | `step`         | Step         | **migration 030** (2026-07-06) — separate row from `stepfun` |
| 26 | `kwaiyii`      | KwaiYii / 快意 | **migration 030** (2026-07-06) — same family as `kuaishou` |
| 27 | `wenxin`       | Wenxin / 文小言 | **migration 030** (2026-07-06) — same family as `ernie` (Baidu) |
| 28 | `seed`         | Seed         | **migration 030** (2026-07-06) — ByteDance model family |
| 29 | `gpt`          | GPT          | frontier seed — OpenAI (`openai` co. id 21). No query/account/filter yaml on disk. |
| 30 | `claude`       | Claude       | frontier seed — Anthropic (`anthropic` co. id 22). No query/account/filter yaml on disk. |
| 31 | `gemini`       | Gemini       | frontier seed — Google (`google` co. id 23). No query/account/filter yaml on disk. |
| 32 | `gemma`        | Gemma        | frontier seed — Google (`google` co. id 23). No query/account/filter yaml on disk. |
| 33 | `grok`         | Grok         | frontier seed — xAI (`xai` co. id 24). No query/account/filter yaml on disk. |

The frontier seeds (gpt/claude/gemini/gemma/grok) exist in the DB with
their parent companies linked, but `enabled_models` does not list them
yet, so they do not enter the live query plan. Migration 032 seeds them;
operator opt-in is a separate config change.

The migration-030 brand rows (chatglm/sensenova/step/kwaiyii/wenxin/seed)
are pre-staged as the schema-side complement of the U5 cross-cutting
brand renames; they exist so that the new names can be linked to
companies (and posts) without a follow-up migration.

### Known gap: 3 parent companies exist, 3 brand links missing

The `meta`, `nvidia`, and `lg_ai` company rows were inserted by
migration 030 (2026-07-06), but the corresponding `brands_companies`
rows have **not** been written yet. The DB therefore reports no parent
for:

- `llama` (id 13) — should link to `meta` (id 12)
- `nemo_megatron` (id 14) — should link to `nvidia` (id 13)
- `exaone` (id 18) — should link to `lg_ai` (id 16)

This is a known data-completeness gap, not a schema bug. The hq column
above shows the *expected* parent (US / US / KR) for clarity. A future
migration should `INSERT INTO brands_companies (brand_id, company_id)`
for these three pairs. Verify with:

```sql
SELECT b.nickname AS brand, c.nickname AS expected_parent
  FROM brands b
  JOIN companies c ON c.nickname IN ('meta', 'nvidia', 'lg_ai')
 WHERE b.nickname IN ('llama', 'nemo_megatron', 'exaone')
   AND NOT EXISTS (
     SELECT 1 FROM brands_companies bc
       WHERE bc.brand_id = b.id AND bc.company_id = c.id
   );
-- expected: 3 rows
```

### Inventory: per-brand official/staff handles

The runtime source of truth for per-brand `official` and `staff`
handles is the `brands_accounts` table joined to `accounts` and
`roles`, filtered to `role_id IN (2, 3)`. As of 2026-07-11 the
DB has 115 rows in `brands_accounts` (every yaml-listed handle
across the 20 enabled brands is mirrored). Operator contract:
edit handles via SQL migration inserting into `accounts` +
`brands_accounts`.

```sql
-- Add a new official handle to the minimax brand:
INSERT INTO accounts (author_id, handle) VALUES
    ('1234567890', 'NewMiniMaxHandle');
INSERT INTO brands_accounts (brand_id, accounts_id, role_id, added_at)
    SELECT b.id, a.id, r.id, datetime('now')
    FROM brands b, accounts a, roles r
    WHERE b.nickname = 'minimax'
      AND a.handle = 'NewMiniMaxHandle'
      AND r.key = 'official';
```

`data/accounts/*.yaml` is **retired** (plan 2026-07-11-002 U4).
The directory is deleted from the repo; the runtime reads from
DB, never from yaml. The post-step export `data/brands_accounts.json`
round-trips the current state for PR review.

`data/queries/*.yaml` is **retired** (plan 2026-07-11-001 U3).
The per-brand token source is now `brand_keywords` (a SQL table
populated by migration 034 + 035 + 036). The `data/queries/`
directory is deleted from the repo.

`data/filters/*.yaml` is **retired** (plan 2026-07-11-001 U3).
The relevance-filter step was the only consumer; the in-code
banned-token review-queue and low-engagement-filter steps remain.
The `data/filters/` directory is deleted from the repo.

Four brands have **no accounts yaml** (list-only): `mistral`,
`stepfun`, `ernie`, `hunyuan`. This is by design — those vendors
have no first-party handle in the curated brand-account list; they
are picked up by Call A's curated X-list (the operator can add
them on the X side) and by Call C's co-occurrence filter.

---

## Sentinel / taxonomy confusion

Three values are **overloaded** — they're both a real taxonomy entry AND
the parser's fallback:

- `post_type` → `hands_on_usage` (overloaded: real value + parse fallback)
- `sentiment` → `neutral` (overloaded: real value + parse fallback)
- `nationalism` → `none` (overloaded: real value + parse fallback)

The v12 plan's parser-layer demotion (`_post_process_pragmatics`) breaks
the `hands_on_usage` conflation by moving posts out when source-text
markers fire. The same is not yet done for `neutral` or `none` — those
remain conflated.

`discourse` → `uncategorized` is NOT overloaded: it's only a runtime
sentinel, never a taxonomy entry. If you see it in DB output, something
went wrong upstream.

## How to add a new value

1. **Migration:** add a new row to the `*_keys` table.
   ```
   -- example for a new post_type
   INSERT INTO post_type_keys (key, created_at) VALUES ('my_new_type', '...');
   ```
2. **Python constant:** add the same value to the matching `_VALID_*`
   frozenset in `x_monitor/attribution.py`. The parser uses this to filter
   LLM emissions — without this, the value will be silently dropped.
3. **Prompt legend:** update `build_pragmatics_full_prompt` so the LLM
   knows the new value exists. Without this, the LLM will never emit it.
4. **Test fixtures:** add the value to a regression fixture (e.g.
   `/tmp/v20_fixture.jsonl`) so the smoketest exercises it.
5. **This doc:** add the new row to the table above.
6. **Skill doc:** if it's a discourse/post_type/nationalism that operators
   will read in smoketest artifacts, update
   `~/.claude/skills/custom-claude-skills/pushin_weight_smoketest/SKILL.md`.

Steps 1, 2, 3, 5 should land in a single commit so they don't drift.
