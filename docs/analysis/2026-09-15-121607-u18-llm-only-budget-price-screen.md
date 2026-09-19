# U18: $150/month LLM-only budget and current price comparison

Recorded 2026-09-15T12:16:07.960302+09:00. This is a read-only price screen, not a quality test or a production model change.

The owner has set a $150/month total LLM spending target, including classification, translation, Japanese output, headlines, and other model calls. Frontier coverage is expected to increase post volume 2–3 times. TwitterAPI and hosting are outside this calculation. Additional calls are worth exploring only if the model prices create substantial room, ideally approximately a tenfold reduction from DeepSeek V4.1 Flash.

## Finding

Mistral NeMo has paid routes close to the requested price reduction: about 9.5–9.9 times cheaper before OpenRouter credit-purchase fees, using the input/output mixture from R101. The cheapest route is about 9.4 times cheaper after a 5.5% fee. Ling's current promotion is about 7.1 times cheaper before fees; its regular price is only about 2.5 times cheaper. Qwen3.7 Flash is about 4.3 times cheaper. These are fixed-token price comparisons. Different tokenizers, longer answers, reasoning, retries, and fallback models can change the actual savings.

## Current baseline and method

[DeepSeek's current price sheet](https://api-docs.deepseek.com/quick_start/pricing/) identifies `deepseek-flash` as DeepSeek-V4.1-Flash; legacy `deepseek-v4-flash` requests also route there. Per million tokens: off-peak $0.15 uncached input, $0.003 cached input, and $0.60 output; peak prices are twice those amounts. Peak periods are Monday–Friday 01:00–04:00 and 06:00–10:00 UTC. Use these current rates for comparison rather than the older $0.44/$1.32 budget bound in pilot scripts.

R101's three primary requests processed 45 rows with 20,621 uncached input tokens, 5,120 cache-read tokens, and 4,824 output tokens. The pilot used the Anthropic-compatible usage representation, which reports uncached input separately from cache reads. Source: `.context/u18/single-primary-conditional-pilot-r101-v1/result.json`, `measurements` filtered to `stage=primary`.

At current off-peak rates that mixture costs $0.00600291 in DeepSeek inference. This is repricing a stored workload, not a provider invoice; R101's recorded start times were within peak hours. For alternative models the table assumes all 25,741 input tokens are uncached and the same 4,824 output tokens. DeepSeek retains its observed cache benefit; no cache benefit is assumed for alternatives.

| Model / route | Input per 1M | Output per 1M | Cheaper than DS off-peak | After 5.5% OR fee |
|---|---:|---:|---:|---:|
| Mistral NeMo / DekaLLM | $0.018 | $0.03 | 9.87x | 9.36x |
| Mistral NeMo / DeepInfra | $0.019 | $0.03 | 9.47x | 8.98x |
| Ling 3.0 Flash / Novita promotion | $0.021 | $0.063 | 7.11x | 6.74x |
| Ling 3.0 Flash / regular price | $0.06 | $0.18 | 2.49x | 2.36x |
| Qwen3.7 Flash / Alibaba, prompts below 32K | $0.03 | $0.13 | 4.29x | 4.07x |

Prices were read from both the model pages and exact provider endpoint APIs. No additional discount was applied to promotional displayed prices. Sources: [NeMo](https://openrouter.ai/mistralai/mistral-nemo), [Ling](https://openrouter.ai/inclusionai/ling-3.0-flash), [Qwen3.7 Flash](https://openrouter.ai/qwen/qwen3.7-flash), [OpenRouter fees](https://openrouter.ai/docs/faq). Fee examples assume a purchase large enough that the minimum fee is irrelevant. Endpoint JSON snapshots are saved in `.context/u18/llm-budget-price-screen-20260915/`.

Ling/Novita is advertised at 65% off. Its expiration was not established, so a durable budget must also work at the regular rate or have an independently tested alternative. Its endpoint does not advertise `response_format`/`structured_outputs` in the retrieved API capability list. NeMo's DekaLLM and DeepInfra routes advertise structured outputs. Qwen's above-32K prompt tiers cost more than the row shown here. Provider routing and fallback prices must be bounded during a pilot; the same model slug can route to differently priced providers.

## What fits under $150

For a simplified workload entirely moved to a cheaper model:

`new LLM spend = old comparable LLM spend × post-volume growth × token growth per post ÷ effective price reduction`

- $150 × 3 times the posts × 2 times the tokens ÷ 10 times cheaper = $90/month.
- $150 × 3 times the posts × 3 times the tokens ÷ 10 times cheaper = $135/month.
- $150 × 3 times the posts × 2 times the tokens ÷ 3 times cheaper = $300/month.

These are illustrations, not forecasts. If only classification moves, calculate each unchanged LLM component separately and add it to the migrated component. Increasing Japanese translation output and adding audience topics belong in the measured token growth; neither implies a full multiplication of every existing call. A current spend breakdown by classifier, translator, and other LLM operations is still needed before claiming the whole product will fit. The owner's approximately $150 current spend is not a measured current-price baseline.

## Recommended next experiment

Start with NeMo on a pinned paid route because it comes closest to the economic condition. Use the existing owner-reviewed examples to check valid output, missed secondary labels, invented labels, target-brand attribution, language handling, total tokens, and elapsed time. Its much lower price does not establish adequate quality or speed. Published provider throughput is not a substitute for our own end-to-end timing. Do a tiny capability check before a larger frozen evaluation so unsupported API options do not consume the experiment.

If it succeeds, then test simpler specialized calls or conditional routing using its measured cost. If it fails, a 2–4 times discount alone does not justify assuming that tripled coverage plus substantially more tokens will remain within $150. A free model can be an experiment, but free-tier availability and quota should not be the basis of the recurring budget.

## Human time and evaluation data

The existing 45 reviewed posts are useful development evidence; they have already informed prompt changes, so they are not an untouched holdout. Strong-model drafts can supply provisional labels for real database posts, with owner review concentrated on short, uncertain or disputed decisions and some randomly sampled agreements. Provisional model answers do not become human gold. Include hard negatives as well as rare positives; keyword retrieval alone misses cases and produces false positives.

The requested [fresh 45-case packet](2026-09-15-121342-u18-fresh-45-review-packet.md) has now been assembled with verbatim full text, 500-character previews, stored English translations, stored account roles, parent/quote context, and media links. It is a deliberately enriched challenge set with approximate source-language proportions. Personnel positives are still sparse, and these cases cannot establish population-wide rare-class recall. Keep any evaluation slice separate from teacher labeling, training, prompt examples, and prompt selection if it is to be an untouched holdout. This packet does not change the closed status of the owner's original review.
