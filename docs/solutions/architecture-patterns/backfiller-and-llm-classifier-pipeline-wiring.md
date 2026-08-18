---
module: harvest
date: 2026-07-24
problem_type: architecture_pattern
component: service_object
severity: high
last_updated: 2026-08-17
applies_when:
  - "Recovering a historical date range through the current harvester"
  - "Building a resumable data tool that must share a production pipeline"
  - "Adding provider and LLM cost ceilings to historical processing"
symptoms:
  - "Deployment or token exhaustion left historical collection gaps"
  - "A long range contains obvious downtime but should not be fetched wholesale"
  - "Historical work must survive process and Render instance replacement"
root_cause: incomplete_setup
resolution_type: tooling_addition
related_components:
  - background_job
  - tooling
tags:
  - backfiller
  - llm-classifier
  - harvest-cycle
  - cycle-runner
  - django-management-command
  - data-pipeline
  - render-deploy
---

# Backfiller: share the pipeline, isolate ownership

## Context

Historical recovery has different cursor and scheduling semantics from the
15-minute harvest, but it must not become a second fetch pipeline. A safe
backfiller needs current call planning and attribution behavior while retaining
durable, independently claimable historical work.

The current implementation uses `BackfillJob` plus job-owned
`HarvestBacklogWindow` rows. The scheduled backlog uses the same table with a
null job. Manager methods default to scheduled rows, and recovery supplies one
exact job scope, preventing either side from consuming the other's coverage.

## Pattern

Keep the management command thin:

1. Parse and validate a historical half-open UTC range.
2. Optionally infer conservative zero-post gaps from fully elapsed buckets.
3. Expand selected intervals through `plan_calls_for_cycle()`.
4. Store the current complete call identities and a query-plan signature.
5. Replay one job row through `CycleRunner` with a one-page, 20-result cap.
6. Complete, narrow, return, or quarantine the durable row according to the
   shared replay outcome.

The command never sets global time-window settings and never reads or updates
`CallState`. Scheduled cursor ownership remains unchanged.

### Why PostgreSQL owns progress

Local JSON is not a durable checkpoint on Render. A deterministic job key and
database-owned work rows allow a later process to resume the same range. The
job key includes range, selection mode, thresholds, and brand filter. The plan
signature includes the effective query strings and complete call identities.
Resume rejects plan drift before provider spend.

Completed job rows are retained for audit. Scheduled replay preserves its
existing delete-on-success behavior.

### Selectivity and its limit

Automatic mode buckets `Post.created_at` and selects only consecutive buckets
with zero posts at or above the configured threshold. One post suppresses the
entire bucket. This makes automatic selection conservative and cost-aware, but
it cannot identify a partial outage. The explicit range mode is authoritative
for known downtime with sparse surviving posts.

### Request and lock boundaries

Each job replay is exactly one TwitterAPI advanced-search page with at most 20
returned tweets. `--batch-size` therefore maps directly to the maximum provider
HTTP attempts in one invocation: transport-level TwitterAPI retries are
disabled because the durable row is the retry boundary. A truncated result
narrows the remaining upper bound to one second after the oldest returned tweet
and leaves the row pending.

The command acquires the shared PostgreSQL advisory writer lock for one replay
step and releases it before pausing. Job replay, scheduled quarantined replay,
and exact-job reset all use this ownership seam. Contention is deferred work,
not a failed or completed range.

Quarantined recovery rows are fail-closed: ordinary resume does not claim them.
After the provider issue is repaired, `--retry-quarantined` makes only the exact
matching job's quarantined rows eligible. Scheduled quarantined debt remains a
separate `--quarantined` workflow, and incompatible job-selection flags are
rejected before provider setup.

Second-precision time sliding has one known provider-bound limit. If more than
20 matching tweets share the oldest returned timestamp, the next upper bound
may not expose the remaining same-second results. The row reaches the existing
attempt ceiling and quarantines instead of falsely completing.

### LLM cost ownership

One shared pre-call counter covers relevance, translation, classification,
LLM-client retries, language repair, and per-post classifier fallback. The
budgeted client consumes immediately before `messages_create`. Budget
exhaustion is re-raised through helper retry loops so it cannot cause another
retry or be mistaken for a provider failure; durable enrichment remains
pending.

Models and endpoints are explicit per role in `config.yaml`. The production
caller passes the relevance model, translator config, classifier model, and
role-specific clients. Ambient defaults cannot silently redirect one role to
another endpoint.

## Operational consequences

- Dry-run and status make no provider calls and no writes.
- Cost preview uses the repository TwitterAPI pricing loader. Missing or
  unparsable pricing stops before job creation.
- Backfill skips one-shot metrics refresh and trend-headline dispatch.
- Tweet-ID upsert remains the data deduplication boundary.
- Scheduled and job replay keep the existing attempt, age, deadline, and
  enrichment claim ceilings; no new concurrency is added.
- A job is complete only after every owned work row is completed.

Copyable workflows and state meanings live in
`docs/operations/backfill.md`.
