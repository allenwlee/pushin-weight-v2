# U18A R94A candidate comparison

- Candidate: `deepseek-ai/DeepSeek-V4-Flash-0731` via direct DeepInfra
- Evaluator artifact: `docs/analysis/2026-09-18-210000-u18a-r94a-candidate-blind-source-visible-audit.json`
- Evaluator SHA-256: `cf1ec56b963fe687eb0abb6a5d5e23d88ebf6475adc48b5b0818617cb4ac9678`
- Candidate output SHA-256: `e21b1902a571eaa1833548f18af02e33e2328dcdd95c53115d51a11fe04afce9`
- Calls: 22 successful, 1 errors
- Tokens: 107038 input, 21622 output
- Calculated cost: $0.01031424
- Wall time: 239.421s

| Family/concept | Positive unsupported | Negative/boundary unsupported | Decision |
| --- | ---: | ---: | --- |
| `local_inference` | 10 / 10 | 10 / 10 | `shadow_only` |
| `cost_performance` | 10 / 10 | 10 / 10 | `shadow_only` |
| `model_distillation` | 10 / 10 | 10 / 10 | `shadow_only` |
| `evals_benchmarks` | 10 / 10 | 10 / 10 | `shadow_only` |
| `openness_license` | 10 / 10 | 10 / 10 | `shadow_only` |
| `agents_tools` | 10 / 10 | 10 / 10 | `shadow_only` |
| `api_developer_surface` | 10 / 10 | 10 / 10 | `shadow_only` |
| `news_reporting` | 10 / 10 | 10 / 10 | `shadow_only` |
| `investigate_claim` | 10 / 10 | 10 / 10 | `shadow_only` |
| `geopolitical` | 10 / 10 | 10 / 10 | `shadow_only` |
| `untracked_brand_promotions` | 10 / 10 | 10 / 10 | `shadow_only` |

The R94A floor permits at most one unsupported assignment in each set. A shadow-only decision keeps the family unavailable to user-facing filters while retaining shadow evidence.

## Unsupported cases

### `local_inference`

- `local_inference-P01` (positive): candidate_result_incomplete
- `local_inference-P02` (positive): candidate_result_incomplete
- `local_inference-P03` (positive): candidate_result_incomplete
- `local_inference-P04` (positive): candidate_result_incomplete
- `local_inference-P05` (positive): candidate_result_incomplete
- `local_inference-P06` (positive): candidate_result_incomplete
- `local_inference-P07` (positive): candidate_result_incomplete
- `local_inference-P08` (positive): candidate_result_incomplete
- `local_inference-P09` (positive): candidate_result_incomplete
- `local_inference-P10` (positive): candidate_result_incomplete
- `local_inference-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `local_inference-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `local_inference-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `local_inference-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `local_inference-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `local_inference-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `local_inference-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `local_inference-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `local_inference-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `local_inference-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `cost_performance`

- `cost_performance-P01` (positive): candidate_result_incomplete
- `cost_performance-P02` (positive): candidate_result_incomplete
- `cost_performance-P03` (positive): candidate_result_incomplete
- `cost_performance-P04` (positive): candidate_result_incomplete
- `cost_performance-P05` (positive): candidate_result_incomplete
- `cost_performance-P06` (positive): candidate_result_incomplete
- `cost_performance-P07` (positive): candidate_result_incomplete
- `cost_performance-P08` (positive): candidate_result_incomplete
- `cost_performance-P09` (positive): candidate_result_incomplete
- `cost_performance-P10` (positive): candidate_result_incomplete
- `cost_performance-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `cost_performance-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `cost_performance-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `cost_performance-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `cost_performance-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `cost_performance-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `cost_performance-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `cost_performance-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `cost_performance-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `cost_performance-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `model_distillation`

- `model_distillation-P01` (positive): candidate_result_incomplete
- `model_distillation-P02` (positive): candidate_result_incomplete
- `model_distillation-P03` (positive): candidate_result_incomplete
- `model_distillation-P04` (positive): candidate_result_incomplete
- `model_distillation-P05` (positive): candidate_result_incomplete
- `model_distillation-P06` (positive): candidate_result_incomplete
- `model_distillation-P07` (positive): candidate_result_incomplete
- `model_distillation-P08` (positive): candidate_result_incomplete
- `model_distillation-P09` (positive): candidate_result_incomplete
- `model_distillation-P10` (positive): candidate_result_incomplete
- `model_distillation-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `model_distillation-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `model_distillation-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `model_distillation-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `model_distillation-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `model_distillation-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `model_distillation-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `model_distillation-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `model_distillation-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `model_distillation-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `evals_benchmarks`

- `evals_benchmarks-P01` (positive): candidate_result_incomplete
- `evals_benchmarks-P02` (positive): candidate_result_incomplete
- `evals_benchmarks-P03` (positive): candidate_result_incomplete
- `evals_benchmarks-P04` (positive): candidate_result_incomplete
- `evals_benchmarks-P05` (positive): candidate_result_incomplete
- `evals_benchmarks-P06` (positive): candidate_result_incomplete
- `evals_benchmarks-P07` (positive): candidate_result_incomplete
- `evals_benchmarks-P08` (positive): candidate_result_incomplete
- `evals_benchmarks-P09` (positive): candidate_result_incomplete
- `evals_benchmarks-P10` (positive): candidate_result_incomplete
- `evals_benchmarks-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `evals_benchmarks-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `evals_benchmarks-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `evals_benchmarks-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `evals_benchmarks-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `evals_benchmarks-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `evals_benchmarks-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `evals_benchmarks-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `evals_benchmarks-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `evals_benchmarks-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `openness_license`

- `openness_license-P01` (positive): candidate_result_incomplete
- `openness_license-P02` (positive): candidate_result_incomplete
- `openness_license-P03` (positive): candidate_result_incomplete
- `openness_license-P04` (positive): candidate_result_incomplete
- `openness_license-P05` (positive): candidate_result_incomplete
- `openness_license-P06` (positive): candidate_result_incomplete
- `openness_license-P07` (positive): candidate_result_incomplete
- `openness_license-P08` (positive): candidate_result_incomplete
- `openness_license-P09` (positive): candidate_result_incomplete
- `openness_license-P10` (positive): candidate_result_incomplete
- `openness_license-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `openness_license-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `openness_license-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `openness_license-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `openness_license-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `openness_license-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `openness_license-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `openness_license-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `openness_license-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `openness_license-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `agents_tools`

- `agents_tools-P01` (positive): candidate_result_incomplete
- `agents_tools-P02` (positive): candidate_result_incomplete
- `agents_tools-P03` (positive): candidate_result_incomplete
- `agents_tools-P04` (positive): candidate_result_incomplete
- `agents_tools-P05` (positive): candidate_result_incomplete
- `agents_tools-P06` (positive): candidate_result_incomplete
- `agents_tools-P07` (positive): candidate_result_incomplete
- `agents_tools-P08` (positive): candidate_result_incomplete
- `agents_tools-P09` (positive): candidate_result_incomplete
- `agents_tools-P10` (positive): candidate_result_incomplete
- `agents_tools-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `agents_tools-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `agents_tools-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `agents_tools-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `agents_tools-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `agents_tools-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `agents_tools-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `agents_tools-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `agents_tools-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `agents_tools-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `api_developer_surface`

- `api_developer_surface-P01` (positive): candidate_result_incomplete
- `api_developer_surface-P02` (positive): candidate_result_incomplete
- `api_developer_surface-P03` (positive): candidate_result_incomplete
- `api_developer_surface-P04` (positive): candidate_result_incomplete
- `api_developer_surface-P05` (positive): candidate_result_incomplete
- `api_developer_surface-P06` (positive): candidate_result_incomplete
- `api_developer_surface-P07` (positive): candidate_result_incomplete
- `api_developer_surface-P08` (positive): candidate_result_incomplete
- `api_developer_surface-P09` (positive): candidate_result_incomplete
- `api_developer_surface-P10` (positive): candidate_result_incomplete
- `api_developer_surface-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `api_developer_surface-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `api_developer_surface-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `api_developer_surface-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `api_developer_surface-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `api_developer_surface-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `api_developer_surface-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `api_developer_surface-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `api_developer_surface-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `api_developer_surface-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `news_reporting`

- `news_reporting-P01` (positive): candidate_result_incomplete
- `news_reporting-P02` (positive): candidate_result_incomplete
- `news_reporting-P03` (positive): candidate_result_incomplete
- `news_reporting-P04` (positive): candidate_result_incomplete
- `news_reporting-P05` (positive): candidate_result_incomplete
- `news_reporting-P06` (positive): candidate_result_incomplete
- `news_reporting-P07` (positive): candidate_result_incomplete
- `news_reporting-P08` (positive): candidate_result_incomplete
- `news_reporting-P09` (positive): candidate_result_incomplete
- `news_reporting-P10` (positive): candidate_result_incomplete
- `news_reporting-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `news_reporting-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `news_reporting-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `news_reporting-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `news_reporting-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `news_reporting-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `news_reporting-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `news_reporting-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `news_reporting-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `news_reporting-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `investigate_claim`

- `investigate_claim-P01` (positive): candidate_result_incomplete
- `investigate_claim-P02` (positive): candidate_result_incomplete
- `investigate_claim-P03` (positive): candidate_result_incomplete
- `investigate_claim-P04` (positive): candidate_result_incomplete
- `investigate_claim-P05` (positive): candidate_result_incomplete
- `investigate_claim-P06` (positive): candidate_result_incomplete
- `investigate_claim-P07` (positive): candidate_result_incomplete
- `investigate_claim-P08` (positive): candidate_result_incomplete
- `investigate_claim-P09` (positive): candidate_result_incomplete
- `investigate_claim-P10` (positive): candidate_result_incomplete
- `investigate_claim-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `investigate_claim-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `investigate_claim-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `investigate_claim-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `investigate_claim-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `investigate_claim-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `investigate_claim-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `investigate_claim-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `investigate_claim-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `investigate_claim-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `geopolitical`

- `geopolitical-P01` (positive): candidate_result_incomplete
- `geopolitical-P02` (positive): candidate_result_incomplete
- `geopolitical-P03` (positive): candidate_result_incomplete
- `geopolitical-P04` (positive): candidate_result_incomplete
- `geopolitical-P05` (positive): candidate_result_incomplete
- `geopolitical-P06` (positive): candidate_result_incomplete
- `geopolitical-P07` (positive): candidate_result_incomplete
- `geopolitical-P08` (positive): candidate_result_incomplete
- `geopolitical-P09` (positive): candidate_result_incomplete
- `geopolitical-P10` (positive): candidate_result_incomplete
- `geopolitical-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `geopolitical-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `geopolitical-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `geopolitical-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `geopolitical-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `geopolitical-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `geopolitical-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `geopolitical-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `geopolitical-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `geopolitical-N10` (matched_negative_or_boundary): candidate_result_incomplete

### `untracked_brand_promotions`

- `untracked_brand_promotions-P01` (positive): candidate_result_incomplete
- `untracked_brand_promotions-P02` (positive): candidate_result_incomplete
- `untracked_brand_promotions-P03` (positive): candidate_result_incomplete
- `untracked_brand_promotions-P04` (positive): candidate_result_incomplete
- `untracked_brand_promotions-P05` (positive): candidate_result_incomplete
- `untracked_brand_promotions-P06` (positive): candidate_result_incomplete
- `untracked_brand_promotions-P07` (positive): candidate_result_incomplete
- `untracked_brand_promotions-P08` (positive): candidate_result_incomplete
- `untracked_brand_promotions-P09` (positive): candidate_result_incomplete
- `untracked_brand_promotions-P10` (positive): candidate_result_incomplete
- `untracked_brand_promotions-N01` (matched_negative_or_boundary): candidate_result_incomplete
- `untracked_brand_promotions-N02` (matched_negative_or_boundary): candidate_result_incomplete
- `untracked_brand_promotions-N03` (matched_negative_or_boundary): candidate_result_incomplete
- `untracked_brand_promotions-N04` (matched_negative_or_boundary): candidate_result_incomplete
- `untracked_brand_promotions-N05` (matched_negative_or_boundary): candidate_result_incomplete
- `untracked_brand_promotions-N06` (matched_negative_or_boundary): candidate_result_incomplete
- `untracked_brand_promotions-N07` (matched_negative_or_boundary): candidate_result_incomplete
- `untracked_brand_promotions-N08` (matched_negative_or_boundary): candidate_result_incomplete
- `untracked_brand_promotions-N09` (matched_negative_or_boundary): candidate_result_incomplete
- `untracked_brand_promotions-N10` (matched_negative_or_boundary): candidate_result_incomplete
