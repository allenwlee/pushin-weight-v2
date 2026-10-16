---
title: Fix homepage query performance
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-homepage-query-performance-2026-10-16-075859
  branch: fix/homepage-query-performance
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  delivery_route_selected_by_user: false
  staging_transport: branch
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/homepage-query-performance`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/homepage-query-performance/docs/plans/2026-10-16-075859-fix-homepage-query-performance-plan.md`
- Change: `fix-homepage-query-performance-2026-10-16-075859`
- Branch: `fix/homepage-query-performance`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/homepage-query-performance/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/homepage-query-performance/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/homepage-query-performance` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/homepage-query-performance` without `--force`.
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

## Delivery Exceptions

None.

# Homepage query performance

## Plain-English Summary

Find why homepage loads and window changes are slow, and prepare the smallest
verified local correction. Measure production requests and database execution,
then preserve the same posts, brand counts, filters, labels and page design.
The owner now requests production delivery of this existing fix. Complete exact-candidate checks, compatible staging and production browser proof. No schema, scheduler, provider policy or future daily-summary changes belong to this release.

## Scope and baseline

- Current user: "investigate and let's find the fix. in general the homepage is running slow".
- Branch `fix/homepage-query-performance`, starting HEAD `4e60a2f16dc01663c9807e301c9a4a5ae017c669`.
- Pre-fix tracked tree clean; generated plan only. Other chart session's held
  worktree and uncommitted candidate remain untouched and are evidence only.
- TOUCH: homepage query implementation, existing chart/pulse regression tests,
  existing assurance declaration only when affected source identity needs review.
- PRESERVE: G3 collection/schema work, all runtime routes, date boundaries,
  zero-count brand inventory, locale behavior, filter semantics, cache behavior,
  page design and normal schedules. Zero tables added or retired.
- Current delivery authority: commit/push, compatible staged promotion and observed production deployment of this bounded fix. Ask only for a genuinely missing route/environment decision; unrelated service configuration, pauses and rollback remain excluded.
- Browser production anonymous zh-CN 1280x577: initial server first byte 1553.8ms,
  page load 3029.3ms. Clicking 30d aborts chart request at12000.7ms; old chart
  remains. PostgreSQL18.4 on pushinweight_shadow sampled same correlated query
  at14.49s, IO/DataFileRead, no blockers. Browser and DB baseline before edits.

## Investigation and implementation

1. Compare the repeated pulse count query against date-bounded grouped counts
   for ordinary1d and long30d/365d windows, serial read-only statements with
   finite timeouts. Inspect initial/feed/chart paths and competing lock/network
   explanations. Bound investigation to three causal hypotheses and three fixes.
2. Record causal chain and proposed correction before editing product source.
3. Regression net: exercise real homepage/chart URLs with deterministic fixtures,
   exact half-open date windows, old-only/zero brands, tracked scope and cache.
   Strengthen existing tests; demonstrate relevant pin red then green on localPG18.
4. Apply minimal convergent fix and compare the same production SQL workload.
   Production SQL evidence is not a claim of deployed application behavior.
5. Run required Bridgewright validation/prescription, affected assurance and
   relevant existing browser window/locale regressions, diff and lint review.
   Report required executed/skipped/errors honestly. Candidate release assurance
   requires a later authorized clean commit and exact-revision performance run.
6. Record findings and residuals here; stop owned browser/localPG resources.

## Debug Summary

**Problem:** Initial homepage responses are slow and30d charts abort at12s;
Gunicorn timeouts can also leave unrelated feed requests failing.

**Root Cause:** `home` calls `_build_home_chart_payload` after its feed projection;
`chart_html` calls the same builder. The builder calls `_build_home_pulse_payload`
before any chart aggregation. That helper executes current/prior correlated
PostBrand/Post counts for each of21brands. Production sampled the same query
running14.49s on DataFileRead, no blockers; the browser subsequently observed
chart/feed502s and more12/15s aborts. Cold ordinary1d counts also incur775ms.
The lock/network alternatives do not explain the observed SQL stack/plan.

**Fix:** Reuse the held chart session's reviewed grouped-count proposal in this
separate branch: one small brand metadata read plus one date-bounded aggregate
for both periods. Metadata merging preserves zero-count/old-only brands,
sentinels, scope, half-open boundaries, rounding, sorting, labels and caches.
Existing chart-owner files remain byte-untouched. No tables/migrations added.

**Recommended Tests / Prevention:** Existing tests protected the correlated
SQL shape rather than performance. Preserve their outcome assertions while
requiring one grouped count. New real/chart30d fixture pins all boundaries,
old-only/zero brands and excluded/sentinel inventory. New anonymous/home fixture
pins all four windows in en/zh_cn. Both regressions failed on original source
and passed after the minimal fix.

**Confidence:** High for the diagnosed query bottleneck and semantic parity.
Single-process sampled timings are not a deployment or load-capacity guarantee.

## Measurements and verification

- ProductionSQL, fixed08:00Z anchor, same21brands, serial read-only EXPLAIN
  ANALYZE with8s per-statement timeout: original1d775.410ms; grouped1d129.695ms,
  grouped30d2305.305ms, grouped365d3080.930ms. Plans saved in `.local/`.
- Full real homepage call on production host at4e60/PG18.4, in a separate
  short-lived process with session-only read-only protection and8s statement
  timeout. Demand recording disabled in that diagnostic process. Candidate
  helper substituted only in process memory; running web/service unchanged.
  Original1d1.676s (pulse0.509/feed0.215/render0.152); grouped1d1.084s
  (pulse0.100/feed0.188/render0.088); grouped30d4.136s; grouped365d8.284s.
  Cache cleared per scenario. Single sequential samples share PostgreSQL buffers
  and warm Python/template imports; not a controlled load benchmark. No data
  writes, new model/provider calls, service/scheduler mutations or deployment.
- Residual365d cost: chart bucket SQL2.670s; pulse2.477s; top-voice projection
 2.394s including0.940sSQL. This remains material cold-window work; no speculative
  cache/rollup/schema changes included in this correction.
-46PostgreSQL chart/pulse/inventory tests plus16subtests passed,0skips/errors.
-2real-browser tests plus6locale/viewport subtests passed,0skips/errors;
  repeated30d/365d windows commit before12s, warm cases below2s. Existing browser
  test already owns this behavior and was reused unchanged.
- Discarded test evidence: initial standalone browser invocation lacked DEBUG=1
  and redirected localHTTP toHTTPS. A subsequent run overlapped an assurance
  suite against the same testDB and saw foreign fixture counts. Both are local
  setup failures, not accepted product evidence. Suites rerun on separate
  task-owned PostgreSQL databases, with correct localHTTP settings.
- Ruff22baseline findings/22candidate findings/0new; test file clean;
  `git diff --check` passes. General declaration refreshed only its source hash
  after reviewing the Pulse-only `monitor/views.py` diff; all controls unchanged.
- Initial shared venv symlink allowed uv to refresh its editable package;
  restored the root package's original owning path immediately and replaced
  this worktree's symlink with a private virtualenv for remaining verification.

## Post-Fix Quality

**Scope:** Fix-owned files only, based on4e60, initially clean product tree.
**Simplify:** Inline reuse/quality/efficiency lenses, per AGENTS sequential tool
mapping. No additional abstraction or behavior-preserving cleanup warranted.
**Review:** Targeted manual diff review of counts, zero defaults, boundaries,
tracked inventory, cache behavior and actual callers; no additional findings.
Dedicated independent/cross-model review not run for this local investigation.
**Residuals:** Cold365d view remains8.284s in the sampled profile. Full exact-
revision candidate performance/assurance and production activation are pending
a later delivery request, not passed/waived checks.
**Re-verification:** Affected assurance complete:290passed,59subtests,
124requiredPostgreSQL executed,0skips/errors. JavaScript checks108+114 passed,
0failed. No commit/push/stage/deploy authorized.

## Completion evidence

Prepared local fix. Affected assurance exits0 after99.71spytest phase;
Pro declaration/control digests f084b72a/ba03d215; General5b2aa678/65f216d4,
5028/71normalized obligations prescribed respectively. Affected mode does
not seal or assess a full candidate obligation receipt; do not infer candidate
closure from pytest counts. General source identity is
`worktree-sha256:d55b021f61fab8ae185fa5a2fe87bd6efc97410f2f40f53126cc9d61c97f3aa7`.
Uncommitted source on branchfix/homepage-query-performance at4e60; no production
fix claimed. Final product diff46changed lines inmonitor/views.py; other source
is regression tests and a declaration identity update. All measurements/checks
predate only plan/coordination edits, which do not invalidate them.

Evidence under ignored `.local/`:production-browser-baseline.json,
production-query-benchmark.json, correlated/grouped-*-plan.txt,
production-home-profile.jsonl plus its exact read-only diagnostic program,
red-test.log/home-red-test.log, green-tests.log, browser-isolated.log,
affected-isolated.log and Ruff outputs. Initial contaminated/interrupted runs
retained separately and excluded from passed evidence. Production unchanged.

## Current owner direction — October 16

Owner requests: "actually subagent: let's deploy the fixes first, then we can
continue our conversation of optimization in the meantime". Deploy the existing
tested grouped-count correction through production, using a delegated delivery
session. Record production selection in Ollija metadata before following its
guide. Preserve all unrelated owners, current G3 schema and service activity;
no new authority for unrelated collection, provider calls, pauses or rollbacks.

Future optimization decision: owner says30-day comparisons only need daily
refresh and hourly precision is overkill; then explicitly extends the same rule
to365-day comparisons. Use daily refresh and daily-count precision for both
long-window percentage comparisons. Cutoff/timezone and freshness details belong
to that subsequent design. Do not add hourly rollups for these percentages or
include a new summary schema/scheduler policy in the present query-fix release.
The1-day view and independent chart/feed refresh behavior are not changed by
this decision. Earlier on-request/no-deployment statements describe the completed
investigation stage; this current production request supersedes that endpoint.

## Production delivery progress

2026-10-16: delegated release owns the existing fix through observed production. Staging is ahead at7178ea32/0090; production/base4e60 is ORM-free and compatible, but independent G3 ownership must finish before sharing that lane. Full candidate checks and focused independent review pending.

### Independent review correction and candidate verification

First clean candidateaa60ae15 passed343tests/75subtests/177requiredPostgreSQL with0skips/errors, node108+114, and5028/5028normalizedUI obligations. Local performance was sealed clean at96ffc5269956478496930f93 (two desktop/two mobile runs); mobile LighthouseLCP7.10s remained advisory. These are superseded product-source evidence after the following necessary correction.

External Claude route returned402before review; the sole replacement Grok route reached its600-second hard limit without usable output. Independent in-process adversarial review found a realP2: database ICU-equivalent FK spellings were lost by a case-sensitive Python dict merge. A real anonymous/chart caller regression was red forUP→up and decomposedcafé→canonicalcafé: both counts became0. The corrected aggregate starts from the already-scoped Brand queryset, selects canonical brands.nickname, and keeps shared date bounds inWHERE plus two periodFILTER counts. No normalization/data rewrite is needed.22pulse tests/16subtests/22requiredPG now pass0skips/errors. Independent re-review returns0remainingfindings; original/corrected receipts are under machine-local /tmp/compound-engineering-501/ce-code-review/20261016-homepage-release.

New serial read-only production process measurement of the corrected source on4e60/PG18.4:1d1.100s (Pulse0.110s),30d4.496s (Pulse2.122s),365d8.456s (Pulse2.478s). These single samples preserve the improvement and remain diagnostics, not deployed proof. Fresh full candidate assurance/performance follows the correction commit. No product schema, collectors or summary policy changed.
