# Why-first headline evaluation

- Run: `2026-08-15-owner-approved-why-first-schema-rerun-v2`
- Model: `deepseek-v4-pro`
- Calls used: 28
- Stop reason: `completed`
- Accounted input tokens: 207468
- Accounted cost: $0.100828

The JSON sibling is the reproducible machine record and contains reviewed
verdicts for all nine rubric fields on every call. Raw provider output remains
unchanged.

## Editorial decision

- Schema-valid outputs: 8 of 28, improved from 0 of 28 after the schema-shape
  prompt repair.
- Fully accepted diagnostic outputs: 2 of 28
  (`pairwise:pair-10:e12:c1000` and `pairwise:pair-14:e12:c1000`). Both led
  with recurring download and intelligence reports shared across independent
  sources and avoided suppressed comparisons.
- Remaining failures: six weak recurring explanations, four schema failures,
  four quantitative-family mismatches, three false event-anchor requirements,
  two weak evidence-only entities, and one unselected-candidate claim.
- Quality plateau: none. Every evidence budget retains critical failures.

## Boundary defects found

- Synthetic evidence IDs were reused across DeepSeek and MiniMax, unlike the
  globally unique production evidence contract.
- Low-data-quality scenarios set `comparison_allowed: false` but still exposed
  non-null change values in family facts.
- Recurring validation checked independent sources but did not require those
  sources to share a semantic theme.
- The Chinese event detector interpreted ordinary “users posted” wording as a
  product-release event because both use `发布`.

These defects are corrected in the next evaluation epoch. No evidence budget,
materiality band, or release policy is frozen from this run.
