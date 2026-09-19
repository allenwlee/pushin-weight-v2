# Translation and commentary: larger output allowances

Both models completed all 45 translations after raising the self-imposed output allowance. The incumbent completed all 45 commentary outputs at the larger allowance; cloud 0731 completed 40. These are development results, not activation approval.

The corpus contains 15 English, 15 Chinese, and 15 Japanese source posts, with short/medium/long examples within each language. It is a language-quality test, not a representative production-volume sample. Original source text and stored context were frozen before calls. Translation uses only the original post; commentary also receives available stored context.

## Results

| Task / model | Complete | Calls | Total elapsed | Output tokens | Cost for this run |
|---|---:|---:|---:|---:|---:|
| Translation / incumbent direct DeepSeek | 45/45 | 3 | 194.049 s | 48,011 | $0.057892 estimated |
| Translation / cloud 0731, DeepInfra FP8 | 45/45 | 3 | 794.116 s | 46,796 | $0.008680 reported |
| Commentary / incumbent direct DeepSeek | 45/45 | 45 | 178.021 s | 28,764 | $0.037267 estimated |
| Commentary / cloud 0731, DeepInfra FP8 | 40/45 | 45 | 728.942 s | 26,017 measured | $0.006051 known reported subtotal |

Translation batches were 20/20/5; commentary used one post per call, producing all three locales. Each arm ran serially. Independent arms sometimes overlapped, so these are observed run times, not isolated throughput estimates or production p95 measurements.

The direct API does not supply a billed-cost field. Its estimates use measured uncached input, cache-read input, and output at the documented peak rates of $0.30, $0.006, and $1.20 per million tokens respectively. OpenRouter costs come from response usage; wallet purchase fees are excluded. Two 0731 commentary rate-limit responses had no usage/cost record, so its known subtotal is not claimed as a complete bill. [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/).

For these completed translation runs, 0731 was approximately 6.7 times cheaper before wallet fees and took 4.1 times longer. Do not project monthly cost from this deliberately stratified corpus alone.

## What the limits were doing

The original literal allowance was 650 output tokens per post, or 13,000 for a full batch. Both models reached that limit before finishing the JSON for the first two batches; both initially returned only 5/45 accepted posts. The owner explicitly approved raising this self-imposed ceiling.

The literal caller now scales to 32,768 tokens for 20 posts and 8,192 for five. One incumbent batch used 26,292 tokens in the intermediate run, directly demonstrating why the original allowance was insufficient. Batch size and translation prompt were preserved. The larger allowance is a maximum, not a requested response length.

The first higher-ceiling incumbent run timed out on one batch at the experiment's 60-second socket setting. Raising the experimental literal socket-idle timeout to 180 seconds allowed the full incumbent run to complete. The 0731 translation run completed with its original 60-second socket-idle setting because provider keep-alives can keep a connection open much longer. Its longest call took 526.390 seconds. A socket timeout is **not** a wall-clock deadline; this call exceeded the application's configured 300-second enrichment-attempt budget. No runtime deadline was increased by this experiment.

The original commentary allowance was 1,200 tokens for three locale outputs. Five incumbent results reached that ceiling and failed parsing. Raising the evaluation allowance to 4,000 recovered 45/45. Runtime synthesis configuration remains unchanged at 1,200; this experiment did not activate a different model, provider, or locale lane.

0731's five final commentary failures were different: three `openrouter_response_content_invalid` errors and two HTTP 429 rate-limit responses. The malformed-content responses used only 364, 734, and 923 output tokens, below the new ceiling. Their raw content was not retained by the provider adapter; the saved evidence cannot distinguish malformed JSON, duplicate keys, or an unsupported fence. Do not blame token truncation or invent a more specific cause. There were no automatic transport retries.

## Content diagnostics

An unblinded agent review inspected all 45 translations in all three locales. It found two affected 0731 posts:

- `2079629240996155513`: two source sentences about an observed leadership-departure pattern and mid-level researchers updating profiles were omitted in all three locales.
- `2097798902875599143`: the Chinese translation misspelled “Anthropic” as “Anhtropic”.

The incumbent diagnostic found no material omissions and retained source line counts and observed shortened URLs. Minor localization observations are recorded separately. These checks are diagnostic evidence; they are not a blinded language-quality acceptance result. Commentary fidelity has not yet received a complete source-visible review.

## Verification and continuity

The combined classifier, literal translator, and execution-harness checks passed **102 tests**, including **3 required PostgreSQL tests with zero skips or errors**. New coverage exercises actual caller budgets, variable 20/20/5 output allowances, immutable input verification, once-only attempts, retained error usage, and per-model process locking.

The latest frozen comparison reserves at most $0.50 per model across translation and commentary, with worst-case planning reservations of $0.44654 and $0.44764. Earlier runs remain intact. Source-bearing artifacts stay private:

- Lower-ceiling results: `.context/u20/translation-synthesis-execute-20260916-v1/`
- Higher-ceiling 0731 translations: `.context/u20/translation-synthesis-execute-20260916-v2/arms/0731/translation/`
- Completed incumbent translations and both 4,000-token commentary runs: `.context/u20/translation-synthesis-execute-20260916-v3/`
- Frozen final inputs: `.context/u20/translation-synthesis-prepare-20260916-v4/`
- Translation diagnostics: `.context/u20/0731-translation-complete-diagnostic-20260916.json` and `.context/u20/incumbent-translation-diagnostic-20260916.json`
- Browser review: `.context/u20/translator-review-20260916/translator-review.html`

[Machine-readable comparison](2026-09-16-182000-u20-translation-commentary-comparison.json).

The selected classifier remains cloud 0731. These separate translation/commentary trials do not change that decision. Classifier semantic floors, translation fidelity/latency, commentary completeness, and locale activation retain their existing gates. No production or staging service, database, or runtime configuration was changed.
