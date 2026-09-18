# Qwen translation-v4 prompt and interface research

**Date:** 2026-09-17  
**Decision scope:** Design only. No production change, no model call, and no current pricing claim.  
**Evidence reviewed:** Qwen translation reviews A, D, and F; commentary packet K and its blind review J; the current `qwen_translation_v3` and `qwen_commentary_v2` profile adapter; official Qwen and Alibaba documentation linked below.

## Recommendation

Run a small, fresh Qwen translation-v4 diagnostic before retiring the route. Use a two-message request and a structured per-line response:

1. Put a stable, concise translation contract and four generic contrastive examples in the `system` message.
2. Put only a JSON input object in the `user` message: declared source language, target language, and an ordered array of source text lines.
3. Ask for one JSON object with one `translations` array. Its item count must exactly equal the source-line count.
4. Keep Qwen non-thinking. Request `json_schema` if the frozen Alibaba route accepts it; otherwise use `json_object` and enforce the exact key, string types, and line count locally.
5. Keep `[[PQ...]]` tokens in the text lines, validate their exact per-line multiset after the response, and reconstruct all `[[PW...]]` markers in code only after validation. Do not put PW markers in the model's source payload.

This directly separates semantic fidelity from framing and makes a missing, reordered, or malformed translated line a deterministic failure instead of an ambiguous marker parse.

## What failed, and what v4 addresses

The three translation reviews independently identify the same semantic classes:

| Failure class | Examples from reviews A/D/F | v4 response |
| --- | --- | --- |
| Fraction/percent relation | A Chinese one-tenth price became Japanese “10% off.” | Give a generic remaining-price versus discount example and require numerical relationships, not word-for-word arithmetic labels, to survive. |
| Large units and statistic subject | Chinese-model share became Tencent-only share. | Give a generic large-unit/scope example; explicitly preserve the noun phrase that owns each number. |
| Idiom and slang | French praise was rendered as literal poultry or skepticism. | Give a generic idiom example and require intended stance/tone, never literal imagery when the idiom is recognizable. |
| Code switching and named plan/product strings | Conditional Indonesian advice lost its condition; OpenCode Go was shortened. | Treat each source string as multilingual; preserve conditionals and opaque names exactly unless their ordinary-language part is clearly translatable. |
| Structural delivery | A target was unchanged or missing. | Require an equal-length JSON array and reject failures locally before PW reconstruction. |

Commentary packet K confirms a related grounding problem even after the current `grounded_commentary` instruction: the outputs gave an opaque name a definition, read a quote's different name into the post, inferred meaning from tags and animal words, changed praise into doubt, supplied a currency, and generalized a source-specific metric. A new commentary trial should therefore use the same system/user separation and schema discipline, but it is secondary to translation-v4.

## Proposed translation-v4 wire contract

### System message

Keep this stable across calls. The model is a translator, not a commentator. Its rules should say:

```text
Translate each source line into the requested target language. Return JSON only.
For every array item, preserve the speaker, subject, object, condition, negation,
comparison direction, scope, uncertainty, numbers, units, URLs, handles, hashtags,
and every [[PQ...]] token exactly. Do not add facts or currency.
Keep unfamiliar names, codenames, and product-plan names unchanged; do not identify
or explain them. Render recognizable slang and idioms by intended meaning and tone,
not literal imagery. Blank input line -> blank output line.
Return exactly {"translations":[string,...]} with one string for every input line,
in the same order. No Markdown or other keys.

Generic contrastive examples:
- A price now equal to one tenth of its former price remains a 90% reduction, not a 10% reduction.
- A figure for “models from a region” must not become a figure for one named vendor.
- “4.5B requests” stays 4.5 billion requests; do not change the magnitude or owner.
- In a code-switched informal post, preserve a named service and a conditional such as
  “if I need to save,” while translating the surrounding ordinary-language words.
- An idiom like “this is fire” conveys strong approval where that is its context; do
  not describe literal fire.
```

The examples are deliberately generic and do not reuse this diagnostic's test strings. They target the demonstrated reasoning errors without leaking answers.

### User message

The user message contains data only, for example:

```json
{
  "source_language": "auto",
  "target_language": "Japanese",
  "lines": [
    "First paragraph line with [[PQ0:001]].",
    "",
    "Second paragraph line."
  ]
}
```

For known-language inputs, pass the frozen source-language value rather than `auto`. For the existing `other` class, pass `auto` and keep the instruction that each line may mix languages. This retains visible line and paragraph structure while avoiding the old marker language as a translation task.

### Deterministic adapter responsibilities

Before a call, split the rendered source payload into text lines and retain the PW marker sequence separately. After a call:

1. Parse the JSON response with duplicate-key rejection.
2. Require exactly one `translations` key whose value is an array of strings.
3. Require equal input/output lengths; require empty output for an empty input line.
4. For each line, compare its `[[PQ...]]` token multiset with the source line. Reject on any loss, addition, reorder, or alteration.
5. Rebuild the original PW marker lines around the validated translated lines in code. The model never sees or generates PW markers.

Do not attempt to repair content with a second model call. A rejected output remains a translation failure for the normal recovery/backfill path.

## Qwen-specific evidence and interface choices

Qwen's official structured-output guide documents both `json_object` and strict `json_schema`; it lists Qwen3.7-Flash for JSON Schema, says JSON Object requires the word `JSON` in a system or user message, and warns that JSON Object alone does not guarantee stable field names or types. It also warns that outputs may not be strictly valid JSON in thinking mode for models labelled non-thinking. The current profile already pins reasoning off; retain that setting for v4. [Qwen structured output guide](https://help.aliyun.com/en/model-studio/qwen-structured-output)

The route is currently frozen through OpenRouter's Alibaba endpoint, not a direct Model Studio request. Therefore use strict JSON Schema only after the captured route contract accepts it. `json_object` plus the local validation above is the safe fallback; it uses the response-format capability already present in the current profile without presuming that every direct-provider feature is passed through unchanged.

Qwen's Qwen3 material documents broad multilingual support and explicitly supports disabling thinking. That supports a single structured task for the mixed-language posts, rather than language-specific prompt branches. [Qwen3 documentation](https://qwenlm.github.io/blog/qwen3/)

Alibaba's Qwen-MT documentation is useful as a product-direction reference: it supports automatic source-language detection, explicit source/target languages, and says explicit source language improves accuracy when known. It also recommends preserving document structure and using only relevant context. Do not substitute Qwen-MT into this experiment yet: its documented interface accepts a single user message and does not support system messages, while v4 needs the exact structured line contract and existing frozen route controls. [Qwen-MT documentation](https://help.aliyun.com/en/model-studio/machine-translation)

Alibaba's prompt guide recommends clear, specific requirements and recognizable separators for complex input. JSON arrays provide those boundaries more reliably than raw, interleaved PW marker lines. [Alibaba prompt guide](https://help.aliyun.com/en/model-studio/prompt-engineering-guide)

## Small diagnostic design

Use a fresh, frozen input set rather than replaying the eight reviewed posts. It should contain enough lines to exercise all four contrastive cases, plus ordinary multilingual prose and blank paragraphs. Score every target locale independently under the existing rubric.

The first v4 run should answer only these questions:

- Does the Alibaba-routed model accept the captured JSON Schema request? If it does not, does JSON Object plus local validation deliver every line correctly?
- Does the structured contract eliminate missing/untranslated outputs and marker framing defects?
- Does the generic contrastive instruction improve the demonstrated relation, scope, idiom, and code-switch failures without increasing invented meanings?

Do not claim qualification from a small diagnostic. It can only decide whether a larger fresh qualification is warranted.

## Follow-on commentary-v3 changes

If commentary is retried, use a separate small diagnostic with the following hard constraints:

- Supply `{post, context_items}` as a JSON user object. Label each context item with its provenance. Never state that a post changes, quotes, answers, or replaces a context item unless the post itself says so.
- Do not define opaque terms, identify codenames, infer a tag's purpose, infer an unstated currency, or turn one offer into a market trend.
- For a short or ambiguous post, write a short source-bound explanation. Omit “why this matters” unless the post itself supplies a direct reason.
- Require the three locale fields to preserve the same factual propositions, and produce only the fixed JSON object.

This is more promising than increasing reasoning or adding a separate review call: packet K's defects are unsupported inferences, not a lack of fluency or a JSON transport problem.
