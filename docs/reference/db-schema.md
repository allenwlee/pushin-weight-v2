# Database schema reference

Last verified: 2026-10-05 17:18 JST

Scope: **128 application tables**, **1,605 physical columns**, plus one
compatibility view. Source: `feat/g2-editorial` based on `71377000`; migration graph through
`0068_editorial_media_stage_once`.

Use this guide to find where information lives and how records connect. Start
with a subject below, or use the [alphabetical table inventory](#table-inventory)
to jump directly to any table. Every inventory entry has a full column reference.

The schema is defined by [core/models.py](../../core/models.py) and the
[ordered Django migrations](../../core/migrations/). This snapshot describes
that repository schema, checked against Django models, migration state and an isolated PostgreSQL database; it does not
assert that a particular deployment has applied every migration. Django’s own
authentication, session, content-type, and migration-ledger tables are outside
this **application-table** count. `DiscoveryRunBase` is an abstract model, not
another table; its columns are included under both discovery-run tables.
The retired SQLite database and Graphviz image are not current schema sources.

## Find information by subject

| Subject | Tables | Start here when you need… |
| --- | ---: | --- |
| [People and job history](#people) | 13 | A person, their optional X identity, roles, employment dates, and evidence. |
| [Companies, brands, and organization discovery](#organizations) | 11 | Company/brand identity, ownership, associated accounts, and unresolved organizations. |
| [X accounts, profiles, and lists](#accounts) | 5 | X profiles, observed profile history, list membership, and post appearances. |
| [Countries and regions](#geography) | 6 | Country/region names and interpretation of account geography. |
| [Posts and classification](#posts) | 13 | Source posts, brand attribution, classification, and supporting judgments. |
| [Classification vocabularies and translated labels](#vocabularies) | 22 | Allowed classification concepts and their translated display labels. |
| [Products, model releases, and Hugging Face catalog](#products) | 9 | Exact products, release claims, and catalog observations. |
| [Job listings and official career-site collection](#jobs) | 5 | Advertised roles, their sources, and career-site synchronization status. |
| [Events and opportunities](#events) | 3 | Attendable occurrences and action-for-benefit offers. |
| [Post translation and commentary](#translation) | 9 | Literal post translations, generated commentary, retries, and budgets. |
| [Trend headlines and publication](#headlines) | 9 | Prepared headline text, publication pointers, work requests, and provider costs. |
| [Chatter, Pulse and editorial pictures](#editorial) | 7 | Story identities, accepted editions, quarter-hour decisions, spend and optional assets. |
| [Collection, extraction, and processing records](#processing) | 16 | Search cursors, coverage gaps, extraction attempts, and rare-type search accounting. |

For staff records, begin with **[People and job history](#people)**. A person can
exist without an X account. Their employer/brand relationships and supporting
sources have their own tables. **[Job listings](#jobs)** describe advertised
positions; they are not a person’s employment history.

```mermaid
flowchart LR
    P[people] --> PA[people_accounts]
    PA --> A[accounts]
    P --> H[people_brand_affiliations]
    H --> E[people_brand_affiliation_evidence]
    H --> B[brands]
    H --> D[brand_discovery_candidates]
    B --> BC[brands_companies]
    BC --> C[companies]
    J[job_listings] --> B
    J --> D
    J --> JE[job_listing_evidence]
```

An affiliation or job listing is owned by exactly one known brand **or** one
organization awaiting review. The two arrows in the diagram are alternatives,
not two simultaneous owners. A company is reached through `brands_companies`;
there is no direct company column on the affiliation.

## Reading the table details

- A **primary key (PK)** uniquely identifies a row. Some tables use a natural
  identifier such as a provider ID or brand slug; others use a UUID or a
  generated integer. A **composite primary key** uses several existing columns
  together. Django’s `pk` attribute for those models is not a physical column.
- A **foreign key (FK)** links to another table. Column tables use actual SQL
  column names; a different Django attribute is shown as `model: …`. For example,
  `people_accounts.author_id` is the SQL column for the model’s `account` field.
- **NULL allowed** describes database nullability. It is separate from Django
  form validation (`blank=True`) and from an empty string. A non-null column may
  still accept `''` if its constraints allow it.
- **Default** means a Django/application default unless explicitly marked as a
  database identity. `uuid.uuid4`, `auto_now_add`, and `auto_now` are application
  behavior, not PostgreSQL defaults. Direct SQL writes must supply required
  values themselves. `auto_now` applies to normal model saves, not every bulk
  update or arbitrary SQL statement.
- PostgreSQL types are shown directly: `varchar(n)` is bounded text, `text` is
  unbounded text, `jsonb` is structured JSON, and `timestamp with time zone` is
  a timezone-aware timestamp. Positive integer Django fields also receive
  nonnegative database checks. Field choices are application validation;
  only listed database checks enforce their allowed values in SQL.
- `case_insensitive` is the ICU collation created in the initial migration
  (`und-u-ks-level2`, nondeterministic). Only fields explicitly marked with that
  collation use it; not every identifier does.
- FK deletion labels describe Django behavior: `CASCADE` deletes dependent
  records, `PROTECT` prevents deletion while referenced, and `SET_NULL` clears
  an optional link. These are not a claim that every SQL FK has that same
  `ON DELETE` clause. The migration-specific exceptions are documented below.
- Every table lists its named model indexes and constraints. PKs and unique
  fields provide uniqueness indexes; ordinary FK fields also receive indexes
  unless the field details say otherwise. These automatic indexes are not
  repeated as manually named indexes. Exact check expressions use SQL notation;
  the important meaning is explained in each subject’s introduction.

## Dates, evidence, and languages

Source facts and collection times answer different questions. `observed_at`,
`first_seen_at`, and `last_seen_at` say when PushinWeight saw a claim;
`created_at`/`updated_at` usually track the stored row. A source’s employment,
birth, release, event, or opportunity date stays in its dedicated value field.
For `posts`, `accounts`, and `products`, `created_at` is a source creation time;
the table notes identify those exceptions.

Reduced-precision dates pair a string value with a precision: `YYYY`/`year`,
`YYYY-MM`/`month`, `YYYY-MM-DD`/`day`, or NULL/`unknown`. Models that allow
`datetime` require a timezone-bearing ISO-style timestamp. Named checks express the expected string shapes and precision pairings;
application validation must also handle missing values and valid calendar dates.
As with PostgreSQL checks generally, an expression evaluating to SQL NULL does
not fail a check, so a nullable value plus a precision label is not by itself
proof of a complete or valid date. Comparable start/end values have additional ordering checks where
listed. Never substitute the date a page was crawled for an unknown joining date.

Evidence tables keep observations separate from interpreted facts. A stored
claim, confidence score, or record with `review_status='pending'` is not proof
of a confirmed identity. Do not count evidence rows as distinct people/jobs.
Several observations can support one record, and different claims can still
need reconciliation.

People select primary and English names from `people_names`; the four legacy
name fields remain for compatibility. `people_name_evidence` stores the sources.
Original professional prose and EN/JA translations live in `people_texts` and
`people_text_translations`. Media bytes and person/source attribution have their
own tables. Affiliation title/location originals and supporting evidence remain
in the existing job-history records; no company-headquarters location is inferred
for staff. Job listings retain their own source text and language fields.

<a id="table-inventory"></a>

## Alphabetical table inventory

Each of the 128 application tables appears once in this inventory and once in
the detailed sections. Subject counts above sum to 128.

| Table | Subject | What one row represents |
| --- | --- | --- |
| [_applied_config_snapshot](#table-_applied_config_snapshot) | [Collection, extraction, and processing records](#processing) | One configuration artifact’s last applied content hash. |
| [account_based_in_mappings](#table-account_based_in_mappings) | [Countries and regions](#geography) | One reviewed mapping from an X “based in” string to a country or region. |
| [account_post_appearances](#table-account_post_appearances) | [X accounts, profiles, and lists](#accounts) | One account’s appearance in one collected post, with collection context. |
| [account_profile_snapshots](#table-account_profile_snapshots) | [X accounts, profiles, and lists](#accounts) | One consecutive observation period during which an account’s saved profile hash is unchanged. |
| [accounts](#table-accounts) | [X accounts, profiles, and lists](#accounts) | One X account, keyed by the provider’s stable user ID, with its current saved profile. |
| [audience_topic_concepts](#table-audience_topic_concepts) | [Classification vocabularies and translated labels](#vocabularies) | One stable topic identity within an audience-topic scheme. |
| [audience_topic_labels](#table-audience_topic_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated topic label for a particular revision. |
| [audience_topic_schemes](#table-audience_topic_schemes) | [Classification vocabularies and translated labels](#vocabularies) | One versioned audience-topic scheme and its manifest identity. |
| [brand_discovery_candidate_token_evidence](#table-brand_discovery_candidate_token_evidence) | [Companies, brands, and organization discovery](#organizations) | One source observation supporting an organization token. |
| [brand_discovery_candidate_tokens](#table-brand_discovery_candidate_tokens) | [Companies, brands, and organization discovery](#organizations) | One exact observed spelling or handle for an unresolved organization. |
| [brand_discovery_candidates](#table-brand_discovery_candidates) | [Companies, brands, and organization discovery](#organizations) | One unresolved organization identity awaiting review against known brands. |
| [brand_hashtags](#table-brand_hashtags) | [Companies, brands, and organization discovery](#organizations) | One hashtag associated with a brand. |
| [brand_keywords](#table-brand_keywords) | [Companies, brands, and organization discovery](#organizations) | One literal or regular-expression matching pattern for a brand. |
| [brand_search_terms](#table-brand_search_terms) | [Companies, brands, and organization discovery](#organizations) | One search term associated with a brand. |
| [brand_trend_narrative_texts](#table-brand_trend_narrative_texts) | [Trend headlines and publication](#headlines) | One locale’s headline and byline for a brand narrative. |
| [brand_trend_narratives](#table-brand_trend_narratives) | [Trend headlines and publication](#headlines) | One prepared brand headline outcome within a run. |
| [brands](#table-brands) | [Companies, brands, and organization discovery](#organizations) | One brand identity and its display metadata. |
| [brands_accounts](#table-brands_accounts) | [Companies, brands, and organization discovery](#organizations) | One account’s role for a brand, such as official or researcher. |
| [brands_companies](#table-brands_companies) | [Companies, brands, and organization discovery](#organizations) | One ownership relationship between a brand and a company. |
| [call_state](#table-call_state) | [Collection, extraction, and processing records](#processing) | One harvest cursor for a brand, call, bucket, and query combination. |
| [companies](#table-companies) | [Companies, brands, and organization discovery](#organizations) | One company identity, including its recorded headquarters country. |
| [companies_accounts](#table-companies_accounts) | [Companies, brands, and organization discovery](#organizations) | One account’s role for a company. |
| [countries](#table-countries) | [Countries and regions](#geography) | One country/territory code and optional display-parent relationship. |
| [country_codes_region](#table-country_codes_region) | [Countries and regions](#geography) | One country’s assigned region and the source of that assignment. |
| [country_labels](#table-country_labels) | [Countries and regions](#geography) | One translated label for a country code. |
| [discourse_keys](#table-discourse_keys) | [Classification vocabularies and translated labels](#vocabularies) | One legacy pragmatic-register vocabulary key. |
| [discourse_labels](#table-discourse_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated legacy pragmatic-register label. |
| [editorial_assessments](#table-editorial_assessments) | [Chatter, Pulse and editorial pictures](#editorial) | One fenced quarter-hour editorial or content-picture assessment, with frozen evidence and outcome. |
| [editorial_budgets](#table-editorial_budgets) | [Chatter, Pulse and editorial pictures](#editorial) | One UTC day of conservative spend reservations and text/media call counts. |
| [editorial_calls](#table-editorial_calls) | [Chatter, Pulse and editorial pictures](#editorial) | One reserved provider stage and its saved response or uncertain-send outcome. |
| [editorial_editions](#table-editorial_editions) | [Chatter, Pulse and editorial pictures](#editorial) | One immutable accepted story edition for a track, locale and revision. |
| [editorial_heroes](#table-editorial_heroes) | [Chatter, Pulse and editorial pictures](#editorial) | One current hero pointer, or the shared provider-lock row. |
| [editorial_pictures](#table-editorial_pictures) | [Chatter, Pulse and editorial pictures](#editorial) | One optional source/derivative assignment for a content revision. |
| [editorial_stories](#table-editorial_stories) | [Chatter, Pulse and editorial pictures](#editorial) | One permanent development identity with original-post anchors. |
| [event_evidence](#table-event_evidence) | [Events and opportunities](#events) | One source observation supporting an event occurrence. |
| [events](#table-events) | [Events and opportunities](#events) | One attendance-bearing occurrence, such as a conference or meetup. |
| [geopolitical_mode_keys](#table-geopolitical_mode_keys) | [Classification vocabularies and translated labels](#vocabularies) | One geopolitical-mode vocabulary key. |
| [geopolitical_mode_labels](#table-geopolitical_mode_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated geopolitical-mode label. |
| [harvest_backlog_windows](#table-harvest_backlog_windows) | [Collection, extraction, and processing records](#processing) | One bounded time window still owed collection coverage. |
| [hf_model_catalog_namespace_runs](#table-hf_model_catalog_namespace_runs) | [Products, model releases, and Hugging Face catalog](#products) | One namespace’s enumeration state within a catalog run. |
| [hf_model_catalog_observations](#table-hf_model_catalog_observations) | [Products, model releases, and Hugging Face catalog](#products) | One repository observation within a namespace run. |
| [hf_model_catalog_runs](#table-hf_model_catalog_runs) | [Products, model releases, and Hugging Face catalog](#products) | One overall Hugging Face catalog collection run. |
| [hf_orgs](#table-hf_orgs) | [Products, model releases, and Hugging Face catalog](#products) | One Hugging Face organization/user namespace linked to a company. |
| [job_discovery_runs](#table-job_discovery_runs) | [Job listings and official career-site collection](#jobs) | One job-search query/window run, including coverage, cost, and extracted listing count. |
| [job_listing_evidence](#table-job_listing_evidence) | [Job listings and official career-site collection](#jobs) | One source observation supporting a job listing. |
| [job_listings](#table-job_listings) | [Job listings and official career-site collection](#jobs) | One advertised position/requisition, including its source identity and current saved details. |
| [job_source_states](#table-job_source_states) | [Job listings and official career-site collection](#jobs) | One career-site source’s active lease and last successful synchronization state. |
| [job_source_sync_runs](#table-job_source_sync_runs) | [Job listings and official career-site collection](#jobs) | One attempt to synchronize an official career-site source. |
| [model_release_evidence](#table-model_release_evidence) | [Products, model releases, and Hugging Face catalog](#products) | One observed source claim supporting a model release. |
| [model_releases](#table-model_releases) | [Products, model releases, and Hugging Face catalog](#products) | One source-backed model-release occurrence and its stated date precision. |
| [national_stance_keys](#table-national_stance_keys) | [Classification vocabularies and translated labels](#vocabularies) | One China/US national-stance direction vocabulary key. |
| [national_stance_labels](#table-national_stance_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated national-stance label. |
| [nationalism_keys](#table-nationalism_keys) | [Classification vocabularies and translated labels](#vocabularies) | One legacy nationalism-scale vocabulary key shared by the China and US axes. |
| [nationalism_labels](#table-nationalism_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated legacy nationalism-scale label. |
| [opportunities](#table-opportunities) | [Events and opportunities](#events) | One bounded offer in which an action can provide a benefit, optionally linked to an event. |
| [people](#table-people) | [People and job history](#people) | One person, whether or not they have an X account. |
| [people_accounts](#table-people_accounts) | [People and job history](#people) | One proposed or reviewed link between a person and an X account. |
| [people_brand_affiliation_evidence](#table-people_brand_affiliation_evidence) | [People and job history](#people) | One source observation supporting an affiliation claim. |
| [people_brand_affiliations](#table-people_brand_affiliations) | [People and job history](#people) | One claim about a person’s role or relationship with an organization. |
| [people_identity_corrections](#table-people_identity_corrections) | [People and job history](#people) | One append-only reviewed account confirmation, identity merge or selective split. |
| [people_media](#table-people_media) | [People and job history](#people) | One person-specific attribution of an image or video reference to a source. |
| [people_name_evidence](#table-people_name_evidence) | [People and job history](#people) | One observation supporting a name or explicitly supported name components. |
| [people_names](#table-people_names) | [People and job history](#people) | One sourced spelling of a person’s full name, with optional evidenced components. |
| [people_text_translations](#table-people_text_translations) | [People and job history](#people) | One cached translation of a specific original prose version and provider configuration. |
| [people_texts](#table-people_texts) | [People and job history](#people) | One immutable version of original biography, role, location or job-description prose. |
| [personnel_discovery_runs](#table-personnel_discovery_runs) | [People and job history](#people) | One personnel-search query/window run, including coverage, cost, and extraction counts. |
| [post_enrichment_states](#table-post_enrichment_states) | [Post translation and commentary](#translation) | One post’s replayable translation/classification progress and diagnostics. |
| [post_synthesis_artifacts](#table-post_synthesis_artifacts) | [Post translation and commentary](#translation) | One versioned commentary artifact for a post and its context. |
| [post_synthesis_daily_budgets](#table-post_synthesis_daily_budgets) | [Post translation and commentary](#translation) | One day’s commentary request/token budget accounting. |
| [post_synthesis_demands](#table-post_synthesis_demands) | [Post translation and commentary](#translation) | One coalesced request for post commentary, including its worker claim and retry state. |
| [post_synthesis_rate_limit_buckets](#table-post_synthesis_rate_limit_buckets) | [Post translation and commentary](#translation) | One request-throttle bucket keyed without storing a user ID or IP address. |
| [post_synthesis_texts](#table-post_synthesis_texts) | [Post translation and commentary](#translation) | One locale’s commentary text within a synthesis artifact. |
| [post_translation_artifacts](#table-post_translation_artifacts) | [Post translation and commentary](#translation) | One versioned literal-translation attempt/state for a post body. |
| [post_translation_chunks](#table-post_translation_chunks) | [Post translation and commentary](#translation) | One validated locale chunk retained for resuming a long post translation. |
| [post_translation_texts](#table-post_translation_texts) | [Post translation and commentary](#translation) | One locale’s validated literal text within a translation artifact. |
| [post_type_keys](#table-post_type_keys) | [Classification vocabularies and translated labels](#vocabularies) | One post-type vocabulary key, such as release or review. |
| [post_type_labels](#table-post_type_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated post-type label. |
| [posts](#table-posts) | [Posts and classification](#posts) | One collected X post, its source text, metrics, and author snapshot. |
| [posts_brands](#table-posts_brands) | [Posts and classification](#posts) | One post-to-brand attribution and its relevance weight. |
| [posts_brands_audience_topics](#table-posts_brands_audience_topics) | [Posts and classification](#posts) | One audience-topic assignment for a post/brand pair. |
| [posts_brands_classification_judgments](#table-posts_brands_classification_judgments) | [Posts and classification](#posts) | One recorded stage of a classifier judgment, including inputs and validation. |
| [posts_brands_classification_states](#table-posts_brands_classification_states) | [Posts and classification](#posts) | One current versioned classification state for a post/brand pair. |
| [posts_brands_discourse](#table-posts_brands_discourse) | [Posts and classification](#posts) | One legacy pragmatic speech-act assignment for a post/brand pair. |
| [posts_brands_geopolitical_modes](#table-posts_brands_geopolitical_modes) | [Posts and classification](#posts) | One geopolitical-mode assignment for a post/brand pair. |
| [posts_brands_mentions](#table-posts_brands_mentions) | [Posts and classification](#posts) | One matching source that connected a post to a brand. |
| [posts_brands_product_labels](#table-posts_brands_product_labels) | [Posts and classification](#posts) | One independent product-feedback label for a post/brand pair. |
| [posts_brands_products](#table-posts_brands_products) | [Products, model releases, and Hugging Face catalog](#products) | One source-backed claim that a post names an exact product for a brand. |
| [posts_brands_signals](#table-posts_brands_signals) | [Posts and classification](#posts) | One post type and sentiment assignment for a post/brand pair. |
| [posts_unsanctioned_flags](#table-posts_unsanctioned_flags) | [Posts and classification](#posts) | One post’s legacy unsanctioned-flag assignment. |
| [posts_untracked_brand_promotions](#table-posts_untracked_brand_promotions) | [Posts and classification](#posts) | One current post-level judgment about promotion of an untracked brand. |
| [product_label_keys](#table-product_label_keys) | [Classification vocabularies and translated labels](#vocabularies) | One independent product-feedback vocabulary key. |
| [product_label_labels](#table-product_label_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated product-feedback label. |
| [product_verification_proposals](#table-product_verification_proposals) | [Products, model releases, and Hugging Face catalog](#products) | One reviewable proposal to resolve an observed product name to a product. |
| [products](#table-products) | [Products, model releases, and Hugging Face catalog](#products) | One model/product identity, with optional Hugging Face repository metadata. |
| [profile_movement_candidates](#table-profile_movement_candidates) | [People and job history](#people) | One observed profile change queued for personnel-movement interpretation. |
| [rare_type_category_assignments](#table-rare_type_category_assignments) | [Collection, extraction, and processing records](#processing) | One source-backed rare-category assignment for a post and organization. |
| [rare_type_decision_attempts](#table-rare_type_decision_attempts) | [Collection, extraction, and processing records](#processing) | One funded provider attempt for a relevance decision, with one settlement record. |
| [rare_type_decision_processing_cycles](#table-rare_type_decision_processing_cycles) | [Collection, extraction, and processing records](#processing) | One processing time slot that funds relevance-decision attempts. |
| [rare_type_decisions](#table-rare_type_decisions) | [Collection, extraction, and processing records](#processing) | One reusable, versioned relevance interpretation of a provider result. |
| [rare_type_search_daily_budgets](#table-rare_type_search_daily_budgets) | [Collection, extraction, and processing records](#processing) | One search lane’s budget accounting for a UTC day. |
| [rare_type_search_hits](#table-rare_type_search_hits) | [Collection, extraction, and processing records](#processing) | One durable inbox result from an already-paid rare-type search. |
| [rare_type_search_runs](#table-rare_type_search_runs) | [Collection, extraction, and processing records](#processing) | One paid rare-type search time slot and its coverage/cost record. |
| [region_labels](#table-region_labels) | [Countries and regions](#geography) | One translated label for a region. |
| [regions](#table-regions) | [Countries and regions](#geography) | One region in the geographic hierarchy. |
| [role_labels](#table-role_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated account-role label. |
| [roles](#table-roles) | [Classification vocabularies and translated labels](#vocabularies) | One account-role vocabulary key. |
| [search_queries](#table-search_queries) | [Collection, extraction, and processing records](#processing) | One saved collection/discovery query identity and associated brand/keywords. |
| [sentiment_keys](#table-sentiment_keys) | [Classification vocabularies and translated labels](#vocabularies) | One sentiment vocabulary key. |
| [sentiment_labels](#table-sentiment_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated sentiment label. |
| [staff_collection_work](#table-staff_collection_work) | [Collection, extraction, and processing records](#processing) | One person/source-fingerprint/policy unit of resumable collection work. |
| [staff_intakes](#table-staff_intakes) | [Collection, extraction, and processing records](#processing) | One versioned staff-source observation, including eligibility and its input payload. |
| [staff_media_objects](#table-staff_media_objects) | [People and job history](#people) | One validated image file, addressed by its SHA-256 content hash. |
| [staff_provider_requests](#table-staff_provider_requests) | [Collection, extraction, and processing records](#processing) | One reserved provider request, its outcome and safe response evidence. |
| [targeted_extraction_attempts](#table-targeted_extraction_attempts) | [Collection, extraction, and processing records](#processing) | One recorded attempt to extract a role-specific fact from a post. |
| [targeted_extraction_states](#table-targeted_extraction_states) | [Collection, extraction, and processing records](#processing) | One post/role extraction state, used to avoid repeating the same work. |
| [trend_narrative_demands](#table-trend_narrative_demands) | [Trend headlines and publication](#headlines) | One coalesced brand/window headline request and its scheduling state. |
| [trend_narrative_provider_calls](#table-trend_narrative_provider_calls) | [Trend headlines and publication](#headlines) | One recorded provider attempt for ranking, editing, or reviewing headlines. |
| [trend_narrative_runs](#table-trend_narrative_runs) | [Trend headlines and publication](#headlines) | One common evidence cutoff for an all-brand headline run and time window. |
| [trend_narrative_subjects](#table-trend_narrative_subjects) | [Trend headlines and publication](#headlines) | One reported subject attached to a headline publication. |
| [trend_narrative_visible_runs](#table-trend_narrative_visible_runs) | [Trend headlines and publication](#headlines) | One currently visible run for a supported time window. |
| [trend_narrative_work_slots](#table-trend_narrative_work_slots) | [Trend headlines and publication](#headlines) | One window’s active work claim and optional newer queued cutoff. |
| [trend_narratives](#table-trend_narratives) | [Trend headlines and publication](#headlines) | One durable attempt/version of a shared time-window headline. |
| [twitter_list_memberships](#table-twitter_list_memberships) | [X accounts, profiles, and lists](#accounts) | One account’s membership state in one X list. |
| [twitter_list_sync_state](#table-twitter_list_sync_state) | [X accounts, profiles, and lists](#accounts) | One X list’s last completed membership synchronization. |
| [unsanctioned_flag_keys](#table-unsanctioned_flag_keys) | [Classification vocabularies and translated labels](#vocabularies) | One legacy unsanctioned-flag vocabulary key; there is no paired label table. |
| [untracked_brand_promotion_evidence](#table-untracked_brand_promotion_evidence) | [Posts and classification](#posts) | One visible promoted subject supporting an untracked-brand judgment. |
| [untracked_brand_promotion_keys](#table-untracked_brand_promotion_keys) | [Classification vocabularies and translated labels](#vocabularies) | One current untracked-brand-promotion vocabulary key. |
| [untracked_brand_promotion_labels](#table-untracked_brand_promotion_labels) | [Classification vocabularies and translated labels](#vocabularies) | One translated untracked-brand-promotion label. |


<a id="people"></a>

## People and job history

`people` holds identity. `people_accounts` supplies optional social-account
links, while `people_brand_affiliations` holds the career relationships. One
person can have several affiliations, including separate roles at the same
organization and relationships such as founder, advisor, or board member.
`people_brand_affiliation_evidence` holds the source text/URL/post/profile that
supports each claim. These are core person records, not an implementation-phase
appendix.

The uniqueness of `claim_identity` prevents the same claim identity from being
inserted twice; it does not by itself merge every duplicate person or resolve
conflicting career claims. Confirmed account links have stricter constraints:
an account has at most one confirmed person, and a person has at most one
confirmed primary account. Pending links can coexist during review.

`profile_movement_candidates` is a processing queue built from profile changes,
not a confirmed job-history record. `personnel_discovery_runs` measures searches,
not employment. The current [person reader](../../core/intelligence_readers.py)
returns all affiliations, but its `employment_history` subset includes only
`affiliation_type='employment'`.

Current person identity has 16 columns, including `sex` and two selected name
links. Full names and optional given/family components belong to `people_names`.
Primary selects a sourced professional/original representation; English selects
an established English representation. Both must belong to this person and be
confirmed. The reader falls back to legacy full-name fields when no selection
exists; a fallback does not establish source verification. Its version-2 read
contract exposes `sex`. See [the extraction path](../../core/targeted_extraction.py)
and [profile observations](../../core/profile_snapshots.py) for identity creation.



<a id="table-people"></a>

### `people` — Person

One person, whether or not they have an X account.

Model: [Person](../../core/models.py#L4557).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `uuid` | No | PK. Default: `uuid.uuid4()`. |
| `display_name` | `text` | No | Legacy full display name and fallback; not unique. |
| `display_name_en` | `text` | Yes | English or romanized full name. |
| `display_name_zh_cn` | `text` | Yes | Simplified Chinese full name. |
| `display_name_ja` | `text` | Yes | Japanese full name. |
| `date_of_birth` | `varchar(10)` | Yes | Source-supported date at the paired precision; not necessarily a full date. |
| `date_of_birth_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `day`, `month`, `year`, `unknown`. |
| `sex` | `text` | Yes | Source-supported sex value. |
| `primary_name_id` | `bigint` | Yes | FK → [people_names](#table-people_names); Django SET_NULL. Confirmed name belonging to this person. |
| `english_name_id` | `bigint` | Yes | FK → [people_names](#table-people_names); Django SET_NULL. Confirmed English name belonging to this person. |
| `nationality` | `text` | Yes | — |
| `ethnicity` | `text` | Yes | — |
| `primary_language` | `text` | Yes | — |
| `merged_into_id` | `uuid` | Yes | Retired identity redirects to [people](#table-people); Django PROTECT. Original ID remains addressable. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_person_merge_not_self`: a person cannot redirect to itself. The correction service flattens redirects and rejects retired destinations.

- `ck_people_dob_precision`: Check: `(("date_of_birth" IS NULL AND "date_of_birth_precision" = 'unknown') OR ("date_of_birth"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND "date_of_birth_precision" = 'day') OR ("date_of_birth"::text ~ '^[0-9]{4}-[0-9]{2}$' AND "date_of_birth_precision" = 'month') OR ("date_of_birth"::text ~ '^[0-9]{4}$' AND "date_of_birth_precision" = 'year'))`.

[Back to table inventory](#table-inventory)

<a id="table-people_accounts"></a>

### `people_accounts` — PersonAccount

One proposed or reviewed link between a person and an X account.

Model: [PersonAccount](../../core/models.py#L4904).

**Primary key:** `person_id`, `author_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `person_id` | `uuid` | No | Model: `person`. PK component. FK → [people.id](#table-people); Django delete: `CASCADE`. |
| `author_id` | `text` | No | Model: `account`. PK component. FK → [accounts.author_id](#table-accounts); Django delete: `CASCADE`. |
| `is_primary` | `boolean` | No | Default: `False`. |
| `first_observed_at` | `timestamp with time zone` | No | — |
| `last_observed_at` | `timestamp with time zone` | No | — |
| `confidence` | `double precision` | Yes | — |
| `resolution_status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `confirmed`, `rejected`, `needs_review`. |
| `review_note` | `text` | No | Default: `''`. |
| `reviewed_at` | `timestamp with time zone` | Yes | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_people_accounts_resolution`: Check: `"resolution_status" IN ('pending', 'confirmed', 'rejected', 'needs_review')`.
- `ck_people_accounts_window`: Check: `"last_observed_at" >= ("first_observed_at")`.
- `ck_people_accounts_conf`: Check: `("confidence" IS NULL OR ("confidence" >= 0.0 AND "confidence" <= 1.0))`.
- `uq_people_accounts_confirmed`: Unique (`author_id`) where `"resolution_status" = 'confirmed'`.
- `uq_people_accounts_primary`: Unique (`person_id`) where `("is_primary" AND "resolution_status" = 'confirmed')`.

[Back to table inventory](#table-inventory)

<a id="table-people_brand_affiliations"></a>

### `people_brand_affiliations` — PersonBrandAffiliation

One claim about a person’s role or relationship with an organization.

Model: [PersonBrandAffiliation](../../core/models.py#L5090).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `person_id` | `uuid` | No | Model: `person`. FK → [people.id](#table-people); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `brand_discovery_candidate_id` | `bigint` | Yes | Model: `brand_discovery_candidate`. FK → [brand_discovery_candidates.id](#table-brand_discovery_candidates); Django delete: `PROTECT`. |
| `affiliation_type` | `varchar(32)` | No | Choices: `employment`, `founder`, `advisor`, `board_member`, `contractor`, `ambassador`, `creator_partner`, `affiliate`, `investor`, `community`, `other`. Relationship kind; distinct from the person’s job title. |
| `observed_organization_name` | `text` | No | Organization name as observed in the source. |
| `observed_organization_handle` | `varchar(64)` | Yes | Organization handle as observed in the source. |
| `title_raw` | `text` | Yes | Title wording retained from the source. |
| `title_normalized` | `text` | Yes | Standardized title; not a dedicated English-translation field. |
| `department` | `text` | Yes | — |
| `team` | `text` | Yes | — |
| `job_function` | `text` | Yes | — |
| `seniority` | `text` | Yes | — |
| `employment_type` | `text` | Yes | — |
| `status` | `varchar(16)` | No | Default: `'unknown'`. Choices: `current`, `former`, `future`, `unknown`. |
| `start_date` | `varchar(10)` | Yes | Source-supported relationship start, paired with precision. |
| `start_date_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `day`, `month`, `year`, `unknown`. |
| `end_date` | `varchar(10)` | Yes | Source-supported relationship end, paired with precision. |
| `end_date_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `day`, `month`, `year`, `unknown`. |
| `location` | `text` | Yes | — |
| `workplace_type` | `text` | Yes | — |
| `description` | `text` | Yes | Relationship description; no language-specific sibling columns. |
| `confidence` | `double precision` | Yes | — |
| `review_status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `confirmed`, `rejected`, `needs_review`. |
| `review_note` | `text` | No | Default: `''`. |
| `reviewed_at` | `timestamp with time zone` | Yes | — |
| `source_system` | `varchar(64)` | Yes | — |
| `external_id` | `text` | Yes | — |
| `claim_identity` | `varchar(64)` | No | Unique. Stable identity for this claim; uniqueness is not a person-matching algorithm. |
| `superseded_by_id` | `bigint` | Yes | Reviewed replacement claim in this table; Django PROTECT. Distinct from current/former job status. |
| `superseded_at` | `timestamp with time zone` | Yes | When the replacement decision was recorded. |
| `superseded_by_reviewer` | `text` | No | Reviewer; default empty before replacement. |
| `supersession_reason` | `text` | No | Decision reason; default empty before replacement. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_pba_brand_type_status`: (`brand_id`, `affiliation_type`, `status`).
- `idx_pba_person_type`: (`person_id`, `affiliation_type`).

**Named constraints:**

- `ck_pba_one_organization`: Check: `(("brand_id" IS NOT NULL AND "brand_discovery_candidate_id" IS NULL) OR ("brand_id" IS NULL AND "brand_discovery_candidate_id" IS NOT NULL))`.
- `ck_pba_affiliation_type`: Check: `"affiliation_type" IN ('employment', 'founder', 'advisor', 'board_member', 'contractor', 'ambassador', 'creator_partner', 'affiliate', 'investor', 'community', 'other')`.
- `ck_pba_status`: Check: `"status" IN ('current', 'former', 'future', 'unknown')`.
- `ck_pba_review_status`: Check: `"review_status" IN ('pending', 'confirmed', 'rejected', 'needs_review')`.
- `ck_pba_confidence`: Check: `("confidence" IS NULL OR ("confidence" >= 0.0 AND "confidence" <= 1.0))`.
- `ck_pba_start_precision`: Check: `(("start_date" IS NULL AND "start_date_precision" = 'unknown') OR ("start_date"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND "start_date_precision" = 'day') OR ("start_date"::text ~ '^[0-9]{4}-[0-9]{2}$' AND "start_date_precision" = 'month') OR ("start_date"::text ~ '^[0-9]{4}$' AND "start_date_precision" = 'year'))`.
- `ck_pba_end_precision`: Check: `(("end_date" IS NULL AND "end_date_precision" = 'unknown') OR ("end_date"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND "end_date_precision" = 'day') OR ("end_date"::text ~ '^[0-9]{4}-[0-9]{2}$' AND "end_date_precision" = 'month') OR ("end_date"::text ~ '^[0-9]{4}$' AND "end_date_precision" = 'year'))`.
- `ck_pba_comparable_dates`: Check: `("start_date" IS NULL OR "end_date" IS NULL OR NOT ("start_date_precision" = ("end_date_precision")) OR "start_date" <= ("end_date"))`.

Migration 0063 enforces same-person/organization replacement, complete review metadata and acyclic chains. Recorded replacement decisions cannot be rewritten. Readers use `active_claims`; latest observation time alone never settles competing claims.

[Back to table inventory](#table-inventory)

<a id="table-people_brand_affiliation_evidence"></a>

### `people_brand_affiliation_evidence` — PersonBrandAffiliationEvidence

One source observation supporting an affiliation claim.

Model: [PersonBrandAffiliationEvidence](../../core/models.py#L5258).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `affiliation_id` | `bigint` | No | Model: `affiliation`. FK → [people_brand_affiliations.id](#table-people_brand_affiliations); Django delete: `CASCADE`. |
| `source_post_id` | `text` | Yes | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `SET_NULL`. |
| `source_profile_snapshot_id` | `bigint` | Yes | Model: `source_profile_snapshot`. FK → [account_profile_snapshots.id](#table-account_profile_snapshots); Django delete: `SET_NULL`. |
| `source_url` | `varchar(2048)` | Yes | — |
| `evidence_text` | `text` | No | Default: `''`. Supporting source wording. |
| `observed_at` | `timestamp with time zone` | No | When this evidence was observed, not the employment effective date. |
| `extracted_claim_data` | `jsonb` | No | Default: `{}`. Structured extracted claim data; not a replacement for source evidence. |
| `extraction_method` | `varchar(64)` | No | — |
| `extraction_model` | `text` | Yes | — |
| `extraction_prompt_version` | `text` | Yes | — |
| `confidence` | `double precision` | Yes | — |
| `review_status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `confirmed`, `rejected`, `needs_review`. |
| `reviewer` | `text` | Yes | — |
| `review_note` | `text` | No | Default: `''`. |
| `reviewed_at` | `timestamp with time zone` | Yes | — |
| `evidence_hash` | `varchar(64)` | No | Deduplication identity within an affiliation. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_pbae_review_status`: Check: `"review_status" IN ('pending', 'confirmed', 'rejected', 'needs_review')`.
- `ck_pbae_has_source`: Check: `("source_post_id" IS NOT NULL OR "source_profile_snapshot_id" IS NOT NULL OR ("source_url" IS NOT NULL AND NOT ("source_url" = '' AND "source_url" IS NOT NULL)))`.
- `ck_pbae_confidence`: Check: `("confidence" IS NULL OR ("confidence" >= 0.0 AND "confidence" <= 1.0))`.
- `uq_pbae_affiliation_hash`: Unique (`affiliation_id`, `evidence_hash`).

[Back to table inventory](#table-inventory)

<a id="table-profile_movement_candidates"></a>

### `profile_movement_candidates` — ProfileMovementCandidate

One observed profile change queued for personnel-movement interpretation.

Model: [ProfileMovementCandidate](../../core/models.py#L5037).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `author_id` | `text` | No | Model: `account`. FK → [accounts.author_id](#table-accounts); Django delete: `CASCADE`. |
| `prior_snapshot_id` | `bigint` | No | Model: `prior_snapshot`. FK → [account_profile_snapshots.id](#table-account_profile_snapshots); Django delete: `PROTECT`. |
| `new_snapshot_id` | `bigint` | No | Model: `new_snapshot`. FK → [account_profile_snapshots.id](#table-account_profile_snapshots); Django delete: `PROTECT`. |
| `source_post_id` | `text` | No | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `PROTECT`. |
| `prior_description` | `text` | No | — |
| `new_description` | `text` | No | — |
| `observed_at` | `timestamp with time zone` | No | When the changed profile was observed. |
| `effective_date` | `varchar(10)` | Yes | Source-supported movement date, if known. |
| `effective_date_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `day`, `month`, `year`, `unknown`. |
| `movement_identity` | `varchar(64)` | No | Unique. |
| `status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `succeeded`, `failed`. |
| `attempts` | `smallint` | No | Nonnegative. Default: `0`. |
| `last_error_code` | `varchar(128)` | No | Default: `''`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_profile_movement_transition`: Unique (`author_id`, `prior_snapshot_id`, `new_snapshot_id`).
- `ck_profile_movement_status`: Check: `"status" IN ('pending', 'succeeded', 'failed')`.
- `ck_profile_movement_date_precision`: Check: `(("effective_date" IS NULL AND "effective_date_precision" = 'unknown') OR ("effective_date"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND "effective_date_precision" = 'day') OR ("effective_date"::text ~ '^[0-9]{4}-[0-9]{2}$' AND "effective_date_precision" = 'month') OR ("effective_date"::text ~ '^[0-9]{4}$' AND "effective_date_precision" = 'year'))`.

[Back to table inventory](#table-inventory)

<a id="table-personnel_discovery_runs"></a>

### `personnel_discovery_runs` — PersonnelDiscoveryRun

One personnel-search query/window run, including coverage, cost, and extraction counts.

Model: [PersonnelDiscoveryRun](../../core/models.py#L5966).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `run_identity` | `varchar(64)` | No | Unique. |
| `run_id` | `text` | No | — |
| `cycle_id` | `text` | Yes | — |
| `query_id` | `bigint` | No | Model: `query`. FK → [search_queries.id](#table-search_queries); Django delete: `PROTECT`. |
| `query_text` | `text` | No | — |
| `query_hash` | `varchar(64)` | No | — |
| `query_pack_version` | `text` | No | — |
| `provider_boundary` | `text` | No | — |
| `tool_boundary` | `text` | Yes | — |
| `language` | `varchar(16)` | No | — |
| `query_family` | `varchar(32)` | No | — |
| `window_start` | `timestamp with time zone` | No | — |
| `window_end` | `timestamp with time zone` | No | — |
| `input_cursor` | `text` | Yes | — |
| `output_cursor` | `text` | Yes | — |
| `reviewed_post_count` | `integer` | No | Nonnegative. Default: `0`. |
| `accepted_post_count` | `integer` | No | Nonnegative. Default: `0`. |
| `excluded_count` | `integer` | No | Nonnegative. Default: `0`. |
| `exclusion_reasons` | `jsonb` | No | Default: `{}`. |
| `discovered_organization_count` | `integer` | No | Nonnegative. Default: `0`. |
| `provider_capabilities` | `jsonb` | No | Default: `{}`. |
| `provider_call_count` | `integer` | No | Nonnegative. Default: `0`. |
| `provider_credit_count` | `integer` | No | Nonnegative. Default: `0`. |
| `telemetry` | `jsonb` | No | Default: `{}`. |
| `limitations` | `jsonb` | No | Default: `[]`. |
| `status` | `varchar(16)` | No | Default: `'planned'`. Choices: `planned`, `running`, `completed`, `failed`, `truncated`, `blocked`. |
| `started_at` | `timestamp with time zone` | Yes | — |
| `completed_at` | `timestamp with time zone` | Yes | — |
| `completion_reason` | `text` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |
| `extracted_affiliation_count` | `integer` | No | Nonnegative. Default: `0`. |
| `extracted_evidence_count` | `integer` | No | Nonnegative. Default: `0`. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_personnel_runs_status`: Check: `"status" IN ('planned', 'running', 'completed', 'failed', 'truncated', 'blocked')`.
- `ck_personnel_runs_window`: Check: `"window_end" > ("window_start")`.

[Back to table inventory](#table-inventory)


<a id="table-people_names"></a>

### `people_names` — PersonName

One sourced spelling of a person’s full name, with optional evidenced components.

Original names stay authoritative. Language/script and origin are independent of the selected display locale. Generated or converted origins remain unchanged after corroboration. Names never identify or merge people. PostgreSQL triggers reject cross-person derivations and edits that would erase an original representation.

Model: [PersonName](../../core/models.py#L4603).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. |
| `person_id` | `uuid` | No | FK → [people](#table-people); Django CASCADE. |
| `full_name` | `text` | No | — |
| `given_name` | `text` | Yes | — |
| `family_name` | `text` | Yes | — |
| `language` | `varchar(35)` | No | Default: `'und'`. |
| `name_type` | `varchar(32)` | No | Default: `'professional'`. |
| `name_order` | `varchar(24)` | No | Default: `'unknown'`. |
| `origin` | `varchar(24)` | No | Default: `'source'`. |
| `derived_from_id` | `bigint` | Yes | FK → [people_names](#table-people_names); Django PROTECT. |
| `review_status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `confirmed`, `rejected`. |
| `review_history` | `jsonb` | No | Default: `list()`. |
| `fingerprint` | `varchar(64)` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_person_name_fingerprint`: `CONSTRAINT "uq_person_name_fingerprint" UNIQUE ("person_id", "fingerprint")`.
- `ck_person_name_nonempty`: `CONSTRAINT "ck_person_name_nonempty" CHECK (NOT ("full_name" = ''))`.
- `ck_person_name_review`: `CONSTRAINT "ck_person_name_review" CHECK ("review_status" IN ('pending', 'confirmed', 'rejected'))`.
- `ck_person_name_origin`: `CONSTRAINT "ck_person_name_origin" CHECK ("origin" IN ('source', 'owner', 'converted', 'generated', 'legacy'))`.
- `ck_person_name_not_self`: `CONSTRAINT "ck_person_name_not_self" CHECK (NOT ("derived_from_id" = ("id") AND "derived_from_id" IS NOT NULL))`.

Migration 0060 installs `g1_person_name_guard` on this table and `g1_person_name_selection` on `people`. These PostgreSQL triggers enforce same-person derivation/selection, confirmed selections, immutable original representations, and clearing selections before rejecting a name.

[Back to table inventory](#table-inventory)

<a id="table-people_name_evidence"></a>

### `people_name_evidence` — PersonNameEvidence

One observation supporting a name or explicitly supported name components.

Several observations can corroborate the same representation. Source excerpts, observation time, collection method and review reason remain separate from the name’s review status. Legacy backfills explicitly record unknown provenance.

Model: [PersonNameEvidence](../../core/models.py#L4657).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. |
| `name_id` | `bigint` | No | FK → [people_names](#table-people_names); Django CASCADE. |
| `source_kind` | `varchar(40)` | No | — |
| `source_reference` | `text` | No | — |
| `source_text` | `text` | No | Default: `''`. |
| `supports_fields` | `jsonb` | No | Default: `list()`. |
| `observed_at` | `timestamp with time zone` | No | — |
| `collection_method` | `varchar(64)` | No | — |
| `review_reason` | `text` | No | Default: `''`. |
| `evidence_hash` | `varchar(64)` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_person_name_evidence`: `CONSTRAINT "uq_person_name_evidence" UNIQUE ("name_id", "evidence_hash")`.
- `ck_person_name_source`: `CONSTRAINT "ck_person_name_source" CHECK (NOT ("source_reference" = ''))`.

[Back to table inventory](#table-inventory)

<a id="table-people_texts"></a>

### `people_texts` — PersonText

One immutable source version of biography, role, title, location or job-description prose, with separately reviewed attribution.

The version hash covers language and exact text, plus origin/derivation for translated or other derived representations. New source wording creates a new version; prior originals and translations remain available. Person names use the name tables instead.

Model: [PersonText](../../core/models.py#L4863).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. |
| `person_id` | `uuid` | No | FK → [people](#table-people); Django CASCADE. |
| `affiliation_id` | `bigint` | Yes | [Job claim](#table-people_brand_affiliations); required for titles. Django PROTECT. |
| `origin` | `varchar(24)` | No | Default source; source, translation, summary or unknown. |
| `derived_from_id` | `bigint` | Yes | Exact parent text in this table; Django PROTECT. |
| `review_status` | `varchar(16)` | No | Default pending; pending, confirmed or rejected. |
| `review_note` | `text` | No | Source audit or review explanation; default empty. |
| `kind` | `varchar(32)` | No | — |
| `language` | `varchar(35)` | No | — |
| `text` | `text` | No | — |
| `source_reference` | `text` | No | — |
| `version_hash` | `varchar(64)` | No | — |
| `observed_at` | `timestamp with time zone` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_person_text_version`: `CONSTRAINT "uq_person_text_version" UNIQUE NULLS NOT DISTINCT ("person_id", "affiliation_id", "kind", "source_reference", "version_hash")`.

- `ck_person_text_origin` and `ck_person_text_review` enforce the values above.
- `ck_person_title_affiliation` requires an affiliation for each title.

Migration 0064 prevents changing captured wording, language, source, version, origin, derivation or affiliation. New wording creates a new row. Deferred database guards enforce the same person for text and job, matching person/affiliation for derived text and acyclic derivation. Identity corrections can move complete dependencies together.

[Back to table inventory](#table-inventory)

<a id="table-people_text_translations"></a>

### `people_text_translations` — PersonTextTranslation

One cached translation of a specific original prose version and provider configuration.

English/Japanese display text stays linked to the exact original. Missing or failed translation does not replace the source or prevent staff intake. Translation runs explicitly outside source transactions.

Model: [PersonTextTranslation](../../core/models.py#L4883).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. |
| `original_id` | `bigint` | No | FK → [people_texts](#table-people_texts); Django CASCADE. |
| `language` | `varchar(35)` | No | — |
| `text` | `text` | No | — |
| `provider` | `varchar(64)` | No | — |
| `model` | `varchar(128)` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_person_text_translation`: `CONSTRAINT "uq_person_text_translation" UNIQUE ("original_id", "language", "provider", "model", "prompt_version")`.

[Back to table inventory](#table-inventory)

<a id="table-people_identity_corrections"></a>

### `people_identity_corrections` — PersonIdentityCorrection

One operator's reviewed account confirmation, merge or selective split. This is
an audit record, not another identity or evidence source. Original names, intake
payloads and provider histories retain their source meanings.

Model: [PersonIdentityCorrection](../../core/models.py).
Writer: [correct_identity](../../core/person_identity_corrections.py).

**Primary key:** `id`. **Named indexes:** automatic primary-key, unique request-key and foreign-key indexes only.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | Database-generated identity. |
| `request_key` | `varchar(128)` | No | Unique operator request; reuse requires exactly the same request. |
| `kind` | `varchar(24)` | No | merge, split or confirm_account. |
| `source_id` | `uuid` | No | Original [person](#table-people); Django PROTECT. |
| `target_id` | `uuid` | No | Destination [person](#table-people); Django PROTECT. |
| `reviewer` | `text` | No | Operator identity. |
| `reason` | `text` | No | Explanation of the reviewed correction. |
| `request` | `jsonb` | No | Exact requested operation and selected row IDs; default dict. |
| `changes` | `jsonb` | No | Source snapshots, mappings and resulting identity/account state; default dict. |
| `created_at` | `timestamp with time zone` | No | Django creation timestamp. |

**Named constraints:** `ck_identity_correction_kind` allows the three operations;
`ck_identity_correction_review` requires nonempty reviewer, reason and request key.
Migration 0062's `protect_identity_correction` trigger rejects UPDATE and DELETE.
The Python service validates selected dependencies, serializes against worker
claims, refuses running workers and records the correction atomically.

[Back to table inventory](#table-inventory)

<a id="table-people_media"></a>

### `people_media` — PersonMedia

One person-specific attribution of an image or video reference to a source.

Multiple publisher attributions may point to identical media bytes. Source verification, individual-portrait suitability, availability and permission for reuse remain separate. An X avatar may be a logo; downloading it does not make it a verified portrait. Video-page references can exist without downloadable video bytes.

Model: [PersonMedia](../../core/models.py#L4812).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. |
| `person_id` | `uuid` | No | FK → [people](#table-people); Django CASCADE. |
| `media_id` | `varchar(64)` | Yes | FK → [staff_media_objects](#table-staff_media_objects); Django PROTECT. |
| `fingerprint` | `varchar(64)` | No | — |
| `source_url` | `varchar(4096)` | No | — |
| `original_url` | `varchar(4096)` | No | Default: `''`. |
| `source_kind` | `varchar(40)` | No | — |
| `discovery_provider` | `varchar(64)` | No | Default: `''`. |
| `kind` | `varchar(24)` | No | Default: `'image'`. |
| `availability` | `varchar(24)` | No | Default: `'unfetched'`. |
| `source_verified` | `boolean` | No | Default: `False`. |
| `individual_portrait` | `boolean` | No | Default: `False`. |
| `suitability` | `varchar(24)` | No | Default: `'pending'`. |
| `reuse_status` | `varchar(24)` | No | Default: `'unknown'`. |
| `verification_reason` | `text` | No | Default: `''`. |
| `evidence` | `jsonb` | No | Default: `dict()`. |
| `review_history` | `jsonb` | No | Default: `list()`. |
| `observed_at` | `timestamp with time zone` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_person_media_attribution`: `CONSTRAINT "uq_person_media_attribution" UNIQUE ("person_id", "fingerprint")`.
- `ck_media_verification_reason`: `CONSTRAINT "ck_media_verification_reason" CHECK ((NOT "source_verified" OR NOT ("verification_reason" = '')))`.
- `ck_media_suitability`: `CONSTRAINT "ck_media_suitability" CHECK ("suitability" IN ('pending', 'approved', 'rejected'))`.
- `ck_media_reuse`: `CONSTRAINT "ck_media_reuse" CHECK ("reuse_status" IN ('unknown', 'permitted', 'restricted'))`.

[Back to table inventory](#table-inventory)

<a id="table-staff_media_objects"></a>

### `staff_media_objects` — StaffMediaObject

One validated image file, addressed by its SHA-256 content hash.

Bytes live in the configured staff_media Django storage, outside PostgreSQL and Git. Records retain dimensions, type and byte size. File decoding and bounded public-network checks run before publication in a dossier.

Model: [StaffMediaObject](../../core/models.py#L4799).

**Primary key:** `sha256`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `sha256` | `varchar(64)` | No | PK. |
| `storage_name` | `text` | No | — |
| `media_type` | `varchar(64)` | No | — |
| `byte_size` | `bigint` | No | — |
| `width` | `integer` | Yes | — |
| `height` | `integer` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond field-level database rules.

[Back to table inventory](#table-inventory)

<a id="organizations"></a>

## Companies, brands, and organization discovery

A company and a brand are separate identities: a company can own brands,
and ownership is recorded in `brands_companies`. Account-role links describe an
account’s association with a company/brand; they do not replace a person’s dated
affiliation history. `roles` labels those account relationships.

Organization candidates hold unresolved names instead of forcing them into a
known brand. Exact candidate tokens and their source evidence are separate,
reviewable records. Review can point the candidate at a known brand. Keywords,
search terms, and hashtags support matching/collection and do not establish
ownership or employment. See [organization extraction](../../core/targeted_extraction.py)
and the [lookup guide](lookup-tables.md).


<a id="table-companies"></a>

### `companies` — Company

One company identity, including its recorded headquarters country.

Model: [Company](../../core/models.py#L450).

**Primary key:** `nickname`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `nickname` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `display_name` | `text` | Yes | — |
| `hq_country` | `text` | Yes | — |
| `accent_color` | `text` | Yes | — |
| `description` | `text` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `display_name_en` | `text` | Yes | — |
| `display_name_zh_cn` | `text` | Yes | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-brands"></a>

### `brands` — Brand

One brand identity and its display metadata.

Model: [Brand](../../core/models.py#L424).

**Primary key:** `nickname`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `nickname` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `display_name` | `text` | Yes | — |
| `accent_color` | `text` | Yes | — |
| `is_sentinel` | `boolean` | No | Default: `False`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `display_name_en` | `text` | Yes | — |
| `display_name_zh_cn` | `text` | Yes | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-brands_companies"></a>

### `brands_companies` — BrandCompany

One ownership relationship between a brand and a company.

Model: [BrandCompany](../../core/models.py#L2010).

**Primary key:** `brand_id`, `company_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `company_id` | `varchar(64)` | No | Model: `company`. PK component. FK → [companies.nickname](#table-companies); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `ownership_pct` | `double precision` | No | Default: `1.0`. Stored ownership weight/fraction; model default is 1.0. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-brands_accounts"></a>

### `brands_accounts` — BrandAccount

One account’s role for a brand, such as official or researcher.

Model: [BrandAccount](../../core/models.py#L2032).

**Primary key:** `brand_id`, `accounts_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `accounts_id` | `text` | No | Model: `account`. PK component. FK → [accounts.author_id](#table-accounts); Django delete: `CASCADE`. |
| `role_id` | `varchar(64)` | No | Model: `role`. FK → [roles.key](#table-roles); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `added_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_brands_accounts_role_id`: (`role_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-companies_accounts"></a>

### `companies_accounts` — CompanyAccount

One account’s role for a company.

Model: [CompanyAccount](../../core/models.py#L2064).

**Primary key:** `company_id`, `author_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `company_id` | `varchar(64)` | No | Model: `company`. PK component. FK → [companies.nickname](#table-companies); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `author_id` | `text` | No | Model: `account`. PK component. FK → [accounts.author_id](#table-accounts); Django delete: `CASCADE`. |
| `role_id` | `varchar(64)` | No | Model: `role`. FK → [roles.key](#table-roles); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `added_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_companies_accounts_role_id`: (`role_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-brand_discovery_candidates"></a>

### `brand_discovery_candidates` — BrandDiscoveryCandidate

One unresolved organization identity awaiting review against known brands.

Model: [BrandDiscoveryCandidate](../../core/models.py#L5330).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `observed_name` | `text` | No | — |
| `aliases` | `jsonb` | No | Default: `[]`. |
| `candidate_handles` | `jsonb` | No | Default: `[]`. |
| `organization_ai_relationship` | `text` | Yes | — |
| `source_post_id` | `text` | Yes | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `SET_NULL`. |
| `source_query_id` | `bigint` | Yes | Model: `source_query`. FK → [search_queries.id](#table-search_queries); Django delete: `SET_NULL`. |
| `source_identities` | `jsonb` | No | Default: `[]`. |
| `confidence` | `double precision` | Yes | — |
| `verification_status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `confirmed`, `rejected`, `needs_review`. |
| `reviewer` | `text` | Yes | — |
| `review_note` | `text` | No | Default: `''`. |
| `reviewed_at` | `timestamp with time zone` | Yes | — |
| `reviewed_brand_id` | `varchar(64)` | Yes | Model: `reviewed_brand`. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `candidate_identity` | `varchar(64)` | No | Unique. |
| `first_observed_at` | `timestamp with time zone` | No | — |
| `last_observed_at` | `timestamp with time zone` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_brand_candidate_review`: Check: `"verification_status" IN ('pending', 'confirmed', 'rejected', 'needs_review')`.
- `ck_brand_candidate_window`: Check: `"last_observed_at" >= ("first_observed_at")`.
- `ck_brand_candidate_conf`: Check: `("confidence" IS NULL OR ("confidence" >= 0.0 AND "confidence" <= 1.0))`.

[Back to table inventory](#table-inventory)

<a id="table-brand_discovery_candidate_tokens"></a>

### `brand_discovery_candidate_tokens` — BrandDiscoveryCandidateToken

One exact observed spelling or handle for an unresolved organization.

Model: [BrandDiscoveryCandidateToken](../../core/models.py#L5400).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `candidate_id` | `bigint` | No | Model: `candidate`. FK → [brand_discovery_candidates.id](#table-brand_discovery_candidates); Django delete: `CASCADE`. |
| `form` | `text` | No | — |
| `kind` | `varchar(16)` | No | Choices: `spelling`, `handle`, `nickname`. |
| `script` | `varchar(16)` | No | — |
| `first_observed_at` | `timestamp with time zone` | No | — |
| `last_observed_at` | `timestamp with time zone` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_brand_candidate_token_exact`: Unique (`candidate_id`, `form`, `kind`).
- `ck_brand_candidate_token_form`: Check: `NOT ("form" = '')`.
- `ck_brand_candidate_token_kind`: Check: `"kind" IN ('spelling', 'handle', 'nickname')`.
- `ck_brand_candidate_token_window`: Check: `"last_observed_at" >= ("first_observed_at")`.

[Back to table inventory](#table-inventory)

<a id="table-brand_discovery_candidate_token_evidence"></a>

### `brand_discovery_candidate_token_evidence` — BrandDiscoveryCandidateTokenEvidence

One source observation supporting an organization token.

Model: [BrandDiscoveryCandidateTokenEvidence](../../core/models.py#L5445).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `token_id` | `bigint` | No | Model: `token`. FK → [brand_discovery_candidate_tokens.id](#table-brand_discovery_candidate_tokens); Django delete: `CASCADE`. |
| `source_hit_id` | `bigint` | Yes | Model: `source_hit`. FK → [rare_type_search_hits.id](#table-rare_type_search_hits); Django delete: `PROTECT`. |
| `source_profile_movement_id` | `bigint` | Yes | Model: `source_profile_movement`. FK → [profile_movement_candidates.id](#table-profile_movement_candidates); Django delete: `PROTECT`. |
| `source_post_id` | `text` | No | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `PROTECT`. |
| `rare_type` | `varchar(32)` | No | Choices: `personnel_changes`, `job_listings`, `events`, `opportunities`, `model_releases`. |
| `observed_at` | `timestamp with time zone` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_candidate_token_hit_evidence`: Unique (`token_id`, `source_hit_id`, `source_post_id`, `rare_type`) where `"source_hit_id" IS NOT NULL`.
- `uq_candidate_token_movement_evidence`: Unique (`token_id`, `source_profile_movement_id`, `source_post_id`, `rare_type`) where `"source_profile_movement_id" IS NOT NULL`.
- `ck_candidate_token_one_source`: Check: `(("source_hit_id" IS NOT NULL AND "source_profile_movement_id" IS NULL) OR ("source_hit_id" IS NULL AND "source_profile_movement_id" IS NOT NULL))`.
- `ck_brand_candidate_token_rare_type`: Check: `"rare_type" IN ('personnel_changes', 'job_listings', 'events', 'opportunities', 'model_releases')`.

[Back to table inventory](#table-inventory)

<a id="table-brand_keywords"></a>

### `brand_keywords` — BrandKeyword

One literal or regular-expression matching pattern for a brand.

Model: [BrandKeyword](../../core/models.py#L3063).

**Primary key:** `brand_id`, `pattern` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `pattern` | `text` | No | PK component. |
| `is_regex` | `boolean` | No | Default: `False`. |
| `added_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `is_primary` | `boolean` | No | Default: `False`. Selects the primary keyword subset for brand-wide query composition. |

**Named indexes:**

- `idx_brand_keywords_brand_id`: (`brand_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-brand_search_terms"></a>

### `brand_search_terms` — BrandSearchTerm

One search term associated with a brand.

Model: [BrandSearchTerm](../../core/models.py#L3047).

**Primary key:** `brand_id`, `term` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `term` | `text` | No | PK component. |
| `added_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-brand_hashtags"></a>

### `brand_hashtags` — BrandHashtag

One hashtag associated with a brand.

Model: [BrandHashtag](../../core/models.py#L3086).

**Primary key:** `brand_id`, `tag` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `tag` | `text` | No | Model: `hashtag`. PK component. Tag string without the leading #. |
| `added_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_brand_hashtags_brand_id`: (`brand_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)


<a id="accounts"></a>

## X accounts, profiles, and lists

An account is an X identity keyed by `author_id`; it can represent a person,
a company, or another kind of account. `handle` can be absent or change. People
without X accounts belong in `people`, rather than receiving fabricated X IDs.

`accounts` contains the current saved profile. `account_profile_snapshots`
preserves consecutive profile observations: another observation of the same
hash extends a period instead of creating an identical snapshot row. A profile
that later returns to an earlier value can begin a new observation period.
The author fields inside `posts` are per-post snapshots, a different record
from either account table. Missing profile values remain NULL; NULL does not
mean the account explicitly denied a fact.

List membership and list-sync completion are separate so a successfully
fetched empty list can still have a completion marker. See [profile handling](../../core/profile_snapshots.py)
and [collection behavior](twitterapi-io-calls.md).


<a id="table-accounts"></a>

### `accounts` — Account

One X account, keyed by the provider’s stable user ID, with its current saved profile.

Model: [Account](../../core/models.py#L944).

**Primary key:** `author_id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `author_id` | `text` | No | PK. X provider user ID as text; stable account identity. |
| `handle` | `varchar(64)` | Yes | Collation: `case_insensitive`. Current saved username; nullable and case-insensitively unique when present. |
| `display_name` | `text` | Yes | — |
| `bio` | `text` | Yes | Saved biography text. |
| `bio_fetched_at` | `timestamp with time zone` | Yes | — |
| `verified` | `boolean` | No | Default: `False`. Provider verification/checkmark flag, not identity-review approval. |
| `bio_contains_brand` | `boolean` | Yes | — |
| `first_seen_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `last_seen_at` | `timestamp with time zone` | No | Set by Django on model save. |
| `source_query_ids` | `text` | Yes | — |
| `notes` | `text` | Yes | — |
| `bio_en` | `text` | Yes | English biography text. |
| `bio_zh_cn` | `text` | Yes | Simplified Chinese biography text. |
| `followers_count` | `integer` | Yes | — |
| `following_count` | `integer` | Yes | — |
| `favourites_count` | `integer` | Yes | — |
| `statuses_count` | `integer` | Yes | — |
| `media_count` | `integer` | Yes | — |
| `fast_followers_count` | `integer` | Yes | — |
| `is_blue_verified` | `boolean` | Yes | — |
| `verified_type` | `text` | Yes | — |
| `profile_picture` | `text` | Yes | Saved profile-image URL; the image need not depict the account holder. |
| `location` | `text` | Yes | Free-form profile location; not the resolved geography. |
| `description` | `text` | Yes | Provider author.description text. |
| `profile_bio_text` | `text` | Yes | Provider profile_bio.description text. |
| `followers_fetched_at` | `timestamp with time zone` | Yes | Observation/write timestamp for saved engagement/profile metadata. |
| `created_at` | `timestamp with time zone` | Yes | Source account-creation time. |
| `protected` | `boolean` | Yes | — |
| `affiliate_label_badge_url` | `varchar(2048)` | Yes | — |
| `affiliate_label_description` | `text` | Yes | — |
| `affiliate_label_url` | `varchar(2048)` | Yes | — |
| `affiliate_label_url_type` | `varchar(128)` | Yes | — |
| `affiliate_label_user_label_display_type` | `varchar(128)` | Yes | — |
| `affiliate_label_user_label_type` | `varchar(128)` | Yes | — |
| `account_based_in` | `text` | Yes | X-provided “based in” text. |
| `location_accurate` | `boolean` | Yes | — |
| `learn_more_url` | `varchar(2048)` | Yes | — |
| `affiliate_username` | `varchar(64)` | Yes | — |
| `source` | `varchar(128)` | Yes | — |
| `username_changes_count` | `integer` | Yes | Nonnegative. |
| `username_changes_last_changed_at_msec` | `bigint` | Yes | Nonnegative. |
| `created_country_accurate` | `boolean` | Yes | — |
| `verification_info_id` | `varchar(128)` | Yes | — |
| `verification_info_is_identity_verified` | `boolean` | Yes | — |
| `verification_info_reason_verified_since_msec` | `bigint` | Yes | Nonnegative. |
| `verification_info_reason_override_verified_year` | `smallint` | Yes | Nonnegative. |
| `unavailable` | `boolean` | Yes | — |
| `unavailable_reason` | `text` | Yes | — |
| `identity_profile_label_badge_url` | `varchar(2048)` | Yes | — |
| `identity_profile_label_description` | `text` | Yes | — |
| `identity_profile_label_long_description` | `text` | Yes | — |
| `identity_profile_label_url` | `varchar(2048)` | Yes | — |
| `identity_profile_label_url_type` | `varchar(128)` | Yes | — |
| `identity_profile_label_user_label_display_type` | `varchar(128)` | Yes | — |
| `identity_profile_label_user_label_type` | `varchar(128)` | Yes | — |
| `country_code` | `varchar(2)` | Yes | Model: `country`. FK → [countries.code](#table-countries); Django delete: `PROTECT`. |
| `based_in_region_key` | `varchar(64)` | Yes | Model: `based_in_region`. FK → [regions.key](#table-regions); Django delete: `PROTECT`. |
| `account_based_in_fetched_at` | `timestamp with time zone` | Yes | Freshness timestamp for the X geography observation. |

**Named indexes:**

- `idx_accounts_handle`: (`handle`).
- `idx_accounts_last_seen_at`: (`last_seen_at`).

**Named constraints:**

- `ck_accounts_one_geography_target`: Check: `("country_code" IS NULL OR "based_in_region_key" IS NULL)`.

Migration-only index: `uniq_accounts_handle_lower` is unique on
`LOWER(handle)` where `handle IS NOT NULL` ([migration 0009](../../core/migrations/0009_accounts_handle_unique_ci.py)).
The country FK is explicitly named `fk_accounts_country_code` in
[migration 0027](../../core/migrations/0027_account_country_foreign_key.py).

[Back to table inventory](#table-inventory)

<a id="table-account_profile_snapshots"></a>

### `account_profile_snapshots` — AccountProfileSnapshot

One consecutive observation period during which an account’s saved profile hash is unchanged.

Model: [AccountProfileSnapshot](../../core/models.py#L4969).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `author_id` | `text` | No | Model: `account`. FK → [accounts.author_id](#table-accounts); Django delete: `CASCADE`. |
| `profile_hash` | `varchar(64)` | No | Hash of the observed profile content used for consecutive compression. |
| `first_observed_at` | `timestamp with time zone` | No | Start of this consecutive observation period. |
| `last_observed_at` | `timestamp with time zone` | No | Latest observation of this same consecutive profile value. |
| `observation_count` | `integer` | No | Nonnegative. Default: `1`. |
| `first_source_kind` | `varchar(32)` | No | — |
| `first_source_post_id` | `text` | Yes | Model: `first_source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `SET_NULL`. |
| `first_source_run` | `text` | Yes | — |
| `handle` | `varchar(64)` | Yes | — |
| `display_name` | `text` | Yes | — |
| `description` | `text` | Yes | — |
| `profile_bio_text` | `text` | Yes | — |
| `location` | `text` | Yes | — |
| `profile_image_url` | `varchar(2048)` | Yes | — |
| `verified` | `boolean` | Yes | — |
| `is_blue_verified` | `boolean` | Yes | — |
| `verified_type` | `text` | Yes | — |
| `affiliate_target_username` | `varchar(64)` | Yes | — |
| `affiliate_target_url` | `varchar(2048)` | Yes | — |
| `affiliate_label_description` | `text` | Yes | — |
| `affiliate_badge_image_url` | `varchar(2048)` | Yes | — |
| `affiliate_label_type` | `varchar(128)` | Yes | — |
| `affiliate_display_type` | `varchar(128)` | Yes | — |
| `present_fields` | `jsonb` | No | Default: `[]`. Which fields were present; distinguishes absent source fields from supplied values. |
| `profile_data` | `jsonb` | No | Default: `{}`. |
| `raw_profile_payload` | `jsonb` | Yes | — |
| `recorded_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_profile_snap_account_last`: (`author_id`, `last_observed_at DESC`).
- `idx_profile_snap_hash`: (`profile_hash`).

**Named constraints:**

- `ck_profile_snap_window`: Check: `"last_observed_at" >= ("first_observed_at")`.
- `ck_profile_snap_count`: Check: `"observation_count" >= 1`.
- `uq_profile_snap_identity`: Unique (`author_id`, `profile_hash`, `first_observed_at`).

[Back to table inventory](#table-inventory)

<a id="table-twitter_list_memberships"></a>

### `twitter_list_memberships` — TwitterListMembership

One account’s membership state in one X list.

Model: [TwitterListMembership](../../core/models.py#L1331).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `list_id` | `bigint` | No | — |
| `author_id` | `text` | No | Model: `account`. FK → [accounts.author_id](#table-accounts); Django delete: `CASCADE`. |
| `active` | `boolean` | No | Default: `True`. |
| `first_seen_at` | `timestamp with time zone` | No | Default: `django.utils.timezone.now()`. |
| `last_seen_at` | `timestamp with time zone` | No | Default: `django.utils.timezone.now()`. |
| `last_complete_reconciliation_at` | `timestamp with time zone` | Yes | — |
| `source` | `varchar(32)` | No | — |
| `source_run_id` | `varchar(128)` | No | Default: `''`. |

**Named indexes:**

- `idx_tlm_list_active`: (`list_id`, `active`).

**Named constraints:**

- `uq_twitter_list_membership`: Unique (`list_id`, `author_id`).
- `ck_tlm_seen_order`: Check: `"last_seen_at" >= ("first_seen_at")`.
- `ck_tlm_reconciled_order`: Check: `("last_complete_reconciliation_at" IS NULL OR "last_complete_reconciliation_at" >= ("first_seen_at"))`.

[Back to table inventory](#table-inventory)

<a id="table-twitter_list_sync_state"></a>

### `twitter_list_sync_state` — TwitterListSyncState

One X list’s last completed membership synchronization.

Model: [TwitterListSyncState](../../core/models.py#L1379).

**Primary key:** `list_id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `list_id` | `bigint` | No | PK. |
| `snapshot_id` | `varchar(128)` | No | — |
| `last_complete_at` | `timestamp with time zone` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-account_post_appearances"></a>

### `account_post_appearances` — AccountPostAppearance

One account’s appearance in one collected post, with collection context.

Model: [AccountPostAppearance](../../core/models.py#L2740).

**Primary key:** `author_id`, `tweet_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `author_id` | `text` | No | Model: `account`. PK component. FK → [accounts.author_id](#table-accounts); Django delete: `CASCADE`. |
| `tweet_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `role_at_time` | `text` | Yes | — |
| `source_query_ids` | `text` | Yes | — |

**Named indexes:**

- `idx_acct_post_app_post_id`: (`tweet_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)


<a id="geography"></a>

## Countries and regions

These tables describe country/territory codes, geographic regions, and
display names. The account’s free-form `location` text and X’s `account_based_in`
value are different inputs. A reviewed mapping can resolve a “based in” value
to one country or one region. An account cannot have both resolved targets at
once, and an unresolved account can have neither. A display-parent relationship
does not change a country/territory’s stored identity.


<a id="table-countries"></a>

### `countries` — Country

One country/territory code and optional display-parent relationship.

Model: [Country](../../core/models.py#L811).

**Primary key:** `code`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `code` | `varchar(2)` | No | PK. |
| `m49_code` | `varchar(3)` | No | Unique. |
| `display_parent_country_id` | `varchar(2)` | Yes | Model: `display_parent_country`. FK → [countries.code](#table-countries); Django delete: `PROTECT`. |
| `display_parent_relationship_type` | `varchar(64)` | Yes | Choices: `special_administrative_region`, `owner_display_context`, `us_insular_area`, `french_overseas`, `british_overseas_territory`, `crown_dependency`, `kingdom_constituent_country`, `netherlands_public_body`. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_countries_display_parent_complete`: Check: `(("display_parent_country_id" IS NULL AND "display_parent_relationship_type" IS NULL) OR ("display_parent_country_id" IS NOT NULL AND "display_parent_relationship_type" IS NOT NULL))`.
- `ck_countries_not_self_parent`: Check: `("display_parent_country_id" IS NULL OR NOT ("display_parent_country_id" = ("code") AND "display_parent_country_id" IS NOT NULL))`.
- `ck_countries_parent_relationship_type`: Check: `("display_parent_relationship_type" IS NULL OR "display_parent_relationship_type" IN ('special_administrative_region', 'owner_display_context', 'us_insular_area', 'french_overseas', 'british_overseas_territory', 'crown_dependency', 'kingdom_constituent_country', 'netherlands_public_body'))`.

[Back to table inventory](#table-inventory)

<a id="table-country_labels"></a>

### `country_labels` — CountryLabel

One translated label for a country code.

Model: [CountryLabel](../../core/models.py#L871).

**Primary key:** `country_code`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `country_code` | `varchar(2)` | No | Model: `country`. PK component. FK → [countries.code](#table-countries); Django delete: `CASCADE`. |
| `lang` | `varchar(16)` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-regions"></a>

### `regions` — Region

One region in the geographic hierarchy.

Model: [Region](../../core/models.py#L765).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. |
| `m49_code` | `varchar(3)` | Yes | Unique. |
| `source` | `varchar(64)` | No | — |
| `level` | `varchar(32)` | No | — |
| `parent_id` | `varchar(64)` | Yes | Model: `parent`. FK → [regions.key](#table-regions); Django delete: `PROTECT`. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_regions_not_self_parent`: Check: `("parent_id" IS NULL OR NOT ("parent_id" = ("key") AND "parent_id" IS NOT NULL))`.

[Back to table inventory](#table-inventory)

<a id="table-region_labels"></a>

### `region_labels` — RegionLabel

One translated label for a region.

Model: [RegionLabel](../../core/models.py#L795).

**Primary key:** `region_key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `region_key` | `varchar(64)` | No | Model: `region`. PK component. FK → [regions.key](#table-regions); Django delete: `CASCADE`. |
| `lang` | `varchar(16)` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-country_codes_region"></a>

### `country_codes_region` — CountryRegion

One country’s assigned region and the source of that assignment.

Model: [CountryRegion](../../core/models.py#L887).

**Primary key:** `country_code`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `country_code` | `varchar(2)` | No | Model: `country`. PK. FK → [countries.code](#table-countries); Django delete: `CASCADE`. |
| `region_key` | `varchar(64)` | No | Model: `region`. FK → [regions.key](#table-regions); Django delete: `PROTECT`. |
| `source` | `varchar(64)` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-account_based_in_mappings"></a>

### `account_based_in_mappings` — AccountBasedInMapping

One reviewed mapping from an X “based in” string to a country or region.

Model: [AccountBasedInMapping](../../core/models.py#L909).

**Primary key:** `value`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `value` | `text` | No | PK. |
| `country_code` | `varchar(2)` | Yes | Model: `country`. FK → [countries.code](#table-countries); Django delete: `CASCADE`. |
| `region_key` | `varchar(64)` | Yes | Model: `region`. FK → [regions.key](#table-regions); Django delete: `CASCADE`. |
| `review_note` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_account_based_in_mapping_one_target`: Check: `(("country_code" IS NOT NULL AND "region_key" IS NULL) OR ("country_code" IS NULL AND "region_key" IS NOT NULL))`.

[Back to table inventory](#table-inventory)


<a id="posts"></a>

## Posts and classification

`posts` stores source content and snapshots. The related tables answer
different questions: which brand the post concerns, which tokens matched,
which type/sentiment/topic was assigned, and what evidence/versions produced
the judgment. A post may concern several brands, so counting brand edges is
not the same as counting unique posts.

Current classification uses versioned state, Audience Topics, geopolitical
modes, national stance, and untracked-brand promotion records. Legacy discourse,
nationalism, and unsanctioned-flag tables remain queryable for compatibility;
their presence does not make them the current classifier’s output contract.
China/US national stance is separate from geopolitical mode and is meaningful
with the nationalism mode under the [classification contract](classifier-prompts.md).
The judgment ledger records provider/input/output lineage; it does not by itself
imply an additional runtime model call.

The post’s `created_at` is the source posting time, `created_at_raw` preserves
the provider’s timestamp string, and `fetched_at` is collection time. The
quoted-post link is NULL if its target is not stored; no placeholder post is
required. The top-level provider fields and `author_*` snapshots can be sparse,
especially for sources that did not supply those fields. `accounts` is the
current saved profile, not an automatic reconstruction from every post snapshot.


<a id="table-posts"></a>

### `posts` — Post

One collected X post, its source text, metrics, and author snapshot.

Model: [Post](../../core/models.py#L1395).

**Primary key:** `tweet_id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `tweet_id` | `text` | No | PK. X status/post ID as text. |
| `author_handle` | `varchar(64)` | Yes | Collation: `case_insensitive`. Saved author handle for direct display. |
| `author_id` | `text` | Yes | Model: `author`. FK → [accounts.author_id](#table-accounts); Django delete: `SET_NULL`. |
| `text` | `text` | Yes | Original source post text. |
| `lang` | `text` | Yes | Provider-declared language. |
| `created_at` | `timestamp with time zone` | Yes | Parsed source posting time. |
| `fetched_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `like_count` | `integer` | Yes | — |
| `retweet_count` | `integer` | Yes | — |
| `reply_count` | `integer` | Yes | — |
| `quote_count` | `integer` | Yes | — |
| `in_reply_to_user_id` | `text` | Yes | Replied-to account’s provider ID; plain text, not an account FK. |
| `quoted_status_id` | `text` | Yes | FK → [posts.tweet_id](#table-posts); Django delete: `SET_NULL`. Quoted/retweeted inner post; NULL when that post is not stored. |
| `conversation_id` | `text` | Yes | — |
| `entities` | `jsonb` | Yes | Provider entity payload. |
| `source_query_id` | `text` | Yes | — |
| `headline` | `text` | Yes | Saved extracted headline text. |
| `headline_source` | `text` | Yes | — |
| `text_en` | `text` | Yes | English translation compatibility field. |
| `text_zh_cn` | `text` | Yes | Chinese translation compatibility field. |
| `commentary_en` | `text` | Yes | English commentary compatibility field. |
| `commentary_zh_cn` | `text` | Yes | Chinese commentary compatibility field. |
| `lang_detected` | `text` | Yes | Detected source language. |
| `quoted_text` | `text` | Yes | — |
| `last_quote_count_seen` | `integer` | Yes | — |
| `last_quote_fetched_at` | `timestamp with time zone` | Yes | — |
| `metrics_refreshed_at` | `timestamp with time zone` | Yes | Completion timestamp for metrics refresh. |
| `created_at_epoch` | `bigint` | Yes | Posting time as epoch seconds for range queries. |
| `created_at_raw` | `text` | Yes | Provider’s unparsed posting timestamp. |
| `bookmark_count` | `integer` | Yes | — |
| `is_reply` | `boolean` | Yes | — |
| `is_retweet` | `boolean` | Yes | — |
| `is_quote` | `boolean` | Yes | — |
| `in_reply_to_id` | `text` | Yes | Replied-to post/status ID; distinct from in_reply_to_user_id. |
| `in_reply_to_username` | `text` | Yes | — |
| `tweet_type` | `text` | Yes | — |
| `tweet_url` | `text` | Yes | — |
| `tweet_twitter_url` | `text` | Yes | — |
| `card` | `jsonb` | Yes | Provider card object. |
| `place` | `jsonb` | Yes | Provider geo-place object. |
| `client_source` | `text` | Yes | Source client application. |
| `view_count` | `integer` | Yes | — |
| `article` | `jsonb` | Yes | X Article/long-form post object. |
| `is_limited_reply` | `boolean` | Yes | — |
| `community_info` | `jsonb` | Yes | — |
| `display_text_range` | `jsonb` | Yes | Display-text start/end indices. |
| `extended_entities` | `jsonb` | Yes | Full media/entity payload. |
| `quoted_author_handle` | `text` | Yes | Saved handle of the quoted post’s author. |
| `author_name` | `text` | Yes | — |
| `author_followers_count` | `integer` | Yes | — |
| `author_following_count` | `integer` | Yes | — |
| `author_verified` | `boolean` | Yes | — |
| `author_is_blue_verified` | `boolean` | Yes | — |
| `author_verified_type` | `text` | Yes | Provider verification type, e.g. Business or Government. |
| `author_is_translator` | `boolean` | Yes | — |
| `author_is_automated` | `boolean` | Yes | — |
| `author_automated_by` | `text` | Yes | — |
| `author_description` | `text` | Yes | — |
| `author_location` | `text` | Yes | — |
| `author_media_count` | `integer` | Yes | — |
| `author_statuses_count` | `integer` | Yes | — |
| `author_favourites_count` | `integer` | Yes | — |
| `author_fast_followers_count` | `integer` | Yes | — |
| `author_can_dm` | `boolean` | Yes | — |
| `author_can_media_tag` | `boolean` | Yes | — |
| `author_profile_picture` | `text` | Yes | Profile-image URL in this post’s author snapshot. |
| `author_profile_bio` | `jsonb` | Yes | Full profile_bio object in this post’s author snapshot. |
| `author_cover_picture` | `text` | Yes | — |
| `author_pinned_tweet_ids` | `jsonb` | Yes | List of pinned post IDs in the author snapshot. |
| `author_affiliates_highlighted_label` | `jsonb` | Yes | — |
| `author_withheld_in_countries` | `jsonb` | Yes | Country-code list in the author snapshot. |
| `author_possibly_sensitive` | `boolean` | Yes | — |
| `author_has_custom_timelines` | `boolean` | Yes | — |
| `author_entities` | `jsonb` | Yes | — |
| `author_twitter_url` | `text` | Yes | — |
| `author_type` | `text` | Yes | Provider account type, e.g. user or bot. |
| `author_url` | `text` | Yes | Author’s external URL from the snapshot. |
| `author_created_at_raw` | `text` | Yes | — |
| `author_status` | `text` | Yes | — |

**Named indexes:**

- `idx_posts_author_id`: (`author_id`).
- `idx_posts_created_at`: (`created_at`).
- `idx_posts_created_cover`: (`created_at`); includes `tweet_id`, `author_id`.
- `idx_posts_lang`: (`lang`).
- `idx_posts_lang_detected`: (`lang_detected`).
- `idx_posts_source_query_id`: (`source_query_id`).
- `idx_posts_created_at_epoch`: (`created_at_epoch`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Migration 0005](../../core/migrations/0005_fix_posts_fks_on_delete_set_null.py)
explicitly gives the SQL `author_id` and `quoted_status_id` foreign keys
`ON DELETE SET NULL`, `DEFERRABLE INITIALLY DEFERRED`. Do not generalize those
SQL clauses to every Django `on_delete=SET_NULL` field.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands"></a>

### `posts_brands` — PostBrand

One post-to-brand attribution and its relevance weight.

Model: [PostBrand](../../core/models.py#L2096).

**Primary key:** `post_id`, `brand_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `weight` | `double precision` | No | Default: `1.0`. Attribution relevance weight. |

**Named indexes:**

- `idx_posts_brands_brand_id`: (`brand_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands_mentions"></a>

### `posts_brands_mentions` — PostBrandMention

One matching source that connected a post to a brand.

Model: [PostBrandMention](../../core/models.py#L2121).

**Primary key:** `post_id`, `brand_id`, `source` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `source` | `text` | No | PK component. Match origin, e.g. keyword, hashtag, or handle. |
| `raw_token` | `text` | Yes | Exact token that matched. |
| `mentioned_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_post_brand_mention_brand`: (`brand_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands_signals"></a>

### `posts_brands_signals` — PostBrandSignal

One post type and sentiment assignment for a post/brand pair.

Model: [PostBrandSignal](../../core/models.py#L2150).

**Primary key:** `post_id`, `brand_id`, `post_type_key` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `post_type_key` | `varchar(64)` | No | Model: `post_type`. PK component. FK → [post_type_keys.key](#table-post_type_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `sentiment` | `varchar(64)` | No | FK → [sentiment_keys.key](#table-sentiment_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |

**Named indexes:**

- `idx_pb_sig_b_p_type`: (`brand_id`, `post_type_key`).
- `idx_pb_sig_b_sent`: (`brand_id`, `sentiment`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands_classification_states"></a>

### `posts_brands_classification_states` — PostBrandClassificationState

One current versioned classification state for a post/brand pair.

Model: [PostBrandClassificationState](../../core/models.py#L2195).

**Primary key:** `post_id`, `brand_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `contract_version` | `varchar(64)` | No | — |
| `taxonomy_version` | `varchar(64)` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `model` | `varchar(256)` | No | — |
| `source_language` | `varchar(64)` | No | Default: `''`. |
| `input_context_fingerprint` | `varchar(64)` | No | — |
| `outcome` | `varchar(32)` | No | Choices: `classified`, `context_missing`. |
| `sentiment` | `varchar(64)` | Yes | FK → [sentiment_keys.key](#table-sentiment_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `china_nationalism` | `varchar(64)` | Yes | FK → [nationalism_keys.key](#table-nationalism_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `us_nationalism` | `varchar(64)` | Yes | FK → [nationalism_keys.key](#table-nationalism_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `china_national_stance` | `varchar(64)` | Yes | FK → [national_stance_keys.key](#table-national_stance_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `us_national_stance` | `varchar(64)` | Yes | FK → [national_stance_keys.key](#table-national_stance_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `selected_final_judgment_id` | `bigint` | Yes | Model: `selected_final_judgment`. FK → [posts_brands_classification_judgments.id](#table-posts_brands_classification_judgments); Django delete: `SET_NULL`. |
| `classified_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_pb_cls_state_brand_outcome`: (`brand_id`, `outcome`).
- `idx_pb_cls_state_contract`: (`contract_version`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands_classification_judgments"></a>

### `posts_brands_classification_judgments` — PostBrandClassificationJudgment

One recorded stage of a classifier judgment, including inputs and validation.

Model: [PostBrandClassificationJudgment](../../core/models.py#L2380).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `post_id` | `text` | No | Model: `post`. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `revision_id` | `varchar(64)` | No | — |
| `stage` | `varchar(32)` | No | Choices: `primary`, `review`, `content`, `brand_interpretation`, `final`. |
| `canonical_judgment` | `jsonb` | No | — |
| `contract_version` | `varchar(64)` | No | — |
| `taxonomy_version` | `varchar(64)` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `model` | `varchar(256)` | No | — |
| `provider_role` | `varchar(64)` | No | — |
| `input_context_fingerprint` | `varchar(64)` | No | — |
| `selector_version` | `varchar(64)` | No | — |
| `validation_state` | `varchar(32)` | No | — |
| `changes_json` | `jsonb` | No | Default: `{}`. |
| `parent_judgment_id` | `bigint` | Yes | Model: `parent_judgment`. FK → [posts_brands_classification_judgments.id](#table-posts_brands_classification_judgments); Django delete: `CASCADE`. |
| `content_judgment_id` | `bigint` | Yes | Model: `content_judgment`. FK → [posts_brands_classification_judgments.id](#table-posts_brands_classification_judgments); Django delete: `CASCADE`. |
| `brand_interpretation_judgment_id` | `bigint` | Yes | Model: `brand_interpretation_judgment`. FK → [posts_brands_classification_judgments.id](#table-posts_brands_classification_judgments); Django delete: `CASCADE`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_pb_cls_judgment_history`: (`post_id`, `brand_id`, `created_at DESC`).
- `idx_pb_cls_judgment_revision`: (`revision_id`, `stage`).

**Named constraints:**

- `uq_pb_cls_judgment_revision_stage`: Unique (`post_id`, `brand_id`, `revision_id`, `stage`).
- `ck_pb_cls_judgment_parent`: Check: `(("brand_interpretation_judgment_id" IS NULL AND "content_judgment_id" IS NULL AND "parent_judgment_id" IS NULL AND "stage" = 'primary') OR ("brand_interpretation_judgment_id" IS NULL AND "content_judgment_id" IS NULL AND "parent_judgment_id" IS NOT NULL AND "stage" = 'review') OR ("brand_interpretation_judgment_id" IS NULL AND "content_judgment_id" IS NULL AND "parent_judgment_id" IS NULL AND "stage" IN ('content', 'brand_interpretation')) OR ("brand_interpretation_judgment_id" IS NULL AND "content_judgment_id" IS NULL AND "parent_judgment_id" IS NOT NULL AND "stage" = 'final') OR ("brand_interpretation_judgment_id" IS NOT NULL AND "content_judgment_id" IS NOT NULL AND "parent_judgment_id" IS NULL AND "stage" = 'final'))`.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands_audience_topics"></a>

### `posts_brands_audience_topics` — PostBrandAudienceTopic

One audience-topic assignment for a post/brand pair.

Model: [PostBrandAudienceTopic](../../core/models.py#L2268).

**Primary key:** `post_id`, `brand_id`, `concept_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `concept_id` | `bigint` | No | Model: `concept`. PK component. FK → [audience_topic_concepts.id](#table-audience_topic_concepts); Django delete: `PROTECT`. |
| `scheme_key` | `varchar(128)` | No | Model: `scheme`. FK → [audience_topic_schemes.key](#table-audience_topic_schemes); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `scheme_revision` | `smallint` | No | Nonnegative. |
| `evidence` | `jsonb` | No | Default: `{}`. |
| `prompt_version` | `varchar(64)` | No | — |
| `model` | `varchar(256)` | No | — |
| `provider_role` | `varchar(64)` | No | — |
| `final_judgment_id` | `bigint` | Yes | Model: `final_judgment`. FK → [posts_brands_classification_judgments.id](#table-posts_brands_classification_judgments); Django delete: `SET_NULL`. |
| `assigned_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_pb_aud_topic_brand_concept`: (`brand_id`, `concept_id`).
- `idx_pb_aud_topic_scheme_rev`: (`scheme_key`, `scheme_revision`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands_geopolitical_modes"></a>

### `posts_brands_geopolitical_modes` — PostBrandGeopoliticalMode

One geopolitical-mode assignment for a post/brand pair.

Model: [PostBrandGeopoliticalMode](../../core/models.py#L2327).

**Primary key:** `post_id`, `brand_id`, `geopolitical_mode_key` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `geopolitical_mode_key` | `varchar(64)` | No | Model: `geopolitical_mode`. PK component. FK → [geopolitical_mode_keys.key](#table-geopolitical_mode_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `taxonomy_version` | `varchar(64)` | No | — |
| `evidence` | `jsonb` | No | Default: `{}`. |
| `prompt_version` | `varchar(64)` | No | — |
| `model` | `varchar(256)` | No | — |
| `provider_role` | `varchar(64)` | No | — |
| `final_judgment_id` | `bigint` | Yes | Model: `final_judgment`. FK → [posts_brands_classification_judgments.id](#table-posts_brands_classification_judgments); Django delete: `SET_NULL`. |
| `assigned_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_pb_geo_mode_brand_mode`: (`brand_id`, `geopolitical_mode_key`).
- `idx_pb_geo_mode_taxonomy`: (`taxonomy_version`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands_product_labels"></a>

### `posts_brands_product_labels` — PostBrandProductLabel

One independent product-feedback label for a post/brand pair.

Model: [PostBrandProductLabel](../../core/models.py#L2499).

**Primary key:** `post_id`, `brand_id`, `product_label_key` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `product_label_key` | `varchar(64)` | No | Model: `product_label`. PK component. FK → [product_label_keys.key](#table-product_label_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |

**Named indexes:**

- `idx_pb_product_brand_label`: (`brand_id`, `product_label_key`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands_discourse"></a>

### `posts_brands_discourse` — PostBrandDiscourse

One legacy pragmatic speech-act assignment for a post/brand pair.

Model: [PostBrandDiscourse](../../core/models.py#L2526).

**Primary key:** `post_id`, `brand_id`, `discourse_key`, `act_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `discourse_key` | `varchar(64)` | No | Model: `discourse`. PK component. FK → [discourse_keys.key](#table-discourse_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `act_id` | `smallint` | No | PK component. Nonnegative. Distinguishes separate speech acts for a post/brand pair. |
| `china_nationalism` | `varchar(64)` | Yes | FK → [nationalism_keys.key](#table-nationalism_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `us_nationalism` | `varchar(64)` | Yes | FK → [nationalism_keys.key](#table-nationalism_keys); Django delete: `PROTECT`. Collation: `case_insensitive`. |

**Named indexes:**

- `idx_post_brand_dis_b_dr`: (`brand_id`, `discourse_key`).
- `idx_post_brand_dis_b_cn_nat`: (`brand_id`, `china_nationalism`).
- `idx_post_brand_dis_b_us_nat`: (`brand_id`, `us_nationalism`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-posts_untracked_brand_promotions"></a>

### `posts_untracked_brand_promotions` — PostUntrackedBrandPromotion

One current post-level judgment about promotion of an untracked brand.

Model: [PostUntrackedBrandPromotion](../../core/models.py#L2624).

**Primary key:** `post_id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `promotion_keys` | `jsonb` | No | Default: `[]`. |
| `evidence` | `jsonb` | No | Default: `{}`. |
| `contract_version` | `varchar(64)` | No | — |
| `taxonomy_version` | `varchar(64)` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `model` | `varchar(256)` | No | — |
| `provider_role` | `varchar(64)` | No | — |
| `final_judgment_id` | `bigint` | Yes | Model: `final_judgment`. FK → [posts_brands_classification_judgments.id](#table-posts_brands_classification_judgments); Django delete: `SET_NULL`. |
| `decided_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_post_untracked_promo_keys`: (`promotion_keys`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-untracked_brand_promotion_evidence"></a>

### `untracked_brand_promotion_evidence` — UntrackedBrandPromotionEvidence

One visible promoted subject supporting an untracked-brand judgment.

Model: [UntrackedBrandPromotionEvidence](../../core/models.py#L2661).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `promotion_post_id` | `text` | No | Model: `promotion`. FK → [posts_untracked_brand_promotions.post_id](#table-posts_untracked_brand_promotions); Django delete: `CASCADE`. |
| `brand_discovery_candidate_id` | `bigint` | No | Model: `brand_discovery_candidate`. FK → [brand_discovery_candidates.id](#table-brand_discovery_candidates); Django delete: `PROTECT`. |
| `source_post_id` | `text` | No | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `PROTECT`. |
| `exact_matched_account_id` | `text` | Yes | Model: `exact_matched_account`. FK → [accounts.author_id](#table-accounts); Django delete: `SET_NULL`. |
| `observed_name` | `text` | No | — |
| `aliases` | `jsonb` | No | Default: `[]`. |
| `handles` | `jsonb` | No | Default: `[]`. |
| `domains` | `jsonb` | No | Default: `[]`. |
| `products` | `jsonb` | No | Default: `[]`. |
| `hashtags` | `jsonb` | No | Default: `[]`. |
| `evidence_spans` | `jsonb` | No | Default: `[]`. |
| `subject_identity` | `varchar(64)` | No | — |
| `first_seen_at` | `timestamp with time zone` | No | — |
| `last_seen_at` | `timestamp with time zone` | No | — |
| `recurrence_count` | `integer` | No | Nonnegative. Default: `1`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_untracked_promo_cand_last`: (`brand_discovery_candidate_id`, `last_seen_at DESC`).
- `idx_untracked_promo_acct_last`: (`exact_matched_account_id`, `last_seen_at DESC`).

**Named constraints:**

- `uq_untracked_promo_subject_identity`: Unique (`promotion_post_id`, `subject_identity`).
- `ck_untracked_promo_evidence_window`: Check: `"last_seen_at" >= ("first_seen_at")`.
- `ck_untracked_promo_evidence_recurrence`: Check: `"recurrence_count" >= 1`.
- `ck_untracked_promo_evidence_source_post`: Check: `"source_post_id" = ("promotion_post_id")`.

[Back to table inventory](#table-inventory)

<a id="table-posts_unsanctioned_flags"></a>

### `posts_unsanctioned_flags` — PostUnsanctionedFlag

One post’s legacy unsanctioned-flag assignment.

Model: [PostUnsanctionedFlag](../../core/models.py#L2594).

**Primary key:** `post_id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `flags` | `text` | No | Legacy JSON array serialized as text. |
| `flag_set` | `jsonb` | Yes | Structured flag-key set; nullable, including older/unbackfilled rows. |
| `evidence` | `text` | Yes | — |
| `decided_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_unsanctioned_flag_set`: (`flag_set`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)


<a id="vocabularies"></a>

## Classification vocabularies and translated labels

Vocabulary tables store stable keys; their paired label tables store
language-specific display text. Labels do not change the underlying identity.
Audience Topics add a scheme and revision, so a label revision can change
without inventing a new concept. The primary keys prevent duplicate labels
for the same identity/locale (and revision where applicable).

`roles` describes account relationships such as official, researcher, executive,
or investor. A person’s actual job title is free/source text in an affiliation,
not a `roles` key. The legacy discourse vocabulary includes genuine hype,
sarcasm, and dunk registers; legacy nationalism keys cover the shared China/US
scale. Current runtime vocabulary and seed details are in [Lookup tables](lookup-tables.md).


<a id="table-roles"></a>

### `roles` — Role

One account-role vocabulary key.

Model: [Role](../../core/models.py#L368).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-role_labels"></a>

### `role_labels` — RoleLabel

One translated account-role label.

Model: [RoleLabel](../../core/models.py#L386).

**Primary key:** `key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | Model: `role`. PK component. FK → [roles.key](#table-roles); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `lang` | `text` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-post_type_keys"></a>

### `post_type_keys` — PostTypeKey

One post-type vocabulary key, such as release or review.

Model: [PostTypeKey](../../core/models.py#L45).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-post_type_labels"></a>

### `post_type_labels` — PostTypeLabel

One translated post-type label.

Model: [PostTypeLabel](../../core/models.py#L63).

**Primary key:** `key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | Model: `post_type`. PK component. FK → [post_type_keys.key](#table-post_type_keys); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `lang` | `text` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-sentiment_keys"></a>

### `sentiment_keys` — SentimentKey

One sentiment vocabulary key.

Model: [SentimentKey](../../core/models.py#L263).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-sentiment_labels"></a>

### `sentiment_labels` — SentimentLabel

One translated sentiment label.

Model: [SentimentLabel](../../core/models.py#L281).

**Primary key:** `key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | Model: `sentiment`. PK component. FK → [sentiment_keys.key](#table-sentiment_keys); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `lang` | `text` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-product_label_keys"></a>

### `product_label_keys` — ProductLabelKey

One independent product-feedback vocabulary key.

Model: [ProductLabelKey](../../core/models.py#L79).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-product_label_labels"></a>

### `product_label_labels` — ProductLabelLabel

One translated product-feedback label.

Model: [ProductLabelLabel](../../core/models.py#L94).

**Primary key:** `key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | Model: `product_label`. PK component. FK → [product_label_keys.key](#table-product_label_keys); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `lang` | `text` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-audience_topic_schemes"></a>

### `audience_topic_schemes` — AudienceTopicScheme

One versioned audience-topic scheme and its manifest identity.

Model: [AudienceTopicScheme](../../core/models.py#L110).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(128)` | No | PK. Collation: `case_insensitive`. |
| `revision` | `smallint` | No | Nonnegative. Default: `1`. |
| `manifest_hash` | `varchar(64)` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-audience_topic_concepts"></a>

### `audience_topic_concepts` — AudienceTopicConcept

One stable topic identity within an audience-topic scheme.

Model: [AudienceTopicConcept](../../core/models.py#L127).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `scheme_key` | `varchar(128)` | No | Model: `scheme`. FK → [audience_topic_schemes.key](#table-audience_topic_schemes); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `key` | `varchar(64)` | No | Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_audience_topic_scheme_key`: Unique (`scheme_key`, `key`).

[Back to table inventory](#table-inventory)

<a id="table-audience_topic_labels"></a>

### `audience_topic_labels` — AudienceTopicLabel

One translated topic label for a particular revision.

Model: [AudienceTopicLabel](../../core/models.py#L152).

**Primary key:** `concept_id`, `revision`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `concept_id` | `bigint` | No | Model: `concept`. PK component. FK → [audience_topic_concepts.id](#table-audience_topic_concepts); Django delete: `CASCADE`. |
| `revision` | `smallint` | No | PK component. Nonnegative. Default: `1`. |
| `lang` | `varchar(16)` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-geopolitical_mode_keys"></a>

### `geopolitical_mode_keys` — GeopoliticalModeKey

One geopolitical-mode vocabulary key.

Model: [GeopoliticalModeKey](../../core/models.py#L170).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-geopolitical_mode_labels"></a>

### `geopolitical_mode_labels` — GeopoliticalModeLabel

One translated geopolitical-mode label.

Model: [GeopoliticalModeLabel](../../core/models.py#L185).

**Primary key:** `key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | Model: `geopolitical_mode`. PK component. FK → [geopolitical_mode_keys.key](#table-geopolitical_mode_keys); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `lang` | `varchar(16)` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-national_stance_keys"></a>

### `national_stance_keys` — NationalStanceKey

One China/US national-stance direction vocabulary key.

Model: [NationalStanceKey](../../core/models.py#L201).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-national_stance_labels"></a>

### `national_stance_labels` — NationalStanceLabel

One translated national-stance label.

Model: [NationalStanceLabel](../../core/models.py#L216).

**Primary key:** `key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | Model: `national_stance`. PK component. FK → [national_stance_keys.key](#table-national_stance_keys); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `lang` | `varchar(16)` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-untracked_brand_promotion_keys"></a>

### `untracked_brand_promotion_keys` — UntrackedBrandPromotionKey

One current untracked-brand-promotion vocabulary key.

Model: [UntrackedBrandPromotionKey](../../core/models.py#L232).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-untracked_brand_promotion_labels"></a>

### `untracked_brand_promotion_labels` — UntrackedBrandPromotionLabel

One translated untracked-brand-promotion label.

Model: [UntrackedBrandPromotionLabel](../../core/models.py#L247).

**Primary key:** `key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | Model: `untracked_brand_promotion`. PK component. FK → [untracked_brand_promotion_keys.key](#table-untracked_brand_promotion_keys); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `lang` | `varchar(16)` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-discourse_keys"></a>

### `discourse_keys` — DiscourseKey

One legacy pragmatic-register vocabulary key.

Model: [DiscourseKey](../../core/models.py#L297).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-discourse_labels"></a>

### `discourse_labels` — DiscourseLabel

One translated legacy pragmatic-register label.

Model: [DiscourseLabel](../../core/models.py#L315).

**Primary key:** `key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | Model: `discourse`. PK component. FK → [discourse_keys.key](#table-discourse_keys); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `lang` | `text` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-nationalism_keys"></a>

### `nationalism_keys` — NationalismKey

One legacy nationalism-scale vocabulary key shared by the China and US axes.

Model: [NationalismKey](../../core/models.py#L331).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-nationalism_labels"></a>

### `nationalism_labels` — NationalismLabel

One translated legacy nationalism-scale label.

Model: [NationalismLabel](../../core/models.py#L352).

**Primary key:** `key`, `lang` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | Model: `nationalism`. PK component. FK → [nationalism_keys.key](#table-nationalism_keys); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `lang` | `text` | No | PK component. |
| `label` | `text` | No | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-unsanctioned_flag_keys"></a>

### `unsanctioned_flag_keys` — UnsanctionedFlagKey

One legacy unsanctioned-flag vocabulary key; there is no paired label table.

Model: [UnsanctionedFlagKey](../../core/models.py#L402).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(64)` | No | PK. Collation: `case_insensitive`. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)


<a id="products"></a>

## Products, model releases, and Hugging Face catalog

A product has its own stable `product_key`; a Hugging Face `repo_id` is
optional. This lets a product exist without a Hugging Face repository. `hf_orgs`
maps a namespace to a company, while the product’s brand link identifies its
tracked brand. Product verification proposals preserve an observed name and
the evidence used to resolve it. `posts_brands_products` records a specific,
source-backed product mention.

`model_releases` describes a release claim/occurrence; it is not the catalog
row itself. The release’s evidence may remain pending review. Catalog run,
namespace-run, and observation tables separate overall execution, pagination
coverage, and individual repository observations. Repository `created_at` and
`last_modified` are source dates; `collected_at` and `updated_at` track local
collection. Raw JSON columns remain separate from selected searchable fields.


<a id="table-products"></a>

### `products` — Product

One model/product identity, with optional Hugging Face repository metadata.

Model: [Product](../../core/models.py#L2771).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `product_key` | `uuid` | No | Unique. Default: `uuid.uuid4()`. Stable product identity independent of an optional repository. |
| `repo_id` | `varchar(256)` | Yes | Unique. Collation: `case_insensitive`. Optional Hugging Face repository slug; unique when supplied. |
| `type` | `varchar(32)` | Yes | Choices: `llm-model`, `other-ai-model`, `agent-harness`. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `SET_NULL`. Collation: `case_insensitive`. |
| `hf_org_id` | `varchar(64)` | Yes | Model: `hf_org`. FK → [hf_orgs.namespace](#table-hf_orgs); Django delete: `SET_NULL`. Collation: `case_insensitive`. |
| `hf_type` | `text` | No | Default: `'model'`. Hugging Face resource kind, e.g. model, dataset, or space. |
| `display_name` | `text` | Yes | — |
| `author` | `text` | Yes | — |
| `sha` | `text` | Yes | — |
| `private` | `boolean` | Yes | — |
| `gated` | `text` | Yes | — |
| `disabled` | `boolean` | Yes | — |
| `pipeline_tag` | `text` | Yes | — |
| `library_name` | `text` | Yes | — |
| `downloads` | `bigint` | Yes | Recent source download count. |
| `downloads_all_time` | `bigint` | Yes | Source all-time download count when supplied. |
| `download_velocity` | `double precision` | Yes | — |
| `likes` | `bigint` | Yes | — |
| `trending_score` | `double precision` | Yes | — |
| `paperswithcode_id` | `text` | Yes | — |
| `created_at` | `timestamp with time zone` | Yes | Source repository/product creation time. |
| `last_modified` | `timestamp with time zone` | Yes | Source repository last-modified time. |
| `tags_json` | `jsonb` | Yes | Model: `tags`. Repository tags. |
| `siblings_json` | `jsonb` | Yes | Model: `siblings`. Repository file listing. |
| `card_data_json` | `jsonb` | Yes | Model: `card_data`. Model-card metadata. |
| `config_json` | `jsonb` | Yes | Model: `config`. Repository configuration metadata. |
| `spaces_json` | `jsonb` | Yes | Model: `spaces`. Associated Spaces metadata. |
| `raw_json` | `jsonb` | Yes | Model: `raw`. Saved raw source metadata. |
| `hf_metadata` | `jsonb` | No | Default: `{}`. Hugging Face metadata envelope. |
| `collected_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_products_brand`: (`brand_id`).
- `idx_products_hf_org_id`: (`hf_org_id`).
- `idx_products_collected_at`: (`collected_at`).

**Named constraints:**

- `ck_product_type`: Check: `("type" IS NULL OR "type" IN ('llm-model', 'other-ai-model', 'agent-harness'))`.

[Back to table inventory](#table-inventory)

<a id="table-hf_orgs"></a>

### `hf_orgs` — HFOrg

One Hugging Face organization/user namespace linked to a company.

Model: [HFOrg](../../core/models.py#L477).

**Primary key:** `namespace`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `namespace` | `varchar(64)` | No | PK. Collation: `case_insensitive`. Hugging Face organization/user slug. |
| `company_id` | `varchar(64)` | No | Model: `company`. FK → [companies.nickname](#table-companies); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `confirmed` | `boolean` | No | Default: `False`. Namespace-to-company confirmation state. |
| `discovered_via` | `text` | No | Default: `'curated'`. |
| `added_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_hf_orgs_company`: (`company_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-posts_brands_products"></a>

### `posts_brands_products` — PostBrandProduct

One source-backed claim that a post names an exact product for a brand.

Model: [PostBrandProduct](../../core/models.py#L2859).

**Primary key:** `post_id`, `brand_id`, `product_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK component. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. PK component. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `product_id` | `bigint` | No | Model: `product`. PK component. FK → [products.id](#table-products); Django delete: `PROTECT`. |
| `observed_name` | `text` | No | — |
| `source_evidence` | `jsonb` | No | Default: `{}`. |
| `verification_policy_version` | `varchar(128)` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_pbp_product_post`: (`product_id`, `post_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-product_verification_proposals"></a>

### `product_verification_proposals` — ProductVerificationProposal

One reviewable proposal to resolve an observed product name to a product.

Model: [ProductVerificationProposal](../../core/models.py#L2894).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `proposal_key` | `varchar(64)` | No | Unique. |
| `source_post_id` | `text` | No | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `PROTECT`. |
| `source_release_id` | `bigint` | Yes | Model: `source_release`. FK → [model_releases.id](#table-model_releases); Django delete: `SET_NULL`. |
| `proposed_brand_id` | `varchar(64)` | Yes | Model: `proposed_brand`. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `proposed_candidate_id` | `bigint` | Yes | Model: `proposed_candidate`. FK → [brand_discovery_candidates.id](#table-brand_discovery_candidates); Django delete: `PROTECT`. |
| `author_id` | `text` | No | Model: `account`. FK → [accounts.author_id](#table-accounts); Django delete: `PROTECT`. |
| `account_handle_snapshot` | `varchar(64)` | No | Default: `''`. |
| `observed_name` | `text` | No | — |
| `candidate_repo_id` | `varchar(256)` | No | Default: `''`. |
| `account_evidence` | `jsonb` | No | Default: `{}`. |
| `hf_evidence` | `jsonb` | No | Default: `{}`. |
| `hf_outcome` | `varchar(16)` | No | Default: `ProductVerificationProposal.HFOutcome.PENDING`. Choices: `pending`, `matched`, `missing`, `private`, `timeout`, `throttled`, `error`, `malformed`, `deferred`. |
| `policy_version` | `varchar(128)` | No | — |
| `rule_trace` | `jsonb` | No | Default: `[]`. |
| `review_status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `approved`, `rejected`. |
| `resolved_product_id` | `bigint` | Yes | Model: `resolved_product`. FK → [products.id](#table-products); Django delete: `PROTECT`. |
| `attempted_at` | `timestamp with time zone` | Yes | — |
| `next_attempt_at` | `timestamp with time zone` | Yes | — |
| `verification_claim_token` | `uuid` | Yes | — |
| `verification_claim_expires_at` | `timestamp with time zone` | Yes | — |
| `reviewer` | `text` | Yes | — |
| `review_reason` | `text` | No | Default: `''`. |
| `reviewed_at` | `timestamp with time zone` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_product_proposal_due`: (`hf_outcome`, `next_attempt_at`).

**Named constraints:**

- `ck_product_proposal_one_owner`: Check: `(("proposed_brand_id" IS NOT NULL AND "proposed_candidate_id" IS NULL) OR ("proposed_brand_id" IS NULL AND "proposed_candidate_id" IS NOT NULL))`.

[Back to table inventory](#table-inventory)

<a id="table-model_releases"></a>

### `model_releases` — ModelRelease

One source-backed model-release occurrence and its stated date precision.

Model: [ModelRelease](../../core/models.py#L6407).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `brand_discovery_candidate_id` | `bigint` | Yes | Model: `brand_discovery_candidate`. FK → [brand_discovery_candidates.id](#table-brand_discovery_candidates); Django delete: `PROTECT`. |
| `observed_model_name` | `text` | No | — |
| `version` | `text` | No | Default: `''`. |
| `release_channel` | `varchar(16)` | No | Default: `'other'`. Choices: `stable`, `preview`, `beta`, `other`. |
| `release_value` | `varchar(64)` | Yes | — |
| `release_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `day`, `month`, `year`, `unknown`. |
| `release_identity` | `varchar(64)` | No | Unique. |
| `first_seen_at` | `timestamp with time zone` | No | — |
| `last_seen_at` | `timestamp with time zone` | No | — |
| `extraction_version` | `text` | No | — |
| `review_status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `confirmed`, `rejected`, `needs_review`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_model_release_one_owner`: Check: `(("brand_id" IS NOT NULL AND "brand_discovery_candidate_id" IS NULL) OR ("brand_id" IS NULL AND "brand_discovery_candidate_id" IS NOT NULL))`.
- `ck_model_release_seen_window`: Check: `"last_seen_at" >= ("first_seen_at")`.
- `ck_model_release_precision`: Check: `(("release_precision" = 'unknown' AND "release_value" IS NULL) OR ("release_precision" = 'day' AND "release_value"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') OR ("release_precision" = 'month' AND "release_value"::text ~ '^[0-9]{4}-[0-9]{2}$') OR ("release_precision" = 'year' AND "release_value"::text ~ '^[0-9]{4}$'))`.

[Back to table inventory](#table-inventory)

<a id="table-model_release_evidence"></a>

### `model_release_evidence` — ModelReleaseEvidence

One observed source claim supporting a model release.

Model: [ModelReleaseEvidence](../../core/models.py#L6461).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `release_id` | `bigint` | No | Model: `release`. FK → [model_releases.id](#table-model_releases); Django delete: `CASCADE`. |
| `source_post_id` | `text` | No | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `PROTECT`. |
| `source_url` | `varchar(2048)` | Yes | — |
| `observed_at` | `timestamp with time zone` | No | — |
| `observed_claim` | `jsonb` | No | Default: `{}`. |
| `evidence_hash` | `varchar(64)` | No | — |
| `extraction_version` | `text` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_model_release_evidence`: Unique (`release_id`, `source_post_id`, `evidence_hash`).

[Back to table inventory](#table-inventory)

<a id="table-hf_model_catalog_runs"></a>

### `hf_model_catalog_runs` — HFModelCatalogRun

One overall Hugging Face catalog collection run.

Model: [HFModelCatalogRun](../../core/models.py#L2977).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `uuid` | No | PK. Default: `uuid.uuid4()`. |
| `scope` | `jsonb` | No | — |
| `outcome` | `varchar(40)` | No | Default: `'pending'`. |
| `invocations` | `jsonb` | No | Default: `[]`. |
| `report` | `jsonb` | No | Default: `{}`. |
| `started_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |
| `finished_at` | `timestamp with time zone` | Yes | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-hf_model_catalog_namespace_runs"></a>

### `hf_model_catalog_namespace_runs` — HFModelCatalogNamespaceRun

One namespace’s enumeration state within a catalog run.

Model: [HFModelCatalogNamespaceRun](../../core/models.py#L2991).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `run_id` | `uuid` | No | Model: `run`. FK → [hf_model_catalog_runs.id](#table-hf_model_catalog_runs); Django delete: `CASCADE`. |
| `namespace` | `varchar(64)` | No | — |
| `ownership` | `jsonb` | No | — |
| `cursor` | `text` | Yes | — |
| `cursor_history` | `jsonb` | No | Default: `[]`. |
| `enumeration_complete` | `boolean` | No | Default: `False`. |
| `outcome` | `varchar(64)` | No | Default: `'pending'`. |
| `envelopes` | `jsonb` | No | Default: `[]`. |
| `raw_count` | `bigint` | No | Default: `0`. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_hf_catalog_run_namespace`: Unique (`run_id`, `namespace`).

[Back to table inventory](#table-inventory)

<a id="table-hf_model_catalog_observations"></a>

### `hf_model_catalog_observations` — HFModelCatalogObservation

One repository observation within a namespace run.

Model: [HFModelCatalogObservation](../../core/models.py#L3013).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `namespace_run_id` | `bigint` | No | Model: `namespace_run`. FK → [hf_model_catalog_namespace_runs.id](#table-hf_model_catalog_namespace_runs); Django delete: `CASCADE`. |
| `repo_key` | `varchar(256)` | No | — |
| `repo_id` | `varchar(256)` | No | — |
| `product_id` | `bigint` | Yes | Model: `product`. FK → [products.id](#table-products); Django delete: `SET_NULL`. |
| `created_product` | `boolean` | No | Default: `False`. |
| `listing` | `jsonb` | No | Default: `{}`. |
| `envelopes` | `jsonb` | No | Default: `[]`. |
| `groups` | `jsonb` | No | Default: `{}`. |
| `outcome` | `varchar(64)` | No | Default: `'pending'`. |
| `observed_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_hf_catalog_repo_observation`: Unique (`namespace_run_id`, `repo_key`).

[Back to table inventory](#table-inventory)


<a id="jobs"></a>

## Job listings and official career-site collection

`job_listings` represents advertised positions, not people currently doing
those jobs. A listing belongs to a known brand or an unresolved organization,
and evidence can come from posts, web pages, or media observations. Source
identity, application route, salary, workplace, eligibility, and observation
dates are separate fields. A listing’s first collection date does not establish
when it was originally posted.

The official career-site adapters use `job_source_sync_runs` and
`job_source_states` for bounded runs, leases, counts, and complete-snapshot
tracking. `job_discovery_runs` instead records query/window searches. These are
different collection paths. A failed/incomplete source snapshot is not evidence
that every missing job has closed; closure behavior belongs to the sync logic.

The current [official-source sync](../../core/job_sources/sync.py) saves source
title, description, and raw payload and assigns `source_language='zh-CN'` for
its five registered sources. That is an adapter assignment, not automatic
language detection. The current schema has no saved EN/JA job translations.
Current official-source evidence is updated in place by the sync path, so it
is not an immutable archive of every page revision. See the [source registry](../../core/job_sources/registry.py)
and [official jobs runbook](../deploy/render.md#official-ai-lab-jobs-sync).


<a id="table-job_listings"></a>

### `job_listings` — JobListing

One advertised position/requisition, including its source identity and current saved details.

Model: [JobListing](../../core/models.py#L5523).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `brand_discovery_candidate_id` | `bigint` | Yes | Model: `brand_discovery_candidate`. FK → [brand_discovery_candidates.id](#table-brand_discovery_candidates); Django delete: `PROTECT`. |
| `hiring_organization` | `text` | No | — |
| `source_key` | `varchar(64)` | Yes | Field index. |
| `source_name` | `text` | Yes | — |
| `source_listing_id` | `text` | Yes | — |
| `canonical_url` | `varchar(2048)` | Yes | — |
| `application_url` | `varchar(2048)` | Yes | — |
| `application_route_kind` | `varchar(32)` | No | Default: `'unresolved'`. Choices: `direct_url`, `careers_page`, `email`, `qr`, `direct_message`, `other`, `unresolved`. |
| `application_contact` | `text` | Yes | — |
| `application_resolution_status` | `varchar(32)` | Yes | — |
| `title` | `text` | No | Saved source job title. |
| `description_html` | `text` | Yes | Saved source description HTML. |
| `description_text` | `text` | Yes | Saved source description text. |
| `department` | `text` | Yes | — |
| `team` | `text` | Yes | — |
| `job_function` | `text` | Yes | — |
| `seniority` | `text` | Yes | — |
| `employment_type` | `text` | Yes | — |
| `workplace_type` | `text` | Yes | — |
| `locations_raw` | `text` | Yes | — |
| `locations` | `jsonb` | No | Default: `[]`. |
| `remote_applicant_restrictions` | `text` | Yes | — |
| `salary_text` | `text` | Yes | — |
| `salary_min` | `numeric(18, 2)` | Yes | — |
| `salary_max` | `numeric(18, 2)` | Yes | — |
| `salary_currency` | `varchar(3)` | Yes | — |
| `salary_period` | `varchar(32)` | Yes | — |
| `posted_at` | `timestamp with time zone` | Yes | Source posting time, when supplied. |
| `updated_source_at` | `timestamp with time zone` | Yes | Source-side last update, when supplied. |
| `first_seen_at` | `timestamp with time zone` | No | First observation of this listing. |
| `last_seen_at` | `timestamp with time zone` | No | Latest observation of this listing. |
| `expires_at` | `timestamp with time zone` | Yes | — |
| `closed_at` | `timestamp with time zone` | Yes | — |
| `status` | `varchar(16)` | No | Default: `'unknown'`. Choices: `open`, `closed`, `future`, `unknown`. |
| `consecutive_missing_snapshots` | `smallint` | No | Nonnegative. Default: `0`. Count used by official-source closure handling. |
| `last_complete_source_sync_at` | `timestamp with time zone` | Yes | Last complete career-site snapshot that observed this listing. |
| `campaign_openings` | `integer` | Yes | Nonnegative. |
| `role_openings` | `integer` | Yes | Nonnegative. |
| `skills` | `jsonb` | No | Default: `[]`. |
| `responsibilities` | `jsonb` | No | Default: `[]`. |
| `qualifications` | `jsonb` | No | Default: `[]`. |
| `education_requirements` | `text` | Yes | — |
| `experience_requirements` | `text` | Yes | — |
| `benefits` | `jsonb` | No | Default: `[]`. |
| `eligibility` | `text` | Yes | — |
| `source_language` | `varchar(32)` | Yes | Source language tag; official-source sync currently assigns zh-CN. |
| `organization_ai_relationship` | `text` | Yes | — |
| `role_ai_relationship` | `text` | Yes | — |
| `listing_identity` | `varchar(64)` | No | Unique. Stable listing/requisition deduplication identity. |
| `content_hash` | `varchar(64)` | Yes | — |
| `extraction_version` | `text` | Yes | — |
| `extraction_confidence` | `double precision` | Yes | — |
| `raw_payload` | `jsonb` | Yes | Saved structured source payload; no dedicated translation bundle. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_jobs_brand_status`: (`brand_id`, `status`).
- `idx_jobs_source_status`: (`source_key`, `status`).
- `idx_jobs_status_expiry`: (`status`, `expires_at`).

**Named constraints:**

- `ck_jobs_one_organization`: Check: `(("brand_id" IS NOT NULL AND "brand_discovery_candidate_id" IS NULL) OR ("brand_id" IS NULL AND "brand_discovery_candidate_id" IS NOT NULL))`.
- `ck_jobs_application_route`: Check: `"application_route_kind" IN ('direct_url', 'careers_page', 'email', 'qr', 'direct_message', 'other', 'unresolved')`.
- `ck_jobs_status`: Check: `"status" IN ('open', 'closed', 'future', 'unknown')`.
- `ck_jobs_seen_window`: Check: `"last_seen_at" >= ("first_seen_at")`.
- `ck_jobs_salary_range`: Check: `("salary_min" IS NULL OR "salary_max" IS NULL OR "salary_max" >= ("salary_min"))`.
- `ck_jobs_salary_nonnegative`: Check: `(("salary_min" IS NULL OR "salary_min" >= 0) AND ("salary_max" IS NULL OR "salary_max" >= 0))`.
- `ck_jobs_campaign_openings`: Check: `("campaign_openings" IS NULL OR "campaign_openings" >= 1)`.
- `ck_jobs_role_openings`: Check: `("role_openings" IS NULL OR "role_openings" >= 1)`.
- `ck_jobs_extraction_conf`: Check: `("extraction_confidence" IS NULL OR ("extraction_confidence" >= 0.0 AND "extraction_confidence" <= 1.0))`.

[Back to table inventory](#table-inventory)

<a id="table-job_listing_evidence"></a>

### `job_listing_evidence` — JobListingEvidence

One source observation supporting a job listing.

Model: [JobListingEvidence](../../core/models.py#L5804).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `listing_id` | `bigint` | No | Model: `listing`. FK → [job_listings.id](#table-job_listings); Django delete: `CASCADE`. |
| `source_post_id` | `text` | Yes | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `SET_NULL`. |
| `source_url` | `varchar(2048)` | Yes | — |
| `observed_author_handle` | `varchar(64)` | Yes | — |
| `observed_author_display_name` | `text` | Yes | — |
| `source_relationship` | `varchar(16)` | No | Choices: `official`, `staff`, `third_party`. |
| `evidence_text` | `text` | No | Default: `''`. |
| `linked_urls` | `jsonb` | No | Default: `[]`. |
| `observed_at` | `timestamp with time zone` | No | — |
| `media_url` | `varchar(2048)` | Yes | — |
| `media_hash` | `varchar(64)` | Yes | — |
| `extraction_method` | `varchar(32)` | No | Choices: `structured_text`, `ocr`, `vision`, `manual`. |
| `image_derived_fields` | `jsonb` | No | Default: `[]`. |
| `confidence` | `double precision` | Yes | — |
| `raw_evidence` | `jsonb` | Yes | — |
| `extraction_identity` | `varchar(64)` | No | — |
| `evidence_hash` | `varchar(64)` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_job_evidence_relationship`: Check: `"source_relationship" IN ('official', 'staff', 'third_party')`.
- `ck_job_evidence_method`: Check: `"extraction_method" IN ('structured_text', 'ocr', 'vision', 'manual')`.
- `ck_job_evidence_has_source`: Check: `("source_post_id" IS NOT NULL OR ("source_url" IS NOT NULL AND NOT ("source_url" = '' AND "source_url" IS NOT NULL)) OR ("media_url" IS NOT NULL AND NOT ("media_url" = '' AND "media_url" IS NOT NULL)))`.
- `ck_job_evidence_conf`: Check: `("confidence" IS NULL OR ("confidence" >= 0.0 AND "confidence" <= 1.0))`.
- `uq_job_evidence_hash`: Unique (`listing_id`, `evidence_hash`).

[Back to table inventory](#table-inventory)

<a id="table-job_source_sync_runs"></a>

### `job_source_sync_runs` — JobSourceSyncRun

One attempt to synchronize an official career-site source.

Model: [JobSourceSyncRun](../../core/models.py#L5721).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `source_key` | `varchar(64)` | No | — |
| `status` | `varchar(16)` | No | Default: `'running'`. Choices: `running`, `succeeded`, `partial`, `failed`, `skipped`. |
| `started_at` | `timestamp with time zone` | No | Default: `django.utils.timezone.now()`. |
| `finished_at` | `timestamp with time zone` | Yes | — |
| `snapshot_complete` | `boolean` | No | Default: `False`. |
| `declared_total` | `integer` | Yes | Nonnegative. |
| `observed_total` | `integer` | Yes | Nonnegative. |
| `created_count` | `integer` | No | Nonnegative. Default: `0`. |
| `updated_count` | `integer` | No | Nonnegative. Default: `0`. |
| `unchanged_count` | `integer` | No | Nonnegative. Default: `0`. |
| `reopened_count` | `integer` | No | Nonnegative. Default: `0`. |
| `closed_count` | `integer` | No | Nonnegative. Default: `0`. |
| `error_summary` | `text` | No | Default: `''`. |
| `metadata` | `jsonb` | No | Default: `{}`. |

**Named indexes:**

- `idx_job_sync_source_started`: (`source_key`, `started_at`).

**Named constraints:**

- `ck_job_sync_run_status`: Check: `"status" IN ('running', 'succeeded', 'partial', 'failed', 'skipped')`.

[Back to table inventory](#table-inventory)

<a id="table-job_source_states"></a>

### `job_source_states` — JobSourceState

One career-site source’s active lease and last successful synchronization state.

Model: [JobSourceState](../../core/models.py#L5765).

**Primary key:** `source_key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `source_key` | `varchar(64)` | No | PK. |
| `lease_token` | `varchar(64)` | Yes | — |
| `lease_expires_at` | `timestamp with time zone` | Yes | — |
| `active_run_id` | `bigint` | Yes | Model: `active_run`. FK → [job_source_sync_runs.id](#table-job_source_sync_runs); Django delete: `SET_NULL`. |
| `last_successful_at` | `timestamp with time zone` | Yes | — |
| `last_snapshot_count` | `integer` | Yes | Nonnegative. |
| `last_error` | `text` | No | Default: `''`. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_job_source_lease_complete`: Check: `(("lease_expires_at" IS NULL AND "lease_token" IS NULL) OR ("lease_expires_at" IS NOT NULL AND "lease_token" IS NOT NULL))`.

[Back to table inventory](#table-inventory)

<a id="table-job_discovery_runs"></a>

### `job_discovery_runs` — JobDiscoveryRun

One job-search query/window run, including coverage, cost, and extracted listing count.

Model: [JobDiscoveryRun](../../core/models.py#L5944).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `run_identity` | `varchar(64)` | No | Unique. |
| `run_id` | `text` | No | — |
| `cycle_id` | `text` | Yes | — |
| `query_id` | `bigint` | No | Model: `query`. FK → [search_queries.id](#table-search_queries); Django delete: `PROTECT`. |
| `query_text` | `text` | No | — |
| `query_hash` | `varchar(64)` | No | — |
| `query_pack_version` | `text` | No | — |
| `provider_boundary` | `text` | No | — |
| `tool_boundary` | `text` | Yes | — |
| `language` | `varchar(16)` | No | — |
| `query_family` | `varchar(32)` | No | — |
| `window_start` | `timestamp with time zone` | No | — |
| `window_end` | `timestamp with time zone` | No | — |
| `input_cursor` | `text` | Yes | — |
| `output_cursor` | `text` | Yes | — |
| `reviewed_post_count` | `integer` | No | Nonnegative. Default: `0`. |
| `accepted_post_count` | `integer` | No | Nonnegative. Default: `0`. |
| `excluded_count` | `integer` | No | Nonnegative. Default: `0`. |
| `exclusion_reasons` | `jsonb` | No | Default: `{}`. |
| `discovered_organization_count` | `integer` | No | Nonnegative. Default: `0`. |
| `provider_capabilities` | `jsonb` | No | Default: `{}`. |
| `provider_call_count` | `integer` | No | Nonnegative. Default: `0`. |
| `provider_credit_count` | `integer` | No | Nonnegative. Default: `0`. |
| `telemetry` | `jsonb` | No | Default: `{}`. |
| `limitations` | `jsonb` | No | Default: `[]`. |
| `status` | `varchar(16)` | No | Default: `'planned'`. Choices: `planned`, `running`, `completed`, `failed`, `truncated`, `blocked`. |
| `started_at` | `timestamp with time zone` | Yes | — |
| `completed_at` | `timestamp with time zone` | Yes | — |
| `completion_reason` | `text` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |
| `extracted_listing_count` | `integer` | No | Nonnegative. Default: `0`. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_job_runs_status`: Check: `"status" IN ('planned', 'running', 'completed', 'failed', 'truncated', 'blocked')`.
- `ck_job_runs_window`: Check: `"window_end" > ("window_start")`.

[Back to table inventory](#table-inventory)


<a id="events"></a>

## Events and opportunities

An event is an occurrence people can attend. An opportunity is an offer
with an action and a benefit, such as a program or giveaway; it may reference
an event but is not interchangeable with it. Neither table is a generic
identity for every news story or headline topic.

Keep the source’s schedule/availability wording, timezone, precision, and
status alongside normalized values. `event_evidence` preserves multiple source
observations about one occurrence. Opportunities currently store their source
post/URL and raw payload on the main row; there is no separate
`opportunity_evidence` table. Organization ownership, source presence, review
state, nonnegative benefit values, and comparable date order are constrained
where shown. See [rare-type readers and extraction](rare-types.md).


<a id="table-events"></a>

### `events` — Event

One attendance-bearing occurrence, such as a conference or meetup.

Model: [Event](../../core/models.py#L5989).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `brand_discovery_candidate_id` | `bigint` | Yes | Model: `brand_discovery_candidate`. FK → [brand_discovery_candidates.id](#table-brand_discovery_candidates); Django delete: `PROTECT`. |
| `source_post_id` | `text` | Yes | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `PROTECT`. |
| `source_url` | `varchar(2048)` | Yes | — |
| `canonical_url` | `varchar(2048)` | Yes | — |
| `external_event_source` | `text` | Yes | — |
| `external_event_id` | `text` | Yes | — |
| `normalized_title` | `text` | Yes | — |
| `title` | `text` | No | — |
| `organizer_name` | `text` | No | — |
| `organizer_handle` | `varchar(64)` | Yes | — |
| `attendance_mode` | `varchar(16)` | No | Default: `'unknown'`. Choices: `in_person`, `online_live`, `hybrid`, `unknown`. |
| `physical_location` | `text` | Yes | — |
| `virtual_location` | `text` | Yes | — |
| `attendance_url` | `varchar(2048)` | Yes | — |
| `start_value` | `varchar(64)` | Yes | — |
| `start_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `datetime`, `day`, `month`, `year`, `unknown`. |
| `end_value` | `varchar(64)` | Yes | — |
| `end_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `datetime`, `day`, `month`, `year`, `unknown`. |
| `source_timezone` | `varchar(64)` | Yes | — |
| `source_schedule_text` | `text` | Yes | — |
| `source_status` | `varchar(16)` | No | Default: `'unknown'`. Choices: `scheduled`, `live`, `completed`, `cancelled`, `postponed`, `unknown`. |
| `first_seen_at` | `timestamp with time zone` | No | — |
| `last_seen_at` | `timestamp with time zone` | No | — |
| `event_identity` | `varchar(64)` | No | Unique. |
| `content_hash` | `varchar(64)` | Yes | — |
| `extraction_version` | `text` | Yes | — |
| `extraction_confidence` | `double precision` | Yes | — |
| `review_status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `confirmed`, `rejected`, `needs_review`. |
| `raw_payload` | `jsonb` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_events_one_organization`: Check: `(("brand_id" IS NOT NULL AND "brand_discovery_candidate_id" IS NULL) OR ("brand_id" IS NULL AND "brand_discovery_candidate_id" IS NOT NULL))`.
- `ck_events_attendance_mode`: Check: `"attendance_mode" IN ('in_person', 'online_live', 'hybrid', 'unknown')`.
- `ck_events_source_status`: Check: `"source_status" IN ('scheduled', 'live', 'completed', 'cancelled', 'postponed', 'unknown')`.
- `ck_events_review_status`: Check: `"review_status" IN ('pending', 'confirmed', 'rejected', 'needs_review')`.
- `ck_events_has_source`: Check: `("source_post_id" IS NOT NULL OR ("source_url" IS NOT NULL AND NOT ("source_url" = '' AND "source_url" IS NOT NULL)))`.
- `ck_events_seen_window`: Check: `"last_seen_at" >= ("first_seen_at")`.
- `ck_events_start_precision`: Check: `(("start_precision" = 'unknown' AND "start_value" IS NULL) OR ("start_precision" = 'day' AND "start_value"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') OR ("start_precision" = 'month' AND "start_value"::text ~ '^[0-9]{4}-[0-9]{2}$') OR ("start_precision" = 'year' AND "start_value"::text ~ '^[0-9]{4}$') OR ("start_precision" = 'datetime' AND "start_value"::text ~  E'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$'))`.
- `ck_events_end_precision`: Check: `(("end_precision" = 'unknown' AND "end_value" IS NULL) OR ("end_precision" = 'day' AND "end_value"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') OR ("end_precision" = 'month' AND "end_value"::text ~ '^[0-9]{4}-[0-9]{2}$') OR ("end_precision" = 'year' AND "end_value"::text ~ '^[0-9]{4}$') OR ("end_precision" = 'datetime' AND "end_value"::text ~  E'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$'))`.
- `ck_events_extraction_conf`: Check: `("extraction_confidence" IS NULL OR ("extraction_confidence" >= 0.0 AND "extraction_confidence" <= 1.0))`.

[Back to table inventory](#table-inventory)

<a id="table-event_evidence"></a>

### `event_evidence` — EventEvidence

One source observation supporting an event occurrence.

Model: [EventEvidence](../../core/models.py#L6155).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `event_id` | `bigint` | No | Model: `event`. FK → [events.id](#table-events); Django delete: `CASCADE`. |
| `source_post_id` | `text` | Yes | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `PROTECT`. |
| `source_url` | `varchar(2048)` | Yes | — |
| `observed_title` | `text` | No | — |
| `observed_organizer_name` | `text` | No | Default: `''`. |
| `observed_start_value` | `varchar(64)` | Yes | — |
| `observed_start_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `datetime`, `day`, `month`, `year`, `unknown`. |
| `observed_end_value` | `varchar(64)` | Yes | — |
| `observed_end_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `datetime`, `day`, `month`, `year`, `unknown`. |
| `observed_at` | `timestamp with time zone` | No | — |
| `extraction_version` | `text` | Yes | — |
| `extraction_confidence` | `double precision` | Yes | — |
| `raw_payload` | `jsonb` | Yes | — |
| `evidence_hash` | `varchar(64)` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_event_evidence_observation`: Unique (`event_id`, `source_post_id`, `evidence_hash`).
- `ck_event_evidence_has_source`: Check: `("source_post_id" IS NOT NULL OR ("source_url" IS NOT NULL AND NOT ("source_url" = '' AND "source_url" IS NOT NULL)))`.
- `ck_event_evidence_start_precision`: Check: `(("observed_start_precision" = 'unknown' AND "observed_start_value" IS NULL) OR ("observed_start_precision" = 'day' AND "observed_start_value"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') OR ("observed_start_precision" = 'month' AND "observed_start_value"::text ~ '^[0-9]{4}-[0-9]{2}$') OR ("observed_start_precision" = 'year' AND "observed_start_value"::text ~ '^[0-9]{4}$') OR ("observed_start_precision" = 'datetime' AND "observed_start_value"::text ~  E'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$'))`.
- `ck_event_evidence_end_precision`: Check: `(("observed_end_precision" = 'unknown' AND "observed_end_value" IS NULL) OR ("observed_end_precision" = 'day' AND "observed_end_value"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') OR ("observed_end_precision" = 'month' AND "observed_end_value"::text ~ '^[0-9]{4}-[0-9]{2}$') OR ("observed_end_precision" = 'year' AND "observed_end_value"::text ~ '^[0-9]{4}$') OR ("observed_end_precision" = 'datetime' AND "observed_end_value"::text ~  E'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$'))`.

[Back to table inventory](#table-inventory)

<a id="table-opportunities"></a>

### `opportunities` — Opportunity

One bounded offer in which an action can provide a benefit, optionally linked to an event.

Model: [Opportunity](../../core/models.py#L6223).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `brand_discovery_candidate_id` | `bigint` | Yes | Model: `brand_discovery_candidate`. FK → [brand_discovery_candidates.id](#table-brand_discovery_candidates); Django delete: `PROTECT`. |
| `related_event_id` | `bigint` | Yes | Model: `related_event`. FK → [events.id](#table-events); Django delete: `SET_NULL`. |
| `source_post_id` | `text` | Yes | Model: `source_post`. FK → [posts.tweet_id](#table-posts); Django delete: `SET_NULL`. |
| `source_url` | `varchar(2048)` | Yes | — |
| `sponsor_name` | `text` | No | — |
| `sponsor_handle` | `varchar(64)` | Yes | — |
| `opportunity_type` | `varchar(32)` | No | Choices: `giveaway`, `discount`, `free_credits`, `beta_access`, `grant`, `bounty`, `contest`, `referral`, `collaboration`, `other`. |
| `action_type` | `text` | No | — |
| `action_url` | `varchar(2048)` | Yes | — |
| `benefit_type` | `text` | No | — |
| `benefit_value` | `numeric(18, 2)` | Yes | — |
| `benefit_currency` | `varchar(8)` | Yes | — |
| `benefit_text` | `text` | Yes | — |
| `eligibility` | `text` | Yes | — |
| `geographic_restrictions` | `text` | Yes | — |
| `open_value` | `varchar(64)` | Yes | — |
| `open_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `datetime`, `day`, `month`, `year`, `unknown`. |
| `close_value` | `varchar(64)` | Yes | — |
| `close_precision` | `varchar(16)` | No | Default: `'unknown'`. Choices: `datetime`, `day`, `month`, `year`, `unknown`. |
| `source_timezone` | `varchar(64)` | Yes | — |
| `source_availability_text` | `text` | Yes | — |
| `source_status` | `varchar(16)` | No | Default: `'unknown'`. Choices: `upcoming`, `open`, `closed`, `cancelled`, `unknown`. |
| `first_seen_at` | `timestamp with time zone` | No | — |
| `last_seen_at` | `timestamp with time zone` | No | — |
| `opportunity_identity` | `varchar(64)` | No | Unique. |
| `content_hash` | `varchar(64)` | Yes | — |
| `extraction_version` | `text` | Yes | — |
| `extraction_confidence` | `double precision` | Yes | — |
| `review_status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `confirmed`, `rejected`, `needs_review`. |
| `raw_payload` | `jsonb` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_opportunities_one_organization`: Check: `(("brand_id" IS NOT NULL AND "brand_discovery_candidate_id" IS NULL) OR ("brand_id" IS NULL AND "brand_discovery_candidate_id" IS NOT NULL))`.
- `ck_opportunities_type`: Check: `"opportunity_type" IN ('giveaway', 'discount', 'free_credits', 'beta_access', 'grant', 'bounty', 'contest', 'referral', 'collaboration', 'other')`.
- `ck_opportunities_source_status`: Check: `"source_status" IN ('upcoming', 'open', 'closed', 'cancelled', 'unknown')`.
- `ck_opportunities_review_status`: Check: `"review_status" IN ('pending', 'confirmed', 'rejected', 'needs_review')`.
- `ck_opportunities_has_source`: Check: `("source_post_id" IS NOT NULL OR ("source_url" IS NOT NULL AND NOT ("source_url" = '' AND "source_url" IS NOT NULL)))`.
- `ck_opportunities_seen_window`: Check: `"last_seen_at" >= ("first_seen_at")`.
- `ck_opportunities_open_precision`: Check: `(("open_precision" = 'unknown' AND "open_value" IS NULL) OR ("open_precision" = 'day' AND "open_value"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') OR ("open_precision" = 'month' AND "open_value"::text ~ '^[0-9]{4}-[0-9]{2}$') OR ("open_precision" = 'year' AND "open_value"::text ~ '^[0-9]{4}$') OR ("open_precision" = 'datetime' AND "open_value"::text ~  E'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$'))`.
- `ck_opportunities_close_precision`: Check: `(("close_precision" = 'unknown' AND "close_value" IS NULL) OR ("close_precision" = 'day' AND "close_value"::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') OR ("close_precision" = 'month' AND "close_value"::text ~ '^[0-9]{4}-[0-9]{2}$') OR ("close_precision" = 'year' AND "close_value"::text ~ '^[0-9]{4}$') OR ("close_precision" = 'datetime' AND "close_value"::text ~  E'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$'))`.
- `ck_opportunities_extraction_conf`: Check: `("extraction_confidence" IS NULL OR ("extraction_confidence" >= 0.0 AND "extraction_confidence" <= 1.0))`.

[Back to table inventory](#table-inventory)


<a id="translation"></a>

## Post translation and commentary

Literal translation preserves what a post says; commentary interprets it.
Their artifacts and localized texts are stored separately. An artifact records
which source/version/provider work produced a set of texts; the text table holds
one locale per artifact. Translation chunks preserve validated partial work for
long posts. `post_enrichment_states` holds progress, retries, and diagnostics,
not a second copy of provider payloads.

Commentary demand rows combine repeated requests, claim work for one worker,
and track retry timing. Daily budgets account for requests/tokens, and throttle
buckets limit cross-process demand without storing user IDs or IP addresses.
These tables are explicitly linked to posts and do not currently provide
translations for people, affiliations, or job listings. Details: [literal
translation](translator-output.md) and [post commentary](commenter.md).


<a id="table-post_enrichment_states"></a>

### `post_enrichment_states` — PostEnrichmentState

One post’s replayable translation/classification progress and diagnostics.

Model: [PostEnrichmentState](../../core/models.py#L1527).

**Primary key:** `post_id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `post_id` | `text` | No | Model: `post`. PK. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `translation_status` | `varchar(16)` | No | Default: `PostEnrichmentState.Status.PENDING`. Choices: `pending`, `succeeded`, `failed`. |
| `translation_attempts` | `smallint` | No | Nonnegative. Default: `0`. |
| `translation_first_attempt_at` | `timestamp with time zone` | Yes | — |
| `translation_last_attempt_at` | `timestamp with time zone` | Yes | — |
| `translation_next_attempt_at` | `timestamp with time zone` | Yes | — |
| `translation_error_code` | `varchar(128)` | No | Default: `''`. |
| `translation_diagnostics` | `jsonb` | No | Default: `{}`. |
| `classification_status` | `varchar(16)` | No | Default: `PostEnrichmentState.Status.PENDING`. Choices: `pending`, `succeeded`, `failed`. |
| `classification_attempts` | `smallint` | No | Nonnegative. Default: `0`. |
| `classification_first_attempt_at` | `timestamp with time zone` | Yes | — |
| `classification_last_attempt_at` | `timestamp with time zone` | Yes | — |
| `classification_next_attempt_at` | `timestamp with time zone` | Yes | — |
| `classification_error_code` | `varchar(128)` | No | Default: `''`. |
| `claim_owner` | `varchar(128)` | No | Default: `''`. |
| `claim_run_id` | `varchar(128)` | No | Default: `''`. |
| `claimed_at` | `timestamp with time zone` | Yes | — |
| `claim_expires_at` | `timestamp with time zone` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_pes_translation_due`: (`translation_status`, `translation_next_attempt_at`).
- `idx_pes_classify_due`: (`classification_status`, `classification_next_attempt_at`).
- `idx_pes_claim_expiry`: (`claim_expires_at`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-post_translation_artifacts"></a>

### `post_translation_artifacts` — PostTranslationArtifact

One versioned literal-translation attempt/state for a post body.

Model: [PostTranslationArtifact](../../core/models.py#L1584).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `post_id` | `text` | No | Model: `post`. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `source_content_fingerprint` | `varchar(64)` | No | — |
| `source_language` | `varchar(16)` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `model` | `varchar(128)` | No | — |
| `provider_role` | `varchar(64)` | No | — |
| `state` | `varchar(16)` | No | Choices: `generating`, `succeeded`, `failed`. |
| `attempts` | `smallint` | No | Nonnegative. Default: `1`. |
| `input_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `output_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `latency_ms` | `integer` | Yes | Nonnegative. |
| `error_code` | `varchar(128)` | No | Default: `''`. |
| `is_current` | `boolean` | No | Default: `False`. |
| `started_at` | `timestamp with time zone` | No | — |
| `completed_at` | `timestamp with time zone` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_post_translation_post`: (`post_id`, `created_at DESC`).
- `idx_post_translation_state`: (`state`, `updated_at`).

**Named constraints:**

- `uq_post_translation_identity`: Unique (`post_id`, `source_content_fingerprint`, `source_language`, `prompt_version`, `model`, `provider_role`).
- `uq_post_translation_current`: Unique (`post_id`) where `"is_current"`.
- `ck_post_translation_state`: Check: `(("completed_at" IS NULL AND NOT "is_current" AND "state" = 'generating') OR ("completed_at" IS NOT NULL AND "error_code" = '' AND "state" = 'succeeded') OR ("completed_at" IS NOT NULL AND "error_code" > '' AND NOT "is_current" AND "state" = 'failed'))`.

[Back to table inventory](#table-inventory)

<a id="table-post_translation_texts"></a>

### `post_translation_texts` — PostTranslationText

One locale’s validated literal text within a translation artifact.

Model: [PostTranslationText](../../core/models.py#L1665).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `artifact_id` | `bigint` | No | Model: `artifact`. FK → [post_translation_artifacts.id](#table-post_translation_artifacts); Django delete: `CASCADE`. |
| `locale` | `varchar(8)` | No | — |
| `text` | `text` | No | — |
| `is_source` | `boolean` | No | Default: `False`. True for text representing the source locale rather than a translation. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_post_translation_locale`: Unique (`artifact_id`, `locale`).
- `ck_post_translation_locale`: Check: `"locale" IN ('en', 'zh-cn', 'ja')`.
- `ck_post_translation_text`: Check: `NOT ("text" = '')`.

[Back to table inventory](#table-inventory)

<a id="table-post_translation_chunks"></a>

### `post_translation_chunks` — PostTranslationChunk

One validated locale chunk retained for resuming a long post translation.

Model: [PostTranslationChunk](../../core/models.py#L1692).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `post_id` | `text` | No | Model: `post`. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `source_content_fingerprint` | `varchar(64)` | No | — |
| `source_chunk_fingerprint` | `varchar(64)` | No | — |
| `source_language` | `varchar(16)` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `model` | `varchar(128)` | No | — |
| `target_language` | `varchar(8)` | No | — |
| `chunk_index` | `smallint` | No | Nonnegative. |
| `translated_text` | `text` | No | — |
| `input_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `output_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_post_translation_chunk_identity`: Unique (`post_id`, `source_content_fingerprint`, `source_language`, `prompt_version`, `model`, `target_language`, `chunk_index`).
- `ck_post_translation_chunk_target`: Check: `"target_language" IN ('en', 'zh-Hans', 'ja')`.
- `ck_post_translation_chunk_text`: Check: `NOT ("translated_text" = '')`.

[Back to table inventory](#table-inventory)

<a id="table-post_synthesis_artifacts"></a>

### `post_synthesis_artifacts` — PostSynthesisArtifact

One versioned commentary artifact for a post and its context.

Model: [PostSynthesisArtifact](../../core/models.py#L1736).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `post_id` | `text` | No | Model: `post`. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `input_context_fingerprint` | `varchar(64)` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `model` | `varchar(128)` | No | — |
| `provider_role` | `varchar(64)` | No | — |
| `output_schema_version` | `smallint` | No | Nonnegative. Default: `1`. |
| `state` | `varchar(16)` | No | Choices: `generating`, `succeeded`, `failed`. |
| `attempts` | `smallint` | No | Nonnegative. Default: `1`. |
| `input_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `output_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `latency_ms` | `integer` | Yes | Nonnegative. |
| `error_code` | `varchar(128)` | No | Default: `''`. |
| `evidence_provenance` | `jsonb` | No | Default: `[]`. |
| `review_state` | `varchar(32)` | No | Default: `''`. |
| `is_current` | `boolean` | No | Default: `False`. |
| `started_at` | `timestamp with time zone` | No | — |
| `completed_at` | `timestamp with time zone` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_post_synthesis_post`: (`post_id`, `created_at DESC`).
- `idx_post_synthesis_state`: (`state`, `updated_at`).

**Named constraints:**

- `uq_post_synthesis_identity`: Unique (`post_id`, `input_context_fingerprint`, `prompt_version`, `model`, `provider_role`, `output_schema_version`).
- `uq_post_synthesis_current`: Unique (`post_id`) where `"is_current"`.
- `ck_post_synthesis_state`: Check: `(("completed_at" IS NULL AND NOT "is_current" AND "state" = 'generating') OR ("completed_at" IS NOT NULL AND "error_code" = '' AND "state" = 'succeeded') OR ("completed_at" IS NOT NULL AND "error_code" > '' AND NOT "is_current" AND "state" = 'failed'))`.

[Back to table inventory](#table-inventory)

<a id="table-post_synthesis_texts"></a>

### `post_synthesis_texts` — PostSynthesisText

One locale’s commentary text within a synthesis artifact.

Model: [PostSynthesisText](../../core/models.py#L1819).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `artifact_id` | `bigint` | No | Model: `artifact`. FK → [post_synthesis_artifacts.id](#table-post_synthesis_artifacts); Django delete: `CASCADE`. |
| `locale` | `varchar(8)` | No | — |
| `text` | `text` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_post_synthesis_locale`: Unique (`artifact_id`, `locale`).
- `ck_post_synthesis_locale`: Check: `"locale" IN ('en', 'zh-cn', 'ja')`.
- `ck_post_synthesis_text`: Check: `NOT ("text" = '')`.

[Back to table inventory](#table-inventory)

<a id="table-post_synthesis_demands"></a>

### `post_synthesis_demands` — PostSynthesisDemand

One coalesced request for post commentary, including its worker claim and retry state.

Model: [PostSynthesisDemand](../../core/models.py#L1845).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `post_id` | `text` | No | Model: `post`. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `input_context_fingerprint` | `varchar(64)` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `model` | `varchar(128)` | No | — |
| `output_schema_version` | `smallint` | No | Nonnegative. Default: `1`. |
| `reason` | `varchar(16)` | No | Choices: `prewarm`, `lookahead`, `visible`, `expanded`, `operator`. |
| `priority` | `smallint` | No | Nonnegative. |
| `request_count` | `integer` | No | Nonnegative. Default: `1`. |
| `first_requested_at` | `timestamp with time zone` | No | — |
| `last_requested_at` | `timestamp with time zone` | No | — |
| `not_before` | `timestamp with time zone` | No | — |
| `expires_at` | `timestamp with time zone` | Yes | — |
| `state` | `varchar(16)` | No | Default: `PostSynthesisDemand.State.PENDING`. Choices: `pending`, `processing`, `succeeded`, `failed`, `cancelled`. |
| `lease_owner` | `varchar(128)` | No | Default: `''`. |
| `lease_expires_at` | `timestamp with time zone` | Yes | — |
| `lease_fence` | `integer` | No | Nonnegative. Default: `0`. |
| `attempts` | `smallint` | No | Nonnegative. Default: `0`. |
| `last_error` | `varchar(128)` | No | Default: `''`. |
| `artifact_id` | `bigint` | Yes | Model: `artifact`. FK → [post_synthesis_artifacts.id](#table-post_synthesis_artifacts); Django delete: `SET_NULL`. |
| `budget_id` | `bigint` | Yes | Model: `budget`. FK → [post_synthesis_daily_budgets.id](#table-post_synthesis_daily_budgets); Django delete: `PROTECT`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_post_synth_demand_due`: (`state`, `not_before`, `priority DESC`).
- `idx_post_synth_lease_expiry`: (`lease_expires_at`).

**Named constraints:**

- `uq_post_synthesis_demand_identity`: Unique (`post_id`, `input_context_fingerprint`, `prompt_version`, `model`, `output_schema_version`).
- `ck_post_synth_demand_priority`: Check: `("priority" >= 1 AND "priority" <= 100)`.
- `ck_post_synth_request_order`: Check: `"last_requested_at" >= ("first_requested_at")`.
- `ck_post_synth_demand_lease`: Check: `(("lease_expires_at" IS NOT NULL AND "lease_fence" > 0 AND "lease_owner" > '' AND "state" = 'processing') OR (NOT ("state" = 'processing') AND "lease_expires_at" IS NULL AND "lease_owner" = ''))`.

[Back to table inventory](#table-inventory)

<a id="table-post_synthesis_daily_budgets"></a>

### `post_synthesis_daily_budgets` — PostSynthesisDailyBudget

One day’s commentary request/token budget accounting.

Model: [PostSynthesisDailyBudget](../../core/models.py#L1956).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `usage_date` | `date` | No | — |
| `control_revision` | `varchar(64)` | No | — |
| `provider` | `varchar(32)` | No | — |
| `model` | `varchar(128)` | No | — |
| `reserved_requests` | `integer` | No | Nonnegative. Default: `0`. |
| `reserved_input_tokens` | `bigint` | No | Nonnegative. Default: `0`. |
| `reserved_output_tokens` | `bigint` | No | Nonnegative. Default: `0`. |
| `observed_input_tokens` | `bigint` | No | Nonnegative. Default: `0`. |
| `observed_output_tokens` | `bigint` | No | Nonnegative. Default: `0`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_post_synth_daily_budget`: Unique (`usage_date`, `control_revision`, `provider`, `model`).

[Back to table inventory](#table-inventory)

<a id="table-post_synthesis_rate_limit_buckets"></a>

### `post_synthesis_rate_limit_buckets` — PostSynthesisRateLimitBucket

One request-throttle bucket keyed without storing a user ID or IP address.

Model: [PostSynthesisRateLimitBucket](../../core/models.py#L1981).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `bucket_start` | `timestamp with time zone` | No | — |
| `scope_hash` | `varchar(64)` | No | — |
| `count` | `integer` | No | Nonnegative. Default: `0`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_psynth_rate_time`: (`bucket_start`).

**Named constraints:**

- `uq_post_synth_rate_bucket`: Unique (`bucket_start`, `scope_hash`).

[Back to table inventory](#table-inventory)


<a id="headlines"></a>

## Trend headlines and publication

Headline content, published selection, work ownership, and provider attempts
are different records. `trend_narrative_runs` fixes a shared facts cutoff;
`brand_trend_narratives` and their locale text rows hold prepared brand outcomes.
`trend_narrative_visible_runs` points readers at the visible run for a window.
Work slots and demands coordinate preparation; provider-call rows record bounded
attempts and costs. Existence of a prepared row alone does not prove it is
currently visible.

`trend_narratives` and its subjects also represent the shared-window publication
path. Version/identity columns and constraints preserve the relationship between
evidence cutoff, generated text, and publication. JSON evidence and measurement
fields are not free-form replacements for their versioned contract. See [Trend
narrative contract](headline-trend-narratives.md) for exact serving and generation
behavior. The SQL view `trend_narrative_versions` is listed separately below.


<a id="table-trend_narratives"></a>

### `trend_narratives` — TrendNarrative

One durable attempt/version of a shared time-window headline.

Model: [TrendNarrative](../../core/models.py#L3480).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `source_cycle_id` | `varchar(128)` | No | — |
| `window_days` | `smallint` | No | Nonnegative. |
| `status` | `varchar(16)` | No | Choices: `checked`, `suppressed`, `generating`, `abandoned`, `failed`, `published`, `superseded`. |
| `semantic_fingerprint` | `varchar(64)` | No | Default: `''`. |
| `publication_epoch` | `integer` | No | Nonnegative. Default: `1`. |
| `is_current` | `boolean` | No | Default: `False`. |
| `facts_as_of` | `timestamp with time zone` | No | — |
| `generation_facts` | `jsonb` | Yes | — |
| `output_schema_version` | `smallint` | No | Nonnegative. Default: `1`. |
| `observations_en` | `jsonb` | No | Default: `[]`. |
| `observations_zh_cn` | `jsonb` | No | Default: `[]`. |
| `selected_candidate_ids` | `jsonb` | No | Default: `[]`. |
| `claims` | `jsonb` | No | Default: `[]`. |
| `latest_checked_source_cycle_id` | `varchar(128)` | No | Default: `''`. |
| `latest_checked_as_of` | `timestamp with time zone` | Yes | — |
| `latest_checked_at` | `timestamp with time zone` | Yes | — |
| `latest_checked_facts` | `jsonb` | Yes | — |
| `narrative_type` | `varchar(32)` | No | Default: `''`. |
| `coverage_state` | `varchar(32)` | No | Default: `''`. |
| `primary_brand_id` | `varchar(64)` | Yes | Model: `primary_brand`. FK → [brands.nickname](#table-brands); Django delete: `SET_NULL`. Collation: `case_insensitive`. |
| `secondary_brand_id` | `varchar(64)` | Yes | Model: `secondary_brand`. FK → [brands.nickname](#table-brands); Django delete: `SET_NULL`. Collation: `case_insensitive`. |
| `primary_brand_key` | `varchar(64)` | No | Default: `''`. |
| `primary_brand_name_en` | `text` | No | Default: `''`. |
| `primary_brand_name_zh_hans` | `text` | No | Default: `''`. |
| `secondary_brand_key` | `varchar(64)` | No | Default: `''`. |
| `secondary_brand_name_en` | `text` | No | Default: `''`. |
| `secondary_brand_name_zh_hans` | `text` | No | Default: `''`. |
| `body_en` | `text` | No | Default: `''`. |
| `body_zh_hans` | `text` | No | Default: `''`. |
| `body_zh_cn` | `text` | Yes | — |
| `output_hash` | `varchar(64)` | No | Default: `''`. |
| `prompt_version` | `varchar(64)` | No | Default: `''`. |
| `provider` | `varchar(32)` | No | Default: `''`. |
| `provider_host` | `varchar(255)` | No | Default: `''`. |
| `model_name` | `varchar(128)` | No | Default: `''`. |
| `llm_model_name` | `varchar(128)` | Yes | — |
| `call_slot_consumed` | `boolean` | No | Default: `False`. |
| `claim_owner` | `varchar(128)` | No | Default: `''`. |
| `claim_fence` | `integer` | No | Nonnegative. Default: `0`. |
| `claimed_at` | `timestamp with time zone` | Yes | — |
| `claim_expires_at` | `timestamp with time zone` | Yes | — |
| `transport_started_at` | `timestamp with time zone` | Yes | — |
| `transport_completed_at` | `timestamp with time zone` | Yes | — |
| `generated_at` | `timestamp with time zone` | Yes | — |
| `published_at` | `timestamp with time zone` | Yes | — |
| `next_attempt_at` | `timestamp with time zone` | Yes | — |
| `consecutive_failures` | `integer` | No | Nonnegative. Default: `0`. |
| `error_code` | `varchar(64)` | No | Default: `''`. |
| `input_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `output_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `latency_ms` | `integer` | Yes | Nonnegative. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_tnv_window_fingerprint`: (`window_days`, `semantic_fingerprint`).
- `idx_tnv_window_facts`: (`window_days`, `facts_as_of`).
- `idx_tnv_status_retry`: (`status`, `next_attempt_at`).
- `idx_tnv_window_created`: (`window_days`, `created_at DESC`).

**Named constraints:**

- `uq_tnv_source_window`: Unique (`source_cycle_id`, `window_days`).
- `uq_tnv_current_window`: Unique (`window_days`) where `"is_current"`.
- `ck_tnv_window`: Check: `"window_days" IN (1, 7, 30, 365)`.
- `ck_tnv_status`: Check: `"status" IN ('checked', 'suppressed', 'generating', 'abandoned', 'failed', 'published', 'superseded')`.
- `ck_tnv_current_published`: Check: `(NOT "is_current" OR "status" = 'published')`.
- `ck_tnv_slot_status`: Check: `((NOT "call_slot_consumed" AND "status" IN ('checked', 'suppressed')) OR ("call_slot_consumed" AND "status" IN ('generating', 'abandoned', 'failed', 'published', 'superseded')))`.
- `ck_tnv_claim_shape`: Check: `((NOT "call_slot_consumed" AND "claim_expires_at" IS NULL AND "claim_fence" = 0 AND "claim_owner" = '' AND "claimed_at" IS NULL) OR ("call_slot_consumed" AND "claim_expires_at" IS NOT NULL AND "claim_fence" > 0 AND "claim_owner" > '' AND "claimed_at" IS NOT NULL))`.
- `ck_tnv_claim_order`: Check: `("claimed_at" IS NULL OR "claim_expires_at" > ("claimed_at"))`.
- `ck_tnv_terminal_error`: Check: `(NOT ("status" IN ('failed', 'abandoned')) OR "error_code" > '')`.
- `ck_tnv_output_shape`: Check: `(("body_en" > '' AND "body_zh_hans" > '' AND "generated_at" IS NOT NULL AND "output_hash" > '' AND "primary_brand_key" > '' AND "primary_brand_name_en" > '' AND "primary_brand_name_zh_hans" > '' AND "published_at" IS NOT NULL AND "status" IN ('published', 'superseded')) OR ("body_en" = '' AND "body_zh_hans" = '' AND "generated_at" IS NULL AND "output_hash" = '' AND "published_at" IS NULL AND "status" IN ('checked', 'suppressed', 'generating', 'abandoned', 'failed')))`.
- `ck_tnv_transport_start`: Check: `("transport_started_at" IS NULL OR ("call_slot_consumed" AND "transport_started_at" >= ("claimed_at")))`.
- `ck_tnv_transport_finish`: Check: `("transport_completed_at" IS NULL OR ("transport_completed_at" >= ("transport_started_at") AND "transport_started_at" IS NOT NULL))`.
- `ck_tnv_generated_order`: Check: `("generated_at" IS NULL OR ("generated_at" >= ("transport_completed_at") AND "transport_completed_at" IS NOT NULL))`.
- `ck_tnv_published_order`: Check: `("published_at" IS NULL OR "published_at" >= ("generated_at"))`.
- `ck_tnv_check_shape`: Check: `(("latest_checked_as_of" IS NULL AND "latest_checked_at" IS NULL AND "latest_checked_facts" IS NULL AND "latest_checked_source_cycle_id" = '') OR ("latest_checked_as_of" IS NOT NULL AND "latest_checked_at" IS NOT NULL AND "latest_checked_facts" IS NOT NULL AND "latest_checked_source_cycle_id" > ''))`.

[Back to table inventory](#table-inventory)

<a id="table-trend_narrative_subjects"></a>

### `trend_narrative_subjects` — TrendNarrativeSubject

One reported subject attached to a headline publication.

Model: [TrendNarrativeSubject](../../core/models.py#L4338).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `trend_narrative_id` | `bigint` | No | Model: `trend_narrative`. FK → [trend_narratives.id](#table-trend_narratives); Django delete: `CASCADE`. |
| `position` | `smallint` | No | Nonnegative. Choices: `0`, `1`. |
| `support_type` | `varchar(32)` | No | Choices: `measured_candidate`, `evidence_only`. |
| `entity_type` | `varchar(16)` | No | Choices: `company`, `brand`, `product`, `model`, `organization`. |
| `identity_type` | `varchar(16)` | No | Choices: `brand`, `product`, `unresolved`. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `SET_NULL`. Collation: `case_insensitive`. |
| `product_id` | `bigint` | Yes | Model: `product`. FK → [products.id](#table-products); Django delete: `SET_NULL`. |
| `observed_name` | `text` | No | Default: `''`. |
| `canonical_key_snapshot` | `text` | No | Default: `''`. |
| `name_en_snapshot` | `text` | No | Default: `''`. |
| `name_zh_cn_snapshot` | `text` | No | Default: `''`. |
| `candidate_id` | `varchar(192)` | No | Default: `''`. |
| `evidence_ids` | `jsonb` | No | Default: `[]`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_tns_narrative_position`: Unique (`trend_narrative_id`, `position`).
- `ck_tns_position`: Check: `"position" IN (0, 1)`.
- `ck_tns_entity_type`: Check: `"entity_type" IN ('company', 'brand', 'product', 'model', 'organization')`.
- `ck_tns_identity_shape`: Check: `(("canonical_key_snapshot" > '' AND "identity_type" = 'brand' AND "name_en_snapshot" > '' AND "name_zh_cn_snapshot" > '' AND "observed_name" = '' AND "product_id" IS NULL) OR ("brand_id" IS NULL AND "canonical_key_snapshot" > '' AND "identity_type" = 'product' AND "name_en_snapshot" > '' AND "name_zh_cn_snapshot" > '' AND "observed_name" = '') OR ("brand_id" IS NULL AND "canonical_key_snapshot" = '' AND "identity_type" = 'unresolved' AND "name_en_snapshot" > '' AND "name_zh_cn_snapshot" > '' AND "observed_name" > '' AND "product_id" IS NULL))`.
- `ck_tns_support_shape`: Check: `(("candidate_id" > '' AND "evidence_ids" = '[]'::jsonb AND "support_type" = 'measured_candidate') OR ("candidate_id" = '' AND "support_type" = 'evidence_only' AND NOT ("evidence_ids" = '[]'::jsonb)))`.
- `ck_tns_evidence_pos`: Check: `("support_type" = 'measured_candidate' OR "position" = 1)`.

[Back to table inventory](#table-inventory)

<a id="table-trend_narrative_runs"></a>

### `trend_narrative_runs` — TrendNarrativeRun

One common evidence cutoff for an all-brand headline run and time window.

Model: [TrendNarrativeRun](../../core/models.py#L3795).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `source_cycle_id` | `varchar(128)` | No | — |
| `window_days` | `smallint` | No | Nonnegative. |
| `facts_as_of` | `timestamp with time zone` | No | — |
| `packet_schema_version` | `smallint` | No | Nonnegative. |
| `snapshot` | `jsonb` | No | — |
| `brand_manifest` | `jsonb` | No | Default: `[]`. |
| `batch_manifest` | `jsonb` | No | Default: `[]`. |
| `internal_order` | `jsonb` | No | Default: `[]`. |
| `status` | `varchar(16)` | No | Default: `TrendNarrativeRun.Status.PREPARING`. Choices: `preparing`, `suspended`, `terminal`, `active`, `superseded`. |
| `suspension_reason` | `varchar(64)` | No | Default: `''`. |
| `activated_at` | `timestamp with time zone` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_tnr_window_facts`: (`window_days`, `facts_as_of`).
- `idx_tnr_status_created`: (`status`, `created_at`).

**Named constraints:**

- `uq_tnr_source_window`: Unique (`source_cycle_id`, `window_days`).
- `ck_tnr_window`: Check: `"window_days" IN (1, 7, 30, 365)`.
- `ck_tnr_status`: Check: `"status" IN ('preparing', 'suspended', 'terminal', 'active', 'superseded')`.
- `ck_tnr_activation_shape`: Check: `(("activated_at" IS NOT NULL AND "status" IN ('active', 'superseded')) OR ("activated_at" IS NULL AND "status" IN ('preparing', 'suspended', 'terminal')))`.
- `ck_tnr_suspension_reason`: Check: `(("status" = 'suspended' AND "suspension_reason" > '') OR NOT ("status" = 'suspended'))`.

[Back to table inventory](#table-inventory)

<a id="table-brand_trend_narratives"></a>

### `brand_trend_narratives` — BrandTrendNarrative

One prepared brand headline outcome within a run.

Model: [BrandTrendNarrative](../../core/models.py#L4165).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `run_id` | `bigint` | No | Model: `run`. FK → [trend_narrative_runs.id](#table-trend_narrative_runs); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `SET_NULL`. Collation: `case_insensitive`. |
| `brand_key_snapshot` | `varchar(64)` | No | — |
| `brand_name_en_snapshot` | `text` | No | — |
| `brand_name_zh_cn_snapshot` | `text` | No | — |
| `status` | `varchar(32)` | No | Choices: `prepared`, `approved`, `held`, `unavailable`, `no_content`, `data_quality_unavailable`. |
| `headline_en` | `text` | No | Default: `''`. |
| `headline_zh_cn` | `text` | No | Default: `''`. |
| `secondary_en` | `text` | No | Default: `''`. |
| `secondary_zh_cn` | `text` | No | Default: `''`. |
| `critic_decision` | `varchar(16)` | No | Default: `''`. Choices: `approve`, `repair`, `hold`. |
| `critic_review_state` | `varchar(16)` | No | Default: `''`. |
| `critic_reason_codes` | `jsonb` | No | Default: `[]`. |
| `critic_audit_eligible` | `boolean` | No | Default: `False`. |
| `narrative_kind` | `varchar(32)` | No | Default: `''`. Choices: `event_led`, `content_shift`, `mix_shift`, `quiet_context`. |
| `confidence` | `varchar(16)` | No | Default: `''`. Choices: `high`, `medium`, `low`. |
| `propositions` | `jsonb` | No | Default: `[]`. |
| `events` | `jsonb` | No | Default: `[]`. |
| `cited_fact_ids` | `jsonb` | No | Default: `[]`. |
| `cited_evidence_ids` | `jsonb` | No | Default: `[]`. |
| `selected_evidence_packet` | `jsonb` | Yes | — |
| `final_critic_payload` | `jsonb` | Yes | — |
| `verified_at` | `timestamp with time zone` | Yes | — |
| `attempted_at` | `timestamp with time zone` | No | — |
| `error_code` | `varchar(64)` | No | Default: `''`. |
| `last_good_id` | `bigint` | Yes | Model: `last_good`. FK → [brand_trend_narratives.id](#table-brand_trend_narratives); Django delete: `PROTECT`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_btn_brand_attempt`: (`brand_key_snapshot`, `attempted_at DESC`).
- `idx_btn_run_status`: (`run_id`, `status`).

**Named constraints:**

- `uq_btn_run_brand`: Unique (`run_id`, `brand_key_snapshot`).
- `ck_btn_status`: Check: `"status" IN ('prepared', 'approved', 'held', 'unavailable', 'no_content', 'data_quality_unavailable')`.
- `ck_btn_output_shape`: Check: `(("status" = 'prepared' AND "verified_at" IS NULL) OR ("headline_en" > '' AND "headline_zh_cn" > '' AND "secondary_en" > '' AND "secondary_zh_cn" > '' AND "status" = 'approved' AND "verified_at" IS NOT NULL) OR "status" IN ('held', 'unavailable', 'no_content', 'data_quality_unavailable'))`.
- `ck_btn_held_last_good`: Check: `(("last_good_id" IS NOT NULL AND "status" = 'held') OR NOT ("status" = 'held'))`.
- `ck_btn_critic_decision`: Check: `"critic_decision" IN ('', 'approve', 'repair', 'hold')`.
- `ck_btn_critic_review_state`: Check: `"critic_review_state" IN ('', 'bypassed', 'reviewed')`.
- `ck_btn_narrative_kind`: Check: `"narrative_kind" IN ('', 'event_led', 'content_shift', 'mix_shift', 'quiet_context')`.
- `ck_btn_confidence`: Check: `"confidence" IN ('', 'high', 'medium', 'low')`.

[Back to table inventory](#table-inventory)

<a id="table-brand_trend_narrative_texts"></a>

### `brand_trend_narrative_texts` — BrandTrendNarrativeText

One locale’s headline and byline for a brand narrative.

Model: [BrandTrendNarrativeText](../../core/models.py#L4307).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `narrative_id` | `bigint` | No | Model: `narrative`. FK → [brand_trend_narratives.id](#table-brand_trend_narratives); Django delete: `CASCADE`. |
| `locale` | `varchar(8)` | No | — |
| `headline` | `text` | No | — |
| `secondary` | `text` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_brand_trend_narrative_locale`: Unique (`narrative_id`, `locale`).
- `ck_brand_trend_narrative_locale`: Check: `"locale" IN ('en', 'zh-cn', 'ja')`.
- `ck_brand_trend_narrative_text`: Check: `(NOT ("headline" = '') AND NOT ("secondary" = ''))`.

[Back to table inventory](#table-inventory)

<a id="table-trend_narrative_visible_runs"></a>

### `trend_narrative_visible_runs` — TrendNarrativeVisibleRun

One currently visible run for a supported time window.

Model: [TrendNarrativeVisibleRun](../../core/models.py#L3951).

**Primary key:** `window_days`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `window_days` | `smallint` | No | PK. Nonnegative. |
| `run_id` | `bigint` | No | Model: `run`. FK → [trend_narrative_runs.id](#table-trend_narrative_runs); Django delete: `PROTECT`. |
| `facts_as_of` | `timestamp with time zone` | No | — |
| `activated_at` | `timestamp with time zone` | No | — |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_tnvr_window`: Check: `"window_days" IN (1, 7, 30, 365)`.

[Back to table inventory](#table-inventory)

<a id="table-trend_narrative_work_slots"></a>

### `trend_narrative_work_slots` — TrendNarrativeWorkSlot

One window’s active work claim and optional newer queued cutoff.

Model: [TrendNarrativeWorkSlot](../../core/models.py#L3871).

**Primary key:** `window_days`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `window_days` | `smallint` | No | PK. Nonnegative. |
| `active_source_cycle_id` | `varchar(128)` | No | Default: `''`. |
| `active_facts_as_of` | `timestamp with time zone` | Yes | — |
| `active_run_id` | `bigint` | Yes | Model: `active_run`. FK → [trend_narrative_runs.id](#table-trend_narrative_runs); Django delete: `SET_NULL`. |
| `snapshot_claim_owner` | `varchar(128)` | No | Default: `''`. |
| `snapshot_claim_fence` | `integer` | No | Nonnegative. Default: `0`. |
| `snapshot_claimed_at` | `timestamp with time zone` | Yes | — |
| `snapshot_claim_expires_at` | `timestamp with time zone` | Yes | — |
| `queued_source_cycle_id` | `varchar(128)` | No | Default: `''`. |
| `queued_facts_as_of` | `timestamp with time zone` | Yes | — |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_tnws_window`: Check: `"window_days" IN (1, 7, 30, 365)`.
- `ck_tnws_active_shape`: Check: `(("active_facts_as_of" IS NULL AND "active_run_id" IS NULL AND "active_source_cycle_id" = '' AND "snapshot_claim_expires_at" IS NULL AND "snapshot_claim_fence" = 0 AND "snapshot_claim_owner" = '' AND "snapshot_claimed_at" IS NULL) OR ("active_facts_as_of" IS NOT NULL AND "active_source_cycle_id" > ''))`.
- `ck_tnws_snapshot_claim`: Check: `(("snapshot_claim_expires_at" IS NULL AND "snapshot_claim_fence" = 0 AND "snapshot_claim_owner" = '' AND "snapshot_claimed_at" IS NULL) OR ("snapshot_claim_expires_at" > ("snapshot_claimed_at") AND "snapshot_claim_fence" > 0 AND "snapshot_claim_owner" > '' AND "snapshot_claimed_at" IS NOT NULL))`.
- `ck_tnws_queued_shape`: Check: `(("queued_facts_as_of" IS NULL AND "queued_source_cycle_id" = '') OR ("queued_facts_as_of" IS NOT NULL AND "queued_source_cycle_id" > ''))`.

[Back to table inventory](#table-inventory)

<a id="table-trend_narrative_demands"></a>

### `trend_narrative_demands` — TrendNarrativeDemand

One coalesced brand/window headline request and its scheduling state.

Model: [TrendNarrativeDemand](../../core/models.py#L3974).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `brand_id` | `varchar(64)` | No | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `CASCADE`. Collation: `case_insensitive`. |
| `window_days` | `smallint` | No | Nonnegative. |
| `target_contract_version` | `varchar(64)` | No | — |
| `target_prompt_version` | `varchar(255)` | No | — |
| `target_model` | `varchar(128)` | No | — |
| `demand_reason` | `varchar(16)` | No | Choices: `visible`, `prewarm`, `operator`. |
| `priority` | `smallint` | No | Nonnegative. Default: `10`. |
| `request_count` | `integer` | No | Nonnegative. Default: `1`. |
| `last_enqueued_request_count` | `integer` | No | Nonnegative. Default: `0`. |
| `operator_request_count` | `integer` | No | Nonnegative. Default: `0`. |
| `last_enqueued_operator_request_count` | `integer` | No | Nonnegative. Default: `0`. |
| `first_requested_at` | `timestamp with time zone` | No | — |
| `last_requested_at` | `timestamp with time zone` | No | — |
| `hot_until` | `timestamp with time zone` | No | — |
| `is_pinned` | `boolean` | No | Default: `False`. |
| `last_material_input_fingerprint` | `varchar(64)` | No | Default: `''`. |
| `last_enqueued_at` | `timestamp with time zone` | Yes | — |
| `last_satisfied_at` | `timestamp with time zone` | Yes | — |
| `last_decision_reason` | `varchar(64)` | No | Default: `''`. |
| `suppression_count` | `integer` | No | Nonnegative. Default: `0`. |
| `state` | `varchar(16)` | No | Default: `TrendNarrativeDemand.State.PENDING`. Choices: `pending`, `scheduled`, `satisfied`, `suppressed`, `failed`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_tnd_window_due`: (`window_days`, `state`, `hot_until`).
- `idx_tnd_state_priority`: (`state`, `priority DESC`).

**Named constraints:**

- `uq_tnd_brand_window`: Unique (`brand_id`, `window_days`).
- `ck_tnd_window`: Check: `"window_days" IN (1, 7, 30, 365)`.
- `ck_tnd_priority`: Check: `("priority" >= 1 AND "priority" <= 100)`.
- `ck_tnd_request_order`: Check: `"last_requested_at" >= ("first_requested_at")`.
- `ck_tnd_hot_order`: Check: `"hot_until" >= ("last_requested_at")`.
- `ck_tnd_enqueued_count`: Check: `"last_enqueued_request_count" <= ("request_count")`.
- `ck_tnd_operator_count`: Check: `"last_enqueued_operator_request_count" <= ("operator_request_count")`.

[Back to table inventory](#table-inventory)

<a id="table-trend_narrative_provider_calls"></a>

### `trend_narrative_provider_calls` — TrendNarrativeProviderCall

One recorded provider attempt for ranking, editing, or reviewing headlines.

Model: [TrendNarrativeProviderCall](../../core/models.py#L4073).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `run_id` | `bigint` | No | Model: `run`. FK → [trend_narrative_runs.id](#table-trend_narrative_runs); Django delete: `CASCADE`. |
| `stage` | `varchar(16)` | No | Choices: `rank`, `editor`, `critic`. |
| `batch_key` | `varchar(128)` | No | Default: `''`. |
| `request_identity` | `varchar(128)` | No | — |
| `request_hash` | `varchar(64)` | No | — |
| `response_hash` | `varchar(64)` | No | Default: `''`. |
| `request_packet` | `jsonb` | Yes | — |
| `response_payload` | `jsonb` | Yes | — |
| `state` | `varchar(16)` | No | Default: `TrendNarrativeProviderCall.State.RESERVED`. Choices: `reserved`, `sent`, `completed`, `ambiguous`, `failed`. |
| `claim_owner` | `varchar(128)` | No | Default: `''`. |
| `claim_fence` | `integer` | No | Nonnegative. Default: `0`. |
| `claimed_at` | `timestamp with time zone` | Yes | — |
| `claim_expires_at` | `timestamp with time zone` | Yes | — |
| `reserved_at` | `timestamp with time zone` | No | — |
| `sent_at` | `timestamp with time zone` | Yes | — |
| `completed_at` | `timestamp with time zone` | Yes | — |
| `error_code` | `varchar(64)` | No | Default: `''`. |
| `input_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `output_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `latency_ms` | `integer` | Yes | Nonnegative. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_tnpc_claim_due`: (`state`, `claim_expires_at`).
- `idx_tnpc_run_stage`: (`run_id`, `stage`).

**Named constraints:**

- `uq_tnpc_run_stage_batch`: Unique (`run_id`, `stage`, `batch_key`).
- `uq_tnpc_request_identity`: Unique (`request_identity`).
- `ck_tnpc_stage`: Check: `"stage" IN ('rank', 'editor', 'critic')`.
- `ck_tnpc_state`: Check: `"state" IN ('reserved', 'sent', 'completed', 'ambiguous', 'failed')`.
- `ck_tnpc_claim_shape`: Check: `(("claim_expires_at" IS NULL AND "claim_fence" = 0 AND "claim_owner" = '' AND "claimed_at" IS NULL) OR ("claim_expires_at" > ("claimed_at") AND "claim_fence" > 0 AND "claim_owner" > '' AND "claimed_at" IS NOT NULL))`.
- `ck_tnpc_sent_shape`: Check: `(("sent_at" IS NULL AND "state" = 'reserved') OR ("sent_at" IS NOT NULL AND "state" IN ('sent', 'completed', 'ambiguous', 'failed')))`.
- `ck_tnpc_completed_shape`: Check: `(("completed_at" IS NULL AND "state" IN ('reserved', 'sent', 'ambiguous', 'failed')) OR ("completed_at" IS NOT NULL AND "response_hash" > '' AND "state" = 'completed'))`.

[Back to table inventory](#table-inventory)


<a id="editorial"></a>

## Chatter, Pulse and editorial pictures

These seven tables preserve editorial decisions, shareable editions, spend and
optional picture assignments. They do not replace atomic source posts or the
existing brand/window headlines. See [editorial operation](editorial-stories.md).

Application services publish editions once and never edit their accepted copy.
This is a writer convention, not a database immutability trigger. Picture rows
can progress while a video task is collected.


<a id="table-editorial_assessments"></a>

### `editorial_assessments` — EditorialAssessment

One fenced quarter-hour editorial or content-picture assessment, with frozen evidence and outcome.

Model: [EditorialAssessment](../../core/models.py).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | Primary key. Database-generated identity. |
| `interval` | `timestamp with time zone` | No | — |
| `scope` | `varchar(80)` | No | Default: `'editorial'`. |
| `cutoff` | `timestamp with time zone` | No | — |
| `source_cycle_id` | `text` | No | — |
| `state` | `varchar(24)` | No | Default: `'running'`. |
| `fence` | `integer` | No | Default: `1`. |
| `lease_until` | `timestamp with time zone` | No | — |
| `packet` | `jsonb` | No | Default: `dict`. |
| `decisions` | `jsonb` | No | Default: `dict`. |
| `outcome` | `jsonb` | No | Default: `dict`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_editorial_assessment_state`: `CREATE INDEX "idx_editorial_assessment_state" ON "editorial_assessments" ("state", "interval")`.

**Named constraints:**

- `uq_editorial_scope_interval`: `CONSTRAINT "uq_editorial_scope_interval" UNIQUE ("scope", "interval")`.

[Back to table inventory](#table-inventory)


<a id="table-editorial_budgets"></a>

### `editorial_budgets` — EditorialBudget

One UTC day of conservative spend reservations and text/media call counts.

Model: [EditorialBudget](../../core/models.py).

**Primary key:** `day`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `day` | `date` | No | Primary key. |
| `reserved_usd` | `numeric(12, 6)` | No | Default: `0`. |
| `calls` | `integer` | No | Default: `0`. |
| `media_calls` | `integer` | No | Default: `0`. |

**Named indexes:**

None beyond primary-key, unique-field and automatic FK indexes.

**Named constraints:**

- `ck_editorial_budget_positive`: `CONSTRAINT "ck_editorial_budget_positive" CHECK ("reserved_usd" >= 0)`.

[Back to table inventory](#table-inventory)


<a id="table-editorial_calls"></a>

### `editorial_calls` — EditorialCall

One reserved provider stage and its saved response or uncertain-send outcome.

Model: [EditorialCall](../../core/models.py).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | Primary key. Database-generated identity. |
| `assessment_id` | `bigint` | No | FK → [editorial_assessments](#table-editorial_assessments). Django PROTECT. Model: `assessment`. |
| `stage` | `varchar(200)` | No | — |
| `kind` | `varchar(16)` | No | — |
| `state` | `varchar(24)` | No | Default: `'sent'`. |
| `reserved_usd` | `numeric(12, 6)` | No | — |
| `budget_day` | `date` | No | — |
| `response` | `jsonb` | No | Default: `dict`. |
| `error_code` | `varchar(80)` | No | Default: `''`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_editorial_call_state`: `CREATE INDEX "idx_editorial_call_state" ON "editorial_calls" ("state", "created_at")`.

**Named constraints:**

- `uq_editorial_call_stage`: `CONSTRAINT "uq_editorial_call_stage" UNIQUE ("assessment_id", "stage")`.
- `uq_editorial_media_stage`: `CREATE UNIQUE INDEX "uq_editorial_media_stage" ON "editorial_calls" ("stage") WHERE "kind" = 'media'`.

[Back to table inventory](#table-inventory)


<a id="table-editorial_stories"></a>

### `editorial_stories` — EditorialStory

One permanent development identity with original-post anchors.

Model: [EditorialStory](../../core/models.py).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `uuid` | No | Primary key. Default: `uuid.uuid4`. |
| `development_key` | `varchar(160)` | No | Unique. |
| `anchor_ids` | `jsonb` | No | Default: `list`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_editorial_story_anchors`: `CREATE INDEX "idx_editorial_story_anchors" ON "editorial_stories" USING gin ("anchor_ids")`.

**Named constraints:**

None beyond the keys and field checks described above.

[Back to table inventory](#table-inventory)


<a id="table-editorial_editions"></a>

### `editorial_editions` — EditorialEdition

One immutable accepted story edition for a track, locale and revision.

Model: [EditorialEdition](../../core/models.py).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `uuid` | No | Primary key. Default: `uuid.uuid4`. |
| `story_id` | `uuid` | No | FK → [editorial_stories](#table-editorial_stories). Django PROTECT. Model: `story`. |
| `assessment_id` | `bigint` | No | FK → [editorial_assessments](#table-editorial_assessments). Django PROTECT. Model: `assessment`. |
| `track` | `varchar(16)` | No | — |
| `locale` | `varchar(12)` | No | — |
| `revision` | `integer` | No | — |
| `headline` | `varchar(160)` | No | — |
| `byline` | `varchar(500)` | No | — |
| `article` | `text` | No | — |
| `importance` | `double precision` | No | — |
| `occurred_at` | `timestamp with time zone` | No | — |
| `fingerprint` | `varchar(64)` | No | — |
| `voice` | `jsonb` | No | Default: `dict`. |
| `model` | `varchar(160)` | No | — |
| `evidence` | `jsonb` | No | Default: `dict`. |
| `selection` | `jsonb` | No | Default: `dict`. |
| `published_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_editorial_feed`: `CREATE INDEX "idx_editorial_feed" ON "editorial_editions" ("track", "locale", "published_at" DESC, "id" DESC)`.

**Named constraints:**

- `uq_editorial_edition_revision`: `CONSTRAINT "uq_editorial_edition_revision" UNIQUE ("story_id", "track", "locale", "revision")`.
- `uq_editorial_edition_evidence`: `CONSTRAINT "uq_editorial_edition_evidence" UNIQUE ("story_id", "track", "locale", "fingerprint")`.
- `uq_editorial_chatter_interval`: `CREATE UNIQUE INDEX "uq_editorial_chatter_interval" ON "editorial_editions" ("assessment_id", "locale") WHERE "track" = 'chatter'`.
- `ck_editorial_edition_track`: `CONSTRAINT "ck_editorial_edition_track" CHECK ("track" IN ('chatter', 'pulse'))`.
- `ck_editorial_importance`: `CONSTRAINT "ck_editorial_importance" CHECK (("importance" >= 0.0 AND "importance" <= 100.0))`.

[Back to table inventory](#table-inventory)


<a id="table-editorial_heroes"></a>

### `editorial_heroes` — EditorialHero

One current hero pointer, or the shared provider-lock row.

Model: [EditorialHero](../../core/models.py).

**Primary key:** `key`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `key` | `varchar(40)` | No | Primary key. |
| `edition_id` | `uuid` | Yes | FK → [editorial_editions](#table-editorial_editions). Django PROTECT. Model: `edition`. |

**Named indexes:**

None beyond primary-key, unique-field and automatic FK indexes.

**Named constraints:**

None beyond the keys and field checks described above.

[Back to table inventory](#table-inventory)


<a id="table-editorial_pictures"></a>

### `editorial_pictures` — EditorialPicture

One optional source/derivative assignment for a content revision.

Model: [EditorialPicture](../../core/models.py).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `uuid` | No | Primary key. Default: `uuid.uuid4`. |
| `content_kind` | `varchar(24)` | No | — |
| `content_id` | `varchar(160)` | No | — |
| `source_platform` | `varchar(24)` | No | Default: `'x'`. |
| `revision_hash` | `varchar(64)` | No | — |
| `assessment_id` | `bigint` | Yes | FK → [editorial_assessments](#table-editorial_assessments). Django PROTECT. Model: `assessment`. |
| `person_media_id` | `bigint` | Yes | FK → [people_media](#table-people_media). Django PROTECT. Model: `person_media`. |
| `source_media_id` | `varchar(64)` | Yes | FK → [staff_media_objects](#table-staff_media_objects). Django PROTECT. Model: `source_media`. |
| `provenance` | `jsonb` | No | Default: `dict`. |
| `treatment` | `text` | No | Default: `''`. |
| `mode` | `varchar(16)` | No | — |
| `state` | `varchar(24)` | No | Default: `'selected'`. |
| `provider_task_id` | `varchar(160)` | No | Default: `''`. |
| `poll_count` | `integer` | No | Default: `0`. |
| `next_poll_at` | `timestamp with time zone` | Yes | — |
| `poll_lease_until` | `timestamp with time zone` | Yes | — |
| `generated_storage_name` | `text` | No | Default: `''`. |
| `generated_sha256` | `varchar(64)` | No | Default: `''`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_editorial_picture_poll`: `CREATE INDEX "idx_editorial_picture_poll" ON "editorial_pictures" ("state", "next_poll_at")`.

**Named constraints:**

- `uq_editorial_picture_revision`: `CONSTRAINT "uq_editorial_picture_revision" UNIQUE ("content_kind", "content_id", "revision_hash")`.

[Back to table inventory](#table-inventory)

<a id="processing"></a>

## Collection, extraction, and processing records

These tables describe collection and interpretation work. A query identity,
a completed cursor, a missing coverage window, a paid search result, and an
accepted domain fact are different units. `call_state` advances completed
collection progress; `harvest_backlog_windows` records bounded coverage still
owed without storing tweet/provider payloads. The cursor’s text `brand_id`
is not a foreign key and can use `'*'` for a combined query.

Targeted extraction state prevents repeating the same role-specific work;
attempts record sanitized outcomes and resource use. Rare-type search runs
record paid time slots and coverage; hits retain results for later decisions.
A decision can be reused for the same content and model/question/threshold
versions. Separate processing-cycle and attempt records reserve and settle
decision spending. Reserved, accounted, and confirmed costs are not synonyms.
See [Rare-type intelligence](rare-types.md) and [collection calls](twitterapi-io-calls.md).


<a id="table-search_queries"></a>

### `search_queries` — SearchQuery

One saved collection/discovery query identity and associated brand/keywords.

Model: [SearchQuery](../../core/models.py#L3112).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `query_id` | `text` | No | Unique. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `SET_NULL`. Collation: `case_insensitive`. |
| `keywords_json` | `jsonb` | Yes | Model: `keywords`. |
| `plan_calls_run_id` | `text` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

- `idx_search_queries_brand_id`: (`brand_id`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-call_state"></a>

### `call_state` — CallState

One harvest cursor for a brand, call, bucket, and query combination.

Model: [CallState](../../core/models.py#L3137).

**Primary key:** `brand_id`, `call_id`, `call_kind`, `bucket`, `query_id` (composite; no separate `pk` column).

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `brand_id` | `text` | No | PK component. Brand slug or * for combined queries; intentionally not an FK. |
| `call_id` | `text` | No | PK component. |
| `call_kind` | `text` | No | PK component. |
| `bucket` | `text` | No | PK component. Default: `''`. |
| `query_id` | `text` | No | PK component. |
| `last_completed_at` | `timestamp with time zone` | Yes | Completed collection cursor; query planning applies its configured overlap. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_call_state_completed_at`: (`last_completed_at`).

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-harvest_backlog_windows"></a>

### `harvest_backlog_windows` — HarvestBacklogWindow

One bounded time window still owed collection coverage.

Model: [HarvestBacklogWindow](../../core/models.py#L3386).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `brand_id` | `text` | No | — |
| `call_id` | `text` | No | — |
| `call_kind` | `text` | No | — |
| `bucket` | `text` | No | Default: `''`. |
| `query_id` | `text` | No | — |
| `original_since` | `timestamp with time zone` | No | — |
| `original_until` | `timestamp with time zone` | No | — |
| `remaining_since` | `timestamp with time zone` | No | — |
| `remaining_until` | `timestamp with time zone` | No | — |
| `state` | `varchar(16)` | No | Default: `HarvestBacklogWindow.State.PENDING`. Choices: `pending`, `claimed`, `quarantined`, `waived`. |
| `reason_code` | `varchar(64)` | No | — |
| `attempts` | `smallint` | No | Nonnegative. Default: `0`. |
| `first_seen_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `last_seen_at` | `timestamp with time zone` | No | Set by Django on model save. |
| `next_attempt_at` | `timestamp with time zone` | Yes | — |
| `claim_owner` | `varchar(128)` | No | Default: `''`. |
| `claim_run_id` | `varchar(128)` | No | Default: `''`. |
| `claimed_at` | `timestamp with time zone` | Yes | — |
| `claim_expires_at` | `timestamp with time zone` | Yes | — |
| `quarantine_reason` | `varchar(128)` | No | Default: `''`. |
| `quarantined_at` | `timestamp with time zone` | Yes | — |
| `waiver_reason` | `varchar(128)` | No | Default: `''`. |
| `waived_at` | `timestamp with time zone` | Yes | — |

**Named indexes:**

- `idx_hbw_call_state_since`: (`brand_id`, `call_id`, `call_kind`, `bucket`, `query_id`, `state`, `remaining_since`).
- `idx_hbw_state_due`: (`state`, `next_attempt_at`).
- `idx_hbw_claim_expiry`: (`claim_expires_at`).

**Named constraints:**

- `ck_hbw_original_interval`: Check: `"original_since" < ("original_until")`.
- `ck_hbw_remaining_interval`: Check: `"remaining_since" < ("remaining_until")`.
- `ck_hbw_remaining_start`: Check: `"remaining_since" >= ("original_since")`.
- `ck_hbw_remaining_end`: Check: `"remaining_until" <= ("original_until")`.
- `uq_hbw_call_remaining`: Unique (`brand_id`, `call_id`, `call_kind`, `bucket`, `query_id`, `remaining_since`, `remaining_until`).

[Back to table inventory](#table-inventory)

<a id="table-_applied_config_snapshot"></a>

### `_applied_config_snapshot` — AppliedConfigSnapshot

One configuration artifact’s last applied content hash.

Model: [AppliedConfigSnapshot](../../core/models.py#L4480).

**Primary key:** `artifact`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `artifact` | `text` | No | PK. |
| `content_hash` | `text` | No | — |
| `written_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

None beyond the column-level keys, uniqueness, nullability, and type checks described above.

[Back to table inventory](#table-inventory)

<a id="table-targeted_extraction_states"></a>

### `targeted_extraction_states` — TargetedExtractionState

One post/role extraction state, used to avoid repeating the same work.

Model: [TargetedExtractionState](../../core/models.py#L6526).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `post_id` | `text` | No | Model: `post`. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `role` | `varchar(64)` | No | — |
| `status` | `varchar(16)` | No | Default: `'pending'`. Choices: `pending`, `succeeded`, `failed`. |
| `content_identity` | `varchar(64)` | No | — |
| `model` | `text` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `attempts` | `integer` | No | Nonnegative. Default: `0`. |
| `result_hash` | `varchar(64)` | Yes | — |
| `last_error_code` | `varchar(128)` | No | Default: `''`. |
| `last_attempted_at` | `timestamp with time zone` | Yes | — |
| `completed_at` | `timestamp with time zone` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_target_extract_due`: (`status`, `role`).

**Named constraints:**

- `ck_target_extract_status`: Check: `"status" IN ('pending', 'succeeded', 'failed')`.
- `ck_target_extract_role`: Check: `"role" IN ('event_extraction', 'opportunity_extraction', 'job_listing_extraction', 'personnel_change_extraction', 'profile_affiliation_extraction', 'model_release_extraction')`.
- `uq_target_extract_post_role`: Unique (`post_id`, `role`).

[Back to table inventory](#table-inventory)

<a id="table-targeted_extraction_attempts"></a>

### `targeted_extraction_attempts` — TargetedExtractionAttempt

One recorded attempt to extract a role-specific fact from a post.

Model: [TargetedExtractionAttempt](../../core/models.py#L6583).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `state_id` | `bigint` | No | Model: `state`. FK → [targeted_extraction_states.id](#table-targeted_extraction_states); Django delete: `CASCADE`. |
| `attempt_identity` | `varchar(64)` | No | Unique. |
| `attempted_at` | `timestamp with time zone` | No | — |
| `outcome` | `varchar(16)` | No | Choices: `succeeded`, `failed`. |
| `model` | `text` | No | — |
| `prompt_version` | `varchar(64)` | No | — |
| `input_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `output_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `latency_ms` | `integer` | No | Nonnegative. Default: `0`. |
| `error_code` | `varchar(128)` | No | Default: `''`. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_target_attempt_outcome`: Check: `"outcome" IN ('succeeded', 'failed')`.

[Back to table inventory](#table-inventory)

<a id="table-rare_type_category_assignments"></a>

### `rare_type_category_assignments` — RareTypeCategoryAssignment

One source-backed rare-category assignment for a post and organization.

Model: [RareTypeCategoryAssignment](../../core/models.py#L6483).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `post_id` | `text` | No | Model: `post`. FK → [posts.tweet_id](#table-posts); Django delete: `CASCADE`. |
| `brand_id` | `varchar(64)` | Yes | Model: `brand`. FK → [brands.nickname](#table-brands); Django delete: `PROTECT`. Collation: `case_insensitive`. |
| `brand_discovery_candidate_id` | `bigint` | Yes | Model: `brand_discovery_candidate`. FK → [brand_discovery_candidates.id](#table-brand_discovery_candidates); Django delete: `PROTECT`. |
| `category` | `varchar(32)` | No | Choices: `llm-model`, `other-ai-model`, `agent-harness`. |
| `source_evidence` | `jsonb` | No | Default: `{}`. |
| `classification_version` | `text` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `ck_rare_category_one_owner`: Check: `(("brand_id" IS NOT NULL AND "brand_discovery_candidate_id" IS NULL) OR ("brand_id" IS NULL AND "brand_discovery_candidate_id" IS NOT NULL))`.
- `uq_rare_category_post_brand`: Unique (`post_id`, `brand_id`, `category`) where `"brand_id" IS NOT NULL`.
- `uq_rare_category_post_candidate`: Unique (`post_id`, `brand_discovery_candidate_id`, `category`) where `"brand_discovery_candidate_id" IS NOT NULL`.

[Back to table inventory](#table-inventory)

<a id="table-rare_type_search_daily_budgets"></a>

### `rare_type_search_daily_budgets` — RareTypeSearchDailyBudget

One search lane’s budget accounting for a UTC day.

Model: [RareTypeSearchDailyBudget](../../core/models.py#L6621).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `usage_date` | `date` | No | — |
| `lane` | `varchar(64)` | No | — |
| `search_credits_reserved` | `integer` | No | Nonnegative. Default: `0`. |
| `search_credits_accounted` | `integer` | No | Nonnegative. Default: `0`. |
| `decision_usd_reserved` | `numeric(16, 9)` | No | Default: `0`. |
| `decision_usd_accounted` | `numeric(16, 9)` | No | Default: `0`. |
| `decision_usd_confirmed` | `numeric(16, 9)` | No | Default: `0`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_rare_budget_day_lane`: Unique (`usage_date`, `lane`).
- `ck_rare_budget_dec_reserved`: Check: `"decision_usd_reserved" >= 0`.
- `ck_rare_budget_dec_accounted`: Check: `"decision_usd_accounted" >= 0`.
- `ck_rare_budget_dec_confirmed`: Check: `"decision_usd_confirmed" >= 0`.

[Back to table inventory](#table-inventory)

<a id="table-rare_type_search_runs"></a>

### `rare_type_search_runs` — RareTypeSearchRun

One paid rare-type search time slot and its coverage/cost record.

Model: [RareTypeSearchRun](../../core/models.py#L6661).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `lane` | `varchar(64)` | No | — |
| `slot_start` | `timestamp with time zone` | No | — |
| `daily_budget_id` | `bigint` | No | Model: `daily_budget`. FK → [rare_type_search_daily_budgets.id](#table-rare_type_search_daily_budgets); Django delete: `PROTECT`. |
| `source_query_id` | `bigint` | No | Model: `source_query`. FK → [search_queries.id](#table-search_queries); Django delete: `PROTECT`. |
| `query_string` | `text` | No | — |
| `query_hash` | `varchar(64)` | No | — |
| `query_version` | `varchar(128)` | No | — |
| `window_start` | `timestamp with time zone` | No | — |
| `window_end` | `timestamp with time zone` | No | — |
| `attempted_start` | `timestamp with time zone` | No | — |
| `attempted_end` | `timestamp with time zone` | No | — |
| `complete_start` | `timestamp with time zone` | Yes | — |
| `complete_end` | `timestamp with time zone` | Yes | — |
| `status` | `varchar(16)` | No | Default: `RareTypeSearchRun.Status.RESERVED`. Choices: `reserved`, `dispatched`, `returned`, `empty`, `failed`, `usage_unknown`. |
| `request_count` | `smallint` | No | Nonnegative. Default: `0`. |
| `raw_result_count` | `integer` | Yes | Nonnegative. |
| `normalized_result_count` | `integer` | Yes | Nonnegative. |
| `reserved_credits` | `integer` | No | Nonnegative. Default: `300`. |
| `estimated_credits` | `integer` | Yes | Nonnegative. |
| `confirmed_credits` | `integer` | Yes | Nonnegative. |
| `decision_usd_reserved` | `numeric(16, 9)` | No | Default: `0`. |
| `decision_usd_accounted` | `numeric(16, 9)` | No | Default: `0`. |
| `decision_usd_confirmed` | `numeric(16, 9)` | No | Default: `0`. |
| `has_coverage_gap` | `boolean` | No | Default: `False`. |
| `gap_start` | `timestamp with time zone` | Yes | — |
| `gap_end` | `timestamp with time zone` | Yes | — |
| `gap_reason` | `varchar(128)` | No | Default: `''`. |
| `truncated` | `boolean` | No | Default: `False`. |
| `error_code` | `varchar(128)` | No | Default: `''`. |
| `error_detail` | `text` | No | Default: `''`. |
| `environment` | `varchar(64)` | No | — |
| `release_sha` | `varchar(64)` | No | — |
| `reserved_at` | `timestamp with time zone` | No | — |
| `dispatched_at` | `timestamp with time zone` | Yes | — |
| `returned_at` | `timestamp with time zone` | Yes | — |
| `finished_at` | `timestamp with time zone` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_rare_run_attempted`: (`lane`, `attempted_end DESC`).
- `idx_rare_run_status_slot`: (`status`, `slot_start`).

**Named constraints:**

- `uq_rare_run_lane_slot`: Unique (`lane`, `slot_start`).
- `ck_rare_run_status`: Check: `"status" IN ('reserved', 'dispatched', 'returned', 'empty', 'failed', 'usage_unknown')`.
- `ck_rare_run_window`: Check: `"window_end" > ("window_start")`.
- `ck_rare_run_attempted_window`: Check: `"attempted_end" > ("attempted_start")`.
- `ck_rare_run_complete_window`: Check: `(("complete_end" IS NULL AND "complete_start" IS NULL) OR ("complete_end" > ("complete_start") AND "complete_end" IS NOT NULL AND "complete_start" IS NOT NULL))`.
- `ck_rare_run_gap_shape`: Check: `(("gap_end" IS NULL AND "gap_reason" = '' AND "gap_start" IS NULL AND NOT "has_coverage_gap") OR ("gap_end" > ("gap_start") AND "gap_end" IS NOT NULL AND "gap_reason" > '' AND "gap_start" IS NOT NULL AND "has_coverage_gap"))`.
- `ck_rare_run_dispatch_shape`: Check: `(("dispatched_at" IS NULL AND "request_count" = 0 AND "status" = 'reserved') OR ("dispatched_at" IS NOT NULL AND "request_count" = 1 AND "status" IN ('dispatched', 'returned', 'empty', 'usage_unknown')) OR ("request_count" IN (0, 1) AND "status" = 'failed'))`.
- `ck_rare_run_result_shape`: Check: `(("confirmed_credits" IS NULL AND "estimated_credits" IS NULL AND "normalized_result_count" IS NULL AND "raw_result_count" IS NULL AND "returned_at" IS NULL AND "status" IN ('reserved', 'dispatched')) OR ("estimated_credits" IS NOT NULL AND "normalized_result_count" IS NOT NULL AND "normalized_result_count" <= ("raw_result_count") AND "raw_result_count" > 0 AND "raw_result_count" IS NOT NULL AND "returned_at" IS NOT NULL AND "status" = 'returned') OR ("estimated_credits" IS NOT NULL AND "normalized_result_count" = 0 AND "normalized_result_count" IS NOT NULL AND "raw_result_count" = 0 AND "raw_result_count" IS NOT NULL AND "returned_at" IS NOT NULL AND "status" = 'empty') OR "status" IN ('failed', 'usage_unknown'))`.
- `ck_rare_run_dec_reserved`: Check: `"decision_usd_reserved" >= 0`.
- `ck_rare_run_dec_accounted`: Check: `"decision_usd_accounted" >= 0`.
- `ck_rare_run_dec_confirmed`: Check: `"decision_usd_confirmed" >= 0`.

[Back to table inventory](#table-inventory)

<a id="table-rare_type_search_hits"></a>

### `rare_type_search_hits` — RareTypeSearchHit

One durable inbox result from an already-paid rare-type search.

Model: [RareTypeSearchHit](../../core/models.py#L7115).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `run_id` | `bigint` | No | Model: `run`. FK → [rare_type_search_runs.id](#table-rare_type_search_runs); Django delete: `PROTECT`. |
| `provider_post_id` | `text` | No | Provider post ID retained before/without a posts row. |
| `content_hash` | `varchar(64)` | No | — |
| `original_text` | `text` | No | Default: `''`. |
| `public_payload` | `jsonb` | No | Default: `{}`. Saved result payload with its own expiration lifecycle. |
| `payload_expires_at` | `timestamp with time zone` | No | — |
| `payload_expired_at` | `timestamp with time zone` | Yes | — |
| `source_query_hash` | `varchar(64)` | No | — |
| `source_query_version` | `varchar(128)` | No | — |
| `source_window_start` | `timestamp with time zone` | No | — |
| `source_window_end` | `timestamp with time zone` | No | — |
| `gate_state` | `varchar(24)` | No | Default: `RareTypeSearchHit.GateState.DECISION_PENDING`. Choices: `decision_pending`, `kept`, `junk`, `review_needed`, `provider_failed`, `expired_unprocessed`. |
| `decision_id` | `bigint` | Yes | Model: `decision`. FK → [rare_type_decisions.id](#table-rare_type_decisions); Django delete: `SET_NULL`. |
| `post_id` | `text` | Yes | Model: `post`. FK → [posts.tweet_id](#table-posts); Django delete: `SET_NULL`. |
| `fetched_at` | `timestamp with time zone` | No | — |
| `gate_completed_at` | `timestamp with time zone` | Yes | — |
| `post_persisted_at` | `timestamp with time zone` | Yes | — |
| `classified_at` | `timestamp with time zone` | Yes | — |
| `extracted_at` | `timestamp with time zone` | Yes | — |
| `first_visible_at` | `timestamp with time zone` | Yes | — |
| `last_error_code` | `varchar(128)` | No | Default: `''`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_rare_hit_gate_due`: (`gate_state`, `fetched_at`).
- `idx_rare_hit_post`: (`provider_post_id`).
- `idx_rare_hit_expiry`: (`payload_expires_at`).

**Named constraints:**

- `uq_rare_hit_run_post`: Unique (`run_id`, `provider_post_id`).
- `ck_rare_hit_gate_state`: Check: `"gate_state" IN ('decision_pending', 'kept', 'junk', 'review_needed', 'provider_failed', 'expired_unprocessed')`.
- `ck_rare_hit_source_window`: Check: `"source_window_end" > ("source_window_start")`.
- `ck_rare_hit_payload_expiry`: Check: `"payload_expires_at" > ("fetched_at")`.

[Back to table inventory](#table-inventory)

<a id="table-rare_type_decisions"></a>

### `rare_type_decisions` — RareTypeDecision

One reusable, versioned relevance interpretation of a provider result.

Model: [RareTypeDecision](../../core/models.py#L6911).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `provider_post_id` | `text` | No | — |
| `content_hash` | `varchar(64)` | No | — |
| `model` | `varchar(255)` | No | — |
| `question_version` | `varchar(128)` | No | — |
| `threshold_version` | `varchar(128)` | No | — |
| `status` | `varchar(16)` | No | Default: `RareTypeDecision.Status.PENDING`. Choices: `pending`, `claimed`, `completed`, `review_needed`, `failed`. |
| `response_id` | `varchar(255)` | No | Default: `''`. |
| `probabilities` | `jsonb` | No | Default: `{}`. |
| `derived_types` | `jsonb` | No | Default: `[]`. |
| `gate_outcome` | `varchar(16)` | No | Default: `''`. Choices: `kept`, `junk`, `review_needed`. |
| `input_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `output_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `cost_usd` | `numeric(16, 9)` | No | Default: `0`. |
| `latency_ms` | `integer` | Yes | Nonnegative. |
| `attempts` | `smallint` | No | Nonnegative. Default: `0`. |
| `next_attempt_at` | `timestamp with time zone` | Yes | — |
| `last_error_code` | `varchar(128)` | No | Default: `''`. |
| `claim_owner` | `varchar(128)` | No | Default: `''`. |
| `claim_fence` | `integer` | No | Nonnegative. Default: `0`. |
| `claimed_at` | `timestamp with time zone` | Yes | — |
| `claim_expires_at` | `timestamp with time zone` | Yes | — |
| `completed_at` | `timestamp with time zone` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_rare_decision_due`: (`status`, `next_attempt_at`).
- `idx_rare_decision_post`: (`provider_post_id`).

**Named constraints:**

- `uq_rare_decision_identity`: Unique (`provider_post_id`, `content_hash`, `model`, `question_version`, `threshold_version`).
- `ck_rare_decision_status`: Check: `"status" IN ('pending', 'claimed', 'completed', 'review_needed', 'failed')`.
- `ck_rare_decision_attempts`: Check: `"attempts" <= 2`.
- `ck_rare_decision_claim_shape`: Check: `(("claim_expires_at" > ("claimed_at") AND "claim_expires_at" IS NOT NULL AND "claim_fence" > 0 AND "claim_owner" > '' AND "claimed_at" IS NOT NULL AND "status" = 'claimed') OR (NOT ("status" = 'claimed') AND "claim_expires_at" IS NULL AND "claim_owner" = '' AND "claimed_at" IS NULL))`.
- `ck_rare_decision_complete_shape`: Check: `(("completed_at" IS NOT NULL AND "status" = 'completed') OR (NOT ("status" = 'completed') AND "completed_at" IS NULL))`.
- `ck_rare_decision_cost`: Check: `"cost_usd" >= 0`.

[Back to table inventory](#table-inventory)

<a id="table-rare_type_decision_processing_cycles"></a>

### `rare_type_decision_processing_cycles` — RareTypeDecisionProcessingCycle

One processing time slot that funds relevance-decision attempts.

Model: [RareTypeDecisionProcessingCycle](../../core/models.py#L6846).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `lane` | `varchar(64)` | No | — |
| `environment` | `varchar(16)` | No | — |
| `slot_start` | `timestamp with time zone` | No | — |
| `usage_date` | `date` | No | — |
| `daily_budget_id` | `bigint` | No | Model: `daily_budget`. FK → [rare_type_search_daily_budgets.id](#table-rare_type_search_daily_budgets); Django delete: `PROTECT`. |
| `attempts_reserved` | `smallint` | No | Nonnegative. Default: `0`. |
| `attempts_accounted` | `smallint` | No | Nonnegative. Default: `0`. |
| `attempts_in_flight` | `smallint` | No | Nonnegative. Default: `0`. |
| `decision_usd_reserved` | `numeric(16, 9)` | No | Default: `0`. |
| `decision_usd_accounted` | `numeric(16, 9)` | No | Default: `0`. |
| `decision_usd_confirmed` | `numeric(16, 9)` | No | Default: `0`. |
| `allocation_started_at` | `timestamp with time zone` | No | — |
| `allocation_deadline` | `timestamp with time zone` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_rare_dec_cycle_slot`: Unique (`lane`, `environment`, `slot_start`).
- `ck_rare_dec_cycle_environment`: Check: `"environment" IN ('normal', 'staging')`.
- `ck_rare_dec_cycle_reserved`: Check: `"decision_usd_reserved" >= 0`.
- `ck_rare_dec_cycle_accounted`: Check: `"decision_usd_accounted" >= 0`.
- `ck_rare_dec_cycle_confirmed`: Check: `"decision_usd_confirmed" >= 0`.
- `ck_rare_dec_cycle_inflight`: Check: `"attempts_in_flight" <= 2`.
- `ck_rare_dec_cycle_allocation`: Check: `"allocation_deadline" > ("allocation_started_at")`.

[Back to table inventory](#table-inventory)

<a id="table-rare_type_decision_attempts"></a>

### `rare_type_decision_attempts` — RareTypeDecisionAttempt

One funded provider attempt for a relevance decision, with one settlement record.

Model: [RareTypeDecisionAttempt](../../core/models.py#L7030).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. Database-generated identity. |
| `decision_id` | `bigint` | No | Model: `decision`. FK → [rare_type_decisions.id](#table-rare_type_decisions); Django delete: `PROTECT`. |
| `processing_cycle_id` | `bigint` | No | Model: `processing_cycle`. FK → [rare_type_decision_processing_cycles.id](#table-rare_type_decision_processing_cycles); Django delete: `PROTECT`. |
| `fence` | `integer` | No | Nonnegative. |
| `state` | `varchar(16)` | No | Default: `RareTypeDecisionAttempt.State.RESERVED`. Choices: `reserved`, `sent`, `settled`, `retained`. |
| `reserved_usd` | `numeric(16, 9)` | No | — |
| `accounted_usd` | `numeric(16, 9)` | No | Default: `0`. |
| `confirmed_usd` | `numeric(16, 9)` | Yes | — |
| `error_code` | `varchar(128)` | No | Default: `''`. |
| `response_id` | `varchar(255)` | No | Default: `''`. |
| `input_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `output_tokens` | `integer` | No | Nonnegative. Default: `0`. |
| `reserved_at` | `timestamp with time zone` | No | — |
| `sent_at` | `timestamp with time zone` | Yes | — |
| `settled_at` | `timestamp with time zone` | Yes | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_rare_dec_attempt_fence`: Unique (`decision_id`, `fence`).
- `ck_rare_dec_attempt_state`: Check: `"state" IN ('reserved', 'sent', 'settled', 'retained')`.
- `ck_rare_dec_attempt_reserved`: Check: `"reserved_usd" > 0`.
- `ck_rare_dec_attempt_accounted`: Check: `"accounted_usd" >= 0`.
- `ck_rare_dec_attempt_confirmed`: Check: `("confirmed_usd" IS NULL OR "confirmed_usd" >= 0)`.
- `ck_rare_dec_attempt_send_shape`: Check: `(("sent_at" IS NULL AND "state" = 'reserved') OR ("sent_at" IS NOT NULL AND "state" IN ('sent', 'settled', 'retained')))`.
- `ck_rare_dec_attempt_settle_shape`: Check: `(("settled_at" IS NOT NULL AND "state" = 'settled') OR (NOT ("state" = 'settled') AND "settled_at" IS NULL))`.

[Back to table inventory](#table-inventory)

<a id="table-staff_intakes"></a>

### `staff_intakes` — StaffIntake

One versioned staff-source observation, including eligibility and its input payload.

Stable source keys and existing person/account IDs support repeat imports. Excluded contributor-only observations have no person. Names alone never authorize a merge. Payloads retain the original dossier or source evidence; these are private operator records.

Model: [StaffIntake](../../core/models.py#L4683).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. |
| `source_key` | `varchar(512)` | No | — |
| `fingerprint` | `varchar(64)` | No | — |
| `person_id` | `uuid` | Yes | FK → [people](#table-people); Django PROTECT. |
| `eligibility` | `varchar(32)` | No | — |
| `payload` | `jsonb` | No | Default: `dict()`. |
| `observed_at` | `timestamp with time zone` | No | — |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_staff_intake_version`: `CONSTRAINT "uq_staff_intake_version" UNIQUE ("source_key", "fingerprint")`.

Migration 0064 prevents updates to the source key, fingerprint, payload and capture timestamps. Reviewed eligibility and person association can change. `needs_review` retains unresolved identity observations without creating collection work.

[Back to table inventory](#table-inventory)

<a id="table-staff_collection_work"></a>

### `staff_collection_work` — StaffCollectionWork

One person/source-fingerprint/policy unit of resumable collection work.

Source writers register work after commit; periodic catch-up covers bulk writes. A shared PostgreSQL advisory lock enforces one active worker lease. Expired leases can resume; interrupted paid requests require review. Stale workers cannot publish collection outcomes.

Model: [StaffCollectionWork](../../core/models.py#L4709).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. |
| `person_id` | `uuid` | No | FK → [people](#table-people); Django CASCADE. |
| `fingerprint` | `varchar(64)` | No | — |
| `policy_version` | `varchar(32)` | No | Default: `'staff-v1'`. |
| `state` | `varchar(24)` | No | Default: `'queued'`. |
| `context` | `jsonb` | No | Default: `dict()`. |
| `attempts` | `integer` | No | Default: `0`. |
| `next_attempt_at` | `timestamp with time zone` | No | Default: `now()`. |
| `lease_token` | `uuid` | Yes | — |
| `lease_expires_at` | `timestamp with time zone` | Yes | — |
| `error_category` | `varchar(64)` | No | Default: `''`. |
| `result` | `jsonb` | No | Default: `dict()`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `updated_at` | `timestamp with time zone` | No | Set by Django on model save. |

**Named indexes:**

- `idx_staff_work_due`: `state`, `next_attempt_at`.

**Named constraints:**

- `uq_staff_work_identity`: `CONSTRAINT "uq_staff_work_identity" UNIQUE ("person_id", "fingerprint", "policy_version")`.
- `ck_staff_work_state`: `CONSTRAINT "ck_staff_work_state" CHECK ("state" IN ('queued', 'running', 'retry_due', 'complete', 'needs_review', 'needs_evidence'))`.
- `ck_staff_work_lease`: `CONSTRAINT "ck_staff_work_lease" CHECK ((("lease_expires_at" IS NOT NULL AND "lease_token" IS NOT NULL AND "state" = 'running') OR (NOT ("state" = 'running') AND "lease_expires_at" IS NULL AND "lease_token" IS NULL)))`.

[Back to table inventory](#table-inventory)

<a id="table-staff_provider_requests"></a>

### `staff_provider_requests` — StaffProviderRequest

One reserved provider request, its outcome and safe response evidence.

Reservations commit before HTTP. They count toward lifetime per-person, per-run and UTC-day caps, including failures. Completed identical queries are reused; uncertain requests are held for review. Explicit operator retry authorization retains the original reservation and records a new query identity.

Model: [StaffProviderRequest](../../core/models.py#L4768).

**Primary key:** `id`.

| SQL column | PostgreSQL type | NULL allowed | Meaning, relationships, and defaults |
| --- | --- | --- | --- |
| `id` | `bigint` | No | PK. |
| `person_id` | `uuid` | No | FK → [people](#table-people); Django CASCADE. |
| `work_id` | `bigint` | Yes | FK → [staff_collection_work](#table-staff_collection_work); Django SET_NULL. |
| `provider` | `varchar(32)` | No | — |
| `fingerprint` | `varchar(64)` | No | — |
| `run_id` | `uuid` | No | — |
| `parameters` | `jsonb` | No | Default: `dict()`. |
| `state` | `varchar(24)` | No | Default: `'reserved'`. |
| `response` | `jsonb` | No | Default: `dict()`. |
| `error_category` | `varchar(64)` | No | Default: `''`. |
| `created_at` | `timestamp with time zone` | No | Set by Django on creation. |
| `completed_at` | `timestamp with time zone` | Yes | — |

**Named indexes:**

None beyond primary-key, unique-field, and automatic field/FK indexes described above.

**Named constraints:**

- `uq_staff_request_identity`: `CONSTRAINT "uq_staff_request_identity" UNIQUE ("person_id", "provider", "fingerprint")`.
- `ck_staff_request_state`: `CONSTRAINT "ck_staff_request_state" CHECK ("state" IN ('reserved', 'complete', 'needs_review'))`.

[Back to table inventory](#table-inventory)

## Compatibility view and schema boundary

`trend_narrative_versions` is a PostgreSQL **view**, outside the application-table count, with no Django model. [Migration 0014](../../core/migrations/0014_expand_trend_narrative.py)
creates it with `SELECT * FROM trend_narratives`. PostgreSQL fixes that view’s
column list at creation; do not assume later table columns automatically appear
in the existing view. Inspect the deployed view definition before relying on
its exact column set.

The column/type/index inventory above was reconciled with all 128 concrete
`core` models and the final migration state through migration 0068. Raw SQL
migrations additionally supply the account-handle expression index, the named
account-country FK, the two explicit SQL delete actions on posts, the ICU
collation, the person-name selection/immutability triggers, and this compatibility view. Application-level validators and
reader/writer behavior still matter; a database check does not prove that a
real-world identity or source claim is true.

Useful related references: [Lookup tables](lookup-tables.md), [Rare-type
intelligence](rare-types.md), [Classifier prompts](classifier-prompts.md),
[Post translation](translator-output.md), [Post commentary](commenter.md),
[Trend narratives](headline-trend-narratives.md), and [maintaining these
references](updating-reference-docs.md).
