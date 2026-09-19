---
title: Model-specific optimization research for classification, translation, and commentary
date: 2026-09-17
type: research
---

# Model-specific optimization research

Each candidate gets its own attempt to deliver error-free results for its assigned task, with a bounded tuning budget.
The canonical execution plan is [U25–U29 in the enrichment plan](../plans/2026-09-08-134925-feat-ai-enrichment-stage1-plan.md#u25-freeze-model-specific-route-and-request-profiles).
This report contains documentation findings and starting hypotheses. The execution addendum below records the first route probe; semantic quality remains unassessed until the task trials are reviewed.

## Evidence and pricing boundary

All prices come from `docs/research/2026-09-17-143812-openrouter-pricing-snapshot/`, with manifest SHA-256 `28e5394ed2e9d15aca585d3c0556f8734720c14d7e970b83104ec251db839e52`.
The derived workload estimates are in `docs/research/2026-09-17-144306-snapshot-only-model-task-cost-screen/`.
Official web documentation below establishes capabilities and recommended interfaces, never a replacement price.
Catalog capabilities describe a model family across routes; only a pinned provider's capabilities and captured request/response establish a tested route.

| Candidate | Assigned tasks | Saved input/output USD per million tokens | Price evidence |
| --- | --- | --- | --- |
| Qwen3.7 Flash | Translation, commentary; classifier trials closed | 0.03 / 0.13 below 32,000 input tokens | Alibaba endpoint; larger inputs have separate saved tiers |
| Gemini 2.5 Flash-Lite | Translation, commentary; classifier trials stopped | Flex 0.05 / 0.20; standard 0.10 / 0.40 | Separate saved Google AI Studio endpoint tiers |
| Hy-MT2-1.8B | Translation | 0.044 / 0.177 | Catalog only; endpoint not captured |
| Hy-MT2-7B | Translation | 0.074 / 0.295 | Catalog only; endpoint not captured |
| GPT-OSS-120B | Commentary reserve only | 0.037 / 0.17 | Catalog only; endpoint not captured |
| GPT-5 Nano | Removed from remaining scope | 0.05 / 0.40 | Catalog only; endpoint not captured |
| DeepSeek V4 Flash 0731 | Owner-selected classifier | 0.06 / 0.18 | Pinned DeepInfra FP8 endpoint; catalog headline is a different price |

An endpoint not captured is **unknown**, not an empty endpoint list or an unavailable model.
Qwen and Gemini do have endpoint captures.
The four catalog-only candidates need endpoint coverage before an exact route can be budgeted; their catalog estimates cannot authorize inference on a guessed provider.
Any later coverage extension must be a new immutable snapshot, with its own manifest, adopted explicitly into the trial contract before pricing a call.

## What the tasks require

Classification needs exhaustive multi-label decisions, strict target-brand attribution, and distinctions between reporting, author stance, product experience, and promotional subjects.
Valid JSON does not establish any of these.
Translation needs fidelity to meaning, numbers, entity roles, uncertainty, idioms, and source formatting across the actual source-language distribution into EN/ZH-CN/JA.
Commentary needs grounded interpretation and useful explanation in three locales without importing facts from an unavailable image, parent, link, or model memory.
These are three quality rubrics, not one model-intelligence score.

The measured random100 commentary workload was about 279 input and 455 output tokens per served post; output was not negligible.
Classification's measured two-role workload was about 1,138 input and 138 output tokens per source post.
Translation was about 955 input and 513 output tokens per source post across generated targets.
These observations explain the initial shortlist, but each customized trial must measure its own usage, including reasoning.
Source: the snapshot-only cost screen and `docs/analysis/2026-09-17-133300-u20-random100-incumbent-vs-0731.md`.

## Qwen3.7 Flash on Alibaba through OpenRouter

The saved endpoint maps `qwen/qwen3.7-flash` to upstream `qwen3.7-flash-20260727`.
Alibaba's retrieved documentation describes generic Qwen3.7 Flash and a July 15 snapshot; exact July 27 behavior remains a route-verification question.
Native hybrid thinking defaults on and uses `enable_thinking`; its budget is `thinking_budget`.
Use OpenRouter's normalized reasoning controls only after verifying their mapping for this endpoint.
Hiding reasoning text is not disabling reasoning or its cost. [Alibaba thinking](https://www.alibabacloud.com/help/en/model-studio/deep-thinking), [OpenRouter reasoning](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

The saved route advertises `response_format`, temperature, top-p, seed, and presence penalty, but not `structured_outputs`.
Start classification with compact plain JSON and local schema validation, reflecting the successful 0731 representation lesson.
A separate tiny strict-schema probe is permitted only after provider support is established; it must not silently remove an unsupported parameter.
The current OpenRouter model page explicitly lacks JSON Schema enforcement; do not spend a probe on that unsupported mode without new capability evidence. [OpenRouter Qwen model documentation](https://openrouter.ai/qwen/qwen3.7-flash).
Alibaba's JSON-object mode requires an explicit JSON instruction, while JSON Schema is a distinct interface.
Do not assume native schema support proves gateway support. [Alibaba structured output](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen-structured-output), [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).

Proposed first profiles: retain the two classifier roles with five posts per request; use explicit thinking-off raw text for one source/target translation; use one source post for all three commentary locales.
If semantic errors remain, test a documented bounded thinking budget before adding another call.
Change temperature alone if needed; do not simultaneously sweep top-p.
The native temperature range is `[0,2)` and top-p is `(0,1]`; these are accepted ranges, not evidence that any setting is optimal. [Alibaba chat parameters](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions).

## Gemini 2.5 Flash-Lite

Use the stable `gemini-2.5-flash-lite`, not a retired preview.
Google documents structured output, thinking, a 1,048,576-token input limit and 65,536-token output limit; the selected host may impose tighter limits. [Model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite).
Native Flash-Lite defaults to no thinking; `thinkingBudget: 0` disables it, positive budgets start at 512, and `-1` enables dynamic budgeting.
Proposed trials use off initially, then 2,048 only for diagnosed semantic failures; avoid uncapped dynamic reasoning in the first experiment. [Thinking documentation](https://ai.google.dev/gemini-api/docs/generate-content/thinking).

Start classification with a compact schema using supported JSON Schema features and five posts per role request.
Translation starts as one-source/one-target raw text with thinking off.
Commentary starts with one source and a small object with the three locale fields.
Keep reasoning plus visible-answer headroom within the provider's combined limit.
Provider rejection of a complex schema calls for a simpler equivalent representation, not removal of required labels. [Structured output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).

Treat Flex and standard as separate operational profiles.
Flex may return capacity errors and has variable latency; native Google guidance recommends long timeouts and bounded backoff.
That guidance does not prove OpenRouter forwards every native field or that Flex meets this app's completion-time gate.
Pin the OpenRouter endpoint/tier and attest the served tier; never hide a standard-tier fallback inside a Flex cost result.
The saved Flex endpoint tag is `google-ai-studio/flex`; pin it with `provider.only` and request `service_tier: flex`, with provider fallbacks disabled. Standard is the separate `google-ai-studio` profile.
Offline Batch is a different service from packing several posts into one synchronous prompt and does not establish live-cycle latency. [Google Flex](https://ai.google.dev/gemini-api/docs/flex-inference), [OpenRouter service tiers](https://openrouter.ai/docs/guides/features/service-tiers).

## Hy-MT2-1.8B and Hy-MT2-7B

These are translation specialists, not proposed classifiers or commentators.
Tencent supplies user-message templates for translation, terminology, background context, and delimiter preservation, and lists EN/ZH/JA among its supported languages.
Start with its translation template, full language names, a small relevant glossary, and no inherited DeepSeek system prompt.
Use one source/target pair and raw text; preserve the application's paragraph and protected-token rules through the documented delimiter form.
Cross-post batching still needs its own evidence. [Tencent model card](https://huggingface.co/tencent/Hy-MT2-1.8B).

Tencent recommends temperature 0.7, top-p 0.6, top-k 20, repetition penalty 1.05, and a 4,096 generation allowance for these sizes.
The saved catalog advertises temperature but not the other sampling controls, so record which recommendations the selected host can actually apply.
Do not send silently ignored controls or treat an unavailable sampler as a semantic model failure.
The snapshot's 8,192 context requires source, instructions, glossary, and output to fit together.
Test 1.8B first and give 7B its own trial if the smaller model leaves fidelity failures; do not assume the larger model fixes them. [Tencent 7B card](https://huggingface.co/tencent/Hy-MT2-7B).

## GPT-OSS-120B and GPT-5 Nano

GPT-OSS uses Harmony internally, but a hosted Chat Completions API receives ordinary role messages; raw Harmony must not be pasted into the chat input.
Its reasoning levels are model-specific; start with a verified low-effort profile rather than assuming a generic off switch.
Native GPT-OSS uses `low`, `medium`, or `high`, defaulting to medium; an off setting is not part of that contract.
Use a compact classifier schema or a grounded three-locale commentary shape according to the verified host capabilities. [OpenAI open models](https://openai.com/open-models/), [Harmony](https://github.com/openai/harmony).

For exact `gpt-5-nano`, omit unsupported sampling controls, especially inherited temperature/top-p.
Start with provider-verified low reasoning and a compact structured classifier response; test a lower supported effort only as a separately measured profile.
Original GPT-5 Nano supports `minimal`, `low`, `medium`, and `high`, with medium the default; do not send later-family `none` or `xhigh`. Its official combined reasoning/output limit is 128,000 tokens, but the trial allowance should be sized to this workload and the selected host's effective limits.
Do not import newer GPT-family effort names or assume tiny visible JSON means tiny output billing.
Reasoning consumes output budget and can exhaust it before a usable answer appears. [GPT-5 Nano](https://developers.openai.com/api/docs/models/gpt-5-nano), [Reasoning accounting](https://developers.openai.com/api/docs/guides/reasoning).

Both candidates need exact endpoint evidence before any paid trial.
Their saved catalog fields do not prove provider schema dialect, reasoning mapping, quantization, or usage reporting.
They are reserves for a task that the first candidates cannot satisfy within the operating budget.

## Repository integration and unresolved execution facts

Reuse `scripts/u18_runtime_classifier_candidate.py` for classifier accounting and `scripts/u20_plaintext_translation_compare.py`, `scripts/u20_random100_live.py`, and `scripts/u20_translation_synthesis_execute.py` for frozen requests and response replay.
The last script currently has live-price preflight logic; a new trial must use the saved manifest instead.
The actual callers are `x_monitor/openrouter.py`, `x_monitor/literal_translation.py`, `x_monitor/synthesis.py`, and the classification caller; an experiment adapter must preserve their input and publication contracts.
Do not copy DeepSeek's accepted parameters into a universal profile.

Before each model's first quality run, the profile must resolve exact provider/model identity, accepted reasoning/sampling/output parameters, effective context/output limits, token accounting, endpoint/tier behavior, credential availability, and lifecycle.
Unknown compatibility is resolved by a separately budgeted small probe, not guessed during a full corpus run.
No new model can claim zero error merely because its output parses; reference blanks, unavailable context, unsupported languages, unresolved semantic reviews, and missing outputs remain visible.

## Execution addendum — September 17

The owner authorized up to three configuration attempts per model/task, with automatic diagnosis, delegated reports, and corrections. The owner subsequently replaced the 1% threshold: success now means equal or better reviewed quality than DeepSeek V4.1 Flash on matching source/context and required outputs, independently per task (R113 / Delivery Exception 30). Semantic, structural, transport and coverage failures count for both arms. Model disagreement alone is not error. Original frozen run criteria remain historical; decisions use versioned parity reassessments. Diagnostic parity alone advances to regression/fresh qualification rather than certifying population quality.

The new immutable specialist endpoint snapshot is explicitly adopted as supplemental price authority for future specialist contracts: `docs/research/2026-09-17-062006-model-specialist-endpoints/manifest.json`, SHA-256 `46e265fd438f4f85d0766103987d8b10f310d4966f49dd04b3c8716d0e6b4c38`. It contains 30 endpoint records across all four previously catalog-only candidates. Their status in the original table describes the earlier snapshot; the new snapshot now resolves endpoint availability at capture time. Each paid specialist contract must name its exact selected record and this manifest. Qwen and Gemini retain the original snapshot authority.

A single Qwen Alibaba capability probe returned a Japanese translation in 0.96 seconds, with 32 input tokens, 13 output tokens, zero reported reasoning tokens, `finish_reason=stop`, and reported cost $0.00000265. It pinned `qwen/qwen3.7-flash` to `alibaba`, disabled reasoning and fallback, and used raw text. Evidence: `.context/model-task-20260917/qwen-route-probe/`. This establishes a working request, not translation accuracy or production latency.

Two additional one-request probes also completed with `finish_reason=stop`: Gemini 2.5 Flash-Lite on `google-ai-studio/flex` accepted strict JSON Schema, returned an explicit `service_tier=flex`, and reported 24 input/22 output/zero reasoning tokens in 1.02 seconds ($0.0000056); Tencent Hy-MT2-1.8B on `tencent/fp8` accepted its documented user-only translation template with temperature 0.7 and no unsupported sampling or reasoning fields, reporting 35 input/16 output/zero reasoning tokens in 0.50 seconds ($0.000004372). Evidence is in the adjacent `gemini-route-probe/` and `hy18-route-probe/` directories. Each probe reserved $0.001 before its single send; no retries or fallback occurred. Reported costs are observations, while forward reservations remain snapshot-based.

Classifier preparation uncovered an important version distinction: `x_monitor/classifier_0731_prompts.py` is the historical r123 prompt with 13 post types and legacy flags. Its revision suffix `v4` does not mean the proposed expanded taxonomy. The newer experiment contract includes Audience Topics, Geopolitical modes, claim investigation, and untracked-brand promotions. Tests must label these contracts explicitly and cannot claim expanded-taxonomy qualification from the legacy runtime prompt or incomplete historical references.


## Current execution scope after owner classifier selection

The owner selected cloud 0731 for classification and stopped all further alternative classifier tests. Earlier classification advice and completed results above remain historical research, not pending authorization. Continue only translation/commentary candidate trials against 4.1 quality parity. Keep prepared/unspent classifier contracts without running or deleting them. GPT-OSS remains a commentary reserve; GPT-5 Nano is no longer queued. The selected classifier still receives normal integration/regression verification for staging, without reopening model selection.
