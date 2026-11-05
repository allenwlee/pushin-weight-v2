---
module: harvest
date: 2026-07-24
problem_type: architecture_pattern
component: service_object
severity: high
last_updated: 2026-11-05
applies_when:
  - "Recovering past X posts for a bounded time window through the existing harvest pipeline"
  - "Wiring translation and classification into historical X post recovery with spend caps"
  - "Running a long X post backfill as a Render one-off without disturbing the 15-minute harvest"
symptoms:
  - "Need X posts from a past window that the 15-minute harvest missed"
  - "LLM classification of recovered posts is slow and expensive and needs caps"
  - "A long recovery outlives one Render one-off job and must resume"
root_cause: incomplete_setup
resolution_type: tooling_addition
related_components:
  - background_job
  - tooling
tags:
  - x-post-backfill
  - backfiller
  - llm-classifier
  - harvest-cycle
  - cycle-runner
  - django-management-command
  - data-pipeline
  - render-deploy
---

# X post backfill: date-bounded historical post recovery through the shared harvest pipeline

> **Which backfill this is.** This learning covers the **X post backfill**:
> `python manage.py backfill` (and the month campaigns run by
> `python manage.py run_backfill`). It searches X through TwitterAPI.io for a
> past window and writes Posts into the production database through the same
> `CycleRunner` as the 15-minute harvest. It is **not** the **Backfiller data
> source** (`python manage.py backfiller_data_source`), which collects numeric
> provider measurements such as Hugging Face downloads, Arena ratings and
> OpenRouter tokens into the separate `xbackfiller` database. It is also not a
> **Backfill transfer**, which moves those reviewed measurements into
> production. For those, read
> [Replay reviewed backfill measurements into production](../data-migration/2026-11-05-150150-replay-reviewed-backfill-measurements-into-production.md)
> and `docs/reference/collection-jobs.md`. `CONCEPTS.md` defines all three terms.

## Context

The production harvest runs every 15 minutes as the Render cron
`pushinweight-harvest` (`python manage.py run_cycle --scheduled`, defined in
`render.yaml`). Celery beat is not a production scheduler. Each cycle plans a
set of TwitterAPI calls, fetches recent posts, attributes them to brands,
persists them through the Django ORM, and then translates and classifies them.
That forward-moving window cannot reach back into the past. When the harvest
misses a window (a deployment gap, an outage, a query defect), `run_cycle`
alone cannot recover it.

The X post backfill exists for that case. Its durable lesson is architectural:
recovery reuses the harvest pipeline rather than duplicating it, runs inside
explicit spend and time caps, and stays out of the live harvest's way.

## Guidance

### The X post backfill is a thin orchestration layer over `CycleRunner`

`monitor/management/commands/backfill.py` does not contain its own fetch,
attribute or persist logic. It sets a fixed time window and caps, then drives
the same `CycleRunner` the scheduled harvest uses. Two seams make this work:

- **`plan_calls_for_cycle(cfg)`** in `monitor/cycle.py` is the one call planner
  shared by `CycleRunner` and the backfill command. Both pass the `Config`
  loaded by `x_monitor.config.load_config`, so the scheduled harvest and the
  backfill plan the same queries for the same brands.
- **`_backfill_call_ids`** on `CycleRunner.__init__` narrows the full plan to
  the selected call IDs (for example `B1`), so the backfill can run one call at
  a time through the standard cycle machinery.

The backfill selects only the core logical calls (`x_monitor.config.VALID_CALL_IDS`).
Optional discovery searches have their own evidence and budgets and do not
silently join a recovery. Historical Call A is refused unless a frozen
account-population manifest exists; select B/C calls for bounded recovery.
`--brands` must name enabled models and drops Call A.

### Time window

`--since` and `--until` are both required (except for `--quarantined` replays).
They are fixed bounds in UTC, `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`, so the run
can resume against the same window. The command threads them through Django
settings that `CycleRunner` reads:

```
backfill._parse_iso()
  → settings.X_MONITOR_CYCLE_SINCE_TIME / X_MONITOR_CYCLE_UNTIL_TIME (epoch)
  → settings.X_MONITOR_CYCLE_LIMIT_PER_CALL / X_MONITOR_CYCLE_MAX_PAGES_PER_CALL
  → CycleRunner fetch → TwitterAPI search with since_time/until_time
```

`--query` overrides the frozen historical query for exactly one brand and one
B/C call. It must omit time operators, because the command's bounds own the
interval. The command rejects a query whose length, after the appended
`since_time:`/`until_time:` window, exceeds 512 **characters**. Since
2026-11-04 the provider has silently returned nothing for queries over 512
UTF-8 **bytes** including that window. A Chinese-heavy query can pass the
character check and still come back empty, so count bytes yourself.

### Explicit caps, not estimates

The July design estimated `max_results` and `max_pages` from a posts-per-day
baseline. That estimator is gone. `--safety-margin` survives only as a
validated, deprecated option. Every invocation now runs under explicit caps:

| Option | Default | Meaning |
| --- | --- | --- |
| `--max-results` | 100 | Per-unit result cap; must be a multiple of 20 (complete pages) |
| `--max-pages` | 5 | Per-unit page cap |
| `--max-api-requests` | 10 | Invocation-wide HTTP request cap |
| `--max-llm-calls` | 60 | Invocation-wide model transport cap, including retries |
| `--run-seconds` | 300 | Invocation deadline; at most 780 outside `--batch` |
| `--slice-minutes` | 15 | Fixed unit duration for ordinary runs |
| `--batch-size` | 1 unit (or the HTTP allowance with `--batch`) | Work steps per invocation |

Caps do not grow with the window. A long window with default caps simply needs
more invocations, or `--batch`, or a frozen collection job.

### Staying out of the live harvest's way

Ordinary runs process one 15-minute unit per invocation by default. Before each
unit, the command checks the time to the next 15-minute slot
(`_seconds_to_next_slot`). If the unit's remaining deadline plus a 120-second
reserve would not fit before that slot, it defers instead of competing with the
cron. Each unit also takes `harvest_writer_lock(execution_mode="backfill")`
(`monitor/run_lock.py`) and stops if the shared Post writer is busy. The
`--pause` seconds between units are spent without holding the lock.

`--batch` collects a whole historical window as one unit. Each step is one
20-result page with a committed cursor, so the unit repeats until it drains.
It skips the slot wait but still takes the writer lock. It does no inline model
work (`--max-llm-calls` and `--enrichment-limit` are forced to 0).

The backfill uses TwitterAPI's on-demand credential lane:
`CycleRunner.twitterapi_credential_purpose` returns `ON_DEMAND` for backfill and
manual cycles and `SCHEDULED` only for the cron. Run long recoveries as a Render
one-off job from the deployed `pushinweight-harvest` revision (see
"Historical X batch jobs and safe handover" in `docs/deploy/render.md`). Never
run them inside the live web service, and never pause the cron to make room.
AGENTS.md makes live-operation continuity a release invariant.

### Resumability: host checkpoints for short runs, PostgreSQL jobs for campaigns

Ordinary runs checkpoint to
`data/backfill/<since_epoch>-<until_epoch>[-<scope_hash>].json`. The scope
hash separates different brand and call selections over the same window. Fixed
bounds, policy and limits must match the checkpoint to resume. `--status`
prints it, `--reset` discards it, `--retry-blocked` retries an anomalous unit
after its cause is fixed, and `--state-dir` points at a durable directory on
the executing host.

Render one-off jobs do not share a filesystem, so a host checkpoint dies with
its job. Campaigns that span invocations use frozen collection jobs instead:

- `--plan-collection-job KEY` freezes a reusable current-policy historical job
  (`--dry-run` prints it only).
- `--collection-job JOB_UUID` executes that frozen job. Progress, page
  checkpoints and provider evidence live in PostgreSQL through
  `monitor/backfill_collection.py`. Its adapter accepts `B1`–`B3` and `C1`–`C4`
  and requires the on-demand credential.
- `run_backfill --month-recipe` runs month campaigns in phases (see
  `docs/deploy/render.md`).

### Translation and classification of recovered posts

`CycleRunner._run_post_fetch` runs the same two stages for backfilled and
scheduled posts:

1. **Translate** with `x_monitor.translator.translate_batch_pragmatics`.
2. **Classify** with `x_monitor.attribution.classify_batch_pragmatics_full`,
   after converting Django `Brand` rows to the classifier's `BrandRow` shape.
   Per-brand results are stored as `PostBrandSignal` rows.

Clients are role-specific: `build_translator_client_from_env` and
`build_classifier_client_from_env` in `x_monitor/reattribute.py`. Backfill
cycles pass `deepinfra_key_env="DEEPINFRA_ON_DEMAND"`, so recovery spend uses
the on-demand DeepInfra credential rather than the scheduled one.

Guardrails:

- `X_MONITOR_LLM_PAUSE_SECONDS` (default 1 s) spaces classifier request starts.
- `--max-llm-calls` caps model transport for the whole invocation, retries
  included. Remaining posts stay unenriched for a later invocation.
- Concurrency is bounded by `enrichment.translation_concurrency` and
  `enrichment.classification_concurrency` in `config.yaml`. It is not
  unbounded, and it is no longer strictly sequential.
- `--enrichment-limit` (default 5) freezes the small cohort of recovered posts
  that an ordinary run enriches inline.

To re-enrich posts that are already stored, do not re-fetch them from X. Use
`--enrich-native` (native model batches) or `--enrich-direct` (ordinary
DeepInfra calls, `--enrichment-concurrency` default 32). Both make zero X
requests and require `DEEPINFRA_ON_DEMAND`. `--enrichment-control
status|pause|resume` inspects or controls a collection job's enrichment.

### Build and deploy notes from the original build

- `plan_calls_for_cycle` takes no per-call limits. Per-call result and page
  caps travel through the `X_MONITOR_CYCLE_*` settings shown above. That is
  still how the command passes them.
- The July i18n workarounds (forcing `LANGUAGE_CODE="en"` and skipping
  `compilemessages`) are superseded. `project/settings.py` uses `zh-hans`, and
  `build.sh` runs `compilemessages`. See the i18n debugging journey under
  Related.

## Why This Matters

Duplicating fetch, attribute and persist logic inside the backfill command
would let the two copies drift: a fix to `CycleRunner` would not reach
recovery, and every pipeline change would need testing at two entry points.
Keeping one planner (`plan_calls_for_cycle`) and one runner (`CycleRunner`),
with the backfill only setting bounds, caps and checkpoints, keeps scheduled
and historical collection on one source of truth. The repo enforces the same
rule as M7 in `.claude/skills/avoiding-recurring-mistakes/SKILL.md`.

Sharing the pipeline is not the same as sharing collection scope. Proving that
a backfill found what the scheduled harvest would have found is a separate
claim; see the coverage learning under Related.

Coexistence matters as much as reuse. Slot-aware deferral, the shared writer
lock and on-demand credentials let a recovery run alongside the live harvest
without stealing its slot, its writer or its credit lane. That is what lets
recovery proceed without the planned harvest gaps AGENTS.md forbids.

## When to Apply

**Use the X post backfill when:**

- A deployment, outage or query defect left a window of X posts unharvested.
- You need X posts from a specific past window for analysis.

**Use the regular harvest** (the `pushinweight-harvest` cron running
`run_cycle --scheduled`) for ongoing, forward-looking collection. The backfill
is not a scheduler.

**Use something else when:**

- The posts are already stored and only need translation or classification:
  use `--enrich-native` or `--enrich-direct` instead of re-fetching.
- The data is numeric provider measurements (Hugging Face, Arena, OpenRouter,
  OpenCode): that is the Backfiller data source and Backfill transfer, not this
  command.
- The window spans many invocations or Render jobs: freeze a collection job
  (`--plan-collection-job`) rather than relying on a host checkpoint file.

## Examples

These mirror the command's own usage block in
`monitor/management/commands/backfill.py`.

```bash
# Plan only
python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 --dry-run

# One scoped unit: one brand, one call
python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 \
  --brands qwen --call-ids B1

# Bound the whole invocation, including model calls and HTTP retries
python manage.py backfill --since 2026-08-09T00:00Z --until 2026-08-09T00:15Z \
  --brands qwen --call-ids B1 --max-api-requests 10 --max-llm-calls 60

# Resume: re-run the same command; the scoped checkpoint picks up where it stopped
python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 \
  --brands qwen --call-ids B1

# Start the same scope over
python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 \
  --brands qwen --call-ids B1 --reset

# Whole-window historical collection with page checkpoints and no inline model work
python manage.py backfill --batch --since 2026-08-01 --until 2026-08-31 \
  --call-ids B1,B2,B3,C1,C2,C3 --max-api-requests 500 --run-seconds 3600
```

## Related

- [Prove X backfill coverage separately from processing completion](../workflow-issues/2026-10-16-131500-backfill-coverage-and-completion.md): finishing searches and enriching saved posts do not prove historical coverage.
- [Replay reviewed backfill measurements into production](../data-migration/2026-11-05-150150-replay-reviewed-backfill-measurements-into-production.md): the Backfill transfer for the separate Backfiller data source. It shares the word "backfill" but not this command.
- `docs/deploy/render.md`, "Historical X batch jobs and safe handover": Render one-off execution, month campaigns and enrichment phase commands.
- `docs/reference/collection-jobs.md`: collection jobs, runs and checkpoints.
- `docs/solutions/workflow-issues/django-i18n-locale-toggle-debugging-journey.md`: why the July i18n workarounds were superseded.
