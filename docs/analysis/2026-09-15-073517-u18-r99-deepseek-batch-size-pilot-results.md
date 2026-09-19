---
title: U18 R99 DeepSeek 40-Post Batch Pilot Results
type: analysis
date: 2026-09-15
status: blocked-quality-gates-failed
---

# U18 R99 DeepSeek 40-Post Batch Pilot Results

## Plain-English Summary

The 40-post DeepSeek test completed all 45 rows without truncation, omission, transport failure, retry, or reasoning tokens. It used four calls instead of six. The larger batch improved every measured top-level classification score compared with the earlier 20/20/5 DeepSeek run, but the result still missed the frozen quality requirements by a wide margin. DeepSeek is therefore not selected, and classifier activation remains blocked at U18.

The earlier 4,096 setting was not a DeepSeek model limit. It was the application’s minimum output allowance for 20-row batches. This run used the existing scaling rule and allowed 8,000 output tokens for each 40-row role request. The largest responses used 5,462 and 5,355 tokens, so the higher allowance was useful and neither response reached the ceiling.

## Efficiency and capacity

| Measurement | R98: 20/20/5 | R99: 40/5 | Change |
| --- | ---: | ---: | ---: |
| Logical requests | 6 | 4 | -33.3% |
| Transport attempts | 6 | 4 | -33.3% |
| Cache-inclusive prompt tokens | 44,789 | 43,559 | -2.7% |
| Output tokens | 12,191 | 12,215 | +0.2% |
| Complete-result latency p95 | 8.793 s | 14.427 s | +64.1% |
| Runner ledger estimate | $0.03512344 | $0.02554640 | -27.3% |
| Full-input-rate, cache-inclusive estimate | $0.03579928 | $0.03528976 | -1.4% |

R99 reported 21,415 non-cache input tokens and 22,144 cache-read input tokens. The runner ledger prices the former and the output tokens, while its normalized token counter reports cache reads separately. The cache-inclusive estimate above deliberately prices every cache-read token at the full frozen input rate, producing a conservative comparison rather than claiming settled provider billing. Both estimates remain far below the frozen $0.22642488 cap.

Latency is based on only two R99 batch-pair observations versus three in R98, so this is directional pilot evidence. The full run finished in about 17 seconds. The 40-row role calls took about 14.4 seconds each; the 5-row calls took about 2.4 seconds each.

## Classification quality

| Metric | R98: 20/20/5 | R99: 40/5 | Change |
| --- | ---: | ---: | ---: |
| Outcome accuracy | 0.911 | 0.911 | 0.000 |
| Post-type exact-set accuracy | 0.244 | 0.311 | +0.067 |
| Post-type micro F1 | 0.654 | 0.708 | +0.054 |
| Product-label exact-set accuracy | 0.822 | 0.844 | +0.022 |
| Product-label micro F1 | 0.769 | 0.821 | +0.051 |
| Sentiment accuracy | 0.622 | 0.667 | +0.044 |
| China-nationalism accuracy | 0.156 | 0.178 | +0.022 |
| U.S.-nationalism accuracy | 0.156 | 0.222 | +0.067 |
| Improvement composite | 0.485 | 0.522 | +0.037 |

The event F1 rose from 0.000 to 0.500, research explanations from 0.526 to 0.600, and results/evaluations from 0.476 to 0.609. Opportunities stayed at 0.333, and testimonial F1 declined slightly from 0.857 to 0.839.

The result failed all four semantic release gates: absolute quality floors, top-level regression limits, per-label regression limits, and the improvement composite. The composite reached 0.522 against the required 0.864. Post-type exact-set accuracy reached 0.311 against a 0.700 floor, and China/U.S. nationalism remained especially weak because the model continued to confuse assessable `none` values with `unknown` or null. No row matched the owner reference across every axis.

## Decision

The larger batch is operationally viable for this 45-row pilot and avoids the former 4,096 output constraint. It reduces request count while leaving total token volume and conservative cost nearly unchanged, and it increases latency for the large batch. Its semantic scores improved but still fail the preregistered release gates, so no classifier is selected and U18A, staging activation, and production promotion remain blocked.

This is agreement with the already consumed, sole owner reference. It is not unseen validation or an estimate of population accuracy. The machine-readable result is `docs/analysis/2026-09-15-073517-u18-r99-deepseek-batch-size-pilot-results.json`. Raw public-X packets and provider responses remain under `.context/u18/openrouter-two-role-pilot-r99-deepseek-batch-size-v1` and are not committed.

## Independent audit

A separate agent reconciled the frozen contract, all four request signatures, provider attestations, token and spending caps, recomputed score, gate result, private artifact shape, and the R98 comparison. It passed the audit with no findings and made no provider calls.

## Batch-size decision after review

Keep the runtime default at 20 rows for now. The 40-row run remains evidence that a token-scaled larger batch is feasible, but it does not justify a runtime/configuration change while semantic quality remains blocked. If the semantic design later passes, reconsider a token-budgeted maximum of 40 with 20 retained as a rollback setting. The detailed semantic and cost analysis is in `docs/analysis/2026-09-15-094428-u18-deepseek-semantic-failure-and-model-costs.md`.
