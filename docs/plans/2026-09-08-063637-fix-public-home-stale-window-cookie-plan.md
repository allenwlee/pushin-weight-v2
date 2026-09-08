---
title: fix/public-home-stale-window-cookie plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-public-home-stale-window-cookie-2026-09-08-063637
  branch: fix/public-home-stale-window-cookie
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/public-home-stale-window-cookie`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/public-home-stale-window-cookie/docs/plans/2026-09-08-063637-fix-public-home-stale-window-cookie-plan.md`
- Change: `fix-public-home-stale-window-cookie-2026-09-08-063637`
- Branch: `fix/public-home-stale-window-cookie`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/public-home-stale-window-cookie/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/public-home-stale-window-cookie/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/public-home-stale-window-cookie` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/public-home-stale-window-cookie` without `--force`.
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

Prevent a legacy one-year `home_window` cookie from forcing an expensive
365-day query during initial public-home navigation.

The owner explicitly authorized promotion of the staging-verified candidate to
production on 2026-09-08.

## Product Contract

- The public `/` route defaults to the one-day window unless a valid explicit
  query or filter payload selects another allowed window.
- Public home ignores the shared legacy `home_window` cookie without deleting
  it, preserving internal and brand-page window persistence.
- Runtime feed/chart requests continue to honor their explicit window state.
- Internal and brand-page cookie behavior remains unchanged.
- No visual, scrolling, filtering, locale, chart, or feed-row behavior changes.

## Regression Net

- A real-browser regression starts with both legacy v1 local storage and a
  `home_window=365` cookie, then proves `/` renders the one-day state without
  startup chart/feed refetches while leaving the shared cookie intact.
- Bridgewright desktop and mobile assurance scenarios seed the same stale
  cookie so the production-like state remains covered.
- Existing focused Django, browser, declaration, and affected assurance checks
  remain green.

## Implementation

1. Strengthen the owning browser and performance-declaration tests so they fail
   on the production stale-cookie path.
2. Scope cookie suppression to the public initial home response; keep the
   shared cookie, explicit URL/filter state, and all other routes unchanged.
3. Run focused tests, the affected Bridgewright gate, and the original browser
   reproduction before handoff.

## Verification

- Red proof: the DB-free production call-chain tests rendered 365 days from the
  legacy cookie before the product change.
- Focused PostgreSQL + Chromium proof: 8 tests passed, including the stale
  cookie/local-storage migration scenario with zero startup feed/chart fetches.
- Bridgewright assurance validation, prescription, and performance declaration
  validation all returned clean.
- Affected assurance gate: 82 Python tests and 14 subtests passed with all seven
  required PostgreSQL checks executed; chart, feed, and timezone JavaScript
  contract suites also passed.
- Django system check, focused Ruff check, and `git diff --check` passed.
