# Render runbook — Pushin Weight v2

Last verified against the Render account and Blueprint: 2026-08-13.

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

## V22 shared trend narrative candidate

The additive `render.yaml` declares the desired topology:

| Resource | Purpose |
|---|---|
| `pushinweight-headlines-broker` | Owned persistent/no-eviction Key Value broker |
| `pushinweight-headlines` | Dedicated Celery worker consuming only `trend-narratives`, concurrency/prefetch one |

The web, harvest, and headline services run the analytical/schema-two
revision; the broker and dedicated worker are present. After the staged
production canary and browser proof, the checked-in Blueprint keeps all three
controls live under control revision `v22-analytical-live-v1`. Disable the
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

The read-only pre-rollout inventory found the prior revision live with serving,
enqueueing, and worker provider calls enabled under separate old control
revisions. Do not deploy the schema-two code while inheriting those values.
Before deployment, verify the resolved service environment will take the
checked-in all-off values; if Render preserves an old per-service override,
set that control to `False` before the build starts.

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

The headline route is pinned to DeepSeek V4 via
`https://api.deepseek.com/anthropic` + `deepseek-v4-pro`, matching the
translation/classification route. Anthropic is a separate explicit route using
`https://api.anthropic.com` + `claude-haiku-4-5-20251001`; MiniMax is a
separate explicit/evaluated route using
`https://api.minimax.io/anthropic` + `MiniMax-M3`; legacy M3 model names and
the deprecated endpoint are rejected.

## Cost and freshness contract

- One successful refresh can make zero to four physical requests: at most one
  for each fixed `1/7/30/365d` window.
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
   yield four suppressed/no-slot rows and zero HTTP attempts.
6. Empty the queue. Enable provider calls for one canary. Verify `0..4` slots,
   HTTP starts never exceed slots, valid bilingual rows publish independently,
   normalized subjects and claim links are valid, and harvest external calls
   remain at baseline.
7. Review all four locales/windows in a real browser. Enable serving only after
   content, freshness, link, mobile geometry, and accessibility checks pass.
8. Observe +1h, +6h, and +24h. Queue depth must return to zero, oldest message
   stay below 30 minutes, and no source cycle may exceed four slots.

## Rollback matrix

| Incident | First action | Preserve |
|---|---|---|
| Cost, provider, or queue | Disable provider calls; verify worker revision; disable enqueue | Last-good database rows and serving |
| Bad content | Disable serving and provider calls | Harvester and rows |
| UI regression | Disable serving only | Worker evidence and rows |
| Worker/broker outage | Disable enqueue; pause dedicated worker if needed | Web and harvester |

Never remove the expanded parent/subject tables or compatibility view during
operational rollback. Do not delete rows or reactivate legacy worker/beat
resources. Browser traffic must remain incapable of generating work.

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
