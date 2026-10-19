---
title: fix/post-counter-zeros plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: execution-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-post-counter-zeros-2026-10-19-005316
  branch: fix/post-counter-zeros
  workflow: work
  delivery_target: production
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/post-counter-zeros`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/post-counter-zeros/docs/plans/2026-10-19-005316-fix-post-counter-zeros-plan.md`
- Change: `fix-post-counter-zeros-2026-10-19-005316`
- Branch: `fix/post-counter-zeros`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/post-counter-zeros/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/post-counter-zeros/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/post-counter-zeros` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/post-counter-zeros` without `--force`.
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

# Preserve initial engagement zeros

## Plain-English Summary

Known zero likes, reposts, replies and quotes must be saved as zero when a natural harvest first inserts a Post. The same writer must accept a counter decreasing to zero. Production delivery, including commit/push/merge, is explicitly authorized by the owner through the current delegated continuation and immutable handoff.

Use explicit None-aware fallback for the four reads. Keep existing positive/camelCase inputs and sparse update behavior. Preserve refresh timing, optional counts, existing NULL history, models, queries, providers and schedulers. Verification covers the real cycle path, writer edge cases, hosted checks, staged deployment and natural pre-refresh production rows.

## Product Contract

- Four supplied snake_case zeros persist on insert and update and take precedence over stale alternate positive keys.
- Positive values persist; camelCase inputs remain accepted; snake_case None falls back to camelCase.
- Absent/None partial counters do not erase existing values. Unknown view/bookmark counts stay unknown.
- Existing Post storage is suitable; zero tables, columns or migrations added/retired.

## Execution and regression net

1. Add a regression in `tests/test_cycle_cursor_wiring.py` using `_normalize_tweet`, fake API, real CycleRunner and actual Post. Prove red before fix.
2. Add focused writer create/update cases in `tests/test_account_field_freshness.py`. Apply only four None-aware fallbacks in `monitor/cycle.py`.
3. Run focused PostgreSQL tests and adjacent normalization, metrics-refresh and backfill coverage. Run configured `pytest tests/ollija`, applicable lint/checks and exact-diff hosted suites. Required skips/errors fail.
4. Review the narrow diff sequentially. No external model review or provider calls authorized by this task.
5. Verify shared stage occupancy, reserve bounded use in authoritative root index, push unchanged candidate to staging, observe exact SHA and provider-free staging checks. No manual harvest/provider acceptance.
6. Promote unchanged reviewed SHA to main, observe exact production services including harvest, inspect a natural cycle and read-only freshly inserted pre-refresh counter evidence.
7. Literal latest-20 health cohort then same-ID recheck after 30-minute grace; report preexisting enrichment defects separately. Notify originating parent immediately when release and zero proof are complete.
8. Record receipts in ignored `.ollija/state/post-counter-zeros-20261019/` and authoritative root index. Guarded clean canonical-worktree removal is final filesystem action after production verification; preserve branch.

## Boundaries and resource guard

No historical NULL rewrite/backfill, schema/model/UI or optional-counter change. No extra provider/model call, manual harvest, cron pause/resume, credential/config/schedule change. Serial read-only production queries use transaction read-only and bounded time/lock limits. Shared staging receives one coordinated release lane; preserve other jobs/claims. Missing infrastructure gets cause-specific repair and a prompt parent notice.

## Evidence ledger

- Base: fresh `origin/main` a5f7b230673488722799b95cba88e05431d8b932.
- Source: initial writer drops normalized zero through `or`; metrics writer already preserves zero. Provider normalizer already supplies four numeric counters.
- Red proof: corrected real scheduled/backfill call-chain tests each persisted one Post but observed four NULL counters; writer tests independently rejected NULL and stale-alternate values. Red logs retained privately.
- Green: 253 focused tests passed in37.50s; required PostgreSQL executed110/skipped0/errors0. Sparse-new-row assertion added afterwards:2/2 passed, required2/skipped0/errors0; prior source/test evidence remains valid.
- `manage.py check`, `makemigrations --check --dry-run` and `git diff --check` pass. Ruff on changed tests has six preexisting findings outside changed lines; no changed-line lint finding. No unrelated cleanup.
- Sequential local review covers zero/positive precedence, None fallback, sparse create/update, real scheduled/backfill persistence and unchanged optional counts. No independent/external-model review claimed.
- Hosted, staging, production and health receipts pending at candidate publication; retained runtime evidence in ignored state, copied to authoritative root before cleanup.
