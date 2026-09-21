# Pushin Weight database schema — v2 Django ORM

Version: v0.2.0-beta.1 (package `0.2.0b1`)
Last updated: 2026-09-21 12:39:30 JST

`core/models.py` and the ordered files in `core/migrations/` are the schema
source of truth for the production PostgreSQL database. The retired
`schema.dot`, PNG, and v1 SQLite database are not schema authorities.

## Conventions

- Entity and lookup tables use natural keys where the domain has one (`tweet_id`,
  `author_id`, `nickname`, or `key`).
- Junction and i18n tables use Django composite primary keys.
- Durable observations, claims, listings, events, opportunities, extraction
  attempts, and control-plane records use `BigAutoField` where they need their
  own identity.
- Natural-key `CharField`s use the PostgreSQL `case_insensitive` collation.
- Structured payloads use `JSONField`; timestamps are timezone-aware.
- Lookup foreign keys protect vocabulary rows; owned junctions cascade;
  optional relationships set null.

## Core entities

| Table | Identity | Purpose |
| --- | --- | --- |
| `brands` | `nickname` | Tracked brands and the `_unattributed` discovery sentinel |
| `companies` | `nickname` | Company identity derived from brand relationships |
| `accounts` | `author_id` | X account profile and engagement snapshots |
| `posts` | `tweet_id` | Source post, author snapshot, context, metrics, and locale data |
| `products` | `hf_org_id`/natural product identity | Optional product catalog records |
| `search_queries` | `BigAutoField` | Query and brand attribution provenance |

Posts retain source text and stored translations. Parent/quoted relationships
are nullable because a referenced post may not have been fetched.

## Brand and classification relationships

| Table | Primary identity | Purpose |
| --- | --- | --- |
| `brands_accounts` | `(brand, account)` | Reviewed account role for a brand |
| `companies_accounts` | `(company, account)` | Company/account relationship |
| `brands_companies` | `(brand, company)` | Brand/company relationship |
| `posts_brands` | `(post, brand)` | Attributed brand mention and weight |
| `posts_brands_mentions` | `(post, brand, source)` | Raw matched mention evidence |
| `posts_brands_signals` | `(post, brand, post_type)` | Persisted current post-type/sentiment signal |
| `posts_brands_product_labels` | `(post, brand, product_label)` | Product labels for the current brand |
| `posts_brands_classification_states` | `(post, brand)` | Versioned v4 classification state and stance fields |
| `posts_brands_audience_topics` | `(post, brand, topic)` | Current Audience Topic edges |
| `posts_brands_geopolitical_modes` | `(post, brand, mode)` | Current geopolitical mode edges |
| `post_brand_classification_judgments` | durable judgment identity | Input, proposal, and final classification provenance |
| `posts_brands_discourse` | `(post, brand, discourse, act_id)` | Historical per-act discourse compatibility data |
| `posts_unsanctioned_flags` | `post` | Historical flag JSON; current writes use Untracked Brand Promotions |

Every current type, product label, topic, sentiment, geopolitical mode, and
stance is evaluated for the attributed brand in the row. A comparison foil
does not inherit another brand's advertising or sentiment.

## Current intelligence tables

| Table | Identity | Purpose |
| --- | --- | --- |
| `people` | UUID | Person identity, localized names, reduced-precision DOB, `sexs`, nationality, ethnicity, and primary language |
| `people_accounts` | `(person, account)` | Person-to-account relationship |
| `account_profile_snapshots` | `BigAutoField` | Hash-compressed observed profile history |
| `people_brand_affiliations` | `BigAutoField` | Person relationship to a known brand or pending organization candidate |
| `people_brand_affiliation_evidence` | `BigAutoField` | Post/profile/URL evidence for an affiliation |
| `brand_discovery_candidates` | `BigAutoField` | Review queue for untracked organizations |
| `job_listings` | `BigAutoField` | Requisition identity and normalized employment fields |
| `job_listing_evidence` | `BigAutoField` | Source posts, URLs, and media supporting a listing |
| `job_discovery_runs` | `BigAutoField` | Job-search query/window provenance and credit accounting |
| `personnel_discovery_runs` | `BigAutoField` | Personnel-search provenance and affiliation counts |
| `events` | `BigAutoField` | Attendance-bearing occurrence and source schedule facts |
| `opportunities` | `BigAutoField` | Bounded action-for-benefit offer; may reference an event |
| `targeted_extraction_states` | `BigAutoField` | Latest idempotent extraction state per post/role |
| `targeted_extraction_attempts` | `BigAutoField` | Sanitized model, prompt, token, latency, and outcome telemetry |

Event, opportunity, job, and employment dates carry explicit precision. A
profile observation timestamp is never treated as an employment or event date.

## Lookup and control tables

The lookup families are `post_type_keys`, `product_label_keys`,
`audience_topic_schemes`/`audience_topic_concepts`, `sentiment_keys`,
`geopolitical_mode_keys`, `national_stance_keys`, historical
`nationalism_keys`, `discourse_keys`, and `role_keys`, with language label
tables where applicable. Control-plane tables include `call_state`,
`_applied_config_snapshot`, enrichment state/attempt rows, and headline
narrative run/provider/work-slot tables.

## Migration and compatibility boundary

The current migration graph includes the audience-topic and intelligence
tables through the 0043/0044 merge. Existing v1–v3 classification rows remain
readable; v4 writes use `results_analysis`, `news_reporting`, the seven
Audience Topics, geopolitical modes, and `untracked_brand_promotions`.
Compatibility mappings do not rewrite historical rows.

Last reviewed: 2026-09-21 12:39:30 JST — Current schema snapshot reconciled
with `core/models.py`, the migration graph, classification contract, and
intelligence models. Retired Graphviz/SQLite artifacts and dated review notes
are intentionally excluded from this product reference.
