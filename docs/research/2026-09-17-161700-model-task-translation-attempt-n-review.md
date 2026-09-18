# Translation attempt N: source-only blind diagnostic review

**Packet:** `.context/model-task-20260917/review-packet-n.json`  
**Rubric:** `.context/model-task-20260917/review-rubric.md`  
**Scope:** eight supplied posts × English, Simplified Chinese, and Japanese targets (24 outputs).  
**Evidence:** root-post source text; raw receipts were inspected only to explain two missing targets.

## Result

Twelve outputs are reviewed good, eleven have confirmed errors, and one is unresolved. The unresolved Chinese rendering of `ox Alpha` is not counted as correct: source-only evidence cannot determine whether `ox` is an opaque name or literal animal reference.

Six of eight source posts have at least one confirmed defect, so this diagnostic fails the rubric's zero-error threshold. It cannot establish a population error rate.

## Confirmed failures

- English leaves the discount term `一折` as `one-zhe`; Japanese says both “10% off” and “pay 10%,” even though the source says the price is one tenth (90% cut). Japanese also adds “language” to a multimodal large model.
- The English target for the French post and Japanese target for the GLM post are missing. Missing targets are coverage failures.
- The French slang `c'est quoi ce poulet` conveys impressed disbelief at an unusually good deal; Chinese and Japanese render it as literal chicken. Chinese additionally changes unspecified `cts` into U.S. cents.
- Japanese changes one speaker’s “I have used Codex” into “we have used Codex,” and changes a wish to become Ox Alpha into belief that Union Alpha already is Ox Alpha.
- All Korean headline translations reverse or blur the U.S.-must-get-ahead-of-China relationship. Chinese overstates nationality as no longer primary; Japanese broadens U.S. companies' coding agents into U.S. coding agents generally.

## Raw-response diagnosis

The two missing targets are not evidence of a clean translation omitted by post-processing. Both local receipts end with `finish_reason: stop`, not a length finish. The missing English receipt returns an echoed source line plus an English line; the missing Japanese receipt returns a Japanese line plus an empty line. That is consistent with an output-shape/assembly failure, though the receipts alone do not prove the parser's rule.

The visible `source_reading` is also unsafe in a production translation response: one receipt calls `poulet` cheapness and another invents an OpenAI/Alpha identity. It consumes output tokens and creates unsupported assertions without improving the required target.

## Suggested next configuration

Use a translation-only response contract with exactly one required string target per request and no model-generated `source_reading`. Enforce a one-element output array or a single `translation` field, reject source echoes and blank elements before accepting a result, and reserve enough output capacity for the full translation rather than an explanatory preface. The receipts do not expose the configured maximum, so they do not support a numeric `max_tokens` recommendation; both ended normally, making contract shape the first configuration issue to fix.

The detailed, per-locale evidence is in `.context/model-task-20260917/review-n.json`.
