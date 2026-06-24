# x-monitoring DB schema (ASCII)

`x-monitoring/data/x_monitoring.db`
(SQLite 3, ~36 MB on disk as of 2026-06-22, 4,191 rows in `posts`)

Source files: `x_monitor/migrations/00{1,2,3,4,5,6}_*.sql`
Migration ledger: `_migrations` (versions 1 / 2 / 3 / 4 / 5 / 6 applied on production; the redesigned migration 005 from the `feat/hf-products-crawler` worktree is not yet on production).

Conventions used in the diagrams:

- `PK` = PRIMARY KEY, `FK` = FOREIGN KEY
- `*` after a column = `NOT NULL`
- `d` suffix on PK/FK = descending direction
- A column annotated `JSON` is `TEXT` at the storage layer; the app parses it
- `1:N` lines below a table are explicit `FOREIGN KEY` declarations from the migration
- v1.8 introduces a `companies` / `brands` / `accounts` / `posts` model that
  replaces the v1.7 `model_id`-partitioned single-table layout. Model
  metadata is now DB-resident (was code-resident in v1.7).

---

## Tables

### `posts` (2,008 rows)

The core fact table. One row per kept tweet (after the per-model
relevance filter in Unit 4 of the v1.7 plan). In v1.8 the brand and
signal columns were dropped (moved to `posts_brands` /
`posts_brands_signals`); `favorite_count` was renamed to `like_count`
(per R9 / Decision 3, the user-facing name).

```
posts
├── tweet_id*           TEXT  PK                       ← Twitter/X status id (str)
├── author_handle*      TEXT                            ← @handle
├── author_id           TEXT                            ← numeric X user id (str), FK → accounts.author_id (logical only)
├── text                TEXT                            ← original post text
├── lang                TEXT                            ← X-declared BCP-47 (often wrong; see lang_detected)
├── created_at          TEXT                            ← ISO-8601 UTC
├── fetched_at*         TEXT                            ← ISO-8601 UTC, when the run ingested it
├── like_count          INTEGER  DEFAULT 0              ← (migration 004) renamed from favorite_count
├── retweet_count       INTEGER  DEFAULT 0
├── reply_count         INTEGER  DEFAULT 0
├── quote_count         INTEGER  DEFAULT 0
├── in_reply_to_user_id TEXT                            ← nullable
├── quoted_status_id    TEXT                            ← nullable
├── conversation_id     TEXT                            ← nullable
├── entities            TEXT  JSON                      ← X entities payload (mentions, urls, hashtags)
├── source_query_id     TEXT                            ← which search_queries row fetched this post (R6c storage fork)
├── raw                 TEXT  JSON                      ← full Apify response row, for replay
├── headline            TEXT                            ← (migration 002) article title from URL
├── headline_source     TEXT                            ← (migration 002) "fetched"|"cached"|"url_only"|"fetch_failed"
├── text_en             TEXT                            ← (migration 003) English translation
├── text_zh_cn          TEXT                            ← (migration 003) Simplified Chinese translation
└── lang_detected       TEXT                            ← (migration 003) post-fetch detected lang, e.g. "zh-Hans"
                                                         (migration 004 also backfills from existing text_en/text_zh_cn rows)
```

**DROPPED in v1.8 (migration 004):**

- `posts.model_id` (R1 / Decision 1) — brand attribution moves to
  `posts_brands`. There is no longer a `model_id` column anywhere in
  the `posts` schema. Migration 003's `idx_posts_model_created` and
  `idx_posts_signal_model` are dropped with the column.
- `posts.signal` (R6d) — per-brand signal moves to
  `posts_brands_signals`. A post naming 2 brands with different
  sentiments writes 2 rows there.

Indexes:

```
idx_posts_author                (author_handle)                     — handle lookups
idx_posts_headline_null_urlonly (tweet_id) WHERE headline IS NULL
                                            AND text GLOB 'https*'   — backfill subcommand
idx_posts_text_en_backfill      (tweet_id) WHERE text_en IS NULL
                                            AND lang_detected IS NOT NULL
                                            AND lang_detected NOT IN
                                                ('en','en-US','en-GB','und')   — (004) re-created w/ new predicate
idx_posts_text_zh_cn_backfill   (tweet_id) WHERE text_zh_cn IS NULL
                                            AND lang_detected IS NOT NULL
                                            AND lang_detected NOT IN
                                                ('zh','zh-CN','zh-Hans','zh-Hant','und')   — (004) re-created w/ new predicate
idx_posts_lang_detected         (lang_detected)                     — locale filtering
```

The 003-era `idx_posts_model_created`, `idx_posts_signal_model`,
`idx_posts_text_en_null`, and `idx_posts_text_zh_cn_null` indexes
are dropped in migration 004. The two text backfill indexes are
re-created with the new lang-aware predicates (Decision 8,
P1 review fix #30 — `'und'` is treated as eligible for both
translations).

---

### `accounts` (≥1 row; backfilled by migration 004 from `posts.author_id`)

Per-handle authoritative + community accounts. PK is now the
immutable X `author_id` (was `(model_id, handle)` in v1.7). The
per-account `role` column is gone (P1 review fix #15): multi-brand
accounts make per-account role meaningless; the per-brand role
lives in `brands_accounts.role`. `bio` + `bio_fetched_at` are new
(R13); `multi_brand_voice` is dropped (R12).

```
accounts
├── author_id*            TEXT  PK                       ← numeric X user id (str)
├── handle*               TEXT                           ← @handle (backfilled from posts; may be out of date)
├── display_name          TEXT                           ← resolved from X profile
├── bio                   TEXT                           ← (migration 004) X profile bio
├── bio_fetched_at        TEXT                           ← (migration 004) ISO-8601 when bio was last fetched
├── verified*             INTEGER DEFAULT 0              ← X blue-check flag
├── bio_contains_brand*   INTEGER DEFAULT 0              ← did the bio mention the brand?
├── engagement_tier*      TEXT  DEFAULT 'low'            ← "low" | "medium" | "high" (based on followers)
├── first_seen_at         TEXT
├── last_seen_at          TEXT
├── source_query_ids      TEXT                           ← which search_queries discovered this account
└── notes                 TEXT
```

**DROPPED in v1.8 (migration 004):**

- `accounts.model_id` (R13 / Decision 2) — brand/account edge lives
  in `brands_accounts` now.
- `accounts.role` — moved to `brands_accounts.role`.
- `accounts.multi_brand_voice` (R12).
- The composite PK `(model_id, handle)` is replaced by single-column
  `author_id PK`. Posts with `author_id IS NULL` are filtered out
  during the migration backfill; the migration loader logs them to
  `data/runs/<ts>/degraded_accounts.json`.

---

### `account_post_appearances` (0 rows; created by migration 004)

Join table: which accounts appeared on which posts. PK is now
`(author_id, tweet_id)` (was `(model_id, handle, tweet_id)` in
v1.7). Per Decision 4, `accounts.author_id` is the immutable X user
id, so the per-brand fan-in lives in `brands_accounts`, not in this
join.

```
account_post_appearances
├── author_id*     TEXT  PK[1]                   ← FK → accounts.author_id (logical only, no declared FK in 004)
├── tweet_id*      TEXT  PK[2]                   ← FK → posts.tweet_id  ON DELETE CASCADE
└── role_at_time   TEXT                          ← snapshot of the active brands_accounts.role at the time of appearance
```

Indexes:

```
(only the PK index — the v1.7 idx_apa_model is gone with the model_id column)
```

Foreign keys (declared in 004):

```
FOREIGN KEY(tweet_id) REFERENCES posts(tweet_id) ON DELETE CASCADE
```

The `FOREIGN KEY(author_id) REFERENCES accounts(author_id)` edge
is logical only (not declared) — the application enforces it.

---

### `companies` (10 rows; seeded by migration 004)

Corporate parents of the brand registry. Replaces the v1.7
"models live in code" approach with a DB-resident registry.

```
companies
├── company_id*   TEXT  PK                       ← e.g. "alibaba", "moonshot", "mistral_ai"
├── display_name* TEXT                           ← human-readable, e.g. "Alibaba"
├── hq_country    TEXT                           ← ISO-3166-1 alpha-2 (CN, FR, US, ...)
└── created_at*   TEXT                           ← ISO-8601 UTC
```

Seed rows (10):

```
company_id     display_name     hq_country
-----------    --------------   ----------
alibaba        Alibaba          CN
baidu          Baidu            CN
tencent        Tencent          CN
moonshot       Moonshot AI      CN
zhipu          Zhipu AI         CN
stepfun_inc    StepFun Inc      CN
xiaomi         Xiaomi           CN
mistral_ai     Mistral AI       FR
inclusion_ai   Inclusion AI     CN
deepseek_co    DeepSeek         CN
```

---

### `brands` (12 rows; seeded by migration 004)

Canonical brand registry. Replaces v1.7's `KNOWN_MODELS` frozenset
for DB reads. The `_unattributed` sentinel (`is_sentinel = 1`) is
the catch-all for posts that don't match any detection rule; the
treemap and grid filter it out at query time (Decision 15, P0
review fix).

```
brands
├── brand_id*      TEXT  PK                       ← e.g. "minimax", "qwen", "_unattributed"
├── display_name*  TEXT                           ← human-readable
├── accent_color*  TEXT  DEFAULT '#9ca3af'        ← hex color for the treemap card
├── is_sentinel*   INTEGER DEFAULT 0              ← 1 only for the "_unattributed" row
└── created_at*    TEXT                           ← ISO-8601 UTC
```

Seed rows (12 — 11 tracked brands + 1 sentinel):

```
brand_id         display_name          accent_color   is_sentinel
-----------      -------------------   ------------   -----------
minimax          MiniMax AI            #3b82f6        0
qwen             Qwen                  #f97316        0
deepseek         DeepSeek              #10b981        0
glm              Zhipu GLM             #a855f7        0
xiaomi_mimo      Xiaomi MiMo           #eab308        0
moonshot_kimi    Moonshot Kimi         #ec4899        0
inclusionai      InclusionAI           #06b6d4        0
mistral          Mistral               #facc15        0
stepfun          StepFun               #22c55e        0
ernie            Baidu ERNIE           #0ea5e9        0
hunyuan          Tencent Hunyuan       #ec4899        0
_unattributed    Unattributed          #6b7280        1
```

---

### `brands_companies` (10 rows; seeded by migration 004)

M:N edge between brands and corporate parents (Decision 2).
`ownership_pct` is `1.0` for wholly-owned brands; the column exists
for future joint ventures (e.g. a hypothetical `0.6`).

```
brands_companies
├── brand_id*       TEXT  PK[1]                ← FK → brands.brand_id    ON DELETE CASCADE
├── company_id*     TEXT  PK[2]                ← FK → companies.company_id ON DELETE CASCADE
└── ownership_pct*  REAL  DEFAULT 1.0
```

Seed rows (10 — one per tracked brand):

```
brand_id         company_id
-----------      -----------
qwen             alibaba
ernie            baidu
hunyuan          tencent
moonshot_kimi    moonshot
glm              zhipu
stepfun          stepfun_inc
xiaomi_mimo      xiaomi
mistral          mistral_ai
inclusionai      inclusion_ai
deepseek         deepseek_co
```

---

### `brands_accounts` (0 rows; application-seeded)

M:N edge between brands and accounts. The per-brand `role` lives
here (moved off `accounts.role` in v1.8; Decision 10).

```
brands_accounts
├── brand_id*   TEXT  PK[1]                 ← FK → brands.brand_id    ON DELETE CASCADE
├── author_id*  TEXT  PK[2]                 ← FK → accounts.author_id ON DELETE CASCADE
├── role*       TEXT  DEFAULT 'community'   ← "official" | "community" | "researcher" | "press" | "community"
└── added_at*   TEXT                         ← ISO-8601 UTC
```

Seeded by the application on the first run from
`data/brands/<brand>/accounts.yaml` (the migration loader does a
best-effort seed, but the application is authoritative).

---

### `companies_accounts` (0 rows; application-populated)

M:N edge between companies and accounts. Empty by design at
migration time (Scope Boundaries: "No new analytics"); the
application populates it on the first `account_graph` pass that
joins `accounts` → `brands_accounts` → `brands_companies`.

```
companies_accounts
├── company_id*  TEXT  PK[1]                ← FK → companies.company_id ON DELETE CASCADE
├── author_id*   TEXT  PK[2]                ← FK → accounts.author_id   ON DELETE CASCADE
├── role*        TEXT  DEFAULT 'community'   ← "official" | "community" | "researcher" | "press" | "community"
└── added_at*    TEXT                         ← ISO-8601 UTC
```

---

### `posts_brands` (≥0 rows; populated by `x_monitor.reattribute`)

Per-(post, brand) attribution with fractional weight (Decision 9,
Option C). `weight = 1.0 / N` for a post naming N distinct brands;
single-brand posts get `weight = 1.0`. Unattributed posts get a
sentinel row (`brand_id = '_unattributed'`, `weight = 1.0`) that
queries filter out via `is_sentinel`.

```
posts_brands
├── brand_id*  TEXT  PK[1]                 ← FK → brands.brand_id  ON DELETE SET NULL
├── post_id*   TEXT  PK[2]                 ← FK → posts.tweet_id   ON DELETE CASCADE
└── weight*    REAL  DEFAULT 1.0
```

Indexes:

```
idx_posts_brands_brand       (brand_id)               — per-brand scans
idx_posts_brands_brand_post  (brand_id, post_id)      — polarity JOIN (Decision 18, no IN subquery)
```

---

### `post_mentions` (≥0 rows; populated by `x_monitor.reattribute`)

Per-mention provenance: how was each brand named on each post?
The PK `(post_id, brand_id, source)` preserves the 4-source
decomposition (`user_mention | hashtag | body_keyword |
search_term`). Same brand named via 3 sources produces 3 rows.
The dedup key for polarity weight is `(post_id, brand_id)`,
enforced on `posts_brands`.

```
post_mentions
├── post_id*       TEXT  PK[1]              ← FK → posts.tweet_id   ON DELETE CASCADE
├── brand_id       TEXT  PK[2]              ← FK → brands.brand_id  ON DELETE SET NULL (nullable for un-attributed mentions)
├── source*        TEXT  PK[3]              ← user_mention | hashtag | body_keyword | search_term
├── raw_token*     TEXT                     ← literal matched text: "@MiniMaxAI", "#minimax", "M3.0", "from:minimax OR ..."
└── mentioned_at*  TEXT                     ← posts.created_at (ISO-8601 UTC)
```

Indexes:

```
idx_post_mentions_brand_source_recent  (brand_id, source, mentioned_at DESC)  — source-breakdown card
idx_post_mentions_post                 (post_id)                              — per-post mention lookup
```

---

### `posts_brands_signals` (≥2,008 rows; backfilled from `posts.signal` by migration 004)

Per-(post, brand) signal classification (R6d / Decision 18).
Replaces the v1.7 post-level `posts.signal` column. A post naming
2 brands with different sentiments writes 2 rows. The CHECK
constraint excludes the sentinel (Decision 15) — `_unattributed`
rows have no meaningful per-brand signal.

```
posts_brands_signals
├── post_id*   TEXT  PK[1]                 ← FK → posts.tweet_id   ON DELETE CASCADE
├── brand_id*  TEXT  PK[2]                 ← FK → brands.brand_id  ON DELETE SET NULL
└── signal*    TEXT                         ← release | community_question | criticism | commenter_capture | praise | other
                                             CHECK (brand_id <> '_unattributed')
```

Indexes:

```
idx_posts_brands_signals_brand_signal  (brand_id, signal)  — per-brand polarity aggregation
idx_posts_brands_signals_post          (post_id)          — per-post signal lookup
```

---

### `brand_hashtags` (≥0 rows; detection registry, R6a)

Detection registry: hashtags (lowercase, no `#` prefix) that
trigger a brand mention via the `hashtag` source.

```
brand_hashtags
├── brand_id*  TEXT  PK[1]                 ← FK → brands.brand_id  ON DELETE CASCADE
├── tag*       TEXT  PK[2]                 ← lowercase, no '#' prefix
└── added_at*  TEXT
```

---

### `brand_keywords` (≥0 rows; detection registry, R6b)

Detection registry: literal substrings or regex patterns that
trigger a brand mention via the `body_keyword` source. `is_regex`
is `0` for substring (case-insensitive contains) and `1` for
regex (RE2 syntax; the application validates on insert).

```
brand_keywords
├── brand_id*  TEXT  PK[1]                 ← FK → brands.brand_id  ON DELETE CASCADE
├── pattern*   TEXT  PK[2]                 ← substring or regex pattern
├── is_regex*  INTEGER DEFAULT 0           ← 0 = substring, 1 = regex
└── added_at*  TEXT
```

---

### `brand_search_terms` (≥0 rows; detection registry, R6c)

Detection registry: free-text search terms that triggered the
ingest (the original v1.7 plan_calls intents). The
`search_queries` table is the storage fork for these terms
keyed by `query_id`; `brand_search_terms` is the per-brand
discovery view.

```
brand_search_terms
├── brand_id*  TEXT  PK[1]                 ← FK → brands.brand_id  ON DELETE CASCADE
├── term*      TEXT  PK[2]
└── added_at*  TEXT
```

---

### `search_queries` (≥0 rows; populated by the ingest pipeline)

Search-query registry (R6c storage fork). Replaces the v1.7 soft
pointer from `posts.source_query_id` to
`data/queries/<id>.json` with a real DB row. `ON DELETE SET NULL`
on the FK from `posts.source_query_id` preserves posts when a
query is dropped; the application backfills `search_queries`
before applying the FK.

```
search_queries
├── query_id*          TEXT  PK              ← opaque id (was the filename in data/queries/)
├── brand_id*          TEXT                  ← FK → brands.brand_id  ON DELETE CASCADE
├── keywords_json*     TEXT  JSON            ← the OR-grouped query string
├── plan_calls_run_id  TEXT                  ← the run that produced this query (nullable)
└── created_at*        TEXT                  ← ISO-8601 UTC
```

---

## Pending (worktree-only) tables

The two tables in this section are part of the in-development HF products
crawler (branch `feat/hf-products-crawler`, worktree DB at
`worktrees/hf-products/x-monitoring/data/x_monitoring.db`). They are NOT
applied to the production `x-monitoring/data/x_monitoring.db` until that
work merges. The numbers, indexes, and FK behavior documented here
reflect the worktree DB.

### `hf_orgs` (11 rows; seeded by migration 005 on worktree DB only)

1:N edge from `companies` to HuggingFace namespaces. A real associative
entity, not a pure join table — it carries three attributes beyond the
FK pair (`confirmed`, `discovered_via`, `added_at`). `is_primary` was
dropped: with one company owning the org, all rows for that company are
equally canonical.

```
hf_orgs
├── id*              TEXT  PK                   ← HF namespace, e.g. "MiniMaxAI", "deepseek-ai"
├── company_id*      TEXT                       ← FK → companies.company_id  ON DELETE CASCADE
├── confirmed*       INTEGER DEFAULT 0          ← 1 = curated/operator-confirmed (scraped)
                                                    0 = runtime-discovered candidate (review)
├── discovered_via*  TEXT  DEFAULT 'curated'    ← 'curated' | 'search:<query>'
└── added_at*        TEXT                       ← ISO-8601 UTC
```

Seed rows (11 — one per company that has a corporate parent in
`companies`; the `_unattributed` brand is intentionally excluded — it
has no corporate parent and no HF coverage):

```
id              company_id     confirmed   discovered_via
------------    ------------   ----------  --------------
MiniMaxAI       minimax        1           curated
Qwen            alibaba        1           curated
THUDM           zhipu          1           curated
XiaomiMiMo      xiaomi         1           curated
baidu           baidu          1           curated
deepseek-ai     deepseek_co    1           curated
inclusionAI     inclusion_ai   1           curated
mistralai       mistral_ai     1           curated
moonshotai      moonshot       1           curated
stepfun-ai      stepfun_inc    1           curated
tencent         tencent        1           curated
```

Foreign keys:

```
FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE
```

Indexes:

```
idx_hf_orgs_company  (company_id)
```

Runtime writes go through `x_monitor.store.upsert_hf_org`, which never
demotes `confirmed = 1` rows and preserves `discovered_via = 'curated'`
when updating an existing curated edge. The HF-org resolution path
(`x_monitor.hf_products.resolve_hf_orgs`) is hybrid: it first reads from
this table (`confirmed_only=True`), and only if nothing is found does it
call `hf_client.search_organizations` and write new candidate edges
(`confirmed = 0`) for operator review — those are **flagged, not
scraped**, until promoted.

---

### `products` (509 rows on worktree DB; 0 on production)

The HuggingFace product catalog. One row per HF model (today);
`hf_type` is reserved by CHECK for future datasets and spaces.
Mirrors `posts` in spirit (a fact row + a brand FK + rich JSON columns)
but for HF artifacts instead of X posts.

```
products
├── repo_id*              TEXT  PK                   ← HF model id, e.g. "MiniMaxAI/MiniMax-M1"
├── brand_id              TEXT                       ← FK → brands.brand_id  ON DELETE SET NULL
├── hf_org_id             TEXT                       ← FK → hf_orgs.id       ON DELETE SET NULL
├── hf_type*              TEXT  DEFAULT 'model'      ← CHECK (hf_type IN ('model','dataset','space'))
├── display_name          TEXT                       ← repo name part (after the '/')
├── author                TEXT                       ← HF `author` field
├── sha                   TEXT                       ← git revision
├── private               INTEGER                    ← 0/1
├── gated                 TEXT                       ← 'auto' | 'manual' | 'false' | NULL
├── disabled              INTEGER                    ← 0/1
├── pipeline_tag          TEXT                       ← HF task, e.g. "text-generation"
├── library_name          TEXT                       ← e.g. "transformers"
├── downloads             INTEGER                    ← 30-day count (canonical public metric)
├── downloads_all_time    INTEGER                    ← not exposed by HF API (always NULL)
├── download_velocity     REAL                       ← not exposed by HF API (always NULL)
├── likes                 INTEGER
├── trending_score        REAL
├── paperswithcode_id     TEXT
├── created_at            TEXT                       ← HF ISO-8601
├── last_modified         TEXT                       ← HF ISO-8601
├── tags_json             TEXT  JSON                 ← HF tags array
├── siblings_json         TEXT  JSON                 ← [{rfilename[, size]}, ...]
├── card_data_json        TEXT  JSON                 ← license, language, base_model, …
├── config_json           TEXT  JSON                 ← architectures, model_type, quantization_config, …
├── spaces_json           TEXT  JSON                 ← dependent Spaces array
├── raw_json              TEXT  JSON                 ← verbatim HF ModelInfo payload (lossless archive)
├── collected_at*         TEXT                       ← ISO-8601; set on first upsert, stable
└── updated_at*           TEXT                       ← ISO-8601; rewritten on every upsert
```

`brand_id` uses `ON DELETE SET NULL`; `hf_org_id` also uses `ON DELETE
SET NULL` (added in the redesigned migration 005). The crawl path is
brand → company (via `brands_companies`) → HF orgs (via `hf_orgs`) →
products, so a single company can produce rows for each of its brands.

Foreign keys:

```
FOREIGN KEY(brand_id)  REFERENCES brands(brand_id)  ON DELETE SET NULL
FOREIGN KEY(hf_org_id) REFERENCES hf_orgs(id)       ON DELETE SET NULL
```

Indexes:

```
idx_products_brand       (brand_id)
idx_products_hf_org_id    (hf_org_id)
```

**Stable vs mutable columns.** `repo_id`, `brand_id`, `hf_org_id`,
`hf_type`, `display_name`, `author`, `created_at`, `collected_at` are
identity-stable — re-running the crawler does not touch them. Everything
else (`sha`, `downloads`, `likes`, `last_modified`, the `*_json`
columns, `updated_at`) is refreshed on each upsert via
`store.upsert_product`'s `ON CONFLICT(repo_id) DO UPDATE SET` clause.

**`hf_type` CHECK constraint.** The CHECK
(`'model' | 'dataset' | 'space'`) is enforced at INSERT — invalid
artifact kinds fail at the upsert, not silently downstream. Today's
crawler only emits `hf_type = 'model'`; the dataset/space arms are
reserved by the constraint for when the crawler is extended.

**List vs detail.** The HF list endpoint
(`/api/models?author=…&full=true`) is lean: it returns downloads /
likes / tags / siblings / pipeline_tag / library_name / sha /
timestamps only. The license, base_model, language, architectures,
model_type, quantization_config, and dependent Spaces are populated by
a per-model `GET /api/models/{id}` call and persisted as JSON text
columns so new fields can be added without re-scraping.
`downloads_all_time` and `download_velocity` are **not** exposed by
the HF API at all and stay NULL.

---

### `_migrations` (4 rows)

Tracks which SQL files have been applied. Written by
`x_monitor/store.py::_apply_migration`.

```
_migrations
├── version*    INTEGER  PK                   ← matches the "00N_" prefix on the migration filename
└── applied_at* TEXT                          ← ISO-8601 timestamp with offset (e.g. "2026-06-19T06:41:47+00:00")
```

Rows currently in this DB:

```
version  applied_at
-------  -------------------
1        2026-06-08T22:53:57+00:00    ← 001_initial.sql
2        2026-06-11T05:52:02+00:00    ← 002_post_headline.sql
3        2026-06-17T04:22:26+00:00    ← 003_translation_columns.sql
4        2026-06-19T06:41:47+00:00    ← 004_company_brand_account_model.sql
```

---

## Relationships (ER overview)

```
                ┌──────────────────────────────┐
                │           posts              │
                │ tweet_id PK, author_id, ...  │
                └─┬─────────────┬─────────────┬┘
                  │ 1           │ 1           │ 1
                  │             │             │
                  │ N           │ N           │ N
   ┌──────────────▼──┐  ┌───────▼────────┐  ┌▼────────────────────┐
   │ posts_brands     │  │ post_mentions  │  │ posts_brands_signals  │
   │ PK (brand,post) │  │ PK (post,brand,│  │ PK (post,brand)     │
   │ FK → brands     │  │     source)    │  │ FK → posts          │
   │ FK → posts      │  │ FK → posts     │  │ FK → brands         │
   │   (weight)      │  │ FK → brands    │  │   (signal)          │
   └──────┬──────────┘  └────┬────────────┘  └──────┬──────────────┘
          │ N                │ N                    │ N
          │                  │                      │
          │ 1                │ 1                    │ 1
          └────────┬─────────┴──────────────────────┘
                   │
                   ▼
              ┌─────────┐
              │ brands  │  (12 rows; sentinel _unattributed is_sentinel=1)
              └────┬────┘
                   │ 1
                   │
   ┌───────────────┼─────────────────┬──────────────────────┐
   │ N             │ N               │ N                    │ N
   ▼               ▼                 ▼                      ▼
┌────────┐  ┌────────────┐   ┌──────────────┐    ┌──────────────────┐
│brands_ │  │brands_     │   │brand_        │    │ brand_search_    │
│companies│ │accounts    │   │hashtags /    │    │ terms            │
│PK(b,c) │  │PK(b,a)     │   │keywords      │    │ PK (brand, term) │
│FK→brand│  │FK→brand    │   │PK (brand, *) │    │ FK → brands      │
│FK→comp │  │FK→accounts │   │FK → brands   │    │                  │
└───┬────┘  └─────┬──────┘   └──────────────┘    └──────────────────┘
    │ N          │ N
    │            │
    │ 1          │ 1
┌───▼────┐  ┌────▼──────────┐
│companies│  │  accounts     │
│PK id    │  │ PK author_id  │
│(10 rows)│  │  (≥1 row)     │
└────┬────┘  └────┬──────────┘
     │            │
     │ 1          │ 1
     │            │
     │ N          │ N
┌────▼────────────▼────┐
│ companies_accounts     │
│ PK (company, author) │
│ FK → companies       │
│ FK → accounts        │
└──────────────────────┘

                ┌──────────────────────────────┐
                │ search_queries               │
                │ PK query_id                  │
                │ FK → brands                  │
                └──────────────────────────────┘
                         (posts.source_query_id is a soft pointer here;
                          no declared FK, so query rows can be dropped
                          without losing posts)

                ┌────────────────────────────────┐
                │ account_post_appearances       │
                │ PK (author_id, tweet_id)       │
                │ FK → posts.tweet_id            │
                │   ON DELETE CASCADE            │
                │   (FK → accounts is logical)   │
                └────────────────────────────────┘
```

Logical (un-FK'd) edges:

- `posts.author_id` → `accounts.author_id`. The migration does not
  declare this FK on `posts` (it would block the 004 backfill that
  inserts `accounts` rows from `posts.author_id`). The application
  enforces it. Likewise `account_post_appearances.author_id` is
  not a declared FK to `accounts.author_id`.
- `posts.source_query_id` → `search_queries.query_id`. Soft
  pointer; `ON DELETE SET NULL` semantics are achieved by the
  application setting the column to NULL when a query row is
  removed, not by a real FK.
- `_unattributed` brand rows. They are seeded into `brands`
  (`is_sentinel = 1`), they appear in `posts_brands` for
  un-attributed posts (filtered at query time), but they NEVER
  appear in `posts_brands_signals` (CHECK constraint enforces this).
  They are the only `brand_id` values that should not be rendered
  on the treemap or grid.
- Brand source priority (R2): `user_mention` + `hashtag` are
  higher confidence than `body_keyword` + `search_term`. Multi-
  source matches take the max confidence across contributing
  sources. This is enforced by the application, not the schema.
- `posts_brands_signals.signal` enum:
  `"release" | "community_question" | "criticism" | "commenter_capture" | "praise" | "other"`.
  Identical to the v1.7 `posts.signal` enum, just lifted off the
  post level and replicated per (post, brand).
- `post_mentions.source` enum:
  `"user_mention" | "hashtag" | "body_keyword" | "search_term"`.
- `posts.headline_source` enum (v1.7, unchanged):
  `"fetched" | "cached" | "url_only" | "fetch_failed"`.
- The `models` table that v1.7 lacked is now `brands` (the
  canonical registry) + `companies` (the corporate parents). The
  dashboard reads brand colors from `brands.accent_color` instead
  of `MODEL_ACCENT_COLORS` in `treemap.py`.
- `account_post_appearances` is no longer the multi-account fan-in
  for brand attribution. That role moved to `posts_brands` +
  `post_mentions` + `posts_brands_signals` (one row per detected
  brand per post). `account_post_appearances` is now the
  per-account appearance log (which accounts posted or were
  mentioned on which tweets), populated lazily by
  `account_graph`.

---

## Migration history

```
001_initial.sql
   ├── CREATE posts                (12 base columns + raw/entities JSON)
   ├── CREATE accounts             (12 columns, PK = model_id + handle)
   ├── CREATE account_post_appearances  (3-col PK, 2 FKs)
   └── 3 supporting indexes

002_post_headline.sql
   ├── ALTER posts +headline TEXT
   ├── ALTER posts +headline_source TEXT
   └── CREATE idx_posts_headline_null_urlonly (partial)

003_translation_columns.sql
   ├── ALTER posts +text_en TEXT
   ├── ALTER posts +text_zh_cn TEXT
   ├── ALTER posts +lang_detected TEXT
   ├── ALTER posts +signal TEXT
   └── 4 indexes (2 partial for backfill + 2 full)

004_company_brand_account_model.sql
   ├── CREATE companies           (10 seed rows)
   ├── CREATE brands              (12 seed rows incl. _unattributed sentinel)
   ├── CREATE brands_companies     (10 seed rows; M:N brand ↔ company)
   ├── CREATE brands_accounts      (M:N brand ↔ accounts; role per brand)
   ├── CREATE companies_accounts    (M:N company ↔ accounts; empty at migration time)
   ├── CREATE posts_brands         (M:N post ↔ brand with fractional weight)
   ├── CREATE post_mentions       (per-source mention provenance; 4 sources)
   ├── CREATE posts_brands_signals  (per-brand signal; replaces posts.signal)
   ├── CREATE brand_hashtags      (R6a detection registry)
   ├── CREATE brand_keywords      (R6b detection registry; substring or regex)
   ├── CREATE brand_search_terms  (R6c detection registry)
   ├── CREATE search_queries      (R6c storage fork; replaces soft pointer)
   ├── INSERT posts_brands_signals  (backfill from posts.model_id + posts.signal)
   ├── UPDATE posts lang_detected (backfill from text_en/text_zh_cn rows)
   ├── DROP INDEX idx_posts_model_created
   ├── DROP INDEX idx_posts_signal_model
   ├── DROP INDEX idx_posts_text_en_null
   ├── DROP INDEX idx_posts_text_zh_cn_null
   ├── ALTER posts RENAME COLUMN favorite_count TO like_count
   ├── ALTER posts DROP COLUMN model_id
   ├── ALTER posts DROP COLUMN signal
   ├── DROP + CREATE accounts            (PK = author_id; role & multi_brand_voice dropped; bio + bio_fetched_at added)
   ├── DROP + CREATE account_post_appearances  (PK = (author_id, tweet_id); only posts FK remains)
   ├── INSERT accounts            (backfill from distinct posts.author_id + author_handle)
   ├── CREATE idx_posts_text_en_backfill     (lang-aware predicate; 004)
   ├── CREATE idx_posts_text_zh_cn_backfill  (lang-aware predicate; 004)
   ├── CREATE idx_posts_brands_brand          (single-column per-brand)
   ├── CREATE idx_posts_brands_brand_post     (polarity JOIN)
   ├── CREATE idx_post_mentions_brand_source_recent  (source-breakdown card)
   ├── CREATE idx_post_mentions_post
   ├── CREATE idx_posts_brands_signals_brand_signal
   └── CREATE idx_posts_brands_signals_post
```

The `posts` table grew in two stages and then SHRANK in v1.8:
- **v1.2 (migration 002):** article headlines for URL-only posts
- **v1.7 (migration 003):** LLM translation columns + post-fetch signal classification
- **v1.8 (migration 004):** dropped `model_id` + `signal` (moved to
  join tables); renamed `favorite_count` → `like_count`; tightened
  the translation backfill indexes with lang-aware predicates.
