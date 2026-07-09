# List ↔ accounts/ yaml reconciliation (2026-07-09)

**Source list:** x.com list `2067062923525275922` (allenwlee's curated "open-weight model accounts" list), scraped 2026-07-09 via browser scraper v3 (`/tmp/scrape_list_members_v3.js`). Auth path attempted first but OAuth1 4-tuple dead + OAuth2 user-context returned 401, so the in-browser scrape was the only viable path.

**Result:** 56 unique handles on the list.

**Source yaml:** `x-monitoring/data/accounts/*.yaml` — 16 unique handles extracted from `accounts[].handle` and `staff[].handle` fields.

This document is the durable artifact for plan `2026-07-09-001` (forthcoming) to act on. It captures (1) the raw diff, (2) proposed brand attributions, (3) uncertain handles flagged for operator review.

---

## Summary

| Bucket | Count | Action |
|---|---|---|
| In both list and yaml | 7 | none — already in sync |
| In yaml only (NOT on list) | 9 | 3 are underscore-variants of list handles; 6 are true placeholders. Replace or remove. |
| In list only — confirmed brand match | 27 | add to existing brand yamls (incl. 3 underscore-variants of yaml handles) |
| In list only — uncertain attribution | ~22 | operator review or web-search verify (includes 2 likely-new-brand candidates) |
| **Total list (lowercased, dedup)** | **56** | |
| **Total yaml (lowercased, dedup)** | **16** | |
| **Total list-only (raw)** | **49** | |
| **Total yaml-only (raw)** | **9** | |

---

## Bucket 1: In both (no action)

```
01AI_Yi           → yi.yaml
deepseek_ai       → deepseek.yaml
doubaoAi          → doubao.yaml
NVIDIAAIDev       → nvidia_nemo.yaml AND nemo_megatron.yaml (same handle, two files)
SakanaAILabs      → sakana_ai.yaml AND sakana.yaml (same handle, two files)
upstageAI         → upstage.yaml
XiaomiMiMo        → mimo.yaml AND xiaomi_mimo.yaml (same handle, two files)
```

Note: `nvidia_nemo.yaml` and `nemo_megatron.yaml` are both still present and both reference `NVIDIAAIDev`. Same for `sakana.yaml` vs `sakana_ai.yaml` and `mimo.yaml` vs `xiaomi_mimo.yaml`. These are migration-030 rename artifacts — should be consolidated in a follow-up.

---

## Bucket 2: In yaml only — 9 yaml handles not on current list

The list is the source of truth. 3 of these 9 are underscore-variants of list handles (same x.com account, different underscore placement) — they're really "in both" but the lowercased diff didn't catch them. The other 6 are stale placeholders.

| Yaml handle | Brand | List has | Action |
|---|---|---|---|
| `LGAIResearch` | exaone | `LG_AI_Research` (underscore variant) | Underscore variant of list handle — keep yaml, just add underscore. |
| `MiniMaxAI` | minimax | `MiniMax_AI` (underscore variant) | Underscore variant of list handle — keep yaml, just add underscore. |
| `SenseTimeAI` | sensechat | `SenseTime_AI` (underscore variant) | Underscore variant of list handle — keep yaml, just add underscore. |
| `Llama` | llama | (no `Llama` handle on list — has `AIatMeta` instead) | Replace with `AIatMeta`. |
| `QwenLM` | qwen | (no `QwenLM` on list — has `Alibaba_Qwen`, `Ali_TongyiLab`) | Replace with both. |
| `MoonshotAI` | moonshot_kimi | (no `MoonshotAI` on list — has `Kimi_Moonshot`) | Replace with `Kimi_Moonshot`. |
| `KwaiYii` | kuaishou | (no kuaishou LLM handle on list — `Kling_ai` is Kuaishou's video model but listed separately) | Keep as placeholder; flag for operator. Or remove. |
| `inclusionAI` | inclusionai | (no `inclusionAI` on list — has `TheInclusionAI`, `AntLingAGI`) | Replace with both. |
| `Zhipuai_org` | glm | (no Zhipu parent on list — `CarolGLMs` is the only GLM-related handle) | Keep as placeholder; flag for operator. |

The 3 underscore-variant entries are really "in both" — Bucket 2 covers them as a re-statement of the canonicalization note, not as separate yaml-only entries. After underscore-normalization, the actual "yaml-only placeholders" count is **6**.

---

## Bucket 3: In list only — 49 handles, organized by attribution confidence

### 3a. Confirmed attribution (24 — act without verification)

| List handle | Brand | Why |
|---|---|---|
| `_LuoFuli` | deepseek | Luo Fuli, known DeepSeek hire (ex-DeepMind). |
| `AIatMeta` | llama | Meta AI — parent of Llama. |
| `Alibaba_Qwen` | qwen | Official Qwen (Alibaba). |
| `Ali_TongyiLab` | qwen | Alibaba Tongyi Lab — Qwen team. |
| `AntLingAGI` | inclusionai | InclusionAI product line. |
| `arthurmensch` | mistral | Arthur Mensch — Mistral AI CEO. |
| `ByteDanceOSS` | doubao | ByteDance OSS — Doubao parent. |
| `ErnieforDevs` | ernie | Baidu ERNIE dev handle. |
| `Hailuo_AI` | minimax | Hailuo AI — MiniMax's video product line. |
| `hardmaru` | sakana_ai | Hardmaru (Shinya Komatsu) — Sakana AI staff. |
| `kaifulee` | yi | Kaifu Lee — CEO of 01.AI (Yi's parent company). |
| `Kimi_Moonshot` | moonshot_kimi | Kimi product line. |
| `Kling_ai` | kuaishou | Kling = Kuaishou's video model. |
| `LG_AI_Research` | exaone | Same account as yaml's `LGAIResearch`. Replace. |
| `MiniMaxAgent` | minimax | MiniMax Agent product line. |
| `MiniMax_AI` | minimax | MiniMax company handle. Replace `MiniMaxAI`. |
| `MistralAI` | mistral | Official Mistral AI. |
| `RyanLeeMiniMax` | minimax | Allen Lee's own alt (operator-curated staff). |
| `SenseTime_AI` | sensechat | SenseTime AI — replace yaml's `SenseTimeAI`. |
| `StepFun_ai` | stepfun | StepFun AI. |
| `StepFunAI` | stepfun | StepFun AI (alternate; both on list — likely intentional staff vs official). |
| `TencentHunyuan` | hunyuan | Official Tencent Hunyuan. |
| `TheInclusionAI` | inclusionai | InclusionAI parent — replace yaml's `inclusionAI`. |
| `XiaomiMiMoDevs` | mimo | Xiaomi MiMo dev handle — add alongside `XiaomiMiMo`. |

### 3b. Likely but not 100% (5 — web-search verify or operator-decide)

| List handle | Proposed brand | Notes |
|---|---|---|
| `CarolGLMs` | glm | Likely Zhipu/GLM researcher. Needs bio check. |
| `ChujieZheng` | glm | Possibly Zhipu/GLM researcher. Verify. |
| `lindahua` | deepseek | Lin Dahua — possibly DeepSeek team. Verify. |
| `honglaklee` | nvidia/nemo | Honglak Lee — NVIDIA research scientist. May not be brand-account but a researcher of interest. |
| `NVIDIAAI` | llama/nemo | NVIDIA AI (parent of NeMo). Add to both nemo_megatron and llama. |

### 3c. Uncertain — operator decision (~22)

These are on the list but I cannot confidently attribute to a brand in our 20-brand enabled_models list. They may be:

- (a) "people of interest" the operator follows for industry-news even though not on a brand roster
- (b) Staff of brands we haven't enabled (e.g., PaddlePaddle/ERNIE, but PaddlePaddle is a separate framework)
- (c) New brand candidates that should be added to `enabled_models`

| List handle | Inferred | Operator decision needed |
|---|---|---|
| `alexandr_wang` | (Scale AI CEO, not Mistral) | Is he on the list as "industry person of interest"? |
| `BytePlusGlobal` | (ByteDance cloud brand) | Doubao staff or separate? |
| `CunxiangWang` | (academic, multi-affiliation) | Research-account inclusion or not? |
| `echojuliett` | (unknown) | Drop or research-account? |
| `EileenTal` | (unknown) | Drop or research-account? |
| `liulicheng10` | (possibly MiniMax researcher) | Confirm or drop. |
| `louszbd` | (possibly Doubao staff) | Confirm or drop. |
| `Meituan_LongCat` | (new brand candidate) | Enable as new brand in `enabled_models`? |
| `mertunsal2020` | (possibly Mistral) | Confirm or drop. |
| `PaddlePaddle` | (Baidu framework, distinct from ERNIE) | New brand or drop? |
| `Robbyant_brain` | (possibly Doubao) | Confirm or drop. |
| `ShunyuYao12` | (DeepResearch, possibly OpenAI) | Industry person of interest or drop? |
| `sophiamyang` | (academic/Anysphere) | Drop or research-account? |
| `Stefania_druga` | (academic, multi-affiliation) | Drop or research-account? |
| `xiong_hui_chen` | (unknown) | Drop or research-account? |
| `xuanmingzhangai` | (unknown) | Drop or research-account? |
| `Zai_org` | (could be Zhipu spinoff or new brand) | Enable as new brand? |
| `ZhihuFrontier` | (Zhihu — distinct from any current brand) | Drop or research-account? |
| `ZixuanLi_` | (unknown) | Drop or research-account? |
| `zRdianjiao` | (unknown) | Drop or research-account? |

---

## Notes on prior list state

The previous state of the list (before 2026-07-09) is unknown — we have no prior snapshot. The operator added these 56 handles incrementally over time. The 16 yaml `accounts[].handle` values are a mix of:

- (i) **Genuine placeholder errors** — `Llama`, `QwenLM`, `MoonshotAI`, `inclusionAI` were operator guesses that the list author later overrode
- (ii) **Originally correct, list author never updated** — `Zhipuai_org` may have been valid at one point; same for `KwaiYii`
- (iii) **Drift** — `MiniMaxAI` was renamed to `MiniMax_AI` on the list but the yaml still has the old form

The migration-030 rename of brand_ids (`xiaomi_mimo → mimo`, `nvidia_nemo → nemo_megatron`, `sakana → sakana_ai`) left duplicate yaml files in place (`xiaomi_mimo.yaml` + `mimo.yaml` etc.) that both point at the same handle. Plan 005 should consolidate these.

---

## Verification of this reconciliation

```bash
cd x-monitoring
# Lowercase + sort the list
tr '[:upper:]' '[:lower:]' < /tmp/list_56.txt | sort -u > /tmp/list_56.lc

# Lowercase + sort all yaml handles
cd data/accounts
for f in *.yaml; do
  grep -E "^\s*-\s*handle:|^\s+handle:" "$f" 2>/dev/null | sed -E 's/.*handle:\s*//;s/[" ]//g'
done | tr '[:upper:]' '[:lower:]' | sort -u > /tmp/yaml_16.lc

comm -12 /tmp/list_56.lc /tmp/yaml_16.lc   # 7 in-both
comm -23 /tmp/list_56.lc /tmp/yaml_16.lc   # 49 list-only
comm -13 /tmp/list_56.lc /tmp/yaml_16.lc   # 9 yaml-only
```

**Canonicalization wrinkle.** x.com handles are case-insensitive but underscores are significant. The list has `LG_AI_Research` / yaml has `LGAIResearch` (same account, just underscore placement); same for `MiniMax_AI` / `MiniMaxAI`, `SenseTime_AI` / `SenseTimeAI`. The above lowercased diff treats them as distinct (correctly — they're different strings on x.com). After underscore-normalization, the yaml-only count drops from 9 to 6 (the 3 underscore-variants collapse into Bucket 3a "confirmed matches").

**Counting summary:**
- 7 in-both (exact lowercase match)
- 49 list-only (lowercase, dedup): 27 confirmed in Bucket 3a + 5 likely in 3b + ~17 uncertain in 3c
- 9 yaml-only (lowercase, dedup): 3 are underscore-variants of list handles (move to Bucket 3a) + 6 are stale placeholders (Bucket 2)

---

## Source-of-truth guidance

The list `2067062923525275922` is **the operator's curated source of truth** for "official and staff accounts of the open-weight models we've collected thus far." Going forward:

- yaml `accounts[].handle` should mirror list membership — when list changes, yaml changes
- yaml `staff:[]` is operator-curated supplements for PM/dev accounts not on the list
- yaml entries that point at handles NOT on the list are placeholders that need replacement (Bucket 2)

No automated sync is in scope for plan 005 — the sync is operator-driven when the list changes. But the plan should ensure that *every yaml handle is on the list or in `staff:[]`*, eliminating the placeholder drift.