# U18A bounded shadow, prevalence, and activation report

This report records the U18A frozen-corpus evidence used before staging activation. It separates three things that must not be conflated: broad lexical screens over the historical database, candidate quality on a small source-visible audit, and the per-family activation decision. The work used the read-only `pushinweight_u18_eval` PostgreSQL database and saved artifacts only. It made no provider calls and wrote no application data.

## Plain-English result

The historical database is large enough to justify keeping all eleven U18A families in the schema and shadow pipeline, but the lexical screens are intentionally rough. They are useful for estimating whether a topic exists and where overlap will occur; they are not classifier accuracy measurements. For example, the broad cost/performance screen matches 56.330% of posts because generic words such as “cost,” “performance,” “speed,” and “API” are common. That number must not be read as the eventual `cost_performance` label rate.

The bounded R94A candidate audit supports user-facing activation only for `local_inference`, `model_distillation`, and `api_developer_surface`. The other eight families remain shadow-only: their rows may be retained for analysis, but their filters and query dimensions remain unavailable. This decision is independent of the owner’s separate decision to use direct DeepInfra 0731 for classification.

## Frozen source and artifact integrity

- Database: `pushinweight_u18_eval`, read-only, 211,245 posts.
- Frozen dump SHA-256: `618f31498b94a42e54940c4e5bf90d7bb09a122b72f1406181b4e029f9b25e06`.
- Primary historical prevalence artifact: [`2026-09-14-075314-u18-owner-edge-prevalence.json`](2026-09-14-075314-u18-owner-edge-prevalence.json), SHA-256 `d0cb2163f79f9baf993f845e265c7d26859897c934033bf36fde1458350954f1`.
- Frozen R94A source cohort: 700 rows, source SHA-256 `3c7ddbe896f0fc5b5f163f7ac300af4431d8aacac2c3da615b6e239960f1598b`.
- Candidate-blind evaluator: [`2026-09-18-210000-u18a-r94a-candidate-blind-source-visible-audit.json`](2026-09-18-210000-u18a-r94a-candidate-blind-source-visible-audit.json), SHA-256 `cf1ec56b963fe687eb0abb6a5d5e23d88ebf6475adc48b5b0818617cb4ac9678`.
- Normalized candidate comparison: [`2026-09-18-212500-u18a-r94a-direct-0731-normalized-candidate-comparison.json`](2026-09-18-212500-u18a-r94a-direct-0731-normalized-candidate-comparison.json), SHA-256 `dcf845e0c413c1240abd950dd32de05304d9328ab321d71927f590948d0be2ee`.
- Candidate output hash recorded inside that comparison: `9d47e93d019685be179bfaf8271b19b5eeee70b7b072d7b69298200b98f05cbb`.
- Comparator SHA-256: `6514ea2030cc38a9c6124d6d609bba2a78b09cb6559461e14bec3c849d2ccc8b`.
- Frozen evaluator case-list SHA-256: `cadfd813ea768a08ea737228a81cded4c9685a73ed7e50f5c9540cb4c1f05734`.

## Historical lexical topic screens

The query lowercased and concatenated `posts.text`, `posts.text_en`, and `posts.text_zh_cn`, then applied PostgreSQL case-insensitive regexes. The Japanese terms were applied to the raw source field when present; there is no stored `text_ja` column in this frozen schema. The screens are multilingual lexical proxies, not semantic labels.

| Audience Topic | Proxy posts | Share of 211,245 | Interpretation |
| --- | ---: | ---: | --- |
| `local_inference` | 21,815 | 10.327% | local, on-device, self-hosted, constrained hardware, and related terms |
| `cost_performance` | 118,995 | 56.330% | deliberately broad screen; generic cost/performance words create substantial overcount |
| `model_distillation` | 3,195 | 1.512% | distillation, imitation, extraction, teacher/student, and related terms |
| `evals_benchmarks` | 38,104 | 18.038% | benchmark, test, score, ranking, evaluation, and related terms |
| `openness_license` | 27,827 | 13.173% | open source/weights, licensing, access, and restrictions |
| `agents_tools` | 43,730 | 20.701% | agents, harnesses, MCP, tool use, orchestration, and related terms |
| `api_developer_surface` | 32,143 | 15.216% | APIs, SDKs, endpoints, integrations, quotas, and developer terms |

The exact multilingual regexes used for reproducibility are stored in the matching machine-readable report. In compact form, they cover these terms:

- `local_inference`: `local`, `on-device`, `self-host`, `on-prem`, `air-gapped`, `llama.cpp`, `ollama`, and Chinese/Japanese local-inference equivalents.
- `cost_performance`: cost, price, free, latency, speed, efficiency, throughput, tokens/s, VRAM, RAM, GPU, compute, resource, performance, and Chinese/Japanese equivalents.
- `model_distillation`: distill, teacher/student model, model extraction, imitation, trained on outputs, and Chinese/Japanese equivalents.
- `evals_benchmarks`: benchmark, evaluation, score, ranking, leaderboard, test, measured, accuracy, win rate, SWE-bench, arena, and Chinese/Japanese equivalents.
- `openness_license`: open source/weights, source availability, released weights, license, Apache/MIT/GPL, access, download, and Chinese/Japanese equivalents.
- `agents_tools`: agent, harness, MCP, tool use, function calling, orchestration, workflow, autonomous, copilot, coding agent, and Chinese/Japanese equivalents.
- `api_developer_surface`: API, SDK, developer, endpoint, integration, webhook, rate limit, quota, context window, and Chinese/Japanese equivalents.

### Topic overlap

The screens match 59,183 posts in none of the seven proxies, 75,461 in exactly one, and 76,601 in two or more. Thus 36.262% of the frozen corpus has at least two lexical topic hits. Pairwise counts below are intersections, not mutually exclusive buckets:

| Pair | Posts | Pair | Posts |
| --- | ---: | --- | ---: |
| local + cost/performance | 15,007 | local + distillation | 626 |
| local + evals | 5,878 | local + openness | 5,922 |
| local + agents | 7,178 | local + API | 5,718 |
| cost/performance + distillation | 2,275 | cost/performance + evals | 28,213 |
| cost/performance + openness | 20,221 | cost/performance + agents | 30,744 |
| cost/performance + API | 25,854 | distillation + evals | 1,205 |
| distillation + openness | 1,180 | distillation + agents | 1,082 |
| distillation + API | 1,084 | evals + openness | 9,138 |
| evals + agents | 14,833 | evals + API | 11,618 |
| openness + agents | 10,039 | openness + API | 8,716 |
| agents + API | 14,499 | | |

These overlaps are one reason the model must treat Audience Topics as independently assignable labels rather than a single-choice topic field. They also show why a later quality audit must score each axis separately.

## Other bounded prevalence screens

These are carried forward from the September 14 historical analysis. They are proxies and compatibility signals, not newly inferred U18A labels.

| Family or issue | Historical screen |
| --- | --- |
| `news_reporting` | 4,299 third-party news-marker posts (2.041%); 3,556 news-marker posts had no historical release signal (1.689%); 743 overlapped a historical release signal (0.353%). Historical release rows total 13,298 (6.315%). |
| `investigate_claim` | Tight distillation/allegation screen: 961 posts (0.456%); 209 also had historical negative sentiment. Generic allegation language matched 10,856 posts (5.155%) and is too noisy to substitute for the label. |
| `geopolitical` | 6,468 posts had a historical non-none country stance (3.071%). Broad actor/framework screen: 10,683 (5.073%), of which 8,543 (79.968%) had no stored country stance. Narrow China/U.S. framework screen: 1,913 (0.908%), of which 1,308 (68.374%) had no stored stance. |
| `untracked_brand_promotions` | 15,090 third-party advertising brand-pairs; 10,761 also had a legacy marketing-spam flag (71.312%), while 4,329 did not (28.688%). Official-account posts: 1,204, with 143 legacy marketing-spam flags (11.877%). Staff posts: 1,001, with 66 flags (6.593%). |
| media dependency | 57,055 posts had stored media (27.093%). Structural short-media/no-context screen: 6,691 (3.177%); short-URL/no-context screen: 9,228 (4.382%). In a 100-row exploratory agent review, one appeared clearly media/link-dependent; this is not human gold. |
| repeated `b.ai` promoter proxy | 4,116 mention posts (1.955%) from 341 authors; 1,988 had legacy marketing-spam flags (48.299%), so the legacy flag missed more than half of this recurrence screen. |
| Qwen clip collision proxy | 372 posts (0.177%) from eight authors; 12 normalized templates, with the top ten covering 92.204% of rows. Five carried a legacy marketing-spam flag. This is better handled by recurrence/relevance policy than a taxonomy branch. |
| persisted candidate identity | `brand_discovery_candidates` contained zero rows in the frozen database. There is therefore no historical prevalence estimate for recurring novel promoted-brand identities. |

## R94A candidate quality and activation

The candidate-blind audit froze 220 cases: ten positive and ten negative/boundary cases for each of eleven families. It contained 33 retained real positive cases and 77 source-visible synthetic positives. The provider was not called during evaluator construction. The direct candidate run made 22 successful role calls with no transport errors.

“Unsupported” below means the declared comparator could not support the frozen expected field. It is not a verified false-positive or false-negative rate and must not be generalized to the 211,245-post database.

| Family | Unsupported positive | Unsupported negative/boundary | Decision |
| --- | ---: | ---: | --- |
| `local_inference` | 1 / 10 | 0 / 10 | **enabled** |
| `cost_performance` | 10 / 10 | 9 / 10 | shadow-only |
| `model_distillation` | 0 / 10 | 0 / 10 | **enabled** |
| `evals_benchmarks` | 1 / 10 | 6 / 10 | shadow-only |
| `openness_license` | 10 / 10 | 7 / 10 | shadow-only |
| `agents_tools` | 4 / 10 | 0 / 10 | shadow-only |
| `api_developer_surface` | 1 / 10 | 0 / 10 | **enabled** |
| `news_reporting` | 5 / 10 | 0 / 10 | shadow-only |
| `investigate_claim` | 10 / 10 | 7 / 10 | shadow-only |
| `geopolitical` | 10 / 10 | 10 / 10 | shadow-only |
| `untracked_brand_promotions` | 10 / 10 | 8 / 10 | shadow-only |

The audit floor is at most one unsupported case in each positive and negative/boundary set. Therefore only the three bold families are enabled. Shadow rows may still be persisted for later analysis, but all eight shadow-only families must remain unavailable to user-facing filters and query dimensions; stale links must be reported as unavailable and canonicalized accordingly.

### False-positive pressure samples

The comparison did not produce a defensible measured false-positive rate: most unsupported negative rows were mechanically incomplete, and the one valid geopolitical mismatch returned `context_missing` rather than a positive assignment. The frozen evaluator nevertheless includes the following source-visible hard negatives. They show the specific lexical or semantic confusions that later revisions must resist; they are pressure cases, not observed population false positives.

| Family | Case | Hard-negative text |
| --- | --- | --- |
| `cost_performance` | `cost_performance-N01` | MiniMax’s office rent increased; no model cost or product performance is discussed. |
| `evals_benchmarks` | `evals_benchmarks-N01` | MiniMax is impressive; generic praise is not an evaluation or benchmark. |
| `openness_license` | `openness_license-N01` | MiniMax opened a new office; “opened” is not an openness or licensing claim. |
| `agents_tools` | `agents_tools-N01` | MiniMax hired a talent agent; that employment role is not an AI agent/tool topic. |
| `news_reporting` | `news_reporting-N01` | I think MiniMax will release a better model next year; this is a prediction, not reporting. |
| `investigate_claim` | `investigate_claim-N01` | MiniMax is worse than its rival; ordinary opinion is not a consequential investigate-claim. |
| `geopolitical` | `geopolitical-N01` | MiniMax is based in China; nationality alone is not geopolitical mode or nationalism. |
| `untracked_brand_promotions` | `untracked_brand_promotions-N01` | MiniMax’s official account promotes MiniMax H3; a tracked brand’s own promotion is not an untracked-brand promotion. |

This per-family result is separate from the owner’s model decision. It does not qualify or disqualify direct DeepInfra 0731 as a whole; it determines which U18A fields are exposed while that selected route is being integrated on staging.

## Execution and cost evidence

The candidate used direct DeepInfra `deepseek-ai/DeepSeek-V4-Flash-0731`, request profile `deepseek_0731`, two roles, 20 cases per family, and the selected no-reasoning two-role shape.

- 22 calls; 0 transport errors.
- 107,038 input tokens and 21,985 output tokens.
- Calculated standard-price cost: `$0.01037958`.
- Provider-reported cost: `$0.00758022` after the retained cache accounting.
- Wall time: `241.871s`.
- Conservative reservation: `$0.07622016`, under the `$0.10` cap.
- Fixed UTF-8 system prompt: 6,158 bytes for the content role and 4,350 bytes for the brand-interpretation role.
- Across the 22 calls, compact JSON user payloads ranged from 11,169 to 29,235 bytes and totaled 320,548 bytes. Combined system-plus-user prompt bytes ranged from 15,519 to 35,393 and totaled 436,136 bytes.

Prompt-byte totals are request-shape measurements for this audit, not token billing: provider tokenization, caching, and output usage determine the actual charge.

## Limitations and next use

Lexical screens overcount generic terms and miss paraphrases. Historical labels are model outputs, not human truth. The 220-case audit uses synthetic fixtures for rare predicates and is an agent source-visible contract, not human adjudication. The database is time-bounded and cannot forecast future rates. The empty `BrandDiscoveryCandidate` table means this report cannot estimate the recurrence of newly detected untracked brands. Media screens are structural upper bounds, and the 100-row media review was exploratory.

The operational consequence is narrow: preserve all U18A fields and shadow evidence, expose only the three enabled families, and keep the other eight behind the activation gate until each has a new per-family audit that meets the same floor. The owner’s direct-DeepInfra route selection remains recorded separately, including its known model-quality limitations.
