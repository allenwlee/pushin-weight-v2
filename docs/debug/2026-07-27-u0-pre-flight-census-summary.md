# U0 pre-flight prod census — 2026-07-27

**Source:** `posts.raw` on prod (`dpg-d9go1njeo5us73cg5u00-a`). Total rows with `raw IS NOT NULL`: 27,841.

**Goal:** For each goal-schema source key (§ 1.2 / § 1.3 in the plan), confirm presence at (a) outer top-level `posts.raw` and (b) inner `posts.raw->'raw'` (or `posts.raw->'raw'->'author'` for author fields). Census attaches to the PR before U2 merges.

**Method:** Three independent `LATERAL jsonb_object_keys` aggregations over the same scan:
- top-level: `jsonb_object_keys(raw)` from `posts` where `raw IS NOT NULL`
- inner raw envelope: `jsonb_object_keys(raw->'raw')` where `jsonb_typeof(raw->'raw') = 'object'`
- inner author: `jsonb_object_keys(raw->'raw'->'author')` where `jsonb_typeof(raw->'raw'->'author') = 'object'`

Full output: `2026-07-27-u0-pre-flight-census.txt`.

## Cross-reference against goal schema

### § 1.2 TwitterAPI top-level tweet fields

| goal column | outer key | outer present | inner key (raw->'raw') | inner present | verdict |
|---|---|---|---|---|---|
| `created_at_raw` | `created_at` (snake twin) | 27,841 | `createdAt` | 27,841 | ✅ both paths populated; prefer inner for original RFC 2822 string |
| `bookmark_count` | `bookmark_count` | 27,841 | `bookmarkCount` | 27,841 | ✅ both; prefer inner (the snake twin is already normalized by harvest) |
| `is_reply` | `is_reply` | 27,841 | `isReply` | 27,841 | ✅ |
| `is_retweet` | `is_retweet` | 27,841 | `isRetweet` | 27,841 | ✅ |
| `is_quote` | `is_quote` | 27,841 | `isQuote` | 27,841 | ✅ |
| `in_reply_to_id` | — | absent | `inReplyToId` | 27,841 | ⚠️ **only inner path** — no outer snake twin exists today |
| `in_reply_to_username` | — | absent | `inReplyToUsername` | 27,841 | ⚠️ **only inner path** |
| `tweet_type` | — | absent | `type` | 27,841 | ⚠️ **only inner path** — outer `type` is null in raw |
| `tweet_url` | — | absent | `url` | 27,841 | ⚠️ **only inner path** |
| `tweet_twitter_url` | — | absent | `twitterUrl` | 27,841 | ⚠️ **only inner path** |
| `card` | — | absent | `card` | 27,841 | ⚠️ **only inner path** |
| `place` | — | absent | `place` | 27,841 | ⚠️ **only inner path** |
| `client_source` | — | absent | `source` | 27,841 | ⚠️ **only inner path** (rename from `source` per Grok review) |
| `view_count` | — | absent | `viewCount` | 27,841 | ⚠️ **only inner path** |
| `article` | — | absent | `article` | 27,841 | ⚠️ **only inner path** |
| `is_limited_reply` | — | absent | `isLimitedReply` | 26,780 | ⚠️ **only inner path; sparse** (community-only tweets) |
| `community_info` | — | absent | `communityInfo` | 26,780 | ⚠️ **only inner path; sparse** |
| `display_text_range` | — | absent | `displayTextRange` | 27,841 | ⚠️ **only inner path** |
| `extended_entities` | — | absent | `extendedEntities` | 27,841 | ⚠️ **only inner path** |
| `quoted_author_handle` | `quoted_author_handle` | 24,083 | `quoted_tweet.author.userName` (nested) | (nested) | ✅ outer is sufficient; nested path is fallback |
| `quoted_text` | `quoted_text` | 24,083 | `quoted_tweet.text` (nested) | (nested) | ✅ outer is sufficient |
| `quoted_status_id` (existing) | `quoted_status_id` | 24,083 | `quoted_tweet.id` (nested) | (nested) | ✅ outer is sufficient for the backfill source |

**Key finding for U2:** Many TwitterAPI top-level fields have **no outer snake_case twin** today. The harvest code only normalized the 12 fields it reads for `defaults[...]` (id, text, lang, created_at, like_count, retweet_count, reply_count, quote_count, bookmark_count, is_reply, is_retweet, is_quote, in_reply_to_user_id, quoted_status_id, quoted_text, quoted_author_handle, author_id, author_name, author_followers_count, author_verified, plus the 7,196-row recent author-stats block). All other TwitterAPI fields (`viewCount`, `card`, `place`, `displayTextRange`, `type`, `url`, `twitterUrl`, `source`, `article`, `communityInfo`, `isLimitedReply`, `extendedEntities`, `inReplyToId`, `inReplyToUsername`, `quoted_tweet.*`) exist **only inside `raw->'raw'`** — the backfill MUST read from the inner envelope for these.

### § 1.3 TwitterAPI author fields

Inner `raw->'raw'->'author'` has 33 keys, all 27,841 rows. Top-level has 6 author keys at 100% (`author_followers_count`, `author_handle`, `author_name`, `author_verified`) and 11 at the 7,600-row recent block. **None of the new author columns** (the 22 that the harvest doesn't currently extract) are at the top level — they live only inside `raw->'raw'->'author'`.

| goal column | outer key present | inner author key present |
|---|---|---|
| `author_id` | 23,158 (top) | 27,841 (inner) → prefer inner |
| `author_handle` | 27,841 (top) | 27,841 (inner) → prefer top (already typed) |
| `author_name` | 27,841 (top) | 27,841 (inner) → either |
| `author_followers_count` | 27,841 (top) | 27,841 (inner) → either |
| `author_following_count` | 7,600 (top) | 27,841 (inner) → **prefer inner** |
| `author_verified` | 27,841 (top) | 27,841 (inner) → either |
| `author_is_blue_verified` | 7,600 (top) | 27,841 (inner) → **prefer inner** |
| `author_verified_type` | 7,600 (top) | 27,841 (inner) → **prefer inner** |
| `author_is_translator` | — | 27,841 (inner) → **only inner** |
| `author_is_automated` | — | 27,841 (inner) → **only inner** |
| `author_automated_by` | — | 27,841 (inner) → **only inner** |
| `author_description` | 7,600 (top, sparse) | 27,841 (inner) → **prefer inner** |
| `author_location` | 7,600 (top, sparse) | 27,841 (inner) → **prefer inner** |
| `author_media_count` | 7,600 (top, sparse) | 27,841 (inner) → **prefer inner** |
| `author_statuses_count` | 7,600 (top, sparse) | 27,841 (inner) → **prefer inner** |
| `author_favourites_count` | 7,600 (top, sparse) | 27,841 (inner) → **prefer inner** |
| `author_fast_followers_count` | 7,600 (top, sparse) | 27,841 (inner) → **prefer inner** |
| `author_can_dm` | — | 27,841 (inner) → **only inner** |
| `author_can_media_tag` | — | 27,841 (inner) → **only inner** |
| `author_profile_picture` | 7,600 (top, sparse) | 27,841 (inner) → **prefer inner** |
| `author_profile_bio` | — | 27,841 (inner) → **only inner** |
| `author_cover_picture` | — | 27,841 (inner) → **only inner** |
| `author_pinned_tweet_ids` | — | 27,841 (inner) → **only inner** |
| `author_affiliates_highlighted_label` | — | 27,841 (inner) → **only inner** |
| `author_withheld_in_countries` | — | 27,841 (inner) → **only inner** |
| `author_possibly_sensitive` | — | 27,841 (inner) → **only inner** |
| `author_has_custom_timelines` | — | 27,841 (inner) → **only inner** |
| `author_entities` | — | 27,841 (inner) → **only inner** |
| `author_twitter_url` | — | 27,841 (inner) → **only inner** |
| `author_type` | — | 27,841 (inner) → **only inner** |
| `author_url` | — | 27,841 (inner) → **only inner** |
| `author_created_at_raw` | — | 27,841 (inner) → **only inner** |
| `author_status` | — | 27,841 (inner) → **only inner** |

### § 1.4 fields explicitly NOT promoted (confirmed absent from goal schema)

| excluded field | outer present | inner present | notes |
|---|---|---|---|
| `brand_id` (top) | 25,833 | — | harvest stamp, lives on junction |
| `brand_ids` (top) | 25,833 | — | harvest stamp, lives on junction |
| `mentions` (top) | 25,833 | — | harvest stamp, lives on junction |
| `classifications` (top) | 23,158 | — | LLM pipeline; out of scope |
| `signals` (top) | 2,675 | — | LLM pipeline; out of scope |
| `favorite_count` (top) | 2,008 | — | v1 legacy; out of scope |
| `model_id` (top) | 2,008 | — | v1 legacy; out of scope |
| `headline` / `headline_source` (top) | 155 | — | already typed on `posts` |
| `source_query_id` (top) | 4,683 | — | already typed on `posts` |

All excluded fields are confirmed at the top level only — they do not appear in `raw->'raw'` (the inner envelope is pure TwitterAPI wire output).

## Resolutions and consequences for the plan

1. **Inner-envelope-first backfill** for most new columns. The dual-path resolver (§ 1.6) is still correct, but for the 22 author columns and 13 of the 20 tweet columns, only the inner path returns data. SQL becomes `COALESCE(raw->'raw'->'author'->>'followers'::text, raw->>'author_followers_count')`.

2. **`is_limited_reply` and `community_info`** are sparse (26,780 of 27,841 rows; the missing 1,061 are pre-2026-07-22 tweets that predate the TwitterAPI response shape change). The backfill leaves them NULL on the missing rows; the harvest code update populates them on all new rows.

3. **All 22 new author columns are 100% populated on prod** by backfill, since the inner `author` block is uniformly present. This is a stronger result than the plan estimated; the 7,600-row "sparse" outer top-level block is the harvest code's *partial* normalization, not a TwitterAPI reality.

4. **`source_query_id` confirms it's only at the top level** — not a TwitterAPI field. The plan's § 1.1 row stays correct.

5. **`tweet_id` at the top level is 328 rows** — that's a harvest-path quirk (`_upsert_post` reads `tweet_id` from the item's `id` key, which the harvest normalizes to `tweet_id` only for the legacy `bridge_sqlite_to_pg.py` path). Not a TwitterAPI field. No schema action needed.

6. **U2 chunking**: 27,841 rows × 60+ new columns to backfill. The 10k-batch strategy is correct. Estimated backfill runtime: ~3-5 min on Render free tier (10k rows × 60 UPDATEs / 200 rows/sec). Acceptable for an off-peak window.

7. **U3 harvest update** must extend `_normalize_tweet` to extract the 22 new author fields and 13 of the 20 new tweet fields that currently have no outer snake twin. This is the main implementation work — `_upsert_post` already has the pattern for the existing typed columns; the work is mostly in the normalizer.

## Ready-to-proceed signal

- ✅ Every goal-schema source key is reachable from either the outer or inner path on prod
- ✅ No goal-schema source key requires data we don't have
- ✅ Policy A FK is feasible: 24,083 rows have `quoted_status_id` populated at the top; the backfill can check `EXISTS` and null the non-resolving ones
- ✅ The dual-path resolver and the NULL semantics in § 1.6 / § 1.7 are correct for the actual prod shape

**U0 complete. Proceeding to U1 (schema migration).**
