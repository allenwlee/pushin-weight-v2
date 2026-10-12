---
title: Publish G5 round-two handoff and domain record to main
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: docs-g5-handoff-main-2026-10-09-060210
  branch: docs/g5-handoff-main
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
# Publish G5 round-two handoff and domain record to main

## Plain-English Summary

Publish G5's existing session handoff, its charter/index links and the
pushinweight.si registration record so the next session can find them on main.
Preserve G5's uncommitted application and private data, other streams' local
supplements, and all documentation already published on main. Verify the exact
documentation changes and their presence on remote main. No deployment is selected.

## Scope and verification

- Owner endpoint, October 9: “commit and push that to main.”
- Initial base: `f23542d8991b0b45afd8e68da6fc32f80acf574b`, including the
  earlier round-two merge and G4 handoff publication.
- Named files: existing round-two register, scoped G5 charter/index additions,
  `docs/reference/domains.md`, its README discovery link, and this publication record.
- Copy only G5's section into current main; do not replace whole shared files
  with the dirty authoritative-root versions. Preserve G1–G4 byte-for-byte.
- Reconcile the handoff's local-only wording with this documentation request;
  application implementation and deployment remain separate.
- Verify local evidence links against fuchitalee and portable document links
  against the publication checkout. Machine-local code/evidence references are
  explicitly labeled; publishing the handoff does not publish those artifacts.
- Check scoped diff, whitespace, managed annotation and named staged files.
- Commit with `[skip render]`, then push normally to `HEAD:main`. If main advances,
  fetch and replay only this documentation change, preserving other owners.
- Completion requires remote-main equality or ancestry plus exact file checks.
  No application tests are required for these prose-only additions.
- This is a documentation publication record, not a new G5 implementation plan;
  the round-one G5 plan remains closed.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g5-handoff-main`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g5-handoff-main/docs/plans/2026-10-09-060210-docs-g5-handoff-main-plan.md`
- Change: `docs-g5-handoff-main-2026-10-09-060210`
- Branch: `docs/g5-handoff-main`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g5-handoff-main/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/g5-handoff-main/render.yaml`
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

The owner explicitly selected commit-and-push to main. Use the isolated
documentation branch and a non-forced fast-forward push to main; no PR, staging
or production deployment is part of this task. `delivery_target: on-request`
continues to mean no environment deployment was selected. The current user
request supplies Git authority despite the generated guide's default wait text.
Retain the G5 implementation worktree and all unrelated changes/resources.
