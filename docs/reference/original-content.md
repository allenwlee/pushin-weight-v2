# Original authored content and packet preparation

OriginalContent is PushinWeight's own writing; a collected `Post` remains source
material. Each saved language/version owns its headline, byline, optional body,
producing-call reference and exact cited posts. Counts measure distinct posts,
not independent publishers or verified confirmations.

Compatibility delivery retains physical names and Python import aliases. The
source join is the only new table. Full column, key and constraint details for
all seven models below are in the linked schema sections, verified against
models/migration state through `0078_original_content_workflow_shape`.

| Model | Physical table | One record means |
| --- | --- | --- |
| OriginalContent | [brand_trend_narratives](db-schema.md#table-brand_trend_narratives) | One output version or held headline outcome. |
| OriginalContentText | [brand_trend_narrative_texts](db-schema.md#table-brand_trend_narrative_texts) | One saved language/version with its public UUID. |
| OriginalContentSource | [original_content_sources](db-schema.md#table-original_content_sources) | One distinct cited post for that text, in citation order. |
| OriginalContentRun | [trend_narrative_runs](db-schema.md#table-trend_narrative_runs) | One evidence/dispatch execution, cutoff, configuration and claim. |
| OriginalContentCall | [trend_narrative_provider_calls](db-schema.md#table-trend_narrative_provider_calls) | One reserved provider attempt and its completion/uncertainty state. |
| OriginalContentSelection | [trend_narrative_visible_runs](db-schema.md#table-trend_narrative_visible_runs) | A selected all-brand window or exact featured text. |
| ContentPicture | [editorial_pictures](db-schema.md#table-editorial_pictures) | A generic source/derivative attachment with optional text/run references. |

`TrendNarrative`, trend work slots/demands, staff media objects and people media
remain separate. Pictures retain atomic commentary and other generic attachment
kinds. Image selection/generation metadata does not become a post citation.

## Versions, workflows and citations

Stable keys identify producing code: `brand-window`, `social-brief` and
`development-report`, currently displayed as trend headlines, Chatter and Pulse.
`editorial-dispatch` is shared selection: its editor call is charged once.
`media-derivative` identifies media work. Display labels do not define budgets.

Each imported editorial edition becomes its own parent/text; its UUID becomes
text `public_id`. Languages can have different revisions/citations. Bilingual
headline parents retain grouped locale rows and integer IDs; headline texts
receive deterministic UUIDs. Story UUIDs are version snapshots, with no new
story table.

Sources protect actual `Post` relationships and save URL, author and projected
source hash. Unique text/post and text/position constraints preserve distinct
citation order. `hash_basis` distinguishes writing-packet hashes, known legacy
projections and unavailable legacy hashes. Missing posts, invalid URLs and
unresolved old evidence aliases block reconciliation; no placeholders are
created. All safe HTTP(S) URLs survive shared reads, including non-X sources.
Fact-only headlines can have zero post citations with aggregate facts in audit.

Publication saves copy, sources, verification and selection in one transaction.
Fresh text requires a matching completed producing call. Unknown legacy
producers are labeled instead of guessed. Compatible writes save the same
accepted result to both stores without another provider call. Trend activation
still requires a complete all-brand window and preserves last-good publication.

## Calls and budgets

Attempts retain actual request hashes, stage, provider/model, profile/configuration
version, UTC day and pessimistic reservation. Reservation is a ceiling, not an
invoice. Unknown historical usage/completion metadata stays marked as legacy.
Fresh calls require their real request identity.

Reservations serialize under a short PostgreSQL lock per scope/day and the
existing global in-flight guard. Headline and editorial policies stay separate.
Legacy counters are rollback shadows: do not add them again to shared calls.
Proven external spend lives in zero-send `reservation-carryforward` run outcomes,
included exactly once by `budget_totals("editorial", utc_day)`. These receipts
are not invented calls. Uncertain sends stay charged and cannot automatically
resubmit.

## Code-only packet-maker

[`packet_maker.py`](../../monitor/packet_maker.py) accepts a typed profile with
key, version, explicit timezone cutoff, byte bound and serialized settings.
Adapters collect evidence, apply existing selection/transformations and optionally
project it. The engine collects once, checks UTF-8 bytes, freezes JSON and returns
a reuse key. It imports no provider client, reserves nothing and sends nothing.
Each caller receives its own working copy of the immutable packet.

Headlines keep repeatable-read, read-only snapshots and fixed-window facts.
Editorial discovery keeps its 24-hour sample/seven-day context. Both story
writers share relevance-led name/phrase retrieval across months, including
explicit timeout/omission reports. Trimming removes whole rows; oversized
required anchors produce a hold rather than sliced passages.

Reuse includes source/enrichment revisions and settings. Editorial revisions
cover stored source/metrics, enrichment and classification; corrected staff roles
appear in the people packet. The advancing clock alone is not new evidence for
unchanged-input checks. Queries exclude future created/fetched posts. Current
affiliation observations remain labeled as observed now.

Selection, ranking, critics, routes, schedules and caps retain their behavior.
Final requests omit a repeated provenance rule from data while preserving the
complete system instructions, source groups, ownership alternatives and local
checks. Offline size tests do not establish live writing quality.

## Controls, cutover and rollback

- `ORIGINAL_CONTENT_STORAGE=legacy` is the default reader/accounting path.
- `ORIGINAL_CONTENT_MIRROR=true` enables compatible same-result persistence.
- `ORIGINAL_CONTENT_STORAGE=shared` serves relational content and shared
  accounting; compatible legacy writes continue for rollback.

These controls do not activate collection, generation or paid providers.

```bash
python manage.py backfill_original_content
python manage.py backfill_original_content --apply --batch-size 200
python manage.py original_content_storage
python manage.py original_content_storage --retirement-report
```

Backfill is read-only by default. Apply is bounded/resumable using
`--after-assessment`/`--limit`; replay preserves UUIDs and call identities.
Readiness checks copy, ordered citations, missing imports and UTC balances.
Errors block cutover. Catch up under compatible writers before switching
readers. Each reader/provider role must have the same observed candidate revision
and adapter version; an old worker fails the consumer-receipt check.

After shared activation, `original_content_storage --record-cutover
--consumer-receipts <file>` records an immutable timestamp using runtime
`RENDER_GIT_COMMIT`. Repeating it for that revision does not reset the clock.
Rollback switches readers to `legacy` while retaining compatible claim/call
ownership and dual persistence. Uncertain sends do not become retryable.

Physical retirement is later: seven days after observed cutover, proven encrypted
restore, reconciled overlaps and zero legacy consumers are all required. The
compatible adapter still uses legacy assessments, calls/budgets, stories/editions
and heroes. Time alone does not permit deletion. Compatibility delivery contains
no drop or physical-rename migration.

Implementation: [`original_content.py`](../../monitor/original_content.py),
[`original_content_backfill.py`](../../monitor/original_content_backfill.py),
[`original_content_cutover.py`](../../monitor/original_content_cutover.py).
Verification: `tests/test_original_content*.py`, `tests/test_packet_maker*.py`.
