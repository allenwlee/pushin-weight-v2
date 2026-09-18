---
title: Qwen classifier v2 smoke-8 review
date: 2026-09-17
type: experiment-review
---

# Qwen classifier v2 smoke-8 review

Qwen v2 kept the two required roles but used raw JSON and a local fixed-slot
parser. Its new independent-axis and country-stance table materially improved
delivery, but did not clear the smoke gate. This is a fresh source-evidence
review under the current taxonomy, not a comparison with historical labels.

## Run record

- Frozen contract: `.context/model-task-20260917/qwen-classification-v2-smoke8/contract.json`, SHA-256
  `8b26aa6cbf17e2dac6e8101c02d610f05e8de561b19dfd4dcb40e5cb0b8bd412`.
- Four sequential Alibaba-only calls completed with `finish_reason=stop`; no
  fallback, retry, or reasoning tokens. The largest complete request was
  17,006 bytes, below the frozen 32,000-byte Qwen bound.
- Reported cost was $0.00065543 against a $0.00391996 reservation. The raw
  report is `attempt-1.consumed.json`, SHA-256
  `d213d99df5cda3f52687936d5591ba37fa58264f2d1386d93334734b6b20f2ba`.

The second brand batch parsed completely. The first did not parse because its
DeepSeek D03 output selected `["reporting","framework"]` but still selected
directional China and U.S. stances. That makes its five sources delivery
errors even where other raw decisions are useful for semantic review. The
result is 5/8 source delivery errors, so the smoke threshold of zero errors
and the 1% cohort ceiling both fail.

## What improved and what remains wrong

| Source | Improvement over v1 | Remaining source-evidence issue |
| --- | --- | --- |
| `H-H0040D161174` / Qwen | It now detects `local_inference` and `cost_performance`; brand country stances are valid. | Still omits `openness_license` and reduces the self-hosted open-weight explanation and recommendation to `news_reporting` alone. |
| `H-H0DEC6F537E0` / Qwen | Stances are now valid. | It still emits only `events`; the explicit request to discuss issues needs `questions_requests`. |
| `H-H2B36BE298C6` / DeepSeek | It removes the prior unsupported author-opinion label and retains reporting, distillation, and the review flag. | It again makes the reporting/framework stance impossible. The attributed allegation does not establish adopted China/U.S. nationalism or negative brand sentiment. |
| `H-H7046A8A0689` / Qwen | The direct opinion is retained with a valid non-geopolitical brand decision. The unsupported “better than qwen 3.6” comparison is correctly not labeled `results_analysis`; negative Qwen sentiment is defensible because the praised model is compared against Qwen. | No additional error asserted. |
| `L-L45-01` / DeepSeek, Doubao, GLM, MiniMax | It recovers `personnel_changes`; all three comparison/investment brands remain correctly `context_missing`. | DeepSeek's reported CFO/IPO/underwriter account also supports `news_reporting`, which is missing. The whole batch remains unpublishable because of the unrelated D03 state contradiction. |
| `L-L45-02` / DeepSeek | It now has valid `bug`, negative sentiment, and country stances. | A CVE report is news plus a technical sandbox/agent explanation, not a product-result evaluation. It wrongly adds `results_analysis`, misses `research_explanations` and `agents_tools`, and substitutes `api_developer_surface` for the agent-harness topic. |
| `L-L45-09` / MiniMax | Hands-on usage and non-geopolitical state remain correct. | It again omits the observed fine-motion limitation as `results_analysis`; `ideas_requests` and neutral sentiment do not follow from a firsthand limitation plus praise. |
| `L-L45-21` / Kimi, DeepSeek, GLM | It retains per-brand opinion and now returns structurally valid nationalism/framework state. | `news_reporting` is unsupported: this is the author's argument, not a report. The comparison is opinion rather than a substantiated `results_analysis` result. The uniform China-pro/U.S.-anti stance oversimplifies a post that praises capability while warning about Chinese state ideology and urges the U.S. not to stagnate. |

## V3 rationale

The v2 prompt table fixed most malformed country states but still left a
single incorrect sparse selection able to discard a whole batch. More prose or
an additional reviewer call would not address that failure mode. V3 retains
exactly the same two roles and provider route, but changes the response
representation: every decision returns full boolean maps for every post type,
Audience Topic, product label, promotion type, and geopolitical mode. The
local adapter verifies every boolean key and deterministically converts true
keys into the current taxonomy arrays. It rejects contradictions; it does not
invent a missing `nationalism` flag or overwrite country stances.

This forces the model to consider each axis rather than selecting one sparse
label. Qwen v3 adds the separately saved 2,048-token bounded-thinking route
only because v2 still has demonstrated multi-label omissions and a
geopolitical state contradiction. It is a new frozen configuration, not a
retry of v2.
