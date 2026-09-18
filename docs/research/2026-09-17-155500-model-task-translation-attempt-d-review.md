---
title: Translation attempt D blind review
date: 2026-09-17
scope: packet D, eight supplied posts, EN / Simplified Chinese / Japanese
status: diagnostic
---

# Translation attempt D blind review

This is a source-context-only fidelity and coverage review of the eight posts in review packet D. It is a diagnostic, not a population estimate or a qualification result.

All 24 required locale outputs were assessed. Six of eight source posts have at least one confirmed material defect. Nine locale outputs are affected, with ten findings because the Korean post's Simplified Chinese output has two independent errors. Fifteen outputs are explicitly recorded as reviewed good in `review-d.json`; there are no unresolved findings.

The recurring failures are narrow and actionable:

- Keep discount framing mathematically consistent: a price of one tenth means 90% off, while a 10% discount leaves 90% to pay.
- Translate colloquial idioms for their intended praise rather than their literal noun; this packet's French `poulet` means an exceptionally good thing in context.
- Treat a source-language copy in a different requested locale as missing translation coverage, even if `translation_failed` is false.
- Preserve speaker sentiment and proper-name order when compressing informal posts.
- Preserve comparison grammar: the Korean headline says Trump urges getting ahead of China. It does not say that he urges leading China.
- Do not narrow a general attribution to a named company when the source names a broader group; the Korean body says Chinese models, not Tencent models, for the OpenRouter token-share statistic.

These are review findings only. They do not call for extra model calls, source fact-checking, or application-code changes. The machine-readable record is `.context/model-task-20260917/review-d.json`.
