# Translation attempt M: independent blind review

This automated diagnostic checked all eight supplied source posts and every English, Simplified Chinese, and Japanese translation against the frozen rubric. It used source and supplied stored context only, without inspecting another candidate’s outputs. It is not new human gold and cannot estimate a population rate. The detailed record is [review-m.json](../../.context/model-task-20260917/review-m.json).

The structured v4 format is complete: all 24 required outputs are present. It nevertheless fails on six of eight source posts, with 10 material and one minor locale finding; 13 outputs were explicitly reviewed good and none are unresolved. A difficult eight-post diagnostic needs zero erroneous source posts to advance.

| Post | EN | zh-CN | JA | Review result |
| --- | --- | --- | --- | --- |
| 2100245604027043870 | good | good | good | Country/model comparisons and Bhedbhav GPT preserved. |
| 2100249221484220856 | good | good | minor | Japanese contains the stray Korean token `없이`; price direction and remaining meaning are correct. |
| 2100262531788832809 | material | material | material | English and Japanese literalize French praise slang as chicken; Chinese converts unspecified `cts` into Chinese currency. |
| 2100270972465008655 | good | material | material | Chinese drops `ox` from `ox alpha`; Japanese misparses the GLM 4 hypothetical as `If Its`. |
| 2100277491390951481 | good | good | material | Japanese changes the author’s first-person saving-money conditional into a condition about the addressee using DeepSeek. |
| 2100314574721315014 | good | good | material | Japanese reverses whose wish it is. |
| 2100346971144036571 | good | good | good | The target outputs preserve uncertainty in the source’s ambiguous tokenizer phrasing. |
| 2100430324899455118 | material | material | material | Each headline fails to express Trump’s call to get ahead of China; Chinese reverses the subject entirely. |

The failures support the proposed v5 same-call `source_reading` brief. Before translating, require a compact source-faithful ledger for language/script, speaker and relationship direction, conditionality, named strings, quantities and price direction, currency scope, and contextual idiom polarity. Keep it in the same structured response before the three translations; it is not a fact check, repair call, or post-specific correction.

The brief alone will not prevent the Japanese `없이` contamination. Retain deterministic target validation that rejects unexpected Hangul in Japanese prose while allowing ordinary Latin-script names. This keeps v4’s complete structured delivery while adding a small semantic guardrail.
