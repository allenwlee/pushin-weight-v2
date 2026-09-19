# Translation attempt G: independent review

**Packet:** `.context/model-task-20260917/review-packet-g.json`  
**Rubric:** `.context/model-task-20260917/review-rubric.md`  
**Scope:** 8 source posts × 3 required locales = 24 outputs, all reviewed.

## Method

This review examined the supplied source, stored context, and packet-G results only. It checked every English, Simplified Chinese, and Japanese target for source meaning, names, quantities, currency, comparison direction, paragraph structure, and target presence. Native-language copies were checked for exactness. It does not infer a population result from this diagnostic sample.

## Confirmed findings

| Post | Locale | Severity | Evidence |
| --- | --- | --- | --- |
| 2100245604027043870 | zh_cn | material | Required Chinese output is `null`. |
| 2100249221484220856 | en | material | Required English output is `null`. |
| 2100249221484220856 | ja | material | The entire Japanese-field output is English. |
| 2100262531788832809 | en | material | French colloquial `poulet` is approving surprise; `chicken` is a literal mistranslation. |
| 2100262531788832809 | zh_cn | material | `美分` invents U.S. currency for unspecified `cts`; `这是什么鬼？` loses the approving idiom. |
| 2100262531788832809 | ja | material | `ショボい` reverses the source's positive surprised reaction. |
| 2100270972465008655 | ja | minor | Omits the speaker's eagerness to try the model. |
| 2100277491390951481 | ja | material | Says to economize on DeepSeek rather than expressing the speaker's conditional of saving money. |
| 2100314574721315014 | zh_cn | material | Turns Union Alpha's wish to be `ox Alpha` into a greeting and loses the name. |
| 2100430324899455118 | en | material | `China must lead` reverses Trump's stated aim to get ahead of China. |
| 2100430324899455118 | zh_cn | material | `中国应领先` reverses the headline's comparative direction. |
| 2100430324899455118 | ja | material | `中国が先行すべき` reverses the headline's comparative direction. |

`7700억` and `49억` in the Korean post are correctly rendered as 770 billion and 4.9 billion, respectively. The remaining 12 outputs are explicitly recorded as reviewed-good in [review-g.json](../../.context/model-task-20260917/review-g.json).

## Diagnostic result

Seven of eight source posts have at least one confirmed semantic or structural defect. Under the frozen rubric, an eight-case diagnostic needs zero erroneous source posts; this packet does not meet that diagnostic threshold. It remains a diagnostic result only and cannot establish a population error rate or qualification result.
