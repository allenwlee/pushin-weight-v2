---
title: Restrict public homepage analytics to tracked brands
artifact_contract: ce-unified-plan/v1
artifact_readiness: execution-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-tracked-brand-homepage-20261012-2026-10-12-011832
  branch: fix/tracked-brand-homepage-20261012
  workflow: fix-ui
  delivery_target: production
  delivery_selected_by_user: true
---
# Restrict public homepage analytics to tracked brands

## Plain-English Summary

The public homepage currently treats every ordinary database Brand row as a
tracked subject. Newly collected official-company accounts therefore expanded
trending, graph series and brand menus to 179 displayed brands. Use the existing
21 `enabled_models` as the public homepage subject boundary while preserving
Call A collection, classification, company associations and the internal page.

The owner explicitly requests implementation, push and deployment. Delivery
uses the existing staged route. Verify anonymous rendered pages and actual
window/filter interactions, execute PostgreSQL regression and UI assurance
checks, measure the committed candidate, and observe its production revision.

## Scope and execution

- Base: production/main `b92618e3351340203ae5067b5688ad5b3d087a20`.
- Session: `live-tracked-brands-20261012`, independent G5 live-site repair.
- Own public analytics/brand selection changes in `monitor/views.py`, relevant
  existing tests, task-specific declaration authority, and this plan only.
- Preserve harvest/config/schema/provider behavior, `/internal/`, brand detail
  URLs, source posts and all G1–G5 worktrees, databases and previews.
- Reuse `load_config(...).enabled_models`; do not hardcode the 119 companies or
  use database creation dates to determine tracking.
- Derive menu and graph eligibility from the same tracked projection. A URL
  naming only an untracked company must not create an untracked graph line.
- Restrict trending before expensive counts. Preserve exact equal windows,
  per-brand post counts, zero rows, ordering and percentage semantics.
- Diagnose any remaining cold-window delay before considering query changes.
- Preserve pre-existing assurance behavior with controlled tracked-brand
  configurations for synthetic fixtures; independently test the real config
  loader and newly added company rows through the public request call chain.

## Regression net and release evidence

1. Add a failing anonymous route regression containing tracked subjects and
   Call A-only companies. Check localized menus, pulse entries and chart series
   for default, 7d, 30d and 365d, including explicit untracked filter requests.
2. Verify Call A/company association rows remain stored and `/internal/`
   retains its broad registry. Browser-check actual visible selectors and lines.
3. Run affected UI assurance and relevant PostgreSQL tests against a new local
   disposable database; no required skips or errors are accepted.
4. Commit product source, run full candidate assurance and candidate performance
   with that identity, then use available staging and inspect exact deployed SHA.
5. Push/promote to main without forcing, verify live SHA and anonymous window
   switching on `https://pushinweight.ai`, record results and release the claim.

## Progress

- Diagnosis: cold trend counts 14.1s/3.2s/20.9s/19.1s for 1/7/30/365 days;
  public graph requests abort silently at 12s. Production has one sync worker.
- Scope narrowed by owner to tracked-subject selection across the three public
  surfaces. No timeout, language, harvest or classifier change is selected.
- Coordination readback: G3 evidence scope complete; G5 retained General code
  does not edit `monitor/views.py`. Preserve shared runtime ownership.
- New route regression failed on the 119 company rows before implementation;
  all 25 inventory checks now pass, with zero PostgreSQL skips/errors.
- Unmocked production-config browser regression passes six desktop/mobile
  locale cases, each exercising all four windows, menu visibility, pulse and
  chart membership, actual canvas geometry, language and failure state.
- Existing taxonomy/visual fixtures now explicitly configure their synthetic
  subjects. Their oracle images and assertions are unchanged. The visual
  fixture passes both reviewed captures; 233 other affected cases and 58
  subtests passed in the prior gate. Full candidate gate remains required.
- Focused chart/Ollija cases passed (58 cases in the focused run; two failures
  were only transient geometry checks in the newly added browser test and were
  corrected by waiting for visible committed canvas state). New browser rerun
  passes all six cases. Django system check is clean; changed-line lint and
  whitespace checks are clean. Whole-file lint retains 30 pre-existing findings.
- Inline scope/simplicity review follows the repository's sequential-agent
  instruction; no independent reviewer or external code review is claimed.
- A read-only restricted 21-brand 30d query on production PostgreSQL took
  4.105s, compared with the earlier 20.9s full-registry pulse. No query strategy,
  browser timeout, schema, harvest or classifier change was needed.
- Final candidate performance uses an owned local database containing the real
  configured subjects, 119 company rows and deterministic metadata posts;
  staging/production checks will separately measure actual collected data.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/tracked-brand-homepage-20261012`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/tracked-brand-homepage-20261012/docs/plans/2026-10-12-011832-fix-tracked-brand-homepage-20261012-plan.md`
- Change: `fix-tracked-brand-homepage-20261012-2026-10-12-011832`
- Branch: `fix/tracked-brand-homepage-20261012`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/tracked-brand-homepage-20261012/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/tracked-brand-homepage-20261012/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `fix-ui`
- Delivery target: `production`
- Owner selection recorded: `true`
- Delivery route: `staged`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/tracked-brand-homepage-20261012` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/tracked-brand-homepage-20261012` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

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

None.

# Goal

<!-- Planner: replace this requirements-only placeholder with the change goal. -->

## Product Contract

<!-- Planner: define the user-visible contract, acceptance cases, and verification. -->
