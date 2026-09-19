# 0731 classifier: per-post validation and complete coverage

The selected model remains cloud DeepSeek 0731 on OpenRouter, pinned to DeepInfra FP8. This work recovered complete valid output without adding a third call or changing the model. Semantic acceptance has **not** passed; staging classifier activation remains disabled.

## What failed and what changed

The first shared-relevance prompt run returned all six responses, but five content decisions combined `other` with a specific type. The parser rejected both entire 20-post batches. Only four posts survived the final merge. The plan requires independent posts to survive another post's malformed answer.

The selected fixed-slot adapter now validates the complete response envelope first, then validates values per post. Every attributed brand within a post must still pass together. Missing/extra slots or fields reject the envelope; unknown labels, invalid values, mixed `other`, and contradictory role results remain rejected. No labels are invented, removed, or repaired. The legacy transport is unchanged.

Replaying the saved responses after this correction recovered 38/45 posts without provider calls. Five invalid type combinations and two conflicting role results remained pending. The earlier relevance paragraph was unsuccessful and is retained as failed evidence, not the selected prompt.

The final bounded retry retains the original R123 base prompts and uses a shorter shared instruction clarifying target-brand evidence, exclusive `other`, and `none` versus null. Its role/merge versions are `stage1-content-0731-v4`, `stage1-brand-interpretation-0731-v4`, and `stage1-two-role-merge-0731-v4`. These are prompt revisions of the existing taxonomy-v3 contract, not the planned taxonomy-v4 expansion.

## Results

| Run | Valid posts | Original-reference field matches | Billed USD | Wall time |
|---|---:|---:|---:|---:|
| Historical R123 | 45/45 | 180/270 | See original exhibit | See original exhibit |
| Restored R123 runtime | 43/45 | 178/270 | 0.00291204 | 21.279 s |
| First shared rule, original parser | 4/45 | 9/270 | 0.00298062 | 12.820 s |
| Same responses, corrected parser (offline) | 38/45 | 155/270 | 0 additional | Offline replay |
| Shorter shared rule, corrected parser | 45/45 | 180/270 | 0.00280908 | 19.948 s |

The retry made six calls in batches of 20/20/5 with at most three transports in parallel and no retries. It used no reasoning tokens. Coverage, bounded spend, and pilot latency checks passed. This is a consumed development cohort; these results are not population accuracy or production-capacity evidence.

| Axis | Historical matches | Latest matches |
|---|---:|---:|
| outcome | 40/45 | 40/45 |
| post_types | 14/45 | 7/45 |
| product_labels | 28/45 | 28/45 |
| sentiment | 21/45 | 29/45 |
| china_nationalism | 37/45 | 37/45 |
| us_nationalism | 40/45 | 39/45 |

Equal aggregate field matches do not imply equal quality. The latest run improved sentiment agreement but reduced exact post-type agreement. Against the original reference, post-type micro-F1 is 0.6705 and product-label micro-F1 is 0.3200; against the owner-amended reference, they are 0.6704 and 0.2857. Both remain below the frozen 0.70 thresholds. The model emitted only seven testimonial and one complaint labels. Against the owner-amended reference it missed 11 testimonials, two ideas/requests, and one each of complaint, bug, and misinformation. The source-bearing per-case inventory is `semantic-failure-inventory.json` in the latest run directory. Ordered array equality in the historical field-match statistic differs from set-based exact-match metrics; neither should be presented as overall accuracy.

## Verification and artifacts

Seven new real-caller regression cases cover invalid values with valid neighboring posts, multi-brand atomicity, and full-envelope rejection. Before the fix, the four value-isolation cases failed and the three envelope cases passed. After the fix, the focused suite passed **78 tests**, including **3 required PostgreSQL tests with zero skips**. Independent review found no actionable parser regression.

Command: `DATABASE_URL=postgresql:///pw_u18_runtime_20260916 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_u18_runtime_0731.py tests/test_u18_two_role_foundation.py tests/test_u18_runtime_0731_acceptance.py tests/test_u18_openrouter_two_role_pilot.py -q --basetemp=/Users/fuchitalee/.cache/pw-u18-0731-v4`

Private source-bearing artifacts:

- Failed shared-rule run: `.context/u18/runtime-0731-shared-relevance-20260916-v1/`
- Offline replay: `.context/u18/0731-shared-relevance-row-isolation-replay-20260916.json`
- Latest frozen requests, endpoint receipt, responses, usage, candidate and scoring: `.context/u18/runtime-0731-relevance-v4-20260916/`

No production/staging configuration, scheduler, or database content changed. The next classifier action must address label quality; more schema-success tests cannot satisfy that gate. Translation/commentary comparisons remain independently authorized diagnostics.
