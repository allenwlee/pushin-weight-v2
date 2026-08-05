# x-monitor DB schema -- v2 Django ORM

Last updated: 2026-08-05-20:38:42

Source of truth: [`core/models.py`](../../core/models.py). Migrations: `core/migrations/` (range: 001-039 applied).


![x-monitor schema -- v2 Django ORM, post-migration-039 (core/models.py)](images/xmonitor-schema-post-batch.png)

> **Note:** The schema image is auto-generated from `schema.dot`, which is
> derived from the Django ORM graph in `core/models.py`. The PNG stamp
> reflects the latest applied migration at regeneration time.

## Conventions

- **Natural keys as PK.** Entity and lookup tables use their natural key as the
  primary key (`nickname`, `author_id`, `tweet_id`, `key`, etc.). No synthetic
  `id` column on these tables.
- **CompositePrimaryKey.** Junction and i18n-label tables use
  `django.db.models.CompositePrimaryKey`. No surrogate `id` column.
- **BigAutoField synthetic PK** only on `products` and `search_queries`, which
  are control-plane tables populated by external scrapers/internal schedulers.
- **case_insensitive collation.** All `CharField` natural keys (nicknames,
  handles, namespaces, lookup keys) use `db_collation="case_insensitive"`
  (PostgreSQL: `CREATE COLLATION case_insensitive (provider = icu, locale =
  'und-u-ks-level2', deterministic = false)`).
- **JSONField** for structured data (tweet entities, raw payloads, product
  metadata, keyword lists, flag sets).
- **DateTimeField** with `USE_TZ=True` (stores as `TIMESTAMPTZ` in PostgreSQL).
  `auto_now_add` for creation timestamps, `auto_now` for last-modified.
- **No soft-delete columns.**
- **on_delete=PROTECT** on lookup-table FKs.
  **on_delete=CASCADE** for junction tables. **on_delete=SET_NULL** for
  optional relationships.

---

## 1. Entities

### Brand (`brands`)

| Field | Type | Notes |
|---|---|---|
| nickname | `CharField(max_length=64, pk)` | case_insensitive |
| display_name | `TextField` | nullable |
| accent_color | `TextField` | nullable |
| is_sentinel | `BooleanField(default=False)` | |
| created_at | `DateTimeField(auto_now_add)` | |
| display_name_en | `TextField` | nullable |
| display_name_zh_cn | `TextField` | nullable |

### Company (`companies`)

| Field | Type | Notes |
|---|---|---|
| nickname | `CharField(max_length=64, pk)` | case_insensitive |
| display_name | `TextField` | nullable |
| hq_country | `TextField` | nullable |
| accent_color | `TextField` | nullable |
| description | `TextField` | nullable |
| created_at | `DateTimeField(auto_now_add)` | |
| display_name_en | `TextField` | nullable |
| display_name_zh_cn | `TextField` | nullable |

### Account (`accounts`)

| Field | Type | Notes |
|---|---|---|
| author_id | `TextField(pk)` | X/Twitter user ID string |
| handle | `CharField(max_length=64)` | case_insensitive; nullable |
| display_name | `TextField` | nullable |
| bio | `TextField` | nullable |
| bio_fetched_at | `DateTimeField` | nullable |
| verified | `BooleanField(default=False)` | legacy checkmark |
| bio_contains_brand | `BooleanField` | nullable |
| first_seen_at | `DateTimeField(auto_now_add)` | |
| last_seen_at | `DateTimeField(auto_now)` | |
| source_query_ids | `TextField` | nullable |
| notes | `TextField` | nullable |
| bio_en | `TextField` | nullable |
| bio_zh_cn | `TextField` | nullable |
| followers_count | `IntegerField` | nullable; inline from tweet author payload |
| following_count | `IntegerField` | nullable |
| favourites_count | `IntegerField` | nullable |
| statuses_count | `IntegerField` | nullable |
| media_count | `IntegerField` | nullable |
| fast_followers_count | `IntegerField` | nullable |
| is_blue_verified | `BooleanField` | nullable; X Premium checkmark |
| verified_type | `TextField` | nullable; e.g. "Business", "Government" |
| profile_picture | `TextField` | nullable; URL |
| location | `TextField` | nullable |
| description | `TextField` | nullable; author.description from tweet payload |
| profile_bio_text | `TextField` | nullable; author.profile_bio.description |
| followers_fetched_at | `DateTimeField` | nullable; last-write timestamp for engagement+profile bundle |

Indexes: `idx_accounts_handle (handle)`, `idx_accounts_last_seen_at (last_seen_at)`

> **Sparse data note:** The inline author metadata fields (`followers_count`
> through `followers_fetched_at`) were added later in the migration history and
> are only populated for tweets fetched after that point. Accounts that were
> last seen before the metadata harvesting was added will have NULLs in these
> columns.

### Post (`posts`)

| Field | Type | Notes |
|---|---|---|
| tweet_id | `TextField(pk)` | X/Twitter status ID string |
| author_handle | `CharField(max_length=64)` | case_insensitive; nullable; denormalized for fast display |
| author | FK -> `Account` | `on_delete=SET_NULL`; db_column=`author_id`; to_field=`author_id` |
| text | `TextField` | nullable |
| lang | `TextField` | nullable; declared language |
| created_at | `DateTimeField` | nullable |
| fetched_at | `DateTimeField(auto_now_add)` | |
| like_count | `IntegerField` | nullable |
| retweet_count | `IntegerField` | nullable |
| reply_count | `IntegerField` | nullable |
| quote_count | `IntegerField` | nullable |
| in_reply_to_user_id | `TextField` | nullable |
| quoted_status_id | FK -> `self` (self-referential) | `on_delete=SET_NULL`; nullable; references the inner quoted/retweeted tweet (Policy A: NULL if the parent was never harvested); `db_constraint=True` |
| conversation_id | `TextField` | nullable |
| entities | `JSONField` | nullable; tweet entities payload |
| source_query_id | `TextField` | nullable |
| headline | `TextField` | nullable; extracted headline |
| headline_source | `TextField` | nullable |
| text_en | `TextField` | nullable; English translation |
| text_zh_cn | `TextField` | nullable; Chinese translation |
| lang_detected | `TextField` | nullable; auto-detected language |
| quoted_text | `TextField` | nullable |
| last_quote_count_seen | `IntegerField` | nullable |
| last_quote_fetched_at | `DateTimeField` | nullable |
| created_at_epoch | `BigIntegerField` | nullable; epoch seconds for range queries |

**Section 1.2 — TwitterAPI top-level tweet fields** (added later; nullable
snapshots of the raw TwitterAPI Advanced Search response):

| Field | Type | Notes |
|---|---|---|
| created_at_raw | `TextField` | nullable; TwitterAPI raw timestamp string |
| bookmark_count | `IntegerField` | nullable |
| is_reply | `BooleanField` | nullable |
| is_retweet | `BooleanField` | nullable |
| is_quote | `BooleanField` | nullable |
| in_reply_to_id | `TextField` | nullable; distinct from `in_reply_to_user_id` (the *status* id being replied to) |
| in_reply_to_username | `TextField` | nullable |
| tweet_type | `TextField` | nullable; TwitterAPI type tag |
| tweet_url | `TextField` | nullable; canonical URL |
| tweet_twitter_url | `TextField` | nullable; x.com canonical URL |
| card | `JSONField` | nullable; TwitterAPI card object |
| place | `JSONField` | nullable; geo place object |
| client_source | `TextField` | nullable; client app that posted |
| view_count | `IntegerField` | nullable |
| article | `JSONField` | nullable; X Article object (long-form posts) |
| is_limited_reply | `BooleanField` | nullable |
| community_info | `JSONField` | nullable |
| display_text_range | `JSONField` | nullable; [start, end] indices |
| extended_entities | `JSONField` | nullable; full media/entity payload |
| quoted_author_handle | `TextField` | nullable; handle of the quoted tweet's author |

**Section 1.3 — TwitterAPI author fields** (snapshot of inner `author` object
captured at fetch time; distinct from the per-account `accounts` row which is
the slowly-updating canonical author profile):

| Field | Type | Notes |
|---|---|---|
| author_name | `TextField` | nullable |
| author_followers_count | `IntegerField` | nullable |
| author_following_count | `IntegerField` | nullable |
| author_verified | `BooleanField` | nullable; legacy checkmark |
| author_is_blue_verified | `BooleanField` | nullable; X Premium |
| author_verified_type | `TextField` | nullable; e.g. "Business", "Government" |
| author_is_translator | `BooleanField` | nullable |
| author_is_automated | `BooleanField` | nullable |
| author_automated_by | `TextField` | nullable |
| author_description | `TextField` | nullable |
| author_location | `TextField` | nullable |
| author_media_count | `IntegerField` | nullable |
| author_statuses_count | `IntegerField` | nullable |
| author_favourites_count | `IntegerField` | nullable |
| author_fast_followers_count | `IntegerField` | nullable |
| author_can_dm | `BooleanField` | nullable |
| author_can_media_tag | `BooleanField` | nullable |
| author_profile_picture | `TextField` | nullable; URL |
| author_profile_bio | `JSONField` | nullable; full profile_bio object |
| author_cover_picture | `TextField` | nullable; URL |
| author_pinned_tweet_ids | `JSONField` | nullable; list of pinned tweet ids |
| author_affiliates_highlighted_label | `JSONField` | nullable |
| author_withheld_in_countries | `JSONField` | nullable; list of country codes |
| author_possibly_sensitive | `BooleanField` | nullable |
| author_has_custom_timelines | `BooleanField` | nullable |
| author_entities | `JSONField` | nullable |
| author_twitter_url | `TextField` | nullable |
| author_type | `TextField` | nullable; e.g. "user", "bot" |
| author_url | `TextField` | nullable; external URL |
| author_created_at_raw | `TextField` | nullable |
| author_status | `TextField` | nullable |

> **Sparse data note:** The § 1.2 and § 1.3 fields are nullable snapshots
> populated for tweets fetched after TwitterAPI Advanced Search harvesting
> was wired in. Tweets fetched under the older Search-API-only path will
> have NULLs in these columns. The per-account `accounts` table remains the
> canonical, slowly-updating source of truth for an author's current
> profile metadata.

Indexes: `idx_posts_author_id (author_id)`, `idx_posts_created_at (created_at)`,
`idx_posts_lang (lang)`, `idx_posts_lang_detected (lang_detected)`,
`idx_posts_source_query_id (source_query_id)`, `idx_posts_created_at_epoch (created_at_epoch)`
### HFOrg (`hf_orgs`)

| Field | Type | Notes |
|---|---|---|
| namespace | `CharField(max_length=64, pk)` | case_insensitive; HuggingFace org/user slug |
| company | FK -> `Company` | `on_delete=CASCADE`; db_column=`company_id`; to_field=`nickname` |
| confirmed | `BooleanField(default=False)` | |
| discovered_via | `TextField(default='curated')` | |
| added_at | `DateTimeField(auto_now_add)` | |

Indexes: `idx_hf_orgs_company (company_id)`

### Product (`products`)

| Field | Type | Notes |
|---|---|---|
| id | `BigAutoField(pk)` | synthetic PK |
| repo_id | `CharField(max_length=256, unique=True)` | case_insensitive; HF repo slug |
| brand | FK -> `Brand` | `on_delete=SET_NULL`; nullable; db_column=`brand_id`; to_field=`nickname` |
| hf_org | FK -> `HFOrg` | `on_delete=SET_NULL`; nullable; db_column=`hf_org_id`; to_field=`namespace` |
| hf_type | `TextField(default='model')` | "model", "dataset", or "space" |
| display_name | `TextField` | nullable |
| author | `TextField` | nullable |
| sha | `TextField` | nullable |
| private | `BooleanField` | nullable |
| gated | `TextField` | nullable |
| disabled | `BooleanField` | nullable |
| pipeline_tag | `TextField` | nullable |
| library_name | `TextField` | nullable |
| downloads | `IntegerField` | nullable; recent download count |
| downloads_all_time | `IntegerField` | nullable |
| download_velocity | `FloatField` | nullable |
| likes | `IntegerField` | nullable |
| trending_score | `FloatField` | nullable |
| paperswithcode_id | `TextField` | nullable |
| created_at | `DateTimeField` | nullable; repo creation |
| last_modified | `DateTimeField` | nullable; repo last-modified |
| tags | `JSONField(db_column='tags_json')` | nullable |
| siblings | `JSONField(db_column='siblings_json')` | nullable |
| card_data | `JSONField(db_column='card_data_json')` | nullable |
| config | `JSONField(db_column='config_json')` | nullable |
| spaces | `JSONField(db_column='spaces_json')` | nullable |
| raw | `JSONField(db_column='raw_json')` | nullable |
| collected_at | `DateTimeField(auto_now_add)` | |
| updated_at | `DateTimeField(auto_now)` | |

Indexes: `idx_products_brand (brand_id)`, `idx_products_hf_org_id (hf_org_id)`,
`idx_products_collected_at (collected_at)`

---

## 2. Junctions

### PostBrand (`posts_brands`)

Composite PK: `(post, brand)`.

| Field | Type | Notes |
|---|---|---|
| post | FK -> `Post` | `on_delete=CASCADE`; db_column=`post_id`; to_field=`tweet_id` |
| brand | FK -> `Brand` | `on_delete=CASCADE`; db_column=`brand_id`; to_field=`nickname` |
| weight | `FloatField(default=1.0)` | attribution relevance score |

Indexes: `idx_posts_brands_brand_id (brand_id)`

### PostBrandMention (`posts_brands_mentions`)

Composite PK: `(post, brand, source)`.

| Field | Type | Notes |
|---|---|---|
| post | FK -> `Post` | `on_delete=CASCADE`; db_column=`post_id`; to_field=`tweet_id` |
| brand | FK -> `Brand` | `on_delete=PROTECT`; db_column=`brand_id`; to_field=`nickname` |
| source | `TextField` | match origin (e.g. "keyword", "hashtag", "handle") |
| raw_token | `TextField` | nullable; the raw matched token |
| mentioned_at | `DateTimeField(auto_now_add)` | |

Indexes: `idx_post_brand_mention_brand (brand_id)`

### PostBrandSignal (`posts_brands_signals`)

Composite PK: `(post, brand, post_type)`.

| Field | Type | Notes |
|---|---|---|
| post | FK -> `Post` | `on_delete=CASCADE`; db_column=`post_id`; to_field=`tweet_id` |
| brand | FK -> `Brand` | `on_delete=PROTECT`; db_column=`brand_id`; to_field=`nickname` |
| post_type | FK -> `PostTypeKey` | `on_delete=PROTECT`; db_column=`post_type_key`; to_field=`key` |
| sentiment | FK -> `SentimentKey` | `on_delete=PROTECT`; db_column=`sentiment`; to_field=`key` |

Indexes: `idx_pb_sig_b_p_type (brand_id, post_type_key)`,
`idx_pb_sig_b_sent (brand_id, sentiment)`

### PostBrandDiscourse (`posts_brands_discourse`)

Per-act pragmatics. Composite PK: `(post, brand, discourse, act_id)`.

| Field | Type | Notes |
|---|---|---|
| post | FK -> `Post` | `on_delete=CASCADE`; db_column=`post_id`; to_field=`tweet_id` |
| brand | FK -> `Brand` | `on_delete=PROTECT`; db_column=`brand_id`; to_field=`nickname` |
| discourse | FK -> `DiscourseKey` | `on_delete=PROTECT`; db_column=`discourse_key`; to_field=`key` |
| act_id | `PositiveSmallIntegerField` | distinguishes multiple speech-acts toward same brand (1..N) |
| china_nationalism | FK -> `NationalismKey` | `on_delete=PROTECT`; nullable; db_column=`china_nationalism`; to_field=`key` |
| us_nationalism | FK -> `NationalismKey` | `on_delete=PROTECT`; nullable; db_column=`us_nationalism`; to_field=`key` |

Indexes: `idx_post_brand_dis_b_dr (brand_id, discourse_key)`,
`idx_post_brand_dis_b_cn_nat (brand_id, china_nationalism)`,
`idx_post_brand_dis_b_us_nat (brand_id, us_nationalism)`

> **Sparse data note:** `china_nationalism` and `us_nationalism` are nullable;
> rows from the initial backfill window may have NULL values here.

### BrandCompany (`brands_companies`)

Composite PK: `(brand, company)`.

| Field | Type | Notes |
|---|---|---|
| brand | FK -> `Brand` | `on_delete=CASCADE`; db_column=`brand_id`; to_field=`nickname` |
| company | FK -> `Company` | `on_delete=CASCADE`; db_column=`company_id`; to_field=`nickname` |
| ownership_pct | `FloatField(default=1.0)` | |

### BrandAccount (`brands_accounts`)

Composite PK: `(brand, account)`.

| Field | Type | Notes |
|---|---|---|
| brand | FK -> `Brand` | `on_delete=CASCADE`; db_column=`brand_id`; to_field=`nickname` |
| account | FK -> `Account` | `on_delete=CASCADE`; db_column=`accounts_id`; to_field=`author_id` |
| role | FK -> `Role` | `on_delete=PROTECT`; db_column=`role_id`; to_field=`key` |
| added_at | `DateTimeField(auto_now_add)` | |

Indexes: `idx_brands_accounts_role_id (role_id)`

### CompanyAccount (`companies_accounts`)

Composite PK: `(company, account)`.

| Field | Type | Notes |
|---|---|---|
| company | FK -> `Company` | `on_delete=CASCADE`; db_column=`company_id`; to_field=`nickname` |
| account | FK -> `Account` | `on_delete=CASCADE`; db_column=`author_id`; to_field=`author_id` |
| role | FK -> `Role` | `on_delete=PROTECT`; db_column=`role_id`; to_field=`key` |
| added_at | `DateTimeField(auto_now_add)` | |

Indexes: `idx_companies_accounts_role_id (role_id)`

### BrandKeyword (`brand_keywords`)

Composite PK: `(brand, pattern)`.

| Field | Type | Notes |
|---|---|---|
| brand | FK -> `Brand` | `on_delete=CASCADE`; db_column=`brand_id`; to_field=`nickname` |
| pattern | `TextField` | keyword or regex pattern |
| is_regex | `BooleanField(default=False)` | |
| added_at | `DateTimeField(auto_now_add)` | |
| is_primary | `BooleanField(default=False)` | used by B-spec renderer to select primary subset per brand |

Indexes: `idx_brand_keywords_brand_id (brand_id)`

### BrandSearchTerm (`brand_search_terms`)

Composite PK: `(brand, term)`.

| Field | Type | Notes |
|---|---|---|
| brand | FK -> `Brand` | `on_delete=CASCADE`; db_column=`brand_id`; to_field=`nickname` |
| term | `TextField` | |
| added_at | `DateTimeField(auto_now_add)` | |

### BrandHashtag (`brand_hashtags`)

Composite PK: `(brand, hashtag)`.

| Field | Type | Notes |
|---|---|---|
| brand | FK -> `Brand` | `on_delete=CASCADE`; db_column=`brand_id`; to_field=`nickname` |
| hashtag | `TextField(db_column='tag')` | the tag string (without #) |
| added_at | `DateTimeField(auto_now_add)` | |

Indexes: `idx_brand_hashtags_brand_id (brand_id)`

### AccountPostAppearance (`account_post_appearances`)

Composite PK: `(account, post)`.

| Field | Type | Notes |
|---|---|---|
| account | FK -> `Account` | `on_delete=CASCADE`; db_column=`author_id`; to_field=`author_id` |
| post | FK -> `Post` | `on_delete=CASCADE`; db_column=`tweet_id`; to_field=`tweet_id` |
| role_at_time | `TextField` | nullable |
| source_query_ids | `TextField` | nullable |

Indexes: `idx_acct_post_app_post_id (tweet_id)`

---

## 3. Lookup tables

### Role (`roles`)

| Field | Type | Notes |
|---|---|---|
| key | `CharField(max_length=64, pk)` | case_insensitive; e.g. "official", "researcher", "executive" |
| created_at | `DateTimeField(auto_now_add)` | |

### RoleLabel (`role_labels`)

Composite PK: `(role, lang)`. FK role -> `Role`.

| Field | Type | Notes |
|---|---|---|
| role | FK -> `Role` | `on_delete=CASCADE`; db_column=`key`; to_field=`key` |
| lang | `TextField` | |
| label | `TextField` | |

### PostTypeKey (`post_type_keys`)

| Field | Type | Notes |
|---|---|---|
| key | `CharField(max_length=64, pk)` | case_insensitive; e.g. "release", "update", "review" |
| created_at | `DateTimeField(auto_now_add)` | |

### PostTypeLabel (`post_type_labels`)

Composite PK: `(post_type, lang)`. FK post_type -> `PostTypeKey`.

| Field | Type | Notes |
|---|---|---|
| post_type | FK -> `PostTypeKey` | `on_delete=CASCADE`; db_column=`key`; to_field=`key` |
| lang | `TextField` | |
| label | `TextField` | |

### SentimentKey (`sentiment_keys`)

| Field | Type | Notes |
|---|---|---|
| key | `CharField(max_length=64, pk)` | case_insensitive; e.g. "positive", "negative", "mixed", "neutral" |
| created_at | `DateTimeField(auto_now_add)` | |

### SentimentLabel (`sentiment_labels`)

Composite PK: `(sentiment, lang)`. FK sentiment -> `SentimentKey`.

| Field | Type | Notes |
|---|---|---|
| sentiment | FK -> `SentimentKey` | `on_delete=CASCADE`; db_column=`key`; to_field=`key` |
| lang | `TextField` | |
| label | `TextField` | |

### DiscourseKey (`discourse_keys`)

9-way pragmatic-register vocabulary.

| Field | Type | Notes |
|---|---|---|
| key | `CharField(max_length=64, pk)` | case_insensitive; e.g. "genuine_hype", "sarcasm", "dunk" |
| created_at | `DateTimeField(auto_now_add)` | |

### DiscourseLabel (`discourse_labels`)

Composite PK: `(discourse, lang)`. FK discourse -> `DiscourseKey`.

| Field | Type | Notes |
|---|---|---|
| discourse | FK -> `DiscourseKey` | `on_delete=CASCADE`; db_column=`key`; to_field=`key` |
| lang | `TextField` | |
| label | `TextField` | |

### NationalismKey (`nationalism_keys`)

6-step nationalism scale shared across both axes (china / us).

| Field | Type | Notes |
|---|---|---|
| key | `CharField(max_length=64, pk)` | case_insensitive; e.g. "none", "mild_pro", "pro", "constructive_critical", "anti", "mixed" |
| created_at | `DateTimeField(auto_now_add)` | |

### NationalismLabel (`nationalism_labels`)

Composite PK: `(nationalism, lang)`. FK nationalism -> `NationalismKey`.

| Field | Type | Notes |
|---|---|---|
| nationalism | FK -> `NationalismKey` | `on_delete=CASCADE`; db_column=`key`; to_field=`key` |
| lang | `TextField` | |
| label | `TextField` | |

### UnsanctionedFlagKey (`unsanctioned_flag_keys`)

Flag vocabulary lookup. No label table.

| Field | Type | Notes |
|---|---|---|
| key | `CharField(max_length=64, pk)` | case_insensitive |

---

## 4. Control plane

### CallState (`call_state`)

Cursor tracker for per-call brand harvest cycles. Composite PK:
`(brand_id, call_id, call_kind, bucket, query_id)`.

`brand_id` uses nickname slugs (e.g. `"deepseek"`) or `"*"` for fan-in. Not an
FK because call_state records may reference brands that were later removed.

| Field | Type | Notes |
|---|---|---|
| brand_id | `TextField` | nickname slug or `"*"` |
| call_id | `TextField` | e.g. "A", "B", "C1" |
| call_kind | `TextField` | "account" or "brand_wide" |
| bucket | `TextField(default='')` | nullable in legacy rows |
| query_id | `TextField` | |
| last_completed_at | `DateTimeField` | nullable; pipeline offsets by CURSOR_OVERLAP_HOURS before emitting `since=` |
| updated_at | `DateTimeField(auto_now)` | |

Indexes: `idx_call_state_completed_at (last_completed_at)`

### AppliedConfigSnapshot (`_applied_config_snapshot`)

| Field | Type | Notes |
|---|---|---|
| artifact | `TextField(pk)` | |
| content_hash | `TextField` | |
| written_at | `DateTimeField(auto_now_add)` | |

### SearchQuery (`search_queries`)

| Field | Type | Notes |
|---|---|---|
| id | `BigAutoField(pk)` | synthetic PK |
| query_id | `TextField(unique=True)` | |
| brand | FK -> `Brand` | `on_delete=SET_NULL`; nullable; db_column=`brand_id`; to_field=`nickname` |
| keywords | `JSONField(db_column='keywords_json')` | nullable |
| plan_calls_run_id | `TextField` | nullable |
| created_at | `DateTimeField(auto_now_add)` | |

Indexes: `idx_search_queries_brand_id (brand_id)`

---

## 5. Flags

### PostUnsanctionedFlag (`posts_unsanctioned_flags`)

| Field | Type | Notes |
|---|---|---|
| post | `OneToOneField(pk) -> Post` | `on_delete=CASCADE`; db_column=`post_id`; to_field=`tweet_id` |
| flags | `TextField` | JSON array of flag keys |
| flag_set | `JSONField` | nullable; extracted from flags |
| evidence | `TextField` | nullable |
| decided_at | `DateTimeField(auto_now_add)` | |

Indexes: `idx_unsanctioned_flag_set (flag_set)`

> **Sparse data note:** `flag_set` is nullable; it is populated by application
> code and may be NULL in rows that existed before the application-level
> backfill ran.

---

## Last reviewed: 2026-07-24

**Source-of-truth:** `core/models.py` (Django 5.2 ORM), migrations `core/migrations/` (range: 001-039 applied as of 2026-08-05).
All 32 models, their fields, types, FKs, indexes, and constraints were
cross-referenced against the model source and migration file and found to be
accurate.

**Key architectural decisions reflected in this schema:**

1. **Natural keys as PK** on Brand, Company, Account, Post, HFOrg, and all
   lookup tables -- no synthetic `id` columns.
2. **CompositePrimaryKey** on all junction and i18n-label tables -- no
   surrogate `id`.
3. **BigAutoField synthetic PK** retained only on `products` and
   `search_queries`.
4. **case_insensitive collation** on all `CharField` natural keys for
   case-insensitive equality at the database level.
5. **JSONField** replaces TEXT for structured payloads (`entities`, `raw`,
   `tags`, `siblings`, `card_data`, `config`, `spaces`, `keywords`,
   `flag_set`).
6. **on_delete semantics:** PROTECT on lookup FKs,
   CASCADE on owned junctions, SET_NULL on optional relationships.

---

## Last reviewed: 2026-07-31

Substantive corrections made during the 2026-07-31 review pass
(against `core/models.py`):

1. **`Post.quoted_status_id` was mis-typed.** Previously documented as
   `TextField` (nullable, plain column). It is actually a self-referential
   `ForeignKey("self")` with `on_delete=SET_NULL`, `db_constraint=True`,
   `related_name="quoted_by"`. Policy A semantics: NULL when the parent
   tweet was never harvested.
2. **`Post.raw` JSONField was removed from the schema.** Previously listed
   as `nullable; full tweet JSON`. The field has been retired — raw
   payloads are no longer snapshotted into `posts`. Consumers should rely
   on the § 1.2 / § 1.3 field set or re-fetch from TwitterAPI.
3. **`Post` table was missing the entire § 1.2 TwitterAPI top-level tweet
   fields section** (20 fields: `created_at_raw`, `bookmark_count`,
   `is_reply`, `is_retweet`, `is_quote`, `in_reply_to_id`,
   `in_reply_to_username`, `tweet_type`, `tweet_url`, `tweet_twitter_url`,
   `card`, `place`, `client_source`, `view_count`, `article`,
   `is_limited_reply`, `community_info`, `display_text_range`,
   `extended_entities`, `quoted_author_handle`). All nullable snapshots
   populated for tweets fetched via the TwitterAPI Advanced Search path.
4. **`Post` table was missing the entire § 1.3 TwitterAPI author fields
   section** (31 fields: `author_name`, `author_followers_count`,
   `author_following_count`, `author_verified`, `author_is_blue_verified`,
   `author_verified_type`, `author_is_translator`, `author_is_automated`,
   `author_automated_by`, `author_description`, `author_location`,
   `author_media_count`, `author_statuses_count`,
   `author_favourites_count`, `author_fast_followers_count`,
   `author_can_dm`, `author_can_media_tag`, `author_profile_picture`,
   `author_profile_bio`, `author_cover_picture`, `author_pinned_tweet_ids`,
   `author_affiliates_highlighted_label`,
   `author_withheld_in_countries`, `author_possibly_sensitive`,
   `author_has_custom_timelines`, `author_entities`, `author_twitter_url`,
   `author_type`, `author_url`, `author_created_at_raw`, `author_status`).
   These are per-fetch snapshots distinct from the slowly-updating
   `accounts` row.
5. **`Post` table grew from ~27 documented fields to ~76 fields.** Updated
   sparse-data note to reflect that § 1.2 / § 1.3 are nullable for tweets
   fetched before TwitterAPI harvesting was wired in.

All other tables (Brand, Company, HFOrg, Account, PostBrand,
PostBrandMention, PostBrandSignal, PostBrandDiscourse, BrandCompany,
BrandAccount, CompanyAccount, BrandKeyword, BrandSearchTerm, BrandHashtag,
AccountPostAppearance, all lookup tables, CallState, AppliedConfigSnapshot,
SearchQuery, Product, PostUnsanctionedFlag) verified accurate against
`core/models.py` — no changes.

Cross-checks performed: `db_table` Meta values, PK shapes (natural-key vs.
CompositePrimaryKey vs. BigAutoField), on_delete semantics
(PROTECT/CASCADE/SET_NULL), `db_column` overrides, `db_collation` on
natural keys, index definitions, JSONField `db_column` renames
(`tags_json`, `siblings_json`, `card_data_json`, `config_json`,
`spaces_json`, `raw_json`, `keywords_json`).

