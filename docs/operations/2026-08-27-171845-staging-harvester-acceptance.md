# Staging harvester acceptance

Created: 2026-08-27. Delivery target: staging only.

This record is both the runbook and the evidence template for one bounded live
staging attempt. It does not authorize a production deploy, production service
mutation, production cron pause, or replay of an earlier production gap.

## Ownership and fixed limits

Staging owns `pushinweight-staging-db`, its `call_state` cursors,
`harvest_backlog_windows`, `post_enrichment_states`, list-sync state, headline
runs/work slots/provider ledgers/visible pointers, and
`pushinweight-staging-headlines-broker`. Production owns a disjoint copy of
each. The external TwitterAPI.io/provider account and quota remain shared.

One Trigger Run is fixed at one configured call, one logical/physical search
attempt, one page, five returned/persisted posts, no HTTP retries, no metrics
refresh, and five enrichment claims. Operators may not bypass the profile with
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
   target is `staging` and the candidate worktree/branch are canonical.
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

- `accepted`: at least one result entered persistence and bounded enrichment;
- `inconclusive`: safe zero/filtered/no-enrichment result; no automatic retry;
- `failed`: identity, provider, pipeline, or hard-bound failure; no retry.

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
enrichment_claimed:
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

## Production continuity evidence

Production success is a separate read-only gate. A green staging result does
not prove it. Record UTC observations spanning the staging Trigger Run and run
this query only through the documented production Render psql route:

```sql
SELECT max(fetched_at) AS latest_fetch,
       count(*) FILTER (WHERE fetched_at >= now() - interval '45 minutes') AS recent_posts
FROM posts;
```

```text
production_service: pushinweight-harvest
production_schedule_before: */15 * * * *
production_schedule_after: */15 * * * *
observation_before_utc:
latest_fetch_before:
observation_during_utc:
latest_fetch_during:
observation_after_utc:
latest_fetch_after:
production_service_mutations: none
continuity_result: pass|fail|inconclusive
```

Do not change production to make this evidence pass. A stalled production
timestamp is a separate incident and a staging stop condition.

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
