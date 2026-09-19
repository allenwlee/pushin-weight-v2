# Gemma 4 31B translation-trial rationale

## Scope

This is a proposed bounded translation candidate, not an implementation or a
quality claim. It covers `google/gemma-4-31b-it` only. Classification remains
settled on 0731, and neither commentary nor production routing is in scope.
The first possible paid step is the existing eight-source translation smoke
after a frozen profile, contract, focused caller tests, and the shared paid
slot are available.

The governing acceptance criterion is R113: a candidate must equal or beat
DeepSeek V4.1 on matching source/context and every required output under
source-grounded review. The trial retains the existing three configurations per
model/task, $3 reserved per model/task, $30 portfolio, one process, at most
three in-flight requests, and no retry/fallback constraints. A delivered JSON
or text response is not semantic success.

## Evidence and route

The saved September 17 catalog is the exclusive price authority. Its exact
paid ID is `google/gemma-4-31b-it` (canonical slug
`google/gemma-4-31b-it-20260402`), with a 262,144-token context window,
16,384 maximum completion tokens, nonmandatory/default-off reasoning, and
prices of `$0.09` input and `$0.34` output per million tokens. It lists
`reasoning`, `max_tokens`, and `response_format` among supported controls.
The catalog also lists a separate `:free` SKU; it is not the proposed route or
price source for this trial.

The original catalog did not contain a Gemma endpoint response. A new route-
and-capability-only immutable supplement fills that gap:

- raw response:
  `docs/research/2026-09-17-223000-gemma4-31b-openrouter-endpoint-snapshot/raw/endpoints-google__gemma-4-31b-it.json`
  (`8189242dbeec3701e1faf571e390dfd0eddb8ee3289db85505698babb0334e91`)
- manifest:
  `docs/research/2026-09-17-223000-gemma4-31b-openrouter-endpoint-snapshot/manifest.json`
  (`25c89d2953e0e54f0ba0e81460f60f1ca7965bf0928885a1e90b8a6f488f9406`)

It identifies the matching selected route as **DeepInfra FP4**:
`provider=DeepInfra`, `provider.only=["deepinfra/turbo"]`, endpoint tag
`deepinfra/turbo`, upstream model
`google/gemma-4-31b-it-20260402`, 262,144 context tokens and 16,384 completion
tokens. The endpoint reports support for `reasoning`, `include_reasoning`,
`max_tokens`, and `response_format`. Current rate values in this response are
not used to price the trial; the frozen catalog rate remains the cap.

Google’s [Gemma 4 prompt-format guide](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)
documents the model’s system/user/model turn tokens and says thinking is
activated by a `<|think|>` token in a system turn. Its [thinking guide](https://ai.google.dev/gemma/docs/capabilities/thinking)
specifies that the 31B off-template includes an empty thought channel to
suppress ghost thought channels, while the prompt guide warns that larger
Gemma 4 variants may still emit one when thinking is off. The
[official Hugging Face model card](https://huggingface.co/google/gemma-4-31B-it)
lists a 256K window and multilingual support in more than 140 languages; its
[canonical chat template](https://huggingface.co/google/gemma-4-31B-it/blob/main/chat_template.jinja)
confirms that provider formatting owns the special-turn syntax. The existing
OpenRouter chat caller should therefore receive ordinary role messages only;
it must not inject raw Gemma turn or thought tokens.

## Recommended v1 profile

The initial profile should be `gemma4_translation_v1` with these fixed values:

| Field | Value |
| --- | --- |
| Task / model | `translation` / `google/gemma-4-31b-it` |
| Route | DeepInfra FP4, `deepinfra/turbo`, upstream `google/gemma-4-31b-it-20260402` |
| Pricing cap | Saved catalog `$0.09` input / `$0.34` output per million |
| Caller shape | Existing literal plaintext translation caller; one source/target request, raw text result |
| Reasoning | Explicit `{"enabled": false, "exclude": true}`; do not add `<|think|>` |
| Output / timeout | 8,192 profile cap; 180 seconds |
| Samplers | Omit `temperature`, `top_p`, `top_k`, `min_p`, seed, penalties, and stop rather than inherit defaults |
| Provider safety | Require the pinned provider parameters; disallow fallbacks |
| Parallelism | Existing shared maximum of three source-target calls |

The frozen smoke8 input contains eight source records in English, Simplified
Chinese, Korean, and `other`; the existing caller expands that to 19 required
target calls. An in-memory capture with the proposed profile produced 19
requests, maximum request size 3,592 bytes, request ceilings from 1,061 to
2,756 tokens, and a saved-price reservation of `$0.01422844`. Those figures
are preflight evidence only, not a contract or a call. They fit the source and
endpoint context/completion limits and leave the $3 task cap intact.

The exact implementation after authorization is limited to adding this profile
and a focused request-capture test that pins route, disabled reasoning,
omitted samplers, raw-text translation shape, and the saved prices. No harness
change is expected: the existing task profile applies the request to the
literal translation caller, freezes the contract, records before-send markers,
and limits live concurrency to three.

## Conditional v2 and v3 hypotheses

No second or third configuration is preselected as a spend target. Each must
be tied to a retained v1 source-only review finding.

- **v2, only if v1 delivers complete protected spans but has source-fidelity
  errors attributable to an overloaded literal instruction:** retain the same
  route, pricing, no-thinking setting and output cap; replace only the prompt
  style with the existing compact literal translation prompt. Review the same
  smoke8 sources and carry every v1 failure forward.
- **v3, only if v2’s review shows a specific remaining semantic failure family
  that warrants a representation change:** retain the route and no-thinking
  setting; use the existing structured line representation with deterministic
  restoration and protected-span validation. The change is only justified if
  it addresses the documented failure family, not to fill the configuration
  budget.

Neither variation may encode case-specific answers, post-specific glossaries,
semantic repair, hidden retry, provider fallback, dropped locale, or an
unreviewed fresh corpus. A structural/transport failure remains a failed source
for R113 rather than evidence of language quality.

## Interpretation limits

Past Gemini failures are not evidence about Gemma: they use a different model,
provider route, prompt behavior, and reasoning implementation. Likewise, an
older free-Gemma transport outcome cannot establish semantic quality or route
reliability for this paid, pinned DeepInfra FP4 candidate. The first review
must compare Gemma outputs directly with supplied source/context and the
matching incumbent cohort.

After any live run, the packet should follow the established translation
review shape: one source/context record per post, generated and native output
fields, retained transport/structural status, and an exact packet hash. The
blind reviewer receives source, source language, supplied context, candidate
texts, and coverage only; no candidate profile, old answer, reference output,
or prior score. Reviewers must record exact source and output spans and keep
unknowns separate from confirmed errors.
