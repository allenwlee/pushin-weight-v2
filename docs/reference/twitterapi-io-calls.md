# TwitterAPI.io call inventory (v2 Django architecture)

Last updated: 2026-08-05-20:38:42


Last reviewed: 2026-08-05

**Stack:** Django + gunicorn + WhiteNoise on Render (v2). The legacy v1
Flask + macOS launchd system is retired.

**API provider:** TwitterAPI.io — cookie-free X/Twitter data API.
Replaced the Apify-based scraper in 2026-06-08. ~95% cheaper ($0.15/1k
tweets vs $3/1k on Apify).

**API key env vars:** `TWITTERAPI_IO_SCHEDULED_API_KEY` for recurring
`run_cycle` collection; `TWITTERAPI_IO_ON_DEMAND_API_KEY` for explicitly
launched batches, backfills, reconciliation, probes, and API-backed smoke
tests. Callers declare one purpose and never fall back to the other key or the
retired unsuffixed name.
**Base URL:** `https://api.twitterapi.io`
**HTTP method:** All calls are `GET` with `params=...` query string.
**Auth header:** `X-API-Key: <key>`

The one-time `/twitter/user_about` Account population uses the on-demand key,
5-QPS operator pacing, bounded concurrency, missing-only checkpoints, and the
production recovery gate documented in
`docs/operations/2026-08-29-223000-account-user-about-backfill.md`. It is not a
scheduled harvester endpoint.
**Timeout:** 60 s per request; up to 3 attempts (1 initial + 2 retries,
`max_retries=2`) on 429/5xx/network errors.

---

## Architecture: how the harvest cycle runs

The harvest pipeline is orchestrated by `CycleRunner` in
`monitor/cycle.py` and invoked by the Django management command
`python manage.py run_cycle` (`monitor/management/commands/run_cycle.py`).

The Render cron job (`render.yaml`) fires the cycle every 15 minutes:

```yaml
schedule: "*/15 * * * *"
startCommand: python manage.py run_cycle --scheduled
```

Each cycle:

1. **Plan calls** via `x_monitor/query_plan.py::plan_calls()` — returns a
   list of `PlannedCall` objects (7: A + B1/B2/B3 + C1/C2/C3).
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

## The 7-call cycle

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

### Calls C1/C2/C3 — co-occurrence-constrained (kind: `brand_wide`, `is_wide_net: false`)

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

**Used by:** every cycle call (A + B1/B2/B3 + C1/C2/C3).

**Method:** `TwitterApiClient.run_search(query, max_results, since, ...)`
→ `_walk_search(query, max_results, max_pages=5, max_per_page=20)`.

**Per-page cap:** 20 tweets (the TwitterAPI.io platform cap; the live
`config.yaml` `search.max_per_page` overrides to 20 — same value, no
drift).
**Pagination:** `has_next_page` + `next_cursor`. The apify default is
`max_pages=5`, but the live `config.yaml` sets `search.max_pages: 100`
(operator-tunable via the config block). The `_effective_max_pages` that
drives the budget guard reads this config value unless
`--max-pages-per-call` is passed on the CLI. The `max_pages=5` default
in `apify._walk_search` is the defensive ceiling used when
`config.search.max_pages` is unset.

**Query params sent:**
- `query` (str) — X advanced-search string.
- `queryType` (str) — always `"Latest"`.
- `limit` (int) — `min(20, remaining_to_reach_max_results)`.
- `cursor` (str, optional) — `next_cursor` from previous page.

**Time-cursor operators** (injected into the query string, NOT as URL params
— TwitterAPI.io silently drops unknown URL params on this endpoint;
verified by direct API test 2026-07-14 — see commits `a46020f` and
`dcf0a8c`, and `docs/debug/2026-07-14-160222-call-state-not-persisting.md`):
- `since:<YYYY-MM-DD>` — date-only floor, injected only when `since_time`
  is not set AND `since:` is absent from the query. The two operators
  conflict — when both are present, TwitterAPI.io's parser silently
  drops results, so `run_search` suppresses the `since:` injection when
  `since_time` is active.
- `since_time:<epoch>` + `until_time:<now>` — sub-day-precision window,
  injected together when a prior cycle cursor exists.
  `until_time` is exclusive (everything up to the moment of the cycle);
  TwitterAPI.io's verified-working pattern is `since_time:<floor>
  until_time:<now>`.

**Credit cost:** **300 credits per page** (flat rate regardless of
`n_results`). This is the figure used by the pre-flight budget guard
(defined in `x_monitor/run.py`, evaluated before any API calls).

**Pre-call validation:** `assert_under_length_cap()` in
`x_monitor/queries.py` raises `ValueError` if the query string exceeds
**512 characters**. Over-cap queries silently return 0 tweets on X — the
loud-fail prevents credit burn.

**Response shape:** `{ "tweets": [...], "has_next_page": bool, "next_cursor": "..."|null, "status": "success" }`.

**Per-cycle credit cost (1 page each, 6 calls at `max_pages=1`):** 6 x 300 =
**1,800 credits/cycle minimum**. At the live config defaults
(`search.max_pages=100`, `search.max_results=2000`), worst-case per-call
ceiling is **100 pages × 300 credits = 30,000 credits/call**; worst-case
per-cycle is **6 × 30,000 = 180,000 credits/cycle** — but the pre-flight
budget guard caps a single run at **2,000,000 credits** regardless of
`max_pages` (see "Credit tracking and budget guard" below). At 4
cycles/hour × 24 hours = 96 cycles/day nominal; actual daily spend is
gated by the budget guard, and many cycles return 0 new tweets because
wide-net B/C calls may produce empty results for low-volume brands.

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

### 7. `GET /twitter/list/members` — Call A roster reconciliation

**Used by:** scheduled cycles when the configured six-hour reconciliation is due.

**Method:** `TwitterApiClient.run_list_members(list_id, ...)`.

**Vendor contract:** page size is fixed at 20. Send only required `list_id` and
the optional `cursor`; `page_size` is not a supported query parameter. See the
vendored contract at
`docs/external_vendors/twitterapi_docs/endpoint/get_list_members.md`.

**Safety:** provider error status, malformed/partial pagination, missing or
duplicate stable ids, and an empty first page produce an incomplete snapshot.
An incomplete snapshot cannot deactivate known members or advance the
last-complete sync state.

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

At the live config defaults (`config.yaml::search.max_pages=100`,
`config.yaml::search.max_results=2000`):
- Would-spend: 6 × 100 × 300 = **180,000 credits/run** (~$27/run) — still
  under the 2,000,000 hard cap, so the guard does NOT trip on a fresh
  run. The guard only fires when the operator passes a
  `--max-pages-per-call` value that, combined with `_N_CALLS × 300`,
  would exceed 2,000,000 — i.e., `--max-pages-per-call >= 1112` would
  trip it.

**Operator overrides** via management command flags:
- `--limit-per-call N` — cap tweets per call (default 50; falls back to
  `config.search.max_results` when unset — currently 2000 on Render).
- `--max-pages-per-call N` — cap pagination depth (default 5; falls back
  to `config.search.max_pages` when unset — currently 100 on Render).
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
`TwitterApiClient.run_search(call.query_string, max_results=<config>,
max_pages=<config>, max_per_page=20)`. The `max_results` and `max_pages`
values come from `config.search.{max_results, max_pages}` (2000 and 100
on Render); the CLI flags `--limit-per-call` and `--max-pages-per-call`
override these when set. The `max_per_page=20` value is the
TwitterAPI.io platform cap and is hardcoded into `apify._walk_search`'s
default. Returns normalized tweet dicts.

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

Last reviewed: 2026-07-31

**Substantive corrections in this review (2026-07-31):**

- Verified against `x_monitor/run.py`:
  - `_CREDITS_PER_ADVANCED_SEARCH_PAGE = 300` (line 959) — doc claim of 300
    credits/page matches. The earlier 2026-07-16 review had caught a
    15→300 drift; the live value remains 300 as of this review.
  - `_BUDGET_HARD_CAP_CREDITS = 2_000_000` (line 958) — matches the $20
    cap referenced in the doc.
  - `_N_CALLS = 6` — matches the A+B1+B2+B3+C1+C2 smoketest shape
    referenced in the doc and pinned by `tests/test_budget_guard.py`.
  - The would-spend formula `_N_CALLS * _effective_max_pages *
    _CREDITS_PER_ADVANCED_SEARCH_PAGE` matches the formula pinned by
    `tests/test_budget_guard.py::test_budget_guard_math_formula`.
  - The `>` (strict greater-than) threshold matches the boundary-case
    pin in `tests/test_budget_guard.py::test_budget_guard_threshold`.
- Verified against `x_monitor/apify.py`:
  - `TWITTERAPI_BASE = "https://api.twitterapi.io"` (line 28) — matches.
  - `timeout_s: int = 60` and `max_retries: int = 2` (lines 74-75) —
    match the "60 s, up to 3 attempts" claim in the doc.
  - `_headers()` returns `{"X-API-Key": self.api_key, "Accept":
    "application/json"}` (lines 95-98) — matches the doc's auth-header
    claim.
  - `_get` retry/backoff math: `2 ** (attempt + 2)` for 429 (4s, 8s)
    and `2 ** attempt` for 5xx/network (1s, 2s) — matches the table in
    the doc.
  - `_walk_search` defaults `max_pages=5, max_per_page=20` (line 210) —
    matches the "20/page, 5-page cap" claim.
  - All six endpoint paths exist: `SEARCH_PATH = "/twitter/tweet/
    advanced_search"`, `FOLLOWERS_PATH = "/twitter/user/followers"`,
    `USER_INFO_PATH = "/twitter/user/info"`, `ARTICLE_PATH =
    "/twitter/article"`, `QUOTES_PATH = "/twitter/tweet/quotes"`,
    `TWEETS_BY_IDS_PATH = "/twitter/tweets"`.
  - Public methods named in the doc (`run_search`, `get_quote_tweets`,
    `get_tweets_by_ids`, `run_followers`, `user_info`, `get_article`)
    all exist on `TwitterApiClient`.
- Verified against `x_monitor/query_plan.py`:
  - `MIN_FAVES_FOR_LIST_CALL: int = 0` (line 357) — Call A renders
    `min_faves:0`, matching the doc's "Query: `(list:...) min_faves:0`".
  - The 512-character length cap and `assert_under_length_cap` from
    `x_monitor.queries` are referenced from `query_plan.py` (line 350)
    — matches.
- Verified against `render.yaml`:
  - `schedule: "*/15 * * * *"` and `startCommand: python manage.py
    run_cycle --limit-per-call 50` (lines 37, 39) — match.

**No drift found.** The doc is consistent with the source-of-truth on
every constant, path, method name, and formula that the doc references.
The only items that remain unverifiable from source (and are not load-
bearing for the budget/cycle math) are the per-call credit cost claims
for `/twitter/user/info` ("~1 credit") and `/twitter/user/followers`
("1-3 credits per follower") — neither is asserted in `x_monitor/
apify.py` or `x_monitor/run.py` (the apify.py follower comment names
the page-size thresholds — 20-99=3cr, 100-199=2cr, 200=1cr — but the
general "~1 credit per call" for `/twitter/user/info` would need the
upstream TwitterAPI.io pricing page to confirm). These are doc-only
comments, not budget-guard inputs, so they do not affect runtime
behavior.

Last reviewed: 2026-07-24

---

## Review pass 2026-08-05 — drift corrections

Re-verified against HEAD `27a8cb3`. Drift found and corrected:

- **`max_pages` default vs. live config drift** — the doc claims
  `max_pages=5` (the apify.py default) without distinguishing that the
  live `config.yaml` sets `search.max_pages: 100`. The
  `_effective_max_pages` value the budget guard reads is
  `self.config.search.max_pages` (100 on Render) unless the CLI flag
  `--max-pages-per-call` overrides it. The doc's "Pagination" paragraph
  and "At default settings" example were updated to call this out, and
  the Phase 2 Fetch example now shows the config-driven values rather
  than the code-default.
- **`max_results` default vs. live config drift** — the doc claimed
  `max_results=50` (apify.py default) without noting that the live
  `config.yaml` sets `search.max_results: 2000`. Phase 2 Fetch now
  shows `<config>` instead of the hardcoded 50.
- **`--limit-per-call` default clarification** — the doc listed this as
  "default 50" without noting it falls back to `config.search.
  max_results` (2000 on Render). Now documented.
- **sinceTime/untilTime operator injection** — the doc claimed the
  injection logic without noting (a) TwitterAPI.io silently DROPS
  results when both `since:` and `since_time:` are present (so the
  code suppresses `since:` when `since_time` is active), and (b) the
  inline-only contract was verified by direct API test on 2026-07-14
  (commits `a46020f`, `dcf0a8c`). Updated the Time-cursor operators
  bullet to spell out both behaviors.
- **Per-cycle credit cost** — the doc's "1,800 credits/cycle minimum"
  example was based on the implicit `max_pages=1` baseline; with the
  live `max_pages=100` config the worst-case per-call ceiling is 100 ×
  300 = 30,000 credits and worst-case per-cycle is 6 × 30,000 =
  180,000 credits. Updated to show both baselines, plus the budget
  guard interaction.
- **Budget guard trip threshold** — the doc did not state the
  `--max-pages-per-call` value that would actually trip the guard.
  Now documented: `>= 1112` pages/call would exceed 2,000,000 credits
  (6 × 1112 × 300 = 2,001,600).

**No drift found** on the items re-verified below:

- `_CREDITS_PER_ADVANCED_SEARCH_PAGE = 300`, `_BUDGET_HARD_CAP_CREDITS =
  2_000_000`, `_N_CALLS = 6`, the would-spend formula, the `>` strict
  threshold — all match `x_monitor/run.py` (lines 959-981) and
  `tests/test_budget_guard.py`.
- `TWITTERAPI_BASE = "https://api.twitterapi.io"`, `timeout_s: int = 60`,
  `max_retries: int = 2`, the `_headers()` shape (`{"X-API-Key":
  api_key, "Accept": "application/json"}`), the retry/backoff math
  (`2 ** (attempt + 2)` for 429, `2 ** attempt` for 5xx/network) — all
  match `x_monitor/apify.py` (lines 28, 80, 96-100, 117-145).
- `_walk_search` defaults `max_pages=5, max_per_page=20` — still
  correct as the code default.
- All six endpoint paths (`SEARCH_PATH`, `FOLLOWERS_PATH`,
  `USER_INFO_PATH`, `ARTICLE_PATH`, `QUOTES_PATH`, `TWEETS_BY_IDS_PATH`)
  and all public methods (`run_search`, `get_quote_tweets`,
  `get_tweets_by_ids`, `run_followers`, `user_info`, `get_article`) —
  still present.
- `MIN_FAVES_FOR_LIST_CALL: int = 0` — matches Call A rendering
  `min_faves:0`.
- `X_LENGTH_CAP = 512` and `assert_under_length_cap` — match.
- `render.yaml` `schedule: "*/15 * * * *"` and `startCommand: python
  manage.py run_cycle --limit-per-call 50` — match.

**Items that remain unverifiable from source** (unchanged from prior
review, still not load-bearing):

- `/twitter/user/info` credit cost ("~1 credit") — no source-of-truth
  in repo.
- `/twitter/user/followers` credit cost ("1-3 credits per follower
  depending on page size") — the page-size thresholds (20-99=3cr,
  100-199=2cr, 200=1cr) are in `apify.py`'s `FOLLOWERS_MAX_PER_PAGE`
  comment; the per-call totals would need the upstream pricing page.
- Per-cycle credit cost when the live config is used — depends on
  actual `max_pages` × `max_results` × TwitterAPI.io's page-fill
  behavior; the doc shows the worst-case ceiling only.

Last reviewed: 2026-08-05

## Update 2026-08-10 (plan 2026-08-10-002)

Cycle no longer runs continuous QT capture. `GET /twitter/tweets` is used only for **one-shot metrics refresh** on posts older than `metrics_refresh.delay_hours` that have never been stamped (`metrics_refreshed_at` null). `GET /twitter/tweet/quotes` is not invoked from the harvest cycle.
