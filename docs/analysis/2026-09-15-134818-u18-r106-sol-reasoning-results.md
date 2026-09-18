# GPT-5.6 Sol: low versus xhigh reasoning on the classifier

Completed on September 15, 2026. Both settings received the same 45 reviewed posts, full primary prompt, and response schema. Only `reasoning.effort` changed. This is an offline capability experiment; production is unchanged.

`low` achieved post-type F1 0.813 and product-label F1 0.622; `xhigh` achieved 0.735 and 0.571. Extra reasoning used 49,012 tokens versus 1,793, with serial inference time 688.9s versus 65.2s. Higher effort is a model setting, not a guarantee that every answer improves.

**Extra reasoning worsened agreement on this cohort.** Xhigh recovered three additional correct post-type assignments compared with low, but added 25 extra false positives. Product-label recovery stayed at 14/17 while false positives rose from 14 to 18. Low was the better Sol setting in this trial, yet it did not beat DeepSeek across the axes: its post-type score improved slightly while product-label F1 and sentiment agreement declined. Neither Sol arm passes the existing quality requirements, and low costs 22.7 times the repriced off-peak DeepSeek primary. Keep the existing model; this experiment provides no basis for paying more to activate Sol.

## Same-cohort results

F1 balances recovered labels against missing and extra labels; 1.0 is perfect agreement. Complete agreement requires all six measured axes to match. Missing or invalid rows count wrong on every exact-agreement axis. Headline scores use only batches accepted by the complete response validator; diagnostic salvage is stored separately in the JSON.

| Configuration | Valid rows | Post-type F1 | Product-label F1 | Complete agreement | Serial inference | Cost for 45 posts |
|---|---:|---:|---:|---:|---:|---:|
| Saved DeepSeek primary | 45/45 | 0.789 | 0.645 | 13/45 | 15.4s | $0.00600291 |
| Sol low | 45/45 | 0.813 | 0.622 | 9/45 | 65.2s | $0.13616800 |
| Sol xhigh | 45/45 | 0.735 | 0.571 | 4/45 | 688.9s | $0.60989800 |

DeepSeek is the saved R101 **primary only**, with no conditional follow-up. Its tokens are repriced at current off-peak rates; peak costs twice as much. Sol costs are actual returned charges. Sol versus DeepSeek also changes model, provider, schema enforcement, and supported settings; only low versus xhigh isolates reasoning effort. These single-run latency samples do not establish stable provider speed.

## Exact agreement by axis

| Configuration | Outcome | Post types | Product labels | Sentiment | China nationalism | US nationalism |
|---|---:|---:|---:|---:|---:|---:|
| Saved DeepSeek primary | 42/45 | 20/45 | 34/45 | 30/45 | 38/45 | 41/45 |
| Sol low | 42/45 | 21/45 | 30/45 | 27/45 | 39/45 | 42/45 |
| Sol xhigh | 42/45 | 11/45 | 28/45 | 22/45 | 37/45 | 39/45 |

Predicting no product labels can score well on exact agreement because many posts have none. The positive-label counts below show actual recovery.

## What xhigh fixed or made worse

These are paired counts on the same posts. A fix means low disagreed with the owner reference and xhigh agreed; a regression means the reverse. Two wrong answers can differ without either becoming correct.

| Axis | Fixed by xhigh | Regressed with xhigh | Wrong under both |
|---|---:|---:|---:|
| Outcome | 0 | 0 | 3 |
| Post types | 0 | 10 | 24 |
| Product labels | 2 | 4 | 13 |
| Sentiment | 2 | 7 | 16 |
| China nationalism | 0 | 2 | 6 |
| US nationalism | 0 | 3 | 3 |

All changed cases, exact reference labels, both model outputs, and fixed/regressed case IDs are in the detailed JSON. There are 29 cases with at least one changed axis.

## Tokens and billed reasoning

| Effort | Input | Cache reads | Cache writes | Reasoning | Other completion | Total completion | Billed cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| low | 28,825 | 0 | 28,816 | 1,793 | 4,618 | 6,411 | $0.13616800 |
| xhigh | 28,825 | 0 | 28,816 | 49,012 | 4,772 | 53,784 | $0.60989800 |

Reasoning tokens are already included in total completion tokens and billed output. They must not be added twice. “Other completion” subtracts reported reasoning from completion; it is not a claim that every remaining token is visible text. Reasoning traces were excluded from the returned message, but the usage counts were retained.

The standard OpenAI route on OpenRouter advertised a 50% discount: $2 input, $10 output, $0.20 cache read, and $2.50 cache write per million tokens. Dispatch-time receipts are retained. Normal-price sensitivity doubles the same measured charges; it is not a second billed run. The zero-cache sensitivity prices all input at the $2 ordinary input rate and all completion at $10, excluding cache-write premiums. In this run both arms had exactly the same input usage: 28,825 tokens, zero cache reads, and 28,816 cache writes. Their input charges were identical; the observed billed difference is entirely additional completion tokens. Future cache behavior may differ.

| Effort | Billed + 5.5% fee sensitivity | Zero-cache ordinary rate | Same-cache normal-price estimate | Cost / off-peak DeepSeek | Cost / peak DeepSeek |
|---|---:|---:|---:|---:|---:|
| low | $0.14365724 | $0.12176000 | $0.27233600 | 22.68× | 11.34× |
| xhigh | $0.64344239 | $0.59549000 | $1.21979600 | 101.60× | 50.80× |

Total reported inference: **$0.746066** across **6 calls**, or **$0.787099630** including fee sensitivity. Billing reconciliation: **reconciled**. The frozen reservation including fees was $2.4344494250 under a $2.50 ceiling. Ratios compare raw returned Sol charges with repriced DeepSeek; the fee-adjusted ratios are also retained in JSON.

These are classifier-only cohort costs. They do not establish the $150/month budget for translation, summaries, and all other LLM work, or a tenfold cheaper replacement. Coverage expansion would require an actual volume forecast. No automatic replacement is authorized by this result.

## Recovery by label

Each result cell is correct positives / extra positives / missed positives. Support is the owner's positive count. No positive examples means sensitivity is unmeasured, even if a model emits no false positives.

| Label | Support | DeepSeek TP/FP/FN | Sol low TP/FP/FN | Sol xhigh TP/FP/FN |
|---|---:|---:|---:|---:|
| post_types: `releases_updates` | 8 | 6/1/2 | 6/2/2 | 7/8/1 |
| post_types: `hands_on_usage` | 9 | 6/1/3 | 6/3/3 | 7/5/2 |
| post_types: `results_evaluations` | 16 | 9/1/7 | 12/3/4 | 12/6/4 |
| post_types: `questions_requests` | 4 | 4/0/0 | 3/0/1 | 3/1/1 |
| post_types: `advertising_marketing` | 5 | 4/0/1 | 4/0/1 | 5/4/0 |
| post_types: `events` | 3 | 1/0/2 | 3/0/0 | 3/0/0 |
| post_types: `opportunities` | 5 | 2/0/3 | 4/0/1 | 3/0/2 |
| post_types: `job_listings` | 1 | 1/0/0 | 1/0/0 | 0/0/1 |
| post_types: `personnel_changes` | 0 | 0/0/0 | 0/0/0 | 0/0/0 |
| post_types: `opinions_reactions` | 26 | 23/6/3 | 25/5/1 | 25/9/1 |
| post_types: `research_explanations` | 14 | 10/1/4 | 10/3/4 | 12/5/2 |
| post_types: `business_finance` | 4 | 3/1/1 | 2/0/2 | 2/3/2 |
| post_types: `other` | 0 | 0/0/0 | 0/0/0 | 0/0/0 |
| product_labels: `bug` | 0 | 0/0/0 | 0/1/0 | 0/1/0 |
| product_labels: `complaint` | 1 | 1/0/0 | 1/4/0 | 1/5/0 |
| product_labels: `testimonial` | 13 | 7/3/6 | 12/7/1 | 12/11/1 |
| product_labels: `ideas_requests` | 2 | 1/1/1 | 0/0/2 | 0/0/2 |
| product_labels: `misinformation` | 1 | 1/0/0 | 1/2/0 | 1/1/0 |

## Existing quality requirements

All frozen release requirements are still enforced. This table reports the existing R98 comparison thresholds, which use their own saved composite baseline; the DeepSeek primary-only table above is a different comparison. Beating that primary alone does not imply all release requirements pass.

| Effort | Requirement | Result | Recorded details |
|---|---|---|---|
| low | improvement composite | Fail | Observed 0.744; minimum 0.864 |
| low | axis regression | Fail | 0/6 measured checks pass; unsupported labels excluded |
| low | per label regression | Fail | 7/15 measured checks pass; unsupported labels excluded |
| xhigh | improvement composite | Fail | Observed 0.663; minimum 0.864 |
| xhigh | axis regression | Fail | 0/6 measured checks pass; unsupported labels excluded |
| xhigh | per label regression | Fail | 5/15 measured checks pass; unsupported labels excluded |

The literal gate counts above have a pre-existing precision caveat: the frozen baseline rates are rounded to six decimals, while one permitted case of regression is subtracted as exactly 1/45. For low, outcome and US agreement are 42/45 (0.933333333), just below the literal minimum 0.933333778; China agreement is 39/45 (0.866666667), just below 0.866666778. Xhigh has the same outcome edge. These are sub-millionth rounding differences, not extra incorrect cases. The frozen gate outputs are preserved unchanged and the affected comparisons are listed in JSON. This does not change either arm's overall failure: substantial post-type, product-label, sentiment, composite, and per-label failures remain. A future scorer correction can use exact counts without buying new inference.

## Execution and limits

- API model `openai/gpt-5.6-sol`, dated response `openai/gpt-5.6-sol-20260709`, pinned standard `openai` route. No substitution with the agent-hosted Sol model, Sol Pro, Flex, or Fast.
- Full R101 primary prompt (13,944 characters), original IDs and evidence, strict JSON schema, three 20/20/5 batches per effort. The compact NeMo prompt was not used.
- Only `reasoning.effort` differs across arms. `temperature` and `top_p` are omitted because this route does not support them. Reasoning is enabled natively, with `exclude: true` for returned traces.
- 28,000 completion tokens per request include reasoning and final output. Timeout 300 seconds, one in flight, no retries, repair calls, tools, fallback providers, or extra LLM judges.
- Order: low batch 0, xhigh batch 0, xhigh batch 1, low batch 1, low batch 2, xhigh batch 2. This varies which arm goes first, but does not eliminate cache or provider-load effects.
- Raw responses and charges were saved before parsing. No owner answers entered requests. Public-post transport uses the already recorded OpenAI no-training policy with retention possible; this is not a zero-retention claim.
- Same consumed 45-case owner reference, 15 posts per language (English, Japanese, simplified Chinese). Results are development-set agreement, not unseen or representative-production accuracy. Per-language metrics are in JSON.
- Current-v3 axes only. Future Audience Topics, Geopolitical revisions, new affiliation evidence, media access, and the unreviewed second packet are excluded. There is one job positive, no personnel positives, and no bug positives. Unsanctioned outputs lack a complete owner reference for quantitative scoring.
- The original human review remains complete. This test adds no human-review gate and does not waive quality or budget requirements.

## Evidence

- [Frozen experiment contract](2026-09-15-134818-u18-r106-sol-reasoning-contract.json), SHA-256 `efe2f11fa8903b88b37494734e8e55f8bffbefa6083a351b85db27e525083eda`.
- [Detailed results and paired case changes](2026-09-15-134818-u18-r106-sol-reasoning-results.json).
- Exact requests, source hashes, provider receipts, raw responses, measurements, and billing reconciliation: `.context/u18/sol-reasoning-r106-v1/`.
- Implementation: `scripts/u18_sol_reasoning_pilot.py`. Twelve focused local tests passed, with zero required-test skips or errors; no production code was changed.
- [OpenAI Sol model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-sol) lists reasoning settings; the [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) explains billed reasoning and output-token allowances.
- [OpenRouter Sol pricing](https://openrouter.ai/openai/gpt-5.6-sol) and [reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) support the route and parameter choices. Dispatch receipts, rather than future page contents, preserve this experiment's prices.
