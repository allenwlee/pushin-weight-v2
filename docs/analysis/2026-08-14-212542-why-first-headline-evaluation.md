# Why-first headline evaluation

- Run: `2026-08-15-owner-approved-why-first-support-rerun-v3`
- Model: `deepseek-v4-pro`
- Calls used: 28
- Stop reason: `completed`
- Accounted input tokens: 214056
- Accounted cost: $0.105817

The JSON sibling is the reproducible machine record with all 28 bilingual
outputs editorially reviewed.

Five outputs were publishable: both quiet-window sentinels at four excerpts,
the pairwise high-content/high-evidence outputs at 12 and 24 excerpts, and the
corresponding 12-excerpt high-content result. They either stated the supported
absence of a recurring theme or led with the recurring downloads-and-
intelligence explanation. One accepted output used MiniMax's cited 45% volume
rise as secondary color.

The remaining 23 outputs were not publishable. Deterministic validation found
nine weak recurring explanations, five invalid evidence-confidence choices,
three missing English subjects, two isolated-event claims without an event,
one malformed schema, one unused or unaligned quantitative fact, and one
causal-language rejection. Review also rejected the otherwise schema-valid
12-excerpt quiet-window output because it called movement small while
comparison was suppressed.

This run identifies four bounded corrections for the next and final rerun:

- hide all prior-window and change inputs from the provider when comparison is
  suppressed;
- reserve `aggregate_only` for claims with no evidence IDs;
- reserve `isolated_event` for a concrete linked event with a nonempty anchor;
- make the weak-evidence fixture explicitly repeat one source instead of
  calling each excerpt an independent report.
