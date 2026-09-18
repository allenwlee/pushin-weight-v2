# Gemini 2.5 Flash-Lite Flex classifier v1 — preparation

## Capability evidence

Google's current model page lists `gemini-2.5-flash-lite` as the fastest,
most budget-oriented model in the Gemini 2.5 family. It also continues to list
the `gemini-2.5-flash-lite` endpoint rather than a retired preview alias.
[Google model guide](https://ai.google.dev/gemini-api/docs/models).

Google documents JSON Schema structured output for structured classification.
[Google structured-output guide](https://ai.google.dev/gemini-api/docs/structured-output).
The saved September 17 OpenRouter endpoint record independently captures the
chosen `google-ai-studio/flex` endpoint as available and advertising
`reasoning`, `max_tokens`, `response_format`, and `structured_outputs`.

This repository's already-consumed Gemini route probe established the exact
route behavior used here: Google AI Studio Flex accepted strict JSON Schema,
reported `service_tier: flex`, and reported zero reasoning tokens with
reasoning disabled. It is transport evidence only, not classifier quality
evidence.

## Frozen v1 trial

The prepared contract is
`.context/model-task-20260917/gemini-flex-classification-v1-smoke8/contract.json`
(SHA-256 `aa93aa06eb1eeba5b72255062e216dc8caf4d9d4c62c16fa6029ece6c2c5c4ac`).

It uses the exact current smoke eight from `classifier-input.json` (source SHA
`fe4aa63eb4bbfdb38deba5d0f3b4f08a71d62e5db67021b437d384559ce9d0bf`):

- `google/gemini-2.5-flash-lite`, pinned to `google-ai-studio/flex` with
  `service_tier: flex`; fallback is disabled.
- Two roles only, `content` and `brand_interpretation`; two five-post-or-less
  batches, for four calls total.
- Native strict JSON Schema using the current fixed decision and post slots.
- Reasoning disabled, 4,096 maximum output tokens, no temperature/top-p/seed
  sweep.
- September 17 snapshot reservation: $0.00751125. This is a ceiling from the
  saved Flex endpoint prices, separate from any reported spend.

The contract’s quality metadata follows the current parity rule: a candidate
must equal or beat direct DeepSeek V4.1 on the same cohort, supplied context,
and current taxonomy under an independent rubric. It requires a full source
review; disagreement alone is not an error, and coverage/missing labels are
reviewed separately.

No provider request was made by this preparation.
