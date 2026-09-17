# Snapshot-only model costs by task

Price source: `../2026-09-17-143812-openrouter-pricing-snapshot/manifest.json`, captured 2026-09-17. All source file hashes verified before analysis. No live price lookups or inference calls. [All 444 catalog entries, computed task costs](all-model-task-costs.csv).

This is a cost screen to identify models worth testing. It is not an intelligence ranking or proof of cost per successful result. Each row is repriced at the SAME observed task token volume, so tokenizer differences, extra reasoning, prompt changes, retries, completeness and actual quality remain unmeasured for untested candidates.

## Workloads

- Classification: 45,512 input and 5,538 output tokens / 40 source posts, two-role 20-post batches, 0731 R116. Includes observed multiple-brand work but is not a per-brand-row denominator.
- Translation: 95,535 input and 51,298 output tokens / 100 source posts, direct 4.1 frozen random-100. Includes all generated target languages; native copies do not add model calls.
- Commentary: 26,747 input and 43,638 output tokens / 96 submitted posts; each response covers three locales. Four pre-call cap rejections excluded. Production demand rate is separate.

Formula: cost per 1,000 task executions = (mean input tokens × input USD/M + mean output tokens × output USD/M) / 1,000. Uncached, base text usage, no reasoning multiplier, funding fees, tax, tool usage or retry costs. Costs are estimates, not actual bills.

## Candidate comparison

All prices USD/M; task cost columns USD per 1,000 posts at the fixed workload.

| Candidate | Input/M | Output/M | Classification | Translation | Commentary |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0731 baseline | 0.06000000 | 0.18000000 | 0.093 | 0.150 | 0.099 |
| Qwen 3.7 Flash | 0.03000000 | 0.13000000 | 0.052 | 0.095 | 0.067 |
| Gemini 2.5 Flash-Lite Flex | 0.05000000 | 0.2000000 | 0.085 | 0.150 | 0.105 |
| Hy-MT2-1.8B | 0.044000000 | 0.177000000 | 0.075 | 0.133 | 0.093 |
| Hy-MT2-7B | 0.074000000 | 0.295000000 | 0.125 | 0.222 | 0.155 |
| GPT-OSS-120B | 0.037000000 | 0.17000000 | 0.066 | 0.123 | 0.088 |
| GPT-5 Nano | 0.05000000 | 0.4000000 | 0.112 | 0.253 | 0.196 |
| 4.1 Flash, off-peak | 0.15000000 | 0.6000000 | 0.254 | 0.451 | 0.315 |

For the three task columns, cheaper does not mean better: some candidates are specialized for just one task. No quality score is inferred from parameter count, vendor descriptions, context window, valid JSON or price.

- **0731 baseline**: Measured baseline; material translation/commentary errors and provider failures.
- **Qwen 3.7 Flash**: First general-purpose trial; quality unknown; prompt must stay below 32K for quoted tier.
- **Gemini 2.5 Flash-Lite Flex**: Second general-purpose trial; quality unknown; Flex latency/availability must pass.
- **Hy-MT2-1.8B**: Translation-only specialist candidate, catalog-described; exact endpoint and language coverage not yet captured.
- **Hy-MT2-7B**: Larger translation specialist alternative; defer until smaller specialist result; endpoint not captured.
- **GPT-OSS-120B**: Reserve classification/commentary trial; reasoning could inflate output; endpoint not captured.
- **GPT-5 Nano**: Reserve input-heavy classification trial; output/reasoning spend unknown; endpoint not captured.
- **4.1 Flash, off-peak**: Quality control was measured via direct API; displayed price here comes exclusively from saved OpenRouter endpoint, not a direct-provider quote.

## Suggested order, not model-selection decisions

1. Qwen 3.7 Flash and Gemini 2.5 Flash-Lite Flex: general-purpose comparison against stored 0731/4.1 controls, with each task scored independently.
2. Hy-MT2-1.8B: translation-only probe if a separately authorized endpoint snapshot and model instructions confirm required language pairs and prompt compatibility. Its existing catalog rate is only a screening quote. Keep unsupported languages on a measured general model rather than silently dropping them.
3. GPT-OSS-120B or GPT-5 Nano: reserve classifier candidates if the first group leaves semantic gaps. Cheap input helps, but hidden reasoning tokens can overturn the visible-output estimate.
4. Hy-MT2-7B: follow only if the smaller translation specialist makes a credible showing or reveals a capacity limit.

Schematron V2 Turbo is NOT prioritized merely for structured outputs: the saved catalog describes HTML-to-JSON extraction, which differs from our contextual multi-label social-post judgment. Prior NeMo/Ling failures remain relevant negatives, but they do not justify excluding every small model or every Qwen model.

## Screening scope and limitations

The CSV preserves all catalog entries, including free offerings, batch services, routers, non-text models and missing prices. The task screen flags only paid, concrete-ID, standard offerings accepting text and returning text alone. A model qualifies separately for a task when its catalog-based estimated cost is at most twice the tested 0731 endpoint cost. This 2× band is an analyst's exploratory screen, NOT an owner-approved spending ceiling or quality floor. A dedicated Flex endpoint can qualify even when its standard catalog row does not.

Do not rank free previews or batch offers as production replacements without separately evaluating their availability, latency and pricing conditions. Missing prices are unknown; zero rates alone are not proof that every usage dimension is free. Threshold and time-of-day overrides remain visible in the original snapshot; base-rate CSV costs require checking applicability.

Endpoint prices are authoritative for a selected route. The 0731 catalog headline is $0.06/$0.12 in this snapshot while our tested DeepInfra endpoint is $0.06/$0.18; silently substituting the headline would understate the tested route's output cost.

For a genuine two-axis cost/quality map, test the shortlist on fixed inputs. Plot separate maps for classification, translation and commentary; quality is presently UNKNOWN for new candidates. Preserve precision/recall and attribution mistakes for classification, fidelity errors for translation, unsupported claims for commentary, and operational failures separately. Exclude configuration failures from claims of semantic inferiority, but include them in usable-result economics.

Total monthly cost = classified posts × classifier unit cost + translated posts × translation unit cost + requested commentary posts × commentary unit cost + other LLM jobs (especially headlines). Do not multiply every post by commentary cost when commentary is on demand. Do not use these normalized costs to claim a verified $150 monthly forecast.

Task-specific screen counts (catalog rows, not proven usable models): {"classification": 66, "translation": 65, "commentary": 64}.
