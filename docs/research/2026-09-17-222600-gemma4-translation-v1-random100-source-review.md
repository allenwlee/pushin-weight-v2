# Gemma 4 31B translation v1: matched random-100 source review

This is a matched diagnostic regression, not a qualification result. Its frozen normalized source-row hash is the same `61cd2421…` cohort used by the incumbent and HY regression artifacts; no new incumbent model call was made.

The 100-by-3 source/context review records 10 locale errors across 7 source posts: eight coverage failures from seven HTTP 429 responses across six source posts, plus two synthetic numeric marker additions on one post. The markers, such as `[[PQ:2B]]`, are absent from the source and appear in the Chinese and Japanese result. HTTP 429s are recorded as coverage only; retained evidence cannot attribute them to OpenRouter or the selected provider, and they do not prove model-quality or prompt-shape failure.

The complete ledger is `.context/model-task-20260917/gemma4-translation-v1-r113-random100-20260917-220700/source-grounded-review-v2.json`. The peer packet is content-masked: it removes model identity and incumbent output, but its path can reveal the candidate, so it is not described as fully blind. The independent peer review and parent adjudication remain pending.

## Amendment

The original own-review ledger missed five erroneous locale fields across two source posts present in the raw report. The additive amendment records the French colloquial phrase `c’est quoi ce poulet` rendered as literal chicken imagery in all three targets, and the unchanged Hausa paragraph in Chinese and Japanese. The amended primary union is nine source posts: two semantic sources and seven coverage sources. The original ledger remains intact; the independent peer review was not informed of these findings before it freezes.

## Second amendment

A final exact-span audit adds one minor Japanese linguistic error on source `2100109982775570765`: `si el modelo ya lo había leído antes` appears as `以前に読んだことがあるかどうkかです`, with a stray Latin `k`. The amended primary union is ten source posts.

## Fourth amendment

Source `2100190300669169957` adds one material Japanese-to-Chinese organizational-identity error. `事前学習に特化した研究所ではなく推論重視の企業として` contrasts an inference-focused company with a pretraining-specialist research lab. The Chinese output instead calls it `一家重视推理而非专注于预训练的研究所`, a research institute. This changes only the Gemma candidate ledger; the matching incumbent/control is not rescored. The primary union is now eleven source posts.


## Final parent reconciliation

Earlier counts above are historical checkpoints. Final review is eleven affected sources, 17 erroneous locale fields and 283 good fields, with no additional unknown. Independent review is complete; its missed semantic cases were corrected by parent source checks. Canonical ledger: `.context/model-task-20260917/gemma4-translation-v1-r113-random100-20260917-220700/parent-reconciled-review.json`. This does not match the incumbent interval of nine to ten affected sources.


### Gemma 429 investigation — attribution correction

The seven HTTP 429s affected **five** posts, not six, and clustered within about ten seconds of the 715-second run. The sixth missing-output post received a successful response copying Danish into the Chinese target; validation correctly rejected it. Total score remains 11/100, now described as five transport-affected posts plus six posts with output defects. No retry or fallback was enabled, and the client discarded HTTP error details, so transient capacity is the leading explanation but OpenRouter-versus-DeepInfra attribution remains unproven. [Investigation and proposed bounded recovery test](2026-09-17-230000-gemma-rate-limit-investigation.md). No new inference or runtime change.
