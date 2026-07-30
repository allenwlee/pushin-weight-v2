<!-- {{AGENT_ATTRIBUTION}} -->
# TwitterAPI.io live queries -- v2 Django architecture (20 brands, A + B1/B2/B3 + C1/C2/C3)

Last updated: 2026-07-24-11:36:23 (pre-hybrid-funnel)
Last updated: 2026-07-30 (post-hybrid-funnel -- plan 2026-07-30-002 U3)

Last updated: 2026-07-30

The harvest pipeline runs as a **Render cron job** (`render.yaml`, schedule
`*/15 * * * *`) executing `python manage.py run_cycle --limit-per-call 50`.
Each invocation plans, fetches, attributes, and persists one complete cycle.

**Source of truth (v2 Django):**

- `config.yaml` -- `enabled_models` (20 brands), `x_query_specs` (6 entries: C1, C2, C3, B1, B2, B3), `x_monitor_list_id`
- `project/settings.py` -- `KNOWN_MODELS` (frozenset of 20), `X_MONITOR_LIST_ID`, `X_MONITOR_X_QUERY_SPECS` (loaded from config.yaml at startup)
- `monitor/cycle.py` -- `_plan_calls()`, `_load_primary_keywords()`, `_load_x_query_specs()`, `_load_x_monitor_list_id()`
- `x_monitor/query_plan.py` -- `plan_calls()`, `_build_query()`, `XQuerySpec` dataclass (U2: added `handles` field for handle-only calls; renderer omits empty-co paren)
- `core/models.py` -- `Brand`, `BrandKeyword` (Django ORM, source of `is_primary=1` tokens)
- `monitor/management/commands/run_cycle.py` -- Django management command, the entry point invoked by the Render cron job

> **Pipeline:** each cycle resolves the `KNOWN_MODELS` list, loads primary
> keywords from `BrandKeyword.objects.filter(is_primary=True)` (Django ORM),
> builds a **7-call plan** (1 Call A + 6 `x_query_specs` entries: C1 + C2 +
> C3 + B1 + B2 + B3), and fires each `PlannedCall.query_string` against
> TwitterAPI.io's `advanced_search` endpoint.
> `assert_under_length_cap(query_string, 512)` guards every emitted call.

## How the cycle runs

The Render cron job (`pushinweight-harvest` in `render.yaml`) invokes the
Django management command every 15 minutes:

```
schedule: "*/15 * * * *"
startCommand: python manage.py run_cycle --limit-per-call 50
```

Each invocation:

1. **Plan calls.** `CycleRunner._plan_calls()` in `monitor/cycle.py` loads
   `X_MONITOR_LIST_ID` and `X_MONITOR_X_QUERY_SPECS` from Django settings
   (populated from `config.yaml` by `project/settings.py`). Primary brand
   keywords are loaded from the DB via `BrandKeyword.objects.filter(is_primary=True)`
   (Django ORM, `monitor/cycle.py::_load_primary_keywords()`). The plan is
   built by `x_monitor/query_plan.py::plan_calls()`. Emit 6 calls: Call A
   (curated X-list), C1/C2 (co-occurrence-constrained), B1/B2/B3 (wide-net
   with co-occurrence AND-filter).

2. **Fetch posts.** Fire each query against TwitterAPI.io's `advanced_search`
   endpoint. Max 50 tweets per call (configurable via
   `settings.X_MONITOR_CYCLE_LIMIT_PER_CALL`), paginated 20 per page, up to
   5 pages.

3. **Attribute brands.** For each tweet, match against `brand_keywords`,
   `brand_hashtags`, and `brand_search_terms` in the DB via
   `x_monitor/attribution.py::attribute_to_brands`. Each match is one
   row in `posts_brands_mentions`; the unique brand list is one row per
   brand in `posts_brands` (with a fractional weight -- 1/N if N brands
   matched, 1.0 if just one).

4. **Persist.** Write results via Django ORM: `Account`, `Post`,
   `PostBrand`, `PostBrandMention`, `PostBrandSignal`.

5. **Post-fetch (stubbed).** Translation and classification steps are
   deferred to a follow-up unit. The cycle currently stops at persistence.

**What the config decides vs what the DB decides.** The config
(`x_query_specs` + `brand_keywords.is_primary=1`) decides what we ask X
for (the search strings). The DB tables (`brand_keywords`,
`brand_hashtags`, `brand_search_terms`) decide what we found (which
brands are mentioned in each returned tweet, and how). The two registries
are kept in sync by hand: a token added to `brand_keywords` won't be in
the live query unless it also has `is_primary=True`.

---

## At-a-glance inventory

| Stat | Value |
|---|---|
| Enabled brands (`config.yaml::enabled_models` / `settings.KNOWN_MODELS`) | **20** |
| `brand_keywords` rows (total) | **207** |
| `brand_keywords` rows (`is_primary=True`) | **55** across 20 brands |
| Primary tokens per brand | **2--4** (curated subset: high-signal tokens that fit under the 512-char cap) |
| `x_query_specs` entries | **5** (C1, C2, B1, B2, B3) |
| Plan size per cycle (live) | **6 calls** (1 Call A + 5 specs) |
| Call A length | **38 chars** |
| Live call-string lengths | **A 38 / C1 461 / C2 295 / B1 414 / B2 377 / B3 353** (all under 512-char cap) |
| `degraded_skip_order` | B3 -> B2 -> B1 -> C2 -> C1 -> A |
| Co-occurrence terms (C1/B1/B2/B3) | **22 terms** |
| Co-occurrence terms (C2) | **20 terms** (drops `xiaomi`/`小米`, adds `baidu`/`文心`) |

> **`plan_calls` signature:** `plan_calls(x_monitor_list_id, x_query_specs, *, primary_keywords=None)`.
> The wide-net B-specs (B1/B2/B3) have `is_wide_net: true` and read
> per-brand tokens from `primary_keywords` (pre-loaded from
> `BrandKeyword.objects.filter(is_primary=True)` via Django ORM).
> Non-wide-net specs (C1/C2) read tokens inline from `spec.brands`.

---

## Call A -- curated public x.com list (1 call/cycle)

**Shape:** `(list:2067062923525275922) min_faves:0`
**Length:** 38 characters.
**Source of truth:** `config.yaml::x_monitor_list_id = 2067062923525275922` (operator-managed public x.com list; every enabled brand's official handle from `brands_accounts` + `accounts` DB tables should be on the list).

The list is the only place the operator maintains handle membership. Adding an account to the DB does NOT auto-add to the x.com list -- that is a manual operator step.

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
-- the operator must add staff handles to the X-list separately.

---

## Call C specs -- co-occurrence-constrained brand-wide

Configured in `config.yaml::x_query_specs` -- entries where
`is_wide_net` is absent or `false`. Two specs are live:

### C1 -- mimo + moonshot_kimi + yi + llama (4 brands, 22 co-occurrence terms)

**`call_id: C1`**, **4 brands, 22 co-occurrence terms.**

**Primary group tokens (inline in `config.yaml`):**
- `mimo`: `[MiMo, "Xiaomi MiMo", "小米 MiMo"]`
- `moonshot_kimi`: `[Kimi, "Moonshot AI", 月之暗面, 暗面, MoonshotAI]`
- `yi`: `[Yi, "01.AI", 零一万物, "Yi LLM", Yi-VL, Yi-Coder]`
- `llama`: `[Llama, "Llama 3", "Llama 4", "Meta Llama", "Code Llama", "Muse Spark"]`

**Co-occurrence group:** `[api, llm, model, xiaomi, 小米, moonshot, chatbot, weights, gguf, ollama, code, coding, agent, agentic, benchmark, reasoning, release, "open source", huggingface, inference, moe, "tool calling"]`

**Shape (live, from `_build_query` in `x_monitor/query_plan.py`):**
```
((MiMo OR Xiaomi MiMo OR 小米 MiMo) OR (Kimi OR Moonshot AI OR 月之暗面 OR 暗面 OR MoonshotAI) OR (Yi OR 01.AI OR 零一万物 OR Yi LLM OR Yi-VL OR Yi-Coder) OR (Llama OR Llama 3 OR Llama 4 OR Meta Llama OR Code Llama OR Muse Spark)) (api OR llm OR model OR xiaomi OR 小米 OR moonshot OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 461 characters. Headroom: 51 chars (10% of the cap).

**Why this exists:** these 4 brands' bare tokens collide with unrelated common nouns:
- `MiMo` -> Mimo Studio (kids' video app); `xiaomi` alone -> phone posts.
- `Kimi` -> Turkish interrogative ("who?") and Japanese second-person pronoun (きみ); bare `moonshot` -> Moonshot crypto exchange (intentionally absent from the brand group).
- `Yi` -> common Chinese surname and dynasty name.
- `Llama` -> the animal.

Co-occurrence terms exclude non-AI false positives. The `must_have_none`
filter in `brand_keywords` (via `is_primary=False` patterns) further softens
F1-driver Kimi Antonelli hijacks for `moonshot_kimi`.

**2026-07-11:** `upstage` was moved from C1 to C2 to fix a substring
leak -- bare `Solar` in C1's Upstage OR-group matched "solar winds" in
the co-occurrence AND-filter, producing false positives for everyday
"solar" English text.

### C2 -- ernie + upstage (2 brands, 20 co-occurrence terms)

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
- `ERNIE` collides with the Sesame Street character and the Bert variant. C1 had only 7 chars of headroom -- adding ERNIE's paren group would have exceeded the cap, so it got its own spec (C2).
- `Upstage` was moved here from C1 (2026-07-11). Bare `Solar` is intentionally DROPPED from the Upstage OR-group -- it matched substring "solar" in everyday English ("solar wind", "solar panel", "solar energy"). The three product-name tokens (`"Solar Pro"`, `"Solar LLM"`, `업스테이지`) keep precision-recall intact for actual Upstage coverage.

---

## Call B specs -- wide-net with co-occurrence AND-filter

Three `x_query_specs` entries with `is_wide_net: true`. Each renders a
`(<per-brand paren groups>) (<co-occurrence>) min_faves:0` query where
per-brand tokens come from `BrandKeyword` rows with `is_primary=True`
(loaded once per cycle via `monitor/cycle.py::_load_primary_keywords()`
using Django ORM).

The co-occurrence filter is the same 22-term list as C1. This means
the B-specs are **AND-filtered** -- a tweet must mention both a brand
token AND a co-occurrence term.

### B1 -- top-presence / global brands (6 brands, 414 chars)

**`wide_net_brands`:** `[minimax, qwen, deepseek, mistral, stepfun, hunyuan]`

**Shape (live, from `_build_query`):**
```
((Hailuo OR MiniMax OR m2.5 OR 海螺) OR (Qwen OR Qwen3 OR 通义千问) OR (DeepSeek OR deepseek-r1 OR 深度求索) OR (Mistral OR Mixtral) OR (StepFun OR 阶跃星辰) OR (Hunyuan OR 混元 OR 腾讯混元)) (api OR llm OR model OR xiaomi OR 小米 OR moonshot OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 414 characters. Headroom: 98 chars (19% of the cap).

| # | brand_id | Primary tokens (from DB, `is_primary=True`) | Count |
|---|---|---|---|
| 1 | `minimax` | `Hailuo`, `MiniMax`, `m2.5`, `海螺` | 4 |
| 2 | `qwen` | `Qwen`, `Qwen3`, `通义千问` | 3 |
| 3 | `deepseek` | `DeepSeek`, `deepseek-r1`, `深度求索` | 3 |
| 4 | `mistral` | `Mistral`, `Mixtral` | 2 |
| 5 | `stepfun` | `StepFun`, `阶跃星辰` | 2 |
| 6 | `hunyuan` | `Hunyuan`, `混元`, `腾讯混元` | 3 |

**Dedup note:** `llama` and `ernie` are intentionally absent from B1 --
they are covered exclusively by C1 and C2 respectively
(co-occurrence-constrained) to avoid duplicate TwitterAPI credit spend on
the wide-net path.

### B2 -- Chinese-language brands (4 brands, 377 chars)

**`wide_net_brands`:** `[doubao, glm, sensechat, inclusionai]`

**Shape (live, from `_build_query`):**
```
((ByteDance OR Doubao OR 豆包) OR (ChatGLM OR GLM OR Zhipuai OR 智谱) OR (SenseChat OR SenseTime OR 日日新) OR (InclusionAI OR Ling OR Ring)) (api OR llm OR model OR xiaomi OR 小米 OR moonshot OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 377 characters. Headroom: 135 chars (26% of the cap).

| # | brand_id | Primary tokens (from DB, `is_primary=True`) | Count |
|---|---|---|---|
| 1 | `doubao` | `ByteDance`, `Doubao`, `豆包` | 3 |
| 2 | `glm` | `ChatGLM`, `GLM`, `Zhipuai`, `智谱` | 4 |
| 3 | `sensechat` | `SenseChat`, `SenseTime`, `日日新` | 3 |
| 4 | `inclusionai` | `InclusionAI`, `Ling`, `Ring` | 3 |

**Dedup note:** `moonshot_kimi`, `mimo`, and `yi` are intentionally absent
from B2 -- they are covered exclusively by C1.

### B3 -- specialized / smaller brands (4 brands, 353 chars)

**`wide_net_brands`:** `[nemo_megatron, exaone, sakana_ai, kuaishou]`

**Shape (live, from `_build_query`):**
```
((Megatron-LM OR NVIDIA NeMo) OR (EXAONE OR LG AI) OR (Sakana OR Sakana AI OR サカナAI) OR (Kuaishou OR KwaiYii)) (api OR llm OR model OR xiaomi OR 小米 OR moonshot OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR open source OR huggingface OR inference OR moe OR tool calling) min_faves:0
```
**Length:** 353 characters. Headroom: 159 chars (31% of the cap).

| # | brand_id | Primary tokens (from DB, `is_primary=True`) | Count |
|---|---|---|---|
| 1 | `nemo_megatron` | `Megatron-LM`, `NVIDIA NeMo` | 2 |
| 2 | `exaone` | `EXAONE`, `LG AI` | 2 |
| 3 | `sakana_ai` | `Sakana`, `Sakana AI`, `サカナAI` | 3 |
| 4 | `kuaishou` | `Kuaishou`, `KwaiYii` | 2 |

**Dedup note:** `upstage` is intentionally absent from B3 -- it is covered
exclusively by C2.

### B-spec token source: `is_primary=True` via Django ORM

The wide-net B-specs source their tokens from `core.models.BrandKeyword`
rows where `is_primary=True`. The loader is
`monitor/cycle.py::_load_primary_keywords()`:

```python
def _load_primary_keywords() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for kw in BrandKeyword.objects.filter(is_primary=True).select_related("brand"):
        brand_id = kw.brand_id
        out.setdefault(brand_id, []).append(kw.pattern)
    return out
```

This replaces the v1 system's `Store.read_primary_brand_keywords()` which
read from SQLite directly. The Django ORM provides the same data through
the `brand_keywords` table managed by `core/models.py`.

---

## Per-brand breakdown (20 brands)

Every brand listed in `config.yaml::enabled_models` (and validated against
`settings.KNOWN_MODELS`) is documented below. All data comes from the DB --
primary tokens from `brand_keywords` (`is_primary=True`), official handles
from `brands_accounts` JOIN `accounts` JOIN `roles` (`roles.key = 'official'`).

### 1. `minimax` (MiniMax / Hailuo)

- **Display name:** MiniMax
- **Company:** MiniMax (CN)
- **Accent color:** `#3b82f6`
- **Official handle:** `@MiniMax_AI` (also: `@MiniMaxAgent`, `@hailuo_ai`)
- **Primary tokens (4):** `Hailuo`, `MiniMax`, `m2.5`, `海螺`
- **Call group:** B1
- **Covered by:** Call A (X-list) + B1 (wide-net with co-occurrence)

### 2. `qwen` (Alibaba Qwen / 通义千问)

- **Display name:** Qwen
- **Company:** Alibaba Group (CN)
- **Accent color:** `#f97316`
- **Official handle:** `@Alibaba_Qwen`
- **Primary tokens (3):** `Qwen`, `Qwen3`, `通义千问`
- **Call group:** B1
- **Covered by:** Call A + B1

### 3. `deepseek` (DeepSeek / 深度求索)

- **Display name:** DeepSeek
- **Company:** DeepSeek (CN)
- **Accent color:** `#10b981`
- **Official handle:** `@deepseek_ai`
- **Primary tokens (3):** `DeepSeek`, `deepseek-r1`, `深度求索`
- **Call group:** B1
- **Covered by:** Call A + B1

### 4. `glm` (Zhipu AI / 智谱)

- **Display name:** GLM / ChatGLM
- **Company:** Zhipu AI (CN)
- **Accent color:** `#a855f7`
- **Official handle:** `@Zai_org`
- **Primary tokens (4):** `ChatGLM`, `GLM`, `Zhipuai`, `智谱`
- **Call group:** B2
- **Covered by:** Call A + B2

### 5. `mimo` (Xiaomi MiMo)

- **Display name:** MiMo
- **Company:** Meituan (CN)
- **Accent color:** `#eab308`
- **Official handle:** `@XiaomiMiMo`
- **Primary tokens (3):** `MiMo`, `Xiaomi MiMo`, `小米 MiMo`
- **Call group:** C1 (co-occurrence-constrained)
- **Covered by:** Call A + C1

### 6. `moonshot_kimi` (Kimi / 月之暗面)

- **Display name:** Moonshot AI / Kimi
- **Company:** Moonshot AI (CN)
- **Accent color:** `#ec4899`
- **Official handle:** `@Kimi_Moonshot`
- **Primary tokens (3):** `Kimi`, `MoonshotAI`, `月之暗面`
- **Call group:** C1 (co-occurrence-constrained)
- **Covered by:** Call A + C1
- **Bare `moonshot`** is intentionally absent from primary tokens
  (matches Moonshot crypto exchange spam, not Moonshot AI)

### 7. `inclusionai` (InclusionAI / Ling / Ring)

- **Display name:** InclusionAI
- **Company:** InclusionAI Co. (CN)
- **Accent color:** `#06b6d4`
- **Official handle:** `@TheInclusionAI`
- **Primary tokens (3):** `InclusionAI`, `Ling`, `Ring`
- **Call group:** B2
- **Covered by:** Call A + B2

### 8. `mistral` (Mistral AI / Mixtral)

- **Display name:** Mistral
- **Company:** Mistral AI (FR)
- **Accent color:** `#facc15`
- **Official handle:** `@MistralAI`
- **Primary tokens (2):** `Mistral`, `Mixtral`
- **Call group:** B1
- **Covered by:** Call A + B1

### 9. `stepfun` (StepFun / 阶跃星辰)

- **Display name:** StepFun
- **Company:** StepFun (CN)
- **Accent color:** `#22c55e`
- **Official handle:** `@StepFun_ai`
- **Primary tokens (2):** `StepFun`, `阶跃星辰`
- **Call group:** B1
- **Covered by:** Call A + B1

### 10. `ernie` (Baidu ERNIE / 文心一言)

- **Display name:** ERNIE
- **Company:** Baidu Inc. (CN)
- **Accent color:** `#0ea5e9`
- **Official handle:** `@ErnieforDevs`
- **Primary tokens (2):** `ERNIE`, `文心一言`
- **Call group:** C2 (co-occurrence-constrained)
- **Covered by:** Call A + C2

### 11. `hunyuan` (Tencent Hunyuan / 混元)

- **Display name:** Hunyuan
- **Company:** Tencent (CN)
- **Accent color:** `#ec4899`
- **Official handle:** `@TencentHunyuan`
- **Primary tokens (3):** `Hunyuan`, `混元`, `腾讯混元`
- **Call group:** B1
- **Covered by:** Call A + B1

### 12. `llama` (Meta Llama)

- **Display name:** Llama
- **Company:** Meta Platforms Inc. (US)
- **Accent color:** `#14b8a6`
- **Official handle:** `@AIatMeta`
- **Primary tokens (3):** `"Llama 3"`, `"Meta Llama"`, `Llama`
- **Call group:** C1 (co-occurrence-constrained)
- **Covered by:** Call A + C1

### 13. `nemo_megatron` (NVIDIA NeMo / Megatron)

- **Display name:** NeMo / Megatron
- **Company:** NVIDIA (US)
- **Accent color:** `#84cc16`
- **Official handle:** `@NVIDIAAIDev`
- **Primary tokens (2):** `Megatron-LM`, `NVIDIA NeMo`
- **Call group:** B3
- **Covered by:** Call A + B3

### 14. `doubao` (ByteDance Doubao / 豆包)

- **Display name:** Doubao
- **Company:** ByteDance (CN)
- **Accent color:** `#f43f5e`
- **Official handle:** `@DoubaoAI`
- **Primary tokens (3):** `ByteDance`, `Doubao`, `豆包`
- **Call group:** B2
- **Covered by:** Call A + B2

### 15. `yi` (01.AI Yi / 零一万物)

- **Display name:** Yi
- **Company:** 01.AI (CN)
- **Accent color:** `#8b5cf6`
- **Official handle:** `@01AI_Yi`
- **Primary tokens (3):** `01.AI`, `Yi`, `零一万物`
- **Call group:** C1 (co-occurrence-constrained)
- **Covered by:** Call A + C1

### 16. `sensechat` (SenseTime SenseChat / 商汤)

- **Display name:** SenseChat
- **Company:** SenseTime (CN)
- **Accent color:** `#d946ef`
- **Official handle:** `@SenseTime_AI`
- **Primary tokens (3):** `SenseChat`, `SenseTime`, `日日新`
- **Call group:** B2
- **Covered by:** Call A + B2

### 17. `exaone` (LG AI Research / EXAONE)

- **Display name:** EXAONE
- **Company:** LG AI Research (KR)
- **Accent color:** `#0d9488`
- **Official handle:** `@LG_AI_Research`
- **Primary tokens (2):** `EXAONE`, `LG AI`
- **Call group:** B3
- **Covered by:** Call A + B3

### 18. `kuaishou` (Kuaishou KwaiYii / 快意)

- **Display name:** Kling / Kuaishou
- **Company:** Kuaishou Technology (CN)
- **Accent color:** `#fb923c`
- **Official handle:** `@Kling_ai`
- **Primary tokens (2):** `Kuaishou`, `KwaiYii`
- **Call group:** B3
- **Covered by:** Call A + B3

### 19. `sakana_ai` (Sakana AI)

- **Display name:** Sakana AI
- **Company:** Sakana (JP)
- **Accent color:** `#6366f1`
- **Official handle:** `@SakanaAILabs`
- **Primary tokens (3):** `Sakana`, `Sakana AI`, `サカナAI`
- **Call group:** B3
- **Covered by:** Call A + B3
- **Note:** `Sakana` = Japanese for "fish" -- collides with food/sushi posts.
  The co-occurrence AND-filter + 3-token curated set (incl. the Japanese
  katakana `サカナAI`) keeps precision intact.

### 20. `upstage` (Upstage / Solar)

- **Display name:** Upstage
- **Company:** Upstage Inc. (KR)
- **Accent color:** `#dc2626`
- **Official handle:** `@upstageai`
- **Primary tokens (2):** `Solar`, `Upstage`
- **Call group:** C2 (co-occurrence-constrained)
- **Covered by:** Call A + C2

---

## Brand alias / handle index (consolidated)

| brand_id | Official handle | Display name | Company | H/Q | Primary tokens (DB, `is_primary=True`) | Call group |
|---|---|---|---|---|---|---|
| `minimax` | `MiniMax_AI` | MiniMax | MiniMax | CN | `Hailuo`, `MiniMax`, `m2.5`, `海螺` | B1 |
| `qwen` | `Alibaba_Qwen` | Qwen | Alibaba Group | CN | `Qwen`, `Qwen3`, `通义千问` | B1 |
| `deepseek` | `deepseek_ai` | DeepSeek | DeepSeek | CN | `DeepSeek`, `deepseek-r1`, `深度求索` | B1 |
| `glm` | `Zai_org` | GLM / ChatGLM | Zhipu AI | CN | `ChatGLM`, `GLM`, `Zhipuai`, `智谱` | B2 |
| `mimo` | `XiaomiMiMo` | MiMo | Meituan | CN | `MiMo`, `Xiaomi MiMo`, `小米 MiMo` | C1 |
| `moonshot_kimi` | `Kimi_Moonshot` | Moonshot AI / Kimi | Moonshot AI | CN | `Kimi`, `MoonshotAI`, `月之暗面` | C1 |
| `inclusionai` | `TheInclusionAI` | InclusionAI | InclusionAI Co. | CN | `InclusionAI`, `Ling`, `Ring` | B2 |
| `mistral` | `MistralAI` | Mistral | Mistral AI | FR | `Mistral`, `Mixtral` | B1 |
| `stepfun` | `StepFun_ai` | StepFun | StepFun | CN | `StepFun`, `阶跃星辰` | B1 |
| `ernie` | `ErnieforDevs` | ERNIE | Baidu Inc. | CN | `ERNIE`, `文心一言` | C2 |
| `hunyuan` | `TencentHunyuan` | Hunyuan | Tencent | CN | `Hunyuan`, `混元`, `腾讯混元` | B1 |
| `llama` | `AIatMeta` | Llama | Meta Platforms Inc. | US | `"Llama 3"`, `"Meta Llama"`, `Llama` | C1 |
| `nemo_megatron` | `NVIDIAAIDev` | NeMo / Megatron | NVIDIA | US | `Megatron-LM`, `NVIDIA NeMo` | B3 |
| `doubao` | `DoubaoAI` | Doubao | ByteDance | CN | `ByteDance`, `Doubao`, `豆包` | B2 |
| `yi` | `01AI_Yi` | Yi | 01.AI | CN | `01.AI`, `Yi`, `零一万物` | C1 |
| `sensechat` | `SenseTime_AI` | SenseChat | SenseTime | CN | `SenseChat`, `SenseTime`, `日日新` | B2 |
| `exaone` | `LG_AI_Research` | EXAONE | LG AI Research | KR | `EXAONE`, `LG AI` | B3 |
| `kuaishou` | `Kling_ai` | Kling / Kuaishou | Kuaishou Technology | CN | `Kuaishou`, `KwaiYii` | B3 |
| `sakana_ai` | `SakanaAILabs` | Sakana AI | Sakana | JP | `Sakana`, `Sakana AI`, `サカナAI` | B3 |
| `upstage` | `upstageai` | Upstage | Upstage Inc. | KR | `Solar`, `Upstage` | C2 |

---

## Primary token counts per brand

| brand_id | Count | Call group |
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

**Total:** 55 primary tokens across 20 brands (2--4 per brand).

---

## Query rendering logic

All 6 calls pass through one uniform renderer in `x_monitor/query_plan.py`:

```python
def _build_query(spec, *, x_monitor_list_id=None, primary_keywords=None) -> str
```

**Three branches, one shape:**

1. **Call A** -- `not spec.is_wide_net and not spec.brands`:
   Renders `(list:<x_monitor_list_id>) min_faves:0`. Uses `MIN_FAVES_FOR_LIST_CALL`
   (currently 0).

2. **Wide-net B-spec** -- `spec.is_wide_net=True`:
   Reads per-brand tokens from `primary_keywords` (loaded once per cycle from
   `BrandKeyword.objects.filter(is_primary=True)` via Django ORM). For each
   brand in `spec.wide_net_brands`, creates one `(tok1 OR tok2 OR ...)` paren
   group. Joins all groups with OR inside an outer paren. Appends the
   co-occurrence group. Shape: `((brand1 tokens) OR (brand2 tokens) OR ...)
   (co_occurrence terms) min_faves:N`.

3. **C-spec (co-occurrence-constrained)** -- `not spec.is_wide_net and spec.brands`:
   Same shape as B-specs, but tokens come from `spec.brands` (inline in
   `config.yaml`) instead of the DB. Shape: `((brand1 tokens) OR ...)
   (co_occurrence terms) min_faves:N`.

**The 512-char cap** is enforced by `assert_under_length_cap()` in
`x_monitor/queries.py` (called in `plan_calls()` before returning each
`PlannedCall`). An over-cap query raises `ValueError` -- no credits are
burned.

**`LANG_ALLOWLIST` is empty** -- the default is "all-languages" (no `lang:`
operator in any query).

**Recency:** TwitterAPI.io's recent-search cap is 7 days for self-serve.
No brand overrides this. The `since_time:`/`until_time:` epoch-precision
operators are used at the cursor level by `run_search()`.

---

## How to verify the live inventory

```bash
# Dry-run: print the per-cycle call plan (6 calls) without network calls
python manage.py run_cycle --dry-run --json
```

**Expected output:** 6 calls -- Call A (38 chars), C1 (461 chars), C2 (295 chars),
B1 (414 chars), B2 (377 chars), B3 (353 chars). All under the 512-char cap.

---

## Things that change the inventory

| Change | Effect |
|---|---|
| Add a brand to `enabled_models` + `KNOWN_MODELS` | Add `BrandKeyword` rows (`is_primary=True` for the curated subset). Assign to an existing B group or a new C spec. Add official handles to `brands_accounts` + `accounts` + `roles`. Add the handle to the public X-list. |
| Toggle `is_primary` on a `BrandKeyword` row | The token appears / disappears from the B-spec query. Re-measure length. |
| Edit `x_query_specs[].brands` tokens (C1/C2) | The C-spec query changes. Re-measure `len(query_string)` under 512 chars. |
| Edit `x_query_specs[].co_occurrence` | All specs sharing that list change. The current 22-term list is shared across C1/B1/B2/B3; C2 has a 20-term variant. Re-measure all affected lengths. |
| Add a new `XQuerySpec` to `x_query_specs` in `config.yaml` | One extra API call per cycle. Must conform to the uniform `(<tokens>) (<co_occurrence>) min_faves:N` shape. |
| Remove a brand from `enabled_models` | The brand's primary tokens drop from its B-spec paren group; the brand still appears in any C-spec it's part of. Remove the handle from the X-list manually. |
| Add/change an official handle in the DB | Update `accounts` table + `brands_accounts` join row. Then manually add the handle to the public X-list (Call A). |
| Change `x_monitor_list_id` in `config.yaml` | Call A query changes (different list). Re-verify the list contains all official handles. Also update `X_MONITOR_LIST_ID` env var in `render.yaml`. |
| Rename a brand slug | Update `enabled_models`, `KNOWN_MODELS`, `Brand.nickname` in DB, `BrandKeyword.brand_id`, `brands_accounts` references, `x_query_specs[].brands` keys, `x_query_specs[].wide_net_brands` entries. Then re-run `makemigrations` + `migrate`. |

---

## Schema references

This doc covers the live TwitterAPI.io query path. The pipeline's
downstream tables are touched only as sinks -- query strings are built
purely from `config.yaml` + `BrandKeyword.objects.filter(is_primary=True)` (Django ORM).

| Concern | Detail |
|---|---|
| Brand attribution sources | `BrandKeyword` (body text patterns), `BrandHashtag` (hashtag -> brand mapping), `BrandSearchTerm` (query-string -> brand mapping) |
| Per-mention rows | `PostBrandMention` (one row per match source: `hashtag`, `body_keyword`, `search_term`) |
| Per-brand rows | `PostBrand` (one row per unique brand, weight = 1/N if N brands matched) |
| Classification | `PostBrandSignal` -- `post_type` (FK -> `PostTypeKey`), `sentiment` (FK -> `SentimentKey`) |
| Discourse | `PostBrandDiscourse` -- `discourse` (FK -> `DiscourseKey`), `china_nationalism`, `us_nationalism` (FK -> `NationalismKey`) |
| Translation | `Post.text_en`, `Post.text_zh_cn`, `Post.lang_detected` |
| Cursor tracking | `CallState` table -- composite PK on `(brand_id, call_id, call_kind, bucket, query_id)` |
| Account resolution | `BrandAccount` (M:N join with `role_id` FK -> `Role`), `Account` (handle, author_id, verified, bio) |
| Frontier brands | OpenAI/Anthropic/Google/xAI (companies), gpt/claude/gemini/gemma/grok (brands) -- DB-only seed for downstream attribution. Not in `KNOWN_MODELS`, not in any TwitterAPI query. |

---

## Last reviewed: 2026-07-24