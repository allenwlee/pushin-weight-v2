<!-- {{AGENT_ATTRIBUTION}} -->
# TwitterAPI.io live queries — v1.7.x (20 brands, A + B1/B2/B3 + C1)

**Regenerated:** 2026-06-25 (JST) — schema references re-verified against the 9 migrations (011–019) on `feat/schema-modernization-batch` @ `4cd62d2`; live-query inventory unchanged from 2026-06-23.
**Source of truth:** code on `main` of `/Users/fuchitalee/development/minimax-marketing/x-monitoring/`
- `config.yaml::enabled_models` (20 brands), `config.yaml::call_b_groups` (3 groups), `config.yaml::call_c_specs` (1 spec)
- `data/queries/<brand>.yaml` — 6 queries (Q1–Q6) per brand = **120 total**
- `data/accounts/<brand>.yaml` — official handle + empty `staff:` list per brand
- `data/filters/<brand>.yaml` — per-brand `min_faves` + `must_have_*` overrides (7 brands)
- `x_monitor/config.py::KNOWN_MODELS` (frozenset of 20)
- `x_monitor/query_plan.py::plan_calls(...)` — call planner
- `x_monitor/apify.py::TwitterApiClient.run_search(query, max_results, since)` — the live HTTP path to `https://api.twitterapi.io/twitter/tweet/advanced_search`
- `x_monitor/run.py` — cycle orchestrator (every 15 min via LaunchAgent)

> **Pipeline:** the cycle resolves the `enabled_models` list, builds a 1 + N + M call plan
> (Call A list-based + one Call B per `call_b_groups` group + one Call C per `call_c_specs` entry),
> and fires each `PlannedCall.query_string` against TwitterAPI.io's `advanced_search` endpoint.
> `assert_under_length_cap(query_string, 512)` guards every emitted call so an over-length query
> short-circuits to `status: "length_cap_exceeded"` and no credits are burned.

## How it all fits together

Every 15 minutes, three things happen in sequence:

1. **Ask X for posts.** Read `data/queries/<brand>.yaml`, build a search string like `(MiniMax OR 海螺 OR Hailuo) min_faves:2`, send it to TwitterAPI.io's `advanced_search` endpoint. Get up to 100 tweets back.

2. **For each tweet, decide which brand(s) it's about.** Read the tweet's body, hashtags, @-mentions, and the search query that fetched it. Match against `brand_hashtags`, `brand_keywords`, `brand_search_terms` — the per-brand detection rules in the DB. Each match is one row in `posts_brands_mentions`; the unique brand list is one row per brand in `posts_brands` (with a fractional weight — 1/N if N brands matched, 1.0 if just one).

3. **For each (tweet, brand) pair, decide the signal.** One row per pair in `posts_brands_signals`. The legacy column `signal_id` (FK → `signals.key`, still present) classifies into the 6-bucket taxonomy `release | community_question | criticism | commenter_capture | praise | other`. As of migration 019, two ADDITIVE columns coexist with `signal_id`: `post_type` (FK → `post_type_keys.key`, values `buzz_releases | hands_on_usage | performance_comparisons | feedback_questions`) and `sentiment` (FK → `sentiment_keys.key`, values `positive | negative | neutral | mixed`). The new columns are backfilled heuristically from `signal_id`; classifier pipeline upgrade is follow-up work. Classification source: heuristic by default (inferred from which query fetched the post), Claude LLM when `--with-llm` is passed.

**Worked example.** TwitterAPI.io returns:

```
@claude_code: Just shipped our new build with #minimax + 海螺 integration, the latency is amazing.
```

The reattribute step finds three matches: `#minimax` in `brand_hashtags`, `海螺` in `brand_keywords`, and the tweet was fetched by a minimax search. Three rows in `posts_brands_mentions` (one per source: `hashtag`, `body_keyword`, `search_term`); one row in `posts_brands` with `weight=1.0` because only minimax matched. The signal step then classifies the (tweet, minimax) pair — likely `signal_id = 'release'` (or `'praise'`), with the new `post_type = 'buzz_releases'` and `sentiment = 'positive'` columns backfilled from that legacy value by migration 019's heuristic.

**What the yaml decides vs what the DB decides.** The yaml decides what we ask X for (the search string). The DB tables decide what we found (which brands are mentioned in each returned tweet, and how). The yaml has a 512-char cap on the search string, so it carries the high-signal tokens only. The DB has no such cap, so the detection registries can be exhaustive. The two registries are kept in sync by hand: a token added to `brand_keywords` won't be in the live query unless the operator also adds it to the yaml.

---

## At-a-glance inventory

| Stat | Value |
|---|---|
| Enabled brands (`config.yaml::enabled_models`) | **20** |
| `KNOWN_MODELS` (frozenset in `x_monitor/config.py`) | **20** |
| Brand query yaml files (`data/queries/<brand>.yaml`) | **20** (1:1 with enabled_models) |
| Queries per brand (Q1–Q6) | **6** uniformly |
| Total query entries across all yaml | **120** (20 × 6) |
| Account yaml files (`data/accounts/<brand>.yaml`) | **20** (1:1 with enabled_models) |
| Filter yaml files (`data/filters/<brand>.yaml`) | **7** (only the v1-era brands) |
| Call A length | 38 chars |
| Call B groups (config) | 3 (B1, B2, B3) |
| Call C specs (config) | 1 (`call_id: C1`, multi-brand) |
| Plan size per cycle (if all groups + Call C emitted) | **1 Call A + 3 Call B + 1 Call C = 5 calls** |
| Deduped brand tokens (sum across all brands) | **75** |

> **⚠️ Live-path caveat — `call_b_groups` is configured but not yet plumbed in `run.py`.**
> `x_monitor/run.py:575-579` calls `plan_calls(self.data_dir, models, x_monitor_list_id=…, call_c_specs=…)` and **does not pass `call_b_groups`**. With the kwarg omitted, `plan_calls` falls back to the v1.7 single-B branch (`call_b_groups is None → b_groups = [list(enabled_models)]`) and emits one Call B spanning all 20 enabled brands. Computed live: that single Call B is **867 characters** — **well over the 512-char cap**. The `assert_under_length_cap` check inside `plan_calls` will raise on cycle entry. The configured B1/B2/B3 split (279 / 359 / 249 chars) would fit; the wiring fix is in `run.py` (pass `call_b_groups=self.config.call_b_groups`). **The live cycle is currently broken at 20 brands; do not add more brands until this is fixed.**

---

## Call A — curated public x.com list (1 call/cycle)

**Shape:** `(list:2067062923525275922) min_faves:1`
**Length:** 38 characters (the Snowflake-style list ID is 19 digits; `(list:<id>) ` is 32 chars + `min_faves:1` is 10 chars = 42 minus 4 from the no-space trim used in the actual query = 38).
**Source of truth:** `config.yaml::x_monitor_list_id = 2067062923525275922` (operator-managed public x.com list; every enabled brand with a `data/accounts/<brand>.yaml::accounts[].handle` contributes that handle to the list).

The list is the only place the operator maintains handle membership. Adding a `staff:` entry to `data/accounts/<brand>.yaml` does NOT auto-add to the x.com list — that is a manual operator step (see "List-drift detection" in the v1.7 plan).

**List-membership today (computed from `data/accounts/*.yaml::accounts[0].handle`):**

| # | brand_id | Official handle | Verified | accounts yaml |
|---|---|---|---|---|
| 1 | `minimax` | `MiniMaxAI` | true | ✓ |
| 2 | `qwen` | `QwenLM` | true | ✓ |
| 3 | `deepseek` | `deepseek_ai` | true | ✓ |
| 4 | `glm` | `Zhipuai_org` | true | ✓ |
| 5 | `xiaomi_mimo` | `XiaomiMiMo` | true | ✓ |
| 6 | `moonshot_kimi` | `MoonshotAI` | true | ✓ |
| 7 | `inclusionai` | `inclusionAI` | true | ✓ |
| 8 | `llama` | `Llama` | **false** (placeholder) | ✓ |
| 9 | `nvidia_nemo` | `NVIDIAAIDev` | **false** (placeholder) | ✓ |
| 10 | `doubao` | `doubaoAi` | **false** (placeholder) | ✓ |
| 11 | `yi` | `01AI_Yi` | **false** (placeholder) | ✓ |
| 12 | `sensechat` | `SenseTimeAI` | **false** (placeholder) | ✓ |
| 13 | `exaone` | `LGAIResearch` | **false** (placeholder) | ✓ |
| 14 | `kuaishou` | `KwaiYii` | **false** (placeholder) | ✓ |
| 15 | `sakana` | `SakanaAILabs` | **false** (placeholder) | ✓ |
| 16 | `upstage` | `upstageAI` | **false** (placeholder) | ✓ |

For the 4 query-only brands (`mistral`, `stepfun`, `ernie`, `hunyuan`), there is no `data/accounts/<brand>.yaml` — they have **no list membership** and contribute **0 handles to the x.com list**. Their Call A coverage is therefore zero; their visibility comes entirely from Call B (or Call C where applicable).

**`staff:` list** is empty (`[]`) on every `data/accounts/<brand>.yaml` — no per-brand staff handles are currently curated.

---

## Call B groups (config split — B1 / B2 / B3)

Configured in `config.yaml::call_b_groups` (a list of brand-id lists; v1.7.x field, validated in `x_monitor/config.py::Config._validate_call_b_groups`). When set, `plan_calls` emits one Call B per inner list in the order given; the call_id is `B1`, `B2`, `B3`, ….

### B1 — top-presence / global brands (8 brands, 320 chars)

**Order (from `config.yaml`):** `llama, minimax, qwen, deepseek, mistral, stepfun, ernie, hunyuan`

**Shape (verbatim from `_build_brand_wide_query`):**
```
((Llama OR "Llama 3" OR "Llama 4" OR "Meta Llama" OR "Code Llama" OR "Muse Spark" OR "Llama 3.1") OR (MiniMax OR 海螺 OR Hailuo) OR (Qwen OR 通义千问 OR 通义 OR Qwen3) OR (DeepSeek OR 深度求索 OR "DeepSeek V4") OR ("Mistral" OR "Mixtral") OR ("StepFun" OR "阶跃星辰") OR ("ERNIE" OR "文心一言") OR ("Hunyuan" OR "混元" OR "腾讯混元")) min_faves:0
```
**Length:** 320 characters. Headroom: 192 chars (37% of the 512-char cap).

| # | brand_id | Deduped brand tokens (Q2/Q3/Q5/Q6 first paren, source of truth for Call B) | Token count |
|---|---|---|---|
| 1 | `llama` | `Llama`, `"Llama 3"`, `"Llama 4"`, `"Meta Llama"`, `"Code Llama"`, `"Muse Spark"`, `"Llama 3.1"` | 7 |
| 2 | `minimax` | `MiniMax`, `海螺`, `Hailuo` | 3 |
| 3 | `qwen` | `Qwen`, `通义千问`, `通义`, `Qwen3` | 4 |
| 4 | `deepseek` | `DeepSeek`, `深度求索`, `"DeepSeek V4"` | 3 |
| 5 | `mistral` | `"Mistral"`, `"Mixtral"` (quoted) | 2 |
| 6 | `stepfun` | `"StepFun"`, `"阶跃星辰"` (quoted) | 2 |
| 7 | `ernie` | `"ERNIE"`, `"文心一言"` (quoted) | 2 |
| 8 | `hunyuan` | `"Hunyuan"`, `"混元"`, `"腾讯混元"` (quoted) | 3 |

### B2 — Chinese-language brands (7 brands, 474 chars)

**Order (from `config.yaml`):** `doubao, glm, moonshot_kimi, xiaomi_mimo, sensechat, yi, inclusionai`

**Shape (verbatim):**
```
((Doubao OR 豆包 OR Seed OR 字节 OR ByteDance OR "Seed-VL" OR "Seed-1.5" OR "豆包大模型") OR (GLM OR 智谱 OR ChatGLM OR Zhipuai OR "GLM-5.2") OR (Kimi OR 月之暗面 OR MoonshotAI OR "Kimi K2") OR (MiMo OR Xiaomi MiMo OR 小米 MiMo OR "MiMo-V2.5-Pro" OR "MiMo-V2.5" OR "MiMo Code" OR "MiMo-7B" OR "MiMo-VL" OR 小米) OR (SenseChat OR SenseNova OR SenseTime OR 商汤 OR 日日新) OR (Yi OR "01.AI" OR 零一万物 OR "Yi LLM" OR Yi-VL OR Yi-Coder OR "Yi-Large") OR (InclusionAI OR Ling OR Ring OR Ming)) min_faves:0
```
**Length:** 474 characters. Headroom: 38 chars (7% of the cap).

| # | brand_id | Deduped brand tokens | Token count |
|---|---|---|---|
| 1 | `doubao` | `Doubao`, `豆包`, `Seed`, `字节`, `ByteDance`, `"Seed-VL"`, `"Seed-1.5"`, `"豆包大模型"` | 8 |
| 2 | `glm` | `GLM`, `智谱`, `ChatGLM`, `Zhipuai`, `"GLM-5.2"` | 5 |
| 3 | `moonshot_kimi` | `Kimi`, `月之暗面`, `MoonshotAI`, `"Kimi K2"` | 4 |
| 4 | `xiaomi_mimo` | `MiMo`, `Xiaomi MiMo`, `小米 MiMo`, `小米`, `"MiMo-V2.5-Pro"`, `"MiMo-V2.5"`, `"MiMo Code"`, `"MiMo-7B"`, `"MiMo-VL"` | 9 |
| 5 | `sensechat` | `SenseChat`, `SenseNova`, `SenseTime`, `商汤`, `日日新` | 5 |
| 6 | `yi` | `Yi`, `"01.AI"`, `零一万物`, `"Yi LLM"`, `Yi-VL`, `Yi-Coder`, `"Yi-Large"` | 7 |
| 7 | `inclusionai` | `InclusionAI`, `Ling`, `Ring`, `Ming` | 4 |

### B3 — specialized / smaller brands (5 brands, 310 chars)

**Order (from `config.yaml`):** `nvidia_nemo, exaone, sakana, kuaishou, upstage`

**Shape (verbatim):**
```
((NeMo OR Megatron OR "NVIDIA NeMo" OR "Megatron-LM") OR (EXAONE OR "LG AI" OR "LG EXAONE") OR (Sakana OR "Sakana AI" OR "Sakana Labs" OR "サカナAI") OR (KwaiYii OR 快意 OR "KwaiYii LLM" OR Kuaishou) OR (Upstage OR Solar OR "Solar Pro" OR "Solar Mini" OR "Solar Pro 3" OR "Solar Pro 2" OR "Solar Open")) min_faves:0
```
**Length:** 310 characters. Headroom: 202 chars (39% of the cap).

| # | brand_id | Deduped brand tokens | Token count |
|---|---|---|---|
| 1 | `nvidia_nemo` | `NeMo`, `Megatron`, `"NVIDIA NeMo"`, `"Megatron-LM"` | 4 |
| 2 | `exaone` | `EXAONE`, `"LG AI"`, `"LG EXAONE"` | 3 |
| 3 | `sakana` | `Sakana`, `"Sakana AI"`, `"Sakana Labs"`, `"サカナAI"` | 4 |
| 4 | `kuaishou` | `KwaiYii`, `快意`, `"KwaiYii LLM"`, `Kuaishou` | 4 |
| 5 | `upstage` | `Upstage`, `Solar`, `"Solar Pro"`, `"Solar Mini"`, `"Solar Pro 3"`, `"Solar Pro 2"`, `"Solar Open"` | 7 |

### Brand tokens not in Call B

The four brands `mistral`, `stepfun`, `ernie`, `hunyuan` have **no `data/accounts/<brand>.yaml`** — they appear in Call B (group B1) but contribute **0 to Call A's list membership**. The other 16 brands have an accounts yaml and contribute to both Call A and Call B.

### What happens if `call_b_groups` is `None`

`plan_calls` (`x_monitor/query_plan.py:312-316`) falls back to `b_groups = [list(enabled_models)]` and emits **one** Call B spanning all 20 enabled brands. Computed: **867 characters** — over the 512-char cap. The cycle's `assert_under_length_cap` check raises and the call short-circuits. **Currently this is the active path** (see "Live-path caveat" above).

---

## Call C — co-occurrence-constrained brand-wide (1 spec → 1 call)

Configured in `config.yaml::call_c_specs` (list of `CallCBrandSpec` from `x_monitor/query_plan.py:99-137`). Default empty → no Call C emitted. v1.7.x ships with one operator-curated spec.

### C1 — MiMo + Kimi + Yi + Upstage + Llama (multi-brand co-occurrence)

**`call_id: C1`**, **5 brands in the primary group, 22 co-occurrence terms.**

**Primary group tokens (verbatim from `config.yaml`):**
- `xiaomi_mimo`: `[MiMo, "Xiaomi MiMo", "小米 MiMo"]`
- `moonshot_kimi`: `[Kimi, "Moonshot AI", 月之暗面, 暗面, MoonshotAI]`
- `yi`: `[Yi, "01.AI", 零一万物, "Yi LLM", Yi-VL, Yi-Coder]`
- `upstage`: `[Upstage, Solar, "Solar Pro", "업스테이지"]`
- `llama`: `[Llama, "Llama 3", "Llama 4", "Meta Llama", "Code Llama", "Muse Spark"]`

**Co-occurrence group:** `[api, llm, model, xiaomi, 小米, moonshot, chatbot, weights, gguf, ollama, code, coding, agent, agentic, benchmark, reasoning, release, "open source", huggingface, inference, moe, "tool calling"]`

**Min-faves floor:** 0. **Expected signal:** `other` (Call C targets the long tail; the post-fetch `classify_signal` may upgrade).

**Shape (verbatim from `_build_call_c_query`):**
```
((MiMo OR Xiaomi MiMo OR 小米 MiMo) OR (Kimi OR Moonshot AI OR 月之暗面 OR 暗面 OR MoonshotAI) OR (Yi OR 01.AI OR 零一万物 OR Yi LLM OR Yi-VL OR Yi-Coder) OR (Upstage OR Solar OR Solar Pro OR 업스테이지) OR (Llama OR Llama 3 OR Llama 4 OR Meta Llama OR Code Llama OR Muse Spark)) (api OR llm OR model OR xiaomi OR 小米 OR moonshot OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 505 characters. Headroom: 7 chars (1% of the cap — tight; future additions require a C2 spec).

**Why this exists:** these 5 brands' bare tokens collide with unrelated common nouns:
- `MiMo` → Mimo Studio (kids' video app), `xiaomi` alone → phone posts.
- `Kimi` → Turkish interrogative ("who?") and Japanese second-person pronoun (きみ); bare `moonshot` → Moonshot crypto exchange.
- `Yi` → common Chinese surname and dynasty name.
- `Upstage` → theater term.
- `Llama` → the animal.

Co-occurrence terms exclude non-AI false positives. The `must_have_none` keys in `data/filters/moonshot_kimi.yaml` (F1, antonelli, mercedes, …) further soften F1-driver Kimi Antonelli hijacks.

---

## Per-brand breakdown (20 brands)

Every brand listed in `config.yaml::enabled_models` is documented below. The "yaml" column points at the curated query file; "accounts" points at the per-brand staff/official file; "filter" points at the per-brand `min_faves` / `must_have_*` file (only 7 brands have one — the v1-era brands).

Query IDs Q1–Q6 are present in every yaml with the same shape:
- **Q1 (release):** `from:<official_handle> [context OR exclusions] min_faves:N` (or brand-name fallback for unconfirmed-handle brands)
- **Q2 (community_question):** `(<brand tokens>) (how OR 怎么 OR 教程 OR tutorial OR guide OR …) min_faves:2`
- **Q3 (criticism):** `(<brand tokens>) (broken OR fails OR bad OR 翻车 OR 不好 OR 不行 OR …) min_faves:1`
- **Q4 (commenter_capture):** `to:<official_handle> min_faves:5` (or brand-name fallback)
- **Q5 (other / technical):** `(<brand tokens>) (benchmark OR eval OR paper OR github OR code OR 开源 OR …) min_faves:3`
- **Q6 (praise):** `(<brand tokens>) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了 OR …) min_faves:5`

`min_faves` is the **call-level** floor in the `min_faves:` operator suffix; the per-brand filter in `data/filters/<brand>.yaml` is the **post-fetch** floor applied after attribution.

---

### 1. `minimax` (MiniMax / Hailuo) — 6 queries

- **yaml:** `data/queries/minimax.yaml`
- **accounts:** `data/accounts/minimax.yaml` (official `MiniMaxAI`, verified=true, staff=[])
- **filter:** `data/filters/minimax.yaml` (canonical handles: `MiniMaxAI`, `MiniMaxM3`, `MiniMax_Hailuo`; must_have_any: `minimax`, `m3`, `m2.7`, `m2.5`, `minimax-agent`, `minimax-coding`, `minimax-work`; must_have_none: `hailuo-2.3`, `hailuo ai prompt`)
- **Call group:** B2
- **Brand tokens:** `MiniMax`, `海螺`, `Hailuo` (3)
- **Q1:** `from:MiniMaxAI min_faves:5`
- **Q2:** `(MiniMax OR 海螺 OR Hailuo) (how OR 怎么 OR 如何 OR 教程 OR tutorial) min_faves:2`
- **Q3:** `(MiniMax OR 海螺 OR Hailuo) (broken OR fails OR bad OR 翻车 OR 不行 OR 垃圾) min_faves:1`
- **Q4:** `to:MiniMaxAI min_faves:5`
- **Q5:** `(MiniMax OR Hailuo) (benchmark OR eval OR paper OR github OR code) min_faves:3`
- **Q6:** `(MiniMax OR 海螺 OR Hailuo) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** `must_have_none` filters celebrity-Hailuo noise (Kylie, Kim K, Purnell); `Q2` uses `如何` (additional how-token not present in most other brands); `Q5` does not include `开源` (other brands include it).

### 2. `qwen` (Alibaba) — 6 queries

- **yaml:** `data/queries/qwen.yaml`
- **accounts:** `data/accounts/qwen.yaml` (official `QwenLM`, verified=true, staff=[])
- **filter:** `data/filters/qwen.yaml` (present — content not audited in this pass)
- **Call group:** B1
- **Brand tokens:** `Qwen`, `通义千问`, `通义`, `Qwen3` (4)
- **Q1:** `from:QwenLM min_faves:5`
- **Q2:** `(Qwen OR 通义千问 OR 通义 OR Qwen3) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(Qwen OR 通义) (broken OR fails OR bad OR 翻车 OR 不好 OR 不行) min_faves:1`
- **Q4:** `to:QwenLM min_faves:5`
- **Q5:** `(Qwen OR 通义) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(Qwen OR 通义千问 OR 通义 OR Qwen3) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** Q3/Q5 use the shorter `(Qwen OR 通义)` token subset (omits `通义千问`); Q2/Q6 use the full `(Qwen OR 通义千问 OR 通义 OR Qwen3)` triple.

### 3. `deepseek` (深度求索) — 6 queries

- **yaml:** `data/queries/deepseek.yaml`
- **accounts:** `data/accounts/deepseek.yaml` (official `deepseek_ai`, verified=true, staff=[])
- **filter:** `data/filters/deepseek.yaml` (present)
- **Call group:** B1
- **Brand tokens:** `DeepSeek`, `深度求索`, `"DeepSeek V4"` (3)
- **Q1:** `from:deepseek_ai min_faves:5`
- **Q2:** `(DeepSeek OR 深度求索 OR "DeepSeek V4") (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(DeepSeek OR 深度求索 OR "DeepSeek V4") (broken OR fails OR bad OR 翻车 OR 不好 OR 不行) min_faves:1`
- **Q4:** `to:deepseek_ai min_faves:5`
- **Q5:** `(DeepSeek OR 深度求索 OR "DeepSeek V4") (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(DeepSeek OR 深度求索 OR "DeepSeek V4") (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`

### 4. `glm` (Zhipu AI / 智谱) — 6 queries

- **yaml:** `data/queries/glm.yaml`
- **accounts:** `data/accounts/glm.yaml` (official `Zhipuai_org`, verified=true, staff=[])
- **filter:** `data/filters/glm.yaml` (present)
- **Call group:** B2
- **Brand tokens:** `GLM`, `智谱`, `ChatGLM`, `Zhipuai`, `"GLM-5.2"` (5 — `Zhipuai` is the org name; every Q uses all 5 tokens)
- **Q1:** `from:Zhipuai_org min_faves:5`
- **Q2:** `(GLM OR 智谱 OR ChatGLM OR Zhipuai) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(GLM OR 智谱 OR ChatGLM OR Zhipuai) (broken OR fails OR bad OR 翻车 OR 不好 OR 不行) min_faves:1`
- **Q4:** `to:Zhipuai_org min_faves:5`
- **Q5:** `(GLM OR 智谱 OR ChatGLM OR Zhipuai) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(GLM OR 智谱 OR ChatGLM OR Zhipuai) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** 5-token brand group (notable vs. most brands' 2-3); every query uses the full set; no `Q5` notes line.

### 5. `xiaomi_mimo` (小米 MiMo) — 6 queries

- **yaml:** `data/queries/xiaomi_mimo.yaml`
- **accounts:** `data/accounts/xiaomi_mimo.yaml` (official `XiaomiMiMo`, verified=true, staff=[])
- **filter:** `data/filters/xiaomi_mimo.yaml` (present; rot threshold 5 per `config.yaml::query_rot_streak_threshold_per_model`)
- **Call group:** B2
- **Brand tokens:** `MiMo`, `Xiaomi MiMo`, `小米 MiMo`, `小米`, `"MiMo-V2.5-Pro"`, `"MiMo-V2.5"`, `"MiMo Code"`, `"MiMo-7B"`, `"MiMo-VL"` (9 — broader than other brands' brand tokens)
- **Q1:** `from:XiaomiMiMo min_faves:3` (lowered from 5 — low-volume brand)
- **Q2:** `(MiMo OR Xiaomi MiMo OR 小米 MiMo) (how OR 怎么 OR 教程 OR tutorial) min_faves:2`
- **Q3:** `(MiMo OR 小米 MiMo) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `to:XiaomiMiMo min_faves:3` (lowered)
- **Q5:** `(MiMo OR 小米) (benchmark OR eval OR paper OR github OR 开源) min_faves:2` (no `code` token)
- **Q6:** `(MiMo OR Xiaomi MiMo OR 小米 MiMo) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** Q1/Q4 use `min_faves:3` instead of the default 5 (volume tuning); rot threshold 5 (vs default 3); bare `小米` is part of brand tokens but excluded from Q2/Q3/Q6 paren groups.

### 6. `moonshot_kimi` (Kimi / 月之暗面) — 6 queries

- **yaml:** `data/queries/moonshot_kimi.yaml`
- **accounts:** `data/accounts/moonshot_kimi.yaml` (official `MoonshotAI`, verified=true, staff=[])
- **filter:** `data/filters/moonshot_kimi.yaml` (must_have_none: F1, antonelli, verstappen, hamilton, pirelli, pole position, formula 1, mclaren, mercedes, red bull, qualifying, sprint race, race result — F1 hijack mitigation)
- **Call group:** B2
- **Brand tokens:** `Kimi`, `月之暗面`, `MoonshotAI`, `"Kimi K2"` (4)
- **Q1:** `from:MoonshotAI min_faves:5`
- **Q2:** `(Kimi OR 月之暗面 OR MoonshotAI) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(Kimi OR 月之暗面 OR MoonshotAI) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `to:MoonshotAI min_faves:5`
- **Q5:** `(Kimi OR 月之暗面 OR MoonshotAI) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(Kimi OR 月之暗面 OR MoonshotAI) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** filter `must_have_none` is the largest in the project (14 tokens) — F1 driver Antonelli hijack is the dominant noise source. The brand tokens deliberately exclude bare `moonshot` to avoid Moonshot crypto exchange spam.

### 7. `inclusionai` (InclusionAI / Ling / Ring / Ming) — 6 queries

- **yaml:** `data/queries/inclusionai.yaml`
- **accounts:** `data/accounts/inclusionai.yaml` (official `inclusionAI`, verified=true, staff=[])
- **filter:** `data/filters/inclusionai.yaml` (must_have_none: tolkien, middle-earth, wwe, wrestling, fanfic, smackdown, rollins, reigns, undertaker, "aj styles", "raw results")
- **Call group:** B2
- **Brand tokens:** `InclusionAI`, `Ling`, `Ring`, `Ming` (4)
- **Q1:** `from:inclusionAI min_faves:3` (lowered from 5 — low volume)
- **Q2:** `(InclusionAI OR Ling OR Ring OR Ming) (how OR 怎么 OR 教程 OR tutorial) min_faves:2`
- **Q3:** `(InclusionAI OR Ling OR Ring OR Ming) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `to:inclusionAI min_faves:3` (lowered)
- **Q5:** `(InclusionAI OR Ling OR Ring OR Ming) (benchmark OR eval OR paper OR github OR 开源) min_faves:2` (no `code` token)
- **Q6:** `(InclusionAI OR Ling OR Ring OR Ming) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** tokens consolidated from prior `inclusionai_ling/ring/ming` (commit consolidating 3 product variants into one brand-level entry, since Ling/Ring/Ming are versions of the same InclusionAI product line); Q1/Q4 use `min_faves:3`; filter `must_have_none` is the second-largest (11 tokens) — Tolkien fanfic, WWE wrestling, and Brat fanfic are the dominant noise.

### 8. `mistral` (Mistral AI / Mixtral) — 6 queries, **no accounts yaml, no filter yaml**

- **yaml:** `data/queries/mistral.yaml`
- **accounts:** **none** (no `data/accounts/mistral.yaml` — brand is query-only)
- **filter:** **none**
- **Call group:** B1
- **Brand tokens:** `"Mistral"`, `"Mixtral"` (2, both quoted)
- **Q1:** `("Mistral" OR "Mixtral") (AI OR model OR LLM OR 7B OR 8x7B) -weather -meteorology min_faves:5`
- **Q2:** `("Mistral" OR "Mixtral") (how OR tutorial OR guide OR 教程) min_faves:2`
- **Q3:** `("Mistral" OR "Mixtral") (broken OR fails OR bad OR "not working") min_faves:1`
- **Q4:** `to:MistralAI min_faves:5` (note: `to:` form, not brand-name — placeholder pending official handle confirmation; expected to return 0 until confirmed)
- **Q5:** `("Mistral" OR "Mixtral") (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `("Mistral" OR "Mixtral") (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯) min_faves:5` (no 卧槽/太强了)
- **Per-brand quirks:** all tokens are quoted (case-sensitive matching); Q1 has explicit negative operators (`-weather -meteorology`) to exclude the Mistral weather brand; Q4 uses a `to:`-shape (not the brand-name fallback) with a note that it "may be 0 results until the official handle is confirmed." No Call A coverage; Call C coverage is 0 (C1 spec doesn't include Mistral).

### 9. `stepfun` (StepFun / 阶跃星辰) — 6 queries, **no accounts yaml, no filter yaml**

- **yaml:** `data/queries/stepfun.yaml`
- **accounts:** **none**
- **filter:** **none**
- **Call group:** B1
- **Brand tokens:** `"StepFun"`, `"阶跃星辰"` (2, both quoted; Q1 also has `"StepFun AI"`)
- **Q1:** `("StepFun" OR "阶跃星辰" OR "StepFun AI") (LLM OR model OR "step" OR 阶跃) -dance -choreography min_faves:5`
- **Q2:** `("StepFun" OR "阶跃星辰") (how OR tutorial OR guide OR 教程) min_faves:2`
- **Q3:** `("StepFun" OR "阶跃星辰") (broken OR fails OR bad OR 翻车 OR 不好 OR 不行) min_faves:1`
- **Q4:** `to:StepFunAI min_faves:5` (placeholder, 0 results expected)
- **Q5:** `("StepFun" OR "阶跃星辰") (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `("StepFun" OR "阶跃星辰") (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** Q1 includes `"StepFun AI"` (3rd token) plus `(LLM OR model OR "step" OR 阶跃)` context disambiguator; `-dance -choreography` exclusion; Q4 is `to:`-placeholder.

### 10. `ernie` (Baidu ERNIE / 文心一言) — 6 queries, **no accounts yaml, no filter yaml**

- **yaml:** `data/queries/ernie.yaml`
- **accounts:** **none**
- **filter:** **none**
- **Call group:** B1
- **Brand tokens:** `"ERNIE"`, `"文心一言"` (2, both quoted)
- **Q1:** `("ERNIE" OR "文心一言") (LLM OR model OR Baidu OR 文心) -"Sesame Street" -Bert min_faves:5`
- **Q2:** `("ERNIE" OR "文心一言") (how OR tutorial OR guide OR 教程 OR 怎么) min_faves:2`
- **Q3:** `("ERNIE" OR "文心一言") (broken OR fails OR bad OR 翻车 OR 不好 OR 不行) min_faves:1`
- **Q4:** `to:Baidu_ERNIE min_faves:5` (placeholder)
- **Q5:** `("ERNIE" OR "文心一言") (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `("ERNIE" OR "文心一言") (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** Q1 includes Sesame Street and Bert as exclusions (ERNIE = Bert variant + Sesame Street character; the disambiguator is `(LLM OR model OR Baidu OR 文心)`).

### 11. `hunyuan` (Tencent Hunyuan / 混元 / 腾讯混元) — 6 queries, **no accounts yaml, no filter yaml**

- **yaml:** `data/queries/hunyuan.yaml`
- **accounts:** **none**
- **filter:** **none**
- **Call group:** B1
- **Brand tokens:** `"Hunyuan"`, `"混元"`, `"腾讯混元"` (3, all quoted)
- **Q1:** `("Hunyuan" OR "混元" OR "腾讯混元") (LLM OR model OR Tencent OR 混元 OR 腾讯) min_faves:5`
- **Q2:** `("Hunyuan" OR "混元" OR "腾讯混元") (how OR tutorial OR guide OR 教程 OR 怎么) min_faves:2`
- **Q3:** `("Hunyuan" OR "混元" OR "腾讯混元") (broken OR fails OR bad OR 翻车 OR 不好 OR 不行) min_faves:1`
- **Q4:** `to:HunyuanAI min_faves:5` (placeholder)
- **Q5:** `("Hunyuan" OR "混元" OR "腾讯混元") (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `("Hunyuan" OR "混元" OR "腾讯混元") (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** Q1's disambiguator includes `混元` and `腾讯` tokens (Hunyuan is a Chinese philosophical term — bare usage is non-AI).

### 12. `llama` (Meta Llama / Code Llama / Muse Spark) — 6 queries

- **yaml:** `data/queries/llama.yaml`
- **accounts:** `data/accounts/llama.yaml` (official `Llama`, **verified=false** — placeholder, operator must confirm Meta's official handle; note: bare `Llama` is the animal)
- **filter:** **none**
- **Call group:** B1 (also in Call C spec C1)
- **Brand tokens:** `Llama`, `"Llama 3"`, `"Llama 4"`, `"Meta Llama"`, `"Code Llama"`, `"Muse Spark"`, `"Llama 3.1"` (7 — largest in the project)
- **Q1:** `(Llama OR "Llama 3" OR "Llama 4" OR "Meta Llama" OR "Code Llama" OR "Muse Spark" OR "Llama 3.1") min_faves:5`
- **Q2:** `(…) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(…) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `(…) min_faves:5` (brand-name Q4 fallback)
- **Q5:** `(…) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(…) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** no `from:`/`to:`-shape on Q1/Q4 (no confirmed handle); all 7 brand tokens repeat in every query; accounts yaml says `verified: false` with `Llama` as the placeholder handle (note: `Llama` is also the animal and the broader family of Meta's open models); included in Call C1.

### 13. `nvidia_nemo` (NVIDIA NeMo / Megatron) — 6 queries

- **yaml:** `data/queries/nvidia_nemo.yaml`
- **accounts:** `data/accounts/nvidia_nemo.yaml` (official `NVIDIAAIDev`, **verified=false**)
- **filter:** **none**
- **Call group:** B3
- **Brand tokens:** `NeMo`, `Megatron`, `"NVIDIA NeMo"`, `"Megatron-LM"` (4 — both the NeMo framework and the Megatron training stack)
- **Q1:** `(NeMo OR Megatron OR "NVIDIA NeMo" OR "Megatron-LM") min_faves:5`
- **Q2:** `(…) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(…) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `(…) min_faves:5` (brand-name fallback)
- **Q5:** `(…) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(…) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** all 4 brand tokens repeat; verified=false; not in Call C.

### 14. `doubao` (ByteDance / 豆包 / Seed) — 6 queries

- **yaml:** `data/queries/doubao.yaml`
- **accounts:** `data/accounts/doubao.yaml` (official `doubaoAi`, **verified=false**; note: `豆包` is a literal Chinese snack word)
- **filter:** **none**
- **Call group:** B2
- **Brand tokens:** `Doubao`, `豆包`, `Seed`, `字节`, `ByteDance`, `"Seed-VL"`, `"Seed-1.5"`, `"豆包大模型"` (8 — the largest brand-token set in the project, by a wide margin)
- **Q1:** `(Doubao OR 豆包 OR Seed OR 字节 OR ByteDance OR "Seed-VL" OR "Seed-1.5" OR "豆包大模型") min_faves:5`
- **Q2:** `(…) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(…) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `(…) min_faves:5` (brand-name fallback)
- **Q5:** `(…) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(…) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** 8 brand tokens (incl. parent-company and product-line names); not in Call C; `豆包`/`Seed`/`字节` collide with the consumer Doubao snack app and ByteDance the company — co-occurrence is the practical noise control.

### 15. `yi` (01.AI Yi) — 6 queries

- **yaml:** `data/queries/yi.yaml`
- **accounts:** `data/accounts/yi.yaml` (official `01AI_Yi`, **verified=false**; note: `Yi` is a common Chinese surname and dynasty name)
- **filter:** **none**
- **Call group:** B2 (also in Call C spec C1)
- **Brand tokens:** `Yi`, `"01.AI"`, `零一万物`, `"Yi LLM"`, `Yi-VL`, `Yi-Coder`, `"Yi-Large"` (7)
- **Q1:** `(Yi OR "01.AI" OR 零一万物 OR "Yi LLM" OR Yi-VL OR Yi-Coder) min_faves:5`
- **Q2:** `(…) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(…) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `(…) min_faves:5` (brand-name fallback)
- **Q5:** `(…) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(…) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** 6 brand tokens (incl. company + product-line); included in Call C1 (the multi-brand co-occurrence spec).

### 16. `sensechat` (SenseTime / 商汤 / 日日新) — 6 queries

- **yaml:** `data/queries/sensechat.yaml`
- **accounts:** `data/accounts/sensechat.yaml` (official `SenseTimeAI`, **verified=false**; note: `Nova` is generic)
- **filter:** **none**
- **Call group:** B2
- **Brand tokens:** `SenseChat`, `SenseNova`, `SenseTime`, `商汤`, `日日新` (5)
- **Q1:** `(SenseChat OR SenseNova OR SenseTime OR 商汤 OR 日日新) min_faves:5`
- **Q2:** `(…) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(…) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `(…) min_faves:5` (brand-name fallback)
- **Q5:** `(…) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(…) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`

### 17. `exaone` (LG AI Research / EXAONE) — 6 queries

- **yaml:** `data/queries/exaone.yaml`
- **accounts:** `data/accounts/exaone.yaml` (official `LGAIResearch`, **verified=false**)
- **filter:** **none**
- **Call group:** B3
- **Brand tokens:** `EXAONE`, `"LG AI"`, `"LG EXAONE"` (3)
- **Q1:** `(EXAONE OR "LG AI" OR "LG EXAONE") min_faves:5`
- **Q2:** `(…) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(…) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `(…) min_faves:5` (brand-name fallback)
- **Q5:** `(…) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(…) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`

### 18. `kuaishou` (Kuaishou / KwaiYii) — 6 queries

- **yaml:** `data/queries/kuaishou.yaml`
- **accounts:** `data/accounts/kuaishou.yaml` (official `KwaiYii`, **verified=false**; note: bare `Kuaishou` is the video-app brand — non-AI posts dominate)
- **filter:** **none**
- **Call group:** B3
- **Brand tokens:** `KwaiYii`, `快意`, `"KwaiYii LLM"`, `Kuaishou` (4)
- **Q1:** `(KwaiYii OR 快意 OR "KwaiYii LLM" OR Kuaishou) min_faves:5`
- **Q2:** `(…) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(…) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `(…) min_faves:5` (brand-name fallback)
- **Q5:** `(…) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(…) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`

### 19. `sakana` (Sakana AI) — 6 queries (replaces `karakuri`)

- **yaml:** `data/queries/sakana.yaml`
- **accounts:** `data/accounts/sakana.yaml` (official `SakanaAILabs`, **verified=false**; note: `Sakana` is Japanese for `fish` — collides with food/restaurant/fishing posts)
- **filter:** **none**
- **Call group:** B3
- **Brand tokens:** `Sakana`, `"Sakana AI"`, `"Sakana Labs"`, `"サカナAI"` (4)
- **Q1:** `(Sakana OR "Sakana AI" OR "Sakana Labs") min_faves:5`
- **Q2:** `(…) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(…) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `(…) min_faves:5` (brand-name fallback)
- **Q5:** `(…) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(…) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** `sakana` replaced `karakuri` in commit `887f50e` (2026-06-23) — Karakuri was a speculative Japanese brand that collided heavily with anime/dining/figure posts. Sakana AI (Evolutionary Model Merge) is the replacement. The `Sakana` (fish) collision risk is the same as `Karakuri`'s anime/dining risk; no `must_have_none` filter currently exists for sakana (unlike moonshot_kimi/inclusionai).

### 20. `upstage` (Upstage / Solar / Solar Pro / Solar Mini) — 6 queries

- **yaml:** `data/queries/upstage.yaml`
- **accounts:** `data/accounts/upstage.yaml` (official `upstageAI`, **verified=false**; note: `Upstage` is a theater term but rare in AI contexts)
- **filter:** **none**
- **Call group:** B3 (also in Call C spec C1)
- **Brand tokens:** `Upstage`, `Solar`, `"Solar Pro"`, `"Solar Mini"`, `"Solar Pro 3"`, `"Solar Pro 2"`, `"Solar Open"` (7)
- **Q1:** `(Upstage OR Solar OR "Solar Pro" OR "Solar Mini") min_faves:5`
- **Q2:** `(…) (how OR 怎么 OR 教程 OR tutorial OR guide) min_faves:2`
- **Q3:** `(…) (broken OR fails OR bad OR 翻车 OR 不好) min_faves:1`
- **Q4:** `(…) min_faves:5` (brand-name fallback)
- **Q5:** `(…) (benchmark OR eval OR paper OR github OR code OR 开源) min_faves:3`
- **Q6:** `(…) (amazing OR incredible OR "love it" OR best OR "mind blowing" OR 🤯 OR 卧槽 OR 太强了) min_faves:5`
- **Per-brand quirks:** `Solar` is generic (matches the star, the battery, etc.) — co-occurrence gate in Call C1 helps. Included in Call C1.

---

## Brand alias / handle index (consolidated)

| brand_id | Official handle | Verified | Tokens in Call B (deduped) |
|---|---|---|---|
| `minimax` | `MiniMaxAI` | true | `MiniMax`, `海螺`, `Hailuo` |
| `qwen` | `QwenLM` | true | `Qwen`, `通义千问`, `通义` |
| `deepseek` | `deepseek_ai` | true | `DeepSeek`, `深度求索` |
| `glm` | `Zhipuai_org` | true | `GLM`, `智谱`, `ChatGLM`, `Zhipuai` |
| `xiaomi_mimo` | `XiaomiMiMo` | true | `MiMo`, `Xiaomi MiMo`, `小米 MiMo`, `小米` |
| `moonshot_kimi` | `MoonshotAI` | true | `Kimi`, `月之暗面`, `MoonshotAI` |
| `inclusionai` | `inclusionAI` | true | `InclusionAI`, `Ling`, `Ring`, `Ming` |
| `mistral` | (no accounts yaml) | n/a | `"Mistral"`, `"Mixtral"` |
| `stepfun` | (no accounts yaml) | n/a | `"StepFun"`, `"阶跃星辰"` |
| `ernie` | (no accounts yaml) | n/a | `"ERNIE"`, `"文心一言"` |
| `hunyuan` | (no accounts yaml) | n/a | `"Hunyuan"`, `"混元"`, `"腾讯混元"` |
| `llama` | `Llama` (placeholder) | **false** | `Llama`, `"Llama 3"`, `"Llama 4"`, `"Meta Llama"`, `"Code Llama"`, `"Muse Spark"`, `"Llama 3.1"` |
| `nvidia_nemo` | `NVIDIAAIDev` (placeholder) | **false** | `NeMo`, `Megatron`, `"NVIDIA NeMo"`, `"Megatron-LM"` |
| `doubao` | `doubaoAi` (placeholder) | **false** | `Doubao`, `豆包`, `Seed`, `字节`, `ByteDance`, `"Seed-VL"`, `"Seed-1.5"`, `"豆包大模型"` |
| `yi` | `01AI_Yi` (placeholder) | **false** | `Yi`, `"01.AI"`, `零一万物`, `"Yi LLM"`, `Yi-VL`, `Yi-Coder` |
| `sensechat` | `SenseTimeAI` (placeholder) | **false** | `SenseChat`, `SenseNova`, `SenseTime`, `商汤`, `日日新` |
| `exaone` | `LGAIResearch` (placeholder) | **false** | `EXAONE`, `"LG AI"`, `"LG EXAONE"` |
| `kuaishou` | `KwaiYii` (placeholder) | **false** | `KwaiYii`, `快意`, `"KwaiYii LLM"`, `Kuaishou` |
| `sakana` | `SakanaAILabs` (placeholder) | **false** | `Sakana`, `"Sakana AI"`, `"Sakana Labs"`, `"サカナAI"` |
| `upstage` | `upstageAI` (placeholder) | **false** | `Upstage`, `Solar`, `"Solar Pro"`, `"Solar Mini"`, `"Solar Pro 3"`, `"Solar Pro 2"`, `"Solar Open"` |

---

## Per-brand quota / language / recency overrides

| brand_id | `min_faves` floor (query) | `query_rot_streak_threshold` | `data/filters/<brand>.yaml` | Special notes |
|---|---|---|---|---|
| `minimax` | Q1=5, Q2=2, Q3=1, Q4=5, Q5=3, Q6=5 | 3 (default) | ✓ | must_have_none: hailuo-2.3 noise |
| `qwen` | Q1=5, Q2=2, Q3=1, Q4=5, Q5=3, Q6=5 | 3 | ✓ | (audited filter not in this pass) |
| `deepseek` | Q1=5, Q2=2, Q3=1, Q4=5, Q5=3, Q6=5 | 3 | ✓ | |
| `glm` | Q1=5, Q2=2, Q3=1, Q4=5, Q5=3, Q6=5 | 3 | ✓ | |
| `xiaomi_mimo` | Q1=3, Q2=2, Q3=1, Q4=3, Q5=2, Q6=5 | **5** (override in `query_rot_streak_threshold_per_model`) | ✓ | Low-volume tuning |
| `moonshot_kimi` | Q1=5, Q2=2, Q3=1, Q4=5, Q5=3, Q6=5 | 3 | ✓ | must_have_none: 14 F1 tokens |
| `inclusionai` | Q1=3, Q2=2, Q3=1, Q4=3, Q5=2, Q6=5 | 3 | ✓ | must_have_none: 11 Tolkien/WWE tokens |
| `mistral` | Q1=5, Q2=2, Q3=1, Q4=5, Q5=3, Q6=5 | 3 | **✗** | Tokens quoted; Q1 has `-weather -meteorology` |
| `stepfun` | Q1=5, Q2=2, Q3=1, Q4=5, Q5=3, Q6=5 | 3 | **✗** | Q1 has `-dance -choreography` |
| `ernie` | Q1=5, Q2=2, Q3=1, Q4=5, Q5=3, Q6=5 | 3 | **✗** | Q1 has `-"Sesame Street" -Bert` |
| `hunyuan` | Q1=5, Q2=2, Q3=1, Q4=5, Q5=3, Q6=5 | 3 | **✗** | Q1 disambiguator includes `混元`, `腾讯` |
| `llama` | all min_faves:5 (Q2=2, Q3=1, Q5=3) | 3 | **✗** | 7 tokens; placeholder handle |
| `nvidia_nemo` | all min_faves:5 (Q2=2, Q3=1, Q5=3) | 3 | **✗** | 4 tokens (incl. Megatron); placeholder |
| `doubao` | all min_faves:5 (Q2=2, Q3=1, Q5=3) | 3 | **✗** | 8 tokens (largest); placeholder |
| `yi` | all min_faves:5 (Q2=2, Q3=1, Q5=3) | 3 | **✗** | 7 tokens; in Call C1 |
| `sensechat` | all min_faves:5 (Q2=2, Q3=1, Q5=3) | 3 | **✗** | 5 tokens; placeholder |
| `exaone` | all min_faves:5 (Q2=2, Q3=1, Q5=3) | 3 | **✗** | 3 tokens (incl. "LG AI", "LG EXAONE") |
| `kuaishou` | all min_faves:5 (Q2=2, Q3=1, Q5=3) | 3 | **✗** | 4 tokens; `Kuaishou` is the video app |
| `sakana` | all min_faves:5 (Q2=2, Q3=1, Q5=3) | 3 | **✗** | 4 tokens; replaces `karakuri` (2026-06-23); `Sakana` = fish |
| `upstage` | all min_faves:5 (Q2=2, Q3=1, Q5=3) | 3 | **✗** | 7 tokens; in Call C1 |

**`LANG_ALLOWLIST` is empty** in `x_monitor/queries.py:54` — the default is "all-languages" (no `lang:` operator in any query). The `since:`/`until:` operators are unused in the curated queries (recency is implicit in the TwitterAPI.io 7-day recent-search default for self-serve).

**Recency:** TwitterAPI.io's recent-search cap is 7 days for self-serve (`X_LENGTH_CAP=512` for the length cap; the same 7-day recency cap is enforced by the underlying X API). No brand in the curated library overrides this.

---

## How to verify the live inventory

```bash
# Print the per-call plan
ssh fuchitalee 'cd ~/development/minimax-marketing/x-monitoring && \
  source ~/.env.secrets && \
  PYTHONPATH=. .venv/bin/python -c "from pathlib import Path; \
  from x_monitor.config import load_config; \
  from x_monitor.query_plan import plan_calls; \
  cfg = load_config(Path(\"config.yaml\")); \
  plan = plan_calls(Path(\"data\"), cfg.enabled_models, \
                    x_monitor_list_id=cfg.x_monitor_list_id, \
                    call_b_groups=cfg.call_b_groups, \
                    call_c_specs=cfg.call_c_specs); \
  [print(c.call_id, c.call_kind, c.brand_id, c.query_length, c.query_string) for c in plan]"'
```

**Expected (when `call_b_groups` is plumbed through `run.py`):** 5 entries — Call A (38 chars), Call B1 (320 chars), Call B2 (474 chars), Call B3 (310 chars), Call C1 (505 chars — multi-brand co-occurrence). All under the 512-char cap.

**Currently emitted (no `call_b_groups` kwarg in `run.py`):** 3 entries — Call A (38 chars), Call B (867 chars — **fails length cap**), Call C1. **The cycle is broken until `run.py` passes `call_b_groups=self.config.call_b_groups` to `plan_calls`.**

```bash
# In dry-run mode, the cycle still plans the calls but doesn't fire them
python -m x_monitor dry-run
```

**Test evidence 2026-06-25 (plan `2026-06-25-001`):** Lengths verified live against TwitterAPI.io before widening:
- B1: 279 → **320** chars (+41, new tokens: `"Llama 3.1"`, `Qwen3`, `"DeepSeek V4"`)
- B2: 359 → **474** chars (+115, new tokens: 5 MiMo variants, `"Yi-Large"`, `"Kimi K2"`, `"GLM-5.2"`)
- B3: 249 → **310** chars (+61, new tokens: `"Solar Pro 3"`, `"Solar Pro 2"`, `"Solar Open"`, `"サカナAI"`)
- C1: 471 → **505** chars (+34, added 12 co-occurrence terms + 1 Korean brand alias)

C1 has only **7 chars of headroom** under the cap. Any further co-occurrence or brand additions require either dropping terms, splitting into C1/C2, or moving to `live/archived` query shape. The 12 added co-occurrence terms (`code`, `coding`, `agent`, `agentic`, `benchmark`, `reasoning`, `release`, `"open source"`, `huggingface`, `inference`, `moe`, `"tool calling"`) were each validated against live `x_keyword_search` returns to surface relevant posts the original 10-term list missed.

---

## Things that change the inventory

| Change | Effect |
|---|---|
| Add a brand to `enabled_models` (and drop `data/queries/<brand>.yaml` + optionally `data/accounts/<brand>.yaml`) | One more paren group appended to the single Call B (when `call_b_groups` is None). Adds ~10-30 chars to the (already over-cap) single Call B. With `call_b_groups` plumbed, the operator must also add the new brand to one of B1/B2/B3 and the group's call must still fit under 512 chars. |
| Switch a brand from `verified: false` placeholder to `verified: true` (operator confirms the official handle) | Update `data/accounts/<brand>.yaml::verified: true` and optionally switch Q1 from `(<brand tokens>)` to `from:<handle>` and Q4 from `(<brand tokens>)` to `to:<handle>`. The yaml `notes` fields flag this for every placeholder brand. |
| Add a staff handle to `data/accounts/<brand>.yaml::staff` | Two-step: (1) add the handle to the yaml, (2) operator adds the handle to the public x.com list (`x_monitor_list_id`). The list-drift detection soft-warns if step (2) is missed. |
| Edit a brand's tokens in `data/queries/<brand>.yaml::Q2` (or any of Q2/Q3/Q5/Q6) | The Call B paren group's tokens change — re-measure `len(query_string)` and re-verify under 512 chars. `_load_brand_tokens_per_model` reads the first `(...)` group of Q2/Q3/Q5/Q6 in iteration order. |
| Add a `CallCBrandSpec` to `config.yaml::call_c_specs` | One extra Call C per cycle. The spec is read in order, gets a `C1`/`C2`/… label. |
| Disable a brand in `enabled_models` | The brand's paren group drops from its Call B; the `data/accounts/<brand>.yaml` handle stays on the x.com list (operator must remove it manually). |
| Per-brand `min_faves` in `data/filters/<brand>.yaml` | Filters out low-engagement posts after Call A/B returns and after brand attribution. Default no filter (file absent). |
| Swap one brand for another (e.g. `karakuri` → `sakana`, commit `887f50e`) | Edit `data/queries/<brand>.yaml` and `data/accounts/<brand>.yaml`, swap the brand_id in `enabled_models` and in `call_b_groups`. The old yaml files can be removed. |

---

## Schema references (post schema-modernization batch)

This doc is about the live TwitterAPI.io query path, not direct SQL against the DB. The pipeline's downstream tables (`posts_brands`, `posts_brands_mentions`, `posts_brands_signals`, `signals`, `roles`, …) are touched only as sinks — the query string is built purely from yaml. For convenience, the DB-side names referenced in step 2 / step 3 above reflect the state after the 9-unit schema modernization batch landed on `feat/schema-modernization-batch` at commit `4cd62d2` (migrations 011–019):

| Old name (pre-batch) | New name (post-batch) | Migration | Query-shape impact |
|---|---|---|---|
| `signal_keys` (table) | `signals` | 014 | FK source for `posts_brands_signals.signal_id` |
| (column) `signal` | `signal_id` | 014 | FK column on `posts_brands_signals` |
| `role_keys` (table) | `roles` | 015 | FK from `brands_accounts` / `companies_accounts` |
| (column) `role` | `role_id` | 015 | FK column on those M:N tables |
| `post_mentions` (table) | `posts_brands_mentions` | 013 | Source table for per-match attribution rows |
| (column) `locale` on `signal_labels` / `role_labels` | `lang` | 011 | i18n label lookup column (not on `posts.*` directly) |
| `engagement_tier_keys` + `engagement_tier_labels` (tables) | **dropped** | 012 | Dead code — never read by production. The `accounts.engagement_tier` column is also dropped. |
| (column) `accounts.engagement_tier` | **dropped** | 012 | The 3-tier classification moves to a control-layer query (follow-up plan). |
| (n/a) | `post_type_keys` + `post_type_labels` | 019 | New enum — values `buzz_releases`, `hands_on_usage`, `performance_comparisons`, `feedback_questions`. |
| (n/a) | `sentiment_keys` + `sentiment_labels` | 019 | New enum — values `positive`, `negative`, `neutral`, `mixed`. |
| (n/a) | `posts_brands_signals.post_type` (column) | 019 | Additive nullable TEXT FK → `post_type_keys.key`. Coexists with `signal_id`. |
| (n/a) | `posts_brands_signals.sentiment` (column) | 019 | Additive nullable TEXT FK → `sentiment_keys.key`. Coexists with `signal_id`. |
| Roles seeded in 008: `{official, community, researcher, press, vendor}` | Trimmed to `{official, staff, community}` | 016 | `researcher` / `press` / `vendor` keys (and their label rows) deleted; any FK rows pointing at them backfilled to `'community'`. `staff` added. |
| `signals` / `roles` PK was TEXT (the key string) | PK is now INTEGER AUTOINCREMENT; `key` column stays TEXT UNIQUE | 018 | FK columns (`signal_id`, `role_id`) still store the TEXT key — no consumer rewrite required. |

**Why this section is here.** The live query string (Calls A/B/C) is unaffected by these schema changes — yaml is the source of truth for query construction. But the *pipeline outputs* that the live path writes into (`posts_brands_mentions`, `posts_brands_signals.signal_id` / `post_type` / `sentiment`, `brands_accounts.role_id`, etc.) are all renamed. If you are debugging "the live call returned a row but it isn't classified correctly," the DB-side name you read from is the new name, not the legacy name.

**Out of scope for this doc** (covered by other reference docs):
- The `_pick_enum_label` and label-table read path (see migration 011 / 008 comments for the i18n detail).
- The TEMP TABLE backup pattern used to preserve label rows across DROP TABLE CASCADE FK in migration 018.
- The full classifier pipeline rewrite that consumes the new `post_type` / `sentiment` columns (U9 follow-up — see plan `docs/plans/2026-06-24-002-refactor-schema-modernization-batch-plan.md`).
