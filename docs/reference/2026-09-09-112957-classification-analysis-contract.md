# Classification analysis contract

Use the shared classification analysis command when comparing stored Stage 1
results across taxonomy versions or when explicitly including the older,
unversioned dashboard population. The command is read-only and makes no model
call.

```bash
python manage.py analyze_classifications \
  --history-policy current_definition \
  --start 2026-09-01T00:00:00Z \
  --end 2026-09-08T00:00:00Z
```

Repeat `--brand` to restrict the query to known, non-sentinel brands:

```bash
python manage.py analyze_classifications \
  --history-policy historical_inclusive \
  --start 2026-09-01T00:00:00Z \
  --end 2026-09-08T00:00:00Z \
  --brand minimax --brand qwen
```

`--history-policy`, `--start`, and `--end` are required. Timestamps must be
explicit UTC (`Z` or `+00:00`), and the interval is always half-open:
`Post.created_at >= start AND Post.created_at < end`. The output says
`range_basis: post_created_at`. `classified_at` appears only in provenance
summaries and never selects rows or infers a classification era.

`current_definition` reports only recognized, versioned Stage 1 state. A
recognized row has contract `stage1-v1`, taxonomy `stage1-taxonomy-v1`,
`stage1-taxonomy-v2`, or `stage1-taxonomy-v3`, and outcome `classified` or
`context_missing`. The two
outcomes remain separate. Pending or failed post-level enrichment state cannot
be coerced into either outcome. A state with another contract, taxonomy, or
outcome is excluded and counted; its presence also blocks all unversioned
fallback for that post-brand. Current null scalar judgments remain null.

`historical_inclusive` leaves the complete `exact_stage1` object unchanged and
adds `legacy_unversioned_approximate`. The legacy population contains only
post-brand pairs with no classification-state row. It is approximate because
its definitions predate versioned Stage 1. Its product-label availability is
the string `unavailable`; zero would incorrectly claim those labels were
measured.

The legacy six-key source vocabulary is pinned to
`af272b6fe0b43be3276429792508749b9ddc8194:monitor/views.py`:

| Stored key | Canonical output key |
| --- | --- |
| `buzz_releases` | `releases_updates` |
| `hands_on_usage` | `hands_on_usage` |
| `performance_comparisons` | `results_evaluations` |
| `feedback_questions` | `questions_requests` |
| `advertising_marketing` | `advertising_marketing` |
| `event_announcement` | `events_opportunities` |

The result also carries the complete identifier-only shared crosswalk. It
canonicalizes stored aliases before distinct counts and grouping. One post-type
or product-label membership is one distinct
`(post_id, brand_id, canonical_key)` tuple. `unique_posts` counts posts in its
named population. `classified_post_brand_denominator` counts distinct exact
post-brand states whose outcome is `classified`; `context_missing` has its own
count and cannot enter that denominator. Exact provenance remains grouped by
the stored contract, taxonomy, prompt, model, and `classified_at` range.

With `current_definition`, matching unversioned pairs are reported under
`exclusions.legacy_unversioned_omitted`; they do not enter exact totals. With
`historical_inclusive`, their approximate totals are reported in the separate
legacy section. Unknown edge keys and unrecognized or invalid state are always
explicit exclusions. A no-state post type outside the pinned six-key legacy
vocabulary, and every no-state product-label edge, appears under
`unversioned_edges_outside_legacy_population`; these rows cannot silently make
the result look empty or broaden the historical approximation.

Posts whose `created_at` is null cannot belong to a requested time interval.
Their separate count uses scope
`brand_scope_all_dates_missing_timestamp`: all missing-timestamp post-brand
pairs under the optional brand scope, independent of the requested date range.
Do not describe that count as in-range.

Successful output uses schema `classification-analysis/v1`. The shared query
service observes the Render deploy revision or local Git HEAD itself and states
whether a local worktree was dirty. It records PostgreSQL's statement timestamp
under `observation.observed_at`, outside the SHA-256 query identity. An
archive nested inside another repository does not borrow that parent's HEAD:
the application directory must be Git's own top level or the revision is
reported unavailable with `source_revision_parent_repository_ignored`. An
unavailable or invalid revision is explicit and warned. Schema, aggregate
ordering, and query identity are deterministic; a fresh database observation
has a fresh timestamp and may have different counts. A valid query with no
included rows exits zero with
`status: empty`; exclusion metadata can still show that stored data was omitted
by policy. Invalid policy, range, brand, schema, or crosswalk input writes one
structured error document to stderr, writes no partial counts to stdout, and
exits 2. A database query failure follows the same no-partial-output rule and
exits 3 with a generic safe error.

`PostBrandClassificationState` is a latest-state table, not an event ledger.
The source revision and query identity reproduce the query definition. The
saved JSON preserves the aggregates observed at its statement timestamp, but
it is not a database snapshot. Reproducing the underlying rows later requires
a separately retained database snapshot, and later reclassification may have
replaced the state.

Taxonomy-v2 `events_opportunities` is retained as an exact historical combined
category. It is not an identifier alias for taxonomy-v3 `events` or
`opportunities`. Exact event/opportunity analysis must filter to taxonomy v3;
a compatibility query that includes all three keys must report the stored key
and taxonomy for every row or group. See
`docs/reference/2026-09-10-203138-stage1c-intelligence-analysis-contract.md`.
