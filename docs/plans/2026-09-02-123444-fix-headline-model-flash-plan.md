---
title: fix/headline-model-flash plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-headline-model-flash-2026-09-02-123444
  branch: fix/headline-model-flash
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-model-flash`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-model-flash/docs/plans/2026-09-02-123444-fix-headline-model-flash-plan.md`
- Change: `fix-headline-model-flash-2026-09-02-123444`
- Branch: `fix/headline-model-flash`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-model-flash/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-model-flash/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-model-flash` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/headline-model-flash` without `--force`.
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

Switch the dedicated trend-headline rank, editor, critic, and finite evaluation
route from `deepseek-v4-pro` to `deepseek-v4-flash` without changing prompts,
cadence, batching, concurrency, activation, harvesting, translation, or
classification behavior.

## Product Contract

- Runtime configuration and its Pydantic default explicitly name
  `deepseek-v4-flash` at the existing DeepSeek Anthropic-compatible base URL.
- The route validator accepts only the Flash model for the DeepSeek headline
  provider, so a stale Pro environment override fails closed.
- Rank, editor, and critic request builders pass the configured Flash model to
  the provider boundary with thinking still disabled.
- The finite evaluation command and operator manifest contract use the same
  Flash model as production.
- Dollar reservations use DeepSeek's official 2026-09-02 conservative peak,
  cache-miss Flash rates: $0.44/M input and $1.32/M output. Existing call,
  token, dollar, concurrency-one, and timeout caps remain unchanged.

## Scope

- **Touch:** headline configuration/default/route validation, evaluation model
  guard, focused request/config/evaluation tests, and current headline route
  reference/runbook text.
- **Preserve:** translator/classifier models, prompts, output caps, cadence,
  work-slot behavior, provider base URL, credentials, service topology, and
  production service state.
- **No live calls:** verification uses fake clients and request capture only.
- **Delivery:** production, explicitly selected by the owner on 2026-09-03.
  Promote one unchanged candidate SHA through staging before production.

## Regression Net

1. Before the product change, update the production request-builder assertion
   and config/evaluation defaults to expect Flash; confirm focused tests fail
   on the stale Pro value.
2. After the change, prove the real rank/editor/critic request builders capture
   `model=deepseek-v4-flash`, and prove YAML/default/validator/evaluation paths
   agree on the same explicit model.
3. Run the complete trend-narrative generation, evaluation, orchestration,
   lifecycle, task, configuration, and worker-boundary suites with zero skips
   or errors, plus `manage.py check --deploy`.

## Definition of Done

- One production-call-chain request-capture test and the focused config and
  evaluation tests are red before and green after.
- No runtime or current operator/reference headline route still names
  `deepseek-v4-pro`; historical persisted-row fixtures may retain their model
  strings because they test schema compatibility rather than routing.
- The full relevant suite passes with executed/skipped/error counts reported.
- The diff contains no cadence, prompt, topology, credential, translator, or
  classifier change.
