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

## November 9 continuation: isolated ChartEngine test database

The owner authorizes a separate local PostgreSQL test database for this task, superseding the shared-test-database-only instruction for this task. A fresh isolated PostgreSQL 18 instance is running at 127.0.0.1:55439, data directory `/Users/fuchitalee/.local/share/pushinweight/chartengine-test-db`, with `chartengine_dev` and pytest's `test_chartengine_dev`. It contains no production copy. The first fresh-schema test run passed 64 tests, including 41 PostgreSQL-required tests and no skips/errors. The existing cache improvement remains local and undeployed.

Continue investigating the cold historical-identity lookup and reusable reconciliation; do not change production data or deploy without a current delivery selection. Do not add tables or columns. Preserve original observation evidence, contract history, timing, exact source IDs, gap semantics and competing live work. The existing `correct_attribution` requires a publisher account: production 0813 mappings for OpenRouter, Arena and OpenCode lack one, so its direct reuse is not yet established. Evaluate existing replay and corrections against actual constraints rather than directly updating historical fields. Measure any query/index candidate on realistic synthetic data and retain only changes whose behavior and performance can be verified; do not mutate production to obtain a measurement.

## November 9 index candidate and regression evidence

Added one partial PostgreSQL index (`idx_obs_native_chart`) on existing observation identifier, subject kind and ID for unmapped model/repository rows, via non-atomic `AddIndexConcurrently`; no tables or columns. PostgreSQL 18 fresh test-schema migration applied successfully and reports `indisvalid=true`, `indisready=true`. The model and migration agree (`makemigrations --check --dry-run`). Existing 64 ChartEngine checks passed, including 41 PostgreSQL-required checks; the index readiness check passed separately. Scoped lint is clean. Full `core/models.py` lint reports 196 pre-existing warnings; do not blanket-edit the model file to hide them.

A synthetic 1.5M-observation, 300K-metric join produced the same 500 rows, with 124.975ms before versus 4.276ms after and an approximately 15.8MB index on the synthetic 300K eligible rows. This is one local sample, not measured production speed or cost. Production statistics estimate 2.44M total observations, with approximately 14.6% repository and 3.4% model kinds before accounting for mapping nulls; benchmark and evaluate write/maintenance cost and capacity before production deployment. Build concurrently without intentionally interrupting live collection; handle an invalid partial index using the existing migration safeguards. No production schema or data change is authorized by this test. The exact-id chart fallback remains in place so historical data stays visible; this index improves its lookup without retroactively rewriting attribution.

General-page affected UI assurance is running against the dedicated test database; its result must be recorded honestly. The reusable mapping-correction problem is not resolved by the index: production OpenRouter and Arena 0813 mappings lack the publisher account required by the existing correction helper, and normal mapped reads also depend on collection contract identity. Do not perform a naive mapping-field update.

## November 9 General-page regression repair

The first full affected run exposed a prior shipped chart regression: General loaded Chart.js from an external domain, violating its existing no-external-request browser contract. Vendor the exact Chart.js 4.4.0 asset under `monitor/static/vendor/chartjs/` with its MIT license; the SHA-256 matches the earlier exact unpkg asset (`321e3a3fa98da4aaa957d10be57cbb514de0989eed8f9d726b5d05902cd01904`). The General assurance identity now covers the chart endpoint, CSS, JS and vendored library. Update its source identity after inspection. Repair a stale geography test to require all three locale records while allowing additional real alternate names seeded by the fresh schema. Targeted rerun: six tests passed, including five PostgreSQL-required, nine browser subtests; zero required skips/errors. A fresh-schema full affected run is in progress.

## November 9 affected-suite completion

The full affected General-page assurance gate now passes on the owner-authorized isolated PostgreSQL instance: 423 tests, 140 subtests, 179 PostgreSQL-required tests executed, zero skipped or errored; JavaScript regressions also passed. Declaration validation and prescription were clean (General: 71 obligations; homepage: 5,191 obligations). This is an affected-scope result, not an exact-revision candidate assessment or production performance proof.

The pre-port snapshot failure was independently reproduced on unchanged main `99c91a54` and a separately created fresh test database. Its captured baseline lacked the current seeded `neutral` sentiment and classified one audience-topic point as unclassified when the current audience scheme is present. Recaptured on unchanged main and independently verified before editing: 12 sentiment snapshots differ only by the zero-valued `neutral` line and its localized legend; 12 audience snapshots differ only by moving one point from `__unclassified__` to `__no_audience_topic__`. Updated only these exact expected fields and made the test fixture restore the two migration-seeded vocabulary records after test flushes. The complete snapshots continue to be compared. Source identity now includes the core ChartEngine modules, endpoint, chart CSS/JS, and exact locally hosted Chart.js asset.

The reusable attribution reconciliation remains separate and unfinished: do not silently change historical records or assume the publisher-dependent correction API applies to OpenRouter/Arena. The index makes the current fallback faster without requiring those writes. No deployment is selected for this follow-up.

## November 9 final local verification

With the local index and bundled Chart.js candidate, the affected General-page gate completed: 423 tests and 140 browser subtests passed, including 179 PostgreSQL-required tests (zero skipped/errors), and its Node checks passed. The independent chart/index/browser run passed 66 tests including 42 PostgreSQL-required (zero skipped/errors). Scoped Ruff and `git diff --check` passed. Migration readiness and index validity were confirmed on the dedicated PostgreSQL 18 instance. The synthetic query result is a preliminary local measurement, not a claim of live production latency. The cache and index are local candidates and have not been pushed, deployed, or applied to production; new tables and columns: zero, new index: one. General assurance source identity `worktree-sha256:407b3650a91de30614c19b701a0dc8ce5e4b2e21b4b615f9ff1a61d460a1f50e`; separate exact-candidate release assessment/performance proof remains unperformed.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

Generated by `ollija annotate-plan`; do not edit between the markers. Delivery policy lives in `AGENTS.md` under "Plans and delivery". Project facts (host, repository, branches, environments, URLs and blueprints) live in `.ollija/project.yaml`. Record owner exceptions under Delivery Exceptions below.

- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/optimize/chartengine-latency-20261107/docs/plans/2026-11-07-042940-optimize-chartengine-latency-20261107-plan.md`
- Branch: `optimize/chartengine-latency-20261107`
- Change: `optimize-chartengine-latency-20261107-2026-11-07-042940`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/optimize/chartengine-latency-20261107`
- Workflow: `plan`
- Delivery target: `on-request`
- Route: `staged`
- Owner selection recorded: `false`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery steps

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

Occupied staging: if a staged route finds `staging` in use by an unrelated release while production is authorized, follow the occupied-staging default in `AGENTS.md`.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

None.

# Goal

<!-- Planner: replace this requirements-only placeholder with the change goal. -->

## Product Contract

<!-- Planner: define the user-visible contract, acceptance cases, and verification. -->
