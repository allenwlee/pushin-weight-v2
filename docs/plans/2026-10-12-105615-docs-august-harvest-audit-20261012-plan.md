---
title: Audit August X gaps and prepare bounded historical recovery
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: docs-august-harvest-audit-20261012-2026-10-12-105615
  branch: docs/august-harvest-audit-20261012
  workflow: delivery
  delivery_target: staging
  delivery_selected_by_user: true
---
# Audit August X gaps and prepare bounded historical recovery

## Plain-English Summary

The production audit confirms five substantial gaps in August 2026, including
the nearly empty August 9. Exact evidence boundaries, padded recovery windows,
daily counts in UTC and Japan time, and an hourly plot are saved.

The on-demand backfiller must treat historical recovery as a one-time batch.
Search whole requested windows, remember the provider cursor after every stored
page, and collect independently of translation and classification. Fixed sleeps,
quarter-hour admission and arbitrary five-page query caps are retired for batch
execution. Shared fetch, attribution and Post storage remain in use. Missing
enrichment on stored posts is a separate workload.

The original 15-minute probes found no new posts. The owner widened the test
to two hours across all 21 brands; it recovered 98 new staging posts, with 48 of
49 sampled posts having completed assessments. On October 13 the owner accepted
the remaining pending classifier conflict as good enough and selected a 24-hour
August 9 staging run instead of the prepared four-hour step. The classifier
protocol remains unchanged. Collection completion, sampled enrichment results
and actual resource use will be reported separately.

Verification will exercise the management command through the shared runner,
captured fake providers and PostgreSQL. Time bounds, credential purpose,
checkpoints, total budgets and lock release must work together, while the
scheduled seven-call path remains unchanged.

## Goal Capsule

- Objective: fix the current on-demand backfiller's deficiencies and prove a
  successful real staging recovery; owner widened U7 to two hours/all21brands.
- Authority: owner's LFG fixes-and-test request; G3's approved atomic-JSON
  staging-pilot boundary, verified in both plans after the owner's check-files
  continuation. Shared schema, production collection and month campaigns remain
  outside this run.
- Means: shared CycleRunner, finite page units and invocation budgets, atomic
  host checkpoints, exact-ID enrichment and a staged provider-backed pilot.
- Execution: inline, sequential work on this existing canonical branch. The
  parent owns review, PR/CI and live pilot proof; implementation returns locally
  verified code and its prepared pilot contract.
- Stop: preserve state and report a real failed/partial test or exhausted finite
  allowance; never replace the fixed window or substitute a mock for live proof.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/august-harvest-audit-20261012`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/august-harvest-audit-20261012/docs/plans/2026-10-12-105615-docs-august-harvest-audit-20261012-plan.md`
- Change: `docs-august-harvest-audit-20261012-2026-10-12-105615`
- Branch: `docs/august-harvest-audit-20261012`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/august-harvest-audit-20261012/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/august-harvest-audit-20261012/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `delivery`
- Delivery target: `staging`
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

The October 13 LFG request authorizes implementation, commits, a pull request,
CI and the fixed 15-minute staging pilot below. Production delivery remains
on-request. These actions follow the owner's explicit request, not the generated
guide's default planning authority. G3's atomic-JSON pilot agreement is settled.

The October14 owner request `lfg this` explicitly selects the Render one-off
backfiller move, staged build and observed staging execution. The following owner
note selects assessment/reuse of G3's collection schema/API as part of that move.
This is no production or month activation grant. G3 dependency delivery is not
resumed by an assumption that its new migration was already deployed; coordinate
the actual dependency handover. Keep the already authorized local Aug9batch
progressing while preparing the Render integration.

## Scope and ownership

Owner request: “for now let's check august” for significant gaps, then dust off
the on-demand backfiller for a separate recovery run; later support slow
month-sized collection such as July.

The October 12 read-only audit is complete. The October 13 owner invocation
of LFG now authorizes U2–U7 implementation, applicable review/delivery and the
planned real 15-minute test. Success requires the test itself to succeed;
local green tests or an open pull request alone are incomplete. U8 remains
explicitly deferred. No production release, production cron pause/resume or
new scheduler was selected. The first live test should target staging; final
runtime placement and delivery metadata must reflect the actual authorized
route rather than claiming a production grant.

- Authoritative host: fuchitalee.
- Worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/august-harvest-audit-20261012`.
- Branch: `docs/august-harvest-audit-20261012`.
- Audit base: `f43b2904393013107598af3904b78d3be36c76b4`; October 13 planning base: `db5510cc` (includes G3 collection schema at `b9f03bc1`).
- Independent of G1–G5: consult their authoritative index/charter for conflicts;
  no G task, implementation file or runtime resource was claimed.
- Preserve root uncommitted documents and every retained worktree. Reconcile
  current source/file ownership before starting follow-up implementation.

## Product Contract

An operator specifies fixed historical bounds and query/brand scope, inspects
without writes or paid calls, executes finite small units, and resumes actual
remaining coverage. A completed collection receipt means the planned interval
was drained under its pinned scope; capped, failed and non-progressing work
stays incomplete. Enrichment has its own pending/completed evidence. Already
stored IDs remain deduplicated.

Historical work uses ON_DEMAND only, advances no live cursors, and releases the
shared writer lease between units. Limits cover physical page/walk/retry
requests and aggregate model requests across the whole invocation. Sleeping
holds no writer lease. Scheduled A/B/C shape, policy, credential purpose,
cursor/replay rules, models and enrichment defaults remain unchanged.

Choose and pin the collection population before execution. Current brands,
queries and list membership do not reconstruct August automatically. Preserve
historical aliases/languages/engagement scope explicitly; report unavailable
accounts and uncertain coverage rather than quietly dropping them.

## U1 — Production August audit [complete]

[Report](../analysis/harvester/2026-10-12-195900-august-coverage-audit.md)
and [proposed windows](../analysis/harvester/2026-10-12-195900-august-coverage-audit-recovery-windows.json)
link exact read-only SQL/JSON and derived CSV/plot evidence.

- 148,298 posts in UTC August / 149,787 in Japan-time August.
- August 9: 19 UTC-day posts / 22 Japan-time-day posts.
- Five major grouped windows: Aug 1–2, 3–4, 5–6, 8–10, 16–17 UTC.
- Smaller interruptions: Aug 13 and 27 UTC.
- Five padded major intervals: 143.5 hours, not a missing-post estimate.
- All UTC-August source-query identifiers are null; no current backlog row
  overlaps August. Lane-specific August misses cannot be reconstructed.
- 86,196 stored posts lack English text; enrichment repair is a separate task
  from historical search and from versioned classification counts.
- Verified: 62 daily totals against 1,488 hourly cells, populated-hour and
  insertion-age splits, read-only metadata and the plotted artifact.
- No application behavior changed; application tests were not run for this audit.

## Shared collection coordination — October 13

The owner reports G3 deployed `CollectionRun`, `CollectionObservation` and
`CollectionScopeRun` at `b9f03bc1`, and is planning exactly one new permanent
table, `CollectionJob`, for instructions and scheduling. X integration is still
being planned. Do not add standalone backfill job/run tables or independently
change shared constraints. Keep tweets in `Post`; preserve `call_state` and
`harvest_backlog_windows` semantics.

Target adapter mapping for the later database integration:

| Responsibility | Proposed shared destination | Boundary |
| --- | --- | --- |
| Fixed manual campaign instructions, frozen interval/scope, budget and activation | `CollectionJob` | G3 owns model/migration/general API; manual testing creates no recurring schedule |
| Invocation/attempt history, usage and outcome | `CollectionRun` | G3 must define supported X purpose/lifecycle; existing constraint currently permits only metric/catalog |
| Per-call/time-slice cursor and remaining work | `CollectionScopeRun` | Agree cross-attempt identity, committed progress and lease rules before adapter implementation |
| Retrieved tweet content and brand/classification facts | Existing `Post` and related tables | No per-tweet duplication into `CollectionObservation` |
| Scheduled live cursors/backlog | Existing cursor/backlog tables | Historical completion never advances/reinterprets live cursor ownership |

Proposed backfill file scope: `monitor/management/commands/backfill.py`,
`monitor/cycle.py`, `monitor/run_lock.py` only if lock admission changes require
it, `x_monitor/apify.py`, focused tests, and a small recovery-state/resource
helper only if it prevents duplication. `core/models.py`, `core/migrations/`,
G3 collection scheduling/history files and its new plan are not claimed.

The interim persistence boundary is settled: use atomic JSON checkpoints on
the authoritative `fuchitalee` host for the staging pilot. The pilot can proceed
under this session's existing authorization without waiting for `CollectionJob`
or the database adapter. Freeze campaign identity and bounds, save only committed
progress, replace the checkpoint atomically, and retain the prior checkpoint if
a replacement fails. Do not rely on an ephemeral Render filesystem for recovery.

G3 owns the shared model, migration, lifecycle and persistence API. The backfill
session owns the X command, cycle/transport changes, checkpoint implementation,
focused tests and the later X database adapter. The adapter depends on G3's
implemented contract; the JSON pilot does not. No shared schema mutation or
standalone backfill table is authorized by this boundary. A later adapter must
preserve campaign identity and distinguish imported checkpoint evidence from
native database attempt receipts; it must not invent missing run times.

The G3 dependency is recorded in
`docs/plans/2026-10-13-062212-feat-g3-collection-jobs-history-plan.md` on branch
`feat/g3-collection-jobs-history`. Coordinate the final fields/API and adapter
handover there before database integration. The pilot persistence choice is no
longer an unresolved planning blocker.

The owner's later G3 plan amendment extends the future shared X adapter to
ordinary scheduled harvest receipts as well as manual/backfill attempts (G3
U9). Persist one content-run receipt per invocation through the common runner
path, retaining the existing Render cron, live lock, actual call bounds and
cursor/backlog ownership. This is later adapter work after shared-API handover;
it does not change this pilot's JSON route, budget, runtime scope or authority.

## U2 — Validate and freeze the campaign [implemented; verification recorded below]

Primary file: `monitor/management/commands/backfill.py`.

Accept consistent documented timestamps. Reject unordered/equal bounds and
nonpositive limits before provider construction. Freeze the upper bound:
repeated invocations currently derive a new “now” and state filename when
`--until` is omitted. Replace obsolete six-call/2,350-post estimation with
explicit finite slices and allowances.

Bind resume identity to bounds, selected calls/brands, effective query/policy
fingerprints, list-population evidence when relevant and limits. Save atomic
checkpoints; reject incompatible prior state. Retain scoped state separation,
read-only status/dry-run, setting restoration and existing scope validation.

Acceptance: invalid options fail before provider construction; dry-run/status
write nothing; same campaign keeps the same bounds; interrupted checkpoint
write retains readable state; changed queries cannot inherit old completion.

## U3 — Preserve the shared pipeline and isolate recovery work [implemented; verification recorded below]

Primary files: backfill command and `monitor/cycle.py`; shared client/planning
helpers only when tracing proves necessary. Do not implement another collector.

Historical recovery explicitly selects the seven core calls or an approved
subset. Avoid incidental modern discovery searches, unrelated global enrichment
or rare-type drains, verification, list mutations and synthesis/editorial demand
consuming its allowance. Scope inline enrichment to the campaign IDs while
retaining durable pending work. Existing posts needing enrichment repair use an
explicit cohort and separate allowance, rather than blind re-fetching.

Keep ON_DEMAND resolution, explicit-window cursor protection, scheduled defaults
and canonical models/policy. Count in-window primary search and out-of-window
quoted context separately. Do not change policy just to improve keeper yield.

Acceptance: management command → real runner → captured fake provider uses exact
scope/time bounds and ON_DEMAND; live `call_state` is unchanged; optional provider
fakes are untouched by basic recovery; scheduled control cases remain intact.

## U4 — Resume actual remaining coverage [implemented and verified]

Primary files: command and `monitor/cycle.py`; `x_monitor/apify.py` only if its
shared client needs a continuation seam.

Partition long spans into small units and distinguish pending, running, drained,
capped, failed and non-progressing work. Checkpoint remaining time/page progress.
A truncated call currently stays pending but re-fetches its original bounds;
resumption must reach older work rather than repeatedly buying the newest part.

Handle repeated cursors, same-second boundary posts, empty continuing pages,
partial persistence and paid retries. Retain raw request/return counts before
derived deduplication. A stable fuchitalee coordinator can use atomic local
checkpoints; ephemeral Render jobs cannot be assumed to share files. Select
checkpoint placement/receipt transfer before live execution. Do not casually
repurpose the scheduled backlog ledger or add a separate fetch pipeline.

Acceptance: two invocations through the real runner drain older remaining
coverage; capped/no-progress/failure never completes; duplicate/boundary IDs
persist once; restart resumes the correct unit without losing committed work.

## U5 — Enforce total budgets and yield to live harvesting [implemented and verified]

Primary files: command, `monitor/cycle.py`, `monitor/run_lock.py` and existing
provider transports if necessary. Preserve no-wait lock identity and acquisition.

- Reserve allowance before sending each physical page/walk/retry request; charge
  raw returned duplicates and empty-call floors. Keep estimated and confirmed
  usage separate. Unknown usage does not imply zero cost.
- Share one invocation/campaign model allowance across calls. The current fresh
  runner per call resets the advertised per-invocation LLM cap. Translation,
  classification, relevance and optional requests need explicit accounting.
- Thread a deadline through historical fetches, page walks and retries. Ordinary
  runner fetching currently omits the available `_fetch_tweets` deadline. Start
  only if the remaining slot fits the full timeout/retry envelope; otherwise
  checkpoint and defer.
- Lease one bounded unit, release, then pause. The current outer lock also covers
  `--pause`. Do not sleep while blocking scheduled writer admission.
- Give upcoming scheduled slots their reserve; defer on contention, resource
  pressure or inadequate time. Observe shared worker/model and DB load before
  selecting defaults: the harvest lock does not cap other workers.
- Report successful drain, partial/deferred, lock-busy and failed outcomes
  separately; swallowed exceptions and exit zero are not harvest health.

Acceptance: multiple logical calls/retries never exceed aggregate captured
request starts; deadline checks reject inadequate timeout envelopes; competing
scheduled PostgreSQL writer acquires between units and during pauses; contention
makes zero provider calls; failure releases the lease and checkpoints progress.

## U6 — Regression net and offline proof [complete]

Extend existing tests with production-call-chain coverage, not only helpers:

| Existing test surface | Required proof |
| --- | --- |
| `tests/test_backfill_quarantined.py` | Real command → runner scope, input/state validation, partial receipt and setting restoration |
| `tests/test_cycle_run_lock.py` | Actual PostgreSQL competing writers, contention, pause outside lease, failure cleanup |
| `tests/test_cycle_cursor_wiring.py`, `tests/test_harvest_cursor_lifecycle.py` | Historical bounds/no live cursor change plus scheduled controls |
| `tests/test_cycle_search_caps.py`, `tests/test_cycle_error_counters.py` | Aggregate request/deadline budget, partial persistence, failure receipts |
| Existing credential-purpose and model transport-cap tests | Captured exact ON_DEMAND, translation/classification and total allowances |
| `tests/test_hybrid_harvest_regression_net.py`, `tests/test_harvest_surface_regression_net.py` | Scheduled seven-call and policy behavior preserved |

Discover current prerequisites and use an isolated PostgreSQL test database,
not production or another task's database. On macOS use a durable `--basetemp`
on fuchitalee. Run affected required tests after implementation; report executed,
skipped and error counts. Skips are not passing concurrency evidence. Review
shared callers and simplicity before preparing a live run.

## U7 — Real recovery test [original 15-minute attempts unsuccessful; widened test authorized]

**Owner amendment, October 13:** “test it over 2 hours”, then “widen it to
21 brands”. This supersedes the pending replacement-window menu. Execute
August 9, 2026 **00:00–02:00 UTC / 09:00–11:00 JST** against staging for exactly
the 21 `config.yaml` enabled brands. Use all six applicable B/C keyword/handle
calls and eight fixed 15-minute slices (48 collection units). Include a separate
Qwen/B1 historical-name supplement over the same bounds and slices using the
already verified `"Qwen3.8"` alias (eight further units). Retain both original
failed pilot receipts; no full-day/month campaign, production mutation, shared
schema, deployment or schedule change is authorized by this amendment.

Freeze actual dry-run queries/config/database identities before paid execution.
Each invocation has at most 60 physical API starts, 60 model starts, 300 seconds,
five pages/100 primary results per unit, and five newly inserted posts per unit
for inline enrichment. One foreground controller may resume the two campaigns
at most **12 invocations total** (720 API and 720 model starts reserved across
the test), serially, with pauses outside writer leases and the existing scheduled
slot admission/reserve. No unbounded retries or new windows. Stop on blocked
pagination, identity/schema errors, authentication/funding failures or exhaustion;
inspect actual failures before an explicitly bounded repair/resume.

At current provider prices, 720 normal 20-result pages imply a conditional
USD2.16 search allowance; actual raw results, empty-call floors, retries and
lookup usage must be reconciled from transport receipts, not inserts. This is
a planning estimate, not a billing guarantee. Capture model usage when returned;
keep unknown token/cost evidence explicit. Preserve canonical model routes and
the literal-translation/canonical-classification acceptance contract.

Success requires both campaigns' collection units drained, at least one newly
inserted in-window post, persisted literal translation and canonical per-brand
classification for every frozen new-post cohort, and unchanged staging
CallState/HarvestBacklogWindow digests. Report all recovered posts outside the
bounded cohort as pending separately. Report per-call/brand/slice inserts,
duplicates, API/model starts, token usage, elapsed/CPU time, peak memory/threads
and active concurrency; scale forecasts only from a meaningful measured sample.

The following records the original sample and its unsuccessful execution.

After cleanup, render a concrete dry-run manifest for the exact sample already
defined in this conversation: Qwen through B1, August 9, 2026
00:00:00–00:15:00 UTC (09:00:00–09:15:00 JST), one finite invocation. A changed
window or a substitute helper-only/probe-only route cannot silently replace it.
The full padded August windows remain follow-up work; this authorization is
for the 15-minute test after the fixes, not automatic full-month collection.

Make population, finite API/model limits, runtime placement, resource admission
and stopping rules concrete before the live test. The owner now authorized that
test; do not ask again whether to run it. Resolve only genuinely missing runtime
or release authority. Implement a finite test allowance and stop/review on its
exhaustion; no repeated paid attempts merely to obtain a green result.

Live proof: executing revision, actual on-demand receipts, before/after unique
counts for fixed creation intervals, deduplication, enrichment outcomes for exact
IDs, live-cursor invariance and observed scheduled harvest continuity. Apply the
persisted-health skill if changes touch enrichment, retaining its exact cohort
and grace window. Fresh pending work is inconclusive. Search draining is scoped
coverage, not proof of a complete X census.

## U8 — Slow month-sized campaigns [deferred]

Reuse U2–U5 units for a fixed July/month interval. Require restartable checkpoints,
finite batches, pauses outside leases, low concurrency, daily/campaign allowances,
queue/resource watermarks and live-collection priority. Report per-call/window
collection separately from enrichment. Choose hosting/scheduling only in the
later task: do not create cron, activate beat or replace scheduled harvesting now.

## Sources and checks

Read: current-main command/runner/client/config/tests, `AGENTS.md`, relevant
skills and vocabulary, historical backfiller solution and pause runbook.
Provider [Advanced Search](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search)
and [pricing](https://twitterapi.io/pricing) verified October 12; raw-result costs
include duplicate retrieval. No cost forecast is inferred from stored posts.

The October 12 audit used read-only production aggregates. October 13 work added
code fixes, PostgreSQL regression proof, two actual staging attempts and bounded
provider diagnostics. No production writes, schema changes, schedule mutations,
production release or month process ran. Detailed current evidence follows.

## Session log

- 2026-10-12T19:56:15+09:00 ON — Independent August audit opened at current main
  in canonical worktree; preserve root edits and G1–G5 ownership.
- 2026-10-12T19:58:21+09:00 EVIDENCE — Read-only month snapshot captured;
  hourly collapse and long first-insert gaps identified.
- 2026-10-12T20:11:34+09:00 OFF — August audit complete; five major/two smaller proposed recovery windows, current-main backfill assessment and follow-up requirements saved. CSV/hourly reconciliation, links, plot and annotation checks passed. Cleanup implementation and paid/background runs remain unexecuted; preserve worktree and G1–G5.
- 2026-10-13T15:33:13+09:00 ON — LFG resumed after owner selects fixes plus successful real 15-minute test; latest main fast-forwarded in own worktree, G3 scope/persistence proposal sent. Shared-schema edits held pending contract.
- 2026-10-13T15:43:05+09:00 GATE — Shared persistence contract remains pending G3 response (X purpose/lifecycle, cross-attempt resume, adapter ownership or atomic-JSON interim boundary). Scope/design sent twice with full detail here; no application changes, schema edits, commits, pushes or paid test performed. LFG success remains the successful 15-minute test, not this coordination receipt.
- 2026-10-13T17:45:03+09:00 STATUS — Owner's check-files continuation verified G3's JSON-pilot approval in both plans. U2–U6 implemented; final regression net252pass/107requiredPG/0skips/errors. Real fixed-window staging attempts atfd8d0b79 and0c967468 recovered0new posts; second deduplicatedoneexisting Qwen3.8 post. Test remains unsuccessful; replacement sample manifests prepared read-only and owner selection requested. No shared schema, production mutation, schedule or month campaign.

## October 13 implementation and live evidence

Source commits: `d2906dc1` (bounds/atomic checkpoints), `fd8d0b79`
(cursor units/resource isolation), `0c967468` (explicit historical query),
`2cf43ef3` (zero-budget deferral and PostgreSQL fixture repair).

- 252 tests passed; 107 required PostgreSQL tests executed, zero skips/errors.
  Includes the real command/runner/transport/ORM chain, pause-time competing
  writer, physical retries, concurrent model caps, failed enrichment, exact
  cursor resumption, changed-query rejection and scheduled seven-call controls.
- Focused Ruff lint and Django system checks pass. Project-wide Ruff finds
  existing debt outside this scope; no project typecheck is configured.
- G3 owns shared tables/lifecycle/API. Atomic JSON on fuchitalee is approved
  for the pilot. No `core/models.py`, migration or collection-schema edits.
- Historical Call A stops before provider construction until its account
  population can be frozen. B/C recovery supports one-brand/one-call `--query`
  overrides, rejects embedded time bounds, and fingerprints the actual query.
- Real pilot1: August9 00:00–00:15UTC, Qwen/B1, staging, sourcefd8d0b79.
  One request, zero results/inserts/model calls, 3.150seconds, 103.22MiB peak RSS.
- Real pilot2: identical dates/brand/call/limits, source0c967468, explicitly
  includes verified historical Qwen3.8 name. Two pages returnonealready-stored
  ID, zero inserts, one update, zero model calls, 9.813seconds, 103.67MiB RSS.
  Both attempts preserve staging cursor/backlog digests. No new cohort exists.
- Seven additional diagnostic requests isolate the name mismatch. Exact
  Qwen3.8 searches return the known August9 post; the current Qwen/Qwen3 query
  does not. `Top` with epoch bounds returns October rows and is not adopted.
  Ten total TwitterAPI requests across pilots/diagnostics; all ON_DEMAND,
  zero model calls. These observations do not estimate enrichment or month cost.
- A production health baseline and the same20IDs after30minutes were read
  without writes/providers: translation/classification states succeeded, but
  the legacy commentary acceptance criterion remains unmet. This is existing
  deployed behavior, not proof of this undeployed candidate's enrichment.
- Reviews ran inline under the repo tool mapping. The independent Grok route
  requestedgrok-4.7/xhigh and returned findings; serving model/effort are
  unverified, different-family independence is attested. Claude's first route
  returned402/no review. Supported findings were fixed; no peer job remains.
- Browser testing: no affected routes; backend command/transport/database only.

Private host evidence and native implementation/review receipts live under
`data/backfill-fixes-20261013/`; raw responses, credentials and runtime dumps
remain uncommitted. A concise report is saved in
`docs/analysis/harvester/2026-10-13-174503-backfill-fixes-and-pilot.md`.

Prepared, unexecuted replacement choices (Qwen/B1, one invocation, explicit
Qwen/Qwen3/Qwen3.6/Qwen3.8/通义千问 query, same finite limits):

1. August1 08:00–08:15UTC /17:00–17:15JST, inside the first confirmed gap.
2. August9 00:15–00:30UTC /09:15–09:30JST, adjacent to the original sample.

Actual read-only dry-run identities are retained in
`data/backfill-fixes-20261013/proposed-pilot-manifests.json`.
These proposed alternatives were superseded by the owner's two-hour/all-21-brand
amendment in U7; do not execute them. The original unsuccessful
receipts and campaign identities must remain intact. U7 and the overall LFG
task are incomplete until a real approved recovery test satisfies the required
new-post and persisted translation/classification evidence.

## Planning Contract — bounded JSON pilot

Use a versioned atomic JSON campaign record on fuchitalee. Freeze ordered UTC
bounds, brand/call selection and effective-query/config identity. Add explicit
state-directory selection; refuse incompatible old completion state rather
than silently inheriting it. Retain attempt timestamps/counts for later G3 import.
Do not implement CollectionJob or alter shared schema in this run.

Historical fetching should use the shared client's provider cursor page iterator
rather than repeated newest-first time sweeps. Commit the returned continuation
only after successful persistence. Same-second IDs, repeated cursor and partial
failure need regression coverage. Keep scheduled behavior on its existing path.
Use a shared invocation budget at physical HTTP/model transport boundaries,
including retries; isolate optional/global work and enrichment to the recovered
IDs. Acquire the existing writer lock per bounded unit, release before pauses,
and refuse admission if the full configured envelope would cross the next live
slot reserve. Invalid options/status/dry-run must perform no paid work.

## Verification Contract

- Meaningful red/green tests through the command, shared runner, captured real
  HTTP client boundary and PostgreSQL. Required PostgreSQL tests must execute
  without skips. Preserve scheduled regression nets.
- Atomic-file fault and concurrent-writer checks; resumed requests use committed
  provider continuation and unchanged frozen bounds; aggregate budgets span calls.
- Prepare a finite pilot manifest before provider work: Qwen/B1, August 9
  00:00:00–00:15:00 UTC, on-demand credential, staging database identity, at most
  five primary search pages and a finite total API/model allowance. Raw-return
  and paid-attempt counts remain distinct from inserted/deduplicated totals.
- Pilot success needs real matching results and at least one newly stored scoped
  post, truthful drained/partial collection state, complete persisted translation
  and canonical classification for a frozen bounded recovered cohort, unchanged
  live cursors and no production writes. Explicit remaining enrichment is retained
  and reported; do not claim all posts finished from the cohort check.
- A cap/failure/empty or unavailable-provider result is inconclusive/failed, not
  successful proof. Fix an evidenced cause and resume only within the frozen
  finite allowance; no automatic expanding search or repeated paid quality loop.

## Definition of Done

U2–U6 code and appropriate tests are implemented, reviewed and delivered within
the authorized route. The parent executes U7's exact live staging pilot and
retains actual request/post/enrichment evidence. The original user requirement
wins: no DONE until that 15-minute test succeeds. U8 and G3's future DB adapter
remain deferred. Remove abandoned experimental code; preserve unrelated work.
- 2026-10-13T15:58:09+09:00 RESUME — G3 approval verified in both files: atomic JSON staging pilot may proceed without CollectionJob. Prior coordination gate cleared; preserve G3 shared schema ownership and exact 15-minute success requirement.

- 2026-10-13T09:46:31.906637+00:00 ON — Owner widened U7 to August9 00:00–02:00UTC/all21brands. Frozen dry-run manifests prepared against verified staging at f5bbe190; 48 normal B/C units plus8 historical-name Qwen units, serial execution,12 finite invocations/720API/720model starts maximum. Original failures and G3 shared-schema ownership preserved.

- 2026-10-13T10:13:39.131194+00:00 EVIDENCE — Expanded test first3invocations:67new scoped posts,49API starts,49model starts,33frozen sample posts/19complete; normal collection30of48units drained. Cursor/backlog digests unchanged. Measurement-only controller now bulk-reads cohort facts and was restarted while idle; application source/frozen limits/checkpoints remain unchanged. No test failure or paid invocation was discarded.

## Live-test repair and next four-hour scope

The two-hour normal collection drained48units and inserted98new posts at f5bbe190. Live enrichment exposed a persistent long-post timeout (5k-character chunks against the manual30-second request limit) and first-unit starvation during enrichment-only resumption. Retain all six invocation receipts and unsuccessful model attempts. Repair visits each enrichment unit once per invocation and threads a2k chunk size through manual translation and matching cache loading; scheduled defaults stay5k/90seconds. No shared schema or model route changes. New actual-caller tests pin manual cache/translation agreement and scheduled defaults. Final repair regression net303pass/109requiredPG/0skips/errors; focused lint passes. Independent Grok review remains required before Git publication; the authorized staging test may validate the green local repair concurrently.

Owner selected **four hours** next: August9 **02:00–06:00UTC /11:00–15:00JST**, all21brands, only after the current two-hour sample passes its complete cohort/collection/invariance check. Use a separate manifest/checkpoint directory and the same15-minute slices, six B/C calls plus verified historical Qwen supplement, serial300-second invocations/60API/60model starts each,12invocations total per new window. Preserve all previous evidence; no production, deployment, scheduler or schema action.

- 2026-10-13T10:47:47.684087+00:00 STATUS — Live two-hour collection98new/drained; enrichment incomplete. Controller stopped after durable invocation6 for targeted timeout/fairness repairs. Current source regression303pass; independent review pending. Owner-approved next4hours recorded above, not started.

- 2026-10-13T11:10:51.894904+00:00 REPAIR — Smaller2k model calls returned successfully, but live invocation7 revealed a cache unique-key collision with legacy5k chunks. Chunk layout now uses a distinct prompt-version namespace in the existing table. Two invocation7 chunks with validated2k fingerprints were relabeled in staging, with exact pre-correction backup and no translated-text/token loss. No schema or model change. Database regression pins coexistence with scheduled5k cache rows; full304pass/110requiredPG/0skips/errors. Grok4.7/xhigh attempt timed out600s without usable output; native inline review completed and peer terminal job cleaned.


### Bounded classification diagnosis after invocation12

The12-invocation controller stopped at98new inserts/48normal units drained,48of49cohort posts complete,81API and175model starts. One two-brand post (`2086263847346663470`) remains classification pending despite successful model transports; the8historical Qwen units have not started. No success or four-hour launch is claimed. Under the existing LFG fix-until-live-pass request, add exactly one diagnostic invocation, followed by at most two repair/supplement invocations only after inspecting the cause. Retain the original cumulative720API/720model allowance,10800-second wall deadline, frozen options and all prior receipts;15total invocation ceiling now includes this bounded repair. Capture private classifier role responses and publication result without changing semantic acceptance. Stop after diagnostic capture.

The private checker now matches `literal_translation_artifact_complete`: current source fingerprint, succeeded/current artifact, all EN/ZH-CN/JA meaningful locale texts. Its legacy six-language helper incorrectly rejected a valid Spanish `es` artifact; preserve that legacy compatibility result separately. This strengthens translation proof from two fields to three current locale texts and does not modify product behavior.


### Confirmed shared classifier conflict; protocol decision pending

Invocation 13 captured the real selected two-role responses. Both role parsers accept them. For GLM, content returns `classified` with supported types/topics, while brand interpretation returns `unknown` sentiment and unavailable geopolitical context. `core/classification_contract.py:319` rejects a classified row with null/unknown sentiment; `x_monitor/attribution.py:4414` therefore returns the empty invalid result and no publication is attempted. The scheduled harvester shares that path. This is a semantic disagreement under the selected classifier protocol, not a remaining chunk/cache failure. Preserve strict validation and the pending post; do not insert neutral sentiment, remove an attributed brand or waive the cohort.

The controller is stopped after diagnostic invocation 13. Actual cumulative use is 81 X API starts / 177 model starts, 98 newly stored posts, 48/49 complete frozen cohort posts, unchanged cursor/backlog digests. The eight historical Qwen units have not started. The owner-approved next four-hour window is prepared and waiting for current acceptance. No paid continuation is running.

Proposed bounded reassessment, pending owner direction: make one additional semantic assessment only for a post whose individually valid roles cannot produce a valid combined judgment. Keep the canonical model, source/context, all expected brands and strict acceptance. Fit both requests within the existing model-start/deadline guard; save no new classification unless the complete combined result passes. Record the reassessment's prompt/request provenance. Limit to one reassessment per post per attempt; a second disagreement remains pending. Cover successful reconciliation, repeated disagreement, insufficient call/deadline budget, unchanged normal success, and actual runner publication in tests. This changes the selected two-call classifier protocol, so it is not applied without direction.

Evidence: [two-hour report](../analysis/harvester/2026-10-13-204138-august-backfill-wide-pilot.md). The async owner question offers bounded reassessment then continuation, or preserving the classifier protocol and leaving the test incomplete. This is a protocol decision; August bounds, all 21 brands, staging execution and G3 JSON approval are already settled.

- 2026-10-13T11:44:52.043048+00:00 OFF — Controller stopped after diagnostic13; shared classifier conflict confirmed, no protocol fix applied pending owner decision. Updated draftPR58 description with98new/48of49cohort incomplete and304tests/110requiredPG. Four-hour window remains approved/prepared but not started. Retain own dirty plan/local evidence and close only owned staging tunnel; other sessions and services preserved.


## Owner override and 24-hour staging continuation

Latest owner direction: “i'll override and call that good enough. let's instead go to 24 hours... based on our first 2 tests, will that overtax the system”. The prior classifier-protocol question is retired; do not add reassessment, invent labels, retry the last post until it passes, or recreate the earlier all-cohort gate. The two-hour receipt retains its strict incomplete result; record a separate owner acceptance. The four-hour manifest is historical/prepared only and will not run.

Execute August 9, 2026 **00:00–August10 00:00UTC** / **Aug9 09:00–Aug10 09:00JST**, all 21 enabled brands, staging only. Keep six B/C calls plus the verified historical-name Qwen supplement, 15-minute slices:576normal plus96supplemental collection units. Use a fresh atomic checkpoint/manifest directory. Source remains committed6925e846; no application, classifier protocol, schema, production, scheduler or service mutation.

Resource controls: one serial local controller; one X request at a time, existing maximum three model workers, per-unit writer leases and scheduled-slot admission/reserve. Each invocation retains60API/60model starts,300seconds,5pages/100results per unit and5new-post sampled enrichment; add2seconds between units outside the writer lease and60seconds minimum between invocations. Entire run stops at72invocations,1440XAPI starts,3240model starts or18hours of wall time, whichever comes first. A complete invocation's60starts must fit remaining cumulative allowance before admission. Stop on blocked pagination, command/storage/authentication errors, cursor/backlog drift, excessive local RSS (>512MiB) or PostgreSQL connection saturation (>=80%of maximum). Do not enlarge limits silently. Retain all receipts if incomplete.

The two-hour measurements are118.16MiB peak local memory,43.169CPU seconds/2560.163active elapsed seconds,81XAPI/177model starts,USD0.0315 estimated X cost andUSD0.145739 known model cost with7unknown-cost requests. Twelvefold scaling suggests972X/2124model starts and8.53active hours; it includes fixed-path repair overhead and is not a throughput promise. The first15-minute probe was empty and supplies no useful volume estimate. Peak load is bounded by concurrency, while total time/credits grow. Staging harvest is suspended, so overlap with live production harvesting is not proved.

For this owner-accepted collection continuation, completion means both provider campaigns drain, newly scoped posts are stored and shared cursor/backlog digests remain unchanged. Report every sampled assessment status and unfinished post without labelling pending work as completed. Do not make complete enrichment of every recovered post a gate for finishing collection; existing tests and canonical validation remain unchanged. Monthly background scheduling remains deferred.

- 2026-10-13T13:24:32.877368+00:00 ON — Owner accepts2h partial assessment and selects24h instead of4h. Retire reassessment question/all-cohort barrier; prepare fresh stagedAug9 full-day manifests with finite serial/resource guards. Source6925e846 preserved; no production/schema/scheduler mutation.


### Month-sized recovery: proposed changes, not launched

Owner asks how to build toward a month. Keep the existing shared fetch/attribution/storage path and 15-minute checkpointed units. A 31-day month across the current six B/C calls contains17,856normal units; a comparable single-query historical supplement adds2,976units. Treat provider-query exhaustion as scoped evidence, not complete X coverage. Verify month-appropriate brand aliases and freeze the query/config snapshot. Historical CallA needs a frozen account population before inclusion.

Add one background dispatcher with durable pause/resume/stop/status and progress. Coordinate instruction/scheduling persistence and a legitimate X-collection run purpose with G3's `CollectionJob`/shared lifecycle APIs; do not add parallel job/run tables or label X collection as catalog/metrics work. Preserve Post storage and existing cursor/backlog semantics. Interim host checkpoints remain until an approved shared integration exists.

Add durable hourly/daily physical-request and spending budgets, recording admission before transport so process failure cannot reset credit allowance. Expose a manual/background model concurrency limit (start low), pauses outside writer leases, normal-harvester priority, finite leases and bounded retries. Separate collection progress from enrichment progress: an unresolved assessment cannot indefinitely hold up the month; failed provider pagination still remains explicit and cannot be marked drained. Record total units, newly stored/duplicate posts, provider cap/blocked slices, sampled/all enrichment states and measured costs.

Split the month into day-sized instructions that resume the same quarter-hour slices; one process handles them serially. Use the completed24-hour measurements to choose daily budget and duty cycle. CPU/memory peaks are governed by concurrency; elapsed time, traffic and credits scale with volume. A month at the same pace may take many days. No month collection or scheduler/worker deployment is authorized or launched by this design answer.

- 2026-10-13T13:37:59.466388+00:00 STATUS — Full-day controllerPID20739 running; firststaging invocation completed271.905s/6.408CPUs,29XAPI/0models,108.55MiB/2threads/1Xrequestconcurrency,11of103DBconnections.19 normal units drained and existing posts deduplicated; no command error, cursor/backlog digests unchanged. HistoricalQwen next; no full-day completion claimed. Keep tunnelSSH19742/session32290 andcontroller/session8987 alive.


### October14 JST: inspected X transport timeout and bounded continuation

The full-day controller stopped after invocation22 at2026-10-13T16:55UTC/Oct14 01:55JST. It stored323new posts (144normal/179historicalQwen), drained110/576normal and54/96Qwen units, and retained all pages. Receipt:305API/256model starts,123.97MiB peak RSS,101.263CPU seconds/6124.281active seconds,85of228sampled posts with complete persisted assessments; incomplete enrichment remains explicitly reported under the owner override. Shared cursor/backlog digests were unchanged.

The last Qwen request at Aug9 13:30–13:45UTC returned no response within30seconds: ReadTimeout,0received pages,0posts,0persistence failures. Its pending unit retains a null cursor and empty IDs; the previous13:15–13:30slice had safely drained its saved continuation. There is no evidence of authentication/funding/storage/pagination corruption or local memory pressure. A fresh read-only DB/source/invariance check precedes continuation.

After inspecting this exact fault, resume within the original72invocation/1440API/3240model/18hwall limits. The private controller may recover only pure first-page fetch ReadTimeout/ConnectTimeout/ConnectionError with explicit0persistence failures and an unblocked pending unit, at most two additional attempts per unit. Retain failure receipts and pause60/120seconds outside writer leases; all starts consume the original counters. Other errors still stop. This does not change application source, canonical classification or the owner-accepted pending-assessment rule. Do not reset the wall deadline or increase budgets.

- 2026-10-13T21:59:52.394070+00:00 ON — Status revealed stopped24hcontroller after one30sXReadTimeout. Inspect pending checkpoint; prepare bounded retry/resume within existing caps. No schema/source/production/scheduler mutation.

- 2026-10-13T22:03:49.741821+00:00 STATUS — Resumed owned controller PID20839/session42937, with original deadline and budgets. Invocation23 prioritizes the timed-out Qwen unit; new X responses returned HTTP200 at22:02UTC. Prior complete receipt:323new staging posts/164of672units drained/85of228sample assessments complete. No production writes or shared-schema/code change. Keep owned tunnel19742/session32290 and controller alive.


### Staging rollout interrupted SSH; transport and failure accounting repaired

Staging web deployments at22:01–22:04UTC and22:10–22:12UTC replaced the instances used by the owned DB tunnel. Invocation23 retried X successfully, then lost its DB connection. No production resource was changed. Fresh native SSH forwarding with keepalives is verified against the same staging PostgreSQL18.4/database/role and unchanged cursor/backlog digests. External PostgreSQL access is intentionally denied by the IP allowlist; preserve that configuration. No global SSH keys/host checking/networking change was made.

The private controller had reused stale last-invocation usage when DB loss prevented checkpoint finalization. Preserve the original invocation23 receipt in diagnostics; reconcile its actual2Xresponses/8modelevents, and observe the live budget directly for future failure receipts. The interrupted batch stored2additional scoped posts before checkpoint completion. Replay the pending slice through existing Post dedup to recover bookkeeping; do not advance its cursor by hand or fabricate assessment completion. Original72/1440/3240/18hlimits and source6925e846 remain fixed.

- 2026-10-13T22:25:11.702054+00:00 STATUS — Native staging SSH25418/session33409 and controllerPID25918/session19092 live. Identity18.4/stagingrole and unchanged cursor/backlog verified.323checkpointed new posts plus2verified partial-batch inserts;85of228sample complete. No deadline/budget reset; keep both owned processes alive.

## Owner correction: historical batch, independent of harvest cadence

The owner explicitly rejects reproducing the harvester over each quarter-hour:
"this is not reproducing harvester * n days. it's a one time batch exercise
without the limits of harvester". Retire fixed 15-minute slicing, two-second
unit sleeps, sixty-second batch sleeps, scheduled-slot admission/reserve and
five-page/100-result query stopping for the batch route. Preserve the existing
scheduled collector and the compatibility sliced route. Payment is not a reason
to throttle a batch. Provider response pagination still returns at most20posts;
a month is a broad paginated query, not one physical HTTP request.

TOUCH: on-demand `backfill` command, its PostgreSQL integration regression net,
private staging controller and this plan. PRESERVE: shared CycleRunner fetch/
attribution/persistence, normal harvest policy/cursors/backlog, model semantics,
G3 schema and service inventory. The authorized live interval remains Aug9 UTC,
all21brands, staging. No July/month execution or production mutation is added.

Implementation-ready batch amendment:

1. Add explicit `--batch` mode. One unit spans the entire supplied query window;
   fetch one complete provider page through the real runner, persist it and
   atomically checkpoint before asking for the next page. No per-query page cap
   can falsely complete the query. Invocation-wide physical-request/time budgets
   remain finite and resumable; batch admission has no cron timing dependency.
2. Collect with zero inline model calls/cohort. Existing or newly pending
   translation/classification is reported separately and cannot hold collection.
3. Stop only the owned old controller between invocations. Freeze its evidence;
   merge adjacent pending intervals independently for each exact frozen query.
   Preserve completed intervals. Never transfer a cursor to changed bounds;
   replay any partly persisted unit via existing Post deduplication.
4. Continue within the original cumulative1440API/3240model/18hallowance and
   original deadline. Remove obsolete72invocation-count coupling when each new
   invocation is page-checkpointed batch work; do not reset spent requests.
5. Keep retry pauses only for observed recoverable transport/database failures.
   Reconnect and verify staging identity/invariance before replay; never advance
   past persistence failure. Keep the staging web tunnel limitation visible.

Regression net: real command→CycleRunner→TwitterAPI transport→PostgreSQL proves
30-day bounds are preserved, no scheduled-slot query/sleep/model transport is
used, cursor progress is saved after every page, failed later pages retain earlier
stored pages, capped invocations resume exact cursors, shared live state stays
unchanged, and the compatibility reserve remains enforced outside batch mode.
Live completion: all previously drained and newly merged query intervals cover
the pinned Aug9day, provider continuations end normally, saved distinct posts
are reconciled, shared cursor/backlog digests stay unchanged, and enrichment is
reported separately under the existing owner override. Prior scaling estimates
describe the old sliced/inline route and are retired for the batch design.

Batch implementation and live continuation: `--batch` is a thin mode in the
existing command, using the same CycleRunner/TwitterAPI/attribution/Post path.
Each page is committed and atomically checkpointed; per-query five-page stopping
is gone. Batch collection requests no model calls or cron timing/sleeps. A
thread-safe remaining-API property stops at invocation allowance without making
normal budget exhaustion an error. The compatibility sliced route is preserved.

Verified129tests,89requiredPostgreSQL tests executed,0skips/errors; focused Ruff
and Django system checks pass. Initial normalization-through-kwargs failure was
fixed by returning resolved options with preparation; a test cursor assertion
was corrected to the documented optional first-page cursor. Both original failed
logs remain private. Regression proof includes a real30-day query through7pages,
per-page Post/checkpoint agreement and later-timeout/capped-invocation resumption.

Owned old controller25918 stopped between invocations after42completed attempts
(496API starts); preserve its entire manifest/state/receipts. HistoricalQwen is
drained. Merge remaining normal intervals into6queries: C1/C2/C3/B2/B3 from
Aug9 07:00UTC and B1 from07:15UTC, all endingAug10 00:00UTC. Verified their exact
queries match the frozen original. New controller66296/session22824 uses the
same owned staging SSH25418/session33409, retains original1440cumulativeAPI
allowance and16:26:50JSTdeadline, and stores private evidence under
`data/backfill-fixes-20261013/full-day-batch-aug09-21brands/`. The running candidate
records baseline HEAD6925e846 plus an exact application-source digest; code is
locally modified, not a deployed revision. Never call this an exact-SHA deploy.

First real batch pages returnHTTP200, persist new Posts, and commit continuation
without persistence failures or model starts. Current remaining latency includes
many ORM round trips through the Japan→Oregon tunnel: one observed20-result page
took78.7seconds, with75.9seconds to the final Post commit. Read-only pg_stat_activity
showed client waits and no observed database-lock wait. No claim that provider
calls alone determine runtime or that the full day is complete. G3 notified of
command/resource/test scope and unchanged approved JSON/shared-schema boundary.

## U8 — Render one-off execution with G3 collection bookkeeping

Owner selected `lfg this` for the Render move, then requested incorporation of
G3's completed collection work. Source/API inspection establishes the correct
reuse: CollectionJob stores frozen manual content/x_backfill/historical
instructions; CollectionRun records a claimed attempt and actual usage;
CollectionScopeRun stores fenced per-query/page continuation. Tweets remain in
Post and existing relationships/enrichment. No backfill-specific table is added
or retired. G3's one planned CollectionJob table remains its owned dependency.

Read-only live evidence on October14: actual database/rolepushinweight_staging,
PostgreSQL18.4, only0080_collection_schema; collection_runs/observations/scope_runs
exist, collection_jobs does not. Run lifecycle currently admits metric/catalog,
not content, and run.job/lease_token are absent. Latest staging web deployment is
b53c2e8bd7ce26688b0f93612297b391a83462e0. G3 source/API at443d13f3 implements
0081–0082 and supports X explicitly. The G3 owner has now authorized its PR59
deployment through a separate delegate; that session owns schema delivery.
These are independent observations. Do not label existing stage0080 as a ready
X-job lifecycle, misuse catalog purpose or silently deploy another owner's paused
release. Coordinate dependency delivery and preserve current local collection.

Implementation scope once the supported dependency is available:

- Existing backfill command exposes a database-job route while retaining JSON
  compatibility/import. Add a narrow monitor/backfill_collection.py adapter and
  focused command→runner→PostgreSQL tests. Reuse core.collection_jobs/state/budgets
  rather than copying registration, lease, cursor or finish rules.
- Freeze exact query/bounds/brand/config identity and on-demand credential-purpose
  name in instructions; never store credentials. Import actual committed legacy/
  merged progress with file hashes and provenance; do not invent historical run
  timestamps. Preserve completed prefixes and exact broad cursors.
- Provider requests stay outside transactions. Fence the existing shared Post
  writer and commit scope continuation atomically with that page's writes;
  stale/paused/expired workers cannot publish or advance. Persist physical request
  admission before transport so executor failure cannot reset paid allowance.
- Start a separate Oregon Render one-off job from the verified staging build,
  using its internal staging DATABASE_URL and ON_DEMAND key. Shared database
  state becomes authoritative; JSON/logs are optional exports. No new recurring
  scheduler, normal-harvester activation or standalone backfill service/table.
- Verify exact build/source, database/role, source/query ownership, real page
  persistence, pause/restart/continuation and unchanged live cursor/backlog.
  Compare a matched captured page near the DB versus the local route; report
  observed speed rather than extrapolating the unmeasured97%phase.
- Finish at an observed successful Render job and reconciled authorized Aug9
  collection, with pending enrichment explicit. If Aug9finishes locally before
  transfer, import completed coverage and use a bounded captured-page storage
  benchmark; do not expand to another day/month.

G3 received the live discrepancy, exact file scope and API handover request.
Render move gate: supported0081content/job schema and matching G3 API build must
be observed in staging before a DB-job-backed paid launch. This is a runtime
prerequisite, not renewed approval for the already authorized backfill or move.

- 2026-10-14T03:55:52.423660+00:00 ON — Owner reconfirmed LFG and explicitly required TWITTERAPI_IO_ON_DEMAND_API_KEY for backfiller. G3 owner resumed PR59 deployment through its own delegate; no duplicate release or shared-schema edits here. Local batch source is preserved before DB-adapter work; current tests cover129passed/89requiredPG/0skips/errors.

- 2026-10-14T04:03:26.917228+00:00 COLLECTION COMPLETE — Local Aug9 UTC day drained all7query windows,1557new staging Posts; original live cursor/backlog digest unchanged. Batch broad phase100physicalAPI starts,0models. Existing completed source626a3007/private bytehashes retained. U8 now imports completed evidence and runs matched duplicate-update captured-page storage probes locally/Render, with zero extra paid calls.

- 2026-10-14T04:12:54.958424+00:00 U8 IMPLEMENTATION — DB-job route, durable physical admission, fenced shared Post/page commit, stale/paused/expired rejection and source-pinned captured-page duplicate-update probe implemented. Final212pass/111requiredPG/0skips/errors, Ruff and Django checks pass; makemigrations reports0newtables/changes. Source G3 dependency merged locally unchanged. Live stage948f05ad/0081–0082 observed; import instruction registered paused. New scope does not activate any scheduler. Browser routes:0affected; pipeline browser step skipped with that reason. Compound documentation skipped: reasoning and limits already preserved here/code/tests. Review is inline per AGENTS toolmap plus sanctioned Grok pass; receipt pending.

- 2026-10-14T04:14:56.273726+00:00 REVIEW — Native sequential review of X adapter completed; lease-expiry commit guard and Post reconciliation pins applied. Grok4.7/xhigh reached600s timeout and produced no usable schema output; cross-model coverage degraded, no approval claimed, terminal peer scratch removed. Exact scoped source/diff digest and limitations saved privately. Local regression evidence212pass/111requiredPG/0skips/errors covers final adapter.
