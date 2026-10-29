# Product-release intake — review and verification

Date: 2026-10-29 JST  
Scope: main `c445ec24` through application revision `5e3c475e4d42c776b9d8d33aecd2d56dc5dfb26d`  
Plan: [selected staging slice](../plans/2026-10-28-083502-feat-product-release-intake-20261027-plan.md)

The implementation supports the selected staging study. No blocking code finding remains from this review. Production activation, autonomous targeted source acquisition and TN writing are separate work.

## Intent and coverage

Review performed inline in the same session, as required by the owner's tool mapping and session-only model restriction. This is not an independent peer/model review. Examined correctness, schema ownership, migration safety, identity/replay, security, performance, operational reliability, maintainability, adversarial inputs and regression coverage across the complete feature diff. The source-to-command-to-writer-to-reader path was traced; no simulated service output is presented as a staging run.

The four new tables have distinct record meanings: an intake disposition, an immutable numerical calculation, its categorical counts, and a dossier's dated use of that calculation. No new JSON columns, full-population Post membership table or source-specific candidate identity was introduced. Existing dossier, evidence, Product, publisher and discovery records remain authoritative. Database guards enforce ownership, immutability, sealed counts and merge-cycle prevention. The migration is additive; rollback disables new entry points while retaining history.

## Corrections verified

- Bound historical Post queries by their time-filtered ID population before loading wide enrichment; the previous plan scanned the wrong index and timed out. The fixed staging census completed 265,340 Posts.
- Require actual availability evidence before an available-state review. Require publisher identity, account control and the existing verified ownership relationship before announcement confirmation.
- Restrict the report to the selected review's accepted/uncertain claims; later unreviewed evidence cannot inherit an earlier confirmation.
- Reject future research/effective dates and invalid rank categories; preserve date-only precision and unknown lineage.
- Preserve source-supported unknown publisher observations in the existing discovery flow; no affiliation inferred from upstream model tags.
- Balance representative sources across time segments before classification/engagement diversity; cap repeated authors and expose partial follow-up.
- Label every discussion comparison with its exact anchor claim, milestone type, value and precision. Browser review caught an ambiguity between announcement and availability windows; `5e3c475e` corrects it.

## Executed evidence

- `f85f67f7`: 83 focused tests passed, including 47 PostgreSQL-required tests; zero required skips/errors. Coverage includes detector, replay, real source/persistence paths, milestones, strict study input, numerical reuse, review readers and dossier invariants.
- `5e3c475e`: 14 report/study tests passed, including 11 PostgreSQL-required tests; zero required skips/errors. This includes the new real database-to-report regression distinguishing announcement from availability. Remaining prior tests retain valid evidence because their code and inputs were unchanged.
- Earlier applicable shared-vocabulary/classification and Ollija regression checks: 54 passed. Ruff and migration-drift checks passed; no extra migration is required by the report correction.
- Staging: 35 entries from the frozen 30 nominations; all nominations admitted through routine rules. Exact study replay left dossier, claim, review and numerical row counts unchanged. Six misleading controls produced zero false confirmations. Controls used an existing native source with replaced in-memory text and a rolled-back transaction; they were not ingested as real synthetic Posts.
- Five requested windows, including shifted overlapping boundaries, matched direct Post/account queries. Repeat created no snapshots. All 38 distinct seven-day side totals matched direct source queries.
- Browser: the normal staging reader/renderer exported a real 35-row report. At 1280px, filtering Giotto shows Alto and Solo separately; significance sorting orders numeric values; evidence expands; announcement/availability totals stay distinct. At 390px, the page stays within the viewport and the wide table scrolls. HTTP(S)-only links and zero browser errors observed. Screenshots are retained in the private run receipts.

## Limits and follow-up

- Two announcements are confirmed; 33 provisional entries retain unknown publisher/date/identity facts. A company's name or matching classifier tag is insufficient proof.
- The 69,550 broad-scan candidates are source records, not unique or confirmed releases, and the broad census is read-only. Persisted candidate pilots and the finite study remain available in staging.
- Staging has less historical coverage than the source database. Observed-count averages are diagnostic only; they cannot establish how releases actually affect attention. No worldwide completeness or 95% computational-reuse claim is supported.
- A synthetic Post INSERT in an earlier staging control setup hit the existing database timeout before detector execution. Subsequent diagnostics found no remaining blocker; the original cause was not established. No trigger, index or service setting was changed. Private read-only probe setup failures were corrected and rerun; they are not passing executions.
- Routine intake retains pending source dossiers but does not yet automatically resolve arbitrary new products, crawl every linked repository or activate a harvester hook. PR-U4 owns those steps. Non-X inference depends on retained release-bearing content; metadata-only observations are explicitly reported as unsupported.
- The future TN writer must use the saved numerical/anchor identities and selected evidence packet, expose coverage/source names, and implement shape/subject interpretation. This change does not generate or publish TN/Pulse prose.

Known project learning applied: [bound and verify evidence before judging editorial output](../solutions/workflow-issues/2026-10-09-110145-editorial-evidence-delivery-before-voice-evaluation.md). No separate learning document was added: the concrete diagnosis, guards and residual work are preserved in code, tests, this review and the selected plan.
