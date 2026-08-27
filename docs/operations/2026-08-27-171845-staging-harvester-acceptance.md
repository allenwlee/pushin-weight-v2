# Staging harvester acceptance

Created: 2026-08-27. Delivery target: production, with staging-first gates.

This record is both the runbook and the evidence template for one bounded live
staging attempt. It does not independently authorize a production deploy;
production authority and exact-SHA promotion gates live in the annotated Ollija
plan. It never authorizes a production cron pause, schedule change, Blueprint
application, manual data mutation, or replay of an earlier production gap.

## Ownership and fixed limits

Staging owns `pushinweight-staging-db`, its `call_state` cursors,
`harvest_backlog_windows`, `post_enrichment_states`, list-sync state, headline
runs/work slots/provider ledgers/visible pointers, and
`pushinweight-staging-headlines-broker`. Production owns a disjoint copy of
each. The external TwitterAPI.io/provider account and quota remain shared.

One Trigger Run is fixed at one configured call, one logical/physical search
attempt, one page, five returned/persisted posts, no HTTP retries, and no
metrics refresh. Its enrichment profile is aggregate/current/carryover
`5/5/0`: up to five newly inserted current-cycle rows and no carryover rows.
The lanes cannot borrow capacity. Operators may not bypass the profile with
plain `python manage.py run_cycle`.

## One-time Render setup

Apply only `render-staging.yaml` to the staging Blueprint. Confirm the stage
branch and names exactly match the ownership table in `docs/deploy/render.md`.
Do not apply `render.yaml`, suspend `pushinweight-harvest`, or change its
`*/15 * * * *` schedule.

Configure service-scoped secrets in the Render Dashboard without printing or
copying their values into a terminal transcript:

- harvester: `TWITTERAPI_IO_API_KEY` plus the credentials selected by the
  effective translator/classifier URLs (`ANTHROPIC_API_KEY`,
  `MINIMAX_API_TOKEN`, or `DEEPSEEK_API_KEY`);
- headline worker: `DEEPSEEK_API_KEY`;
- staging web: `STAGING_REFRESH_SOURCE_DATABASE_URL` only for refresh.

Do not link the broad production secret group. A distinct revocable provider
key is preferred, but it still consumes the shared account quota.

## Pre-trigger stop gates

Stop at the first failed gate. Do not Trigger Run and do not try a plain
command as a workaround.

1. Run `./bin/ollija annotate-plan <plan-path> --check`; confirm the recorded
   target matches the owner's current selection and the candidate
   worktree/branch are canonical. A production target still requires every
   staging-first gate in the generated guide.
2. Confirm the exact candidate SHA locally with `git rev-parse HEAD` and on
   staging with `printenv RENDER_GIT_COMMIT`. Record both; they must match.
3. Confirm `printenv RENDER_SERVICE_NAME` is
   `pushinweight-staging-harvest` and
   `printenv X_MONITOR_DEPLOYMENT_ENVIRONMENT` is `staging`.
4. Confirm the cron schedule remains `0 0 31 2 *` and no prior manual run is
   active.
5. Confirm the staging refresh receipt and zero-state census have passed, the
   staging worker is running the same candidate SHA, and its owned queue is
   empty before the attempt.
6. Confirm the owner explicitly authorizes exactly one Twitter search attempt
   returning at most five shared-quota results now. Provider dashboards, not
   old marketing limits, are quota evidence.
7. Run `python manage.py headline_status --json` on staging and compare it to
   the candidate `config.yaml`. Confirm the owner separately authorizes the
   headline-provider envelope: per brand, at most 25 calls, 500,000 input
   tokens, 160,000 output tokens, and USD 1.00 at pricing revision
   `deepseek-v4-pro-peak-2026-08-27`, across at most 25 expected brands. Stop if
   the effective controls or provider dashboard do not fit that authorization.

Read the live database identity independently from a shell on each of
`pushinweight-staging-web`, `pushinweight-staging-harvest`, and
`pushinweight-staging-headlines`, without printing `DATABASE_URL`:

```sql
SELECT current_database(), current_user, inet_server_addr(), inet_server_port();
```

All three services must report database/role
`pushinweight_staging` / `pushinweight_staging`. The harvester's structured
acceptance output is a second identity proof for that service. The internal
host on each service must match the tracked staging refresh target and must not
match a production-deny host. A match on only one service is not sufficient.

## Manual Trigger Run

In the Render Dashboard open `pushinweight-staging-harvest`, verify the start
command contains `--staging-acceptance` and the selected non-secret call value
is `A`, then choose **Trigger Run** once. Do not trigger again after an empty,
filtered, rate-limited, or failed result.

Capture only the command's structured JSON. It must report all caps, the stage
service/environment/database identity, selected call, safe totals, selected
call outcome, enrichment claim count, and headline dispatch status. It must
not contain a URL, query payload, credential, or provider response body.

Interpret the top-level status literally:

- `accepted`: one through five posts were newly inserted, the inserted IDs are
  exactly the current-cycle claimed IDs, carryover is empty, and every inserted
  ID is terminal-complete with valid persisted output;
- `inconclusive`: a safe zero-result, update-only, or still-pending outcome;
  there is no automatic retry and it cannot authorize production;
- `failed`: an identity, cap, provider, pipeline, carryover, terminal-stage,
  output-validity, or exact-ID mismatch; there is no retry and it cannot
  authorize production.

An accepted command result is necessary but not sufficient. Read-only staging
database and feed observations must also prove that every inserted ID was
hidden before terminal success and is visible after terminal success. The
existing 60-second feed refresh may be driven once without waiting a wall-clock
minute. A pending, failed, or incomplete row appearing in the feed fails.

## Staging acceptance evidence

Fill every field; use `unknown` rather than inference.

```text
candidate_sha_local:
RENDER_GIT_COMMIT_web:
RENDER_GIT_COMMIT_harvester:
RENDER_GIT_COMMIT_worker:
web_service_name:
harvester_service_name:
worker_service_name:
database_name_web:
database_role_web:
database_name_harvester:
database_role_harvester:
database_name_worker:
database_role_worker:
broker_resource_name:
selected_call:
twitter_budget_authorized_at_utc:
headline_budget_authorized_at_utc:
headline_per_brand_call_cap: 25
headline_per_brand_input_token_cap: 500000
headline_per_brand_output_token_cap: 160000
headline_per_brand_cost_cap_usd: 1.00
headline_expected_max_brands: 25
started_at_utc:
finished_at_utc:
status: accepted|inconclusive|failed
search_requests:
results:
inserted:
updated:
enrichment_claim_cap_aggregate: 5
enrichment_claim_cap_current_cycle: 5
enrichment_claim_cap_carryover: 0
n_enrichment_claimed:
n_enrichment_claimed_current_cycle:
n_enrichment_claimed_carryover:
n_enrichment_succeeded:
n_enrichment_succeeded_current_cycle:
n_enrichment_succeeded_carryover:
n_enrichment_pending:
n_enrichment_pending_current_cycle:
n_enrichment_pending_carryover:
n_enrichment_failed:
n_enrichment_failed_current_cycle:
n_enrichment_failed_carryover:
n_enrichment_deferred:
n_enrichment_quarantined:
inserted_post_ids: []
enrichment_current_cycle_post_ids: []
enrichment_carryover_post_ids: []
enrichment_state_facts: []
# Each fact contains only post_id, lane, translation_status,
# classification_status, and output_complete.
inserted_current_identity_result: pass|fail
every_inserted_id_terminal_complete: pass|fail
feed_hidden_before_terminal_success: pass|fail
feed_visible_after_terminal_success: pass|fail
feed_observed_at_utc:
translator_effective_model_redacted:
translator_effective_host_redacted:
classifier_effective_model_redacted:
classifier_effective_host_redacted:
provider_routing_candidate_match: pass|fail
cursor_advanced:
headline_dispatch_status:
headline_provider_calls_before:
headline_provider_calls_after:
headline_provider_calls_delta:
headline_input_tokens_delta:
headline_output_tokens_delta:
queue_depth_after:
provider_secrets: present, values redacted
operator:
```

The command and evidence must prove
`inserted_post_ids == enrichment_current_cycle_post_ids` and
`enrichment_carryover_post_ids == []`. Every inserted ID must have exactly one
fact with `lane=current_cycle`, `translation_status=succeeded`,
`classification_status=succeeded`, and `output_complete=true`. Total and lane
claimed/succeeded/pending/failed counts must reconcile exactly with those
facts. Deferred and quarantined are totals and do not authorize acceptance.

Derive the four effective provider-routing values from the loaded candidate
configuration and the same environment fallback used by the production
factories, without constructing a provider client. Store only a stable
redacted fingerprint of each normalized model/host value; do not store a URL,
credential, process environment dump, or provider response. Staging and
production fingerprints must match each other and the candidate configuration.

After the run, query only staging:

```sql
SELECT brand_id, call_id, call_kind, bucket, query_id, last_completed_at
FROM call_state WHERE call_id = 'A';

SELECT count(*) AS backlog_rows FROM harvest_backlog_windows;
SELECT count(*) AS enrichment_rows FROM post_enrichment_states;
SELECT count(*) AS headline_runs FROM trend_narrative_runs;
SELECT count(*) AS headline_work_slots FROM trend_narrative_work_slots;
SELECT count(*) AS headline_provider_calls FROM trend_narrative_provider_calls;
SELECT count(*) AS headline_visible_pointers FROM trend_narrative_visible_runs;

SELECT count(*) AS provider_calls,
       coalesce(sum(input_tokens), 0) AS input_tokens,
       coalesce(sum(output_tokens), 0) AS output_tokens
FROM trend_narrative_provider_calls
WHERE created_at >= '<started_at_utc>'::timestamptz
  AND created_at <= '<finished_at_utc>'::timestamptz;
```

Inspect broker/worker status without provider calls. Queue depth must return to
zero. A broker/provider headline failure is recorded separately; it does not
erase accepted harvested posts.

## Candidate staging stop rule

This candidate gets one bounded staging attempt. A zero-result or update-only
attempt is inconclusive; any pending exact inserted cohort is also
inconclusive. Any hard error or failed terminal/output/feed gate is failed.
Both classifications stop promotion. There is no automatic retry, manual
substitute, cursor reset, refresh, backfill, or newer-cohort substitution. A
new attempt requires separate owner authorization and a new recorded attempt;
the historical result below remains immutable.

## Same-path staging and production parity

Staging and production use the same `CycleRunner`, writer lock, claimant,
translator, classifier, persistence, terminalization, and feed predicate.
Only bounded configuration differs: staging caps `5/5/0` and production caps `100/50/50`
for aggregate/current/carryover. Batch size 20, provider
concurrency three, request/stage/outer deadlines, models, hosts, prompts, and
search semantics are identical. A redacted effective model or host mismatch,
different candidate SHA, or different code path fails promotion.

## Pre-promotion read-only feed blast-radius gate

Before moving the unchanged candidate to `main`, run the five-warm-request
PostgreSQL benchmark and a read-only unfiltered/default-window feed census on
the production-shaped snapshot. Apply eligibility in the database before the
limit. Record the baseline and candidate query plans, SQL round trips, response
counts, and timings. No write, repair, provider call, or owner check-in is part
of this gate.

For the unfiltered default feed, fewer than 50 rows when at least 50 eligible rows exist
fails promotion. When fewer than 50 are eligible in the identical
window, the page count must equal that eligible count. SQL round trips must not
increase. Candidate median must be no more than baseline median plus the
greater of 25% or 50 ms, and every candidate request must remain below 2,000
ms. Any unacceptable threshold fails promotion rather than being waived.

Record:

```text
feed_snapshot_id:
feed_window_days:
feed_eligible_global_count:
feed_default_limit: 50
feed_default_page_count:
feed_page_fill_result: pass|fail
feed_baseline_query_round_trips:
feed_query_round_trips:
feed_baseline_median_ms:
feed_candidate_median_ms:
feed_candidate_max_ms:
feed_baseline_query_plan_hash:
feed_candidate_query_plan_hash:
feed_blast_radius_result: pass|fail
```

## Promotion preparation and forbidden actions

Record the exact pre-promotion `main` SHA and the people responsible before
promotion. The rollback route is a prepared feature-only revert advanced to
`main` through ordinary Git and Render auto-deploy; its validation uses only
natural scheduled cron jobs.

Do not suspend production. Do not reschedule production. Do not manually trigger production.
Do not apply a production Blueprint. Do not substitute a
backfill, replay, or manual harvest for a natural boundary. Promotion starts
immediately after a completed natural production cycle.

## Production continuity evidence

Production success is a separate read-only gate. A green staging result does
not prove it. Define the closed continuity ledger as follows:

- `B0` is the completed natural quarter-hour boundary immediately before
  promotion starts.
- `B1...Bn` are every expected `00/15/30/45` boundary after `B0` through the
  first qualifying natural candidate-SHA cycle. Candidate behavioral
  acceptance starts only after both web and harvester report that SHA.
- `Bn+1` is the following natural boundary after the acceptance cycle.

Every boundary must correlate exactly one scheduled Render execution with
exactly one terminal canonical `HARVEST_SUMMARY`. Match service ID, deploy SHA,
run ID, terminal status, and the summary's own start/finish timestamps and
hash. Post `fetched_at`, insertion timestamps, and wall-clock proximity are
useful context, but timestamps are supplemental and cannot establish the
correlation by themselves.

The summary line is counts-only. New releases emit summary schema v2; evidence
readers must parse historical v1 against its original narrower allowlists and
must reject a v1 envelope that claims v2 fields. This version rule does not
change the one-summary-per-boundary continuity requirement.

Use one entry per boundary:

```text
boundary_label: B0|B1...Bn|Bn+1
scheduled_boundary_utc:
render_execution_id:
render_trigger: schedule
render_started_at:
render_finished_at:
render_status:
render_service_id:
render_deploy_sha:
summary_run_id:
summary_started_at:
summary_finished_at:
summary_status:
summary_service_id:
summary_deploy_sha:
summary_hash:
correlation_result: pass|fail
```

A missing, duplicate, aborted, lock-skipped, manual, or uncorrelatable
execution/summary pair fails permanently. A later successful job cannot repair
or replace that boundary. Do not change production to make this evidence pass;
a continuity failure transfers to incident handling and makes zero-disruption
success impossible.

The older `max(fetched_at)` observation remains supplemental and may be
captured through the documented production Render psql route:

```sql
SELECT max(fetched_at) AS latest_fetch,
       count(*) FILTER (WHERE fetched_at >= now() - interval '45 minutes') AS recent_posts
FROM posts;
```

## Exact production cohort and quality evidence

After both production services report the unchanged candidate SHA, inspect the
first of at most two natural candidate-SHA cycles that inserts at least one
post. A zero-insert or update-only first cycle is inconclusive and may advance
only to the second natural cycle. The first nonempty inserted cohort is immutable:
retain its summary run ID and the exactly one `HARVEST_COHORT` receipt emitted
for that run before querying any posts. The receipt must be schema-valid,
independently hashed, bounded, and correlated to the canonical summary's
service ID, deploy SHA, run ID, and summary hash. Its inserted IDs, disjoint
current/carryover IDs, lane facts, and derived outcome counts must reconcile;
a missing, duplicate, malformed, truncated, or uncorrelated receipt fails.
Never reconstruct the cohort from timestamps or substitute a later or newer
cohort if enrichment, visibility, or quality fails.

The exact cohort passes only when current-cycle claim identity reconciles,
carryover accounting reconciles, every inserted ID is terminal-complete and
feed-visible, and these quality gates pass:

- all posts have canonical `lang_detected`;
- at least 99% of non-`zh-Hans` posts have valid nonblank `text_zh_cn`;
- at least 99% of all posts have valid nonblank, distinct `commentary_en` and
  `commentary_zh_cn` under the shared persisted-output policy.

Record numerators, denominators, rates, and percentages. A zero non-`zh-Hans`
denominator is valid. Integer acceptance is strict: N=50 requires 50/50 for
each 99% gate.

## Supplemental latest-N harvester report

Run the read-only harvester latest-N checker with `N=50` and save its detailed
report under `docs/analysis/harvester/`. Retain its literal ordered IDs. This
report is supplemental population evidence and never replaces the exact
candidate-cycle cohort.

Because this release changes enrichment timing, invoke the helper exactly twice
through its enrichment-relevant route. First run
`"$HEALTH_PYTHON" "$HEALTH_SCRIPT" --latest 50 --json` and freeze the ordered
IDs. Wait the skill's single 30-minute grace without polling. Then run one
`"$HEALTH_PYTHON" "$HEALTH_SCRIPT" --tweet-id <id> ... --report` invocation
containing every frozen ID in its original order. Do not retry, substitute a
newer cohort, or make a third checker call.

The report must follow the harvester health-check skill and contain full source text,
persisted translations and commentaries, durable enrichment states and
attempt timestamps, per-brand facts, discourse, nationalism, mentions, and
unsanctioned-flag evidence. The provider-call evidence is limited to the checker's empty
LLM-call ledger plus verbatim current-code prompt reconstructions and
deterministically known request kwargs. It must state that these are not
historical wire calls, mark runtime-only values unavailable, and include the
exact read-only SQL, invocation, Python version, checker SHA-256, repository
commit, and complete checker source. Never include credentials, environment
values, raw Render stderr, or tracebacks.

## Production release evidence

Fill every field without inference. Use `unknown`, which fails the associated
gate; never omit a field.

```text
candidate_sha:
pre_promotion_sha:
production_web_service: pushinweight-web
production_harvester_service: pushinweight-harvest
production_database_resource: pushinweight-db-shadow
production_web_sha:
production_harvester_sha:
promotion_started_at_utc:
rollback_route:
release_operator:
continuity_observer:
rollback_decider:
incident_owner:
staging_caps: 5/5/0
production_caps: 100/50/50
staging_provider_routing_fingerprint:
production_provider_routing_fingerprint:
production_translator_effective_model_redacted:
production_translator_effective_host_redacted:
production_classifier_effective_model_redacted:
production_classifier_effective_host_redacted:
provider_routing_parity: pass|fail
candidate_cycles_observed: 1|2
candidate_cycle_summary_run_id:
candidate_cycle_cohort_receipt_hash:
candidate_cycle_cohort_summary_hash:
candidate_cycle_inserted_post_ids: []
candidate_cycle_current_claimed_post_ids: []
candidate_cycle_carryover_claimed_count:
candidate_cycle_terminal_complete_count:
candidate_cycle_feed_visible_count:
canonical_lang_numerator:
canonical_lang_denominator:
non_zh_hans_text_zh_cn_numerator:
non_zh_hans_text_zh_cn_denominator:
non_zh_hans_text_zh_cn_rate:
non_zh_hans_text_zh_cn_percentage:
commentary_en_valid_numerator:
commentary_en_valid_denominator:
commentary_en_valid_rate:
commentary_en_valid_percentage:
commentary_zh_cn_valid_numerator:
commentary_zh_cn_valid_denominator:
commentary_zh_cn_valid_rate:
commentary_zh_cn_valid_percentage:
quality_gate: pass|fail
latest_n: 50
latest_n_report_path:
continuity_first_boundary: B0
continuity_acceptance_boundary:
continuity_following_boundary: Bn+1
continuity_result: pass|fail
production_service_mutations: none
release_result: pass|fail
```

## Scheduler-preserving rollback

If a post-promotion stop trigger fires, advance the prepared feature-only
revert through ordinary auto-deploy and natural cron. Do not suspend,
reschedule, manually trigger, apply a Blueprint, delete rows, or run a manual
replacement harvest. Rollback completes only after web and harvester report
the rollback SHA and the closed continuity ledger extends through the first
natural rollback-SHA cycle with seven-call, error, credit, and feed baselines
restored. An emergency suspension may be necessary for incident safety, but it
makes this release's zero-disruption success impossible.

## Recorded staging acceptance — 2026-08-27

The first and only live attempt ran at candidate
`e7468bd89674a9dc3f72242c1435f0b29c98e194` from 09:42:22Z through
09:42:32Z. The cron-hosted preflight and the live command both reported
`pushinweight-staging-harvest`, environment `staging`, and database/role
`pushinweight_staging` / `pushinweight_staging`.

The bounded result was safe but inconclusive: one call A, one search request,
one page, zero retries, zero results, zero inserts or updates, zero enrichment
claims, and no headline dispatch. The staging call-A cursor advanced once;
backlog, enrichment, headline run/work/provider/visible-pointer state and all
owned broker queue, unacked, watermark, and namespace keys remained zero. Per
this runbook, the empty result was not retried.

The deployed command initially emitted top-level `failed` because its result
classifier accepted only call status `completed`; the normal successful-empty
status is `no_results`. The follow-up candidate treats both statuses as safe
and returns `inconclusive`, with regression coverage preserving hard failures
for cursor-write and provider/pipeline errors. This classification correction
does not change the provider envelope or justify a second live attempt.

Production continuity passed independently. Before the attempt, at
09:41:14Z, production's latest `fetched_at` was 09:30:41Z with 148 posts in
the prior 45 minutes. After the attempt, at 09:45:53Z, it advanced to
09:45:44Z with 191 posts in the prior 45 minutes. The production service
remained unsuspended on branch `main` with schedule `*/15 * * * *`; no
production service mutation occurred.

## Secret rotation

Repeat this service-scoped sequence for TwitterAPI.io, translator/classifier,
and headline credentials:

1. **Install the replacement** in the correct staging Render service without
   displaying it. Never paste a secret into chat, a command argument, logs,
   evidence, or source control.
2. **Verify the guarded staging path** at the replacement revision using the
   pre-trigger identity gates and one separately authorized bounded attempt.
3. **Revoke the prior value** only after verification succeeds and no service
   still uses it.

Rotate immediately after suspected exposure or an access/owner change. Follow
the provider account's standing cadence otherwise. If verification fails,
leave the prior credential valid while diagnosing unless exposure requires
immediate revocation.

## Suspension and owner-only reactivation

To stop staging cost without affecting production, leave the harvester at its
dormant schedule, suspend `pushinweight-staging-headlines`, and disable the
stage acceptance/enqueue/provider-call controls. Preserve the staging database
and broker for diagnosis unless the owner explicitly chooses to discard them.

Before reactivation, the owner must re-check the candidate SHA on web,
harvester, and worker; the latest refresh receipt; exact staging database
identity; zero queue/unacked/envelope state; zero imported cursor/claim/
headline-runtime state after any refresh; and current provider budget
authorization. Resume the worker first, prove it is queue-only, then permit a
new manual harvester Trigger Run. Production remains untouched throughout.
