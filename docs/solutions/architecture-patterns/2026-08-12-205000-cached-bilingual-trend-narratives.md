---
module: monitor
tags: [trend-narrative, celery, postgres, cache, llm, time-series, evidence]
problem_type: architecture-pattern
---

# Cached bilingual trend narratives

The V22 headline is a shared, fixed-window product projection. PostgreSQL must
choose and bound the trend facts before any provider call; the model only turns
that closed aggregate packet into validated English and Simplified-Chinese
headlines, observations, subjects, and fact-linked claims.

The essential analytical pattern is two-resolution measurement. Coarse,
zero-filled arrays describe the full trajectory without overflowing the model
window. Fine arrays detect short exceptional episodes before projection, so a
one-day spike can survive inside a year-long analysis even though the provider
receives only monthly-scale points. Engagement is included only where the
metrics refresh was observed by the snapshot cutoff; missing engagement remains
unknown rather than becoming zero.

Candidate selection is family-diverse and bounded. Volume, engagement,
post-type, discourse, sentiment, and nationalism each seed a ranked stream;
round-robin merge yields at most six candidates. A small evidence set can add
concrete event context or one unresolved off-list entity, but that entity is
explicitly evidence-only until harvesting/entity resolution can measure it.
Every narrative claim links back to supplied candidates, aggregate families,
and optional evidence IDs.

`TrendNarrative` (`trend_narratives`) is both the durable serving cache and the
outbound-call ledger. `TrendNarrativeSubject`
(`trend_narrative_subjects`) normalizes one or two measured/evidence-backed
identities while retaining snapshots across brand/product deletion. A
`(source_cycle_id, window_days)` row consumes at most one irreversible provider
slot. A current published row survives failed or disabled refreshes, and
publication is serialized per window by a PostgreSQL advisory lock and ordered
by `(publication_epoch, facts_as_of)`.

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

The full implementation/tuning contract, including the literal prompt, bucket
schedules, provider route, schema columns, and verification commands, lives in
[`docs/reference/headline-trend-narratives.md`](../../reference/headline-trend-narratives.md).
