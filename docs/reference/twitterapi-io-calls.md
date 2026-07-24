# TwitterAPI.io call inventory (v2 Django architecture)

Last updated: 2026-07-24-11:36:23

Last reviewed: 2026-07-24

**Stack:** Django + gunicorn + WhiteNoise on Render (v2). The legacy v1
Flask + macOS launchd system is retired.

**API provider:** TwitterAPI.io — cookie-free X/Twitter data API.
Replaced the Apify-based scraper in 2026-06-08. ~95% cheaper ($0.15/1k
tweets vs $3/1k on Apify).

**API key env var:** `TWITTERAPI_IO_API_KEY`
**Base URL:** `https://api.twitterapi.io`
**HTTP method:** All calls are `GET` with `params=...` query string.
**Auth header:** `X-API-Key: <key>`
**Timeout:** 60 s per request; up to 3 attempts (1 initial + 2 retries)
on 429/5xx/network errors.

---

## Architecture: how the harvest cycle runs

The harvest pipeline is orchestrated by `CycleRunner` in
`monitor/cycle.py` and invoked by the Django management command
`python manage.py run_cycle` (`monitor/management/commands/run_cycle.py`).

The Render cron job (`render.yaml`) fires the cycle every 15 minutes:

```yaml
schedule: "*/15 * * * *"
startCommand: python manage.py run_cycle --limit-per-call 50
```

Each cycle:

1. **Plan calls** via `x_monitor/query_plan.py::plan_calls()` — returns a
   list of `PlannedCall` objects (typically 6: A + B1/B2/B3 + C1/C2).
2. **Fetch tweets** via `TwitterApiClient.run_search()` — shared library
   code that wraps the TwitterAPI.io REST API.
3. **Attribute to brands** via `x_monitor/attribution.py::attribute_to_brands()`
   — stamps `brand_id`, `brand_ids`, and `mentions` on each tweet.
4. **Persist** via Django ORM — `Post`, `Account`, `PostBrand`,
   `PostBrandMention`, `PostBrandSignal` models in `core/models.py`.
5. **Post-fetch** (translate + classify) — stubbed; LLM-backed steps are
   deferred to a follow-up unit.

The CycleRunner is stateless per invocation — each Render cron execution
spawns a fresh process.

---

## The 6-call cycle

Each cycle fires up to 6 `advanced_search` calls. The calls are planned by
`plan_calls()` in `x_monitor/query_plan.py` and rendered by the uniform
`_build_query()` function. Every call produces the same shape:

```
<tokens> <co_occurrence> min_faves:N
```

### Call A — list-based fan-in (kind: `account`)

**Source:** `x_monitor_list_id` in `config.yaml` (or `X_MONITOR_LIST_ID`
env var on Render). Current value: `2067062923525275922`.

**Query:** `(list:<x_monitor_list_id>) min_faves:0`

Pulls every tweet authored by anyone in the curated public X.com list.
This is the highest-signal call — it surfaces posts from official/staff
handles of all tracked brands in a single API call. `min_faves:0` means
no engagement floor; every list-authored tweet is captured.

**brand_id:** `"*"` (the list spans all brands; post-fetch attribution
resolves each tweet to its actual brand).

### Calls B1/B2/B3 — wide-net keyword (kind: `brand_wide`, `is_wide_net: true`)

**Source:** `x_query_specs` entries in `config.yaml` with
`is_wide_net: true`. Each B-spec defines a `wide_net_brands` list and a
`co_occurrence` list. Per-brand tokens are read at cycle time from the
`brand_keywords` DB table (`is_primary=1` rows), not from the config file.

**Query:** `((BrandTok1a OR BrandTok1b) OR (BrandTok2a) OR ...) (co_occurrence1 OR co_occurrence2 OR ...) min_faves:0`

**Group split** (from `config.yaml`):

| Spec | Brands | Character length |
|------|--------|-----------------|
| B1 | minimax, qwen, deepseek, mistral, stepfun, hunyuan | ~473 chars |
| B2 | doubao, glm, sensechat, inclusionai | ~470 chars |
| B3 | nemo_megatron, exaone, sakana_ai, kuaishou | ~375 chars |

6 brands (llama, mimo, moonshot_kimi, yi, ernie, upstage) are intentionally
absent from the B-specs — they are covered exclusively by C1/C2 via
co-occurrence AND-filter to avoid duplicate credit spend.

### Calls C1/C2 — co-occurrence-constrained (kind: `brand_wide`, `is_wide_net: false`)

**Source:** `x_query_specs` entries in `config.yaml` with explicit
`brands:` maps. These are the precision-oriented calls — each brand's
tokens are AND-filtered against a co-occurrence list to suppress
false-positives from polysemous brand names (e.g., "mimo" matches a kids'
video app, "kimi" matches an F1 driver and a Turkish interrogative).

**Query:** `((MiMo OR "Xiaomi MiMo") OR (Kimi OR "Moonshot AI") OR ...) (api OR llm OR model OR ...) min_faves:0`

| Spec | Brands covered | Character length |
|------|---------------|-----------------|
| C1 | mimo, moonshot_kimi, yi, llama | ~461 chars |
| C2 | ernie, upstage | ~282 chars |

---

## Endpoints used

### 1. `GET /twitter/tweet/advanced_search` — the workhorse

**Used by:** every cycle call (A + B1/B2/B3 + C1/C2).

**Method:** `TwitterApiClient.run_search(query, max_results, since, ...)`
→ `_walk_search(query, max_results, max_pages=5, max_per_page=20)`.

**Per-page cap:** 20 tweets (the TwitterAPI.io platform cap).
**Pagination:** `has_next_page` + `next_cursor`; up to 5 pages (100 tweets
max) per call. The `max_pages=5` defensive cap guards against a runaway
cursor draining the credit budget.

**Query params sent:**
- `query` (str) — X advanced-search string.
- `queryType` (str) — always `"Latest"`.
- `limit` (int) — `min(20, remaining_to_reach_max_results)`.
- `cursor` (str, optional) — `next_cursor` from previous page.

**Time-cursor operators** (injected into the query string, NOT as URL params
— TwitterAPI.io silently drops unknown URL params on this endpoint):
- `since:<YYYY-MM-DD>` — date-only floor, injected only when `since_time` is
  not set (the two operators conflict).
- `since_time:<epoch>` + `until_time:<now>` — sub-day-precision window,
  injected together when a prior cycle cursor exists. `until_time` is
  exclusive (everything up to the moment of the cycle).

**Credit cost:** **300 credits per page** (flat rate regardless of
`n_results`). This is the figure used by the pre-flight budget guard
(defined in `x_monitor/run.py`, evaluated before any API calls).

**Pre-call validation:** `assert_under_length_cap()` in
`x_monitor/queries.py` raises `ValueError` if the query string exceeds
**512 characters**. Over-cap queries silently return 0 tweets on X — the
loud-fail prevents credit burn.

**Response shape:** `{ "tweets": [...], "has_next_page": bool, "next_cursor": "..."|null, "status": "success" }`.

**Per-cycle credit cost (1 page each, 6 calls):** 6 x 300 = **1,800
credits/cycle minimum**. At 4 cycles/hour x 24 hours = **172,800
credits/day** (~$25.92/day at $0.15/1k). Actual costs are lower — many
cycles return 0 new tweets, and the wide-net B/C calls may produce empty
results for low-volume brands.

### 2. `GET /twitter/article` — long-form X article body

**Used by:** NOT currently wired in the v2 cycle. Available in the shared
client for future headline enrichment of URL-only posts.

**Method:** `TwitterApiClient.get_article(tweet_id)`.

**Credit cost:** 100 credits per call.

**Query params:** `tweet_id` (str) — the tweet that links to the article.

**Response shape:** `{ "article": { "title": str, "preview_text": str, "contents": [...], ... }, "status": "success" }`.

### 3. `GET /twitter/user/info` — public profile lookup

**Used by:** NOT currently wired in the v2 cycle. Available in the shared
client for operator diagnostics (e.g., verifying canonical handles).

**Method:** `TwitterApiClient.user_info(handle)`.

**Credit cost:** ~1 credit per call (low-cost endpoint).

**Query params:** `userName` (str) — handle WITHOUT the `@` prefix.

**Response shape:** `{ "data": { "id": "...", "userName": "...", ... }, "status": "success" }`.

### 4. `GET /twitter/user/followers` — follower list

**Used by:** NOT currently wired in the v2 cycle. Available in the shared
client for operator-initiated account bootstrapping.

**Method:** `TwitterApiClient.run_followers(handle, max_results)`.

**Per-page cap:** 200 followers (always request 200 — cheapest per-item
price at 1 credit each).

**Credit cost:** 1-3 credits per follower depending on page size.

### 5. `GET /twitter/tweet/quotes` — quote-tweets of a given tweet

**Used by:** NOT currently wired in the v2 cycle. Available in the shared
client for future QT-capture regimes.

**Method:** `TwitterApiClient.get_quote_tweets(tweet_id, since_time=..., max_pages=5)`.

**Per-page cap:** 20 quotes. Pagination stops on empty page OR `has_next_page=false`.

**Query params:** `tweetId` (str), `includeReplies` ("true"/"false"), `sinceTime` (int, optional), `cursor` (str, optional).

### 6. `GET /twitter/tweets` — batched tweet lookup by ID

**Used by:** NOT currently wired in the v2 cycle. Available in the shared
client for cheap `quote_count` refreshes (one call returns metrics for up
to 50 tweet IDs).

**Method:** `TwitterApiClient.get_tweets_by_ids(tweet_ids)`.

**Chunk size:** 50 IDs per call (auto-split for longer lists).

**Query params:** `tweet_ids` (str) — comma-separated, no spaces.

**Response shape:** `{ "tweets": [{ "id": "...", "quoteCount": N, ...}, ...] }`.

---

## Credit tracking and budget guard

**Pre-flight guard** (in `x_monitor/run.py`):

```python
_BUDGET_HARD_CAP_CREDITS = 2_000_000  # $20 at TwitterAPI.io pricing
_CREDITS_PER_ADVANCED_SEARCH_PAGE = 300
_N_CALLS = 6  # A, B1, B2, B3, C1, C2
_would_spend = _N_CALLS * _effective_max_pages * _CREDITS_PER_ADVANCED_SEARCH_PAGE
```

If `would_spend > 2,000,000` credits, the pipeline raises `RuntimeError`
and refuses to start. This guards against an accidental `--max-pages-per-call 99999`
silently draining the budget.

**At default settings** (`max_pages=5`, `limit_per_call=50`):
- Would-spend: 6 calls x 5 pages x 300 = **9,000 credits ($0.09)** — well
  under the $20 cap.
- The Render cron passes `--limit-per-call 50` explicitly.

**Operator overrides** via management command flags:
- `--limit-per-call N` — cap tweets per call (default 50).
- `--max-pages-per-call N` — cap pagination depth (default 5).
- `--skip-fetch` — plan only, no API calls (for dry-run inspection).

---

## Fetch / attribute / persist pipeline

The v2 `CycleRunner.run()` method walks through these phases per cycle:

### Phase 1: Plan calls

`_plan_calls()` loads `x_monitor_list_id` and `x_query_specs` from Django
settings (sourced from `config.yaml` or env vars), loads primary keywords
from `BrandKeyword.objects.filter(is_primary=True)`, and calls
`plan_calls()` from `x_monitor/query_plan.py`. Returns 0-6 `PlannedCall`
objects.

### Phase 2: Fetch

For each `PlannedCall`, `_fetch_tweets()` calls
`TwitterApiClient.run_search(call.query_string, max_results=50,
max_pages=5, max_per_page=20)`. Returns normalized tweet dicts.

Per-call errors (rate limit, server error) are caught — one bad query does
not kill the cycle. Auth errors (HTTP 401) are fatal.

### Phase 3: Attribute

`_attribute_items()` runs `attribute_to_brands()` from
`x_monitor/attribution.py` on each tweet. The keyword index is built from
enabled model names (self-brand matching). The `brand_search_terms` map is
loaded from the `brand_search_terms` DB table and augmented with brand
aliases (e.g., "kimi" -> "moonshot_kimi", "chatglm" -> "glm").

Tweets matching no brand are marked `_unattributed` and dropped from the
kept set.

### Phase 4: Persist

`_persist_items()` writes to Django ORM models with `transaction.atomic()`
per tweet:

1. **Account** — `update_or_create` on `author_id`, upserting handle,
   display_name, verified, followers_count, following_count.
2. **Post** — `update_or_create` on `tweet_id`, storing the full raw
   response in a JSONField, plus scalar fields (text, lang, created_at,
   engagement counts, etc.).
3. **PostBrand** — `get_or_create` junction row per (post, brand).
4. **PostBrandMention** — `get_or_create` per (post, brand, source),
   deduplicated by source.
5. **PostBrandSignal** — `update_or_create` per (post, brand, post_type);
   writes `post_type` and `sentiment` enum keys.

All persistence is idempotent — re-running the same cycle with the same
tweets produces no duplicate rows.

### Phase 5: Post-fetch (stubbed)

Translation (`text_en`, `text_zh_cn`) and classification (`post_type`,
`sentiment`) via Claude Haiku are deferred to a follow-up unit. The
current v2 cycle skips LLM calls entirely.

---

## Rate limiting and backoff

`TwitterApiClient._get()` handles errors uniformly across all endpoints:

| HTTP code | Behavior |
|-----------|----------|
| 200 | Return `r.json()`. |
| 401 | Raise `TwitterApiAuthError` (fatal — aborts the cycle). |
| 429 | Retry with backoff (4s, 8s); raise `TwitterApiRateLimitError` after exhaustion. |
| 5xx | Retry with backoff (1s, 2s); raise `TwitterApiServerError` after exhaustion. |
| Other 4xx | Raise `RuntimeError` with response text (first 200 chars). |
| Network error | Retry with backoff (1s, 2s); re-raise after exhaustion. |

`max_retries=2` means up to 3 total attempts per call (1 initial + 2
retries). The sleep formula:
- 429: `2 ** (attempt + 2)` — 4s on attempt 0, 8s on attempt 1.
- 5xx/network: `2 ** attempt` — 1s on attempt 0, 2s on attempt 1.
- On attempt 2, no retry is possible (`2 < 2` = False); the exception
  propagates immediately.

In the v2 `CycleRunner`, per-call rate-limit and server errors are caught
in `_fetch_tweets()` — the call is logged as an error and the cycle
continues to the next call. Auth errors are fatal (the cycle aborts).

---

## Why no POST/PUT/DELETE

The monitor is **read-only**. It never writes to Twitter, never posts,
never modifies user data. All 6 TwitterAPI.io endpoints are pure `GET`
reads. There is no cookie-based auth — the old Apify cookie probe and
cookie-rot failure mode are gone.

---

## Caching and dedup

- **Search results:** NOT cached at the API layer. The pipeline relies on
  `Post.tweet_id` UNIQUE constraint in the Django ORM to dedup
  re-ingested tweets.
- **Per-cycle dedup:** The accumulator in `CycleRunner.run()` tracks seen
  tweet IDs across calls so the same tweet appearing in multiple calls is
  only processed once.

---

## Source files

- `monitor/cycle.py` — CycleRunner: plan, fetch, attribute, persist (v2
  entrypoint).
- `monitor/management/commands/run_cycle.py` — Django management command
  invoked by Render cron.
- `x_monitor/query_plan.py` — `plan_calls()`, `XQuerySpec`, `_build_query()`
  (shared call-planning library).
- `x_monitor/attribution.py` — `attribute_to_brands()`, `compile_keyword_index()`
  (shared attribution library).
- `x_monitor/queries.py` — `assert_under_length_cap()` (512-char query
  length guard).
- `config.yaml` — `x_monitor_list_id`, `x_query_specs` (B1/B2/B3/C1/C2
  definitions), `enabled_models`.
- `render.yaml` — Render cron job schedule and `startCommand`.
- `core/models.py` — Django ORM models: Post, Account, Brand, BrandKeyword,
  BrandSearchTerm, PostBrand, PostBrandMention, PostBrandSignal,
  PostTypeKey, SentimentKey.

---

Last reviewed: 2026-07-24
