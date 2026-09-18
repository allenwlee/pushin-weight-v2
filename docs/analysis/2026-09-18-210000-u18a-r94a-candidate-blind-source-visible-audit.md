# U18A R94A candidate-blind source-visible audit

## Status

This is a provider-free, candidate-blind evaluator artifact. It freezes expected source-visible boundaries before any candidate-result comparison. It is development evidence only, not human gold or a population-accuracy claim.

## Blindness and provenance

- Frozen source cohort: `.context/u18-final-v3/cohort-source.json` (`700` rows; SHA-256 `3c7ddbe896f0fc5b5f163f7ac300af4431d8aacac2c3da615b6e239960f1598b`).
- U18A definition source: `x_monitor/classifier_0731_prompts.py` (SHA-256 `7b0b6f10a89b74e4d7d513702558a1887ad7e2707020754ea958dcc3b3f12397`).
- Evaluator: `codex-source-visible-blind-evaluator/v1`; provider calls: 0; candidate, owner-answer, provider-output, repository-tool, and network access: false.
- Evaluator prompt SHA-256: `a6aa23112485590710a4b9c9e601eb0cd4f815c8c56e75f74d49ae8218719656`; schema SHA-256: `e8ed9f60fba98becfc665b49fbca62690366a7ab582a3865668198960722087c`; comparator SHA-256: `6514ea2030cc38a9c6124d6d609bba2a78b09cb6559461e14bec3c849d2ccc8b`; selected-case SHA-256: `cadfd813ea768a08ea737228a81cded4c9685a73ed7e50f5c9540cb4c1f05734`.

## Coverage

| Family/concept | Positive | Negative/boundary | Retained real positives | Synthetic positives |
| --- | ---: | ---: | ---: | ---: |
| `local_inference` | 10 | 10 | 4 | 6 |
| `cost_performance` | 10 | 10 | 5 | 5 |
| `model_distillation` | 10 | 10 | 0 | 10 |
| `evals_benchmarks` | 10 | 10 | 2 | 8 |
| `openness_license` | 10 | 10 | 8 | 2 |
| `agents_tools` | 10 | 10 | 10 | 0 |
| `api_developer_surface` | 10 | 10 | 1 | 9 |
| `news_reporting` | 10 | 10 | 3 | 7 |
| `investigate_claim` | 10 | 10 | 0 | 10 |
| `geopolitical` | 10 | 10 | 0 | 10 |
| `untracked_brand_promotions` | 10 | 10 | 0 | 10 |

## `local_inference`

Local, on-device, self-hosted, or constrained-hardware inference.

Retained-source scan found 4 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `local_inference-P01` | retained_real_source | `2077484989671678041` | `llama` | `third_party` | `{"audience_topics":["local_inference"]}` | - Bonsai itself runs locally via Llama.cpp |
| `local_inference-P02` | retained_real_source | `2086879111574917290` | `minimax` | `official` | `{"audience_topics":["local_inference"]}` | • @VictorSuOrtiz of MiniMax, joined by @alexinexxx, demo MiniMax H3, our video-generation model running locally on a Mac |
| `local_inference-P03` | retained_real_source | `2090023760703193444` | `qwen` | `third_party` | `{"audience_topics":["local_inference"]}` | I wanna run QWEN locally, is it worth it? |
| `local_inference-P04` | retained_real_source | `2091419315392356739` | `llama` | `third_party` | `{"audience_topics":["local_inference"]}` | Back in April 2023 I was running LLaMA and Alpaca locally and telling people to spread their bets across two or three models instead of one API. |
| `local_inference-P05` | source_visible_synthetic_fixture | `u18a-local_inference-p05` | `minimax` | `third_party` | `{"audience_topics":["local_inference"]}` | MiniMax quantized to 4-bit and completed local inference on a Ryzen AI laptop. |
| `local_inference-P06` | source_visible_synthetic_fixture | `u18a-local_inference-p06` | `minimax` | `third_party` | `{"audience_topics":["local_inference"]}` | The MiniMax Docker guide documents a self-hosted local server for private documents. |
| `local_inference-P07` | source_visible_synthetic_fixture | `u18a-local_inference-p07` | `minimax` | `third_party` | `{"audience_topics":["local_inference"]}` | I benchmarked MiniMax running locally through llama.cpp on a desktop GPU. |
| `local_inference-P08` | source_visible_synthetic_fixture | `u18a-local_inference-p08` | `minimax` | `third_party` | `{"audience_topics":["local_inference"]}` | MiniMax now supports an air-gapped on-premise inference deployment. |
| `local_inference-P09` | source_visible_synthetic_fixture | `u18a-local_inference-p09` | `minimax` | `third_party` | `{"audience_topics":["local_inference"]}` | A developer used MiniMax locally on an iPad-class neural accelerator. |
| `local_inference-P10` | source_visible_synthetic_fixture | `u18a-local_inference-p10` | `minimax` | `third_party` | `{"audience_topics":["local_inference"]}` | MiniMax’s local runtime fits a 16 GB VRAM workstation after KV-cache compression. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `local_inference-N01` | source_visible_synthetic_fixture | `u18a-local_inference-n01` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax opened a local Tokyo office; the post says nothing about model execution. |
| `local_inference-N02` | source_visible_synthetic_fixture | `u18a-local_inference-n02` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax will comply with local regulations in each market; no inference location is described. |
| `local_inference-N03` | source_visible_synthetic_fixture | `u18a-local_inference-n03` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | I called the MiniMax remote API from my laptop; the model ran in the cloud. |
| `local_inference-N04` | source_visible_synthetic_fixture | `u18a-local_inference-n04` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax posted a photo from a neighborhood meetup with no product details. |
| `local_inference-N05` | source_visible_synthetic_fixture | `u18a-local_inference-n05` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax announced a desktop wallpaper pack, not a locally runnable model. |
| `local_inference-N06` | source_visible_synthetic_fixture | `u18a-local_inference-n06` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A link says MiniMax has a fast model, but its linked video is unavailable here. |
| `local_inference-N07` | source_visible_synthetic_fixture | `u18a-local_inference-n07` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax has users in many local communities; no hardware or deployment information appears. |
| `local_inference-N08` | source_visible_synthetic_fixture | `u18a-local_inference-n08` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax reduced server latency in its hosted service; that does not establish local inference. |
| `local_inference-N09` | source_visible_synthetic_fixture | `u18a-local_inference-n09` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | The post compares MiniMax with a locally run Qwen model but gives no local-run evidence for MiniMax. |
| `local_inference-N10` | source_visible_synthetic_fixture | `u18a-local_inference-n10` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax staff praised the team’s work without describing where the model runs. |

## `cost_performance`

Cost, compute, speed, efficiency, or resource use in relation to product performance.

Retained-source scan found 5 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `cost_performance-P01` | retained_real_source | `2059314052892099070` | `mimo` | `official` | `{"audience_topics":["cost_performance"]}` | 🚀 Better inference efficiency, lower costs, broader access.  MiMo-V2.5 Series API pricing is now permanently reduced — by up to 99% compared to previous pricing. |
| `cost_performance-P02` | retained_real_source | `2068687433609490683` | `glm` | `third_party` | `{"audience_topics":["cost_performance"]}` | Welcome to agentic engineering on local machine and loop engineer at low cost  An opensource GLM-5.2 will change the game.   And it’s the first open-weights model that feels frontier-adjacent for real software engineering |
| `cost_performance-P03` | retained_real_source | `2085360265600938156` | `qwen` | `third_party` | `{"audience_topics":["cost_performance"]}` | 🔗 Alibaba Cloud Model Studio: https://t.co/5akK2z4Tti 🔗 Qwen Cloud: https://t.co/Drnf2UuCkx  API pricing (USD): |
| `cost_performance-P04` | retained_real_source | `2092865007533051963` | `deepseek` | `third_party` | `{"audience_topics":["cost_performance"]}` | The other day I talked about how DeepSeek flash was 1/10th token cost of kimi k3 the frontier model 1/2 |
| `cost_performance-P05` | retained_real_source | `2096119938393993299` | `deepseek` | `third_party` | `{"audience_topics":["cost_performance"]}` | DeepSeek-V4-Flash — built for fast, efficient AI workloads where speed and cost matter. |
| `cost_performance-P06` | source_visible_synthetic_fixture | `u18a-cost_performance-p06` | `minimax` | `third_party` | `{"audience_topics":["cost_performance"]}` | MiniMax’s 4-bit variant kept the same task pass rate while reducing VRAM use. |
| `cost_performance-P07` | source_visible_synthetic_fixture | `u18a-cost_performance-p07` | `minimax` | `third_party` | `{"audience_topics":["cost_performance"]}` | The MiniMax API price fell and the published throughput rose on the same workload. |
| `cost_performance-P08` | source_visible_synthetic_fixture | `u18a-cost_performance-p08` | `minimax` | `third_party` | `{"audience_topics":["cost_performance"]}` | MiniMax completed the workflow in 18 seconds rather than 70 seconds at lower spend. |
| `cost_performance-P09` | source_visible_synthetic_fixture | `u18a-cost_performance-p09` | `minimax` | `third_party` | `{"audience_topics":["cost_performance"]}` | MiniMax’s cache change lowered tokens per correct answer in a reproducible run. |
| `cost_performance-P10` | source_visible_synthetic_fixture | `u18a-cost_performance-p10` | `minimax` | `third_party` | `{"audience_topics":["cost_performance"]}` | MiniMax is cheaper per million tokens and faster on the cited coding evaluation. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `cost_performance-N01` | source_visible_synthetic_fixture | `u18a-cost_performance-n01` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s office rent increased; no model cost or product performance is discussed. |
| `cost_performance-N02` | source_visible_synthetic_fixture | `u18a-cost_performance-n02` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A customer says MiniMax is expensive, but gives no performance, compute, or usage evidence. |
| `cost_performance-N03` | source_visible_synthetic_fixture | `u18a-cost_performance-n03` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax offered a merch coupon; it is not a product cost-performance claim. |
| `cost_performance-N04` | source_visible_synthetic_fixture | `u18a-cost_performance-n04` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax raised venture funding, which is company finance rather than serving efficiency. |
| `cost_performance-N05` | source_visible_synthetic_fixture | `u18a-cost_performance-n05` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | The author calls MiniMax fast without a comparison, measurement, cost, or resource evidence. |
| `cost_performance-N06` | source_visible_synthetic_fixture | `u18a-cost_performance-n06` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax mentions token limits but not price, usage cost, performance, or efficiency. |
| `cost_performance-N07` | source_visible_synthetic_fixture | `u18a-cost_performance-n07` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A rival’s API price is discussed; MiniMax is only a comparison foil. |
| `cost_performance-N08` | source_visible_synthetic_fixture | `u18a-cost_performance-n08` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax announced a free community event, not a product cost-performance result. |
| `cost_performance-N09` | source_visible_synthetic_fixture | `u18a-cost_performance-n09` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | An unavailable chart is said to show MiniMax efficiency; the visible text supplies no result. |
| `cost_performance-N10` | source_visible_synthetic_fixture | `u18a-cost_performance-n10` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax staff celebrate revenue growth, which is not a product cost-performance topic. |

## `model_distillation`

Distillation, imitation, model extraction, or training on another model's outputs.

Retained-source scan found 0 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `model_distillation-P01` | source_visible_synthetic_fixture | `u18a-model_distillation-p01` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | A report alleges MiniMax trained its model on another vendor’s outputs through distillation. |
| `model_distillation-P02` | source_visible_synthetic_fixture | `u18a-model_distillation-p02` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | The filing claims MiniMax used synthetic answers from a closed model to train a student checkpoint. |
| `model_distillation-P03` | source_visible_synthetic_fixture | `u18a-model_distillation-p03` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | MiniMax says its compact model was distilled from its larger teacher model. |
| `model_distillation-P04` | source_visible_synthetic_fixture | `u18a-model_distillation-p04` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | The author asks whether MiniMax extracted a competitor’s behavior through repeated API queries. |
| `model_distillation-P05` | source_visible_synthetic_fixture | `u18a-model_distillation-p05` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | An investigation describes MiniMax imitation training on generated answers from a third-party model. |
| `model_distillation-P06` | source_visible_synthetic_fixture | `u18a-model_distillation-p06` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | MiniMax’s release notes call M1 a distilled version of the company’s frontier checkpoint. |
| `model_distillation-P07` | source_visible_synthetic_fixture | `u18a-model_distillation-p07` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | The post alleges MiniMax copied hidden reasoning traces into a training set. |
| `model_distillation-P08` | source_visible_synthetic_fixture | `u18a-model_distillation-p08` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | Researchers report a possible MiniMax model-extraction attack against a proprietary API. |
| `model_distillation-P09` | source_visible_synthetic_fixture | `u18a-model_distillation-p09` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | MiniMax published a student-teacher distillation recipe for its small model. |
| `model_distillation-P10` | source_visible_synthetic_fixture | `u18a-model_distillation-p10` | `minimax` | `third_party` | `{"audience_topics":["model_distillation"]}` | A former employee claims MiniMax’s benchmark gains came from competitor-output distillation. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `model_distillation-N01` | source_visible_synthetic_fixture | `u18a-model_distillation-n01` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax compared its outputs to a competitor; comparison alone is not distillation. |
| `model_distillation-N02` | source_visible_synthetic_fixture | `u18a-model_distillation-n02` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax released a smaller model, but no teacher, extraction, imitation, or output-training evidence appears. |
| `model_distillation-N03` | source_visible_synthetic_fixture | `u18a-model_distillation-n03` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A user says MiniMax copied a user-interface layout; that is not model distillation. |
| `model_distillation-N04` | source_visible_synthetic_fixture | `u18a-model_distillation-n04` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax compressed a model file; compression alone is not distillation. |
| `model_distillation-N05` | source_visible_synthetic_fixture | `u18a-model_distillation-n05` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | The author speculates MiniMax learned quickly, without alleging training on another model’s outputs. |
| `model_distillation-N06` | source_visible_synthetic_fixture | `u18a-model_distillation-n06` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A report alleges a rival copied data; MiniMax is only mentioned as a benchmark foil. |
| `model_distillation-N07` | source_visible_synthetic_fixture | `u18a-model_distillation-n07` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax uses synthetic data, but the source does not say it came from another model’s outputs. |
| `model_distillation-N08` | source_visible_synthetic_fixture | `u18a-model_distillation-n08` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s score resembles a rival’s score; similarity is not visible evidence of extraction. |
| `model_distillation-N09` | source_visible_synthetic_fixture | `u18a-model_distillation-n09` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | An unavailable video supposedly proves MiniMax distillation; no visible predicate supports it. |
| `model_distillation-N10` | source_visible_synthetic_fixture | `u18a-model_distillation-n10` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax staff say the model was trained efficiently, without a teacher/student or imitation claim. |

## `evals_benchmarks`

Actual test, benchmark, evaluation method, score, ranking, reported evaluation result, or source-visible comparative assessment.

Retained-source scan found 2 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `evals_benchmarks-P01` | retained_real_source | `2078840100826550492` | `qwen` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | 所以真的很怕以后 Qwen 模型 Benchmark 越刷越漂亮，但实战很拉垮，最后高分低能，变成一个完成领导 KPI 任务的 AGI 🙈 |
| `evals_benchmarks-P02` | retained_real_source | `2095889674942517364` | `qwen` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | @cyrilXBT worth knowing the SWE-bench Pro number is apples to oranges though , Qwen reran the other models on a corrected task set but imported Opus's official score from the original benchmark |
| `evals_benchmarks-P03` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-p03` | `minimax` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | The evaluation method ran MiniMax and the baseline on identical prompts and reported latency. |
| `evals_benchmarks-P04` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-p04` | `minimax` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | MiniMax won 63 of 100 blinded pairwise preference tests in this study. |
| `evals_benchmarks-P05` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-p05` | `minimax` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | A paper reports MiniMax’s exact score, test split, and evaluation protocol. |
| `evals_benchmarks-P06` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-p06` | `minimax` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | MiniMax’s regression test found 14 failures after the new release. |
| `evals_benchmarks-P07` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-p07` | `minimax` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | The benchmark ranks MiniMax above the baseline on tool-use success rate. |
| `evals_benchmarks-P08` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-p08` | `minimax` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | We measured MiniMax on a fixed dataset and published the per-task results. |
| `evals_benchmarks-P09` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-p09` | `minimax` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | MiniMax’s safety evaluation reports a 4.1% refusal failure rate. |
| `evals_benchmarks-P10` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-p10` | `minimax` | `third_party` | `{"audience_topics":["evals_benchmarks"]}` | The author’s visible comparison shows MiniMax completed 9 of 12 workflow tests. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `evals_benchmarks-N01` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n01` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax is impressive; generic praise is not an evaluation or benchmark. |
| `evals_benchmarks-N02` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n02` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax is the best model, with no test, score, method, ranking, or observed output. |
| `evals_benchmarks-N03` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n03` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | The post links a benchmark video but the visible text gives no evaluative result. |
| `evals_benchmarks-N04` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n04` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A rival scored highly; MiniMax is merely named in a hashtag. |
| `evals_benchmarks-N05` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n05` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax has a fast release cadence, which is not a quality evaluation. |
| `evals_benchmarks-N06` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n06` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | The author predicts MiniMax will win a benchmark next year; prediction is not a result. |
| `evals_benchmarks-N07` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n07` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s founder says the model is strong; authority is not an actual test. |
| `evals_benchmarks-N08` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n08` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A customer calls MiniMax useful without describing observed performance or comparison. |
| `evals_benchmarks-N09` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n09` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax shipped a feature; release reporting alone is not an evaluation. |
| `evals_benchmarks-N10` | source_visible_synthetic_fixture | `u18a-evals_benchmarks-n10` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | The word ‘benchmark’ appears in a quote about another vendor, not as MiniMax evidence. |

## `openness_license`

Open weights, open source, source availability, licensing, access, or restrictions.

Retained-source scan found 8 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `openness_license-P01` | retained_real_source | `2077228477808607696` | `deepseek` | `third_party` | `{"audience_topics":["openness_license"]}` | -Open-source, native: DeepSeek V4 Pro, Qwen 3.7 Max, GLM 5.2, Kimi K2.7 Code |
| `openness_license-P02` | retained_real_source | `2083234926485532965` | `deepseek` | `third_party` | `{"audience_topics":["openness_license"]}` | Was watching CNN with my dad when they started discussing DeepSeek nd Chinese open source AI models. |
| `openness_license-P03` | retained_real_source | `2084410948358705273` | `minimax` | `staff` | `{"audience_topics":["openness_license"]}` | Apply by emailing api@minimax.io with the subject “MiniMax H3 licensing - authorization request.” |
| `openness_license-P04` | retained_real_source | `2084689694278013316` | `qwen` | `third_party` | `{"audience_topics":["openness_license"]}` | Now DeepSeek and Qwen run on domestic silicon and ship open weights |
| `openness_license-P05` | retained_real_source | `2087114164560912691` | `qwen` | `third_party` | `{"audience_topics":["openness_license"]}` | @Alibaba_Qwen can you please release Qwen-3.8 27B open weights today |
| `openness_license-P06` | retained_real_source | `2088668007560003690` | `qwen` | `third_party` | `{"audience_topics":["openness_license"]}` | The arrival of models like DeepSeek, Qwen, and the broader open-source ecosystem is our TCP/IP moment. |
| `openness_license-P07` | retained_real_source | `2092507336405553330` | `qwen` | `third_party` | `{"audience_topics":["openness_license"]}` | European companies want to use the latest open-weight models: Qwen, DeepSeek, GLM, Llama, Kimi, GPT-OSS, Mistral… |
| `openness_license-P08` | retained_real_source | `2093889800017453424` | `deepseek` | `third_party` | `{"audience_topics":["openness_license"]}` | Chinese state-linked hacking groups are reportedly launching 2X+ more attacks after integrating open-source AI models like DeepSeek into their operations. |
| `openness_license-P09` | source_visible_synthetic_fixture | `u18a-openness_license-p09` | `minimax` | `third_party` | `{"audience_topics":["openness_license"]}` | MiniMax removed public download access to its previously open checkpoint. |
| `openness_license-P10` | source_visible_synthetic_fixture | `u18a-openness_license-p10` | `minimax` | `third_party` | `{"audience_topics":["openness_license"]}` | MiniMax’s open-weight release includes a license link and access terms. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `openness_license-N01` | source_visible_synthetic_fixture | `u18a-openness_license-n01` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax opened a new office; ‘opened’ is not an openness or licensing claim. |
| `openness_license-N02` | source_visible_synthetic_fixture | `u18a-openness_license-n02` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s API is publicly accessible, but no source, weights, or license terms are discussed. |
| `openness_license-N03` | source_visible_synthetic_fixture | `u18a-openness_license-n03` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A user says MiniMax is transparent; that is not source availability or a license. |
| `openness_license-N04` | source_visible_synthetic_fixture | `u18a-openness_license-n04` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax invited users to an open webinar, not an open-source release. |
| `openness_license-N05` | source_visible_synthetic_fixture | `u18a-openness_license-n05` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | The post mentions a competitor’s open weights; MiniMax is only a comparison foil. |
| `openness_license-N06` | source_visible_synthetic_fixture | `u18a-openness_license-n06` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax has an open job requisition, which is unrelated to model openness. |
| `openness_license-N07` | source_visible_synthetic_fixture | `u18a-openness_license-n07` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | An unavailable linked page may contain a license; no visible terms are available. |
| `openness_license-N08` | source_visible_synthetic_fixture | `u18a-openness_license-n08` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s CEO calls the company open-minded; this is not a licensing predicate. |
| `openness_license-N09` | source_visible_synthetic_fixture | `u18a-openness_license-n09` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax exposes a dashboard to customers, not code/weights/source access. |
| `openness_license-N10` | source_visible_synthetic_fixture | `u18a-openness_license-n10` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax staff refer to an ‘open question’ about research, not a source or license status. |

## `agents_tools`

Agents, harnesses, orchestration, tool use, or agent-development tooling.

Retained-source scan found 38 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `agents_tools-P01` | retained_real_source | `2083796905755365386` | `llama` | `third_party` | `{"audience_topics":["agents_tools"]}` | • 为什么重要：2026 年开源 LLM 的质变不在于某个模型的参数又叠高了一层，而在于三个结构性转变：(a) 许可证大洗牌——Gemma 4 从 Google 专有限制条款转向 Apache 2.0，DeepSeek V4 和 GLM-5.2 均采用宽松许可，但 Llama 和 Qwen 的大参数版本仍有商业天花板限制，企业在选型时需要逐版检查而非按家族记忆；(b) Agent Harness 生态成形——Nemotron、Gemma 4 等模型已明确适配 OpenClaw、OpenCode、Hermes Agent 等主流 Agent 框架，模型不再是孤立的"回复器"而是可嵌入工程流水线的组件；(c) 成本拐点到达——一个小团队可以几乎完全基于开源模型运行生产力平台，仅在极少数高难度任务上切换到顶级闭源模型，整体成本下降 80% 以上。 |
| `agents_tools-P02` | retained_real_source | `2083805766608470442` | `deepseek` | `third_party` | `{"audience_topics":["agents_tools"]}` | 很希望参与 DeepSeek Harness 内测，验证这些场景下的持续执行效果。 |
| `agents_tools-P03` | retained_real_source | `2083846657712779286` | `deepseek` | `third_party` | `{"audience_topics":["agents_tools"]}` | @xiongchun007 你还是没理解为什么 DeepSeek 要做自己的 Harness，而不是用 Pi, Codex 等，就是要协同训练形成飞轮。Harness 这个壳子作为独立产品的话，远没你想象中那么有价值 |
| `agents_tools-P04` | retained_real_source | `2085570929879588986` | `deepseek` | `third_party` | `{"audience_topics":["agents_tools"]}` | 希望能第一时间接入 DeepSeek Harness，提供多 Agent 协作 + MCP 支持。 |
| `agents_tools-P05` | retained_real_source | `2085654906426597529` | `deepseek` | `third_party` | `{"audience_topics":["agents_tools"]}` | 我又重读了邮件：经筛选，恭喜您获得 DeepSeek Harness 内测资格！ |
| `agents_tools-P06` | retained_real_source | `2087754769100071372` | `deepseek` | `third_party` | `{"audience_topics":["agents_tools"]}` | 🚨 LATEST: China’s DeepSeek has launched a new “Harness Team” and is hiring talent to develop advanced AI agents that could rival Anthropic’s Claude Code. |
| `agents_tools-P07` | retained_real_source | `2087808991812608025` | `deepseek` | `third_party` | `{"audience_topics":["agents_tools"]}` | #DeepSeek #Harness #AIAgent #大模型 #L站 |
| `agents_tools-P08` | retained_real_source | `2087888888249581740` | `deepseek` | `third_party` | `{"audience_topics":["agents_tools"]}` | DeepSeek Harness v0.1  已经发布 |
| `agents_tools-P09` | retained_real_source | `2087945965420564921` | `deepseek` | `third_party` | `{"audience_topics":["agents_tools"]}` | 我感觉 DeepSeek Harness 有点把这件事玩明白了。 |
| `agents_tools-P10` | retained_real_source | `2087961591505358962` | `deepseek` | `third_party` | `{"audience_topics":["agents_tools"]}` | DeepSeek Harness 团队，真正需要招的不是一帮天才程序员、奥林匹克金牌选手，需要真正懂 AI 产品的 AI 产品经理，这个阶段把产品定义清楚、规划清楚最重要。 |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `agents_tools-N01` | source_visible_synthetic_fixture | `u18a-agents_tools-n01` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax hired a talent agent; that employment role is not an AI agent/tool topic. |
| `agents_tools-N02` | source_visible_synthetic_fixture | `u18a-agents_tools-n02` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s customer support agent answered a billing question, with no model agent/tool capability detail. |
| `agents_tools-N03` | source_visible_synthetic_fixture | `u18a-agents_tools-n03` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | The post says MiniMax is proactive; it does not describe agents, harnesses, tools, or orchestration. |
| `agents_tools-N04` | source_visible_synthetic_fixture | `u18a-agents_tools-n04` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A competitor’s agent uses tools; MiniMax is merely listed among models. |
| `agents_tools-N05` | source_visible_synthetic_fixture | `u18a-agents_tools-n05` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax released a chat feature with no action-taking, tool, or workflow evidence. |
| `agents_tools-N06` | source_visible_synthetic_fixture | `u18a-agents_tools-n06` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax staff call their product an assistant, but no agentic behavior is shown. |
| `agents_tools-N07` | source_visible_synthetic_fixture | `u18a-agents_tools-n07` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | An unavailable demo supposedly shows MiniMax computer use; visible text has no details. |
| `agents_tools-N08` | source_visible_synthetic_fixture | `u18a-agents_tools-n08` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax is discussed in a workflow at a company, but the workflow is human-only. |
| `agents_tools-N09` | source_visible_synthetic_fixture | `u18a-agents_tools-n09` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A post asks for an agent feature for MiniMax; a request is not proof the topic exists in the product. |
| `agents_tools-N10` | source_visible_synthetic_fixture | `u18a-agents_tools-n10` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s brand ambassador is an ‘agent’ in a marketing sense, not agent tooling. |

## `api_developer_surface`

APIs, SDKs, developer interfaces, integrations, quotas, or developer-facing behavior.

Retained-source scan found 1 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `api_developer_surface-P01` | retained_real_source | `2090859504669798594` | `mimo` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | The others diverged, including MiMo pinned to Xiaomi's own endpoint. |
| `api_developer_surface-P02` | source_visible_synthetic_fixture | `u18a-api_developer_surface-p02` | `minimax` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | The MiniMax API migration guide explains a changed request schema and version header. |
| `api_developer_surface-P03` | source_visible_synthetic_fixture | `u18a-api_developer_surface-p03` | `minimax` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | MiniMax documented rate quotas and retry behavior for its developer API. |
| `api_developer_surface-P04` | source_visible_synthetic_fixture | `u18a-api_developer_surface-p04` | `minimax` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | MiniMax shipped a TypeScript SDK with streaming and tool-call interfaces. |
| `api_developer_surface-P05` | source_visible_synthetic_fixture | `u18a-api_developer_surface-p05` | `minimax` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | The MiniMax developer console now exposes usage keys and webhook configuration. |
| `api_developer_surface-P06` | source_visible_synthetic_fixture | `u18a-api_developer_surface-p06` | `minimax` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | MiniMax announced an API integration for a code editor with setup instructions. |
| `api_developer_surface-P07` | source_visible_synthetic_fixture | `u18a-api_developer_surface-p07` | `minimax` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | MiniMax’s endpoint adds JSON-mode support and a deprecation date for the old route. |
| `api_developer_surface-P08` | source_visible_synthetic_fixture | `u18a-api_developer_surface-p08` | `minimax` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | A developer reports MiniMax SDK authentication fails after a token refresh. |
| `api_developer_surface-P09` | source_visible_synthetic_fixture | `u18a-api_developer_surface-p09` | `minimax` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | MiniMax published API reference docs for batch jobs and response fields. |
| `api_developer_surface-P10` | source_visible_synthetic_fixture | `u18a-api_developer_surface-p10` | `minimax` | `third_party` | `{"audience_topics":["api_developer_surface"]}` | MiniMax’s developer platform raised a concurrency quota and documented the limit. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `api_developer_surface-N01` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n01` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s public web chat is available, but no API, SDK, integration, quota, or developer interface appears. |
| `api_developer_surface-N02` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n02` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax uses the word ‘interface’ to describe a visual design, not a developer surface. |
| `api_developer_surface-N03` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n03` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A user wants a MiniMax API; a request is not evidence of existing API behavior. |
| `api_developer_surface-N04` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n04` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s job listing seeks a developer; hiring is not an API/developer-surface topic. |
| `api_developer_surface-N05` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n05` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | A competitor’s SDK is described while MiniMax is only a comparison foil. |
| `api_developer_surface-N06` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n06` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax staff thank developers without describing a technical interface. |
| `api_developer_surface-N07` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n07` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | An unavailable documentation link may contain an endpoint, but no visible detail is available. |
| `api_developer_surface-N08` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n08` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax added a browser extension for end users, not an SDK/API/developer interface. |
| `api_developer_surface-N09` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n09` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | The post says MiniMax has many users; user volume is not API surface evidence. |
| `api_developer_surface-N10` | source_visible_synthetic_fixture | `u18a-api_developer_surface-n10` | `minimax` | `third_party` | `{"audience_topics":["none"]}` | MiniMax’s app has a settings menu, which is not a developer API or integration. |

## `news_reporting`

Broad factual or attributed reporting and news roundups involving the target brand; it may overlap independently supported types.

Retained-source scan found 3 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `news_reporting-P01` | retained_real_source | `2065802849661927518` | `qwen` | `third_party` | `{"post_types":["news_reporting"]}` | only the weaker Qwen models have been released as open source |
| `news_reporting-P02` | retained_real_source | `2087928070711771339` | `deepseek` | `third_party` | `{"post_types":["news_reporting"]}` | DeepSeek V4 Pro is released. |
| `news_reporting-P03` | retained_real_source | `2090085393764900926` | `minimax` | `third_party` | `{"post_types":["news_reporting"]}` | DomoAI Launches Seedance 2.5 and MiniMax H3 in Omni Reference for Long-Form Character Storytelling and Music Video Creation https://t.co/sApDHsVCsy #MarTech #MarketingTechnology #MarketingTech #AdTech #ContentMarketing |
| `news_reporting-P04` | source_visible_synthetic_fixture | `u18a-news_reporting-p04` | `minimax` | `third_party` | `{"post_types":["news_reporting"]}` | A roundup says MiniMax appointed a new research lead, attributing the information to the company filing. |
| `news_reporting-P05` | source_visible_synthetic_fixture | `u18a-news_reporting-p05` | `minimax` | `third_party` | `{"post_types":["news_reporting"]}` | The reporter relays MiniMax’s published API outage update without taking a personal stance. |
| `news_reporting-P06` | source_visible_synthetic_fixture | `u18a-news_reporting-p06` | `minimax` | `official` | `{"post_types":["news_reporting"]}` | MiniMax staff posted a factual update that the beta waitlist has reopened. |
| `news_reporting-P07` | source_visible_synthetic_fixture | `u18a-news_reporting-p07` | `minimax` | `third_party` | `{"post_types":["news_reporting"]}` | According to MiniMax’s release notes, the service changed its pricing tiers today. |
| `news_reporting-P08` | source_visible_synthetic_fixture | `u18a-news_reporting-p08` | `minimax` | `third_party` | `{"post_types":["news_reporting"]}` | A journalist summarizes MiniMax’s funding announcement and quotes the press release. |
| `news_reporting-P09` | source_visible_synthetic_fixture | `u18a-news_reporting-p09` | `minimax` | `official` | `{"post_types":["news_reporting"]}` | MiniMax’s official account reports a security patch and the affected product versions. |
| `news_reporting-P10` | source_visible_synthetic_fixture | `u18a-news_reporting-p10` | `minimax` | `third_party` | `{"post_types":["news_reporting"]}` | The post attributes a MiniMax hiring expansion to a named interview with its executive. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `news_reporting-N01` | source_visible_synthetic_fixture | `u18a-news_reporting-n01` | `minimax` | `third_party` | `{"post_types":[]}` | I think MiniMax will release a better model next year; this is a prediction, not reporting. |
| `news_reporting-N02` | source_visible_synthetic_fixture | `u18a-news_reporting-n02` | `minimax` | `third_party` | `{"post_types":[]}` | MiniMax is excellent; this is an opinion rather than factual or attributed reporting. |
| `news_reporting-N03` | source_visible_synthetic_fixture | `u18a-news_reporting-n03` | `minimax` | `third_party` | `{"post_types":[]}` | Do you think MiniMax will announce a new model? A question is not news reporting. |
| `news_reporting-N04` | source_visible_synthetic_fixture | `u18a-news_reporting-n04` | `minimax` | `third_party` | `{"post_types":[]}` | MiniMax posted a meme with no factual update or attributed claim. |
| `news_reporting-N05` | source_visible_synthetic_fixture | `u18a-news_reporting-n05` | `minimax` | `third_party` | `{"post_types":[]}` | A rival released a model; MiniMax is merely mentioned in a comparison reply. |
| `news_reporting-N06` | source_visible_synthetic_fixture | `u18a-news_reporting-n06` | `minimax` | `third_party` | `{"post_types":[]}` | The linked video may report MiniMax news, but its contents are unavailable in this packet. |
| `news_reporting-N07` | source_visible_synthetic_fixture | `u18a-news_reporting-n07` | `minimax` | `third_party` | `{"post_types":[]}` | MiniMax staff praise their team without giving a factual update. |
| `news_reporting-N08` | source_visible_synthetic_fixture | `u18a-news_reporting-n08` | `minimax` | `third_party` | `{"post_types":[]}` | The author says ‘breaking’ but supplies no factual or attributed MiniMax information. |
| `news_reporting-N09` | source_visible_synthetic_fixture | `u18a-news_reporting-n09` | `minimax` | `third_party` | `{"post_types":[]}` | MiniMax’s benchmark score is discussed as personal analysis, not a report or news roundup. |
| `news_reporting-N10` | source_visible_synthetic_fixture | `u18a-news_reporting-n10` | `minimax` | `third_party` | `{"post_types":[]}` | A historical anecdote about the author’s MiniMax use is not news reporting. |

## `investigate_claim`

A consequential allegation or unusually material assertion about the target brand/product/company that could materially affect product evaluation, reputation, safety, or strategy if true. It is not a truth judgment.

Retained-source scan found 0 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `investigate_claim-P01` | source_visible_synthetic_fixture | `u18a-investigate_claim-p01` | `minimax` | `third_party` | `{"product_labels":["investigate_claim"]}` | A former contractor alleges MiniMax trained on private customer data; the allegation warrants verification. |
| `investigate_claim-P02` | source_visible_synthetic_fixture | `u18a-investigate_claim-p02` | `minimax` | `third_party` | `{"product_labels":["investigate_claim"]}` | The report claims MiniMax concealed a security breach affecting API keys. |
| `investigate_claim-P03` | source_visible_synthetic_fixture | `u18a-investigate_claim-p03` | `minimax` | `third_party` | `{"product_labels":["investigate_claim"]}` | Researchers allege MiniMax extracted competitor model outputs through automated queries. |
| `investigate_claim-P04` | source_visible_synthetic_fixture | `u18a-investigate_claim-p04` | `minimax` | `third_party` | `{"product_labels":["investigate_claim"]}` | A filing asserts MiniMax misstated model-safety test results to customers. |
| `investigate_claim-P05` | source_visible_synthetic_fixture | `u18a-investigate_claim-p05` | `minimax` | `third_party` | `{"product_labels":["investigate_claim"]}` | The author reports an allegation that MiniMax paid for undisclosed benchmark manipulation. |
| `investigate_claim-P06` | source_visible_synthetic_fixture | `u18a-investigate_claim-p06` | `minimax` | `third_party` | `{"product_labels":["investigate_claim"]}` | A whistleblower claims MiniMax routed sensitive prompts to an unannounced third party. |
| `investigate_claim-P07` | source_visible_synthetic_fixture | `u18a-investigate_claim-p07` | `minimax` | `third_party` | `{"product_labels":["investigate_claim"]}` | The post alleges MiniMax copied licensed training data without permission. |
| `investigate_claim-P08` | source_visible_synthetic_fixture | `u18a-investigate_claim-p08` | `minimax` | `third_party` | `{"product_labels":["investigate_claim"]}` | A security researcher says MiniMax exposed private files through a configuration flaw and asks for verification. |
| `investigate_claim-P09` | source_visible_synthetic_fixture | `u18a-investigate_claim-p09` | `minimax` | `third_party` | `{"product_labels":["investigate_claim"]}` | An investigation claims MiniMax hid a serious model-evasion finding from users. |
| `investigate_claim-P10` | source_visible_synthetic_fixture | `u18a-investigate_claim-p10` | `minimax` | `staff` | `{"product_labels":["investigate_claim"]}` | A former staff member alleges MiniMax fraudulently represented an external certification. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `investigate_claim-N01` | source_visible_synthetic_fixture | `u18a-investigate_claim-n01` | `minimax` | `third_party` | `{"product_labels":["none"]}` | MiniMax is worse than its rival; ordinary opinion is not a consequential investigate-claim. |
| `investigate_claim-N02` | source_visible_synthetic_fixture | `u18a-investigate_claim-n02` | `minimax` | `third_party` | `{"product_labels":["none"]}` | MiniMax scored 80 on a benchmark; an ordinary evaluation is not an investigate-claim. |
| `investigate_claim-N03` | source_visible_synthetic_fixture | `u18a-investigate_claim-n03` | `minimax` | `third_party` | `{"product_labels":["none"]}` | MiniMax’s customer says the app crashed; a bug report is not a material company claim. |
| `investigate_claim-N04` | source_visible_synthetic_fixture | `u18a-investigate_claim-n04` | `minimax` | `third_party` | `{"product_labels":["none"]}` | MiniMax claims its model is best; routine marketing is not an investigate-claim. |
| `investigate_claim-N05` | source_visible_synthetic_fixture | `u18a-investigate_claim-n05` | `minimax` | `third_party` | `{"product_labels":["none"]}` | A report alleges a rival leaked data; MiniMax is only a comparison foil. |
| `investigate_claim-N06` | source_visible_synthetic_fixture | `u18a-investigate_claim-n06` | `minimax` | `third_party` | `{"product_labels":["none"]}` | MiniMax may improve next year; a prediction is not a material allegation. |
| `investigate_claim-N07` | source_visible_synthetic_fixture | `u18a-investigate_claim-n07` | `minimax` | `third_party` | `{"product_labels":["none"]}` | The post questions MiniMax’s design choices without alleging wrongdoing, leakage, fraud, or security harm. |
| `investigate_claim-N08` | source_visible_synthetic_fixture | `u18a-investigate_claim-n08` | `minimax` | `third_party` | `{"product_labels":["none"]}` | An unavailable video supposedly accuses MiniMax; visible evidence is insufficient. |
| `investigate_claim-N09` | source_visible_synthetic_fixture | `u18a-investigate_claim-n09` | `minimax` | `third_party` | `{"product_labels":["none"]}` | MiniMax staff deny a rumor, but the post does not state what consequential claim is being alleged. |
| `investigate_claim-N10` | source_visible_synthetic_fixture | `u18a-investigate_claim-n10` | `minimax` | `third_party` | `{"product_labels":["none"]}` | The author says MiniMax is expensive; customer cost criticism is not an investigate-claim. |

## `geopolitical`

reporting neutrally relays an attributed geopolitical claim; framework explains relationships among states, policy, markets, security, national systems, or state actors; nationalism adopts evaluative sentiment toward a nation/national system/group or evaluates through national origin.

Retained-source scan found 0 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `geopolitical-P01` | source_visible_synthetic_fixture | `u18a-geopolitical-p01` | `minimax` | `third_party` | `{"geopolitical_modes":["reporting"],"china_national_stance":"none","us_national_stance":"none"}` | Reuters reported that a Chinese official called China’s AI policy superior; this post attributes that view and adopts no national stance about MiniMax. |
| `geopolitical-P02` | source_visible_synthetic_fixture | `u18a-geopolitical-p02` | `minimax` | `third_party` | `{"geopolitical_modes":["framework"],"china_national_stance":"none","us_national_stance":"none"}` | MiniMax’s supply chain illustrates how U.S. export rules, Chinese cloud capacity, and national compute policy shape deployment; this is a neutral framework. |
| `geopolitical-P03` | source_visible_synthetic_fixture | `u18a-geopolitical-p03` | `minimax` | `third_party` | `{"geopolitical_modes":["nationalism"],"china_national_stance":"none","us_national_stance":"none"}` | China’s national AI system is exploitative, so companies such as MiniMax should not be trusted because they are Chinese. |
| `geopolitical-P04` | source_visible_synthetic_fixture | `u18a-geopolitical-p04` | `minimax` | `third_party` | `{"geopolitical_modes":["reporting"],"china_national_stance":"none","us_national_stance":"none"}` | The article relays a U.S. senator’s criticism of Chinese AI firms, without endorsing the senator’s position about MiniMax. |
| `geopolitical-P05` | source_visible_synthetic_fixture | `u18a-geopolitical-p05` | `minimax` | `third_party` | `{"geopolitical_modes":["framework"],"china_national_stance":"none","us_national_stance":"none"}` | The post explains how China-U.S. chip restrictions alter MiniMax’s access to accelerators without praising either nation. |
| `geopolitical-P06` | source_visible_synthetic_fixture | `u18a-geopolitical-p06` | `minimax` | `third_party` | `{"geopolitical_modes":["nationalism"],"china_national_stance":"none","us_national_stance":"none"}` | America’s AI ecosystem is morally superior because capitalism makes U.S. companies like MiniMax’s rivals more deserving of trust. |
| `geopolitical-P07` | source_visible_synthetic_fixture | `u18a-geopolitical-p07` | `minimax` | `third_party` | `{"geopolitical_modes":["reporting"],"china_national_stance":"none","us_national_stance":"none"}` | MiniMax’s official account quotes a government export-control notice without evaluating either country. |
| `geopolitical-P08` | source_visible_synthetic_fixture | `u18a-geopolitical-p08` | `minimax` | `third_party` | `{"geopolitical_modes":["framework"],"china_national_stance":"none","us_national_stance":"none"}` | MiniMax’s expansion is analyzed through state procurement, security policy, and cross-border data rules. |
| `geopolitical-P09` | source_visible_synthetic_fixture | `u18a-geopolitical-p09` | `minimax` | `third_party` | `{"geopolitical_modes":["nationalism"],"china_national_stance":"none","us_national_stance":"none"}` | MiniMax proves Chinese engineering is inherently superior to American model builders. |
| `geopolitical-P10` | source_visible_synthetic_fixture | `u18a-geopolitical-p10` | `minimax` | `third_party` | `{"geopolitical_modes":["reporting"],"china_national_stance":"none","us_national_stance":"none"}` | A reporter attributes praise of American AI leadership to an investor, rather than adopting it. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `geopolitical-N01` | source_visible_synthetic_fixture | `u18a-geopolitical-n01` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | MiniMax is based in China; nationality alone is not geopolitical mode or nationalism. |
| `geopolitical-N02` | source_visible_synthetic_fixture | `u18a-geopolitical-n02` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | MiniMax released a model in the U.S. market; market location alone is not geopolitics. |
| `geopolitical-N03` | source_visible_synthetic_fixture | `u18a-geopolitical-n03` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | The author praises MiniMax’s speed without evaluating any nation or national system. |
| `geopolitical-N04` | source_visible_synthetic_fixture | `u18a-geopolitical-n04` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | A post names Chinese food at a MiniMax meetup; it has no state, policy, national-system, or evaluative predicate. |
| `geopolitical-N05` | source_visible_synthetic_fixture | `u18a-geopolitical-n05` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | A rival’s founder is American; individual nationality alone is insufficient. |
| `geopolitical-N06` | source_visible_synthetic_fixture | `u18a-geopolitical-n06` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | MiniMax staff mention a U.S. conference itinerary with no geopolitical analysis or stance. |
| `geopolitical-N07` | source_visible_synthetic_fixture | `u18a-geopolitical-n07` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | An unavailable image may contain a flag, but the visible text supplies no geopolitical evidence. |
| `geopolitical-N08` | source_visible_synthetic_fixture | `u18a-geopolitical-n08` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | The author criticizes MiniMax’s product design, not China, the U.S., or a national system. |
| `geopolitical-N09` | source_visible_synthetic_fixture | `u18a-geopolitical-n09` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | A neutral benchmark compares MiniMax and a U.S. rival without explaining or evaluating their national origins. |
| `geopolitical-N10` | source_visible_synthetic_fixture | `u18a-geopolitical-n10` | `minimax` | `third_party` | `{"geopolitical_modes":["none"],"china_national_stance":"none","us_national_stance":"none"}` | The post reports a country name in an address, not a geopolitical claim. |

## `untracked_brand_promotions`

Promotion of a company/product/service/project outside the tracked catalog. general is an exclusive fallback; spam requires repetition; scam requires visible fraud; crypto is a crypto/token/blockchain asset promotion; unauthorized requires visible evidence of lack of authorization.

Retained-source scan found 0 bounded lexical candidates. case-insensitive source-visible lexical predicate over the frozen 700-row source cohort; rows over 3,500 characters excluded for bounded human-readable packets

### Positive cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `untracked_brand_promotions-P01` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p01` | `minimax` | `third_party` | `{"post_promotions":["general"],"promoted_subjects":[{"name":"Astorie","evidence":"Astorie launched an AI video editor with timeline agents. Try it at https://astorie.example/start."}]}` | Astorie launched an AI video editor with timeline agents. Try it at https://astorie.example/start. |
| `untracked_brand_promotions-P02` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p02` | `minimax` | `third_party` | `{"post_promotions":["spam"],"promoted_subjects":[{"name":"RepeatBot","evidence":"RepeatBot AI: subscribe at https://repeatbot.example now. RepeatBot AI: subscribe at https://repeatbot.example now."}]}` | RepeatBot AI: subscribe at https://repeatbot.example now. RepeatBot AI: subscribe at https://repeatbot.example now. |
| `untracked_brand_promotions-P03` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p03` | `minimax` | `third_party` | `{"post_promotions":["scam"],"promoted_subjects":[{"name":"QuickProfit AI","evidence":"QuickProfit AI promises guaranteed 40% daily returns; send funds now at https://quickprofit.example."}]}` | QuickProfit AI promises guaranteed 40% daily returns; send funds now at https://quickprofit.example. |
| `untracked_brand_promotions-P04` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p04` | `minimax` | `third_party` | `{"post_promotions":["crypto"],"promoted_subjects":[{"name":"PokePay Token","evidence":"PokePay Token airdrop: connect your wallet to claim tokens at https://pokepay.example/claim."}]}` | PokePay Token airdrop: connect your wallet to claim tokens at https://pokepay.example/claim. |
| `untracked_brand_promotions-P05` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p05` | `minimax` | `third_party` | `{"post_promotions":["unauthorized"],"promoted_subjects":[{"name":"FakeMiniMaxPlus","evidence":"FakeMiniMaxPlus claims it is MiniMax-approved, but MiniMax says this reseller is not authorized. Buy at https://fakeminimax.example."}]}` | FakeMiniMaxPlus claims it is MiniMax-approved, but MiniMax says this reseller is not authorized. Buy at https://fakeminimax.example. |
| `untracked_brand_promotions-P06` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p06` | `minimax` | `third_party` | `{"post_promotions":["general"],"promoted_subjects":[{"name":"Sider","evidence":"Sider’s new AI research workspace is available now; start a workspace at https://sider.example/join."}]}` | Sider’s new AI research workspace is available now; start a workspace at https://sider.example/join. |
| `untracked_brand_promotions-P07` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p07` | `minimax` | `third_party` | `{"post_promotions":["spam"],"promoted_subjects":[{"name":"ClickForge","evidence":"ClickForge giveaway at https://clickforge.example/claim. ClickForge giveaway at https://clickforge.example/claim."}]}` | ClickForge giveaway at https://clickforge.example/claim. ClickForge giveaway at https://clickforge.example/claim. |
| `untracked_brand_promotions-P08` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p08` | `minimax` | `third_party` | `{"post_promotions":["scam"],"promoted_subjects":[{"name":"Recovery Genius","evidence":"Recovery Genius says it can recover any lost crypto instantly for an upfront fee at https://recoverygenius.example."}]}` | Recovery Genius says it can recover any lost crypto instantly for an upfront fee at https://recoverygenius.example. |
| `untracked_brand_promotions-P09` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p09` | `minimax` | `third_party` | `{"post_promotions":["crypto"],"promoted_subjects":[{"name":"ChainMind Coin","evidence":"Buy ChainMind Coin before the exchange listing at https://chainmind.example/buy; token holders get AI credits."}]}` | Buy ChainMind Coin before the exchange listing at https://chainmind.example/buy; token holders get AI credits. |
| `untracked_brand_promotions-P10` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-p10` | `minimax` | `third_party` | `{"post_promotions":["unauthorized"],"promoted_subjects":[{"name":"MiniMax Official Rewards","evidence":"MiniMax warns that ‘MiniMax Official Rewards’ is not an authorized partner, despite its promotion at https://fake-rewards.example."}]}` | MiniMax warns that ‘MiniMax Official Rewards’ is not an authorized partner, despite its promotion at https://fake-rewards.example. |

### Matched negative or boundary cases

| Case | Provenance | Source | Target | Source role | Expected | Exact visible evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `untracked_brand_promotions-N01` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n01` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | MiniMax’s official account says: MiniMax H3 is available today at https://minimax.example; a tracked brand’s own promotion is not untracked-brand promotion. |
| `untracked_brand_promotions-N02` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n02` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | MiniMax benchmarked against ExampleForge, but gives no pitch, link, call to action, or promotion for ExampleForge. |
| `untracked_brand_promotions-N03` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n03` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | A reporter neutrally names untracked Astorie in a MiniMax market roundup without promoting it. |
| `untracked_brand_promotions-N04` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n04` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | DeepSeek’s official account says DSV4 outperformed MiniMax and links to DeepSeek; MiniMax is a comparison foil, not the promoted subject. |
| `untracked_brand_promotions-N05` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n05` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | The post uses #crypto while discussing MiniMax safety research, with no token, wallet, asset, or promotion. |
| `untracked_brand_promotions-N06` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n06` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | A customer repeats the word ‘subscribe’ while asking MiniMax for a billing fix; this is not repeated promotion of an untracked subject. |
| `untracked_brand_promotions-N07` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n07` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | The author calls ExampleForge suspicious but supplies no fraud/deception promotion or actionable solicitation. |
| `untracked_brand_promotions-N08` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n08` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | An unavailable linked video may advertise a third party, but no promoted subject or visible evidence is supplied. |
| `untracked_brand_promotions-N09` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n09` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | MiniMax staff share a partner’s neutral technical paper, with no promotion or claimed commercial relationship. |
| `untracked_brand_promotions-N10` | source_visible_synthetic_fixture | `u18a-untracked_brand_promotions-n10` | `minimax` | `third_party` | `{"post_promotions":["none"],"promoted_subjects":[]}` | A parody account claims an affiliate relationship, but visible text gives no target, offer, product, or promotion to classify. |

## Limitations

- The frozen 700-row source cohort predates U18A labels, so lexical selection establishes source visibility but cannot establish population prevalence or independently annotated negative support.
- Synthetic fixtures are used only to fill missing rare U18A predicates or create unambiguous matched boundaries; each says so and contains its entire visible evidence.
- The artifact freezes expected decisions before candidate comparison. It does not assert that a later candidate passes R94A; the deterministic comparator must score candidate rows against this artifact.
- Promotion fixtures use a test-local tracked catalog containing MiniMax only. Production comparison must substitute the actual frozen tracked catalog and reject any subject that is tracked there.
- No unseen media, URLs, parent posts, source-account history, truth adjudication, or candidate/owner/model output was used.
