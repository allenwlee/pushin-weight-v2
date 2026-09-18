# U18 V4 Flash 0731: DeepInfra 20-post comparison

The DeepInfra 20-post arm **failed its frozen no-repair contract**. All four calls returned, but the first content call wrapped its JSON in a Markdown fence, and the content calls repeatedly used empty arrays instead of explicit `none` sentinels. This is mainly an output-adapter failure: deterministic representation normalization recovers all 40 rows and raises exact owner agreement from 63.6% to 70.6%.

## Results

| Model and execution | Status | Exact owner agreement | Matches / reviewed | Cost for 40 | Role-parallel time | Semantic issues |
|---|---|---:|---:|---:|---:|---:|
| V4 0731 / DeepInfra / 20-post (raw diagnostic) | failed | 63.6% | 210 / 330 | $0.003933 with fee | 40.2s | 60 |
| V4 0731 / DeepInfra / 20-post (representation-normalized) | diagnostic only | 70.6% | 233 / 330 | $0.003933 with fee | 40.2s | 0 |
| V4 0731 / OpenInference / 5-post | passed shape | 64.8% | 214 / 330 | $0.001775 with fee | 148.4s | 30 |
| V4.1 Flash direct / 20-post | passed shape | 65.2% | 215 / 330 | $0.012118 off-peak / $0.024236 peak | 11.7s | 0 |
| GPT-5.6 Sol / 20-post | passed shape | 68.2% | 225 / 330 | $0.228765 with fee | 77.6s | 0 |

## Agreement by axis

| Axis | 0731 DeepInfra | 0731 OpenInference | V4.1 Flash | Sol |
|---|---:|---:|---:|---:|
| `outcome` | 100.0% (46/46) | 100.0% (46/46) | 89.1% (41/46) | 89.1% (41/46) |
| `sentiment` | 57.9% (22/38) | 63.2% (24/38) | 52.6% (20/38) | 71.1% (27/38) |
| `post_types` | 19.6% (9/46) | 19.6% (9/46) | 19.6% (9/46) | 15.2% (7/46) |
| `product_labels` | 68.4% (13/19) | 68.4% (13/19) | 78.9% (15/19) | 36.8% (7/19) |
| `audience_topics` | 46.2% (12/26) | 38.5% (10/26) | 26.9% (7/26) | 30.8% (8/26) |
| `geopolitical_modes` | 83.3% (35/42) | 71.4% (30/42) | 76.2% (32/42) | 81.0% (34/42) |
| `china_national_stance` | 90.2% (37/41) | 82.9% (34/41) | 90.2% (37/41) | 97.6% (40/41) |
| `us_national_stance` | 90.2% (37/41) | 90.2% (37/41) | 90.2% (37/41) | 90.2% (37/41) |
| `untracked_brand_promotions` | 71.0% (22/31) | 35.5% (11/31) | 54.8% (17/31) | 77.4% (24/31) |

## Multi-label recovery

| Axis | Model | Recall | Precision | Missing | Extra |
|---|---|---:|---:|---:|---:|
| `post_types` | V4 0731 / DeepInfra / 20-post (representation-normalized) | 53.7% | 57.3% | 44 | 38 |
| `post_types` | V4 0731 / OpenInference / 5-post | 55.8% | 58.2% | 42 | 38 |
| `post_types` | V4.1 Flash direct / 20-post | 59.0% | 64.4% | 39 | 31 |
| `post_types` | GPT-5.6 Sol / 20-post | 71.6% | 58.1% | 27 | 49 |
| `product_labels` | V4 0731 / DeepInfra / 20-post (representation-normalized) | 68.4% | 68.4% | 6 | 6 |
| `product_labels` | V4 0731 / OpenInference / 5-post | 79.0% | 71.4% | 4 | 6 |
| `product_labels` | V4.1 Flash direct / 20-post | 79.0% | 79.0% | 4 | 4 |
| `product_labels` | GPT-5.6 Sol / 20-post | 68.4% | 50.0% | 6 | 13 |
| `audience_topics` | V4 0731 / DeepInfra / 20-post (representation-normalized) | 56.5% | 81.2% | 20 | 6 |
| `audience_topics` | V4 0731 / OpenInference / 5-post | 52.2% | 66.7% | 22 | 12 |
| `audience_topics` | V4.1 Flash direct / 20-post | 47.8% | 59.5% | 24 | 15 |
| `audience_topics` | GPT-5.6 Sol / 20-post | 58.7% | 55.1% | 19 | 22 |
| `geopolitical_modes` | V4 0731 / DeepInfra / 20-post (representation-normalized) | 91.5% | 86.0% | 4 | 7 |
| `geopolitical_modes` | V4 0731 / OpenInference / 5-post | 83.0% | 76.5% | 8 | 12 |
| `geopolitical_modes` | V4.1 Flash direct / 20-post | 78.7% | 84.1% | 10 | 7 |
| `geopolitical_modes` | GPT-5.6 Sol / 20-post | 83.0% | 83.0% | 8 | 8 |
| `untracked_brand_promotions` | V4 0731 / DeepInfra / 20-post (representation-normalized) | 64.7% | 71.0% | 12 | 9 |
| `untracked_brand_promotions` | V4 0731 / OpenInference / 5-post | 32.4% | 68.8% | 23 | 5 |
| `untracked_brand_promotions` | V4.1 Flash direct / 20-post | 52.9% | 58.1% | 16 | 13 |
| `untracked_brand_promotions` | GPT-5.6 Sol / 20-post | 73.5% | 80.7% | 9 | 6 |

## What failed

- `1-content` stopped normally but returned its complete object inside a `json` Markdown fence; the official arm therefore fails before semantic scoring.
- Deterministic fence removal recovered 20 rows for diagnosis. Across both content calls, the model emitted 60 empty arrays where the contract requires an explicit sentinel such as `none`.
- Mapping only those representation choices to the explicit sentinels raises agreement to 70.6%. This exceeds the raw V4.1 and Sol scores on the incomplete owner controls, so the weights are not the main failure here.
- The normalized arm's weakest reviewed axis remains post types at 19.6%; normalization improves audience topics to 46.2% and untracked-brand promotions to 71.0%.
- DeepInfra was much faster than the earlier OpenInference route. It cost $0.003933 for 40 posts: about 3.1x cheaper than V4.1 off-peak and 6.2x cheaper at peak, short of the required 10x reduction.
- No retry, label repair, fallback provider, media fetch, or database write occurred.

## Decision

Do not advance V4 Flash 0731 as-is: it fails strict output compliance and the 10x cost target. Its normalized semantic score is strong enough to retain as a fallback candidate if a 3–6x saving becomes acceptable. For the current requirement, test the next cheaper model with the same two-role workload and permit only a declared deterministic output adapter.

## Limits

Owner blanks are excluded, and some selected checkbox sets may be incomplete. This enriched, already-consumed challenge set measures development agreement rather than live prevalence-weighted accuracy.
