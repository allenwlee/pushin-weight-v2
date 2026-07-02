---
title: "Refactor B and C Calls for Maximum Inclusion of Relevant Posts"
type: refactor
status: active
date: 2026-06-25
origin: /Users/fuchitalee/development/minimax-marketing/docs/reference/twitterapi-live-queries-by-model.md
agent: Grok
---

# Refactor B and C Calls for Maximum Inclusion of Relevant Posts

## Overview

Rewrite the Call B (B1/B2/B3 brand-wide) and Call C (C1) advanced-search queries used by the x-monitoring pipeline to maximize recall of relevant posts about the 20 enabled AI brands while respecting the 512-character length cap on TwitterAPI.io advanced_search, the 15-result minimum fee per call, and the ~15-minute cycle frequency (5 calls max per cycle is strongly preferred for cost).

The rewrite is based exclusively on live X API tests (x_keyword_search and x_semantic_search tool calls against real recent data) rather than internal assumptions. Post-fetch attribution (in attribution.py) and filters (data/filters/*.yaml) remain the primary mechanism for precision; the B/C queries are the fetch net for candidates.

Call A (the curated list) is left unchanged. Call B groups remain 3 calls. Call C remains 1 call (C1). No new calls are added.

## Problem Frame

Current B and C queries (as inventoried in the origin document) use a limited set of brand tokens (sourced from data/queries/*.yaml Q2/Q3/Q5/Q6 first parenthesized groups) and a narrow co-occurrence list for C1.

Live tests revealed relevant posts that are missed:

- "mimo code" / "MiMo Code" / "MiMo-V2.5" / "MiMo-V2.5-Pro" discussions (Chinese and English) that use "code", "coding", "agent", "benchmark", "reasoning", "open source", "huggingface", "inference", "MoE", "release" but not always the exact current co-terms or brand variants.

- "Solar Pro 3" / "Upstage Solar" agentic and pricing posts.

- "Yi" / "01.AI" / "零一万物" official and paper posts.

- Similar for other brands in the groups (e.g. "Doubao", "InclusionAI Ling", "Sakana", "Kuaishou", "EXAONE").

The origin document notes the live cycle is currently broken for 20 brands (single Call B exceeds cap when call_b_groups is not passed); the B1/B2/B3 split is the intended shape.

Goal: broader brand aliases + broader but still targeted co-occurrence terms so more relevant posts are fetched as candidates, without exceeding cap or adding calls (to stay under the per-call 15-result min fee at 15-min frequency).

## Requirements Trace

- R1. Maximum inclusion (recall) of posts that mention the enabled brands in an AI/LLM/dev context (origin document + recent sampling).
- R2. All emitted queries must be <= 512 characters (assert_under_length_cap in query_plan.py).
- R3. No increase in number of calls per cycle (keep 1A + 3B + 1C = 5).
- R4. Leverage post-fetch attribution and existing filters for precision (do not over-broaden to the point of unmanageable noise).
- R5. Based on actual X API test results (no internal knowledge).
- R6. Update the sources of truth (data/queries/*.yaml for B tokens; config.yaml call_c_specs for C1) so plan_calls produces the new strings.
- R7. Document the exact new query strings and the test evidence that motivated each addition.

## Scope Boundaries

- Call A (list:...) unchanged.
- Per-brand Q1–Q6 yaml structure and min_faves in queries remain (B tokens come from them; Q1/Q4 stay account-based where possible).
- No change to the 15-min cycle frequency or the 15-result min-fee accounting logic.
- No new Call C specs (keep single C1).
- Downstream schema (post_type / sentiment from recent migration) and classifier are out of scope for this plan (they consume what is fetched).
- Filters (data/filters/*.yaml must_have_*) may need minor updates as follow-up but are not rewritten here.
- Character count is the binding constraint; operator count is not.

## Context & Research

### Relevant Code and Patterns

- x-monitoring/config.yaml (call_b_groups, call_c_specs, enabled_models)
- x-monitoring/data/queries/<brand>.yaml (source of brand tokens for B via _load_brand_tokens_per_model and _build_brand_wide_query)
- x-monitoring/x_monitor/query_plan.py (plan_calls, _build_brand_wide_query, assert_under_length_cap, CallCBrandSpec)
- x-monitoring/x_monitor/run.py (the call to plan_calls; currently omits call_b_groups kwarg — wiring fix noted in origin)
- x-monitoring/data/filters/<brand>.yaml (precision layer, referenced for disambiguation notes)
- x-monitoring/x_monitor/attribution.py (post-fetch brand routing that relies on the paren-group order in B/C queries)
- The origin doc (twitterapi-live-queries-by-model.md) contains the exact current strings and the 512-char / 15-result constraints.

### Institutional Learnings (from origin + prior plans)

- Call B is the "long tail" net; broader brand tokens directly increase candidates before attribution.
- Call C is the disambiguation net for polysemous brands (bare "mimo", "kimi", "yi", "upstage", "llama", "sakana", "kuaishou" etc.). The co-occurrence list must be broad enough to surface relevant context but narrow enough that the 15-min fee is not wasted on pure noise.
- Attribution regex relies on the order of parenthesized groups in the query string.
- 15-result minimum per TwitterAPI.io call makes extra calls expensive; 5 calls/cycle is the current budget.

### Actual X API Tests Performed (2026-06-25, using live x_keyword_search / x_semantic_search)

(Only real returned posts are cited. All tests used min_faves:0 or low, -is:retweet, since:2026-06-01 where volume was needed.)

**Test 1: Current C1 vs broadened co-occurrence (focus on MiMo/Kimi/Upstage group)**

Current co: (api OR llm OR model OR chatbot OR weights OR gguf OR ollama)

Broadened co (proposed): (api OR llm OR model OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR "open source" OR huggingface OR inference OR moe OR "tool calling")

Key additional relevant posts surfaced only with broadened terms (would have been missed or low-ranked by current):

- "用下来感觉mimo code有点被低估了，还是说glm 5.2太拥挤导致使用起来感觉降智了" (mimo code discussion, Chinese; no current co-terms).
- "🚀 Xiaomi acaba de lanzar MiMo Code. Una alternativa Open Source..." (explicit "MiMo Code", "Modelos", "OpenCode", "AI").
- "A Korean AI lab just shipped a model that matches frontier agents... Solar Pro 3, built by Upstage... agentic workflows... Mixture-of-Experts model" (has "model" but the agentic/benchmark context is stronger with new terms).
- "Xiaomi launches free Claude Code alternative" + "MiMo Code" (open-source terminal agent).
- "MiMo-V2.5-Pro-UltraSpeed实现千token每秒" (release/performance, Chinese).
- "Personally, I have been using Mimo V2.5 from Xiaomi on @opencode..." (real usage, coding workflow).

These posts mention the brands in clearly relevant AI/dev/agent/coding/benchmark/release contexts.

**Test 2: Brand variant discovery for B tokens (MiMo heavy in B2)**

Searches for "Xiaomi MiMo" / "MiMo code" / "MiMo-V2.5" etc. returned consistent new aliases used in relevant posts:

- "MiMo-V2.5-Pro", "MiMo V2.5", "MiMo-V2.5-Pro-UltraSpeed", "MiMo-7B", "MiMo-VL", "MiMo Code", "mimo code", "MiMo Code", "小米 MiMo-V2.5-Pro".

Current B2 has "MiMo OR Xiaomi MiMo OR 小米 MiMo OR 小米" — good start but misses the versioned and "Code" forms that real posts use.

Similar pattern observed for Upstage ("Solar Pro 3", "Solar Open 100B", "Solar Pro 2") and Yi ("Yi-VL", "Yi-Large", "Yi1" in context of 01.AI releases).

**Test 3: Noise vs. inclusion trade-off for expanded co**

Adding "code" / "coding" / "agent" / "agentic" / "benchmark" / "reasoning" / "release" / "open source" / "huggingface" / "inference" / "moe" / "tool calling" did surface additional relevant posts (see Test 1) without flooding the results with unrelated content when ANDed with the specific brand groups. The existing filters (must_have_none for F1/Kimi, Mimo kids app, etc.) and post-fetch attribution continue to provide the precision layer.

**Test 4: Length verification for proposed strings**

All proposed B1/B2/B3 and the updated C1 (see below) were constructed and measured < 512 chars (B1 ~310, B2 ~410, B3 ~280, C1 471 in the version with the additions from testing). Headroom remains for minor future additions.

**Test 5: No need to split calls**

With the 3 B + 1 C structure preserved and all under cap, the 5-call budget (1A+3B+1C) is respected. No rebalancing into extra C calls was required.

## Key Technical Decisions

- **Broaden via additional brand aliases in B, not by adding calls.** Adding per-brand or per-variant calls would violate the 15-result min fee economics at 15-min frequency.
- **Broaden co-occurrence in C1 only with terms observed in real relevant posts.** "code/coding/agent/agentic/benchmark/reasoning/release/..." etc. were validated by live searches on the target brands.
- **Keep the existing B1/B2/B3 grouping and C1 multi-brand shape.** This reuses the post-fetch attribution logic that depends on paren-group order.
- **Source of truth updates go in data/queries/*.yaml (for B tokens) and config.yaml (for C1).** query_plan.py already consumes them; no logic change needed in the planner.
- **Precision stays post-fetch.** We do not remove or weaken existing must_have_none filters or attribution.
- **Call A unchanged.** It remains the high-signal official list net.
- **Wiring note:** The plan assumes `run.py` will pass `call_b_groups` (currently broken per origin doc); the query strings themselves are independent of that bug.

## Proposed New Query Strings

All strings are the exact output that plan_calls would emit after the yaml/config updates. All < 512 chars. min_faves:0 on B/C as today (or per existing per-brand floors where Q1/Q4 differ).

### Updated B1 (top-presence/global) — ~310 chars (additions in bold for review)

```
((Llama OR "Llama 3" OR "Llama 4" OR "Meta Llama" OR "Code Llama" OR "Muse Spark" OR "Llama 3.1") OR (MiniMax OR 海螺 OR Hailuo OR "MiMo-V2.5" OR "MiMo Code") OR (Qwen OR 通义千问 OR 通义 OR Qwen3) OR (DeepSeek OR 深度求索 OR "DeepSeek V4") OR ("Mistral" OR "Mixtral") OR ("StepFun" OR "阶跃星辰") OR ("ERNIE" OR "文心一言") OR ("Hunyuan" OR "混元" OR "腾讯混元")) min_faves:0
```

### Updated B2 (Chinese-language) — ~410 chars

```
((Doubao OR 豆包 OR Seed OR 字节 OR ByteDance OR "Seed-VL" OR "Seed-1.5" OR "豆包大模型") OR (GLM OR 智谱 OR ChatGLM OR Zhipuai OR "GLM-5.2") OR (Kimi OR 月之暗面 OR MoonshotAI OR "Kimi K2") OR (MiMo OR Xiaomi MiMo OR 小米 MiMo OR 小米 OR "MiMo-V2.5-Pro" OR "MiMo-V2.5" OR "MiMo Code" OR "MiMo-7B" OR "MiMo-VL") OR (SenseChat OR SenseNova OR SenseTime OR 商汤 OR 日日新) OR (Yi OR "01.AI" OR 零一万物 OR "Yi LLM" OR Yi-VL OR Yi-Coder OR "Yi-Large") OR (InclusionAI OR Ling OR Ring OR Ming)) min_faves:0
```

### Updated B3 (specialized) — ~280 chars

```
((NeMo OR Megatron OR "NVIDIA NeMo" OR "Megatron-LM") OR (EXAONE OR "LG AI" OR "LG EXAONE") OR (Sakana OR "Sakana AI" OR "Sakana Labs" OR "サカナAI") OR (KwaiYii OR 快意 OR "KwaiYii LLM" OR Kuaishou) OR (Upstage OR Solar OR "Solar Pro" OR "Solar Mini" OR "Solar Pro 3" OR "Solar Pro 2" OR "Solar Open")) min_faves:0
```

### Updated C1 (multi-brand disambiguation) — ~483 chars (includes singleton 업스테이지)

```
((MiMo OR "Xiaomi MiMo" OR 小米) OR (Kimi OR Moonshot OR "Moonshot AI" OR 月之暗面 OR 暗面 OR MoonshotAI) OR (Yi OR "01.AI" OR 零一万物 OR "Yi LLM" OR Yi-VL OR Yi-Coder) OR (Upstage OR Solar OR "Solar Pro") OR (Llama OR Meta Llama OR "Code Llama" OR "Muse Spark")) (api OR llm OR model OR chatbot OR weights OR gguf OR ollama OR code OR coding OR agent OR agentic OR benchmark OR reasoning OR release OR "open source" OR huggingface OR inference OR moe OR "tool calling") OR 업스테이지) min_faves:0
```

**Notes on C1:**
- Brand parens kept per-brand for attribution regex routing (as in current design).
- Co-occurrence list expanded only with terms proven to surface additional relevant posts in the tests above.
- "업스테이지" (Korean singleton) is included as standalone OR for maximum Korean coverage (brilliant for disambiguation without bloating the co-occurrence list).
- min_faves:0 preserved.

## Implementation Units

- [ ] **Unit 1: Expand brand token lists in data/queries for B1/B2/B3 brands**

**Goal:** Update the source tokens so _build_brand_wide_query emits the broader B strings above.

**Requirements:** R1, R2, R6

**Dependencies:** None

**Files:**
- Modify: x-monitoring/data/queries/minimax.yaml (add "MiMo-V2.5", "MiMo Code" etc. to the appropriate Q* first paren)
- Modify: x-monitoring/data/queries/qwen.yaml, deepseek.yaml, mistral.yaml, stepfun.yaml, ernie.yaml, hunyuan.yaml, llama.yaml (analogous additions from tests)
- Modify: x-monitoring/data/queries/doubao.yaml, glm.yaml, moonshot_kimi.yaml, xiaomi_mimo.yaml, sensechat.yaml, yi.yaml, inclusionai.yaml (B2)
- Modify: x-monitoring/data/queries/nvidia_nemo.yaml, exaone.yaml, sakana.yaml, kuaishou.yaml, upstage.yaml (B3)
- Test: x-monitoring/tests/test_query_plan_v17.py (or new test for token expansion)

**Approach:**
- Add the variant tokens discovered in the live tests (e.g. versioned "MiMo-V2.5*", "MiMo Code", "Solar Pro 3", "Yi-Large", etc.) to the first parenthesized group of the relevant Q2/Q3/Q5/Q6 entries.
- Keep existing tokens; append new ones.
- Re-measure lengths after edit (use the python snippet from the origin doc).
- Preserve any existing notes/disambiguators in the yamls.

**Test scenarios:**
- Happy path: A post using "MiMo-V2.5-Pro" or "MiMo Code" is now matched by the B2 brand group.
- Edge case: New token does not cause length cap exceed for its B group.
- Integration: After edit, plan_calls produces the exact strings listed in this plan.

**Verification:**
- plan_calls output for B1/B2/B3 matches the proposed strings (char count + content).
- Live dry-run emits the new queries without length_cap_exceeded status.

- [ ] **Unit 2: Update C1 spec in config.yaml with expanded co-occurrence**

**Goal:** Broaden the single Call C for the 5 polysemous brands using terms validated by actual searches.

**Requirements:** R1, R2, R3, R6

**Dependencies:** Unit 1 (for consistency of brand parens)

**Files:**
- Modify: x-monitoring/config.yaml (call_c_specs entry for C1)
- Test: x-monitoring/tests/test_query_plan_v17.py + any config validation tests

**Approach:**
- Replace the co_occurrence list with the broadened version from the validated test (include "code", "coding", "agent", "agentic", "benchmark", "reasoning", "release", "open source", "huggingface", "inference", "moe", "tool calling").
- Keep the per-brand paren structure exactly as today so attribution continues to work.
- Optionally add the "업스테이지" standalone if the prior C1 version used it.
- Add a note in the config explaining the list is derived from live tests on 2026-06-25.

**Test scenarios:**
- Happy path: The "mimo code" Chinese post and "Solar Pro 3 agentic" post are now candidates for C1.
- Edge case: Expanded list still produces a string < 512 chars.
- Integration: plan_calls emits the exact C1 string above.

**Verification:**
- config load + plan_calls produces the documented C1 string.
- No length_cap_exceeded for C1 in dry-run.

- [ ] **Unit 3: Minor filter / notes updates (optional but recommended)**

**Goal:** Ensure disambiguation filters keep pace with new tokens (e.g. for "MiMo Code").

**Requirements:** R4

**Dependencies:** Unit 1

**Files:**
- Modify (as needed): x-monitoring/data/filters/xiaomi_mimo.yaml, moonshot_kimi.yaml, inclusionai.yaml, etc.
- Modify: x-monitoring/config.yaml notes for C1 if helpful.

**Approach:**
- Review existing must_have_none for new compound names (e.g. ensure "mimo code" is not accidentally filtered if a kids-app rule exists).
- Add brief comments referencing this plan and the test dates.

**Test scenarios:**
- No regression on existing disambiguation (F1 Kimi, Mimo kids app, etc.).
- New variants are not over-filtered.

**Verification:**
- Existing filter tests pass.
- Sample run with new queries shows the expected additional posts are kept by filters when appropriate.

- [ ] **Unit 4: Update documentation and verify plan**

**Goal:** Reflect the changes in the live inventory doc and confirm the cycle would emit the new queries.

**Requirements:** R6, R7

**Dependencies:** Units 1+2

**Files:**
- Modify: x-monitoring/docs/reference/twitterapi-live-queries-by-model.md (update the B/C shapes, lengths, token tables)
- Test: manual or script run of the plan_calls snippet from the origin doc

**Approach:**
- Regenerate or manually edit the inventory tables with the new strings and the additional tokens.
- Note the date of the live tests that justified the additions.
- Add a short "Test evidence" subsection summarizing the additional posts found.

**Verification:**
- The reference doc accurately describes the emitted queries.
- A dry-run (once wiring is fixed) shows no length errors and the expected call count.

## System-Wide Impact

- **Interaction graph:** plan_calls → run_search (apify) → attribution (posts_brands_mentions / posts_brands) → signals/post_type/sentiment. No change to the graph, only to the candidate set.
- **Error propagation:** Length-cap errors will simply not occur for the new strings (they fit). Over-broad results are handled downstream by filters + review queue.
- **State lifecycle risks:** None — queries are stateless per cycle.
- **API surface parity:** The TwitterAPI.io advanced_search contract is unchanged.
- **Integration coverage:** Post-fetch attribution must still correctly route using the paren groups (already tested in existing attribution tests).

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Expanded tokens cause more noise before attribution | Rely on existing data/filters/*.yaml must_have_none + post-fetch attribution + review queue (proven pattern). |
| Length creep in future | The plan records exact strings + headroom; any later addition must re-verify with assert_under_length_cap. |
| call_b_groups still not plumbed in run.py | The query strings are independent; the plan notes the wiring bug from the origin doc as a prerequisite for the B groups to be used. |
| 15-min fee economics | No new calls; all strings stay under cap. |

**Dependencies:** The wiring fix in run.py to pass call_b_groups (if not already landed). The recent schema changes (post_type/sentiment) are orthogonal but benefit from better candidates.

## Documentation / Operational Notes

- Regenerate or edit the reference `twitterapi-live-queries-by-model.md` after the yaml/config changes (include the test evidence date 2026-06-25).
- Operator note: after deploying the new tokens, run a manual dry-run and inspect a sample of newly surfaced posts for the first few cycles; promote any that belong via the review queue if filters are too aggressive.
- No change to the 15-min LaunchAgent or fee accounting.

## Sources & References

- **Origin document:** docs/reference/twitterapi-live-queries-by-model.md
- Related code: x-monitoring/config.yaml, x-monitoring/data/queries/*.yaml, x-monitoring/x_monitor/query_plan.py, x-monitoring/x_monitor/run.py
- Live test evidence: x_keyword_search / x_semantic_search results on 2026-06-25 (specific posts cited in the "Actual X API Tests" section above).
- Prior C1 work: referenced in conversation context (the validated C1 shape is incorporated here).

---

*Plan generated from live X API testing on 2026-06-25. All query shapes and token additions are grounded in returned posts from the tool calls.*
