---
title: Hy-MT2-30B-A3B translation trial contract
date: 2026-09-17
type: research
status: v1-complete
---

# Hy-MT2-30B-A3B translation trial contract

Hy-MT2-30B-A3B is a translation-only candidate. V1 completed its frozen
smoke8 and diagnostic24 contracts. It did not meet the R113 coverage gate and
does not qualify as a translation candidate on this evidence.

## Route and pricing evidence

The frozen catalog price authority is
`docs/research/2026-09-17-143812-openrouter-pricing-snapshot/models.csv`,
captured September 17. Its `tencent/hy-mt2-30b-a3b` row supplies the request
caps: $0.074 per million input tokens and $0.295 per million output tokens.

The additive public endpoint capture is
`docs/research/2026-09-17-212537-hy30-endpoints/manifest.json`
(SHA-256 `958b92c9bbc86ccd92e3f42f5c6a22072e137427b6c566591bb9172a8228e2cf`).
It received HTTP 200 from the public endpoint-metadata API and returned one
route: Tencent `tencent/fp8`, FP8, upstream
`tencent/hy-mt2-30b-a3b-20260521`, 8,192 context tokens and a 4,096-token
maximum completion. Its accepted controls are `temperature`, `stop`,
`max_completion_tokens`, `max_tokens`, `response_format`, and
`structured_outputs`. The capture contains no credential or inference request.
Its returned token rates match the frozen catalog caps; they are retained as
metadata and do not replace the saved pricing authority.

Tencent’s official [Hy-MT2 repository](https://github.com/Tencent-Hunyuan/Hy-MT2)
documents the 30B-A3B family member, full target-language names, a single-user
translation prompt, terminology and delimiter forms, no default system prompt,
and 4,096 maximum generated tokens. Its documented local decoding settings for
30B-A3B are temperature 0.7, top-p 1.0, top-k -1, repetition penalty 1.0 and
4,096 maximum tokens. The pinned OpenRouter endpoint exposes temperature but
does not advertise the other three sampler controls, so the prepared profile
sends only supported temperature 0.7 and completion limits.

## Frozen starting profile

`hy30_translation_v1` has profile SHA-256
`51943b4a8d80b5e65071d182d243cd8aade459d292c93cc4ddf205f285fd10a7`.
It is raw-text literal translation, pins Tencent FP8 with fallback disabled,
has a 180-second timeout and maximum three simultaneous requests, and sends no
reasoning or unsupported sampler fields. It uses the existing
`hy_mt2_native_terminology` adapter: one user message, full target-language
name, a deterministic glossary of up to eight source-visible capitalized or
version-bearing terms mapped to themselves, explicit `[[PW...]]` marker
preservation, and no answer-fed glossary or semantic repair.

This is a native-template baseline. The prior 1.8B and 7B trials found
source-fidelity failures in price fraction, idiomatic praise, unspecified
currency, product-name preservation and relation direction; 7B also malformed
one terminal marker. Those failures motivate review axes but do not establish
that HY30 will repeat or resolve them. A delimiter-template change is reserved
for a separately frozen profile only if this baseline shows structural evidence.

## Prepared contracts

| Cohort | Contract | Sources / requests | Reservation | Contract SHA-256 |
| --- | --- | ---: | ---: | --- |
| smoke8 | `.context/model-task-20260917/hy30-translation-v1-smoke8-20260917-212807/contract.json` | 8 / 19 | $0.010874456 | `551662a23e53420d888f736f19459e5771096d004d2af7b7c60da0bf4ce0306a` |
| diagnostic24 | `.context/model-task-20260917/hy30-translation-v1-diagnostic24-20260917-212807/contract.json` | 24 / 55 | $0.037168555 | `60436937a5e34b4b9ca22b82a1303aea540876677857e770ddd56291b769bbfb` |

Both cohorts derive from `.context/u20/random100-live-input.json`, whose
frozen source SHA-256 is
`862076a5a39f04fd9f41441f7fe616cc317446a365a7ed617f0d17f44310c833`.
They are consumed development diagnostics, not a prevalence estimate or fresh
qualification sample. Their contracts retain their own source-row, caller,
request and contract hashes.

## V1 execution receipt and source-only review

The locked, serialized paid execution consumed every frozen request once, with
zero retries, zero fallbacks, and no database touch. Smoke8 received 15 of 19
requests and recorded $0.001176595 from 4,375 input and 2,891 output tokens.
Diagnostic24 received 50 of 55 requests and recorded $0.005347684 from 17,101
input and 13,838 output tokens. The raw receipts are retained at
`.context/model-task-20260917/hy30-translation-v1-smoke8-20260917-212807/attempt-1.live/report.json`
and
`.context/model-task-20260917/hy30-translation-v1-diagnostic24-20260917-212807/attempt-1.live/report.json`.

The harness labeled four smoke and five diagnostic requests as `transport`.
They were not network exceptions: each inspected failure is an HTTP 200,
`finish_reason: stop` provider response with `message.content: null` and
`reasoning: null`, despite nonzero billed completion/reasoning telemetry. This
is distinct provider empty-answer coverage failure; neither its billed tokens
nor absent reasoning text is treated as a translation. Four diagnostic source
rows consequently miss at least one target: `2100079736537923768` (JA),
`2100262531788832809` (JA), `2100270972465008655` (ZH), and
`2100277491390951481` (EN and JA). This alone fails R113 coverage.

The source-only semantic packet is
`docs/research/2026-09-17-213753-hy30-v1-translation-source-review.md`. It
also records confirmed marker/URL corruption, unsupported additions, ordinary
prose left untranslated by the source-derived glossary, and a Korean headline
relation inversion. These are review findings, not an inferred reconstruction
of any empty response.

V2 is warranted as a new, separately frozen prompt configuration: retain the
same route, caps, raw-text response shape, temperature and no-fallback policy,
but use Tencent's documented delimiter-only native template and remove the
derived glossary. That directly addresses the observed glossary interference
and marker complexity. It cannot repair a V1 empty response; a structured
output V3 is only worth preparing if V2 still shows provider empty answers and
the harness can prove it will decode the endpoint's supported response format.
