---
title: "Historical schema ledger reconciliation - Plan"
type: docs
date: "2026-10-28"
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-plan-bootstrap
execution: knowledge-work
origin: docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md
ollija:
  change_id: docs-schema-ledger-reconciliation-20261028-2026-10-28-004220
  branch: docs/schema-ledger-reconciliation-20261028
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/schema-ledger-reconciliation-20261028`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/schema-ledger-reconciliation-20261028/docs/plans/2026-10-28-004220-docs-schema-ledger-reconciliation-20261028-plan.md`
- Change: `docs-schema-ledger-reconciliation-20261028-2026-10-28-004220`
- Branch: `docs/schema-ledger-reconciliation-20261028`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/schema-ledger-reconciliation-20261028/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/schema-ledger-reconciliation-20261028/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

### Failure handling

- Complete applicable, unwaived checks for the selected route. A waived check is waived, never passed. Owner-selected direct production does not require staging.
- Product defects return to the parent implementation workflow; repeat only checks invalidated by the fix. Environment failures require repairing the environment, not a new source commit. Retry only after a relevant fact changes.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE --># Historical schema ledger reconciliation - Plan

## Plain-English Summary

The delivered RG1–RG7 database work is closed under the owner's October28 scope decision. This separate plan owns the remaining interpretation of the original1013-position field ledger. It establishes which proposals were implemented, superseded, explicitly deferred or still require a decision. It does not treat every old proposal as an approved migration.

The audit found247 proposed changes whose source columns remain and96 positions whose source columns are absent or renamed. Those343 positions need evidence-backed dispositions. The616 retained-source positions and54 deferred chart positions remain part of the complete inventory, so no row disappears from accounting. Of176 historical FK proposals whose scalar source survives,161 have extant target tables and15 do not; this does not prove target data coverage or continuing approval.

This is a documentation and read-only research plan. It authorizes no migrations, production writes, provider requests or live-operation changes. Concrete further implementation must be scoped from the reconciled decisions.

## Goal Capsule

- Objective: Every historical field proposal has a clear current disposition, and the owner can see the exact remaining implementation decisions without reopening completed releases.
- Means: One row-by-row decision register grounded in source, current catalog metadata, release receipts and later owner decisions.
- Authority: Plan creation, branch isolation and commit/push of this handoff are authorized. Running this reconciliation or implementing further conversions needs the next selected task.
- Completion boundary: A complete1013-position register, with implemented/retained/superseded/deferred/unresolved categories and concrete evidence for each; actionable remaining choices are explicit.

## Product Contract

### Problem Frame

The historical whole-database field design was not fully mapped into the62 original release work items. Batch correctness did not establish original-inventory completeness. Owner-approved closure now applies to the delivered RG1–RG7 scope, while this plan retains responsibility for unresolved historical proposals.

### Requirements

- R1. Preserve all1013 unique original table/column identities, including54 chart deferrals, without silently promoting a proposal into approval.
- R2. Resolve the247 source-present change proposals against later decisions and actual storage, starting with the161 FK proposals whose target tables exist.
- R3. Resolve the96 absent/renamed positions using actual migrations and the released evidence-preservation/caller contract, rather than treating absence as success.
- R4. Retain the616 source-present retention entries and54 chart deferrals as explicit categories, checking any contradictory later owner decision.
- R5. Classify each row as implemented, retained, superseded, explicitly deferred, or unresolved; attach source/decision evidence and a concrete destination for any implementation still selected.
- R6. Keep current production collection and workers running. No schema change, source rewrite, paid query or service mutation belongs to this plan.

## Planning Contract

### Key Technical Decisions

- KTD1. Close the delivered release scope and track the unresolved historical design separately (session-settled: user-directed — chosen over keeping the original plan open for every old proposal: preserve completed deployment acceptance while making remaining decisions explicit). Governs R1–R5.
- KTD2. Use the committed CSV ledger plus a new disposition register, with the original identity as the stable key. Current lookup existence is prioritization evidence, not semantic or migration approval.
- KTD3. Keep known deferrals and rejected changes intact: organization units, career configuration, opportunity action/benefit, provider account types and retained scalar person-name/disclosure decisions require their actual owner provenance. Recheck each row before reusing a historical target.
- KTD4. Reuse the October28 read-only catalog snapshots for schema facts while their revision remains relevant. Later runtime facts need a new bounded read-only capture, never a full source-data scan by default.

### Implementation Units

### U1. Establish the complete decision register

**Requirements:** R1/R4/R5. **Dependencies:** Committed origin ledger and closure audit.

**Files:** `docs/analysis/2026-10-20-160626-entire-database-field-decisions.csv`, `docs/analysis/2026-10-28-093000-global-schema-ledger-reconciliation.csv`, proposed dated `docs/analysis/*-schema-ledger-final-dispositions.csv` and a concise decision report.

**Approach:** Copy stable identities into the new register, retain original proposal wording, and add current physical owner, actual target, disposition, decision source, implementation evidence and remaining decision. Preserve source-ledger hashes. Keep original artifacts immutable evidence.

**Verification:** Exactly1013 unique positions, exact original-set equality, no missing or duplicate identities. This is document validation; no application tests or production writes are required.

### U2. Map retired and renamed fields to released destinations

**Requirements:** R3/R5. **Dependencies:** U1.

**Files:** `core/migrations/`, group release records in the origin plan, `docs/analysis/*-schema-ledger-final-dispositions.csv`, `docs/reference/db-schema.md`.

**Approach:** For each of96 positions, identify its actual rename, retained scalar, replacement relationship, restricted evidence owner or retired entity. Cite the migration and the applicable retained-history/caller proof. Reuse group evidence only within its recorded cohort; unresolved mapping remains unresolved.

**Verification:** Every absent/renamed row has a destination/preservation proof or explicit unresolved decision. A removed prototype table is not counted as a new lookup conversion.

### U3. Reconcile source-present proposals with current decisions

**Requirements:** R2/R5. **Dependencies:** U1.

**Files:** Existing source and target models, writer/reader paths, original plan's owner-decision entries, `docs/analysis/*-schema-ledger-final-dispositions.csv`.

**Approach:** Examine all247 rows, including the176 historical FK proposals. Record existing lookup identities, target semantics, cardinality, source wording/evidence requirements and whether the same target is genuinely reusable. Inspect representative reads/writes and bounded distinct-value queries only when necessary. Explicitly separate fields already retained by owner decision from missed approved changes and unapproved design proposals. Do not add persistence or new Char/Text/JSON fields during review.

**Verification:** Each proposal has a decision-backed disposition. Existing target tables are never reported as completed source conversions without FK/caller/data evidence. No automatic conversion is inferred from the161 extant-target count.

### U4. Publish the remaining decision and implementation boundaries

**Requirements:** R1–R6. **Dependencies:** U2/U3.

**Files:** This plan, final disposition register, a dated decision report, and later implementation plans only after scope is selected.

**Approach:** Group unresolved rows by shared semantic owner and reader/writer boundary. Present owner-reserved choices together with evidence, expected table additions/retirements and preserved-source requirements. Give any confirmed implementation gap its own bounded plan, without reopening accepted RG1–RG7 migrations or redefining historical completeness.

**Verification:** Every unresolved row has a precise question and consequence; every selected implementation gap has a named next artifact. The final register's counts sum to1013 and agree with the decision report.

## Verification Contract

Use source/document inspection and read-only catalog evidence. Verify stable-key set equality, decision provenance, current physical targets, real caller references, scope counts and links. Do not run application tests, migrate the shared test database or contact providers solely to classify these rows. No approval or implementation conclusion follows from catalog existence alone.

## Definition of Done

All1013 positions have an evidence-backed disposition or an explicit owner decision still needed, with the unresolved set visibly retained. The96 renamed/absent and247 source-present proposals have been individually reconciled, and retained/chart categories remain accounted for. The delivered database plan stays closed within its selected scope. This research completion does not imply any unimplemented conversion has shipped.

## Sources

Authoritative origin close-out: [delivered RG1–RG7 scope at0a8ac05f](https://github.com/allenwlee/pushin-weight-v2/blob/0a8ac05f/docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md). This follow-up retains the older origin copy for source history; its scope comes from the owner-selected closure recorded at that commit.

- Origin: `docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md`.
- `docs/analysis/2026-10-28-093000-global-schema-closure-reconciliation.md` and its ledger CSV/summary.
- `docs/analysis/2026-10-20-160626-entire-database-field-decisions.csv` and later owner scope decisions.
- Current `core/models.py`, ordered `core/migrations/`, and `docs/reference/db-schema.md`.

## Delivery Exceptions

The owner explicitly requested a separate follow-up and committing/pushing the handoff. No new implementation, provider spend or deployment is authorized by this plan.
