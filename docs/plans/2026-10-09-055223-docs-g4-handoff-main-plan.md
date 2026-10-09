---
title: Publish G4 round-two handoff to main
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: docs-g4-handoff-main-2026-10-09-055223
  branch: docs/g4-handoff-main
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
# Publish G4 round-two handoff to main

## Plain-English Summary

Publish the existing G4 continuity record to main so round two can resume after
session clearing. Add the G4 supplement to the merged round-two register and preserve
all non-G4 content from the owner-published charter/index. Preserve
all unrelated working edits. Verify scoped diffs, links and the remote commit.

## Scope and evidence

- Owner endpoint: October 9 “commit/push to main”; no deployment requested.
- Initial base: 671e9682. Publication paused at owner request while charter/index
  merged. Resumed on owner instruction against main 60181a88; retained merged
  documents and applied only the G4 additions. Earlier commit a96c3bb1 stayed local.
- Only register, targeted main index updates and this publication record change.
- Preserve the merged charter/plan rollout and exclude other sessions' unpublished supplements.
- Checks: document links, whitespace, scoped diff and remote main readback.
- This is a documentation publication record, not the round-two implementation plan.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g4-handoff-main`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g4-handoff-main/docs/plans/2026-10-09-055223-docs-g4-handoff-main-plan.md`
- Change: `docs-g4-handoff-main-2026-10-09-055223`
- Branch: `docs/g4-handoff-main`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g4-handoff-main/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g4-handoff-main/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`
- Delivery route: `staged`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

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

Owner explicitly requests direct commit/push to main. Use an isolated branch
and a normal fast-forward push to main; no PR, staging or deployment workflow.
Delivery target remains on-request because no environment deployment was selected.
The user request authorizes this Git endpoint despite the generic guide's default
wait wording. No application tests are required for prose-only changes; document
checks and exact remote verification are the relevant evidence.
