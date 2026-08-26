---
title: feat/ollija-worktree-cleanup plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: feat-ollija-worktree-cleanup-2026-08-26-050048
  branch: feat/ollija-worktree-cleanup
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ollija-worktree-cleanup`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ollija-worktree-cleanup/docs/plans/2026-08-26-050048-feat-ollija-worktree-cleanup-plan.md`
- Change: `feat-ollija-worktree-cleanup-2026-08-26-050048`
- Branch: `feat/ollija-worktree-cleanup`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ollija-worktree-cleanup/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ollija-worktree-cleanup/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ollija-worktree-cleanup` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ollija-worktree-cleanup` without `--force`.
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

Make completed production delivery self-cleaning: after the parent workflow
proves the unchanged candidate SHA is live on production, the generated Ollija
Delivery Guide directs that workflow to safely remove the canonical linked
worktree as its final filesystem action.

## Product Contract

### Requirements

- R1. A user-authorized `production` guide must place worktree cleanup after
  exact-SHA remote-main and Render production verification, never after the
  feature-branch push or staging deployment.
- R2. Cleanup must target only the resolved canonical linked worktree under
  the configured Ollija release worktree area and run from the authoritative
  repository root.
- R3. Before removal, the parent workflow must prove the worktree is
  registered, clean, unlocked, and still at the verified candidate SHA. Any
  failed guard retains the worktree and reports the reason.
- R4. Cleanup must use `git worktree remove <exact-path>` without `--force`,
  preserve the local and remote feature branches, and be the final filesystem
  action so reporting continues from the authoritative root.
- R5. `on-request`, unauthorized, staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees must not receive an
  executable removal command.
- R6. Ollija remains a stateless plan annotator with only `annotate-plan` as
  its public command. The parent delivery workflow owns all checks and the
  cleanup mutation; no hook, daemon, background janitor, or retired release
  controller is introduced.

### Acceptance examples

- AE1. Given a canonical production worktree and explicit production
  selection, annotation places a guarded exact-path removal step after
  production SHA verification.
- AE2. Given staging selection or absent owner selection, annotation contains
  no worktree-removal command and retains the checkout for later promotion.
- AE3. Given a production plan outside the canonical worktree area,
  annotation withholds the removal command and requires relocation plus
  reannotation first.
- AE4. Given any cleanup guard failure, the guide requires retention and
  forbids force removal.

## Implementation

### U1 — Generated production cleanup guidance

- Extend `scripts/ollija/annotate_plan.py` to render a canonical-worktree-only
  cleanup tail after production verification.
- Add focused annotation tests for production, staging, unauthorized, and
  noncanonical routes.
- Keep delivery action numbering deterministic and byte-stable.

### U2 — Shared agent contract

- Update `.claude/skills/ollija/SKILL.md`, `AGENTS.md`, and `CONCEPTS.md` with
  the same parent-owned cleanup boundary.
- Preserve `.agents/skills/ollija` as the existing compatibility symlink; do
  not create a second skill package.

## Verification Contract

- `pytest tests/ollija/test_annotate_plan.py tests/ollija/test_agent_parity.py`
- `pytest tests/ollija`
- Ruff on changed Python and Ollija tests.
- `./bin/ollija annotate-plan docs/plans/2026-08-26-050048-feat-ollija-worktree-cleanup-plan.md --check`
- Regression net: staging, unauthorized, and noncanonical plans contain no
  executable `git worktree remove` command.
