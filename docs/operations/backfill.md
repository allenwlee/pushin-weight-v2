# Historical harvest recovery

Use `python manage.py backfill` to recover posts from a historical UTC range.
The command uses the current seven-call harvester plan and the shared fetch,
attribution, persistence, translation, and classification pipeline. Progress is
stored in PostgreSQL as a `BackfillJob` with job-owned
`HarvestBacklogWindow` rows; local files are not recovery state.

The command has two selection modes:

- `--detect-gaps` finds consecutive, fully elapsed 15-minute buckets with no
  `Post.created_at` values. The default minimum run is 60 minutes. This is a
  conservative way to recover obvious downtime while avoiding unnecessary
  TwitterAPI spend.
- Without `--detect-gaps`, the entire explicit range is recovered. Use this for
  a known partial outage because a bucket containing even one post is not an
  automatic gap.

## Preview a seven-day range

Always preview first. This reads PostgreSQL and the repository pricing source,
but does not create a job or construct a provider client.

```bash
python manage.py backfill \
  --since 2026-08-10T00:00:00Z \
  --until 2026-08-17T00:00:00Z \
  --detect-gaps \
  --dry-run
```

The preview reports:

- inferred UTC intervals and the partial-outage limitation;
- current call IDs and work-row fan-out;
- remaining durable state when the job already exists;
- a first-pass TwitterAPI credit and USD range;
- the next invocation's request ceiling.

The estimate is a range. Every request is one page with at most 20 returned
tweets. A dense interval may be truncated and require more time-slice requests;
the work row remains pending with a narrower upper bound.

## Execute or resume automatic recovery

Run the same selection arguments without `--dry-run`. `--batch-size` is a hard
TwitterAPI search-request budget, not a planned-call count. The command disables
transport-level TwitterAPI retries, so the default of three means at most three
actual advanced-search HTTP attempts. A failed durable row remains available to
a later invocation. `--max-llm-calls` is a shared pre-call ceiling across
relevance, translation, classification, LLM-client retries, language repair,
and classifier fallback; the default is 20.

```bash
python manage.py backfill \
  --since 2026-08-10T00:00:00Z \
  --until 2026-08-17T00:00:00Z \
  --detect-gaps \
  --batch-size 3 \
  --max-llm-calls 20 \
  --pause 5
```

Repeat the exact command to resume. Job identity includes the requested range,
selection mode, bucket thresholds, and brand filter. The current call-plan
signature is checked before any provider request; query-plan drift stops the
run rather than remapping old work silently.

Each request acquires the shared harvest writer lock, completes one replay step,
and releases the lock before `--pause`. Lock contention leaves the work pending
for the next invocation. Backfill never reads or advances live `CallState`
cursors, refreshes one-shot metrics, or dispatches trend headlines.

If provider credentials are unavailable or a request repeatedly fails, the row
eventually becomes `quarantined`. Restore the provider first, then resume only
the quarantined rows belonging to that exact job:

```bash
python manage.py backfill \
  --since 2026-08-10T00:00:00Z \
  --until 2026-08-17T00:00:00Z \
  --detect-gaps \
  --retry-quarantined \
  --batch-size 3
```

Job identity includes all selection arguments, so repeat `--bucket-minutes`,
`--min-gap-minutes`, and `--brands` too when they differed from the defaults.
Ordinary resume processes pending or expired claimed rows; quarantined rows are
eligible only with the explicit `--retry-quarantined` flag.

## Recover a known partial outage

Omit `--detect-gaps` to select the whole interval even if some posts exist:

```bash
python manage.py backfill \
  --since 2026-08-16T03:00:00Z \
  --until 2026-08-16T07:30:00Z \
  --dry-run

python manage.py backfill \
  --since 2026-08-16T03:00:00Z \
  --until 2026-08-16T07:30:00Z \
  --batch-size 3
```

The upper bound is exclusive. Minute-precision, second-precision, `Z`, and
explicit-offset ISO-8601 forms are accepted. A naive value is interpreted as
UTC for compatibility.

Use `--brands deepseek,qwen` only when the recovery should retain the existing
brand-filtered planner behavior. Repeat the same brand list on status, resume,
and reset commands because it is part of job identity.

## Status and reset

Status is read-only. Repeat the selection arguments exactly:

```bash
python manage.py backfill \
  --since 2026-08-10T00:00:00Z \
  --until 2026-08-17T00:00:00Z \
  --detect-gaps \
  --status
```

The durable row states mean:

- `pending`: eligible for another bounded request;
- `claimed`: currently owned, or recoverable after its claim expires;
- `completed`: fully drained and retained as an audit row;
- `quarantined`: repeated failures reached the existing attempt/age ceiling;
- `waived`: operator-owned terminal state outside the normal command flow.

Preview an exact reset, then run it without `--dry-run`:

```bash
python manage.py backfill \
  --since 2026-08-10T00:00:00Z \
  --until 2026-08-17T00:00:00Z \
  --detect-gaps \
  --reset \
  --dry-run

python manage.py backfill \
  --since 2026-08-10T00:00:00Z \
  --until 2026-08-17T00:00:00Z \
  --detect-gaps \
  --reset
```

Reset takes the shared writer lock, then deletes only that job and its owned
windows. It cannot race a replay request, delete scheduled recall debt, or
delete another recovery job. Lock contention defers the reset without mutation.

Scheduled quarantined recall debt remains a separate workflow and never claims
job-owned rows. It uses the same one-request lock boundary and transport-retry
policy as job recovery. Range, detection, brand, reset, and job-retry flags are
rejected in this scheduled-ledger-only mode:

```bash
python manage.py backfill --quarantined --dry-run
python manage.py backfill --quarantined --batch-size 1
```

## Dense-window limitation

The provider returns at most 20 tweets per request. When a page is full, the
backfiller time-slides toward older results and keeps the durable row pending.
If more than 20 matching tweets have the same oldest timestamp, second-level
time bounds may make no further progress. The existing attempt ceiling then
quarantines the row rather than marking incomplete coverage as complete. Review
the range manually before retrying or resetting that job.

## Production boundary

This command does not deploy code or modify Render scheduling. Run production
recovery only after the intended SHA has completed the repository's Ollija
release and owner-approval workflow. If a harvest incident is ongoing rather
than historical, follow `docs/operations/pause-and-resume-harvest-cron.md`
before live diagnosis. Do not resume the cron without owner authorization.
