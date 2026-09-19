---
title: HY-MT2-30B-A3B V2 diagnostic24 contract
date: 2026-09-17
type: research
status: terminal-not-qualified
---

# HY-MT2-30B-A3B V2 diagnostic24 contract

This is the second and distinct HY30 translation configuration. Its terminal
receipt follows below. The frozen contract is
`.context/model-task-20260917/hy30-translation-v2-diagnostic24-20260917-214317/contract.json`
(file SHA-256 `1c6fafc6e1830596fb1b6b47df1108a46d93ee405245541eaecd817dc270bac7`).

It freezes 24 sources and 55 locale requests, reserves $0.037146947 at the
saved $0.074/$0.295-per-million catalog caps, and has contract SHA-256
`17816d200d85802957f63814f8460ff79ace36918a9a62574d73e47b5e9e09b1`.
The profile SHA-256 is
`e8a87f403dc16c2d26b74bf142e6e20252a552f88d50b5af7880a37a5d864e8d`.
It uses Tencent FP8, raw text, temperature 0.7, a 180-second timeout, no
fallback, and no retry. The contract is diagnostic24-only: it does not repeat
the consumed smoke8 cohort.

## Verbatim V2 prompt form

Each frozen request uses this exact user-message form, replacing only
`{target language}` and `{marker-delimited source payload}`:

```text
Please accurately translate the following text into {target language}. You must retain the exact same number of delimiters in the translation as in the original text. Do not omit, escape, or translate any delimiters. Preserve their original placement. Delimiters are the supplied [[PW...]] and [[PQ...]] markers. Output only the translated text without any additional explanation:

{marker-delimited source payload}
```

The contract retains every fully rendered prompt verbatim in its `requests`
array. This template removes V1's source-derived terminology glossary while
keeping the route, caps, sampler, raw-text response shape, and execution
limits unchanged.

## Execution boundary

Run only after the serialized Qwen direct lock handoff. Preserve raw receipts,
actual billed usage, coverage accounting, and a closed 24-source/72-locale
source review. The primary result must report the union of semantic and
coverage failing sources, alongside the separate counts. A response-format V3
is not prepared by this contract; it is a contingent hypothesis only if V2
still demonstrates a recoverable format/null-content problem.

## Terminal V2 receipt and closed review

The serialized attempt is terminal at
`.context/model-task-20260917/hy30-translation-v2-diagnostic24-20260917-214317/attempt-1.live/report.json`
(SHA-256 `de7a47ea5290631a7c3c4d8c697f82b35dd8a65a8f8fd3ab3e800fd57d2d876d`).
All 55 frozen requests were consumed once. It records zero retries, zero
fallbacks, and no database touch. Summed raw provider usage is 16,985 input
tokens, 13,945 output tokens, and **$0.005370665 actual billed cost**.

Two source rows fail coverage. Post `2100270972465008655` has an HTTP 200
`stop` response with null content and null reasoning (25 billed output tokens,
all recorded as reasoning telemetry). Post `2100079736537923768` has an HTTP
200 `length` response that reached the 4,096-token completion cap and is
incomplete. These are provider-result coverage failures, not network failures,
and neither received a retry.

The closed 24-source/72-locale review is
`.context/model-task-20260917/hy30-translation-v2-diagnostic24-20260917-214317/source-grounded-review-v2.json`
(SHA-256 `2c681913289915dd4963fa4a94c66c5396f2f5052d0073fab1ff315a7bd0f676`).
It validates each cited source and one-field output span literally. It finds
six semantic-error sources, two coverage sources, and zero additional-unknown
sources. The primary R113 union is **seven erroneous sources** because one
source has both a semantic and coverage defect. Locale counts are 12 confirmed
semantic errors, two coverage failures, and 58 reviewed-good fields.

Removing V1's glossary corrected its ordinary-English preservation and the
Korean headline direction finding, but the delimiter-only instruction creates
new fabricated delimiter blocks and extra content on otherwise unmarked input.
It also leaves the null-content behavior present and reaches the completion cap
on one large marked post.

Against the supplied S3 incumbent interval of 7–8, V2 has no additional
unknown sources and its primary diagnostic interval is [7,7]. Its upper bound
therefore does not exceed the incumbent's confirmed lower bound of seven: this
establishes **diagnostic conservative parity only**. It is not production
qualified: the diagnostic still contains seven erroneous sources, and parity
on one consumed diagnostic cohort is not a release or adoption decision.

## V3 hypothesis

The endpoint advertises `response_format` and `structured_outputs`. A final
V3 may be warranted because the observed faults are response-shape faults:
fabricated delimiter blocks, a null final content response, and one truncated
long marked response. It must use a new, frozen structured-lines response
format only if the existing harness can first prove decoding and exact marker
restoration from the raw response. It is a distinct third configuration, not a
retry or repair of V2, and must retain raw receipts and the same price caps.
