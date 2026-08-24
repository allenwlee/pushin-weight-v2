---
date: 2026-08-15
topic: quantitative-headline-evaluation-contract
---

# Quantitative Headline Evaluation Contract

## What We're Building

Every synthetic headline scenario will contain comparison-safe percentage-change
facts, and every generated headline will use at least one cited fact as supporting
color after the content-derived explanation. Low data quality remains a scenario
dimension, but represents sufficient near-threshold coverage rather than total
comparison suppression.

## Why This Approach

The rejected run conflated low data quality with unavailable comparison: 20 of
28 calls had no projected quantitative facts, only eight cited any fact, and
only six displayed a percentage. Keeping those cases in the core matrix cannot
evaluate the intended why-plus-validation product contract.

Selected-window percentages for suppressed comparisons were considered, but
they would not test the requested change metrics. Leaving percentage use as an
optional editorial rubric was rejected because the model already omitted it in
otherwise usable outputs.

## Key Decisions

- Core scenarios always permit comparison and project percentage-change facts.
- High coverage is complete; low coverage is near the configured minimum but
  still sufficient.
- Quiet scenarios use a small 0.1% lead versus a flat comparison rather than a
  contradictory 0% versus 5% setup.
- The headline claim must cite and display at least one quantitative fact when
  the selected candidate has one.
- Content remains first; a percentage can validate the story but cannot replace
  the why.
- Comparison suppression remains a separate deterministic fail-closed test.

## Open Questions

None. The user explicitly requires quantitative evidence in each test.

## Next Steps

Update the existing implementation plan and harness, run deterministic
regressions, then preflight a newly bounded live evaluation before any provider
transport.
