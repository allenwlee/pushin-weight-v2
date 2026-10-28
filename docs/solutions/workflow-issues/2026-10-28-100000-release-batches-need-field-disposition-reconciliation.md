---
title: "Release batches require a complete field-disposition reconciliation"
date: "2026-10-28"
module: pushin-weight-v2
problem_type: workflow_issue
component: development_workflow
severity: high
root_cause: missing_workflow_step
resolution_type: workflow_improvement
applies_when:
  - "A broad database proposal is delivered through narrower release groups"
  - "A final deployment is being used as evidence of whole-plan completion"
tags:
  - "schema"
  - "migration"
  - "scope"
  - "closure"
  - "field-ledger"
---

# Release batches require a complete field-disposition reconciliation

## Context

The global schema design ledger contained1013 field positions:959 existing/pending and54 deferred chart positions. Execution was organized into62 original work items and then RG7 product-release integration. Group checks proved selected migration/data/caller contracts, but the original field positions were not all mapped to final delivered, retained, superseded or deferred decisions.

A read-only October28 catalog reconciliation found247 historical change proposals whose source columns remained, including176 historical FK proposals. Of those176,161 already had their proposed target tables in production. Those counts are evidence for further reconciliation, not proof that every old proposal remained approved or that existing lookup records covered all source values. Another96 positions had absent/renamed source columns and required release mapping. The616 source-present retention positions and54 chart deferrals completed the original inventory.

## Guidance

Before executing grouped schema work, give each original field identity one disposition owner: a selected release item, an explicit retention decision, a superseding design, or an approved deferral. Keep the link when a table name or release grouping changes. A newly added lookup does not close all its prospective consumers.

At release acceptance, check the selected fields' copied values, FK constraints, current callers and old-column retirement. At whole-plan closure, additionally reconcile the original identity set against all recorded dispositions. Code/database agreement proves that the implemented schema is deployed; it cannot establish that omitted requirements were implemented.

If closure scope changes, record the owner's decision and preserve the remaining inventory in a concrete follow-up plan. Do not silently mark proposals complete or create new conversion authority from their old presence in a ledger. Here the owner explicitly chose to close delivered RG1–RG7 and transfer unresolved historical proposals to the separately branched reconciliation plan. Continuity protections and the actual harvest-gap recovery also have a distinct plan. The externally owned enrichment issue was excluded without relabeling its failed check as passed.

## Verification and limits

The committed closure audit inventories all1013 unique original positions and retains their catalog classifications. The owner scope decision supplies the closure boundary. Further per-field semantic reconciliation and all future conversions remain follow-up work; the process correction does not claim those migrations shipped. No source rows or live schedules were changed for the audit.

## Sources

- [Original plan](../../plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md).
- [Closure reconciliation](../../analysis/2026-10-28-093000-global-schema-closure-reconciliation.md).
- [Complete catalog-position register](../../analysis/2026-10-28-093000-global-schema-ledger-reconciliation.csv).
