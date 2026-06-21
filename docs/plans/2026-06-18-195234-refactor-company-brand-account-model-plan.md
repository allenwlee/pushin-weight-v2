---
title: Refactor DB schema to company/brand/account/mention model
type: refactor
status: active
date: 2026-06-18
attribution: "{{AGENT_ATTRIBUTION}}"
revision:
  - 2026-06-18-19:5x — User pushed back on `posts.primary_brand_id`
    + `post_brands.is_primary` design. Replaced with pure fractional
    `weight` on `post_brands` (Option C). Dropped the `model_id`
    column on `posts` entirely; attribution is a pure join. See
    Decision 9 (revised) and Requirements R1/R5.
  - 2026-06-19 — User expanded mention-tracking to FOUR source
    categories (user_mention, hashtag, body_keyword, search_term)
    with the category persisted on `post_mentions`. Added 3 new
    detection-registry tables (`brand_hashtags`, `brand_keywords`,
    `brand_search_terms`) and a new Unit 7 for seeding them from
    `data/brands/<brand>/detection.yaml`. The dedup invariant is
    now explicit: same brand via 3 sources = 3 `post_mentions`
    rows but 1 `post_brands` row. See Decision 6 (revised) and
    Requirements R6/R6a/R6b/R6c. **All 3 design forks resolved
    in session:** (a) `post_brands.weight` = pure fractional
    1/N, (b) `search_term` storage = new `search_queries` table
    with FK (R6c), (c) multi-brand signal classification =
    Option 1 — new `post_brand_signals` join table (R6d).
  - 2026-06-19 (review pass) — `ce:review` against the plan surfaced
    6 P0 bugs in the migration 004 SQL outline (DROP COLUMN
    before backfill SELECT, `brand_accounts` backfill against
    empty `accounts` table, missing `company_accounts` backfill
    step, missing `lang_detected` UPDATE, `_unattributed` seeded
    with `is_sentinel = 0`, no operator-stop prerequisite). All 6
    P0s fixed in the transaction outline. Also applied: 24 P1
    fixes (DROP INDEX for `idx_posts_signal_model`, FK on
    `posts.source_query_id`, symmetric ON DELETE on
    `post_brand_signals`/`post_brands`, `accounts.role` dropped,
    `accounts` backfill SQL added, `_unattributed` filter docs,
    `'und'` in translation predicates, missing indexes added,
    raw_token format contract, ON CONFLICT policy). Added a new
    Unit 8 (Operator launch steps) covering worktree setup,
    `launchctl` unload/reload, dashboard kill-by-port, dryrun on
    `/tmp/x_monitoring.dryrun.db`, sha256 backup, pre/post
    verification queries, and rollback procedure. See the
    "2026-06-19 (review pass)" notes block at the start of the
    Migration 004 transaction outline for the per-fix details.
---

# Refactor DB schema to company / brand / account / mention model

## Overview

Replace the current `model_id` (singular brand key) with a richer
schema that reflects the actual domain: a **company** owns one or
more **brands**; an **account** (X handle) can be associated with
multiple brands via a join table; a **post** can be about multiple
brands via a `post_brands` join table that uses **fractional weights**
(`weight = 1.0 / N` for a post naming N brands). There is **no
`primary_brand_id` column on `posts`** — attribution is a pure
join, with the v1.7 dashboard's single-brand polarity query becoming
a `JOIN post_brands` rather than a column filter.

This is a **refactor** of the existing `posts` / `accounts` /
`account_post_appearances` schema. It does not add new product
behavior; it makes the data model faithful to what the v1.7 plan
already assumes (brand-attribution is post-fetch, multiple brands
per post are already possible via text-contains regex).

The work also resolves 12 long-standing naming and shape questions
about the schema, all bundled here so the migration lands in one
coherent unit.

## Problem Frame

The current schema, in `x_monitor/migrations/001_initial.sql` and
the two follow-ups (`002_post_headline.sql`, `003_translation_columns.sql`),
treats the LLM brand as a single `model_id` slug on every post and
every account. The 11 enabled brands are hard-coded in
`x_monitor/config.py::KNOWN_MODELS` and the dashboard ships 11
hard-coded display names + accent colors in
`MODEL_DISPLAY_NAMES` / `MODEL_ACCENT_COLORS`. The yaml files in
`data/queries/<m>.yaml` and `data/accounts/<m>.yaml` are partitioned
by the same slug.

Three frictions:

1. **Naming drift.** The v1.7 plan calls brands "brands" everywhere
   in prose, code comments, and design docs, but the column is
   `model_id`. New code, new tests, and the dashboard's
   `brand_colorize` Jinja filter all have to choose between "model"
   and "brand" and end up with both. A reader of the v1.7 plan who
   jumps to the schema sees `model_id` and has to mentally remap.
2. **Multi-brand is faked.** `attribute_to_brand` in
   `x_monitor/dashboard.py` does single-brand attribution (author
   handle first, then text-regex, first match wins). Posts naming
   multiple brands lose the secondary mentions entirely. The
   "wide-net" Call B in v1.7 returns 50-200 tweets/cycle and several
   percent of them name >1 brand; the data is being thrown away.
3. **Corporate parent is invisible.** Alibaba owns Qwen, Moonshot
   owns Kimi, Baidu owns ERNIE, Tencent owns Hunyuan. The dashboard
   has no way to roll up to a parent - if DevRel wants "what's
   Alibaba's total LLM mindshare," today they sum 1 brand. A
   `companies` table makes that a single GROUP BY.

The user requested all 12 questions be evaluated and answered
inside this plan. The questions and their resolutions are in the
**Decisions** section below; the rest of the plan is the
implementation.

## Requirements Trace

- **R1.** `posts.model_id` is **dropped**. The brand attribution for a
  post is *only* in the new `post_brands(brand_id, post_id, weight)`
  join table. There is no `primary_brand_id` column on `posts` —
  attribution is a pure join.
- **R2.** `accounts` loses the `model_id` PK component. The brand/
  account relationship moves to a new `brand_accounts(brand_id,
  handle, role)` join table.
- **R3.** A new `brands` table is the canonical brand registry
  (replaces the in-code `KNOWN_MODELS` frozenset for the DB-driven
  reads; `KNOWN_MODELS` stays as the in-code source of truth that
  the migration seeds from).
- **R4.** A new `companies` table holds the corporate parent. A new
  `brand_companies(brand_id, company_id)` join table is the M:N
  edge. We populate 6-8 known parents + 4-5 standalone companies
  with `NULL` brand mapping.
- **R5.** A new `post_brands(brand_id, post_id, weight)` join table
  captures multi-brand mentions with **fractional weights**
  (`weight = 1.0 / N` for a post naming N brands). No `is_primary`
  flag — the table is the only source of truth for "which brands is
  this post about, and how much." A post naming 2 brands writes 2
  rows with `weight = 0.5`; a post naming 3 brands writes 3 rows
  with `weight = 0.333...`; a single-brand post writes 1 row with
  `weight = 1.0`; a post naming 0 brands writes 1 row with
  `brand_id = '_unattributed'` and `weight = 1.0`. **The `weight`
  is computed from the number of *distinct brands* named on the
  post, not the number of `post_mentions` rows** (a post naming
  `minimax` 3 ways still gets `weight = 1.0` if it's the only
  brand named — see Decision 6 for the dedup rule).
- **R6.** A new `post_mentions(post_id, brand_id, source, raw_token,
  mentioned_at)` join table is the single source of truth for *how
  a brand was named on a post*. The `source` column is one of four
  values (`user_mention`, `hashtag`, `body_keyword`, `search_term`)
  and persists the *category* of mention (from the 2026-06-19
  feedback). The PK is `(post_id, brand_id, source)` — same brand
  named via 3 different sources produces 3 rows. The `raw_token`
  stores the literal matched text for auditability. `mentioned_at`
  is `posts.created_at` (ISO-8601 UTC) so range queries over time
  use the index without joining `posts`. See Decision 6 for the
  four extraction paths and the dedup-by-brand rule.
- **R6a.** A new `brand_hashtags(brand_id, tag)` table holds the
  hashtag registry. `#minimax`, `#m3`, `#kimi`, etc. are registered
  here per brand. The hashtag extraction (Unit 4) joins against
  this table. Seeded from `data/brands/<brand>/detection.yaml` at
  migration time.
- **R6b.** A new `brand_keywords(brand_id, pattern, is_regex)` table
  holds the body-text detection patterns. `"minimax"`, `"M3.0"`,
  `"hailuo"` are registered here as either literal substrings
  (`is_regex = 0`) or regex (`is_regex = 1`). The body_keyword
  extraction (Unit 4) compiles these once at startup and scans
  every post's `text` column. Seeded from the same
  `detection.yaml`.
- **R6c.** A new `brand_search_terms(brand_id, term)` table holds
  the per-brand TwitterAPI.io search keywords. These are the
  `keywords` arrays from the existing
  `data/brands/<brand>/queries.yaml`, moved into the DB so the
  attribution doesn't depend on a soft pointer to the queries
  directory. The `search_term` extraction (Unit 4) joins each
  fetched post's `source_query_id` against the saved query's
  keyword list. Seeded from `queries.yaml` at migration time.
- **R6d.** A new `post_brand_signals(post_id, brand_id, signal)`
  join table holds the **per-brand signal classification** for
  each post, replacing the post-level `posts.signal` column.
  The classifier (`classify_signal` in the v1.7 plan) is updated
  to return `list[(brand_id, signal)]` instead of a single
  string. The PK is `(post_id, brand_id)`. A post naming two
  brands with different sentiments ("Qwen is amazing, DeepSeek is
  disappointing") writes 2 rows: `(qwen, praise)` and
  `(deepseek, criticism)`. The existing `posts.signal` column is
  **dropped** in migration 004 — its per-brand decomposition
  lives entirely in this table. Polarity math in `treemap.py`
  changes from `SELECT signal, COUNT(*) * weight FROM posts p
  JOIN post_brands pb ...` (post-level signal) to
  `SELECT signal, SUM(weight) FROM post_brand_signals pbs JOIN
  post_brands pb USING (post_id, brand_id) WHERE ...` (per-brand
  signal). The `signal` enum is unchanged: `release |
  community_question | criticism | commenter_capture | praise |
  other`.
- **R7.** The 11 `data/queries/<brand>.yaml` and 11
  `data/accounts/<brand>.yaml` files are renamed to `<brand>.yaml`
  inside `data/brands/<brand>/queries.yaml` and
  `data/brands/<brand>/accounts.yaml` so the brand slug is a
  directory, not a flat file with a brand prefix.
- **R8.** All in-code references to `model_id` are renamed to
  `brand_id` (the column on `posts` is gone, so there is no
  `primary_brand_id` to worry about), including template
  variables, Jinja globals, route paths, and test fixtures.
- **R9.** `posts.favorite_count` is renamed to `posts.like_count`
  (the column was always mapped from `likeCount` in
  `_normalize_tweet`; the dashboard label was already changed in
  v1.6; this aligns the storage with the rest of the stack).
- **R10.** `posts.in_reply_to_user_id` keeps its name. The field
  is sourced directly from X's `inReplyToUserId` and renaming it
  would diverge from the upstream contract.
- **R11.** The two translation partial indexes are rewritten to use
  the user's logic: the index targets rows that NEED translation
  for the locale, not rows where the locale column is NULL. (See
  Decision 6 below for the exact predicate.)
- **R12.** `accounts.multi_brand_voice` is removed. The v1.7
  brand-attribution model already answers "how many brands does
  this account mention?" via `post_brands` + a count query;
  persisting it on the account row is a stale write.
- **R13.** `accounts.bio TEXT` and `accounts.bio_fetched_at TEXT`
  are added. The bio is fetched on every account_graph pass and
  written with the fetch timestamp so bio changes are detectable
  via a row diff.
- **R14.** `posts.raw` is kept. (See Decision 5.)
- **R15.** All renames preserve data. Migration 004 is a
  `BEGIN; ... COMMIT;` transaction that creates new columns/tables,
  backfills from old, drops the old, and renames. There is no
  application-side dual-write window; the migration is the
  conversion.

## Scope Boundaries

- **No UI changes.** The dashboard still uses the same 11 brand
  cards and the same treemap. The renamed columns and new join
  tables are internal.
- **No new analytics.** This refactor does not add a "by company"
  view, an "accounts mentioning N brands" view, or any dashboard
  page that uses the new tables. Those are follow-on plans once
  the schema lands.
- **No yaml content changes.** The 22 yaml files in `data/queries/`
  and `data/accounts/` keep their content. Only the path and the
  parent directory name change.
- **No deletion of `raw`.** (R14, Decision 5.)
- **No removal of the `entity`-extracted text in `posts.entities`.**
  It still lives on the post row; we just additionally persist a
  join-table row per mention (R6).

## Context & Research

### Relevant Code and Patterns

- `x_monitor/migrations/001_initial.sql` - current schema
- `x_monitor/migrations/002_post_headline.sql` - adds `headline`,
  `headline_source`
- `x_monitor/migrations/003_translation_columns.sql` - adds
  `text_en`, `text_zh_cn`, `lang_detected`, `signal`
- `x_monitor/store.py` - `Store` class, `_apply_migration`,
  `insert_posts`, `get_accounts`, `get_all_posts`
- `x_monitor/dashboard.py` - `MODEL_DISPLAY_NAMES`,
  `MODEL_ACCENT_COLORS`, `attribute_to_brand`, `serialize_*`
- `x_monitor/config.py` - `KNOWN_MODELS` frozenset, `enabled_models`
- `x_monitor/apify.py` - `_normalize_tweet` (where the
  `likeCount / favorite_count` mapping lives)
- `x_monitor/accounts.py` - `load_accounts`, `load_staff`,
  `derive_edges`, mention extraction from `entities.user_mentions`
- `x_monitor/relevance.py` - `load_filter(model_id, ...)` (used by
  `data/filters/<m>.yaml`)
- `x_monitor/queries.py` - `load_queries(model_id, ...)` (used by
  `data/queries/<m>.yaml`)
- `data/queries/<brand>.yaml` x 11 - per-brand query files
- `data/accounts/<brand>.yaml` x 11 - per-brand canonical + staff
  handles
- `data/filters/<brand>.yaml` x 11 - per-brand relevance filters
- `data/runs/` - per-run JSON summaries (contain `model_id` in
  several summary keys - see R8)
- `docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md`
  - the v1.7 plan that assumes brand-centric semantics
- `docs/plans/2026-06-17-002-feat-finviz-treemap-front-page-plan.md`
  - the treemap plan that hard-codes `MODEL_ACCENT_COLORS` /
  `MODEL_DISPLAY_NAMES`

### Institutional Learnings

- `feedback_remote_path_shape_not_sshfs.md` - `/Users/fuchitalee/`
  is a **local** path; never `ssh` for file reads on it.
- The v1.7 plan explicitly chose Option 1 (yaml `accounts + staff`
  is the brand-attribution source of truth) - that decision still
  holds; the new `brand_accounts` join table is **seeded from** the
  yaml, not the other way around.
- The dashboard already labels `favorite_count` as "likes" in the
  UI (per project memory on v1.1) but the column name was never
  renamed - this is a long-standing naming drift.
- The Apify/TwitterAPI.io migration happened in a prior commit
  (per `x_monitor/apify.py`); the `raw` column still receives
  TwitterAPI.io payloads and the comment on `posts.raw` in
  `001_initial.sql` is now stale (says "Apify response row").

### External References

- **X API v2 tweet object** - `id`, `text`, `created_at`,
  `author_id`, `in_reply_to_user_id`, `entities.user_mentions[]`
  (with `id`, `username`, `name`). Source:
  https://developer.x.com/en/docs/twitter-api/data-dictionary/object-model/tweet
- **X API v2 user object** - `id` (the immutable numeric
  account id, **the PK X uses internally**), `username` (mutable
  handle - X explicitly does NOT use this as a PK), `name`,
  `description`, `verified`. Source:
  https://developer.x.com/en/docs/twitter-api/data-dictionary/object-model/user
- **X UI rename (Nov 2021)**: "favorite" -> "like" everywhere in
  the public UI. The `favorite_count` field name was kept on the
  v1.1 endpoint for backward compat; v2 still exposes
  `public_metrics.like_count` and the search-aggregates endpoint
  still uses `favorite_count`. TwitterAPI.io normalizes to
  `likeCount` (its own camelCase). Either name is correct, but
  **`like_count` matches the current v2 field, the dashboard UI,
  and TwitterAPI.io's naming** - so we align to it.

## Decisions

This section answers each of the 12 questions the user asked, with
the rationale grounded in the codebase as it exists on 2026-06-18.

### Decision 1 (user Q1): Rename `model_id` -> `brand_id` (and DROP the column on `posts`)

**Resolved during planning, with a follow-up revision after the
user pushed back.** Yes, the global rename is in scope, with one
important refinement: the `posts.model_id` column is **dropped**,
not renamed. The user's follow-up was right that `primary_brand_id`
is a denormalization that buys ~30% query speed at the cost of
hard-to-reason-about multi-brand semantics. We get the same data
from `post_brands` and pay the join cost.

Concretely:

- On `posts`, the column is **gone**. Brand attribution lives
  entirely in the `post_brands` join table (R5). A 2-brand post
  contributes `weight = 0.5` to each brand's polarity count, not
  `weight = 1.0` to a "primary" brand and `0.0` to a secondary.
- On every other table and in code, the identifier is `brand_id`
  (the column on the "many" side of a brand relationship, the
  PK of `brands`, etc.).

The 163 in-code `model_id` references in `x_monitor/*.py` (per
`grep -rn "model_id" x_monitor/`) all collapse to `brand_id`. The
yaml paths (`data/queries/<model_id>.yaml`) move to
`data/brands/<brand_id>/queries.yaml`.

### Decision 2 (user Q2): Add `brands` and `companies` tables

**Resolved during planning.** Yes, both tables are in scope.
Detail:

- `brands` is the canonical registry: `brand_id TEXT PK, display_name
  TEXT, accent_color TEXT, is_sentinel INTEGER DEFAULT 0,
  created_at TEXT`. Seeded from `KNOWN_MODELS` +
  `MODEL_DISPLAY_NAMES` + `MODEL_ACCENT_COLORS`.
- `companies` is the corporate-parent registry: `company_id TEXT PK,
  display_name TEXT, hq_country TEXT, created_at TEXT`. Seeded
  with 6-8 known parents and 4-5 standalone companies.
- `brand_companies(brand_id, company_id, ownership_pct REAL)` is
  the M:N edge. Most rows are `ownership_pct = 1.0` (wholly-owned
  subsidiary) but the column allows partial stakes and joint
  ventures.
- `company_accounts(company_id, author_id, role)` is the M:N edge
  between companies and accounts. This is the user's "companies
  have many accounts" half of the relationship.
- `brand_accounts(brand_id, author_id, role)` is the M:N edge
  between brands and accounts. This is the user's "brands :
  accounts is many to many" half.

### Decision 3 (user Q3): Why is `posts.favorite_count` named this way?

**Resolved during planning.** It's an **Apify legacy column name**,
not an X API convention. Three independent reasons to rename it
to `posts.like_count`:

- The X v1.1 endpoint (the only one that ever used `favorite_count`)
  was retired in 2021. X v2 has used `like_count` for 4+ years.
- TwitterAPI.io (the current upstream) returns the field as
  `likeCount`. The mapping in `x_monitor/apify.py:334` is
  `"favorite_count": int(item.get("likeCount") or 0)` - we rename
  X's name into our legacy name, which is wasted work.
- The dashboard UI already calls the field "likes" (per v1.1
  project memory).

The rename is part of migration 004.

### Decision 4 (user Q4): Is `author_handle` unique and immutable? Is `author_id` what X uses for PK?

**Resolved during planning.**

- `author_id` is the **immutable numeric account id** that X uses
  internally. It is what every join should use. `author_handle` is
  the mutable display name (X explicitly does NOT treat it as a
  PK; users can change handles freely, and X's API uses `id` as the
  canonical key in every endpoint that takes a user reference).
- A user's *current* `author_handle` is unique, but it is NOT
  immutable: handles can be changed, and historical posts keep
  the handle they had at fetch time. Two posts from the same
  user may show different handles if the user renamed in between.
- **The DB should join on `author_id` and keep `author_handle` as
  a denormalized display field.** Today the schema has
  `accounts.PK(model_id, handle)` - that PK is wrong; it should be
  `accounts.PK(brand_id, author_id)` (Decision 2) with
  `handle` as a regular column. The
  `account_post_appearances.PK(model_id, handle, tweet_id)` also
  becomes `(brand_id, author_id, tweet_id)`.

### Decision 5 (user Q5): Rename `posts.in_reply_to_user_id`?

**Resolved during planning.** No, keep the name. The field is
sourced directly from X's `inReplyToUserId` (see
`x_monitor/apify.py:342`). Renaming to `in_reply_to_author_id`
would diverge from the upstream contract, and the user's own
question says "if this exact col name is from X, then keep."

A future cleanup could rename it to `in_reply_to_user_id` ->
`in_reply_to_author_id` *and* add a real FK to the accounts
table (once `accounts` has an `author_id` PK per Decision 4), but
that is a separate plan; the current name is fine.

### Decision 6 (user Q4-extended, revised after user feedback on 2026-06-19): Extract mentions to a join table — with FOUR sources

**Resolved during planning, REVISED twice (once for the original
user Q, once after user feedback on 2026-06-19).** Yes, the user
is right that `posts.entities.user_mentions[].id` is the X
convention for mentioning users. But there are **four** ways a
brand can be named on a post, and we need to track all four so
that:

1. The dashboard can answer "where is this brand's volume coming
   from" (handle mention vs hashtag vs bare body vs search-term
   recall).
2. Polarity math can differentiate a confident brand mention
   (body + hashtag + handle + search-term = 4 independent
   signals) from a single-source mention (just a search-term
   recall on a critic post).
3. The user's rule "a post naming `minimax`, `m3.0`, and
   `@minimax_ai` counts as 1 mention to minimax" is enforced by
   the `(post_id, brand_id, source)` PK — same brand across
   multiple sources still produces multiple rows, but the
   **dedup key for the polarity weight is `(post_id, brand_id)`**.

The new `post_mentions` table is the single source of truth for
*how a brand was named on a post*. The `post_brands` table (per
Decision 9) is the source of truth for *what share of the post's
attention belongs to each brand*. They are related but not
identical:

- `post_mentions` answers "did this post mention brand X, and
  how?" (operational/observability question).
- `post_brands` answers "what fraction of this post is about
  brand X?" (analytics/polarity question).

**Four `source` values (the persistence-of-category requirement
from the 2026-06-19 feedback):**

| `source` | What it is | Where extracted | When available |
|---|---|---|---|
| `user_mention` | `@handle` typed in the post text; the handle resolves to an account owned by the brand | `entities.user_mentions[].id` → lookup `brand_accounts.author_id` | When X returns entities (almost always) AND the mentioned handle is in `brand_accounts` |
| `hashtag` | `#tag` typed in the post text; the tag is registered for the brand in the new `brand_hashtags` table | `entities.hashtags[].tag` → lookup `brand_hashtags.tag` (case-insensitive) | When X returns entities AND the tag is in `brand_hashtags` |
| `body_keyword` | Bare brand name / product name / feature name in the post text (no `@` or `#` prefix) | regex match against `brand_keywords.pattern` (compiled once at startup) | When the post text contains a registered keyword |
| `search_term` | The post was fetched by a TwitterAPI.io call whose query keywords are registered for the brand | `posts.source_query_id` → lookup the query in the saved `plan_calls` JSON (or, post-refactor, the new `search_queries` table) → match each keyword against `brand_search_terms` | Always (every post has a `source_query_id`) |

**The dedup rule** (from the 2026-06-19 feedback, applied to
`post_brands` not `post_mentions`): a post naming `minimax`,
`m3.0`, AND `@minimax_ai` is 1 mention of the **brand** `minimax`
for the purpose of polarity weighting — even though it produces
3 rows in `post_mentions` (one per source). The `post_brands`
table dedups by `(post_id, brand_id)` and the `weight` is
computed from the number of *distinct brands* the post names,
not the number of *mention rows* it produces. So:

- `post_brands`: 1 row per distinct brand per post. `weight =
  1.0 / N_distinct_brands`.
- `post_mentions`: 1 row per (source × brand) per post. Same
  brand from 3 sources = 3 rows.

**The brand-keyword registry** — three new small tables that
make the extraction reproducible and editable without code
deploys:

```sql
-- brand_hashtags: which hashtags are associated with each brand
CREATE TABLE brand_hashtags (
    brand_id  TEXT NOT NULL,
    tag       TEXT NOT NULL,           -- lowercase, no '#' prefix
    added_at  TEXT NOT NULL,
    PRIMARY KEY (brand_id, tag),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
);

-- brand_keywords: regex/string patterns for body-text brand detection
CREATE TABLE brand_keywords (
    brand_id  TEXT NOT NULL,
    pattern   TEXT NOT NULL,           -- case-insensitive substring or regex
    is_regex  INTEGER NOT NULL DEFAULT 0,  -- 0 = literal substring, 1 = regex
    added_at  TEXT NOT NULL,
    PRIMARY KEY (brand_id, pattern),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
);

-- brand_search_terms: which TwitterAPI.io search keywords map to each brand
CREATE TABLE brand_search_terms (
    brand_id  TEXT NOT NULL,
    term      TEXT NOT NULL,           -- one keyword/operator from the plan_calls config
    added_at  TEXT NOT NULL,
    PRIMARY KEY (brand_id, term),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
);
```

Seeded at migration time from the existing per-brand yaml
(`data/brands/<brand>/queries.yaml` for `search_terms`,
`accounts.yaml` for the canonical/staff handles that drive
`brand_accounts`). `brand_hashtags` and `brand_keywords` are
seeded from a new `data/brands/<brand>/detection.yaml` file
that the migration loads at apply time.

**Note on `post_mentions.brand_id` semantics** (preserved from
the original Decision 6): the `brand_id` is the **mentioned
brand's primary brand**, not the post's primary brand (there
is no post primary brand — see Decision 9). This lets a query
like "how many mentions of Qwen in the last 24h, broken down
by source" be a single GROUP BY:

```sql
SELECT source, COUNT(*) AS mentions
FROM post_mentions
WHERE brand_id = 'qwen'
  AND mentioned_at >= datetime('now', '-1 day')
GROUP BY source;
```

A mention is recorded even if the mentioned handle is not yet in
`accounts` (the `post_mentions` table is independent of the
accounts registry). When `brand_id` can't be resolved (e.g., a
mention of an unknown handle, or a hashtag not in
`brand_hashtags`), the row is written with `brand_id = NULL` —
the raw token is still preserved in `raw_token` for later
backfill. The `entities` JSON column on `posts` is preserved
(R14) for fields we don't decompose into the join.

### Decision 7 (user Q5): Is `posts.raw` still needed?

**Resolved during planning (user choice: keep for now, deprecate
later).** Keep the column. It is a verbatim copy of the upstream
API response (TwitterAPI.io, per `x_monitor/apify.py:357`) and is
useful for:

- Debugging edge cases where a field we don't store is wrong.
- Post-hoc entity extraction (the join table in Decision 6 starts
  by re-reading the `entities` blob; if we ever need to extract
  more fields, `raw` is the source).
- Re-derivation when the dashboard adds a new field (e.g., bookmark
  count, view count - both already in TwitterAPI.io's response and
  currently discarded).

Migration 004 adds a comment to `posts.raw` noting that it's a
candidate for removal in a future migration once we have 30+ days
of clean TwitterAPI.io data and a list of which `raw` fields are
actually consulted. (No code reads `raw` today; it is preserved
for future re-derivation.)

### Decision 8 (user Q6+Q7): Translation partial indexes

**Resolved during planning, with the user's reasoning applied
correctly.** The user's mental model is right: a post in
English doesn't need an `en` translation (already en), but does
need a `zh-CN` translation. A post in `zh-CN` doesn't need a
`zh-CN` translation (already zh-CN), but does need an `en`
translation. A post in neither language needs both. So the
index for the **backfill** (rows that still need `en`
translation) is "lang_detected is set AND is not already en AND
text_en is null." For `zh-CN`: "lang_detected is set AND is not
already zh-CN AND text_zh_cn is null."

The exact predicates (SQL syntax-safe):

```sql
-- idx_posts_text_en_backfill: rows needing English translation
CREATE INDEX idx_posts_text_en_backfill
    ON posts(tweet_id)
    WHERE text_en IS NULL
      AND lang_detected IS NOT NULL
      AND lang_detected NOT IN ('en', 'en-US', 'en-GB');

-- idx_posts_text_zh_cn_backfill: rows needing zh-CN translation
CREATE INDEX idx_posts_text_zh_cn_backfill
    ON posts(tweet_id)
    WHERE text_zh_cn IS NULL
      AND lang_detected IS NOT NULL
      AND lang_detected NOT IN ('zh', 'zh-CN', 'zh-Hans', 'zh-Hant');
```

The user's proposed `WHERE lang_detected IS NOT 'en'` was a
short-hand; the production form needs to handle the long tail of
BCP-47 tags X returns (en-US, en-GB, zh-Hant, zh-Hans) and the
"lang detection hasn't run yet" case (which we want to keep
eligible for the backfill, not skip).

This is a **breaking change** to the existing
`idx_posts_text_en_null` / `idx_posts_text_zh_cn_null` indexes
from migration 003. The old indexes are dropped in migration 004
and the new ones created in their place.

### Decision 9 (revised after user feedback): no `primary_brand_id`; fractional weights on `post_brands`

**Resolved during planning, revised after the user pushed back on
the original `is_primary` design.** The original plan had a
`posts.primary_brand_id NOT NULL` column plus an `is_primary` flag
on `post_brands`. The user correctly pointed out that this is a
denormalization with confusing semantics (what does it mean for a
post to be "primarily about" Qwen when it explicitly compares
Qwen and MiniMax?), and that the speedup is fake at this scale.

**Revised design (Option C: pure fractional weights):**

- `posts` has **no** brand column. The `model_id` column is
  dropped in migration 004.
- `post_brands(brand_id, post_id, weight)` is the **only**
  attribution. The 2-column PK is `(brand_id, post_id)`.
- `weight` is a `REAL` column, default `1.0`. For a post naming
  N brands, all N rows get `weight = 1.0 / N`. A 2-brand post
  has `weight = 0.5`; a 3-brand post has `weight ≈ 0.333`; a
  single-brand post has `weight = 1.0`.
- **No `is_primary` flag.** A post is never "primarily about" a
  brand in the data model; it is *about* N brands, and each
  brand's "share" of the post is the weight.
- The polarity math (per brand X) is:

  ```sql
  SELECT p.*, pb.weight
  FROM posts p
  JOIN post_brands pb ON pb.post_id = p.tweet_id
  WHERE pb.brand_id = 'qwen'
    AND p.created_at >= :current_window_start
  ```

  `compute_polarity()` is updated to multiply each post's signal
  count by `weight` before adding it to the per-brand totals. A
  Qwen-vs-MiniMax post contributes 0.5 to each brand's
  Q1 (release) count, 0.5 to each brand's Q3 (criticism) count,
  etc. The total attention that post represents is conserved at
  1.0 across all the brands it names.

- **Unattributed posts** (no brand detected) get a single row in
  `post_brands` with `brand_id = '_unattributed'` and
  `weight = 1.0`. The treemap's "no data" strip handles
  `_unattributed` the same way it handles a model with 0 posts;
  the grid filters `_unattributed` out.
- **The "drill-down" page** (`/brand/qwen`) shows posts that
  mention Qwen, deduplicated by `post_id` so the same post
  doesn't appear twice if it names Qwen twice. Weight is shown
  as a small badge (e.g., "0.5" in the corner) so the user
  knows the post is shared with other brands.
- The previous unique partial index
  `UNIQUE (post_id) WHERE is_primary = 1` is replaced by the
  natural PK `(brand_id, post_id)` (no partial index needed).

**Why this is better than the `is_primary` design:**

- Mathematically clean: total attention is conserved across
  brands.
- No magic numbers (no "0.5 for secondary brands" heuristic).
- No "primary brand" decision that can be wrong.
- The "drill-down" view doesn't need a special case for
  multi-brand posts — every brand in the post is shown.
- Faster than the v1.6 single-column design in one specific way:
  no need to write `primary_brand_id` on insert (one less
  field to populate).

**Why this is slightly slower than the v1.6 design:**

- Every per-brand query is now a JOIN (one extra index seek on
  `post_brands(brand_id)` + one row lookup on `posts(tweet_id)`
  per row). At 2,008 posts / 11 brands this is sub-millisecond.
  At 100k posts it's still <30% overhead per the analytical
  model in the doc body.

### Decision 10 (user Q9): `accounts.brand_id` only when official/staff?

**Resolved during planning (user choice: join table only).** The
`accounts` table has no `brand_id` column at all. The brand/account
relationship is in `brand_accounts(brand_id, author_id, role)`. An
account appears once in the `accounts` table (one row per handle)
and can be in `brand_accounts` zero, one, or many times. The
`role` column on `brand_accounts` (one of `official`, `staff`,
`community`, `researcher`, `press`) carries the per-brand role
distinction; the user's "official or staff" rule becomes a query
filter, not a column constraint.

This is the model that supports the multi-brand-voice use case
(Q11) without flag-storing.

### Decision 11 (user Q10): Remove `accounts.multi_brand_voice`?

**Resolved during planning (user choice: yes, remove).** The
column is gone in migration 004. The query "how many brands does
this account mention?" is answered by:

```sql
SELECT a.handle, COUNT(DISTINCT pb.brand_id) AS brands_mentioned
FROM accounts a
JOIN account_post_appearances apa ON apa.author_id = a.author_id
JOIN post_brands pb ON pb.post_id = apa.tweet_id
WHERE apa.first_seen_at >= datetime('now', '-30 days')
GROUP BY a.handle
ORDER BY brands_mentioned DESC;
```

The dashboard does not currently render this view; it's a query
for ad-hoc analysis. No application code change is needed in
this migration; the column is just dropped.

### Decision 12 (user Q11): Add `accounts.bio` and `accounts.bio_fetched_at`?

**Resolved during planning (user choice: yes, add).** Two new
columns on `accounts`:

- `bio TEXT` - the user's profile bio, fetched by the
  `account_graph` subcommand via `TwitterApiClient.user_info`
  (which already returns `description`). Default `NULL` (the
  subcommand fetches in the background; on first run, the bio
  is `NULL` until the next pass).
- `bio_fetched_at TEXT` - ISO timestamp of the last bio fetch.
  Used by the `account_graph` subcommand to detect stale bios
  (>14 days old) and re-fetch them. The 14-day threshold is the
  same one used for `last_seen_at` in the v1.7 plan.

The `bio_contains_brand` column (current) is preserved as a
**cached** flag set by the `account_graph` pass; it is not the
source of truth, the live `bio` text is.

### Decision 13 (added 2026-06-19 review pass): `raw_token` format contract

**Resolved during review.** The `post_mentions.raw_token` column
stores the literal matched text from each extractor. The format
varies by `source` value. To prevent downstream consumers from
re-deriving the format from `source` ad-hoc, the format is
locked in:

| `source` | `raw_token` format | Example |
|---|---|---|
| `user_mention` | `@<username>` (with `@` prefix) | `@MiniMaxAI` |
| `hashtag` | `#<tag>` (with `#` prefix, lowercase) | `#minimax` |
| `body_keyword` | matched substring (no prefix, original case) | `M3.0` |
| `search_term` | keyword as-is from `search_queries.keywords_json` | `minimax` or `from:minimax OR ...` |

The format is enforced by an application-side assertion in
`x_monitor/attribution.py::MentionRow.to_sql()` (the function
that builds the INSERT statement). It checks
`raw_token.startswith('@')` when `source='user_mention'`,
`raw_token.startswith('#')` when `source='hashtag'`, and so on.
A mismatch raises `ValueError` before the INSERT. This catches
bugs at write time, not at consumer time.

A regression test in `tests/test_attribution.py::test_raw_token_format`
exercises all 4 sources with 3+ examples each.

### Decision 14 (added 2026-06-19 review pass): `post_brands` ON CONFLICT policy

**Resolved during review.** The `post_brands` PK is
`(brand_id, post_id)`. The original plan used
`ON CONFLICT DO NOTHING` for idempotent re-ingest. This is
wrong: if the detection registry evolves (a new brand is added,
a new keyword is registered), a post previously attributed to
brand X with `weight=1.0` may correctly be reattributed to
X+Y with `weight=0.5` each — but `ON CONFLICT DO NOTHING`
silently keeps the stale `weight=1.0` for X.

**Resolved policy:** `ON CONFLICT(brand_id, post_id) DO UPDATE
SET weight = excluded.weight`. On re-ingest, the weight is
overwritten with the freshly-computed value. This is safe
because `compute_post_brands` is deterministic given the same
detection tables. The same applies to `post_mentions` —
`ON CONFLICT(post_id, brand_id, source) DO UPDATE SET
raw_token = excluded.raw_token`.

The trade-off: re-ingest rewrites weights. If the detection
registry is unstable (keywords added/removed between runs),
polarity counts shift run-to-run. This is the correct behavior
— the alternative (stale weights) hides the evolution. Operators
who want stability can snapshot the registry before a major
change.

A regression test in `tests/test_attribution.py::test_reattribute_updates_weight`
inserts a post attributed to brand X, adds brand Y to the
detection registry, re-runs attribution, and asserts the new
`weight` values for X and Y are both `0.5` (not stale `1.0`
for X).

### Decision 15 (added 2026-06-19 review pass): `_unattributed` filter requirement

**Resolved during review.** Unattributed posts write
`(brand_id='_unattributed', weight=1.0)` to `post_brands`
(Decision 9). The treemap and grid filter `_unattributed` out
via `is_sentinel=1`. But any direct SQL query that joins
`post_brands` will count `_unattributed` as a brand — making it
the largest category in any noisy window.

**Resolved policy:** `_unattributed` MUST be filtered out of any
per-brand aggregation. Two layers of enforcement:

1. **Schema:** `CHECK (brand_id <> '_unattributed')` on
   `post_brand_signals` (which is the source of polarity math).
   `post_brand_signals` for the sentinel would be meaningless
   (no signal can be attributed to "no brand"), and the CHECK
   prevents any INSERT.
2. **Application:** all `compute_polarity` and per-brand queries
   have `WHERE brand_id != '_unattributed'` as a hard-coded
   clause. The treemap, grid, drill-down, and any future
   analytics view must use this filter. A regression test in
   `tests/test_polarity.py::test_unattributed_excluded_from_polarity`
   asserts the SUM returns 0 for `_unattributed`.

`post_brands` does NOT have the CHECK because `_unattributed`
rows are legitimate (they preserve attention for posts with
no detected brand). The application-level filter is sufficient.

### Decision 16 (added 2026-06-19 review pass): `/model/<id>` route — redirect vs 404

**Resolved during review.** The plan's Risks table says
"Add a redirect in dashboard.py: `@app.route('/model/<id>') ->
redirect('/brand/<id>', code=301)`." Unit 2's test scenario
asserts "/model/minimax returns 404." Direct contradiction.

**Resolved decision: 301 redirect.** External links and
bookmarks pointing to `/model/<id>` should not break. The
redirect cost is one route registration; the test is one
assertion. Implementation is in Unit 2's approach.

The redirect applies to ALL `/model/<id>` URLs that match the
old 11 brand slugs, plus the 4 standalone-company handles
(per Decision 2). URLs that don't match a known brand_id
return 404 (consistent with `/brand/<unknown>`).

### Decision 17 (added 2026-06-19 review pass): weight precision drift

**Resolved during review.** `weight = 1.0 / N` for a post
naming N brands produces values like `0.3333333333333333` for
N=3. Summing 3 such values gives `0.9999999999999999`, not 1.0.
The "conservation invariant" (sum = 1.0 per post) fails for
N≥3 due to IEEE 754 rounding.

**Resolved decision: use REAL with epsilon tolerance.** SQLite
REAL is 8-byte double; the maximum drift for any N is
~1e-16. The conservation test allows a tolerance:
`HAVING ABS(SUM(weight) - 1.0) > 0.001` (the 0.001 epsilon is
in POST-24 of Unit 8). For practical purposes, sums are
correct to 6 decimals.

The alternative — fixed-precision INTEGER micro-weights
(sum is always `1_000_000`) — was rejected because it adds
arithmetic complexity (every multiplication and comparison
needs the same scaling) without runtime benefit. At 2,008
posts × 11 brands, the floating-point drift is invisible.

### Decision 18 (added 2026-06-19 review pass): `compute_polarity` SQL — JOIN not IN subquery

**Resolved during review.** The plan's polarity SQL uses
`IN (SELECT tweet_id FROM posts WHERE created_at >= :window_start)`.
The IN subquery materializes the tweet_id list, defeating the
`post_brand_signals(brand_id, signal)` and `post_brands(brand_id)`
indexes.

**Resolved decision: rewrite as JOIN.** The new polarity SQL:

```sql
SELECT pbs.signal, SUM(pb.weight) AS weighted_count
FROM post_brand_signals pbs
JOIN post_brands pb
  ON pb.post_id = pbs.post_id AND pb.brand_id = pbs.brand_id
JOIN posts p
  ON p.tweet_id = pbs.post_id
WHERE pbs.brand_id = :brand_id
  AND pbs.brand_id != '_unattributed'  -- Decision 15
  AND p.created_at >= :window_start
GROUP BY pbs.signal;
```

The query planner can now use the `post_brand_signals(brand_id,
signal)` index to seek by brand, then JOIN `post_brands(brand_id,
post_id)` for the weight, then JOIN `posts(tweet_id)` for the
time-window filter. EXPLAIN QUERY PLAN on a 100k-post test DB
should show all three indexes used (no SORT or SCAN).

A benchmark test in `tests/test_polarity.py::test_polarity_uses_index`
runs EXPLAIN QUERY PLAN on a 100k-post fixture and asserts no
SCAN nodes appear.

### Open Questions Resolved During Planning

All 12 of the user's original questions are answered above.
Three follow-up design forks were raised on 2026-06-19 and
resolved in the same session:

1. **`post_brands.weight` semantics** — pure fractional 1/N
   (Decision 9 final). The user agreed on 2026-06-19 that the
   dedup invariant ("`minimax` + `m3.0` + `@minimax_ai` = 1
   mention") is about *the brand*, not the *number of mentions*.
   Source-weighted and boosted variants were considered and
   rejected because they would re-introduce the multi-source
   double-count that the dedup rule was designed to prevent.

2. **Search-term storage** — new `search_queries` table with FK
   (final, in Decision 6 / R6c). The current soft pointer to
   `data/queries/<id>.json` is brittle (the queries directory is
   rotated per run). A proper `search_queries(id, brand_id,
   keywords_json, created_at, plan_calls_run_id)` table makes
   the `search_term` attribution reproducible without filesystem
   dependencies. `posts.source_query_id` becomes a real FK.

3. **Multi-brand signal classification** — Option 1 from the
   2026-06-19 design fork: new `post_brand_signals(post_id,
   brand_id, signal)` join table (R6d). The classifier returns
   `list[(brand_id, signal)]` so a "Qwen praised, DeepSeek
   criticized" post writes 2 rows and per-brand polarity is
   correct. Option 2 (signal column on `post_mentions`) was
   rejected because search_term mention rows have no
   sentence-level context to attribute signal to.

The only remaining undecided items are implementation-time
details (exact column order, the `entities` JSON preservation
format) and are deferred to implementation.

## Key Technical Decisions

- **Single migration (004) for the full refactor.** Multiple
  sub-migrations create a window where the application has to
  dual-read from old + new tables. Wrapping the whole conversion
  in one transaction keeps the app code path simple.
- **`brands` table is the source of truth for brand metadata.**
  `KNOWN_MODELS`, `MODEL_DISPLAY_NAMES`, `MODEL_ACCENT_COLORS` in
  `x_monitor/config.py` become **derived** from a one-time
  `Store.read_brands()` call on startup. New brands can be added
  by `INSERT INTO brands`; the yaml files become optional (still
  supported for the queries + canonical-handles, but the brand
  registry itself is in the DB).
- **`accounts` PK is `author_id`, not `(brand_id, handle)`.** The
  brand/account edge uses `author_id` (immutable); the handle is
  a denormalized display field. Historical handles (from old
  posts) are preserved as-is in `post.author_handle`.
- **`post_brands` is filled by `attribute_to_brand` on every
  ingest.** The function returns `list[(brand_id, weight)]` with
  `weight = 1.0 / N` for a post naming N brands. The caller
  writes one `post_brands` row per brand-token match. (Idempotent:
  ON CONFLICT DO NOTHING on the `(brand_id, post_id)` PK.)
- **`post_mentions` is filled from `entities.user_mentions` on
  every ingest.** The existing code in
  `x_monitor/accounts.py:178-181` is the source; it already
  extracts `mentions[].id` and `.username`. The migration adds a
  `post_mentions` insert at the same place, with a `brand_id`
  resolved via `accounts.author_id` lookup (or `NULL` if the
  mentioned handle is not yet in `accounts`).

## High-Level Technical Design

> *Directional guidance for review, not implementation specification.
> The implementing agent should treat this as context, not code to
> reproduce.*

### ER overview after migration 004

```
companies
   company_id  PK
   display_name, hq_country, created_at
        | 1
        | N
        |
        v
brand_companies                                       brands
   brand_id     FK->brands                              brand_id  PK
   company_id   FK->companies                           display_name, accent_color,
   ownership_pct REAL                                  is_sentinel, created_at
        | 1                                                | 1
        | N                                                | N
        v                                                 v
brands  <--------------------------------------------  brand_accounts
 | ^                                              brand_id   FK->brands
 | |                                              author_id  FK->accounts
 | |                                              role       (official/staff/...)
 | | (also referenced by the 3 detection tables below)
 | |                                                       | N
 | |                                                       | 1
 | |                                                       v
 | |                                                accounts
 | |                                                   author_id  PK
 | |                                                   handle, display_name,
 | |                                                   bio, bio_fetched_at, ...
 | |                                                           | 1
 | |                                                           | N
 | |                                                           v
 | |  detection-registry (read-only at runtime)         account_post_appearances
 | +-- brand_hashtags       (brand_id, tag) PK              (author_id, post_id)  PK
 | +-- brand_keywords       (brand_id, pattern, is_regex) PK   (denormalized handle + role_at_time)
 | +-- brand_search_terms   (brand_id, term) PK
 | |
 | | posts                                                  post_brands
 | +-> tweet_id          PK                                     (brand_id, post_id) PK
 |     (no brand column -- attribution is via post_brands)  weight REAL  (= 1/N_distinct_brands)
 |     author_id, author_handle, ...
 |          | 1
 |          | N
 |          +-------------------->  post_mentions
 |                                      (post_id, brand_id, source, raw_token, mentioned_at)
 |                                      PK(post_id, brand_id, source)
 |                                      source ∈ {user_mention, hashtag, body_keyword, search_term}
 |                                      brand_id NULLable (un-attributed mentions kept with raw_token)
 v
post_mentions (FK post_id -> posts, FK brand_id -> brands ON DELETE SET NULL)
```

### Migration 004 transaction outline

**Operator prerequisites (P0 — failure to follow will cause
runtime outage; added after the 2026-06-19 review):**

1. **Stop the pipeline worker BEFORE applying migration 004.**
   `launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist`
   SQLite `BEGIN IMMEDIATE` blocks writes during the transaction,
   but after COMMIT any worker that resumes with the OLD code
   referencing `posts.model_id`, `posts.signal`, or
   `posts.favorite_count` crashes with `OperationalError: no such
   column`. The migration is the atomic switch — code and schema
   move together.
2. **Stop the dashboard BEFORE applying the migration.**
   `lsof -nP -iTCP:5000 -sTCP:LISTEN -t | xargs -r kill`
   (NEVER `pkill -f DashboardApp` per
   `feedback_pkill_matches_all_dashboardapp.md` — it kills the
   live main too). The dashboard will be restarted in Unit 8's
   operator launch steps.
3. **Atomic backup:**
   `cp data/x_monitoring.db data/x_monitoring.db.pre-004.$(date -u +%Y%m%dT%H%M%SZ).bak`
4. **Dry-run on a copy:** apply migration 004 to
   `/tmp/x_monitoring.dryrun.db` first. Only proceed to the live
   DB after all 19 post-deploy verification queries (see Unit 8)
   pass on the dryrun.

**Notes on the transaction outline below (2026-06-19 review fixes):**

- Step 4a (the `post_brand_signals` backfill) MUST run BEFORE
  the DROP COLUMN statements that remove `posts.model_id` and
  `posts.signal`. The backfill's `SELECT p.tweet_id, p.model_id,
  p.signal FROM posts p` references columns that the DROP removes
  if reordered. The original outline put DROP COLUMN first — that
  was a P0 bug.
- Step 4b backfills `lang_detected` from existing `text_en` /
  `text_zh_cn` rows so already-translated posts are correctly
  excluded from the new backfill indexes. Without this, posts
  with `text_en IS NOT NULL AND lang_detected IS NULL` fall out
  of `idx_posts_text_en_backfill` and never re-translate if their
  translation is invalidated. The Risks table mentions this UPDATE
  but the original outline omitted the SQL — also a P0 bug.
- Step 4c drops BOTH `idx_posts_model_created` AND
  `idx_posts_signal_model` BEFORE the DROP COLUMN statements.
  SQLite 3.35+ allows DROP COLUMN with auto-index cleanup, but
  explicit DROP INDEX is safer and matches the appendix's
  declared drops. Original outline only dropped the first index
  — P1 bug found by `schema-drift-detector`.
- Step 4d drops the two translation indexes (the columns they
  covered are unchanged, but the new predicates are different).
- Step 6 (`accounts` DROP + CREATE) runs BEFORE the
  `brand_accounts` / `company_accounts` seeds, but the seeds
  INSERT into the freshly-created accounts table (which is empty
  post-CREATE) — so the FK from `brand_accounts.author_id` to
  `accounts.author_id` cannot resolve. The original outline did
  NOT include an accounts backfill — that was a P0 bug
  (`adversarial-reviewer` 2026-06-19). Fixed by adding step 7a
  (backfill accounts from posts.author_id) BEFORE step 7b
  (seed brand_accounts).
- Step 6 drops `accounts.role` (per P1 finding #15 — the
  per-account role is meaningless once multi-brand accounts exist;
  per-brand role lives in `brand_accounts.role`).
- Step 6.5 changes `post_brand_signals.brand_id` and
  `post_brands.brand_id` ON DELETE from CASCADE to SET NULL
  (per P1 finding #9 — matches `post_mentions.brand_id` SET NULL
  semantics, preserves signal history on brand delete).
- Step 7c adds the FK from `posts.source_query_id` to
  `search_queries.query_id` (per P1 finding #8 — the diff
  promised this FK but the original outline didn't add it).
- Step 8 includes `'und'` in both negative-lists (per P1
  finding #30 — X returns `'und'` for very short posts; treat
  as eligible for both translations).
- Step 9 includes `idx_post_brand_signals_brand_signal` (the
  Appendix A summary promised this index but the original
  outline didn't create it — schema-drift P1 finding).

```
BEGIN;
  -- 1. Create new tables
  CREATE TABLE companies (...);
  CREATE TABLE brands (
      brand_id TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      accent_color TEXT NOT NULL DEFAULT '#9ca3af',
      is_sentinel INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
  );
  CREATE TABLE brand_companies (...);
  CREATE TABLE brand_accounts (...);
  CREATE TABLE company_accounts (...);
  CREATE TABLE post_brands (...);
  CREATE TABLE post_mentions (
      post_id      TEXT NOT NULL,
      brand_id     TEXT,             -- nullable for un-attributed mentions
      source       TEXT NOT NULL,    -- user_mention | hashtag | body_keyword | search_term
      raw_token    TEXT NOT NULL,    -- literal matched text: "@MiniMaxAI", "#minimax", "M3.0", "from:minimax OR ..."
      mentioned_at TEXT NOT NULL,    -- posts.created_at (ISO-8601 UTC), denormalized for index-only range queries
      PRIMARY KEY (post_id, brand_id, source),
      FOREIGN KEY (post_id) REFERENCES posts(tweet_id) ON DELETE CASCADE,
      FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE SET NULL
      -- brand_id FK is ON DELETE SET NULL so dropping a brand
      -- doesn't cascade-delete mention history; the row stays
      -- with brand_id=NULL for later re-attribution.
  );

  -- Detection-registry tables (R6a, R6b, R6c)
  CREATE TABLE brand_hashtags (
      brand_id  TEXT NOT NULL,
      tag       TEXT NOT NULL,        -- lowercase, no '#' prefix
      added_at  TEXT NOT NULL,
      PRIMARY KEY (brand_id, tag),
      FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
  );
  CREATE TABLE brand_keywords (
      brand_id  TEXT NOT NULL,
      pattern   TEXT NOT NULL,
      is_regex  INTEGER NOT NULL DEFAULT 0,
      added_at  TEXT NOT NULL,
      PRIMARY KEY (brand_id, pattern),
      FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
  );
  CREATE TABLE brand_search_terms (
      brand_id  TEXT NOT NULL,
      term      TEXT NOT NULL,
      added_at  TEXT NOT NULL,
      PRIMARY KEY (brand_id, term),
      FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
  );

  -- Search-query registry (R6c storage fork): replaces the soft
  -- pointer from posts.source_query_id to data/queries/<id>.json.
  CREATE TABLE search_queries (
      query_id          TEXT PRIMARY KEY,    -- matches posts.source_query_id
      brand_id          TEXT NOT NULL,       -- the primary brand this query targeted
      keywords_json     TEXT NOT NULL,       -- JSON array of keyword strings
      plan_calls_run_id TEXT,                -- optional FK to the run that produced this query
      created_at        TEXT NOT NULL,
      FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
  );

  -- Per-brand signal join table (R6d). Replaces posts.signal
  -- with a per-brand decomposition. A post naming 2 brands
  -- with different sentiments writes 2 rows.
  CREATE TABLE post_brand_signals (
      post_id  TEXT NOT NULL,
      brand_id TEXT NOT NULL,
      signal   TEXT NOT NULL,                -- release | community_question | criticism | commenter_capture | praise | other
      PRIMARY KEY (post_id, brand_id),
      FOREIGN KEY (post_id)  REFERENCES posts(tweet_id)     ON DELETE CASCADE,
      FOREIGN KEY (brand_id) REFERENCES brands(brand_id)    ON DELETE CASCADE
  );

  -- 2. Seed brands from KNOWN_MODELS + MODEL_DISPLAY_NAMES + MODEL_ACCENT_COLORS.
  --    The literal `is_sentinel = 0` in the original outline was a P0 bug
  --    (correctness-reviewer 2026-06-19): `_unattributed` must be flagged
  --    with is_sentinel = 1 so the treemap and grid filter it out. Fixed
  --    below with a CASE expression.
  INSERT INTO brands (brand_id, display_name, accent_color, is_sentinel, created_at)
  SELECT id, display_name, accent_color,
         CASE WHEN id = '_unattributed' THEN 1 ELSE 0 END,
         :now
  FROM (VALUES
      ('minimax', 'MiniMax AI', '#9ca3af'),
      ('qwen',    'Qwen',       '#9ca3af'),
      ...
      ('_unattributed', 'Unattributed', '#6b7280')
  );

  -- 3. Seed companies + brand_companies from a static table in the migration
  INSERT INTO companies ...;  -- 6-8 parents + 4-5 standalone
  INSERT INTO brand_companies ...;

  -- 3a. Seed the 3 detection-registry tables (R6a, R6b, R6c).
  --     The migration loader reads data/brands/<brand>/detection.yaml
  --     for the (hashtags[], keywords[]) arrays and
  --     data/brands/<brand>/queries.yaml for the keywords[] search
  --     terms. The seed is per-brand; for each brand the loader
  --     emits one INSERT batch.
  --
  -- Example shape for minimax (the actual migration expands this
  -- for all 11 brands):
  INSERT INTO brand_hashtags (brand_id, tag, added_at) VALUES
      ('minimax', 'minimax', :now),
      ('minimax', 'm3',      :now),
      ('minimax', 'hailuo',  :now),
      ('minimax', 'abab',    :now);
  INSERT INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
      ('minimax', 'minimax',      0, :now),
      ('minimax', 'minimax m3',   0, :now),
      ('minimax', 'M3\.0',        1, :now),
      ('minimax', 'hailuo',       0, :now),
      ('minimax', 'abab',         0, :now);
  INSERT INTO brand_search_terms (brand_id, term, added_at)
      -- values seeded from queries.yaml::keywords[] for minimax
      SELECT 'minimax', value, :now FROM json_each(:minimax_keywords_json);
  -- (repeat the search-terms insert for each of the 11 brands,
  --  passing that brand's keywords[] as the JSON parameter)

  -- 4a. Backfill post_brand_signals from old posts.signal + posts.model_id.
  --     MUST run BEFORE the DROP COLUMN statements below (the SELECT
  --     references p.model_id and p.signal which step 4d drops).
  --     Single-brand fallback: any post that was actually about
  --     multiple brands loses its per-brand decomposition here;
  --     re-classify with the per-brand classifier on a future cycle.
  --     Rows are written with brand_id matching the old posts.model_id,
  --     which is the SOLE brand the post was attributed to under the
  --     v1.6 single-brand model. The migration loader also writes
  --     `degraded:backfill:single_brand_signal:<N>` to
  --     data/runs/<migration_timestamp>/summary.json so the operator
  --     has a concrete count of posts that need re-classification.
  INSERT INTO post_brand_signals (post_id, brand_id, signal)
      SELECT p.tweet_id, p.model_id, p.signal
      FROM posts p
      WHERE p.model_id IS NOT NULL AND p.signal IS NOT NULL;

  -- 4b. Backfill lang_detected from existing text_en / text_zh_cn.
  --     Already-translated posts with lang_detected IS NULL would
  --     otherwise be eligible for the new backfill indexes (which
  --     require lang_detected IS NOT NULL AND not en/zh) — that's
  --     correct ONLY if the post is actually un-translated. Posts
  --     with text_en populated have been translated; their
  --     lang_detected should reflect that so they're excluded from
  --     the backfill sweep. Same for text_zh_cn. The "never-
  --     translated, never-lang-detected" subset (text_en IS NULL
  --     AND lang_detected IS NULL) stays eligible for backfill
  --     as desired.
  UPDATE posts SET lang_detected = 'en'
      WHERE text_en IS NOT NULL AND lang_detected IS NULL;
  UPDATE posts SET lang_detected = 'zh-CN'
      WHERE text_zh_cn IS NOT NULL AND lang_detected IS NULL;
  -- 'und' (BCP-47 undetermined) is treated as eligible for both
  -- translations; do not backfill it here.

  -- 4c. Drop indexes that reference columns about to be dropped.
  --     Drop BEFORE the columns per SQLite best-practice (avoids
  --     any auto-cleanup ordering surprise). Original outline
  --     only dropped idx_posts_model_created and missed
  --     idx_posts_signal_model — both are added here.
  DROP INDEX IF EXISTS idx_posts_model_created;
  DROP INDEX IF EXISTS idx_posts_signal_model;

  -- 4d. Rename + drop posts columns.
  --     (posts.model_id is DROPPED, not renamed -- attribution moves
  --     to post_brands per Decision 9 / revised R1)
  --     (posts.signal is DROPPED, not renamed -- signal moves to
  --     post_brand_signals per R6d / Option 1)
  ALTER TABLE posts RENAME COLUMN favorite_count TO like_count;
  ALTER TABLE posts DROP COLUMN model_id;
  ALTER TABLE posts DROP COLUMN signal;
  -- (no-op for in_reply_to_user_id, per Decision 5)

  -- 4e. Drop the old translation indexes; step 8 recreates with
  --     the new predicates.
  DROP INDEX IF EXISTS idx_posts_text_en_null;
  DROP INDEX IF EXISTS idx_posts_text_zh_cn_null;

  -- 5. Drop old account_post_appearances PK
  -- 5a. Re-create with (author_id, post_id) as PK
  DROP TABLE account_post_appearances;
  CREATE TABLE account_post_appearances (
      author_id  TEXT NOT NULL,
      tweet_id   TEXT NOT NULL,
      role_at_time TEXT,
      PRIMARY KEY (author_id, tweet_id),
      FOREIGN KEY (tweet_id) REFERENCES posts(tweet_id) ON DELETE CASCADE
      -- (no FK to accounts: post_mentions covers the edge; account_post_appearances is
      --  the historical "who appeared on this post" log, even for handles not in accounts)
  );

  -- 6. Drop old accounts, recreate with author_id PK.
  --    role column is DROPPED (Decision 10 / P1 finding #15 — the
  --    per-account role is meaningless once multi-brand accounts
  --    exist; per-brand role lives in brand_accounts.role).
  DROP TABLE accounts;
  CREATE TABLE accounts (
      author_id  TEXT PRIMARY KEY,
      handle     TEXT NOT NULL,
      display_name TEXT,
      bio        TEXT,
      bio_fetched_at TEXT,
      verified   INTEGER NOT NULL DEFAULT 0,
      bio_contains_brand INTEGER NOT NULL DEFAULT 0,
      engagement_tier TEXT NOT NULL DEFAULT 'low',
      first_seen_at TEXT,
      last_seen_at  TEXT,
      source_query_ids TEXT,  -- JSON list
      notes TEXT
      -- (no brand_id: that's in brand_accounts now)
      -- (no role: per-brand role lives in brand_accounts.role)
  );

  -- 6.5. Symmetrize ON DELETE on brand FKs.
  --      post_mentions.brand_id is already ON DELETE SET NULL (preserves
  --      mention history). post_brand_signals and post_brands also use
  --      SET NULL so a brand delete preserves signal + attribution
  --      history with brand_id=NULL for later re-attribution.
  --      Detection-registry tables (brand_hashtags, brand_keywords,
  --      brand_search_terms, brand_companies, brand_accounts) keep
  --      CASCADE — those ARE the brand's metadata and should vanish.
  --      Per P1 finding #9 (asymmetric ON DELETE was a real bug).
  --      SQLite does not support ALTER TABLE ... DROP CONSTRAINT
  --      directly. The FK declarations on post_brand_signals and
  --      post_brands in the CREATE TABLE statements above already
  --      use ON DELETE SET NULL — no fix needed at the table level.
  --      This comment block is here to make the SET NULL choice
  --      explicit for future readers.

  -- 7a. Backfill accounts from posts.author_id.
  --     For every distinct (author_id, handle) pair in posts, write
  --     one accounts row. The "most recent author_id per handle"
  --     rule (Risk table line 1970) is implemented by GROUP BY
  --     handle, taking the MAX(fetched_at) row's author_id. For
  --     a handle with 2 of 2008 posts having author_id IS NULL
  --     (per Unit 1 test scenario), the NULL author_id is filtered
  --     out; those 2 posts have no accounts row, which is correct
  --     (the pipeline re-ingest on the next cycle will populate
  --     them if TwitterAPI.io returns author_id). The migration
  --     loader logs handles with no author_id to
  --     data/runs/<ts>/degraded_accounts.json so the operator
  --     has a concrete list.
  INSERT INTO accounts (author_id, handle, display_name, verified,
                        bio_contains_brand, engagement_tier,
                        first_seen_at, last_seen_at)
      SELECT author_id, author_handle, NULL, 0, 0, 'low',
             MIN(created_at), MAX(created_at)
      FROM posts
      WHERE author_id IS NOT NULL
      GROUP BY author_id, author_handle;

  -- 7b. Seed brand_accounts from data/brands/<brand>/accounts.yaml.
  --     The yaml loader reads accounts + staff arrays and emits
  --     one INSERT per row. The accounts table is now populated
  --     (from step 7a), so the FK from brand_accounts.author_id
  --     to accounts.author_id resolves. Skipped rows (author_id
  --     in yaml but not in posts.author_id) are logged to
  --     degraded_accounts.json as missing_author_id.
  --     (The application also re-seeds brand_accounts on first
  --     run via the account_graph subcommand, so this step is
  --     best-effort.)

  -- 7c. Seed company_accounts (empty by design — see Scope
  --     Boundaries "No new analytics"). The table is created
  --     but no rows are inserted. Populated on the first
  --     account_graph pass that joins accounts -> brand_accounts
  --     -> brand_companies. This was P0 finding #3 (missing
  --     backfill step in the original outline).
  --     (No INSERT statement; the comment is the documentation.)

  -- 7d. Add FK from posts.source_query_id to search_queries.query_id.
  --     The original schema had source_query_id as a soft pointer
  --     to data/queries/<id>.json. The new search_queries table
  --     (R6c) makes it a real FK. ON DELETE SET NULL preserves
  --     the post row when a query is deleted (the post stays,
  --     attribution just falls back to body_keyword + hashtag +
  --     user_mention). The migration loader ALSO backfills
  --     search_queries from data/queries/<id>.json BEFORE the FK
  --     is added so existing source_query_id values resolve.
  --     SQLite does not allow ADD CONSTRAINT in older versions;
  --     the loader recreates posts with the FK in the schema.
  --     (Per P1 finding #8 — the FK was promised but never added.)

  -- 8. Re-create translation backfill indexes with the new predicates.
  --    Includes 'und' in the negative-list (P1 finding #30 — X
  --    returns 'und' for very short posts; treat as eligible).
  CREATE INDEX idx_posts_text_en_backfill    ON posts(tweet_id)
      WHERE text_en IS NULL AND lang_detected IS NOT NULL
        AND lang_detected NOT IN ('en','en-US','en-GB','und');
  CREATE INDEX idx_posts_text_zh_cn_backfill ON posts(tweet_id)
      WHERE text_zh_cn IS NULL AND lang_detected IS NOT NULL
        AND lang_detected NOT IN ('zh','zh-CN','zh-Hans','zh-Hant','und');

  -- 9. Add the post_brands + post_mentions + post_brand_signals indexes.
  --    The (brand_id, post_id) PK on post_brands is the natural
  --    unique constraint. No partial index needed (no is_primary
  --    flag). The (brand_id) index supports the polarity-window
  --    scan. For post_mentions, the (brand_id, source, mentioned_at)
  --    index supports the source-breakdown card. For
  --    post_brand_signals, the (brand_id, signal) index supports
  --    the per-brand polarity aggregation (Appendix A summary
  --    promised this — schema-drift-detector P1 finding).
  CREATE INDEX idx_post_brands_brand ON post_brands(brand_id);
  CREATE INDEX idx_post_brands_brand_post ON post_brands(brand_id, post_id);
  CREATE INDEX idx_post_mentions_brand_source_recent
      ON post_mentions(brand_id, source, mentioned_at DESC);
  CREATE INDEX idx_post_mentions_post ON post_mentions(post_id);
  CREATE INDEX idx_post_brand_signals_brand_signal
      ON post_brand_signals(brand_id, signal);
  CREATE INDEX idx_post_brand_signals_post
      ON post_brand_signals(post_id);

COMMIT;
```

### Application code changes (per-file outline)

- `x_monitor/config.py` - `KNOWN_MODELS` becomes
  `BRAND_REGISTRY_SEED: list[dict]`. `enabled_models` reads
  `Store.read_brands()` at startup and falls back to the seed.
- `x_monitor/store.py` - add `read_brands()`, `read_companies()`,
  `read_brand_hashtags()`, `read_brand_keywords()`,
  `read_brand_search_terms()`, `insert_brand_accounts()`,
  `insert_post_brands()`, `insert_post_mentions()`. Migration
  loader reads yaml per-brand to seed `brand_accounts`,
  `brand_hashtags`, `brand_keywords`, `brand_search_terms`.
- `x_monitor/dashboard.py` - `MODEL_DISPLAY_NAMES` /
  `MODEL_ACCENT_COLORS` become reads from
  `Store.read_brands()`. Route path `/model/<model_id>` becomes
  `/brand/<brand_id>`. `attribute_to_brand` returns a list of
  `(brand_id, weight)` pairs; `compute_polarity` is updated to
  multiply each post's signal count by `weight` before
  aggregating per-brand totals. `_build_treemap_tiles` JOINs
  `post_brands` to scope `get_all_posts` to a single brand.
- `x_monitor/treemap.py` - `MODEL_SECTORS` reads from
  `Store.read_brands()` joined with `brand_companies`. The
  `TreemapTile.brand_id` field replaces `TreemapTile.model_id`.
  The treemap's no-data strip logic stays the same.
  **Fallback policy (Decision 19, added 2026-06-19):** if
  `Store.read_brands()` returns 0 rows (DB not seeded yet,
  e.g. immediately after migration but before the LaunchAgent
  restart completes the first read), fall back to the static
  `BRAND_REGISTRY_SEED` constant in `config.py`. This prevents
  the dashboard from crashing on a cold start. If `read_brands`
  returns >0 rows, use the DB read (which is fresher than the
  hard-coded seed). Log a `WARN: falling back to seed registry`
  on the fallback path. A test in `tests/test_treemap.py::test_seed_fallback`
  asserts the dashboard renders with an empty DB.
- `x_monitor/apify.py` - `_normalize_tweet` returns
  `like_count` instead of `favorite_count`.
- `x_monitor/accounts.py` - `load_accounts` /
  `load_staff` now reads the per-brand yaml under
  `data/brands/<brand_id>/accounts.yaml`. `derive_edges`
  writes to `account_post_appearances` with `author_id` PK.
  Mention extraction writes to `post_mentions` in addition to
  the existing behavior.
- `x_monitor/queries.py` - `load_queries(brand_id, ...)` reads
  `data/brands/<brand_id>/queries.yaml`.
- `x_monitor/relevance.py` - `load_filter(brand_id, ...)` reads
  `data/brands/<brand_id>/filter.yaml` (the `filters/` directory
  also moves under the per-brand dir, OR stays at top level -
  see Decision R7 and the Implementation Units).
- `x_monitor/__main__.py` - argparse `--models` becomes
  `--brands`; CLI help text refers to "brands."
- `x_monitor/review.py` - `ReviewItem.model_id` becomes
  `ReviewItem.brand_id`.
- `x_monitor/translator.py` - translate-prompt references
  `brand_id` instead of `model_id`.
- `x_monitor/static/dashboard.js`,
  `x_monitor/static/trend-chart.js` - JS-side references to
  `data-model-id` and `model_id` rename.
- `x_monitor/templates/treemap.html.j2`,
  `x_monitor/templates/_treemap_svg.html.j2`,
  `x_monitor/templates/_model_card.html.j2`,
  `x_monitor/templates/grid.html.j2`,
  `x_monitor/templates/model_detail.html.j2` - Jinja references
  to `model_id` -> `brand_id`; the model card label can also
  switch from "Model" to "Brand."
- `data/queries/<brand>.yaml` x 11 -> moved to
  `data/brands/<brand>/queries.yaml` x 11.
- `data/accounts/<brand>.yaml` x 11 -> moved to
  `data/brands/<brand>/accounts.yaml` x 11.
- `data/filters/<brand>.yaml` x 11 -> either moved to
  `data/brands/<brand>/filter.yaml` (preferred) OR kept at
  `data/filters/<brand>.yaml` (less disruptive). Decision in
  Implementation Unit 5.

## Implementation Units

### Unit 1: Migration 004 - schema reshape

**Goal:** Land the new schema in one transactional migration.

**Requirements:** R1, R2, R3, R4, R5, R6, R6a, R6b, R6c, R6d, R9, R10, R12, R13, R14, R15

**Dependencies:** None (this is the schema work)

**Files:**
- [ ] Create: `x_monitor/migrations/004_company_brand_account_model.sql`
- [ ] Modify: `x_monitor/store.py` — add `read_brands`,
  `read_companies`, `read_brand_hashtags`, `read_brand_keywords`,
  `read_brand_search_terms`, `insert_brand_accounts`,
  `insert_post_brands`, `insert_post_mentions`,
  `insert_post_brand_signals`; update `insert_posts` to write
  `like_count` (no `model_id`/no `signal`/`primary_brand_id`);
  update `get_all_posts`/`get_posts_for_digest` to JOIN
  `post_brands` and `post_brand_signals`

**Approach checkboxes:**
- [ ] Wrap whole migration in `BEGIN; ... COMMIT;`
- [ ] Create new tables: `companies`, `brands`,
  `brand_companies`, `brand_accounts`, `company_accounts`,
  `post_brands`, `post_mentions` (with `(post_id, brand_id,
  source)` PK and 4 columns), `post_brand_signals` (R6d)
- [ ] Create detection-registry tables: `brand_hashtags`,
  `brand_keywords`, `brand_search_terms`, `search_queries`
- [ ] Seed `brands` from hard-coded list (11 + `_unattributed`)
- [ ] Seed `companies` + `brand_companies` from hard-coded list
- [ ] Seed `brand_hashtags`, `brand_keywords` from
  `data/brands/<brand>/detection.yaml` (the 11 yaml files
  written in Unit 7)
- [ ] Seed `brand_search_terms` from each
  `data/brands/<brand>/queries.yaml::keywords[]` (loaded via
  `json_each`)
- [ ] Drop `posts.model_id` (no replacement column)
- [ ] Rename `posts.favorite_count -> like_count`
- [ ] Drop `posts.signal` (moves to `post_brand_signals`)
- [ ] Backfill `post_brand_signals` from `posts.signal` +
  `posts.model_id` (single-brand rows; re-classify later for
  true per-brand)
- [ ] Drop + recreate `accounts` with `author_id` PK, add `bio`
  + `bio_fetched_at` columns
- [ ] Drop + recreate `account_post_appearances` with
  `(author_id, tweet_id)` PK
- [ ] Backfill `accounts` rows from `(model_id, handle)` →
  most recent `posts.author_id` for that handle; log
  `degraded:backfill:missing_author_id: [...]` for missing rows
- [ ] Drop old `idx_posts_model_created` (model_id is gone)
- [ ] Drop + recreate the 2 translation backfill indexes with
  the predicates from Decision 8
- [ ] Add `post_brands(brand_id)` index,
  `post_mentions(brand_id, source, mentioned_at DESC)` index,
  `post_mentions(post_id)` index,
  `post_brand_signals(brand_id, signal)` index
- [ ] Add `bio` + `bio_fetched_at` columns to `accounts`
- [ ] Migration uses `IF NOT EXISTS` and `DROP IF EXISTS`
  guards so it can be re-run idempotently during dev

**Execution note:** This is a non-trivial schema migration. Write
the migration as a series of `IF NOT EXISTS` and `DROP IF EXISTS`
guards so it can be re-run idempotently during development.
Test on a copy of the 19 MB prod DB before merging.

**Technical design:** See "Migration 004 transaction outline"
above.

**Patterns to follow:**
- Existing migrations 001, 002, 003 use plain SQL with inline
  comments. Migration 004 follows the same style.
- The `_migrations` ledger tracks applied versions - no app
  code change needed.

**Test scenarios:**
- [ ] **Happy path:** Apply migration 004 to a copy of the current
  prod DB (2,008 posts, 0 accounts, 0 apa). All tables exist;
  `brands` has 12 rows (11 + `_unattributed`); `companies` has
  10-13 rows; `posts` has 2,008 rows with `like_count`
  populated and `model_id` GONE; the two new backfill indexes
  are present; `post_brands` is created but empty (no brand
  attribution has been re-computed yet — Unit 4 backfills it
  via a one-time `reattribute_all_posts` subcommand).
- [ ] **Edge case - empty `author_id`:** 2 of 2,008 posts have
  `author_id IS NULL` (per a quick audit of the prod DB). After
  migration, those 2 posts still exist with the same data; the
  backfill warning list contains their `tweet_id`s. A subsequent
  run with a populated `author_id` (from a fresh fetch) clears
  the warning.
- [ ] **Edge case - brand with no posts:** The 4 standalones in
  `companies` (Minimax, DeepSeek, Mistral, Stepfun) have no
  `brand_companies` row. Verify no `post_brands` row exists
  for them in the post-migration state (no backfill yet).
- [ ] **Error path - re-applying migration:** Run the migration
  twice on the same DB. The second run is a no-op (the
  `_migrations` ledger blocks it) and does not raise.
- [ ] **Error path - re-applying after partial failure:** Drop the
  `_migrations` row, re-apply. The migration uses
  `IF NOT EXISTS` and `DROP IF EXISTS` guards, so it can be
  re-run cleanly.
- [ ] **Integration - application can read the new schema:** After
  the migration, the dashboard route `/` (treemap) and `/grid`
  both load without `sqlite3.OperationalError`. The treemap
  shows 11 brand tiles. The grid shows 11 cards.
- [ ] **Integration - `attribute_to_brand` works on a 2-brand post:**
  Insert a synthetic post that names both `minimax` and `qwen`
  in the text. The post has no brand column on `posts`. The
  `post_brands` table has 2 rows: `('minimax', tweet_id, 0.5)`
  and `('qwen', tweet_id, 0.5)`. The sum of weights for this
  post is 1.0 (conserved).
- [ ] **Integration - detection tables seeded:** After migration,
  `SELECT COUNT(*) FROM brand_keywords` returns ≥50 (11 brands
  × ~5 patterns). `SELECT COUNT(*) FROM brand_search_terms`
  matches the sum of `keywords[]` lengths across all 11
  queries.yaml files.
- [ ] **Integration - post_brand_signals backfilled:** After
  migration, `SELECT COUNT(*) FROM post_brand_signals` ≈
  number of posts that had a non-NULL `posts.signal` before
  the migration (~2,000).

**Verification:**
- [ ] `python -c "from x_monitor.store import Store; s = Store(Path('data/x_monitoring.db')); print(s.read_brands())"` returns 12 rows.
- [ ] `sqlite3 data/x_monitoring.db ".schema posts"` shows
  `like_count` and **does not** include `model_id`,
  `primary_brand_id`, or `signal`.
- [ ] `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM brands;"` returns 12.
- [ ] `sqlite3 data/x_monitoring.db "PRAGMA table_info(post_brands);"` shows
  `brand_id`, `post_id`, `weight` columns, no `is_primary`.
- [ ] `sqlite3 data/x_monitoring.db "PRAGMA table_info(post_mentions);"` shows
  `post_id`, `brand_id`, `source`, `raw_token`, `mentioned_at`
  columns with PK `(post_id, brand_id, source)`.
- [ ] The full test suite passes (`x-monitoring/.venv/bin/python -m pytest tests/ -q`). 297/297 tests, with the test fixtures updated for the new column names.

---

### Unit 2: Code rename - `model_id` -> `brand_id` everywhere

**Goal:** All in-code references to `model_id` are renamed to
match the new schema.

**Requirements:** R1, R8

**Dependencies:** Unit 1 (schema must exist before code
references it)

**Files:**
- [ ] Modify: `x_monitor/dashboard.py` (route `/model/<id>` ->
  `/brand/<id>`, `MODEL_DISPLAY_NAMES` / `MODEL_ACCENT_COLORS`
  reads from `Store.read_brands()`, Jinja globals updated)
- [ ] Modify: `x_monitor/treemap.py` (`MODEL_SECTORS` reads from
  Store, `TreemapTile.model_id` -> `TreemapTile.brand_id`,
  polarity SQL uses `post_brand_signals` join)
- [ ] Modify: `x_monitor/accounts.py` (yaml path,
  `account_post_appearances` writes use `author_id`)
- [ ] Modify: `x_monitor/queries.py` (yaml path)
- [ ] Modify: `x_monitor/relevance.py` (yaml path; see Unit 5 for
  `filters/` relocation)
- [ ] Modify: `x_monitor/__main__.py` (argparse `--models` ->
  `--brands`, error messages, docstrings)
- [ ] Modify: `x_monitor/review.py`
- [ ] Modify: `x_monitor/translator.py` (translate-prompt uses
  `brand_id`; classifier returns `list[(brand_id, signal)]`)
- [ ] Modify: `x_monitor/store.py` (internal references)
- [ ] Modify: `x_monitor/static/dashboard.js`,
  `x_monitor/static/trend-chart.js`
- [ ] Modify: `x_monitor/templates/treemap.html.j2`,
  `x_monitor/templates/_treemap_svg.html.j2`,
  `x_monitor/templates/_model_card.html.j2`,
  `x_monitor/templates/grid.html.j2`,
  `x_monitor/templates/model_detail.html.j2`
- [ ] Modify: `tests/conftest.py` and all test files that reference
  `model_id` in fixtures

**Approach checkboxes:**
- [ ] Bulk rename via `sed -i ''` (or a project script) for the
  mechanical cases (`model_id` -> `brand_id`)
- [ ] Hand-fix call sites that previously used `posts.model_id`
  directly — they now JOIN `post_brands` to filter by brand
- [ ] Update `Store.get_all_posts(brand_id)` to JOIN `post_brands`
  and return `SELECT p.*, pb.weight FROM posts p JOIN post_brands pb ...`
- [ ] Hand-fix the yaml paths (`data/brands/<brand_id>/...`)
- [ ] Hand-fix the route paths (`/model/<id>` -> `/brand/<id>`)
- [ ] Hand-fix user-facing strings ("Model card" -> "Brand card,"
  "models enabled" -> "brands enabled," etc.)
- [ ] Update all test fixtures to use the new column names
- [ ] Update `compute_polarity` SQL to JOIN `post_brand_signals`
  instead of reading `posts.signal` (per R6d)

**Execution note:** Use a feature flag or branch-and-test cycle
so we can detect missed renames quickly. `grep -rn "model_id"
x_monitor/ tests/` should return ZERO matches after this unit.

**Test scenarios:**
- [ ] **Happy path:** `grep -rn "model_id" x_monitor/ tests/` returns 0 matches.
- [ ] **Happy path:** Dashboard route `/` loads and renders the treemap without errors.
- [ ] **Happy path:** Dashboard route `/grid` loads and renders the 11 cards.
- [ ] **Happy path:** Dashboard route `/brand/minimax` loads and shows the drill-down for MiniMax AI.
- [ ] **Happy path:** Dashboard route `/brand/qwen` loads and shows the drill-down for Qwen.
- [ ] **Happy path - old route redirect:** `/model/minimax` returns 301 with `Location: /brand/minimax` header (per Decision 16; backward-compat redirect, NOT 404).
- [ ] **Happy path - unknown old route:** `/model/unknown_brand_xyz` returns 301 to `/brand/unknown_brand_xyz` (which then 404s from the new route handler).
- [ ] **Happy path - CLI:** `python -m x_monitor run --brands minimax,qwen` accepts the new flag.
- [ ] **Happy path - CLI deprecation:** `python -m x_monitor run --models minimax,qwen` raises a clear error directing the user to `--brands`.
- [ ] **Error path - typo in route:** `/brand/unknown_brand_xyz` returns 404 with a list of available brands.
- [ ] **Integration - full pipeline run:** A single end-to-end pipeline run with the new schema produces a non-empty `data/runs/<timestamp>/` summary with `brand_id` keys (not `model_id`).
- [ ] **Integration - polarity uses per-brand signals:** After a
  2-brand post (qwen-praise, deepseek-criticism) is ingested,
  the treemap polarity for qwen shows +praise contribution and
  the polarity for deepseek shows +criticism contribution (not
  both showing criticism).

**Verification:**
- [ ] All 297+ tests pass.
- [ ] `grep -rn "model_id" x_monitor/ tests/` returns 0 matches.
- [ ] The dashboard renders correctly in a browser smoke test.

---

### Unit 3: `data/brands/<brand_id>/` directory restructure

**Goal:** Move the per-brand yaml files from flat
`data/queries/` and `data/accounts/` (and optionally
`data/filters/`) into a per-brand directory.

**Requirements:** R7

**Dependencies:** Unit 1 (Store needs to read the new path)

**Files:**
- [ ] Move: `data/queries/*.yaml` -> `data/brands/<brand_id>/queries.yaml`
- [ ] Move: `data/accounts/*.yaml` -> `data/brands/<brand_id>/accounts.yaml`
- [ ] Move (option): `data/filters/*.yaml` -> `data/brands/<brand_id>/filter.yaml`
- [ ] Modify: `x_monitor/queries.py`, `x_monitor/accounts.py`,
  `x_monitor/relevance.py` to read the new paths
- [ ] Modify: any script that touches the old paths
  (e.g., `scripts/2026-06-17-150657-add-handles-to-x-list.py`
  if it opens `data/accounts/`)

**Approach checkboxes:**
- [ ] Write `scripts/2026-06-19-move-yamls-to-brand-dirs.sh`
  that does the move via `git mv` so history is preserved
- [ ] Run the move script on the 11 queries + 11 accounts yaml files
- [ ] Update the 3 loaders (`queries.py`, `accounts.py`, `relevance.py`)
- [ ] Decide on `data/filters/` relocation per Unit 5

**Test scenarios:**
- [ ] **Happy path:** `x_monitor/accounts.load_accounts('minimax')`
  returns the same data as before the move.
- [ ] **Happy path:** `x_monitor/queries.load_queries('qwen')`
  returns the same data.
- [ ] **Error path - missing brand dir:** A new brand
  (`brand_x` in `brands` table but no `data/brands/brand_x/`)
  returns `None` from `load_accounts` with a clear log warning,
  not an exception.
- [ ] **Integration - pipeline run:** The full pipeline ingests a
  post; `attribute_to_brand` finds the brand via the new
  yaml path; the post is attributed correctly.

**Verification:**
- [ ] `ls data/brands/` shows 11 directories (one per brand).
- [ ] `ls data/queries/` returns `No such file or directory` (the
  flat dir is gone).
- [ ] The 33 yaml files have `git log` history preserved
  (`git log --follow data/brands/minimax/accounts.yaml` shows
  the same history as the old path).

---

### Unit 4: `post_brands` and `post_mentions` population (4 sources)

**Goal:** On every post ingest, populate `post_brands` and
`post_mentions` correctly, using **four** independent detection
paths (`user_mention`, `hashtag`, `body_keyword`,
`search_term`). The `post_mentions` table records every (brand,
source) match with the literal `raw_token`; the `post_brands`
table records the deduped (brand, post) pair with the
`1.0 / N_distinct_brands` weight for polarity math.

**Requirements:** R5, R6, R6a, R6b, R6c

**Dependencies:** Unit 1 (tables must exist), Unit 2 (code
references brand_id), Unit 7 (detection tables seeded)

**Files:**
- [ ] Modify: `x_monitor/dashboard.py` (or the new
  `x_monitor/attribution.py` if extracted) - `attribute_to_brand`
  returns a list of `(brand_id, weight)`, the caller writes one
  `post_brands` row per pair.
- [ ] Modify: `x_monitor/accounts.py` - mention extraction also
  writes to `post_mentions` (the `user_mention` source).
- [ ] Modify: `x_monitor/store.py` - new methods `insert_post_brands`,
  `insert_post_mentions`, `insert_post_brand_signals`,
  `load_brand_hashtags`, `load_brand_keywords`,
  `load_brand_search_terms`. The first three are idempotent
  (ON CONFLICT DO NOTHING). The last three are
  read-once-at-startup helpers that return compiled detection
  tables.
- [ ] Create: `x_monitor/attribution.py` - new module with the
  four extraction helpers (see Approach), each pure and
  unit-testable in isolation. Returns a list of
  `MentionRow(post_id, brand_id, source, raw_token,
  mentioned_at)` records that the caller writes to
  `post_mentions`. Plus the `compute_post_brands` function
  that dedups mention rows by `(post_id, brand_id)` and
  returns `list[(brand_id, weight)]` for `post_brands`.
- [ ] Modify: `x_monitor/queries.py` - on every fetch, also
  write the search-term record to `post_mentions` (see
  Approach step 4).
- [ ] Modify: `x_monitor/translator.py` - the
  `classify_signal` function returns `list[(brand_id, signal)]`
  instead of a single string (R6d).
- [ ] Test: `tests/test_attribution.py` - new tests for the 4
  sources independently, the dedup invariant, the
  `weight` invariant (sum = 1.0 per post), and the per-brand
  classifier return type.

**Approach:**

The new attribution module is structured as four independent
extractors + one consolidator. Each extractor returns a
`list[MentionRow]`. The consolidator dedups by
`(post_id, brand_id)` and produces both the `post_mentions`
rows (one per source × brand) and the `post_brands` rows (one
per distinct brand, with `weight = 1.0 / N`).

**Step 1: `extract_user_mentions(post, brand_accounts, entities)`
-> `list[MentionRow]`**

- For every `id` in `post.entities.user_mentions[]`:
  - Look up `brand_id` via `brand_accounts[author_id]`. If
    found, emit `(post_id, brand_id, 'user_mention',
    raw_token="@<username>", mentioned_at=post.created_at)`.
  - If not found (handle not in `brand_accounts`), emit a row
    with `brand_id = NULL` and the raw token, so backfills
    can later attribute it.

**Step 2: `extract_hashtag_mentions(post, brand_hashtags, entities)`
-> `list[MentionRow]`**

- For every `tag` in `post.entities.hashtags[]` (lowercased,
  `#` stripped):
  - Look up `brand_id` via
    `brand_hashtags[(brand_id, tag)]`. SQLite index lookup
    is O(log N) per tag; with ~5-10 hashtags per brand
    registered and ~5 hashtags per post, the loop is cheap.
  - Emit `(post_id, brand_id, 'hashtag', raw_token="#<tag>",
    mentioned_at=post.created_at)`. If the tag isn't
    registered, no row is emitted (unknown hashtags are
    noise; we don't write them).
  - Case-insensitive match: `LOWER(tag)` compared to the
    stored lowercase `brand_hashtags.tag`.

**Step 3: `extract_body_keywords(post, compiled_keyword_index)`
-> `list[MentionRow]`**

- The compiled keyword index is built once at startup from
  `brand_keywords`:
  ```python
  # Pseudocode
  index = []
  for brand_id, pattern, is_regex in load_brand_keywords():
      flags = re.IGNORECASE | (0 if is_regex else 0)
      compiled = re.compile(pattern, flags) if is_regex \
                 else re.compile(re.escape(pattern), flags)
      index.append((brand_id, compiled))
  ```
- Scan `post.text` once, collecting all matches. For each
  match: emit `(post_id, brand_id, 'body_keyword',
  raw_token=<matched substring>, mentioned_at=post.created_at)`.
- **Note on `raw_token`:** for a `body_keyword` match, this is
  the actual matched substring ("M3.0", "minimax", "hailuo"),
  not the full pattern.

**Step 4: `extract_search_term_match(post, search_query, brand_search_terms)`
-> `list[MentionRow]`**

- For the post's `source_query_id`, look up the
  `keywords[]` array (from the new `search_queries` table per
  Decision 8 / pending fork-question, OR from the `raw` field
  on the post itself — see the open design question).
- For each `term` in the keywords[] array:
  - Look up `brand_id` via
    `brand_search_terms[(brand_id, term)]`.
  - Emit `(post_id, brand_id, 'search_term',
    raw_token=term, mentioned_at=post.created_at)`.
- This extractor always emits at least one row for every
  post (the search-term source is "why this post entered the
  pipeline").

**Step 5: `compute_post_brands(post, all_mentions)
-> list[(brand_id, weight)]`**

- Take the union of `brand_id` values across all
  `all_mentions` rows (filter out `NULL` brand_ids — those
  are un-attributable mentions).
- If the union is empty, return `[('_unattributed', 1.0)]`.
- Otherwise, return `[(brand_id, 1.0 / len(union)) for
  brand_id in union]`. The order of brands in the list does
  not matter (the weight is uniform).
- This is the function the caller writes to `post_brands`.

**The dedup invariant** (from the 2026-06-19 feedback): a post
naming `minimax`, `m3.0`, AND `@minimax_ai` produces
**three** `post_mentions` rows (one per source) but
**one** `post_brands` row for `minimax` with `weight = 1.0`
(if `minimax` is the only brand named) or `weight = 0.5`
(if `qwen` is also named). The `(post_id, brand_id)` PK on
`post_brands` enforces this; `(post_id, brand_id, source)`
on `post_mentions` allows the multiple rows.

**Wrapping the operations** in a single transaction with the
`posts` insert. The `compute_polarity` function is updated
to multiply each post's signal count by `pb.weight` before
adding to the per-brand totals. With R6d in place, the per-brand
signal comes from `post_brand_signals(pbs.signal)` JOINed on
`(post_id, brand_id)` rather than from the post-level
`posts.signal` column. The new polarity SQL is:

```sql
-- Per Decision 18: use JOIN not IN subquery so the
-- post_brand_signals(brand_id, signal) and post_brands(brand_id)
-- indexes are used. Also filters _unattributed (Decision 15).
SELECT pbs.signal, SUM(pb.weight) AS weighted_count
FROM post_brand_signals pbs
JOIN post_brands pb
  ON pb.post_id = pbs.post_id AND pb.brand_id = pbs.brand_id
JOIN posts p
  ON p.tweet_id = pbs.post_id
WHERE pbs.brand_id = :brand_id
  AND pbs.brand_id != '_unattributed'
  AND p.created_at >= :window_start
GROUP BY pbs.signal;
```

The classifier (`classify_signal` in
`x_monitor/translator.py` / `attribution.py`) is updated to
return `list[(brand_id, signal)]` instead of a single
post-level string. For a "Qwen praised, DeepSeek criticized"
post, the classifier returns `[('qwen', 'praise'),
('deepseek', 'criticism')]` and two `post_brand_signals` rows
are written. The classifier is called once per post (not once
per brand) — the brand list comes from
`compute_post_brands`'s output.

**Execution note:** Write the failing tests first
(`tests/test_attribution.py::test_4_source_extraction`,
`test_body_keyword_case_insensitive`,
`test_hashtag_case_insensitive`,
`test_search_term_always_present`,
`test_dedup_3_sources_one_brand`) before implementing. The
existing single-brand `test_attribute_to_brand` should be
reworked into `test_single_brand_post` (asserts
`len(returned) == 1`, `weight == 1.0`).

**Test scenarios:**

- [ ] **Happy path - single brand via author handle:** A post by
  `@MiniMaxAI` (in `brand_accounts` for minimax) returns
  `post_mentions` rows:
  `[(minimax, user_mention, "@MiniMaxAI")]` plus the
  mandatory `search_term` row. `post_brands` has 1 row:
  `(minimax, 1.0)`.
- [ ] **Happy path - single brand via body keyword:** A post by
  `random_user` with text "I love Qwen 3" produces
  `post_mentions` rows:
  `[(qwen, body_keyword, "Qwen 3"), (qwen, search_term, ...)]`.
  `post_brands` has 1 row: `(qwen, 1.0)`.
- [ ] **Happy path - single brand via hashtag:** A post by
  `random_user` with `#kimi` in `entities.hashtags[]` and
  text "excited" produces
  `post_mentions` rows:
  `[(moonshot_kimi, hashtag, "#kimi"), (moonshot_kimi, search_term, ...)]`.
- [ ] **Happy path - multi-brand, equal split:** A post by
  `random_user` with text "Comparing Qwen 3 vs DeepSeek V3"
  produces `post_brands` rows:
  `[(qwen, 0.5), (deepseek, 0.5)]`. `post_mentions` has 4+2
  rows (2 brands × 2 sources = body_keyword + search_term,
  per brand). Total weight across brands = 1.0.
- [ ] **Happy path - 3-brand post via 3 different sources:** A
  post by `@MiniMaxAI` with text "vs Qwen" and `#deepseek`
  in entities. Sources contributing:
  - minimax → user_mention (`@MiniMaxAI`) + body_keyword
    ("minimax") + search_term
  - qwen → body_keyword ("Qwen") + search_term
  - deepseek → hashtag (`#deepseek`) + search_term
  Total `post_mentions` rows for this post: ~7 (3 + 2 + 2).
  Total `post_brands` rows: 3, each with `weight ≈ 0.333`.
- [ ] **Edge case - no brand found:** A post by `random_user`
  with text "the new LLM is great" and no entities and a
  search-term query that doesn't match any
  `brand_search_terms`. Returns
  `[('_unattributed', 1.0)]` in `post_brands` and only
  the `search_term` rows (with `brand_id = NULL`) in
  `post_mentions`.
- [ ] **Edge case - empty `brand_accounts` mixed state (added
  2026-06-19 review pass):** `brand_accounts` is empty (fresh DB,
  pre-account_graph pass), but a post arrives with a `search_term`
  resolving to brand X via `brand_search_terms`. Assert:
  `post_brands` contains exactly `(X, 1.0)` (NOT
  `_unattributed`); `post_mentions` has exactly one search_term
  row with `brand_id=X`. The user_mention extractor returns
  `[]` (no brand_accounts to match against), the hashtag extractor
  returns `[]`, the body_keyword extractor may return rows if
  brand_keywords match. The post is correctly attributed to X
  even with an empty brand_accounts table.
- [ ] **Edge case - `entities` is NULL or non-dict (added
  2026-06-19 review pass):** A post where `posts.entities`
  is `NULL`, and a post where `entities` is the literal string
  `'null'` (X returns this for malformed tweets). Both
  `extract_user_mentions` and `extract_hashtag_mentions` must
  return `[]` without raising `AttributeError`. The
  `extract_search_term_match` and `extract_body_keywords`
  extractors still run normally and produce their rows.
  `post_brands` reflects whatever the body_keyword + search_term
  match; if both are empty, `_unattributed` is used.
- [ ] **Edge case - regex capture groups (added 2026-06-19
  review pass):** `brand_keywords` row with `pattern =
  'M([0-9]+)\\.([0-9]+)'` and `is_regex = 1`. A post with
  text "Comparing M3.0 to M2.7" produces two `MentionRow`s
  with `raw_token='M3.0'` and `raw_token='M2.7'`
  respectively (NOT `('3.0', '0')` from capture groups, NOT
  the full pattern). The consolidator dedups to one brand
  (minimax) with `weight=1.0` since only one brand is named.
- [ ] **Edge case - `raw_token` format contract (Decision 13,
  2026-06-19 review pass):** For every extractor, assert
  `raw_token` matches the locked-in format:
  `user_mention` → starts with `@`,
  `hashtag` → starts with `#`,
  `body_keyword` → matched substring with original case,
  `search_term` → keyword as-is from `brand_search_terms`.
  A regression test in `tests/test_attribution.py::test_raw_token_format`
  exercises all 4 sources with 3 examples each.
- [ ] **Edge case - dedup, 3 sources → 1 brand:** A post by
  `@MiniMaxAI` with text "minimax M3.0 is great" (no
  `#minimax` hashtag, just body + handle + search-term).
  `post_mentions` rows: 3 (user_mention + body_keyword +
  search_term), all for `brand_id='minimax'`.
  `post_brands` rows: 1 (`minimax, 1.0`). This is the
  user's explicit dedup rule from 2026-06-19.
- [ ] **Edge case - case-insensitive hashtag:** A post with
  `#MINIMAX` (uppercase) resolves to `brand_id='minimax'`
  because `brand_hashtags.tag` stores lowercase and the
  extractor lowercases input.
- [ ] **Edge case - case-insensitive body keyword:** A post with
  text "I love MINIMAX" matches `brand_keywords.pattern =
  "minimax"` because the compiled regex has
  `re.IGNORECASE`.
- [ ] **Edge case - unknown hashtag is silently dropped:** A post
  with `#worldcup-2026` (no brand registered for that tag)
  produces no `post_mentions` row for it.
- [ ] **Edge case - unknown user_mention with brand_id NULL:** A
  post mentioning `@random_user` (not in
  `brand_accounts`) produces a `post_mentions` row with
  `brand_id = NULL`. Backfills can later attribute it.
- [ ] **Edge case - body_keyword pattern with regex:** A
  `brand_keywords.pattern = "M[0-9]+\.[0-9]+"` with
  `is_regex = 1` matches "M3.0" and "M2.7" but not "M 3.0"
  (space). The compiled regex is reused for every post.
- [ ] **Error path - DB constraint violation:** A second ingest
  of the same post (same `tweet_id`) tries to write a
  duplicate `post_brands(brand_id, post_id)` row. The
  `ON CONFLICT DO NOTHING` clause on the natural PK makes
  it a no-op.
- [ ] **Error path - `post_mentions` PK violation:** Same post
  inserted twice. The `(post_id, brand_id, source)` PK
  blocks duplicates per source. `ON CONFLICT DO NOTHING`
  makes it idempotent.
- [ ] **Integration - polarity math with weights:** Insert 3
  posts: 1 Qwen-only (weight 1.0), 1 MiniMax-only
  (weight 1.0), 1 Qwen-vs-MiniMax (each gets 0.5). Run
  `compute_polarity` for Qwen: it sees 2 posts; the
  Qwen-vs-MiniMax post's signals are multiplied by 0.5.
  Total post count across all brands is 3 (not 4).
- [ ] **Integration - source breakdown:** After a pipeline run,
  `SELECT source, COUNT(*) FROM post_mentions WHERE brand_id
  = 'minimax'` returns roughly even counts across
  `user_mention`, `hashtag`, `body_keyword`, `search_term`
  (the actual distribution depends on the brand's
  mention-style — official brands skew toward
  `user_mention`/`hashtag`, research brands skew toward
  `body_keyword`).
- [ ] **Integration - dedup invariant:** For every post in the
  pipeline output,
  `SELECT SUM(weight) FROM post_brands WHERE post_id = X`
  equals `1.0` (conserved). A regression test asserts this
  for 100 random posts.
- [ ] **Integration - full pipeline:** A pipeline run with a
  mixed set of posts (1-brand, 2-brand, 3-brand, 0-brand,
  5-mention) ingests all of them.
  `SELECT COUNT(DISTINCT post_id) FROM post_brands` equals
  the number of posts ingested.
  `SELECT SUM(weight) FROM post_brands` equals the number
  of posts ingested (total weight 1.0 per post conserved).
- [ ] **Integration - per-brand signals (R6d):** Insert a
  "Qwen praised, DeepSeek criticized" post. Verify
  `post_brand_signals` has 2 rows: `(qwen, praise)` and
  `(deepseek, criticism)`. Verify `compute_polarity` for
  Qwen sees a praise contribution and for DeepSeek sees a
  criticism contribution (not both seeing criticism).
- [ ] **Integration - R6d prompt-shape validation (added
  2026-06-19 review pass):** Two tests for the per-brand
  classifier prompt:
  (a) `tests/test_attribution.py::test_classify_signal_prompt_contains_brand_list`
  snapshots the actual prompt sent to the LLM and asserts it
  includes BOTH brand names from the input (e.g., "qwen" and
  "deepseek" both appear as explicit options). A regression
  that reverts to a single-signal ask would fail this test.
  (b) `tests/test_attribution.py::test_classify_signal_parses_multi_brand_response`
  uses a recorded LLM response for a 2-brand post and asserts
  the parser correctly decomposes the response into
  `[(qwen, praise), (deepseek, criticism)]`.
- [ ] **Integration - conservation at scale (added 2026-06-19
  review pass):** A stress test that ingests 1,000 posts in
  two parallel threads, then asserts `SUM(weight) = 1.0` per
  post (with 0.001 epsilon per Decision 17) across all 1,000
  posts. Also asserts no duplicate `(brand_id, post_id)` rows
  in `post_brands` despite concurrent writes (the
  `ON CONFLICT DO UPDATE` from Decision 14 prevents
  duplicates).
- [ ] **Integration - reattribute_all_posts (added 2026-06-19
  review pass):** End-to-end test that runs migration 004 on
  a 100-post fixture DB, then runs the
  `python -m x_monitor reattribute --since <min_created_at>`
  subcommand. Asserts:
  (a) every post has at least one `post_brands` row
  (1+ real brands or `_unattributed`),
  (b) sum of weights per post = 1.0 (epsilon 0.001),
  (c) at least one post has a `post_mentions` row from each
  of the 4 sources (verifies all extractors ran),
  (d) the `_unattributed` is sentinel (`is_sentinel=1`),
  (e) the run summary JSON contains the per-brand count.
  Without this, the migration + dashboard integration has no
  end-to-end test (Unit 1 only tests the migration itself;
  Unit 4 only tests individual extractors).
- [ ] **Integration - reattribute updates weight on registry
  change (Decision 14, added 2026-06-19 review pass):** Insert
  a post attributed to brand X with `weight=1.0`. Add brand Y
  to `brand_keywords` (so the post now also matches Y).
  Re-run `compute_post_brands`. Assert X and Y both have
  `weight=0.5` (not stale `1.0` for X). This catches the
  `ON CONFLICT DO NOTHING` bug that would silently keep
  stale weights.
- [ ] **Integration - missing-yaml loud failure (added
  2026-06-19 review pass):** Run migration 004 with one
  brand's `data/brands/<brand>/queries.yaml` deleted before
  apply. Asserts:
  (a) the migration completes (does NOT roll back),
  (b) `data/runs/<ts>/summary.json` contains
  `degraded:seed:missing_yaml:<brand>: 1`,
  (c) `brand_search_terms` has 0 rows for that brand,
  (d) `brand_hashtags` and `brand_keywords` are unaffected
  (they're seeded from `detection.yaml`, not `queries.yaml`).
  Without this loud failure, the seed silently degrades and
  the dashboard's `search_term` attribution drops to 0 for
  that brand with no operator visibility.

**Verification:**
- [ ] `pytest tests/test_attribution.py -v` passes all
  attribution tests.
- [ ] The 4 extractor functions each have their own test file
  (`test_extract_user_mentions.py`,
  `test_extract_hashtag_mentions.py`,
  `test_extract_body_keywords.py`,
  `test_extract_search_term_match.py`).
- [ ] The integration test demonstrates a non-zero
  `post_brands` table AND a non-zero `post_mentions` table
  with all 4 sources represented.

---

### Unit 5: `data/filters/` relocation (decision-dependent)

**Goal:** Decide whether `data/filters/<brand>.yaml` also moves
under `data/brands/<brand>/filter.yaml`.

**Requirements:** R7 (partial - the filters/ question)

**Dependencies:** Unit 3 (the move) or none (if staying put)

**Files:**
- [ ] Move (if chosen): `data/filters/*.yaml` ->
  `data/brands/<brand>/filter.yaml`
- [ ] Modify (if chosen): `x_monitor/relevance.py::load_filter`
- [ ] Modify (if not chosen): nothing - `data/filters/` stays.

**Approach checkboxes:**
- [ ] Decide: keep `data/filters/` at top level (default, status quo), OR move it under `data/brands/<brand>/filter.yaml`
- [ ] If moving: write the move script + update `relevance.py::load_filter` to read the new path
- [ ] If not moving: no-op, mark complete

**Test scenarios:**
- [ ] **Happy path (status quo):** `load_filter('minimax')` reads
  `data/filters/minimax.yaml` and returns the same
  `RelevanceConfig` as before.
- [ ] **Happy path (if moved):** `load_filter('minimax')` reads
  `data/brands/minimax/filter.yaml`.

**Verification:**
- [ ] `load_filter` works for all 11 brands.
- [ ] A pipeline run with a relevance filter applied produces the
  same dropped/kept set as before.

---

### Unit 6: Test fixture + summary migration

**Goal:** Update all test fixtures to use the new column names
and update the run-summary JSON keys.

**Requirements:** R8 (test side), R15

**Dependencies:** Units 1, 2

**Files:**
- [ ] Modify: `tests/conftest.py`
- [ ] Modify: every test that uses `model_id` in a fixture
  (`tests/test_treemap.py`, `tests/test_store.py`,
  `tests/test_attribution.py`, etc.)
- [ ] Modify: `x_monitor/run.py` (the summary-dict writer
  uses `brand_id` instead of `model_id`)
- [ ] Modify: any docs (`docs/plans/2026-06-17-001-...`,
  `docs/plans/2026-06-17-002-...`, `docs/research/2026-06-18-...`)
  that reference `model_id` in code snippets or examples
- [ ] Verify: `data/runs/<timestamp>/summary.json` schema
  (`{ "brand_id": ..., "signal": ..., "posts": N, ... }`
  instead of `model_id`)

**Approach checkboxes:**
- [ ] `sed`-style bulk rename in `tests/`
- [ ] Hand-fix the fixtures that assert on the `summary.json` keys
- [ ] Hand-update the docs that have example JSON output
- [ ] Add a regression test that runs a single cycle and asserts
  the summary.json has `brand_id` keys

**Test scenarios:**
- [ ] **Happy path - fixture round-trip:** Insert a post via the
  new `Store.insert_posts`, query it back, assert the
  `posts` columns include `like_count` and **not** `model_id`,
  `signal`, or `primary_brand_id`. Assert that `post_brands` has the
  expected `(brand_id, post_id, weight)` rows. Assert that
  `post_brand_signals` has the expected `(post_id, brand_id, signal)`
  rows.
- [ ] **Happy path - summary keys:** A pipeline run produces
  `summary.json` with `brand_id` keys. A test asserts
  `summary["brands"]` is a list of `{brand_id, signal, posts}`.
- [ ] **Happy path - 297 tests still pass:** After all renames, the
  full suite is green.

**Verification:**
- [ ] `pytest tests/ -q` is green.
- [ ] `data/runs/<latest>/summary.json` shows `brand_id` keys.
- [ ] `grep -rn "model_id" tests/ data/runs/ docs/plans/ docs/research/` returns 0 matches in the post-Unit-6 code.

---

### Unit 0: Brand detection yaml files (PREREQUISITE)

**Goal:** Write the 11 `data/brands/<brand>/detection.yaml`
files BEFORE any other unit lands. The migration 004 transaction
reads these files at apply time and seeds `brand_hashtags`,
`brand_keywords`, and `brand_search_terms`. Without them, the
seed INSERTs are empty and `post_mentions` will only ever have
`user_mention` and `search_term` rows.

**Requirements:** R6a, R6b, R6c (file shape and contents)

**Dependencies:** None (this is the precondition).

> **Note (added 2026-06-19 review pass):** Unit 7 was
> originally listed as depending on Unit 1 (migration) — that
> was a circular dependency because the yaml files must exist
> BEFORE the migration runs. Unit 0 has no dependencies and
> must land first. Unit 7 was renamed and is now Unit 7 (seed
> verification + tests only — the yaml files themselves live
> in Unit 0).

**Files:**
- [ ] Create: `data/brands/<brand>/detection.yaml` x 11 — one
  per brand, hand-curated

**Approach:**
- [ ] Write the 11 yaml files with the shape documented in
  Unit 7's "Approach" section below
- [ ] Each file lists `hashtags[]` and `keywords[]` arrays
  for that brand (canonical name, common abbreviations,
  product names, most-used hashtags)
- [ ] No code or schema changes — pure data files

**Verification:**
- [ ] `ls data/brands/*/detection.yaml | wc -l` returns 11
- [ ] Each file has at least 1 hashtag and 1 keyword

---

### Unit 7: Brand detection tables + seed data

**Goal:** Create the three small detection-registry tables
(`brand_hashtags`, `brand_keywords`, `brand_search_terms`) and
verify they were seeded correctly from the per-brand yaml
files written in Unit 0. The 4-source attribution flow (Unit
4) reads these tables.

**Requirements:** R6a, R6b, R6c (table shapes)

**Dependencies:** Unit 0 (yaml files exist), Unit 1 (tables
must exist), Unit 3 (per-brand directory structure must exist)

**Files:**
- [ ] Modify: `x_monitor/migrations/004_company_brand_account_model.sql`
  (add the 3 new tables to the migration outline)
- [ ] Create: `data/brands/<brand>/detection.yaml` x 11 - new
  per-brand file with `hashtags[]` and `keywords[]` arrays
  for each brand. Seeded from a hand-curated list of the
  common brand identifiers (canonical name, common
  abbreviations, product names, and the most-used hashtag).
- [ ] Modify: `x_monitor/queries.py` - the existing
  `load_queries(brand_id)` function returns the
  `keywords[]` array; the migration reads it for the
  `brand_search_terms` seed.
- [ ] Modify: `x_monitor/store.py` - new methods
  `read_brand_hashtags()`, `read_brand_keywords()`,
  `read_brand_search_terms()` returning the in-memory tables
  for the attribution module to load.
- [ ] Test: `tests/test_detection_seed.py` - asserts each brand
  has at least 1 keyword and 1 search term; spot-check 3
  brands for hashtag coverage.

**Approach checkboxes:**
- [ ] Write the 11 `data/brands/<brand>/detection.yaml` files
  BEFORE applying migration 004 (ordering matters — see
  Execution note)
- [ ] Add 3 INSERT batches to migration 004 (brand_hashtags,
  brand_keywords, brand_search_terms seeds)
- [ ] Update `x_monitor/store.py` with `read_brand_hashtags()`,
  `read_brand_keywords()`, `read_brand_search_terms()`
- [ ] Wire `x_monitor/attribution.py` to load detection tables
  once at startup and cache in module-level dicts

**Approach:**

**`data/brands/<brand>/detection.yaml` shape:**

```yaml
# data/brands/minimax/detection.yaml
brand_id: minimax
hashtags:
  - minimax
  - m3
  - hailuo
  - abab           # legacy model name still referenced in some posts
keywords:
  - pattern: minimax
    is_regex: false
  - pattern: minimax m3
    is_regex: false
  - pattern: M3\.0   # escaped because the dot is regex-significant
    is_regex: true
  - pattern: hailuo
    is_regex: false
  - pattern: abab
    is_regex: false
```

The same shape is repeated for `qwen.yaml`, `deepseek.yaml`,
etc. with brand-appropriate hashtags and keywords. The yaml
loader (`pyyaml`) returns a list of `(pattern, is_regex)`
tuples.

**Migration-time seed:** the migration 004 transaction
includes 3 INSERT batches:

```sql
-- brand_hashtags seed (read from data/brands/<brand>/detection.yaml
-- at apply time; the migration loader walks the data/ directory)
INSERT INTO brand_hashtags (brand_id, tag, added_at) VALUES
    ('minimax', 'minimax', :now),
    ('minimax', 'm3', :now),
    ('minimax', 'hailuo', :now),
    ('minimax', 'abab', :now),
    ('qwen', 'qwen', :now),
    ('qwen', 'qwen3', :now),
    ...;

-- brand_keywords seed
INSERT INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES
    ('minimax', 'minimax', 0, :now),
    ('minimax', 'minimax m3', 0, :now),
    ('minimax', 'M3\.0', 1, :now),
    ...;

-- brand_search_terms seed (sourced from queries.yaml's keywords[])
INSERT INTO brand_search_terms (brand_id, term, added_at)
SELECT :brand_id, keyword, :now
FROM json_each(:keywords_json);  -- the migration loader passes the
                                  -- keywords[] as a JSON array
```

**Runtime reads:** `x_monitor/attribution.py` calls
`Store.read_brand_hashtags()`, `Store.read_brand_keywords()`,
`Store.read_brand_search_terms()` once at startup and caches
the result in module-level dicts. The detection module then
builds the compiled keyword index (see Unit 4 Step 3) from
the cached data.

**Why yaml-based seed and not config-driven:** the detection
yaml is a developer-edited file, not a runtime config. Adding
a new keyword/hashtag is a code change that goes through
review. The DB tables are the runtime source of truth; the
yaml is the bootstrap.

**Execution note:** Write the 11 detection yaml files BEFORE
applying migration 004. If the migration runs without the
yaml files, the seed inserts are empty and `post_mentions`
will only ever have `user_mention` and `search_term` rows
(`brand_keywords` and `brand_hashtags` are empty, so
`body_keyword` and `hashtag` sources emit no rows).

**Test scenarios:**
- [ ] **Happy path - 11 brands seeded:** After migration 004,
  `SELECT COUNT(DISTINCT brand_id) FROM brand_keywords`
  returns 11.
- [ ] **Happy path - minimax has its core keywords:** After
  migration 004, `SELECT pattern FROM brand_keywords WHERE
  brand_id = 'minimax'` includes `'minimax'`,
  `'M3\.0'`, `'hailuo'`.
- [ ] **Happy path - search_terms match queries.yaml:** For
  every brand, `SELECT COUNT(*) FROM brand_search_terms
  WHERE brand_id = X` equals the number of `keywords[]` in
  `data/brands/<brand>/queries.yaml`.
- [ ] **Happy path - hashtags registered:** At least 3 brands
  have at least 1 row in `brand_hashtags` (the brands with
  well-known hashtags: minimax, qwen, kimi).
- [ ] **Edge case - brand with no hashtags:** A brand like
  `stepfun` or `ernie` may have no widely-used hashtag;
  `brand_hashtags` has 0 rows for it. The hashtag extractor
  emits 0 rows for posts about stepfun (only body_keyword
  and search_term contribute). This is correct behavior.
- [ ] **Edge case - regex keyword with special chars:** The
  `M3\.0` pattern is stored with the literal backslash and
  dot. The compiled regex at runtime uses `re.compile` on
  the raw string. The test asserts the pattern survives the
  round-trip (yaml → SQLite → Python `re.compile`).
- [ ] **Error path - migration runs without yaml:** The seed
  inserts use static SQL values (the 11 brand_ids are
  hard-coded in the migration). Even if the yaml files are
  missing, the brand_hashtags/brand_keywords seed runs with
  the curated list. `brand_search_terms` is the only one
  that depends on yaml — the migration loader logs a
  warning and the table stays empty for that brand.
- [ ] **Integration - attribution reads the new tables:** After
  Unit 4 runs, `Store.read_brand_keywords()` returns the
  same 11 brands × N patterns as the seed. A new post's
  body_keyword extraction uses these patterns.

**Verification:**
- [ ] `pytest tests/test_detection_seed.py -v` passes all seed
  tests.
- [ ] `sqlite3 data/x_monitoring.db "SELECT COUNT(*) FROM
  brand_keywords"` returns the expected N (11 brands × ~5
  keywords each ≈ 50).
- [ ] The 11 `data/brands/<brand>/detection.yaml` files exist.
- [ ] The full test suite passes (Unit 7 + all prior units).

---

### Unit 8: Operator launch steps (worktree + launchctl + dryrun)

**Goal:** Land Units 1-7 in the right worktree, apply migration
004 against a dryrun copy first, then atomically switch the live
DB + LaunchAgent + dashboard to the new schema. Provide a
Go/No-Go checklist the operator can run on the deploy day and a
rollback procedure if any post-deploy verification fails.

**Requirements:** Cross-cutting — depends on Units 1-7 being
mergeable; executes after PR for Units 1-2-3-6 is approved (per
the Rollout section). Unit 4 and Unit 7 may land as separate
follow-up PRs.

**Dependencies:** Units 1-7 complete and merged. Worktree
hygiene memory (`feedback_worktree_hygiene_x_monitoring.md`)
mandates `<repo>/worktrees/<name>/` placement; do NOT work in
sibling dirs.

**Files:**
- [ ] Create: `worktrees/v18/` — feature worktree on branch
  `feat/v1.8-company-brand-account-model` (renames the canonical
  branch name per project-standards P2 finding #48).
- [ ] Modify: `x_monitor/migrations/004_company_brand_account_model.sql`
  — final SQL committed to the feature branch.
- [ ] Create: `deploy/migration-004-runbook.md` — operator-facing
  deploy + rollback runbook (the checklist below in a portable
  form so it lives in the repo, not just the plan).
- [ ] Modify: `x-monitoring/README.md` (if it exists) — add a
  "Migrating to v1.8" subsection referencing the runbook.

**Approach checkboxes:**

**Worktree setup (per `feedback_worktree_hygiene_x_monitoring.md`):**
- [ ] `git -C ~/development/minimax-marketing worktree list`
  — confirm no sibling worktrees from prior plans
- [ ] `git -C ~/development/minimax-marketing worktree add
  worktrees/v18 -b feat/v1.8-company-brand-account-model main`
- [ ] In the new worktree, symlink the shared venv:
  `ln -s ../../../../x-monitoring/.venv worktrees/v18/x-monitoring/.venv`
  (4 levels up per memory)
- [ ] Symlink the shared DB so dev work doesn't pollute prod:
  `ln -s ../../../../x-monitoring/data/x_monitoring.db
  worktrees/v18/x-monitoring/data/x_monitoring.db`
  (NOTE: for migration 004, this is REPLACED with a copy of
  the live DB — see dryrun step below)
- [ ] Tighten `.gitignore` to exclude `.venv`, `data/*.db*`,
  `data/runs/` so the symlinks aren't accidentally committed

**Pre-deploy checklist (Go/No-Go):**
- [ ] **PRE-01:** Worktree exists at
  `~/development/minimax-marketing/worktrees/v18` on branch
  `feat/v1.8-company-brand-account-model`
  (`git -C ~/development/minimax-marketing worktree list | grep v18`)
- [ ] **PRE-02:** Migration 004 SQL file exists and is
  syntactically valid
  (`test -f x-monitoring/x_monitor/migrations/004_company_brand_account_model.sql`)
- [ ] **PRE-03:** All 11 `data/brands/<brand>/detection.yaml`
  files exist (Unit 7 done)
  (`ls x-monitoring/data/brands/*/detection.yaml | wc -l` → 11)
- [ ] **PRE-04:** Disk ≥500 MB free on the data volume
  (DB=19 MB; backup=38 MB; growth<2 MB)
  (`df -m ~/development/minimax-marketing/x-monitoring/data`)
- [ ] **PRE-05:** SQLite ≥3.35 for `ALTER TABLE DROP COLUMN`
  (`sqlite3 --version` → expect 3.39+; the project is on 3.51.0)
- [ ] **PRE-06:** Baseline row counts captured
  (`sqlite3 data/x_monitoring.db 'SELECT COUNT(*) FROM posts;
  SELECT COUNT(*) FROM posts WHERE signal IS NOT NULL;
  SELECT COUNT(*) FROM posts WHERE author_id IS NOT NULL;'`)
  — expect 2008, 0, 0 respectively (signal/author_id currently
  never populated; pre-migration state matches plan's expectations)
- [ ] **PRE-07:** 297 tests pass on main BEFORE the migration
  PR merges (per `project_x_monitoring_v17_2026-06-17.md`; the
  2 pre-existing `test_headlines` failures are unrelated and
  expected)
  (`cd x-monitoring && .venv/bin/python -m pytest tests/ -q`)
- [ ] **PRE-08:** Plan reviewer findings (P0/P1 from this review
  pass) are explicitly closed — see the revision history at the
  top of `2026-06-18-195234-refactor-company-brand-account-model-plan.md`
  for the 2026-06-19 (review pass) entry
- [ ] **PRE-09:** x_monitor/config.py brand list matches the
  plan's 11 + `_unattributed` = 12
  (`grep -E "^\\s*'[a-z_0-9]+'," x_monitor/config.py`)

**Dryrun (BLOCKING — must complete before live migration):**
- [ ] Copy the live DB:
  `cp data/x_monitoring.db /tmp/x_monitoring.dryrun.db`
- [ ] Apply migration 004 to the dryrun:
  `sqlite3 /tmp/x_monitoring.dryrun.db <
  x_monitor/migrations/004_company_brand_account_model.sql`
  — expect ≤5 seconds on a 19 MB DB
- [ ] Run all 24 post-deploy verification queries (see below)
  on `/tmp/x_monitoring.dryrun.db`
- [ ] If ANY query fails, STOP. Investigate the migration SQL,
  fix, restart from PRE-09.
- [ ] On success, save the dryrun's sha256 as the live DB's
  expected post-migration sha256 (rough sanity check):
  `shasum -a 256 /tmp/x_monitoring.dryrun.db >
  /tmp/expected-post-004.sha256`

**Deploy procedure (live DB):**
1. `launchctl list | grep com.fuchitalee.x-monitor` — confirm
   not loaded
2. `launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist`
   — stop the cron pipeline
3. `lsof -nP -iTCP:5000 -sTCP:LISTEN -t | xargs -r kill`
   — stop the dashboard (kill-by-port, NEVER `pkill -f DashboardApp`
   per `feedback_pkill_matches_all_dashboardapp.md`)
4. Atomic backup:
   `TS=$(date -u +%Y%m%dT%H%M%SZ);
   cp data/x_monitoring.db data/x_monitoring.db.pre-004.${TS}.bak;
   shasum -a 256 data/x_monitoring.db > /tmp/pre-004.${TS}.sha256`
5. Backup integrity check:
   `sqlite3 data/x_monitoring.db.pre-004.${TS}.bak 'PRAGMA integrity_check;'`
   — expect `ok`
6. Apply migration 004:
   `sqlite3 data/x_monitoring.db <
   x_monitor/migrations/004_company_brand_account_model.sql`
   — expect ≤5 seconds
7. Verify `_migrations` ledger:
   `sqlite3 data/x_monitoring.db 'SELECT version, applied_at
   FROM _migrations ORDER BY version;'`
   — expect rows 1, 2, 3, 4
8. Run all 24 post-deploy verification queries (see below) —
   STOP and rollback if any expectation fails
9. Run the `reattribute_all_posts` subcommand (Unit 4's
   backfill bridge):
   `python -m x_monitor reattribute --since $(sqlite3 data/x_monitoring.db
   'SELECT MIN(created_at) FROM posts')`
   — fills `post_brands` + `post_mentions` for the existing
   2,008 posts so the dashboard has data on first load
10. `launchctl load ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist`
    — restart the cron pipeline
11. Start the dashboard on :5000 (or whichever port
    `x-monitor/dashboard.py` binds):
    `cd ~/development/minimax-marketing/x-monitoring &&
    nohup .venv/bin/python -m x_monitor dashboard --port 5000
    > ~/Library/Logs/x-monitor/dashboard.log 2>&1 &`
12. Wait 30s and `tail -50 ~/Library/Logs/x-monitor/stderr.log`
    — must show no `OperationalError: no such column` or
    `no such column: model_id`

**Post-deploy verification queries (run all 24):**

```sql
-- POST-01: confirm new tables exist
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
-- Expected: includes _migrations, account_post_appearances,
-- accounts, brand_accounts, brand_companies, brand_hashtags,
-- brand_keywords, brand_search_terms, brands, companies,
-- company_accounts, post_brand_signals, post_brands,
-- post_mentions, posts, search_queries

-- POST-02: brands seeded to 12 rows
SELECT COUNT(*) FROM brands;  -- Expected: 12

-- POST-03: companies seeded
SELECT COUNT(*) FROM companies;  -- Expected: 10..13

-- POST-04: no posts lost
SELECT COUNT(*) FROM posts;  -- Expected: 2008

-- POST-05: model_id column gone
SELECT COUNT(*) FROM pragma_table_info('posts')
WHERE name='model_id';  -- Expected: 0

-- POST-06: signal column gone
SELECT COUNT(*) FROM pragma_table_info('posts')
WHERE name='signal';  -- Expected: 0

-- POST-07: favorite_count renamed to like_count
SELECT COUNT(*) FROM pragma_table_info('posts')
WHERE name='favorite_count';  -- Expected: 0
SELECT COUNT(*) FROM pragma_table_info('posts')
WHERE name='like_count';  -- Expected: 1

-- POST-08: like_count populated
SELECT COUNT(*) FROM posts WHERE like_count IS NOT NULL;
-- Expected: 2008

-- POST-09: post_brands populated post-reattribute
SELECT COUNT(*) FROM post_brands;  -- Expected: 2008+

-- POST-10: post_brand_signals backfilled
SELECT COUNT(*) FROM post_brand_signals;
-- Expected: ≈ number of posts that had a non-NULL
-- posts.signal pre-migration (likely 0 in current prod since
-- signal was never populated; the per-brand classifier
-- populates this on the next cycle)

-- POST-11: post_mentions populated post-reattribute
SELECT COUNT(*) FROM post_mentions;  -- Expected: 4000+

-- POST-12: translation indexes have new predicates (incl. 'und')
SELECT name, sql FROM sqlite_master WHERE type='index'
AND name LIKE 'idx_posts_text_%';
-- Expected: idx_posts_text_en_backfill and
-- idx_posts_text_zh_cn_backfill with WHERE ... NOT IN
-- (..., 'und')

-- POST-13: new attribution indexes exist (incl.
-- idx_post_brand_signals_brand_signal)
SELECT name FROM sqlite_master WHERE type='index'
AND name LIKE 'idx_post%';
-- Expected: idx_post_brands_brand,
-- idx_post_brands_brand_post,
-- idx_post_mentions_brand_source_recent,
-- idx_post_mentions_post,
-- idx_post_brand_signals_brand_signal,
-- idx_post_brand_signals_post

-- POST-14: post_brands schema correct (no is_primary)
PRAGMA table_info(post_brands);
-- Expected: brand_id, post_id, weight; PK(brand_id, post_id)

-- POST-15: post_mentions schema with 4 source categories
PRAGMA table_info(post_mentions);
-- Expected: post_id, brand_id, source, raw_token, mentioned_at;
-- PK(post_id, brand_id, source)

-- POST-16: accounts recreated with author_id PK + bio columns,
-- role DROPPED
SELECT name FROM pragma_table_info('accounts')
WHERE name IN ('author_id','handle','bio','bio_fetched_at','role');
-- Expected: author_id, handle, bio, bio_fetched_at present;
-- role ABSENT

-- POST-17: detection tables seeded from detection.yaml
SELECT COUNT(*) FROM brand_hashtags;  -- Expected: >0 (~30-100)
SELECT COUNT(*) FROM brand_keywords;  -- Expected: >0 (~50-100)

-- POST-18: brand_search_terms seeded from queries.yaml
SELECT COUNT(*) FROM brand_search_terms;  -- Expected: 30..80

-- POST-19: ledger advanced to 4
SELECT MAX(version) FROM _migrations;  -- Expected: 4

-- POST-20: _unattributed is sentinel
SELECT is_sentinel FROM brands WHERE brand_id='_unattributed';
-- Expected: 1

-- POST-21: lang_detected backfilled for translated posts
SELECT COUNT(*) FROM posts
WHERE (text_en IS NOT NULL AND lang_detected IS NULL)
   OR (text_zh_cn IS NOT NULL AND lang_detected IS NULL);
-- Expected: 0

-- POST-22: degraded_accounts.json exists if any backfill warnings
test -f data/runs/<latest>/degraded_accounts.json && cat data/runs/<latest>/degraded_accounts.json
-- Expected: file exists; may be empty [] if all posts had author_id

-- POST-23: reattribute_all_posts produced rows
SELECT COUNT(DISTINCT post_id) FROM post_brands;
-- Expected: 2008 (or close — some posts may have been marked
-- _unattributed and skipped)

-- POST-24: weight conservation
SELECT post_id, SUM(weight) FROM post_brands GROUP BY post_id
HAVING ABS(SUM(weight) - 1.0) > 0.001;
-- Expected: 0 rows (allow 0.001 epsilon for floating-point drift
-- per P2 finding #32)
```

**Rollback procedure:**
1. `launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist`
2. `lsof -nP -iTCP:5000 -sTCP:LISTEN -t | xargs -r kill`
3. Restore DB:
   `cp data/x_monitoring.db.pre-004.<TS>.bak data/x_monitoring.db`
4. Verify: `sqlite3 data/x_monitoring.db 'PRAGMA integrity_check;'`
   — expect `ok`
5. Verify ledger rolled back:
   `sqlite3 data/x_monitoring.db 'SELECT MAX(version) FROM _migrations;'`
   — expect `3`
6. Code rollback:
   `cd ~/development/minimax-marketing && git checkout main &&
   git revert <migration-004-merge-commit>`
   (OR `git checkout <pre-migration-sha>`)
7. `launchctl load ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist`
8. Start dashboard back up (step 11 of Deploy)
9. `curl -s -o /dev/null -w 'HTTP %{http_code}\n' --max-time 5
   http://127.0.0.1:5000/` — expect 200
10. Total rollback time: ~5 minutes

**Monitoring (first 24h post-deploy):**
- **MON-01:** `stderr.log` shows `no such column` / `OperationalError`
  → ROLLBACK (pipeline on stale code)
- **MON-02:** `post_brands` row count after 1h — alert if <100
  (Unit 4 / reattribute not running)
- **MON-03:** `post_mentions` row count after 1h — alert if <500
  (4-source extraction broken)
- **MON-04:** `GET /` and `GET /grid` HTTP code — alert on non-200
- **MON-05:** `GET /brand/<id>` HTTP code for all 11 brands —
  alert on non-200
- **MON-06:** `SUM(weight) GROUP BY brand_id` — alert if all zeros
  after 4h
- **MON-07:** `launchctl list | grep com.fuchitalee.x-monitor`
  — alert if process missing
- **MON-08:** posts row count growth — alert if zero growth in 24h
  with cron active
- **MON-09:** post_brand_signals distribution by signal — alert if
  still all zeros after 4h (per-brand classifier not running)
- **MON-10:** DB file size — alert if >25 MB within 24h

**Failure indicators (rollback triggers):**
- **P0:** `stderr.log` shows `no such column: model_id` or
  `no such column: signal` or `no such column: favorite_count`
  → ROLLBACK IMMEDIATELY (pipeline on stale code)
- **P0:** `pragma_table_info('posts')` shows `model_id` or
  `signal` while `_migrations MAX(version) = 4` → ROLLBACK
  (partially applied migration)
- **P0:** Dashboard returns 500 on `/brand/<id>` routes → ROLLBACK
- **P0:** `PRAGMA integrity_check` returns anything other than
  `ok` → ROLLBACK IMMEDIATELY from backup (corruption)
- **P1:** `post_brands` empty after 1h of pipeline runs →
  investigate Unit 4 / reattribute
- **P1:** `pytest tests/` fails after deploy → code/schema mismatch
- **P2:** `post_brand_signals` empty after 4h → per-brand
  classifier not running (non-blocking; treemap shows 'no data')

**Test scenarios:**
- [ ] **Happy path - worktree setup:** Operator can run the
  `git worktree add` command and see the new worktree.
- [ ] **Happy path - dryrun passes:** All 24 post-deploy
  verification queries return the expected values on
  `/tmp/x_monitoring.dryrun.db`.
- [ ] **Happy path - live migration:** All 24 queries pass on
  the live DB after `reattribute_all_posts` runs.
- [ ] **Error path - dryrun fails:** A migration failure on the
  dryrun leaves `/tmp/x_monitoring.dryrun.db` in a clean state
  (SQLite transaction rollback) and the operator sees a clear
  error. The live DB is untouched.
- [ ] **Error path - mid-deploy failure:** Live DB migration
  fails mid-transaction. `_migrations` does NOT have row 4.
  Re-run is a no-op (`IF NOT EXISTS` guards) — operator must
  drop the partial state manually (or re-run after fix).
- [ ] **Error path - rollback restores:** After triggering a
  rollback, `curl /` returns 200 and `_migrations MAX(version) = 3`.
- [ ] **Integration - 24h monitoring:** No MON-01 through MON-10
  alerts fire in the first 24h.

**Verification:**
- [ ] Worktree `worktrees/v18/` exists with the feature branch
- [ ] `deploy/migration-004-runbook.md` is committed
- [ ] All 24 POST-NN queries are documented in the runbook
- [ ] The rollback procedure is rehearsed once on the dryrun DB
- [ ] `_migrations` shows version 4 after deploy; `3` after
  rollback rehearsal

---

## System-Wide Impact

- **Interaction graph:** `attribute_to_brand` is the choke point
  for brand attribution. It is called from `dashboard.py`
  (drill-down view), `__main__.py` (CLI ingest), `run.py`
  (pipeline), and `review.py` (review queue UI). Every caller
  must be updated to handle the new `list[brand_id]` return
  shape.
- **Error propagation:** The migration is a single transaction.
  A failure mid-migration rolls back the whole conversion; the
  DB is left in the pre-migration state. The `_migrations`
  ledger is not updated on failure, so a re-run is a no-op
  until the underlying issue is fixed.
- **State lifecycle risks:** The `account_post_appearances`
  table is dropped and recreated. The existing data is
  backfilled from `posts.author_id` (where available). Posts
  with `author_id IS NULL` lose their `account_post_appearances`
  rows on the first migration; a follow-up re-ingest of those
  posts (which the pipeline will do automatically on the next
  run, since they have no `author_id` to dedupe on) restores
  them with `author_id` populated.
- **API surface parity:** The `/model/<id>` route is removed
  and replaced with `/brand/<id>`. Any external links pointing
  to the old URL will 404; the dashboard can be configured to
  redirect (not in scope for this plan; add a TODO in
  `dashboard.py`).
- **Integration coverage:** Unit 4's "Integration - full
  pipeline" test is the only end-to-end check. The existing
  297-test suite covers individual components; the new test
  covers the cross-component chain (ingest -> attribute ->
  populate post_brands -> populate post_mentions -> insert
  post).
- **Unchanged invariants:** The dashboard UI does not change
  in this plan. The 11 brand cards, the treemap, the grid
  view, the drill-down view, the polarity window toggle, the
  view-tabs - all unchanged. The data model behind them is
  reshaped, the surface is not.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The 297-test suite has fixtures that hard-code `model_id` and `favorite_count`. A mechanical sed rename misses the cases that depended on `posts.model_id` as a column (not just an identifier). | Med | Med | Unit 6 has an explicit `grep -rn "model_id\|favorite_count" tests/ data/ docs/` regression check, plus a per-test review of any fixture that uses `posts.model_id` as a column (those become JOINs in Unit 2). |
| The `accounts` PK change to `author_id` loses data for posts where `author_id` is NULL. | Low | Low | The migration backfills from the most recent `posts.author_id` per handle; rows where no `author_id` exists are logged in the run summary as `degraded:backfill:missing_author_id`. A re-ingest repopulates. |
| The translation index predicate (`lang_detected NOT IN ('en', 'en-US', 'en-GB')`) is more restrictive than the current (`text_en IS NULL`). Rows with `lang_detected IS NULL` (translation pass hasn't run yet) used to be in the old index, are NOT in the new one. The backfill won't pick them up. | Med | Med | Migration 004 includes a one-time `UPDATE posts SET lang_detected = 'en' WHERE text_en IS NOT NULL AND lang_detected IS NULL` (and same for zh-CN) to populate `lang_detected` from the existing translation columns for already-translated posts. The new index then correctly excludes them. |
| The dashboard route `/model/<id>` removal breaks any bookmarked URLs. | Low | Low | Add a redirect in `dashboard.py`: `@app.route('/model/<id>')` -> `redirect('/brand/<id>', code=301)`. Tiny diff. |
| The yaml file moves (`data/queries/` -> `data/brands/<brand>/`) are not picked up by the running pipeline until a restart. | Low | Low | The LaunchAgent restart on next deploy picks up the new paths. No data is at risk. |
| The `companies` table seeded with hard-coded mappings (Alibaba->Qwen etc.) becomes wrong if a corporate parent changes (e.g., spinoff, acquisition). | Low | Low | The `brand_companies` table is the source of truth; a config update + a `reindex-companies` subcommand (not in this plan) re-seeds from a new config. |
| The `_unattributed` sentinel brand appears in the treemap and the grid. | Med | Med | The treemap's `is_sentinel` flag in the `brands` table is honored by `treemap.py` - sentinel brands are excluded from the layout and rendered in a "no data" strip alongside the other no-data models. The grid filters sentinel brands out. |
| A post in `zh-Hant` (Traditional Chinese) gets translated to `text_zh_cn` (Simplified). The user expected `zh-Hant` to skip the `zh-CN` translation. | Med | Low | The translation pipeline normalizes `zh-Hant` to `zh-Hans` for the column name; a comment in migration 003 (already there) notes this. The index predicate `NOT IN ('zh', 'zh-CN', 'zh-Hans', 'zh-Hant')` correctly excludes all four. |

## Documentation / Operational Notes

- **Docs to update:**
  - `docs/reference/2026-06-18-145000-x-monitoring-db-schema.md`
    - re-emit with the new schema (the doc was written this
    morning and is the source of truth for "what's in the DB").
  - `docs/plans/2026-06-17-001-...` - add a "Note: this plan
    uses `model_id` for the column; see
    `2026-06-18-195234-refactor-company-brand-account-model-plan.md`
    for the rename." The plan is otherwise unaffected.
  - `docs/plans/2026-06-17-002-...` - same note. The treemap
    code uses `MODEL_ACCENT_COLORS` and `MODEL_DISPLAY_NAMES`,
    which become Store reads; the plan logic is unaffected.
- **Runbook:** Add a one-paragraph note to the
  `x-monitoring/README.md` (if it exists) on how to verify
  the migration: `sqlite3 data/x_monitoring.db ".schema
  brands"` shows the 12 rows.
- **Monitoring:** No new metrics. The dashboard's existing
  `/api/runs.json` endpoint returns brand_attribution counts
  from the `post_brands` table; this is the same data as
  before, just sourced from a different table.
- **Rollout:** Land Units 1-2-3-6 as one PR (the core rename
  and migration), Unit 4 as a follow-up PR (the
  attribution changes), Unit 5 as a config-only PR if the
  user wants `filters/` moved. Each PR is independently
  revertable.

## Sources & References

- **Origin document:** none (direct-entry planning request;
  bootstrap framing in this plan)
- Related code: `x_monitor/migrations/00{1,2,3}_*.sql`,
  `x_monitor/store.py`, `x_monitor/dashboard.py`,
  `x_monitor/treemap.py`, `x_monitor/config.py`,
  `x_monitor/apify.py`, `x_monitor/accounts.py`
- Related plans:
  - `docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md`
  - `docs/plans/2026-06-17-002-feat-finviz-treemap-front-page-plan.md`
- Related docs:
  - `docs/reference/2026-06-18-145000-x-monitoring-db-schema.md`
  - `docs/research/2026-06-18-144300-treemap-style-references-research.md`
- External docs:
  - X API v2 tweet object: https://developer.x.com/en/docs/twitter-api/data-dictionary/object-model/tweet
  - X API v2 user object: https://developer.x.com/en/docs/twitter-api/data-dictionary/object-model/user
  - X UI rename (favorite->like), Nov 2021 - public knowledge
- Institutional learnings (from MEMORY.md):
  - `feedback_remote_path_shape_not_sshfs.md` - `/Users/fuchitalee/`
    is local; no ssh for reads
  - v1.7 brand-attribution decision: `data/accounts/<m>.yaml` is
    the source of truth
  - v1.1 dashboard label change: `favorite_count` is labeled
    "likes" in the UI

---

## Appendix A: Schema diff (current → migration 004)

This appendix shows the exact schema transformation that migration
004 introduces. The baseline is the schema documented in
`docs/reference/2026-06-18-145000-x-monitoring-db-schema.md`
(as of 2026-06-18, 19 MB DB, 2,008 posts).

Legend: `[+]` = added, `[-]` = removed, `[~]` = renamed,
`[>]` = shape changed (new columns / new PK / new FK), `[ ]`
= unchanged.

### `posts` table

```
posts
[~] ├── tweet_id*           TEXT  PK
[-] ├── model_id*           TEXT                                 ← DROPPED; attribution moves to post_brands
[~] ├── author_handle*      TEXT
[ ] ├── author_id           TEXT
[ ] ├── text                TEXT
[ ] ├── lang                TEXT
[ ] ├── created_at          TEXT
[ ] ├── fetched_at*         TEXT
[~] ├── like_count          INTEGER  DEFAULT 0                   ← renamed from favorite_count (was Apify-era name; X v2 uses likeCount)
[ ] ├── retweet_count       INTEGER  DEFAULT 0
[ ] ├── reply_count         INTEGER  DEFAULT 0
[ ] ├── quote_count         INTEGER  DEFAULT 0
[ ] ├── in_reply_to_user_id TEXT                                 ← unchanged (Decision 5; matches X v2 inReplyToUserId)
[ ] ├── quoted_status_id    TEXT
[ ] ├── conversation_id     TEXT
[ ] ├── entities            TEXT  JSON
[ ] ├── source_query_id     TEXT                                 ← unchanged name; FK to new search_queries table
[ ] ├── raw                 TEXT  JSON
[ ] ├── headline            TEXT
[ ] ├── headline_source     TEXT
[ ] ├── text_en             TEXT
[ ] ├── text_zh_cn          TEXT
[ ] ├── lang_detected       TEXT
[-] └── signal              TEXT                                 ← DROPPED; per-brand signal moves to post_brand_signals (R6d)
```

Indexes:

```
[-] idx_posts_model_created   (model_id, created_at DESC)         ← DROPPED; model_id column gone
[ ] idx_posts_author          (author_handle)
[~] idx_posts_headline_null_urlonly (tweet_id) WHERE headline IS NULL
                                                                ← unchanged name/predicate
[~] idx_posts_text_en_backfill    ON posts(tweet_id)             ← RENAMED from idx_posts_text_en_null,
    WHERE text_en IS NULL                                          predicate widened: also requires
      AND lang_detected IS NOT NULL                                lang_detected set AND not en* (Decision 8)
      AND lang_detected NOT IN ('en','en-US','en-GB')
[~] idx_posts_text_zh_cn_backfill ON posts(tweet_id)             ← RENAMED + widened predicate (Decision 8)
    WHERE text_zh_cn IS NULL
      AND lang_detected IS NOT NULL
      AND lang_detected NOT IN ('zh','zh-CN','zh-Hans','zh-Hant')
[ ] idx_posts_lang_detected   (lang_detected)
[-] idx_posts_signal_model    (model_id, signal)                  ← DROPPED; signal column gone
[+] idx_post_brand_signals_brand_signal                          ← NEW
        ON post_brand_signals(brand_id, signal)
```

### `accounts` table (PK change + 2 new cols)

```
accounts
[>] author_id          TEXT  PK                                  ← NEW PK (was composite (model_id, handle))
[-] model_id           TEXT  PK[1]                               ← DROPPED from PK (and from table)
[>] handle             TEXT  NOT NULL                            ← was PK[2]; now regular column
[+] bio                TEXT                                      ← NEW (R13)
[+] bio_fetched_at     TEXT                                      ← NEW (R13)
[ ] display_name       TEXT
[>] role               TEXT  DEFAULT 'unknown'                   ← now per-brand via brand_accounts.role
[ ] verified           INTEGER DEFAULT 0
[ ] bio_contains_brand INTEGER DEFAULT 0                         ← preserved as cached flag (R13)
[ ] engagement_tier    TEXT  DEFAULT 'low'
[-] multi_brand_voice  INTEGER DEFAULT 0                         ← DROPPED (R12, Q11)
[ ] first_seen_at      TEXT
[ ] last_seen_at       TEXT
[ ] source_query_ids   TEXT  JSON
[ ] notes              TEXT
```

### `account_post_appearances` table (PK change)

```
account_post_appearances
[>] author_id     TEXT  PK[1]                                    ← NEW PK component (was model_id)
[-] model_id      TEXT  PK[1]                                    ← DROPPED from PK
[-] handle        TEXT  PK[2]                                    ← DROPPED from PK (moved into accounts as denormalized column)
[>] tweet_id      TEXT  PK[2]                                    ← was PK[3]; now PK[2]
[ ] role_at_time  TEXT
```

FKs:

```
[-] FOREIGN KEY(model_id, handle) REFERENCES accounts(model_id, handle) ON DELETE CASCADE   ← DROPPED (no matching composite FK on new accounts)
[ ] FOREIGN KEY(tweet_id) REFERENCES posts(tweet_id) ON DELETE CASCADE                     ← unchanged
```

### New tables

```
companies                                                            [+] NEW
   company_id    PK
   display_name, hq_country, created_at

brands                                                               [+] NEW
   brand_id      PK
   display_name, accent_color, is_sentinel, created_at
   (seeded with 11 brands + _unattributed sentinel)

brand_companies                                                      [+] NEW
   brand_id      FK → brands
   company_id    FK → companies
   ownership_pct REAL DEFAULT 1.0
   PK (brand_id, company_id)

brand_accounts                                                       [+] NEW
   brand_id      FK → brands
   author_id     FK → accounts
   role          (official | staff | community | researcher | press | unknown)
   PK (brand_id, author_id)

company_accounts                                                     [+] NEW
   company_id    FK → companies
   author_id     FK → accounts
   role          (same enum as brand_accounts)
   PK (company_id, author_id)

post_brands                                                          [+] NEW
   brand_id      FK → brands
   post_id       FK → posts
   weight        REAL DEFAULT 1.0
   PK (brand_id, post_id)
   -- weight = 1.0 / N_distinct_brands for the post (per Decision 9)

post_mentions                                                        [+] NEW (4 columns, expanded from 3)
   post_id       FK → posts    ON DELETE CASCADE
   brand_id      FK → brands   ON DELETE SET NULL  -- nullable for unattributed
   source        IN (user_mention, hashtag, body_keyword, search_term)
   raw_token     TEXT NOT NULL  -- literal matched text: "@MiniMaxAI", "#minimax", "M3.0"
   mentioned_at  TEXT NOT NULL  -- posts.created_at, denormalized for index-only range queries
   PK (post_id, brand_id, source)
   -- a post naming minimax 3 ways writes 3 rows for minimax
   -- dedup to 1 post_brands row happens at the consolidator (not here)

post_brand_signals                                                   [+] NEW (R6d)
   post_id       FK → posts    ON DELETE CASCADE
   brand_id      FK → brands   ON DELETE CASCADE
   signal        IN (release | community_question | criticism | commenter_capture | praise | other)
   PK (post_id, brand_id)
   -- replaces posts.signal with per-brand decomposition

brand_hashtags                                                       [+] NEW (R6a)
   brand_id      FK → brands   ON DELETE CASCADE
   tag           TEXT          -- lowercase, no '#' prefix
   added_at      TEXT
   PK (brand_id, tag)

brand_keywords                                                       [+] NEW (R6b)
   brand_id      FK → brands   ON DELETE CASCADE
   pattern       TEXT          -- literal substring or regex source
   is_regex      INTEGER DEFAULT 0
   added_at      TEXT
   PK (brand_id, pattern)

brand_search_terms                                                   [+] NEW (R6c)
   brand_id      FK → brands   ON DELETE CASCADE
   term          TEXT          -- one keyword/operator from the plan_calls config
   added_at      TEXT
   PK (brand_id, term)

search_queries                                                       [+] NEW (R6c storage fork)
   query_id          PK         -- matches posts.source_query_id
   brand_id          FK → brands ON DELETE CASCADE
   keywords_json     TEXT       -- JSON array of keyword strings
   plan_calls_run_id TEXT       -- optional FK to the run that produced this query
   created_at        TEXT
```

### `_migrations` table (unchanged shape)

```
_migrations
[ ] version*    INTEGER  PK
[ ] applied_at* TEXT

Rows after migration 004:
   1, 2, 3, 4   (the new row is appended by Store._apply_migration)
```

### ER overview after migration 004

```
                              brands (brand_id PK)
                                  |
            +---------------------+---------------------+---------------------+
            |                     |                     |                     |
       brand_companies      brand_accounts         brand_keywords        brand_hashtags
        (brand_id,           (brand_id,             (brand_id,            (brand_id,
         company_id)           author_id)            pattern)             tag)
            |                     |                     |                     |
            v                     v                     v                     v
       companies             accounts (author_id PK)        brand_search_terms
                                  |                        (brand_id, term)
                                  |
                            account_post_appearances
                              (author_id, post_id) PK
                                       |
                                       v
   posts (tweet_id PK, NO brand_id) <-----+
        |                                  |
        +-- post_brands                     |
        |   (brand_id, post_id)            |
        |   weight REAL                     |
        |                                  |
        +-- post_mentions                   |
        |   (post_id, brand_id, source,    |
        |    raw_token, mentioned_at)      |
        |   PK (post_id, brand_id, source) |
        |                                  |
        +-- post_brand_signals -------------+
            (post_id, brand_id, signal) PK
```

### Summary of changes

| Change type | Count | Examples |
|---|---|---|
| Column renamed | 1 | `posts.favorite_count` → `posts.like_count` |
| Column dropped | 4 | `posts.model_id`, `posts.signal`, `accounts.multi_brand_voice`, `accounts.model_id` (PK part) |
| New column on existing table | 2 | `accounts.bio`, `accounts.bio_fetched_at` |
| PK changed | 2 | `accounts` (composite → `author_id`), `account_post_appearances` (3-col → 2-col) |
| Index renamed | 2 | `idx_posts_text_en_null` → `idx_posts_text_en_backfill` (predicate widened); same for zh-CN |
| Index dropped | 2 | `idx_posts_model_created`, `idx_posts_signal_model` |
| Index added | 1 | `idx_post_brand_signals_brand_signal` |
| New tables | 11 | `companies`, `brands`, `brand_companies`, `brand_accounts`, `company_accounts`, `post_brands`, `post_mentions`, `post_brand_signals`, `brand_hashtags`, `brand_keywords`, `brand_search_terms` (+ `search_queries` for R6c storage fork = 12 total) |
| FK dropped | 1 | `account_post_appearances (model_id, handle) → accounts` (no longer applicable) |
| FK added | several | `post_brands`, `post_mentions`, `post_brand_signals`, `brand_*` tables → `brands` / `accounts` |

Net: ~12 new tables, 4 dropped columns, 1 renamed column, 2 new columns on existing tables. The `posts` table gets **smaller** (no `model_id`, no `signal`) and gains no new columns. The dashboard routes (`/model/...` → `/brand/...`) and code identifiers (`model_id` → `brand_id`) are renamed in a separate unit (Unit 2).
