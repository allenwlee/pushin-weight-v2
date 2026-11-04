---
title: docs/db-skill-two-questions-20261104 plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: docs-db-skill-two-questions-20261104-2026-11-04-082208
  branch: docs/db-skill-two-questions-20261104
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/db-skill-two-questions-20261104`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/db-skill-two-questions-20261104/docs/plans/2026-11-04-082208-docs-db-skill-two-questions-20261104-plan.md`
- Change: `docs-db-skill-two-questions-20261104-2026-11-04-082208`
- Branch: `docs/db-skill-two-questions-20261104`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/db-skill-two-questions-20261104/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/db-skill-two-questions-20261104/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`

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

## Plain-English Summary

Add two questions to the project's database rule (M19 in the
avoiding-recurring-mistakes skill) so agents ask them before planning database
work: can the result be written as rows through existing writers instead of a
structure change, and can the exact change list be fixed before production is
touched? This changes agent guidance only; no code, schema or data changes.
The owner asked for a commit and push of this branch; it ends when the branch
is verified on GitHub. Nothing is merged, staged or deployed.

## Delivery Exceptions

None. Owner request 2026-11-04 (JST): "add these two questions to our
database skill" then "commit/push", with the owner choosing "Also add to
project M19" for the commit target. Endpoint: `docs/db-skill-two-questions-20261104`
pushed to `origin` and verified there. No merge, staging or production.

# Goal

Agents working in this repository ask two questions before planning database
work, so that changes expressible as rows through existing writers skip
migrations and deploys, and production steps only apply a precomputed list.

## Product Contract

- `.claude/skills/avoiding-recurring-mistakes/SKILL.md` M19 contains the two
  questions with this repo's specifics: existing writers such as
  `core.collection_identity.review_catalog_mapping`; read-only `render psql`
  exports; never inside `pushinweight-web`; a one-off job per AGENTS.md
  "Protect the live web service"; a rolled-back rehearsal, then a commit only
  if every row passes; write authorization required for both runs.
- The M19 Quick reference row names both questions.
- No other file changes besides this plan.
- Verification: `git diff origin/main` shows only these edits; the pushed
  branch head on `origin` matches the local commit.
- Companion (outside git, not part of this commit): the same two questions were
  added to the shared show-locally schema-review procedure at
  `~/.agents/skills/show-locally/references/db-schema-walkthrough.md`
  (machine-local; backup `db-schema-walkthrough.md.bak-20261104`).
