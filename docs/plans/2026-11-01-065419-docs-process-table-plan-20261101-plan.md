---
title: Process table consolidation - Plan
type: refactor
date: 2026-11-01
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-planned
product_contract_source: owner-request-2026-11-01
execution: code
ollija:
  change_id: docs-process-table-plan-20261101-2026-11-01-065419
  branch: docs/process-table-plan-20261101
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
# Process table consolidation - Plan

## Plain-English Summary

Prevent each new workflow from adding its own run, call, budget and receipt tables, then consolidate existing families in separate, rehearsed changes. Preserve what the application knows, how spending is limited, and how interrupted work resumes. Existing person-name, affiliation and job-listing evidence stays separate because those records describe different facts and relationships.

The code checked out from `origin/main` has **221 physical application tables**, not 219. The existing staging production copy has **227**, including six tables from newer work. The recommended scope removes **25 net tables**: **221 → 196** on this branch's baseline, or **227 → 202** including the six staging additions. Against the original illustrative 219 baseline, the same reduction is **219 → 194**. Reaching exactly 190 would require more scope or unsafe conflation; this plan does neither.

The sequence is guardrails, budgets, classification vocabularies, provider calls, discovery runs, then event/opportunity dossiers. Each family gets its own branch and production-copy rehearsal. The budget phase keeps the request throttle separate. The call phase keeps the official-company business decision record and defers its operational decision JSON; it removes call envelopes and operational call JSON only after their typed replacements exist.

This session produces documentation only. Implementation and release require a later instruction. Staging is an existing populated rehearsal resource, but its newer migration history and current occupancy must be reconciled before any future write. No production connection, database write, R2 operation, implementation, deployment or merge is authorized here.

## Goal Capsule

- **Outcome:** fewer overlapping process tables, one documented default owner for each process record meaning, and continuous-integration checks preventing new accidental duplication.
- **Source revision:** `76834dba`, `docs/process-table-plan-20261101`, based on fetched `origin/main`; core migration files through `0205`.
- **Authority:** plan only; optionally commit and push this document on its docs branch. Future implementation remains `delivery_target: on-request`.
- **Execution:** independent family branches from the then-current `origin/main`; sequence dependent families after their predecessor is integrated under later authority. Do not run all migrations from this docs branch.
- **Stop conditions:** ambiguous ownership, missing row mapping, unavailable rehearsal environment, stale deployment image, parity discrepancy, unsupported source shape, or an operation that would interrupt live collection.
- **Readiness:** design and sequencing are actionable; the explicit environment and deferred-subscope gates below prevent treating the entire program as immediately executable.

## Product Contract

### Requirements

- R1. Name shared defaults for execution runs, provider/model calls, spend allowance windows, execution claims/leases, and raw evidence/receipts. Extensions must preserve the record's meaning and constraints.
- R2. Add a linked policy to `AGENTS.md`, extend M19 in `.agents/skills/avoiding-recurring-mistakes/SKILL.md`, and extend the canonical shared schema-walkthrough reference. Build on its existing reader-first and write-path consolidation rules.
- R3. Continuous integration rejects new process-shaped tables without demonstrated shared-table reuse/extension or a specific owner-approved exception in the selected plan.
- R4. Consolidate one family per branch and rehearsal, using additive storage, historical copy, writer/reader cutover, independent parity and guarded physical retirement.
- R5. Preserve limits, reservations, ambiguous spend, token/credit units, request identity, lease fencing, taxonomy meaning, historical evidence, source clocks and review state.
- R6. Keep name, affiliation, citizenship and job-listing evidence typed by domain. Keep RG5 `BusinessVocabularyCode` subclasses separate.
- R7. Measure application table counts using a declared denominator; include necessary new relationship/detail tables and retained tables in the arithmetic.
- R8. Reuse identified databases, object storage and services. Do not create another full local test database, fresh production restore, scheduler or service by inference.
- R9. Characterize current caller behavior before replacement; every family includes application-level regression coverage and realistic failure/restart proof.
- R10. Harvesting and other live collectors/workers continue throughout a future release. Use online copying, stale-row detection and bounded final delta checks; never stop collection to obtain a stable cohort.

### Boundaries and decisions from evidence

The requested six budget tables are not six interchangeable spending windows. `PostSynthesisRateLimitBucket` is a hashed caller throttle with two-day cleanup, unrelated to paid usage settlement. Retain it as a documented exception; consolidate the other five. This is the evidence-based scope adjustment allowed by the request.

`OfficialCompanyAttempt` also records owner attestations with no provider request. Keep it as the official-company decision journal; move only actual provider-call facts. Its `decision` document is consumed operationally by requalification. Removing that document safely requires a separate typed decision/citation design and is deferred here, rather than moving business state into an archive. Its `budget_keys` list is retired in U2.

The event family is a domain-identity consolidation, not a process-table merger. Its detail records remain typed. Discovery runs are a separate family and therefore a separate branch, even though the request grouped them with events.

## Planning Contract

### Evidence and denominator

Code and migrations were inspected without loading application settings or connecting to production. Read-only staging queries on **2026-11-01** verified `current_database() = pushinweight_staging` and `transaction_read_only = on`. Counts below are exact `count(*)` results from bounded read-only transactions; the two main inventory groups used repeatable-read, while supplemental shape/catalogue probes used read committed. Different inventory groups are separate snapshots and are not a global atomic census. Use new same-cohort counts for each rehearsal. Two initial broad count queries timed out read-only; the narrower inventory and index-oriented dependency inventory completed.

Staging is `dpg-d9vb8ds9v7es738lepsg-a`, with migration ledger through `0219_release_mapping_reconcile_index`. It has **243 public physical tables = 227 application + 16 Django/allauth tables**. The latter are the six `auth_*`, two `account_email*`, four `django_*`, and four `socialaccount_*` tables. Views, materialized views and aliases are excluded. `home_brand_time_counts` is not counted as a physical table; aliases such as `TrendNarrativeRun` do not add tables.

`core/models.py` at the source revision names 222 relations, of which 221 are physical application tables. The six additional staging tables are `discussion_window_counts`, `discussion_window_snapshots`, `event_dossier_claim_collection_jobs`, `event_dossier_discussion_windows`, `event_dossier_intake_decisions`, and `product_release_detection_states`. They are outside this plan's consolidation scope. Do not deploy this older checkout over that schema or infer compatibility from its migration ledger alone.

Local read-only cross-check: `test_pw_g3_timing_20261019`, `127.0.0.1:55436`, PostgreSQL 18.6, 243 physical public tables, migration ledger through `0213`; the inspected application tables were empty except two `data_sources` rows. It supplies no populated-family rehearsal evidence.

Historical RG6 evidence is in `docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md`, especially the October 27 staging parity/checkpoint entries, and RG7 decisions near its “Frozen RG7 storage decision” entry. The October 27 `serving-stage-0195-checkpoint-002.json` reference identifies **the staging copy**, not a separately verified local database. The current staging database is that reusable target, now advanced. Historical production-copy language elsewhere in the plan sometimes means copying rows inside production; it is not permission to connect there. RG6 pause/schedule practices are superseded by R10.

### KTD1. Canonical ownership map

This is the destination policy, with implementation maturity stated explicitly. U1 documents it; U2–U5 implement only their bounded extensions. It does not authorize rewriting every existing process family.

| Record meaning | Canonical table/model | Reader and reason | Extension boundary |
| --- | --- | --- | --- |
| Logical collection/discovery execution | `collection_runs` / `CollectionRun` | Collection status, recovery and coverage readers in `core/collection_state.py`; one logical execution, not one HTTP call | Reuse `CollectionJob` and `CollectionScopeRun` for instructions and scoped progress. Existing authored-content runs remain a named legacy/domain exception until separately reviewed; never invent a collection job for an editorial assessment. |
| One provider operation, including model inference | Generalize/rename `original_content_calls` to `provider_calls` / `ProviderCall` in U4 | Spend, response replay, provider batch importer, staff request recovery | Reuse current call identities/PKs and `ProviderBatch` for multi-call transport. Distinguish a billable logical operation from its physical transport attempts. |
| One spend allowance window | New `spend_budgets` / `SpendBudget` in U2 | Reservation/settlement and operator budget readers | Typed dimensions and counters; one row per allowance, not one row per provider. Retain throttle as a different record kind. |
| One execution claim/lease attempt | `collection_attempts` / `CollectionAttempt` | `core/collection_state.py` fences writes and accounts resumption | Default for collection/discovery. Reuse `CollectionRun`'s active token projection atomically. Existing provider-call/batch and work-item leases remain explicit compatibility exceptions; do not claim that they already share this table. A future non-collection lease requires a reviewed typed-owner extension here or owner exception, not a new per-feature lease table. |
| Immutable raw document | `collection_evidence_archives` / `CollectionEvidenceArchive` | Capture/replay, historical comparison, dossier evidence | Existing BinaryField archive with content hash, encoding and size. It is not a mutable state store. |
| Physical transport receipt, including no response | `collection_requests` / `CollectionRequest` | Capture and collection accounting readers | Existing required attempt/scope FKs must remain truthful. ProviderCall can reference a real captured request when it exists; do not fabricate collection scopes to fill them. |

The broad labels “runs” and “calls” conceal different grains. The table map is one shared default for each precise meaning, not permission to force authored-content decisions into collection execution records. U1 must list legacy exceptions by table and reason. A newly encountered workflow may not silently expand that list.

`ProviderBatch` remains one resumable group, with `ProviderCall` children. A group is not another individual call. No new generic run/lease table is proposed, and this work does not opportunistically centralize every existing lease implementation.

### KTD2. New-table accounting and schema shape

Six permanent tables are proposed across the entire program: `SpendBudget`, `SpendBudgetCharge`, `PostPromotionClassification`, `ProviderCallInput`, `ScheduledEventDetail`, and `OpportunityDetail`. `SpendBudget` replaces five tables; `SpendBudgetCharge` models a many-to-many reservation relationship previously hidden in JSON. `ProviderCallInput` models ordered Post inputs and per-input validation snapshots currently hidden in call JSON. The two detail tables represent event schedule/attendance facts and opportunity action/benefit facts, which cannot fit product-release details. U3 adds the typed Post-to-promotion-concept assignment hidden in existing JSON; U5 adds no permanent tables. U4 renames one existing call table and retires two. Temporary copy markers are columns, not permanent mapping tables.

Use existing `ServiceProvider`, `InferenceModel`, `DefinitionVersion`, `WorkflowStage`, `Language`, `Locale`, `TimeZone` and measurement/currency references where the definition really matches. Preserve unresolved historical names explicitly rather than silently assigning a convenient current model. Uniqueness, scope and nullable shapes must reflect the original counting unit. No new JSON/JSONB column is proposed. Raw archived bytes remain versioned, validated immutable evidence, never a way to disguise live mutable relationships.

### KTD3. Table arithmetic

These counts are the **end of each phase**, after physical retirement. Renames do not change totals. The six newer staging application tables are carried through unchanged. Temporary additive coexistence peaks are listed so a large intermediate schema is not mistaken for failure.

| Phase / branch suffix | Added | Retired | Net | Branch baseline | Staging baseline | Maximum temporary additions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Start | 0 | 0 | 0 | 221 | 227 | 0 |
| U1 guardrails | 0 | 0 | 0 | 221 | 227 | 0 |
| U2 spend-budgets | 2 | 5 | -3 | 218 | 224 | +2 |
| U3 classification-vocabularies | 1 | 19 | -18 | 200 | 206 | +1, extend/rename existing three |
| U4 provider-calls | 1 | 2 | -1 | 199 | 205 | +1 |
| U5 discovery-runs | 0 | 2 | -2 | 197 | 203 | 0 |
| U6 event-opportunity-dossiers | 2 | 3 | -1 | **196** | **202** | +2 |
| Total | **6** | **31** | **-25** | | | |

The original “19 into 3” classification estimate understates the saving: the 19 old key/label tables are retired **in addition to** retaining/generalizing the three existing audience-topic tables. Thus the vocabulary tables alone go 22 → 3, net -19; the required promotion assignment table makes the complete phase net -18. Budget savings are reduced by the necessary charge relation and retained throttle. Official-company decisions remain a table, so four call-related source tables do not become one whole-table replacement. If U6 remains deferred, the delivered endpoint is 197/203. If a full official-decision JSON redesign adds tables later, recalculate the total; do not hide them.

## Resources

The following resource identities are specific, existing resources. This table is a future execution dependency list, not authorization to use write credentials now.

| Resource | Exact identity and access | Needed by |
| --- | --- | --- |
| Repository | Authoritative root on fuchitalee: `/Users/fuchitalee/development/pushin-weight-v2`; this plan worktree under `.worktrees/docs/process-table-plan-20261101` | All phases. Leave the main checkout's unrelated changes alone. |
| Populated rehearsal copy | Render `pushinweight-staging-db`, ID `dpg-d9vb8ds9v7es738lepsg-a`, database/role `pushinweight_staging`, port 5432. Target identity in `config/staging_refresh.yaml`. Current read-only counts above; earlier RG6 checkpoint dated Oct 27. | U2–U6, one owner/family at a time. U1 policy tests need no database. |
| Local test database | Existing `test_pw_g3_timing_20261019`, fuchitalee `127.0.0.1:55436`; state `/Users/fuchitalee/.local/share/pushinweight/test-db/`; private connection metadata `connection.json`; lock `use.lock` | U2–U6 regression tests through `~/.local/bin/pushinweight-test-db`. Read `/Users/fuchitalee/infra/docs/reference/pushinweight-shared-test-database.md`. Never restore or clone another database. |
| Eventual production target | Render `pushinweight-db-shadow`, ID `dpg-d9koekqjobas73fvjqng-a`, database `pushinweight_shadow`; service-managed `DATABASE_URL` | Later authorized production delivery only. This session did not connect. Do not use the retired database ID from older memory. |
| R2 evidence storage | **None required for this consolidation.** `CollectionEvidenceArchive.body` is PostgreSQL byte storage | U4/U6 archive copy and verification need database access, not R2 credentials. |
| Existing media buckets | `pushinweight-media-staging` and `pushinweight-media-production`; prefixes `staff/`, `editorial/` | Only existing media rendering smoke checks in a later authorized U4 release. No media copy, deletion, new bucket or new prefix required. |
| Staging execution services | `pushinweight-staging-jobs` (`crn-dain9moae00c73f7d73g`), `pushinweight-staging-web`, `pushinweight-staging-headlines`, `pushinweight-staging-synthesis`, `pushinweight-staging-enrichment`, `pushinweight-staging-harvest` | Jobs runs bounded copy/parity; web and affected worker images provide cutover proof. U2 touches synthesis/enrichment/harvest/headlines; U3 touches all classification/role readers and writers; U4 touches headlines/enrichment plus on-demand staff/official paths; U5/U6 touch harvest/enrichment/web/headlines and jobs. |
| Existing broker | `pushinweight-staging-headlines-broker`; production counterpart `pushinweight-headlines-broker`; existing queue URLs in service environment | Only worker smoke/recovery proof. No broker flush, new broker, beat or scheduler. |
| Production services | `pushinweight-web`, `pushinweight-jobs`, `pushinweight-headlines`, `pushinweight-synthesis`, `pushinweight-enrichment`, `pushinweight-harvest`, `pushinweight-home-counts`; existing broker above | Later release image/dependency census, following `render.yaml`. Do not reactivate legacy worker/beat. Actual services and deployed revisions must be rechecked then. |

**Environment and credentials by phase:** U1 uses no environment file or provider key. U2–U6 local tests use the wrapper-supplied connection, not a copied repository `.env`. Runtime code currently loads repository `.env`; never source it for an audit or assume it targets local PostgreSQL. Candidate processes must receive an explicit validated target URL. Staging copies/parity use the existing staging jobs service's Render-managed `DATABASE_URL`; its role must have the required schema privileges before a future migration. The Render CLI's existing fuchitalee login was sufficient for this session's read-only staging query; no credential value was printed or copied.

No provider credentials are required for migration, stored-data parity or fixture tests in any phase. Keep provider sends disabled in rehearsal and replace network adapters with deterministic test replies. Do not use `TWITTERAPI_IO_SCHEDULED_API_KEY` for probes. An owner-selected live probe would be a separate extension using `TWITTERAPI_IO_ON_DEMAND_API_KEY`, and must load the X routing skill; it is unnecessary here. Likewise no MiniMax, DeepInfra, OpenAI or Anthropic spend is required. U4 staff/official replay must not trigger X list membership or owner OAuth actions.

If media smoke checks need existing files, Render already maps `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`; the operator store is `/Users/fuchitalee/.env.secrets`, using `R2_STAGING_ACCESS_KEY_ID` / `R2_STAGING_SECRET_ACCESS_KEY` or the corresponding `R2_PRODUCTION_*` variables. Do not copy production keys into staging. No secret file needs editing for this plan. `STAGING_REFRESH_SOURCE_DATABASE_URL` and `STAGING_DATA_REFRESH_ENABLED` belong only to staging jobs; **do not invoke staging refresh** as an automatic prerequisite because it connects to production and replaces data. Reuse the present copy.

**Resource gates:** identify the staging owner and current deployed SHA before rehearsal. It is ahead of this branch, so use a reconciled then-current candidate containing those migrations, not a fake ledger update or reversal. If occupied, wait/coordinate; do not create a substitute database. The staging refresh policy excludes some operational rows: zero official-company/staff rows do not establish production emptiness. U4 requires an authorized representative historical fixture or later approved production census before those paths can retire. No new resource is proposed.

## Implementation Units

### U1. Install the shared-process policy and migration check

**Branch:** `chore/process-storage-guardrails-<date>`. No schema change. Covers R1–R3, R6–R8.

Extend the schema-first block in `AGENTS.md` with the KTD1 map and a link to its maintained policy owner. Extend M19 rather than adding a second schema-policy skill. Resolve `.agents`/`.claude` aliases before editing so one canonical skill is changed. In `/Users/fuchitalee/.agents/skills/show-locally/references/db-schema-walkthrough.md`, add a short process-storage check directly after “Consolidate decisions on the write path,” referring back to “First principle: name the reader before storing anything.” Keep it project-neutral; the PushinWeight map belongs in the repo. The external skill edit is its own tracked owner/review artifact in the skill's owning repository when implementation is authorized, not an untracked change silently bundled in a project commit.

Policy text must require the reader, record grain, selected shared owner, concrete mismatch if reuse fails, invariants, and table delta. A domain evidence record is not a process receipt merely because its name ends in Evidence. Preserve the existing JSON-specific approval rule.

Add a dedicated required workflow, proposed `.github/workflows/process-schema-policy.yml`, with no path filter that can skip a migration-bearing PR. Proposed checker `scripts/check_process_schema_policy.py` compares the PR merge-base migration state to head. Detect `CreateModel`, explicit `db_table`, multi-table inheritance and auto-created through tables, nested `SeparateDatabaseAndState`, table-creating `RunSQL`, and opaque `RunPython`/custom database operations. Unknown table-creating operations require explicit review; substring matching alone is insufficient. Supplement static detection with before/after catalog comparison in CI's existing ephemeral PostgreSQL service. Never execute untrusted migration code with deployment secrets.

Heuristics inspect model and physical names, case-insensitively: Run, Attempt, Call, Budget, Evidence, Receipt, Claim, Lease and plural/snake-case forms; inspect added tables for token/owner/fence/expiry/claim/lease column groups even under neutral names. A rename must preserve table identity to avoid false new-table findings. A new table with an FK to a shared table is **not automatically an extension**: require a typed detail/link with an independently justified record meaning and no duplicate lifecycle. In-place shared-table additions pass this gate but still receive schema review. An abstract base class does not exempt a concrete table.

Use a small structured block in the **existing branch plan**, not a second approval database: migration operation/table, shared owner or exception reason, reader, addition/retirement count, owner approval reference and exact schema-declaration digest. The initial registry names this plan's intended shared additions, but **does not mark the proposal owner-approved**. Missing, stale, blanket or self-authored “approved” claims fail. Bind the approval reference to an owner-authored review/comment or checked-in owner decision for that exact declaration; validate the actor against protected repository configuration. An attacker must not be able to edit both the allowlist and approver identity in one PR. Pure offline checking can validate shape/digest but cannot authenticate an owner, so a protected CI approval check supplies that part. Read-only GitHub permissions suffice; never run PR code under `pull_request_target` with secrets.

**Verification:** fixtures for innocent domain EventEvidence, legitimate typed budget charge, new `FooRun`, neutral table with lease fields, raw SQL creation, nested operations, autogenerated through table, rename, shared `AddField`, absent approval, changed digest, forged approval actor and modified checker/config. New semantic evidence tables still need a reviewed domain classification, not blanket suffix suppression. Existing baseline process tables are grandfathered by exact identity, with no retroactive migration edits. Update `docs/reference/db-schema.md` only to describe implemented policy/storage under the reference-doc skill.

### U2. Consolidate five spend owners and remove budget-key JSON

**Branch:** `refactor/shared-spend-budgets-<date>`. Depends on U1. Covers R4, R5, R7–R10. Net -3.

Add `SpendBudget` and `SpendBudgetCharge`. A budget row owns one allowance at a particular scope/window. A charge row links one reservation identity to each allowance it consumes; a single official-company call currently consumes both a day budget and a cycle budget. A single FK cannot replace `budget_keys`, and an archive would make settlement incorrect. Existing collection attempts represent executions, not these allowance relationships, so they cannot substitute for the charge relation.

Use UUID budget IDs; retain the exact original kind/key and map old UUID/day/string/integer keys deterministically. Window kind distinguishes fixed interval, UTC day, cycle and initial-total. Scope includes workflow, config/policy revision and provider/model where currently applicable. Fixed-window bounds are required; lifetime/initial scopes have an explicitly different checked nullable shape. Keep numeric units separate: request counts, media-call counts, input/output tokens, search credits, and USD. USD precision must preserve the existing official-company 10 decimal places and rare-type 9 places; choose a common decimal with sufficient integral range, never float or 6-place rounding. Store reserved, accounted, confirmed and observed amounts separately when meanings differ.

`SpendBudgetCharge` has budget FK, stable reservation identity, typed optional owner FKs to existing official attempt/shared call or collection execution as applicable, reservation/settlement state, reserved/actual amounts and source timestamps. Enforce one charge per reservation/budget, truthful owner shape, nonnegative amounts and exactly-once settlement. U2 initially needs official-attempt ownership; U4 switches its provider-call linkage without losing the decision association. Do not manufacture historical per-call charges from aggregate-only totals: preserve a typed opening balance and a counted historical-coverage state. Unknown cost remains reserved.

Characterize each policy before sharing its transaction primitive. Enrichment reserves a conservative bound without refund; editorial can refund down to actual; rare search distinguishes reserved/accounted/confirmed; synthesis counts per-demand reserved requests/tokens and observed tokens; official company releases reserved into spent only with valid usage. Keep each policy's admission decision while sharing locking, scope identity and accounting storage. Do not turn a schema refactor into a new budget algorithm.

Lock all applicable budget rows in deterministic order, reserve before network I/O, and settle idempotently. Preserve live old/new accounting through a transactional compatibility projection or an equivalent rehearsed protocol: never independently spend from two ledgers. Update old rows on new writes until old images drain; replay concurrent changes below the copy cursor. Keep `PostSynthesisRateLimitBucket` and its expiry cleanup unchanged.

Switch the U2 writers/readers in Appendix A and the three inbound FK owners in Appendix B. The observed five source tables contain 1,599 rows in total; preserve their distinct scope identities rather than merging equal dates across workflows. Copy and compare sums grouped by original scope/unit/state, not just row counts. Confirm limits cannot be reset by config change, clock rollover, worker restart or ambiguous reply. Retire five old budget tables and `OfficialCompanyAttempt.budget_keys` only after exact relationship parity and all-old-writer drain.

**Regression net:** simultaneous reservations at a cap; day/cycle dual charging; replayed settlement; lost provider reply; expired enrichment window; fingerprint conflict; 10-decimal spend; media cap; synthesis retry and stale publication; rare credit reconciliation; unchanged throttle response and cleanup. Include operator `enrichment_budget`, `enrichment_health`, `synthesis_status`, `editorial` and official requalification output parity.

### U3. Generalize the existing classification vocabulary

**Branch:** `refactor/shared-classification-vocabularies-<date>`. Depends on U1 and lands separately after U2. Net -18.

Extend and later rename `AudienceTopicScheme/Concept/Label` to `ClassificationScheme/Concept/Label`. Reuse their three physical tables during copy. Preserve existing concept IDs and audience-topic assignment behavior. Add schemes for the nine key/label pairs and UnsanctionedFlagKey. Preserve raw keys, case-insensitive identity, every locale label, legacy key, scheme manifest and revision; never merge equal text across schemes. Do not equate taxonomy-v2 and taxonomy-v3 categories.

Keep each existing assignment/entity table. Add scheme-qualified concept references beside old key FKs. One existing assignment is not yet relational: `PostUntrackedBrandPromotion.promotion_keys` is a JSON list, read by `monitor/views.py` containment filters and written by `monitor/classification_persistence.py`. Add `PostPromotionClassification` with promotion/Post FK, fixed promotion scheme and concept FK, unique per promotion/concept, plus ordinal if needed to preserve response order. Copy the list and switch those readers/writers before dropping `promotion_keys` and its index. Enforce no duplicates and the existing “general must be the only key” rule at the write boundary with a database constraint trigger for bulk/raw writes. Preserve the parent judgment and its subject evidence; neither can substitute for this membership relation. This extra table is necessary to make the requested scheme-safe assignment real; it is included in KTD3. An assignment with multiple axes carries a separate scheme/concept pair for each axis, including China/US nationalism and stance. Enforce a fixed scheme for single-purpose columns and a database composite FK `(scheme_id, concept_id)` to a unique `(scheme_id, id)` on concepts. For optional assignments both values must be NULL or both present. The existing audience-topic assignment also needs the database relation, not merely application `clean()` validation. A label's ordinary concept FK inherits scheme identity; labels remain revision/locale specific.

Django 5.2 cannot express all composite relations with ordinary `ForeignKey`. Retain a simple concept PK for ORM joins and add the composite database constraint through explicit migration SQL with aligned migration state. Do not rely on `ForeignObject` alone to create a constraint. PostgreSQL supports multi-column FKs; use a same-row fixed-scheme check plus the FK, not a CHECK that queries another table. See the official references below.

Inbound tables and exact counts are in Appendix B. Trace ORM relation traversals and SQL names in `core/classification_analysis.py`, `monitor/classification_persistence.py`, `monitor/views.py`, `monitor/trend_narrative_facts.py`, `monitor/general_readers.py`, the chart/dashboard queries, and seed/import commands. Preserve response keys and display labels. Role assignment means both `BrandAccount` and `CompanyAccount`; replacing only label lookups is incomplete. For this frozen vocabulary census, complete copying yields 11 schemes, 75 concepts and 242 labels, including the existing audience-topic rows, if no concurrent seed changes occur. Independently compare keys/revisions/locales as well as these counts. `UnsanctionedFlagKey` has no label table, so do not invent translations.

Keep all 19 source tables until the new composite constraints are validated, all assignments map exactly, old key writers drain and old-query dependencies are absent. Then drop the old tables and rename the three generalized tables with a compatible staged name transition.

**Regression net:** wrong-scheme insert through raw SQL and bulk writer fails; optional pair half-NULL fails; duplicate key within a scheme fails; same key in different schemes succeeds; all old labels and mixed-case identities survive; historical taxonomy queries, chart totals, account-role selection and EN/ZH-CN/JA surfaces match. Preserve the analysis contracts in `docs/analysis/2026-09-09-112957-classification-analysis-contract.md` and `docs/analysis/2026-09-10-203138-stage1c-contracts.md`.

### U4. Consolidate provider calls and remove operational call JSON safely

**Branch:** `refactor/shared-provider-calls-<date>`. Depends on U2. Net -1 with one required input relation.

Generalize `OriginalContentCall` into `ProviderCall`, preserving PKs and `OriginalContentText.producing_call`. Extend typed ownership for authored run, ProviderBatch, staff person/work and official-company attempt with database checks. Staff requests include search/media discovery; a model FK is optional for non-model providers. Keep the original staff identity `(person, provider, fingerprint)` and identity-merge lookup. Preserve `work` SET_NULL behavior and explicitly decide whether the historical person CASCADE policy should remain; this plan selects preservation, not an incidental retention change.

All 23 staging `EditorialCall` rows already map to `request_identity = legacy-editorial-call:<id>` in `OriginalContentCall`. Compare and reuse these rows; do not insert or charge again. Preserve the global media-stage deduplication, per-assessment text-stage uniqueness, ambiguous sends, response hashes and unknown historical completion times. Keep `ProviderBatch` as parent transport group with existing fencing, polling and import cursor semantics.

Move raw `request_packet`, `response_payload`, EditorialCall.response and staff parameters/response to immutable `CollectionEvidenceArchive` references. Staff fingerprint calculation still uses the exact canonical parameter encoding. Archive replay is allowed for the immutable captured response; operational selection and settlement query typed fields. Hash saved encodings without claiming that a JSONB reserialization is the original network bytes. Mark whether bytes are original or reconstructed. Retain request and response availability separately from successful completion.

`OriginalContentCall.provenance` and `import_evidence` are **not merely raw payloads**: `monitor/backfill_enrichment.py` uses operation, role, chunk index, source language, Post snapshots, revalidation and operator-closed-missing-import state to decide whether imports are safe. Add typed call columns for scalar operation/role/chunk/validation state and archive only immutable historical packets. Add `ProviderCallInput` with call FK, Post FK, ordinal, immutable input content/context hash, source/version references and per-input application/validation outcome as needed by the existing importer. Uniqueness is call/Post or call/ordinal as established by the batch manifest, with both checked for the currently bounded 1–20 members. Preserve enough named scalar snapshot fields to reproduce each existing freshness comparison; hash parity alone does not authorize dropping a field a reader needs. Its independent Post relationship and ordered per-input state cannot live in a scalar call row or collection archive. Enumerate every actual provenance/import key before migration; unknown keys stop copying until classified. Drop both JSON columns only when replay, stale-input rejection and recovery use typed owners.

For official company, create provider-call rows only for actual paid/model attempts. Owner-attestation rows remain business decisions with no invented provider request. Move call model/usage/cost/timing/error facts to the shared call and update admin/requalification readers through that relation. Preserve attempt status as the decision outcome, distinct from transport outcome. Replace attempt.evidence with an immutable evidence-archive FK after all its readers use the explicit saved snapshot. `budget_keys` was already replaced by U2.

**Deferred scope:** `OfficialCompanyAttempt.decision` and `OfficialCompanyAccountState.decision/evidence` remain existing business storage. Their nested claims, model types, offering categories and citations are operational inputs to account registration and requalification; copying them to opaque archive bytes would violate R5. A future full typed-decision refactor must name ownership and citation relationships before promising removal. U4 must explicitly report this retained JSON and must not claim “all four tables/JSON eliminated.” Also retain unrelated `ProviderBatch.policy/control_evidence` and staff work-context JSON; changing them is separate scope.

**Regression net:** duplicate editorial mirror; staff merged identity and request cap; owner attestation creates zero call rows; stale lease and late response; timeout with unknown cost; batch partial import/restart; missing archived body; changed Post snapshot; operator-closed missing import; repeated replay creates no duplicate artifacts or charge. Whole caller workflows must pass, including `core/provider_batches.py`, editorial service, backfill recovery and staff review command.

### U5. Fold discovery execution into shared collection runs

**Branch:** `refactor/shared-discovery-runs-<date>`. Depends on U1; sequence after U4 to avoid migration-graph overlap. Net -2.

`JobDiscoveryRun` and `PersonnelDiscoveryRun` inherit the same `DiscoveryRunBase`; their only added fields are extracted-listing versus affiliation/evidence counts. Neither has rows in this staging copy. Reuse **CollectionRun** as the one run table with a constrained discovery kind; do not add a third DiscoveryRun table.

Use a truthful collection job definition for discovery and a scope for each query/window. The discovery logical identity must include kind and original run identity, so equal original identities in two source tables cannot collide. Preserve `run_id`, cycle linkage, query FK/text/hash/pack version, provider/tool boundary, language, window/cursors, reviewed/accepted/excluded counts, discovered organizations and subtype output counters. Store query/window facts on existing `CollectionScopeRun`, execution clocks/status on `CollectionRun`, credential/reservation/physical accounting on `CollectionAttempt`/`CollectionRequest` only when known. Use kind-qualified scalar counters rather than embedding totals in JSON.

Archive legacy diagnostic telemetry, capabilities and limitations as immutable evidence where only report/replay readers need them; any operational field used by discovery planning or reporting gets a typed owner first. No historical credit estimate may become a fabricated physical request. For discovery invoked within an existing collection run, link its scoped record to that run rather than inserting another logical execution. The future mapping census must distinguish those embedded cases from standalone runs.

Update `_RUN_MODELS`, run reservation/reporting in `core/discovery.py`, and per-run output counters in `core/targeted_extraction.py`; follow these into `monitor/cycle.py` and discovery reports. Zero staging rows mean there is **no populated historical-copy proof** for this family. Rehearse synthetic populated historical records plus both actual caller paths; obtain later authorized representative history before production retirement if production contains rows.

**Regression net:** jobs and personnel with identical old IDs remain distinct; one shared run with two query scopes; truncation and unknown coverage remain distinct from success; expired claim/restart; cursor preservation; zero accepted posts with provider usage; no network calls or false successful receipts. If the owner requires a literal new DiscoveryRun table instead, stop and revise the exception/counts: that alternative saves one table, not two.

### U6. Consolidate events and opportunities last

**Branch:** `refactor/event-opportunity-dossiers-<date>`. Depends on the shared archive and classification changes; requires resolving the existing staging migration boundary. Net -1, conditional on the checks below.

Reuse `EventDossier`, `EventDossierSource`, `EventDossierClaim`, `EventDossierReview` and review-claim links. Add `ScheduledEventDetail` and `OpportunityDetail`; preserve `ProductReleaseDetail` and `PersonnelChangeDetail`. A scheduled event has organizer, attendance, locations, schedule and source status. An opportunity has sponsor, action, benefit, eligibility, availability and optional related event. Neither is a product release and neither should be represented by a bag of optional product-release columns.

Preserve identities with kind-namespaced deterministic mapping. Do not merge records merely because titles, URLs or times match. Opportunity.related_event maps to the target event dossier. Preserve tracked versus discovery-candidate ownership with an exclusive typed shape. Old raw payloads and complete legacy row snapshots become immutable archives for historical comparison, with operational fields copied to typed columns.

All 29 staging Events, 29 EventEvidence rows and 35 Opportunities are pending. **Do not create a completed review during migration.** The two new detail tables each support a typed source-report owner OR a reviewed owner, with an exclusive FK check and uniqueness per owner. Source-report detail links to an EventDossierClaim; reviewed detail links to EventDossierReview, analogous to ProductReleaseDetail. A database trigger/constraint must enforce matching dossier kind and prevent cross-dossier owner linkage. Extend the active integrity functions introduced in `0097_event_dossier_integrity.py` and subsequently revised by RG5, plus `core/event_dossiers.py` review publication, to recognize the new kinds and require their proper detail shape. Do not edit applied migrations. Rehearse unchanged product/personnel review paths against those revised functions. A pending record becomes a source report and detail, with `current_review` left NULL. Later genuine review may create a separate reviewed detail. This explicitly separates source assertion from accepted result without adding a per-feature evidence table.

One source claim preserves each EventEvidence identity/hash/observed clock. Keep current Event row assertions as a separate current-source report if they contain facts not recoverable from its evidence rows. No evidence is discarded as “duplicate” solely because its source Post repeats. Staging rows all have source Posts; the model also permits URL-only records. Extend EventDossierSource with a checked archive-backed source alternative for such real legacy sources, preserving locator and captured provenance, rather than fabricating a Post or CollectionObservation. Reuse the existing archive; no new source table.

Keep original start/end/open/close values, precision and timezone links. Convert only values the existing parser can interpret unambiguously; unknown precision stays unknown, never midnight UTC. Preserve source schedule text, native IDs, normalized/canonical URL rules, confidence and first/last-seen clocks. Reader contracts must still distinguish pending from reviewed and event from opportunity. The existing typed claim schema's timestamp rules are not a license to invent dates for month/year/range values.

Switch targeted extraction upsert/deduplication and all readers in Appendix A. Preserve General candidate counts, intelligence report results, rare-type telemetry, editorial grounding and opportunity-to-event links. Use the RG7 invalidation/copy/parity/drop structure from `0202`–`0205`, with this family's own mapping and no assumption that RG7 release rules cover events. Retire Event, EventEvidence and Opportunity only after independently verifying every source field, pointer and downstream result.

**Regression net:** existing pending rows stay pending; URL-only source; changed schedule on existing identity; multiple conflicting evidence rows; month/year/range and missing timezone; opportunity linked to an event; malformed legacy payload; repeated copy after source edit below high-water; late insertion during copy; rejected/confirmed legacy review states. A populated current staging copy proves only the pending/Post-backed subset. Other legal states require characterized fixtures before retirement.

## Verification Contract

### Shared family rehearsal and release protocol

Apply once per family; do not repeat the entire program's checks on every intermediate commit. Reuse valid evidence tied to the same code/schema/fixtures.

1. Reconcile source revision, actual migration graph, schema catalog, staging occupancy, available disk, workload and credential purpose. Record exact family row counts and inbound FK/view/trigger/function/grant dependencies. `config/staging_refresh.yaml` and policy tests must reflect new/retired tables before that family closes.
2. Characterize current writers/readers and negative invariants on the permanent local test database through its wrapper. Adapt `isolated_migration_database` tests to the shared-database policy before running them; do not create extra test databases. Any explicit schema preparation requires exclusive ownership and future implementation authority. The pytest wrapper must not silently migrate.
3. Add the new/extended typed storage and compatibility bridge. Use bounded indexed copy batches, deterministic identities and restart checkpoints. Keep old writers live. Mirror transactional counters/FKs consistently; for immutable evidence use source-hash invalidation and retry on change. A once-only high-water copy is insufficient for updates below the cursor.
4. Independently verify per-source-row mapping, hashes and values, grouped counters/units, nullable states, duplicates and orphan links. Compare missing **and extra** targets. Record mapping counts rather than expecting naive source-count sums where rows were already mirrored. Budget parity requires balances; classification parity requires exact assignments; event parity requires evidence and state.
5. Switch all writers and readers, including SQL, admin, worker, one-off jobs, commands, offline import/replay, cached query projections and restricted serving views. Capture every relevant service's image SHA and active one-off revision. Drain old images through normal rolling replacement; never stop harvesting/collection to simplify it. Refuse physical retirement while any old image can still execute.
6. Run the final bounded delta and dependency check under short transactions with lock timeout. Add constraints with a rehearsed validation strategy, avoid long transactions over archived payloads, and fail without partial unsafe deletion if writers introduce unmatched rows. Run parity again after cutover.
7. Retire physical tables/columns with guarded migrations and RESTRICT, not CASCADE. Reconcile Django state, database catalog, retained grants, indexes, constraints and docs. Observe application and natural worker/collection outcomes under separately authorized release scope. A deployed page is not proof of accounting or worker health.

**Rollback:** before retirement, a reader switch can revert only if the compatibility bridge has preserved all new writes in the old shape. Prove this in staging. After retirement, do not claim reversing Django migrations restores deleted data. Prefer forward repair; recovery from a verified backup requires later explicit authority and a replay of subsequent writes. Keep immutable evidence and typed owner links sufficient for supported reconstruction, but do not claim the archive alone is a complete database backup. Never pause production to prepare a backup/copy. No production restore is part of this plan's automatic path.

**Concrete local commands for later execution:** use `~/.local/bin/pushinweight-test-db pytest <focused tests>`, `~/.local/bin/pushinweight-test-db run <explicit schema/check command>`, `python manage.py makemigrations --check --dry-run` with explicit safe connection context, and the repository's lint command. Run no tests in this planning session. Candidate required tests must produce zero required skips. Use existing suites such as `tests/test_collection_schema_regression_net.py`, `tests/test_taxonomy_compatibility_surfaces.py`, `tests/test_official_company_accounts.py`, staging-refresh policy tests and the relevant budget/provider/discovery/intelligence suites discovered from the changed callers. Add family-specific integration/concurrency tests where current suites do not exercise the differentiator.

### Acceptance examples

- AE1 (R3): a renamed `FooJournal` table with lease token/expiry columns fails CI without the exact shared-owner mapping or authenticated owner exception.
- AE2 (R5): two workers reserve against one remaining allowance; exactly one succeeds, and replayed settlement cannot free the allowance twice.
- AE3 (R5): a sentiment assignment pointing at an audience-topic concept fails at the database boundary, including a bulk insert.
- AE4 (R5): the 23 existing mirrored editorial rows retain 23 logical charges; consolidation adds zero duplicates.
- AE5 (R5): a timed-out provider request keeps unknown spend reserved; a later response is archived without permitting stale publication.
- AE6 (R5): pending event/opportunity records remain available under the same pending filters and do not acquire a fabricated confirmed review.
- AE7 (R9, R10): a live old writer changes a row below the copy cursor; invalidation/delta catches it and retirement refuses until parity is restored, without stopping the writer.

## Definition of Done

For this planning task: this single plan is written, internally reviewed, linked to exact source/count/resource evidence, reannotated by Ollija, and delivered for review. Only this plan is eligible for a docs commit/push. No implementation or release is implied.

For each future family: its named shared owner and field mapping are implemented; required schema/integration/concurrency/copy tests pass; populated-copy rehearsal and its limitations are recorded; every caller is cut over; exact final delta and catalog checks pass; the old physical storage is retired; counts and references match reality; its separately authorized delivery endpoint is observed. No family is “complete” merely because a new table exists or fixtures pass.

## Risks and open decisions

1. **Target count:** adopt the measured -25 reduction (196 code baseline / 202 current staging baseline). The original approximate 190 target is not supported without added scope. This is a planning recommendation, not an owner-approved CI exception.
2. **Official-company decision JSON:** this plan defers its full normalization, retaining the operational decision journal. Decide whether the later implementation brief accepts that boundary or requires a separately designed decision/citation family before U4 closes. No missing production data is assumed absent from staging zeroes.
3. **Shared run/lease boundary:** KTD1 names collection execution/attempts as defaults while acknowledging distinct existing authored/provider owners. A universal process engine spanning all of them is outside this bounded consolidation. If literal universal storage is required now, redesign that abstraction and recalculate counts before implementing it.
4. **Execution and release authority:** implementation is intentionally later. Before the background session starts, select which family and its delivery endpoint, and confirm occupancy of the existing staging copy. A later production census is necessary to establish production row shapes/size; it is not allowed in this session.

Technical risks resolved in the design include budget precision and concurrency, already-mirrored calls, taxonomy wrong-scheme assignment, operational JSON masquerading as evidence, pending reviews, source-only events, and active writers. Remaining execution risks are environment drift, sparse rehearsal families, long copy/constraint validation and old service images. U6 and official historical retirement must stop at their stated evidence gates rather than weaken them to meet a table count.

## Appendix

### A. Source-table inventory, exact staging counts and caller evidence

Counts are the November 1 read-only staging snapshot. “W” means code that creates/updates/deletes the records; “R” means reads, including related-object reads. A zero count confirms only this copy. Test and migration-only fixtures are additional verification paths, not production writers.

| Table/model | Rows | Writers | Readers | Merge verdict |
| --- | ---: | --- | --- | --- |
| `enrichment_budget_windows` / EnrichmentBudgetWindow | 3 | `monitor/enrichment_budget.py:78`, `monitor/management/commands/enrichment_budget.py:39` | Same reservation code; `enrichment_health.py:64` | Eligible with fixed interval, fingerprint conflict and nonrefundable bound preserved. |
| `post_synthesis_daily_budgets` / PostSynthesisDailyBudget | 0 | `monitor/post_synthesis.py:205,268` | Same; `monitor/management/commands/synthesis_status.py:46`; demand budget FK | Eligible with per-demand/token accounting; populated fixtures required. |
| `post_synthesis_rate_limit_buckets` / PostSynthesisRateLimitBucket | 382 | `monitor/views.py:5512`, cleanup `monitor/post_synthesis.py:181` | Request-admission check `monitor/views.py:5517` | Retain: short-lived caller throttle, not spend allowance. |
| `rare_type_search_daily_budgets` / RareTypeSearchDailyBudget | 1,592 | `core/rare_type_search.py:264,395,511,606,643`; `monitor/backfill_collection.py:637` | Same module reconciliation/reporting through lines 1188–1653; run/processing-cycle FKs | Eligible; distinguish credits, decision USD and confirmed/accounted/reserved amounts. |
| `editorial_budgets` / EditorialBudget | 4 | `monitor/editorial/persistence.py:146,213` | Same; `monitor/original_content_backfill.py:302`, `original_content_cutover.py:128`, command `editorial.py:51` | Eligible; reconcile external zero-send provenance and shared-call mirror before balances. |
| `official_company_budgets` / OfficialCompanyBudget | 0 | `core/official_company_accounts.py:569,639` | Same admission/settlement functions | Eligible with multi-budget links and decimal precision; staging has no representative history. |
| `original_content_calls` / OriginalContentCall | 3,610 | `monitor/original_content.py`, `monitor/original_content_backfill.py:102`, `monitor/backfill_enrichment.py`, `core/provider_batches.py` | Same; `monitor/backfill_recovery.py`, `monitor/editorial/persistence.py`, `scripts/backfill_campaign.py`, `scripts/backfill_targeted.py`; OriginalContentText FK | Shared base to generalize. 3,595 request bodies, 3,286 responses, 3,610 nonempty provenance and 3,270 nonempty import-evidence documents. Typed operational replacement is mandatory. |
| `editorial_calls` / EditorialCall | 23 | `monitor/editorial/persistence.py:184,209` | Same; `monitor/editorial/media.py:149`, `monitor/original_content_backfill.py:286` | Retire after mirror parity; all 23 already have shared calls. |
| `staff_provider_requests` / StaffProviderRequest | 0 | `core/staff_assets/queue.py:150` and `record_response` | Queue claim/reserve/recovery; `core/management/commands/review_staff_collection.py:86` | Eligible as provider operations, not all model inference. No populated-history proof. |
| `official_company_attempts` / OfficialCompanyAttempt | 0 | `core/official_company_accounts.py:488,587,614`, `core/official_company_induction.py:144` | `core/official_company_admin.py:75,86`, `core/official_company_requalification.py:78,214`; claim/completion | Retain decision owner; split model-call fields, archive evidence, remove budget_keys. Defer decision JSON. Owner attestations must never become paid calls. |
| `job_discovery_runs` / JobDiscoveryRun | 0 | `core/discovery.py` reserve/update path; `core/targeted_extraction.py:1797` counters | `_RUN_MODELS`, `core/discovery.py:271` and downstream discovery reports | Eligible for shared collection execution with kind; historical coverage unresolved by zero rows. |
| `personnel_discovery_runs` / PersonnelDiscoveryRun | 0 | Same discovery functions; `core/targeted_extraction.py:1807` | Same discovery report path | Same, preserving affiliation and evidence counts separately. |
| `events` / Event | 29 | `core/targeted_extraction.py:1297` and event upsert/dedup helpers | `core/intelligence_readers.py:166,516,563`, `monitor/general_readers.py:195`, `monitor/editorial/grounding.py`; bindings/contracts; related opportunities | Conditional: all pending, all source-Post-backed in this copy. Preserve identity and draft/source-report semantics. |
| `event_evidence` / EventEvidence | 29 | `core/targeted_extraction.py:1342` | `core/intelligence_readers.py:83`, `monitor/general_readers.py:205`, `monitor/rare_type_telemetry.py:157` | Eligible within dossier event family; retain one claim per evidence identity and its clocks/hash. |
| `opportunities` / Opportunity | 35 | `core/targeted_extraction.py:1487` | `core/intelligence_readers.py:171,540,598`, `monitor/general_readers.py:213`, `monitor/rare_type_telemetry.py:162,181`; editorial selection/grounding | Conditional: all pending/Post-backed. Preserve benefit/action meaning and related event. |

`Event` name occurrences in `monitor/enrichment_worker.py`, threading code and provider modules are not automatically ORM Event reads; distinguish imported threading Event from `core.models.Event`. The inventory above follows actual model use.

Classification seed W below is `core/management/commands/seed_i18n_labels.py`; it writes both the key and corresponding label table. Historical migration writers remain frozen migration history; update the current seed/import paths rather than editing applied migrations.

| Key table / label table | Key rows / label rows | Writers beyond seed | Readers and assignment owners | Verdict |
| --- | ---: | --- | --- | --- |
| `post_type_keys` / `post_type_labels` | 20 / 66 | `monitor/cycle.py:2122`; legacy port script | `PostBrandSignal`; `monitor/views.py:610`; classification analysis/facts | Eligible; preserve legacy and canonical keys, not just active taxonomy. |
| `product_label_keys` / `product_label_labels` | 7 / 21 | Seed | `PostBrandProductLabel`; views label map | Eligible with product-label scheme. |
| `geopolitical_mode_keys` / `geopolitical_mode_labels` | 3 / 9 | Seed | `PostBrandGeopoliticalMode`; views label map | Eligible with own scheme. |
| `national_stance_keys` / `national_stance_labels` | 6 / 18 | Seed | `PostBrandClassificationState` China/US stance; views label map | Eligible; both axes constrained to stance scheme. |
| `untracked_brand_promotion_keys` / `untracked_brand_promotion_labels` | 5 / 15 | Seed | Classification persistence and `posts_untracked_brand_promotions`/promotion evidence readers; views | Eligible vocabulary only; preserve independent promotion evidence. |
| `sentiment_keys` / `sentiment_labels` | 4 / 16 | `monitor/cycle.py:2123`; legacy port script | `PostBrandSignal`, `PostBrandClassificationState`; views filtered queries and label map | Eligible; no collision with stance/nationalism “neutral” meanings. |
| `discourse_keys` / `discourse_labels` | 10 / 40 | Seed and legacy port script | `PostBrandDiscourse`; classification/narrative/analytics readers | Eligible; retain all locale rows, including historical extras. |
| `nationalism_keys` / `nationalism_labels` | 6 / 24 | Seed and legacy port script | `PostBrandClassificationState`, `PostBrandDiscourse`, both China/US axes; views | Eligible; preserve shared scale but independent axes. |
| `roles` / `role_labels` | 3 / 12 | `core/official_company_accounts.py:810,904`, `core/publisher_accounts.py:71`, `monitor/management/commands/onboard_brand.py:727`, `load_seed.py:135,230`; import script | `BrandAccount`, `CompanyAccount`, official-company admin and `monitor/views.py:2898` | Eligible, but role meaning is account affiliation, not RG5 job-role AI relationship. |
| `unsanctioned_flag_keys` (no label table) | 4 / n/a | `monitor/unsanctioned_flags.py:127`, legacy port script | `PostUnsanctionedFlagAssignment`; legacy post flags and icon/report readers | Eligible with its own scheme; no invented labels. |
| `audience_topic_schemes` / `audience_topic_concepts` / `audience_topic_labels` | 1 / 7 / 21 | Seed; `monitor/classification_persistence.py:483,490` | `PostBrandAudienceTopic`; `monitor/views.py:612,718,727,2079,3183,4232` | Reuse/generalize the existing three, preserving original concept identities and revisions. |

Additional operational scripts such as `scripts/port_sqlite_to_django.py` retain explicit old table/model assumptions. Retire their old import route or adapt it to scheme-qualified storage with fixtures; do not execute the retired SQLite import on live data. Existing pilot scripts using Role must either keep a tested compatibility API or clearly refuse unsupported old input. A grep-clean runtime is not proof that replay/import paths are safe.

### B. Dependent and shared-table inventory

These are existing tables whose FKs, fields or related readers change, plus shared targets needed to establish fit. Counts are exact staging results. Tables identified as “unchanged” are counted for scope clarity and are not additions/retirements.

| Existing table | Rows | Writer/reader path and planned effect |
| --- | ---: | --- |
| `post_synthesis_demands` | 44 | `monitor/post_synthesis.py` claims/publishes; synthesis status/recovery. Replace budget FK with shared budget; preserve demand lease and artifact linkage. |
| `rare_type_search_runs` | 1,204 | `core/rare_type_search.py` and `monitor/backfill_collection.py`; budget/report readers. Replace daily-budget FK only. |
| `rare_type_decision_processing_cycles` | 392 | Rare-type decision reservation/reconciliation; `core/rare_type_search.py`. Replace budget FK only. |
| `brands_accounts` | 102 | Seed/onboard, publisher/official-company account writers; feed, classification, admin, query planners. U3 role FK/scheme pair. |
| `companies_accounts` | 33 | Publisher/official-company registration; company/admin joins. U3 role FK/scheme pair. |
| `posts_brands_signals` | 286,291 | `monitor/classification_persistence.py`, cycle writers; views and classification analysis. U3 post type/sentiment pairs. |
| `posts_brands_classification_states` | 63,060 | Classification persistence; views, analysis, narrative facts. U3 sentiment/nationalism/stance pairs. |
| `posts_brands_audience_topics` | 52,680 | Classification persistence; topic filters/analytics. Preserve IDs and validate scheme/concept FK. |
| `posts_brands_geopolitical_modes` | 5,952 | Classification persistence; geopolitical filters. U3 scheme/concept. |
| `posts_brands_product_labels` | 16,783 | Classification persistence; product label filters. U3 scheme/concept. |
| `posts_brands_discourse` | 120,287 | Classification persistence; discourse/nationalism analysis. U3 separate constrained pairs. |
| `post_unsanctioned_flag_assignments` | 16,560 | `monitor/unsanctioned_flags.py`, legacy-flag projection; feed/analysis readers. U3 flag scheme/concept. |
| `original_content_texts` | 5 | Shared authored-content publication/import; editorial serving/replay. Keep producing_call PK linkage while call table generalizes. |
| `provider_batches` | 54 | `core/provider_batches.py`, backfill runner/recovery; per-call import readers. Existing group remains; update relation to generalized calls. |
| `staff_collection_work` | 39 | `core/staff_assets/queue.py`, staff collection/review; expired-lease recovery. No schema merge; call existence/replay queries move to ProviderCall. |
| `official_company_account_states` | 0 | Official account claim/completion/registration and admin/requalification. Preserve business state; move model-call relation readers, defer its JSON. |
| `collection_jobs` | 3,958 | `core/collection_jobs.py` and `core/collection_instructions.py` writers and `core/collection_state.py`; job/report readers. Extend accepted discovery instructions; no new process table. |
| `collection_runs` | 4,112 | `core/collection_state.py`, collection cycle/adapters; status/coverage/metric/history readers. U5 discovery kind and truthful execution mapping. |
| `collection_scope_runs` | 226,343 | Collection state/capture/cycle; query/cursor/report readers. U5 discovery query/window and subtype counters. |
| `collection_attempts` | 218 | `core/collection_state.py`; capture/resumption/accounting. Existing canonical lease attempt; U5 reuse only when a real execution is represented. |
| `collection_requests` | 28,854 | `core/collection_capture.py` and collection adapters; replay/accounting. Reuse actual receipts; no fabricated call ownership. |
| `collection_evidence_archives` | 1,360,306 | `core/collection_capture.py`, existing RG6/RG7 capture/copy writers; replay/parity/dossier readers. U4/U6 new versioned capture kinds and FKs, same table. |
| `event_dossiers` | 4,431 | `core/event_dossiers.py`, `core/product_release_dossiers.py` and `core/targeted_extraction.py` release path; dossier/general/editorial readers. U6 new event/opportunity identities and kinds. |
| `event_dossier_sources` | 4,479 | Dossier capture/intake; claims/readers. U6 real Post/observation reuse plus checked archive-backed source. |
| `event_dossier_claims` | 8,314 | Dossier research and targeted extraction; review/parity/grounding. U6 report claims and typed detail links. |
| `event_dossier_reviews` | 52 | Dossier research/review publication; current-review readers. U6 only actual reviews, never fabricated by copy. |
| `event_dossier_review_claims` | 141 | Dossier review acceptance; grounding/evidence readers. U6 preserve accepted/rejected attribution through existing joins. |
| `product_release_details` | 52 | Dossier release review writer/readers. Unchanged; pattern reference for typed review detail. |
| `posts_untracked_brand_promotions` | 7,026 | `monitor/classification_persistence.py:546` writes; `monitor/views.py:2112,3384,3593,4305` reads JSON membership. U3 replaces promotion_keys with typed assignments, retaining the parent judgment. |
| `untracked_brand_promotion_evidence` | 7,646 | `monitor/classification_persistence.py:371,380,413`; classification/analysis readers. Unchanged evidence owner, vocabulary API adaptation only. |
| `role_ai_relationship_types` | 0 | `core/shared_vocabulary.py`; job classification consumers. Unchanged RG5 catalogue, distinct from account Role. |
| `job_role_ai_relationship_assignments` | 8 | Job extraction/classification; intelligence readers. Unchanged; not part of Role vocabulary consolidation. |

| `event_kinds` / `event_claim_kinds` | 2 / 11 | `core/shared_vocabulary.py` seeds; `core/event_dossiers.py` and database integrity functions read. U6 adds only reviewed event/opportunity/report codes; retain separate RG5 catalogues. |
| `service_providers` / `inference_models` / `workflow_stages` | 0 / 0 / 0 | Shared-definition seed/resolve paths and typed process readers. U2/U4 must preserve unknown historical identities; seed only justified mappings, never infer that empty staging catalogues mean no provider usage. |
| `definition_versions` | 1 | Shared-definition resolver and typed policy references. Reuse known revisions; preserve source hashes. |
| `locales` / `languages` / `time_zones` / `currencies` | 8,173 / 8,163 / 597 / 307 | Existing shared-reference seeds and resolvers; classification labels/discovery/detail readers. Reuse references, no merging or reseeding whole catalogues. |

For counts not shown for newly proposed tables, the source count is **not applicable: table does not exist**; they begin at zero only when an authorized migration creates them. Their target row count is derived from mapping multiplicity, not asserted in advance. The budget-charge and call-input tables can contain more rows than their parents without defeating consolidation.

### C. Why the exclusions matter

Person-name evidence records an assertion about a name, with name/language/source selection semantics. Affiliation evidence records a person's relationship with an organization and its temporal/review meaning. Job-listing evidence supports a particular listing and its source status. They have different parent identities, uniqueness, constraints, queries and retention relationships. A generic Evidence table would weaken foreign-key enforcement or accumulate mutually exclusive columns and make every reader reconstruct domain meaning. A shared immutable archive may hold raw bytes for all three without merging those typed evidence relationships.

RG5 `BusinessVocabularyCode` is an abstract implementation convenience, not one domain vocabulary. Its subclasses include employment type, workplace type, salary period, event kind, release maturity and opportunity type. Their separate FKs prevent one domain's code from being assigned to another. They are not the localized classification key/label families requested in U3. U3 earns consolidation by explicitly retaining scheme-qualified assignment constraints; repeating that broad conversion across RG5 would be extra scope and risk with no evidence of a reader benefit.

### D. Migration and research anchors

- `core/models.py` is schema authority at the named revision; `docs/reference/db-schema.md` and `CONCEPTS.md` are navigation/context, not substitutes for code.
- Original family definitions and later constraints: `core/migrations/0032_stage1c_people_jobs_events.py`, `0038_split_translation_synthesis_ja.py`, `0041_event_canonical_url_event_external_event_id_and_more.py`, `0043_audiencetopicconcept_audiencetopicscheme_and_more.py`, `0045_raretypedecision_raretypesearchdailybudget_and_more.py`, `0065_editorial_stories.py`, `0065_official_company_discovery.py`, and `0197_enrichment_budget_window.py`. Trace subsequent AlterField/RunSQL operations, not just CreateModel, before generating candidate migrations.
- Reuse release patterns from `core/migrations/0202_rg7_expand.py` through `0205_rg7_retire_model_release_storage.py`; their invalidation, hash/owner checks and guarded deletion are concrete precedents. `0201_rg6_remove_legacy_collection_json.py` demonstrates the earlier physical retirement boundary.
- Resource ownership: `config/staging_refresh.yaml`, `docs/operations/staging-data-refresh.md`, `docs/operations/r2-media-storage.md`, `render.yaml`, `render-staging.yaml`, and the Oct 27 RG6 entries in `docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md`.
- [Django 5.2 composite primary keys](https://docs.djangoproject.com/en/5.2/topics/composite-primary-key/) documents the relation limitations relevant to U3. [PostgreSQL 18 constraints](https://www.postgresql.org/docs/18/ddl-constraints.html) documents multi-column foreign keys and the limits of cross-row CHECK constraints. These support the explicit database composite-FK design, not a framework upgrade.

## Delivery Exceptions

The owner explicitly requested planning only, with no code, migration, database or R2 writes, no deployment, no merge and no production connection. A documentation-only commit and push on `docs/process-table-plan-20261101` are permitted. The main checkout's uncommitted work is excluded. Current permission does not carry through to a future background implementation or release. The policy/CI changes and shared skill edits described here are planned work, not changes made during this session. Do not present an implementation-start menu; return the requested summary and stop.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/process-table-plan-20261101`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/process-table-plan-20261101/docs/plans/2026-11-01-065419-docs-process-table-plan-20261101-plan.md`
- Change: `docs-process-table-plan-20261101-2026-11-01-065419`
- Branch: `docs/process-table-plan-20261101`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/process-table-plan-20261101/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/process-table-plan-20261101/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

### Failure handling

- Complete applicable, unwaived checks for the selected route. A waived check is waived, never passed. Owner-selected direct production does not require staging.
- Product defects return to the parent implementation workflow; repeat only checks invalidated by the fix. Environment failures require repairing the environment, not a new source commit. Retry only after a relevant fact changes.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->
