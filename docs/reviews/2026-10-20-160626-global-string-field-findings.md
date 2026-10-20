# Global CharField/TextField review — first inventory and recommendations

Status: source-grounded database-wide recommendations. The owner has approved the shared-definition, naming, preserved-evidence and scoped-claim policies. Exact physical design and implementation endpoint remain open. No schema is implemented by this document.

The owner appoints G2 session `g2-chartengine-01a15790` to lead this global review and reports G3 data backfill halted for it. Scope includes all application tables on current main, sister G2 EventDossier, G3 collection working schema, and the ChartEngine proposal. G3 handoff retains implementation/migration ownership in G3; this session returns exact field recommendations without changing that worktree. Earlier deferral of dossier vocabulary comments is superseded for this global field review.

Current main is64b95c26 with migrations through0092. G2 is2daeb735 with dossier0093/0094. G3 is64b95c26 plus dirty collection0093–0107. These are separate local variants, not an integrated deployed schema. Source-only inspection; no live DB access or data-value census has occurred. App framework/auth internals are excluded; `core/models.py` is the application's only model module.

Inventory counts below are static model field positions including abstract-field inheritance. G3 handoff's593CharFields in135declaring classes matches direct declarations; the expanded concrete-table inventory has598CharField columns and327TextField columns. The figures use different counting units; neither is production row-count evidence. Repeated names are candidates, not proven defects.

| Schema variant | Concrete models | CharField positions | TextField positions |
| --- | ---: | ---: | ---: |
| Main64b95c26 |151|502|305|
| G2 dossier2daeb735 |158|516|325|
| G3 dirty through0107 |160|598|327|
| ChartEngine proposal |9|50|4|

The combined inventory contains1,013unique(table,column)positions across variants and2,627variant-specific entries. The overlapping variant totals must not be added as if they were one deployed database. Chart proposal includes its already-referencing post key; a text-backed FK is not unconstrained text.

## Decision rules

Prefer existing shared records for entity identity and business vocabulary. A catalogue can itself have a textual primary key; the issue is shared meaning, constraints and ownership. Preserve actual prose and source-native evidence when justified. Distinguish snapshots from editable duplicates. Share small internal choices only when meanings match, and enforce them at DB/write boundaries. Do not create one universal values/status table, one catalogue per column, or replace strings with JSON.

The owner approved FK catalogues for business vocabularies, shared checked choices for internal states, and preservation of exact source wording alongside resolved references. Both recommendations are now approved by the owner. Exact catalogue inventories, field layouts and migration mappings still require design; broad policy approval is not approval of every proposed table. The prior nine-table ChartEngine field layout is reopened by this global review; its dossier-owned atomic architecture remains settled.

The canonical database skill now requires CharField/TextField review and says: “Ask the user before settling unresolved string storage.” The updated skill and aliases validate; no redundant user confirmation is required for already-settled meanings.

## Source-grounded findings

### Timezones

Confirmed repeated concept; shared catalogue candidate.

Fields: `metrics.source_timezone`, `metric_values.source_timezone`, `events.source_timezone`, `opportunities.source_timezone`, `event_dossier_claims.event_timezone`, `collection_corrections.before_source_timezone` and `after_source_timezone`, plus both proposed chart timezone fields.

Recommendation: No TimeZone model exists in inspected schemas. Propose one shared IANA-identifier catalogue and FK references, with unknown represented explicitly and never coerced to UTC. Preserve source wording/legacy hashes and reviewed alias mapping; a fixed UTC offset is not a timezone catalogue. The exact new catalogue definition and integration rollout remain to be settled.

### Languages and locales

Repeated text across labeling, extraction, evidence and UI.

Fields: `post_type_labels.lang`, other label-table `lang` fields, `posts.lang`, translation `source_language`/`target_language`/`locale`, `people_names.language`, `people_texts.language`, `people.primary_language`, `editorial_editions.locale`.

Recommendation: No shared Language/Locale model exists in inspected schemas. Review one shared catalogue with separately meaningful language and locale references. Do not equate UI locale configuration with the complete source-language universe. Retain raw provider tags where provenance requires them; map existing UI aliases without rewriting old evidence.

### Metric definitions and units

Existing shared identities should be reused.

Fields: Existing `metric_types` and versioned `metrics`; proposed `chart_series.metric_key`, `unit`, `quantity_form`, and copied `chart_metric_inputs.source_*` definition fields.

Recommendation: Replace independently editable chart metric codes with existing metric-type/source-metric references where semantics match. Derived line transformations remain explicit. Definition-owned metadata should be derived from the exact immutable definition version rather than another editable copy. Existing readers compare a pinned definition snapshot and reject changes, so FK-only replay requires proven version immutability; retain a specifically justified snapshot until that guarantee exists. No existing Unit model was found; a shared unit catalogue is a candidate, not an approved addition.

### Actor, method and policy identity

Text can conceal identities and independently versioned definitions.

Fields: `event_dossier_reviews.actor`, `method_version`, `ranking_method`; `event_dossier_claims.extraction_version`; `collection_corrections.actor_identifier`/`policy_version`; `taxonomy_versions.reviewed_by`, `metric_collection_contracts.reviewed_by`, `source_subject_mappings.reviewed_by`; provider/model fields on processing records.

Recommendation: Resolve whether an actor is a human, agent or system identity before choosing a shared record; an auth-user FK alone cannot represent all three. Scope method/version identifiers to a named method family and preserve the exact implementation/configuration version. Do not equate inference provider model names with tracked release Product identities. No new actor/method registry is selected without the required owner answers.

### G2 dossier claim meaning and scope

High-priority schema-contract gap.

Fields: `event_dossier_claims.claim_kind` and TextField `scope_key`; `event_dossiers.event_kind`; release `release_channel`/`availability_state`/`disclosure_state`; `personnel_change_details.change_kind`.

Recommendation: The claim writer stores supplied kind/scope in its hash and validates timezone; tests use announcement/x and repository_created/repository. That does not establish an authoritative shared claim vocabulary or the meaning/cardinality of scope. The owner selects one scoped claim per channel/region availability fact; use explicit existing references for that scope and reuse announcement evidence. Review event/release classifications as business vocabularies. Review/disposition codes are separate from release availability; never merge their shared word “unknown.”

### G2 dossier source wording and narrative

TextField is sometimes the correct evidence representation.

Fields: `assertion_text`, `source_excerpt`, `reason`, `display_title`, `observed_name`, `native_identifier`, `version_label`, `variant`, `observed_person_name`, `from_organization_name`, `to_organization_name`, `from_title`, `to_title`.

Recommendation: Verbatim assertions/excerpts/reasons and authored titles can remain prose. Resolve identities separately through existing Product, Person, Company and affiliation links without erasing source wording. Existing `roles` classifies accounts (official/researcher/executive), not exact employment titles: do not force title strings into it. Model variant/version/native identity require their own cardinality and namespace review; they are not automatically display prose.

### G3 execution, coverage and reasons

Same spelling does not prove one vocabulary.

Fields: `collection_jobs.state`; `collection_runs.status`, `execution_state`, `coverage_state`; scope admission/execution/coverage/outcome; `collection_attempts.outcome`/`stop_reason`; `collection_requests.transport_outcome`; observation processing outcome; metric-gap/correction reason codes.

Recommendation: Trace transition writers and reports, then share a definition only where meaning and allowed transitions match. Execution completed, request received and coverage complete are distinct facts. Shared code choices with DB constraints are the owner-approved representation for internal states. Business-managed reasons/classifications may warrant domain-scoped catalogue rows. No universal status table is proposed.

### G3 kinds, request coordinates and opaque evidence

Separate selected dimensions from source tokens.

Fields: Target kind/role/resolution, request group/config/category, input role, resource kind, archive media_type/encoding, `collection_job_targets.membership_run_reference`, provider revisions, ETags, cursors and row locators.

Recommendation: Inspect actual consumers: request config/category/group can be analytical dimensions; input roles are relationship semantics; cursor/ETag/provider revisions/row locators are opaque evidence and may remain text. `membership_run_reference` needs a specific referent or preserved external namespace, not an arbitrary string-to-FK conversion. Keep exact request/resource/observation distinctions and existing evidence archives; never move operational fields into retained JSON.

### Existing geography and relationship registries

Concrete reuse targets outside ChartEngine.

Fields: `companies.hq_country`, `people.nationality`, job/opportunity currency fields, `accounts.source_query_ids`, `account_post_appearances.source_query_ids`, `posts.source_query_id`, `content_pictures.content_kind`/`content_id`.

Recommendation: Country/Region and SearchQuery already exist. Inspect whether each field is source text or canonical identity and whether nationality or query membership is one-to-many. Do not replace a plural string with a single FK. External post/reply IDs can refer to uncollected records and need not become invalid mandatory FKs. Polymorphic content IDs need an explicit target contract. No new shared country/query table is needed.

### Temporal strings, hashes and scalar values

A field-type audit also catches non-catalogue modeling.

Fields: `people.date_of_birth`; affiliation start/end strings; event/opportunity start/end/open/close values; `posts.created_at_raw`; revision hashes, identity keys and brand accent colors.

Recommendation: Review temporal strings together with precision and source wording; never fabricate a missing date component. Raw timestamps and exact provider tokens can remain preserved evidence alongside typed values. Hashes and validated colors are scalar data; repeated values alone do not justify entity tables. Renaming TextField to CharField is not a normalization fix.

## G3 implementation return map

G3 retains its nine-table collection design and owns any accepted migration/code changes. The linked collection CSV includes every CharField/TextField position in the15model area named in the handoff, including existing tables and all nine additions. It is a complete field inventory with triage families, not approval to normalize each field or proof that each family is a defect.

1. Reuse DataSource, metric definitions, MeasurementSubject, reviewed mappings and typed request/observation/input links; do not create parallel identity catalogues.
2. Align shared timezone references and precision/basis/unknown-reason definitions with G2's global decisions; preserve before/after correction evidence.
3. Keep admission, transport, execution, processing, coverage and terminal-stop outcomes distinct unless actual transition contracts prove equivalence.
4. Catalogues and any definition immutability changes need coordinated additive migrations after the current0093–0107 branch and sibling dossier0093/0094 leaves are integrated. Do not invent a migration number in advance or rewrite peers' migration histories.
5. Backfill aliases and matched references with reconciliation reports. Preserve NULL/unknown/unmapped cases and raw evidence; no fallback timezone, fabricated identity, changed historical hash or lost source value.
6. Switch each writer and reader—including bulk and correction paths—before retiring an old text field. Require focused allowed/invalid-value, missing-reference, historical-replay, row-count and identity checks on isolated PostgreSQL. Existing G3 local checks are not global-migration proof.
7. This review does not resume the owner-halted backfill, restart schedulers, collect providers or grant production/deployment authority. Return unresolved product meanings to the owner; do not silently fill them with new strings.

## Evidence and limits

Inspected core models and migration boundaries; main/G2 `CONCEPTS.md` and `docs/reference/db-schema.md`; G2 `core/event_dossiers.py`, `core/benchmark_metric_identity.py`, `core/benchmark_metric_series.py`, `tests/test_event_dossiers.py`; G3 `core/collection_capture.py`, `core/collection_instructions.py`, `core/collection_matching.py`, `core/collection_resources.py`, `core/collection_corrections.py`, `core/collection_reports.py`, and its selected collection plan. Source line/hash provenance is in the inventory CSV. The main source snapshot is recoverable with `git show 64b95c26:core/models.py`.

IANA defines timezone identifiers as zones or links: https://www.iana.org/time-zones/theory. Python ZoneInfo accepts IANA keys available in its timezone-data search path: https://docs.python.org/3.14/library/zoneinfo.html. Shared references therefore need a deliberate identifier/alias policy; local library availability alone does not establish a canonical database catalogue.

Inventory families are automated triage; semantic decisions remain source-verified findings or explicitly open questions. The report does not claim every field has passed design review. The next pass applies the approved catalogue/choice, source-evidence, naming and atomic scoped-claim decisions, then traces the remaining high-priority writer/reader families and revises the global schema/migration plan in the existing plan.

## Owner decisions applied — October20 continuation

The owner approved both recommendations: business vocabularies use shared catalogue records and foreign keys; internal workflow states use centrally defined choices enforced at the database/write boundary. Preserve exact source wording alongside resolved references. These questions are resolved and must not be asked again.

The owner further requires a global column-name contract. General business names belong to shared definitions. Independent concepts with different definitions use different descriptive names. Role prefixes such as source_timezone_id and bucket_timezone_id can reference the same shared timezone catalogue. Distinct request transport, collection execution, collection coverage and dossier review states retain distinct names and definitions. A catalogue primary key may itself be text; this rule targets duplicated meaning and weak relationships, not every text-backed SQL value.

The owner approves one separately scoped EventDossier claim per channel/region availability fact, reusing the same announcement evidence when appropriate. Do not make one claim span several availability channels/regions or give all of them one invented common access date.

### Shared-name dictionary and reference contract

| Concept / approved naming rule | Reference or definition | Important boundary |
| --- | --- | --- |
| language_id; source_language_id; target_language_id | One shared language catalogue | Preserve reported source tag separately where needed; UI locale is a different concept |
| locale_id; presentation_locale_id | One shared locale definition linked to language | A locale is not renamed to language; no claim that UI choices cover all source languages |
| timezone_id; source_timezone_id; bucket_timezone_id; event_timezone_id | One shared IANA timezone catalogue | Unknown never becomes UTC; source/bucket/event are roles, not independent zone definitions |
| unit_id; measurement_window_unit_id | Shared measurement-unit definitions | Keep quantity/duration basis and metric semantics explicit; do not equate day with a fixed24hours |
| metric_type_id; source_metric_id | Existing metric_types and exact versioned metrics rows | Derived metric transform stays explicit; immutable replay must not read mutable current meanings |
| review_actor_id; correction_actor_id | Shared actor identity contract for humans, agents and systems | Preserve actor_identifier_reported; database-user identity alone is insufficient |
| extraction_method_version_id; review_method_version_id; timing_policy_version_id | Domain-qualified immutable method-version definitions | Internal extraction versions and provider methodology labels are different namespaces |
| claim_kind_id; event_kind_id | Domain-specific business catalogues | “Announcement” and “usable access” have distinct machine-readable meanings |
| access_channel_id | Shared access-delivery catalogue: e.g. API/downloadable weights | Different from stable/preview/beta release maturity |
| release_maturity_id | Shared release maturity: stable/preview/beta | Replaces misleading model_release_details.release_channel meaning; no string-value migration inferred |
| release_availability_id; release_disclosure_id | Separate business definitions and catalogue references | A release being announced and being usable are different facts |
| request_transport_outcome; run_execution_state; run_coverage_state; scope_execution_state; scope_coverage_state; dossier_review_state | Checked internal choices, shared only for identical meanings | No generic status table or silent merging of execution, coverage and review |
| reported_*_text; *_snapshot where justified | Verbatim source or frozen historical value with explicit owner | Keep names distinct from canonical FK columns; avoid duplicating raw text already retained in source capture |
| *_sha256; provider_revision_text; provider_etag_text | Validated hash or opaque source token | Preserve exact bytes/namespace; values are not business catalogues merely because they repeat |

These are logical naming/reference contracts, not final generated SQL names or approval of every candidate catalogue table. Existing Product, Person, Company, Country/Region, MeasurementSubject, mapping and source records remain the first reuse targets. New shared-table counts and immutable-definition implementation still need the complete integration design.

### Concrete G2 EventDossier return recommendations

- event_dossier_claims.claim_kind → claim_kind_id. Replace overloaded scope_key with explicit scoped references matched to that single fact; use existing product/repository/source and Country/Region identities where applicable. Preserve legacy scope wording/hashes rather than rewriting a completed claim. Evidence platform and availability channel are distinct: a post on X can evidence API access.
- event_dossier_claims.event_timezone → event_timezone_id, referencing the same shared timezone catalogue as measurement and chart roles. source_excerpt/assertion_text stay evidence prose with preserved source/claim hashes.
- model_release_details.release_channel → release_maturity_id because its current values are stable/preview/beta. Add/reference access_channel_id only at the scoped-availability claim owner; do not put a single mutable availability channel on the whole dossier.
- model_release_details.availability_state/disclosure_state → release_availability_id/release_disclosure_id as separate shared business definitions. event_dossier_reviews.review_state → dossier_review_state, a checked review workflow, not the release business state catalogue.
- event_dossier_reviews.actor → review_actor_id with an explicitly named reported identity if source history needs it; method_version/ranking_method → review_method_version_id/ranking_method_version_id. Claim extraction_version uses extraction_method_version_id. Exact physical actor/method schema is still a design item, not an invented auth-user relationship.
- observed_name/observed_person_name/native_identifier/from_organization_name/to_organization_name/from_title/to_title retain their source-evidence role, named reported_* or *_snapshot in the final dictionary. Resolve Product/Person/Company/affiliation links alongside them; do not overwrite the source wording or map employment titles into account-classification roles.
- One announcement can produce API-access, weight-access and region-specific claims with shared evidence but separate meaning/date/disposition. Resolved business references must be immutable/version-pinned where historical meanings can change.

### G3 exact-field return map

The G3 CSV now includes proposed semantic names, representation, shared target/choice definition, provenance handling and remaining review requirements for all147fields. It is a recommendation map for G3 to apply in its own worktree, not evidence of a completed migration or acceptance of every candidate shared table.

The inspected collection_state.complete_attempt maps legacy status success to execution completed and coverage complete/partial, while legacy partial maps execution yielded and coverage partial. Therefore collection_runs.status cannot simply be replaced by a FK to a universal status list. Keep it explicitly named as a legacy compatibility result until all real readers/writers move to separately defined execution and coverage contracts. Preserve job scheduling state, request receipt/transport, metric missingness and review state as different concepts.

No current owner question remains pending from the three decisions above. Further field-specific questions must identify a genuinely unresolved meaning; do not ask again about catalogue-versus-choice, source-wording preservation or one scoped claim per availability fact.

### Global and sister-schema naming maps

The [34-field G2 dossier map](../analysis/2026-10-20-160626-g2-dossier-field-recommendations.csv) and [141-position global naming review](../analysis/2026-10-20-160626-global-column-name-review.csv) apply the approved dictionary beyond the [147-field G3 map](../analysis/2026-10-20-160626-g3-string-field-recommendations.csv). Naming candidates with unresolved exact vocabulary/target definitions remain labelled as recommendations. No candidate catalogue count, enum value set or migration is inferred approved merely because its naming rule is settled.

## Entire application database expansion — October 20

### Plain-English Summary

The shared-definition and column-naming rules apply to every application table, including tables outside ChartEngine, EventDossier and collections. Business vocabularies reference shared definitions; internal states have centrally defined allowed values enforced at the database/write boundary. Different meanings get different descriptive names. Exact source wording, opaque source identifiers, genuine prose and necessary immutable snapshots remain preserved with explicit roles.

The expanded audit gives a recommendation for every inventoried string position and includes every concrete application table, including those without literal string columns. It does not settle every physical target or complete the migration design. No application model, migration or database has been changed. The pending owner question distinguishes completing the database-wide design from also implementing model, migration and caller changes; the four approved design decisions are not being reopened.

### Coverage and artifacts

- [Entire-database field map](../analysis/2026-10-20-160626-entire-database-field-decisions.csv): 1,013 unique literal CharField/TextField positions across the three schema variants and the reopened chart proposal. Each has a proposed semantic name, representation recommendation, definition/preservation requirements and explicit design status. Family-level recommendations still need exact allowed values, cardinality and caller verification; a populated row is not a passed semantic review.
- [Every concrete application table](../analysis/2026-10-20-160626-entire-database-table-coverage.csv): 151 main + 158 G2 + 160 G3 entries, 469 overlapping model-variant rows representing 167 existing table names. Nine proposed chart tables remain separately identified in the field map. Nineteen variant entries have no declared/inherited literal CharField/TextField.
- [String subclass review](../analysis/2026-10-20-160626-global-string-subclass-review.csv): 24 unique URLField positions, 72 overlapping variant entries. These retain validated source/resource-locator meaning; a shared URL vocabulary is not proposed.
- [Browser walkthrough](../analysis/2026-10-20-160626-global-string-field-audit.html#entire-db) and [source-grounded findings](../reviews/2026-10-20-160626-global-string-field-findings.md) remain the human-readable entry points. The original inventory retains source lines and hashes.
- Existing FK columns with text target keys are already relationships. JSON/arrays are separately owned storage boundaries, not silently converted by this field audit. Framework/auth tables retain framework-owned contracts; application actors may reference authenticated users while also representing agents/systems. No new JSON/JSONB column is proposed or approved.
- Source hashes match the recorded main snapshot and the inspected G2/G3 working files at this checkpoint. These counts describe source variants; deployed migration drift, unmanaged tables and external writers must be reconciled before any migration execution.

### Additional concrete findings beyond the focused maps

1. `accounts.source_query_ids` and `account_post_appearances.source_query_ids` encode plural relationships. Reuse SearchQuery and the actual account/appearance owner; replacing either field with a single FK would lose cardinality. Prove whether each writer is active or legacy before choosing normalization versus retirement. `posts.source_query_id` has a current SearchQuery reader in targeted extraction and needs its own source-ID/unmatched contract.
2. `posts_unsanctioned_flags.flags` is documented as a serialized JSON array inside TextField, with generated `flag_set`. Trace active readers and writers; reuse UnsanctionedFlagKey relationships if still active, or retire only after proving legacy-only use. Its evidence text is a separate fact. No replacement JSON column is proposed.
3. `original_content_calls.budget_scope` is used for accounting by scope/day and can contain `backfill:<job.pk>` as well as workflow labels. Identify budget owner and optional job relationship, preserve original reservation grouping, and prevent double counting across cutover. It is not safely normalized by adding one workflow FK.
4. `call_state.bucket` and `harvest_backlog_windows.bucket` are legacy query-identity components. Current v2 calls use None normalized to an empty-string sentinel. Census nonempty stored values and uniqueness before retiring the component; never change cursor identity by a cosmetic rename.
5. `original_content.brand_key_snapshot` and `trend_narrative_subjects.canonical_key_snapshot` intentionally preserve historical identity. The latter can contain a Brand nickname or Product repository/product key according to identity type. Retain the explicit namespace and existing resolved relationships rather than introducing an editable generic key catalogue.
6. `posts_brands_classification_judgments.selector_version` is included in the stable revision hash. `trend_narrative_demands.target_contract_version` selects the requested narrative contract independently of prompt/model versions. Resolve immutable version records while retaining old serialized tokens and hash-version rules.
7. `people_brand_affiliations.superseded_by_reviewer` identifies the actor who replaced a reviewed claim. Use the shared actor contract plus preserved reviewer wording, respecting the existing replacement-history trigger. Unknown reviewer labels must not become fabricated authenticated users.
8. `rare_type_search_runs.error_detail` is diagnostic prose, distinct from machine-readable `error_code`; current dispatch/failure paths clear it. Retain it if a genuine diagnostic consumer exists, or retire after the full caller census. A catalogue of arbitrary exception prose is not justified.
9. Date strings with precision need a typed partial-date contract that preserves year/month/day precision and exact source wording. Converting a year to January 1 is prohibited. Country/Region M49 codes retain leading zeroes as validated standard codes on their existing owning catalogues.

### Coordinated implementation sequence, after physical design is settled

These units belong to this same plan. They do not create another plan, select deployment, or grant writes to peer worktrees.

| Unit | Concrete work and dependency | Required completion evidence |
| --- | --- | --- |
| DB1 — reconcile source and deployment | Compare current main, committed G2 dossier leaves, G3 working collection leaves and read-only deployed migration state; inventory unmanaged SQL/generated columns and callers outside Django. Reconcile conflicting migration numbers after peer integration; do not renumber or rewrite another session's pending history. | Pinned source hashes/commits, migration graph and exact inclusion/exclusion list; no omitted active writer. |
| DB2 — settle shared definitions | Specify timezone, language versus locale, units, actors and immutable method/contract versions. Reuse Country/Region, metric definitions, subjects/mappings, Product/Person/Company/affiliation and SearchQuery. Decide each catalogue's identity, version/alias policy, uniqueness and unknown handling. | Exact physical columns, relationships, permitted values where fixed, representative reads/writes and explained table additions/retirements. Global new-table count remains unselected until this unit is complete. |
| DB3 — name and constrain internal choices | Trace actual execution, coverage, admission, transport, processing, review and stop transitions. Keep meanings distinct; replace overloaded generic names through compatible readers/writers. | One domain-qualified definition per meaning; DB check constraints and negative writes for invalid values; verified legacy run-result decomposition. |
| DB4 — resolve relationships and partial dates | Design query memberships, polymorphic content ownership, budget scope/job ownership, legacy cursor keys and precision-aware temporal facts. | Cardinality, uniqueness, source/unmatched handling and active-versus-retired caller evidence. No single FK for plural membership, no fabricated dates. |
| DB5 — additive storage and reference mapping | On an integrated candidate, add approved references/typed fields without dropping evidence. Build deterministic alias/value mappings and explicit unresolved reports; preserve original hashes and protected history. | Isolated PostgreSQL migration forward/reverse evidence where reversal is supported; row/identity counts and unmatched report. No default UTC, silent actor merge or erased raw value. |
| DB6 — writer and reader cutover | Update ORM, bulk writers, raw SQL, correction/review paths, services, imports, reports and API readers. Pin immutable definition versions for saved calculations/reviews; retain compatibility where required. G3 applies its owned collection changes. | Each field's writer/reader checklist completed; constraints hold at all write boundaries; no remaining active caller of retired meaning. |
| DB7 — regression net | Cover existing collection state/cursor behavior, dossier hash/review history, post attribution/query membership, classification revision hashes, OriginalContent accounting/replay, geography and partial dates. Exercise allowed/invalid values, unmatched references, duplicate memberships and historical replay. | Focused existing tests plus behavior-specific new cases pass on the integrated candidate; schema drift and database invariants checked. Document checks are not application proof. |
| DB8 — retire compatibility and document | Drop old columns only after mapping reconciliation and caller cutover, with a stated rollback/retention approach. Refresh authoritative schema references from implemented code. Follow the selected delivery endpoint separately. | Exact final table/column delta, documented retained source/snapshot fields and proven replay. Backfill stays paused until the owner authorizes its resumption. |

The global design is not implementation-ready until DB1–DB4 specify the actual target and DB2 records the justified table count. The prior nine-table ChartEngine proposal remains reopened; its atomic EventDossier chart ownership is still selected. This expansion changes neither delivery authorization nor the selected no-new-JSON policy.

## Strict review of the 428 tentative text survivors — October 20

### Plain-English Summary

The first-pass retention total is superseded. This pass reviewed the meanings, declarations and representative callers for all 428 fields in that bucket. It distinguishes source prose/identities and scalar hashes from canonical definitions, fixed-language duplicates, packed relationships and unresolved referents. It also distinguishes native source IDs already paired with a foreign key from genuinely missing relationships.

Of those 428 positions, 290 have a reason to retain text/scalar storage, and five more belong to centrally defined checked choices. Twelve native-ID compatibility fields already have companion Account relationships. The remaining 121 need references, locale-row moves, removal of redundant projections, typed relationship/key redesign, conditional retirement, or further owner/referent design. This is a stricter recommendation set, not migration execution or proof that all old columns can safely disappear.

### Exact disposition and coverage

| Disposition | Fields |
| --- | ---: |
| Retain justified source/prose/keys/hashes/snapshots/locators/tokens/scalars | 290 |
| Remain text as centrally defined, database-checked choices | 5 |
| Native evidence/compatibility already paired with Account FKs | 12 |
| Reference shared definitions, versions or canonical values | 44 |
| Move fixed-language values to locale rows, including four immutable snapshots | 27 |
| Reuse existing relationships / retire redundant projections | 7 |
| Redesign planner cursor identity or packed/mixed data | 13 |
| Conditional retirement candidates requiring caller/data proof | 5 |
| Explicit owner/referent design still unresolved | 25 |
| **Total reviewed** | **428** |

The [428-field strict review](../analysis/2026-10-20-172810-strict-retention-review.csv) records the field meaning, target, cardinality, declaration/source hash, caller evidence and preservation requirements. The [frozen original bucket](../analysis/2026-10-20-172810-strict-retention-baseline.csv) makes the before/after denominator reproducible. The [walkthrough](../analysis/2026-10-20-160626-global-string-field-audit.html#strict-retention) and existing entire-database/G3/general-name CSVs incorporate these corrections. Unreviewed fields outside this 428-field bucket retain their earlier provisional status; this pass does not convert the other 201 unresolved main fields into approved decisions.

A reference may coexist with reported source text; a translation move preserves wording in another row. Therefore 44 + 27 is not a claim that 71 textual values disappear. Twelve compatibility fields are not twelve newly missing Account relationships. In the 290 retained fields, 74 are digest/fingerprint/idempotency scalars, 23 own canonical keys, 109 preserve source wording/identity, 44 are genuine owned/localized prose, 11 are justified frozen snapshots, 15 are coordination/observation tokens, 12 are locators, and two are validated colors. Owning catalogue keys/names remain legitimate text on their authoritative record.

### Corrections that change the design

1. **Planner identity is not Brand/SearchQuery identity.** `monitor/cycle.py:_cursor_key` explicitly says `brand_id` may be `*` and `query_id` carries planner `call_id`. Both cursor/backlog tables need honest planner-specific naming and a preserved identity contract. A direct Brand or SearchQuery FK inferred from spelling would be incorrect. Eight legacy key components require migration design, not a generic lookup table.
2. **Existing account relationships must be reused.** Migrations 0066 and 0074 introduce generic Account relationships and native compatibility columns/triggers. Preserve existing nullability and source evidence; determine retirement only after native SQL/provider writers are cut over. Some native columns are themselves constrained SQL FKs despite their TextField declaration.
3. **Versions and classifications escaped the first pass.** Forty-four fields now point toward shared definitions/values, including classification contracts/taxonomies, prompt/query-pack/workflow definitions, provider verification/account/affiliate kinds, person-name kind, inference provider/model and career-site definitions. Classification taxonomy is not automatically the existing measurement TaxonomyVersion entity. Career `source_name` may be unresolved reported wording, so a canonical FK must not erase it.
4. **Fixed-language prose and names move to rows.** Reuse PersonName, PostTranslationText, PostSynthesisText, OriginalContentText and TrendNarrativeSubject where semantics match. Four frozen name-snapshot columns also move toward versioned locale rows: historical names and hashes survive; current mutable catalogue labels cannot replace them. Existing canonical/source names retain explicit source/unspecified-language meaning when the language is not known.
5. **Packed data remains a modeling issue inside TextField.** OfficialCompanyScan.cursor alternates scalar cursors, timestamp/PK positions and JSON-encoded frozen cohort members/queued/excluded state. Job adapters join plural locations into a middle-dot string. Budget keys pack initial/day/cycle ownership; EditorialHero.key mixes track:locale selection with a provider-lock sentinel; owner credential keys encode account/list context. These five fields need explicit typed components/relationships without adding JSON columns.
6. **Outcome and prompt wording are different.** PostSynthesisDemand.reason, person-name order, translation error code, headline acquisition outcome and source hash basis are checked values. ContentPicture.treatment is actual generated-image instructions assembled with a per-picture visual brief, so the full prompt remains prose beside a reusable method/prompt-version reference when justified.
7. **Native and execution namespaces differ.** Twitter-list membership source_run_id can be an official-owner claim token; list snapshot_id is a locally composed observation token. Neither is automatically a CollectionRun or AccountProfileSnapshot PK. ProviderBatch.import_cursor contains an existing call request identity, so reuse the actual call/import relationship rather than treating it as a remote cursor.
8. **Conditional retirement requires data proof.** The five field candidates include two fields on `_applied_config_snapshot` (one possible legacy-table retirement), collection legacy result projections, and a search diagnostic slot whose current writer clears it. Source inspection alone does not prove safe deletion or absence of nonempty historical values.

### New-table candidates from this slice

Five distinct owned locale-table candidates arise here. They are translation/snapshot tables, separate from the new shared language/locale/timezone/unit lookup candidates already identified. They are proposals, not five approved or implemented additions; integration may establish further reuse. Each needs a concrete key, uniqueness, versioning and writer/read contract before implementation.

| Candidate | Distinct row meaning | Why current storage is insufficient |
| --- | --- | --- |
| Brand labels | One brand's selected display wording in one locale | Brand currently uses fixed en/zh-cn columns; no existing BrandLabel model was found. Country/Region labels have different owners. |
| Company labels | One company's selected display wording in one locale | Company identity differs from Brand identity; its fixed-language columns cannot grow by rows. Existing person/country labels cannot own company labels. |
| Account profile-text translations | One captured profile-text role/version translated into one locale | PersonText translations belong to professional person prose; PostTranslationText belongs to posts. Neither can safely own account biography translations without changing meaning. Top-level description and nested profile_bio are distinct source roles. |
| OriginalContent frozen subject labels | One immutable content-owned subject-name snapshot in one locale | Current content stores fixed English/Chinese brand-name snapshots; current mutable Brand labels cannot preserve used historical wording. Existing OriginalContentText stores publication headline/body, not a subject-name role. |
| TrendNarrativeSubject frozen labels | One immutable narrative-subject name snapshot in one locale | Existing subject identity/linkage should be reused, but its fixed-language snapshot columns cannot accommodate additional locales. Its owner is distinct from an OriginalContent brand outcome. |

**Slice-level table delta:** five proposed addition candidates; one conditional legacy-table retirement candidate; zero selected/applied table changes. This is not the final global lookup-table count. Actor, method/version and provider-vocabulary physical layouts, plus global lookup additions, still belong to DB2. Existing table reuse is required before claiming any final addition total.

### Remaining 25 cases and verification contract

The 25 open cases are now explicit rather than hidden inside keep-text: eleven compound/owner-scoped keys, ten execution/cycle provenance fields, two evidence-source references and two credential/control revision identities. Their CSV rows state the actual observed meaning and the referent that still needs design. Do not synthesize executions, guess a CollectionRun FK, collapse namespaces or silently retain an arbitrary string to close these rows. These are outstanding physical ownership decisions, not a request to repeat settled catalogue/naming/source-preservation policies.

Verification for this document correction checks exact 428-field membership and uniqueness; current-main declaration/source hashes; all-field-map correspondence; 12 existing-account compatibility cases; 27 locale moves; classified outcome/hash-basis fields; cursor wildcard semantics; packed scan/locations evidence; local links and HTML desktop/narrow rendering. Evidence is model/source and document validation. It does not establish all active writer coverage, production data mapping, application tests, migration safety, runtime parity or a completed whole-database physical schema. DB1–DB8 and the backfill hold remain in force.

## October20 implementation-plan document review

The same canonical plan now contains active global-integration units U23–U30. Sequential main-thread review covered coherence, feasibility, scope, technical failure modes, sensitive refresh boundaries and locale behavior under the repository's tool-mapping rule. No independent agent or cross-model agreement is claimed.

Two corrections were applied within the planning request:

- Reuse the existing build migration runner and its cluster/application locks; migrations must support the application version still serving during build. The lock does not replace bounded mapping or concurrent-write checks.
- Make readiness explicit: ownership/design work can start, but database-writing batches require an exact physical manifest first. Four named catalogues are candidates, not a settled column/relationship design.

The later peer August coverage report was incorporated as new source evidence, with its observations attributed to that session. Range-discoverable coverage assessment design is required even without Post membership; no extra table, fake historical execution, numerical recall factor or ChartEngine eligibility policy is selected. August acquisition execution remains separate.

No proposed review fixes or user decisions remain from this pass. The outstanding physical mappings remain planned U23 design work and block affected implementation batches; this is not a claim of migration readiness. Source/path/ID/count checks and Ollija annotation are document evidence only. No application tests or migrations ran.

Reviewed plan SHA-256: `21efe1a1412aed2ab5b05448db8266a5df6558ac8b8b42856a853b5018ba3f66`. Detailed original claims, dispositions and coverage are retained in `/tmp/compound-engineering-501/global-schema-plan/resolved-document-review.json` on fuchitalee; the temporary path is not a durable project dependency.


## Final physical design review — 2026-10-20T21:54:32.435256+09:00

The [same canonical plan](../plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md) now has a complete source-level physical design. Its reviewed SHA256 is `8e31b532a43bca68a7b0366141b07f68696b3f721d73bab6f9708d521213c58b`. The [resolved review receipt](2026-10-20-215432-global-schema-final-review.json) preserves original findings, dispositions, scope, source pins and document verification. This is sequential main-session review, not independent agent/model review.

The final ledger has 959 existing/pending positions:326 remodeled,240 checked choices,376 justified text/scalars,12 existing-FK compatibility and5 conditional retirement.54 reopened chart positions remain deferred. The table manifest has64 proposed additions,0 mandatory retirements, and FK-target closure against167 existing/pending core table names. Each addition names purpose, columns, constraints and the gap in existing storage. Release families allocate64 once, in small compatible candidates. These are design counts, not deployed schema or net text-column reduction.

Three stale statements were corrected: five versus six locale owners, formerly uncertain fields treated as still undecided, and historical-X policy treated as an unanswered product question. No proposed correction or owner decision remains in the document review. Confidence strengthening added source-grounded mappings, explicit composite-key transitions, dedicated business/relationship caller scenarios, the existing external Render cron driver and range-assessment semantics.

Document assertions and Ollija annotation/check pass. The standalone walkthrough shows1,013field rows/64table cards, works at1440/390pixels without page overflow, filters the54deferred positions, and has no missing anchors, duplicate IDs or browser errors. This does not substitute for later application tests, value census, migration/staging tests or deployed-writer proof; none ran here. G1–G5/BackfillDB acknowledgements remain pending.

A final writer trace also corrected X `about_profile.source` to exact reported text rather than a checked internal enum, and qualified the unrelated membership/mention/person-text names. Four corrections are recorded in the final resolved receipt.


## Implementation source validation — 2026-10-21

The one canonical plan now resides in the clean `refactor/global-shared-vocabulary-20261021` checkout; the old ec5a plan path redirects to it. The former review receipts describe their original source-level snapshots, not the current code candidate. Actual G3 writer inspection corrected `collection_requests.method`: it is an HTTP transport verb, represented as checked `http_method`, with no DefinitionVersion FK. Source wording and old hash inputs remain preserved. Current959-position counts are325remodeled,240checked choices,377justified text/scalars,12existing-FK compatibility and5conditional retirement; the64-table design count is unchanged. This technical correction follows the owner's existing internal-choice rule and reopens no product decision.

The independent F0 candidate implements TimeZone, Language, Locale and MeasurementUnit with three additive migration boundaries and offline, hash-checked seeds. Fresh/forward PostgreSQL18 migration proof preserves the actual existing metric-definition writer and complete row values.54scoped tests pass, including24required PostgreSQL cases with no skips; the subsequent indexed-lookup simplification passes all9affected vocabulary cases. New code lint passes; the full legacy model file retains its177baseline RUF012 diagnostics with none added. Django system/migration-drift checks and a byte-identical offline seed rebuild pass. The reference inventory matches155core tables and1973columns for this candidate, including the4newtables/5columns. No staging/production migration, provider work, or global reference cutover occurred. G3's dirty collection source handover remains a prerequisite to central integration, rather than a presumed acknowledgement.
