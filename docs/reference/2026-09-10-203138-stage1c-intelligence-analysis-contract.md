# Stage 1C intelligence analysis contract

Use this contract when querying classifications, people, affiliations, job
listings, events, or opportunities created around the Stage 1C taxonomy
change. It prevents old combined categories and new exact categories from
silently appearing to mean the same thing.

## Classification populations

Every exact classification row carries its stored `contract_version`,
`taxonomy_version`, `prompt_version`, model, and outcome. Analyze these as
separate populations:

| Stored population | Exact meaning |
| --- | --- |
| Unversioned legacy | Approximate six-type dashboard data; report separately |
| `stage1-taxonomy-v1` | Ten Stage 1 meanings with five old identifier aliases |
| `stage1-taxonomy-v2` | Ten types including combined `events_opportunities` |
| `stage1-taxonomy-v3` | Thirteen types with exact `events`, `opportunities`, `job_listings`, and `personnel_changes` |

The identifier-only v1 aliases can be grouped with their v2 equivalents. For
example, `performance_comparisons` and `results_evaluations` represent the same
category meaning, so a canonical Results and Evaluations aggregate may contain
both while retaining each row's source taxonomy.

The event change is different. Taxonomy v2 `events_opportunities` cannot be
truthfully split into v3 `events` or `opportunities` without reclassification.
A broad compatibility filter may return the old combined population alongside
both v3 populations, but it must label the result as broad and include the
stored key and taxonomy version. Exact event or opportunity analysis uses only
v3 rows with the corresponding exact key.

Run the existing read-only command with an explicit half-open UTC post range:

```bash
python manage.py analyze_classifications \
  --history-policy current_definition \
  --start 2026-09-01T00:00:00Z \
  --end 2026-09-08T00:00:00Z
```

The state table contains the latest classification for each post and brand. It
is not an append-only event log. A saved aggregate records what was visible at
its observation time; a retained database dump is needed to reproduce the
underlying rows after later reclassification.

## People and affiliations

`people` stores a person identity. `people_accounts` links that identity to an
X account. `people_brand_affiliations` stores interpreted relationships, and
`people_brand_affiliation_evidence` records the source observations supporting
each relationship.

Use `person_intelligence(person_id)` from `core.intelligence_readers` as the
stable internal read shape. Its `employment_history` field includes only
`affiliation_type=employment`; advisors, investors, ambassadors, creator
partners, affiliates, and community relationships remain in `affiliations`.
The employer is a brand, with company inferred through the existing
brand-company edge. `observed_organization_name` preserves the source wording.

Treat `observed_at` as the time PushinWeight saw evidence. It is never an
employment start or end date. Effective dates remain `{value: null,
precision: unknown}` unless the source states a date. Confidence and pending
review status are part of the result and must not be hidden.

Profile evidence, a self-authored personnel announcement, and an official
announcement that names the person's X handle reuse the same account-linked
person identity regardless of which source arrives first. They may still create
separate affiliation claims when their normalized role, date, or status facts
differ; consumers must retain each claim's evidence and review state rather
than collapsing rows by name alone.

## Jobs, events, and opportunities

Use `job_listing_document`, `event_document`, and `opportunity_document` from
`core.intelligence_readers` for stable internal JSON shapes. One source post
may support several job-listing rows; count source posts, listings, and
organizations separately. Unknown organizations remain
`BrandDiscoveryCandidate` records until reviewed.

The machine-readable root-key schemas, required nested paths, and complete
examples are frozen in
`2026-09-10-203138-stage1c-intelligence-read-contract.json`. Contract tests
compare the reader output with that file so an accidental response-shape
change fails before an MCP or API client can depend on it.

Event and opportunity lifecycle is derived at read time from source-stated
facts. Callers must pass a timezone-aware `as_of`. Partial dates do not become
invented instants, so their dynamic lifecycle may remain `unknown`.

```python
from datetime import datetime, timezone
from core.intelligence_readers import event_document

document = event_document(
    event_id,
    as_of=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
)
```

Public MCP/API routes and recruiter write access are not part of Stage 1C.
These internal functions define the shape those surfaces can later expose
after access, review, and data-quality gates are approved.
