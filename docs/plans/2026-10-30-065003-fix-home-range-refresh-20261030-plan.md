---
title: fix/home-range-refresh-20261030 plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-home-range-refresh-20261030-2026-10-30-065003
  branch: fix/home-range-refresh-20261030
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
---
# Homepage range refresh repair

## Plain-English Summary

A single click from 365 days to 30 days or from 30 days to 7 days should update the chart and Pulse together. A failed request must visibly explain that the previous result remains displayed. Reuse existing saved counts for the seven-day comparison without changing its exact rolling boundaries or any collection/worker behavior.

Verify the real homepage in Playwright, including descending ranges, a controlled timeout and recovery, exact PostgreSQL count parity at partial bucket boundaries, historical corrections, and existing state/race regressions. The owner selected production deployment on October30 and explicitly approved direct production delivery after release preparation. Complete review, candidate UI/performance verification and exact deployed-revision readback. The unaccepted product-release work remains excluded.

## Scope and observed cause

- Base/live web revision: `c445ec24701c3c28decf661844b6d7402f551e2a`; clean isolated feature worktree before this task. Root checkout has unrelated peer documentation changes; preserve them.
- Production browser: anonymous `/`, zh_cn, Asia/Tokyo, Chromium 1280x577. First seven-day request aborted while selector=7 and chart/Pulse=30; another click succeeded in242ms. Initial `?days=365` was an invalid query parameter and is not used by the regression; valid parameter is `window`.
- Render2026-10-30T03:59:10Z worker timeout stack ends in `monitor/views.py::_build_home_pulse_payload` raw count. The browser deadline is12s and all AbortErrors are silently ignored. This explains the stuck projection; the owner's exact502/503 reload is not independently correlated. Gunicorn's subsequent SIGKILL message is not proof of memory exhaustion.
- Seven-day Pulse always scans14days;30/365 already reuse saved counts. Warm raw production count measured576.816ms; cache cost varies; do not represent that warm sample as the failed request's latency. Saved history exists with a dirty prefix boundary requiring exact live-tail recounts.

## Implementation and regression net

1. Extend existing `read_home_counts` to exclude partial first/midpoint buckets from saved counts and count them from source alongside the exact live/dirty tail. Preserve one snapshot and dirty-boundary race guard; no new tables/columns/migrations.
2. Use that reader for7d Pulse; preserve1d behavior and30/365 midnight semantics. Preserve the existing one-minute7d cache contract; invalidate30/365 by publication identity as before.
3. Distinguish the current request's deadline from superseded/cancelled requests in `pw-chart.js`; show existing localized failure status on deadline, keep last good chart, preserve latest-request-wins.
4. Regression: existing caller-level materialization tests plus6new real-root/chart endpoint cases with subsecond boundaries and historical corrections; one new real homepage browser test for365→30→7, timeout visibility and recovery. Existing Node request races and affected UI assurance gate.

## Verification record

- Bridgewright assurance validate/prescribe clean:5191 obligations, control-model `dd9ec46338b46319778fcdd872cd383d4fdcb8dad22263b0324247b49e4989ee`.
- Red: new materialization cases fail because7d caller never requests midpoint-based saved counts. New real-browser timeout test fails waiting for visible failure status (plus an initially incompatible test teardown; receipt retained).
- Green:120 backend tests plus16subtests; new real-browser365→30→7/timeout/recovery test passes;122 existing Node assertions pass. No required skips/errors in the green focused runs. One test-clock setup issue initially kept the accelerated deadline during recovery; corrected to restore the real timer before recovery without changing the product.
- Production read-only query comparison at the same fixed window: exact counts match; warm raw query576.816ms, candidate470.548ms. This is one SQL sample, not end-to-end or cold-load acceptance. Prefix reflects active historical corrections; no materialization refreshed in production.
- Lint: helper/new backend test clean;20view and7existing browser-file findings match baseline exactly. Existing tests were not weakened or rewritten.
- Broader affected UI assurance is running; any failures remain failures until diagnosed.
- Why this escaped: existing abort coverage treated superseded cancellation and own deadline alike; ascending fast-fixture ranges did not exercise a stalled descending switch. The7d comparison had no saved-history path for sub-quarter-hour rolling bounds.
- Shared test DB already includes0206 from PR74. Exact0206migration is a temporary untracked loader-only compatibility file, hash recorded outside repository; never migrate, integrate or deliver it. Remove only after hash verification once testing finishes. Production remains0205, verified2026-10-30. Owner explicitly confirms0206is unaccepted; its models/migration are excluded from this patch. A private test-only teardown adapter includes its four already-existing child tables in normal test-row TRUNCATE, preserving FK checks and schema; it is not delivered or used in production.
- Operational receipts: `/Users/fuchitalee/.local/share/render-operations/2026-10-30-home-range/`.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/home-range-refresh-20261030`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/home-range-refresh-20261030/docs/plans/2026-10-30-065003-fix-home-range-refresh-20261030-plan.md`
- Change: `fix-home-range-refresh-20261030-2026-10-30-065003`
- Branch: `fix/home-range-refresh-20261030`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/home-range-refresh-20261030/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/home-range-refresh-20261030/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `production`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. On the owner-selected direct route, fetch the remote production lane: `git fetch origin refs/heads/main`.
5. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
6. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
7. After step 6 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/home-range-refresh-20261030` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/home-range-refresh-20261030` without `--force`.
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

Owner requests “deploy” twice on October30, then answers “approve” to the explicit direct-production question after the tested candidate is pushed. Direct production delivery is selected; staging is omitted, not reported as passed. The shared staging branch/image is0a974d77 and contains unaccepted PR74 work; preserve it and exclude its migration/models/four tables from Git and production.

The deployment commit adds only this plan's approval and verification record to tested product-source revision `d9f66ff02ffe422ff66e15ae11a9e253854e4e52`. Reuse its 495 tests, 5191-obligation assessment, focused checks and sealed performance result: application code, assets, dependencies, tests, fixtures and runtime assumptions are unchanged. Verify the documentation-only diff before promotion, and observe the actual deployment commit in Render and the production browser. This is a real authorization record, not an empty source commit or a substitute for a missing runtime prerequisite.

## Regression acceptance

- A single descending365→30→7click updates chart/Pulse from the real endpoint; active selection and committed payload share a window.
- A current request deadline shows the existing localized failure status while preserving last-good data; recovery and superseded-request cancellation remain correct.
- Exact `[start,end)` counts match source at subsecond first/midpoint boundaries, including old corrections and publication races.
- No new persistence, collection changes, workers or source-query changes.


## Remaining verification and delivery

Finish the correctly configured affected assurance run, retain separate failed/incompatible observations, and remove only the hash-pinned test-only0206loader file. Production verification of the owner's exact502/503reload remains outstanding; a warm SQL comparison does not establish that symptom resolved. Candidate release/performance sealing follows only a later selected delivery endpoint.


## Test runner correction

The first affected assurance invocation used the wrapper's maintenance `run` route, which does not pin nested pytest's TEST database name. Django selected `test_test_pw_g3_timing_20261019`; its normal teardown removed that database, verified absent afterward. The designated shared database identity and schema remain intact. The supported `--pytest-wrapper /Users/fuchitalee/.local/bin/pushinweight-test-db` option now invokes the guarded pytest route directly. No wrapper guard is bypassed. First-run failures are retained, not called passed. Two dataset-sensitive failures pass against basec445ec24 on the intended shared database; source was restored hash-for-hash. General's source-only declaration identity was refreshed for the changed views.py; controls and obligations remain unchanged.

## Local completion — October30

- Corrected affected gate exits0:422tests/140subtests,178required PostgreSQL tests,0skips/errors. Node suites pass122chart assertions and125feed assertions, plus timezone checks. Corrected gate command: `PYTHONPATH=<OPS>:. PYTEST_PLUGINS=pw_home_test_schema uv run --extra dev python -m tests.ui_assurance.gate --scope affected --pytest-wrapper /Users/fuchitalee/.local/bin/pushinweight-test-db`.
- Focused backend120tests/16subtests and the new browser test pass separately. Initial browser regression red; current deadline feedback and exact365→30→7recovery green.
- Pro declaration5191obligations/control-modeldd9ec463… and General71/control-model65f216d4… retained; affected gate passed. No formal candidate sealing/performance claim: uncommitted local implementation only, not a released candidate.
- Temporary0206loader removed after exact hash check; no migration remains in the diff. Shared DB schema/persistent instance preserved; test-row cleanup follows ordinary exclusive-use isolation. No production mutation, worker/schedule change, paid provider/model call, commit or push.
- All product-source and lint checks complete. Remaining production502/503correlation and exact-revision candidate/performance/deploy proof require a later selected delivery endpoint. Keep this dirty feature worktree and branch.

## Production continuation — October30

- Production grant: owner explicitly says “deploy” twice. Existing implementation scope and unaccepted0206 exclusion retained. Remote main/live web=c445ec24; staging branch/live web=0a974d77, carrying independent product-release work.
- Asked which permitted route to use: stage exact homepage commit without moving shared staging branch, then production; or direct production after checks. No route answer has arrived yet. This does not block independent review/commit/candidate verification, but dependent deployment must retain the question.
- Review found that unconditional partial-bucket OR predicates could widen existing aligned source scans. Preserve the original concrete boundary predicate whenever both boundaries align. Two new caller-level scan-bound tests red before correction, green afterward. Final focused suite123tests/16subtests,0requiredskips/errors; helper/new tests lint clean.
- Internal GPT correctness, SQL/performance and request-race review in the primary session per AGENTS's sequential tool mapping. External Claude route remains excluded; no independent cross-model claim. Partial-boundary exactness, historical correction race guards and latest-request-wins preserved; no unresolved introduced finding after the aligned-scan correction.
- Candidate assurance/performance and deployment observations remain pending. No schema/runtime mutations or production pauses are authorized or needed.

## Exact-candidate release preparation — October30 17:30 JST

- Committed and remote-verified candidate: `d9f66ff02ffe422ff66e15ae11a9e253854e4e52`, branch `fix/home-range-refresh-20261030`. Production main remains `c445ec24`; staging remains `0a974d77`. No PR or deployment performed.
- Candidate test phase:495passed/198subtests,251required PostgreSQL tests executed,0requiredskips/errors. Node122chart/125feedassertions and timezone checks pass. Structural assessment:5191/5191required obligations passed,0failed/skipped/errored/missing/unknown. Configured Ollija checks36passed.
- Candidate gate command initially exited1during private performance-fixture setup: incorrect Account.geolocation field. Corrected fixture to existing based_in_location with an exact row-count assertion. First actual performance attempt0368fcdb19a4b010348a4c5c invalidated by test-server static handler omitting WhiteNoise cache headers; evidence retained. Route fixture static requests through the project's actual WhiteNoise middleware; assert real200andCache-Control before measuring. No product code or acceptance requirement changed. Reuse completed candidate test/assessment evidence because only private fixture setup changed; do not claim the initial command exited0.
- Repaired public performance-run and performance-result exit0, clean sealed attempt `2ce2f5432a63febe1aed3d44`, target exact candidateSHA, evidence digest `5fb29b0bc2a6bc2057fda942993a7861866618f75a0991dd420c542738ad9d9e`; fixture cleanly tears down and releases shared DB lock. Desktop/mobile2samples each; required budgets/network/cache checks clean. Lighthouse medianLCP desktop1.72s/mobile9.41s (mobile remains above advisory6s, not a blocking target); synthetic local measurement is not production timing proof. Functional range probe passed with one click per transition,179ms/149ms in the initial repaired fixture; final probe receipt retained separately. No production performance claim.
- Removed temporary0206loader only after exactSHA256verification. No migration/schema/product-release integration. Private test scripts/receipts remain outside Git.
- All remaining independent release preparation is complete, including a bounded production browser smoke script for exact revision,3cache-disabled loads and365→30→7chart/Pulse agreement. Pending required route choice remains unanswered. AGENTS.md explicitly requires owner selection for direct production or exact-commit staging; shared staging contains unaccepted work and an active peer pilot. No production/staging Git ref or service changed.
- This final execution record is a local plan-only change after the tested/pushed candidate; product source/tests/dependencies are unchanged. Preserve worktree and branch pending the route answer; do not remove a dirty or undeployed worktree.
