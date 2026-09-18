# U18 R104: NeMo and Ling against incumbent DeepSeek V4.1 Flash

Neither candidate passes as a replacement using the unchanged full primary prompt. NeMo failed the output contract in all three batches. Ling was close to DeepSeek in elapsed inference time, but missed every positive product-label assignment and most results/evaluation cases. Both models were actually invoked; these are output and classification failures, not blocked API trials.

The owner target is ten times lower cost per inference, with $150/month for all LLM spending. The measured token-price savings do not establish that target for completed, usable classifications.

## Same workload, measured results

The test reused R101's original 45 ordered public-X packets, 13,944-character full primary prompt, 20/20/5 batch sizes, and current-v3 taxonomy. The saved R101 primary responses are the incumbent Flash control; its conditional follow-up was excluded. Each alternative first received a tiny JSON/route smoke and then the three benchmark requests. There were no retries, repairs, provider fallbacks, extra classifier passes, or production changes.

| Measure | Incumbent Flash control | Mistral NeMo / DekaLLM | Ling 3.0 Flash / Novita |
|---|---:|---:|---:|
| Fully valid batches | 3/3 | 0/3 | 2/3 |
| Rows accepted under strict batch validation | 45/45 | 0/45 | 25/45 |
| Individually valid rows, diagnostic only | 45/45 | 3/45 | 44/45 |
| Post-type exact agreement, invalid rows wrong | 20/45 | 1/45 | 10/45 |
| Product-label exact agreement, invalid rows wrong | 34/45 | 2/45 | 25/45 |
| Post-type F1 | 0.789 | Not usable as classifier output | 0.564 |
| Product-label F1 | 0.645 | Not usable as classifier output | 0.000 |
| Sentiment correct | 30/45 | 1/45 | 24/45 |
| China / US nationalism correct | 38/45; 41/45 | 1/45; 1/45 | 5/45; 4/45 |
| Sum of three inference durations | 15.369s | 267.959s | 18.768s |
| Output tokens | 4,824 | 9,169 | 5,457 |
| Cost for three attempted benchmark calls | $0.00600291 off-peak / $0.01200582 peak | $0.00081478 | $0.00085355 |

Individual valid rows in an invalid batch are retained only for diagnosis, not treated as published results. Exact agreement credits no missing row as a correct empty answer. The inherited scorer did credit some missing rows that way; this report recomputes those exact metrics while leaving frozen artifacts intact. F1 is the score balancing correct labels against missed and extra labels; empty product-label predictions can get moderate exact agreement because many reference posts correctly have no label, even while positive-label F1 is zero.

## What failed

**NeMo:** First batch returned 18 of 20 rows. Sixteen contained literal string `"null"`, `other` alongside specific post types, and flags at the wrong level. The second batch reached 6,000 output tokens with unfinished JSON, omitted the required tweet IDs, and repeated expansive label sets. The final five-row batch contained only one individually valid row. The output ceiling was reached once; simply raising it would not repair missing identities, illegal values, or unsupported label assignments. Batch durations were 142.661, 89.746, and 35.552 seconds.

**Ling:** All three responses were complete JSON. One row returned brand `qwen` for the requested `minimax`, so its 20-row batch failed strict validation. The other 44 rows were individually valid. It emitted two testimonials, both false positives, and recovered 0 of 17 positive product-label assignments: 13 testimonials, two ideas/requests, one complaint, and one review flag. It found 0/3 events, 1/16 results/evaluations, 3/5 opportunities, and the sole job listing. Its nationalism fields commonly returned null where the reference required `none`. Batch durations were 8.315, 7.572, and 2.881 seconds. Its difficulty therefore includes missing secondary label axes as well as target-brand and post-type errors.

## Cost against the tenfold target

Actual cost for all eight requests, including both smoke calls, was **$0.0016699134**. The settled key-usage delta was $0.001669913, agreeing within rounding. This is below the frozen $0.006311319 conservative reservation. NeMo's smoke cost $4.86E-7; Ling's cost $0.000001092.

Ignoring usability for the moment, the same 45 attempted rows were 7.37 times cheaper on NeMo and 7.03 times cheaper on Ling than off-peak Flash. Against peak Flash they were 14.74 and 14.07 times cheaper. Thus neither provides a durable tenfold raw-cost reduction across both price periods in this unchanged prompt test. The owner’s actual peak/off-peak workload mix still matters.

After a 5.5% OpenRouter credit-purchase fee, the off-peak raw-cost ratios are approximately 6.98 and 6.67. NeMo produced no fully usable batch, so its cost per completed batch is undefined. Including the failed batch's cost, Ling is only 3.91 times cheaper per strictly accepted row than off-peak Flash (7.81 times against peak). No quality-preserving tenfold saving has been demonstrated.

Novita's Ling price includes its advertised 65% promotion. At the corresponding regular rates, the same measured tokens would cost approximately $0.00243872, before fees. Do not budget its promotion as permanent.

DeepSeek usage is repriced at the current [official Flash rates](https://api-docs.deepseek.com/quick_start/pricing/): $0.15/$0.003/$0.60 for uncached input/cache-read/output off-peak, twice those amounts at peak. The R101 requests occurred during peak hours. Model/provider receipts were rechecked before each alternative: [NeMo](https://openrouter.ai/mistralai/mistral-nemo), [Ling](https://openrouter.ai/inclusionai/ling-3.0-flash). The [OpenRouter fee](https://openrouter.ai/docs/faq) is separate from returned inference cost.

## Decision and next useful test

Keep Flash as the incumbent. These results reject a model-only swap with this full prompt, not every architecture using these models. Ling is the more useful next candidate because its API behavior and timing were workable. A bounded, short product-label-only prompt would directly test whether it can recover the missing product signals before investing in a multi-call design. Any such test still needs to demonstrate useful completed-output cost; this result does not start it or waive the existing quality gates.

The original human review remains complete. This consumed 45-case corpus measures agreement with that reference, not unseen accuracy. It contains only one job positive and no personnel or bug positives, so those rare classes remain unmeasured or weakly measured. The new 45-case packet was excluded because owner answers do not yet exist. Audience Topics and the future Geopolitical taxonomy were not part of this current-v3 experiment. Post-level promotional flags are retained in raw output but lack a complete owner reference for quantitative scoring.

## Evidence

- [Frozen contract](2026-09-15-124808-u18-r104-low-cost-primary-contract.json), SHA-256 `2e83bc4b15b499d93e934f48d81125afa5d3644671a05ced746aebbb2e61d4d1`.
- [Machine-readable results](2026-09-15-124808-u18-r104-low-cost-primary-results.json), including per-label true/false positives and false negatives, case-level differences, usage, costs, and latency.
- Private raw requests/responses and endpoint policy snapshots: `.context/u18/low-cost-single-primary-r104-v1/`.
- Verification: six existing primary/parser tests and two new raw-evidence/row-identity tests passed; no required tests skipped. Source hashes and packet/prompt identity were checked before each model run.
