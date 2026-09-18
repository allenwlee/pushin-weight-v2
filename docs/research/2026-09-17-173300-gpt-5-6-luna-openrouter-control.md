# GPT-5.6 Luna OpenRouter control

## Scope and boundary

This records the translation and commentary control for the exact requested
model ID, `openai/gpt-5.6-luna`, through OpenRouter Chat Completions. It does
not add a classifier profile or alter production defaults. Both controls use
the frozen eight-source smoke cohort; a later expansion, if warranted by the
source-only review, must reuse the frozen 24-source cohort unchanged.

The September 14 classifier record is not a quality result. It made zero
inference calls because its shared request sent `temperature: 0`, which the
selected Luna endpoint did not advertise. The present control removes that
unsupported sampler field and does not infer any quality conclusion from the
old block. See [the recorded R98 result](../2026-09-15-135812-u18-classifier-model-and-architecture-experiment-report.md).

## Evidence used to freeze the request

- The [official OpenAI Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna) identifies Luna as the cost-sensitive GPT-5.6 tier, gives its 1,050,000-token context window and 128,000-token output ceiling, and lists `low` among its supported reasoning efforts.
- OpenRouter's [reasoning documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) specifies `reasoning.effort`, describes `low` as allocating a small portion of the completion budget, and permits `exclude: true` to keep the reasoning trace out of returned content. It also requires remaining completion space for the visible answer.
- OpenRouter's [structured-output documentation](https://openrouter.ai/docs/guides/features/structured-outputs) specifies `response_format: {type: "json_schema"}` and recommends strict schemas on routes that advertise structured-output support.
- The immutable endpoint receipt at [2026-09-17-172422-luna-openrouter-endpoint-snapshot](2026-09-17-172422-luna-openrouter-endpoint-snapshot/README.md) has manifest SHA-256 `61f7290768e0f323dbb3388991c8941f23d23038b4b34262071d8a6a145e1dad`. Its raw public response pins the available OpenAI Flex endpoint: tag `openai/flex`, served alias `openai/gpt-5.6-luna-20260709`, status `0`, 1,050,000 context tokens, 128,000 output tokens, and support for `reasoning`, `max_tokens`, `response_format`, and `structured_outputs`.
- Prices used to freeze the contract ceiling come only from the immutable September 17 [catalog snapshot](2026-09-17-143812-openrouter-pricing-snapshot/README.md), whose manifest SHA-256 is `28e5394ed2e9d15aca585d3c0556f8734720c14d7e970b83104ec251db839e52`: $0.20/M input and $1.20/M output. The separate immutable endpoint receipt preserves the live `openai/flex` rate fields as evidence, but those lower values were not used to relax the contract ceiling: $0.10/M input, $0.60/M output, $0.01/M cache-read, $0.125/M cache-write, with a >=272K prompt override of $0.20/M input and $0.90/M output.

## Frozen profile

`luna_translation_v1` and `luna_commentary_v1` both pin:

- OpenRouter as the transport, exact model ID `openai/gpt-5.6-luna`, provider `openai/flex`, `service_tier: flex`, `allow_fallbacks: false`, `require_parameters: true`, and the saved-snapshot price ceiling.
- `reasoning: {"effort":"low","exclude":true}`. Translation adds 1,024 tokens to each caller's visible request. Commentary keeps 4,096 caller-visible tokens plus that same 1,024-token reserve, for a 5,120-token wire cap.
- Omission of `temperature`, `top_p`, and every other sampler field unsupported by the saved model record and endpoint receipt. The commentary control uses a strict JSON Schema; translation retains the literal plaintext caller and all target locales.

The focused regression net proves that Luna's actual commentary caller uses the visible-plus-reasoning budget without exceeding the profile cap, and that profiles with no headroom retain their prior output limit. It passed 13 tests before transport.

## Smoke execution record

The completed contracts are [translation](../../.context/model-task-20260917/luna-translation-v1-final-smoke8/contract.json) (`a72be7f2384044174856cffa5da7a17ca3db08960f8ed5cebbb8cd3c911263b7`) and [commentary](../../.context/model-task-20260917/luna-commentary-v1-final-smoke8/contract.json) (`32d365c6424122ee6b7bb0c02ce4c6c02cdb37e665e0a246af5a1d6e382e9849`). They have the same frozen source-row hash, `829ca9c8c8d5502be35669f85cfbf1b00657a361495d174efed51c4864d1d19b`.

| Task | Calls | Reservation from saved prices | Transport result | Attested route |
| --- | ---: | ---: | --- | --- |
| Translation | 19 | $0.0689238 | 8/8 rows complete; no transport or structural error | OpenAI / OpenAI / Flex; Luna model ID returned |
| Commentary | 8 | $0.0519662 | 8/8 rows complete; no transport or structural error | OpenAI / OpenAI / Flex; Luna model ID returned |

The response receipts total $0.0035352 for translation and $0.0021510 for
commentary. The translation receipt exactly reconciles to the saved Flex
endpoint rates: 7,548 input tokens at $0.10/M plus 4,634 output tokens at
$0.60/M. These are observed receipt metrics, while the higher catalog rates
remain the frozen reservation and request `max_price` ceiling.

Both reports remain semantically unassessed. The source-only packets preserve
each exact source, supplied context, and candidate output without an incumbent
answer: [translation packet](../../.context/model-task-20260917/luna-translation-v1-final-smoke8/source-only-review-packet.json) and [commentary packet](../../.context/model-task-20260917/luna-commentary-v1-final-smoke8/source-only-review-packet.json). They are the next review input; no 24-source transport is justified until that review is complete.

## V3 translation preparation

The V2 source-only review found unresolved marker-framing and source-fidelity
failures. The prepared `luna_translation_v3` therefore changes the output
representation, not a reviewed answer: it requests a JSON object with one
translated `lines` entry for each caller-derived source line, then restores the
existing markers locally. This removes model-generated protocol framing from
the semantic task while rejecting a malformed line count, non-string line, or
moved protected placeholder rather than repairing it.

The same official model page and OpenRouter reasoning documentation list
`medium` effort for Luna. V3 uses that supported effort with 4,096 tokens of
separate completion headroom, so the visible source-derived translation budget
remains available after reasoning. Its prompt gives only general rules:
preserve grammatical relationships with natural target syntax, translate idiom
meaning, retain opaque product names while translating ordinary neighboring
prose, and preserve ambiguous units. It contains no case answer, source-derived
glossary, or automatic Unicode correction. The profile and its caller-shape
tests are prepared, but no V3 contract or transport is authorized until the V2
semantic review confirms the need for this final trial.

## Later control receipts

The V2 source-bound translation smoke completed all 19 requests but had one
structural row failure. Parent source review then confirmed four affected
sources plus one unresolved tokenizer attachment, which exceeds the corrected
translation baseline's four confirmed source errors. It did not qualify.
Its paired V2 commentary smoke completed all eight rows; the parent-confirmed
review found two affected sources against the corrected commentary baseline's
four confirmed source errors, so the same V2 profile was run on the unchanged
24-source diagnostic as wider evidence rather than as a new configuration.

V3 translation completed all 19 requests and all eight structural rows with
JSON-line restoration. Its source-only review packet is
[here](../../.context/model-task-20260917/luna-translation-v3-jsonlines-medium-smoke8/source-only-review-packet.json);
semantic assessment remains independent and unassessed in the run artifact.
The V2 commentary diagnostic completed 24/24 structural rows. Its packet is
[here](../../.context/model-task-20260917/luna-commentary-v2-sourcebound-diagnostic24/source-only-review-packet.json).

| Run | Calls | Receipt tokens (input/output/reasoning) | Provider-reported receipt cost | p95 latency |
| --- | ---: | ---: | ---: | ---: |
| V2 translation smoke | 19 | 5,741 / 6,351 / 3,415 | $0.0043847 | 8,835 ms |
| V2 commentary smoke | 8 | 3,548 / 2,660 / 822 | $0.0019508 | 6,810 ms |
| V3 translation smoke | 19 | 6,125 / 7,485 / 4,652 | $0.0051035 | 14,999 ms |
| V2 commentary diagnostic24 | 24 | 13,569 / 7,600 / 1,859 | $0.006015325 | 6,924 ms |
| V3 translation diagnostic24 | 55 | 20,845 / 23,486 / 10,576 | $0.0163085 | 12,999 ms |

These are response receipt totals. The saved September catalog price ceiling
continues to govern reservation and `max_price`; no live rate was substituted
into a frozen contract.

Parent verification after the final diagnostic passed 48 tests with no skips or
warnings using the retained basetemp
`.context/model-task-20260917/pytest-parent-luna-v3-20260917-175800`.
The profile and caller sources remained unchanged after the V3 diagnostic
contract froze. Wider source-only review remains the next decision point; this
control wave makes no further paid call.

## V3 commentary final attempt

The V2 wider review did not meet commentary parity, so `luna_commentary_v3`
was the final configuration. It retained the compact one-to-two-sentence,
strict-schema call and used documented `medium` reasoning with a 4,096-token
visible budget plus 4,096 tokens of headroom. The source-bound prompt uses
general fidelity rules: language-complete output, ordinary-prose translation,
numeric magnitude preservation, no association inferred from quoted or
addressed handles, and retained ambiguity for unclear pronouns or colloquial
phrases. It contains no post-specific answer, glossary, or response repair.

The smoke completed seven rows and recorded one `synthesis_response_identity_mismatch` as a structural error; its packet is
[here](../../.context/model-task-20260917/luna-commentary-v3-medium-sourcebound-smoke8/source-only-review-packet.json).
The separately authorized unchanged diagnostic24 completed 23 rows. Its 24th
request was consumed once and returned a retained OpenRouter upstream 429
rate-limit response; no retry occurred. Its packet is
[here](../../.context/model-task-20260917/luna-commentary-v3-medium-sourcebound-diagnostic24/source-only-review-packet.json).

| Run | Received calls | Complete rows | Receipt tokens (input/output/reasoning) | Provider-reported receipt cost | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| V3 commentary smoke | 8 | 7/8 | 3,964 / 3,720 / 2,062 | $0.0026284 | 20,335 ms |
| V3 commentary diagnostic24 | 23 | 23/24 | 14,385 / 11,721 / 6,252 | $0.008572125 | 20,334 ms |

The incomplete diagnostic is transport evidence, not a semantic result. Both
records preserve all delivered outputs and the one unserved source without a
retry or fallback. No additional Luna configuration or paid call is authorized
in this control wave.
