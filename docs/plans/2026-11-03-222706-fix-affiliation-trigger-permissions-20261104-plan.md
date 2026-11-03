---
title: fix/affiliation-trigger-permissions-20261104 plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-affiliation-trigger-permissions-20261104-2026-11-03-222706
  branch: fix/affiliation-trigger-permissions-20261104
  workflow: work
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
---
## Plain-English Summary

Fix affiliation saves by limiting trigger reads to validation columns. No tables, columns, grants or collection behavior change. Owner requests LFG through production deployment with a strict regression net.

## Delivery Exceptions

Owner explicitly selected direct production deployment in the current continuation; staging is omitted. Cast ingestion and live-service import work are outside this fix.

## Investigation and verification

- Production web is live at 9088ed7479db68d94a82ce781e4f0dc2c8d4b323. Read-only database inspection confirms pushinweight_shadow, migrations through 0219 and both broad trigger reads.
- New real-login ORM-save regression failed at deferred constraint execution with the exact reported permission error before the fix.
- Forward migration 0221 replaces only two SELECT projections. All validation logic remains unchanged; reversal restores the historical function.
- Regression net covers restricted-login insert/update, protected location read denial, cross-person and organization replacement, missing review, cycles, dependency movement, and authorized versus restricted source-evidence writes.
- Shared local PostgreSQL: 42 passed, one existing case deselected in the second run. Full initial run: 36 passed, one failed before the six later cases were added. Existing failure: test_serving_login_reads_canonical_columns_but_cannot_reach_source_or_owner queries retired collection_runs.raw_payload and receives UndefinedColumn instead of InsufficientPrivilege. This is unresolved, not waived or passed.
- Test-only Chatter migration compatibility overlay was removed. Candidate SQL and temporary merge ledger entries were reverted under the shared wrapper; existing Chatter migration and persistent database retained.
- Owner continuation: retire only the obsolete collection_runs.raw_payload permission assertion with an explanatory note; keep all current privacy checks, rerun the full scoped net, then deploy. Prior failure remains historical evidence, not a passed check.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/affiliation-trigger-permissions-20261104`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/affiliation-trigger-permissions-20261104/docs/plans/2026-11-03-222706-fix-affiliation-trigger-permissions-20261104-plan.md`
- Change: `fix-affiliation-trigger-permissions-20261104-2026-11-03-222706`
- Branch: `fix/affiliation-trigger-permissions-20261104`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/affiliation-trigger-permissions-20261104/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/affiliation-trigger-permissions-20261104/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `work`
- Delivery target: `production`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. On the owner-selected direct route, fetch the remote production lane: `git fetch origin refs/heads/main`.
5. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
6. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
7. After step 6 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/affiliation-trigger-permissions-20261104` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/affiliation-trigger-permissions-20261104` without `--force`.
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

## Final local verification — owner continuation

- Full scoped suite:79 passed, zero exclusions;43 PostgreSQL cases executed, zero skips/errors. Command: `pushinweight-test-db pytest tests/test_geolocation_access.py tests/test_person_affiliations.py tests/test_staff_library.py tests/ollija -q`.
- Retired only the obsolete collection_runs.raw_payload assertion by owner direction, with inline retirement note. Current protected-source, owner-escalation and schema-write denial assertions retained.
- Review found one organization-test false-positive risk; corrected to use a valid second Brand committed before replacement, and match the specific replacement exception. Re-review:Ready to merge; no residual findings.
- Simplification invocation omitted under LFG's roughly-sub-10-line implementation exception: only two SQL projections change; copied historical function/reversal and regression cases dominate file size.
- Browser route mapping: no UI/routes changed; database-only migration exercised through actual Django ORM and restricted-login commit. Browser tests:Skip, no affected browser route.
- Documentation skipped under ce-compound durable-learning bar: final SQL, regression tests and this plan retain the complete reasoning.
- Migration lint passes; test lint has only pre-existing SIM117 at unchanged existing code (baseline108/current109). Diff whitespace check passes.
- Shared test SQL and temporary migration ledger restored after final run; Chatter0220 retained. Temporary graph overlay files removed and excluded from delivery.
- Owner selected direct production deployment after79tests/review. Preserve Chatter staging3d83bf81. This metadata-only route update does not invalidate the code/test evidence at3e848b15.
