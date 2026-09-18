---
title: Translation attempt E blind review
date: 2026-09-17
task: translation
packet: review-packet-e.json
scope: 8 posts × 3 locales
status: does-not-qualify
---

# Translation attempt E blind review

## Result

All 24 required locale outputs were present and marked successful. The review found confirmed defects in 4 of 8 source posts (50.0%) and 8 of 24 locale outputs (33.3%): 7 material and 1 minor. This diagnostic therefore does not qualify; an eight-post diagnostic requires zero erroneous source posts.

| Locale | Confirmed erroneous outputs | Rate |
| --- | ---: | ---: |
| English | 2 / 8 | 25.0% |
| Simplified Chinese | 2 / 8 | 25.0% |
| Japanese | 4 / 8 | 50.0% |

The detailed, exact-span record is `.context/model-task-20260917/review-e.json`.

## Confirmed failure patterns

1. A positive French colloquialism ("c'est quoi ce poulet") was rendered as criticism in all three targets. In this context it expresses surprise at an exceptionally good offer, so "nonsense," "这是什么鬼," and "なんだこのザマ" reverse the stance.
2. Japanese translated the code-mixed entity names `Union Alpha` and `ox Alpha` as ordinary words. That turns a model/entity comparison into a comparison of different names.
3. Japanese inserted a line break after a handle even though the source was a single line.
4. The Korean headline phrase `중국 앞서야` means getting ahead of China. All three targets instead make China the party that must lead. The parameter figure remains correctly preserved: `49억` is 4.9 billion, not 49 billion.

## Prompt remedies for a future attempt

- Preserve model, product, organization, and code-mixed entity names verbatim unless their status as ordinary language is clear. Do not translate components of a name such as `ox Alpha`.
- Translate idioms by their local pragmatic meaning and author stance. Before using a negative phrase for a foreign-language idiom, check whether it is colloquial praise, surprise, or approval.
- For every comparative headline, explicitly preserve the actor, comparison target, and direction: `get ahead of China` must never become `China must lead`.
- Treat line breaks and paragraph boundaries as immutable transport data. Emit the same boundary sequence, except for explicitly designated protocol markers.
- For price promotions, retain both equivalent forms when supplied: one-tenth of price and 90% off are consistent, and neither should be converted into a different discount fraction.

No third translation call was made or recommended by this review.
