# August recovery inventory, collection-table adoption and ChartEngine coverage

Verified 2026-10-20T17:52:39+09:00. Production web and harvest images both remain at `64b95c266d4af333ab7bfb2cc50744a98290e5f4`. This report uses production READ ONLY queries, deployed source and separately labeled G3 work in progress. No provider/model calls or application/database writes occurred.

## Do all sources use the collection tables?

**No: ordinary scheduled X harvesting is the important exception.** All five enabled non-X sources have shared collection jobs/runs in production. X has shared records for historical backfills, saved-data transfer and earlier probes, but none for its ordinary scheduled cycles.

| Source/path | Collection jobs | Collection runs | Meaning |
| --- | --- | --- | --- |
| Arena | 62 | 68 | Shared records exist |
| GitHub | 55 | 80 | Shared records exist |
| Hugging Face | 274 | 537 | Shared records exist |
| OpenCode | 190 | 287 | Shared records exist |
| OpenRouter | 86 | 92 | Shared records exist |
| X historical/backfill/probe paths | 20 | 199 | All 20 jobs have operation=x_backfill and mode=historical |
| X ordinary scheduled harvesting | 0 | 0 | Separate cycle/cursor/backlog/discovery records |

Artificial Analysis and Vercel AI Gateway are disabled in the source registry and have no shared jobs/runs. X is also disabled in that generic registry, while its independent Render harvest cron is active. That registry flag must not be interpreted as a suspended X cron.

The production database enforces the numeric lineage chain with NOT NULL columns and validated foreign keys: `metric_values.observation_id → collection_observations.run_id → collection_runs.job_id → collection_jobs.source_id`. This is structural proof for MetricValue rows, not a claim that every legacy source-specific table or all historical resource fields have migrated.

For X, 756 Posts published in the six hours before the inventory query had zero shared CollectionObservation memberships. Deployed CycleRunner records dedicated discovery runs for discovery lanes; ordinary A/B/C collection does not invoke the shared collection writer. G3 explicitly defers adding ordinary scheduled X collection recording in its current relational-refactor plan. Source-level job counts alone do not prove that every record or every old import path is covered.

## What remains for the August gaps?

The seven original recovery jobs are all completed. Each latest saved assessment is verified, all seven saved scopes are drained, no active collection run is attached and pending base translation/classification is zero. Their nonoverlapping window memberships total **13,491 Posts**. This rechecks current status and existing saved assessments; it does not rerun the full semantic enrichment verifier.

| Window | Publication interval UTC | Saved cohort Posts | Saved assessment | Pending base enrichment |
| --- | --- | --- | --- | --- |
| 1 | Aug 01 07:30 → Aug 02 04:15 | 1431 | verified | 0 |
| 2 | Aug 03 04:30 → Aug 04 05:00 | 3153 | verified | 0 |
| 3 | Aug 05 16:00 → Aug 06 12:30 | 2605 | verified | 0 |
| 4 | Aug 08 04:15 → Aug 10 05:45 | 2467 | verified | 0 |
| 5 | Aug 13 05:30 → Aug 13 07:30 | 198 | verified | 0 |
| 6 | Aug 16 02:15 → Aug 17 06:30 | 3238 | verified | 0 |
| 7 | Aug 27 03:15 → Aug 27 06:30 | 399 | verified | 0 |

**Completed jobs do not mean complete source coverage.** The actual scope receipts for all seven August jobs record B1/B2/B3/C1/C2/C3 and no A or RARE_EXTRA. The seventh scope is supplemental query work, not proof of the missing routes. Those omitted routes are concrete remaining collection scope. The later July job used the corrected v2 adapter and records A plus RARE_EXTRA; it does not retrospectively repair the August v1 campaign. Current list membership also cannot reconstruct historical list membership exactly.

A subsequent August recovery pass should preserve completed cohorts and enrichment, add the missing route coverage through the shared backfill path, and use measured shorter historical query windows where justified. It should keep actual versus raw/duplicate/rejected counts and existing run lineage, and enrich only new or genuinely incomplete records. This is additional acquisition, not reopening already-finished enrichment. Exact further population and attainable recall remain unknown.

August currently contains **161,781 Posts**. Every one of its 744 UTC hours contains at least one Post; that rules out wholly empty hours, not missing brands, quieter subintervals or search omissions. August 9 remains **1,712 Posts**, August 8 has 2,024 and August 16 has 3,051. The correctly reconciled August 9 staging transfer did not produce 782+1,660 disjoint records: 730 overlapped, leaving 1,712 total. The paid recall experiments establish that historical keyword results can omit accessible matching Posts. No rerun was launched during this inventory.

## DB-level qualification for pre-September X data

Owner requirement: ChartEngine must carry the limitation of X data published before September 1, 2026 when comparing historical and current releases or combining metrics from different sources. The qualifier belongs to **source/metric plus affected publication interval and collection scope**, with an assessment clock/evidence version. It is not a Boolean saying that each valid older Post is bad. September 1 is the selected warning boundary, not proof that every later period is complete.

Proposed storage direction for G3, **not implemented**: reuse CollectionJob for source/method/requested-scope identity, CollectionRun for the observed execution and coverage assessment, and CollectionScopeRun for affected scope/bounds where those semantics agree. G3 already proposes separate typed execution_state and coverage_state on runs/scopes. A successfully drained run can retain successful execution while carrying a coverage limitation. Reuse that design rather than adding a separate X/backfill table or another JSON payload. No new table or migration is selected here.

The exact typed reason/evidence mapping still needs agreement with G3. A known provider recall limitation, an actual measured omission, an unsearched route, a transport failure and missing enrichment are different facts. Do not use a generic runtime error to represent all of them or set a numerical recall percentage from our sample. Do not overwrite existing success receipts or immutable job definitions.

There is an additional reader requirement: range-level warnings must be discoverable even when there are no Posts, or legacy Posts have no shared observation link. ChartEngine cannot rely solely on joining each Post to its original run. The implementation must resolve applicable source/interval assessments as well as available per-record lineage. Requested query bounds, affected publication dates, retrieval times and the assessment time have distinct meanings; do not substitute one for another. If this needs a source-wide assessment activity, G3 must define its shared Job/Run semantics explicitly, without manufacturing successful historical harvest attempts or fake provider requests.

ChartEngine should retain actual observed counts, carry the qualifier into the saved chart inputs/result, and expose the limitation when comparing affected ranges. Missing collection is not evidence of zero activity; do not multiply historical counts by an assumed recovery factor. A recovered window or a later assessment should not silently rewrite the provenance of a previously frozen chart. Exact exclusion/normalization/default-eligibility behavior remains a ChartEngine design choice, not approved in this audit.

## G3/G2 coordination handoff

Current file scope: this root evidence report, bounded launch-index coordination and the existing backfill plan only; private read-only query receipts under the directory below. No peer model/migration/collector/chart file was edited. Proposed implementation scope to reconcile with G3/G2: scheduled X recording at the existing CycleRunner/shared-writer boundary; typed coverage/reason/evidence on shared run/scope storage; legacy/range-level lookup; ChartEngine reading and pinning those qualifiers. Preserve existing scheduled query shape, Post storage, cursor/backlog rules, keys, budgets and provider accounting.

G3’s current plan explicitly excludes ordinary scheduled X integration: the October 20 local G3 collection plan. Its proposed coverage_state fields are present only in the dirty implementation worktree, not in the deployed schema inspected here. This handoff records the new requirement; it does not claim that G3 has accepted or deployed an extension. Zero new tables are proposed by this audit; exact extensions await shared-design reconciliation.

## Evidence and limits

Private evidence on fuchitalee: `~/.local/share/render-operations/2026-10-20-august-resumption-inventory`. Includes deployed source blobs; Render live-SHA snapshot; actual column and FK introspection; current-inventory SQL/output/JSON; X job scope audit; numeric lineage constraints. SQL uses READ ONLY and 10–20-second per-statement deadlines; no Post text or secret values were printed. Source IDs and counters were inspected, not secret environment configuration.

Relevant prior evidence: [historical window study](2026-10-20-163017-august13-five-minute-window-comparison.md), [matched recent study](2026-10-20-164640-recent-fifteen-vs-five-minute-search-comparison.md), the October 17 backfill handoff. None establishes exhaustive X recall or eliminates the need to verify collection scope and processing separately.
