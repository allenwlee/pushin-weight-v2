---
description: Review and refresh the seven maintained runtime reference documents for the v2 Django and Render stack.
---

# Updating reference docs

Use this procedure whenever an operator asks to update, refresh, or verify the
runtime reference documentation. It covers six focused files under
`docs/reference/` and the repository overview in `x-monitoring/README.md`.

The legacy `docs/reference/schema.dot` and
`docs/reference/images/xmonitor-schema-post-batch.png` artifacts are retired.
Do not edit or regenerate them. `core/models.py` and `core/migrations/` are the
only repository sources of truth for the production PostgreSQL schema.

## Maintained files

| File | Contract | Primary sources of truth |
| --- | --- | --- |
| `docs/reference/twitterapi-io-calls.md` | TwitterAPI request paths, parameters, cursor behavior, retries, and credit accounting | `monitor/cycle.py`, `x_monitor/apify.py`, `x_monitor/queries.py`, `config.yaml`, `scripts/harvest_cost/` |
| `docs/reference/twitterapi-live-queries-by-model.md` | Current brand/model query groups and live call composition | `config.yaml`, query-planning code, seed data, and focused harvest tests |
| `docs/reference/db-schema.md` | Django/PostgreSQL tables, columns, relationships, constraints, and indexes | `core/models.py`, `core/migrations/`, and optional read-only PostgreSQL introspection |
| `docs/reference/lookup-tables.md` | Lookup keys, labels, seed ownership, and usage | Django models, seed commands/data, and attribution code |
| `docs/reference/classifier-prompts.md` | Literal classifier prompts, model route, input/output contracts, and validation | `x_monitor/attribution.py`, `x_monitor/config.py`, `config.yaml`, and focused tests |
| `docs/reference/headline-trend-narratives.md` | V22 headline trend math, adaptive series, engagement/nationalism facts, evidence packet, literal prompt, DeepSeek route, output validation, ledger/subjects, public DTO, rollout controls, and follow-ups | `monitor/trend_narrative_*.py`, `monitor/tasks.py`, `core/models.py`, current migrations, `x_monitor/config.py`, `config.yaml`, `render.yaml`, `docs/deploy/render.md`, and focused tests |
| `x-monitoring/README.md` | High-level v2 system overview and links to the six focused references | The six reviewed reference files plus current application and deployment code |

## Procedure

### 1. Capture the review boundary

Before editing, record:

- the current commit SHA;
- `git status --short` so unrelated work is preserved;
- the current JST timestamp for the review headers;
- the latest Django migration leaf from `python manage.py showmigrations core`;
- whether production facts are required and, if so, the approved read-only
  PostgreSQL route.

Never copy credentials, API keys, connection strings, raw private identifiers,
or provider response bodies into a reference document.

### 2. Review the six focused references

The six files under `docs/reference/` are independent and may be reviewed in
parallel. Each reviewer must:

- edit only its assigned file;
- verify every current-state claim against code, configuration, migrations,
  tests, or explicitly approved read-only runtime evidence;
- prefer current Django/Render paths over retired Flask, launchd, or SQLite
  paths;
- preserve literal prompts and request examples character-for-character when
  the section says they are literal;
- flag unverifiable runtime claims instead of guessing;
- report substantive changes, unresolved questions, and drift found outside
  the assigned file.

For `db-schema.md`, derive schema shape from `core/models.py` and the ordered
Django migration graph. PostgreSQL introspection may verify a deployed schema,
but it does not replace the model/migration source of truth. Do not use the
legacy SQLite database, `schema.dot`, or the retired PNG.

For `headline-trend-narratives.md`, also perform these exact checks:

1. Compare the fenced literal prompt with
   `monitor/trend_narrative_generation.py::HEADLINE_SYSTEM_PROMPT_V2`
   character-for-character.
2. Verify candidate, series, episode, evidence, and provider-packet limits
   against `monitor/trend_narrative_candidates.py`.
3. Verify every mathematical fact and coverage rule against
   `monitor/trend_narrative_facts.py`.
4. Verify the exact provider, endpoint, model, timeout, retry policy, prompt
   version, and credential variable against the real generation caller and
   `HeadlineNarrativeConfig`.
5. Verify the seven-key output contract, claim/evidence linkage, and subject
   validation against generation tests.
6. Verify `TrendNarrative`, `TrendNarrativeSubject`, physical PostgreSQL table
   names, compatibility view, and expansion-only migration behavior.
7. Verify the browser DTO contains no provider, claim, evidence, credential,
   or private-source internals.
8. Verify serving, enqueueing, and provider-call controls independently, and
   confirm the checked-in deployment values remain off unless an authorized
   release deliberately changed them.
9. Keep deferred work explicit: off-shortlist harvesting and the V2
   click-through analytical graph remain follow-ups until implemented.

### 3. Review the overview last

Review `x-monitoring/README.md` only after the six focused references settle.
The README is a synthesis layer. Its system overview, deployment description,
brand/query summary, and "where to look next" links must agree with the focused
documents and current v2 code.

The README reviewer must not revive retired launchd services, the v1 Flask
dashboard, or writable SQLite instructions. If a focused document and the
README disagree, verify the source code and correct both documents in their
owned review steps.

### 4. Stamp and reconcile

Add or refresh a line immediately below each H1:

```text
Last updated: YYYY-MM-DD-HH:MM:SS
```

Use one captured JST timestamp for the review pass. Add a short `Last reviewed`
footer that lists substantive corrections and unresolved runtime-only facts.

Read every review summary and reconcile cross-file vocabulary, file paths,
table/model names, provider names, locale names, and deployment controls. Do
not silently fix unrelated code while running this documentation action; put
code drift in the operator handoff.

## Source-of-truth map

| Claim | Verify here |
| --- | --- |
| Production database shape | `core/models.py`, ordered `core/migrations/`, optional read-only PostgreSQL introspection |
| Harvest cycle and external calls | `monitor/cycle.py`, `monitor/management/commands/run_cycle.py`, `x_monitor/apify.py`, `config.yaml`, harvest-cost tooling |
| Query groups and enabled models | `config.yaml`, query planner, seed data, focused tests |
| Classifier prompt and route | `x_monitor/attribution.py`, `x_monitor/config.py`, `config.yaml`, classifier tests |
| Headline prompt and route | `monitor/trend_narrative_generation.py`, `x_monitor/config.py`, `config.yaml`, generation tests |
| Headline facts and packet | `monitor/trend_narrative_facts.py`, `monitor/trend_narrative_candidates.py`, PostgreSQL tests |
| Headline persistence and public DTO | `core/models.py`, current migrations, lifecycle/projection code, schema and browser tests |
| Render topology and controls | `render.yaml`, `project/settings.py`, `docs/deploy/render.md`, read-only Render inventory when authorized |

## Verification before completion

1. Run `git diff --check` and inspect the documentation-only diff.
2. Confirm all seven maintained files were reviewed or explicitly reported as
   unchanged after verification.
3. Confirm each maintained Markdown file has the same review-pass timestamp
   and a current review footer.
4. Spot-check at least two substantive claims in each focused reference
   against its primary source.
5. Programmatically compare the literal headline prompt block with
   `HEADLINE_SYSTEM_PROMPT_V2`; require an exact match.
6. Confirm every README reference link resolves to an existing file and its
   target H1 still describes the linked subject.
7. Confirm `schema.dot`, the retired PNG, code, migrations, configuration, and
   data files were not modified by the documentation-only action.
8. Present unresolved or runtime-only drift to the operator as follow-up work.

## Common mistakes

| Mistake | Correct response |
| --- | --- |
| Regenerating the retired Graphviz schema | Stop. Use Django models/migrations and leave the retired artifacts unchanged. |
| Treating SQLite as production truth | Use PostgreSQL and the Django schema; local SQLite is development-only. |
| Copying a plan estimate into a current-state reference | Verify the live constant/configuration and describe the date/revision of runtime evidence. |
| Paraphrasing a literal prompt | Compare exact characters; put explanation outside the literal block. |
| Letting the headline doc expose a secret | Name only the environment variable and redacted ownership boundary. |
| Reviewing the README before focused files settle | Review the six references first, then reconcile the overview. |
| Silently editing code found to be stale | Report code drift separately unless the operator explicitly expanded scope. |
