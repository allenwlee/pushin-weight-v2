---
title: fix/brand-dot-synthesis-demand plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: owner-confirmed-debug-findings
execution: code
ollija:
  change_id: fix-brand-dot-synthesis-demand-2026-09-21-095125
  branch: fix/brand-dot-synthesis-demand
  workflow: ce-debug
  delivery_target: production
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/brand-dot-synthesis-demand`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/brand-dot-synthesis-demand/docs/plans/2026-09-21-095125-fix-brand-dot-synthesis-demand-plan.md`
- Change: `fix-brand-dot-synthesis-demand-2026-09-21-095125`
- Branch: `fix/brand-dot-synthesis-demand`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/brand-dot-synthesis-demand/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/brand-dot-synthesis-demand/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `ce-debug`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/brand-dot-synthesis-demand` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/brand-dot-synthesis-demand` without `--force`.
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

Correct two regressions in the production homepage without changing the V22
feed or synthesis design: the Brands status dot must return to its default
state when every brand is selected, and anonymous visitors must be able to
request lazy synthesis for newly visible posts without a daily throughput
ceiling stopping the worker.

## Plain-English Summary

Selecting every brand is the default filter, so the Brands dot will no longer
stay blue after the final brand is restored. The homepage will also be able to
ask for synthesis while it is public, and the worker will continue serving
newly viewed posts throughout the day instead of stopping at 200 requests.

The existing V22 behavior stays intact: expanded posts come first, followed by
visible and near-screen posts; browser requests remain bounded and coalesced;
the worker remains single-queue and batch-limited; prewarming stays disabled.
Daily usage is still measured for operations, but it is no longer a hard stop.

Completion requires regression tests, a real-browser check, Bridgewright's
affected and candidate gates, staging verification, and promotion of that
exact tested commit to production. The main risk is accidental anonymous API
abuse; CSRF protection, per-IP rate limiting, batch limits, and worker batch
limits remain in place.

## Product Contract

1. When all brand checkboxes are selected, the shared filter state is
   `brands="__all__"` and the Brands status dot is in its default state,
   regardless of which brands were checked in the initial HTML.
2. A public homepage visitor who received the page's CSRF cookie can request
   synthesis for feed-visible post IDs. Requests without a valid CSRF token
   still fail, and anonymous rate limiting uses the visitor IP rather than one
   global `user:None` bucket.
3. The synthesis worker claims due demand according to `batch_size` even when
   the daily accounting row has passed the former request/token thresholds.
   Daily usage accounting remains available, but it cannot halt throughput.
4. Preserve the current priority order (`expanded > visible > lookahead`),
   browser batch sizes and polling, demand coalescing, retries, model/provider,
   harvest schedule, and disabled prewarm.
5. An old, rare post that becomes visible after filtering follows the same
   request-and-synthesize path as a recent post; age alone does not exclude it.

## Scope Boundaries

### Touch

- `monitor/static/pw-filter-pills.js`: semantic default-state calculation.
- `monitor/views.py`: public CSRF-protected demand access and anonymous rate identity.
- `monitor/post_synthesis.py`: worker claim capacity and accounting semantics.
- `x_monitor/config.py`, `config.yaml`, and `synthesis_status`: remove obsolete
  daily ceiling controls and report usage only.
- Focused API, lifecycle, and browser regression tests.

### Preserve

- Feed ranking, filtering, paging, and V22 lazy-demand priorities.
- Browser demand batch/poll limits and server request batch limit.
- Worker batch size, leases, retries, provider route, and queue isolation.
- All harvesting behavior and schedules.

### Ask First

- Any schema migration, pricing/provider change, priority change, or harvest change.

## Implementation Units

### Unit 1: Canonical Brands Dot

- Make `refreshDots()` treat a fully selected checkbox group as the canonical
  default when the shared filter store reports `__all__`.
- Add a browser regression that selects one brand and then all open and closed
  brands, asserting both `__all__` and a non-blue status dot.

### Unit 2: Public Demand Path

- Remove the login-only restriction from the demand endpoint while retaining
  Django CSRF enforcement, post existence/visibility checks, request-size and
  batch limits, and rate limiting.
- Rate-limit anonymous visitors by IP only; retain user plus IP buckets for
  authenticated users.
- Add an end-to-end anonymous test that first loads `/` for a CSRF cookie, then
  successfully creates demand; verify no-token requests still fail.

### Unit 3: Continuous Bounded Worker

- Remove the request, token, and dollar-cap configuration fields and the
  capacity calculation derived from them.
- Bound each claim only by the existing worker `batch_size`; keep updating the
  daily row as usage telemetry.
- Change `synthesis_status` to label the daily data as usage/accounting rather
  than a budget with maximums.
- Replace the hard-stop test with a regression showing that historical daily
  totals do not prevent the next bounded claim.

## Regression Net

- Unit/API: anonymous CSRF path, no-CSRF rejection, authenticated and anonymous
  rate-limit identity buckets, and continuous claims beyond former thresholds.
- Browser: one-brand-to-all-brands returns state and dot to default.
- Existing synthesis API/lifecycle and V22 homepage browser suites remain green.
- Django system checks and repository lint/static checks pass.

## Verification and Delivery

1. Run focused synthesis API/lifecycle tests and the new browser regression.
2. Run the relevant broader Django/browser suite and `python manage.py check`.
3. Run Bridgewright validate/prescribe, then its affected gate and final
   candidate gate for the homepage/API surfaces.
4. Run `ollija annotate-plan <this-plan> --check`, commit the candidate, and
   push the exact candidate SHA to `staging`.
5. Verify staging service health, homepage/browser behavior, demand creation,
   and synthesis worker progress at that SHA.
6. Fast-forward `main` to the same SHA, verify the production web and synthesis
   services report that exact commit, and repeat smoke checks.
7. Follow the generated Ollija cleanup guard only after exact-SHA production
   verification; preserve the feature branch.

## Exit Criteria

- All five Product Contract requirements are evidenced by automated tests or
  production-safe smoke checks.
- Staging and production deploy the identical verified candidate SHA.
- Production shows a default Brands dot at `__all__`, accepts CSRF-valid public
  synthesis demand, and the worker drains pending demand past the former cap.

## Implementation Evidence

- PostgreSQL synthesis lifecycle and API tests: 21 passed, 0 skipped, 0 errors.
- Synthesis configuration/provider/prewarm tests: 36 passed, 0 skipped, 0 errors.
- Real Chromium one-brand-to-all-brands regression: 1 passed, 0 skipped, 0 errors.
- Django system check: no issues; migration check: no changes detected.
- Bridgewright declaration: clean, control model
  `e8535299404d2eba2f965099d0136fe68dc2812063664912efd2baefcd3d607e`,
  4,466 obligations prescribed.
- Bridgewright affected gate: 191 Python tests plus 59 subtests passed, 0
  required skips/errors; chart contract 110 passed; feed contract 113 passed;
  timezone contract passed.
