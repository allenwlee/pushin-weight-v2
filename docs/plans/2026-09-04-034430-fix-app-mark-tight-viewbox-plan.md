---
title: fix/app-mark-tight-viewbox plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-app-mark-tight-viewbox-2026-09-04-034430
  branch: fix/app-mark-tight-viewbox
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/app-mark-tight-viewbox`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/app-mark-tight-viewbox/docs/plans/2026-09-04-034430-fix-app-mark-tight-viewbox-plan.md`
- Change: `fix-app-mark-tight-viewbox-2026-09-04-034430`
- Branch: `fix/app-mark-tight-viewbox`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/app-mark-tight-viewbox/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/app-mark-tight-viewbox/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/app-mark-tight-viewbox` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/app-mark-tight-viewbox` without `--force`.
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

- Owner explicitly selected production delivery for this app-mark fix on
  2026-09-04. Ship only the sprite viewBox, its focused assertions, and this
  plan; make no CSS, layout, database, harvest, or scheduler changes.

# Goal

Remove the internal canvas padding from the masthead `mark-quiet` symbol so its
visible path fills the unchanged app-mark height and maximum proportional width.

## Product Contract

- Change only the runtime `mark-quiet` symbol viewBox and focused assertions.
- Preserve the exact mark path, color inheritance, 18px/14px responsive icon
  boxes, margin, app-name typography, layout, and every other sprite symbol.
- At desktop and mobile widths, the visible mark fills the app-mark box height;
  its width remains proportional rather than stretched.

## Units

### U1 — Tight mark viewBox

- Replace `mark-quiet`'s padded `0 0 24 24` viewBox with the measured path bounds.
- Do not change CSS or template usage.

### U2 — Regression net

- Pin the one exceptional runtime viewBox while keeping every other symbol at
  `0 0 24 24`.
- Exercise the real homepage in Chromium at desktop, mobile, and 320px widths;
  require the rendered mark height to equal its unchanged icon-box height.

## Definition of Done

- Focused structural and browser tests pass with zero skips or errors.
- Chromium reports full-height visible mark geometry and no page/console errors.
- The scoped diff contains only the sprite line, its focused tests, and this plan.
