# x-monitoring DB schema (ASCII)

`x-monitoring/data/x_monitoring.db`
(SQLite 3, ~36 MB on disk as of 2026-06-22, **4,191 rows in `posts`**)

Source files: `x_monitor/migrations/00{1,2,3,4,5,6}_*.sql`
Migration ledger: `_migrations` (**6 rows** — versions 1–6 applied).

```
version  applied_at                 migration
-------  -------------------------  ----------------------------------------
1        2026-06-08T22:53:57+00:00  001_initial.sql
2        2026-06-11T05:52:02+00:00  002_post_headline.sql
3        2026-06-17T04:22:26+00:00  003_translation_columns.sql
4        2026-06-19T06:41:47+00:00  004_company_brand_account_model.sql
5        2026-06-22T01:59:44+00:00  005_quoted_text.sql
6        2026-06-22T05:03:47+00:00  006_quote_capture_tracking.sql
```

> **Two parallel "005"s.** Production migration 005 is
> `005_quoted_text.sql` (a 1-line `ALTER TABLE posts ADD COLUMN
> quoted_text TEXT` for quote-tweet content capture, branch
> `feat/capture-quote-tweets`). A *different* migration also named
> `005_products.sql` exists on the `feat/hf-products-crawler`
> worktree (`worktrees/hf-products/x-monitoring/`); it adds
> `brand_hf_orgs` + `products` and is the in-development PR #6
> feature. They don't collide because they live on different
> branches — only `005_quoted_text.sql` has been applied to the
> production DB. See `docs/reference/minimax-hf-products-2026-06-22.md`
> for the HF product catalog data; plan at
> `docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md`.
>
> **`brand_hf_orgs` and `products` are NOT documented as production
> tables.** They live only on the worktree DB. They are described
> in the "Pending (worktree-only) tables" section below; the row
> counts, indexes, and FK behavior there reflect the worktree DB,
> not production.

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

### `posts` (4,191 rows)

The core fact table. One row per kept tweet (after the per-model
relevance filter in Unit 4 of the v1.7 plan). In v1.8 the brand and
signal columns were dropped (moved to `post_brands` /
`post_brand_signals`); `favorite_count` was renamed to `like_count`
(per R9 / Decision 3, the user-facing name). Migrations 005 and 006
added quote-tweet content + capture-tracking columns
(`feat/capture-quote-tweets`).

```
posts
├── tweet_id*              TEXT  PK                       ← Twitter/X status id (str)
├── author_handle*         TEXT                            ← @handle
├── author_id              TEXT                            ← numeric X user id (str), FK → accounts.author_id (logical only)
├── text                   TEXT                            ← original post text
├── lang                   TEXT                            ← X-declared BCP-47 (often wrong; see lang_detected)
├── created_at             TEXT                            ← Twitter-format created_at (string; sorts incorrectly for time-window queries — see created_at_epoch)
├── fetched_at*            TEXT                            ← ISO-8601 UTC, when the run ingested it
├── like_count             INTEGER  DEFAULT 0              ← (migration 004) renamed from favorite_count
├── retweet_count          INTEGER  DEFAULT 0
├── reply_count            INTEGER  DEFAULT 0
├── quote_count            INTEGER  DEFAULT 0
├── in_reply_to_user_id    TEXT                            ← nullable
├── quoted_status_id       TEXT                            ← nullable; populated for quote tweets (also see quoted_text)
├── conversation_id        TEXT                            ← nullable
├── entities               TEXT  JSON                      ← X entities payload (mentions, urls, hashtags)
├── source_query_id        TEXT                            ← which search_queries row fetched this post (R6c storage fork)
├── raw                    TEXT  JSON                      ← full Apify response row, for replay
├── headline               TEXT                            ← (migration 002) article title from URL
├── headline_source        TEXT                            ← (migration 002) "fetched"|"cached"|"url_only"|"fetch_failed"
├── text_en                TEXT                            ← (migration 003) English translation
├── text_zh_cn             TEXT                            ← (migration 003) Simplified Chinese translation
├── lang_detected          TEXT                            ← (migration 003) post-fetch detected lang, e.g. "zh-Hans"
                                                              (migration 004 also backfills from existing text_en/text_zh_cn rows)
├── quoted_text            TEXT                            ← (migration 005) quoted tweet's text (was held in memory & discarded pre-005)
├── last_quote_count_seen* INTEGER  DEFAULT 0              ← (migration 006) most recent quote_count observed on this post
├── last_quote_fetched_at  TEXT                            ← (migration 006) ISO-8601; seeds sinceTime for next /twitter/tweet/quotes call
└── created_at_epoch       INTEGER                         ← (migration 006) unix-second epoch parsed from Twitter-format created_at
                                                              (existing rows backfilled by scripts/2026-06-22-140225-backfill-created-at-epoch.py;
                                                              SQLite can't parse the Twitter format in pure SQL)
```

**DROPPED in v1.8 (migration 004):**

- `posts.model_id` (R1 / Decision 1) — brand attribution moves to
  `post_brands`. There is no longer a `model_id` column anywhere in
  the `posts` schema. Migration 003's `idx_posts_model_created` and
  `idx_posts_signal_model` are dropped with the column.
- `posts.signal` (R6d) — per-brand signal moves to
  `post_brand_signals`. A post naming 2 brands with different
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

> **Known drift on production (2026-06-22):** migration 006 also
> creates `idx_posts_created_at_epoch (created_at_epoch)` for the
> polarity time-window filter and the QT daily-pass recency query,
> but **this index is missing from the production DB** even though
> the migration's `INSERT INTO _migrations` row is present (verified
> 2026-06-22 via `SELECT name FROM sqlite_master`). The polarity
> query path can therefore SCAN `posts` until the index is
> recreated. Recreate with:
> `CREATE INDEX IF NOT EXISTS idx_posts_created_at_epoch ON posts(created_at_epoch);`
> (matches the `006_quote_capture_tracking.sql` declaration).

---

### `accounts` (1,522 rows; backfilled by migration 004 from `posts.author_id`)

Per-handle authoritative + community accounts. PK is now the
immutable X `author_id` (was `(model_id, handle)` in v1.7). The
per-account `role` column is gone (P1 review fix #15): multi-brand
accounts make per-account role meaningless; the per-brand role
lives in `brand_accounts.role`. `bio` + `bio_fetched_at` are new
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
  in `brand_accounts` now.
- `accounts.role` — moved to `brand_accounts.role`.
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
id, so the per-brand fan-in lives in `brand_accounts`, not in this
join.

```
account_post_appearances
├── author_id*     TEXT  PK[1]                   ← FK → accounts.author_id (logical only, no declared FK in 004)
├── tweet_id*      TEXT  PK[2]                   ← FK → posts.tweet_id  ON DELETE CASCADE
└── role_at_time   TEXT                          ← snapshot of the active brand_accounts.role at the time of appearance
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

### `brand_companies` (10 rows; seeded by migration 004)

M:N edge between brands and corporate parents (Decision 2).
`ownership_pct` is `1.0` for wholly-owned brands; the column exists
for future joint ventures (e.g. a hypothetical `0.6`).

```
brand_companies
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


### `brand_accounts` (19 rows; application-seeded)

M:N edge between brands and accounts. The per-brand `role` lives
here (moved off `accounts.role` in v1.8; Decision 10).

```
brand_accounts
├── brand_id*   TEXT  PK[1]                 ← FK → brands.brand_id    ON DELETE CASCADE
├── author_id*  TEXT  PK[2]                 ← FK → accounts.author_id ON DELETE CASCADE
├── role*       TEXT  DEFAULT 'community'   ← "official" | "community" | "researcher" | "press" | "community"
└── added_at*   TEXT                         ← ISO-8601 UTC
```

Seeded by the application on the first run from
`data/brands/<brand>/accounts.yaml` (the migration loader does a
best-effort seed, but the application is authoritative).

---

### `company_accounts` (0 rows; application-populated)

M:N edge between companies and accounts. Empty by design at
migration time (Scope Boundaries: "No new analytics"); the
application populates it on the first `account_graph` pass that
joins `accounts` → `brand_accounts` → `brand_companies`.

```
company_accounts
├── company_id*  TEXT  PK[1]                ← FK → companies.company_id ON DELETE CASCADE
├── author_id*   TEXT  PK[2]                ← FK → accounts.author_id   ON DELETE CASCADE
├── role*        TEXT  DEFAULT 'community'   ← "official" | "community" | "researcher" | "press" | "community"
└── added_at*    TEXT                         ← ISO-8601 UTC
```

---

### `post_brands` (5,053 rows; populated by `x_monitor.reattribute`)

Per-(post, brand) attribution with fractional weight (Decision 9,
Option C). `weight = 1.0 / N` for a post naming N distinct brands;
single-brand posts get `weight = 1.0`. Unattributed posts get a
sentinel row (`brand_id = '_unattributed'`, `weight = 1.0`) that
queries filter out via `is_sentinel`.

```
post_brands
├── brand_id*  TEXT  PK[1]                 ← FK → brands.brand_id  ON DELETE SET NULL
├── post_id*   TEXT  PK[2]                 ← FK → posts.tweet_id   ON DELETE CASCADE
└── weight*    REAL  DEFAULT 1.0
```

Indexes:

```
idx_post_brands_brand       (brand_id)               — per-brand scans
idx_post_brands_brand_post  (brand_id, post_id)      — polarity JOIN (Decision 18, no IN subquery)
```

---

### `post_mentions` (4,428 rows; populated by `x_monitor.reattribute`)

Per-mention provenance: how was each brand named on each post?
The PK `(post_id, brand_id, source)` preserves the 4-source
decomposition (`user_mention | hashtag | body_keyword |
search_term`). Same brand named via 3 sources produces 3 rows.
The dedup key for polarity weight is `(post_id, brand_id)`,
enforced on `post_brands`.

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

### `post_brand_signals` (4,303 rows; backfilled from `posts.signal` by migration 004)

Per-(post, brand) signal classification (R6d / Decision 18).
Replaces the v1.7 post-level `posts.signal` column. A post naming
2 brands with different sentiments writes 2 rows. The CHECK
constraint excludes the sentinel (Decision 15) — `_unattributed`
rows have no meaningful per-brand signal.

```
post_brand_signals
├── post_id*   TEXT  PK[1]                 ← FK → posts.tweet_id   ON DELETE CASCADE
├── brand_id*  TEXT  PK[2]                 ← FK → brands.brand_id  ON DELETE SET NULL
└── signal*    TEXT                         ← release | community_question | criticism | commenter_capture | praise | other
                                             CHECK (brand_id <> '_unattributed')
```

Indexes:

```
idx_post_brand_signals_brand_signal  (brand_id, signal)  — per-brand polarity aggregation
idx_post_brand_signals_post          (post_id)          — per-post signal lookup
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

### `brand_keywords` (88 rows; detection registry, R6b)

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

The two tables in this section are part of PR #6
(`feat/hf-products-crawler`) and exist on the **worktree DB**
(`worktrees/hf-products/x-monitoring/data/x_monitoring.db`) used
to develop + smoke-test the HF products crawler. They are NOT
applied to the production `x-monitoring/data/x_monitoring.db`
yet. The numbers, indexes, and FK behavior documented here
reflect the worktree DB. Once PR #6 merges and the migration is
run on production, these tables will move into the main "Tables"
section above and the worktree-only flag will be removed.

### `brand_hf_orgs` (11 rows; seeded by migration 005 on worktree DB only)

M:N edge between brands and their HuggingFace orgs/usernames.
Same shape as `brand_companies` — a real associative entity, not
a pure join table: it carries four attributes beyond the FK pair
(`is_primary`, `confirmed`, `discovered_via`, `added_at`).

```
brand_hf_orgs
├── brand_id*         TEXT  PK[1]                ← FK → brands.brand_id      ON DELETE CASCADE
├── hf_org*           TEXT  PK[2]                ← HF namespace, e.g. "deepseek-ai"
├── is_primary*       INTEGER DEFAULT 0          ← 1 = primary HF org for the brand
├── confirmed*        INTEGER DEFAULT 0          ← 1 = curated/operator-confirmed (scraped)
                                                   0 = runtime-discovered candidate (review)
├── discovered_via*   TEXT  DEFAULT 'curated'    ← 'curated' | 'search:<query>'
└── added_at*         TEXT                       ← ISO-8601 UTC
```

Seed rows (11 — one per tracked brand):

```
brand_id         hf_org              is_primary   confirmed   discovered_via
-----------      ----------------    -----------  ----------  --------------
minimax          MiniMaxAI           1            1           curated
qwen             Qwen                1            1           curated
deepseek         deepseek-ai         1            1           curated
glm              THUDM               1            1           curated
xiaomi_mimo      XiaomiMiMo          1            1           curated
moonshot_kimi    moonshotai          1            1           curated
inclusionai      inclusionAI         1            1           curated
mistral          mistralai           1            1           curated
stepfun          stepfun-ai          1            1           curated
ernie            baidu               1            1           curated
hunyuan          tencent             1            1           curated
```

Foreign keys:

```
FOREIGN KEY(brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
```

Indexes:

```
idx_brand_hf_orgs_brand  (brand_id)
```

Runtime writes go through `x_monitor.store.upsert_brand_hf_org`,
which never demotes `confirmed = 1` rows and preserves
`discovered_via = 'curated'` when updating an existing curated
edge. The HF-org resolution path
(`x_monitor.hf_products.resolve_hf_orgs`) is hybrid: it first
reads from this table (`confirmed_only=True`), and only if
nothing is found does it call `hf_client.search_organizations`
and write new candidate edges (`confirmed = 0`) for operator
review — those are **flagged, not scraped**, until promoted.

---

### `products` (19 rows on worktree DB; 0 on production)

The HuggingFace product catalog. One row per HF model (today);
`hf_type` is reserved by CHECK for future datasets and spaces.
Mirrors `posts` in spirit (a fact row + a brand FK + rich JSON
columns) but for HF artifacts instead of X posts.

```
products
├── repo_id*              TEXT  PK                   ← HF model id, e.g. "MiniMaxAI/MiniMax-M1"
├── brand_id              TEXT                       ← FK → brands.brand_id  ON DELETE SET NULL
├── hf_org*               TEXT                       ← authoring namespace, e.g. "MiniMaxAI"
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

`brand_id` uses `ON DELETE SET NULL` (not CASCADE): deleting a
brand keeps the product row but nulls its `brand_id` — `repo_id`
rows are never cascaded because HF model identity is global.

Foreign keys:

```
FOREIGN KEY(brand_id) REFERENCES brands(brand_id) ON DELETE SET NULL
```

Indexes:

```
idx_products_brand   (brand_id)
idx_products_hf_org  (hf_org)
```

**Stable vs mutable columns.** `repo_id`, `brand_id`, `hf_org`,
`hf_type`, `display_name`, `author`, `created_at`, `collected_at`
are identity-stable — re-running the crawler does not touch them.
Everything else (`sha`, `downloads`, `likes`, `last_modified`,
the `*_json` columns, `updated_at`) is refreshed on each upsert
via `store.upsert_product`'s `ON CONFLICT(repo_id) DO UPDATE SET`
clause.

**`hf_type` CHECK constraint.** The CHECK
(`'model' | 'dataset' | 'space'`) is enforced at INSERT — invalid
artifact kinds fail at the upsert, not silently downstream.
Today's crawler only emits `hf_type = 'model'`; the dataset/space
arms are reserved by the constraint for when the crawler is
extended.

**List vs detail.** The HF list endpoint
(`/api/models?author=…&full=true`) is lean: it returns
downloads / likes / tags / siblings / pipeline_tag / library_name
/ sha / timestamps only. The license, base_model, language,
architectures, model_type, quantization_config, and dependent
Spaces are populated by a per-model `GET /api/models/{id}` call
and persisted as JSON text columns so new fields can be added
without re-scraping. `downloads_all_time` and `download_velocity`
are **not** exposed by the HF API at all and stay NULL.

See `docs/reference/minimax-hf-products-2026-06-22.md` for the
live 19-product MiniMax catalog written from this table on the
worktree DB.

---

### `_migrations` (6 rows)

Tracks which SQL files have been applied. Written by
`x_monitor/store.py::_apply_migration`.

```
_migrations
├── version*    INTEGER  PK                   ← matches the "00N_" prefix on the migration filename
└── applied_at* TEXT                          ← ISO-8601 timestamp with offset (e.g. "2026-06-22T05:03:47+00:00")
```

Rows currently in this DB:

```
version  applied_at                 migration
-------  -------------------------  ----------------------------------------
1        2026-06-08T22:53:57+00:00  001_initial.sql
2        2026-06-11T05:52:02+00:00  002_post_headline.sql
3        2026-06-17T04:22:26+00:00  003_translation_columns.sql
4        2026-06-19T06:41:47+00:00  004_company_brand_account_model.sql
5        2026-06-22T01:59:44+00:00  005_quoted_text.sql
6        2026-06-22T05:03:47+00:00  006_quote_capture_tracking.sql
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
   │ post_brands     │  │ post_mentions  │  │ post_brand_signals  │
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
│brand_  │  │brand_      │   │brand_        │    │ brand_search_    │
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
│(10 rows)│  │ (1,522 rows)  │
└────┬────┘  └────┬──────────┘
     │            │
     │ 1          │ 1
     │            │
     │ N          │ N
┌────▼────────────▼────┐
│ company_accounts     │
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
  (`is_sentinel = 1`), they appear in `post_brands` for
  un-attributed posts (filtered at query time), but they NEVER
  appear in `post_brand_signals` (CHECK constraint enforces this).
  They are the only `brand_id` values that should not be rendered
  on the treemap or grid.
- Brand source priority (R2): `user_mention` + `hashtag` are
  higher confidence than `body_keyword` + `search_term`. Multi-
  source matches take the max confidence across contributing
  sources. This is enforced by the application, not the schema.
- `post_brand_signals.signal` enum:
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
  for brand attribution. That role moved to `post_brands` +
  `post_mentions` + `post_brand_signals` (one row per detected
  brand per post). `account_post_appearances` is now the
  per-account appearance log (which accounts posted or were
  mentioned on which tweets), populated lazily by
  `account_graph`.
- `brand_hf_orgs` + `products` are NOT in this ER diagram —
  they are worktree-only tables (PR #6 pending). See the
  "Pending (worktree-only) tables" section above and
  `docs/reference/minimax-hf-products-2026-06-22.md`.

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
   ├── CREATE brand_companies     (10 seed rows; M:N brand ↔ company)
   ├── CREATE brand_accounts      (M:N brand ↔ accounts; role per brand)
   ├── CREATE company_accounts    (M:N company ↔ accounts; empty at migration time)
   ├── CREATE post_brands         (M:N post ↔ brand with fractional weight)
   ├── CREATE post_mentions       (per-source mention provenance; 4 sources)
   ├── CREATE post_brand_signals  (per-brand signal; replaces posts.signal)
   ├── CREATE brand_hashtags      (R6a detection registry)
   ├── CREATE brand_keywords      (R6b detection registry; substring or regex)
   ├── CREATE brand_search_terms  (R6c detection registry)
   ├── CREATE search_queries      (R6c storage fork; replaces soft pointer)
   ├── INSERT post_brand_signals  (backfill from posts.model_id + posts.signal)
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
   ├── CREATE idx_post_brands_brand          (single-column per-brand)
   ├── CREATE idx_post_brands_brand_post     (polarity JOIN)
   ├── CREATE idx_post_mentions_brand_source_recent  (source-breakdown card)
   ├── CREATE idx_post_mentions_post
   ├── CREATE idx_post_brand_signals_brand_signal
   └── CREATE idx_post_brand_signals_post

005_quoted_text.sql                       (branch `feat/capture-quote-tweets`; APPLIED on production 2026-06-22)
   └── ALTER posts +quoted_text TEXT   ← TwitterAPI.io quote-tweet referenced body (was discarded pre-005)

006_quote_capture_tracking.sql           (branch `feat/capture-quote-tweets`; APPLIED on production 2026-06-22)
   ├── ALTER posts +last_quote_count_seen INTEGER NOT NULL DEFAULT 0   ← reactive QT trigger state
   ├── ALTER posts +last_quote_fetched_at TEXT                          ← seeds sinceTime for next /twitter/tweet/quotes call
   ├── ALTER posts +created_at_epoch INTEGER                           ← unix-second epoch (for time-window queries; Twitter-format created_at sorts wrong)
   └── CREATE idx_posts_created_at_epoch   ← polarity window + QT daily-pass recency
                                                  ⚠ MISSING FROM PRODUCTION (see posts section note above)
```

The `posts` table grew in two stages and then SHRANK in v1.8, then GREW again in v1.8 + QT:
- **v1.2 (migration 002):** article headlines for URL-only posts
- **v1.7 (migration 003):** LLM translation columns + post-fetch signal classification
- **v1.8 (migration 004):** dropped `model_id` + `signal` (moved to
  join tables); renamed `favorite_count` → `like_count`; tightened
  the translation backfill indexes with lang-aware predicates.
- **v1.8 + quote-tweets (migrations 005–006):** added `quoted_text`
  + per-post QT capture tracking (`last_quote_count_seen` /
  `last_quote_fetched_at`) + `created_at_epoch` for correct
  time-window filtering. New columns only — no existing columns
  changed and no rows are backfilled (existing posts keep NULL /
  `0` defaults; the `created_at_epoch` backfill is a separate
  Python script because SQLite can't parse the Twitter format
  in pure SQL).

### Worktree-only migrations (NOT applied to production)

```
005_products.sql                         (branch `feat/hf-products-crawler`; worktree DB only — PR #6 pending)
   ├── CREATE brand_hf_orgs        (M:N brands ↔ HF-orgs; PK (brand_id, hf_org); FK → brands CASCADE; 11 seed rows)
   ├── CREATE products             (HF artifact catalog; PK repo_id; FK → brands SET NULL; hf_type CHECK)
   ├── CREATE idx_brand_hf_orgs_brand
   ├── CREATE idx_products_brand
   └── CREATE idx_products_hf_org
```

These tables exist on the worktree DB
(`worktrees/hf-products/x-monitoring/data/x_monitoring.db`) used
to develop + smoke-test the HF products crawler. They are
**documented in this file's "Pending (worktree-only) tables"
section** but are NOT in the production migration history above
because they have not been merged. The row counts, indexes, and
FK behavior in that section reflect the worktree DB, not
production. See `docs/reference/minimax-hf-products-2026-06-22.md`
for the live 19-product MiniMax catalog and
`docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md` for
the plan.
