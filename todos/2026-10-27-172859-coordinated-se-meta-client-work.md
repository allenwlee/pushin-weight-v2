---
status: ready
priority: p1
issue_id: "se-meta-client-20261027"
tags: [harvester, homepage, meta, special-events]
dependencies: []
---

# Implement special-events, Meta backend and client naming

## Problem Statement

Execute the owner's selected draft while preserving the separate G2/G5 work and existing provider budgets. Broader product-release processing requires the agreed final RG7 storage contract.

## Findings

- Canonical plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/refactor/global-shared-vocabulary-20261021/docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md`, sections Special-events split and vocabulary, Coordinated homepage backend and X-client rename, and Confirmed release-routing bug.
- Implementation branch starts clean at86df8dcf; no pre-existing local implementation commits or changed source files. The root coordination checkout and canonical shared plan contain peer edits, excluded from implementation commits.
- Brand key remains `llama`; display becomes Meta. Add confirmed `meta-models` publisher coverage via existing account/company/product storage. No UUID migration.
- RG7 ProductReleaseDetail/pending-dossier contracts are absent at current main; do not build a substitute schema. R1 timing depends on the RG6 integration point and frozen campaign attestation compatibility.

## Proposed Solutions

Use the selected shared runtime paths and existing persistence. Preserve SE per-query windows and a shared daily allowance. Keep mechanical rename in a separate change. Do not expand workers, budgets or recurring collectors.

## Recommended Action

Execute native inline, starting with independent backend work. Reuse the permanent PostgreSQL test database under its wrapper lock. Gather caller-chain regression and browser evidence before review/delivery. Complete implementation and required checks before any final endpoint clarification.

## Acceptance Criteria

- [x] W1/W7 code: bounded idempotent Meta names/aliases/publisher and brand-color application; seed consistency; classifier/identity contracts preserved. Production application and separate catalog import remain unperformed.
- [ ] W2/W4/W5/W6/W8: server ordering, locale followers/copy, category colors and public-version context verified through consumers.
- [x] W3 code/focused checks: chart endpoints stop at genuine scheduled harvest coverage, including failed/partial/sparse/boundary cases. Full assurance/performance remains pending.
- [ ] SE1/SE2: exact selected queries, distinct windows/run identities, shared allowance, stale assessment rejection and actual scheduler caller tests.
- [ ] Product-release routing: ordinary and special-event sources enter equivalent intake using available agreed storage; no extra detector LLM calls.
- [ ] R1: x_client/XClient rename, all callers/mocks/workflow paths and frozen campaign compatibility verified.
- [ ] Focused checks, required UI/harvester evidence and completed code review recorded; no skipped requirement represented as passing.

## Work Log

### 2026-10-27 17:28 JST — Execution intake

- Read ce-work triage/workspace/engine/strategy/implementation rules and repository harvester/UI/shared-DB rules.
- Selected native inline execution; no external engine preference. Updated prepared feature branch by clean fast-forward70fb5f6e→86df8dcf and linked existing root .venv.
- Shared DB status: PostgreSQL18, expected system identifier, no other clients. Compatibility and browser baseline checks next.
- No application source edit, production mutation, paid request or test pass yet.

### 2026-10-27 — Meta data update verification

- Wrote `core/brand_presentation.py` and `apply_homepage_brand_updates`; seed shares names/colors. Existing Account/CompanyAccount/Product/BrandSearchTerm storage; zero table/column changes.
- Chose a bounded update command over `onboard_brand --csv`: the latter rewrites company geography/locale labels and registers unconfirmed publishers. The bounded command only changes selected brand fields/aliases and uses the existing publisher gateway with verified Meta ownership; no catalog/network request.
- Proof-first: new command test failed with expected unknown-command error before implementation. Initial implementation:7 passed/1 failed due test fixture KNOWN_MODELS unset; corrected fixture, no product workaround.
- Shared wrapper final command: `pytest tests/test_homepage_brand_updates.py tests/test_load_seed_account_observation.py -q`:10 passed,0 skipped/errors. Includes four locale homepage/chart request chains, preview, repeated application, conflicting ownership rollback, preserved products/aliases and seed gateway.
- Scoped new-file Ruff passes. Seed retains two existing BLE001 findings; import check and scoped check excluding that preexisting rule pass. `git diff --check` passes.
- Browser baseline: anonymous production root returned200 with visible Meta Llama, no page errors; screenshot/receipt at authoritative-root `.local/2026-10-27-coordinated-work/homepage-before-en.*`. Actual request used `lang=en` rather than the supported `locale=en`, so do not claim locale-specific baseline from it.
- Bridgewright assurance validate/prescribe both clean,5028 declared obligations. Execution of those obligations remains pending.

### 2026-10-27 — Server presentation prerequisites

- W2/W4/W6/W8 implemented: Meta-first priority; Chinese/Japanese follower values truncated in both feed projections; missing-data gray/catch-all black; capitalized chart labels; separate public version context. W5 English copy implemented with actual stage-specific estimates and existing retry/terminal states retained. Chinese/Japanese wording still awaits owner review; no assumption of approval.
- Verified 145 tests and41 subtests through the shared wrapper, including four-locale real Chromium initial-page/feed-refresh parity. Separate Meta-first/pulse browser check passed1 test/15 subtests. Required-test skips/errors:0. Full assurance gate still pending.
- Corrected two stale verification fixtures: the classification writer requires a live claim lease; the order/browser fixture explicitly tracks its synthetic brands. No production behavior was weakened to satisfy these tests.
- An initial browser attempt used a nonexistent homepage sort selector and was stopped; its leftover fixture caused one setup failure on the next run. Normal test teardown cleared it, then the corrected real filter interaction and clean reruns passed. No replacement database or schema reset was used.
- Scoped Ruff reports21 existing findings in views/context processors; do not call that check clean. Diff whitespace check passes. Root/prototype files remain outside implementation commits.
- Read-only production coverage receipt: `.local/2026-10-27-coordinated-work/harvest-coverage.*` in authoritative root. Latest inspected successful scheduled run has per-query searched bounds and complete coverage, but source_as_of is NULL; W3 must read actual query scopes.

### 2026-10-27 — Harvest-backed chart cutoff

- Added `monitor.harvest_coverage`: bounded latest96 executions over one day, three reads for runs/frozen ordinary targets/scopes. Uses exact query window ends; every ordinary target must be present and fully enumerated. Completed empty searches count; missing, truncated, running and future scopes do not. Optional discovery outcomes are excluded; a settled attempt can establish ordinary coverage even if its run remains partial.
- Both one-day chart builders use closed UTC five-minute buckets, trim the unsearched tail and expose `harvest_coverage` with run/searched-through/completed/end timestamps. Unknown coverage returns no buckets, not fabricated zeros. Existing longer-window behavior remains. Cache identity includes coverage so a newly completed run invalidates the old tail.
- Reuses CollectionRun/CollectionAttempt/CollectionJobTarget/CollectionScopeRun; zero tables, columns or migrations. CallState was rejected because backlog transfer can advance it over incomplete searches; source_as_of is unwritten on the observed scheduled path.
-45 focused PostgreSQL tests/53 subtests passed; separate real Chromium initial-chart/filter-refresh test passed1. No required skips/errors. Test fixture records now go through the real ScheduledCycleLineage writer. Initial fixture attempts hit ingestion/lifecycle guards and were corrected to use the writer; guards stayed intact. Browser test's initial endpoint expectation was corrected to the actual `/chart.html` fragment route.
- Broader graph/control assurance and candidate performance are still pending; these focused results do not replace them.
