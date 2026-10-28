# Global schema closure reconciliation — October 28

RG1–RG7 have recorded production release and retirement evidence through `0205_rg7_retire_model_release_storage`. The original whole-database design ledger has not yet been fully reconciled to later scope decisions. This audit does **not** certify the entire historical design as implemented. After receiving it, the owner explicitly chose to close delivered RG1–RG7 and transfer unresolved historical proposals to a separate reconciliation plan.

## Verified deployed state

Read-only catalog queries of production `pushinweight_shadow` and staging `pushinweight_staging` returned migration0205 and identical public column names/types/nullability. There are221 current managed core models with2505 ordinary ORM columns; their physical tables contain2516 columns, including11 intentionally restricted source columns. No ordinary ORM column is missing from production, and current model state equals the migration graph. All catalogued production constraints are validated.

The public catalog contains2837 column entries when framework tables and views are included; this number must not be reported as application-table columns. Staging/production constraint definitions have49 rendering differences involving varchar/text array casts; these are not column drift. All49 differences were checked for identical CHECK-expression tokens after removing text/varchar casts and redundant grouping around string literals and ARRAY values, while preserving boolean grouping; the checks are equivalent under those captured expressions. Previous group receipts cover their then-current schema and data checks; this catalog audit is not a fresh full historical-data parity sweep.

## Complete inventory of historical proposals

The companion `2026-10-28-093000-global-schema-ledger-reconciliation.csv` contains all1013 unique table/column positions in the original ledger, with no omissions or duplicates:

| Catalog disposition | Positions | Meaning |
| --- | ---: | --- |
| Retention design; original column present | 616 | Catalog evidence supports continued presence, not every historical constraint or reader invariant. |
| Change proposal; original column still present | 247 | Requires comparison with later approvals/deferrals; presence alone is not proof of an unfinished required conversion. |
| Original column absent or source table renamed | 96 | Requires released migration/owner mapping; absence alone is not preservation proof. |
| Explicit deferred ChartEngine proposal | 54 | Outside delivered schema release scope. |
| Total | 1013 | 959 existing/pending positions plus54 chart positions. |

Among the247 unresolved change-proposal positions are176 historical FK proposals whose original columns remain scalar and have no FK constraint on those original columns. Examples include `posts.lang`, `posts.lang_detected`, `audience_topic_labels.lang`, `editorial_editions.locale`, and `event_dossier_claims.extraction_version`. Their exact historical proposals and current catalog types are in the CSV. Some rows concern known deferred organization/career/opportunity/provider work or rejected review-attribution fields. The number176 is **not** an approved migration count.

The original ledger remains a historical design input. Its `physical_status=planned` entries and the old 62-item scope audit cannot be silently relabeled complete based on the seven group deployments. The owner supplied the scope decision: close delivered RG1–RG7 and transfer unresolved proposals to `docs/schema-ledger-reconciliation-20261028`. Their per-field interpretation remains that follow-up’s responsibility.

## Follow-up ownership and current closure boundary

Live-operation protections and October27 gap recovery have moved to branch `fix/live-operation-continuity-20261028`, plan `docs/plans/2026-10-28-002739-fix-live-operation-continuity-20261028-plan.md`. It references the original database plan and retains U37–U42 plus a distinct U43 recovery unit. It grants no paid-provider, provisioning or deployment authority.

The enrichment issue is owned by another session, per the owner's October28 instruction. It is not a schema-refactor closure dependency and no historical failed enrichment check has been relabeled passed.

The missing RG7 production close-out paragraph is restored from commit `b0d53904`. Existing unrelated G3 plan additions and untracked walkthrough/research artifacts are preserved. The detailed database reference has now been refreshed to221 current managed application tables and2516 physical columns through0205, with exact inventory/section/column verification against current models and the production catalog.

No service or schedule was changed, no database row was written, no migration or application test was run, and no provider request was made by this reconciliation. The production/staging catalog queries used explicit READ ONLY transactions and bounded statement timeouts.

## Owner-selected closure and follow-ups

Delivered RG1–RG7 is formally closed within its recorded release scope. The historical whole-ledger audit stays intact and unresolved entries are not mislabeled complete. [Ledger-reconciliation plan](https://github.com/allenwlee/pushin-weight-v2/blob/docs/schema-ledger-reconciliation-20261028/docs/plans/2026-10-28-004220-docs-schema-ledger-reconciliation-20261028-plan.md) owns the remaining field dispositions; [continuity and recovery plan](https://github.com/allenwlee/pushin-weight-v2/blob/fix/live-operation-continuity-20261028/docs/plans/2026-10-28-002739-fix-live-operation-continuity-20261028-plan.md) owns prevention and the October27 incident. The separate enrichment session owns its issue.
