---
title: Restore General and Each Post Type charts
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-general-timezone-reference-2026-10-21-090320
  branch: fix/general-timezone-reference
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
---

# Restore General and Each Post Type charts

## Plain-English Summary

Restore the General page after the timezone schema cutover. Its calendar and
opportunity cards still read a deleted model field. Use the shared reader that
already preserves reported timezone wording and falls back to the new reference.
Keep the existing page, classification, timing and access behavior.

Restore the Each dashboard's Post Type chart refresh. The seven-day DeepSeek
request times out while PostgreSQL opens an ordered cursor. This calculation
consumes every matching row, so ask PostgreSQL to plan for the complete result
only while calculating Post Type charts. Preserve chart counts and line ordering.

No tables, fields, migrations, deployment settings, collection behavior or broader
deployment gate are added. Verify populated events and opportunities through the
real General HTML and feed routes in English, Chinese and Japanese, and retain
bounded database reads. The owner selected direct production in response to the
explicit deployment question. Finish exact-candidate checks and verify both live
pages, including the seven-day chart refresh that failed.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/general-timezone-reference`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/general-timezone-reference/docs/plans/2026-10-21-090320-fix-general-timezone-reference-plan.md`
- Change: `fix-general-timezone-reference-2026-10-21-090320`
- Branch: `fix/general-timezone-reference`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/general-timezone-reference/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/general-timezone-reference/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/general-timezone-reference` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/general-timezone-reference` without `--force`.
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

October21: after the tested correction and direct-production question, the owner
answers “deploy”. This selects production on the proposed direct route; shared
staging acceptance/transport is omitted, not passed. Continue through reviewed
checks, exact non-forced production push, observed deployment and real General
HTML/feed recovery and Each Post Type refresh recovery. Do not ask for the same
deployment authorization again.

Owner first narrows the task to updating the reader after G2's schema change,
then reports the Each DeepSeek Post Type chart refresh failure during release. The
previous all-page deployment-process discussion remains a proposal, outside this
fix. Do not send G2 messages. Preserve its active schema work and the existing
October backfill controller, source data and controls.

# Goal

Anonymous `/general/` must render existing Event and Opportunity facts after
the physical removal of `source_timezone` in migration0122.
The seven-day DeepSeek Post Type chart must return complete results without the
observed Gunicorn worker timeout.

## Product Contract

### Requirements

- R1: General HTML and feeds render populated Event/Opportunity facts in
  en/zh_hans/ja with existing reported-zone/null/reference precedence and bounded reads.
- R2: Each Post Type chart retains its complete payload, buckets, classification
  rules, counts and ranking for seven-, thirty- and 365-day windows.
- R3: Full-result cursor planning is confined to the Post Type calculation and
  restores the caller's PostgreSQL setting after success or any exception.
- R4: Preserve G2's dirty schema worktree, running backfill, all schema and provider
  behavior. Deliver the reviewed candidate directly to production and verify both routes.

## Root cause and scope

Production7d4fec90 reproduces HTTP500 in a fresh Chromium browser at
`https://pushinweight.ai/general/?locale=en`. Trace: General view → general_feed
→ temporal_facts → row.source_timezone → AttributeError. Event and Opportunity
now store nullable `source_timezone_reference`; original reported wording lives
in their owned raw evidence. `core.intelligence_readers._reported_source_timezone`
already implements the new read contract.

Touch `monitor/general_readers.py` and its existing General view/timing tests.
Reuse that helper and load its required evidence in the existing batch query;
do not introduce one deferred-field read per card. Preserve explicit null evidence,
missing evidence fallback to the reference, and unknown reported wording.

## Strict regression net

1. Strengthen the existing anonymous General HTML/feed test with actual Event
   and Opportunity rows. Cover known reference, unmatched evidence, missing zone
   and explicit-null evidence across en/zh_hans/ja. Preserve no-read-writes checks.
2. Add a query-count comparison for1versus20temporal facts in each section, paired
   with the real route regression. Confirm the tests fail on the deleted attribute.
3. Apply the shared-reader correction and run General reader/view/timing/browser,
   atomic content and timezone-reader regressions on private PostgreSQL55477.
4. Validate the existing UI declarations, refresh the General source identity,
   and run the applicable affected/candidate assurance gate before release handoff.
   No control/asset changes. Performance scope is selected from the actual diff;
   query-count proof remains mandatory because raw evidence must not become N+1.
5. Review only fix-owned files; preserve all root and peer work. Record actual
   results, skips and errors. Never infer production recovery from local tests.

## Pre-fix workspace

Clean isolated branch `fix/general-timezone-reference` at7d4fec9088da45e6ed1fc6ea11103bb771d3cddc.
The authoritative root has unrelated documentation/skill edits and is not a source
editing checkout. No shared files in the schema owner's worktree are modified.

## Verified local correction

2026-10-21T18:13:14+09:00: all14newcasechecks first fail on the exact Event/Opportunity.source_timezone AttributeError. The product fix imports and reuses `_reported_source_timezone` and loads its owned evidence within the existing batch query;5changed implementation lines, no new helper/storage/schema/settings. All60focusedPGtests pass, then1new populated real-browser test passes for en/zh_hans/ja with visible cards and successful data endpoints. The affected gate passes304tests+91subtests/138requiredPG,0requiredskips/errors; Node108+114checks pass. The new browser test was added after that gate and verified separately; product source is unchanged. Source-boundGeneraldeclaration refreshed toworktree-sha256:6633d10fc2fc7375aac46a6220673a523a26b794fcb8772ed91b7d28ac5e449d. Scoped Ruff and diff checks pass.

Self-review confirms explicit-null evidence precedence, canonical-reference fallback, unmatched wording, batched loading and no raw evidence exposure. Formal simplification/review skipped for mechanical sub10-line product getter correction under ce-debug post-fix guidance; tests/self-review retained, no independent review claimed. No unresolved local findings. Full exactcandidate release/performance/hosted and live recovery checks are not performed or claimed. User deployment choice pending after concrete local correction; do not infer new production authority from the completed homepage release.

## Each Post Type extension and release continuation

The preceding local-only status is historical. Owner subsequently says “deploy”
to the direct-production question and reports `/dashboard/each?brand=deepseek&tab=post_types`.
Production logs pin the failing request to window7/Asia/Tokyo at09:19:44UTC:
Gunicorn terminates the worker opening the ordered PostBrand cursor. No schema
change is needed. Peer `monitor/views.py` edits concern country/region label
references around1557, disjoint from this fix around4209; preserve them in that
peer checkout, with no direct G2 messages.

In a bounded read-only production-data probe, the default cursor fraction0.1
hits a five-second statement deadline; full-result fraction1 completes the same
seven-day calculation in4.497s. A second auxiliary job, job-dbc8da3rjlhs73b641vg,
executes the exact candidate functions in memory against production data:
7d18173posts/2.801s,30d45913posts/5.861s,365d176844posts/16.791s. Every complete
payload equals the unchanged reference algorithm and the outer setting is
restored. General actual views return200 in all3locales in that read-only job.
These are auxiliary calculation timings, not deployed-source or web-page timings.

`_each_post_type_plan` wraps the complete calculation in an atomic scope, sets
transaction-local cursor_tuple_fraction1 and restores the prior value on success;
rollback restores it on failure. Wrapping the complete call ensures exceptions
in consumers release the transaction even while their traceback is retained.
Other tabs/non-PostgreSQL bypass it. No global settings, timeouts, tables,
migrations, classification rules or result caps change.

The real JSON route regression fails before this fix on both normal and exception
paths. Current tests cover7/30/365 output and prior-setting restoration, iterator
failure and consumer failure with a live traceback. Each route/browser tests pass
11tests+35subtests/11requiredPostgreSQL,0skips/errors. Final source-bound General
declaration is refreshed to worktree-sha256:7d9179f41508d7c12921ddb9037ff1baaea5f6dab5dfe230fae894ecfb9ce602.

### Final release checks

1. Review correctness, exception/transaction lifetime, public payload preservation,
   project rules and regression sufficiency sequentially in the main context per
   owner tool mapping. No independent or cross-model review is claimed.
2. Run scoped lint, Ollija tests and declaration validation/prescription. Commit
   only owned source/tests/declaration/this plan; exclude all private evidence.
3. Run the full exact-candidate UI assurance gate with sealed candidate performance,
   private PostgreSQL55477 and deterministic fixture b129fdfa6cfddef0bb28fb12f2c51fbb632c64c1bb825e18a801ee9790639171.
4. Publish feature branch and PR evidence, complete hosted checks, then refresh
   remote main and shared coordination. Direct non-forced fast-forward only.
5. Observe exact deployed SHA, then normal-network anonymous General HTML/feed in
   all3locales and Each window7/Tokyo Post Type refresh with a visible chart.
   Inspect bounded new logs. Do not infer web performance from auxiliary probes.
6. Archive receipts on fuchitalee, release the shared claim, stop only owned local
   resources, and apply the generated guarded worktree cleanup contract.

### Hosted schema-reference correction

The first hosted homepage suite executes211requiredPGtests but fails its existing
all-table documentation oracle: db-schema.md still lists source_timezone on
events, opportunities and metrics after0122. This is pre-existing schema-reference
drift, not a runtime-test failure. Correct only those removed columns, constraints,
trigger descriptions, the three-column total and verified migration boundary.
Preserve the oracle and all product source. Peer schema worktree has no edits to
this reference. Reuse ab9b8fd7 product verification because source, assets, tests,
fixtures and dependencies are unchanged; the final release receipt records the
documentation-only descendant and exact live deployment identity. Rerun the
existing all-table oracle and hosted checks; do not weaken or waive them.

Existing all-table oracle now passes1/1requiredPostgreSQL,0skips/errors. Verified173concreteapplicationtables/2315columns. Product diff fromab9b8fd7 is empty; only this plan and db-schema.md change. Root README links remain valid and unchanged.
