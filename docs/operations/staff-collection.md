# Staff identity and media collection

The staff library retains people independently of their X accounts, sourced name
representations, employment claims and attributed media. Initial batches and new
staff arrivals use the same importer and collection queue. DeepSeek is the first
local database pilot; production collection is disabled by default.

## Import and review

Use an explicitly selected database and an untracked working folder. Never source
an entire secrets file as shell code. The commands below make no paid requests.

```bash
python manage.py adapt_staff_dossier /private/dossier/data.json --output /private/staff-manifest.json
python manage.py import_staff_manifest /private/staff-manifest.json
python manage.py import_staff_manifest /private/staff-manifest.json --apply --asset-root /private/dossier
python manage.py export_staff_dossier --brand deepseek --output /private/deepseek-review
```

Preview performs reads only. Apply commits each person's source observation
separately so an interrupted batch can resume. Reapplying the same manifest does
not duplicate people, names, roles or media. Asset failures remain visible and
can be retried by reapplying after restoring the supplied file. Local paths must
resolve inside the explicit asset root, including symlinks. Source records and
saved media stay outside Git. The HTML export is a private operator artifact;
it is not a new public API or unauthenticated Django route.

A `staff-intake/v1` manifest has `people` and optional `source_outcomes` arrays.
Each person requires a stable `source_key`, `display_name` and `eligibility`.
Use `staff`, `former_staff` or `dated_staff` with separately sourced employment
affiliations; `call_a_person` and `db_staff` preserve the owner's account intake
rules. Other eligibility values are retained as exclusions without creating a
person. Contributors alone do not qualify. The saved-dossier adapter explicitly
preserves those distinctions.

Resolve `person_id` or a stored stable `account_id` before insertion. Conflicting
links retain a personless `staff_intakes` observation with `needs_review`; replay
it after resolving the identity. A pending cross-source match is not confirmation.
An account's own provisional observation is repeatable, including handle changes.
A name never merges two people. An accountless
source key receives a stable UUID without a placeholder X account. A supplied
account ID must already exist; the importer never guesses an ID from a handle.

Names accept `full_name`, language, source kind/reference/excerpt and collection
method, plus optional sourced components. A `supports_fields` list must explicitly
support given/family components. Optional `review` includes status, reviewer and
reason; only confirmed names can become a primary/English `selection`. A derived
name refers to an earlier manifest name's `key` using `derived_from_key` and keeps
its `generated` or `converted` origin after corroboration. Legacy name backfills
retain unknown provenance and do not automatically become confirmed selections.

Affiliations use the existing `PersonBrandAffiliation` fields, plus `source_url`,
`evidence_text` and optional `source_data`. Keep full original titles, dates and
their precision, department/team and role-specific location. A profile location
or company headquarters does not establish role location. Prose in `texts` has
kind, source language, original text and source reference; its translation cache
uses the exact original version. Names are researched at intake, never passed to
the prose translator.

Media entries require publisher `source_url` and `source_kind`, with optional
original asset URL, local path, discovery provider, kind and evidence. An explicit
review records source attribution, individual-portrait suitability and reuse
status separately. A logo/avatar cannot fill a portrait gap. Video pages are
retained as references; this implementation downloads and validates image bytes,
not video streams. SerpApi discovery thumbnails require source review and may be
replaced by an original publisher image through a later manifest.

Review commands preview unless `--apply` is present:

```bash
python manage.py review_staff_collection name 123 --status confirmed --select english --reviewer Allen --reason 'Named personal biography' --apply
python manage.py review_staff_collection media 456 --source-verified --individual-portrait --suitability approved --reviewer Allen --reason 'Company bio labels this individual portrait' --apply
```

Reviewing a portrait does not imply reuse permission. Set `--reuse permitted` only
when its evidence supports that separate decision. Review history is retained.

## Correcting identities and job history

Use `correct_person_identity` to preview a specific correction. Add `--apply`
to record it. Supply an existing destination person; a split never guesses which
records belong together. For account confirmation, source and target are the
same person ID.

```bash
python manage.py correct_person_identity merge --source OLD_UUID --target KEPT_UUID --reviewer Allen --reason 'Same individual in both sourced profiles' --request-key review-001
python manage.py correct_person_identity split --source OLD_UUID --target OTHER_UUID --selection /private/selected-rows.json --reviewer Allen --reason 'Two different researchers' --request-key review-002
python manage.py correct_person_identity confirm_account --source PERSON_UUID --target PERSON_UUID --account-id STORED_ACCOUNT_ID --reviewer Allen --reason 'Personal site links this account' --request-key review-003
python manage.py review_person_affiliation OLD_CLAIM_ID NEW_CLAIM_ID --reviewer Allen --reason 'Reviewed departure announcement'
```

A split selection is a JSON object whose optional arrays are `names`,
`affiliations`, `texts`, `intakes`, `media` (row IDs), and `accounts` (stored X
account IDs). Include complete employment replacement and text derivation
chains, and the texts attached to a moved affiliation. Invalid dependencies,
conflicting identities and running collection workers stop the transaction.
Text collisions involving derivation need separate review and are refused.
Repeat the same request key only for the exact same correction.

The correction journal preserves the operator, reason, source rows and mappings.
Original name rows remain addressable; a split rejects their old attribution
and copies the representation and evidence to the selected person. A merge
redirects the retired person ID and preserves paid-request history and cache
reuse. No global constraint bypass or automatic same-name merge is used.

Job replacement is a separate decision from `current`/`former` employment status.
It keeps the earlier claim and records who replaced it and why. A later observed
date alone does not settle a contradiction. Replacement must stay within the
same person and organization; concurrent roles stay separate. The dossier and
default roster use unreplaced, nonrejected claims; current collection needs a
current claim or the independent operational account-intake eligibility.

Each affiliation can include a `titles` array. Entries contain `text`, `language`,
`source_reference`, `origin` (`source`, `translation`, `summary`, `unknown`),
`review_status`, and `review_note`. Optional `key`/`derived_from_key` link a
translation to an earlier title in that array. Titles are attached to that exact
affiliation. General biography/location prose remains in the person's `texts`.

For an existing saved DeepSeek import, preview and apply
`python manage.py normalize_staff_dossier_fields [--apply]`. It creates dedicated title
records from the saved audit without editing the intake; ambiguous job matches
remain `needs_review`. Dossier title display reads the dedicated records, and
the intake payload remains the original import/search journal.

Python services perform matching, review, selection, queue registration and
budget checks. PostgreSQL enforces foreign keys, confirmed-account uniqueness,
name-selection provenance, same-person text/job links, replacement consistency,
immutable source versions and the append-only correction journal. Raw SQL does
not run Python callbacks; run the catch-up command after authorized bulk writes.

## Existing population and ongoing arrivals

```bash
python manage.py backfill_staff_collection --list-id 2067062923525275922
python manage.py backfill_staff_collection --list-id 2067062923525275922 --apply
python manage.py run_staff_collection_worker --once
```

The population is the union of active stored Call A membership, both company and
brand staff-role tables, and people with current, unreplaced, nonrejected
employment/founder claims. Former and dated claims remain available in history.
Official company accounts are excluded. The frozen output includes overlap and
identity-review failures. This reads stored membership; it does not make a fresh
authenticated X list request. Preserve the capture provenance when supplying a
new private-list snapshot through the existing list-reconciliation path.

Manual staff-role saves and personnel/profile affiliation writes register work
after their transaction commits. The report's subject receives the work, not its
author. A polling worker with `--list-id` runs a catch-up scan every five minutes
to recover bulk writes and missed callbacks. The operator can run the same catch-up
command independently. No HTTP runs in account creation or harvest transactions.

## Network and storage configuration

Network collection requires both `--enable-network` and
`STAFF_COLLECTION_NETWORK_ENABLED=true`. It also requires
`STAFF_MEDIA_DURABLE=true`, which is the operator's assertion that storage is
shared and durable. Configure `STAFF_MEDIA_STORAGE_BACKEND` and its JSON
`STAFF_MEDIA_STORAGE_OPTIONS` for an installed Django backend, or use the default
filesystem backend with `STAFF_MEDIA_ROOT` on a persistent shared mount. The local
default `.local/staff-media/` is suitable only for a disposable pilot.

No default schedule or Render Blueprint is changed. For a separately authorized
activation, provision the storage and an independent worker, set the environment
flags and use a bounded invocation such as:

```bash
python manage.py run_staff_collection_worker --list-id 2067062923525275922 \
  --enable-network --provider serpapi_baidu --per-person 3 --per-run 25 --per-day 50 \
  --max-seconds 3600 --poll-seconds 15 --run-id REPLACE_WITH_PERSISTED_UUID
```

These numbers are an operating example, not authorization to spend. Budget caps
must be explicitly selected at activation. Keep the same `--run-id` when resuming
that bounded run. A supervisor can invoke another authorized bounded run after it
exits. The worker processes one active lease at a time across processes. Source
metadata, pending review, zero results and exhaustion all remain inspectable.

Only records explicitly marked `baidu_eligible: true` with a disambiguated
`baidu_query` use Baidu. The importer does not infer Chinese nationality from a
name. Set that flag through reviewed intake when the owner's China-only search
scope applies. Other staff still receive local-evidence and source-media work.
The credential is a nonempty `SERP_API_KEY`, then `SERPAPI_API_KEY`; no other search
or X provider is a fallback. The [SerpApi Baidu API](https://serpapi.com/baidu-search-api)
adapter requests one page with `rn=50` and `pn=0`. A search result or thumbnail is
not an identity-verified photograph. Request/asset counts are distinct.

## Recovery and activation evidence

### Schema release and rollback

Migrations 0059–0061 physically rename `people.sexs` to `people.sex`. Old and new
application revisions cannot safely share this column during a rolling release.
For a separately authorized release, take a database backup and coordinate the
web, harvest and other Person readers so old code stops before migration and new
code starts afterward. Keep network collection disabled throughout that change.
This pull request does not activate or schedule that release.

Before migrating, save these read-only results with the selected database and
revision. Repeat the counts after migration, before importing any new staff; use
`sex` in the second query afterward. Counts and the value distribution must match.

```sql
SELECT 'people' AS relation, count(*) FROM people
UNION ALL SELECT 'people_accounts', count(*) FROM people_accounts
UNION ALL SELECT 'people_brand_affiliations', count(*) FROM people_brand_affiliations
UNION ALL SELECT 'people_brand_affiliation_evidence', count(*) FROM people_brand_affiliation_evidence;
SELECT sexs, count(*) FROM people GROUP BY sexs ORDER BY sexs NULLS FIRST;
```

After migration, these checks must return zero invalid selections and zero legacy
names without their unknown-source evidence. The backfill intentionally leaves
both display selections empty until a name is reviewed.

```sql
SELECT count(*) AS invalid_selections
FROM people p
LEFT JOIN people_names n ON n.id = p.primary_name_id
LEFT JOIN people_names e ON e.id = p.english_name_id
WHERE (p.primary_name_id IS NOT NULL AND
       (n.person_id IS DISTINCT FROM p.id OR n.review_status IS DISTINCT FROM 'confirmed'))
   OR (p.english_name_id IS NOT NULL AND
       (e.person_id IS DISTINCT FROM p.id OR e.review_status IS DISTINCT FROM 'confirmed'
        OR e.language NOT IN ('en', 'en-Latn')));
SELECT count(*) AS legacy_names_without_evidence
FROM people_names n
WHERE n.origin = 'legacy' AND NOT EXISTS (
  SELECT 1 FROM people_name_evidence e
  WHERE e.name_id = n.id AND e.source_kind = 'legacy_unknown'
);
```

A rollback must coordinate code and schema too. Before any new intake, restoring
the pre-release database backup together with the old code restores the old
column contract. After new intake, reversing these migrations would drop collected
names, evidence and media records: preserve that data and use a forward repair or
an explicitly planned data-preserving rollback. Keep stored media bytes with the
database backup; database rows alone cannot restore them.

### Collection recovery

Reservations are written before sending a paid request. Complete identical query
fingerprints reuse their saved response. Failures and interrupted reservations
count against the caps and require review, because the provider may already have
charged. Per-person caps are lifetime reservation counts for this provider;
per-day caps use UTC. Budget exhaustion schedules a later attempt without
deleting the work. Leases last three minutes; stale results cannot change work
state or attach candidates. Expired local-only leases retry at most three times.

Requeue unchanged work explicitly after supplying missing media/configuration:

```bash
python manage.py review_staff_collection work 789 --reviewer Allen --reason 'Storage restored; retry local media' --apply
```

For a held provider reservation, first inspect provider/request evidence. If a
new charged attempt is deliberately authorized, `request-retry` preserves the
original reservation, records reviewer/reason and releases its query identity:

```bash
python manage.py review_staff_collection request-retry 123 --reviewer Allen --reason 'Provider receipt reviewed; another request authorized' --apply
```

This still obeys all caps. It cannot retire a successful request, repeatedly
retire an old reservation, or requeue active work. Never remove request history
to make a cap pass. Raw responses strip credential fields and query parameters;
errors retain categories, not credential-bearing exception URLs.

Before calling production G1 active, observe an actual user addition, a real
personnel subject, catch-up, restart/lease recovery and the resulting stored
media/dossier. Account for every frozen batch entry, Chinese/English name gaps,
portrait gaps and reuse decisions. A passing local DeepSeek import or open PR
establishes scaffolding behavior; full-population coverage and production
activation require their own observed results.
