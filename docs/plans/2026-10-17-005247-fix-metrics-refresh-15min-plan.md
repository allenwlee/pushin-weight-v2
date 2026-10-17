---
title: Restore early post engagement refresh
artifact_contract: ce-unified-plan/v1
artifact_readiness: review-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-metrics-refresh-15min-2026-10-17-005247
  branch: fix/metrics-refresh-15min
  workflow: work
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  delivery_route_selected_by_user: false
  staging_transport: branch
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/metrics-refresh-15min`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/metrics-refresh-15min/docs/plans/2026-10-17-005247-fix-metrics-refresh-15min-plan.md`
- Change: `fix-metrics-refresh-15min-2026-10-17-005247`
- Branch: `fix/metrics-refresh-15min`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/metrics-refresh-15min/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/metrics-refresh-15min/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/metrics-refresh-15min` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/metrics-refresh-15min` without `--force`.
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

# Restore early post engagement refresh

## Plain-English Summary

Replace the existing one-time two-hour engagement refresh with a one-time refresh after 15 minutes. The current queue repeatedly retries unavailable June posts and blocks recent posts. Restrict it to recent posts and prioritize newly due work; retain truthful missing/error outcomes. No extra two-hour refresh is added.

Local verification is complete: 89 tests pass, including 15 PostgreSQL-required tests with zero skips/errors. Tests reproduce the starvation and verify the real refresh-to-client-to-HTTP-response-to-Post update chain. Owner has selected production deployment through staging. The original Chatter tester and its exhausted Wang allowance remain untouched.

## Product Contract

- One refresh after 0.25 hours from first fetch, still capped at 200 posts per cycle and 50 IDs per request.
- Eligibility expires after 24 hours from first fetch; known publication time must also be within 24 hours. This queue measures early activity, not historical/backfill activity. Most recently fetched due posts go first, with deterministic ties.
- Missing/unavailable posts retain NULL refresh stamps and do not fabricate zero engagement or success. Expiry and newest-first ordering prevent historical unavailable rows starving fresh posts.
- Explicit provider-error or malformed by-ID responses raise an error; valid unavailable results remain missing. Preserve absent optional metrics as unknown; return supplied views/bookmarks alongside four current counts.
- No schema changes: reuse existing Post counters, fetched_at, created_at and metrics_refreshed_at. Zero tables added/retired; no new persistent observation design in this bounded fix.

## Scope and authority

Owner: “move the current 2 hr refresh to 15 min and fix it”; later “continue”. Implementation/local verification and bounded read-only diagnosis authorized. Owner subsequently requested “deploy”, authorizing the staged production release of this bounded fix. Keep the existing cron schedule and normal provider budgets; no pause or unrelated collection-policy change.

Worktree starts clean at 0e0fa643 except this generated plan. Fix-owned paths: monitor/metrics_refresh.py, x_monitor/apify.py, x_monitor/config.py, config.yaml, existing metrics-refresh tests, and this plan. Preserve all other sessions/worktrees and dirty authoritative coordination files.

## Diagnosis

- October14–16 UTC: 279 scheduled summaries, zero successful updates; repeated due=200/refreshed=0/missing=200/errors=0.
- Production: 5,069 historical stamped posts, first August10, last September30 04:07:09UTC. Latest three-day cohort has zero refresh stamps.
- Oldest queue starts June8. Two on-demand requests, five IDs each, zero retries: both HTTP200/status success/msg success; oldest cohort yields blank IDs, recent control returns all five IDs. No domain writes. Existing `get_tweets_by_ids` drops blank IDs; selection keeps the same NULL-stamped oldest records forever.
- Existing tests mock successful per-ID maps and only seed a handful of due posts; they omit stale-queue contention and real HTTP-to-database refresh behavior.
- Evidence: authoritative root `.local/g2-engagement-cost-20261017/` (machine-local). A failed local key-presence check made zero provider requests. Probe used the explicit Render-managed on-demand key, never scheduled/legacy fallback.

## Implementation and regression net

1. Add regression cases in existing test files for expired backlog, fresh priority under cap, 15-minute config and threshold, provider-error/malformed lookup responses, optional/unknown counts, and real client HTTP-to-Post persistence.
2. Run focused cases before implementation and retain correct failures.
3. Change config/model defaults and bounded selector; validate by-ID envelope/results before mapping counts. Preserve deadline and partial-success behavior.
4. Run existing metrics, caller/search and cost regression suites on an isolated local PostgreSQL test DB, with no skips. Run Django checks and scoped lint.
5. Immediate read-only latest-N health check per harvester skill; it reports existing production only, not undeployed candidate success.
6. Record test counts, source diff and remaining deployment boundary. Deliver plan/results to iPhone with show-on-local mobile.

## Verification limits

Actual provider outcome under the repaired scheduling path requires deployment and a natural cron cycle; local regression success is not production success. No additional paid API requests are planned beyond the two completed control requests.

## Completed verification

- Pre-fix regression run: 11 failures / 15 passes. Failures reproduced oldest-row starvation, expired historical work, incorrect 2-hour default, skipped early HTTP lookup, silent provider errors and fabricated zero counts.
- Final focused suite: **89 passed**, PostgreSQL-required **15 executed / 0 skipped / 0 errors**. Includes existing cycle, caller-shape, cost/emit tests, successful HTTP-to-Post chain and HTTP200/error-body-to-deferred/error chain. Local DB `pw_metrics_01a14722`, isolated Django test database; production credentials never used for tests.
- Django system check: zero issues. Scoped whitespace check passes. Ruff comparison against original HEAD: zero newly introduced findings; pre-existing warnings remain.
- Reuse, clarity, efficiency and correctness/error-path review performed serially in parent per repository Task mapping. No additional abstraction or simplification was warranted; zero blocking findings. No independent agent or external model review claimed. Fix was retained uncommitted until the owner subsequently selected production delivery.
- Read-only production predicate check found 3,564 eligible recent posts at the sampled instant. Exact capped newest-first selection used existing creation-time indexes and completed in **6.817ms**. No index/migration change needed.
- Immediate latest20 production health check completed once: status unhealthy, regression/acceptance failed; 0 complete / 2 pending / 18 unhealthy. Non-Chinese Chinese translation16/16, language present17/20, legacy English/Chinese commentary0/20. These are existing production observations, not candidate regression results; no enrichment/configuration repair or production-green claim. Machine-local receipt `.local/metrics-refresh-production-health.json` contains exact cohort and reason details.
- Historical question answered from persisted stamps: 5,069 successful refresh stamps, August10 through September30 04:07:09UTC (13:07JST). This proves intermittent operation, not complete historical coverage.

## Remaining endpoint

Implementation and local verification are complete. Owner requested production deployment on October17; staged delivery and natural-cycle activation verification are now in progress. After delivery, observe a natural scheduled cycle and query the same newly refreshed posts to establish live activation; do not substitute local test evidence. Do not add another two-hour read.

## Deployment authorization — October17

Owner explicitly requests “deploy”. Production target selected, default staged route with staging branch transport. Commit only the seven fix-owned tracked files and this plan; preserve untracked private evidence and root coordination edits. Confirm staging service/database availability, deploy and verify exact candidate, then promote unchanged SHA to main, observe all active production services and a natural candidate-SHA metrics refresh. Scope has no UI, migration, credential, schedule or model/prompt changes. Staging acceptance uses source/configuration identity, Django/ORM checks and eligible-post read-only query; the dormant staging harvest command intentionally disables metrics, so it cannot establish this feature’s activation. Production natural scheduled cycle is the required final proof.

### Release preflight

Additional API-client/Ollija checks:119passed,0skips/errors. `makemigrations --check --dry-run`: no changes. Staging web/DB verified on0e0fa643, core0092, zero active leased collection runs. Remote main and staging match the implementation base. No code/assets/dependency changes since the89-test local verification. Release ownership is recorded in the authoritative index.

### Hosted-check fixture repair and regression wiring

First candidate af128ded passed staging exact-source/config/ORM/login checks on all3active stage resources. Hosted Official-company check exposed an unchanged baseline test failure: `test_cycle_author_context_queries_are_constant` passed `object()` as the CycleRunner instance, which lacks the `_backfill_context` added by recent main/backfill work. Reproduced locally (1failed), repaired only the test to construct a real CycleRunner, preserving the exact2-query assertion. Combined membership/metrics suite36passed/23requiredPG,0skips/errors. Add this fixture file to the fix-owned commit scope; application cycle code unchanged.

The existing Historical-X-backfill hosted job now runs both metrics regression files and triggers on their implementation/configuration paths. No new job, permission or credential change. This ensures hosted checks exercise the actual15-minute refresh differentiator. Restage the new exact candidate and rerun hosted checks before production; do not retry the old candidate as though the fixture were repaired there.
