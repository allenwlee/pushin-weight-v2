# Direct DeepSeek V4.1 classifier benchmark — diagnostic 24

## Scope

This run compares direct DeepSeek's incumbent request alias `deepseek-v4-flash`
against Qwen classifier v6 on the expanded current taxonomy. It used the exact
24 source posts from `classifier-input.json` (SHA-256
`fe4aa63eb4bbfdb38deba5d0f3b4f08a71d62e5db67021b437d384559ce9d0bf`), one
source per batch, and exactly two roles: `content` and `brand_interpretation`.
It did not expose historical owner labels to the model.

The 48 logical requests have the same source evidence, system prompt, readable
named-field output contract, and 4,096-token maximum as Qwen v6. The direct
wire form uses the verified Anthropic-compatible endpoint:

- request model: `deepseek-v4-flash`
- base URL: `https://api.deepseek.com/anthropic`
- thinking: `{"type":"disabled"}`
- response identity accepted: `deepseek-v4-flash` or the previously observed
  `deepseek-flash`; all 48 replies attested `deepseek-v4-flash` with a provider
  request ID.

The contract, raw model text, provider usage, parsed results, and consumed
marker are retained in
`.context/model-task-20260917/deepseek-v41-incumbent-classification-v1-diagnostic24/`.

## Delivery result

| Measure | Result |
|---|---:|
| Provider calls | 48 / 48 |
| Raw text retained | 48 / 48 |
| Strict local parser calls | 48 / 48 |
| Strict complete source pairs | 24 / 24 |
| Transport or parser source errors | 0 / 24 |
| Qwen v6 bare-envelope replay recovery | 0 additional calls |
| Qwen v6 canonical-brand-key replay recovery | 0 additional calls |

This is a delivery result only. It meets the structural part of the diagnostic
gate but is not a semantic-quality pass.

Reported provider usage totals were 27,844 input tokens, 111,488 cache-read
input tokens, zero cache-creation tokens, and 3,864 output tokens. Aggregate
sequential latency was 51,256 ms (621–1,552 ms per call; 1,067.8 ms mean).

The September 17 OpenRouter snapshot contains a DeepSeek-provider endpoint,
but its own provenance says it is not direct DeepSeek account pricing. The
contract therefore records direct billed cost as unavailable. It reserves the
authorized $3 task budget in the shared ledger as an allocation, not a price
estimate or actual-cost claim.

## Confirmed source-level semantic failures

These are reviewed against the supplied text and context, including the
existing adjudicated boundaries. They show why structural delivery cannot
qualify this arm. They are examples, not a complete semantic error rate.

| Source post | Model output | Evidence-based issue |
|---|---|---|
| `H-H0DEC6F537E0` | Content only `events`; brand `ideas_requests` / neutral | “I have some Issues, Can we discuss about it” is a Qwen-specific question/request. The content role omits `questions_requests`. The `ideas_requests` product label is retained as an owner-accepted boundary and is not counted as an error here. |
| `H-H3569508600E` | Content `results_analysis`; brand `ideas_requests` / neutral | The post is a practical local MiniMax H3 tutorial with a specific measured setup. It omits accepted `research_explanations` and the favorable/testimonial reading, while adding unsupported `ideas_requests`. |
| `H-H92A808A114E` | Brand `none` / neutral | The source directly reports MiniMax H3's nine-second-to-fifteen-second video capability. It omits the accepted positive/testimonial assessment. The later generic digital-human limitation must not be transferred to MiniMax, but it does not erase the direct H3 evidence. |
| `L-L45-21` | All three brands: positive testimonial and China `pro`; U.S. `none` | The post warns that Chinese AI would spread Chinese ideology globally and frames U.S. slowdown as benefiting China. The output reverses the negative China stance and misses the constructive-critical U.S. stance. |
| `L-L45-22` | DeepSeek `releases_updates`, `opinions_reactions`, API/openness/cost topics; brand `none` / neutral | The announced open-weight/API release is an unnamed competitor. DeepSeek is only a comparison foil (“better than DeepSeek Flash”), so release/API/openness should not transfer to it. Whether the unidentified competitor satisfies an untracked-brand promotion identity requirement remains a separate uncertainty, not a confirmed error. |

No aggregate semantic score is reported: the remaining source-level outputs
have not yet received a complete evidence review under the current taxonomy.

## Strict parsed output by source post

This table is a transcription of the strict parsed output, not an adjudicated gold table. `C` is the content role and `B` is the brand role.

| Source post | C: post types / topics | B: product labels; sentiment; geopolitical modes; China / U.S. stance |
|---|---|---|
| `H-H0040D161174` | qwen: opinions_reactions / openness_license,local_inference,cost_performance | qwen: none; neutral; reporting,framework; none / none |
| `H-H0DEC6F537E0` | qwen: events / none | qwen: ideas_requests; neutral; none; none / none |
| `H-H1E48CCEEB2F` | deepseek: hands_on_usage,results_analysis,opinions_reactions / local_inference,agents_tools | deepseek: none; neutral; none; none / none |
| `H-H2B36BE298C6` | deepseek: news_reporting / model_distillation | deepseek: investigate_claim; negative; reporting,framework; none / none |
| `H-H3569508600E` | minimax: results_analysis / local_inference,cost_performance | minimax: ideas_requests; neutral; none; none / none |
| `H-H4E3B98376E5` | deepseek: opinions_reactions / none | deepseek: none; neutral; none; none / none |
| `H-H7046A8A0689` | qwen: opinions_reactions / none | qwen: none; mixed; none; none / none |
| `H-H74C810FB007` | deepseek: results_analysis,opinions_reactions / evals_benchmarks | deepseek: complaint; mixed; none; none / none |
| `H-H8FA9071508D` | hunyuan: [] / unavailable | hunyuan: none; unknown; unavailable; unknown / unknown |
| `H-H92A808A114E` | minimax: results_analysis,opinions_reactions / cost_performance | minimax: none; neutral; none; none / none |
| `H-HAF1D06FBEBA` | glm: hands_on_usage,opinions_reactions,business_finance / cost_performance,api_developer_surface | glm: bug,complaint; mixed; none; none / none |
| `H-HFD61C2DE5BD` | minimax: results_analysis,opinions_reactions / evals_benchmarks,agents_tools | minimax: testimonial; positive; none; none / none |
| `L-L45-01` | deepseek: personnel_changes,business_finance,news_reporting / none; doubao: [] / unavailable; glm: [] / unavailable; minimax: [] / unavailable | deepseek: none; neutral; none; none / none; doubao: none; unknown; unavailable; unknown / unknown; glm: none; unknown; unavailable; unknown / unknown; minimax: none; unknown; unavailable; unknown / unknown |
| `L-L45-02` | deepseek: releases_updates,news_reporting / agents_tools | deepseek: bug,investigate_claim; negative; none; none / none |
| `L-L45-04` | ernie: news_reporting,business_finance,personnel_changes / none | ernie: none; neutral; none; none / none |
| `L-L45-07` | sakana_ai: job_listings / none | sakana_ai: none; neutral; none; none / none |
| `L-L45-09` | minimax: hands_on_usage,results_analysis,opinions_reactions / none | minimax: testimonial; positive; none; none / none |
| `L-L45-13` | deepseek: job_listings,news_reporting,opinions_reactions,business_finance / none | deepseek: none; neutral; framework; none / none |
| `L-L45-17` | deepseek: news_reporting,opinions_reactions,results_analysis / model_distillation,evals_benchmarks; moonshot_kimi: news_reporting,opinions_reactions,results_analysis / model_distillation,evals_benchmarks; qwen: news_reporting,opinions_reactions,results_analysis / model_distillation,evals_benchmarks | deepseek: investigate_claim; negative; reporting,framework; none / none; moonshot_kimi: investigate_claim; negative; reporting,framework; none / none; qwen: investigate_claim; negative; reporting,framework; none / none |
| `L-L45-21` | moonshot_kimi: opinions_reactions,news_reporting / none; deepseek: opinions_reactions,news_reporting / none; glm: opinions_reactions,news_reporting / none | moonshot_kimi: testimonial; positive; framework,nationalism; pro / none; deepseek: testimonial; positive; framework,nationalism; pro / none; glm: testimonial; positive; framework,nationalism; pro / none |
| `L-L45-22` | deepseek: releases_updates,opinions_reactions / api_developer_surface,openness_license,cost_performance | deepseek: none; neutral; none; none / none |
| `L-L45-23` | qwen: events,opportunities,news_reporting / agents_tools | qwen: testimonial; positive; none; none / none |
| `L-L45-30` | qwen: job_listings / none | qwen: none; neutral; none; none / none |
| `L-L45-45` | deepseek: hands_on_usage,opinions_reactions,results_analysis / cost_performance,agents_tools | deepseek: testimonial; positive; none; none / none |
