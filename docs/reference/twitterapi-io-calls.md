<!-- {{AGENT_ATTRIBUTION}} -->
# TwitterAPI.io call inventory

**Repo:** `x-monitoring` (Flask + htmx dashboard for X.com / Twitter monitoring of AI models — `minimax`, `qwen`, `deepseek`, `glm`, `xiaomi_mimo`, `moonshot_kimi`, `inclusionai`, `mistral`, `sakana`, `stepfun`, `ernie`, `hunyuan`, `llama`, `nvidia_nemo`, `doubao`, `yi`, `sensechat`, `exaone`, `kuaishou`, `upstage`)
**Migration origin:** 2026-06-08 — replaced `automation-lab/twitter-scraper` (Apify) with TwitterAPI.io. Cookie-free, ~95% cheaper ($0.15/1k tweets vs $3/1k on Apify).
**Source of truth:** `x-monitoring/x_monitor/apify.py` (`TwitterApiClient` class) and its callers.

**API key env var:** `TWITTERAPI_IO_API_KEY` (read at `TwitterApiClient.from_env()`; sent as `X-API-Key` header)
**Base URL:** `https://api.twitterapi.io`
**HTTP method:** All calls are `GET` with `params=...` query string
**Auth header:** `X-API-Key: <key>` (`x_monitor/apify.py:96`)
**Timeout:** 60 s per request; up to 3 attempts on 429/5xx/network. Backoff: 429 = 4s then 16s; 5xx/network = 1s then 2s. See [Error handling](#error-handling-shared-across-all-endpoints) for the exact `_get` loop.
**Last reviewed:** 2026-07-02 (JST)

This document lists every endpoint x-monitor calls, the call sites that invoke it, the cost model, and the per-call caps the code enforces.

## Per-request HTTP instrumentation (added 2026-07-02)

`TwitterApiClient` now records every logical HTTP exchange into an instance-level `_request_log` list (one entry per `_get` call, with retries collapsed). Fields captured per request (`x_monitor/apify.py:150-196`):

- `path` — endpoint, e.g. `/twitter/tweet/advanced_search`
- `params` — request params (string values truncated to 120 chars for readability)
- `status` — final HTTP status code (after any retries)
- `n_results` — items in the response list (`tweets` / `quotes` / `followers` / `users` / `data` if list)
- `duration_ms` — wall-clock duration including any retries
- `attempts` — number of HTTP attempts (1 = no retry)
- `has_next_page` — boolean: whether the response carried a continuation cursor

The log is captured into `summary["http_log"]` by `RunPipeline.execute` at `x_monitor/run.py:910` and serialized with the run JSON. A companion `summary["phase_timings_sec"]` (`x_monitor/run.py:541-551`) records wall-clock duration per phase (search loop, QT capture, etc.). Inspect any past run with `scripts/dump_http_log.py [RUN_ID | LATEST] [--out <path>]` — it prints a flat list and a grouped view (by search query / QT tweetId / single-call endpoint) and optionally writes a structured report JSON.

> **v1.7 (shipped 2026-06-17, commit `e218d13`):** the workhorse `/twitter/tweet/advanced_search` drops from 10–16 calls/cycle (v1.6) to exactly 2 calls/cycle. Call A is a `list:`-based query that pulls any tweet authored by anyone in a curated public x.com list; Call B is a paren-grouped OR-chain over all deduped brand tokens. v1.8 (commit `ce2eed1`) renamed `model_id` → `brand_id` across the schema and code.
>
> **Schema modernization batch (2026-06-24, `feat/schema-modernization-batch` → commit `4cd62d2`, unmerged):** the 9-unit migration set landed migrations 011-019 — `locale` → `lang` on i18n label tables (011), dropped `engagement_tier_keys` + `engagement_tier_labels` + `accounts.engagement_tier` (012), `post_mentions` → `posts_brands_mentions` (013), `signal_keys` → `signals` + `signal` → `signal_id` (014), `role_keys` → `roles` + `role` → `role_id` (015), roles trimmed to `{official, staff, community}` (016), `brand_search_terms` hybrid-by-design contract documented (017, no DDL), INTEGER PKs on `signals` + `roles` enum tables with the `key` column kept as TEXT UNIQUE — FK columns `signal_id` / `role_id` continue to hold the key string (018), and ADDITIVE `post_type` + `sentiment` columns on `posts_brands_signals` + new `post_type_keys` / `sentiment_keys` enum tables (019, legacy `signal_id` retained). The doc's column/table references below already use post-modernization names; the "official + staff" wording aligns with the post-016 role taxonomy.
>
> **2026-06-22 (quote-tweet capture):** two new endpoints added to the inventory — `/twitter/tweet/quotes` and `/twitter/tweets`. See [docs/plans/2026-06-22-quote-tweets-capture-plan.md](../plans/2026-06-22-quote-tweets-capture-plan.md) (Unit 5 in that plan). The `quote_tweets:` block in `x-monitoring/config.yaml` (`x_monitor/config.py:QuoteTweetConfig`) controls the call budgets.

---

## Endpoints used (6 total)

### 1. `GET /twitter/tweet/advanced_search` — the workhorse

**Method in code:** `TwitterApiClient.run_search(query, max_results, since, cookies)` → `_walk_search(query, max_results, max_pages=5)`
**File:** `x_monitor/apify.py:271-298` (public) + `_walk_search` at `x_monitor/apify.py:229-269`
**Path constant:** `SEARCH_PATH = "/twitter/tweet/advanced_search"` (`x_monitor/apify.py:27`)
**Per-page cap:** 20 tweets (`SEARCH_MAX_PER_PAGE = 20`)
**Pagination:** `has_next_page` + `next_cursor`; up to 5 pages (100 tweets max) per call
**Defensive cap:** `max_pages=5` (`x_monitor/apify.py:298`) — guards against a runaway cursor draining the credit budget. With 20 tweets/page × 5 pages = 100 tweets, which covers all current `max_results=50` calls with headroom.

**Query params sent:**
- `query` (str) — X advanced-search string. v1.7 Call A = `(list:<x_monitor_list_id>) min_faves:1`; Call B = `((BrandTok1a OR BrandTok1b) OR (BrandTok2a) OR ...) min_faves:0`. TwitterAPI.io accepts the same X operators including `list:`. The `since` kwarg, when provided, is appended as ` since:<YYYY-MM-DD>` ONLY if the caller's query doesn't already contain `since:` (`x_monitor/apify.py:295-297`).
- `queryType` (str) — always `"Latest"` (`x_monitor/apify.py:253`)
- `limit` (int) — `min(20, max_results - len(out))`; shrinks the final page when the ceiling is approached
- `cursor` (str, optional) — `next_cursor` from the previous page, omitted on page 1

**Pre-call validation:** `assert_under_length_cap(q.query_string)` (`x_monitor/queries.py:219`) raises `ValueError` if the query string exceeds **512 characters**. The cap is on character length, not on operator count. Over-cap queries silently return 0 tweets on X (and on TwitterAPI.io) — loud-fail BEFORE the call to prevent credit burn.

**Credit cost:** 15 credits per call (TwitterAPI.io charges a 15-credit floor per search call regardless of result count; 15 credits per returned tweet beyond that). Note: this pricing has not been re-verified against the live TwitterAPI.io pricing page since 2026-06-08 — confirm before relying on the number for budgeting.

**Response shape:** `{ "tweets": [ {...}, ... ], "has_next_page": bool, "next_cursor": "..."|null, "status": "success" }`. The walker falls back to `data` if `tweets` is absent.

**Call sites (2):**

1. **`x_monitor/run.py:692` — `RunPipeline.execute` v1.7 plan_calls loop**
   - Per-cycle call list is built by `plan_calls(self.data_dir, models, x_monitor_list_id=<int>)` (`x_monitor/query_plan.py:251-...`). Returns exactly **2** `PlannedCall`s:
     - **Call A** (kind=`account`): `(list:<x_monitor_list_id>) min_faves:1` — pulls any tweet authored by anyone in the curated public x.com list, which contains all official + staff handles across all enabled brands.
     - **Call B** (kind=`brand_wide`): `((BrandTok1a OR BrandTok1b) OR (BrandTok2a) OR ...) min_faves:0` — pulls any tweet whose text contains any deduped brand token from `data/queries/<m>.yaml`.
   - **Optional Call C** (`call_c_specs` in `x_monitor/config.py`): additional co-occurrence-constrained brand-wide queries, default empty (v1.7's 2-call baseline preserved when unset).
   - **Optional Call B group split** (`call_b_groups` in `x_monitor/config.py`): one Call B per group, when the union of all brand tokens exceeds the 512-char cap. Order in the file is the order emitted.
   - **Total per cycle:** **2 calls** at 15 credits floor = **30 credits/cycle minimum**, plus 15 credits per returned tweet.
   - **Schedule:** every 15 minutes via LaunchAgent `com.fuchitalee.x-monitor.scheduled` (`deploy/com.fuchitalee.x-monitor.scheduled.plist`).

2. **Tests (`tests/test_apify.py`, `tests/test_run.py`, `tests/test_query_plan_v17.py`)** — mocked; no live calls in CI.

---

### 2. `GET /twitter/article` — long-form X article body

**Method in code:** `TwitterApiClient.get_article(tweet_id) -> dict | None`
**File:** `x_monitor/apify.py:420-445`
**Path constant:** `ARTICLE_PATH = "/twitter/article"` (`x_monitor/apify.py:34`)
**Credit cost:** **100 credits per call** (flat, regardless of article length)

**Query params sent:**
- `tweet_id` (str) — the integer id of the **tweet that contains the t.co link to the article** (NOT the article path id from the URL). For `x.com/i/article/2064029478616182784`, the relevant tweet_id is on the parent post, not in the URL.

**Response shape:** `{ "article": { "title": str, "preview_text": str, "contents": [ {"type": "...", "text": "..."}, ... ], "cover_media_img_url": str, "author": {...}, "createdAt": str }, "status": "success" }`. Returns `None` if `article` is absent.

**Call sites (2):**

1. **`x_monitor/headlines.py:700` — `enrich_posts()` inner loop**
   - Called from the v1.7 pipeline at `x_monitor/run.py` after `apify.run_search` returns tweets. The pipeline passes `cache=cache, api=apify` to `filter_and_review(...)`, which routes URL-only posts to `enrich_posts` for headline enrichment.
   - Cache key: `f"x_article:{x_tid}"` (key_override)
   - Per-run cap: `per_run_cap` from `x_monitor/__main__.py` (default `200`) — counted via `run_fetches_used[0] += 1` (`x_monitor/headlines.py:706`).
   - On success: `cache.put(x_tid, title, SOURCE_FETCHED, ...)` + `item["headline"] = title` + `item["headline_source"] = "fetched"`.
   - On `None` return: `cache.put(x_tid, None, SOURCE_FETCH_FAILED, error="api_no_article", ...)` + `item["headline_source"] = "fetched_failed"`.
   - On exception: `log.info(...)` + `article = None` + treat as failure (no cache write on exceptions).

2. **`x_monitor/__main__.py:592` — `x-monitor relevance backfill --via-api` loop**
   - Operator-initiated backfill for URL-only posts that the live pipeline didn't enrich. Same cache key scheme (`f"x_article:{x_tid}"`).
   - Per-query cap: `per_query_cap * 25` (default `8 * 25 = 200` calls) — defends against an unbounded backfill exhausting the daily credit budget.

---

### 3. `GET /twitter/user/info` — public profile lookup

**Method in code:** `TwitterApiClient.user_info(handle) -> dict | None`
**File:** `x_monitor/apify.py:394-418`
**Path constant:** `USER_INFO_PATH = "/twitter/user/info"` (`x_monitor/apify.py:32`)
**Credit cost:** ~1 credit per call (low-cost endpoint; exact cost not stated in code).

**Query params sent:**
- `userName` (str) — handle WITHOUT the `@` prefix, e.g. `"MiniMaxAI"`

**Response shape:** `{ "data": { "id": "...", "userName": "...", "name": "...", "description": "...", "followers": N, "verified": bool }, "status": "success" }` or `{ "user": {...} }` on some endpoints. The client falls back to the whole response if neither `data` nor `user` is present.

**Call sites (2):**

1. **`x_monitor/__main__.py:443` — `x-monitor relevance audit-handles <brand>`**
   - For each canonical handle in `data/filters/<model>.yaml::canonical_handles`, fetch the live profile and run a heuristic (`x_monitor/relevance.py`) checking:
     - name contains any of the brand tokens
     - description contains any of the brand tokens
     - `followers_count >= 1000` (configurable)
     - `verified == True`
   - Result: a per-handle `PASS`/`WARN`/`FAIL` verdict. Used during relevance-rule tuning to catch stale canonical_handles entries.

2. **`x_monitor/apify.py:447` — `TwitterApiClient.probe_api()`**
   - Lightweight liveness check: hit `user/info` on `MiniMaxAI` (a known good handle).
   - Returns `True` iff the call succeeds with a non-empty response.
   - Used by tests and operator diagnostics.
   - Returns `True` on transient errors (429/5xx/network) — those are not liveness failures.

---

### 4. `GET /twitter/user/followers` — follower list (bulk)

**Method in code:** `TwitterApiClient.run_followers(handle, max_results, cookies)` → `_walk_followers(handle, max_results)`
**File:** `x_monitor/apify.py:382-392` (public) + `_walk_followers` at `x_monitor/apify.py:198-225`
**Path constant:** `FOLLOWERS_PATH = "/twitter/user/followers"` (`x_monitor/apify.py:28`)
**Per-page cap:** 200 followers (`FOLLOWERS_MAX_PER_PAGE = 200`)
**Pagination:** `next_cursor`; pages until `max_results` is hit
**Per-page cost (per TwitterAPI.io pricing):**
  - 20–99 returned = 3 credits each
  - 100–199 = 2 credits each
  - 200 = 1 credit each (cheapest)

**Why 200 per page:** Always ask for 200 — the price-per-item is the cheapest (`x_monitor/apify.py:36-39`).

**Query params sent:**
- `userName` (str) — handle WITHOUT the `@` prefix
- `page_size` (int) — always 200
- `cursor` (str, optional) — `next_cursor` from the previous page, omitted on page 1

**Response shape:** `{ "followers": [ {...}, ... ], "next_cursor": "..."|null, "status": "success" }`. The walker falls back to `users` if `followers` is absent.

**Call site (1):**

1. **`x_monitor/__main__.py:180` — `x-monitor accounts bootstrap-followers --model <m> --handle <h>`**
   - Operator-initiated command to bootstrap the `discovered_followers` section of `data/accounts/<model>.yaml` from a single handle's follower list. Used for the community-graph feature.
   - `max_results=200` is the default. The `_walk_followers` loop computes `max_pages = max(1, (max_results + 199) // 200)` so a 200-call returns in 1 page, a 400-call in 2 pages, etc.
   - Not part of the scheduled pipeline. Not called from `RunPipeline.execute`.

---

### 5. `GET /twitter/tweet/quotes` — quote-tweets of a given tweet (NEW 2026-06-22)

**Method in code:** `TwitterApiClient.get_quote_tweets(tweet_id, *, since_time=None, max_pages=5, include_replies=False)`
**File:** `x_monitor/apify.py:300-345`
**Path constant:** `QUOTES_PATH = "/twitter/tweet/quotes"` (`x_monitor/apify.py:44`)
**Per-page cap:** 20 quotes (`QUOTES_MAX_PER_PAGE = 20`)
**Pagination:** `has_next_page` + `next_cursor`; stops on empty page OR `has_next_page=false`. Per TwitterAPI.io docs, `has_next_page` can return true even when no more data exists, so the empty-page guard is load-bearing (`x_monitor/apify.py:334-337`).
**Defensive cap:** `max_pages=5` by default, configurable per call (the `quote_tweets.max_pages` setting in `x_monitor/config.py:QuoteTweetConfig`).

**Query params sent:**
- `tweetId` (str) — the tweet whose quote-tweets to fetch
- `includeReplies` (str) — `"true"` or `"false"` (default `"false"`)
- `sinceTime` (int, optional) — unix-second timestamp; only QTs created on/after it are returned (seeds the incremental `sinceTime` resume between captures)
- `cursor` (str, optional) — `next_cursor` from the previous page, omitted on page 1

**Response shape:** `{ "tweets": [ {...}, ... ], "has_next_page": bool, "next_cursor": "..."|null, "status": "success" }`. Same tweet-shape as `/twitter/tweet/advanced_search`.

**Call sites (2):**

1. **`x_monitor/run.py:979` (inside `_capture_official_quote_tweets` defined at `x_monitor/run.py:917`) — adaptive, every cycle**
   - Tracks recent official/staff posts (created within `quote_tweets.track_recency_days`, default 14).
   - Refreshes their current `quote_count` via `get_tweets_by_ids` (endpoint #6 below).
   - For any whose `quote_count` grew by >= `quote_tweets.official_delta` (default 5) since the last fetch, pulls the new QTs and ingests them.
   - Per-cycle call budget: `quote_tweets.official_call_budget` (default 20). After a successful fetch, `store.update_quote_tracking(...)` advances `last_quote_count_seen` and `last_quote_fetched_at`.
   - Triggered as part of the same 15-minute scheduled cycle as endpoint #1.

2. **`x_monitor/run.py:1089` (inside `_capture_nonofficial_quote_tweets_daily` defined at `x_monitor/run.py:1012`) — daily pass**
   - Date-gated via `data/_qt_daily_marker` (runs at most once per UTC day).
   - Selects recent non-official posts (created within `quote_tweets.daily_recency_days`, default 7; author NOT a staff/official handle).
   - Refreshes their `quote_count` via `get_tweets_by_ids`. For any with `delta >= 1` since last fetch, pulls the new QTs.
   - Per-cycle call budget: `quote_tweets.daily_call_budget` (default 50).
   - Toggled by `quote_tweets.daily_enabled` (default `True`).

---

### 6. `GET /twitter/tweets` — batched tweet lookup by ID (NEW 2026-06-22)

**Method in code:** `TwitterApiClient.get_tweets_by_ids(tweet_ids: list[str]) -> dict[str, dict[str, Any]]`
**File:** `x_monitor/apify.py:347-380`
**Path constant:** `TWEETS_BY_IDS_PATH = "/twitter/tweets"` (`x_monitor/apify.py:49`)
**Chunk size:** `TWEETS_BY_IDS_CHUNK = 50` (`x_monitor/apify.py:51`) — lists longer than 50 are split across calls.

**Query params sent:**
- `tweet_ids` (str) — comma-separated list of tweet IDs (no spaces). E.g. `123,456,789`.

**Response shape:** `{ "tweets": [ {"id": "...", "quoteCount": N, "retweetCount": N, "replyCount": N, "likeCount": N, ...}, ... ], "status": "success" }`. Missing/invalid IDs are simply absent from the response.

**Return value shape (normalized):** `{ tweet_id: {"quote_count": N, "retweet_count": N, "reply_count": N, "like_count": N} }`. Keys are the stringified tweet IDs from the request; absent IDs are absent from the result.

**Why this exists:** the cheap quote_count refresh — one call returns current `quoteCount`/`retweetCount` for many tweet IDs, so the QT regimes can observe growth without the search re-surfacing each post (which ages out of "Latest" after ~1-2 days and whose stored `quote_count` is frozen by `INSERT OR IGNORE`).

**Call sites (2):**

1. **`x_monitor/run.py:960` (inside `_capture_official_quote_tweets` defined at `x_monitor/run.py:917`) refresh step**
   - Called BEFORE the per-tweet `get_quote_tweets` fan-out in the official regime. One chunked call covers every tracked official/staff post's `quote_count`.

2. **`x_monitor/run.py:1071` (inside `_capture_nonofficial_quote_tweets_daily` defined at `x_monitor/run.py:1012`) refresh step**
   - Same role in the daily non-official regime. `LIMIT 500` caps the refresh candidate set so a huge recent-post volume can't drain the budget on count-lookups alone.

---

## Call-site × endpoint matrix

| Endpoint | Method | File:line | Trigger | Credits/call | Frequency |
|---|---|---|---|---|---|
| `GET /twitter/tweet/advanced_search` | `run_search` → `_walk_search` | `run.py:692` | Scheduled 15-min | 15 floor + 15/tweet | 2 calls/cycle (plus optional Call C and Call B group split) |
| `GET /twitter/article` | `get_article` | `headlines.py:700` | Live pipeline (URL-only posts) | 100 | Per URL-only post (capped at 200/run) |
| `GET /twitter/article` | `get_article` | `__main__.py:592` (backfill) | `relevance backfill --via-api` | 100 | Per backfill row (capped at 200) |
| `GET /twitter/user/info` | `user_info` | `__main__.py:443` | `relevance audit-handles <brand>` | ~1 | Per canonical handle (manual) |
| `GET /twitter/user/info` | `probe_api` | `apify.py:447` | Diagnostic / tests | ~1 | On-demand |
| `GET /twitter/user/followers` | `run_followers` → `_walk_followers` | `__main__.py:180` | `accounts bootstrap-followers` | 1–3 per follower | On-demand (manual) |
| `GET /twitter/tweet/quotes` | `get_quote_tweets` | `run.py:979` | Scheduled 15-min (official regime) | (per tweet, see plan) | Bounded by `official_call_budget` (20) |
| `GET /twitter/tweet/quotes` | `get_quote_tweets` | `run.py:1089` | Daily pass (non-official regime) | (per tweet) | Bounded by `daily_call_budget` (50), once/UTC day |
| `GET /twitter/tweets` | `get_tweets_by_ids` | `run.py:960` | Scheduled 15-min (official regime refresh) | 1 per 50 IDs | 1 chunked call/cycle (≤ N/50 chunks) |
| `GET /twitter/tweets` | `get_tweets_by_ids` | `run.py:1071` | Daily pass (non-official regime refresh) | 1 per 50 IDs | 1 chunked call/day (≤ 10 chunks over 500 candidates) |
| **Anthropic Messages API** | `translate_batch` | `translator.py:203` | End of each 15-min cycle | ~$0.005 / 1000 tweets | 1 call / 20 kept posts |
| **Anthropic Messages API** | `classify_signal` per brand | `attribution.py` | Post-attribution per kept post | ~$0.0001 / brand-row | 1 call / brand-row (opt-in via `--with-llm`); writes new `post_type` + `sentiment` columns on `posts_brands_signals` (U9), legacy `signal_id` retained alongside |

**The last two rows are a separate endpoint class (Anthropic, not TwitterAPI.io)** — included for completeness. Claude Haiku 4.5 pricing is ~$1/MTok input, $5/MTok output. Typical 200-char tweet ≈ 200 tokens; 1,000 kept posts/cycle ≈ $0.005 per locale. Batched at 20 tweets per request.

---

## Error handling (shared across all endpoints)

`TwitterApiClient._get()` (`x_monitor/apify.py:100-148`) handles errors uniformly:

| HTTP code | Behavior |
|---|---|
| 200 | Return `r.json()` |
| 401 | Raise `TwitterApiAuthError` (fatal; aborts the run via `summary["status"] = "aborted"` in `run.py:698`) |
| 429 | Retry with backoff (4s, 8s, 16s); raise `TwitterApiRateLimitError` after exhaustion |
| 5xx | Retry with backoff (1s, 2s, 4s); raise `TwitterApiServerError` after exhaustion |
| Other 4xx | Raise `RuntimeError` with the response text (first 200 chars) |
| `requests.RequestException` (network) | Retry with backoff (1s, 2s, 4s); re-raise after exhaustion |

`max_retries=2` means up to 3 total attempts per call. Note: the 429 backoff is `2 ** (attempt + 2)` — 4s on the first retry, 8s on the second, 16s on the third — which is longer than the 1s/4s/1s wording from the prior revision. Use the per-status table above as the authoritative policy.

---

## Cost summary

**Live pipeline (15-min cycle, 11 brands baseline):**

| Component | Cost |
|---|---|
| Advanced search floor | 2 × 15 = 30 credits/cycle |
| Returned tweet cost | N × 15 credits |
| QT refresh (`/twitter/tweets`) | 1 chunked call/cycle per regime (official always; daily once/day) |
| QT capture (`/twitter/tweet/quotes`) | bounded by `official_call_budget=20` per cycle + `daily_call_budget=50` once/day |
| URL-only X-article enrichment | 0–200 × 100 credits |
| Translation pass (Anthropic, NEW v1.7) | ~$0.005 / 1000 kept posts |
| Per-brand signal classification (NEW v1.8; U9: now also writes `post_type` + `sentiment`) | ~$0.0001 / brand-row (Haiku direct; 25× slower via proxy) |

**v1.7+ idle (no new tweets, no translations):** ~30 credits/cycle × 4 cycles/hour × 24 hours = **2,880 credits/day** at $0.15/1k ≈ **$0.43/day ≈ $13/month**.

**v1.7+ busy:** 30 credits/cycle + return surcharge + QT regimes + LLM translation ≈ $1-2/day ≈ $30-60/month.

---

## Caching and dedup

- **Search results:** NOT cached at the API layer — TwitterAPI.io's own dedup handles repeat queries on their side. The pipeline relies on `posts.tweet_id` UNIQUE constraint in the SQLite store (`x_monitor/store.py`) to dedup.
- **X-article headlines:** Cached in `data/headlines_cache.json` (`x_monitor/headlines.py` cache module) with key `f"x_article:{tweet_id}"`. Versioned entries; `title=None` + `source="fetched_failed"` entries are kept (not retried by default — the `error="api_no_article"` field distinguishes "no article exists" from "transient failure").
- **Quote-tweet tracking:** `posts.last_quote_count_seen` and `posts.last_quote_fetched_at` columns (v1.x migration). The QT regimes advance these per captured post to seed `sinceTime` resume and avoid re-polling stable posts.
- **Translations (v1.7 NEW):** Stored directly in `posts.text_en` and `posts.text_zh_cn` columns. Idempotent: `bulk_update_translations` re-running with the same data is a no-op. The `x-monitor translate [--locale en|zh-CN|both] [--limit N]` subcommand is the recovery/backfill path for posts where translation failed (NULL columns). Note: the `--locale` CLI flag is the user-facing display-locale concept (cookie/query value on `/grid`) and was intentionally NOT renamed by migration 011 — the schema rename only touched the `*_labels` table columns (`locale` → `lang`).
- **Post-type + sentiment tagging (schema modernization, 2026-06-24):** `posts_brands_signals` now carries two ADDITIVE nullable TEXT columns — `post_type` (FK → `post_type_keys.key`, one of `buzz_releases` / `hands_on_usage` / `performance_comparisons` / `feedback_questions`) and `sentiment` (FK → `sentiment_keys.key`, one of `positive` / `negative` / `neutral` / `mixed`). The legacy `signal_id` column is retained alongside; the `classify_signal` attribution path (see row 225 / 260 / 291) writes the new columns without rewriting the legacy one. Pre-migration-019 rows are backfilled via a static `signal_id` → (`post_type`, `sentiment`) CASE mapping; a future LLM reclassify pass is out of scope.

---

## Why no POST/PUT/DELETE

x-monitor is a **read-only** monitor. It never writes to Twitter, never posts, never modifies user data. All 6 TwitterAPI.io endpoints are pure `GET` reads. The `cookies` parameter that the old ApifyClient required is accepted for backward compatibility but is ignored (`x_monitor/apify.py:276` in `run_search`, `:386` in `run_followers`).

---

## Source files for this inventory

- `x_monitor/apify.py` — the `TwitterApiClient` wrapper (618 lines; this doc references line numbers). Per-request `_request_log` lives here (`x_monitor/apify.py:83, 150-196`).
- `x_monitor/headlines.py` — the `enrich_posts` X-article branch (`x_monitor/headlines.py:695-720`)
- `x_monitor/__main__.py` — the backfill loop (`x_monitor/__main__.py:580-610`), CLI subcommands, and the `accounts bootstrap-followers` command
- `x_monitor/run.py` — the v1.7+ pipeline inner loop at `x_monitor/run.py:525-915` (advanced search + summary write, including `http_log`/`phase_timings_sec` capture at `:910, :551`) and quote-tweet capture at `x_monitor/run.py:917-1100`
- `x_monitor/query_plan.py` — the `plan_calls()` function (`x_monitor/query_plan.py:251-...`; v1.7 emits 2 calls: `list:`-based Call A + paren-grouped Call B)
- `x_monitor/queries.py` — the character-length pre-check (`assert_under_length_cap` at `x_monitor/queries.py:219`)
- `x_monitor/attribution.py` — v1.8 per-brand signal decomposition: `attribute_to_brands()`, `classify_signal(text, brand_ids, brand_registry, anthropic_client)` with optional LLM via `AnthropicClaudeClient` (routes through minimax proxy when `ANTHROPIC_BASE_URL` is set)
- `x_monitor/translator.py` (v1.7 NEW) — Claude Haiku translation pass (`translate_batch` at `x_monitor/translator.py:203`)
- `x-monitoring/config.yaml` — the v1.7-required `x_monitor_list_id` field, plus the `quote_tweets:` block for QT regime budgets
- `data/headlines_cache.json` — the X-article headline cache
- `deploy/com.fuchitalee.x-monitor.scheduled.plist` — the 15-minute LaunchAgent
- `scripts/dump_http_log.py` — post-run inspector for `summary["http_log"]` (flat list + grouped view + optional JSON report)