# Why-first headline evaluation

- Run: `2026-08-15-owner-authorized-why-first-v1`
- Model: `deepseek-v4-pro`
- Calls used: 28
- Stop reason: `completed`
- Accounted input tokens: 208472
- Accounted cost: $0.109000

The JSON sibling is the reproducible machine record and contains the reviewed
verdict for all nine rubric fields on every call. Raw provider output is
retained unchanged even when validation failed.

## Editorial decision

- Publishable outputs: 0 of 28. Every response failed with
  `headline_output_schema_invalid`.
- Quality plateau: none. The 4, 12, 24, and 48 evidence budgets are all
  rejected for policy selection because no budget produced a schema-valid
  output.
- Why-first signal: strong-content cases frequently led with the supplied
  download and intelligence reports, so the editorial hierarchy was visible
  in raw prose. That signal cannot override the publication contract.
- Selection failure: 27 of 28 raw responses selected both measured candidates,
  including ordinary and quiet comparisons where the contract defaults to one.
- Schema failure: all responses emitted subject names instead of subject
  objects and used `null` for `event_anchor`; many also exceeded the maximum of
  four evidence IDs or eight quantitative fact IDs per claim.
- Bilingual review: 27 raw headline pairs preserved the same diagnostic
  judgment. `pairwise:pair-16:e48:c1000` changed English “more useful” into
  Chinese “more intelligent” and failed parity.

## Configuration decision

- Evidence floor and ceiling: not frozen from this run.
- Materiality bands: not frozen. The separate read-only calibration has no
  usable engagement samples in any window and no usable 365-day samples in any
  family, so it fails the all-window release gate.
- Prompt remediation: version `headline-v7-why-first-schema-bounds`, publication
  epoch 7, now specifies measured-subject object shape, empty-string event
  anchors, bounded representative citations, and exceptional two-candidate
  selection. Focused mocked regression tests pass; a newly authorized live run
  is still required to measure model adherence.
- Owner verdict: execution was authorized; editorial and release acceptance
  remain pending after a successful bounded rerun.
