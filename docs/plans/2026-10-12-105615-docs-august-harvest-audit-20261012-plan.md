---
title: Audit August X gaps and prepare bounded historical recovery
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: docs-august-harvest-audit-20261012-2026-10-12-105615
  branch: docs/august-harvest-audit-20261012
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
# Audit August X gaps and prepare bounded historical recovery

## Plain-English Summary

The production audit confirms five substantial gaps in August 2026, including
the nearly empty August 9. Exact evidence boundaries, padded recovery windows,
daily counts in UTC and Japan time, and an hourly plot are saved.

The next step is to repair the existing on-demand backfiller so it can recover
small parts of those windows, remember actual progress, and yield resources to
the normal harvester. It will keep using the same fetch, attribution, storage
and enrichment pipeline. Live collection and G1–G5 retain their ownership and
behavior. Missing enrichment on already-stored posts is a separate workload.

The owner authorized the fixed 15-minute staging test after cleanup. Both real
attempts ran, but neither recovered a new post: the corrected historical query
returned one already-stored post. The requested success condition remains unmet.
Two replacement 15-minute samples have been prepared without paid calls and need
the owner's selection because they change the fixed interval. Later, the same
small units can support month campaigns. No background process or production
release was selected. Historical search does not establish a complete X census.

Verification will exercise the management command through the shared runner,
captured fake providers and PostgreSQL. Time bounds, credential purpose,
checkpoints, total budgets and lock release must work together, while the
scheduled seven-call path remains unchanged.

## Goal Capsule

- Objective: fix the current on-demand backfiller's deficiencies and prove a
  successful real 15-minute Qwen/B1 recovery against staging.
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

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`
- Delivery route: `staged`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

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

## U7 — Successful real 15-minute recovery test [executed; unsuccessful]

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
Do not run either until the owner selects it. The original unsuccessful
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
