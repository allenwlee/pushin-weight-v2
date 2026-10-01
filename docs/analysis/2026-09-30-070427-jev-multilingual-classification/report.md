# Jev multilingual full-taxonomy diagnostic

Completed 2026-09-30. One frozen pass; no application/model-route changes.

## Outcome

On 117 posts across six languages, original-text Jev agrees with the frozen agent reference on **3941/4446 (88.6%)** categorical fields. It agrees on **every field for 2/117 posts**. Positive-label precision is **57.6%**, recall **78.3%**, and F1 **66.4%**.

These numbers are agreement with one agent's pre-written judgments, not independently adjudicated production accuracy. Negative labels are abundant; whole-post agreement and positive-label precision/recall must accompany field agreement. The balanced-language plus coverage-seeking selection is not a random sample of the whole database.

### What this establishes

This 38-question configuration is not ready to replace the application classifier. It is fast and inexpensive in this sequential local run, and every returned field is structurally valid, but semantic over-classification and conflicting answers remain substantial. Classification was tested without requiring Jev to generate extracted names or quotations, so those extraction-output duties cannot explain away the observed failures.

- Across binary categories, 419 of 727 assigned labels agree with the reference; 308 are unsupported by it. Jev also misses 116 of the 535 reference-positive labels.
- Geopolitical modes are the clearest weakness: 24 of 160 assigned tags agree with the reference. Reporting contributes 56 false positives and framework 74; these counts are label decisions, not unique posts.
- Tracked-brand advertising has 6 true positives, 13 false positives and 2 missed positives. The original provider-versus-mentioned-brand problem still occurs. Some other advertising disagreements involve genuinely debatable job-ad or enthusiastic-showcase boundaries; the strict frozen score is not an assertion that every mismatch is indisputable.
- Stored English translations add just one net matching field across the same 68 posts, 2,271 to 2,272 of 2,584. This does not establish a general translation benefit or a language ranking.
- Independent answers conflict in 22/117 original responses and 12/68 translated responses. Structural validity alone therefore does not make the returned classification internally usable.

The previous eight-case primary experiment answered only the targeted geopolitical or advertising questions, used different wording and a much smaller input state, and included previously discussed examples. This experiment uses different posts, all 38 questions, and a 49-brand catalog. Consequently it does **not** isolate whether the changed question wording, expanded state, task scope, or case mix caused the poorer result; nor is it a matched comparison with 0731. The prior 21/22 result must not be extrapolated to full-taxonomy reliability.

### Concrete source/response checks

These examples were checked against the saved source and original provider response after scoring. No reference answer, threshold, or prompt was changed.

| Case | Source meaning | Jev's original-text output | Why it matters |
| --- | --- | --- | --- |
| `en_07` | `@NousResearch when are we getting deepseek flash 4.1?` — no parent or quote | Geo reporting 51%; framework 50% | A straightforward model-availability question receives two geopolitical tags under the frozen >=50% rule. |
| `en_01` | A writer compares Qwen fine-tuning and prompts, with a parent about output quality | Geo reporting 57%; framework 70% | Ordinary product experimentation is treated as geopolitical even in English. |
| `ja_02` | Credits Midjourney, Capcut and MiniMax H3 for a generated movie | Geo reporting 57%; framework 56% | The same overcalling appears on a short Japanese tool-credit post. |
| `zh_cn_14` | B.AI/TRON infrastructure promotion offers free DeepSeek access through that service | DeepSeek advertising 76% | Provider promotion is still attributed to the included model brand. |
| `en_15` | A B.AI promotion advertises its platform's discounts and model access | DeepSeek advertising 83% | The promotion-target problem is not confined to non-English text. |
| `en_12` | WorkBuddy offers free credits for several models, including GLM | GLM advertising 26%; untracked general promotion 76% | A counterexample: Jev correctly keeps this provider's promotion separate from GLM advertising. |

Exact source/translation text is in the corresponding `review-*.md` packet; all probabilities, not just selected examples, are retained in [scores.json](scores.json) and `receipts/`.

## Language results, original text

| Language | Posts | Field agreement | All fields right | Positive precision | Positive recall | Positive F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| en | 20 | 664/760 (87.4%) | 1/20 | 54.5% | 80.6% | 65.0% |
| es | 19 | 648/722 (89.8%) | 0/19 | 59.4% | 80.0% | 68.2% |
| ja | 20 | 663/760 (87.2%) | 0/20 | 52.7% | 83.0% | 64.5% |
| ko | 20 | 671/760 (88.3%) | 0/20 | 65.5% | 69.8% | 67.6% |
| tr | 19 | 657/722 (91.0%) | 1/19 | 55.7% | 83.1% | 66.7% |
| zh-cn | 19 | 638/722 (88.4%) | 0/19 | 60.2% | 76.3% | 67.3% |

Counts: database census 279,892 posts; next three language buckets EN 197,854, ES 4,503, TR 2,226. Source review excluded one Indonesian post stored as ZH-CN, one Portuguese post stored as ES, and one non-Turkish interjection stored as TR. Mixed-language source/quote context remains in eligible cases. See the frozen contract for eligibility and limits.

## By classification family, original text

| Family | Field agreement | Exact family per post | Positive precision | Positive recall |
| --- | ---: | ---: | ---: | ---: |
| china_national_stance | 102/117 (87.2%) | 102/117 | unmeasured | unmeasured |
| geo | 212/351 (60.4%) | 32/117 | 15.0% | 88.9% |
| outcome | 104/117 (88.9%) | 104/117 | unmeasured | unmeasured |
| product | 554/585 (94.7%) | 91/117 | 69.6% | 82.8% |
| promotion | 540/585 (92.3%) | 86/117 | 34.6% | 62.1% |
| sentiment | 77/117 (65.8%) | 77/117 | unmeasured | unmeasured |
| topic | 748/819 (91.3%) | 62/117 | 78.5% | 77.0% |
| type | 1500/1638 (91.6%) | 42/117 | 71.2% | 78.8% |
| us_national_stance | 104/117 (88.9%) | 104/117 | unmeasured | unmeasured |

## Natural versus coverage sample

| Stratum | Posts | Field agreement | Entire post | Positive precision | Positive recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| natural | 69 | 2357/2622 (89.9%) | 2/69 | 58.3% | 75.4% |
| coverage | 48 | 1584/1824 (86.8%) | 0/48 | 56.9% | 81.7% |

## Does adding the stored English translation help?

Only 68 non-English posts have a distinct stored English translation. The table compares identical posts; it does not compare the translated subset with all 117 originals. Translations are unchanged saved outputs, sometimes summaries. Original source/quote/parent text remains, and no new translation or extractor call was made.

| Paired population | Original field agreement | With English | Original positive F1 | With English positive F1 |
| --- | ---: | ---: | ---: | ---: |
| all, 68 posts | 2271/2584 (87.9%) | 2272/2584 (87.9%) | 65.3% | 65.8% |
| es, 11 posts | 364/418 (87.1%) | 360/418 (86.1%) | 60.6% | 57.7% |
| ja, 15 posts | 491/570 (86.1%) | 493/570 (86.5%) | 63.1% | 64.6% |
| ko, 14 posts | 467/532 (87.8%) | 474/532 (89.1%) | 67.1% | 70.5% |
| tr, 10 posts | 346/380 (91.1%) | 347/380 (91.3%) | 67.4% | 69.4% |
| zh-cn, 18 posts | 603/684 (88.2%) | 598/684 (87.4%) | 67.3% | 66.0% |

A single call per arm does not separate translation effects from model variability. There is no English duplicate-call control and no language-wide calibration claim.

## Per-label support and errors, original text

Zero positive support means recall is unmeasured, not perfect. Scant positives are coverage evidence, not reliability estimates.

| Binary label | Reference positives | TP | FP | FN incl. invalid | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| type:releases_updates | 19 | 16 | 15 | 3 | 51.6% | 84.2% |
| type:hands_on_usage | 26 | 25 | 7 | 1 | 78.1% | 96.2% |
| type:results_analysis | 38 | 27 | 4 | 11 | 87.1% | 71.1% |
| type:questions_requests | 8 | 8 | 4 | 0 | 66.7% | 100.0% |
| type:advertising_marketing | 8 | 6 | 13 | 2 | 31.6% | 75.0% |
| type:events | 3 | 2 | 0 | 1 | 100.0% | 66.7% |
| type:opportunities | 7 | 6 | 6 | 1 | 50.0% | 85.7% |
| type:job_listings | 2 | 2 | 0 | 0 | 100.0% | 100.0% |
| type:personnel_changes | 2 | 2 | 1 | 0 | 66.7% | 100.0% |
| type:opinions_reactions | 57 | 57 | 25 | 0 | 69.5% | 100.0% |
| type:research_explanations | 27 | 18 | 5 | 9 | 78.3% | 66.7% |
| type:business_finance | 15 | 11 | 2 | 4 | 84.6% | 73.3% |
| type:news_reporting | 46 | 25 | 1 | 21 | 96.2% | 54.3% |
| type:other | 2 | 0 | 0 | 2 | unmeasured | 0.0% |
| topic:local_inference | 13 | 11 | 6 | 2 | 64.7% | 84.6% |
| topic:cost_performance | 45 | 41 | 8 | 4 | 83.7% | 91.1% |
| topic:model_distillation | 8 | 6 | 0 | 2 | 100.0% | 75.0% |
| topic:evals_benchmarks | 30 | 16 | 0 | 14 | 100.0% | 53.3% |
| topic:openness_license | 17 | 14 | 3 | 3 | 82.4% | 82.4% |
| topic:agents_tools | 25 | 21 | 4 | 4 | 84.0% | 84.0% |
| topic:api_developer_surface | 23 | 15 | 13 | 8 | 53.6% | 65.2% |
| product:bug | 5 | 4 | 2 | 1 | 66.7% | 80.0% |
| product:complaint | 10 | 8 | 3 | 2 | 72.7% | 80.0% |
| product:testimonial | 26 | 20 | 9 | 6 | 69.0% | 76.9% |
| product:ideas_requests | 7 | 6 | 6 | 1 | 50.0% | 85.7% |
| product:investigate_claim | 10 | 10 | 1 | 0 | 90.9% | 100.0% |
| geo:reporting | 13 | 13 | 56 | 0 | 18.8% | 100.0% |
| geo:framework | 9 | 8 | 74 | 1 | 9.8% | 88.9% |
| geo:nationalism | 5 | 3 | 6 | 2 | 33.3% | 60.0% |
| promotion:general | 24 | 13 | 9 | 11 | 59.1% | 54.2% |
| promotion:spam | 1 | 1 | 8 | 0 | 11.1% | 100.0% |
| promotion:scam | 0 | 0 | 2 | 0 | 0.0% | unmeasured |
| promotion:crypto | 4 | 4 | 4 | 0 | 50.0% | 100.0% |
| promotion:unauthorized | 0 | 0 | 11 | 0 | 0.0% | unmeasured |

Unmeasured positive recall: `promotion:scam`, `promotion:unauthorized`.

## Output validity and cross-answer consistency

Invalid fields: raw 0, translated 0. Invalid fields count as incorrect; valid siblings remain scored. No choice was changed to match its probabilities.

Responses with a consistency issue or extra output field: 34/185.

- `missing_context_with_assessed_scalar`: 31 responses.
- `missing_context_with_target_membership`: 14 responses.
- `general_plus_specific_promotion`: 8 responses.

Raw answers remain unchanged. An integration needs explicit policy for conflicting independent answers, unavailable/none sentinels, invalid Choice responses and pending/retry state. These diagnostic scripts do not implement a production provider adapter.

## Confidence is not a correctness guarantee

Bins use probability of the selected answer, not Choice's separate distribution-sharpness confidence. This selected, unweighted development set with agent labels cannot validate production calibration or select a safe fallback cutoff.

| Selected-answer probability, original arm | Reference agreement |
| --- | ---: |
| 0.00-0.60 | 179/352 |
| 0.60-0.80 | 611/859 |
| 0.80-0.90 | 802/858 |
| 0.90-1.00 | 2349/2377 |

## Predeclared reference sensitivity

Strict scores above remain primary. Before inference we flagged Meta-company versus Llama attribution (`es_14`), China stance intensity (`zh_cn_08`), and a national-origin-model generalization (`tr_19`). Removing only the specified fields yields raw 3914/4407 (88.8%) and translated 2246/2546 (88.2%). This does not resolve other debatable label boundaries, including news/opinion overlap and showcase-versus-promotion.

## Extraction boundary and migration implications

Jev returned only categorical decisions/probabilities. The prospective separate extractor would handle promoted entity identity, handles/domains, exact supporting passages and detailed event/job/personnel records. No extractor quality, extraction cost, dependency ordering or classifier-extractor consistency was measured. Jev still had to understand who/what the post discusses; removing extraction output does not remove that reasoning requirement.

The test supplied candidate brand associations and known account facts from storage, all 49 tracked brands/curated aliases, and source-matched products from a 1,804-product catalog. It supplied no manually corrected promoted-company identity, expected label or previous model assignment. Only one selected author had a known official relationship, so staff/community/official differences are not adequately validated here.

Translation and commentary configuration remains Gemma; headline generation and the application classifier remain unchanged. This is not evidence that changing one config model string would be safe, nor authorization to reclassify the database.

## Usage and audit

- Calls: 185 (117 original, 68 with stored English), zero retries.
- Input tokens: 2,900,629; output tokens: 170,416 (unbilled under the checked Jev price).
- Model-cost estimate: US$0.121826418 at $0.042/M input; ceiling $0.50. Not an invoice.
- Median local HTTPS request: 0.333 s; range 0.288–0.623 s.
- Timing is local end-to-end request time; no matched 0731 speed/cost trial or production-throughput/load test.
- Read-only DB calls: 4; includes the retained SQL syntax-error receipt.
- Frozen hashes, start/response counts, cost reconciliation and protected app/test hashes verified.
- No application changes, DB writes, new X retrieval, deployment, scheduler mutation or model switch.

## Evidence

- [Frozen scope](scope.md), [evaluation contract](contract.md), [hashes](frozen.json).
- [Exact requests](requests.json), [question definitions](questions.py), [source cohort](cohort.json).
- [Frozen reference judgments and notes](reference_rows.json), [expanded references](references.json).
- [Scores and raw probabilities](scores.json), [all disagreements](disagreements.json), [per-case review](case-results.md).
- Raw provider and accounting receipts: `receipts/`; read-only SQL/Render responses retained alongside.
- [Prior findings record](../2026-09-30-160557-jev-classification-findings.md).
