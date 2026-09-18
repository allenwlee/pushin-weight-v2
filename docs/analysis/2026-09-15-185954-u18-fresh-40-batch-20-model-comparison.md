# U18 Fresh 40: production batch-size comparison

Generated: 2026-09-15T09:59:54.754449+00:00

This rerun uses cases L45-01 through L45-40 as two batches of 20 posts. Cases L45-41 through L45-45 are excluded. Each model still uses two disjoint roles per batch, so each model made four calls. Owner blanks remain excluded from scoring.

## Overall results

| Model | Exact agreement | Matches / reviewed | Cost | Sequential time | Role-parallel estimate | Stability vs prior 15-post run |
|---|---:|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | 68.2% | 225 / 330 | $0.2168 | 133.9s | 77.6s | 85.5% |
| DeepSeek V4.1 Flash | 65.2% | 215 / 330 | $0.0242 peak / $0.0121 off-peak | 23.3s | 11.7s | 92.5% |

On these same 40 cases, changing from 15-post to 20-post batches left Sol's total agreement unchanged at 68.2% (225/330). DeepSeek moved from 64.8% (214/330) to 65.2% (215/330). This run therefore shows no overall quality penalty from the production batch size, although individual answers changed.

Sol cost $0.00542 per post before the OpenRouter fee ($0.00572 including it). DeepSeek cost $0.000606 per post at peak pricing or $0.000303 off-peak. At peak pricing DeepSeek was about 9× cheaper, and its estimated role-parallel processing time was about 6.6× faster.

## Exact agreement by axis

| Axis | Sol | DeepSeek | Reviewed controls |
|---|---:|---:|---:|
| `outcome` | 89.1% (41/46) | 89.1% (41/46) | 46 |
| `sentiment` | 71.1% (27/38) | 52.6% (20/38) | 38 |
| `post_types` | 15.2% (7/46) | 19.6% (9/46) | 46 |
| `product_labels` | 36.8% (7/19) | 78.9% (15/19) | 19 |
| `audience_topics` | 30.8% (8/26) | 26.9% (7/26) | 26 |
| `geopolitical_modes` | 81.0% (34/42) | 76.2% (32/42) | 42 |
| `china_national_stance` | 97.6% (40/41) | 90.2% (37/41) | 41 |
| `us_national_stance` | 90.2% (37/41) | 90.2% (37/41) | 41 |
| `untracked_brand_promotions` | 77.4% (24/31) | 54.8% (17/31) | 31 |

Sol agreed more often on sentiment, audience topics, geopolitical modes, China stance, and untracked-brand promotions. DeepSeek agreed much more often on product labels and slightly more often on exact post-type sets. The models agreed with each other on 335 of 456 total outputs (73.5%), falling to 36.5% for post types and 46.2% for product labels, so the model choice remains material on the two main multi-label axes.

## Multi-label diagnosis

Exact-set scoring is intentionally strict. The label-level view below shows whether a model more often omits owner-selected labels or adds labels the owner did not select.

| Axis | Model | Label recall | Label precision | Missing labels | Extra labels |
|---|---|---:|---:|---:|---:|
| Post types | Sol | 71.6% | 58.1% | 27 | 49 |
| Post types | DeepSeek | 58.9% | 64.4% | 39 | 31 |
| Product labels | Sol | 68.4% | 50.0% | 6 | 13 |
| Product labels | DeepSeek | 78.9% | 78.9% | 4 | 4 |
| Audience topics | Sol | 58.7% | 55.1% | 19 | 22 |
| Audience topics | DeepSeek | 47.8% | 59.5% | 24 | 15 |

Sol found more of the owner-selected post types and audience topics, but also assigned more additional labels. Because the owner said some lower checkbox selections may be unfinished, those extras require adjudication and should not automatically be treated as model errors.

## Batch-size sensitivity

This compares each model’s new 20-post outputs with its own earlier 15-post outputs for the same first 40 cases. A change is stochastic or batch-context sensitivity; it is not automatically an error.

| Axis | Sol stability | DeepSeek stability |
|---|---:|---:|
| `outcome` | 94.2% (49/52) | 98.1% (51/52) |
| `sentiment` | 86.5% (45/52) | 86.5% (45/52) |
| `post_types` | 59.6% (31/52) | 75.0% (39/52) |
| `product_labels` | 78.8% (41/52) | 98.1% (51/52) |
| `audience_topics` | 71.2% (37/52) | 82.7% (43/52) |
| `geopolitical_modes` | 94.2% (49/52) | 100.0% (52/52) |
| `china_national_stance` | 100.0% (52/52) | 94.2% (49/52) |
| `us_national_stance` | 100.0% (52/52) | 100.0% (52/52) |
| `untracked_brand_promotions` | 85.0% (34/40) | 100.0% (40/40) |

## Execution notes

- DeepSeek semantic invariant issues: 0.
- Both role calls were measured sequentially for clean per-call timing; the role-parallel estimate sums the slower call in each batch.
- Exact agreement requires an entire multi-label set to match; one omitted or extra label makes that field different.
- This challenge set and incomplete owner review cannot estimate live production accuracy.
