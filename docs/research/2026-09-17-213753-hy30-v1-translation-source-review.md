---
title: HY-MT2-30B-A3B V1 translation source review
date: 2026-09-17
type: research
status: terminal-not-qualified
---

# HY-MT2-30B-A3B V1 translation source review

This is a source-only review of the terminal frozen V1 diagnostic24 receipt.
It assesses produced target text against its source text. It does not invent
translations for null responses or infer content from provider token telemetry.
The closed 24-source, 72-locale machine-readable ledger is
`.context/model-task-20260917/hy30-translation-v1-diagnostic24-20260917-212807/source-grounded-review-v1.json`
(SHA-256 `e8c5da504625c843227cfe7954a7a6dd5a4add0bec200e064f5472f13963dbf1`).
Its span validator confirms every finding's source span and its one-field
target span are literal substrings of the frozen inputs and receipt.

## Receipt and coverage result

The receipt is
`.context/model-task-20260917/hy30-translation-v1-diagnostic24-20260917-212807/attempt-1.live/report.json`.
It contains 24 source rows and 55 target requests. Fifty requests have usable
content; five are harness-rejected empty answers. Four source rows have one or
more missing targets, so V1 fails the R113 coverage gate.

| Source post | Missing target(s) | Finding |
| --- | --- | --- |
| `2100079736537923768` | JA | provider empty answer |
| `2100262531788832809` | JA | provider empty answer; EN also changes `https://t.co/...` to `https://co/...` and emits a stray `[[PW]]` |
| `2100270972465008655` | ZH | provider empty answer |
| `2100277491390951481` | EN, JA | provider empty answer; produced ZH adds an imperative to use/subscribe to OpenCode that is absent from source |

The underlying raw records for these failures report HTTP 200 and `stop`, with
null final content and null reasoning. They are provider empty-answer coverage
failures, not retryable network errors.

## Confirmed semantic and structure findings

| Source post | Target | Source-grounded finding |
| --- | --- | --- |
| `2100058309072199756` | ZH, JA | `ENABLE SO MUCH` remains English rather than being translated as ordinary prose. |
| `2100245604027043870` | ZH, JA | Country names in the short ordinary-prose sentence remain `USA`, `China`, and `India`; this follows the source-derived glossary rather than translation intent. |
| `2100281384351015367` | JA | `free run` becomes `フリーラン` (freelance), changing the source meaning. |
| `2100306053913252315` | ZH | The model-list rendering rearranges labels/names, creating a structure and name-preservation concern. |
| `2100314574721315014` | ZH, JA | `ox Alpha` loses `ox`; ZH also retains a stray `[[PW1]]` marker. |
| `2100339358398058923` | ZH, JA | Ordinary words including `Likely`, `China`, and `Spain` are left untranslated. |
| `2100346971144036571` | ZH, JA | Both targets append a stray `[[PW1]]` marker. |
| `2100422464241013210` | ZH, JA | Sentence-initial ordinary prose (`Everyone`, `Apparently`) remains English, consistent with glossary over-preservation. |
| `2100430324899455118` | ZH | The Korean headline says Trump dismissed the slowdown argument while the U.S. should get ahead of China; output changes this to a claim that China must lead. This reverses the stated relation. |

The full receipt also retains outputs for the other twenty rows. This packet
does not count an error rate from the diagnostic sample: its selection was for
diagnostic coverage, and V1 already fails qualification on coverage.

The primary R113 count is 13 erroneous sources: the union of 11 confirmed
semantic-error sources and four coverage sources, with two sources in both
sets. There are zero additional-unknown sources. At locale level that is 19
confirmed semantic errors, five coverage failures, and 48 reviewed-good fields
(72 total). The separate semantic and coverage counts remain visible because a
provider-empty response is not a semantic translation error.

## Smoke8 corroboration

The separately frozen smoke receipt is
`.context/model-task-20260917/hy30-translation-v1-smoke8-20260917-212807/attempt-1.live/report.json`.
It has the same empty-answer shape on four of 19 target requests. Its source
review independently corroborates the diagnostic patterns: post
`2100262531788832809` has the shortened URL and stray marker; post
`2100314574721315014` loses `ox` and contains `[[PW1]]`; and post
`2100430324899455118` contains the same Korea-to-Chinese headline relation
inversion. Smoke also shows source-country names preserved in target prose and
an unsupported OpenCode subscription imperative in `2100277491390951481`.

## Configuration decision

V1 combines Tencent's terminology form with a derived glossary and an extra
marker-preservation instruction. The observed untranslated ordinary prose and
stray markers provide direct evidence to isolate a V2 prompt. V2 should retain
the model route, raw-text response shape, $0.074/$0.295-per-million frozen
caps, temperature 0.7, completion limit, and fallback prohibition; it should
replace that adapter with Tencent's delimiter-only template and omit the
derived glossary.

This would be a new configuration, not a retry. It should start with a new
frozen smoke contract. If its provider empty-answer behavior persists, do not
reinterpret V1 or retry requests. Consider a structured-output V3 only after
proving a supported response format can be decoded through the existing
harness without erasing raw-receipt evidence.
