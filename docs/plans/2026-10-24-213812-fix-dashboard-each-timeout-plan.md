---
title: fix/dashboard-each-timeout plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-dashboard-each-timeout-2026-10-24-213812
  branch: fix/dashboard-each-timeout
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/dashboard-each-timeout`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/dashboard-each-timeout/docs/plans/2026-10-24-213812-fix-dashboard-each-timeout-plan.md`
- Change: `fix-dashboard-each-timeout-2026-10-24-213812`
- Branch: `fix/dashboard-each-timeout`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/dashboard-each-timeout/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/dashboard-each-timeout/render.yaml`
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
6. Verify the remote staging ref resolves to the candidate SHA and the deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/dashboard-each-timeout` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/dashboard-each-timeout` without `--force`.
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

# Fix the Moonshot Kimi dashboard timeout

## Plain-English Summary

The Moonshot Kimi page should open promptly and category tabs should update their chart without a server error. Production currently spends tens of seconds calculating chart data, and some requests terminate with HTTP 500. The dashboard pills should show only the models tracked on the homepage. Keep chart counts, labels, ordering, tabs, and feed for those models. Change how the existing chart reader obtains the same data; no new tables or fields are needed.

Verify exact chart values and the public page/browser path with deterministic fixtures, then compare request cost on representative data. On 2026-10-26 the owner requested `lfg todeployment`; release to production through the default staged route and verify the live page.

## Scope and evidence

- TOUCH: `monitor/views.py` chart and dashboard assembly, dashboard chart JavaScript/template, focused dashboard tests, the homepage counts GitHub Actions job, this plan.
- PRESERVE: other chart routes, classification semantics, full-result counts, locale, feed, trend narrative, stored data, harvest.
- DELIVERY: production authorized on 2026-10-26; default staged route applies.
- Production 2026-10-24 UTC: `/dashboard/each?brand=moonshot_kimi` first byte 6–16 seconds in direct samples; 30-day sample 15.98 seconds. The 30-day Post Types chart returned HTTP 500 after 32.8 seconds; 1-day Language returned HTTP 500 after 31.0 seconds. Render trace shows worker abort in `_each_chart_payload`, including DeepSeek ranking scan and per-batch Post Types edge query. One 1-day Post Types request succeeded after 44 seconds.
- Parallel `fix/home-30d-chart-timeout` worktree last edited October 16 changes a different homepage pulse function in `monitor/views.py`; retain it untouched and isolate this work from current `origin/main`.
- 2026-10-26 owner addition: "for dashboard, pills should only include tracked brands (follow homepage lead). add those to this fix, then execute." Use the homepage's `_tracked_home_brand_nicknames` through `_build_brands_context(..., tracked_only=True)` for page selection and chart endpoint validation; scope pulse entries to that same brand tuple. Unknown or untracked query-string brands fall back to the first tracked model. No direct link to an untracked brand remains selectable from this dashboard.
- Storage review: this is a read-path optimization. Existing `Post`, `PostBrand`, classification state and edge tables retain ownership. Tables added/retired: 0/0; fields added: 0.

## Work and verification

1. Pin the full-result database plan for every post-scanning chart tab, and use 5,000-row batches to reduce query fan-out without limiting rows or labels. For multi-day scans, avoid nested-loop planning; a read-only query on the existing shadow database took 11.9 seconds with the default plan and 6.5 seconds with a hash join on 13,347 Moonshot rows. This is an indicative query comparison, not candidate application timing.
2. Have the page build only the pulse and trend summary it displays. Let the existing chart endpoint load the selected chart after HTML arrives, with a visible loading state. Preserve the chart's filters, selected brand/tab, and browser history behavior.
3. Test the public URL and chart endpoint with deterministic fixtures at 1 and 30 days, including locale and tab switching; include a regression net for the query path that timed out.
   Include a stored but untracked brand and assert it has no pill, cannot remain selected from a direct URL, and is rejected by the chart endpoint.
4. Run the affected UI assurance gate and report executed, skipped and failed obligations. Measure the candidate on representative data if available. Do not claim production fixed until the candidate is deployed and the live URL is checked.

## Verification state

- Source syntax: `python -m py_compile monitor/views.py tests/test_dashboard_each.py tests/test_dashboard_each_browser.py`, `node --check monitor/static/pw-each-chart.js`, and `git diff --check` passed.
- `python manage.py check --deploy` passed its checks with three pre-existing local security warnings.
- Bridgewright declaration validation and prescription were clean: 5,028 obligations, declaration digest `f084b72a16448c8f90441b63164bf93936c2a8aebfee999d9f7458f1d3d5f9ac`, control model digest `ba03d2156ecd99430bd23550d37c7a76c5d917bd034ec19990275a744146b7ce`.
- The affected UI gate was incomplete on the original base: PostgreSQL-required tests executed=0, skipped=144, errors=0, exit 1. After rebasing to `origin/main` at `f4536c2f`, the shared test DB wrapper refused `tests/test_dashboard_each.py`: the database has applied `core.0169`–`core.0171`, which current main lacks.
- The rebased affected assurance run again exited 1 because PostgreSQL cases were skipped. Declaration validation/prescription stayed clean at 5,028 obligations with the same declaration/control digests. Syntax, JavaScript syntax, `git diff --check`, and Django deploy checks passed; Django reported three existing local security warnings. Scoped Ruff output flagged only pre-existing `monitor/views.py` lines outside this diff.
- A deterministic, database-free local browser smoke exercised the real `/dashboard/each` view, template and static assets with patched readers: HTTP 200, exactly one chart request, chart visible, selected tracked Moonshot Kimi after an untracked deep link, zero untracked pills, and no page errors. A corresponding local Django Client call returned HTTP 400 for the untracked chart endpoint. This verifies browser wiring and selection behavior; it does not validate PostgreSQL query timing or replace the skipped ORM/browser suite.
- The existing 1,005-post database fixture now pins exact Post Type totals and one classification-edge read across the full chart result. G2 DB session advised using its `503c36d4` schema in a separate test-only worktree, without altering the shared database; RG6 has no reliable landing date. The dashboard diff applied cleanly there. The required shared PostgreSQL wrapper ran `tests/test_dashboard_each.py` (11 passed, 37 subtests) and `tests/test_dashboard_each_browser.py` (1 passed). These verify the candidate dashboard behavior against G2's advanced schema; old `0168` production schema compatibility still needs release-path verification.
- The homepage counts GitHub Actions job now runs both dashboard suites on a fresh database built from this branch's migration graph. Its result will verify compatibility with the current production schema lineage without modifying the shared local test database.
- Candidate `1ef24589` ran 248 PostgreSQL-required tests with zero skips/errors: both dashboard suites passed, while the broader job had two pre-existing failures unchanged from `origin/main`. The old-migration fixture inserted through the current `Post` model after migrating to `0092`, referencing a later column, and the Render config test omitted the already-declared serving role. Follow-up test-only corrections use historical models for the migration fixture and assert the exact serving role value; CI must rerun before delivery.
- Production remains on the prior revision pending this authorized release.
