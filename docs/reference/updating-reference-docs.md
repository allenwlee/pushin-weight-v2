# Updating reference documents

Last verified: 2026-10-01 11:33:12 JST

References help a person find an answer about the current system without
already knowing its source files, implementation phases, or internal vocabulary.
They also give agents reliable project context. A reference is successful when
a reader can find the subject, understand what it means, and follow a link to
the exact implementation when needed.

This is the human guide to that standard. The
[`updating-reference-docs` project skill](../../.claude/skills/updating-reference-docs/SKILL.md)
is the canonical agent procedure. Keep the two aligned when changing the
standard; do not leave an agent following a weaker rule than this page states.
The [folder taxonomy](../docs-taxonomy.md) explains where documents belong and
remains a draft until the project owner reviews it.

## Organize around the reader’s question

Use stable subjects people can recognize: **People and job history**, Companies
and brands, X accounts, Job listings, Events, and Processing records. Explain
their relationships before presenting detailed fields or commands.

Do not organize a maintained reference around the order work happened. Headings
such as “Stage 1C,” “new tables,” or “Current intelligence tables” do not tell a
reader where to find a person’s name or employment record. Changing “Stage 1C”
to “Current” does not fix that problem. Move each item into its subject and give
it the same treatment as the rest of the reference.

Within a subject, distinguish the roles of the records:

| Record kind | Reader-facing explanation | Example |
| --- | --- | --- |
| Entity | The person, organization, item, or occurrence being described | `people`, `companies`, `job_listings` |
| Relationship | How two records are connected | `people_accounts`, `brands_companies` |
| Claim | An interpreted fact that may still need review | `people_brand_affiliations` |
| Evidence | The source observation supporting a claim | `people_brand_affiliation_evidence` |
| Vocabulary or label | An allowed concept and its display wording | `roles`, `role_labels` |
| Processing record | Work attempted, progress, ownership, coverage, or cost | `personnel_discovery_runs`, `job_source_sync_runs` |

These distinctions explain what rows mean; they need not become a separate
top-level filing system. Keep a person’s identity, account links, affiliations,
and evidence together under the people subject. Explain that an advertised job
and someone’s actual employment are different records.

## Make the full scope discoverable

A document claiming to cover a collection must enumerate that collection.
Provide a complete linked inventory near the beginning, followed by a full
section for each item. A table mentioned in a footnote or one catch-all summary
row does not count as a documented table.

For the [database schema reference](db-schema.md), the checked scope is the
111 concrete application tables declared by `core/models.py` at the recorded
revision. Its alphabetical inventory complements the subject navigation:

- Every table appears exactly once in the inventory and has exactly one
  detailed section, with a stable link between them.
- Table names, model names, and plain-English purposes are all visible.
- Subject counts add up to the declared total.
- Abstract models, views, and framework-managed tables are identified
  separately so the number has a clear boundary.
- A newly added table belongs in the right subject immediately. It must not
  be appended to a “recent additions” bucket or left as a summary-only entry.

The total is a verified snapshot, not a number to hardcode forever. Reconcile
the inventory with the current source whenever the schema reference changes.

## Give every table useful, consistent detail

Each table section must answer the same questions:

1. **What does one row represent?** State its purpose and how it differs from
   nearby records. Explain whether it is a current fact, a source observation,
   a proposed identity match, or work waiting to run.
2. **What identifies the row?** Show the primary key and any separate uniqueness
   rules. Explain composite keys; Django’s composite `pk` is not an extra SQL
   column.
3. **What columns exist?** List every physical column, including inherited
   fields, its type, whether NULL is allowed, and meaningful defaults or allowed
   values. Show differences between SQL column names and model attributes.
4. **How does it connect?** Link foreign keys to the referenced table/column
   and describe deletion behavior accurately. Distinguish Django behavior from
   raw PostgreSQL clauses when they differ.
5. **What rules protect the data?** Identify named indexes, unique constraints,
   checks, and important rules implemented outside model metadata. Explain
   their practical meaning, keeping exact technical detail available.
6. **How should values be interpreted?** Distinguish source dates from collection
   timestamps, source wording from normalized or translated text, and pending
   claims from confirmed records. Define the counting unit so evidence rows
   are not mistaken for distinct people or listings.
7. **Where is the authority?** Link the current model, relevant migrations, and
   focused readers/writers or contracts for behavior that fields alone cannot
   explain.

Do not give older tables full field tables while reducing newer core entities
to a sentence. Preserve useful examples, caveats, and exact contracts from the
material being replaced. A generated inventory can establish completeness; it
does not replace clear explanations of purpose and relationships.

## Verify the current implementation

Start from code, configuration, models, ordered migrations, and focused tests.
For schema work, compare Django model metadata with the final migration state;
include inherited columns, composite identities, field-level uniqueness, and
migration-only SQL. The retired SQLite database and Graphviz image are not
current schema sources.

State what was checked and at which revision/date. Reading repository models
does not prove that a particular deployment has applied the same migrations.
Use authorized read-only database inspection when a live-schema claim requires
it, and distinguish that evidence from a repository snapshot.

Plans describe intended changes. Do not document them as current fields or
behavior before implementation. In particular, a requested column rename does
not change the current SQL column name until its migration exists and has been
applied where claimed. Explain present compatibility behavior where necessary;
leave implementation history to Git.

## Finish the reference, not just the edit

Before completion, read the complete result and compare its coverage with the
source. For schema work, verify exact equality between the source table set,
inventory table set, and detailed-section table set. Compare every table’s
physical columns, types, nullability, keys, defaults, indexes, and constraints;
do not rely only on a matching total.

Check relative links, section anchors, and links into the reference from other
files. Check whitespace with `git diff --check`. Keep a single review timestamp
for the pass. The root README remains an overview and link map; reconcile any
affected link or description without overwriting unrelated work.

Report what was verified and any unresolved drift. A documentation refresh
does not authorize migrations, collection, or deployment. If the owner requests
commit and push, finish at the verified remote commit, preserving unrelated
working-tree changes. Follow the repository’s documentation-only
`[skip render]` convention.
