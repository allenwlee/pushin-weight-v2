# Six owner-approved Sol additions and saved-output comparison

Recorded: 2026-09-15T14:49:39.807186+09:00

The owner accepted six specific labels that Sol found beyond the original reference. Both Sol reasoning settings recovered all six. This establishes six reference omissions, not general superiority over human review. The original reference and reports remain unchanged; this report scores the same saved answers against both revisions, with no new inference cost.

## Owner decision and exact changes

> indeed these look correct. we may need to say that sol is better than my human review

Approval applies to the six additions in the preceding assistant table. It does not approve all 64 extras or every judgment on these posts. The sole original human review remains complete.

| Case | Brand | Axis | Added label | Reason |
|---|---|---|---|---|
| [H92A808A114E](https://x.com/i/status/2094965241201512884) | minimax | post_types | `results_evaluations` | Explicit outcome: 15 seconds of video generated in 9 seconds. |
| [H74C810FB007](https://x.com/i/status/2087672645865427391) | deepseek | product_labels | `testimonial` | Praise of Flash can coexist with criticism of Pro within the same brand. |
| [HAF1D06FBEBA](https://x.com/i/status/2077404641139249235) | glm | product_labels | `bug` | Explicit discount-setting bug; a bug need not disadvantage the customer. |
| [H9C7C731F3C3](https://x.com/i/status/2085604648636055560) | minimax | post_types | `releases_updates` | The article explicitly reports MiniMax pricing changes. |
| [HFD61C2DE5BD](https://x.com/i/status/2090955821484011903) | minimax | product_labels | `testimonial` | Direct endorsement of MiniMax as a capable high-volume executor. |
| [H1E48CCEEB2F](https://x.com/i/status/2086923112126218736) | deepseek | post_types | `research_explanations` | Explains an Opus/local-DeepSeek agent workflow coordinated through Markdown. |

Reference support changes from 95 to 98 post-type assignments and from 17 to 20 product-label assignments. All other values, row metadata and case order are preserved.

## Comparable saved outputs

F1 combines recovered labels, extras and misses; higher is better. These are agreement scores on a development set used to choose the corrections. They do not establish accuracy on unseen posts. Missing rows count against the full 45-case denominator. Diagnostic rows rescued from invalid batches are shown separately.

| Configuration | Accepted rows | Type F1 old → revised | Product F1 old → revised | All six axes exact old → revised |
|---|---:|---:|---:|---:|
| DeepSeek two roles, batch 20 (R98) | 45/45 | 0.654 → 0.641 | 0.769 → 0.762 | 0 → 0 |
| DeepSeek two roles, batch 40 (R99) | 45/45 | 0.708 → 0.707 | 0.821 → 0.810 | 0 → 0 |
| DeepSeek two roles + conditional (R100) | 45/45 | 0.700 → 0.687 | 0.769 → 0.762 | 0 → 0 |
| DeepSeek primary (R101) | 45/45 | 0.789 → 0.775 | 0.645 → 0.647 | 13 → 13 |
| DeepSeek primary + conditional (R101) | 45/45 | 0.807 → 0.793 | 0.645 → 0.647 | 13 → 13 |
| DeepSeek primary + broad follow-up (R103) | 45/45 | 0.791 → 0.789 | 0.645 → 0.647 | 13 → 13 |
| mistral_nemo original (R104) | 0/45 | 0.000 → 0.000 | 0.000 → 0.000 | 0 → 0 |
| ling_flash original (R104) | 25/45 | 0.459 → 0.449 | 0.000 → 0.000 | 1 → 1 |
| NeMo schema_20 (R105) | 5/45 | 0.040 → 0.038 | 0.000 → 0.091 | 0 → 0 |
| NeMo compact_20 (R105) | 45/45 | 0.382 → 0.388 | 0.182 → 0.160 | 1 → 1 |
| NeMo compact_5 (R105) | 45/45 | 0.420 → 0.411 | 0.261 → 0.231 | 2 → 2 |
| NeMo temperature_03 (R105) | 45/45 | 0.364 → 0.356 | 0.100 → 0.087 | 2 → 2 |
| NeMo deepinfra_20 (R105) | 45/45 | 0.305 → 0.299 | 0.000 → 0.000 | 2 → 2 |
| Sol low (R106) | 45/45 | 0.813 → 0.832 | 0.622 → 0.708 | 9 → 12 |
| Sol xhigh (R106) | 45/45 | 0.735 → 0.752 | 0.571 → 0.654 | 4 → 7 |

## Recovery, extras and misses after correction

Extras mean assignments absent from this revised reference, not automatically proven model errors.

| Configuration | Correct / extra / missed types | Correct / extra / missed product labels |
|---|---:|---:|
| DeepSeek primary (R101) | 69 / 11 / 29 | 11 / 3 / 9 |
| Sol low (R106) | 79 / 13 / 19 | 17 / 11 / 3 |
| Sol xhigh (R106) | 82 / 38 / 16 | 17 / 15 / 3 |

## Invalid-batch diagnostics

| Configuration | Individually parseable rows | Type F1 revised | Product F1 revised |
|---|---:|---:|---:|
| mistral_nemo original (R104) | 3/45 | 0.000 | 0.000 |
| ling_flash original (R104) | 44/45 | 0.553 | 0.000 |
| NeMo schema_20 (R105) | 9/45 | 0.109 | 0.083 |

## Limits and verification

- No request, prompt, provider response, original reference or old score was edited. No provider was called and recorded cost/latency are unchanged.
- The original reference describes an unblinded owner calibration, not an independent human gold set. Sol's accepted additions improve that calibration; agreement with a Sol-influenced reference is not independent evidence that Sol is the best model.
- Exact row and per-axis counts are recomputed directly. Historical release gates are not rerun or waived; their rounded-baseline boundary issue still requires the planned scorer revision.
- R103 source-row replay gives 20/45 original exact post-type matches, resolving the old redundant-summary disagreement by using saved rows.
- Rows from rejected batches are never counted as strict valid output. Rejected/canceled pilots and different cohorts are not assigned invented comparable scores.
- Verified exactly six additions, unchanged ordering and scalar axes, 98/20 revised positive support, reproduction of the three known DeepSeek/Sol original scores, and all 15 R106 frozen source hashes.

## Evidence

- [Machine-readable decision, both scores and source hashes](2026-09-15-144939-u18-owner-approved-sol-additions-rescore.json)
- [Full Sol extra-label evidence packet](2026-09-15-143001-u18-sol-extra-label-review.md)
- [Historical model and architecture comparison](../research/2026-09-15-135812-u18-classifier-model-and-architecture-experiment-report.md)
- Revised local reference: `.context/u18/owner-reference-sol-six-additions-v1/owner-accepted-reference.json`; SHA-256 `64e5268894ce36d5db36cdc4ed9b5ce491d14e39af7ed53566f68d2b5a4dc346`.
- Original local reference: `.context/u18/human-ambiguity-study-v1/owner-accepted-reference.json`; SHA-256 `d1c390c0f689e5aae4648a60f5a8878a82e5471fda1c9d6bfe72cee4ab215f80`.
- Reproduction helper: `.context/u18/owner-reference-sol-six-additions-v1/rescore.py`. It writes new artifacts with exclusive creation and never invokes a provider.
