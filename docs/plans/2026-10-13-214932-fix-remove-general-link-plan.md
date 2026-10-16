---
title: Remove homepage General link
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-remove-general-link-2026-10-13-214932
  branch: fix/remove-general-link
  workflow: work
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/remove-general-link`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/remove-general-link/docs/plans/2026-10-13-214932-fix-remove-general-link-plan.md`
- Change: `fix-remove-general-link-2026-10-13-214932`
- Branch: `fix/remove-general-link`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/remove-general-link/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/remove-general-link/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `work`
- Delivery target: `production`
- Owner selection recorded: `true`
- Delivery route: `direct`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. On the owner-selected direct route, fetch the remote production lane: `git fetch origin refs/heads/main`.
5. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
6. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
7. After step 6 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/remove-general-link` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/remove-general-link` without `--force`.
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

Owner explicitly requests remove `data-general-link`, commit/push main and deploy
immediately on October14. Deliver directly to production, without staging or a PR.
Preserve the pre-existing G5 worktree, its dirty records and all prototype artifacts.

# Remove homepage General link

## Plain-English Summary

Remove the General navigation link from the pushinweight.ai homepage in every
language. Keep the rest of the homepage and the existing General route working.
Commit the scoped change, push it to main without forcing and observe that exact
revision deployed. This release uses a clean current-main worktree so the retained
G5 prototype and other sessions' changes are preserved.

## Product Contract

- R1. `/` renders no `data-general-link` or homepage link to `/general/` in EN,
  ZH-CN, ZH-Hans or JA. Remove the anchor itself, not just its attribute.
- R2. Locale/window/filter/chart/feed controls retain their current behavior;
  `/general/` remains accessible at its existing direct URL.
- R3. Publish only this homepage anchor removal, its updated existing regression
  the required unchanged-control declaration source-identity refresh, the
  matching one-sentence navigation-reference correction, and the
  selected release plan. Preserve other sessions' files and service settings.

## Implementation and regression net

1. Reproduce the visible live link at pushinweight.ai on current main `db5510cc`.
2. Update the existing real-route test in `tests/test_general_views.py` to require
   absent homepage navigation across all locale aliases and an available General
   route. Run it red before removing the one anchor from `home.html`, then green.
3. Run applicable stateful UI assurance and scoped review/whitespace checks using
   a new task-owned PostgreSQL test database. Performance measurement is not
   required for deleting one static navigation anchor: no requests, assets,
   queries, scripts or runtime processing are added/changed.
4. Commit named files, non-forced push to main after rechecking remote advancement,
   observe Render's same-SHA deployment and actual public hostname revision.
5. Prove zero General links on desktop/mobile EN/ZH-CN/JA and available neighboring
   controls. Record receipts outside the checkout, release only this G5 claim and
   perform guarded canonical release-worktree cleanup as the final filesystem action.

## Current evidence

- Production browser before edit: HTTP200, revision
  `db5510ccc94ea326dd5f81e833a9c791e5e84d99`, one visible `General ↗` anchor.
- Web service `srv-d9go2breo5us73cg6vqg`, branch main, automatic deploy enabled;
  latest deployment live and no active deployment observed at preflight.

- Red regression executes4 real PostgreSQL locale cases, all failing on the
  existing homepage anchor before the template removal;0required skips/errors.
- General assurance hashes include`home.html` and newer main schema/provider
  files. Refresh only its declared source identity after the one-anchor edit;
  keep all controls, fixture hashes, expected results and obligation sets strict.

- Focused checks pass40tests: four locale regressions plus36Ollija checks;
 4required PostgreSQL tests execute, zero skips/errors. Scoped diff review
 confirms one anchor deletion and no runtime/query/asset/control change.
- Correct only the current reference's statement that Pro links to General;
  preserved direct General route and all other reference content.

Affected UI assurance gate passes: actual required PostgreSQL/browser suites
and three JavaScript programs complete without failure. Exact counts are in
`/Users/fuchitalee/.cache/pw-remove-general-link-affected.log`. General's71 and
Pro's5028 declaration obligations validate without contract/fixture relaxation.
Named-file diff/one-sentence reference and scoped Ruff/whitespace review pass.
Local candidate commit follows, then full same-commit obligation assessment
before non-forced main push and observed direct production delivery.
