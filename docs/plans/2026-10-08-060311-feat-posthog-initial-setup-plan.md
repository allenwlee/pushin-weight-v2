---
title: feat/posthog-initial-setup plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: current-session-posthog-setup
execution: code
ollija:
  enabled: false
  branch: feat/posthog-initial-setup
---
# Independent PostHog initial setup

## Plain-English Summary

Add basic site analytics independently of G1–G5. The owner has supplied a project token and a scoped personal key. US project 652560, currently named Default project, is verified and its token matches. The private key stays in the local operator secret store.

Browser pageviews run automatically on public pages when enabled, while respecting Do Not Track and Global Privacy Control. Capture only the homepage and public brand pages, with sanitized paths and internal account IDs. Automatic clicks, recordings and domain events remain outside this setup. A small server helper queues approved events without delaying site requests. The owner selected direct production deployment with visitor tracking enabled and no opt-in control.

Verify disabled behavior, browser identity transitions, bounded payloads, server failure isolation and actual ingestion of labeled setup traffic. Prepare a starter dashboard using the real events. The subsequent owner request “deploy” authorizes Git delivery and observed production deployment; visitor tracking is enabled without an opt-in requirement under the latest owner instruction.

## Goal Capsule

Implement, verify and deploy the independent PostHog foundation while preserving current main and all other worktrees and their edits. The initial base was origin/main dcbedf22; deployment integrates the current production branch. Host authority remains fuchitalee.

## Product Contract

- R1: Default-off integration with explicit token, US/EU host and environment configuration. A personal API key is never application or browser configuration.
- R2: Basic pageviews run automatically on existing public HTML pages when configured; no API, authentication, private/admin, internal or partial-response tracking. Do not require a consent cookie or add an opt-in control. Respect Do Not Track / Global Privacy Control.
- R3: Use `pushinweight:user:<internal-user-pk>` for logged-in identity. Reset on an observed account switch or logout before capturing another pageview. Capture no email/name, page text, search/filter values, OAuth parameters or URL query/fragment.
- R4: Server capture is nonblocking, disabled when unconfigured, bounded to approved event names/properties and a small SDK queue; analytics errors cannot break site requests. Only an explicit labeled `analytics setup test` event is registered initially.
- R5: Retain a starter dashboard for production pageviews/users/public paths; separate setup/test traffic by environment and `is_test`. Verify project-scoped query and dashboard permissions against actual API responses.

## Implementation and Files

Use inline execution in one isolated worktree. Add a small response middleware and a dedicated static loader, leaving G5 templates intact. Add settings, one pinned SDK dependency/lock update, focused Python/browser regressions and an operating guide. Middleware placement must preserve security/compression/cache behavior and vary user/consent-bearing responses by Cookie. No migrations or harvester/authentication behavior changes.

Files: `project/analytics.py`, `project/settings.py`, `monitor/static/pw-analytics.js`, `pyproject.toml`, `uv.lock`, `.env.example`, `tests/test_posthog_analytics.py`, `tests/test_posthog_analytics_browser.py`, `docs/operations/posthog-analytics.md`.

## Verification Contract

Before production-code writes, observe the new focused regression fail because the integration is absent. Use a worktree-owned Python environment and disposable PostgreSQL database for real homepage/authentication call-chain checks. Browser verification must execute the real SDK with intercepted ingestion payloads, validate account/logout transitions, sanitized URLs, disabled/no-consent/DNT behavior and blocked SDK behavior. Capture at most one live setup pageview and one live server setup event with a shared setup-run UUID; no replay/autocapture/domain traffic. Allow up to three bounded ingestion-query attempts, repairing a demonstrated cause before further retries; report unavailable evidence honestly. Run focused Ruff, Django checks, targeted homepage regressions and appropriate browser checks. No full unrelated harvest suites.

## Definition of Done

Local code/tests and operator instructions are reviewable; disabled configuration sends nothing; the genuine browser and server caller chains show bounded metadata and safe failure behavior. Labeled pageview/server events are queryable and the starter dashboard exists and excludes test traffic. If PostHog query availability blocks live proof, retain that limitation separately from local passes. The authorized deployment finishes when the exact candidate revision is observed on production with tracking enabled and a real no-consent-cookie browser pageview is queryable in PostHog.

## Delivery Exceptions

The October 8 owner instructions “deploy do prod”, “enable visitor tracking” and “no; why would we have opt in. dont do that; dploy to production with tracking enabled, override ollija” authorize Git delivery, direct production deployment and automatic visitor pageviews without an opt-in requirement or control. Ollija is explicitly disabled for this plan and its generated guide is removed. Do not restore staging, preference-flow approval or Ollija gates through another checklist. Preserve billing, harvest/worker controls, other releases and all unrelated service configuration.

The activation candidate incorporates current main `421622c952cc67ba889e65931bedfa60d772a808`, preserving the G2 history-streaming fix and the latest discovery cursor/rate-limit fixes. Before changing the opt-in behavior, four new regression cases failed, including the real homepage/browser caller. After the change, 28 focused tests and 12 subtests passed; all ten PostgreSQL-required tests executed with none skipped. Scoped Ruff, formatting, JavaScript syntax, Django checks and the headline-worker boundary check passed. The earlier 36 Ollija checks are historical evidence; they are not required after the override. G2 currently owns staging; the direct release does not mutate it. Worktree isolation protects the dirty shared documentation checkout. Execution and local review stay inline per the supplied AGENTS.md tool map; no independent local reviewer is claimed.

Activation changes only the two consent checks and their regressions; it adds no visible surface, preference control, application interaction, chart/filter behavior or locale copy. The actual SDK browser suite covers the changed analytics requests. Production proof allows one automatic public pageview from a browser without a consent cookie and at most three bounded ingestion queries; do not repeat the earlier local setup captures. Configure only the four PostHog variables on the production web service; keep the personal key local and all other environment values intact.

## Sources

- https://posthog.com/docs/libraries/js/config — capture/opt-out/recording controls and before_send.
- https://posthog.com/docs/libraries/python — background capture and lifecycle.
- https://posthog.com/docs/api — ingestion versus private management/query endpoints.
- https://posthog.com/docs/api/personal-api-keys — project-scoped private credentials.

## Completion Evidence

Initial foundation completed locally on October 8, 2026. US project 652560 and the matching capture token were verified. One real SDK pageview and one bounded Python setup event are queryable with `environment=test` and `is_test=true`. The dedicated dashboard is https://us.posthog.com/project/652560/dashboard/2184992; all five stored queries were read back and executed. Four production charts return zero traffic; the setup table returns the two actual records. The onboarding dashboard is preserved.

Final focused verification: 28 tests passed, 13 subtests passed; ten PostgreSQL-required tests executed and none skipped. Scoped Ruff, formatting, JavaScript syntax, locked dependency sync and Django system checks passed. The actual SDK failure regression proved that raw error text was logged before the safeguard and is now excluded. Inline reuse, quality and efficiency review required no behavior-preserving refactoring.

Repository-wide Ruff reports 1,854 findings outside the changed Python files; it is not a passed check. Three unchanged direct-view cookie tests have a mock chart payload missing `computed_at`; that existing fixture limitation is retained separately. Homepage route regressions pass with the required local `DEBUG=True` environment. Full unrelated suites were not performed. Inline shipping review found no actionable code defects; it does not represent an independent review. The generated lock also resolves the existing benchmark extra declaration that was absent from the baseline lock.

Detailed initial setup evidence is in `docs/analysis/2026-10-08-posthog-initial-setup/receipt.json`. The foundation commit `e20b8362f7ca17ce8c7ec2d3d3a51dd6f4ddc32f` is published on `feat/posthog-initial-setup`. Production deployment and automatic visitor tracking are authorized and in progress. No preference UI is added. The initial setup receipt describes the earlier opt-in foundation, not this activated release.
