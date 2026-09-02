---
title: fix/headline-cadence-cost plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-headline-cadence-cost-2026-09-02-114744
  branch: fix/headline-cadence-cost
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `./bin/ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-cadence-cost`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-cadence-cost/docs/plans/2026-09-02-114744-fix-headline-cadence-cost-plan.md`
- Change: `fix-headline-cadence-cost-2026-09-02-114744`
- Branch: `fix/headline-cadence-cost`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-cadence-cost/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-cadence-cost/render.yaml`
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
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the Render deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the Render deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-cadence-cost` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-cadence-cost` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

### Failure handling

- Never promote a staging candidate whose automated checks failed.
- Implementation failures return to the parent implementation workflow for diagnosis, correction, recommit, and restaging.
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

Reduce headline-provider spend by slowing the narrative refresh schedule,
including changing the 1-day headline from a 30-minute to an hourly cadence.
This is a scheduling-only change: harvesting, enrichment, prompts, models,
headline rendering, and provider-call graph semantics remain unchanged.

## Product Contract

- The 1-day headline becomes due every 1 hour and stale after 2 hours.
- The 7-day headline becomes due every 1 day and stale after 2 days.
- The 30-day headline becomes due every 7 days and stale after 14 days.
- The 365-day headline becomes due every 30 days and stale after 60 days.
- A regression test must exercise the production configuration through the
  existing config loader and pin all four cadence/staleness pairs.
- Existing lifecycle scheduling tests must remain green, proving that the
  change does not alter coalescing, retry, publication, or work-slot behavior.
- The owner explicitly authorized commit, push, staging verification, and
  production deployment on 2026-09-02. The harvest cron is not paused.

## Implementation

1. Add a failing config regression test for the requested cadence map and the
   required two-times-cadence stale map.
2. Change only `headline_narrative.cadence_minutes` and `stale_minutes` in
   `config.yaml`, unless an existing validator prevents the requested values.
3. Run the focused config and trend-narrative lifecycle/task suites, then run
   Django's deploy check and review the final diff for scope.

## Verification

```bash
pytest tests/test_config.py tests/test_trend_narrative_generation.py tests/test_trend_narrative_lifecycle.py tests/test_trend_narrative_tasks.py tests/test_trend_narrative_orchestration.py
python manage.py check --deploy
```

The focused regression must fail against the former values and pass only with
`{1: 60, 7: 1440, 30: 10080, 365: 43200}` plus matching stale values
`{1: 120, 7: 2880, 30: 20160, 365:
86400}`.

## Verification Results

- Both cadence regression tests failed against the former 30-minute 1-day
  values, then passed after the scheduling-only adjustment.
- The production orchestration regression was repinned to exercise the full
  1-hour, 1-day, 7-day, and 30-day thresholds through the worker call chain.
- The full focused headline suite passed with local PostgreSQL: 94 passed,
  0 skipped, including all 50 PostgreSQL-required tests.
- The Ollija delivery suite passed: 74 passed.
- `python manage.py check --deploy` completed successfully with the three
  repository-pre-existing security warnings.
- `git diff --check` passed.
