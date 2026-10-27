---
status: pending
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
- [x] W2/W4/W5-English/W6/W8: server ordering, localized followers, English pending/promotion copy, category colors and public-version context verified through consumers. New zh/ja copy remains pending owner review.
- [x] W3 code/focused checks: chart endpoints stop at genuine scheduled harvest coverage, including failed/partial/sparse/boundary cases. Full assurance/performance remains pending.
- [x] SE1/SE2 code: exact selected queries, distinct windows/run identities, shared allowance, stale assessment rejection and actual scheduler caller tests. New assessment and activation remain unperformed.
- [ ] Product-release routing: ordinary and special-event sources enter equivalent intake using available agreed storage; no extra detector LLM calls.
- [x] R1 implementation committed31cb1370: client/callers/mocks/workflow rename and frozen campaign contracts corrected. Final expanded regression remains pending below.
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

### 2026-10-27 — Special-events split and browser regression corrections

- Implemented opt-in `special-events-v1`: exact 382/412-character queries (428/458 with eleven-digit epochs), separate run/window identities and one shared existing daily budget. Legacy query/default/receipts retained. No activation or paid assessment performed.
- Real planner/scheduled runner tests cover two searches, duplicate starts, one decision drain, shared credits including prior legacy spend, concurrent final reservation, midnight, stale assessment rejection, both ingestion/provenance paths and staging selection. Telemetry now includes both queries. Planning failure aborts before provider creation, including bounded selection.
- Broader regression:188 passed,3 stale ordinary-call-count fixtures failed; corrected to include existing C4. Those3 then passed. A historical migration test was explicitly deselected because its fixture creates another database; no migrations are introduced by this unit. Later44-test correction run passed40, with3 newly added cache tests calling a helper incorrectly and1 further stale C4 assertion; corrected and awaiting rerun.
- Affected browser gate initially351 passed/94 subtests with7 failures. Found and fixed actual chart-cutoff leakage into narrative freshness, and a long-window cache key regression. Added genuine completed-harvest fixture rows for chart-interaction tests and refreshed only the General source identity. All previously failing browser interactions passed in the correction run, including narrative freshness in both locales.
- Added an explicit shared-DB wrapper option to the assurance gate, preserving its test set and CI default;4 wrapper/candidate-binding tests passed. Full rerun subsequently refused because G2 advanced shared schema to0201. Newly fetched main00dcf8c4 contains that migration; integrate the delivered source rather than reset/clone the DB.
- Bounded read-only production EXPLAIN of the exact new coverage selection: planning11.037ms, execution21.501ms. This covers one query on the observed data, not full-page performance. Root receipt: `.local/2026-10-27-coordinated-work/chart-coverage-explain.*`.
- Scoped new files/telemetry/discovery/assurance lint passes; existing cycle/config lint findings retained. Final integrated verification, candidate assurance/performance and code review remain pending.

### 2026-10-27 — Schema0201 integration and local checkpoint

- Merged delivered main00dcf8c4 into this branch at12af531d, without conflicts or database changes. Source now matches the shared0201 schema. G2's production cutover/deletion is still active in the canonical plan; merging source does not establish that release prerequisite for R1.
- Affected assurance gate on schema0201 passed356 tests/96 subtests, including144 required PostgreSQL tests,0 required skips/errors; Node chart/filter, feed formatter and timezone checks passed. Main model/declaration remain ba03d215.../f084b72a... with5028 prescribed obligations; General has71. This is the affected gate, not a candidate assessment or release receipt.
- Final combined harvester/backend checks:276 passed/16 subtests,191 required PostgreSQL tests,0 skips/errors;1 historical additional-database migration test explicitly deselected. No skipped/deselected migration proof is claimed.
- `ce-simplify-code` lenses run inline per repo agent mapping. Kept distinct legacy/new query identities and historical storage names. No behavior-changing reuse or concurrency rewrite justified; expanded four new files for readability, with AST identity verified against the checkpoint. Corrected the new browser-loop error-handler binding and import formatting. Scoped lint comparison versus main:78 baseline findings,78 current,0 introduced; repository-wide lint remains non-clean (1940 findings), not falsely reported passed.
- Remaining required work: R1 after the selected RG6 production integration point; release-intake integration after actual RG7 ProductReleaseDetail/source-dossier/pending-reader contracts. Current main still defines ModelReleaseDetail and ProductVerificationProposal.source_release. Preserve source-first detector490a34c6 and frozen backfill revisions/recipes; no substitute bridge.
- New zh/ja copy awaits owner review. Meta command is preview-first; production data application and separate public metadata catalog import were not run. SE remains opt-in with old default unchanged. No paid request, provider activation, remote push, PR, service change or deployment.
- Overall ce-work remains blocked at these prerequisites. Final candidate assurance/performance, complete code review and shipping are pending, not passed or waived. Resume this branch and the same canonical plan after prerequisites arrive; existing implementation authority persists.
- Final source-identity/browser rerun:2 tests/4 locale subtests passed,2 required PostgreSQL tests and0 skips/errors. General declaration source identity is577bb1bd...; only its source binding changed, with controls/fixture preserved. `manage.py check` passed with0 issues. Existing staticfiles-directory warnings during browser tests remain environmental; live-server assets and JS checks executed successfully.
- Private implementation logs are retained at authoritative-root `.local/2026-10-27-coordinated-work/implementation-checks/`; browser artifacts remain in this worktree's ignored `.pytest-tmp/`. Source commits and the canonical plan are retained for authorized continuation.

### 2026-10-27 — Authorized production continuation; schema coordination pending

- Owner: “g2 rg6 is deployed, deploy and activate this”. Production authorization persists; default staged branch route with same-SHA promotion. Production/staging web observed00dcf8c4 and RG6 service/schema0201 completion confirmed. No Giants, budget/slot increase or peer ownership change.
- R1 committed31cb1370: `x_monitor.x_client.XClient`, matching errors/callers/mocks/workflow paths. Frozen recipes/revisions retained; old attestation rejected against renamed current runtime. Initial298-pass/3-failure rename run exposed a missed import and stale enrichment fixtures; corrections passed22 focused tests,14 required PostgreSQL and0 skipped/errors.
- Exact paid query assessment: two on-demand one-page calls over11:30–11:45UTC, SE1=6 and SE2=20,26 distinct,390 estimated credits. Both continuation flags true; bounded sample, not exhaustive coverage. Four clear release announcements in SE2; substantial unrelated capture retained under owner's recall-first choice. Shared daily cap remains28,800.
- New assessment `docs/analysis/harvester/2026-10-27-205000-special-events-query-assessment.json` passes, digest `1dd606ceb853b2679fc2064e34f4defd92b3f81f389d1751361652f6db2cef85`. October27 exact-query captures and source review are new; unchanged functional fixtures reuse56 independently revalidated archived September24 provider receipts. Never relabeled old-query volume evidence. Private receipts live at authoritative-root `.local/2026-10-27-special-events-activation/`.
- Added the query-pack environment selector; production harvest/enrichment and staging enrichment Blueprint tuples pin the new artifact. Actual Blueprint→loader→planner checks passed without DB/provider access. Runtime activation remains unperformed.
- Expanded54-file regression stopped after291 passes/12 failures,1 additional-database migration fixture explicitly deselected. Failures trace to stale RG6 tests: fake searches bypass captured-response callbacks, native enrichment fixtures write retired report/envelope fields, and workload assertions include aggregate observations/retired checkpoints. Five test files are corrected locally with real capture/membership/checkpoint contracts preserved; corrections remain **unverified and uncommitted**.
- The next shared-wrapper run refused: installed `core.0202_rg7_expand` and `core.0203_rg7_product_release_cutover` are absent from this0201 candidate. G2 RG7 source is still uncommitted; origin/main remains00dcf8c4. Coordination request recorded in shared index and pending with owner: compatible committed G2 revision or G2-coordinated0201 handback. No database reset/clone, wrapper bypass or borrowing peer WIP.
- Completed144 database-free tests,0 required PostgreSQL executed/skipped/errors. Scoped imports, syntax compilation and diff whitespace pass. Earlier affected UI356tests/96subtests and backend276tests/16subtests are retained at their actual0201 scope, not represented as final candidate proof. Prepared one-day staging performance declaration at `.ollija/tmp/performance-one-day.json`; Bridgewright runtime preparation passed.
- Full ce-code-review receipt: `/tmp/compound-engineering-501/ce-code-review/20261027-se-meta-client/review.json`, status complete, verdict **Not ready** on pending release checks. Nine local lenses run sequentially per AGENTS. Claude returned HTTP402 before review; disclosed Grok replacement hit shared deadline without usable output. Cross-model corroboration is degraded. Both terminal job directories removed; no review worker remains. No confirmed new product defect retained; fixture and candidate/runtime verification remain open.
- Resume: compatible source/schema; corrected regression; candidate assurance; verified candidate commit/push/stage; matching one-day performance and bounded staging acceptance; same-SHA production promotion; exact active-service proof; Meta preview/application and bounded existing HF catalog import; natural SE1/SE2 cycle proof and literal latest20 same-cohort30-minute enrichment follow-up. Broader product-release intake still awaits delivered RG7 contract. No remote push, PR, production data write, deployment or activation yet.

### 2026-10-27 — RG7 delivered and integrated

- G2 final6873cf17 is live on production web/harvest/enrichment and staging web/enrichment. Integrated committed RG7 source through schema0205; the former local schema prerequisite is resolved.
- Routing regression first failed all4 ordinary/special × classification/replay cases; removing the obsolete rare-hit gate lets all routes reach the shared EventDossier writer. Existing limits and idempotence remain. Additional dispatch-guard cases and historical requirements parity added.
- Focused integrated checks:131 passed,131 required PostgreSQL executed,0 skipped/errors. Stale retirement/capture fixtures corrected without weakening live guards. Remaining rename tests, full candidate assurance, staging and deployment remain in progress.
- Remaining client/worker/backend run:507 passed,197 required PostgreSQL executed with0 required skips/errors.20 failures reproduce identically on deployed6873cf17 in an isolated source checkout (no new database); all belong to older probe/SQLite/schema expectations. One optional paid live probe skipped; one additional-database migration fixture deselected. Neither is claimed passed. Routing guards and worker checks passed. Running one serial and one parallel576-scope sample to verify corrected typed fixtures; repeated performance samples and unchanged8-second saturation benchmark are outside this transport-rename check.
