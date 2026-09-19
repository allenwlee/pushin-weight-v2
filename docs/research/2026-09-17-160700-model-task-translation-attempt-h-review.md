# Translation attempt H: independent blind review

This review checked all eight supplied source posts and all three required targets (English, Simplified Chinese, and Japanese) against the frozen source-based rubric. It did not inspect other candidate outputs. The detailed, machine-readable record is [review-h.json](../../.context/model-task-20260917/review-h.json).

The packet fails: five of eight source posts have at least one confirmed material defect, across 12 of 24 locale outputs. There are no unresolved findings. As a deliberately difficult eight-post diagnostic, it would need zero erroneous source posts to advance and cannot estimate a production error rate.

| Post | EN | zh-CN | JA | Review result |
| --- | --- | --- | --- | --- |
| 2100245604027043870 | good | good | good | Country/model comparison and opaque name preserved. |
| 2100249221484220856 | material | good | material | `一折` became a 10% discount instead of one-tenth price / 90% off. |
| 2100262531788832809 | material | material | material | The admiring French `c'est quoi ce poulet` was lost in all targets; Chinese also changed unspecified `30 cts` to U.S. cents. |
| 2100270972465008655 | good | good | material | Japanese turned the conditional `what if its glm 4` into an assertion that GLM 4 can be tried. |
| 2100277491390951481 | material | material | material | The informal Indonesian-English source’s first-person use of Codex, conditional economy claim, and product names were not preserved. |
| 2100314574721315014 | good | good | good | Comparison and mocking tone preserved. |
| 2100346971144036571 | good | good | good | Guesswork/uncertainty and tokenizer basis preserved. |
| 2100430324899455118 | material | material | material | English changes Trump’s aim to get ahead of China; Chinese and Japanese outputs are missing. English correctly renders `49억` as 4.9 billion. |

The exact source and output spans, corrections, and explicit good-output records are in the JSON record. The linguistic adjudication was applied as directed: in this context, French `poulet` is praise rather than a chicken/coward reference; `cts` leaves currency unspecified; Korean `49억` is 4.9 billion; and the headline says Trump wants to get ahead of China.

The smallest general remedy for a third configuration is one bounded per-target fidelity-and-completeness contract: preserve a compact ledger of speaker/subject, names, quantities and price direction, unspecified currency, idiom polarity, and conditionality before generating each locale; require three nonempty fields and enough output headroom for the longest complete source. It is a general prompt/output-budget change, with no post-specific correction and no extra translation call.
