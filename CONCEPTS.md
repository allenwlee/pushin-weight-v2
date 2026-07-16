# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## x-monitor pipeline

The x-monitor service ingests social-media posts about AI/LLM brands, classifies them, and persists the results. The vocabulary below is scoped to the run-summary layer that operators read at the end of each pipeline run.

### Run summary

The JSON document emitted by `x_monitor run` after one pipeline execution. It carries the per-call result rows, the run totals, and a `degraded` block that flags known-acceptable operational degradations (for example, a brand whose keyword table is empty). Operators read this to decide whether a run succeeded.

A `degraded` block with entries is a *signal*, not a failure — entries name known conditions the pipeline tolerated, and an empty block is the cleanest signal.

### Call

One execution of a fetch+classify cycle. Calls are identified by short string codes (`A`, `B1`, `B2`, `B3`, `C1`, `C2`) chosen at planning time. The run-summary's per-row `query_id` field carries the same code.

The codes partition into three shapes by intent: `A` is a curated-list pull, the `B` family is a wide-net brand-token search, and the `C` family is a co-occurrence (AND-filter) search over polysemous brands.

*Avoid:* query id, query_id — these were the legacy names that carried `Q`-string ids before the planner adopted the current short-code scheme.

### Brand keyword

A token (or token OR-chain) associated with a single brand, used by the pipeline's keyword index to match candidate posts. Each brand has one primary keyword chain used by default, and may carry additional non-primary chains.

The primary chain is what the pipeline reads for a brand-wide call; non-primary chains exist for future routing needs.

### Brand keyword gap

A state where a brand listed in the pipeline's enabled-models set has no primary brand-keyword row. A gap surfaces in the run summary as a per-brand `missing_brand_keywords:<brand>` entry rather than blocking the run.

The pipeline tolerates gaps so a partial keyword table still produces a run summary; closing a gap requires adding the row, not relaxing the check.

### Classification upsert

The act of writing one `(post, brand, post_type, sentiment)` triple into the classification store. If the triple already exists, the write becomes an update on the same row.

The store keeps a run-level counter of upserts attempted (which counts both new inserts and updates). That counter answers "did the classifier run?", not "how many new rows landed in the DB?" — a row updated twice still counts twice.

### Post-fetch classification

A second classification pass that runs after the initial fetch+classify loop completes, used to re-classify posts against the full brand set once translation and other enrichments are done. The post-fetch pass writes to the same classification store as the inline pass, so a single per-post triple can be written by both passes.

Because post-fetch runs after the per-call loop, any run-summary counter that snapshots inside the loop will miss post-fetch writes. The snapshot must happen after post-fetch completes.

### Operator-degraded entry

A named key in the `degraded` block of the run summary, signaling that a known condition was tolerated rather than treated as a failure. Naming convention: `<condition>:<detail>` so operators can pattern-match by condition prefix.

The pattern matters because operators triaging failures want to grep a stable prefix (e.g., `missing_brand_keywords:`) rather than read full messages.

## Flagged ambiguities

- "query id" was used for both the v1.6 `Q`-string ids (`Q1`..`Q6`) and the v1.7 short-code call ids (`A`, `B1`..`C2`). The v1.7 call id is canonical; `Q`-string references in older docs are historical-only.
- "call" was used for both the *plan* unit (one fetch+classify cycle) and the *type* (account vs brand-wide). Both are in use; the type is named "call kind" to disambiguate.
