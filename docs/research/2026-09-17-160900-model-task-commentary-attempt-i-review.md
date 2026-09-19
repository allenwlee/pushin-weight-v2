# Commentary attempt I: blind review

**Date:** 2026-09-17  
**Scope:** Eight supplied posts and their stored EN, Simplified Chinese, and Japanese commentaries.  
**Method:** Source-only review using `.context/model-task-20260917/review-rubric.md`. No links were opened, no external facts were added, and no model identity was inferred from opaque names.

## Result

Six of eight source posts have a confirmed commentary defect in all three locale outputs. The other two posts have all three locale outputs recorded as reviewed good. There are no unresolved findings.

This is a diagnostic, not an estimate of population error. At eight posts, the qualification threshold requires zero erroneous posts; this attempt does not qualify.

| Result | Source posts | Outputs |
| --- | ---: | ---: |
| Confirmed defect | 6/8 | 18/24 |
| Reviewed good | 2/8 | 6/24 |
| Unknown | 0/8 | 0/24 |

## Confirmed failure modes

- The commentary expanded opaque terms into alleged meanings or product identities, then used those inventions to draw conclusions about countries, society, or technical capability.
- It inferred political or ecosystem intent from tags alone.
- It changed a colloquial French expression of delighted amazement into skepticism, assigned an unstated currency, and treated the phrase literally.
- It attached a group, insult, and self-deprecating intent to an opaque mocking comparison without source support.
- It reassigned a 20%-to-55% OpenRouter token-share statistic for Chinese models generally to one Tencent model. The source gives that model a separate figure: more than 18 trillion processed tokens.

## Short prompt changes to test later

1. Do not define or identify an unfamiliar term, codename, handle, or product from outside the supplied text. Keep it opaque unless the source explains it.
2. Treat tags and links as identifiers only. Do not infer affiliations, motives, politics, credibility, capabilities, or outside context from them.
3. Preserve idioms, speaker stance, uncertainty, qualifiers, comparison subjects, and the scope of every statistic. Do not supply an unstated currency.
4. When the post provides too little basis for broader significance, give a short literal explanation rather than a speculative one.

These changes are recommendations from the review only. No additional model-review calls were made.

## Record

The machine-readable, per-output record is `.context/model-task-20260917/review-i.json`. Each finding includes exact source and output spans, a source-grounded explanation, and a defensible correction.
