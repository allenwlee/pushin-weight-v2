# U18: restore the tested 0731 request contract and retry

Date: September 16, 2026. Model remains cloud DeepSeek V4 Flash 0731 through OpenRouter/DeepInfra FP8. Deployment target remains staging. No deployment or production change occurred.

## Outcome

Restoring the tested prompts and slot format recovered nearly the earlier reference agreement: **178/270 exact fields**, versus **180/270** in the earlier R123 run. Strict runtime coverage improved from **25/45 to 43/45**. The invalid-outcome batch failure disappeared. Two independent-role conflicts remain; they were rejected, not repaired or published.

This is a successful recovery of most of the observed integration regression, not a claim that all acceptance requirements passed. The existing complete-coverage and semantic floors remain unpassed. The owner's original review remains closed, and model selection remains 0731.

## What had changed

The earlier R123 content/brand prompts were 4,794/3,137 UTF-8 bytes. Integration had replaced them with shorter 3,252/2,390-byte prompts, changed the input root from `cases` to `posts`, changed the returned post-level key from `post_flags` to `post_unsanctioned_flags`, and reordered serialized evidence. That was a different request contract from the selected experiment.

The fix restores the R123 prompts verbatim in `x_monitor/classifier_0731_prompts.py`. Selected runtime input is again `cases`; model output is again `post_flags`, mapped locally to the existing stored `unsanctioned_flags` contract. It retains strict field/enum validation. There is no label guessing, third call, model fallback, or semantic repair. Prompt/merge lineage is versioned as `stage1-content-0731-v2`, `stage1-brand-interpretation-0731-v2`, and `stage1-two-role-merge-0731-v2`.

A preflight compares all six actual runtime request bodies with saved R123 requests and permits exactly two declared differences: study-only case IDs are omitted from production-shaped inputs, and the provider pin is strengthened from `DeepInfra` to `deepinfra/fp8`. Prompt text, public source/context, row order, slot format, serialization, sampling settings, and token limits otherwise match. Runtime concurrency remains bounded at three; the older experiment ran each pair together before advancing to the next batch. This is not a claim of identical generated answers.

## Results

| Measurement | Earlier R123 | Broken integration | Restored runtime retry |
| --- | ---: | ---: | ---: |
| Strictly valid posts | 45/45 (saved responses replayed) | 25/45 | 43/45 |
| Exact fields against original owner reference | 180/270 | 64/270 | 178/270 |
| Post-type F1 | 0.6503 | 0.2542 | 0.6790 |
| Product-label F1 | 0.5405 | 0.5882 | 0.6667 |
| Inference cost | $0.00297612 | $0.00268614 | $0.00291204 |
| Whole runtime test elapsed | Different scheduling; not compared here | 10.183 seconds | 21.279 seconds |

F1 measures precision/recall overlap of multilabel assignments. Exact-set matches count any extra or missing label as a difference, which explains why F1 can improve without an increase in exact-field totals. These are consumed development-set agreement measurements, not production accuracy.

| Axis | Earlier R123 exact matches | Restored retry exact matches |
| --- | ---: | ---: |
| outcome | 40/45 | 37/45 |
| post_types | 14/45 | 12/45 |
| product_labels | 28/45 | 33/45 |
| sentiment | 21/45 | 23/45 |
| china_nationalism | 37/45 | 35/45 |
| us_nationalism | 40/45 | 38/45 |

The amended six-additions reference is still scored separately in `report.json`; it is not mixed with the immutable original reference used in the table. Invalid merged rows count as missing in the exact-field totals. Existing historical aggregate empty-set metrics can count an absent empty label as equal; mandatory coverage is reported separately and does not pass.

## Remaining two conflicts

- **H1A3B3731E1C, Qwen:** content returned `context_missing` with no types; brand interpretation returned `testimonial`, positive sentiment, and `none` for both nationalism axes. The visible post discusses Alibaba/Qwen and an ACL research award. The owner previously requested research explanation with neutral sentiment. The two roles disagree about attributable evidence.
- **H87229E54527, DeepSeek:** content returned `context_missing` with no types; brand interpretation returned `testimonial`, positive sentiment, and `none` for both nationalism axes. The source combines GPT/Gemini with “Good Local AI (DeepSeek V4 Flash or Kimi K3)” for coding. Again the content role rejected relevance while the brand role recognized praise.

The current merged contract disallows product labels on `context_missing` rows. Both rows were correctly kept unpublished by that validation. A future prompt refinement must align brand-relevance/outcome criteria across the two independent roles; simply deleting the labels or changing the outcome in code would conceal the conflict. No further paid attempt or new taxonomy change was made in this retry.

## Verification and frozen evidence

- Worker observed three failing parity tests before the fix.
- Main authoritative suite: **69 passed**, including all **three required PostgreSQL checks**, zero skipped or errored.
- Prompt hashes are checked from actual captured classifier calls against a separate fixture extracted from historical saved requests.
- Replay of the earlier R123 responses through the current runtime: **45/45 valid**, no network requests.
- Six-call preflight equivalence passed before paid execution.
- Frozen reservation: $0.01798916370 including fee allowance; hard cap $0.05. Six paid calls, zero retries/repairs, zero reported reasoning tokens. Cost and conservative latency checks passed.
- New run: `.context/u18/runtime-0731-r123-restored-20260916-v1/`.
- Historical-response replay: `.context/u18/0731-r123-current-runtime-replay-20260916.json`.
- Previous failing integration run remains unchanged: `.context/u18/runtime-0731-acceptance-20260916-v2/`.
- Prompt fingerprint fixture: `tests/fixtures/u18_0731_prior45_r123_prompt_manifest.json`.

The post-review taxonomy refinements and translation/commentary comparisons remain in the plan. This compatibility retry deliberately uses the existing v3 vocabulary; it does not discard the separately planned U18A amendments.
