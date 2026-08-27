# Render runbook — Pushin Weight v2

Last verified against the Render account and Blueprint: 2026-08-27.

The isolated owner-review stack is defined separately in
`render-staging.yaml`. It contains a web service, dormant/manual harvester,
queue-only headline worker, owned broker, and PostgreSQL database on branch
`staging`. It must never share production resource names, database or broker
bindings, secret groups, workers, or cron jobs. Production must remain running
throughout staging delivery. This runbook owns the Render topology and service
verification; the Ollija plan guide owns delivery coordination only.

The parent delivery workflow reads the selected target and current Ollija
Delivery Guide from its plan before making Git or Render changes, and refreshes
it with `./bin/ollija annotate-plan <plan-path> --check`. It pushes the exact
candidate SHA to `staging`, confirms the staging deployment reports that same
SHA, and, only when the plan's recorded target is production, promotes the
unchanged SHA to `main` after staging passes. The workflow confirms the
configured Render services and health route for that candidate. A green build
alone is not sufficient evidence of the intended deployment identity.

### Staging snapshot refresh

The staging web service contains the guarded, operator-invoked production
snapshot mechanism. It is not a deploy hook or scheduled job. Its source role,
single staging-only secret, preflight, refresh, database receipt, rollback, and
prune procedures are defined in
[`docs/operations/staging-data-refresh.md`](../operations/staging-data-refresh.md).
Production must remain refresh-inert: `render.yaml` declares neither
`STAGING_DATA_REFRESH_ENABLED` nor `STAGING_REFRESH_SOURCE_DATABASE_URL`.

### Isolated staging runtime

| Resource | Staging-owned role |
|---|---|
| `pushinweight-staging-web` | Owner-only UI and refresh authority; never harvests |
| `pushinweight-staging-harvest` | Dormant cron; manual Trigger Run only |
| `pushinweight-staging-headlines` | Queue-only `trend-narratives` worker, concurrency one |
| `pushinweight-staging-headlines-broker` | Broker, envelope watermark, and queue state |
| `pushinweight-staging-db` | Posts, cursors, backlog, enrichment claims, and headline ledgers |

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
guardrails are per brand: 25 calls, 500,000 input tokens, 160,000 output
tokens, and USD 1.00 at the pinned pricing revision, across at most 25 expected
brands. Verify those effective values with `headline_status --json` and the
candidate config before authorizing the attempt. A rate/quota refusal is a
failed acceptance, advances no cursor, dispatches no headline work, and has no
automatic retry.

The full acceptance, evidence, secret-rotation, suspension, and reactivation
procedure is
[`docs/operations/2026-08-27-171845-staging-harvester-acceptance.md`](../operations/2026-08-27-171845-staging-harvester-acceptance.md).

### Same-cycle zero-disruption release

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
| `pushinweight-harvest` | Render cron, `*/15 * * * *`, `python manage.py run_cycle` |
| `pushinweight-db-shadow` | PostgreSQL used by the deployed web/cron services |
| `pushinweight-headlines-broker` | Available owned Key Value broker for `trend-narratives` |
| `pushinweight-headlines` | Active queue-only worker for `trend-narratives`, concurrency/prefetch one |
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

## Controls and credentials

These controls are independent and fail closed:

| Service | Variable | Blueprint value after production proof |
|---|---|---|
| web | `X_MONITOR_HEADLINE_SERVING_ENABLED` | `True` |
| harvest cron | `X_MONITOR_HEADLINE_ENQUEUE_ENABLED` | `True` |
| headline worker | `X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED` | `True` |

Before changing a control, verify the resolved service environment and record
the new control revision. Render may preserve an older per-service override;
the deployed value, rather than the Blueprint text alone, is authoritative.

`DEEPSEEK_API_KEY` must be present on the headline worker. Its value is the
same DeepSeek V4 credential used by translation/classification, but it remains
a worker-scoped Render secret; do not attach the broad `pushinweight-secrets`
group to the worker.
Record `X_MONITOR_HEADLINE_CONTROL_REVISION` with every control change.
`DATABASE_URL` is declared with `fromDatabase: pushinweight-db-shadow` for web,
cron, and worker. The existing Render services may retain their prior
environment value after a Blueprint sync, so the release owner must verify the
resolved database identity on every service after sync and manually inject the
same managed credential through Render if a service did not update. Never
commit a connection string to source control.

### Database credential rotation

Use Render-managed users rather than `CREATE USER` or `ALTER ROLE`. A newly
created managed user becomes the database default, but the old user remains
valid until explicitly retired.

1. Create the new managed credential through Render and leave the old user
   active.
2. Sync the Blueprint and redeploy every active database consumer.
3. Inspect the resolved `DATABASE_URL` on web, headlines, and harvest without
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
`https://api.deepseek.com/anthropic` + `deepseek-v4-pro`. Translation and
classification use the same endpoint and credential but are pinned to
`deepseek-v4-flash`. Anthropic is a separate explicit route using
`https://api.anthropic.com` + `claude-haiku-4-5-20251001`; MiniMax is a
separate explicit/evaluated route using
`https://api.minimax.io/anthropic` + `MiniMax-M3`; legacy M3 model names and
the deprecated endpoint are rejected.

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
