# Translation Attempt B: Blind Semantic Review

This is a diagnostic review of the supplied eight posts. It is not a population-accuracy estimate. Candidate identity and other candidate outputs were not inspected.

## Result

All 24 generated locale outputs were reviewed against the supplied source. Three posts were clean. Four source posts have confirmed material defects, so the confirmed affected-post diagnostic rate is 4/8 (50%). One further post remains unknown because its punctuation-free informal French contains an unresolved cultural idiom; its three targets are not treated as confirmed errors.

| Locale | Reviewed outputs | Confirmed material defects | Uncertain outputs |
| --- | ---: | ---: | ---: |
| English | 8 | 0 | 1 |
| Simplified Chinese | 8 | 1 | 1 |
| Japanese | 8 | 4 | 1 |
| Total | 24 | 5 | 3 |

The diagnostic cannot qualify: it contains four confirmed defective source posts, and the unresolved French post must remain unknown under the rubric.

## Confirmed findings

| Source post | Locale | Severity | Source span | Output span | Finding |
| --- | --- | --- | --- | --- | --- |
| 2100249221484220856 | Japanese | Material | `给它打了个一折` | `1割引で提供している` | Chinese *一折* is one tenth of the price, but Japanese *1割引* is only 10% off. The stated discount magnitude reverses. |
| 2100270972465008655 | Japanese | Material | `i am so excited to try` | `GLM 4だったらどうしよう！Ox Alpha みたいだ！` | The output drops the speaker's excitement to try it. |
| 2100277491390951481 | Japanese | Material | `if i was ngehemat ... pake opencode go sub` | `もしDeepSeek V4.1を節約するなら、OpenCodeのサブスクリプションで...` | The speaker's conditional decision to economize becomes saving the model, and the subscription phrase is attached to a new relation. |
| 2100346971144036571 | Simplified Chinese | Material | `@The_Alex` | omitted | The recipient handle is lost. |
| 2100346971144036571 | Japanese | Material | `@The_Alex` | `Alexさん` | The exact handle is converted to a display-name honorific. |

## Unresolved source-language issue

Post `2100262531788832809` is an informal, unpunctuated French post containing `nan` and `c'est quoi ce poulet`. Its English, Chinese, and Japanese outputs make different choices about direct address, a chicken image, and an expletive-like phrase. The supplied source alone does not establish whether *poulet* is literal imagery, a local idiom, or a direct insult here. Each target is therefore recorded as uncertain in [review-b.json](../../.context/model-task-20260917/review-b.json), rather than counted as an error or passed as correct.

## Failure families and minimal generalizable changes

The confirmed defects cluster in three failure families:

- **Culture-bound numeric wording:** Require the model to resolve locale-specific quantity and discount expressions before rendering them, then retain the computed magnitude consistently across the whole output. A lightweight numeric-fact field in the translation shape, checked before generation, would catch cases such as price fraction versus percentage discount.
- **Short-post stance and attachment loss:** Add an instruction that every first-person stance, conditional subject, and trailing recommendation/reference must have a target-language counterpart, even when the input is informal. A compact pre-output checklist of speaker, condition, object, and relation would address this without forcing literal phrasing.
- **Handle preservation:** Treat `@handle`, URLs, hashtags, and other addressable tokens as immutable spans in the output shape. The model may add grammatical wording around them, but may not omit or substitute their spelling.

For low-confidence slang or code-switched source text, add a source-language-confidence/ambiguity field and direct the translator to preserve a neutral rhetorical image rather than fabricate a vocative insult or stronger idiom. That would route examples like the French post to review without claiming a translation error from insufficient evidence.
