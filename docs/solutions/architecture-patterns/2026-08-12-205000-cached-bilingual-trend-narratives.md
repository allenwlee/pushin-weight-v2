---
module: monitor
tags: [trend-narrative, celery, postgres, cache, llm]
problem_type: architecture-pattern
---

# Cached bilingual trend narratives

The V22 headline is a shared, fixed-window product projection. The application
must choose the trend facts from PostgreSQL before any provider call; the model
only turns that closed aggregate packet into one validated English body and one
validated Simplified Chinese body.

`TrendNarrativeVersion` is both the durable serving cache and the outbound-call
ledger. A `(source_cycle_id, window_days)` row consumes at most one irreversible
provider slot. A current published row survives failed or disabled refreshes,
and publication is serialized per window by a PostgreSQL advisory lock and
ordered by `(publication_epoch, facts_as_of)`.

The harvest command dispatches one short-lived envelope after an eligible
committed cycle. The dedicated `trend-narratives` worker has concurrency and
prefetch set to one, automatic retries disabled, and a Redis broker watermark
that coalesces an outage backlog before it reaches the durable ledger. Redis is
transport coordination only; PostgreSQL remains authoritative for facts,
history, publication, and call accounting.

Browser requests read the persisted current row through the existing chart
payload. They never enqueue generation or import the provider boundary. The
three controls are independent and fail closed: serving, enqueueing, and
provider calls. Rollback disables controls and keeps the table and last-good
copy intact.
