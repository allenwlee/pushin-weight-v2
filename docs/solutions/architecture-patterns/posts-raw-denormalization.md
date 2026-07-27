---
module: core
date: 2026-07-27
problem_type: data_migration
component: schema
severity: high
last_updated: 2026-07-27
applies_when:
  - "Promoting JSONB blob fields to typed columns on a high-write table"
  - "Self-referential FK on a graph-shaped relationship where the parent may not exist locally"
  - "Harvest code that already partially flattens a wire payload — the gap is persistence, not extraction"
symptoms:
  - "Every query against a wire-field column requires a jsonb expression"
  - "Two copies of every wire field (outer snake + inner camel) in the same JSONB"
  - "Index support is jsonb-expression only"
  - "Quote/retweet relationship is captured as plain text id, not a join"
---

# Denormalize posts.raw into typed columns and drop the column

## Problem

`posts.raw` was a JSONB blob that held the entire TwitterAPI.io tweet payload. The harvest code in `x_monitor/apify.py:_normalize_tweet` already flattens 12 camelCase fields to snake_case twins at the top of the item dict, then `_upsert_post` writes the whole dict to `raw`. Three artifacts:

1. Schema is invisible — querying `viewCount` requires `posts.raw->'raw'->>'viewCount'`; index support is jsonb-expression only.
2. The harvest code double-writes — the same logical field lives in `created_at` (top) and `createdAt` (inner), `like_count` (top) and `likeCount` (inner), etc.
3. Quote/retweet graph is captured as a plain text id with no join path.

## Solution

Four ordered units (U0–U4) plus a regression net (U5):

- **U0: prod census** — before any schema work, document outer-snake vs inner-camelCase key presence on prod. Critical finding: 13 of 20 new tweet fields have **no** outer snake twin (only `raw->'raw'` has them); 22 of 22 new author fields are 100% populated in the inner `author` block. The dual-path COALESCE in § 1.6 of the plan is the right backfill strategy.
- **U1: schema migration** — add 50 new nullable columns (per § 1.2/1.3) + convert `quoted_status_id` to a self-referential `ForeignKey` (`on_delete=SET_NULL`, deferrable).
- **U2: data backfill with policy A** — chunked (10k) SQL UPDATE from `posts.raw`. `quoted_status_id` is backfilled **last**, only when the target `tweet_id` already exists in `posts` (policy A: no stub rows, no dangling FKs).
- **U3: harvest code update** — extend `_normalize_tweet` to extract all 50 new keys (with § 1.7 NULL-when-absent semantics); extend `_upsert_post` to write the typed columns; fix `_upsert_account` key-name bug (`author_followers` → `author_followers_count`); dual-write overlapping author fields to `Account` (R14).
- **U4: drop `posts.raw`** — generate `RemoveField` migration; remove `defaults["raw"] = ...` from `_upsert_post` and the `"raw": item` key in `_normalize_tweet`; clean up the dead `raw` references in the historical v1→PG bridge scripts.
- **U5: regression net** — `tests/test_post_schema_denormalization.py` with three layers: column pin (model-introspection, runs on any backend), FK pin (Postgres-only, asserts no orphan ids), harvest pin (pure-Python, asserts `_normalize_tweet` returns the new keys with the right types).

## Surprises (U0 census)

- **Author fields are 100% populated on prod** in the inner `raw->'raw'->'author'` block, despite the harvest code's partial outer-snake normalization (7,196 rows on `author_description`, etc.). The 7,196-row block was a harvest-path partial, not a TwitterAPI reality.
- **Many TwitterAPI fields have no outer snake twin** because the harvest code's `_normalize_tweet` only extracts 12 fields. `viewCount`, `card`, `place`, `displayTextRange`, `type`, `url`, `twitterUrl`, `source`, `article`, `communityInfo`, `isLimitedReply`, `extendedEntities`, `inReplyToId`, `inReplyToUsername` exist only in `raw->'raw'`.
- **`is_limited_reply` and `community_info`** are sparse (26,780 of 27,841 rows) — predates the TwitterAPI response shape change. The migration leaves them NULL on the gap rows.
- **`source_query_id` is harvest-stamped**, not from TwitterAPI — confirmed by it being top-level only (25,444 rows), absent from `raw->'raw'`.

## Deviations from the plan

- **Three array-typed columns** (`display_text_range`, `author_pinned_tweet_ids`, `author_withheld_in_countries`) are stored as `jsonb` instead of `integer[]`/`text[]` because the dev DB is SQLite (no `ArrayField`). Data shape preserved; a follow-up prod migration can `ALTER COLUMN ... TYPE integer[] USING jsonb_array_elements_text(...)` if element-wise query is needed.
- **`is_reply`/`is_retweet`/`is_quote` no longer coerce missing keys to `False`** — they return `None` per § 1.7. `_upsert_post` and `_normalize_tweet` were updated to match.
- **`_upsert_account` key-name fix** — the prior code referenced `author_followers` / `author_following` (without `_count`) but the normalize layer never set those keys, so `accounts.followers_count` and `accounts.following_count` were silently never written. Fixed in U3.

## Operational gate (U4)

The plan's U4 gate (per Grok review) is: **for posts fetched in the last hour that had a non-null source value available at write time, the typed column must not be NULL**. This is a property of the harvest deployment, not a unit test. Verify on prod after the harvest has run ≥1 cycle on the new code:

```sql
-- Replace <col> with each new § 1.2/1.3 column. Expect 0 rows.
SELECT COUNT(*) FROM posts
WHERE fetched_at > NOW() - INTERVAL '1 hour'
  AND <col> IS NULL
  AND raw IS NOT NULL;  -- raw was dropped at U4; use the inner envelope directly
```

## Files touched

- `core/models.py` — extended `Post` with 50 new fields + self-FK
- `x_monitor/apify.py` — `_normalize_tweet` extracts all 50 new keys
- `monitor/cycle.py` — `_upsert_post` writes typed columns; `_upsert_account` fixed
- `scripts/bridge_sqlite_to_pg.py`, `scripts/port_sqlite_to_django.py` — removed dead `raw` writes
- `core/migrations/0002_add_post_twitterapi_columns.py` — schema
- `core/migrations/0003_backfill_post_twitterapi_columns.py` — U2 backfill with policy A
- `core/migrations/0004_drop_post_raw.py` — drop `raw`
- `tests/test_post_schema_denormalization.py` — U5 regression net

## Test results

U5 on dev (SQLite): 8 passed, 3 Postgres-only-skipped. The 3 skipped tests run on a Postgres test DB:

```bash
DATABASE_URL=postgres://user@host:5432/db pytest tests/test_post_schema_denormalization.py
```

U5 catches: column name drift, nullability drift, type-family drift, the `raw` column coming back, missing new column, FK present but not `ON DELETE SET NULL`, FK not deferrable, orphan FK ids, `_normalize_tweet` regressing on a new field, `_normalize_tweet` re-emitting `raw` after U4.
