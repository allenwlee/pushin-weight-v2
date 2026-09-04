---
title: feat/inverted-logo-favicon plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: feat-inverted-logo-favicon-2026-09-04-025056
  branch: feat/inverted-logo-favicon
  workflow: lfg
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/inverted-logo-favicon`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/inverted-logo-favicon/docs/plans/2026-09-04-025056-feat-inverted-logo-favicon-plan.md`
- Change: `feat-inverted-logo-favicon-2026-09-04-025056`
- Branch: `feat/inverted-logo-favicon`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/inverted-logo-favicon/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/inverted-logo-favicon/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `lfg`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/inverted-logo-favicon` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/inverted-logo-favicon` without `--force`.
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

- Owner explicitly selected production delivery on 2026-09-04.
- Ship only the favicon asset, its three full-page template references, the
  focused regression test, and this plan. Preserve all unrelated worktrees and
  changes. No database, migration, harvest, or scheduler action is in scope.

# Goal

Create a transparent, tightly cropped favicon from the existing Cyber-Quan
`mark-quiet` logo, add it to every full-page website template, and deliver the
exact tested SHA through staging to production.

## Product Contract

- `monitor/static/favicon.svg` reuses the exact existing `mark-quiet` vector
  path; it is not redrawn or replaced with a generated approximation.
- The favicon has no background fill; its `#0b1220` mark spans the full height
  and maximum proportional width of the canvas.
- `/`, `/internal/`, and `/brands/<brand>/` declare the same SVG favicon via
  Django's `{% static %}` tag.
- The existing logo, layout, behavior, locale copy, routes, authentication,
  runtime assets, harvest stack, and database remain unchanged.

## Units

### U1 — Vector favicon and template wiring

- Add the standalone, square SVG favicon under `monitor/static/`.
- Add one direct `<link rel="icon" type="image/svg+xml">` to each full-page
  template. Do not add runtime JavaScript or a single-use template abstraction.

### U2 — Regression net

- Exercise the real anonymous `/` URL, view, and template with only data-source
  calls replaced by deterministic values.
- Resolve the favicon through Django's static finder and assert its SVG
  tight viewBox, transparent background, exact logo path, and mark color.

### U3 — Delivery and exact-SHA verification

- Run the focused regression, Ruff, Django system check, XML validation, and
  scoped diff hygiene.
- Follow the generated Ollija guide: commit only this plan's files, push the
  feature branch, fast-forward the same candidate SHA through staging and
  production, and verify both Render services report that exact SHA.
- In a real browser on staging and production, require the HTML favicon link
  and its resolved static URL to return HTTP 200 with `image/svg+xml`.

## Definition of Done

- Focused tests execute with zero failures, skips, or errors.
- Chromium fetches the favicon successfully and the 16×16 rendering remains
  recognizable as the existing weight/bag mark.
- Remote `main` and `pushinweight-web` both resolve to the unchanged candidate
  SHA, and the live production favicon response is verified.
