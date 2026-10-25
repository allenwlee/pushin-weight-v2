# Render runbook — Pushin Weight v2

The shared collection foundation is described in
[Collection jobs](../reference/collection-jobs.md). The source-ingestion increment
adds no tables; migration0087creates the conditional statistics snapshot index
concurrently. The build migration runner polls its application-database advisory
lock so another build cannot obstruct concurrent DDL. Inspect both the migration
ledger and index valid/ready state after a failed build before retrying it.

Registering jobs does not activate sources, provider batches or schedules.
Reviewed recurring source roles use explicit collection authority and the existing
hourly benchmark runner. Historical backfiller-data-source work and evidence replay
use the same adapters and numeric writer, with separate finite jobs and budgets.
The existing fifteen-minute X cron remains the only harvest scheduler, and its
runtime receipt adapter and recovery controller have separate ownership.

For compatible OriginalContent storage delivery, follow the
[storage controls and cutover contract](../reference/original-content.md#controls-cutover-and-rollback).
Deploy compatible consumers before backfill/activation; keep legacy writers and
tables during the seven-day rollback window. A shared-storage flag does not
activate provider calls. Production controls remain independent of staging.

Last verified against the Render account and Blueprint: 2026-08-27.

The isolated owner-review stack is defined separately in
`render-staging.yaml`. It contains a web service, dormant/manual harvester,
queue-only headline worker, PostgreSQL-only synthesis worker, owned broker,
and PostgreSQL database on branch `staging`. It must never share production resource names, database or broker
bindings, secret groups, workers, or cron jobs. Production must remain running
throughout staging delivery. This runbook owns the Render topology and service
verification; the Ollija plan guide owns delivery coordination only.

The parent delivery workflow reads the selected target and current Ollija
Delivery Guide from its plan before making Git or Render changes, and refreshes
it with `ollija annotate-plan <plan-path> --check`. It pushes the exact
candidate SHA to `staging`, confirms the staging deployment reports that same
SHA, and, only when the plan's recorded target is production, promotes the
unchanged SHA to `main` after staging passes. The workflow confirms the
configured Render services and health route for that candidate. A green build
alone is not sufficient evidence of the intended deployment identity.

### Database credentials and migrations

Web services use the dedicated `pushinweight_web_serving` database login and
`PW_DATABASE_ACCESS_MODE=serving`. Their `DATABASE_URL` is a Render-managed
`sync: false` value. They have no owner connection or production snapshot
credential. Ordinary ORM models expose canonical local geolocation IDs; source
projections are available only to ingestion/resolution processes with appropriate
column privileges. A web build verifies its restricted identity and waits for the
candidate migration graph to finish; it does not run DDL.

Existing owner processes continue to run `scripts/render_migrate.py` under both
existing locks. `PW_SERVING_DATABASE_ROLE=pushinweight_web_serving` makes the owner
reconcile canonical column grants after successful migrations. Bootstrap the
separate login before enabling that setting. Inspect direct variables and linked
environment groups; never leave an owner URL in the web service as a fallback.

After `0160_rg4_remove_superseded_storage`, recovery and suspended-service
resumption require the tested deletion revision recorded in the global schema
plan, or a verified compatible descendant. The superseded geography columns,
country/region tables and two rejected catalogues are physically absent. Do not
roll back to the preceding image or reverse this migration. Preserve the current
database and apply a compatible forward fix; a database restore is a separate
recovery operation requiring its own authority and verification.

### Staging snapshot refresh

The existing staging jobs service supplies the build and configuration for the guarded, operator-invoked production
snapshot mechanism. It is not a deploy hook or scheduled job. Its source role,
single staging-only secret, preflight, refresh, database receipt, rollback, and
prune procedures are defined in
[`docs/operations/staging-data-refresh.md`](../operations/staging-data-refresh.md).
Production must remain refresh-inert: `render.yaml` declares neither
`STAGING_DATA_REFRESH_ENABLED` nor `STAGING_REFRESH_SOURCE_DATABASE_URL`.

### Isolated staging runtime

| Resource | Staging-owned role |
|---|---|
| `pushinweight-staging-web` | Owner-only UI with a restricted database login; never harvests |
| `pushinweight-staging-jobs` | Manual-only careers cron and base for explicitly invoked refresh jobs |
| `pushinweight-staging-harvest` | Dormant cron; manual Trigger Run only |
| `pushinweight-staging-headlines` | Queue-only `trend-narratives` worker, concurrency one |
| `pushinweight-staging-synthesis` | Database-queue worker for demand-triggered trilingual post synthesis |
| `pushinweight-staging-headlines-broker` | Broker, envelope watermark, and queue state |
| `pushinweight-staging-db` | Posts, cursors, backlog, enrichment claims, headline ledgers, synthesis demands, and artifacts |

The harvester schedule is the exact never-occurring expression
`0 0 31 2 *`. Render Dashboard **Trigger Run** is the only authorized initial
invocation. Its command must remain:

```text
python manage.py run_cycle --staging-acceptance \
  "${X_MONITOR_STAGING_ACCEPTANCE_CALL_ID:?staging acceptance call ID missing}" \
  --json
```

Never replace it with plain `python manage.py run_cycle`, never add `--async`,
and never schedule it periodically. The application guard independently
requires the stage enable flag, deployment environment, configured and Render
service names, one configured call ID, the exact staging PostgreSQL host/name/
role, and provider credentials before it takes the writer lock or builds a
network client. The immutable execution envelope is one call, one page, five
results, one total search pass, zero HTTP retries, no metrics refresh, and
staging `5/5/0` aggregate/current/carryover enrichment claims.

Staging and production currently use the same provider account and therefore
the same shared provider quota. Database and broker isolation prevent cursor,
claim, and queue corruption; they do not create quota headroom. Confirm budget
authorization immediately before every Trigger Run for both the Twitter search
and the separately dispatched headline-provider work. The checked-in headline
guardrails are per brand: 25 calls, 500,000 input tokens, 180,000 output
tokens, and USD 1.00 at the pinned pricing revision, across at most 25 expected
brands. Verify those effective values with `headline_status --json` and the
candidate config before authorizing the attempt. A rate/quota refusal is a
failed acceptance, advances no cursor, dispatches no headline work, and has no
automatic retry.

The full acceptance, evidence, secret-rotation, suspension, and reactivation
procedure is
[`docs/operations/2026-08-27-171845-staging-harvester-acceptance.md`](../operations/2026-08-27-171845-staging-harvester-acceptance.md).

### Same-cycle zero-disruption release

**Applicability:** this contract applies to changes to same-cycle harvest/enrichment behavior
whose plan selects these continuity checks. UI, documentation, and unrelated deployment
changes do not inherit it. The current owner-selected route and explicit exceptions decide
which staging steps remain required; a waived step is not a passed acceptance.

Staging and production run the same `CycleRunner`, claimant, translation,
classification, persistence, and enriched-only feed predicate. Their only
enrichment allocation difference is staging `5/5/0` versus production `100/50/50`
for aggregate/current/carryover. Models, resolved provider routes,
batch size, concurrency, timeouts, deadlines, and search semantics must match;
compare secret-free model/host fingerprints before promotion.

The candidate may move to `main` only after one bounded staging attempt is
accepted under the exact inserted/current-cycle identity and terminal-output
rules in the acceptance runbook. Inconclusive or failed staging has no
automatic retry. Promotion begins immediately after a completed natural
production cycle and keeps a closed continuity ledger from that boundary,
through every `00/15/30/45` deployment boundary and the first qualifying
candidate-SHA natural cycle, to one following boundary. Every entry correlates
exactly one scheduled Render execution with one terminal canonical `HARVEST_SUMMARY`;
missing, duplicate, aborted, lock-skipped, manual, or
uncorrelatable evidence fails permanently.

Canonical summaries emitted by this release use summary schema v2; readers
must continue to parse historical v1 using its narrower post-fetch and metrics
allowlists. A nonempty cycle also emits exactly one bounded `HARVEST_COHORT`
receipt. It is separate from the counts-only summary and must match the same
service ID, deploy SHA, run ID, and summary hash before its post IDs may be
used as acceptance evidence.

No production suspension, schedule change, manual run, or Blueprint
application is part of this release or its rollback. Rollback advances a
prepared feature-only revert through ordinary auto-deploy and natural cron,
then closes the same ledger through the first rollback-SHA natural cycle.
Read-only feed page-fill/performance preflight, immutable exact-cohort quality,
and the supplemental detailed latest-50 report are defined in the acceptance
runbook rather than duplicated here.

## Deployed reality

Production harvesting is synchronous and has one scheduler:

| Resource | Current role |
|---|---|
| `pushinweight-web` | Django/Gunicorn dashboard |
| `pushinweight-harvest` | Render cron, `*/15 * * * *`, `python manage.py run_cycle --scheduled` |
| `pushinweight-db-shadow` | PostgreSQL used by the deployed web/cron services |
| `pushinweight-headlines-broker` | Available owned Key Value broker for `trend-narratives` |
| `pushinweight-headlines` | Active queue-only worker for `trend-narratives`, concurrency/prefetch one |
| `pushinweight-synthesis` | PostgreSQL-only worker for demand-triggered trilingual post synthesis |
| legacy `pushinweight-worker` | Suspended; old SHA; do not reactivate |
| legacy `pushinweight-beat` | Suspended; old SHA; do not reactivate |

`monitor/tasks.py` and old documentation previously implied that Celery beat
scheduled harvesting. It does not. Render cron is authoritative; production
must have exactly one active harvest scheduler and zero active beat services.

## Per-brand trend narrative worker

The additive `render.yaml` declares the desired topology:

| Resource | Purpose |
|---|---|
| `pushinweight-headlines-broker` | Owned persistent/no-eviction Key Value broker |
| `pushinweight-headlines` | Dedicated Celery worker consuming only `trend-narratives`, concurrency/prefetch one |

The web, harvest, and headline services share the all-brand packet-v3
revision; the broker and dedicated worker are present. A run makes one rank
call, then editor and critic calls over deterministic batches of at most five
eligible brands. After staged production proof, the checked-in Blueprint keeps
all three controls live under the recorded control revision. Disable the
relevant control first when following the rollback matrix below.

The worker command intentionally omits beat and consumes no default/harvest
queue:

```text
celery -A project worker -l INFO -Q trend-narratives --concurrency=1 \
  --prefetch-multiplier=1 --without-gossip --without-mingle
```

## Post synthesis worker

The synthesis worker polls `post_synthesis_demands` and holds the staging or
production synthesis coordination lock for its full process lifetime. It has
no Celery broker, harvest command, scheduler, or TwitterAPI credential. The
same lock makes a staging refresh fail closed until the worker is suspended,
and prevents the worker from restarting during the database-name swap.

```text
python manage.py run_synthesis_worker
```

The web request creates or polls shared demand; it never calls the model.
`synthesis_status --json` reports queue, artifact, and usage accounting from
PostgreSQL. Keep prewarm disabled until its separate review has passed.

## Controls and credentials

These controls are independent and fail closed:

| Service | Variable | Blueprint value after production proof |
|---|---|---|
| web | `X_MONITOR_HEADLINE_SERVING_ENABLED` | `True` |
| harvest cron | `X_MONITOR_HEADLINE_ENQUEUE_ENABLED` | `True` |
| headline worker | `X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED` | `True` |
| synthesis worker | `X_MONITOR_SYNTHESIS_PROVIDER_CALLS_ENABLED` | `True` |

The synthesis worker also requires
`X_MONITOR_SYNTHESIS_ACTIVATION_STATE=owner_override` (or `reviewed`) and an
explicit `X_MONITOR_SYNTHESIS_CONTROL_REVISION`. Staging first deploys the new
lane with provider calls disabled, then enables it as a service-local override
only after the refresh and bounded quality/cost gates pass.

TwitterAPI credentials are also purpose-separated and fail closed:

| Purpose | Render-managed variable | Authorized callers |
|---|---|---|
| Scheduled | `TWITTERAPI_IO_SCHEDULED_API_KEY` | Recurring `run_cycle` search and metrics |
| On demand | `TWITTERAPI_IO_ON_DEMAND_API_KEY` | Explicit batches, backfills, reconciliation, probes, and smoke tests |

Store both production values in the existing `pushinweight-secrets`
environment group. Do not define the retired unsuffixed name, duplicate a key
as a service-local override, or configure either credential as a fallback for
the other. Staging declares both names directly on its harvester with
`sync: false`; enter their values manually in the Render Dashboard.

The one-time Account User About population runs as an exact-SHA one-off job
from `pushinweight-harvest`, never as a cron schedule. It requires an explicit
production target, database identity, applied migrations, a fresh
restore-proved recovery receipt, an advisory run lock, and bounded spend and
concurrency. Follow
`docs/operations/2026-08-29-223000-account-user-about-backfill.md`; do not copy
the on-demand key to a shell command or another service.

Before changing a control, verify the resolved service environment and record
the new control revision. Render may preserve an older per-service override;
the deployed value, rather than the Blueprint text alone, is authoritative.

`DEEPSEEK_API_KEY` must be present on the headline worker. `DEEPINFRA_API_KEY`
must be present on the harvest and synthesis services for direct 0731
classification and direct Gemma translation/commentary. Each worker receives
only the provider credential its role uses; do not attach the broad
`pushinweight-secrets` group to a worker.
Record `X_MONITOR_HEADLINE_CONTROL_REVISION` with every control change.
`DATABASE_URL` is declared with `fromDatabase: pushinweight-db-shadow` for web,
cron, headline worker, and synthesis worker. The existing Render services may retain their prior
environment value after a Blueprint sync, so the release owner must verify the
resolved database identity on every service after sync and manually inject the
same managed credential through Render if a service did not update. Never
commit a connection string to source control.

### Historical X batch jobs and safe handover

Historical backfill uses a Render one-off job created from the deployed
`pushinweight-harvest` revision. The one-off has its own process and compute;
the recurring `run_cycle --scheduled` command and schedule stay unchanged.
The backfill command selects `TWITTERAPI_IO_ON_DEMAND_API_KEY` explicitly.
Use the existing Render-managed credentials rather than copying them to the
web or careers-job service. Staging acceptance uses its existing manual donor.

Collection instructions and page checkpoints live in the shared collection
tables. Enrichment uses `ProviderBatch` and `OriginalContentCall`, retaining
saved replies, reservations, unknown costs and the original campaign limits.
Legacy campaign execution defaults to 32 simultaneous model requests per one-off.
The opt-in phase commands below default to eight for enrichment. Collection page
writes coordinate with the normal harvester. In the parallel fetch path, only
HTTP overlaps: the controller archives each response and replays pages through
the shared, serial Post writer. It releases the writer lock during HTTP and
checks live-harvester priority before admitting more requests or replaying pages.

To collect an existing compact month recipe before ordinary enrichment:

```bash
python manage.py run_backfill --month-recipe month-recipe.json \
  --phase collect \
  --runtime-revision FULL_TESTED_COMMIT_SHA \
  --runtime-attestation runtime.json --execute
```

Use `--dry-run` instead of `--execute` to validate inputs and print the unchanged
recipe without starting provider calls or writing collection jobs. A month recipe
preserves its original daily manifests, five-minute query boundaries, routes,
author roles, budgets and deadline. `runtime.json` contains `runtime_revision`
and `source_sha256`; its hashes must cover the original recipe's source inventory
and the required runtime modules declared in `scripts/backfill_month.py`.
Updating the runtime attestation does not rewrite saved collection instructions.

After collection is verified, run the same recipe and runtime inputs with
`--phase enrich --enrichment-concurrency 8 --execute`. Enrichment uses saved Post
memberships and makes no X searches. `--phase all` performs both passes across the
entire requested range: every collection window precedes the first ordinary
enrichment window. Existing `--manifest` campaigns support the same phases;
invocations without `--phase` retain the legacy ordering. Enrichment concurrency
may be reduced or raised only within the original saved ceiling, at most 32.
Collection concurrency is 1–20, independently bounded by the request-start rate,
remaining request allowance, attempt deadline and response byte allowance.
It defaults to one. Opt in with `--collection-concurrency 20` and an explicit
`--collection-starts-per-second` value only when that workload warrants it.
The October 22 low-latency staging fixture preserved identical data and request
counts but averaged 477 seconds serial versus 490 seconds parallel. A second
fixture with eight-second responses sustained 20 active requests and completed
the same 800 Posts/40 requests in 141 seconds versus 434 seconds serially.
Live harvesting acquired its writer lock in 16 milliseconds while 20 requests
were outstanding; captured responses replayed without refetching. These controlled
tests establish concurrency, data parity and priority, not production throughput
or provider capacity. Separating collection from enrichment does not depend on
parallel fetching.

Collection still includes relevance and rare-type admission decisions. Those
model calls are required to decide which source results belong in Post storage.
Phase receipts under `CollectionRun.report.backfill_campaign` distinguish
collection and enrichment, preserving existing campaign history. Their
`phase_usage` separates X requests, inline collection-gate model usage, and
post-enrichment model usage; unknown outcomes and missing provider usage remain
explicit. Post-enrichment totals include counts of ambiguous calls and sent calls
without a reported cost; the reported-cost sum is partial when that count is
nonzero. All usage is cumulative for the collection job, not a per-phase charge.
The model path uses `DEEPINFRA_ON_DEMAND`; the X path uses the on-demand key above.

Received parallel pages are stored using existing collection request/archive
records. A restart replays unconsumed saved responses without another search.
Unknown transport outcomes stop automatic resending and require reconciliation.
`--evaluate-at-end` retains the known enrichment deferral policy; collection
integrity failures still stop acquisition. Neither a completed cursor chain nor
equal ingestion output establishes exhaustive historical X keyword coverage.

Before changing shared database columns, identify any one-off still using an
older image. Deploying its base service does not update an already running job.
After an authorized cancellation, verify terminal native status and release of
its controller lock; retained run markers recover through the existing lease
fencing. Preserve saved posts, cursors, paid history and uncertain final requests.

For an ordinary-API enrichment handover, run these commands against the
campaign's pinned database, substituting its collection-job UUID:

```bash
python manage.py backfill --collection-job JOB_UUID --enrichment-control status
python manage.py backfill --collection-job JOB_UUID --enrichment-control pause \
  --enrichment-actor OPERATOR --enrichment-reason 'controller handover'
```

Pause immediately blocks new paid admission. Already-sent requests may finish
and save their replies. Reissue pause until it reports `safe_to_cancel: true`:
sent calls, active processing claims and outstanding remote native groups must
all be zero. The pause transaction revokes old processing fences at that
barrier. Cancel only the owned old Render one-off and verify its terminal state
before resuming:

```bash
python manage.py backfill --collection-job JOB_UUID --enrichment-control resume \
  --enrichment-actor OPERATOR --enrichment-reason 'old controller is terminal'
```

Resume retains the original budget/deadline and reuses paid replies. It does
not resolve unknown remote outcomes. Inspect ambiguous calls before any
explicit retry. Active native Batch work rejects a local pause with
`native_batch_requires_remote_drain`; drain or explicitly reconcile that remote
work first. Status and control commands require no provider credentials.

Verified with PostgreSQL caller regressions on 2026-10-15. This procedure does
not launch a campaign or transfer staging Posts to production.

### Database credential rotation

Use Render-managed users rather than `CREATE USER` or `ALTER ROLE`. A newly
created managed user becomes the database default, but the old user remains
valid until explicitly retired.

1. Create the new managed credential through Render and leave the old user
   active.
2. Sync the Blueprint and redeploy every active database consumer.
3. Inspect the resolved `DATABASE_URL` on web, headlines, synthesis, and harvest without
   printing it; verify that its username is the new default. A green deploy at
   the expected SHA is necessary but not sufficient.
4. Verify the login endpoint and relevant worker/cron logs, then query
   `pg_stat_activity` for connections using the old username.
5. Retire the old managed credential only when its connection count is zero.
6. Verify the old credential is rejected and repeat the endpoint/log checks.

During the 2026-08-14 rotation, a normal commit-triggered Blueprint deploy was
green but did not refresh the three existing services' resolved database URL.
Retiring the old user caused a short outage until the new internal connection
URL was applied directly and all three services were redeployed. Never use
deploy status alone as the retirement gate.

The headline route is pinned to DeepSeek V4 via
`https://api.deepseek.com/anthropic` + `deepseek-v4-flash`. Scheduled
classification uses `deepseek-ai/DeepSeek-V4-Flash-0731` through DeepInfra's
direct OpenAI-compatible endpoint. Literal translation and on-demand commentary
use `google/gemma-4-31B-it-turbo` through that same direct DeepInfra endpoint.
These routes read only `DEEPINFRA_API_KEY`; OpenRouter is not a fallback.
MiniMax remains a separately configured route using
`https://api.minimax.io/anthropic` + `MiniMax-M3`; legacy M3 model names and
the deprecated endpoint are rejected.

Classifier requests contain public post text, stored quote or locally stored
parent context when available, source timestamp/language, a validated English
translation, reviewed author-to-brand relationships, and the curated tracked-
brand alias/handle catalog needed to distinguish tracked from untracked
promotion. They do not include account bios, profile images, database secrets,
or provider credentials. Treat DeepInfra's processing and retention terms as
part of the release review whenever this payload changes.

## Cost and freshness contract

- Each due `1/7/30/365d` window creates an independent all-brand run. A run
  with `B` eligible brands makes `1 + 2 * ceil(B / 5)` physical requests: one
  rank call and paired editor/critic calls for five-brand batches. With 20
  eligible brands that is nine calls.
- SDK retries, Celery automatic retries, public regeneration, arbitrary filter
  narratives, and repair calls are disabled.
- Cadences are 30 minutes, 1 hour, 6 hours, and 24 hours respectively. Stale
  limits are twice those intervals.
- Semantically unchanged bucket-coordinate/timestamp drift advances the
  durable checked tuple with zero version and zero provider request. A changed
  analytical vector, candidate, evidence set, prompt, model route, or
  publication epoch is generation-relevant.
- Browser loads, locale/filter changes, the 60-second refresh, and repeated
  window switching read PostgreSQL only.
- A failed or invalid output never replaces current copy.

Inspect state without calling the provider:

```bash
python manage.py headline_status
python manage.py headline_status --json
```

## Ordered activation gates

Stop at any failed gate. Record timestamp, deployed SHA, service ID, operator,
observer, and control revision.

1. Disable all three controls on the currently deployed revision and drain the
   headline queue. Capture the pre-migration ledger count/ID/current-row SQL
   from the baseline investigation.
2. Deploy the additive migration and code with all three controls still off.
   Verify the physical `trend_narratives` parent, writable
   `trend_narrative_versions` compatibility view, normalized subject table,
   row/ID/no-rewrite invariants, legacy web fallback, baseline harvest call
   count, one active cron, zero beat, and all three services resolving to
   `pushinweight-db-shadow`.
3. Reconcile the owned broker and headline-only worker. Do not touch the two
   suspended legacy services. If the worker is absent, stop before enabling
   enqueueing.
4. Send one safe provider-free task. Verify only `trend-narratives` is consumed,
   concurrency/prefetch are one, and the queue returns to zero.
5. Enable enqueue on the cron while provider remains off. One real harvest must
   report `provider_disabled`, create no per-brand work slots, and make zero
   HTTP attempts.
6. Empty the queue. Enable provider calls for one canary. Verify the persisted
   brand manifest and exact `1 + 2 * ceil(B / 5)` call graph, HTTP starts never
   exceed reserved calls, valid bilingual brand rows publish independently,
   held brands retain last-good copy, and harvest external calls remain at
   baseline.
7. Review all four locales/windows in a real browser. Enable serving only after
   content, freshness, link, mobile geometry, and accessibility checks pass.
8. Observe +1h, +6h, and +24h. Queue depth must return to zero, oldest message
   stay below 30 minutes, and no run may exceed its persisted call graph.

## Rollback matrix

| Incident | First action | Preserve |
|---|---|---|
| Cost, provider, or queue | Disable provider calls; verify worker revision; disable enqueue | Last-good database rows and serving |
| Bad content | Disable serving and provider calls | Harvester and rows |
| UI regression | Disable serving only | Worker evidence and rows |
| Worker/broker outage | Disable enqueue; pause dedicated worker if needed | Web and harvester |

Never remove the expanded parent/subject tables or compatibility view during
operational rollback. The per-brand migrations refuse destructive reversal
while durable rows or work-slot state exist; select `legacy_only` with enqueue
and provider calls disabled instead. Do not delete rows or reactivate legacy
worker/beat resources. Browser traffic must remain incapable of generating
work.

## Validation commands

Use disposable PostgreSQL only for tests; never aim pytest at shared data.

```bash
render blueprints validate render.yaml
DATABASE_URL=postgresql://fuchitalee@localhost/pushinweight_test \
  .venv/bin/pytest tests/test_trend_narrative_*.py --reuse-db -q
node tests/test_pw_chart_filter.js
python manage.py check --deploy
```

The Blueprint validation must show `pushinweight-db-shadow` as the existing
database resource and must not plan creation of `pushinweight-db`. After a
sync, verify the database host/resource identity on `pushinweight-web`,
`pushinweight-harvest`, and `pushinweight-headlines`; a successful deploy alone
does not prove that an existing service refreshed its environment.

## Official AI-lab jobs sync

`sync_job_sources` pulls public listings from the official recruiting sites
for Qwen, DeepSeek, MiniMax, Z.ai/Zhipu, and Kimi/Moonshot. It is deliberately
separate from `run_cycle`: it uses no TwitterAPI key, broker, Celery worker, or
language-model credential.

Inspect every live contract without writing the database:

```bash
python manage.py sync_job_sources --dry-run --json
```

Limit a diagnostic run to one or more sources by repeating `--source`:

```bash
python manage.py sync_job_sources --source qwen --source deepseek --dry-run
```

For the first controlled write, apply migrations and suppress closure. This
creates or refreshes observed listings while leaving absent listings open:

```bash
python manage.py migrate --noinput
python manage.py sync_job_sources --no-close --json
```

After reviewing `job_source_sync_runs` and `job_source_states`, a normal run
may advance the two-complete-miss closure rule:

```bash
python manage.py sync_job_sources --json
```

A source failure is isolated: successful sources commit, the failed source's
listings and miss counters do not change, and the command exits non-zero.
Inspect the run row's `error_summary`, then use a source-specific dry run. Do
not disable HTTPS/host checks or bypass a login/challenge. If an upstream
contract intentionally changed, replace its sanitized test fixture and parser
together. An active source lease expires after 30 minutes; an expired lease is
reclaimed and its abandoned run is marked failed.

Production schedules `pushinweight-jobs` every six hours. The staging
`pushinweight-staging-jobs` schedule can never occur and must be triggered
manually for acceptance. Neither cron may contain `run_cycle`, Celery beat, or
TwitterAPI/LLM credentials.

The jobs cron is a new Blueprint resource, so pushing its branch does not
create the service by itself. For staging acceptance, sync/apply only
`render-staging.yaml` in the Render Dashboard before triggering
`pushinweight-staging-jobs`. Do not apply `render.yaml` during a staging-only
release; that file defines the production cron.

## Homepage count maintenance

The homepage reads closed UTC days from `home_brand_time_counts`, a native
PostgreSQL materialized view, and adds exact source counts for the live day.
Its `home.brand_time_counts.v1` row in shared `materialization_state` records the published cutoff and
source changes. The 30-day and 365-day percentage comparisons end at UTC
midnight; chart responses retain their live clock and selected local timezone.
One-day and seven-day percentage comparisons remain rolling windows.

Migration `0093_homepage_count_materialization` creates the view without data,
its unique index, the lifecycle table and count-relevant source triggers.
Migration `0094_shared_materialization_state` preserves that publication while
generalizing the table to one row per versioned dataset. It rebinds the source
triggers to the homepage key; the shared refresh implementation in
`core/materializations.py` uses each definition's own lock, sources and cutoff.
Other datasets require their own reviewed definition and invalidation migration.
The state tracks current freshness; immutable article/research results retain
their saved data and identity separately. The
ordinary page query remains available while the view is unpopulated or invalid.
Populate it through the service's managed database configuration:

```bash
python manage.py refresh_home_counts
```

The command emits JSON with `status` equal to `refreshed`, `skipped`, `busy`,
`changed`, or `unavailable`. `changed` means a source write overlapped counting
and the whole refresh was rolled back; retry at the next poll. A missing
lifecycle row is repaired in a separate short transaction only when existing
source writers have finished. A busy source or another refresher causes a
truthful `busy` result. The repair transaction must commit before counting, so
run the command outside an enclosing application transaction.

Production `pushinweight-home-counts` runs at minutes `7,22,37,52` UTC. A healthy
same-day poll skips counting. Normal daily publication begins around 00:07 UTC
(09:07 Japan time); historical corrections can require additional refreshes.
The production count job uses only its own database and runtime environment;
it receives no provider credentials, broker, collection commands or harvest
schedule. The staging manifest declares no count cron: schema integration
does not provision or activate a staging maintenance resource. A separate
provisioning request is required before adding one. Blueprint synchronization
can create declared resources automatically when its branch changes; check
the intended manifest before publishing a branch.

Verify the native view and publication state on the intended database:

```sql
SELECT matviewname, ispopulated
FROM pg_matviews WHERE matviewname = 'home_brand_time_counts';
SELECT indisvalid, indisready
FROM pg_index
WHERE indexrelid = 'home_brand_time_counts_key'::regclass;
SELECT cutoff, refreshed_at, source_generation, published_generation, dirty_since,
       (source_generation = published_generation OR dirty_since >= cutoff)
           AS closed_history_valid
FROM materialization_state WHERE dataset_key = 'home.brand_time_counts.v1';
```

Current-day writes advance the source generation without invalidating closed
history. A generation difference alone therefore does not prove staleness;
check `dirty_since` and the UTC cutoff too. A stale or historically dirty
publication uses the exact query until maintenance succeeds. No browser request
refreshes the view or calculates Top Voices. Saved narrative selection remains
independent.

After activation, verify real homepage switches to 30 days and one year return
200 before the browser timeout, replace every associated projection, and log no
JavaScript errors. Inspect the maintenance JSON and publication fields after a
scheduled poll. If the release causes incorrect counts or source-write failures,
roll back the application revision and suspend only the new count-maintenance
job. The previous application can use the additive schema. Keep source data and
existing harvest schedules intact; schema reversal is a separate controlled
operation after consumers no longer use the view.
