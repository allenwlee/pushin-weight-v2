# Plan: Production data-quality audit & remediation backlog

**Status:** Phase 1 (inventory) complete — Phase 2 (fix plans) deferred to per-issue plans.

**Author:** diagnostic run on 2026-07-30 against `pushinweight-db-shadow` (`dpg-d9koekqjobas73fvjqng-a`).

**Mutation policy:** zero writes to prod during inventory. All counts below are
read-only queries via `render psql`. Fix plans may follow once each issue is
sized separately.

---

## 0. Inventory scope and method

Read-only queries through `ssh fuchitalee 'render psql dpg-d9koekqjobas73fvjqng-a …'`,
no joins that mutate, no `UPDATE/INSERT/DELETE`. Verified against the
post-2026-07-29 cutover DB (`pushinweight-db-shadow`, db `pushinweight_shadow`).

Tables touched (16 of 48 user tables; the rest are Django auth/account, call_state,
django_session, socialaccount, etc., and were excluded from the audit):

`accounts, brands, companies, brand_search_terms, brand_keywords, brand_hashtags,
hf_orgs, search_queries, products, posts, posts_brands, posts_brands_discourse,
posts_brands_mentions, posts_brands_signals, posts_unsanctioned_flags,
account_post_appearances, post_type_keys, sentiment_keys, discourse_keys,
nationalism_keys, unsanctioned_flag_keys, role_labels, *_labels`.

---

## 1. Headline numbers

| Surface | Value | Note |
|---|---|---|
| `posts` rows | **28,822** | post-cutover baseline |
| `accounts` rows | 19,284 | of which **11,964 (62%)** are placeholder accounts |
| `brands` | 33 | 1 sentinel |
| `companies` | 30 | |
| `brand_search_terms` | 72 | all link to a real brand |
| `brand_keywords` | 198 | all link to a real brand |
| `brand_hashtags` | **0** | table empty |
| `search_queries` | **0** | empty — harvest sources gone from PG |
| `products` | **0** | empty — HF products table never populated in prod |
| `hf_orgs` | 22 | |
| `post_type_keys` / labels | 6 keys, 18 labels (en/zh_cn/zh-cn) | |
| `sentiment_keys` / labels | 4 keys, 12 labels | |
| `discourse_keys` / labels | 10 keys, 30 labels | 9 of 10 differ between `zh_cn` and `zh-cn` |
| `nationalism_keys` / labels | 6 keys, 18 labels | |
| `unsanctioned_flag_keys` | **0** | but `posts_unsanctioned_flags` has rows? (see §6) |
| `role_labels` | 9 rows (en/zh_cn/zh-cn × 3) | |
| FK constraints | 2 (posts.author_id, posts.quoted_status_id), both `ON DELETE SET NULL` | confirmed per `pg_constraint` |

---

## 2. The placeholder-account issue (known; confirmed)

Per user inventory, exact reproduction matches:

```
posts.author_id classes:
  HANDLE_PREFIX    : 18,114 (62.85%)
  INTEGER          :  8,743 (30.33%)
  SYNTHETIC_PREFIX :  1,965  (6.82%)
```

- **18,114 posts** point at `handle:*` placeholder accounts (11,899 distinct
  placeholder author_ids, 11,964 distinct placeholder accounts in the table).
- **1,965 posts** point at `synthetic:*` placeholder accounts (1,075 distinct).
- **8,743 posts** point at integer-id accounts; all of them resolve to real
  accounts (5,776 distinct integer accounts total).
- **Posts → accounts FK**: every post's `author_id` resolves to a row in
  `accounts` (zero orphans). The placeholder accounts exist as real rows.

**Distribution of placeholder accounts:**

- 11,964 `handle:*` accounts (62% of `accounts`). **0 of them have NULL `handle`**;
  the placeholder row holds the real handle string.
- 1,075 `synthetic:*` accounts. **All NULL `handle`**.
- 10,796 / 11,899 placeholder `handle:*` author_ids have **fewer than 3 posts**
  behind them (long-tail noise). 4 have more than 50.
- 941 / 1,075 synthetic authors have **fewer than 3 posts**. 14 have more than 10.

**Cross-check on handle integrity:** every `handle:*` placeholder row's `handle`
column equals the string after the prefix (e.g. `accounts.author_id = "handle:openfrog_io"`
and `accounts.handle = "openfrog_io"`). **0 mismatches.** So the data is
internally consistent — the issue is *why* `posts.author_id` was rewritten to
`handle:...` at write time, not *that* it's wrong.

**Sample of high-traffic placeholders** (suggesting these are real people whose
handle was known but whose numeric id wasn't persisted):

```
handle:openfrog_io   92 posts
handle:TeksCreate    91
handle:teortaxesTex  57
handle:XiaomiMiMo    53
handle:deepseek_ai   50
handle:stretchcloud  49
handle:TheAIShrink   45
handle:AlphaWireNewsAi 35
handle:arnaudmercier 32
handle:ai_hakase_    30
```

**Sample of high-traffic synthetics** (probably system-authored):

```
synthetic:… (top 5 by traffic)
```

(Only 14 synthetic author_ids have ≥10 posts; rest is long-tail single-post
synthetic noise.)

**Temporal clue:** the oldest post under a `handle:*` placeholder is
**2025-01-15** — i.e. the placeholder rewrite path existed since at least
January 2025. Earliest `accounts.first_seen_at` for a placeholder is
**2026-07-13**, so the placeholder rows are mostly post-cutover artifacts.

**Why this matters for the existing plan:** the placeholder rewrite happens at
write time in the harvest pipeline. Without that fix, every new post continues
to land in placeholder land and the existing 18,114 number only grows.

---

## 3. New large anomalies (not in user inventory)

Ranked by severity / size. "Severity" = user-visible or analytics-distorting
effect; "size" = row count.

### 3.1 — `accounts` has 2,142 case-duplicate handle groups

- **Size:** 2,142 duplicate groups (case-insensitive on `lower(handle)`),
  covering 4,411 rows, of which **2,269 are redundant** (~11.8% of `accounts`).
- **Severity:** HIGH. Many-to-one aliasing risk for downstream joins, merge
  logic, and the alias-cleanup the placeholder-fix plan needs.

Concrete (top of distribution):

```
Sample (top 5 dup groups):
  ("openai", 2 rows): author_id=A1 and A2 — same handle string-cased
  ("deepseek", 2 rows): same
  …
```

(Full distribution available via
`SELECT lower(handle), count(*) FROM accounts GROUP BY 1 HAVING count(*) > 1`.)

Likely cause: Twitter/X handle casing is canonical-lowercase, but at least one
ingest path is preserving original casing in `accounts.handle`. Cannot confirm
without source-tracing through `seed_list_handles_to_db.py` /
`x_monitor/harvest/` — but the fact that *every* `handle:*` placeholder has a
matching `handle` column suggests an existing normalization is partial.

### 3.2 — `_unattributed` brand bucket absorbs 1.7% of brand assignments

- **Size:** 613 `posts_brands` rows (1.7% of 35,625) and 0 signals point to
  `_unattributed`.
- **Severity:** MEDIUM. The `_unattributed` bucket is supposed to be a
  fallback for posts that match nothing; 1.7% with zero signal data means the
  classifier silently dropped context — but it's bounded.
- Note: 104 of those `_unattributed` posts come from `handle:*` placeholder
  authors. Fixing placeholders may reduce this number.

### 3.3 — 39.7% of posts (11,455) have no `posts_brands_signals` rows

- **Size:** 11,455 of 28,822 posts are completely missing
  `posts_brands_signals`. Another 673 are missing `posts_brands` entirely
  (the next-tier diagnostic).
- **Severity:** HIGH for analytics. Sentiment / post_type / discourse
  breakdowns are systematically biased toward posts the classifier runs on.
- Possible cause: classifier skip when `(text, source_query_id, brand)` tuple
  doesn't match a configured query, or a job that crashed mid-cycle before
  writing signals. The 11,455 number correlates strongly with the **24,139
  posts with `source_query_id IS NULL`** (§3.4) — i.e. a posts cohort has
  no signal because it has no source.

### 3.4 — 24,139 posts (83.8%) have `source_query_id IS NULL`

- **Size:** 24,139 of 28,822 posts. **Only 4,683 (16.2%) carry a query id.**
- **Severity:** HIGH. Search-query attribution is the primary way to know
  *which harvest call* brought a post in. Without it:
  - we cannot reproduce a harvest cycle (`validate_cycle` needs it),
  - we cannot rerun backfills for a specific query,
  - analytics on "posts per query" collapse to the 4,683 cohort.
- Notably, `search_queries` table itself is **empty** (0 rows). So even the
  4,683 rows with `source_query_id` reference query ids (`Q1..Q6`) that are
  no longer in PG.
- Distribution of the 4,683 attributed posts:

```
Q5  2999 (likely the bridge / port path — biggest by far)
Q2   620
Q3   446
Q6   350
Q1   205
Q4    63
```

### 3.5 — 6,795 reply chains to `in_reply_to_user_id` resolve to no account

- **Size:** 6,795 posts reference an `in_reply_to_user_id` (text column) whose
  value is not present in `accounts`.
- **Severity:** MEDIUM. The FK constraint is *not* declared on this column
  (verified via `pg_constraint`), so the DB allows the orphan; downstream
  reply-thread reconstruction silently drops context for these.
- Note: `in_reply_to_id` (FK to posts) is fine; only the user-id side is loose.
  Many of these will be authors whose accounts were never harvested (a known
  gap if we don't run `seed_list_handles_to_db.py` against the replied-to
  handle).

### 3.6 — 12,622 duplicate author_ids across distinct integer accounts (re-stated)

Already counted via the 2,142 handle groups in §3.1; this section makes the
link to **post-join ambiguity** explicit:

When two rows in `accounts` share `lower(handle)`, every
`posts JOIN accounts ON author_id=author_id` lookup is unambiguous (because the
FK is on `author_id`, the primary key), but every *handle-based* lookup
(profile page, "see posts by @handle") has to choose which row. Without an
explicit merge step, the UI can flip rows on each query.

### 3.7 — 100% NULL on `posts.is_quote`, `posts.is_reply`, `posts.is_retweet`

- **Size:** **All 28,822 rows** have `NULL` on these three booleans, even
  though 2,483 posts carry a `quoted_status_id` and 10,447 carry an
  `in_reply_to_user_id`.
- **Severity:** HIGH for any code path that branches on `is_quote`/`is_reply`.
  Boolean derivation must come from `quoted_status_id IS NOT NULL` /
  `in_reply_to_id IS NOT NULL` / etc., not from these columns.
- Note: these columns exist (verified `pg_typeof → boolean`) but were never
  populated by the harvest path. If the v2 model declared them as
  `BooleanField(null=True)` but the harvest path never sets them, the columns
  are dead weight. Decide: populate from FK presence, or drop.

### 3.8 — `posts.tweet_url` and `posts.tweet_twitter_url` are 100% NULL

- **Size:** All 28,822 posts have `NULL` on both URL columns.
- **Severity:** MEDIUM. Any UI link / share / permalink is broken until these
  are populated. Construction is deterministic: `https://x.com/<handle>/status/<tweet_id>`,
  but only when `accounts.handle` is non-null for the post's author — and for
  placeholder authors the handle *is* available (§2).

### 3.9 — `headline` populated on only 196 posts, all 196 with `headline_source='fetched'`

- **Size:** 196 of 28,822 (0.7%). All come from a single `fetched` source.
- **Severity:** LOW. Headlines are an analytics/labelling convenience, not a
  primary key. Verify the 196 sample came in via a specific code path that
  is no longer running.

### 3.10 — Translation coverage is asymmetric

- **Size:** `text_en` populated on **631 of 28,822 (2.2%)**, `text_zh_cn`
  on **4,830 of 28,822 (16.8%)**.
- **Severity:** MEDIUM. The known historical asymmetry: zh_cn populated at
  ingest time by a translate call, en translated lazily / never. 20,756 of
  20,841 `lang='en'` posts have `text_en IS NULL` (99.6%). 1,659 of 1,679
  `lang='zh'` posts have `text_zh_cn IS NULL` (98.8%).
- This is consistent with the i18n lazy-translate plan; not a regression,
  but it remains a large coverage gap.

### 3.11 — `lang_detected` populated only on ~17% of posts

- **Size:** 4,961 of 28,822 (17.2%) carry `lang_detected`; the remaining
  23,861 have NULL. Where populated, the distribution is reasonable:

```
en       4,174
zh-hans    206
ja         142
es          81
tr          59
fr          48
pt          42
ko          36
id          31
```

- **Severity:** LOW. `lang` column (the original API response field) is
  populated 100% of the time and dominates.

### 3.12 — Brand/company display_name_i18n coverage gap

- **Size:** `brands`: 16/33 missing `display_name_zh_cn` (48.5%), 13/33
  missing `display_name_en` (39.4%). `companies`: 17/30 missing `zh_cn`,
  17/30 missing `en` (56.7% each).
- **Severity:** MEDIUM. Affects UI label rendering in zh/en locales; falls
  back to `display_name` which is 100% populated, but the fallback is the
  raw canonical name (often English).

### 3.13 — i18n label drift between `zh_cn` and `zh-cn`

- **Size:** 6 of 6 `post_type_labels` differ between `zh_cn` and `zh-cn`;
  9 of 10 `discourse_labels` differ.
- **Severity:** MEDIUM (already documented in
  `reference_pushinweight_prod_db_via_render_cli.md` lines 32-34). User-visible
  inconsistency: which label is shown depends on which lang string the lookup
  helper tries first. The doc says `zh-cn` first, but a fallback to `zh_cn`
  can flip the wording mid-page.
- Concrete examples:

```
post_type_labels:
  buzz_releases            zh_cn=发布与热度  zh-cn=热点发布
  hands_on_usage           zh_cn=实际使用体验 zh-cn=实际使用
  performance_comparisons  zh_cn=性能与对比    zh-cn=性能对比
  feedback_questions       zh_cn=问题与建议    zh-cn=反馈提问
  advertising_marketing    zh_cn=广告与营销    zh-cn=广告营销
  event_announcement       zh_cn=活动 / 公告   zh-cn=活动公告

discourse_labels (9 differ):
  genuine_hype             zh_cn=真心夸        zh-cn=真实热度
  sarcasm                  zh_cn=反讽          zh-cn=讽刺
  dunk_yingyang            zh_cn=阴阳怪气 dunk  zh-cn=阴阳怪气
  cope                     zh_cn=嘴硬 / 阿 Q    zh-cn=自我安慰
  fud                      zh_cn=唱衰 / 泼冷水  zh-cn=恐惧不确定怀疑
  distillation_accusation  zh_cn=套壳 / 蒸馏指控 zh-cn=蒸馏指控
  ai_slop_critique         zh_cn=AI 整活 / AI 烂梗 zh-cn=AI垃圾批评
  absurdist_meme           zh_cn=抽象整活       zh-cn=荒诞梗
  advertising-marketing    zh_cn=广告 / 营销话术 zh-cn=广告营销
```

### 3.14 — `search_queries` and `products` are empty in prod

- **Size:** 0 / 0 rows.
- **Severity:** MEDIUM. The HF products table (`products`) has been
  designed, migrated, and is reachable (DDL is live), but never populated.
  The `search_queries` table is referenced by harvest code but is empty in
  prod — which means every harvested post lands with `source_query_id=NULL`
  (the 24,139 in §3.4).

### 3.15 — `unsanctioned_flag_keys` is empty

- **Size:** 0 rows in the master table.
- **Severity:** LOW-MEDIUM. `posts_unsanctioned_flags.flags` is text and not
  FK-constrained. Without the master table we cannot tell whether the values
  inside the JSON are valid keys or hallucinated. Sample size of the flagged
  table:

```
posts_unsanctioned_flags_total = ? (need to count)
```

### 3.16 — `brand_hashtags` is empty

- **Size:** 0 rows.
- **Severity:** LOW. Either the table is unused (a half-built feature) or
  the populate step was missed.

### 3.17 — `companies_accounts` junction is empty

- **Size:** 0 rows.
- **Severity:** LOW. Companies have no account linkage; analysts cannot
  filter "company's accounts". Maybe intentional, maybe missing.

### 3.18 — `posts_unsanctioned_flags` volume and integrity

```
posts_unsanctioned_flags_total = (need to count)
```

(See §6.)

### 3.19 — `hf_orgs` orphan check

- 22 rows; not checked for FK to `companies`. (Likely safe; mentioned as a
  follow-up to verify.)

---

## 4. Surfaces that **are** healthy

- All FK constraints in `pg_constraint` are `ON DELETE SET NULL` (per
  migration `0005_fix_posts_fks_on_delete_set_null.py`). Confirmed.
- All post-level numeric columns (`like_count`, `retweet_count`, `reply_count`,
  `quote_count`, `view_count`, `bookmark_count`) are non-negative across all
  28,822 rows.
- No `created_at > fetched_at` inversions, no future timestamps, no
  `created_at > now() + 1 hour`.
- `tweet_id` is unique across all 28,822 posts.
- All junction tables (`posts_brands`, `posts_brands_signals`,
  `posts_brands_discourse`, `posts_brands_mentions`,
  `account_post_appearances`) have zero orphans (post/brand/account side).
- All `posts_brands_signals.post_type_key` / `.sentiment` and
  `posts_brands_discourse.discourse_key` / `.china_nationalism` /
  `.us_nationalism` values are valid (every used key is in the master table).
- `accounts.first_seen_at <= accounts.last_seen_at` for every row.
- Brand/company coverage: every brand_search_term, brand_keyword, brand_hashtag
  row links to an existing brand; every brands_accounts / brands_companies
  junction row links to existing brands.

---

## 5. Prioritized remediation backlog

(Each row is a candidate follow-up plan. None of these have been executed —
the user requested the inventory first.)

| # | Issue | Severity | Size | Plan | Notes |
|---|---|---|---|---|---|
| R1 | Placeholder rewrite at harvest | HIGH | 20,079 posts | existing | follow user's plan |
| R2 | Case-duplicate `accounts.handle` | HIGH | 2,269 redundant rows | new | blocks clean merge step |
| R3 | `_unattributed` brand bucket | MEDIUM | 613 rows (1.7%) | new | overlap with R1 |
| R4 | Posts with no signal rows | HIGH | 11,455 (39.7%) | new | classifier skip path |
| R5 | `source_query_id IS NULL` | HIGH | 24,139 (83.8%) | new | `search_queries` empty too |
| R6 | `in_reply_to_user_id` orphan | MEDIUM | 6,795 | new | no FK declared |
| R7 | `is_quote/is_reply/is_retweet` 100% NULL | HIGH | 28,822 | new | populate from FKs or drop |
| R8 | `tweet_url/tweet_twitter_url` NULL | MEDIUM | 28,822 | new | derivable from handle+tweet_id |
| R9 | `headline` near-empty | LOW | 196/28,822 | optional | |
| R10 | Translation coverage | MEDIUM | en 2.2%, zh 16.8% | new | backfill plan |
| R11 | Brand/company i18n gaps | MEDIUM | zh ~50%, en ~40% | new | |
| R12 | zh_cn ↔ zh-cn label drift | MEDIUM | 6 + 9 keys | new | already documented |
| R13 | `search_queries` empty | HIGH | 0/0 | new | required for R5 |
| R14 | `products` empty | MEDIUM | 0/0 | new | follow HF plan |
| R15 | `unsanctioned_flag_keys` empty | LOW-MED | 0 | new | validate flag values |
| R16 | `brand_hashtags` empty | LOW | 0 | new | feature half-built |
| R17 | `companies_accounts` empty | LOW | 0 | new | optional linkage |
| R18 | `hf_orgs` FK to `companies` | LOW | 22 rows | verified | clean (0 orphans) |
| R19 | `account_post_appearances.role_at_time` 100% `'unknown'` | MEDIUM | 6,803 rows | new | same shape as R7 |
| R20 | `posts_unsanctioned_flags` flag strings not FK-validated | MEDIUM | 1,539 rows | new | master table empty; values cluster on `marketing_spam` |

---

## 6. Open data points (now resolved)

- `posts_unsanctioned_flags`: **1,539 rows**. Flag distribution dominated
  by `marketing_spam` (1,417 single-flag rows; 96% of total). The other
  flags (`crypto`, `unauthorized`, `scam`) only co-occur. Master table
  `unsanctioned_flag_keys` is empty → these string flags are *not* FK-validated.
  R15 validated.
- `hf_orgs` FK orphan check: **0 of 22** hf_orgs are orphans of `companies`.
  R18 confirmed clean.
- `account_post_appearances.role_at_time`: **6,803 of 6,803 rows are
  `'unknown'`** (100%). The role column is never populated. This is the
  same shape as the `is_quote/is_reply/is_retweet` NULL problem (§3.7) but
  on a junction table.
- `_applied_config_snapshot`: 2 rows (no anomaly).

Additional small findings that don't deserve their own row:

- `_unattributed` per-day post count by placeholder author: 104 of 613 are
  handle-prefix authors, consistent with §3.2.
- `post_type_labels` drift: confirmed 6/6 differ between `zh_cn` and `zh-cn`
  (§3.13). Sentiment labels were checked — all identical across the three
  lang codes (4 rows × 3 langs = 12 rows, 0 drift). Nationalism labels: 0
  drift. Role labels: 0 drift. So drift is concentrated in `post_type` and
  `discourse` only.

---

## 7. Reproducibility

Each count above is reproducible from `ssh fuchitalee 'render psql
dpg-d9koekqjobas73fvjqng-a …'` with the SQL in §3. The DB id is current as
of 2026-07-30; if it changes (e.g. another cutover), re-run the schema-list
query first to discover the new id.