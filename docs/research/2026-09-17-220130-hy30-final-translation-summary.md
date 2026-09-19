---
title: HY-MT2-30B-A3B final translation trial summary
date: 2026-09-17
type: research
status: diagnostic-parity-not-production-qualified
---

# HY-MT2-30B-A3B final translation trial summary

HY30 used its three authorized translation configurations on Tencent FP8 under
the saved $0.074/$0.295-per-million caps. Each configuration retained
temperature 0.7, no fallback, no retry, raw receipts, and the fixed 24-source
diagnostic cohort. No configuration is a retry or repair of an earlier answer.

| Configuration | Representation and change | Primary erroneous-source union | Actual cost | Diagnostic result |
| --- | --- | ---: | ---: | --- |
| V1 | raw text, Tencent terminology form plus derived glossary | 13 | $0.006524279 | no parity |
| V2 | raw text, delimiter-only form without glossary | 7 | $0.005370665 | [7,7] conservatively at parity with incumbent [7,8] |
| V3 | structured translation lines / JSON object, existing marker restoration | 6 | $0.005762573 | [6,6] improves on the incumbent confirmed lower bound of 7 |

V3 froze 55 requests in
`.context/model-task-20260917/hy30-translation-v3-diagnostic24-20260917-215842/contract.json`
(contract SHA-256 `6e291739bc7ab7e3576e532a83cee94b8ea602590c73849351e4f0e44f46edb7`; source rows SHA-256
`74219a66999da3ddf98ae32ca501f5084047821a74390f1aa7b48bc0b75542db`).
All were consumed once. The report SHA-256 is
`ae5eb1e62c01fe87005fd36749b66a5aff88ca28b9a199e1b9c2c2fc2337801c`.
It records zero retry, zero fallback, and no database touch; 27,312 input and
12,683 output tokens; 46.455 seconds from started receipt to report mtime; and
23 complete posts with 8.414-second p95 and 44.025-second maximum post
latency.

The V3 closed source review is
`.context/model-task-20260917/hy30-translation-v3-diagnostic24-20260917-215842/source-grounded-review-v3.json`
(SHA-256 `2d1761c54dbe897bd4f5a5b018ac82920d16f86f0b1ae205fef2af0be44d9033`).
The versioned parent-requested amendment is
`.context/model-task-20260917/hy30-translation-v3-diagnostic24-20260917-215842/source-grounded-review-v3-amendment-v1.json`.
All 72 locales are classified and every cited source/output span validates as a
literal substring. It has six semantic sources, one coverage source, zero
additional-unknown sources, and a primary union of six. At locale level: nine
semantic errors, one coverage failure, 62 reviewed-good fields.

The JSON-object representation eliminated V2's fabricated delimiter blocks,
provider-null content, and long-response truncation. The remaining coverage
failure is a source-identical English output rejected by the literal
translation validator. The amended semantic findings include a one-tenth price
rendered as 10% off; Chinese language-model `Tokens` rendered as crypto-style
`代币`; an added English call to action; speaker and imperative changes in the
Codex/OpenCode post; the Japanese `free run` meaning; Chinese `ox Alpha`
translation; and the Chinese Trump-China headline relation. Japanese
`オックス・アルファ` is permitted transliteration, and generic `30分钱` is not
treated as a national-currency assertion.

V3 establishes diagnostic evidence only. It is not production-qualified
because this is one small, consumed diagnostic cohort and no broader
qualification has been completed. The reason is not that diagnostic parity
cannot include errors: V2 and V3 show why the primary-union bound and separate
semantic/coverage accounting must both remain visible.
