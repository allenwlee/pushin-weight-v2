---
title: optimize/chartengine-latency-20261107 plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: optimize-chartengine-latency-20261107-2026-11-07-042940
  branch: optimize/chartengine-latency-20261107
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
## Plain-English Summary

Make repeat General-page chart requests faster by sharing a short-lived chart result between web workers on the same server instance. Stored results can be up to five minutes old; the existing Update data button recalculates them immediately. The chart continues to show its actual calculation time and retains its existing numbers, identity checks and missing-data behavior. No new database tables or columns, paid services, Redis resource or production deployment are included.

A read-only production profile found the first calculation is dominated by scans for unmapped historical Hugging Face and OpenRouter records. The cache improves repeat requests but does not fix that cold calculation, and does not span multiple server instances. Verify behavior and cache isolation, expiry, refresh and failure handling, then compare measured request and cache latency. A further cold-query improvement needs a separately verified query or index design.

## Execution record — 2026-11-07

Production profile: one cold 0813 request 8.599s; 22 metric-value queries 7.392s; post query 0.564s. Two slowest unmapped reads measured 3.401s HF and 1.373s OpenRouter. PostgreSQL EXPLAIN showed 103,686 HF metric rows and 435,755 shared buffer hits to find 15 relevant rows when warm. Local 157,299-byte production payload cross-instance file-cache read median 0.319ms, max 2.566ms over 100 samples; this is cache-read timing, not end-to-end production latency. Focused checks passed 64 tests including 41 PostgreSQL-required, 0 skipped/errors; targeted browser and lint checks passed. Shared DB tests used an overlay of already-applied real migration files; no schema was changed. Cache is per instance, bounded at 256 entries with five-minute expiry; read/write failures fall back to calculation. No production deploy, paid resource, DB writes or migration.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/optimize/chartengine-latency-20261107`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/optimize/chartengine-latency-20261107/docs/plans/2026-11-07-042940-optimize-chartengine-latency-20261107-plan.md`
- Change: `optimize-chartengine-latency-20261107-2026-11-07-042940`
- Branch: `optimize/chartengine-latency-20261107`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/optimize/chartengine-latency-20261107/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/optimize/chartengine-latency-20261107/render.yaml`
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
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

None.

# Goal

<!-- Planner: replace this requirements-only placeholder with the change goal. -->

## Product Contract

<!-- Planner: define the user-visible contract, acceptance cases, and verification. -->
