# Product-release detection and discussion windows

Last checked: 2026-10-29 23:00 JST. Code: `5e3c475e`, schema migration `0206`.
This describes the staging command and study services. Scheduled harvesting does
not invoke this detector, and the study does not generate TN or Pulse prose.

The detector finds possible releases in saved posts and collected documents. It
keeps unfamiliar publishers and products, records why a source was selected, and
leaves verification to a separate evidence review. A popular model, a small
derivative and an unfamiliar agent can all enter the inventory. The detector
makes no provider requests or additional model calls.

A completed review identifies one product/revision and its supporting claims.
An announcement, weight publication, API availability and observed use can have
different dates. Brand discussion around those dates is counted separately and
can be reused by another dossier or a later narrative request.

## Supported workflow

1. Read saved Posts and supported non-Post collection observations. Post inputs
   include original/quoted text, translations, commentary, synthesis, saved
   release labels, extracted reports and expanded entity URLs.
2. Retain release wording or saved classification/extraction signals in a
   pending `EventDossier`. A catalogue Product is optional. A source candidate
   is not yet a distinct or verified real-world release.
3. Record source-backed claims. First-person release assertions may identify an
   observed publisher; an unknown publisher can use `BrandDiscoveryCandidate`.
   The evidence claim preserves where that candidate came from.
4. Apply a source-checked assessment to identify separate products and revisions.
   A family announcement may support several dossiers. Confirmation requires
   publisher-identity evidence, account/repository-control evidence, an existing
   confirmed `CompanyAccount` relationship, and that publisher's announcement.
   An `available` result also requires its own availability claim.
5. Capture exact discussion windows for a dated brand anchor, then export a
   sortable report. Review evidence and discussion examples are different
   populations: a count of 1,000 posts does not imply 1,000 quoted sources.

Routine intake does not resolve arbitrary product names across posts or acquire
new HF/GitHub metadata. Those remain separate acquisition/identity work. The
supported study import supplies assessed identities; it is not an unattended
identity resolver. No `SourceRecord` table or model-only release table exists.

## Commands and clocks

Both commands default to read-only validation/detection. Select the intended
database through the existing environment before running them.

```bash
python manage.py detect_product_releases \
  --start 2026-08-01T00:00:00+09:00 --end 2026-10-29T19:00:00+09:00 \
  --source post --clock publication --batch-size 500 --max-batches 1

python manage.py study_product_releases /path/to/source-checked-study.json
```

`--persist` explicitly enables writes. The study command also accepts
`--discussion`, `--output /path/result.json` and `--report /path/report.html`.
Its packet uses the strict `product-release-study-v1` contract in
[`validate_assessment`](../../core/product_release_study.py). It rejects unknown
fields, invented stored-Post quotations, conflicting date precision and research
that postdates the assessment. Packets are bounded to 4 MB, 60 cases and 40
evidence assertions per case. Each case is atomic and repeatable by content.

The detection command returns `next_cursor`; pass its complete JSON value as
`--cursor` to resume. The cursor is bound to start/end, source, clock and detector
rule version. Pages are ordered by native source identity, not publication time.
It reports candidates, sampled nonmatches, input hashes, timing and coverage
limitations. A candidate count is a count of source records, not unique releases.

| Clock | Meaning |
|---|---|
| `publication` | `posts.created_at`, or a collection observation's exact `published_at`. A day-only observation cannot be assigned to an arbitrary sub-day interval. |
| `first_storage` | `posts.fetched_at`, or `collection_observations.observed_at`. |
| `collection` | A retained physical request receipt in the window; otherwise explicitly labelled first-storage fallback. Cached processing is not a new collection. |

All intervals are `[start, end)`: the start is included, the end excluded.
Timezone-free input requires `--timezone`. Current saved enrichment is used;
this is not a reconstruction of what the classifier knew at the historical time.

Non-Post loading excludes X receipt appearances already covered by Posts. It
uses the canonical archive projector to select the observation's actual object
from a captured response. Supported text fields include body, description,
content, model card, README, title and message; a non-draft GitHub release tag
is also a signal. A repository creation date, metrics or model name alone does
not prove a release. Missing, unsupported or oversized captured documents are
reported as coverage limitations. No archive body over 2 MB is interpreted.

## Existing records reused

| Record | Meaning in this workflow |
|---|---|
| `event_dossiers` | Source candidate or identified atomic release; `current_review_id = NULL` remains pending. |
| `event_dossier_sources` | A selected Post or collection observation attached to its dossier. Existing source identities are reused. |
| `event_dossier_claims` | Immutable source assertions, milestone precision, publisher evidence and assessment context. |
| `event_dossier_reviews`, `event_dossier_review_claims` | Completed interpretation and its exact accepted/uncertain/rejected evidence. |
| `product_release_details` | Existing one-to-one release extension of a completed review; uses the existing Product foreign key when resolved. |
| `brand_discovery_candidates` | Observed unresolved publisher, linked from a release-context claim. Observation does not establish ownership. |
| `collection_evidence_archives` | Retained assessment/research document. An assessment archive is labelled as such, never a fabricated HTTP receipt. |
| `measurement_subjects` | Shared identity for the measured brand. Discussion attribution is not automatically product-specific. |

The report reads claims and sources selected by the current review. Evidence
added afterward cannot silently inherit that review's confirmation. Merging
dossiers preserves original claims, copies evidence by identity and leaves an
immutable pointer to the canonical dossier. A merge cannot change event kind,
be reassigned or form a cycle.

## Four additional tables

These tables store a different fact from existing source observations and
single metric measurements: an intake disposition, an exact-window calculation,
its category counts, and a dossier's use of that calculation. This feature adds
**four tables, zero JSON columns and retires zero tables**. All four records are
immutable under database triggers. Foreign keys below use Django `PROTECT`;
PostgreSQL enforces references without cascading deletion.

### `event_dossier_intake_decisions` / `EventDossierIntakeDecision`

One evidenced intake disposition. It permits rejection of a false positive
without inventing a completed product review or confusing a non-release with a
scam. A new observation cannot silently undo a `non_release` or `scam` decision.

| Column | PostgreSQL type | Meaning |
|---|---|---|
| `id` | uuid, primary key | Application-generated UUID. |
| `event_dossier_id` | uuid, required FK | Dossier receiving the decision. |
| `supporting_claim_id` | uuid, required FK | Evidence claim; database guard requires the same dossier. |
| `recorded_at` | timestamptz, required | Application write time, defaults to now. |
| `outcome` | varchar(16), required | `pending`, `non_release`, `scam`, `superseded`. |
| `actor` | text, required | Who or which deterministic method made the decision. |
| `method_version` | text, required | Interpretation method. |
| `reason` | text, required | Evidence-based explanation. |
| `input_hash` | varchar(64), required | Lowercase SHA-256 used for repeat detection. |

`uq_ed_intake_input` makes `(event_dossier_id, input_hash)` unique.
`ck_ed_intake_outcome`, `ck_ed_intake_hash` and `ck_ed_intake_text` enforce known
outcomes, hash shape and nonempty decision text. `idx_ed_intake_latest` indexes
dossier and descending recorded time. There are no nullable columns.

### `discussion_window_snapshots` / `DiscussionWindowSnapshot`

One calculation of a subject's stored discussion within an exact interval.
The same inputs reuse the row. Corrected classifications or attribution produce
a new row; previous figures survive. No full Post-membership list is stored.

| Column | PostgreSQL type | Meaning |
|---|---|---|
| `id` | uuid, primary key | Application-generated UUID. |
| `subject_id` | uuid, required FK | `measurement_subjects.id`; current service supports brand subjects. |
| `window_start`, `window_end` | timestamptz, required | Exact half-open bounds. |
| `observed_at` | timestamptz, required | Calculation time, defaults to now. |
| `knowledge_cutoff_at` | timestamptz, required | Time of the captured current state, no later than observation time. |
| `method_version` | varchar(64), required | `discussion-window-v1`. |
| `history_policy` | varchar(24), required | `current_definition` or `historical_inclusive`. |
| `input_hash` | varchar(64), required | Fingerprint of selected identity, time, attribution and classification inputs. |
| `post_count` | integer, nonnegative, required | Distinct stored Posts in the interval. |
| `account_count` | integer, nonnegative, required | Distinct identified authors over the whole interval. |
| `count_rows` | integer, nonnegative, required | Expected number of category rows; seals calculation completeness. |
| `coverage` | varchar(24), required | `stored_only` (default) or `no_stored_posts`. Neither guarantees collection completeness. |
| `coverage_note` | text, required | Historical coverage and missing-author limitations. |

`uq_discussion_window_input` makes subject/bounds/method/history-policy/hash
unique. Checks enforce end after start (`ck_discussion_window_order`), accounts
no greater than posts (`ck_discussion_accounts`), cutoff order
(`ck_discussion_cutoff`), hash shape (`ck_discussion_hash`), known history policy
(`ck_discussion_policy`) and known coverage plus nonempty method/note
(`ck_discussion_coverage`). There are no nullable columns.

A deferred database trigger verifies `count_rows` at transaction completion,
preventing incomplete snapshots and later appended categories. Readers also
expose `window_elapsed_at_capture`; an unfinished seven-day follow-up remains
visibly partial even when stored inputs are internally consistent.

### `discussion_window_counts` / `DiscussionWindowCount`

One category count with its actual denominator and classification definition.
For example, positive sentiment under a recognized taxonomy is distinct from
an unversioned legacy sentiment estimate.

| Column | PostgreSQL type | Meaning |
|---|---|---|
| `id` | bigint, generated primary key | Category-row identity. |
| `snapshot_id` | uuid, required FK | Owning `discussion_window_snapshots.id`. |
| `population` | varchar(16), required | `all`, `exact`, `legacy`, `excluded`. |
| `dimension` | varchar(24), required | `volume`, `language`, `sentiment`, `post_type`, `audience`, `geopolitics`, `classification`. |
| `definition` | varchar(128), required | Historical taxonomy or counting definition. |
| `category` | varchar(160), required | Category code under that definition. |
| `count` | integer, nonnegative, required | Distinct posts assigned to the category. |
| `denominator` | integer, nonnegative, required | Covered population for this dimension and definition. |

`uq_discussion_category` makes snapshot/population/dimension/definition/category
unique. Checks enforce count no greater than denominator
(`ck_discussion_denominator`), known populations (`ck_discussion_population`),
known dimensions (`ck_discussion_dimension`) and nonempty definition/category
(`ck_discussion_category_text`). There are no nullable columns.

The writer separates recognized versioned Stage 1, unversioned historical
approximations and excluded states, following the existing classification
contracts. Missing audience/geopolitical assignments do not mean neutral or
zero; their denominators contain assigned Posts only. Multilabel counts need
not sum to the total population. Language retains observed provider codes.

### `event_dossier_discussion_windows` / `EventDossierDiscussionWindow`

One dossier's use of a shared calculation around an evidenced milestone.
Several products launched together can reference the same brand counts.

| Column | PostgreSQL type | Meaning |
|---|---|---|
| `id` | bigint, generated primary key | Association identity. |
| `event_dossier_id` | uuid, required FK | Owning dossier. |
| `anchor_claim_id` | uuid, required FK | Same-dossier claim with supported date precision. |
| `review_id` | uuid, nullable FK | Optional same-dossier review used for this interpretation. |
| `snapshot_id` | uuid, required FK | Reusable discussion calculation. |
| `role` | varchar(16), required | `before`, `after`, `context`. |
| `created_at` | timestamptz, required | Application write time, defaults to now. |

`uq_ed_discussion_use` makes dossier/anchor/snapshot/role/review unique, including
null reviews (`NULLS NOT DISTINCT`). `ck_ed_discussion_role` checks the role.
Database guards require same-dossier claim/review ownership and a dated anchor.
All foreign keys have their Django-generated indexes in addition to the named
unique indexes described above.

## Discussion reuse and evidence selection

`capture_windows(brand_id, windows)` accepts 1..3,000 exact intervals in one
consistent database read. It serializes work for the same brand before opening
that read. A busy brand returns a retryable error. Capturing the same interval
still reads its inputs to validate the fingerprint; saved-row reuse does not
mean zero calculation cost or a measured 95% speedup.

The study preset captures 168 two-hour bins, 16 fifteen-minute bins near the
anchor and two exact seven-day side totals: 186 snapshots before reuse.
Date-only anchors use an explicit UTC-midnight study convention. Another anchor,
including availability, can be captured independently. Exact whole-window
author counts are computed from the union of Posts, never summed across bins.

`discussion_packet(snapshot_id, source_limit=16)` checks that saved inputs still
match, then selects up to 40 representative Posts. It balances the four time
quarters, then language/sentiment strata, with at most two Posts per identified
account. It returns selected source text/names/URLs and the full population
counts. These are inspectable examples, not an exhaustive thematic explanation.
If classifications or attribution changed, capture a new snapshot first.

The report orders releases by the declared significance policy: primary,
derivative, then ablation/limited variant; product kind and change size add
smaller adjustments. Unknown lineage remains unranked. Fame and posting volume
do not enter this score. Brand discussion is displayed separately and shared
family-wide counts must not be summed as independent product attention.

## Source map and operation

- [Models](../../core/models.py) and [migration 0206](../../core/migrations/0206_product_release_study.py) own physical storage and database guards.
- [Intake](../../core/product_release_intake.py), [source readers](../../core/product_release_sources.py) and [milestones](../../core/product_release_milestones.py) own candidate signals and source clocks.
- [Persistence](../../core/product_release_pipeline.py) and [canonical dossier writers](../../core/event_dossiers.py) own evidence, merges and reviews.
- [Study import](../../core/product_release_study.py), [discussion windows](../../core/discussion_windows.py) and [report](../../core/product_release_report.py) own the supported study workflow.
- [Classification contract](../analysis/2026-09-09-112957-classification-analysis-contract.md) owns exact/legacy counting semantics.

Rollback means stop using the additive commands/readers and retain the saved
study history. Reversing the migration deletes its new tables and is not a
data-preserving rollback. The old whole-schema reference is a dated snapshot;
its earlier migration/table totals do not describe this revision.
