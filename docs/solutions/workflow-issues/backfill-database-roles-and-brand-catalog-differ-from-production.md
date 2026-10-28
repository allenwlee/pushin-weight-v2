---
title: "Do not assume the xbackfiller database matches production roles and brand catalog"
date: "2026-10-28"
category: workflow-issues
module: harvest
problem_type: workflow_issue
component: service_object
severity: high
applies_when:
  - "Planning or seeding a backfill job in the dedicated xbackfiller database"
  - "Freezing Call A author contexts from TwitterListMembership and BrandAccount roles"
  - "Adding or switching off test brands that feed the classifier tracked-brand catalog"
symptoms:
  - "twitter_list_memberships has 0 rows in xbackfiller versus 208 active main-list rows in production"
  - "A new manifest freezes 0 main-list author contexts, so Call A attribution differs from production"
  - "Setting is_sentinel=True on a test brand removes it from the classification catalog that production includes"
root_cause: wrong_assumption
resolution_type: tooling_addition
related_components:
  - background_job
  - database
  - tooling
tags: ["backfiller", "xbackfiller", "call-a", "list-membership", "brand-catalog", "undo-receipt", "preflight", "production-parity"]
---

# The dedicated backfill database does not hold production's list memberships, roles or brand catalog

## Context

Historical backfills run in a dedicated Render PostgreSQL database, `xbackfiller`
(Render resource `dpg-dbfemu2vcj2c73fsafe0-a`, database and user `xbackfiller`,
schema at migration 0183). Production is a separate database
(`dpg-d9koekqjobas73fvjqng-a`, database `pushinweight_shadow`).

While preparing the OpenAI/Anthropic size test, the planning and seeding steps
assumed that `xbackfiller` held the same author-role and brand data as
production. It does not. Read-only queries on 2026-10-28 (JST), each wrapped in
`BEGIN TRANSACTION READ ONLY; ...; ROLLBACK;`, found:

| Data (2026-10-28) | xbackfiller | production |
|---|---|---|
| `twitter_list_memberships`, Call A main list `2067062923525275922`, active | 0 | 208 (189 `call_a`, 17 `official_owner_api`, 2 `repair_empty_snapshot`), plus 4 inactive |
| `twitter_list_memberships`, any list | 0 | (not needed) |
| `brands_accounts` rows / distinct accounts | 98 / 76 | 232 / 210 |
| `accounts` with `data_source_id = 'x'` | 12,194 | 131,260 |
| Non-sentinel brands | 177 | about 182 |

Both databases already hold `openai` (created 2026-09-24), `anthropic`
(2026-09-21), `gpt` and `claude` (both 2026-07-23) as non-sentinel Brand rows
with no BrandKeyword rows ("alias-only": the brand name and display names are
their only attribution terms). `gpt` and `claude` also carry roles:
`claude` official @AnthropicAI and @claudeai, staff @DarioAmodei and @karpathy;
`gpt` official @OpenAI and @OpenAIDevs, staff @gdb, @polynoamial and @sama.

The gap does not close by itself. Production learns main-list membership from
the scheduled cycle: each Call A page writes membership rows with source
`call_a` (`monitor/list_membership.py:112-158`, write at 146-153), and the
official X API path writes `official_owner_api` rows
(`core/official_company_lists.py:217`). The main cycle path skips that
observation when it runs as a backfill (`monitor/cycle.py:5506`, condition
`self._backfill_context is None`), and `xbackfiller` runs only backfills. An
auto-memory note from earlier work adds that TwitterAPI.io's list-members
endpoint returns 0 members for private lists such as the Call A main list, so
the membership cannot be rebuilt from TwitterAPI.io member reads either.

The difference changes two things a backfill produces: which brand a Call A
post is credited to, and which brand catalog the classifier reads.

## Guidance

### 1. Know what planning freezes

`plan_job_definition` (`monitor/backfill_collection.py:236-306`) reads the
active members of each author list straight from the database
(`TwitterListMembership.objects.filter(list_id=each, active=True)`, lines
270-272) and resolves their roles with `resolve_call_a_author_contexts`
(`monitor/list_membership.py:172-222`), which joins memberships to
`BrandAccount` roles (lines 182-194) and records official and staff brands per
author (lines 198-219). The result is frozen into the job definition as
`scope.author_scope.contexts`, stamped with `observed_at` and
`historical_membership_reconstructed: False` (lines 294-296).

At run time the frozen contexts replace any live lookup. The backfill passes
them in when it runs under the current policy (`monitor/backfill_collection.py:830`), and
`_prepare_call_a_roles` uses them whenever they are not `None`
(`monitor/cycle.py:3493-3504`). An empty `{}` is not `None`, so there is no
fallback, and `validate_scope` accepts it because it checks only that
`contexts` is a dict (`monitor/backfill_collection.py:177`).

So a manifest built in `xbackfiller` today is valid and freezes zero main-list
author contexts. Its Call A posts are then handled differently from
production's:

- **Official authors** are no longer credited by authorship. Production adds an
  `author_account` mention for an official author's brand
  (`monitor/cycle.py:3519-3523`, applied at 3745-3749); without a context the
  post is attributed only if a keyword matches.
- **Staff authors** skip the relevance gate. Production marks them as staff
  candidates (`monitor/cycle.py:3524-3528`), checks each with the relevance
  model, and credits the staff brand only on a keep verdict
  (`monitor/cycle.py:3566-3609`). Without a context the post goes into the
  ungated group and is saved directly (`monitor/cycle.py:3620-3622`), credited
  only by keywords.

July's existing job `d4440f2e-0366-44ec-9bfe-fe12ac3df79c` was planned on
staging before the database move and froze 207 contexts (session evidence, 2026-10-28). Any new manifest
built on `xbackfiller`, including July's next windows, would freeze none.

### 2. Measure both databases before planning

Count memberships and roles in both databases, read only:

```bash
render psql dpg-dbfemu2vcj2c73fsafe0-a -o text --command "BEGIN TRANSACTION READ ONLY;
SELECT list_id, active, source, count(*) FROM twitter_list_memberships GROUP BY 1,2,3 ORDER BY 1,2,3;
SELECT count(*) AS rows, count(DISTINCT account_key) AS accounts FROM brands_accounts;
SELECT count(*) AS non_sentinel_brands FROM brands WHERE NOT is_sentinel;
ROLLBACK;"

# Same command against production:
render psql dpg-d9koekqjobas73fvjqng-a -o text --command "BEGIN TRANSACTION READ ONLY; ...; ROLLBACK;"
```

The size-test preflight reads the same facts from a saved snapshot. Its SQL
collects `list_memberships` (`scripts/backfill_size_preflight_xbackfiller.sql:87-91`),
and check 6 (`scripts/backfill_size_preflight.py:534-595`) counts main-list
contexts in the manifest. At stage `pre-seed` it reports `pending` with a
warning; at stage `post-seed` a manifest with no main-list contexts fails
(lines 567-577):

```text
the manifest freezes no main list author contexts (July's job froze 207); Call A posts by main-list members would lose their official/staff roles
```

(The July count in that message comes from the saved database snapshot.)

### 3. Seed from a read-only production export, then plan

Copy production's facts in; do not reconstruct them. On branch
`ops/oai-anthropic-size-20261027` (unmerged as of this writing):

1. Export production's current main-list members and every X account role with
   `scripts/backfill_size_main_list_production.sql` (read only, ends in
   `ROLLBACK`):

   ```bash
   render psql dpg-d9koekqjobas73fvjqng-a -o json \
     --command "$(cat scripts/backfill_size_main_list_production.sql)" > DIR/main-list-production.json
   ```

   `-o json` returns `{"output": "<psql aligned text>"}`, not row JSON.
   `load_document` scans the wrapped text for the export document
   (`scripts/backfill_size_report.py:241-273`, wrap handling at 251-253). The
   seed refuses an export whose `database` is not `pushinweight_shadow` or whose
   `list_id` is another list (`scripts/backfill_size_seed.py:632-647`).

2. Seed `xbackfiller`, writing an undo receipt:

   ```bash
   X_MONITOR_DEPLOYMENT_ENVIRONMENT=backfill python -m scripts.backfill_size_seed seed \
     --keywords docs/analysis/2026-10-28-182625-oai-anthropic-keywords.csv \
     --roster docs/analysis/2026-10-28-182625-oai-anthropic-roster.csv \
     --main-list DIR/main-list-production.json \
     --undo-receipt DIR/undo.json
   ```

   The command refuses unless `X_MONITOR_DEPLOYMENT_ENVIRONMENT=backfill` and the
   connected database's `current_database()` and `session_user` are both
   `xbackfiller` (`scripts/backfill_size_seed.py:525-533`). It also refuses
   while a historical run holds a live lease (line 856), when the receipt file
   already exists (line 854), and when the test brands already carry keywords
   (lines 857-858). `_write_main_list` creates missing X accounts and main-list
   memberships, and creates or corrects the roles of the seeded authors only
   (`scripts/backfill_size_seed.py:756-800`; author scope at 780).

3. Build, or rebuild, the manifest after the seed. Planning freezes whatever the
   tables hold at that moment.

4. Run the preflight at stage `post-seed` and require check 6 to pass.

### 4. Switch off by undoing exactly; never hide a brand with `is_sentinel`

The classifier's tracked-brand catalog is built from every Brand with
`is_sentinel=False`, plus its BrandSearchTerm, BrandKeyword (non-regex),
BrandHashtag, BrandAccount (handle and role) and Product rows
(`monitor/cycle.py:165-259`; brand filter at 175). The classifier hashes this
projection into its trace identity (docstring, lines 166-173). Two
consequences:

- Adding test brands' keywords or roles changes the catalog that July's
  enrichment would read.
- Setting `is_sentinel=True` on `openai` and `anthropic` would remove them from
  the catalog. Production keeps them as alias-only, non-sentinel rows, so July's
  catalog would then differ from production's. The plan first chose this
  switch-off (its KTD10) and expected the catalog to omit both brands and still
  match the pre-seed digest (its AE6). Those two outcomes cannot both hold when the brands were in
  the catalog before the seed.

The branch replaces it with an exact undo:

- `seed` records the pre-seed catalog revision, then diffs the catalog-relevant
  state before and after its writes (`scripts/backfill_size_seed.py:859-865`,
  using `seed_state` at 654-676 and `undo_plan` at 679-701). The receipt names
  changed Brand fields; created BrandKeyword, BrandSearchTerm, BrandHashtag,
  BrandAccount, Product and BrandCompany rows (line 591); created or changed
  memberships of the two lab lists and the main list (line 88); created or
  changed roles of the seeded authors; and created Company rows. Several of
  those tables use composite primary keys such as `(brand_id, pattern)`, so rows
  are matched on every key column (`_key_fields`, lines 610-613).
- `switch-off --undo-receipt PATH` reverses exactly those rows in one
  transaction and rolls back unless the catalog revision equals the receipt's
  pre-seed revision (`scripts/backfill_size_seed.py:888-898`). It refuses while
  a historical lease is live (line 903) and fails if PostBrand counts change
  (line 908). Account rows the seed created are left in place: an Account row
  alone does not enter the catalog, which reads handles only through
  BrandAccount (`monitor/cycle.py:221-229`).

## Why This Matters

Nothing errors. The manifest validates, the run completes and the posts are
saved, but Call A attribution and the classifier catalog differ from
production's. A backfill exists to produce history comparable to production,
so a size estimate or a July window planned on unexamined `xbackfiller` data
measures a different pipeline. With 0 main-list memberships, every new
manifest loses all official and staff author credit. The `is_sentinel`
switch-off would have changed the classifier's catalog identity for every post
July enriches afterwards.

## When to Apply

- Building any manifest with `plan_job_definition` against `xbackfiller`,
  including July's next windows and any new size test.
- Seeding test brands, keywords, roles or list memberships into `xbackfiller`.
- Removing or switching off test data there.
- Copying or restoring a database for backfill use. The copy reflects its
  source at copy time, and `xbackfiller` does not learn memberships afterwards.
- Comparing a backfill's Call A counts with production's.

### Operator checklist for any future manifest built in xbackfiller

1. Count active memberships for every author list the manifest will use (main
   list `2067062923525275922` and any lab lists) and `brands_accounts` roles in
   both databases, read only. If `xbackfiller` is short, stop before planning.
2. Seed from a read-only production export
   (`scripts/backfill_size_main_list_production.sql` or an equivalent saved
   query), not from a reconstruction, TwitterAPI.io member reads or memory.
3. Record an undo receipt with the pre-seed catalog revision before writing.
4. Plan the manifest after the seed and confirm its main-list context count is
   close to production's active membership (production had 208 active on
   2026-10-28; July's staging-planned job froze 207).
5. Undo exactly from the receipt and confirm the catalog revision returns to the
   pre-seed value.
6. Never set `is_sentinel=True` to hide a brand that production keeps as
   non-sentinel.

## Examples

**A manifest planned before the seed.** `xbackfiller` holds 0 memberships, so
`resolve_call_a_author_contexts` returns `({}, [])` for the main list and the
manifest freezes `"contexts": {}`. Take a main-list member that production
records as official for brand `B`. Its post saying only "new model out today"
gets no `B` credit in the backfill, because no keyword matches and no
`author_account` mention is added. A main-list member recorded as staff for `B`
is saved without a relevance verdict and without `B` staff credit. Production
credits the first by authorship and checks the second with the relevance model
before crediting `B`.

**The rejected switch-off.** Before the seed, the catalog includes `openai` and
`anthropic` as alias-only rows. Setting `is_sentinel=True` drops them, so the
revision no longer matches the pre-seed value or production's. The exact undo
deletes only the seeded keywords, roles and memberships and restores changed
fields. The PostgreSQL-marked test
`test_switch_off_restores_the_pre_seed_catalog_and_keeps_post_brands`
(`tests/test_backfill_size_seed.py:409-434`) asserts that the revision returns
to the pre-seed value, that both brands stay non-sentinel, that PostBrand rows
remain and that a second switch-off still matches.

**Verification status (2026-10-28).** The pure-Python tests in
`tests/test_backfill_size_seed.py` and `tests/test_backfill_size_preflight.py`
pass, including
`test_manifest_without_main_list_contexts_fails_post_seed_and_warns_pre_seed`
(`tests/test_backfill_size_preflight.py:463-470`). The PostgreSQL-marked seed
and undo tests are written but have not run, because the shared test database
refuses schema 0183. Real read-only runs of the preflight and the export SQL
succeeded against both databases. The seed and switch-off have not yet run
against `xbackfiller`.

## Related

- [Prove X backfill coverage separately from processing completion](2026-10-16-131500-backfill-coverage-and-completion.md): another way a backfill's collection scope silently diverges from production. Its caveat that current list membership cannot reconstruct past membership also applies to the export this doc recommends.
