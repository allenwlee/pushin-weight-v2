# Rare-type operator read and replay contract

The combined rare-type lane saves paid X results before any Jev decision,
classification, or extraction. Operators can therefore inspect each stage and
retry selected saved hits without buying the X search again.

The machine-readable output contract is
`2026-09-24-220000-rare-type-intelligence-read-contract.json`. Counts use
different denominators deliberately: raw provider rows, normalized hits,
distinct persisted posts, classified hits, extracted hits, visible hits,
canonical records, and evidence rows are never interchangeable.

## Inspect a run or post

```bash
python manage.py rare_type_search_status --run-id 123 --json
python manage.py rare_type_search_status --post-id 1900000000000000000 --json
```

Run status includes the immutable query identity and rendered query, separate
TwitterAPI credit and Jev dollar accounting, gate states, post-processing
states, latency milestones, and coverage gaps. It omits raw post text,
credentials, and provider response bodies.

`core.intelligence_readers.model_release_document()` reports one canonical
release separately from its evidence and distinct source-post counts.
`rare_type_post_document()` keeps categories scoped to their Brand or unresolved
candidate and exposes evidence-backed Products separately from unresolved
Product proposals. A category is not a guessed Product identity.

Successfully classified posts appear through the existing authenticated feed
and its `releases_updates`, `events`, `opportunities`, `job_listings`, and
`personnel_changes` filters. Unresolved Product work is private at
`/product-review/`; the status/read functions remain the detailed provenance
surface for canonical records and pending work.

## Replay saved hits

Preview is the default and performs no writes or provider construction:

```bash
python manage.py replay_rare_type_hits 41 42 --json
```

A committed replay requires both the environment gate and an explicit bound
for translation plus classification transport:

```bash
RARE_TYPE_REPLAY_ENABLED=1 python manage.py replay_rare_type_hits \
  41 42 --commit --max-llm-calls 6 --json
```

The command accepts at most 20 explicit hit IDs and never constructs a
TwitterAPI client. Jev retains its separately persisted per-cycle and daily
budgets. Targeted extraction retains `max_calls_per_cycle`. Hugging Face
verification is not drained by replay. Every enrichment, maintenance,
reconciliation, and targeted-retry selector is restricted to the selected
hits' linked post IDs, so unrelated pending or failed work is unchanged.
