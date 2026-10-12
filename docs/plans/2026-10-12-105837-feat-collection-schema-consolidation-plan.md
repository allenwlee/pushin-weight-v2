---
title: Source-neutral collection schema consolidation
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: feat-collection-schema-consolidation-2026-10-12-105837
  branch: feat/collection-schema-consolidation
  workflow: work
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  delivery_route_selected_by_user: false
  staging_transport: branch
---
# Source-neutral collection schema consolidation

## Plain-English Summary

Combine the duplicate HF catalog and metric collection bookkeeping into the existing
metric tables, retaining one shared run table, one observation table and one scope
progress table. This creates no permanent tables and retires two HF tables. Existing
numeric history, product pointers, pagination recovery and collection schedules survive.
The schema work is independent of the remaining G3 chart, release and watcher work.

The owner also removes the original-content storage seven-day retirement waiting
period. Retirement still reports actual legacy-writer dependencies and restore
requirements; this task does not drop original-content storage or live aliases.

The owner authorizes production deployment of both changes on October 13. Delivery
uses the default staged route, with the same candidate revision promoted to production.
Collection schedules and feature activation stay unchanged. Local migration and
collector proofs are retained; completion requires staging and production schema,
data-preservation, application and exact-revision verification.

## Goal Capsule

Upstream: G3 round-two plan, U14 and its October12 ce-pov, in the retained G3 worktree.
This branch owns the standalone implementation; upstream remains the G3 scope authority.
Base: origin/main f43b2904393013107598af3904b78d3be36c76b4.
Engine: native inline execution, return-to-caller implementation/local verification.
No subagent/external-model execution under the repository sequential-agent instruction.

## Product Contract

- R1: generalize MetricCollectionRun/MetricObservation to CollectionRun/CollectionObservation.
- R2: generalize the existing HF namespace progress table to CollectionScopeRun.
- R3: merge HF run/repository history; retire their two tables; create zero permanent tables.
- R4: preserve numeric IDs, values, contracts, source-use controls and saved revision pointers.
- R5: catalog rows require no fake metric contract/value. Numeric runs retain required contracts/leases
  and terminal partial semantics. Catalog partial/interrupted runs preserve continuation.
- R6: preserve HF source payloads, group outcomes, product ownership, native revision/observation times,
  old pointer resolution, pagination and curated projections. Catalog-only enrichment may mutate
  its working metadata; numeric observations never enter that mutable catalog path.
- R7: retain current schedules, cohorts, budgets and activation. No fleet watch or new job registry.
- R8: staging copies numeric evidence and excludes/scrubs catalog run/progress/observation data.
- R9: original-content retirement has no calendar waiting condition, retaining actual dependency checks.

## Technical Contract

Reuse existing metric run/observation storage. Add source-neutral catalog fields there:
run purpose/scope/invocations/report/updated time; observation optional scope/product,
resource key, native listing/envelopes/group outcomes, processing outcome and updated time.
Current run contract and lease become nullable only for catalog-purpose rows, protected
by purpose-conditional constraints. Current metric status/precision/value constraints
remain meaningful. Scope namespace becomes scope_key with scope_kind=namespace.

Metric and catalog writers remain source-specific adapters using the same tables;
source clients, HTTP budgets and parser changes belong to later G3 units. HF observations
remain one resource working record per scope/run, with append-preserved request envelopes
and group revision evidence. Numeric observations retain immutable saved identities.
This explicitly scopes mutation to catalog-purpose records and avoids mixing live
projection progress into numeric readers.

Preserve original numeric primary keys; merged catalog observation integers are allocated
above the existing observation maximum, with durable legacy IDs retained in source metadata.
Handle catalog/metric run UUID collisions deterministically and preserve aliases. Rewrite
Product field-source pointers using both old run and observation ID, retaining original
provenance in imported evidence. Forward/reverse migration data paths preserve pointers,
original field values and numeric foreign keys. Existing namespace integer IDs survive.

Preserve MetricCollectionRun/MetricObservation Python import aliases because the live
Render benchmark launcher imports the old run name. Replay that captured launcher
against real test storage without provider calls. No schedule or service command change.

Use explicit model/table renames and data migrations. Keep old numeric table-name views
for currently compatible SQL readers during a rolling application release; these are
views, not duplicate data tables. No new seven-day retirement delay is added to this
refactor. Legacy schema objects retire after tested reader/writer/reference parity.
Historical migrations remain unchanged; new migrations express the transformation.

## Implementation Units

### U14a — Freeze characterization and remove the original-content calendar wait

Files: tests/test_original_content_retirement.py, monitor/original_content_cutover.py,
docs/reference/original-content.md. Observe the revised retirement test fail before
removing time fields; immediate/future reports must agree about remaining dependencies.

### U14b — Generalize models, merge history and adapt both collectors

Files: core/models.py, new core/migrations, core/hf_catalog.py,
core/benchmark_metric_store.py/operations/series, core/benchmark_opencode.py,
management commands and affected tests. Add schema/migration tests before implementation.
Match exact parent/source identities, statuses, count units and provenance.

### U14c — Preserve staging refresh and verify migration/collector parity

Files: config/staging_refresh.yaml, scripts/staging_refresh/database.py,
tests/staging_refresh and collection/migration tests. Shared tables need purpose-aware
scrub/count selection. Verify raw SQL, sequence names and both old/new schema refresh paths.

## Verification Contract

Use one owned local PostgreSQL database and its disposable Django/migration databases;
never aim pytest at shared data. Authorized Render staging/production migrations
use their service-scoped deployment entry point. Required PostgreSQL checks
must execute with zero required skips/errors. Source transport is mocked.

Run focused original-content retirement, collection schema migration, HF catalog/scope/
persistence/runner, benchmark source/persistence/operations/series/forecast/OpenCode and
staging-refresh tests. Exercise the real manage.py collector → client → DB writer path,
catalog cap/resume after interruption, both schema directions, overlapping integer IDs,
UUID collision, original timestamps/native payloads, Product JSON pointers, replay, numeric
IDs/values/contract hashes, same-provider independent purposes and staging exclusion.
Run makemigrations --check --dry-run, Django system checks and whitespace checks.

## Definition of Done

All R1–R9 behaviors implemented and verified, exact table counts and data references
reconciled, no change to collection topology/activation, and no unrelated G3 code carried
into this branch. The identical candidate SHA must pass staging and be observed on
production, with migration 0080 applied, baseline numeric identities/values retained,
catalog pointers/resume history reconciled and the retirement report omitting the clock.

## Delivery Exceptions

The owner explicitly requests deploying both changes to production on October 13.
Commit/push and necessary staged/production release actions are authorized for this
plan only. The default staged route remains selected. The owner also removes the prior
original-content seven-day waiting period; do not recreate it in a checklist or new code.
Actual legacy dependencies and data restoration checks remain; no original-content table
retirement is authorized by removal of that clock.

Owner resumes the existing production release at 07:21 JST after the HF
write-chronology and run/observation explanation. Both changes remain in scope.

Code review: complete — [2026-10-13-072742-collection-schema-release-review.md](../analysis/2026-10-13-072742-collection-schema-release-review.md).
Sequential main-thread review follows AGENTS.md; no independent review claimed.

## Production delivery verification — October 13

- Claim only this isolated branch and the shared release lane; preserve other worktrees.
- Inspect current remote main/staging, active deploys and actual source/target schemas.
- Review the full uncommitted diff, migration data paths, source permissions, lifecycle
  constraints, numeric references and collector callers in this thread (AGENTS requires
  sequential main-thread review). Fix concrete findings and rerun affected checks.
- Capture source counts, row-ID/value/payload fingerprints, catalog outcomes/scopes,
  Product field-source references, physical table identities and consumed sequences
  through Render CLI before migration. Stop if the catalog lock is owned by a caller.
- Use the checked-in serialized Render migration runner. Preserve existing schedules,
  suspended legacy services and provider/serving flags. No live collection probe.
- Rehearse staging with the same candidate SHA and verify schema, numeric/catalog
  preservation, `/` and `/general/` and provider-free existing readers/status commands. Update
  the staging-refresh reader grants only as required by the renamed scope.
- Promote the exact staging-verified SHA by a non-forced fast-forward production push.
  Observe web/worker revisions, applied migration, preserved evidence and source-free
  retirement report. Inspect errors and the next natural harvest boundary read-only.
- If migration fails, inspect the transaction/migration ledger and repair the cause
  before retry. A code rollback keeps the forward collection schema; any return to old
  HF code requires the tested reverse migration with canonical catalog callers drained.
  Never drop original-content tables or change collection schedules during rollback.
- Save exact-SHA deployment evidence in the authoritative host's ignored state; update
  this branch's final receipt before its final delivery commit. After verification,
  remove only this clean canonical worktree using the guide's guards, as the final
  filesystem action. Retain feature branches.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/collection-schema-consolidation`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/collection-schema-consolidation/docs/plans/2026-10-12-105837-feat-collection-schema-consolidation-plan.md`
- Change: `feat-collection-schema-consolidation-2026-10-12-105837`
- Branch: `feat/collection-schema-consolidation`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/collection-schema-consolidation/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/collection-schema-consolidation/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `work`
- Delivery target: `production`
- Owner selection recorded: `true`
- Delivery route: `staged`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/collection-schema-consolidation` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/collection-schema-consolidation` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

### Failure handling

- Complete applicable, unwaived checks for the selected route. A waived check is waived, never passed. Owner-selected direct production does not require staging.
- Product defects return to the parent implementation workflow; repeat only checks invalidated by the fix. Environment failures require repairing the environment, not a new source commit. Retry only after a relevant fact changes.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->
