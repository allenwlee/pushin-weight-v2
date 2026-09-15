---
title: U18 DeepSeek Semantic Failure and Tested-Model Costs
type: analysis
date: 2026-09-15
status: diagnostic-complete
---

# U18 DeepSeek Semantic Failure and Tested-Model Costs

## Plain-English Summary

DeepSeek's R99 failure was semantic rather than operational. It returned valid JSON for all 45 rows, used no retries or reasoning tokens, and did not hit the 8,000-token output allowance. The classifier nevertheless failed because it omitted many valid secondary post types, used `null` as the default for assessable non-nationalistic posts, accepted four posts whose meaning depended on missing context, and made several testimonial and sentiment mistakes about what the target brand was being credited or criticized for.

The clearest failure is post-type recall. The owner reference contains 95 post-type assignments across 45 rows. DeepSeek emitted 66: 57 correct labels, 38 missed labels, and 9 extra labels. Its 86.4% label precision shows that most labels it did emit were defensible, but its 60.0% recall shows that it often stopped after choosing the one or two most salient types. Exact-set scoring is strict, but the 38 omissions establish that this is not merely a scoring artifact.

This diagnosis does not authorize another provider run or a release-gate change. The current runtime batch size remains 20. The 40-row result remains evidence that larger batches are operationally feasible, but no configuration changes until the semantic design is revised and separately tested.

## What failed

| Dimension | R99 result | Main pattern |
| --- | ---: | --- |
| Row coverage | 45/45 | No missing or malformed rows |
| Exact rows across all six current axes | 0/45 | Dominated by the systematic nationalism `null`/`none` mismatch |
| Post-type exact sets | 14/45, or 31.1% | Secondary labels were commonly omitted |
| Post-type micro F1 | 70.8% | Precision was 86.4%; recall was only 60.0% |
| Product-label exact sets | 38/45, or 84.4% | High recall with several false testimonials |
| Sentiment accuracy | 30/45, or 66.7% | Five errors followed incorrect acceptance of context-missing rows; ten were direct stance errors |
| China-nationalism accuracy | 8/45, or 17.8% | `null` returned for 34 rows whose reference value was `none` |
| U.S.-nationalism accuracy | 10/45, or 22.2% | `null` returned for 34 rows whose reference value was `none` |
| `context_missing` recall | 1/5, or 20.0% | Four cryptic, wrong-brand, or context-dependent posts were forced into a content type |

The R99 composite was 0.522 against the required 0.864. It failed absolute quality floors, top-level regression limits, per-label regression limits, and the composite-improvement requirement.

## 1. DeepSeek treated a multi-label task like a primary-category task

The content prompt defines every post type and permits arrays, but it does not explicitly require DeepSeek to test every type independently before returning the final array. The output shows a consistent salience pattern: 23 rows had only missing labels, four had both missing and extra labels, four had only extras, and 14 were exact. The reference has 29 multi-label post-type rows, and 27 rows had at least one omitted type. DeepSeek usually selected one or two dominant types even when the reference contained three, four, or five compatible types.

| Post type | Reference positives | True positives | Missed | Extra |
| --- | ---: | ---: | ---: | ---: |
| `results_evaluations` | 16 | 7 | 9 | 0 |
| `research_explanations` | 14 | 6 | 8 | 0 |
| `opinions_reactions` | 26 | 18 | 8 | 4 |
| `opportunities` | 5 | 1 | 4 | 0 |
| `hands_on_usage` | 9 | 5 | 4 | 0 |
| `events` | 3 | 1 | 2 | 0 |
| `business_finance` | 4 | 2 | 2 | 1 |
| `advertising_marketing` | 5 | 4 | 1 | 1 |
| `releases_updates` | 8 | 8 | 0 | 3 |
| `questions_requests` | 4 | 4 | 0 | 0 |
| `job_listings` | 1 | 1 | 0 | 0 |

The persistent misses are informative. Across both DeepSeek runs, it missed `results_evaluations` on the same eight cases, `research_explanations` on the same seven, `opinions_reactions` on the same eight, `opportunities` on the same four, and `hands_on_usage` on the same four. All 31 R99 post-type set failures had also failed in R98. This is evidence of a stable interpretation problem rather than a 40-row truncation or late-batch attention problem.

The errors also hit the product's highest-value views. R99 missed 9 of 16 reference `results_evaluations`, 4 of 5 `opportunities`, and 2 of 3 `events`. The sole job listing was found, but one positive is not useful evidence of job-listing recall, and the cohort contains no personnel-change positive. A reasonable overall micro F1 therefore cannot substitute for the rare-type gates.

The current-v3 vocabulary adds another source of difficulty. Owner-identified journalism rows do not yet have the planned `news_reporting` type, so the reference represents them through combinations of `research_explanations`, `opinions_reactions`, and sometimes `releases_updates` or `results_evaluations`. That does not explain most misses, but it makes a single primary-category reading especially likely on those rows. The future taxonomy may make this boundary clearer; R99 does not test it.

There was also no measured position collapse inside the 40-row batch. Post-type recall was 56.5% for positions 1–20 and 58.5% for positions 21–40. Exact post-type sets were 27.5% across the 40-row batch and 60.0% in the five-row tail, but the tail contains only five fixed, easier rows. Row composition and provider variation prevent treating that contrast as a causal batch-size result.

## 2. `null` versus `none` is a contract failure masquerading as model quality

The brand prompt says `null` means evidence is missing or unusable, while `none` means the post is assessable and contains no nationalism. DeepSeek nevertheless used `null` as its normal negative result. It returned `null` on 34 assessable `none` rows for each national axis.

A deterministic counterfactual illustrates the impact. If `null` were converted to `none` only when DeepSeek itself marked the post `classified`, China-nationalism accuracy would rise from 17.8% to 84.4%, U.S.-nationalism from 22.2% to 88.9%, and exact all-axis rows from zero to eight. The classifier would still fail because post-type exactness and the overall composite remain far below their gates, but this conversion would remove a large artificial source of error.

The parser currently accepts both values and therefore treats this as valid semantic output. The next contract revision should either make the invariant mechanically enforceable or remove the nullable state from assessable rows. The planned Geopolitical replacement should avoid carrying this ambiguity forward.

## 3. DeepSeek accepted four rows that required missing context

The owner reference contains five `context_missing` rows. DeepSeek recognized only one and classified the other four as ordinary content. These same four failed in both R98 and R99:

- `H70A9986C432` depends on unavailable media to make sense.
- `H8D074DCC4D3` appears to depend on a missing parent or an accidental standalone post.
- `HF4987074B1F` is a staff reply whose promised feature cannot be identified without its parent.
- `HDA7D2AEEC6F` promotes Hunyuan through b.ai but was attributed to MiniMax; DeepSeek transferred the other product's release/advertising meaning to the target brand.

The prompt says not to fetch missing links, media, or parents, but its positive definition of `context_missing` is narrower and mostly lists bare links, careers pointers, keyword collisions, handles, greetings, and unsupported brands. The model therefore finds a plausible residual category instead of refusing unsupported interpretation.

These outcome mistakes also create downstream errors. Every context-missing row should have null sentiment. The brand role gave all five a neutral sentiment; four of those rows were also incorrectly accepted by the content role. Together they account for one-third of the 15 sentiment errors.

## 4. Product labels are much stronger, but target-brand and testimonial boundaries remain unstable

DeepSeek recovered 16 of the reference's 17 product labels, producing 94.1% recall. It emitted 22 labels total, however, including six extras: five testimonials and one complaint. All five false testimonials came from third-party accounts; official and staff accounts did not receive false self-testimonials.

Several false testimonials reveal different problems:

- `H7F29D6428BB` praises Corpus for winning a Qwen hackathon, but DeepSeek transferred that praise to Qwen.
- `H9C7C731F3C3` is a long article about DeepSeek pricing that only mentions MiniMax among other vendors, but DeepSeek attributed a testimonial to MiniMax.
- `HE6730DF39A2` questions how DeepSeek scored well despite lacking multimodal and visual capabilities; DeepSeek reversed the stance into positive sentiment plus testimonial.
- `H1A3B3731E1C` is informational reporting about Alibaba/Qwen and a research award; the owner reference is neutral with no testimonial, while DeepSeek treated the favorable subject matter as endorsement.
- `HFD61C2DE5BD` gives MiniMax some favorable language inside a multi-model comparison. DeepSeek's testimonial is consistent with the current prompt's broad phrase “favorable product experience or admiration,” but not with the owner's narrower decision for this row.

The last case exposes boundary tension rather than a formal prompt/reference contradiction. The broad testimonial wording makes DeepSeek's reading understandable, while the owner applies a narrower threshold on this row. The next prompt must settle whether any favorable target-brand evaluation counts, or whether testimonial requires clearer endorsement or firsthand experience.

The only missed product label was `ideas_requests` on `H0DEC6F537E0`, where the user says they have issues and asks to discuss them. The owner treats the unspecified issues as an unmet need, while the current prompt says a question does not automatically become `ideas_requests`. The two are not logically contradictory, but the threshold is underspecified and should be made explicit.

## 5. Sentiment errors were partly downstream and partly genuine stance failures

DeepSeek correctly classified 17 positive and 13 neutral rows. Its 15 errors consisted of five context-missing rows rendered neutral, three positive rows rendered neutral, three neutral rows rendered negative, one neutral rendered positive, one neutral rendered mixed, one mixed rendered negative, and one negative rendered positive.

The most serious polarity reversal was `HE6730DF39A2`: surprise at a strong score despite missing basic capabilities was interpreted as praise. Other mistakes reflect the same target-brand and reporting-versus-endorsement ambiguity seen in testimonials. On the 40 rows whose owner outcome was `classified`, sentiment agreement was 75%; the published 66.7% figure includes the five outcome-dependent null errors.

The single negative and single mixed reference rows were both missed, so their measured recall is zero. Those supports are too small to estimate population performance, but they are valid regression failures for the locked cases.

## 6. Language contributed, but it does not explain the main failure

Post-type exactness was 46.7% in English, 20.0% in Japanese, and 26.7% in Chinese. Chinese sentiment was also weakest. The three language slices contain different subjects and only 15 rows each, so this cannot isolate language as the cause. The same multi-label omissions and `null`/`none` behavior occurred in all three languages.

Likewise, there are only two official accounts, two staff accounts, and one named-person account in this cohort. It cannot establish whether affiliation context systematically improves or worsens classification. The staff reply failure does show that provenance cannot replace missing semantic context. Every emitted `target_brand` identifier matched the expected target, so the measured problem is semantic attribution of praise, releases, and advertising rather than structural brand-ID corruption.

## Why valid structured output was not enough

The two-role design solved the earlier execution problem: DeepSeek returned every required row and every required top-level field. It did not solve exhaustive semantic attention within each role. Schema compliance proves that the model filled the form; it does not prove that it independently evaluated every eligible label.

The current content prompt is compact but still asks one reasoning-disabled call to apply thirteen overlapping post types plus post-level promotion flags across many rows. The brand call applies five overlapping product labels, sentiment, and two national axes. Disabling thinking kept reasoning cost at zero, but it may limit difficult multi-label discrimination; that is an inference because no otherwise identical reasoning-enabled R99 run exists.

Historical tests also argue against treating batch size as the root cause. Earlier five-row and singleton experiments failed to improve the classification ceiling, and R99's second half did not deteriorate. R99 improved every top-level score over R98, but 31 post-type failures and all 15 remaining sentiment failures persisted across both runs.

## Batch-size decision recorded September 15

Keep the runtime default at 20 rows for now. R99 established that 40 rows with an 8,000-token allowance can complete reliably and reduce request count, but it also increases the failure radius and individual batch latency. No runtime or configuration change follows from this discussion.

If the semantic design later passes, reconsider a token-budgeted maximum of 40: fill a batch until either 40 rows or a conservative input limit is reached, whichever comes first. Do not reactively split and resend a completed semantic failure because that creates a different request identity and duplicate provider cost.

## Costs for every tested model

These figures use the routes and prices frozen on September 14–15, 2026. “Observed” means billed usage, a provider-token estimate, or a deliberately marked upper bound from the actual attempted run. Several candidates stopped after the first pair or failed transport, so their observed spend is not a full-production cost.

| Model and tested route | What happened | Observed test spend |
| --- | --- | ---: |
| Qwen3.5 9B / DeepInfra BF16 | Invalid JSON after first two calls | $0.00268350 upper bound |
| Gemma 4 31B / Google AI Studio free | Four failed transport attempts | $0 |
| Qwen3 235B A22B / GMICloud FP8 | Six calls; output omitted nearly all brand rows | $0.00686688 |
| DeepSeek V4 Flash direct, 20/20/5 | Complete 45-row run; failed semantic gates | $0.03512344 ledger; $0.03579928 cache-inclusive upper estimate |
| Qwen3 30B A3B / StreamLake | Invalid content after first two calls | $0.00155216 settled billing |
| Mistral Small 3.2 / Parasail BF16 | Four failed transports | $0 settled; $0.00216450 conservative ledger |
| GPT-5.6 Luna / OpenAI Flex | Blocked before transport by parameter mismatch | $0 |
| Gemini 3.8 Flash / Google AI Studio Flex | Two HTTP 400 responses | $0 settled; $0.00450938 conservative ledger |
| DeepSeek V4 Flash direct, 40/5 | Complete 45-row run; failed semantic gates | $0.02554640 ledger; $0.03528976 cache-inclusive upper estimate |

For an apples-to-apples production estimate, the table below applies each frozen route's input/output rate to R99's successful workload: 43,559 cache-inclusive prompt tokens and 12,215 output tokens for 45 posts. Actual model tokenization and verbosity would differ, and failed routes have not demonstrated that they can complete the job.

| Model and frozen price | Estimated cost for 45 posts | Estimated cost per 1,000 posts |
| --- | ---: | ---: |
| Gemma 4 31B free route | $0 | $0 |
| Qwen3 30B / StreamLake promotional rate | $0.00446 | $0.099 |
| Qwen3.5 9B / DeepInfra | $0.00619 | $0.138 |
| Mistral Small 3.2 / Parasail | $0.00758 | $0.169 |
| Qwen3 235B / GMICloud promotional rate | $0.00809 | $0.180 |
| GPT-5.6 Luna / OpenAI Flex | $0.01168 | $0.260 |
| GPT-5.6 Luna regular rate | $0.02337 | $0.519 |
| Qwen3 235B / GMICloud regular rate | $0.03235 | $0.719 |
| DeepSeek V4 Flash direct | $0.03529 | $0.784 |
| Gemini 3.8 Flash / Google Flex | $0.03924 | $0.872 |
| Gemini 3.8 Flash regular rate | $0.07848 | $1.744 |

Qwen3 30B is the cheapest paid projection from the tested set, but its response was unusable. The free Gemma route never completed a transport. DeepSeek is the only tested model that produced complete, parseable results for all 45 rows, and it failed semantic quality. Cost therefore has not selected a viable production model.

Across R97, R98, and R99, recorded spend is approximately $0.0718 on the reports' billed/ledger basis. Pricing all reported DeepSeek cache-read tokens at the full input rate raises the conservative comparison to approximately $0.0822. These totals exclude any OpenRouter credit-purchase fees.

## Evidence and limitations

This analysis compares the immutable R98 and R99 DeepSeek outputs with the same sole, unblinded owner reference. It does not claim unseen accuracy or population prevalence. The 45 rows contain 15 English, 15 Japanese, and 15 Chinese posts, but rare-label support remains small: one job listing, no personnel change, three events, and five opportunities.

Primary evidence:

- `docs/analysis/2026-09-14-194529-u18-openrouter-two-role-pilot-results.json`
- `docs/analysis/2026-09-14-221023-u18-r98-control-fallback-pilot-results.json`
- `docs/analysis/2026-09-15-073517-u18-r99-deepseek-batch-size-pilot-results.json`
- `.context/u18/human-ambiguity-study-v1/owner-accepted-reference.json`
- `.context/u18/openrouter-two-role-pilot-r98-control-fallback-v1/`
- `.context/u18/openrouter-two-role-pilot-r99-deepseek-batch-size-v1/`
- `x_monitor/attribution.py` revisions `stage1-content-v2` and `stage1-brand-interpretation-v2`
