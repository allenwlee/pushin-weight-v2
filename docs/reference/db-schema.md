# x-monitoring DB schema

`x-monitoring/data/x_monitoring.db` (SQLite 3; live, generated via `sqlite3 .schema`)

![x-monitor schema after migration batch 011-023](images/xmonitor-schema-post-batch.png)

*This image is generated from [`docs/reference/schema.dot`](schema.dot) via [`scripts/build_schema_image.sh`](../../scripts/build_schema_image.sh) — regenerate after any migration change.*

## Tables

### `_migrations`

| Column | Type | Notes |
|---|---|---|
| version | INTEGER | PRIMARY KEY |
| applied_at | TEXT | NOT NULL |

### `account_post_appearances`

| Column | Type | Notes |
|---|---|---|
| author_id | TEXT | NOT NULL; PK[1] |
| tweet_id | TEXT | NOT NULL; PK[2]; FK → posts(tweet_id) ON DELETE CASCADE |
| role_at_time | TEXT | |

### `accounts`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| author_id | TEXT | NOT NULL UNIQUE |
| handle | TEXT | |
| display_name | TEXT | |
| bio | TEXT | |
| bio_fetched_at | TEXT | |
| verified | INTEGER | |
| bio_contains_brand | INTEGER | |
| first_seen_at | TEXT | |
| last_seen_at | TEXT | |
| source_query_ids | TEXT | |
| notes | TEXT | |
| bio_en | TEXT | |
| bio_zh_cn | TEXT | |

Indexes: `idx_accounts_author_id (author_id)`, `idx_accounts_handle (handle)`

### `brand_hashtags`

| Column | Type | Notes |
|---|---|---|
| brand_id | TEXT | NOT NULL; PK[1]; FK → brands(nickname) ON DELETE CASCADE |
| tag | TEXT | NOT NULL; PK[2] |
| added_at | TEXT | NOT NULL |

### `brand_keywords`

| Column | Type | Notes |
|---|---|---|
| brand_id | TEXT | NOT NULL; PK[1]; FK → brands(nickname) ON DELETE CASCADE |
| pattern | TEXT | NOT NULL; PK[2] |
| is_regex | INTEGER | NOT NULL DEFAULT 0 |
| added_at | TEXT | NOT NULL |

### `brand_search_terms`

| Column | Type | Notes |
|---|---|---|
| brand_id | INTEGER | NOT NULL; PK[1]; FK → brands(id) ON DELETE CASCADE |
| term | TEXT | NOT NULL; PK[2] |
| added_at | TEXT | |

### `brands`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| nickname | TEXT | NOT NULL UNIQUE |
| display_name | TEXT | |
| accent_color | TEXT | |
| is_sentinel | INTEGER | |
| created_at | TEXT | |
| display_name_en | TEXT | |
| display_name_zh_cn | TEXT | |

Indexes: `idx_brands_nickname (nickname)`

### `brands_accounts`

| Column | Type | Notes |
|---|---|---|
| brand_id | INTEGER | NOT NULL; PK[1]; FK → brands(id) ON DELETE CASCADE |
| author_id | INTEGER | NOT NULL; PK[2]; FK → accounts(id) ON DELETE CASCADE |
| role_id | INTEGER | NOT NULL; FK → roles(id) ON DELETE RESTRICT |
| added_at | TEXT | |

Indexes: `idx_brands_accounts_role_id (role_id)`

### `brands_companies`

| Column | Type | Notes |
|---|---|---|
| brand_id | INTEGER | NOT NULL; PK[1]; FK → brands(id) ON DELETE CASCADE |
| company_id | INTEGER | NOT NULL; PK[2]; FK → companies(id) ON DELETE CASCADE |
| ownership_pct | REAL | |

### `companies`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| nickname | TEXT | NOT NULL UNIQUE |
| display_name | TEXT | |
| hq_country | TEXT | |
| created_at | TEXT | |
| display_name_en | TEXT | |
| display_name_zh_cn | TEXT | |

Indexes: `idx_companies_nickname (nickname)`

### `companies_accounts`

| Column | Type | Notes |
|---|---|---|
| company_id | INTEGER | NOT NULL; PK[1]; FK → companies(id) ON DELETE CASCADE |
| author_id | INTEGER | NOT NULL; PK[2]; FK → accounts(id) ON DELETE CASCADE |
| role_id | INTEGER | NOT NULL; FK → roles(id) ON DELETE RESTRICT |
| added_at | TEXT | |

Indexes: `idx_companies_accounts_role_id (role_id)`

### `discourse_keys`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| key | TEXT | NOT NULL UNIQUE |
| created_at | TEXT | NOT NULL |

### `discourse_labels`

| Column | Type | Notes |
|---|---|---|
| key | TEXT | NOT NULL; PK[1]; FK → discourse_keys(key) ON DELETE CASCADE |
| lang | TEXT | NOT NULL; PK[2] |
| label | TEXT | NOT NULL |

### `hf_orgs`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| namespace | TEXT | NOT NULL UNIQUE |
| company_id | INTEGER | NOT NULL; FK → companies(id) ON DELETE CASCADE |
| confirmed | INTEGER | NOT NULL DEFAULT 0 |
| discovered_via | TEXT | NOT NULL DEFAULT 'curated' |
| added_at | TEXT | NOT NULL |

Indexes: `idx_hf_orgs_namespace (namespace)`, `idx_hf_orgs_company (company_id)`

### `nationalism_keys`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| key | TEXT | NOT NULL UNIQUE |
| created_at | TEXT | NOT NULL |

### `nationalism_labels`

| Column | Type | Notes |
|---|---|---|
| key | TEXT | NOT NULL; PK[1]; FK → nationalism_keys(key) ON DELETE CASCADE |
| lang | TEXT | NOT NULL; PK[2] |
| label | TEXT | NOT NULL |

### `post_type_keys`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| key | TEXT | NOT NULL UNIQUE |
| created_at | TEXT | NOT NULL |

### `post_type_labels`

| Column | Type | Notes |
|---|---|---|
| key | TEXT | NOT NULL; PK[1]; FK → post_type_keys(key) ON DELETE CASCADE |
| lang | TEXT | NOT NULL; PK[2] |
| label | TEXT | NOT NULL |

### `posts`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| tweet_id | TEXT | NOT NULL UNIQUE |
| author_handle | TEXT | |
| author_id | INTEGER | FK → accounts(id) ON DELETE SET NULL |
| text | TEXT | |
| lang | TEXT | |
| created_at | TEXT | |
| fetched_at | TEXT | |
| like_count | INTEGER | |
| retweet_count | INTEGER | |
| reply_count | INTEGER | |
| quote_count | INTEGER | |
| in_reply_to_user_id | TEXT | |
| quoted_status_id | TEXT | |
| conversation_id | TEXT | |
| entities | TEXT | |
| source_query_id | TEXT | |
| raw | TEXT | |
| headline | TEXT | |
| headline_source | TEXT | |
| text_en | TEXT | |
| text_zh_cn | TEXT | |
| lang_detected | TEXT | |
| quoted_text | TEXT | |
| last_quote_count_seen | INTEGER | |
| last_quote_fetched_at | TEXT | |
| created_at_epoch | INTEGER | |

Indexes: `idx_posts_tweet_id (tweet_id)`, `idx_posts_author_id (author_id)`, `idx_posts_headline_null_urlonly (id) WHERE headline IS NULL AND text GLOB 'https*'`, `idx_posts_text_en_null (id) WHERE text_en IS NULL`, `idx_posts_text_zh_cn_null (id) WHERE text_zh_cn IS NULL`, `idx_posts_lang_detected (lang_detected)`, `idx_posts_source_query_id (source_query_id)`, `idx_posts_created_at_epoch (created_at_epoch)`

### `posts_brands`

| Column | Type | Notes |
|---|---|---|
| post_id | INTEGER | NOT NULL; PK[1]; FK → posts(id) ON DELETE CASCADE |
| brand_id | INTEGER | NOT NULL; PK[2]; FK → brands(id) ON DELETE SET NULL |
| weight | REAL | |

Indexes: `idx_posts_brands_brand_id (brand_id)`

### `posts_brands_discourse`

| Column | Type | Notes |
|---|---|---|
| post_id | INTEGER | NOT NULL; PK[1]; FK → posts(id) ON DELETE CASCADE |
| brand_id | INTEGER | NOT NULL; PK[2]; FK → brands(id) ON DELETE SET NULL |
| discourse_key | INTEGER | NOT NULL; PK[3]; FK → discourse_keys(id) ON DELETE RESTRICT |
| act_id | INTEGER | NOT NULL; PK[4]; CHECK (act_id BETWEEN 1 AND 99) |
| china_nationalism | INTEGER | FK → nationalism_keys(id) ON DELETE RESTRICT |
| us_nationalism | INTEGER | FK → nationalism_keys(id) ON DELETE RESTRICT |

Indexes: `idx_post_brand_dis_b_dr (brand_id, discourse_key)`, `idx_post_brand_dis_b_cn_nat (brand_id, china_nationalism)`, `idx_post_brand_dis_b_us_nat (brand_id, us_nationalism)`

### `posts_brands_mentions`

| Column | Type | Notes |
|---|---|---|
| post_id | INTEGER | NOT NULL; PK[1]; FK → posts(id) ON DELETE CASCADE |
| brand_id | INTEGER | PK[2]; FK → brands(id) ON DELETE SET NULL |
| source | TEXT | NOT NULL; PK[3] |
| raw_token | TEXT | |
| mentioned_at | TEXT | |

### `posts_brands_signals`

| Column | Type | Notes |
|---|---|---|
| post_id | TEXT | NOT NULL; PK[1]; FK → posts(tweet_id) ON DELETE CASCADE |
| brand_id | TEXT | NOT NULL; PK[2]; FK → brands(nickname) ON DELETE SET NULL; CHECK (brand_id <> '_unattributed') |
| post_type_key | TEXT | NOT NULL; PK[3]; FK → post_type_keys(key) ON DELETE RESTRICT |
| sentiment | TEXT | FK → sentiment_keys(key) ON DELETE RESTRICT |

Indexes: `idx_posts_brands_signals_brand_id_post_type_key (brand_id, post_type_key)`, `idx_posts_brands_signals_brand_id_sentiment (brand_id, sentiment)`

### `posts_unsanctioned_flags`

| Column | Type | Notes |
|---|---|---|
| post_id | TEXT | NOT NULL; PRIMARY KEY; FK → posts(tweet_id) ON DELETE CASCADE |
| flags | TEXT | NOT NULL |
| flag_set | TEXT | GENERATED ALWAYS AS (json_extract(flags, '$')) STORED |
| evidence | TEXT | |
| decided_at | TEXT | NOT NULL |

Indexes: `idx_unsanctioned_flag_set (flag_set)`

### `products`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| repo_id | TEXT | NOT NULL UNIQUE |
| brand_id | INTEGER | FK → brands(id) ON DELETE SET NULL |
| hf_org_id | INTEGER | FK → hf_orgs(id) ON DELETE SET NULL |
| hf_type | TEXT | NOT NULL DEFAULT 'model'; CHECK (hf_type IN ('model','dataset','space')) |
| display_name | TEXT | |
| author | TEXT | |
| sha | TEXT | |
| private | INTEGER | |
| gated | TEXT | |
| disabled | INTEGER | |
| pipeline_tag | TEXT | |
| library_name | TEXT | |
| downloads | INTEGER | |
| downloads_all_time | INTEGER | |
| download_velocity | REAL | |
| likes | INTEGER | |
| trending_score | REAL | |
| paperswithcode_id | TEXT | |
| created_at | TEXT | |
| last_modified | TEXT | |
| tags_json | TEXT | |
| siblings_json | TEXT | |
| card_data_json | TEXT | |
| config_json | TEXT | |
| spaces_json | TEXT | |
| raw_json | TEXT | |
| collected_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

Indexes: `idx_products_repo_id (repo_id)`, `idx_products_brand (brand_id)`, `idx_products_hf_org_id (hf_org_id)`

### `role_labels`

| Column | Type | Notes |
|---|---|---|
| key | TEXT | NOT NULL; PK[1]; FK → roles(key) ON DELETE CASCADE |
| lang | TEXT | NOT NULL; PK[2] |
| label | TEXT | NOT NULL |

### `roles`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| key | TEXT | NOT NULL UNIQUE |
| created_at | TEXT | NOT NULL |

### `search_queries`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| query_id | TEXT | NOT NULL UNIQUE |
| brand_id | INTEGER | FK → brands(id) ON DELETE SET NULL |
| keywords_json | TEXT | |
| plan_calls_run_id | TEXT | |
| created_at | TEXT | |

Indexes: `idx_search_queries_query_id (query_id)`, `idx_search_queries_brand_id (brand_id)`

### `sentiment_keys`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| key | TEXT | NOT NULL UNIQUE |
| created_at | TEXT | NOT NULL |

### `sentiment_labels`

| Column | Type | Notes |
|---|---|---|
| key | TEXT | NOT NULL; PK[1]; FK → sentiment_keys(key) ON DELETE CASCADE |
| lang | TEXT | NOT NULL; PK[2] |
| label | TEXT | NOT NULL |