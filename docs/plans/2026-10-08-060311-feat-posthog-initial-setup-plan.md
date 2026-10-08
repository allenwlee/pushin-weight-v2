---
title: feat/posthog-initial-setup plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: current-session-posthog-setup
execution: code
ollija:
  change_id: feat-posthog-initial-setup-2026-10-08-060311
  branch: feat/posthog-initial-setup
  workflow: work
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  delivery_route_selected_by_user: false
  staging_transport: branch
---
# Independent PostHog initial setup

## Plain-English Summary

Add basic site analytics independently of G1–G5. The owner has supplied a project token and a scoped personal key. US project 652560, currently named Default project, is verified and its token matches. The private key stays in the local operator secret store.

Browser pageviews will require an explicit opt-in and respect browser tracking preferences. Capture only the homepage and public brand pages, with sanitized paths and internal account IDs. Automatic clicks, recordings and domain events remain outside this setup. A small server helper queues approved events without delaying site requests. Production stays inactive until the owner chooses an activation endpoint and tracking preference flow.

Verify disabled behavior, browser identity transitions, bounded payloads, server failure isolation and actual ingestion of labeled setup traffic. Prepare a starter dashboard using the real events. The subsequent owner request “deploy” authorizes Git delivery and observed production deployment; collection remains disabled while the preference choice is pending.

## Goal Capsule

Implement, verify and deploy the independent PostHog foundation while preserving current main and all other worktrees and their edits. The initial base was origin/main dcbedf22; deployment integrates the current production branch. Host authority remains fuchitalee.

## Product Contract

- R1: Default-off integration with explicit token, US/EU host and environment configuration. A personal API key is never application or browser configuration.
- R2: Basic pageviews on existing public HTML pages only; no API, authentication, private/admin, internal or partial-response tracking. Require cookie `pw_analytics_consent=granted` and respect Do Not Track / Global Privacy Control. No consent UI is added in this task; production activation depends on selecting the preference flow.
- R3: Use `pushinweight:user:<internal-user-pk>` for logged-in identity. Reset on an observed account switch or logout before capturing another pageview. Capture no email/name, page text, search/filter values, OAuth parameters or URL query/fragment.
- R4: Server capture is nonblocking, disabled when unconfigured, bounded to approved event names/properties and a small SDK queue; analytics errors cannot break site requests. Only an explicit labeled `analytics setup test` event is registered initially.
- R5: Retain a starter dashboard for production pageviews/users/public paths; separate setup/test traffic by environment and `is_test`. Verify project-scoped query and dashboard permissions against actual API responses.

## Implementation and Files

Use inline execution in one isolated worktree. Add a small response middleware and a dedicated static loader, leaving G5 templates intact. Add settings, one pinned SDK dependency/lock update, focused Python/browser regressions and an operating guide. Middleware placement must preserve security/compression/cache behavior and vary user/consent-bearing responses by Cookie. No migrations or harvester/authentication behavior changes.

Files: `project/analytics.py`, `project/settings.py`, `monitor/static/pw-analytics.js`, `pyproject.toml`, `uv.lock`, `.env.example`, `tests/test_posthog_analytics.py`, `tests/test_posthog_analytics_browser.py`, `docs/operations/posthog-analytics.md`.

## Verification Contract

Before production-code writes, observe the new focused regression fail because the integration is absent. Use a worktree-owned Python environment and disposable PostgreSQL database for real homepage/authentication call-chain checks. Browser verification must execute the real SDK with intercepted ingestion payloads, validate account/logout transitions, sanitized URLs, disabled/no-consent/DNT behavior and blocked SDK behavior. Capture at most one live setup pageview and one live server setup event with a shared setup-run UUID; no replay/autocapture/domain traffic. Allow up to three bounded ingestion-query attempts, repairing a demonstrated cause before further retries; report unavailable evidence honestly. Run focused Ruff, Django checks, targeted homepage regressions and appropriate browser checks. No full unrelated harvest suites.

## Definition of Done

Local code/tests and operator instructions are reviewable; disabled configuration sends nothing; the genuine browser and server caller chains show bounded metadata and safe failure behavior. Labeled pageview/server events are queryable and the starter dashboard exists and excludes test traffic. If PostHog query availability blocks live proof, retain that limitation separately from local passes. The authorized deployment finishes when the exact candidate revision is observed on production and disabled behavior is verified. Visitor collection requires the owner's preference-flow choice.

## Delivery Exceptions

The October 8 continuation says “deploy”, authorizing Git delivery and observed production deployment of this foundation. The selected target is production; the repository's default staged route remains in effect unless the owner selects another route. The preference-control question is pending. Prepare the existing foundation with production tracking disabled until that choice is resolved; do not add UI or enable collection merely from elapsed time. Preserve billing, harvest/worker controls, other releases and all unrelated service configuration.

The candidate incorporates current main `926ef61cc52a643e2199cb5cdfa3850778645efd`, including the subsequent G2 history-streaming fix. After integration, the combined focused suite passed: 64 tests, 13 subtests and all ten PostgreSQL-required tests executed with none skipped. This includes 36 Ollija contract checks. G2 currently owns the staging service for its OriginalContent production continuation. Check that ownership and service availability before any staging mutation. Worktree isolation protects the dirty shared documentation checkout. Execution and local review stay inline per the supplied AGENTS.md tool map; no independent local reviewer is claimed.

## Sources

- https://posthog.com/docs/libraries/js/config — capture/opt-out/recording controls and before_send.
- https://posthog.com/docs/libraries/python — background capture and lifecycle.
- https://posthog.com/docs/api — ingestion versus private management/query endpoints.
- https://posthog.com/docs/api/personal-api-keys — project-scoped private credentials.

## Completion Evidence

Initial foundation completed locally on October 8, 2026. US project 652560 and the matching capture token were verified. One real SDK pageview and one bounded Python setup event are queryable with `environment=test` and `is_test=true`. The dedicated dashboard is https://us.posthog.com/project/652560/dashboard/2184992; all five stored queries were read back and executed. Four production charts return zero traffic; the setup table returns the two actual records. The onboarding dashboard is preserved.

Final focused verification: 28 tests passed, 13 subtests passed; ten PostgreSQL-required tests executed and none skipped. Scoped Ruff, formatting, JavaScript syntax, locked dependency sync and Django system checks passed. The actual SDK failure regression proved that raw error text was logged before the safeguard and is now excluded. Inline reuse, quality and efficiency review required no behavior-preserving refactoring.

Repository-wide Ruff reports 1,854 findings outside the changed Python files; it is not a passed check. Three unchanged direct-view cookie tests have a mock chart payload missing `computed_at`; that existing fixture limitation is retained separately. Homepage route regressions pass with the required local `DEBUG=True` environment. Full unrelated suites were not performed. Inline shipping review found no actionable code defects; it does not represent an independent review. The generated lock also resolves the existing benchmark extra declaration that was absent from the baseline lock.

Detailed initial setup evidence is in `docs/analysis/2026-10-08-posthog-initial-setup/receipt.json`. The foundation commit `e20b8362f7ca17ce8c7ec2d3d3a51dd6f4ddc32f` is published on `feat/posthog-initial-setup`. Production deployment is authorized and in progress; the route choice is pending because G2 is using staging. Preference UI and visitor collection remain inactive.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/posthog-initial-setup`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/posthog-initial-setup/docs/plans/2026-10-08-060311-feat-posthog-initial-setup-plan.md`
- Change: `feat-posthog-initial-setup-2026-10-08-060311`
- Branch: `feat/posthog-initial-setup`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/posthog-initial-setup/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/posthog-initial-setup/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `work`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/posthog-initial-setup` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/posthog-initial-setup` without `--force`.
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
