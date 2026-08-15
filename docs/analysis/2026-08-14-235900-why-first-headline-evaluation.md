# Why-first headline evaluation

- Run: `2026-08-15-owner-approved-why-first-quantitative-color-v5`
- Model: `deepseek-v4-pro`
- Calls used: 28
- Stop reason: `completed`
- Accounted input tokens: 257296
- Accounted cost: $0.125817

The JSON sibling is the reproducible machine record with every bilingual output
editorially reviewed. All 28 generated headlines are reproduced in the
[readable quantitative headline appendix](2026-08-14-235900-why-first-headline-samples.md).

## Quantitative contract result

The corrected matrix fixed the prior evaluation gap:

- 28 of 28 packets supplied quantitative facts for both candidates;
- every packet supplied 24 bounded display-ready facts;
- 28 of 28 outputs cited at least one headline quantitative fact;
- 27 of 28 English headlines visibly rendered a percentage;
- the one omission was rejected as
  `headline_output_quantitative_fact_unused_or_unaligned`.

The quiet sentinel now measures a 0.1% DeepSeek volume increase against a flat
MiniMax comparison. Low data quality represents 80% selected and prior
coverage, above the 75% comparison threshold, rather than suppressing all
percentage changes. True comparison suppression remains a separate unit test.

## Editorial decision

**The quantitative test contract passes, but activation remains rejected.** Six
quiet-window outputs were editorially publishable. No high-content why-first
scenario passed both deterministic validation and editorial review in this
run. The one schema-valid high-content pairwise output used plural user
reporting despite its one-source low-independence fixture, as did three valid
evidence-count outputs. Those are critical evidence-confidence failures.

Ten outputs passed deterministic validation. The other 18 failed with four
incomplete headline candidate sets, three English primary-order failures, two
missing English subjects, two overlong English headlines, two weak explanation
support failures, and one each for missing evidence family, unaligned quantity,
invalid schema, undeclared entity, and Chinese primary order.

## Resource accounting

- All 28 authorized calls completed sequentially.
- Provider-reported input usage totaled 257,296 tokens.
- Accounted cost was $0.125817, below the $0.80 stop boundary.
- No production writes, harvesting, publishing, or scheduled-worker actions
  occurred.

The evidence policy and materiality policy remain inactive. The next design
problem is evidence semantics and candidate/subject encoding, not missing
quantitative values or excerpt count.
