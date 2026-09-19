# DeepSeek V4 Flash 0731: access and reasoning diagnosis

Generated: 2026-09-15 22:08 JST

## Plain-English Summary

The 0731 weights are still available, but no longer from DeepSeek's own API. DeepSeek retired them on September 10; its old API model name now routes to V4.1 Flash. PushinWeight can access the real 0731 checkpoint through third-party hosts such as DeepInfra, Fireworks, Together, or a self-hosted deployment.

OpenRouter did route our requests to DeepInfra exactly as requested, so it did not substitute a different model. However, the gateway-to-provider translation remains one variable in reasoning behavior. A direct DeepInfra test would remove that variable but requires a separate `DEEPINFRA_TOKEN`; the existing DeepSeek key cannot authenticate to DeepInfra.

The first reasoning experiment found a concrete configuration failure. Both `high` and `low` reasoning consumed the complete 6,000-token output allowance on every call and returned no final JSON. This does not show that reasoning reduces classification quality. It shows that effort selection does not bound DeepInfra's reasoning length for this 20-post workload.

## Evidence

- DeepSeek's September 10 changelog says V4 Flash is retired and the legacy `deepseek-v4-flash` API name now serves V4.1 Flash: <https://api-docs.deepseek.com/updates/>.
- The official 0731 model card says the model has a custom DeepSeek V4 encoding, supports `low`, `high`, and `max` reasoning, and used `max` reasoning for its headline agent benchmarks: <https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731>.
- The encoding reference says reasoning effort is implemented as prompt text; `low` adds no prefix, while `high` and `max` add increasingly exhaustive instructions. It has no effect in non-thinking chat mode: <https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731/blob/main/encoding/README.md>.
- DeepInfra directly serves `deepseek-ai/DeepSeek-V4-Flash-0731` through an OpenAI-compatible API at $0.06/M input and $0.18/M output; its Flex tier is $0.048/M and $0.144/M: <https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash-0731/api>.
- Fireworks directly serves the checkpoint at $0.22/M input and $0.66/M output and also offers dedicated deployments and fine-tuning: <https://fireworks.ai/models/deepseek-ai/deepseek-v4-flash-0731>.
- OpenRouter currently lists 27 0731 providers. Its Exacto route ranks providers using measured tool-call reliability, throughput, and benchmarks: <https://openrouter.ai/deepseek/deepseek-v4-flash-0731> and <https://openrouter.ai/docs/guides/routing/model-variants/exacto>.

## What PushinWeight actually tested

The two classifier roles remained unchanged: content classification and brand interpretation. Each batch contained 20 posts, producing up to 27 brand-specific decisions. The first batch's request held about 14,500 input tokens per role because non-English cases include both source text and English translation.

| Arm | Reasoning | Result | Cost with estimated OpenRouter fee | Role-parallel time |
|---|---|---|---:|---:|
| R116 | disabled | Structurally recoverable; 70.6% after declared representation normalization | $0.003933 | 40.2s |
| R117 | high | All four calls exhausted 6,000 tokens in reasoning; no answers | $0.007449 | 264.9s |
| R118 | low | All four calls exhausted 6,000 tokens in reasoning; no answers | $0.006661 | 287.7s |

R117 and R118 differ from R116 only in the `reasoning` setting. Prompts, input packets, two roles, batch boundaries, provider, sampling, seed, and maximum output stayed the same. Raw responses attest `DeepInfra` and `deepseek/deepseek-v4-flash-0731`.

## Diagnosis

The weights are capable of the task: even the non-thinking R116 output reached 70.6% agreement after mapping consistent serialization choices such as `[]` to the taxonomy's explicit `none` sentinel. The failure is the execution envelope.

One post is not a difficult classification problem, but a 20-post call is a large compound assignment. Across the two roles it asks the model to process 40 long evidence packets, 52 brand perspectives, multi-label choices, cross-brand attribution, and nine stored axes. Thinking mode attempts to deliberate over all of that before emitting any answer, so a 6,000-token ceiling can end inside reasoning.

OpenRouter is not substituting the model or provider. It may still affect how its normalized `reasoning` parameter is translated to DeepInfra, which is why one direct DeepInfra comparison is useful. The same unbounded behavior for `low` and `high` means effort selection alone is not a usable budget control on the current route.

The token receipts show that OpenRouter did translate the effort setting according to DeepSeek's published encoding. R116 non-thinking and R118 low-thinking used the same prompt-token counts. R117 high added 79 prompt tokens per call, consistent with DeepSeek's documented high-effort instruction prefix. Therefore, the all-reasoning failure is not evidence that OpenRouter ignored the setting. DeepSeek's effort levels are prompt instructions, not hard reasoning-token budgets.

## Investigation: who still serves the 0731 checkpoint?

The statement is substantially correct, with one qualification: providers expose the named 0731 release, but “exact checkpoint” should not imply numerically identical inference. Providers use different precision, kernels, speculative decoding, chat-template adapters, and structured-output systems. These can change outputs even when they begin with the same DeepSeek release.

| Provider | Direct 0731 access | Published serving detail | Direct price per 1M input/output | Assessment |
|---|---|---|---:|---|
| DeepInfra | Yes: `deepseek-ai/DeepSeek-V4-Flash-0731` over its OpenAI-compatible endpoint | FP8; JSON and function calling | $0.06 / $0.18; Flex $0.048 / $0.144 | Best direct cost comparison; requires a DeepInfra token |
| Baseten | Yes: `deepseek-ai/DeepSeek-V4-Flash-0731` over `inference.baseten.co` | Its example explicitly passes `chat_template_kwargs.thinking` and `reasoning_effort`; OpenRouter identifies the endpoint as FP8 | $0.13 / $0.26 | Best documented direct test of the native chat-template controls |
| Cloudflare Workers AI | Yes: `@cf/deepseek-ai/deepseek-v4-flash-0731` | Cloudflare-hosted; function calling, reasoning, JSON format; public page does not identify weight precision | $0.44 / $1.32 | Valid independent host, but too expensive for the target production path |
| Fireworks | Yes: `accounts/fireworks/models/deepseek-v4-flash-0731` | Serverless or dedicated; function calling; provider page links the official Hugging Face release | $0.22 / $0.66 | Useful independent host and fine-tuning path; more expensive than DeepInfra |
| Together | Yes: `deepseek-ai/DeepSeek-V4-Flash-0731` | Serverless model listing; Together reports its own 0731 benchmark runs | $0.14 / $0.28 | Reasonable second independent host |
| Self-hosted | Yes, under the MIT license | Official vLLM/SGLang recipes and DeepSeek's custom encoder | Hardware rather than token pricing | Maximum control, but the official recipe uses four GB300 GPUs |

Official provider references:

- DeepInfra: <https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash-0731/api>
- Baseten: <https://www.baseten.co/library/deepseek-v4-flash-0731/>
- Cloudflare: <https://developers.cloudflare.com/workers-ai/models/deepseek-v4-flash-0731/>
- Fireworks: <https://fireworks.ai/models/deepseek-ai/deepseek-v4-flash-0731>
- Together: <https://www.together.ai/models>

OpenRouter's endpoint catalog currently exposes 27 hosts for the model. Their advertised precision spans FP8, FP4, and undisclosed/unknown. OpenRouter can pin one endpoint, but it is still an aggregator in front of that host. R116–R118 were pinned to DeepInfra and the response metadata attested both `DeepInfra` and `deepseek/deepseek-v4-flash-0731`.

## Recommended two-call path

Keep the two classifier roles. Do not add a third taxonomy call yet.

1. Reduce each batch from 20 to 10 posts while retaining the same two roles. This lowers the number of simultaneous brand decisions and should let thinking mode reach the answer.
2. Remove duplicate bilingual evidence from inference packets. Use source text for English, Chinese, and Japanese; use the English translation for other languages. Persisted source and translation data remain unchanged.
3. Use `low` reasoning first with a 10,000- or 12,000-token ceiling and explicitly reserve space for the final JSON in the prompt. Measure actual reasoning tokens rather than assuming the effort label enforces a cap.
4. Keep the deterministic output adapter: remove one optional JSON fence, map empty arrays to explicit no-label sentinels, and reject missing slots or invalid labels.
5. After that configuration completes, rerun one matched batch through OpenRouter Exacto with a forced classification function. This tests a higher-reliability provider and a model-native tool schema without changing taxonomy semantics.
6. If provider variance remains material, obtain a `DEEPINFRA_TOKEN` and send the identical request directly to DeepInfra. Compare raw response, reasoning usage, latency, and labels. The existing DeepSeek key cannot perform this test.

Self-hosting is technically possible under the model's MIT license, but the official vLLM recipe uses a four-GPU GB300 node. That is not economical for the current workload. Fireworks is the cleanest independent direct-provider comparison and supports fine-tuning, but its serverless token prices are roughly 3.7 times DeepInfra's.

## Exit criteria for 0731

- Both roles return all expected slots without another LLM repair call.
- Reasoning reaches a final answer within the fixed ceiling on repeated batches.
- Representation-normalized agreement clears the current V4.1 control.
- Measured monthly LLM spend remains below the owner's $150 ceiling with frontier-brand coverage included.
- Latency is acceptable for the asynchronous post-fetch pipeline.
