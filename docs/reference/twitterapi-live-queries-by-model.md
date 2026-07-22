<!-- {{AGENT_ATTRIBUTION}} -->
# TwitterAPI.io live queries — v2 (20 brands, A + B1/B2/B3 + C1/C2)

Last updated: 2026-07-22-12:35:35

**v2 architecture (plan 2026-07-11-001 + 2026-07-11-002).** The v1.7-era
`data/queries/<brand>.yaml` (Q1–Q6), `data/accounts/<brand>.yaml`, and
`data/filters/<brand>.yaml` files are **all retired**. The live cycle
now sources:
- **Call A**: the curated public X-list (`x_monitor_list_id` in `config.yaml`)
- **Call C specs (C1, C2)**: co-occurrence-constrained per-brand queries
  with tokens inline in `config.yaml::x_query_specs[].brands`
- **Call B specs (B1, B2, B3)**: wide-net per-brand queries with tokens
  loaded from the `brand_keywords` DB table (`is_primary=1` rows) and
  AND-filtered through the same 22-term co-occurrence list as C1/C2
- **Official handles**: loaded from `brands_accounts` + `accounts` DB
  tables (join on `roles.key = 'official'`), NOT from YAML files

One uniform renderer (`_build_query` in `query_plan.py`) handles every
spec — Call A (list-based degenerate), Call C-body
(`<tokens> (<co_occurrence>) min_faves:N`), and wide-net B-call (same
shape, tokens from DB). KTD1 forbids additional renderers per call kind.

**Q1–Q6 status.** `VALID_QUERY_IDS` still exists as a constant in
`config.py:48` but the live cycle never reads it — the per-cycle call
set is `(A, B1, B2, B3, C1, C2)`. The legacy `_planned_call_to_query()`
in `run.py` returns `"Q5"` as a hardcoded placeholder for backward compat
with the `call_state` cursor schema; the value is meaningless and never
reaches the DB path for new calls.

**Source of truth:** code on `main` of
`/Users/fuchitalee/development/minimax-marketing/x-monitoring/`
- `config.yaml::enabled_models` (20 brands), `config.yaml::x_query_specs` (5 specs: C1, C2, B1, B2, B3), `config.yaml::call_b_groups` (3 groups, for validation)
- `x_monitor/config.py::KNOWN_MODELS` (frozenset of 20), `VALID_CALL_IDS` (A, B1, B2, B3, C1, C2)
- `x_monitor/query_plan.py::plan_calls(...)` — v2 call planner with uniform `_build_query` renderer
- `x_monitor/store.py::Store.read_primary_brand_keywords()` — loads `brand_keywords WHERE is_primary=1`
- `x_monitor/apify.py::TwitterApiClient.run_search(query, max_results, since_time, until_time)` — the live HTTP path
- `x_monitor/run.py` — cycle orchestrator (watchpath-driven via LaunchAgent)

> **Pipeline:** the cycle resolves the `enabled_models` list, builds a
> **6-call plan** (1 Call A + 5 `x_query_specs` entries: C1 + C2 + B1 + B2 + B3),
> and fires each `PlannedCall.query_string` against TwitterAPI.io's
> `advanced_search` endpoint. `assert_under_length_cap(query_string, 512)`
> guards every emitted call.

## How it all fits together

A macOS LaunchAgent (`deploy/com.fuchitalee.x-monitor.plist`) invokes
the pipeline on a `config.yaml` WatchPaths trigger with
`ThrottleInterval=300` (minimum 5-minute gap between consecutive runs).

Each invocation:

1. **Plan calls.** Load `config.yaml::x_query_specs`, resolve primary
   brand keywords from the DB (`Store.read_primary_brand_keywords`),
   build per-cycle query strings via `query_plan.plan_calls()`. Emit
   6 calls: Call A (curated X-list), C1/C2 (co-occurrence-constrained),
   B1/B2/B3 (wide-net with co-occurrence AND-filter).

2. **Fetch posts.** Fire each query against TwitterAPI.io's
   `advanced_search` endpoint. Max 50 tweets per call (configurable via
   `config.yaml::search`), paginated 20 per page, up to 5 pages.

3. **Attribute brands.** For each tweet, match against `brand_keywords`,
   `brand_hashtags`, and `brand_search_terms` in the DB. Each match is one
   row in `posts_brands_mentions`; the unique brand list is one row per
   brand in `posts_brands` (with a fractional weight — 1/N if N brands
   matched, 1.0 if just one).

4. **Classify.** For each (tweet, brand) pair, the post-fetch pipeline
   (`attribution.classify_pragmatics_full`) writes `post_type`,
   `sentiment`, `discourse_role`, `china_nationalism`, and
   `us_nationalism` into `posts_brands_signals`.

5. **Translate.** Non-English posts get `text_en` (English translation)
   via LLM; English posts get `text_zh_cn` (Simplified Chinese
   translation).

**What the config decides vs what the DB decides.** The config
(`x_query_specs` + `brand_keywords.is_primary=1`) decides what we ask X
for (the search strings). The DB tables (`brand_keywords`,
`brand_hashtags`, `brand_search_terms`) decide what we found (which
brands are mentioned in each returned tweet, and how). The two registries
are kept in sync by hand: a token added to `brand_keywords` won't be in
the live query unless it also has `is_primary=1`.

---

## At-a-glance inventory

| Stat | Value |
|---|---|
| Enabled brands (`config.yaml::enabled_models`) | **20** |
| `KNOWN_MODELS` (frozenset in `config.py`) | **20** |
| `brand_keywords` rows (total) | **207** |
| `brand_keywords` rows (`is_primary=1`) | **55** across 20 brands |
| Primary tokens per brand | **2–4** (curated subset: the high-signal tokens that fit under the 512-char cap) |
| `x_query_specs` entries | **5** (C1, C2, B1, B2, B3) |
| Plan size per cycle (live) | **6 calls** (1 Call A + 5 specs) |
| Call A length | **38 chars** |
| Live call-string lengths | **A 38 / C1 461 / C2 295 / B1 414 / B2 377 / B3 353** (all under 512-char cap) |
| `degraded_skip_order` | B3 → B2 → B1 → C2 → C1 → A |
| Co-occurrence terms (C1/C2/B1/B2/B3) | **22 terms** (C1/B1/B2/B3); **20 terms** (C2 — drops `xiaomi`/`小米`, adds `baidu`/`文心`) |

> **✅ `plan_calls` signature:** `plan_calls(x_monitor_list_id, x_query_specs, *, primary_keywords=None)`.
> The wide-net B-specs (B1/B2/B3) have `is_wide_net: true` and read
> per-brand tokens from `primary_keywords` (pre-loaded from
> `brand_keywords WHERE is_primary=1`). Non-wide-net specs (C1/C2)
> read tokens inline from `spec.brands`.

---

## Call A — curated public x.com list (1 call/cycle)

**Shape:** `(list:2067062923525275922) min_faves:0`
**Length:** 38 characters.
**Source of truth:** `config.yaml::x_monitor_list_id = 2067062923525275922` (operator-managed public x.com list; every enabled brand's official handle from `brands_accounts` + `accounts` DB tables should be on the list).

The list is the only place the operator maintains handle membership. Adding an account to the DB does NOT auto-add to the x.com list — that is a manual operator step.

**Official handles today** (from `brands_accounts` JOIN `accounts` JOIN `roles` WHERE `roles.key = 'official'`):

| # | brand_id | Official handle | Verified |
|---|---|---|---|
| 1 | `minimax` | `MiniMax_AI` | false |
| 2 | `qwen` | `Alibaba_Qwen` | false |
| 3 | `deepseek` | `deepseek_ai` | false |
| 4 | `glm` | `Zai_org` | false |
| 5 | `mimo` | `XiaomiMiMo` | false |
| 6 | `moonshot_kimi` | `Kimi_Moonshot` | false |
| 7 | `inclusionai` | `TheInclusionAI` | false |
| 8 | `llama` | `AIatMeta` | false |
| 9 | `nemo_megatron` | `NVIDIAAIDev` | false |
| 10 | `doubao` | `DoubaoAI` | false |
| 11 | `yi` | `01AI_Yi` | false |
| 12 | `sensechat` | `SenseTime_AI` | false |
| 13 | `exaone` | `LG_AI_Research` | false |
| 14 | `kuaishou` | `Kling_ai` | false |
| 15 | `sakana_ai` | `SakanaAILabs` | false |
| 16 | `upstage` | `upstageai` | false |
| 17 | `mistral` | `MistralAI` | false |
| 18 | `stepfun` | `StepFun_ai` | false |
| 19 | `ernie` | `ErnieforDevs` | false |
| 20 | `hunyuan` | `TencentHunyuan` | false |

All 20 enabled brands have at least one official account row. Several
brands also have secondary official handles (e.g., `minimax` also has
`MiniMaxAgent` and `hailuo_ai`; `doubao` also has `BytePlusGlobal`,
`bytedanceoss`, `doubaoai`). The Call A list ID covers all handles the
operator has added to the public X-list.

**`staff:` role accounts** also exist in `brands_accounts` for most
brands (not listed here for brevity). The list-membership step is manual
— the operator must add staff handles to the X-list separately.

---

## Call C specs — co-occurrence-constrained brand-wide

Configured in `config.yaml::x_query_specs` — entries where
`is_wide_net` is absent or `false`. Two specs are live:

### C1 — mimo + moonshot_kimi + yi + llama (4 brands, 22 co-occurrence terms)

**`call_id: C1`**, **4 brands, 22 co-occurrence terms.**

**Primary group tokens (inline in `config.yaml`):**
- `mimo`: `[MiMo, "Xiaomi MiMo", "小米 MiMo"]`
- `moonshot_kimi`: `[Kimi, "Moonshot AI", 月之暗面, 暗面, MoonshotAI]`
- `yi`: `[Yi, "01.AI", 零一万物, "Yi LLM", Yi-VL, Yi-Coder]`
- `llama`: `[Llama, "Llama 3", "Llama 4", "Meta Llama", "Code Llama", "Muse Spark"]`

**Co-occurrence group:** `[api, llm, model, xiaomi, 小米, moonshot, chatbot, weights, gguf, ollama, code, coding, agent, agentic, benchmark, reasoning, release, "open source", huggingface, inference, moe, "tool calling"]`

**Shape (live, from `_build_query`):**
```
((MiMo OR Xiaomi MiMo OR 小米 MiMo) OR (Kimi OR Moonshot AI OR 月之暗面 OR 暗面 OR MoonshotAI) OR (Yi OR 01.AI OR 零一万物 OR Yi LLM OR Yi-VL OR Yi-Coder) OR (Llama OR Llama 3 OR Llama 4 OR Meta Llama OR Code Llama OR Muse Spark)) (api OR llm OR model OR xiaomi OR 小米 OR moonshot OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 461 characters. Headroom: 51 chars (10% of the cap).

**Why this exists:** these 4 brands' bare tokens collide with unrelated common nouns:
- `MiMo` → Mimo Studio (kids' video app); `xiaomi` alone → phone posts.
- `Kimi` → Turkish interrogative ("who?") and Japanese second-person pronoun (きみ); bare `moonshot` → Moonshot crypto exchange (intentionally absent from the brand group).
- `Yi` → common Chinese surname and dynasty name.
- `Llama` → the animal.

Co-occurrence terms exclude non-AI false positives. The `must_have_none`
filter in `brand_keywords` (via is_primary=0 patterns) further softens
F1-driver Kimi Antonelli hijacks for `moonshot_kimi`.

**2026-07-11:** `upstage` was moved from C1 to C2 to fix a substring
leak — bare `Solar` in C1's Upstage OR-group matched "solar winds" in
the co-occurrence AND-filter, producing false positives for everyday
"solar" English text.

### C2 — ernie + upstage (2 brands, 20 co-occurrence terms)

**`call_id: C2`**, **2 brands, 20 co-occurrence terms.**

**Primary group tokens (inline in `config.yaml`):**
- `ernie`: `[ERNIE, 文心一言]`
- `upstage`: `[Upstage, "Solar Pro", "Solar LLM", 업스테이지]`

**Co-occurrence group:** Same 22-term list as C1 with 2 swaps:
- **Dropped:** `xiaomi`, `小米` (ERNIE-irrelevant)
- **Added:** `baidu`, `文心` (Baidu/ERNIE disambiguators)

**Shape (live, from `_build_query`):**
```
((ERNIE OR 文心一言) OR (Upstage OR Solar Pro OR Solar LLM OR 업스테이지)) (api OR llm OR model OR baidu OR 文心 OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 295 characters. Headroom: 217 chars (42% of the cap).

**Why this exists:**
- `ERNIE` collides with the Sesame Street character and the Bert variant. C1 had only 7 chars of headroom — adding ERNIE's paren group would have exceeded the cap, so it got its own spec (C2).
- `Upstage` was moved here from C1 (2026-07-11). Bare `Solar` is intentionally DROPPED from the Upstage OR-group — it matched substring "solar" in everyday English ("solar wind", "solar panel", "solar energy"). The three product-name tokens (`"Solar Pro"`, `"Solar LLM"`, `업스테이지`) keep precision-recall intact for actual Upstage coverage.

---

## Call B specs — wide-net with co-occurrence AND-filter

Three `x_query_specs` entries with `is_wide_net: true`. Each renders a
`(<per-brand paren groups>) (<co-occurrence>) min_faves:0` query where
per-brand tokens come from `brand_keywords.is_primary=1` rows (loaded
once per cycle via `Store.read_primary_brand_keywords()`).

The co-occurrence filter is the same 22-term list as C1. This means
the B-specs are **AND-filtered** — a tweet must mention both a brand
token AND a co-occurrence term. This is a change from the v1.7 B-calls
which had no co-occurrence filter (bare OR-chains).

### B1 — top-presence / global brands (6 brands, 414 chars)

**`wide_net_brands`:** `[minimax, qwen, deepseek, mistral, stepfun, hunyuan]`

**Shape (live, from `_build_query`):**
```
((Hailuo OR MiniMax OR m2.5 OR 海螺) OR (Qwen OR Qwen3 OR 通义千问) OR (DeepSeek OR deepseek-r1 OR 深度求索) OR (Mistral OR Mixtral) OR (StepFun OR 阶跃星辰) OR (Hunyuan OR 混元 OR 腾讯混元)) (api OR llm OR model OR xiaomi OR 小米 OR moonshot OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 414 characters. Headroom: 98 chars (19% of the cap).

| # | brand_id | Primary tokens (from DB) | Count |
|---|---|---|---|
| 1 | `minimax` | `Hailuo`, `MiniMax`, `m2.5`, `海螺` | 4 |
| 2 | `qwen` | `Qwen`, `Qwen3`, `通义千问` | 3 |
| 3 | `deepseek` | `DeepSeek`, `deepseek-r1`, `深度求索` | 3 |
| 4 | `mistral` | `Mistral`, `Mixtral` | 2 |
| 5 | `stepfun` | `StepFun`, `阶跃星辰` | 2 |
| 6 | `hunyuan` | `Hunyuan`, `混元`, `腾讯混元` | 3 |

**Dedup note:** The original v1.7 B1 included `llama` and `ernie` (8
brands). Per the 2026-07-13-002 U4 dedup, those brands are covered
exclusively by C1 and C2 respectively (co-occurrence-constrained) to
avoid duplicate TwitterAPI credit spend on the wide-net path.

### B2 — Chinese-language brands (4 brands, 377 chars)

**`wide_net_brands`:** `[doubao, glm, sensechat, inclusionai]`

**Shape (live, from `_build_query`):**
```
((ByteDance OR Doubao OR 豆包) OR (ChatGLM OR GLM OR Zhipuai OR 智谱) OR (SenseChat OR SenseTime OR 日日新) OR (InclusionAI OR Ling OR Ring)) (api OR llm OR model OR xiaomi OR 小米 OR moonshot OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 377 characters. Headroom: 135 chars (26% of the cap).

| # | brand_id | Primary tokens (from DB) | Count |
|---|---|---|---|
| 1 | `doubao` | `ByteDance`, `Doubao`, `豆包` | 3 |
| 2 | `glm` | `ChatGLM`, `GLM`, `Zhipuai`, `智谱` | 4 |
| 3 | `sensechat` | `SenseChat`, `SenseTime`, `日日新` | 3 |
| 4 | `inclusionai` | `InclusionAI`, `Ling`, `Ring` | 3 |

**Dedup note:** The original v1.7 B2 included `moonshot_kimi`, `mimo`,
and `yi` (7 brands). Per the 2026-07-13-002 U4 dedup, those brands are
covered exclusively by C1.

### B3 — specialized / smaller brands (4 brands, 353 chars)

**`wide_net_brands`:** `[nemo_megatron, exaone, sakana_ai, kuaishou]`

**Shape (live, from `_build_query`):**
```
((Megatron-LM OR NVIDIA NeMo) OR (EXAONE OR LG AI) OR (Sakana OR Sakana AI OR サカナAI) OR (Kuaishou OR KwaiYii)) (api OR llm OR model OR xiaomi OR 小米 OR moonshot OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 353 characters. Headroom: 159 chars (31% of the cap).

| # | brand_id | Primary tokens (from DB) | Count |
|---|---|---|---|
| 1 | `nemo_megatron` | `Megatron-LM`, `NVIDIA NeMo` | 2 |
| 2 | `exaone` | `EXAONE`, `LG AI` | 2 |
| 3 | `sakana_ai` | `Sakana`, `Sakana AI`, `サカナAI` | 3 |
| 4 | `kuaishou` | `Kuaishou`, `KwaiYii` | 2 |

**Dedup note:** The original v1.7 B3 included `upstage` (5 brands). Per
the 2026-07-13-002 U4 dedup, `upstage` is covered exclusively by C2.

### What happens if `call_b_groups` is `None` (historical / fallback only)

`plan_calls` (`query_plan.py`) does NOT use `call_b_groups` for query
construction — the `x_query_specs` entries with `is_wide_net: true` are
the canonical source for B1/B2/B3. `call_b_groups` is validated by
`Config._warn_on_call_b_call_c_duplicates` (emits a warning if a brand
appears in both `call_b_groups` and any C-spec) but has no effect on
the emitted query plan.

---

## Per-brand breakdown (20 brands)

Every brand listed in `config.yaml::enabled_models` is documented below.
All data comes from the DB — primary tokens from `brand_keywords`
(`is_primary=1`), official handles from `brands_accounts` JOIN
`accounts` JOIN `roles` (`roles.key = 'official'`).

There are no per-brand YAML files. The Q1–Q6 query taxonomy
(release/community_question/criticism/commenter_capture/other/praise) is
retired — the v2 architecture uses a single query shape per call kind:
`<tokens> (<co_occurrence>) min_faves:N`.

### 1. `minimax` (MiniMax / Hailuo)

- **Official handle:** `@MiniMax_AI` (also: `@MiniMaxAgent`, `@hailuo_ai`)
- **Primary tokens (4):** `Hailuo`, `MiniMax`, `m2.5`, `海螺`
- **Call group:** B1
- **Covered by:** Call A (X-list) + B1 (wide-net with co-occurrence)

### 2. `qwen` (Alibaba Qwen / 通义千问)

- **Official handle:** `@Alibaba_Qwen` (also: `@Ali_TongyiLab`)
- **Primary tokens (3):** `Qwen`, `Qwen3`, `通义千问`
- **Call group:** B1
- **Covered by:** Call A + B1

### 3. `deepseek` (DeepSeek / 深度求索)

- **Official handle:** `@deepseek_ai`
- **Primary tokens (3):** `DeepSeek`, `deepseek-r1`, `深度求索`
- **Call group:** B1
- **Covered by:** Call A + B1

### 4. `glm` (Zhipu AI / 智谱)

- **Official handle:** `@Zai_org` (also: `@ZhihuFrontier`)
- **Primary tokens (4):** `ChatGLM`, `GLM`, `Zhipuai`, `智谱`
- **Call group:** B2
- **Covered by:** Call A + B2

### 5. `mimo` (Xiaomi MiMo)

- **Official handle:** `@XiaomiMiMo` (also: `@XiaomiMiMoDevs`)
- **Primary tokens (3):** `MiMo`, `Xiaomi MiMo`, `小米 MiMo`
- **Call group:** C1 (co-occurrence-constrained)
- **Covered by:** Call A + C1
- **Not in B2** (dedup: C1 already covers via co-occurrence AND-filter)

### 6. `moonshot_kimi` (Kimi / 月之暗面)

- **Official handle:** `@Kimi_Moonshot`
- **Primary tokens (3):** `Kimi`, `MoonshotAI`, `月之暗面`
- **Call group:** C1 (co-occurrence-constrained)
- **Covered by:** Call A + C1
- **Not in B2** (dedup: C1 already covers; F1 driver Antonelli noise is
  mitigated by the co-occurrence AND-filter + `must_have_none`-style
  patterns in `brand_keywords`)
- **Bare `moonshot`** is intentionally absent from primary tokens
  (matches Moonshot crypto exchange spam, not Moonshot AI)

### 7. `inclusionai` (InclusionAI / Ling / Ring)

- **Official handle:** `@TheInclusionAI` (also: `@AntLingAGI`, `@robbyant_brain`)
- **Primary tokens (3):** `InclusionAI`, `Ling`, `Ring`
- **Call group:** B2
- **Covered by:** Call A + B2
- **Token notes:** `Ming` is in the full `brand_keywords` table but not
  in the `is_primary=1` subset (the 3-token curated set fits under cap)

### 8. `mistral` (Mistral AI / Mixtral)

- **Official handle:** `@MistralAI`
- **Primary tokens (2):** `Mistral`, `Mixtral`
- **Call group:** B1
- **Covered by:** Call A + B1

### 9. `stepfun` (StepFun / 阶跃星辰)

- **Official handle:** `@StepFun_ai` (also: `@stepfunai`)
- **Primary tokens (2):** `StepFun`, `阶跃星辰`
- **Call group:** B1
- **Covered by:** Call A + B1

### 10. `ernie` (Baidu ERNIE / 文心一言)

- **Official handle:** `@ErnieforDevs` (also: `@Paddlepaddle`, `@PaddlePaddle`)
- **Primary tokens (2):** `ERNIE`, `文心一言`
- **Call group:** C2 (co-occurrence-constrained)
- **Covered by:** Call A + C2
- **Not in B1** (dedup: C2 already covers; ERNIE = Sesame Street
  character + Bert variant — co-occurrence disambiguation is essential)

### 11. `hunyuan` (Tencent Hunyuan / 混元)

- **Official handle:** `@TencentHunyuan`
- **Primary tokens (3):** `Hunyuan`, `混元`, `腾讯混元`
- **Call group:** B1
- **Covered by:** Call A + B1

### 12. `llama` (Meta Llama)

- **Official handle:** `@AIatMeta`
- **Primary tokens (3):** `"Llama 3"`, `"Meta Llama"`, `Llama`
- **Call group:** C1 (co-occurrence-constrained)
- **Covered by:** Call A + C1
- **Not in B1** (dedup: C1 already covers; bare `Llama` = the animal)

### 13. `nemo_megatron` (NVIDIA NeMo / Megatron)

- **Official handle:** `@NVIDIAAIDev` (also: `@NVIDIAAI`)
- **Primary tokens (2):** `Megatron-LM`, `NVIDIA NeMo`
- **Call group:** B3
- **Covered by:** Call A + B3

### 14. `doubao` (ByteDance Doubao / 豆包)

- **Official handle:** `@DoubaoAI` (also: `@BytePlusGlobal`, `@bytedanceoss`, `@doubaoai`)
- **Primary tokens (3):** `ByteDance`, `Doubao`, `豆包`
- **Call group:** B2
- **Covered by:** Call A + B2

### 15. `yi` (01.AI Yi / 零一万物)

- **Official handle:** `@01AI_Yi`
- **Primary tokens (3):** `01.AI`, `Yi`, `零一万物`
- **Call group:** C1 (co-occurrence-constrained)
- **Covered by:** Call A + C1
- **Not in B2** (dedup: C1 already covers; `Yi` = common Chinese surname)

### 16. `sensechat` (SenseTime SenseChat / 商汤)

- **Official handle:** `@SenseTime_AI`
- **Primary tokens (3):** `SenseChat`, `SenseTime`, `日日新`
- **Call group:** B2
- **Covered by:** Call A + B2

### 17. `exaone` (LG AI Research / EXAONE)

- **Official handle:** `@LG_AI_Research`
- **Primary tokens (2):** `EXAONE`, `LG AI`
- **Call group:** B3
- **Covered by:** Call A + B3

### 18. `kuaishou` (Kuaishou KwaiYii / 快意)

- **Official handle:** `@Kling_ai`
- **Primary tokens (2):** `Kuaishou`, `KwaiYii`
- **Call group:** B3
- **Covered by:** Call A + B3

### 19. `sakana_ai` (Sakana AI)

- **Official handle:** `@SakanaAILabs`
- **Primary tokens (3):** `Sakana`, `Sakana AI`, `サカナAI`
- **Call group:** B3
- **Covered by:** Call A + B3
- **Note:** `Sakana` = Japanese for "fish" — collides with food/sushi posts.
  The co-occurrence AND-filter + 3-token curated set (incl. the Japanese
  katakana `サカナAI`) keeps precision intact.

### 20. `upstage` (Upstage / Solar)

- **Official handle:** `@upstageai`
- **Primary tokens (2):** `Solar`, `Upstage`
- **Call group:** C2 (co-occurrence-constrained)
- **Covered by:** Call A + C2
- **Not in B3** (dedup: C2 already covers; `Upstage` = theater term,
  `Solar` = the star — co-occurrence disambiguation is essential)
- **Bare `Solar` dropped from C2's brand group** (substring leak:
  "solar winds" + generic `model` co-occurrence produced false positives)

---

## Brand alias / handle index (consolidated)

| brand_id | Official handle | Primary tokens (DB, is_primary=1) | Call group |
|---|---|---|---|
| `minimax` | `MiniMax_AI` | `Hailuo`, `MiniMax`, `m2.5`, `海螺` | B1 |
| `qwen` | `Alibaba_Qwen` | `Qwen`, `Qwen3`, `通义千问` | B1 |
| `deepseek` | `deepseek_ai` | `DeepSeek`, `deepseek-r1`, `深度求索` | B1 |
| `glm` | `Zai_org` | `ChatGLM`, `GLM`, `Zhipuai`, `智谱` | B2 |
| `mimo` | `XiaomiMiMo` | `MiMo`, `Xiaomi MiMo`, `小米 MiMo` | C1 |
| `moonshot_kimi` | `Kimi_Moonshot` | `Kimi`, `MoonshotAI`, `月之暗面` | C1 |
| `inclusionai` | `TheInclusionAI` | `InclusionAI`, `Ling`, `Ring` | B2 |
| `mistral` | `MistralAI` | `Mistral`, `Mixtral` | B1 |
| `stepfun` | `StepFun_ai` | `StepFun`, `阶跃星辰` | B1 |
| `ernie` | `ErnieforDevs` | `ERNIE`, `文心一言` | C2 |
| `hunyuan` | `TencentHunyuan` | `Hunyuan`, `混元`, `腾讯混元` | B1 |
| `llama` | `AIatMeta` | `"Llama 3"`, `"Meta Llama"`, `Llama` | C1 |
| `nemo_megatron` | `NVIDIAAIDev` | `Megatron-LM`, `NVIDIA NeMo` | B3 |
| `doubao` | `DoubaoAI` | `ByteDance`, `Doubao`, `豆包` | B2 |
| `yi` | `01AI_Yi` | `01.AI`, `Yi`, `零一万物` | C1 |
| `sensechat` | `SenseTime_AI` | `SenseChat`, `SenseTime`, `日日新` | B2 |
| `exaone` | `LG_AI_Research` | `EXAONE`, `LG AI` | B3 |
| `kuaishou` | `Kling_ai` | `Kuaishou`, `KwaiYii` | B3 |
| `sakana_ai` | `SakanaAILabs` | `Sakana`, `Sakana AI`, `サカナAI` | B3 |
| `upstage` | `upstageai` | `Solar`, `Upstage` | C2 |

---

## Per-brand primary token counts

| brand_id | Primary tokens | Call group |
|---|---|---|
| `minimax` | 4 | B1 |
| `qwen` | 3 | B1 |
| `deepseek` | 3 | B1 |
| `glm` | 4 | B2 |
| `mimo` | 3 | C1 |
| `moonshot_kimi` | 3 | C1 |
| `inclusionai` | 3 | B2 |
| `mistral` | 2 | B1 |
| `stepfun` | 2 | B1 |
| `ernie` | 2 | C2 |
| `hunyuan` | 3 | B1 |
| `llama` | 3 | C1 |
| `nemo_megatron` | 2 | B3 |
| `doubao` | 3 | B2 |
| `yi` | 3 | C1 |
| `sensechat` | 3 | B2 |
| `exaone` | 2 | B3 |
| `kuaishou` | 2 | B3 |
| `sakana_ai` | 3 | B3 |
| `upstage` | 2 | C2 |

**Total:** 55 primary tokens across 20 brands (2–4 per brand).

**`LANG_ALLOWLIST` is empty** in `x_monitor/queries.py` — the default is
"all-languages" (no `lang:` operator in any query). The `since_time:`/
`until_time:` epoch-precision operators are used at the cursor level by
`run_search()`.

**Recency:** TwitterAPI.io's recent-search cap is 7 days for self-serve.
No brand overrides this. The `since_time:` operator (epoch-precision) is
injected by `run_search()` for per-call cursor management; the redundant
`since:` (date-only) operator is suppressed when `since_time` is active
(commit `a691092`).

---

## How to verify the live inventory

```bash
# Print the per-cycle call plan (6 calls)
cd /Users/fuchitalee/development/minimax-marketing/x-monitoring && \
  source ~/.env.secrets && \
  PYTHONPATH=. .venv/bin/python -c "
from pathlib import Path
from x_monitor.config import load_config
from x_monitor.query_plan import plan_calls
from x_monitor.store import Store

cfg = load_config(Path('config.yaml'))
store = Store(Path('data/x_monitoring.db'))
primary_keywords = store.read_primary_brand_keywords()

plan = plan_calls(
    cfg.x_monitor_list_id,
    cfg.x_query_specs,
    primary_keywords=primary_keywords,
)
for c in plan:
    print(f'{c.call_id:4s} | {c.call_kind:12s} | {c.brand_id:16s} | len={c.query_length:3d} | {c.query_string}')
"
```

**Expected (live, as of 2026-07-22):** 6 entries — Call A (38 chars),
C1 (461 chars), C2 (295 chars), B1 (414 chars), B2 (377 chars),
B3 (353 chars). All under the 512-char cap.

```bash
# Dry-run mode: plan calls without firing them
python -m x_monitor dry-run
```

**Length history:**
- A: **38 chars** (unchanged — the list ID is static)
- C1: 505 → **461 chars** (−44: `upstage` moved to C2 on 2026-07-11)
- C2: **295 chars** (new — ernie + upstage on 2026-07-11; was ~247 when solo-upstage)
- B1: **414 chars** (v1.7 was 320 chars with 8 brands + bare OR-chain; now 6 brands + 22-term co-occurrence AND-filter)
- B2: **377 chars** (v1.7 was 468 chars with 7 brands + bare OR-chain; now 4 brands + co-occurrence)
- B3: **353 chars** (v1.7 was 310 chars with 5 brands + bare OR-chain; now 4 brands + co-occurrence)

The B-spec lengths are shorter than v1.7 despite the added co-occurrence
filter because (a) the `is_primary=1` subset is leaner (2–4 tokens per
brand vs. the old Q2 first-paren group which had 4–9 tokens), and (b) 6
polysemous brands were moved to C1/C2 exclusively (dedup from commit
`3915675`).

**The Q1–Q6 retirement (plans 2026-07-11-001, 2026-07-13-001):**
- `data/queries/<brand>.yaml` files: **deleted** (directory no longer exists)
- `data/accounts/<brand>.yaml` files: **deleted** (directory no longer exists)
- `data/filters/<brand>.yaml` files: **deleted** (directory no longer exists)
- `VALID_QUERY_IDS` in `config.py:48`: still present as a constant but
  **never read by the live cycle** — `plan_calls()` uses `call_id` from
  `VALID_CALL_IDS` (`A`, `B1`, `B2`, `B3`, `C1`, `C2`)
- `_planned_call_to_query()` in `run.py:171-177`: returns `"Q5"` as a
  hardcoded placeholder for backward compat with the `call_state` cursor
  schema; the value is meaningless for new calls
- `degraded_skip_order`: uses call IDs (B3 → B2 → B1 → C2 → C1 → A),
  not Q-IDs
- Post-fetch classification: `attribution.classify_pragmatics_full`
  writes `post_type` × `sentiment` × `discourse_role` ×
  `china_nationalism` × `us_nationalism` — the v1.6 Q1–Q6 signal-intent
  buckets are gone (removed in migration 022)

---

## Things that change the inventory

| Change | Effect |
|---|---|
| Add a brand to `enabled_models` + `KNOWN_MODELS` | Add `brand_keywords` rows (`is_primary=1` for the curated subset). Assign to an existing B group or a new C spec. Add official handles to `brands_accounts` + `accounts` + `roles`. Add the handle to the public X-list. |
| Toggle `is_primary` on a `brand_keywords` row | The token appears / disappears from the B-spec query. Re-measure length. |
| Edit `x_query_specs[].brands` tokens (C1/C2) | The C-spec query changes. Re-measure `len(query_string)` under 512 chars. |
| Edit `x_query_specs[].co_occurrence` | All specs sharing that list change. The current 22-term list is shared across C1/B1/B2/B3; C2 has a 20-term variant. Re-measure all affected lengths. |
| Add a new `XQuerySpec` to `x_query_specs` | One extra API call per cycle. Must conform to the uniform `(<tokens>) (<co_occurrence>) min_faves:N` shape (KTD1). |
| Disable a brand in `enabled_models` | The brand's primary tokens drop from its B-spec paren group; the brand still appears in any C-spec it's part of. Remove the handle from the X-list manually. |
| Add/change an official handle in the DB | Update `accounts` table + `brands_accounts` join row. Then manually add the handle to the public X-list (Call A). |
| Change `x_monitor_list_id` | Call A query changes (different list). Re-verify the list contains all official handles. |
| Rename a brand slug | Update `enabled_models`, `KNOWN_MODELS`, `brands.nickname` in DB, `brand_keywords.brand_id`, `brands_accounts` + `accounts` references, `x_query_specs[].brands` keys, `x_query_specs[].wide_net_brands` entries, and `call_b_groups` entries. |

---

## Schema references

This doc covers the live TwitterAPI.io query path. The pipeline's
downstream tables are touched only as sinks — query strings are built
purely from `config.yaml` + `brand_keywords.is_primary=1` (DB). For
convenience, the DB-side names reflect the post-batch state after
migrations 011–034:

| Concern | Detail |
|---|---|
| Brand attribution sources | `brand_keywords` (body text patterns), `brand_hashtags` (hashtag → brand mapping), `brand_search_terms` (query-string → brand mapping) |
| Per-mention rows | `posts_brands_mentions` (one row per match source: `hashtag`, `body_keyword`, `search_term`) |
| Per-brand rows | `posts_brands` (one row per unique brand, weight = 1/N if N brands matched) |
| Classification | `posts_brands_signals` — columns `post_type` (FK → `post_type_keys`), `sentiment` (FK → `sentiment_keys`), `discourse_role` (FK → `discourse_keys` via `posts_brands_discourse`), `china_nationalism` / `us_nationalism` (FK → `nationalism_keys`) |
| Translation | `posts.text_en`, `posts.text_zh_cn`, `posts.lang_detected` |
| Cursor tracking | `call_state` table — keyed by `call_id` (A, B1, B2, B3, C1, C2) |
| Account resolution | `brands_accounts` (M:N join with `role_id` FK → `roles`), `accounts` (handle, author_id, verified, bio) |
| Frontier brands (migration 032) | OpenAI/Anthropic/Google/xAI (companies), gpt/claude/gemini/gemma/grok (brands) — DB-only seed for downstream attribution. Not in `enabled_models`, not in any TwitterAPI query. |

---

## Last reviewed: 2026-07-22 (HEAD `33a98d4`)

### (a) Substantive corrections in this pass

- **Retired the Q1–Q6 architecture throughout.** Removed all per-brand
  Q1–Q6 query breakdowns, the "120 query entries (20 × 6)" stat, and
  references to `data/queries/<brand>.yaml`, `data/accounts/<brand>.yaml`,
  and `data/filters/<brand>.yaml`. None of these directories exist on disk;
  tokens now come from `brand_keywords.is_primary=1` (DB), handles from
  `brands_accounts` + `accounts` (DB).
- **Fixed call count: 5 → 6.** The doc previously claimed 5 calls/cycle
  in some sections and 6 in others. Live code emits 6: A + C1 + C2 + B1 +
  B2 + B3.
- **C1: removed upstage (5 → 4 brands, 505 → 461 chars).** Upstage was
  moved to C2 on 2026-07-11 to fix a bare-`Solar` substring leak.
- **Added C2 section.** ernie + upstage with 20 co-occurrence terms (295
  chars). Previously undocumented.
- **Updated all B1/B2/B3 brand lists.** B1: 8 → 6 brands (no llama, no
  ernie). B2: 7 → 4 brands (no moonshot_kimi, mimo, yi). B3: 5 → 4
  brands (no upstage). All per the 2026-07-13-002 U4 dedup.
- **Documented `is_wide_net: true` and the co-occurrence AND-filter on
  B-specs.** The v1.7 document described bare OR-chains with no
  co-occurrence. B1/B2/B3 now render as
  `<tokens> (<22-term co-occurrence>) min_faves:0` — same shape as C1.
- **Updated all call-string lengths** from live `_build_query` output at
  HEAD: A 38, C1 461, C2 295, B1 414, B2 377, B3 353.
- **Updated all official handles** from live DB (`brands_accounts` JOIN
  `accounts` JOIN `roles`). All `verified` flags are now `false` (were
  mixed true/false).
- **Updated primary token lists** from live `brand_keywords WHERE
  is_primary=1` (55 tokens across 20 brands, 2–4 per brand).
- **Removed the `call_b_groups`-as-canonical framing.** `call_b_groups` is
  a validation-only field; `x_query_specs` entries with `is_wide_net: true`
  are the canonical source for B1/B2/B3.
- **Removed `data/queries/`, `data/accounts/`, `data/filters/` from the
  source-of-truth list.** All three directories are deleted; per-brand
  data lives in the DB.

### (b) Claims not independently verified

- **X-list membership.** The document states the operator must manually
  add handles to the public X-list (`x_monitor_list_id =
  2067062923525275922`). Whether the list actually contains all 20
  official handles cannot be verified from the codebase — it requires
  checking the live X list via the Twitter/X UI or API.
- **LaunchAgent schedule.** The WatchPaths + ThrottleInterval=300 claim
  is carried forward from the previous doc version; the plist at
  `deploy/com.fuchitalee.x-monitor.plist` was not re-read in this pass.
  The memory [[2026-07-16-launchagents-two-cadences]] notes two agents;
  cross-check was not done.

### (c) Drift noticed but not fixed

- **`VALID_QUERY_IDS` still in `config.py:48`.** The tuple `("Q1", "Q2",
  "Q3", "Q4", "Q5", "Q6")` is dead code — never read by the live cycle.
  `queries.py:29,67` has a parallel `QUERY_IDS` tuple + `SynthQuery.id`
  Literal type. Removing them would be a cleanup commit, not a doc change.
- **`_planned_call_to_query()` returns `"Q5"` as hardcoded placeholder**
  in `run.py:177`. The value is meaningless for new calls; kept for
  backward compat with the `call_state` cursor schema. A cursor-schema
  migration could retire it.
- **Dashboard Q1→Q6 mapping** (`dashboard.py:485-498`) is still wired for
  backward compat with old DB rows that have Q-IDs in `source_query_ids`.
  New rows use call IDs (A, B1, B2, B3, C1, C2) but old rows persist.
- **The other 6 reference docs were not reviewed in this pass.** The skill
  prescribes a staged 7-file review; this was a single-file update on
  operator request. `db-schema.md`, `lookup-tables.md`,
  `classifier-prompts.md`, `twitterapi-io-calls.md`, `schema.dot`, and
  `x-monitoring/README.md` may have similar drift.
