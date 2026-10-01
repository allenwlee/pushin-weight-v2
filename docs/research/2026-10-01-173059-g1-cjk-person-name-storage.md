---
title: CJK person names — storage, primary name and English display
date: 2026-10-01
workstream: G1
status: schema-direction-selected
---

# CJK person names — storage, primary name and English display

## Recommendation for PushinWeight

**Owner-selected direction, October 1:** retain
`Person`, `PersonName` and separate `PersonNameEvidence` records in the first
DeepSeek implementation. The intervening complexity discussion suggested
deferring the evidence table and derivation links; inspection of the saved
dossier supports keeping both a source-observation history and a lightweight
link to the original of a converted/generated name. The owner accepted this
reassessment and requested its addition to the existing plan. G1-R15 records
that selection. It supersedes the deferral suggestion; exact column details
will be finalized during scaffold implementation, and no migration has run.

The saved dossier already distinguishes owner-supplied 李元 from subsequent
public corroboration; keeps the third-party 张一凡 candidate for Yifan Zhang
unconfirmed; and preserves Ming-Yu Liu's sourced 劉洺堉 alongside the converted
刘洺堉. Evidence must establish why a spelling belongs to this person, not
merely that somebody with the spelling appears on a page. Preserve the original
excerpt, source URL or durable capture reference, observation time, collection
method/run reference, and the review decision with its reason. Keep source
publisher separate from the search/scraping provider. Several copied articles
are not automatically independent corroboration.

Use the existing affiliation/evidence separation as the local design precedent
(`core/models.py`, `PersonBrandAffiliationEvidence`). Defer a general provenance
graph, automated confidence scoring and elaborate component-level review
workflows. The column counts below remain the earlier concrete proposal;
finalize the evidence and review fields against actual DeepSeek intake before
freezing the migration contract. This decision is about which records
must exist from the start, not adding every possible audit feature.

Collect and persist the person's established English/Latin-script professional
name during intake. Do not put names in the on-demand biography/title translation
queue. Attempt both the original-script and English-facing name during collection;
record an explicit gap if one cannot be established. A generated romanization
can be retained as a marked candidate, never as evidence of the person's spelling.

Use the established original/professional name as the person's primary default;
for a Chinese person with a sourced Chinese name this will usually be Chinese.
Use their separately selected English-facing name on English pages. If the
original-script name is unknown, retain the best established public name as
the fallback. Do not infer a native language from country, employer or appearance.
The person's UUID remains the identity key, independent of all name spellings.

This is our application design, informed by the sources below; no standard
mandates this SQL schema or these column counts. It replaces the earlier proposal
to add six language-specific name-component columns directly to `Person`.
Components remain optional; they move onto individual name representations.
No model, migration or live database was changed by this research.

## Why keep multiple representations?

W3C recommends retaining full names, making parts optional where possible,
supporting Unicode, and considering both original-script and Latin forms when
staff and users need them. It also explains why Japanese readings need separate
data. [W3C personal names](https://www.w3.org/International/questions/qa-personal-names).

Unicode's person-name formatter explicitly allows separate logical name objects
for scripts, alternative names and phonetic readings. Parsing an unknown full
name into components is outside that formatter's scope. These support a related
names table; they do not make a transliteration a verified public spelling.
[Unicode CLDR person names](https://www.unicode.org/reports/tr35/tr35-personNames.html).

ORCID is a relevant researcher-profile example: it distinguishes a preferred
published name from name components and multiple alternative names, including
different character sets. [ORCID name model](https://support.orcid.org/hc/en-us/articles/360006973853-Add-and-edit-your-name-on-your-ORCID-record).

Korean official guidance permits established personal spellings even when a
mechanical application of current romanization rules would produce another
spelling. Source the person's chosen form; do not standardize it away.
[National Institute of Korean Language](https://www.korean.go.kr/front/mcfaq/mcfaqView.do?mcfaq_seq=5685).

## Person: two name-selection columns, 11 total in the target model

The existing model has 13 database columns, including four flat full-name
columns and no given/family-name components (`core/models.py`, `Person`).
Replace those four name strings with two references after a preserving migration.
The proposed complete target `people` column list is:

| # | Column | Purpose |
|---|---|---|
| 1 | `id` | Existing UUID; the stable identity key |
| 2 | `primary_name_id` | Selected original/professional default name record |
| 3 | `english_name_id` | Selected stored name for English display; may equal the primary record |
| 4 | `date_of_birth` | Existing optional value; no new collection requirement |
| 5 | `date_of_birth_precision` | Existing date precision |
| 6 | `sex` | Preserving rename of existing `sexs`; no inferred values |
| 7 | `nationality` | Existing optional field |
| 8 | `ethnicity` | Existing optional field |
| 9 | `primary_language` | Existing person-language field, separate from any name's script/language |
| 10 | `created_at` | Existing creation time |
| 11 | `updated_at` | Existing update time |

Both references must belong to this person and must not select rejected names.
English can remain null with a visible research gap; do not block preservation of
the original record or fabricate a spelling just to satisfy a database constraint.
Primary may be temporarily null during a transaction/backfill, but usable person
records need a supported display fallback. Keep unresolved aliases labeled.

The count of 11 is the final target. The first compatible migration would retain
all 13 existing columns and add the two links: **15 temporarily**, until the four
legacy full-name columns can safely be retired. Adding six flat component columns
as well would create a second competing source of truth and is not recommended.

## PersonName: 14 columns, one row per representation

| # | Column | Purpose |
|---|---|---|
| 1 | `id` | Name-record UUID |
| 2 | `person_id` | Owner of the name representation |
| 3 | `full_name` | Complete name as sourced; display does not depend on a successful split |
| 4 | `given_name` | Optional supported given-name component(s) |
| 5 | `family_name` | Optional supported surname component(s) |
| 6 | `language_tag` | Language/script tag, e.g. `zh-Hans`, `zh-Hant`, `zh-Latn`, `ja`, `ja-Kana`, `ko`, `ko-Latn`; unknown is allowed |
| 7 | `name_type` | Original, professional, romanized, phonetic, localized, alias or unclassified |
| 8 | `name_order` | Family-first, given-first, unknown or not applicable; preserve the full form |
| 9 | `is_preferred` | Reviewed choice among representations with this exact language/script tag |
| 10 | `origin` | Source-attested, owner-supplied, generated or legacy import |
| 11 | `review_status` | Pending, confirmed, rejected or superseded |
| 12 | `derived_from_name_id` | Original record for a generated/converted representation, if applicable |
| 13 | `created_at` | Creation time |
| 14 | `updated_at` | Update time |

Use one preferred record per person and exact language/script tag. English
selection is explicit because its preferred professional name may be tagged
`en`, `zh-Latn`, `ja-Latn`, `ko-Latn` or another language. A romanized Chinese
name does not become English-language name data merely because an English page
shows it. Do not label it from the language of the scraped page.
[W3C language-tag guidance](https://www.w3.org/International/questions/qa-choosing-language-tags.en.html).

Keep full names authoritative for display. A Chinese surname need not be one
character; a Japanese reading is not reliably recoverable from kanji; a hyphenated
Korean given name is not automatically a middle-name split. Source components
or leave them null. Professional names need not be legal names; this project
does not require passport identity collection.

Preserve case, spacing, punctuation and source forms. Use Unicode-aware text
storage. Normalized search forms are derived indexes, not replacement display
names; matching a normalized name is never sufficient to merge two people.
Unicode recommends NFC as a normalization foundation; retain the raw source
form in evidence even when the working representation is normalized.
[CLDR normalization](https://www.unicode.org/reports/tr35/tr35-personNames.html#normalization),
[W3C character support](https://www.w3.org/International/questions/qa-personal-names).

## PersonNameEvidence: eight columns for source observations

Use a separate evidence row for each observation rather than losing multiple
sources when the preferred spelling changes. This follows the application's
existing separation of job claims from job evidence, without misusing job
evidence records for names.

| # | Column | Purpose |
|---|---|---|
| 1 | `id` | Evidence identifier |
| 2 | `person_name_id` | Supported name representation |
| 3 | `source_kind` | Personal site, company bio, publication, account snapshot, owner statement, generation or legacy import |
| 4 | `source_reference` | Source URL or durable internal record/artifact reference |
| 5 | `source_text` | Exact observed name/excerpt; for generation, record the derivation rather than inventing a citation |
| 6 | `supports_fields` | Explicit supported fields such as full name, given name, family name or order |
| 7 | `observed_at` | When this evidence was obtained, not the date the person acquired the name |
| 8 | `created_at` | When this observation was stored |

Origin and review are separate: corroborating a generated candidate later must
not erase its derivation or earlier observations. A full-name source does not
automatically verify its parsed components. Unknown source metadata on legacy
rows remains unknown, even after structurally successful migration.

## Intake, display and migration

1. Reuse existing identity IDs and self-linked evidence. Collect original and
   established English-facing forms during intake. Prefer the person's own
   professional spelling, then attributable company/institutional evidence.
   Publications can support a name for an already eligible person; paper authors
   still do not become an automatic staff discovery queue.
2. Save representations and evidence without name-only person merging. Select
   primary and English records deliberately. Track missing English coverage as
   unfinished name research. Reuse a suitable attested Latin form on English pages.
3. Display the English selection on English pages and the corresponding preferred
   sourced representation in other locales. Preserve source order unless the
   product explicitly asks for a different format. Fall back visibly to an
   available established name when a requested localized form is missing.
4. Add the related tables and nullable selection links before moving old data.
   Backfill all four populated legacy name columns with their existing values;
   retain source/status uncertainty. Update readers/writers and deliberately
   version the read contract. Retire old columns only after preservation and
   compatibility checks; the existing four display keys can remain API outputs.
5. Test Chinese originals/Latin aliases, Chinese script variants, Japanese
   phonetic readings, Korean established spellings, mononyms, unknown components,
   duplicate names across people, alternate order, repeated imports and source
   conflicts using fixtures and the saved eligible DeepSeek population.

English/Japanese biography and job-description translation can remain on demand.
The eager English-name requirement is independent of that text-translation
policy. This research recommends the schema and fallback rules; it does not
claim the database migration or collection worker has been implemented.
