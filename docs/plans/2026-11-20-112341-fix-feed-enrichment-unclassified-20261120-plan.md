---
title: fix/feed-enrichment-unclassified-20261120 plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-feed-enrichment-unclassified-20261120-2026-11-20-112341
  branch: fix/feed-enrichment-unclassified-20261120
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
---
## Plain-English Summary

Restore feed classifications and sentiment when the independent third-party promotion result is uncertain. Keep the uncertainty visible and do not overwrite existing promotion evidence. The owner has authorized direct production delivery, with independent review and live verification.

## Execution and verification

- Preserve harvest operations, model and provider routes, existing physical call limits and independently saved evidence.
- Reproduce the exact failure using the real classifier and publisher, with tests that check sentiment/post type survives while uncertain promotions remain unresolved.
- Check complete, partial, retry, previous-evidence and negative cases, browser rendering and dashboard classification.
- Review the diff and deploy the verified revision directly to production; check live worker and harvest without interruption.
- On the live worker, a 100-post batch made 198 provider requests but saved only 53 feed classifications. A bounded five-post read-only classifier diagnostic found unresolved promotion questions suppressing otherwise independently valid sentiment and post-type results.
- Selected final judgments mark completed feed axes; promotion/release retries remain pending. Existing validated feed-only judgments without a release manifest are recognized by the feed. The promotion filter still treats an absent promotion row as its ordinary off lane, so it does not distinguish unresolved from a confirmed negative.
- After the first fix went live, 131 posts aged 0–5 minutes had never been attempted and the first feed page had only 2 of 50 posts with sentiment. Preserve the 80/20 recent/older allocation and existing provider limits; split the recent allocation between newest publication times and oldest queued arrivals. Keep ordering deterministic and place null publication times last in the newest slice. Verify both lanes, out-of-order collection and missing publication times without extra provider calls.
- The unchanged search-query inputs are outside this post-fetch fix; retain existing scheduled and backfill query behavior and the previously reviewed UTF-8 query guard. Offline `plan_calls_for_cycle` audit at base a5d50176, using a 19-digit list ID and two 10-digit time bounds, gave scheduled bytes/headroom: A 96/416, B1 416/96, C1 495/17, C2 423/89, C3 488/24, C4 322/190, B2 509/3, B3 469/43, B4 437/75, C5 462/50, B5 303/209, B6 456/56, C6 466/46, B7 337/175, B8 511/1, B9 507/5. The production-enabled special-event query pack adds SPECIALEVENTS1 510/2 and SPECIALEVENTS2 505/7. Manual current-policy requests omit 14 scheduled-exclusion bytes. The unchanged query canary passed; no provider query was run.

## Dashboard recovery follow-up — 2026-11-20 22:30 JST

The owner reports continuing recent-bucket unclassified rates on Meta and DeepSeek. Direct dashboard API and database checks confirm real waiting posts, not only Meta identity ambiguity. At 22:27 JST, DeepSeek's 21:15–22:15 cohort had 250 posts: 183 with sentiment, 7 context-missing, 56 never attempted and 4 attempted without a saved state. Its 22:05–22:10 bucket remained 25/25 unclassified. Across all brands, 62 posts ingested during 22:03–22:05 had never been attempted. Seven worker batches claimed 700 slots for 666 distinct posts; 208 of those distinct posts had already been attempted before deployment. The prior saved-result count is not a first-attempt-coverage measure.

Keep the existing 80 recent/20 older allocation, newest/oldest recent split, due times, claim locks, budgets, provider pacing and maximum attempts. Within each existing ordering, reserve 80% of production-sized allocations for runnable scheduled classification with zero attempts and 20% for other due work (retries and requested translation). Small allocations keep at least one other slot when their size permits; a one-slot allocation prefers first attempts. Both sides borrow unused capacity. First-attempt eligibility requires a due classification, a PostBrand target and no historical job owner. This is a queue-only correction, adding no storage. Retries and requested translations retain their reserved share even under sustained first-attempt arrivals; sustained arrivals exceeding capacity can still cause delay. Preserve historical job ownership and explicit-ID/non-worker selection. Do not alter classifier identity decisions or search queries for this queue correction.

Regression net: demonstrate failure before the fix for both recent and aged first attempts competing with retries, then exercise the real CycleRunner caller and assert dispatched first-attempt IDs. Verify retries are selected after first work is claimed, existing oldest/newest behavior, borrowing, overlapping claims, due-time and budgets. Use an empty task-specific local database. Check the changed read query cost and live service revision, then verify an immutable DeepSeek cohort's first-attempt progress. Reuse UI evidence from 50c0cade only for unchanged views/assets; this correction changes no browser rendering or chart reader.

Verification: 155 queue, worker, compressed classifier and Ollija tests passed (69 required PostgreSQL tests, zero skipped/errors). Eight focused first-attempt/runnable/fairness and unchanged-order tests passed; the two original first-attempt tests failed against 50c0cade, and the six fairness/runnability tests failed against the initial strict-priority draft. Independent review found no remaining blocking issue. The other-work share is combined retries plus requested translations, not 20% for each. Read-only representative selection queries measured 14–81 ms execution each on production data; no row-lock timing was claimed. No views, assets or dashboard readers changed, so the 50c0cade interface verification remains applicable to those unchanged surfaces. A fixed 20-post production observation starts before deployment and completes after 30 minutes before final delivery verification; retain its actual incomplete/failed translation acceptance status separately from classification coverage.

The Each chart currently fetches on page load or selection change, with no automatic periodic refresh. Its clock updates independently. Fresh API responses did show recovery (67 to 50 unclassified in the same 250-post DeepSeek cohort between 22:27 and 22:29), but the 25-post gap remained. Automatic chart refreshing is not added by this queue correction. Meta also has completed context-missing errors, including a post explicitly praising Meta AI on WhatsApp; the earlier suggestion that Muse context-missing posts necessarily concern an unrelated product was not established.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

Generated by `ollija annotate-plan`; do not edit between the markers. Delivery policy lives in `AGENTS.md` under "Plans and delivery". Project facts (host, repository, branches, environments, URLs and blueprints) live in `.ollija/project.yaml`. Record owner exceptions under Delivery Exceptions below.

- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/feed-enrichment-unclassified-20261120/docs/plans/2026-11-20-112341-fix-feed-enrichment-unclassified-20261120-plan.md`
- Branch: `fix/feed-enrichment-unclassified-20261120`
- Change: `fix-feed-enrichment-unclassified-20261120-2026-11-20-112341`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/feed-enrichment-unclassified-20261120`
- Workflow: `plan`
- Delivery target: `production`
- Route: `direct`
- Owner selection recorded: `true`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery steps

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. On the owner-selected direct route, fetch the remote production lane: `git fetch origin refs/heads/main`.
5. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
6. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
7. After step 6 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/feed-enrichment-unclassified-20261120` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/feed-enrichment-unclassified-20261120` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

Occupied staging: if a staged route finds `staging` in use by an unrelated release while production is authorized, follow the occupied-staging default in `AGENTS.md`.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

The owner selected direct production delivery for these fixes in the active task.

# Goal

<!-- Planner: replace this requirements-only placeholder with the change goal. -->

## Product Contract

<!-- Planner: define the user-visible contract, acceptance cases, and verification. -->
