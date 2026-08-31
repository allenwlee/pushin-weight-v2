---
title: fix/headline-oversized-batch plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-headline-oversized-batch-2026-08-31-025724
  branch: fix/headline-oversized-batch
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-oversized-batch`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-oversized-batch/docs/plans/2026-08-31-025724-fix-headline-oversized-batch-plan.md`
- Change: `fix-headline-oversized-batch-2026-08-31-025724`
- Branch: `fix/headline-oversized-batch`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-oversized-batch/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-oversized-batch/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-oversized-batch` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-oversized-batch` without `--force`.
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

- 2026-08-31 owner-approved staging-lane handoff: the live staging candidate
  `77ef5cee3f90778df8a10c98a9ecbce4438069b0` is being displaced so the urgent
  Account User About continuation can pass staging and restart in production.
  Preserve this feature branch and worktree. The shared `staging` history will
  contain explicit reverts of this candidate before the About-user change, so
  resuming this work requires reapplying the intended headline diff as a fresh
  commit atop the then-current `staging` branch, rerunning
  `./bin/ollija annotate-plan <plan-path> --check`, and repeating staging
  verification. Do not force-push the original candidate back onto `staging`.
- 2026-08-31 production override: after reviewing the staging result, the
  owner explicitly instructed Ollija to push and deploy this headline change
  to production. The exact-SHA 1-day path passed on staging with a 32-brand
  active run and successful DeepSeek rank/editor/critic calls. The owner was
  informed that staging's 256 MB PostgreSQL tier timed out while building the
  7/30/365-day snapshots, whereas production uses the 1 GB tier. This override
  permits promotion despite that staging-capacity mismatch; it does not permit
  applying `render-staging.yaml` to production or changing production data,
  schedules, credentials, or resource topology.

# Goal

Prevent an irreducibly oversized five-brand editor packet from leaving a trend
narrative run permanently `preparing` and blocking every newer cutoff for that
window.

## Product Contract

- Keep five brands as the normal editor-batch target.
- When a five-brand packet cannot fit the existing 128 KiB provider ceiling
  after text compaction, split only that packet into smaller deterministic
  batches until each packet fits.
- Preserve every eligible brand and its evidence; packet fitting must not
  silently drop a brand or evidence row.
- Preserve the rank order across the split batches and give every emitted
  batch a unique, stable key so editor and critic call entitlements remain
  idempotent.
- A real-shaped oversized batch must progress through the production
  reconciliation call chain instead of leaving the run and work slot stuck.
- Add a focused packet test and a production-call-chain regression test, then
  run the adjacent headline candidate/task suites.
- Keep the staging build entry point retryable when `DATABASE_URL` is missing:
  it must return before Django setup so Ollija's required staging-access check
  and the direct Render script boundary remain valid.
- Keep staging headline controls role-for-role with production: the web service
  serves `prefer_per_brand`, the queue-only headline worker may call the pinned
  provider, and the dormant/manual staging harvester may enqueue completed
  cycles. Staging remains isolated and does not gain a recurring harvest.
- Verify a fresh staging narrative reaches the visible per-brand projection;
  a green deploy with the UI still reporting `Disabled` is not acceptance.
- Delivery continues through production, as explicitly selected by the owner
  after reviewing the staging result and recorded exception above.
