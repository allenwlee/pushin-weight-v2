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
enrichment on stored posts is a separate processing phase.
The owner's October 14 requirement makes batch enrichment part of the backfiller:
collecting posts alone no longer completes the overall task.
The same design must handle a month or longer with bounded memory, durable progress,
and no repeated collection or completed model work.
Collection and Render adoption are verified. Native batch enrichment is implemented
and locally verified. On October 15 the owner selects ordinary DeepInfra API calls
for immediate staging results, retaining native Batch for later production work.
The staging pilot and full-day persisted outputs remain the acceptance work.
Both transports share request preparation, saved replies, validation and persistence.

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

- Objective: recover historical X posts and finish their required enrichment through
  the backfiller, with resumable batches suitable for a month or longer.
  August 9 staging collection is verified; end-to-end completion now also requires U9.
- Authority: owner's LFG fixes-and-test request and October 14 `go`; G3's
  adjudicated ProviderBatch extension is in scope. Production collection,
  production release/import and new month campaigns remain outside this run.
- Means: shared CycleRunner, durable collection scope checkpoints, typed Post
  membership, bounded provider work and physical-call accounting,
  exact-cohort enrichment and a staged provider-backed pilot.
- Execution: inline, sequential work on this existing canonical branch. The
  parent owns review, PR/CI and live pilot proof; implementation returns locally
  verified code and its prepared pilot contract.
- Stop: preserve state and report a real failed/partial test or exhausted finite
  allowance; never replace the fixed window or substitute a mock for live proof.
- Current continuation: the owner's `go` authorizes paid LLM enrichment on the
  existing August 9 staging cohort, followed by its remaining posts after the
  persisted pilot succeeds using the owner's selected ordinary API transport.
  Record physical model calls and measured server use.
  Zero TwitterAPI calls; no new month campaign or production transfer.

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

October 15 owner selection: use ordinary DeepInfra API calls for the present
staging enrichment; native Batch acceptance is superseded for this run. Preserve
the native implementation for future explicitly selected work. The owner challenges
four-call concurrency as unnecessarily conservative: start at32 adjustable
in-flight calls, measure throughput/memory/errors, and raise concurrency when
evidence supports it. No fixed pause between successful ordinary requests.
Retain all prior replies, unknown charges, USD5 pilot/USD25 full-day ceilings,
20000 model starts,5000 control starts,3 attempts/input and the original72-hour
deadline. Reconcile the cancelled six-request native classifier group before
replacing its outstanding work. No new tables/migrations or production authority.

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

- 2026-10-14T04:44:45.982343+00:00 U8 REPAIR — Render59efc07a verified actual staging/internalDB and ON_DEMAND availability, then safely rejected unrelated publisher-config drift before claiming. Collection hash now excludes inactive model/discovery/extraction/publication lanes; changed collection config still rejected. Owner-only web topology requires no provider credentials: restored its prior absent key, removed our placeholder, and selected existing suspended/dormant staging-harvest as the one-off build/secret donor. Its existing ON_DEMAND key matches the authorized batch key. No cron resume/trigger/schedule change. The two Render failures remain real failures;0paid calls. Full final net224pass/123requiredPG/0skips/errors; headline-independence test red before fix. Retired unclaimed v1 instruction; registered v2 with unchanged13completed scopes/1660Posts/bounds/actual596priorAPI.

- 2026-10-14T04:57:59.645532+00:00 U8 COMPLETE — Verified source4b5f1c54 on staging web/dormant staging-jobs donor and successful separate Renderjobjob-db7gkaaj9qps73cd1ilg; shared job58111a25-7e6a-4f96-893f-142a6c4b58ca/rune474fc1f-b8b4-495c-b2bf-07b20bfedd9c completed13scopes/1660Posts,0additionalAPI/models,239enrichmentcomplete/1421pending. Local/Render identical18duplicateupdates:66.533s→2.171s (30.6x writer speedup), total68.114s→2.847s. Source/body hashes match; live cursor/backlog unchanged. All4PR checks green. Stagingweb has no provider key, stagingharvest stayssuspended, productioncron unchanged. Completion report: [2026-10-14-135759-backfill-render-verification.md](../analysis/harvester/2026-10-14-135759-backfill-render-verification.md). Month/newday/production activation not granted or performed. This operational closeout changes documentation only; deployed application candidate stays4b5f1c54.

- 2026-10-14T05:07:11.589418+00:00 FINAL FAILURE RECEIPT PIN — Mixed valid/out-of-window provider page now retains valid saved Post IDs and actual raw count in its fenced scope envelope while its cursor remains unchanged/blocked. Real PG pin failed on missing recovered ID before repair; final focused109pass/73requiredPG/0skips/errors, alongside still-valid224/123PG regression evidence for unchanged paths. Successful4b5f1c54 adoption/paired timing retained; final source confirmation will use a zero-provider captured-page check, not a fresh date/paid run.

- 2026-10-14T05:26:48.193648+00:00 FINAL SOURCE VERIFIED — fd6f9594 live on staging web/build donor; source-check job-db7gt9k9v7es73c1i610 succeeded,1660IDs reconciled,0API/models,state unchanged. CIall4green. Same18-update timing105.618s outlier; bounded diagnostic job-db7h2ajbc2fs73f6ona0 succeeded at1.714s writer/2.381s total,1.579s SQL(380statements),1.322CPU seconds,106.5MiB peak memory. Outlier unaccounted, no stable full-day/month throughput claimed. Acceptance is frozen and fulfilled; no further new-date/provider/performance batches. Remaining changes are evidence-only closeout.

## U9 — Batch enrichment for month-or-longer recovery [ordinary API transport selected; implementation active]

### Owner requirement and present state

The October 14 owner requires enrichment in batches as part of the backfiller and requires that design to scale to a month or longer.
The earlier collection-only acceptance remains a truthful historical receipt, but no longer establishes an end-to-end complete backfiller.
The owner has authorized implementation and bounded staging model acceptance.
No production import, production release or scheduler activation is authorized.

At the read-only October 14 07:32 UTC comparison, the recovered August 9 cohort contains 1,660 staging posts: 239 have both durable enrichment stages succeeded and 1,421 are incomplete.
Of the incomplete posts, 1,399 have never had an enrichment attempt and 22 have incomplete attempts.
Production contains only five of those recovered IDs; 1,655 are missing, including all 239 with completed staging enrichment.
These are distinct collection, enrichment, and production-presence counts.
The 239 status successes still require persisted-output validation before any broader health-completion claim.

### Required behavior

| ID | Requirement |
| --- | --- |
| BFE-R01 | Normal backfill execution orchestrates collection and enrichment, with explicit collection-only and enrichment-only modes available for operations. |
| BFE-R02 | Enrichment-only execution processes the exact durable recovered cohort and makes zero TwitterAPI calls. |
| BFE-R03 | Translation and classification reuse the harvester's request builders, model routes, validators, artifact writers, and final publisher. |
| BFE-R04 | Resume skips valid completed stages and matching saved translation chunks; changing source, context, model, or prompt invalidates reuse through canonical identity rules. |
| BFE-R05 | Month-or-longer inputs use bounded database reads, request files, imports, and in-flight work; total cohort size cannot require loading every ID or result into memory. |
| BFE-R06 | Database progress survives Render process replacement, including submitted provider jobs whose results are still outstanding. |
| BFE-R07 | Historical queue policy does not expire untouched work because a campaign takes longer than the scheduled harvester's 24-hour enrichment age limit. |
| BFE-R08 | Long posts receive a separate fair allocation and resumable chunk processing, without starving shorter posts or other long posts. |
| BFE-R09 | Physical model requests, reserved and actual spend, retries, and unresolved submission outcomes remain accounted for across restarts. |
| BFE-R10 | Model waits hold no global harvest writer lock or long database transaction; short fenced writes prevent duplicate ownership and stale result publication. |
| BFE-R11 | Retry only unfinished work with bounded transient retries; permanent validation failures remain visible and do not block unrelated eligible posts. |
| BFE-R12 | Report collection, translation, classification, submitted/waiting, retryable, and failed counts separately, plus actual throughput, tokens, and costs. |
| BFE-R13 | Overall success requires collection to drain and required persisted enrichment to validate for the full recovered cohort; outstanding or failed work remains partial. |

Canonical `context_missing` outcomes remain valid when the existing classifier contract permits them.
Do not manufacture a sentiment, force a substantive classification, or weaken validation to turn a failure green.
The old two-hour classifier override does not silently waive the new enrichment requirements.

### Selected approach and tradeoff

The owner explicitly selects ordinary DeepInfra calls on October15 for immediate
staging results, replacing native-only acceptance. Integrate direct execution
into the existing durable enrichment runner with32 configurable concurrent HTTP
requests (maximum128 for this implementation), bounded request waves, and imports
on the controller's database connection. No database transaction spans HTTP.
The existing asynchronous Batch transport remains explicitly selectable for
future background production work. This task grants no production activation.
Both transports must use the same prepared requests and validate/persist returned results through the same shared code.

DeepInfra's [Batch API introduction](https://docs.deepinfra.com/batch/introduction) documents a 20% discount, rate limits separate from real-time inference, a 24-hour completion window, and per-file ceilings of 50,000 requests / 200 MB.
Each file uses one model and one endpoint; a request file is a container of independent model calls, not one enormous prompt.
Its [Batch objects reference](https://docs.deepinfra.com/batch/batch-objects) confirms that expired jobs can still have completed results.
Import validated successes from partial provider jobs and retain unresolved requests as unfinished.
These facts favor cost and background throughput; they do not prove faster August 9 wall-clock completion.
Dependent translation and classification waves can each consume a provider completion window.

Implemented flow:

1. Read a bounded part of the durable recovered cohort and identify genuinely missing stages under the current source/model/prompt identities.
2. Prepare language-detection requests only where needed, copy known source-language text into matching locale fields, and submit only required translations/chunks.
3. Persist provider file/job identities before relying on them for continuation; reconcile ambiguous submissions before paying for a duplicate submission.
4. Import translations through existing validators and artifact/chunk writers, then prepare classification inputs using the now-stored source, translations, context, and affiliations.
5. Submit the existing two classification roles in their established groups of up to 20 posts, preserving exact request profiles and final sibling validation.
6. Publish validated results in short transactions, retry unfinished stages, and reconcile persisted outputs before reporting the overall campaign complete.

The active literal translator deliberately uses isolated post/locale/chunk requests.
Do not combine many translations into a new prompt just to reduce request counts; bulk submission can reduce orchestration overhead without changing that contract.
The classifier deliberately does not reuse a partial role as a completed classification: a failed sibling still requires the canonical paired retry/merge behavior.
Batch size is bounded by requests, bytes, token budgets, and spend, independent of historical date intervals.
Provider preparation/import can proceed in successive windows of work without waiting for an entire multi-month collection to finish.
Use low initial in-flight file counts and grow them only from measured import memory, completion rate, and provider behavior.
No fixed pauses apply to work ready for submission; waiting for an asynchronous provider result and backing off an observed failure are separate states.
Bound each execution and resume from database progress instead of requiring one process to live for the whole campaign.
[Render one-off jobs](https://render.com/docs/one-off-jobs) are terminated after 30 days; the historical data window can be longer than any one execution.
Enrichment needs its own explicit finite allowance and asynchronous deadline; it cannot silently reset collection spend or inherit an already-expired collection deadline.

### Persistence review and implemented file scope

Reuse `PostEnrichmentState` for per-post stage state and existing translation artifacts/chunks and classification state/judgments for model output.
Use shared collection records for collection instructions and recovered-cohort evidence; do not rewrite a truthful successful collection run as a failed enrichment attempt.
G3 selected indexed, typed Post membership on `CollectionObservation`; this
records each actual stored page under its real collection run and scope.
An asynchronous provider submission also needs durable request identity, provider file/batch IDs, import progress, and budget reservations; existing in-memory `BackfillBudget` and Render-local files are insufficient.
G3 subsequently selected one generic ProviderBatch table (adds1, retires0),
with the exact delegated boundary and migration slot recorded below.
Do not create parallel backfill job/run tables or put inference attempts into collection records.

Implemented scope: `monitor/management/commands/backfill.py`,
`monitor/backfill_collection.py`, `monitor/backfill_enrichment.py`,
`core/provider_batches.py`, shared enrichment orchestration in `monitor/cycle.py`,
shared request preparation/validation in `x_monitor/deferred_inference.py`,
`x_monitor/deepinfra_batch.py`, `x_monitor/deepinfra.py`,
`x_monitor/literal_translation.py` and `x_monitor/attribution.py`, and their
real-caller PostgreSQL regression tests. The selected four model sections and
reserved0085 passed G3 adjudication and are applied on staging. Refresh policy,
its runbook/tests, the scoped schema reference and CI are aligned.
The current G3 collection owner supplied the October 14 Batch Enrichment Persistence Recommendation in `docs/analysis/2026-10-13-160815-g3-backfill-collection-interface.md` in the authoritative G3 checkout.
The initial recommendation documented those schema gaps; G3's later selected-design
section supersedes its undecided table choice. Existing observation kinds needed
explicit Post admission and the call owner needed an enforced authored/batch XOR.
Audit purpose-safe generalization of that existing provider-call ledger and its readers/writers; do not create a fake authored-content owner or classify a post as an aggregate to bypass constraints.
The selected implementation covers typed cohort membership, distinct group and
physical request identities, import state, cross-lane duplicate-call prevention,
durable budgets and ambiguous submission recovery.
Preserve scheduled models/prompts, ordinary harvester age/claim policy and seven-call collection path, Post storage, live cursor/backlog rules, existing service inventory, and scheduled/on-demand TwitterAPI credential separation.
Production transfer is a separate task from enrichment and remains unperformed.

### Required proof before calling this complete

The regression net must exercise the real command through shared request preparation, fake provider submission/results, PostgreSQL claims, and final publishers.
Cover zero TwitterAPI calls in enrichment-only mode; skipping complete stages; shuffled/duplicate/partial outputs; missing/invalid classification siblings; source changes while waiting; model/token/spend admission; interrupted submission/import; lease recovery; and no global lock held while awaiting model results.
Exercise 30- and 90-day generated cohorts to prove bounded reads/memory, fair long-post progress, restart survival, and no age-based loss of untouched historical work.
Those are scalability tests, not permission for new paid historical collections.

After implementation, a separately bounded live staging check must include short and long posts, partial translations, and the known classification-conflict case, and verify the exact current model profiles through the selected ordinary API endpoint.
Then finish the existing August 9 incomplete cohort, preserve valid completed outputs, and validate full persisted translation/classification coverage.
Any remaining invalid or exhausted work keeps the live result partial; a green Render exit or a provider `completed` status cannot substitute for that database proof.
Publish measured posts/requests per minute, tokens/spend per post, peak Render memory, and import rate before estimating a full month.

- 2026-10-14T16:51:56+09:00 REQUIREMENTS REOPENED — Owner requires integrated batch enrichment and month-or-longer scale. Current application remains collection-complete/enrichment-incomplete. Record provider-batch/direct-mode proposal, shared-code/storage review, and exact-cohort completion proof in this same plan; no application, model, database, scheduler, Git delivery, or production mutation.

### Next implementation and August 9 verification sequence

#### Selected design, authority and implementation claim — October 14

The owner authorizes implementation and staging acceptance ("go"), paid LLM
requests with accounting, zero TwitterAPI calls, and protection against server
limits. This continues the selected staging endpoint; no production transfer,
production release, scheduler activation or new collection window is authorized.
G3 selects one `ProviderBatch` table (adds one, retires zero) in its authoritative
`docs/analysis/2026-10-13-160815-g3-backfill-collection-interface.md` handoff.
This group execution record owns real external files/submission/poll/import state,
which neither one model request nor source collection can represent correctly.
Reuse `OriginalContentCall` for model reservations/results with exactly one owner
(authored run or provider batch), bounded actual Post members and import evidence;
extend `CollectionObservation` with typed Post membership and preserve all numeric
constraints; add historical provenance to `PostEnrichmentState`. Collection
outcomes remain immutable. No synthetic collection run or authored owner.

Active bounded ownership: this branch owns only the `ProviderBatch`,
`OriginalContentCall`, `CollectionObservation`, and `PostEnrichmentState` model
sections; `0085_provider_batch_enrichment` depending on existing0082; one generic
batch persistence helper and PostgreSQL tests; and its existing shared transport,
request preparation, cycle/backfill adapters, CLI and real-caller tests. G3 owns
design review and later account integration. Account sections and migrations0083/
0084 and shared collection lifecycle/scheduler policy are excluded. Send exact
diff and required PostgreSQL evidence to G3 before staging DDL or paid acceptance.

Prepare and replay the existing literal translator and fixed-slot classifier
through a deferred client; preserve prompts/models/validators and publishers.
Preparation transactions roll back when replies are outstanding. Persist request
intents outside them, upload homogeneous bounded model files, wait without any
collection/Post lease, stream responses into exact request identities, then replay
validated results through the same publishers. Translation dependencies precede
classifier evidence; completed stages are skipped. Partial/error/ambiguous states
retain reservations, require reconciliation and never count as success.

Resource contract: maximum2000 requests and16MiB per file, one active file per
model for this campaign, imports bounded to100 Posts, short fenced database leases,
minimum60-second polls with Retry-After and increasing delay on retryable failures.
Preparation/replay performs no network calls or fixed request sleeps. Campaign
admission ceilings include all retained request reservations: USD5 for the100-Post
pilot and USD25 for the entire day,20000 model requests and5000 control requests;
no automatic increases. Reserve conservative UTF-8-byte input/output-token cost
at current standard prices before each physical attempt; record provider cost
when supplied and label calculated or missing costs explicitly. Native pricing
discount may lower observed cost but is not assumed for admission. Pilot deadline
72hours accounts for dependent24-hour Batch waves, with finite3physical attempts
per input identity; missing/invalid work remains partial on exhaustion. A timeout
or uncertain POST is reconciled before another send. No blind retries.

General campaign allowances/deadlines are explicit configurable inputs for later
month-or-longer jobs; defaults do not reset on restart. This authorized live day
keeps its USD5pilot/USD25whole-day,20000model/5000control ceilings and72-hour
deadline. Larger generic input bounds do not grant a new paid month campaign.
The source-job database-name/role pin is checked before any write or HTTP.

2026-10-14T19:35:00+09:00 IMPLEMENTATION — Native preparation/submission/restart/
import uses shared translator/classifier validators/publishers. Required isolated
PG net37pass/0skips/errors plus33provider/caller units; populated0085-first and
accounts-first graph proofs preserve authored calls/Post and refuse reverse with
new evidence (PG17.9). Staging census is read-only PG18.4/0082:1660recovered,
1421flag-incomplete,239flag-complete,198persisted-valid. All41false successes have
only1brand state against2–6current brands; one also lacks a current complete
literal artifact. Initial/pilot-expansion and collection-page auditing reopen
only invalid stages, retain valid translations/judgment history and source
collection success, and protect all untouched historical pending rows from live
expiry. Frozen100incomplete+10genuine controls include all22previous attempts,
knownconflict,10long posts and32declared-language buckets. No paid models/X yet.
Additional bounded file ownership: shared artifact-completeness adapter and
existing backfill CI workflow; no UI/browser routes affected.

2026-10-14T20:30:00+09:00 LOCAL VERIFICATION — Broad450pass/187requiredPG with0
skips/errors; fresh61pass/28requiredPG cover final native/ledger/realHTTP source.
Source mutation between preview and reservation is refused before any network;
actual HTTP admission callback ABI exercised by the real native transport.
Database defaults for member IDs/import state/import evidence allow older authored
writers to insert during additive deployment (red before fix, green afterward).
Both populated migration orders and reverse refusal pass again after that fix.
Inline review/simplification per AGENTS tool mapping complete; no open local
finding. External Claude CLI resolved through MiniMax/non-project credential,
received402 insufficient balance, and produced no review; request should have
been blocked by provider/credential discovery. No retry or account configuration
change; adversarial review completed inline, no independent promotion claimed.
Production checker ran exactly twice on the same20IDs30minutes apart: both
unhealthy on existing deployed code. This is baseline evidence, not a candidate
production health pass. Candidate remains stage-only. Exact diff and PG proof
sent to G3; schema adjudication and native paid pilot/full-cohort proof pending.

2026-10-14T20:54:00+09:00 G3 REVIEW — shared-slice adjudication returned no
blocking findings. Its receipt is in G3's authoritative collection checkout at
`docs/analysis/2026-10-14-203948-g3-provider-batch-shared-review.md`;78unique checks,
62requiredPG, concurrent overlap/invalid200 recovery probes and both populated
migration orders. Native/shared sources stayed unchanged through the subsequent
refresh-policy repair. That repair passes120checks/6requiredPG; source-reader
access remains MAINTAIN-only for excluded batch records. Hosted CI also exposed
the schema reference omission; the scoped reference now has151tables/1975columns,
all34batch fields and six added fields on existing entities. No stagedDDL or paid
models yet. Actual stage remains0082; PR60 must coordinate before accountDDL.

2026-10-14T21:21:00+09:00 LIVE NATIVE ACCEPTANCE — all five hosted checks passed
exact candidate54afc330; that unchanged revision is observed live on staging web
and jobs donor. Actual stage0082+0085 has34batch columns, expected owner checks/
indexes and old-writer defaults. Source1660, cursors/backlog and authored23 call
hashes match the pre-migration baseline. A real old authored INSERT omitting new
columns passes, rolled back without sequence advance. Staging web returns302.
Only the donor received projectDeepInfra key and literal-v2 flag; web stays
provider-free, cron schedules/suspension and production remain untouched.

Native job01/job-db7n162j9qps73d1gcbg submitted317Gemma translation/detection
requests, reservingUSD0.313038;28.507active wall seconds/3.937CPU/168.11MiB peak.
Native job02/job-db7n2dt9fdbs73er0crg recovered the same group in a separate
process: no repeated submission,317sent,3control requests,5.416active wall/
1.404CPU/169.81MiB peak. Both processes exited successfully but the pilot remains
PARTIAL: providervalidating,0returned results,100incomplete+10completecontrols,
0TwitterAPI. No live Post claims remain during provider wait. Unknown billed
cost is retained, not reported as zero. Public provider caps50krequests/200MB/
100concurrent batches; this account had0existing batches at preflight. Actual
Render plan-crn-003 is0.5CPU/512MB; observed process peaks remain below it.

Deadline-bounded Render acceptance controller job-db7n5prbc2fs73fptl1g follows
the same pinned110selection and policy; waits close all database connections.
It calls the existing execute/import/publish/verification helpers, only expands
via finish_pilot after110persisted outputs pass, retains all charges and the
original72-hour deadline, then requires1660valid outputs underUSD25. Model/
control/attempt/file ceilings are unchanged. This private verification program
does not create another job table or activate a scheduler. First advance keeps
the same317requests/USD0.313038,4controls,169.18MiB; waiting on real provider
results. Live native pilot and full-day acceptance are not yet passed.

2026-10-14T21:42:00+09:00 SCALE REPAIR — completed-source adoption loaded the
entire compatibility receipt and rejected more than100000IDs, even when typed
membership already existed. New X reports certify exact typed job membership
across genuine attempts with a scalar version/count after reconciliation; native
resume selects only source identity/status/purpose and that scalar, validates
SQL DISTINCT membership count, and retains bounded legacy adoption for old
reports. Red tests catch whole-Report selection and the misplaced legacy cap;
final43checks/43requiredPG/0skips pass, including oversized unused receipt,
changed-count refusal, real page certification and interrupted-attempt resumption.
Focused Ruff/whitespace pass. Exact delta sent to G3; no schema/cost/model change.
Running Render54afc330/controller remains unchanged; this follow-up is not yet
deployed. Latest live result8controls,317sent/0returned,USD0.313038reserved,
170.82MiB peak; native acceptance remains PARTIAL awaiting provider results.

2026-10-14T21:45:00+09:00 G3 SCALE ADJUDICATION — no blocking findings;
33additional required PostgreSQL checks executed by G3 with0skips/errors.
Native typed resume avoids receipt materialization; collection reporting and
legacy fallback still materialize IDs. The100001-entry test proves projection/
guard behavior, not a100kunique-Post throughput or writer-memory benchmark.
Preserve this limit in later month estimates. Approved follow-up is published
on the feature branch with fresh CI; active paid pilot/controller remains on
54afc330 and is not yet passed. No new collection or production action.

2026-10-14T18:21:56+09:00 ON — implementing the G3-selected persistence slice and
native batch orchestration. Transport/shared callers tested;178 focused checks
executed on isolated PostgreSQL (34 required database checks, zero skips/errors).
One read-only provider control preflight, zero model requests, zero TwitterAPI.

The owner's next-step question identifies the already-collected August 9 UTC day as the appropriate enrichment test data.
Use its existing staging collection job `58111a25-7e6a-4f96-893f-142a6c4b58ca` and exact recovered cohort; the 24 hours describes post creation dates, not a required worker runtime.
The implemented asynchronous runner must exercise native provider batches;
invoking the old collection-only batch is not this test.

1. Finalize the focused persistence proposal with G3: audit existing provider-call owners/readers/writers, indexed post membership, outstanding-request exclusion, durable reservations, and recovery after ambiguous provider acceptance. Implement only the selected shared extension; keep PR60 account work and migration numbering coordinated.
2. Extract shared request preparation/response validation as needed, implement resumable provider submission/import and enrichment-only orchestration, and preserve the scheduled caller's models, profiles, semantics, and resource defaults.
3. Run the real-caller PostgreSQL regression net, including pending work older than 24 hours, asynchronous results outliving a post lease, paired classifier failures, interruption/restart, and generated 30-/90-day cohorts.
4. Refresh the August 9 cohort's states and freeze 100 incomplete posts for the first live check. Include all 22 previously attempted incomplete posts from the planning snapshot where still eligible, the known classifier-conflict case, and a representative mix of languages and short/long posts. Add 10 genuinely complete posts as controls that must incur zero new model calls.
5. Before sending, freeze the deployed revision, model/prompt/request identities, exact selected IDs, finite request/token/spend allowance and a deadline suitable for asynchronous provider completion. Derive the request ceiling from missing locale/chunk/detection work and paired classification calls; retain prior spend and ambiguous reservations. Verify actual staging/database identity and required role credentials without exposing their values.
6. Exercise the native Batch endpoint and restart while results are outstanding, then reconcile validated outputs for the selected posts. Require no duplicate model submission, no TwitterAPI calls, no unrelated-post changes, preserved valid control outputs, and unchanged harvest cursor/backlog state. Keep direct-mode checks distinct; a passing direct-only test cannot prove provider-batch behavior.
7. If the native-batch sample succeeds, resume the remaining incomplete August 9 posts without reprocessing the successful sample or valid completed stages. Reconcile all 1,660 recovered posts and validate their required persisted outputs. A sample failure keeps the rollout partial until its cause is repaired; do not silently waive the conflict or increase retry/spend limits.

Report model request count, tokens and actual/unknown cost, provider wait time versus active preparation/import time, posts per minute, peak Render memory and database import rate.
Use those observations for day/week/month estimates only after separating fixed startup/wait overhead from volume-dependent work.
The first live check and full-cohort continuation remain staging work; neither step copies posts to production or collects a new historical window.

2026-10-14T22:27:00+09:00 OWNER CANCEL / INSPECT / RERUN — owner rejects the
317-request validating stall and explicitly authorizes cancellation, inspection
and rerun. Render controller job-db7n5prbc2fs73fptl1g is confirmed cancelled at
13:22:13UTC. Provider POST cancellation was accepted at13:23:40UTC; initial
inspection remains cancelling, with no errors/counts/usage/results or processing
start. The retrieved0.967MB input matches all317durable canonical packets exactly;
unique identities, one Gemma model and matching endpoint/method verified. Do not
invent a provider-side cause or call this pilot passed. Count all control starts
and retain317sent/unknown charges/USD0.313038reservation/originalUSD5/25/72h bounds.
After terminal cancellation and reconciliation, rerun one existing canonical
request as a native diagnostic batch before re-admitting the full selection.
No direct fallback, new collection, source/schema/production/cron changes. Source
54afc330 remains pinned for runtime; reviewed9b66c5e6 stays feature-only.

2026-10-14T22:46:00+09:00 INSPECTION / BOUNDED RECOVERY — one separately recorded
direct diagnostic uses the exact original Gemma request body and succeeds in
4.052seconds,206input/2output tokens, provider-reported estimateUSD0.000019;
USD0.000179reserved. This is a comparison call, not a completed Post/pilot or
native proof. Totals318model starts/USD0.313217reserved; original317costs remain
unknown. Actual source report, cursors/backlog, outside-pilotPost fields and10
valid controls are unchanged;0control model calls and0livePostclaims.16transport
checks pass. The12-minute local cancellation watch ends with provider still
cancelling, and submits0replacement requests. No invented app fix or provider
root cause: the same body works directly; the stall is in the provider batch path.

Prepare one Render recovery continuation at the same54afc330, reusing the
existing claim/control/reservation/import/strict-parser/execute/finish helpers.
Wait at most30minutes for terminal old cancellation, polling every5minutes
without live database connections or Post claims. Import actual terminal outputs
before admitting exactly1failed original request; retain all prior charges and
original deadline/limits. Cancel that native diagnostic if still outstanding
after10minutes and stop without a full retry. A strict valid reply permits the
existing110pilot/full1660continuation; later native validating groups stop with
cancellation after15minutes without results. Native queue behavior is not an
acceptance waiver. Private flow harness verifies: stuck cancellation sends0new
models; stuck probe sends1and cancels; successful probe hands off with1submission.
Owner was offered normalAPI/fourparallel versus tiny native retry as an optional
route preference; no reply yet. Preserve the existing native contract while that
choice remains pending. No source/schema/production/cron mutation.

2026-10-14T22:49:00+09:00 RECOVERY RUNNING — donor remains observed live54afc330;
guarded Render job-db7og8uk1f9s738fmm2g started13:48:19UTC onplan-crn-003 and is
running. The prior job is cancelled. Actual old provider cancellation is still
pending; no new native submission or full enrichment rerun has occurred yet.
Its limits and guarded sequence above are explicit; no full/native success is
claimed from the normal diagnostic or the new job's running state.

2026-10-14T23:20:00+09:00 RECOVERY STOPPED / EXTERNAL BLOCKER — guarded job
job-db7og8uk1f9s738fmm2g exits failed14:18:52UTC at its30-minute guard with
`cancellation_pending_after_bounded_wait_no_replacement_submitted`. Logs contain
no replacement submission. Latest provider receipt remains cancelling without
counts/usage/results; actual stage14:19:47UTC ledger retains317original sent/
pending calls and1completed direct diagnostic,37counted controlHTTP,USD0.313217
reserved/USD0.000019provider estimate/317unknown costs,100pending pilot posts.
No owned Render controller remains running. No retry/budget reset, direct full
fallback or acceptance waiver is applied. Cancellation acknowledgment is not
terminal-cancellation proof, and a failed guard is not a successful rerun.
Provider finalization is needed for the existing native rerun; optional normal
API/fourparallel route preference remains unanswered. Existing authorization
and staging cohort/schema ownership persist; no production changes/imports.

2026-10-15T05:52:00+09:00 PROVIDER FINALIZATION OBSERVED — owner asks for best
guess; one counted status GET at20:48:54UTC confirms remote cancelled. Actual
provider timestamps: created12:08:51UTC, cancel requested13:23:40UTC, cancelled
14:14:04UTC (50minutes24seconds after request), with no processing-start, request
counts, model, usage or output/error files. The previous recovery's last GET was
14:14:00.529UTC, approximately3.5seconds before finalization; it then stopped at
14:18:52UTC without a final GET. Earlier pending statements describe the last
received state, not the provider's actual state at that later stop.

Best-supported inference is a delayed/stalled provider batch validation queue;
the exact internal cause remains unknown. Initial75-minute wait alone does not
establish provider failure: DeepInfra documents a24-hour batch window. One
working direct request does not prove all317individual requests are accepted.
Repair only the private recovery watcher to recheck status at the cancellation
deadline;4fake-control-flow cases pass, including finalization between the last
interval poll and deadline. No application/schema/model/prompt changes. Confirmed
final cancellation removes the external prerequisite for the already-authorized
one-original-request native rerun, still on frozen54afc330 with unchanged
source/control/financial/deadline guards. No new full cohort, normal-API fallback,
TwitterAPI or production authority is inferred from the owner's question.

2026-10-15T06:28:00+09:00 FIRECRAWL CONTRACT AUDIT — owner explicitly invokes
Firecrawl for the provider docs.11credits used (308to297), at most2concurrent
operations: official Batch introduction/endpoints/objects, Files API, Chat
overview/reference, account rate limits and reasoning; one model API page,
one old-rate-route404 and one URL map. Cache is ignored under.firecrawl/. No
paid inference experiment is added by this documentation audit; the already
authorized native continuation is independent.

Required wire contract matches our caller and retrieved uploaded data: JSONL
unique custom IDs, POST, matching/v1/chat/completions, one model/file, upload
purpose=batch, persisted input_file_id and completion_window=24h, allowed
metadata key/value lengths. No file-ready wait or special batch credential is
required by the docs. Optional input/output expiry parameters default30days;
omitting them does not prevent execution. Current translation max_tokens<=4291
and classifier4096 are below the documented typical16384cap; DeepSeek0731
reasoning_effort=none is explicitly documented and correctly supplied. Batch
limits50krequests/200MB/100concurrent files are distinct from standard200concurrent
requests/model. The generic account page's"batch jobs" advice is for bulk ordinary
requests; use the specific native Batch contract for native File/Batch calls.

Remaining gaps / required follow-ups before claiming month-scale completeness:

- Timing:24-hour provider completion window means our10/15-minute test watchdogs
  are chosen operator stop limits, not documented API failure thresholds. Model,
  counts and usage can be null while validating. Initial75-minute wait alone
  did not prove an outage. Warn/recheck provider state before a timeout decision;
  the private cancellation deadline recheck is fixed, the later short native
  validation guard remains a separate chosen test bound.
- Diagnostics: persist bounded provider errors(code/line/param/message), request
  counts, aggregate usage and transition timestamps. Current code retains status,
  final child responses/usage and generic errors, but loses rich parent polling
  metadata and per-line failure details. Reuse existing ProviderBatch.control_evidence
  and OriginalContentCall.import_evidence/response records; no new table is proposed.
- File resources: provider account cap is2GBtotal including response files, not
  just200MBperfile. Default30-day retention can accumulate multiple historical
  months collected in one week. Check account occupancy, shorten deliberate
  retention or clean only our fully imported/reconciled files; preserve other
  jobs/apps and files needed for uncertain submissions or partial-result recovery.
- Cancellation/expiration: asynchronous termination can retain partial outputs;
  import both success/error files before retry. Existing importer handles both;
  operator cancellation currently uses the private transport rather than a
  first-class management-command path. Cancellation50m24s is observed latency,
  not a documented normal/failure limit. Keep all unknown charges reserved.

Primary evidence: https://docs.deepinfra.com/batch/introduction ;
https://docs.deepinfra.com/batch/batch-endpoints ;
https://docs.deepinfra.com/batch/batch-objects ;
https://docs.deepinfra.com/batch/file-endpoints ;
https://docs.deepinfra.com/chat/overview ;
https://docs.deepinfra.com/chat/reasoning ;
https://docs.deepinfra.com/account/rate-limits .

Native rerun actual observations:1request groupa7f81a20 completes at20:56:50UTC
(about3minutes observed), then319request group9b3b4480 completes at21:03:36UTC
(about6m36s observed), followed by8Gemma requests completing21:09:59UTC. All296
distinct original request bodies have a successful native counterpart across
the tiny and large reruns; this is strong evidence against a missing required
field or malformed original body. Initial provider queue/validation delay is
the strongest remaining inference, not a confirmed internal root cause.
DeepSeek's6classification requests were in_progress with0completed/0failed and
zero aggregate usage at21:19UTC; no hidden reasoning-setting error found in docs.
Pilot/full1660persisted acceptance remains pending. At21:14UTC:652submitted,
329responses(1direct diagnostic,328native translation),USD0.702825reserved/
USD0.063314provider estimates,317original unknown charges retained,0TwitterAPI.
Runtime remains frozen54afc330/job-db7une3l550s73df711g, originalUSD5/25/72h bounds;
no app/schema/production/cron change or new historical collection.

2026-10-15T06:39:00+09:00 AUDIT CLOSEOUT / LIVE LIMIT — docs audit complete;
remaining diagnostics, cancellation-command/file housekeeping follow-ups are
identified, not implemented or waived. At21:36:51UTC actual stage still reports
652submitted/329responses,100pending pilot posts,1active DeepSeek6-request group
in_progress;USD0.702825reserved/USD0.063314provider estimates. The pilot is not
passed. Source/group schema/caller code remains54afc330, no additional model
experiment, TwitterAPI or production mutation. Guarded v2controller continues
under retained ownership; native body/transport proof is distinct from full
persisted translation/classification completion.


2026-10-15T07:25:14+09:00 DIRECT IMPLEMENTATION — Owner selects normal DeepInfra API for immediate staging results; native Batch retained for future selection. Old controller job-db7une3l550s73df711g is observed cancelled22:11:38UTC. Six-request classifier group is now provider-cancelled and reconciled through the shared importer (six error replies, no successes); all prior reservations/deadline preserved. G3 confirms no overlapping edits and no schema changes needed.

Implementation uses existing ProviderBatch transport=direct, existing call admission/fences/importer and exact shared CycleRunner replay. HTTP-only threads send at most32 calls by default (configurable1–128); one bounded wave/model advances at a time, no DB transaction spans HTTP, successful waves have no fixed sleep. Reserved calls resume; interrupted sent/unknown calls remain ambiguous and are never automatically resubmitted. Explicit429/5xx receipts back off30s and retain reservations; original3-attempt cap remains. Native cached replies keep their logical identities and report their actual transport; controls cannot incur calls.

Verification: initial two direct tests fail before implementation at missing transport wiring. After implementation the broad focused suite passes118checks, including49required PostgreSQL checks with0skips/errors. Final eight direct PostgreSQL checks pass with0skips/errors and cover real command/publishers,32 simultaneous HTTP starts with no worker DB connections, admission before HTTP, read-only status, native-reply reuse, unknown-response resume,429 backoff and spending refusal. The earlier timeout test incorrectly rejected legitimate unstarted reservations; corrected it to allow those once while asserting unknown sent requests are never repeated. Inline reuse, quality, efficiency and risk review follows the repository sequential tool mapping; no independent cross-model receipt is claimed. No live normal enrichment calls yet; staging pilot/day acceptance remains pending.


2026-10-15T07:31:29+09:00 DIRECT STAGING DELIVERY — Candidate5d0637eef129830d235f36fd4b198278134b4485 is verified remotely on feature/staging refs and observed live on webdep-db803nss728c73fhuhrg and donordep-db803o4s728c73fhuj5g. Login responds200. Web replacement dropped only our read-only SSH tunnel; restored that owned tunnel without changes to service/network settings. Source/control/outside-pilot/cursor/backlog proof remains intact and no Post claim is active. PR58 now conflicts with independently merged G3 main9cad8f6b, preventing automatic pull-request workflows. Explicit Historical X backfill workflow_dispatch38647979206 tests this exact feature candidate; integration conflict/0086 remains separate G3-owned delivery work. No production merge and no normal enrichment model start yet.


2026-10-15T07:35:10+09:00 DIRECT LIVE START — Hosted workflow38647979206 is observed success for exact5d0637ee:426passed/199requiredPG,0skips/errors, full backfill and scheduled-path net plus lint. One ordinary-only Render controller job-db806pij9qps73b4v700 created22:34:14UTC on owned donor/plan-crn-003. Frozen100incomplete+10controls, knownconflict, originalbudgets/deadline and exactsource revision retained. Normal waves allow32 in flight;328native translation replies reused through canonical identities. Success requires110 persisted pilot outputs before expansion to1660; controller stops on unknown model outcomes or no-progress rather than silently retrying. No TwitterAPI or production calls.


2026-10-15T07:55:05+09:00 PILOT REPAIR — Direct job-db806pij9qps73b4v700 failed22:36:05UTC at no-progress guard after6successful normal classifier replies (USD0.025156 estimate), with0timeouts/429 and peak189.16MiB. No pilot success is claimed. Actual replay diagnosis job-db80bj0m7kps73chn48g sends0models and proves4classifier intents suppressed for missing English in two posts; all100Post writes roll back despite43valid interim assessments. Saved source-copy validator wrongly counts bareHF repository/safetensors identifiers and short versioned product lists as prose;3of328translation replies rejected. Narrow shared guard correction passes original copy/quantity tests and real translation call-chain examples, preserving ordinary narrative rejection. Read-only revalidation now accepts328/328retained replies; all6normal responses parse successfully.

Add canonical cached-response validation before replay and persist rejection evidence outside the Post rollback so genuine invalid replies can retry individually, retaining raw response/cost/history. Direct preparation stops after discovering the next bounded request group instead of scanning2000intents for a32-call wave. Local99checks/39requiredPG and cache29requiredPG pass0skips/errors; pin transition and live acceptance still pending. G3 approves a guard-specific audited processing-policy transition with expected old/new hashes, actor/revision/reason/time, unchanged models/prompts/request bodies/budgets/deadline and preserved original call configuration identity. Do not weaken the general configuration-pin gate; no schema change/new tables/production activation.
