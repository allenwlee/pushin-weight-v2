# U18 R98 direct-control and fallback receipt

**Observed at:** 2026-09-14 21:31 JST (+09:00)  
**Scope:** One direct DeepSeek control and four preapproved OpenRouter fallbacks.  
**Status:** Provider-free research receipt. No inference endpoint was called.

## Frozen experiment boundary

This follow-up keeps the failed R97 outputs immutable and reuses the same 45
ordered, public-X-only packets, two role prompts, 20/20/5 batches, deterministic
parser, merge, owner reference, quality floors, and one identical transport
retry. The consumed owner cohort measures agreement with the owner reference;
it is not unseen validation or a population-accuracy estimate.

The direct control is the classifier already configured in `config.yaml`:
`deepseek-v4-flash` through `https://api.deepseek.com/anthropic`, with thinking
disabled. DeepSeek's current official pricing page lists peak, cache-miss rates
of **$0.44/M input tokens and $1.32/M output tokens** for this model. Those
conservative rates set the control cap; cache hits or off-peak billing may only
reduce actual spend. See [DeepSeek model pricing](https://api-docs.deepseek.com/quick_start/pricing/).

DeepSeek's Open Platform Terms say the developer retains its rights in inputs,
receives any rights in outputs, and must have the rights and permissions needed
for processing. Its privacy policy says submitted prompts may be collected and
that users can opt out of model-training use. This experiment therefore sends
only the already-public X text and minimum public context in the frozen packet;
it excludes owner comments/answers, secrets, private messages, and DB-only
personal or operational data. See [DeepSeek Open Platform Terms](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html)
and [DeepSeek Privacy Policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html).

## Preapproved fallback ladder

Every OpenRouter request pins the exact provider slug, disables provider
fallbacks, requires the requested parameters, enforces the recorded maximum
price, and uses JSON-object output. Reasoning stays disabled or omitted. Flex
routes also send `service_tier: flex` and verify the returned tier.

| Cost order | Model | Exact provider route | Precision | Input/output $/M | Data route | Why it is included |
| --- | --- | --- | --- | ---: | --- | --- |
| 1 | `qwen/qwen3-30b-a3b-instruct-2507` | StreamLake `streamlake` | undisclosed | $0.04815 / $0.19305 | `allow`, non-ZDR | Lowest projected cost; a larger non-thinking instruction model on a provider not used in R97. |
| 2 | `mistralai/mistral-small-3.2-24b-instruct` | Parasail `parasail/bf16` | BF16 | $0.09 / $0.30 | `deny`, ZDR | Model/provider diversity, explicit structured-output support, and documented Chinese/Japanese language coverage. |
| 3 | `openai/gpt-5.6-luna` | OpenAI `openai/flex` | undisclosed | $0.10 / $0.60 | `allow`, non-ZDR | A low-cost proprietary model described for classification, with structured-output support. |
| 4 | direct `deepseek-v4-flash` control | DeepSeek Anthropic-compatible API | provider native | $0.44 / $1.32 | direct | The production-shaped control. It is executed first for diagnosis but remains fourth in cost selection order. |
| 5 | `google/gemini-3.8-flash` | Google AI Studio `google-ai-studio/flex` | undisclosed | $0.375 / $1.875 | `allow`, non-ZDR | Stronger multilingual structured-output fallback, used only if every lower-cost option fails. |

The exact live endpoint records were read from OpenRouter's public endpoint API:
[Qwen3 30B](https://openrouter.ai/api/v1/models/qwen/qwen3-30b-a3b-instruct-2507/endpoints),
[Mistral Small 3.2](https://openrouter.ai/api/v1/models/mistralai/mistral-small-3.2-24b-instruct/endpoints),
[GPT-5.6 Luna](https://openrouter.ai/api/v1/models/openai/gpt-5.6-luna/endpoints), and
[Gemini 3.8 Flash](https://openrouter.ai/api/v1/models/google/gemini-3.8-flash/endpoints).
All selected endpoints were available and advertised `max_tokens`,
`response_format`, and `structured_outputs`; each context and output ceiling
exceeded the frozen request shape.

OpenRouter documents that a full provider slug such as `openai/flex` targets a
specific endpoint variant. It separately documents `service_tier: flex` for
OpenAI and Google routes and returns the served tier in the response. See
[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
and [service tiers](https://openrouter.ai/docs/guides/features/service-tiers).

## Data-policy decision

OpenRouter's provider-policy feed reported `training=false` for all four
selected providers at the observation time. It reported prompt retention for
StreamLake, OpenAI, and Google AI Studio, so those routes explicitly use
`data_collection=allow` and `zdr=false`. It reported no prompt retention for
Parasail, and the selected Parasail endpoint appeared in OpenRouter's ZDR feed,
so that route uses `data_collection=deny` and `zdr=true`. These decisions permit
only the frozen public-X-only packet. They do not authorize private, sensitive,
secret, or DB-only material.

Provider terms and privacy links came from OpenRouter's public providers API:
[providers](https://openrouter.ai/api/v1/providers). Operational policy facts
came from its [provider-policy feed](https://openrouter.ai/api/frontend/v1/all-providers)
and [ZDR endpoint feed](https://openrouter.ai/api/v1/endpoints/zdr). Prices,
availability, endpoint assignments, and policies are dynamic and must be
re-attested immediately before transport; a mismatch blocks that route.

## Adaptive execution and selection

The direct DeepSeek control runs first. The runner then evaluates alternatives
in the cost order above and stops once the cheapest passing candidate is known.
For example, a passing Qwen result stops the ladder. If Qwen fails and Mistral
passes, later routes are skipped. If all three lower-cost alternatives fail but
the already-run DeepSeek control passes, DeepSeek is selected and Gemini is not
called. Gemini runs only when all four lower-cost candidates fail.

A pass requires 45/45 complete role pairs, every frozen quality and regression
gate, measured cost within its cap, and complete-result p95 no greater than 180
seconds. No malformed-output repair, third semantic call, per-post fallback,
provider fallback, cap increase, or weakened floor is authorized.
