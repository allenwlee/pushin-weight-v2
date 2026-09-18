# Luna commentary v3 diagnostic24 source review

This review covers all 24 diagnostic24 source records, their supplied local context, and every delivered Luna v3 commentary field. It is a source-only assessment: it does not use reference answers or external fact checks. One request (`2100158202914406749`) was consumed once, returned an upstream OpenRouter 429, and was retained without retry. Its three locale fields are coverage-unavailable.

The complete per-source and per-locale record is [source-grounded-review-v1.json](../../.context/model-task-20260917/luna-commentary-v3-medium-sourcebound-diagnostic24/source-grounded-review-v1.json) (SHA-256 `698cf352d0bf141188ffe57448eefeb2e3901623801390970ceacf97b8aae961`).

## Results

Of 24 source posts, 23 were delivered. Twenty source posts have no finding, three have confirmed minor semantic or target-language findings, and one is the retained 429 coverage failure. There are no unresolved source-only findings.

| Locale result | Count |
| --- | ---: |
| Good | 63 |
| Minor error | 6 |
| Material error | 0 |
| Unknown | 0 |
| Unavailable (one 429) | 3 |

The confirmed source-level total is 4 including coverage (3 semantic/locale sources plus the 429), below the corrected T3 same-cohort total of 7 (5 semantic plus 2 coverage). This is an observed diagnostic comparison, not a qualification decision.

The three delivered-source findings are all minor:

- `2100270972465008655`: Chinese and Japanese retain ordinary English `lol like` inside an otherwise translated explanation. `ox alpha` may remain as the opaque codename.
- `2100339358398058923`: Chinese and Japanese convert ambiguous `Mistral infra got hit during launch` into an attack. The source does not establish a cyberattack or any other cause.
- `2100430324899455118`: Chinese and Japanese preserve the correct 18-trillion magnitude, but leave the ordinary quantity phrase `18 trillion tokens` in English rather than fully rendering the required target language. Unlike T3’s Japanese defect, neither output reverses the Korean headline’s direction.

The context-bearing rows were checked for attribution. `2100058309072199756` correctly identifies the email test as the quoted writer’s; `2100320389226225806` does not attribute the `local_parent` review to the source author; and `2100420165917982857` summarizes the source’s own ecosystem thesis without treating related local context as the author’s statement.

## Same-cohort comparison

T3’s two pipeline failures (`2100079736537923768`, `2100320389226225806`) both have source-grounded Luna outputs. Luna also avoids the T3 opaque-URL/image inference on `2100158202914406749` only in the limited sense that no output was delivered: its one 429 makes an exact semantic comparison impossible. Luna avoids T3’s actual semantic errors on `2100262531788832809` and `2100346971144036571`. On `2100270972465008655` and `2100430324899455118`, it avoids T3’s invented-release and direction-reversal errors but has the distinct locale-completion findings above.

No same-error shared semantic finding was observed. That does not convert this review into approval for qualification, production changes, profile edits, or more paid calls.

## Receipt

The retained run receipt records 23 received calls out of 24, 14,385 input tokens, 11,721 output tokens (including 6,252 reasoning tokens), provider-reported cost `$0.008572125`, and p95 latency `20,334 ms`. The failed 429 request has no usage receipt. These figures come from the frozen run report and the already recorded Luna research receipt.
