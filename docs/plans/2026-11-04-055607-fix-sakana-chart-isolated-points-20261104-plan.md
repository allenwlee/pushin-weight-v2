---
title: fix/sakana-chart-isolated-points-20261104 plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-sakana-chart-isolated-points-20261104-2026-11-04-055607
  branch: fix/sakana-chart-isolated-points-20261104
  workflow: work
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  delivery_route_selected_by_user: false
  staging_transport: branch
---
## Plain-English Summary

Keep isolated one-post buckets visible on the homepage when filtering to Sakana AI or another low-volume brand. Both values remain in the data; the current minute chart converts zero buckets to gaps and hides ordinary point markers, leaving isolated values with no drawable segment.

Use small brand-shaped markers only for isolated nonzero values, preserving the existing line style, gaps, feed, counts, filters, and collection behavior. Verify the actual homepage and brand-pill replacement in a real browser with deterministic posts and visible canvas pixels in English and Chinese. No schema change. Owner now requests production delivery; release checks and observed deployed/browser verification are required.

## Scope and verification

- TOUCH: monitor/static/pw-chart.js sparse-value rendering; existing chart browser regression suite.
- PRESERVE: other chart styling and continuous segments, totals/feed contents, time zones, all filters and collection.
- Reproduction: production /, anonymous, zh_cn,1280x577, one-day window. Both before/after brand filtering contain two Sakana buckets with value1; zero buckets become NaN and pointRadius is0, so isolated values have no visible line segment. Latest production source b0d0307b.
- Browser-only probes changed chart runtime temporarily in an isolated browser; no production source/data mutation.
- Assurance validation/prescription clean:5191 obligations; control model dd9ec46338b46319778fcdd872cd383d4fdcb8dad22263b0324247b49e4989ee.
- Regression net: real ORM posts → homepage view/template → actual Chart.js canvas → brand-pill request/replacement; verify both isolated positions have visible brand-colored pixels and feed retains posts. Existing axis/style/focus/hover tests and affected assurance gate protect nearby behavior.
- Shared test database has peer Chatter migrations through0224 plus affiliation0221. Temporary matching migration files are test compatibility overlays only, excluded from delivery. Empty temporary0222_local_test_compatibility was applied then unapplied immediately; existing schema/function/peer ledger preserved.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/sakana-chart-isolated-points-20261104`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/sakana-chart-isolated-points-20261104/docs/plans/2026-11-04-055607-fix-sakana-chart-isolated-points-20261104-plan.md`
- Change: `fix-sakana-chart-isolated-points-20261104-2026-11-04-055607`
- Branch: `fix/sakana-chart-isolated-points-20261104`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/sakana-chart-isolated-points-20261104/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/sakana-chart-isolated-points-20261104/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `work`
- Delivery target: `production`
- Owner selection recorded: `true`

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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/sakana-chart-isolated-points-20261104` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/sakana-chart-isolated-points-20261104` without `--force`.
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

# Goal

<!-- Planner: replace this requirements-only placeholder with the change goal. -->

## Product Contract

<!-- Planner: define the user-visible contract, acceptance cases, and verification. -->

## Local implementation checkpoint

- New real-browser regression failed before the fix: two parsed value1 points had zero Sakana-red pixels.
- Added drawIsolatedPoints to the existing public chart plugin: only positive finite buckets whose immediate neighbors are gaps receive a small brand-shaped marker. Final slot keeps existing beacon. Continuous lines, gap semantics, pointRadius0 defaults and feed unchanged.
- Same regression green afterward, covering initial all-brand and filtered canvas in en/zh_cn plus feed retention.
- Node chart122passed; feed formatter125passed; timezone tests pass. Changed Python test lint and whitespace checks pass.
- Assurance validate/prescribe clean for home5191 and General71 declared obligations; this is structural prescription, not completed obligation evidence.
- Affected gate attempted with shared-db wrapper, stopped before tests because peer Chatter session holds exclusive database lock. Waiting without interrupting that session or creating a database copy.
- No commit/push/deployment authorized for this bug report. Preserve local worktree for review.

## Final local verification and residuals

- Affected gate initial product run:422passed,140subtests passed; one General assurance source-identity mismatch. Updated only general-declaration.json.source_revision to reviewed current product hash cead11f43245faa7690bfd3df4773efb2d512ae50243b32cfb5237c006bb47f3; control model/fixture/expectations unchanged. Its product identity inputs exclude pw-chart.js; the mismatch predated this rendering fix.
- Repeated affected gate:421passed,134subtests passed; two Pro cases failed because a late synthesis demand write deadlocked with test teardown TRUNCATE, leaving rows for the next setup. No chart failure. This combined command is not claimed clean.
- Exact General/Pro replays after lock release:3passed,6subtests passed,3required PostgreSQL cases executed, zero skips/errors. All423affected cases now have passing results across the final full run plus replays on the same product/fixture/dependency/environment inputs. Prior valid421case evidence reused; no assertion waived or excluded. Shared-db lock contention attempts ran no tests and are not counted as passes.
- Node:122chart assertions pass,125feed formatter assertions pass, timezone checks pass. Focused pre-fix pixel check red and post-fix green. New browser test covers both en and zh_cn and all-brand→Sakana filtering with actual URL/view/template/assets/requests/canvas/feed.
- Review: targeted source scan confirms only isolated positive buckets receive markers; latest slot retains beacon, ordinary lines keep pointRadius0, focus dimming/brand shapes preserved; no reader/writer/API change. No unrelated source changed.
- Temporary Chatter migration compatibility files removed. Only a temporary empty merge ledger was added/unapplied during setup; existing shared schema, affiliation trigger and peer0220–0224ledger preserved.
- No candidate release/performance assessment or deployment claimed: current endpoint is local bug fix. Combined gate's transient synthesis/teardown race remains an unrelated test-harness residual despite successful replays. A release request must use applicable candidate assurance/performance checks; keep this evidence and its exact scope.

## Production continuation

Owner requests production deployment. Current product evidence is reused where unchanged; perform clean candidate assurance and candidate performance measurement, review, non-forced authorized delivery, observed exact-SHA deployment and live Sakana pixel/filter verification. Route choice requested because default staging holds separate Chatter work. No staging/peer code is included.
