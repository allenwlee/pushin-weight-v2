---
title: docs/qin-quan-ideation plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: docs-qin-quan-ideation-2026-08-26-085543
  branch: docs/qin-quan-ideation
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/qin-quan-ideation`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/qin-quan-ideation/docs/plans/2026-08-26-085543-docs-qin-quan-ideation-plan.md`
- Change: `docs-qin-quan-ideation-2026-08-26-085543`
- Branch: `docs/qin-quan-ideation`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/qin-quan-ideation/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/qin-quan-ideation/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/qin-quan-ideation` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/qin-quan-ideation` without `--force`.
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

Preserve the complete uncommitted Qin Quan design package on current `main`,
classifying its former implementation plan and companion production-graphics
inventory as ideation instead of leaving them in active plan/reference paths.

## Product Contract

### Requirements

- Keep the visual-direction overview at
  `docs/ideation/2026-08-24-162101-qin-quan-visual-design-template.md`.
- Keep the three standalone HTML studies under
  `docs/ideation/mockups/qin-quan/` and retain their entry in the mockup index.
- Move the former SVG icon implementation plan to
  `docs/ideation/2026-08-19-181145-qin-quan-svg-icon-system-plan.md` and mark it
  as preserved ideation, not an active production authorization.
- Move the companion graphics inventory to a dated, Qin-Quan-specific ideation
  path and update the preserved plan's internal references to that path.
- Exclude the unrelated primary-checkout `AGENTS.md` edit from this change.
- Deliver the unchanged candidate through staging and production using this
  plan's generated Ollija guide.

### Verification

- Confirm every intended source artifact is byte-preserved except for the
  explicit classification note and path-reference updates.
- Confirm all relative links from the overview and mockup index resolve inside
  the committed tree.
- Confirm the former 2026-08-19 Qin Quan source plan and inventory are not
  introduced under `docs/plans/` or `docs/reference/`.
- Run `pytest tests/ollija`, Ruff for any changed Python surface, and
  `git diff --check` before delivery.
