# 0731 versus Jev: matched multilingual full-taxonomy diagnostic

Completed 2026-09-30. One frozen pass on existing evidence; no application changes.

## Main result

On the same 117 original-text posts, 0731 agrees with the frozen agent reference on **3507/4446 (78.9%)** fields, versus Jev **3941/4446 (88.6%)**. Complete 38-field agreement occurs on **2/117 posts** for 0731 and **2/117** for Jev.

0731 positive-label precision is **74.7%**, recall **32.5%**, and F1 **45.3%**. Jev has **57.6%**, **78.3%**, and **66.4%**, respectively. Positive precision is the fraction of assigned tags supported by the reference; recall is the fraction of reference-positive tags recovered.

Paired original-field outcomes: both right 3244; 0731 alone right 263; Jev alone right 697; both wrong 242. Net difference: -434 matching fields.

These are agreements with a single agent's source judgments fixed before either run, not independent human-adjudicated production accuracy. Most binary answers should be negative. The balanced-language and coverage-seeking selection is not representative of whole-database prevalence. Neither model should be judged from field agreement alone.

### Interpretation after source/response audit

Jev wins the **strict delivered-output score** in this matched probability-output design, but this is not a clean verdict that Jev reasons better. Of 0731's 939 original-arm failures, **499 are invalid/missing outputs and 440 are valid answers disagreeing with the reference**. Output failures are part of the frozen acceptance contract; they must not be silently repaired or discarded to select a winner.

0731 is much more reluctant to assign positive labels. It emits 233 valid positive memberships, 174 supported by the reference, compared with Jev's 727 and 419. It therefore produces fewer unsupported tags but misses **361/535** reference-positive memberships, versus Jev's **116/535**. For 0731 those 361 misses comprise 292 explicit valid rejections and 69 invalid/missing answers. Reduced false positives alone do not establish successful classification.

- **Geo:** 0731 has 10 supported positive tags, 14 unsupported tags, and 17 missed positives; Jev has 24, 136, and 3. On `en_07`, the plain “when are we getting deepseek flash 4.1?” question, 0731 correctly returns no geo modes and recognizes a question/request. Jev had added reporting and framework. In exchange, 0731 misses more genuine geopolitical memberships.
- **Tracked advertising:** 0731 produces zero supported positives, three unsupported positives, and eight misses, versus Jev's six, 13, and two. Seven of the eight 0731 misses are valid explicit rejections with `p_yes=0`; the eighth (`ja_18_raw`) has malformed JSON. Some expected advertising boundaries remain debatable, but output formatting alone does not explain these misses.
- **Provider versus brand:** `zh_cn_14` and `en_15` promote B.AI access/discounts. 0731 assigns DeepSeek advertising 0% and 20%, correctly below the threshold, versus Jev's 76% and 83%. However, 0731 also rejects `en_15`'s untracked general promotion at 0%. On the WorkBuddy free-credit offer (`en_12`), 0731 rejects untracked general promotion at 2%, while Jev correctly accepts it at 76%. This is not a solved promotion-ownership pipeline.
- **Probabilities:** 0731 gives exactly 100% selected-answer probability to 3,118 valid original-arm answers, of which 333 disagree with the reference. Do not treat these self-reported values as reliable routing guarantees or as equivalent to Jev's native decision probabilities.

All examples were checked against saved source and provider responses. No additional calls, reference edits, coercion of string booleans, JSON repairs, or new scoring exclusions were made. The comparison does not establish the current production 0731 prompt's accuracy, the effect of asking for probabilities versus labels alone, or either model's end-to-end extraction/classification quality.

## What was held fixed

Same 117 source posts, one target brand per post, 38 question definitions/criteria, original/quote/parent text, account relationships, 49-brand catalog with source-matched products, 68 stored English translations, question/input serialization, reference answers, exclusions and sensitivity rules. Same 185-call order. No new source collection or Jev calls.

0731 used the existing direct-DeepInfra non-reasoning profile (temperature 1, top_p 1, seed 42, reasoning_effort none, standard tier), with a 4,096-token output ceiling fixed before calls. The user content exactly matches Jev's state/questions objects. The system wrapper adapts those questions to compact JSON labels plus self-reported probability distributions; it is verbatim the prior matched test's B_probabilities wrapper. This is not the current application's production classifier prompt, nor a test of a higher-reasoning 0731 configuration. No labels-only comparison arm was added.

The same >=50% threshold maps binary probabilities to labels; fixed-choice labels must maximize their distributions. 0731's written percentages and Jev's native decision probabilities have different production mechanisms. Agreement here does not attribute any difference uniquely to model weights, API design, eliciting probabilities, or parallel question handling.

## Language results — original text

| Language | Posts | Jev field agreement | 0731 field agreement | Jev positive precision / recall | 0731 positive precision / recall | 0731 entire post |
| --- | --- | --- | --- | --- | --- | --- |
| ja | 20 | 663/760 (87.2%) | 604/760 (79.5%) | 52.7% / 83.0% | 69.0% / 30.9% | 1 |
| zh-cn | 19 | 638/722 (88.4%) | 565/722 (78.3%) | 60.2% / 76.3% | 71.7% / 34.0% | 1 |
| ko | 20 | 671/760 (88.3%) | 596/760 (78.4%) | 65.5% / 69.8% | 73.7% / 26.4% | 0 |
| en | 20 | 664/760 (87.4%) | 566/760 (74.5%) | 54.5% / 80.6% | 75.6% / 34.7% | 0 |
| es | 19 | 648/722 (89.8%) | 583/722 (80.7%) | 59.4% / 80.0% | 85.7% / 32.0% | 0 |
| tr | 19 | 657/722 (91.0%) | 593/722 (82.1%) | 55.7% / 83.1% | 76.5% / 40.0% | 0 |

English, Spanish and Turkish were the next three language buckets in the saved 279,892-post database census. Three incorrect language assignments were excluded before either model ran; no new exclusions occurred. Small, differently composed language samples do not establish a general language ranking.

## Classification families — original text

| Family | Jev field agreement | 0731 field agreement | Jev positive precision / recall | 0731 positive precision / recall | 0731 exact family |
| --- | --- | --- | --- | --- | --- |
| china_national_stance | 102/117 (87.2%) | 87/117 (74.4%) | unmeasured / unmeasured | unmeasured / unmeasured | 87/117 |
| geo | 212/351 (60.4%) | 288/351 (82.1%) | 15.0% / 88.9% | 41.7% / 37.0% | 88/117 |
| outcome | 104/117 (88.9%) | 93/117 (79.5%) | unmeasured / unmeasured | unmeasured / unmeasured | 93/117 |
| product | 554/585 (94.7%) | 480/585 (82.1%) | 69.6% / 82.8% | 73.9% / 29.3% | 70/117 |
| promotion | 540/585 (92.3%) | 493/585 (84.3%) | 34.6% / 62.1% | 57.1% / 13.8% | 79/117 |
| sentiment | 77/117 (65.8%) | 57/117 (48.7%) | unmeasured / unmeasured | unmeasured / unmeasured | 57/117 |
| topic | 748/819 (91.3%) | 633/819 (77.3%) | 78.5% / 77.0% | 85.7% / 37.3% | 41/117 |
| type | 1500/1638 (91.6%) | 1285/1638 (78.4%) | 71.2% / 78.8% | 76.1% / 31.9% | 21/117 |
| us_national_stance | 104/117 (88.9%) | 91/117 (77.8%) | unmeasured / unmeasured | unmeasured / unmeasured | 91/117 |

Positive precision/recall applies to binary memberships, not the four scalar families.

## Original problem areas and per-label errors

TP = supported positive assignment; FP = unsupported positive assignment; FN = missed reference positive, including invalid answers. False means disagreement with the fixed agent reference, not an independently settled error for every subjective boundary.

| Label | Reference positives | Jev TP / FP / FN | 0731 TP / FP / FN | Jev precision / recall | 0731 precision / recall |
| --- | --- | --- | --- | --- | --- |
| geo:framework | 9 | 8 / 74 / 1 | 4 / 10 / 5 | 9.8% / 88.9% | 28.6% / 44.4% |
| geo:nationalism | 5 | 3 / 6 / 2 | 1 / 3 / 4 | 33.3% / 60.0% | 25.0% / 20.0% |
| geo:reporting | 13 | 13 / 56 / 0 | 5 / 1 / 8 | 18.8% / 100.0% | 83.3% / 38.5% |
| product:bug | 5 | 4 / 2 / 1 | 3 / 3 / 2 | 66.7% / 80.0% | 50.0% / 60.0% |
| product:complaint | 10 | 8 / 3 / 2 | 3 / 2 / 7 | 72.7% / 80.0% | 60.0% / 30.0% |
| product:ideas_requests | 7 | 6 / 6 / 1 | 1 / 0 / 6 | 50.0% / 85.7% | 100.0% / 14.3% |
| product:investigate_claim | 10 | 10 / 1 / 0 | 4 / 0 / 6 | 90.9% / 100.0% | 100.0% / 40.0% |
| product:testimonial | 26 | 20 / 9 / 6 | 6 / 1 / 20 | 69.0% / 76.9% | 85.7% / 23.1% |
| promotion:crypto | 4 | 4 / 4 / 0 | 1 / 1 / 3 | 50.0% / 100.0% | 50.0% / 25.0% |
| promotion:general | 24 | 13 / 9 / 11 | 3 / 2 / 21 | 59.1% / 54.2% | 60.0% / 12.5% |
| promotion:scam | 0 | 0 / 2 / 0 | 0 / 0 / 0 | 0.0% / unmeasured | unmeasured / unmeasured |
| promotion:spam | 1 | 1 / 8 / 0 | 0 / 0 / 1 | 11.1% / 100.0% | unmeasured / 0.0% |
| promotion:unauthorized | 0 | 0 / 11 / 0 | 0 / 0 / 0 | 0.0% / unmeasured | unmeasured / unmeasured |
| topic:agents_tools | 25 | 21 / 4 / 4 | 10 / 2 / 15 | 84.0% / 84.0% | 83.3% / 40.0% |
| topic:api_developer_surface | 23 | 15 / 13 / 8 | 3 / 0 / 20 | 53.6% / 65.2% | 100.0% / 13.0% |
| topic:cost_performance | 45 | 41 / 8 / 4 | 21 / 1 / 24 | 83.7% / 91.1% | 95.5% / 46.7% |
| topic:evals_benchmarks | 30 | 16 / 0 / 14 | 10 / 1 / 20 | 100.0% / 53.3% | 90.9% / 33.3% |
| topic:local_inference | 13 | 11 / 6 / 2 | 6 / 3 / 7 | 64.7% / 84.6% | 66.7% / 46.2% |
| topic:model_distillation | 8 | 6 / 0 / 2 | 5 / 0 / 3 | 100.0% / 75.0% | 100.0% / 62.5% |
| topic:openness_license | 17 | 14 / 3 / 3 | 5 / 3 / 12 | 82.4% / 82.4% | 62.5% / 29.4% |
| type:advertising_marketing | 8 | 6 / 13 / 2 | 0 / 3 / 8 | 31.6% / 75.0% | 0.0% / 0.0% |
| type:business_finance | 15 | 11 / 2 / 4 | 3 / 1 / 12 | 84.6% / 73.3% | 75.0% / 20.0% |
| type:events | 3 | 2 / 0 / 1 | 0 / 0 / 3 | 100.0% / 66.7% | unmeasured / 0.0% |
| type:hands_on_usage | 26 | 25 / 7 / 1 | 11 / 0 / 15 | 78.1% / 96.2% | 100.0% / 42.3% |
| type:job_listings | 2 | 2 / 0 / 0 | 1 / 0 / 1 | 100.0% / 100.0% | 100.0% / 50.0% |
| type:news_reporting | 46 | 25 / 1 / 21 | 12 / 0 / 34 | 96.2% / 54.3% | 100.0% / 26.1% |
| type:opinions_reactions | 57 | 57 / 25 / 0 | 17 / 4 / 40 | 69.5% / 100.0% | 81.0% / 29.8% |
| type:opportunities | 7 | 6 / 6 / 1 | 0 / 0 / 7 | 50.0% / 85.7% | unmeasured / 0.0% |
| type:other | 2 | 0 / 0 / 2 | 1 / 6 / 1 | unmeasured / 0.0% | 14.3% / 50.0% |
| type:personnel_changes | 2 | 2 / 1 / 0 | 1 / 0 / 1 | 66.7% / 100.0% | 100.0% / 50.0% |
| type:questions_requests | 8 | 8 / 4 / 0 | 6 / 0 / 2 | 66.7% / 100.0% | 100.0% / 75.0% |
| type:releases_updates | 19 | 16 / 15 / 3 | 10 / 7 / 9 | 51.6% / 84.2% | 58.8% / 52.6% |
| type:research_explanations | 27 | 18 / 5 / 9 | 6 / 2 / 21 | 78.3% / 66.7% | 75.0% / 22.2% |
| type:results_analysis | 38 | 27 / 4 / 11 | 15 / 3 / 23 | 87.1% / 71.1% | 83.3% / 39.5% |

Scam and unauthorized promotion have no reference-positive examples; their positive recall is unmeasured, not perfect. Spam, jobs and several other labels have very few positives. Only one selected author has a known official relationship, so this does not validate the proposed affiliation-dependent promotion policy.

## Natural versus coverage selection

| Sample | Posts | Jev field agreement | 0731 field agreement | 0731 positive precision / recall |
| --- | --- | --- | --- | --- |
| natural | 69 | 2357/2622 (89.9%) | 2108/2622 (80.4%) | 73.7% / 34.5% |
| coverage | 48 | 1584/1824 (86.8%) | 1399/1824 (76.7%) | 76.0% / 30.3% |

## Translation comparison on identical paired posts

Only the 68 posts with a distinct saved English translation are compared here. Original and quote/parent source remain in both inputs. Stored translations can be summaries; none was generated or repaired for this experiment.

| Model | Paired original field agreement | With translation | Original positive F1 | With translation positive F1 |
| --- | --- | --- | --- | --- |
| Jev | 2271/2584 (87.9%) | 2272/2584 (87.9%) | 65.3% | 65.8% |
| 0731 | 2058/2584 (79.6%) | 2130/2584 (82.4%) | 45.7% | 51.7% |

| Language | Paired posts | 0731 original | 0731 with translation |
| --- | --- | --- | --- |
| ja | 15 | 437/570 (76.7%) | 476/570 (83.5%) |
| zh-cn | 18 | 534/684 (78.1%) | 568/684 (83.0%) |
| ko | 14 | 399/532 (75.0%) | 465/532 (87.4%) |
| es | 11 | 342/418 (81.8%) | 297/418 (71.1%) |
| tr | 10 | 346/380 (91.1%) | 324/380 (85.3%) |

One observation per arm does not separate translation effects from model variability. No repeatability or fresh-translation study was run.

## Output validity and consistency

Invalid 0731 fields: raw **499**, translated **187**. Raw semantic-label agreement ignoring only probability-format failures: **3516/4446 (79.1%)**. Strict scores remain primary; no response was repaired or retried.

The provider returned HTTP 200 and `finish_reason=stop` for all 185 calls; those transport/completion facts did not guarantee usable answers. Original-arm invalid fields occurred in 23/117 responses, translated-arm invalid fields in 9/68. The [output audit](output-audit.json) decomposes them without changing any score:

| Output defect | Original responses / affected fields | Translated responses / affected fields |
| --- | --- | --- |
| Invalid JSON, such as a missing closing brace | 6 / 228 | 2 / 76 |
| Empty `answers` object | 5 / 190 | 1 / 38 |
| Strings `"true"`/`"false"` instead of JSON booleans | 2 / 68 | 2 / 68 |
| Other probability format or label consistency errors | 13 fields | 5 fields |

The semantic-label supplemental score retains only already well-typed labels; it is not a repaired-JSON or human-readable-answer rescore. It does not add missing braces, coerce strings or invent absent fields. Of the 32 responses with invalid fields, 14 provide no strictly valid answers at all (eight malformed JSON, six empty maps).

0731 responses with cross-answer/envelope/extra-output issues: **58/185**; Jev: **34/185**. Counts by issue can overlap:

- `classified_without_type`: 19.
- `directional_stance_without_nationalism`: 3.
- `extra_root_keys`: 1.
- `invalid_response_envelope`: 8.
- `missing_context_with_assessed_scalar`: 26.
- `missing_context_with_target_membership`: 2.
- `other_plus_specific_type`: 2.

Independent valid answers can still conflict; no hidden reconciliation step cleared such answers before scoring.

## Self-reported confidence — descriptive only

Selected-answer probabilities, not token likelihoods. Bins are neither a calibration validation nor a proposed routing threshold; easy negative decisions dominate the highest-confidence bin.

| Probability bin | Jev reference agreement | 0731 reference agreement |
| --- | --- | --- |
| 0.00–0.60 | 179/352 (50.9%) | 4/7 (57.1%) |
| 0.60–0.80 | 611/859 (71.1%) | 36/52 (69.2%) |
| 0.80–0.90 | 802/858 (93.5%) | 91/122 (74.6%) |
| 0.90–1.00 | 2349/2377 (98.8%) | 3376/3766 (89.6%) |

## Predeclared reference sensitivity

Omitting only the original three sets of flagged reference fields yields 0731 **3473/4407 (78.8%)**, versus Jev **3914/4407 (88.8%)**. Strict results above stay primary. There were no post-response edits to expected answers.

## Cost and observed request time

| Metric | Jev | 0731 |
| --- | --- | --- |
| Physical model calls | 185 | 185 |
| Input tokens | 2900629 | 2406620 |
| Output tokens | 170416 | 185238 |
| Reported cached input tokens | not reported by this comparison | 1400832 |
| Estimated model USD | 0.121826418 | 0.11470260000000000325 |
| Median HTTPS seconds | 0.333 | 9.912 |
| Range, seconds | 0.288–0.623 | 0.626–31.343 |

0731 spend is the sum of provider-returned estimated_cost; Jev uses the previously checked input-only price. Neither is an invoice. 0731's model-spend ceiling was US$0.50; Render job compute is excluded. 0731 ran on Render and Jev locally, at different times and cache/load conditions. These durations are observations, not a controlled speed benchmark. This comparison requests 0731's probability text; it does not establish cost against compact labels-only output.

## Extraction and operational boundary

No model generated arbitrary entity names, handles/domains, supporting quotations, translations or commentary. A separate extractor's quality, cost, ordering and consistency with labels remain untested. Jev and 0731 both still needed to reason about the promoted offering from the supplied evidence; no oracle target was supplied.

No production model switch, application/configuration change, database access/write, X retrieval, scheduler resume or deployment. This comparison supplies evidence for a model choice, not a verified production integration or permission to reclassify stored posts.

## Audit and evidence

Frozen input/reference/helper/app hashes verified; every request's source/question parity, start/response identity, field count and cost reconciled. Zero model retries. Offline parser fixtures and a fake-transport end-to-end test passed before inference. Lossless LZMA replaced only the transport compression before submission to keep the job command below the operating-system argument limit; decompressed packet hashes and all model payloads are unchanged.

Independent JSON checks also confirmed 185 matching input objects/IDs with zero mismatches, 185 HTTP-200 responses from the pinned model, and 7,030 scored fields. Job `job-dauc1alg1s2s73cbc27g` succeeded (07:56:26–08:28:23 UTC). [Postflight verification](render-postflight.json) confirms the staging scheduler remains suspended and no one-off job remains active. A slow final log-monitor query eventually returned normally; bounded log recovery captured all results, with no model restart. No process was terminated by the attempted reader cleanup because that reader had already exited.

- [Frozen contract](contract.md), [manifest](frozen.json), [transport manifest](transport-frozen.json).
- [Exact 0731 requests](requests.json), [scores/probabilities](scores.json), [all disagreements](disagreements.json).
- [Paired model decisions](model-pairs.json), [per-case review](case-results.md).
- [Job receipt](job.json), [service preflight](render-preflight.json); raw captured responses in `events/`, original Render logs in `log-pages/`.
- [Unchanged Jev report](../2026-09-30-070427-jev-multilingual-classification/report.md), [pre-inference references](../2026-09-30-070427-jev-multilingual-classification/reference_rows.json).
- [Consolidated findings record](../2026-09-30-160557-jev-classification-findings.md).
