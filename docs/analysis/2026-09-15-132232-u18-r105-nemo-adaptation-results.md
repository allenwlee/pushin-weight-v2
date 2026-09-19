# NeMo adaptation trial: classification quality, time, and cost

**The adaptation fixed output validity, but NeMo still fails the classification requirements.** All four compact variants returned 45/45 valid post-brand rows. The strongest measured label scores came from five-post batches: post-type F1 0.420 and product-label F1 0.261, versus the saved DeepSeek primary's 0.789 and 0.645. No configuration passed the existing quality gates. Retain DeepSeek; the unchanged-prompt failure was not NeMo's best attainable result, but this adaptation still does not justify replacement.

The compact 20-post DekaLLM configuration cost 10.92 times less than off-peak DeepSeek after the 5.5% OpenRouter fee, and 21.84 times less than peak. The slightly more accurate five-post configuration cost only 8.22 times less off-peak (16.44 times at peak). Some output-token savings reflect omitted classifications; a valid-format response is not a quality-approved inference. This experiment does not establish the $150/month budget for the whole LLM pipeline.

In the five-post variant, NeMo recovered 3/17 expected positive product-label assignments, missed all 3 events and the single job listing, and returned context_missing for 12 posts the owner could classify. It recovered only 1/14 research/explanation assignments. The temperature-0.3 run and the DeepInfra run scored worse than the compact DekaLLM baseline. Failures occurred in all three tested languages.

The reserved singleton diagnostic was not run because all nine five-post batches passed the frozen validity trigger. Single-post semantic accuracy remains unmeasured. The completed owner review remains the only human review; this bounded trial is closed without activating a model or changing production.

Status: main comparisons complete. This is an offline inference experiment on the same 45 owner-reviewed posts. Production is unchanged.

The experiment tests whether NeMo benefits from adapting the DeepSeek-developed request. No model weights were trained or modified by this trial. All source text/context and current-v3 definitions are retained; the compact prompt reduces instructions from 13,944 to 7,667 characters (45%). The exact compact wording is attached for review. Results measure agreement with the already-consumed owner reference, not unseen accuracy.

## Measured comparison

Label F1 balances correct labels against missing and extra labels. These headline scores use only batches that pass the complete response contract; all missing or rejected rows remain failures. Individually valid rows in rejected batches are a separate diagnostic in the JSON artifact. Strict validity alone does not mean the labels are correct.

| Configuration | Strictly accepted rows | Post-type F1 | Product-label F1 | Serial inference time | Inference cost |
|---|---:|---:|---:|---:|---:|
| Original NeMo, JSON mode | 0/45 | — | — | 268.0s | $0.00081478 |
| Saved DeepSeek primary | 45/45 | 0.789 | 0.645 | 15.4s | $0.00600291 off-peak |
| schema_20 | 5/45 | 0.040 | 0.000 | 136.9s | $0.00073126 |
| compact_20 | 45/45 | 0.382 | 0.182 | 72.3s | $0.00052095 |
| compact_5 | 45/45 | 0.420 | 0.261 | 91.5s | $0.00069237 |
| temperature_03 | 45/45 | 0.364 | 0.100 | 108.1s | $0.00052038 |
| deepinfra_20 | 45/45 | 0.305 | 0.000 | 75.8s | $0.00054348 |

The DeepSeek cost reprices its saved usage at current off-peak rates; peak is twice that amount. Every NeMo dollar is the provider's returned billed charge, including failed benchmark attempts. No retry or model-based repair was used. A six-row singleton diagnostic, when present, is a different denominator and cannot be ranked against the full 45-row tests.

## What changed in each configuration

- `schema_20`: same original full prompt, source envelope, 20/20/5 batches, temperature 0, output allowance, and DekaLLM route; only JSON mode changes to a strict JSON Schema request.
- `compact_20`: shorter equivalent instructions, short IDs, and one output object per post-brand pair. This bundle changes prompt and representation together; it does not isolate their individual contributions. Code restores only original IDs/brand identifiers, never missing labels or scalar values.
- `compact_5`: the same compact instructions, schema design, and temperature, with nine five-post batches. Output allowance is 1,800 per small batch, versus 6,000 per large batch.
- `temperature_03`: the compact 20/20/5 requests at temperature 0.3 instead of 0.
- `deepinfra_20`: the compact 20/20/5 requests on DeepInfra instead of DekaLLM; same NeMo model and FP8 precision.
- `singleton_diagnostic`: six fixed source-selected posts, two per language, individually classified only if five-post batches remain invalid.

Schema constraints specify keys, enums, and basic shapes. Cross-field rules such as `other` being exclusive and `context_missing` requiring empty arrays still pass through the unchanged semantic validator. Thus a schema-shaped response may still fail our contract or have wrong labels.

## Exact agreement across axes

| Configuration | Outcome | Post types | Product labels | Sentiment | China nationalism | US nationalism |
|---|---:|---:|---:|---:|---:|---:|
| Saved DeepSeek primary | 42/45 | 20/45 | 34/45 | 30/45 | 38/45 | 41/45 |
| schema_20 | 3/45 | 0/45 | 3/45 | 3/45 | 4/45 | 4/45 |
| compact_20 | 33/45 | 6/45 | 27/45 | 19/45 | 4/45 | 5/45 |
| compact_5 | 30/45 | 6/45 | 28/45 | 18/45 | 10/45 | 11/45 |
| temperature_03 | 33/45 | 6/45 | 27/45 | 20/45 | 5/45 | 5/45 |
| deepinfra_20 | 29/45 | 4/45 | 26/45 | 13/45 | 4/45 | 5/45 |

Product-label exact agreement can look reasonable by predicting empty labels on many posts. Product-label F1 and the per-label true/false positives in the JSON artifact are necessary to assess whether testimonials, requests, complaints, and review flags are actually recovered.

## Execution and limits

- **schema_20:** 1/3 complete valid batches; 9 individually valid rows. Two 20-row batches each contained 18 invalid classifications; their independent valid rows are diagnostic only.
- **compact_20:** 3/3 complete valid batches; 45 individually valid rows. All requests passed the output contract.
- **compact_5:** 9/9 complete valid batches; 45 individually valid rows. All requests passed the output contract.
- **temperature_03:** 3/3 complete valid batches; 45 individually valid rows. All requests passed the output contract.
- **deepinfra_20:** 3/3 complete valid batches; 45 individually valid rows. All requests passed the output contract.

Total billed inference spending: **$0.003008445** across **21** attempts, matching the settled key-usage delta exactly. The entire frozen matrix reserves $0.014582723 beneath a $0.10 ceiling. One call at a time; no retries, fallback providers, extra judges, training, database writes, or production changes. Time samples are individual runs, not stable provider speed estimates.

The owner review remains complete. This cohort contains one job listing, no personnel changes, and no bug positives, so this test cannot establish accuracy for those classes. Proposed Audience Topics and Geopolitical revisions are outside the frozen current-v3 comparison. R101 omitted author affiliations and this adaptation deliberately preserves its evidence; any later affiliation experiment must be identified separately.

## Evidence

- [Frozen contract](2026-09-15-132232-u18-r105-nemo-adaptation-contract.json), SHA-256 `5466989f6da3a55c47da43377cdcce91d1d4b1ac2e37f9136698b7d4fc21f033`.
- [Machine-readable results](2026-09-15-132232-u18-r105-nemo-adaptation-results.json), including every axis, per-label support/TP/FP/FN, owner-reference differences, validity, and cost ratios.
- [Compact prompt](2026-09-15-132232-u18-r105-nemo-adaptation-compact-prompt.txt).
- Private exact requests, raw responses, provider/price receipts, usage, and ledger: `.context/u18/nemo-adaptation-r105-v1/`.
- Local verification: nine focused tests passed; zero required-test skips/errors. Tests cover raw usage preservation, ID reconstruction, unchanged schema-only payload, rejected illegal semantics, and no credit for absent rows.
- [OpenRouter structured-output documentation](https://openrouter.ai/docs/guides/features/structured-outputs) explains that enforcement differs by endpoint; [Mistral's NeMo card](https://huggingface.co/mistralai/Mistral-Nemo-Instruct-2407) recommends temperature 0.3. Provider prices/policies were verified before dispatch and retained in the private receipts.
