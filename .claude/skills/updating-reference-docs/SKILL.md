---
name: updating-reference-docs
description: This skill should be used when creating, updating, reorganizing, or verifying PushinWeight reference documents intended for people to read or to give to agents as project context.
---

# Updating Reference Documents

## Purpose

Maintain `docs/reference/` as a useful set of detailed, current descriptions
of PushinWeight. Write for people and for people to refer agents to: explain
the system in plain language, retain the technical detail needed to use it,
and keep each document grounded in the codebase as it exists at the time of
writing.

The human-facing explanation of this standard is
[`Updating reference documents`](../../../docs/reference/updating-reference-docs.md).
This skill remains the canonical agent procedure; keep both aligned when
changing the standard.

Apply this skill when asked to create, refresh, edit, review, verify, rename,
move, or organize a document in `docs/reference/`. Read
[`docs/docs-taxonomy.md`](../../../docs/docs-taxonomy.md) when deciding
whether a document belongs in `reference/` or another existing `docs/`
folder. That taxonomy is a draft until the owner reviews it; follow the
owner's specific direction if it conflicts with the draft.

## Rules for Reference Prose

- Organize by stable subjects and the reader's questions, not implementation
  phases, migration order, or when a feature was added. A core entity such as
  `people` belongs under an obvious people/job-history subject. Do not bury it
  in a mixed “Current intelligence tables” appendix. Renaming an era-based
  catch-all is insufficient; integrate its entries into the subject structure.
- Make the stated scope discoverable. A reference to a finite collection needs
  a complete linked inventory near the beginning and a detailed section for
  every item. A mention or summary-only row does not count as full coverage.
  Use both subject navigation and an alphabetical index when readers need to
  find exact names. State exclusions and the verified total explicitly.
- Apply one consistent level of detail to every item. Explain what one record
  represents and distinguish entities, links, interpreted claims, source
  evidence, vocabularies, and processing records within their subject. Generated
  field lists support completeness; they do not replace human explanations of
  purpose, relationships, dates, provenance, and current behavior.
- Keep every reference comprehensive, detailed, and at least as useful as the
  material it replaces. Do not summarize, shorten, or remove examples,
  conditions, caveats, source maps, or exact contracts merely to make a file
  shorter.
- Describe the current codebase, product, and operating behavior at the time
  of writing. Do not use reference files as a record of how behavior changed.
  Git history serves that purpose.
- Use plain English for explanations. Assume a technically capable reader may
  not know this project or its internal vocabulary. Define a necessary term
  when it first appears, then retain precise names for code, models, fields,
  prompts, commands, and settings.
- Allow a little repetition when it helps a person understand a document
  without opening several other files. Link to the authoritative detail when
  copying it would create two sources that can drift.
- State verified behavior as fact. Separate measured evidence from an
  interpretation, and leave out recommendations or subjective opinions unless
  the owner asks for them.
- Keep literal prompts, machine-checked schemas, and copyable commands exact.
  Explain them outside the literal block rather than editing the quoted
  material.
- Never include credentials, API keys, connection strings, private raw
  identifiers, or provider response bodies.

## Workflow

### 1. Set the boundary

Identify the document or documents the owner asked to change. Record the
current commit, `git status --short`, and one current JST timestamp for any
`Last updated` lines. Preserve unrelated working-tree changes. Do not turn a
reference refresh into unrelated code changes; report code drift separately
unless implementation was also requested.

Check the current `docs/` taxonomy before choosing a destination. Do not
create a new folder under `docs/` unless the owner explicitly requests one.
Use a stable descriptive filename for a maintained reference; use dated names
for evidence, studies, investigations, plans, and iteration records.

### 2. Find the sources of truth

Trace each important claim to current source code, configuration, models,
migrations, tests, fixtures, or explicitly authorized read-only runtime
evidence. Prefer the current Django and PostgreSQL implementation. Do not
copy a plan's proposed behavior into a current reference unless the code and
configuration now implement it.

For production database structure, use `core/models.py` and the ordered
`core/migrations/`. PostgreSQL inspection can confirm a deployed schema when
read-only access is authorized. Do not use the retired `schema.dot`, the
retired schema image, or the historical SQLite database as current truth.

For a complete schema reference, reconcile the set of concrete application
tables with the final migration state. Identify framework tables, abstract
models, and views separately rather than silently mixing them into the count.
Inspect migration-only SQL as well as model metadata. State whether the review
verified repository structure or a particular live deployment; do not claim
the latter from source inspection alone.

For a literal prompt, compare the whole document block with the source
constant. For a request or output contract, check both the caller and its
parser/validator. For an external call, verify endpoint, model, parameters,
retry behavior, budgets, and credential-variable names from the actual
runtime path. Never infer runtime behavior from a plan or a dated report.

### 3. Update the owned reference

Keep the existing level of detail. Refresh stale claims, examples, commands,
source links, and names from the verified current implementation. Add
important boundaries and failure behavior when they help readers use the
system accurately.

Keep the maintained references distinct by responsibility. In particular,
the classifier prompt, generated post commentary, literal post translation,
shared post-artifact lifecycle, rare-type search, and trend headline system
are separate subjects. Cross-link them where their behavior meets; do not
blend their prompts or outputs into one vague “AI” description.

For `db-schema.md`, give every table the same minimum contract:

- one-row meaning, exact SQL table name, model name, and source link;
- primary key, including composite components without inventing a `pk` column;
- every physical column, including inherited columns, SQL type, nullability,
  meaningful defaults and choices, and differing model/SQL names;
- linked FK targets and deletion behavior, distinguishing Django `on_delete`
  from PostgreSQL clauses;
- named indexes and constraints, field-level uniqueness, and relevant
  migration-only rules, with explanations of their practical effect;
- source versus observation dates, precision, language/normalization boundaries,
  review state, evidence relationships, and counting units where relevant.

Preserve useful existing detail while integrating additions into the correct
subject. Core tables must not receive only a catch-all summary while other
tables retain full column documentation. Proposed names, fields, and translation
behavior stay in plans until the code and migrations implement them.

Use one captured JST timestamp for the review pass when the document uses a
`Last updated` line. Do not add a change-history footer. A date may identify
when the snapshot was checked, but the prose should not narrate previous
states or list corrections from earlier revisions.

### 4. Reconcile related documents

Update the repository-root `README.md` after its underlying focused
references settle. The README is a short overview and link map; it does not
replace detailed references.

When a file moves or is renamed, find and update references in documentation,
plans, configuration, tests, and scripts. Keep executable tests and
machine-readable fixtures in the repository's `tests/` tree. Reports about
test or evaluation results belong in `docs/analysis/`, not in a new
`docs/test/` directory.

For the focused runtime references, check the relevant sources below:

| Subject | Main sources to verify |
| --- | --- |
| TwitterAPI calls and credit accounting | `monitor/cycle.py`, `x_monitor/apify.py`, `x_monitor/queries.py`, `config.yaml`, `scripts/harvest_cost/` |
| Live query groups | `config.yaml`, query-planning code, seed data, and focused tests |
| Database schema | `core/models.py`, ordered `core/migrations/`, and optional authorized PostgreSQL inspection |
| Lookup tables | Django models, seed commands/data, and attribution code |
| Classification prompts and route | `core/classification_contract.py`, `x_monitor/classifier_0731_prompts.py`, `x_monitor/attribution.py`, `x_monitor/config.py`, `config.yaml`, and focused tests |
| Post translation | `x_monitor/translator.py`, `monitor/cycle.py`, `monitor/post_artifacts.py`, `core/models.py`, and translation tests |
| Generated post commentary | `x_monitor/synthesis.py`, `monitor/post_synthesis.py`, `monitor/post_artifacts.py`, `core/models.py`, and synthesis tests |
| Shared post artifacts | `monitor/post_artifacts.py`, `monitor/post_synthesis.py`, `core/models.py`, current migrations, and API/browser tests |
| Rare-type intelligence | `core/rare_type_search.py`, `core/intelligence_readers.py`, rare-type management commands, extraction code, current migrations, and focused tests |
| Trend headlines | `monitor/trend_narrative_*.py`, `monitor/tasks.py`, `core/models.py`, current migrations, `x_monitor/config.py`, `config.yaml`, `render.yaml`, `docs/deploy/render.md`, and focused tests |

For headline references, verify the literal rank, editor, and critic prompts;
candidate selection and factual calculations; provider route and limits;
response validation; persisted lifecycle; public output shape; and serving,
enqueue, and provider-call controls independently. Keep future work separate
from current behavior.

### 5. Check the result

Before reporting completion:

1. Read the full changed document and inspect its diff.
2. Confirm each maintained claim against its named source; check literal
   prompts and machine-readable contracts exactly.
3. Confirm moved files exist at their destinations and in-repository links
   point to existing paths.
4. Confirm dates and wording describe a current snapshot, not a change log.
5. Run `git diff --check` for whitespace errors. Run tests only when the owner
   asks for them or when the implementation request specifically includes
   test execution.
6. Report verified changes, untouched related documents, unresolved drift,
   and any check that could not be completed.

For schema references, also verify exact set equality between source tables,
inventory entries, and detailed sections; reject omissions and duplicates even
if the total happens to match. Compare every table's columns, types, nullability,
keys, defaults, indexes, and constraints. Check internal anchors and inbound
links after reorganization. Record the source revision, migration boundary, and
one review timestamp. Completeness checks do not authorize running migrations
or changing production data.

## Existing Reference Boundaries

The following artifacts are retired and must not be refreshed:

- `docs/reference/schema.dot`
- `docs/reference/images/xmonitor-schema-post-batch.png`

The source of truth for the production schema is Django models and migrations.
