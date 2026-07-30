---
title: "Hybrid Harvest Funnel — Bare Pure + Handles + Minimal C Co + C-Only LLM - Plan"
type: feat
date: 2026-07-28
amended: 2026-07-28
amendment_note: "C returns to co-occurrence but minimal (foreign-first loanwords); not bare-C-only; not full-22; optional not_include for hijacks"
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
deprecated: true
deprecated_on: 2026-07-30
deprecated_by: U14 of 2026-07-30-002
superseded_by: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
deprecation_reason: "Amended and merged into the combined plan above. The hybrid funnel half became U1-U8 in the combined plan. Do not re-implement from this file."
---

# Hybrid Harvest Funnel — Bare Pure + Handles + Minimal C Co + C-Only LLM - Plan

> **DEPRECATED 2026-07-30.** Superseded by `docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md` (U14 of that plan). Do not implement from this file.

### written by Grok 4.3

## Goal Capsule

**Objective.** Maximize relevant harvest (especially **foreign-language** posts) with a hybrid funnel:

- **B1** high-purity brand keywords, **bare** (no co)
- **B2 / B3** official `@handles` only (pure brands vs other brands)
- **C1 / C2 / C3** ambiguous brands + a **minimal co-occurrence AND** (Latin stack loanwords), **not** the old 22-term list
- Optional **`not_include`** for stable hijacks (F1/Kimi, …)
- **Binary LLM relevancy on C only**; full classify on keepers
- Dirty primary demotions; anomaly metrics for fetch spikes / keep-rate crashes

**Authority.** Supersedes earlier drafts in this file (handles-in-keyword-groups; bare C + not_include-only; full-22 co). Session-settled: hybrid; C uses **thin co** for foreign capture; B1 bare; handles separate; C-only LLM.

**Stop when.** 7-call plan live; B1 bare; C thin co (≤8 terms, allowlisted); no xiaomi/小米/moonshot in co; handles on B2/B3 only; primaries cleaned; C-only relevancy tested; metrics in summary; reference doc updated; regression nets green.

**Out of band.** Call A list membership; staff handles in search strings; full 22-term co restore; large native ja/ko co packs unless later justified; full classify as relevancy.

---

## Product Contract

### Summary

**Fetch-wide / filter-staged:** pure brands bare on B1; @mentions via B2/B3; ambiguous brands on C with **minimal co** (`llm|model|api|agentic|huggingface` [+ optional moe/ollama/coding; C2 may add baidu/文心]); optional hijack `not_include`; residual noise via **C-only binary LLM**; translate/classify keepers only.

### Problem Frame

1. Call A = posts **by** list members only. `list:` ≠ mentions (`@user` does).
2. **Full 22 co** kills foreign recall (~55–75% of relevant non-EN samples lacked those cos) and brand-tethers (`xiaomi`/`moonshot`) poison other brands.
3. **Bare C** maximizes foreign recall but floods EN dictionary noise.
4. **Minimal co** (Latin loanwords common in ja/ko/id/tr tech posts) is the compromise for foreign-first + light AI-context.
5. Dirty primaries and retired `must_have_none` left precision in the wrong layer (co instead of selective bans).

### Requirements

#### Call layout

- R1. **7 calls:** A, B1, B2, B3, C1, C2, C3.
- R2. **A:** `(list:<id>) min_faves:0` unchanged.
- R3. **B1 pure keywords bare:** cleaned primaries; `co_occurrence: []`; no `@handles`.
- R4. **B2 pure-brand official handles only.**
- R5. **B3 other-brand official handles only** (C1+C2+C3 brands).
- R6. **C1/C2/C3:** brand token groups + **minimal co**; no handles in C strings.
- R7. Handles not stored as `brand_keywords` for harvest; attribution still via `user_mentions` ids.

#### Minimal co-occurrence (C only)

- R8. **Default shared minimal co (5 terms):**  
  `llm`, `model`, `api`, `agentic`, `huggingface`
- R9. **Optional expansions (total co terms per C call ≤ 8):** `moe`, `ollama`, `coding`.  
  **C2 only** may also add `baidu`, `文心`.
- R10. **Never in shared co** (unless explicit brand-local exception PR):  
  `xiaomi`, `小米`, `moonshot`, bare `agent`, bare `code`, bare `release`, bare `ai`.
- R11. Rationale: thin AND keeps light AI-context; loanwords appear in many non-EN tech posts; full 22 is out.

#### Optional `not_include` (C)

- R12. C specs may list `not_include: [...]` for stable hijacks (e.g. F1/Kimi: f1, antonelli, mercedes, …).
- R13. Apply as query-time `-term` (ASCII-safe) and/or post-fetch ban match (reuse `relevance.py` matchers). Complements thin co; does not replace it.
- R14. B1/B2/B3 do not require `not_include`.

#### Primary hygiene

- R15. Demote dirty primaries: `m2.5`, bare `海螺`; bare `Mistral` → prefer `Mistral AI` + `Mixtral`; bare `混元`; bare `GLM` (keep ChatGLM/Zhipuai/智谱); drop bare Ling/Ring/日日新/LG AI from primary if present.
- R16. B1 pure brands: deepseek, qwen, minimax, stepfun, mistral, hunyuan, glm, inclusionai, exaone, sakana_ai, nemo_megatron.

#### Renderer / length / LLM / metrics

- R17. Empty co omits secondary paren (`()` forbidden).
- R18. All planned strings &lt; 512.
- R19. Binary LLM relevancy only for C\* source **or** C-tier brand attribution.
- R19a. **Proposed binary relevancy prompt** (system + user; ship as constants in U6; tweak only via PR):

  **System:**
  ```
  You are a relevance filter for AI/LLM industry monitoring.

  Decide if a social post is ABOUT an AI model, LLM product, lab, API, agent framework,
  or related ML research/product discussion — not merely sharing a word that also names
  a brand (sports, cars, animals, people, consumer gadgets, finance ticker noise).

  Output EXACTLY one token on the first line: KEEP or DROP.
  Optional second line: short reason (≤12 words), English ok.

  Rules:
  - KEEP when the post discusses the AI product/lab/model/API even if the language is
    Japanese, Korean, Chinese, Indonesian, Turkish, Spanish, etc. Latin brand tokens
    and loanwords (llm, model, api) often appear in non-English tech posts — that is fine.
  - KEEP when uncertain but the post plausibly concerns AI/ML (multilingual keep bias).
  - DROP pure sports/F1/racing, pure consumer phone/gadget unboxing with no AI product
    angle, pure name-homonym chatter, spam, or empty engagement bait.
  - DROP if the only match is a bare ambiguous token with no AI product context.
  - Do not translate the post. Do not classify sentiment or post type.
  ```

  **User:**
  ```
  Brand context (may be empty): {brand_hints}
  Call id: {call_id}
  Post text:
  ---
  {post_text}
  ---
  Reply KEEP or DROP.
  ```

- R20. Full translate/classify only after keep.
- R21. Summary metrics: fetch_n, not_include drops, llm drops, keep rates per call (anomaly ops).
- R22. Reference doc + CONCEPTS updated.

### Acceptance Examples

- AE1. `@MiniMax_AI cool` matches **B2**; `user_mention` → minimax.
- AE2. Post with `Kimi` + `llm` or `api` matches **C1** thin co (including many foreign tech posts that code-switch).
- AE3. Pure sports Kimi without co terms does **not** match C1 search.
- AE4. F1 + antonelli excluded if `not_include` seeded.
- AE5. B1 has no co secondary; C co ≤ 8 terms and ⊆ allowlist; no xiaomi/moonshot in co.
- AE6. Pure JA with only モデル/公開 and brand name may still miss C (accepted); multiword primaries + handles cover other paths.

### Scope Boundaries

**In:** config reshape; query_plan empty-co + C thin co; handle-only B2/B3; primary migration; optional not_include; C-only relevancy; metrics; tests; docs.

**Out:** Full-22 restore; staff handles; Call A list membership; LLM on A/B; large native co packs by default.

#### Deferred

- Soft-drop review queue for not_include.
- Brand-local co exceptions after anomaly fire.
- Expanding minimal co with ja/ko natives if metrics demand.

### Success Criteria

- 7-call plan; B1 bare; C thin co live; handles B2/B3; primaries cleaned; C LLM gated; metrics present; docs match; tests green.

---

## Planning Contract

### Key Technical Decisions

- KTD1. **Hybrid funnel.** B1 bare + handle calls wide; **C uses minimal co**; staged filter (optional not_include → C LLM → full classify). (session-settled: user-directed — thin co for C / foreign-first, not full-22, not bare-C-only)

- KTD2. **Call roles:** A list · B1 pure bare · B2 pure `@handles` · B3 other `@handles` · C\* keywords **+ minimal co** · no handles on C.

- KTD3. **No `list:` for mentions** — B2/B3 are `@handle` ORs from official `brands_accounts`.

- KTD4. **Empty co omits `()`** on B1 (and any empty-co spec).

- KTD5. **Minimal co allowlist** R8–R10 is the C default; optional `not_include` for hijacks.

- KTD6. **C-only binary LLM relevancy.**

- KTD7. **Anomaly metrics** on fetch_n / keep rates.

- KTD8. **Primary demotions** via idempotent migration.

- KTD9. **Config source:** `x_query_specs[].co_occurrence` (minimal) + optional `not_include`; no retired-only yaml path.

### High-Level Technical Design

```text
plan_calls
  A:   list:…
  B1:  bare pure primaries, co=[]
  B2:  (@pure_official_handles…)
  B3:  (@other_official_handles…)
  C*:  (brand tokens) (llm OR model OR api OR agentic OR huggingface [+…])
       optional -not_include terms

fetch → attribute
  → not_include post-fetch (if any)
  → C-only llm_binary_relevancy
  → translate + classify (keepers)
  → summary metrics
```

### Alternatives Considered

| Approach | Why not default |
|---|---|
| Full 22 co | Foreign loss; brand-tether poison |
| Bare C (no co) | Max foreign recall, higher EN noise |
| Large ja/ko native co | Length + ops burden |
| LLM on all calls | Cost on pure/handle paths |
| list: for mentions | Wrong operator semantics |

### Risks

- Thin co still misses pure-local wording (accepted; mitigate with multiword primaries + handles).
- `model` still admits some device noise → not_include + C LLM.
- Cursor/noise volume → limits + metrics.

---

## Implementation Units

### U1. Pin harvest surface regression net

**Goal.** BEFORE/AFTER pins for 7-call layout, B1 bare, C thin co allowlist, handle-only B2/B3.

**Files.** `tests/test_hybrid_harvest_regression_net.py`

**Approach.** Pin no xiaomi/moonshot in C co; C co length ≤ 8; B1 no secondary; all &lt; 512.

**Verification.** pytest green as later units land.

---

### U2. Renderer: empty co omit; handle-only; C thin co

**Goal.** `_build_query` supports bare, handle-only, and thin-co C shapes.

**Files.** `x_monitor/query_plan.py`; `tests/test_query_plan_hybrid_shapes.py`

**Approach.** Empty co → no `()`; handle-only OR of `@h`; C still `(primary) (co) min_faves`.

**Verification.** Unit tests.

---

### U3. Config + handle wiring (7 calls)

**Goal.** Live config produces A/B1/B2/B3/C1/C2/C3 with thin co on C.

**Files.** `config.yaml`; `monitor/cycle.py`; store/run handle loaders; `tests/test_cycle_call_layout.py`

**Approach.** B1 co=[]; C co=minimal set; B2/B3 handle maps from official role; C3 new brands.

**Verification.** plan_calls shape tests + call-preview.

---

### U4. Primary demotion migration

**Goal.** DB is_primary matches purity table (R15–R16).

**Files.** Django data migration; `tests/test_primary_purity_seed.py`

**Verification.** Idempotent seed tests.

---

### U5. C minimal co + optional not_include

**Goal.** Enforce allowlist co; optional hijack exclusions.

**Files.** `config.yaml`; `query_plan.py` (optional `-` append); `relevance.py` matchers; `cycle.py`; `tests/test_c_minimal_co_and_not_include.py`

**Approach.** Pin co ⊆ allowlist; seed F1 not_include for C1 if length allows; post-fetch ban path; counters.

**Test scenarios.** C1 has thin co; no xiaomi in co; B1 bare; optional -antonelli; length &lt; 512.

**Verification.** Unit + preview.

---

### U6. C-only binary LLM relevancy

**Goal.** Binary keep/drop for C-path / C-brand only.

**Files.** `x_monitor/relevancy.py` (or attribution); `monitor/cycle.py`; `tests/test_c_relevancy_gate.py`

**Approach.** Gate by call_id or C brand; ship **R19a** prompt as module constants (`BINARY_RELEVANCY_SYSTEM`, user template); parse first-line `KEEP`/`DROP` (case-insensitive); multilingual keep bias on uncertain / parse-fail → KEEP (log); full classify only keepers. No translate step before this gate.

**Proposed prompt.** See **R19a** (source of truth for copy). Summary of intent:

| Signal | Decision |
|---|---|
| AI model / lab / API / agent discussion (any language) | KEEP |
| Uncertain but plausible AI/ML | KEEP (bias) |
| Sports F1 / pure gadget / homonym / spam | DROP |
| Bare token, no AI context | DROP |

**Verification.** Fake client tests: KEEP/DROP parse; uncertain→KEEP; non-EN sample with brand+loanword → KEEP path; gate skipped for A/B.

---

### U7. Anomaly metrics in cycle summary

**Goal.** fetch_n / drop / keep rates per call for ops detector.

**Files.** `monitor/cycle.py`; summary JSON; `tests/test_cycle_anomaly_metrics.py`

**Verification.** Summary keys present.

---

### U8. Reference docs + AFTER pins

**Goal.** Docs + U1 AFTER match shipped behavior.

**Files.** `docs/reference/twitterapi-live-queries-by-model.md`; `CONCEPTS.md`; U1 tests.

**Verification.** pytest + call-preview.

---

## Proposed live query strings (review)

**Minimal co:** `(llm OR model OR api OR agentic OR huggingface)`  
**C2 add-ons:** `baidu`, `文心` as needed.

| Call | Role | ~chars | Cap |
|---|---|---:|---|
| A | list posts-by | 38 | ok |
| B1 | pure keywords bare | 281 | ok |
| B2 | pure official handles | 317 | ok |
| B3 | other official handles | 214 | ok |
| C1 | polysemes + min co | ~300 | ok |
| C2 | ernie/upstage + min co (+baidu/文心) | ~180 | ok |
| C3 | doubao/sensechat/kuaishou + min co | ~170 | ok |

### A

```
(list:2067062923525275922) min_faves:0
```

### B1 — pure bare

```
((DeepSeek OR deepseek-r1 OR 深度求索) OR (Qwen OR Qwen3 OR 通义千问) OR (Hailuo OR MiniMax) OR (StepFun OR 阶跃星辰) OR (Mistral AI OR Mixtral) OR (Hunyuan OR 腾讯混元) OR (ChatGLM OR Zhipuai OR 智谱) OR (InclusionAI) OR (EXAONE) OR (Sakana AI OR サカナAI) OR (Megatron-LM OR NVIDIA NeMo)) min_faves:0
```

### B2 — pure handles

```
(@deepseek_ai OR @Ali_TongyiLab OR @Alibaba_Qwen OR @hailuo_ai OR @MiniMax_AI OR @MiniMaxAgent OR @StepFun_ai OR @stepfunai OR @MistralAI OR @TencentHunyuan OR @Zai_org OR @ZhihuFrontier OR @AntLingAGI OR @robbyant_brain OR @TheInclusionAI OR @LG_AI_Research OR @SakanaAILabs OR @NVIDIAAI OR @NVIDIAAIDev) min_faves:0
```

### B3 — other handles

```
(@bytedanceoss OR @BytePlusGlobal OR @doubaoai OR @SenseTime_AI OR @Kling_ai OR @XiaomiMiMo OR @XiaomiMiMoDevs OR @Kimi_Moonshot OR @01AI_Yi OR @AIatMeta OR @ErnieforDevs OR @PaddlePaddle OR @upstageai) min_faves:0
```

### C1 — + minimal co

```
((MiMo OR Xiaomi MiMo OR 小米 MiMo) OR (Kimi OR Moonshot AI OR 月之暗面 OR 暗面 OR MoonshotAI) OR (Yi OR 01.AI OR 零一万物 OR Yi LLM OR Yi-VL OR Yi-Coder) OR (Llama OR Llama 3 OR Llama 4 OR Meta Llama OR Code Llama OR Muse Spark)) (llm OR model OR api OR agentic OR huggingface) min_faves:0
```

### C2 — + minimal co (+ baidu/文心)

```
((ERNIE OR 文心一言) OR (Upstage OR Solar Pro OR Solar LLM OR 업스테이지)) (llm OR model OR api OR agentic OR huggingface OR baidu OR 文心) min_faves:0
```

### C3 — + minimal co

```
((Doubao OR ByteDance) OR (SenseChat OR SenseTime) OR (Kuaishou OR KwaiYii)) (llm OR model OR api OR agentic OR huggingface) min_faves:0
```

### Notes

1. Multi-word unquoted = live renderer style.
2. Optional C1 `not_include` may append `-f1 -antonelli …` if under 512 (U5).
3. B2/B3 are **not** `list:` — mentions need `@handle`.
4. Thin co is foreign-first compromise: better than full 22; not as open as bare C.
5. Pure local wording without Latin cos may still miss C (accepted).

---

## Verification Contract

- pytest: hybrid regression, query shapes, primary seed, C thin co allowlist, optional not_include, C relevancy, metrics
- call-preview: 7 calls, B1 bare, C thin co, B2/B3 handles, all &lt; 512
- optional live: JA/KO tech posts with `llm`/`api`/`model` loanwords appear in C; F1 Kimi blocked if not_include seeded

## Definition of Done

- [ ] U1 AFTER green
- [ ] Empty co omits `()` on B1
- [ ] 7-call layout live
- [ ] C minimal co (not full 22) live
- [ ] Primary demotions applied
- [ ] Optional not_include path available / seeded where agreed
- [ ] C-only binary relevancy live
- [ ] Anomaly metrics in summary
- [ ] Reference + CONCEPTS updated
- [ ] Scope delivered vs plan documented in commits

---

## System-Wide Impact

- Foreign recall **up** vs full-22 (thin loanword cos).
- EN noise **up** vs full-22, **down** vs bare C → C LLM + optional not_include.
- Onboard new models: add tokens/handles; C only if polysemous; watch anomaly metrics.

## Documentation / Operational Notes

- Ship renderer empty-co before B1 bare config.
- Changing minimal co allowlist is a product PR (not ad-hoc 22 expansion).
- If one C brand explodes: tighten primary or not_include — do not restore full 22 by default.

## Sources & Research

- Session purity probes; foreign-lang miss rates under full 22; LG AI + xiaomi co poison; B3 bare then revert history; relevance.py must_have_none retired 2026-07-11-001; X operators list: vs @.
- Live pre-change lengths: A 38 / C1 461 / C2 295 / B1 414 / B2 377 / B3 359.

