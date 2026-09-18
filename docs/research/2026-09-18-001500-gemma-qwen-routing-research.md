# Gemma and Qwen: provider failures and alternative access

Research date: 2026-09-18 JST. Scope: diagnosis and access research only; no inference, configuration change, account creation, or deployment. Current endpoint availability was retrieved from public APIs and saved under the matching research directory. All prices below come exclusively from existing September 17 snapshots, not today's webpages or API prices.

## Conclusion

The evidence identifies upstream shared-provider capacity failures, not excessive traffic from this application or a demonstrated OpenRouter-wide outage. We also disabled OpenRouter's normal resilience by fixing each experiment to one endpoint at its exact price ceiling. This was useful for identifying which route produced the output, but prevented testing whether the same model could work reliably through other routes. We should distinguish a model-quality experiment from a provider-delivery experiment.

The new error receipts identify DeepInfra `engine_overloaded` for Gemma and GMICloud `rate_limit_exceeded` for Qwen, with `limit_source=upstream_provider_shared_pool` and `is_byok=false`. Gemma had two concurrent requests; Qwen had one with four-second minimum spacing. Those counts do not suggest we overwhelmed an inference platform. DeepInfra explicitly documents occasional busy-model 429s even below a direct account's concurrent-request limit. That direct-account limit does not establish OpenRouter's shared allocation. [DeepInfra rate-limit documentation](https://docs.deepinfra.com/account/rate-limits), [OpenRouter error-source guidance](https://openrouter.ai/docs/api_reference/limits).

## What our implementation contributed

1. **One eligible endpoint, no failover.** Frozen requests contain Gemma `only: ["deepinfra/turbo"]` and Qwen `only: ["gmicloud/fp8"]`, both with `allow_fallbacks: false`. Both their provider allowlist and their price cap exclude alternatives. Changing only the fallback Boolean would not be enough. The shared client's response validator also expects the pinned provider, so its accepted route identities must change alongside any experimental route allowlist. Preserve exact model identity, record actual provider/precision, and admit only reviewed providers. OpenRouter normally supports trying another provider for the same model; this need not mean switching models. [Routing documentation](https://openrouter.ai/docs/guides/routing/provider-selection).
2. **Gemma retries were too short for the observed overload window.** Its retry helper computes approximately one second then two seconds before the next attempt, with small jitter. It adds a roughly four-second cooldown after the final failure, but a new target restarts the short sequence. That is valid bounded exponential retry, but not an adaptive response to sustained pool saturation. A proposed follow-up would retain a provider-level failure streak, use 15/30/60-second cooldowns when no hint is supplied, reduce to one worker while unhealthy, and defer exhausted targets to a later sweep. These numbers are an engineering proposal, not vendor-prescribed constants. Qwen did honor its 60-second Retry-After, so this criticism does not explain its remaining failures.
3. **Transport outages became final missing translations.** The bounded experiment intentionally stopped after three 429/503 attempts, and did not retry other failures. Gemma also had two 180-second read timeouts. For a production-shaped delivery test, retain a resumable pending queue and retry only missing fields after the pool recovers, with an overall time/spend limit. Do not regenerate successful fields or silently remove missing rows from quality scoring. A timeout can have an unknown billable outcome; account for it separately.
4. **Earlier diagnostics lost useful error details.** The normal OpenRouter HTTP path reads the error body and then raises a generic status exception. The corrected isolated reruns capture sanitized body, provider metadata, Retry-After and usage. Keep that evidence in any subsequent shared implementation. Separate 402 credit/budget issues, upstream overload, format rejection and semantic mistakes.
5. **The headline error union mixes availability with language quality.** This is appropriate for end-to-end suitability, but 25/100 Gemma does not mean 25 mistranslated posts: 20 posts have missing/rejected fields, one additional post retains Hausa, and four more have semantic/protocol defects. Qwen has two missing-output posts, eight semantic-error posts, and one additional uncertain post. Eliminating overload is necessary to complete the comparison, but cannot by itself fix the observed language errors.

Local evidence: `x_monitor/openrouter.py:97` (routing), `:204` (generic HTTP failure), `:270` (provider validation); Gemma isolated `recovery_runner.py:87` (backoff); Qwen isolated `qwen_recovery_runner.py:95` (Retry-After). Full receipt/review paths are in [the completed rerun comparison](2026-09-17-235000-gemma-qwen-recovery-rerun-comparison.json).

## Alternative OpenRouter routes, with saved prices

Current public catalogs list 14 Gemma endpoint records and 10 Qwen records. Counts include endpoint variants and nonzero status codes, so they are not counts of independently healthy providers. Short-window uptime percentages do not establish future availability. The saved availability files deliberately omit current prices.

| Exact model | Route | Precision | Saved input / output USD per million tokens | Role |
| --- | --- | --- | --- | --- |
| Gemma 4 31B IT | DeepInfra turbo, current | FP4 | 0.09 / 0.34 | Existing failed route |
| Gemma 4 31B IT | CoreWeave | FP4 | 0.10 / 0.34 | Smallest saved-price step; compare provider at same precision |
| Gemma 4 31B IT | DeepInfra standard | FP8 | 0.13 / 0.38 | Changes precision, but retains provider; not an independent outage domain |
| Gemma 4 31B IT | Crusoe | BF16 | 0.14 / 0.40 | Independent provider plus higher precision; changes two factors |
| Gemma 4 31B IT | Friendli | Undisclosed | 0.14 / 0.40 | Independent route; validate output cap and identity |
| Qwen3 235B A22B Instruct 2507 | GMICloud, current | FP8 | 0.0875 / 0.35 | Existing failed route |
| Qwen3 235B A22B Instruct 2507 | DeepInfra | FP8 | 0.09 / 0.55 | Independent provider, same listed precision |
| Qwen3 235B A22B Instruct 2507 | Novita | FP8 | 0.09 / 0.58 | Independent provider, same listed precision |
| Qwen3 235B A22B Instruct 2507 | Alibaba | Undisclosed | 0.1495 / 0.598 | Model developer via OpenRouter |

Price sources: `2026-09-17-223000-gemma4-31b-openrouter-endpoint-snapshot/raw/endpoints-google__gemma-4-31b-it.json` and `2026-09-17-122545-qwen235-endpoints/openrouter-endpoints-original.json`. These are historical quotes, not guaranteed current execution costs. A route not fitting its cap should fail visibly rather than silently widen spend. The Qwen output-price increase matters because translation produces substantial output.

## Direct access, without OpenRouter

| Model | Confirmed access | Implementation / caveat |
| --- | --- | --- |
| Gemma 4 31B | Google Gemini API: `gemma-4-31b-it` | Official Google documentation lists the exact model. Native `generateContent` interface; Google documents `thinking_level="minimal"` to disable Gemma thinking. Account access/quota still need checking. |
| Gemma 4 31B | DeepInfra: `google/gemma-4-31B-it-turbo` | `https://api.deepinfra.com/v1/openai/chat/completions`; closest direct match to the tested FP4 route. Separate account quota does not guarantee separate physical capacity. |
| Gemma 4 31B | Together: `google/gemma-4-31B-it` | `https://api.together.xyz/v1/chat/completions`; official model page lists serverless access. New provider/account; direct pricing not established by our existing OpenRouter snapshots. |
| Qwen3 235B A22B Instruct 2507 | Alibaba Model Studio: `qwen3-235b-a22b-instruct-2507` | Singapore OpenAI-compatible base: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`. Exact-model docs list structured outputs, 600 requests/minute and one million tokens/minute; actual account quota must be confirmed. |
| Qwen3 235B A22B Instruct 2507 | DeepInfra: `Qwen/Qwen3-235B-A22B-Instruct-2507` | Same DeepInfra OpenAI-compatible base. Alternative to GMICloud with a direct provider account. |

Sources: [Google Gemma API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api), [DeepInfra Gemma turbo API](https://deepinfra.com/google/gemma-4-31B-it-turbo/api), [Together Gemma model/API](https://www.together.ai/models/gemma-4-31b), [Alibaba exact Qwen model](https://www.alibabacloud.com/help/en/model-studio/qwen3-235b-a22b-instruct-2507), [Alibaba regional base URLs](https://help.aliyun.com/en/model-studio/base-url), [DeepInfra Qwen API](https://deepinfra.com/Qwen/Qwen3-235B-A22B-Instruct-2507/api).

A Fireworks listing for this exact Qwen checkpoint also exists, but it advertises **Deploy on Demand**, not confirmed shared serverless access. Dedicated deployment is a different spending model and is not the first choice for this small-volume experiment. Self-hosting the published weights is also possible, but would introduce hardware/capacity work rather than resolve this routing test with minimal changes. [Fireworks exact-model listing](https://fireworks.ai/models/fireworks/qwen3-235b-a22b-instruct-2507).

Bring-your-own-key through OpenRouter is a middle path: supported direct-provider credentials give control of provider account quotas while retaining the OpenRouter interface. For a diagnostic specifically testing independent account capacity, disable automatic fallback to OpenRouter shared capacity; otherwise a BYOK failure can silently return to the pool we are investigating. BYOK does not guarantee independent GPUs or eliminate provider-wide overload. [OpenRouter BYOK documentation](https://openrouter.ai/docs/guides/overview/auth/byok).

## Recommended next experiment

First test Gemma through CoreWeave FP4 and Qwen through Novita or DeepInfra FP8, each with its own recorded configuration and a saved-price cap. This isolates the provider more cleanly than immediately changing precision or model. Use the existing key and frozen source/prompt content, preserve native copies, and apply response-identity validation for the selected new endpoint. After individually validating alternate routes, permit a small allowlist of same-model fallbacks and record every chosen endpoint.

For a direct-provider comparison, prioritize Alibaba's own Qwen endpoint and Google's Gemma endpoint; DeepInfra direct is useful specifically for testing the account-pool hypothesis but is not proof of an independent hardware pool. Snapshot direct prices before deciding spend. Preserve the same semantic rubric and complete missing outputs before making a new language-quality judgment. Do not equate provider success with quality qualification.

Suggested checks before implementation: fake 429 from first provider then second-provider success with provenance; strict rejection of unapproved model/route; max-price enforcement; cooldown persistence across different target rows; Retry-After longer than run deadline; deferred fields resume without regenerating successful outputs; unknown timeout costs retained. No fixes or new paid requests were executed in this research turn.
