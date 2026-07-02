<!-- {{AGENT_ATTRIBUTION}} -->
---
attribution: "Grok"
title: "Wide-Net Query Templates for X-Monitoring Collection Layer"
date: 2026-06-24
description: "Draft wide-net brand-only query templates (for data/queries/*.yaml) and corresponding relevance filters (data/filters/*.yaml) for all 20 enabled AI models. Shift from old signal-seeded queries with expected_signal keywords to pure brand mention collection at fetch time. Post-fetch applies taxonomy (4 Type buckets, Sentiment, Aspects) and relevance filters. Includes canonical_handles, must_have patterns, noise exclusions, implementation notes, and usage in Call B / Call C / relevance pipeline."
tags: [x-monitoring, wide-net, queries, filters, collection, relevance, ai-brands, call-b, minimax]
---

# Wide-Net Query Templates for X-Monitoring Collection Layer

### written by Grok 4.3

## Introduction: The Shift to Wide-Net Collection

The x-monitoring collection layer (v1.7+) already uses a "wide net" architecture:

- **Call A**: List-based fan-in from curated accounts (high-signal, official releases + staff).
- **Call B**: Brand-wide OR of per-model token groups: `((Tok1 OR Tok2 OR CJK) OR (Tok3 OR ...)) min_faves:0` — catches *any* mention of the brand tokens.
- **Call C** (optional, per config.yaml `call_c_specs`): Brand tokens AND co-occurrence terms (for polysemous names like "mimo", "kimi", "doubao").

Previously, `data/queries/*.yaml` embedded signal seeding inside query_strings (e.g. `(Qwen OR 通义千问) (how OR 怎么 OR 教程 ...)` for community_question, `(...) (broken OR fails ...)` for criticism). These keywords were used at *collection time*.

**New direction (wide net)**: 
- Collect *any post mentioning the brand using only brand names/tokens*. No signal/aspect keywords at collection.
- Post-fetch: apply relevance filters (data/filters/), attribute brands, run taxonomy classification (4 Type buckets + Sentiment + Aspects from recent research in docs/research/), then store.
- This maximizes recall for the long tail, avoids biasing the collected corpus toward pre-defined signals, and lets the post-processing taxonomy + LLM classifier (future) handle categorization.

Current queries/*.yaml are legacy "old style". Filters/*.yaml (for ~7 models) already demonstrate the pattern for disambiguation (must_have_any, cjk_tokens, must_have_none, canonical_handles).

This document provides:
- Simplified queries YAML templates (brand tokens only + -is:retweet for cleanliness).
- Corresponding filters YAML (to be added/updated under data/filters/).
- Canonical handles summary.
- Implementation notes for query_plan.py, queries.py, run.py, relevance.py.
- Example for moonshot_kimi using exact style from existing.
- Full coverage for all 20 models from config.yaml.
- Tips for volume, disambiguation, using account graph + Call C.


## Queries YAML Templates (data/queries/*.yaml)

Simplified structure keeps Q1-Q6 for compatibility.



Key changes for wide-net:
- Remove all signal keywords (how, broken, etc).
- Q2/Q3/Q5/Q6 use same broad brand group + -is:retweet min_faves:0.
- from:/to: retained for Q1/Q4 official.
- Call B groups respect config call_b_groups for 512 char cap.

**General pattern**:

```yaml
# {{AGENT_ATTRIBUTION}}
# <Model> query library (wide-net brand-only).
queries:
  - id: Q1
    query_string: "from:OFFICIAL min_faves:1 -is:retweet"
    expected_signal: release
    max_results: 50
    enabled: true
    min_faves: 1
  - id: Q2
    query_string: "(Token1 OR Token2 OR CJK) -is:retweet min_faves:0"
    expected_signal: other
    max_results: 50
    enabled: true
    min_faves: 0
  - id: Q4
    query_string: "to:OFFICIAL min_faves:1 -is:retweet"
    expected_signal: commenter_capture
    max_results: 50
    enabled: true
    min_faves: 1
  - id: Q5
    query_string: "(Token1 OR Token2 OR CJK) -is:retweet min_faves:0"
    expected_signal: other
    max_results: 50
    enabled: true
    min_faves: 0
  - id: Q6
    query_string: "(Token1 OR Token2 OR CJK) -is:retweet min_faves:0"
    expected_signal: other
    max_results: 50
    enabled: true
    min_faves: 0
    notes: Wide-net; post-fetch taxonomy.
```


### Group B1 (llama, minimax, qwen, deepseek, mistral, stepfun, ernie, hunyuan)

**minimax**
```yaml
queries:
  - id: Q1
    query_string: "from:MiniMaxAI min_faves:1 -is:retweet"
    expected_signal: release
  - id: Q2
    query_string: "(MiniMax OR Hailuo OR 海螺) -is:retweet min_faves:0"
    expected_signal: other
  - id: Q4
    query_string: "to:MiniMaxAI min_faves:1 -is:retweet"
```

**qwen**
```yaml
  - id: Q1
    query_string: "from:QwenLM min_faves:5 -is:retweet"
  - id: Q2
    query_string: "(Qwen OR 通义千问 OR 通义) -is:retweet min_faves:0"
  - id: Q4
    query_string: "to:QwenLM min_faves:5 -is:retweet"
```

**deepseek**
```yaml
  - id: Q1
    query_string: "from:deepseek_ai min_faves:5 -is:retweet"
  - id: Q2
    query_string: "(DeepSeek OR 深度求索) -is:retweet min_faves:0"
```

**glm**
```yaml
  - id: Q1
    query_string: "from:Zhipuai_org min_faves:5 -is:retweet"
  - id: Q2
    query_string: "(GLM OR 智谱 OR ChatGLM OR Zhipuai) -is:retweet min_faves:0"
```

**llama**
```yaml
  - id: Q1
    query_string: "(Llama OR \"Llama 3\" OR \"Llama 4\" OR \"Meta Llama\" OR \"Code Llama\") min_faves:1 -is:retweet"
  - id: Q2
    query_string: "(Llama OR \"Llama 3\" OR \"Llama 4\" OR \"Meta Llama\") -is:retweet min_faves:0"
```

**mistral**
```yaml
  - id: Q1
    query_string: "(\"Mistral\" OR \"Mixtral\") -is:retweet min_faves:1"
  - id: Q2
    query_string: "(\"Mistral\" OR \"Mixtral\") -is:retweet min_faves:0"
```

**stepfun**
```yaml
  - id: Q1
    query_string: "(\"StepFun\" OR \"阶跃星辰\") -is:retweet min_faves:1"
  - id: Q2
    query_string: "(\"StepFun\" OR \"阶跃星辰\") -is:retweet min_faves:0"
```

**ernie**
```yaml
  - id: Q1
    query_string: "(\"ERNIE\" OR \"文心一言\") -is:retweet min_faves:1"
  - id: Q2
    query_string: "(\"ERNIE\" OR \"文心一言\") -is:retweet min_faves:0"
```

**hunyuan**
```yaml
  - id: Q1
    query_string: "(\"Hunyuan\" OR \"混元\" OR \"腾讯混元\") -is:retweet min_faves:1"
  - id: Q2
    query_string: "(\"Hunyuan\" OR \"混元\") -is:retweet min_faves:0"
```

**Notes on queries**: Update the 20 yamls. Parser in query_plan will auto use updated tokens for Call B. For broad tokens use Call C or filters. Retain Q1/Q4.


### Group B2 (doubao, glm, moonshot_kimi, xiaomi_mimo, sensechat, yi, inclusionai)

**moonshot_kimi**
```yaml
  - id: Q1
    query_string: "from:MoonshotAI min_faves:5 -is:retweet"
  - id: Q2
    query_string: "(Kimi OR 月之暗面 OR MoonshotAI) -is:retweet min_faves:0"
  - id: Q4
    query_string: "to:MoonshotAI min_faves:5 -is:retweet"
```

**xiaomi_mimo**
```yaml
  - id: Q1
    query_string: "from:XiaomiMiMo min_faves:3 -is:retweet"
  - id: Q2
    query_string: "(MiMo OR \"Xiaomi MiMo\" OR \"小米 MiMo\") -is:retweet min_faves:0"
```

**doubao**
```yaml
  - id: Q1
    query_string: "(Doubao OR 豆包 OR 字节) -is:retweet min_faves:1"
  - id: Q2
    query_string: "(Doubao OR 豆包 OR 字节) -is:retweet min_faves:0"
```

**yi**
```yaml
  - id: Q2
    query_string: "(Yi OR \"01.AI\" OR 零一万物 OR \"Yi LLM\") -is:retweet min_faves:0"
```

**inclusionai**
```yaml
  - id: Q1
    query_string: "from:inclusionAI min_faves:3 -is:retweet"
  - id: Q2
    query_string: "(InclusionAI OR Ling OR Ring OR Ming) -is:retweet min_faves:0"
```

**sensechat**
```yaml
  - id: Q2
    query_string: "(SenseChat OR SenseNova OR SenseTime OR 商汤) -is:retweet min_faves:0"
```


### Group B3 (nvidia_nemo, exaone, sakana, kuaishou, upstage)

**nvidia_nemo**
```yaml
  - id: Q2
    query_string: "(NeMo OR Megatron OR \"NVIDIA NeMo\") -is:retweet min_faves:0"
```

**exaone**
```yaml
  - id: Q2
    query_string: "(EXAONE OR \"LG AI\" OR \"LG EXAONE\") -is:retweet min_faves:0"
```

**sakana**
```yaml
  - id: Q2
    query_string: "(Sakana OR \"Sakana AI\" OR \"Sakana Labs\") -is:retweet min_faves:0"
```

**kuaishou**
```yaml
  - id: Q2
    query_string: "(KwaiYii OR 快意 OR Kuaishou) -is:retweet min_faves:0"
```

**upstage**
```yaml
  - id: Q2
    query_string: "(Upstage OR Solar OR \"Solar Pro\") -is:retweet min_faves:0"
```

**Notes on queries**: Update all 20. Parser auto-picks. Broad tokens prefer Call C or filters.


## Filters YAML Templates (data/filters/*.yaml)

Filters applied post-fetch in relevance.filter_posts().

- canonical_handles: bypass token checks.
- must_have_any: at least one to KEEP (ASCII word-boundary or CJK in).
- cjk_tokens: separate list for CJK matching.
- must_have_none: if match and no must, SOFT-DROP to review (recoverable).
- If no filter file: no-op, keep everything.

**Exact Kimi example** (copy from existing data/filters/moonshot_kimi.yaml):

```yaml
# Moonshot AI / Kimi relevance filter (v1.2).
# Worst-offender: F1 driver Kimi Antonelli hijacks.
canonical_handles:
  - Kimi_Moonshot
  - MoonshotAI
  - dotey

must_have_any:
  - kimi
  - k2
  - k2.5
  - kimi k
  - moonshot ai

cjk_tokens:
  - 月之暗面
  - 暗面
  - 月之暗面ai

must_have_none:
  - F1
  - "grand prix"
  - antonelli
  - verstappen
  - hamilton
  - formula 1
  - mercedes
  - red bull

notes: |
  F1 driver Kimi Antonelli hijacks. Audit canonical_handles.
```

**minimax filter**:
```yaml
canonical_handles:
  - MiniMaxAI
  - MiniMaxM3
must_have_any:
  - minimax
  - m3
  - m2.5
  - hailuo
cjk_tokens:
  - 海螺
must_have_none:
  - hailuo-2.3
notes: Celebrity Hailuo noise. Require MiniMax/M* .
```

**qwen** (existing):
```yaml
canonical_handles:
  - QwenLM
must_have_any:
  - qwen
  - qwen2.5
cjk_tokens:
  - 通义
  - 通义千问
```


**deepseek**:
```yaml
canonical_handles:
  - deepseek_ai
must_have_any:
  - deepseek
  - v3
  - deepseek-r1
cjk_tokens:
  - 深度求索
```

**glm**:
```yaml
canonical_handles:
  - ZhipuAI
must_have_any:
  - glm
  - glm-4
  - chatglm
cjk_tokens:
  - 智谱
```

**xiaomi_mimo**:
```yaml
canonical_handles:
  - XiaomiMiMo
must_have_any:
  - mimo
  - "xiaomi mimo"
cjk_tokens:
  - 小米
  - 米莫
notes: Bare mimo collides with kids app. Use Call C too.
```

**inclusionai**:
```yaml
canonical_handles:
  - InclusionAI
must_have_any:
  - inclusionai
  - ring-1
  - ling-mini
must_have_none:
  - tolkien
  - wwe
  - fanfic
notes: Inclusion generic - require product names.
```


**doubao** (new):
```yaml
canonical_handles:
  - doubaoAi
must_have_any:
  - doubao
  - "doubao ai"
  - 豆包
  - seed-vl
cjk_tokens:
  - 豆包
  - 豆包大模型
must_have_none:
  - snack
notes: 豆包 = snack word too. Prefer Call C co-occurrence.
```

**yi** (new):
```yaml
canonical_handles:
  - 01AI_Yi
must_have_any:
  - "01.ai"
  - "yi llm"
  - 零一万物
cjk_tokens:
  - 零一万物
notes: Yi common name. Co-occurrence gate recommended.
```

**sakana** (new):
```yaml
canonical_handles:
  - SakanaAILabs
must_have_any:
  - sakana
  - "sakana ai"
must_have_none:
  - fish
  - sushi
  - restaurant
notes: Sakana = fish JP. High noise; Call C + min_faves.
```

**kuaishou** (new):
```yaml
canonical_handles:
  - KwaiYii
must_have_any:
  - kuaishou
  - kwaiyii
cjk_tokens:
  - 快意
must_have_none:
  - video
  - app
notes: Kuaishou primarily video app brand.
```


**llama** (new):
```yaml
canonical_handles:
  - Llama
must_have_any:
  - llama
  - "llama 3"
  - "meta llama"
notes: Llama reasonably specific in AI context.
```

**mistral** (new):
```yaml
must_have_any:
  - mistral
  - mixtral
must_have_none:
  - weather
  - meteorology
notes: Also weather term. Use context in Call C.
```

**stepfun** (new):
```yaml
must_have_any:
  - stepfun
  - "阶跃星辰"
must_have_none:
  - dance
  - choreography
notes: Step + context (LLM) needed.
```

**ernie** (new):
```yaml
must_have_any:
  - ernie
  - "文心一言"
must_have_none:
  - "sesame street"
  - bert
notes: Collides with Sesame Street / BERT variant.
```

**hunyuan** (new):
```yaml
must_have_any:
  - hunyuan
  - "腾讯混元"
must_have_none:
  - philosophy
notes: Also philosophical term.
```


**nvidia_nemo** (new):
```yaml
canonical_handles:
  - NVIDIAAIDev
must_have_any:
  - nemo
  - "nvidia nemo"
  - megatron
```

**exaone** (new):
```yaml
canonical_handles:
  - LGAIResearch
must_have_any:
  - exaone
  - "lg ai"
```

**sensechat** (new):
```yaml
canonical_handles:
  - SenseTimeAI
must_have_any:
  - sensechat
  - sensenova
  - 商汤
cjk_tokens:
  - 商汤
  - 日日新
```

**upstage** (new):
```yaml
canonical_handles:
  - upstageAI
must_have_any:
  - upstage
  - solar
  - "solar pro"
notes: Theater term rare in AI.
```

Create the 13 missing filter files. Update the 7 existing.


## Canonical Handles Summary (from accounts/ + filters/)

- minimax: MiniMaxAI, MiniMaxM3, MiniMax_Hailuo
- qwen: QwenLM, Alibaba_Qwen
- deepseek: deepseek_ai
- glm: Zhipuai_org (acc); ZhipuAI, THUDM (filter)
- xiaomi_mimo: XiaomiMiMo
- moonshot_kimi: MoonshotAI ; Kimi_Moonshot, dotey (filter)
- inclusionai: inclusionAI ; InclusionAI, inclusionai_lab
- doubao: doubaoAi
- yi: 01AI_Yi
- llama: Llama
- nvidia_nemo: NVIDIAAIDev
- sensechat: SenseTimeAI
- exaone: LGAIResearch
- kuaishou: KwaiYii
- sakana: SakanaAILabs
- upstage: upstageAI
- mistral/stepfun/ernie/hunyuan: none yet (add after confirm)

Update filters with staff/press handles. Accounts feed Call A list.


## Implementation Notes for Collection Layer

1. Token sourcing in queries yamls: query_plan.py _load_brand_tokens_per_model parses first ( ... ) from Q2/Q3/Q5/Q6. Update yamls -> Call B updated automatically. No code change.

2. Call B: _build_brand_wide_query produces OR-of-ORs. Respects call_b_groups.

3. Call C: in config.yaml call_c_specs for noisy (extend for doubao/sakana etc).

4. Post-fetch: run.py filter_and_review -> relevance.filter_posts + load_filter. Canonical bypass, must_have keep, must_have_none soft to review.

5. queries.py / attribution.py use tokens for routing.

6. Migration: edit the yamls, create missing filters, audit handles with relevance tool, run test cycle.


## Tips for Disambiguation, Volume, Using Existing Infrastructure

- Broad collection (queries tokens for Call B) then tighten with filters/Call C.
- Hierarchy: from:/canonical > Call C co-oc > must_have_any (specific) > must_have_none (soft) > min_faves / -is:retweet.
- Volume: daily_ceiling, query_rot, per-model thresholds.
- Account graph + list for Call A high signal.
- CJK listed separately in filters.
- Initial: wide + low min_faves, review queue, promote real, refine.
- Chinese brands: high CJK, pair with taxonomy from docs/research/.
- Audit after cycles.
- No seeding at collection -> unbiased for taxonomy (Type/Sentiment/Aspects).
- Groups: keep call_b_groups; split if needed.


## Full Model Coverage Checklist (20 from config.yaml)

All have queries yamls. Filters for ~7; drafts for all.

1. minimax (queries+filter)
2. qwen
3. deepseek
4. glm
5. xiaomi_mimo
6. moonshot_kimi (exact kimi filter example)
7. inclusionai
8-20. mistral, stepfun, ernie, hunyuan, llama, nvidia_nemo, doubao, yi, sensechat, exaone, kuaishou, sakana, upstage (drafts provided)

## Next Steps

- Edit data/queries/*.yaml and create/update data/filters/ (PR).
- Extend call_c_specs for noisy brands.
- Test cycle (low ceiling), review output + review queue.
- Align with taxonomy in docs/research/ (4 buckets etc).
- Consider tooling flag for wide_net queries.

Pure brand mentions at collection; rich post-fetch classification and filtering.

