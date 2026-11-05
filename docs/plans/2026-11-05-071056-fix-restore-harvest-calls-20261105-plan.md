---
title: fix/restore-harvest-calls-20261105 plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-restore-harvest-calls-20261105-2026-11-05-071056
  branch: fix/restore-harvest-calls-20261105
  workflow: work
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/restore-harvest-calls-20261105`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/restore-harvest-calls-20261105/docs/plans/2026-11-05-071056-fix-restore-harvest-calls-20261105-plan.md`
- Change: `fix-restore-harvest-calls-20261105-2026-11-05-071056`
- Branch: `fix/restore-harvest-calls-20261105`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/restore-harvest-calls-20261105/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/restore-harvest-calls-20261105/render.yaml`
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
4. On the owner-selected direct route, fetch the remote production lane: `git fetch origin refs/heads/main`.
5. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
6. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
7. After step 6 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/restore-harvest-calls-20261105` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/restore-harvest-calls-20261105` without `--force`.
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

Owner explicitly requests immediate restoration and direct production. Preserve staging and uninterrupted harvesting. No diagnostic provider calls. Existing posts/labels are not rewritten. Keep the mandatory byte-limit skill rule and runtime UTF8 guard.

# Restore previous production harvester

## Plain-English Summary

Restore the exact pre-refactor queries and matching implementation from production revision11e9fc2. Remove only the137keyword rows added by the refactor, with exact natural-key/timestamp guards, so old matching does not continue using newly introduced ambiguous aliases. Keep Dots/Xiaohongshu identity links and unrelated releases. No tables or columns added or retired.

## Implementation and regression net

- Restore refactor-touched runtime files and corresponding baseline tests from11e9fc2; retain UTF8 byte guard.
- Audit every restored enabled query including author exclusion and timestamp bounds. Any oversize query must be shortened by equivalent Boolean spelling before dispatch; never bypass guard.
- Run baseline query/planner/attribution/cycle coverage and focused DB tests using shared permanent DB wrapper if required.
- Review exact diff, annotate/check, commit and normal push main, observe exactSHA on Render web/harvest. No staging changes or scheduled run interruption.
- Restore keyword inventory via bounded guarded transaction using saved before/after snapshots; retain receipt and verify baseline required tokens.
- Inspect normal scheduled cycle logs/DB without starting a harvest or provider probe. Finish with guarded canonical worktree cleanup after production proof.

## Verification and review

153 focused pure tests passed,0skips/errors.31 database tests passed on first run;1invalid frozen-rare fixture corrected to a valid bounded query and re-run passed,0skips/errors (32distinct requiredPostgres tests). Runtime code equals11e9fc2 apart from retained UTF8 guard; policy removes only redundant dots3-note and Hy4/Hy5-preview search aliases already subsumed by dots3/Hy4/Hy5. All10enabled full requests audited. Baseline legacy tests adapted to current planner API, preserving assertions. Temporary compatibility migration files removed; only empty test merge marker unrecorded, no schema operations. Manual review checked all source diffs against baseline, schema unchanged, before/after keyword keys/timestamps, and no changes to Dots identity, service topology or staging.
