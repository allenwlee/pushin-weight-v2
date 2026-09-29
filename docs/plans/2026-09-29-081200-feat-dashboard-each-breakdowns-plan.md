---
title: feat/dashboard-each-breakdowns plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: user-request
execution: code
ollija:
  change_id: feat-dashboard-each-breakdowns-2026-09-29-081200
  branch: feat/dashboard-each-breakdowns
  workflow: plan
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dashboard-each-breakdowns`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dashboard-each-breakdowns/docs/plans/2026-09-29-081200-feat-dashboard-each-breakdowns-plan.md`
- Change: `feat-dashboard-each-breakdowns-2026-09-29-081200`
- Branch: `feat/dashboard-each-breakdowns`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dashboard-each-breakdowns/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dashboard-each-breakdowns/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dashboard-each-breakdowns` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dashboard-each-breakdowns` without `--force`.
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

On 2026-09-29, the owner answered “deploy” to the follow-up choice between direct production and worktree review. The selected route is direct production. The staging branch remains occupied by unrelated work, so staging deployment and staging checks do not apply to this delivery.

# Goal

Refine only `/dashboard/each` so visitors can compare a percentage stack with post volume and read the taxonomy stacks in a consistent order.

## Plain-English Summary

The chart starts in “% of total” mode, where each nonempty time bucket fills a 0–100% scale. Two radio buttons above the graph switch to the existing volume view and back. The Product tab is singular, and each category stack follows the requested color and bottom-to-top order. Categories without a fixed order use DeepSeek’s last three UTC calendar days as the ranking reference across all selected models and windows. The homepage and other routes stay as they are.

The percentage denominator is the displayed stack: posts for exclusive classifications and label assignments for categories that can overlap. Empty buckets show no percentage area. Completion requires deterministic backend counts and order, a real browser check of the radio controls and chart scale, Bridgewright’s affected and candidate checks, and observation of the exact candidate revision on the production service.

## Product Contract

### Requirements

- Two native radio controls inside the chart panel: “% of total” (checked on load) and “By volume of posts”. The percentage chart uses 0–100% on the y-axis and 100% at each nonempty bucket. The volume chart retains raw stack counts. Switching modes must not fetch data or reset brand, tab, or window.
- Rename only this page’s Products tab to Product in English, Chinese, and Japanese.
- Sentiment bottom-to-top: unclassified black, neutral neutral gray, mixed purple, negative red, positive blue.
- Post Type bottom-to-top: unclassified black, other neutral gray, remaining keys by descending DeepSeek three-day volume.
- Lang bottom-to-top: undetected black, other neutral gray, English, remaining keys by descending DeepSeek three-day volume.
- Role bottom-to-top: other neutral gray, official, staff, community.
- Audience Topics bottom-to-top: unclassified black, no assigned topic neutral gray, remaining keys by descending DeepSeek three-day volume.
- Product bottom-to-top: unclassified black, no product signal neutral gray, remaining keys by descending DeepSeek three-day volume.
- Any other enabled tab uses descending DeepSeek three-day volume. Ties are stable by taxonomy key. The ordering is independent of the selected model and chart window.

### Implementation

1. In `monitor/views.py`, reuse the current chart counting path to compute a bounded DeepSeek reference for the last three UTC calendar days, cache that ranking briefly for live requests, and apply each tab’s fixed prefix plus ranked remainder to response entries. Assign explicit residual and sentiment colors; keep the existing accent palette for remaining categories.
2. In `monitor/templates/monitor/dashboard_each.html` and `monitor/static/pw-each-chart.{js,css}`, add the controls and render either normalized percentages or raw counts from the same JSON payload. Localize visible and accessible labels.
3. In `tests/test_dashboard_each.py` and `tests/test_dashboard_each_browser.py`, pin the data ordering, colors, 100% scale, mode switching, tab copy, and unchanged homepage route. Use real URL, template, data, and Chart.js in the browser net.

### Verification

- Before edits: Bridgewright assurance validate and prescribe.
- During work: targeted PostgreSQL route and browser tests, `uv run --extra dev python -m tests.ui_assurance.gate --scope affected`, JavaScript syntax, and Django checks.
- Before handoff: record product-source revision in the Bridgewright declaration and run the candidate gate with the required performance evidence; changing chart rendering and data work makes candidate performance required.
- Before any Git or deployment mutation: review this guide and run `ollija annotate-plan <this-plan> --check`. Follow the owner-selected direct production route and verify the exact deployed revision and live page.
