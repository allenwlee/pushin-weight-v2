---
title: HY-MT2-30B-A3B V1 to V2 translation summary
date: 2026-09-17
type: research
status: diagnostic-parity-not-production-qualified
---

# HY-MT2-30B-A3B V1 to V2 translation summary

HY30 was assessed only for translation on the fixed Tencent FP8 route under
the saved $0.074/$0.295-per-million caps. Both paid configurations used the
same frozen diagnostic24 sources, temperature 0.7, raw provider receipts, no
fallback, and no retries.

V1 (`hy_mt2_native_terminology`) used a source-derived glossary. It completed
50 of 55 target requests, had four coverage sources, and its closed review
found 11 semantic sources and 13 primary erroneous sources in the semantic-or-
coverage union. It did not establish diagnostic parity. Its glossary preserved
ordinary English/country terms, and outputs also showed URL/marker corruption,
unsupported additions, and a Korean-headline relation inversion.

V2 removed that glossary and used Tencent's delimiter-only template. It
completed 53 of 55 target requests, had two coverage sources, and cost
$0.005370665. Its closed review found six semantic sources, no additional
unknowns, and seven primary erroneous sources in the union. That is a [7,7]
diagnostic interval against the supplied incumbent's [7,8] interval, so V2
meets conservative diagnostic parity by the stated bound.

This is not a production qualification. The V2 diagnostic still has seven
erroneous sources. It retains a null-content provider response and an
over-limit partial response; its delimiter instruction also caused fabricated
marker blocks and added text on unmarked inputs. V3 is justified only as a
separate structured-lines/JSON-object representation test that proves marker
restoration through the existing harness. It must not retry, patch, or infer
any V1/V2 answer.

The durable receipts and reviews are:

- V1: `docs/research/2026-09-17-212807-hy30-translation-trial.md` and `.context/model-task-20260917/hy30-translation-v1-diagnostic24-20260917-212807/source-grounded-review-v1.json`.
- V2: `docs/research/2026-09-17-214317-hy30-v2-translation-contract.md` and `.context/model-task-20260917/hy30-translation-v2-diagnostic24-20260917-214317/source-grounded-review-v2.json`.
