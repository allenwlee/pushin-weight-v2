<!-- {{AGENT_ATTRIBUTION}} -->
# TwitterAPI.io call inventory

**Repo:** `x-monitoring` (Flask + htmx dashboard for X.com / Twitter monitoring of 11 Chinese/non-Chinese AI models — `minimax`, `qwen`, `deepseek`, `glm`, `xiaomi_mimo`, `moonshot_kimi`, `inclusionai`, `mistral`, `stepfun`, `ernie`, `hunyuan`)
**Branch (current):** `main` (v1.7 shipped 2026-06-17, commit `e218d13`; v1.8 schema refactor shipped 2026-06-19, commit `ce2eed1`)
**Migration origin:** 2026-06-08 — replaced `automation-lab/twitter-scraper` (Apify) with TwitterAPI.io. Cookie-free, ~95% cheaper ($0.15/1k tweets vs $3/1k on Apify).
**API key env var:** `TWITTERAPI_IO_API_KEY` (read at `TwitterApiClient.from_env()`; sent as `X-API-Key` header)
**Base URL:** `https://api.twitterapi.io`
**HTTP method:** All calls are `GET` with `params=...` query string
**Auth header:** `X-API-Key: <key>` (`x_monitor/apify.py:101`)
**Timeout:** 60 s per request; up to 3 attempts on 429/5xx with exponential backoff (1s, 4s, 1s)
**Last reviewed:** 2026-06-20 (JST) — model count, schema rename, and Anthropic proxy compatibility fixes

This document lists every endpoint x-monitor calls, the call sites that invoke it, the cost model, and the per-call caps the code enforces.

> **v1.7 status (shipped 2026-06-17, commit `e218d13`, PR #3 merged):** The workhorse endpoint `/twitter/tweet/advanced_search` drops from **10–16 calls/cycle (v1.6) to exactly 2 calls/cycle**. Call A is a `list:`-based query that pulls any tweet authored by anyone in a curated public x.com list; Call B is a paren-grouped OR-chain over all deduped brand tokens. The `INTENT_BUCKETS` constants and `_split_brands_to_fit_cap` recursion are retired — all signal classification is post-fetch. A new translation pass (Claude Haiku) runs after the per-brand filter. v1.8 (commit `ce2eed1`) renamed `model_id` → `brand_id` across the schema and code; the call inventory is unchanged but per-model references in this doc now read as per-brand. See [docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md](../plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md) for the v1.7 design and `docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md` for the v1.8 schema refactor.

---

## Endpoints used (4 total)

### 1. `GET /twitter/tweet/advanced_search` — the workhorse

**Method in code:** `TwitterApiClient.run_search(query, max_results, since, cookies)` → `_walk_search(query, max_results, max_pages=5)`
**File:** `x_monitor/apify.py:201-223` (public) + `_walk_search` at `x_monitor/apify.py:127-145`
**Path constant:** `SEARCH_PATH = "/twitter/tweet/advanced_search"` (`x_monitor/apify.py:27`)
**Per-page cap:** 20 tweets (`SEARCH_MAX_PER_PAGE = 20`)
**Pagination:** `has_next_page` + `next_cursor`; up to 5 pages (100 tweets max) per call
**Defensive cap:** `max_pages=5` (`x_monitor/apify.py:159`) — guards against a runaway cursor draining the credit budget. With 20 tweets/page × 5 pages = 100 tweets, which covers all current `max_results=50` queries with headroom.

**Query params sent:**
- `query` (str) — X advanced-search string. v1.6: `(from:OFFICIAL OR to:OFFICIAL OR ... OR from:STAFF10 OR to:STAFF10) min_faves:1`. **v1.7:** Call A = `(list:x_monitor_list_id) min_faves:1`; Call B = `((BrandTok1a OR BrandTok1b) OR (BrandTok2a) OR ...) min_faves:0`. TwitterAPI.io accepts the same X operators including `list:`.
- `queryType` (str) — always `"Latest"` (`x_monitor/apify.py:170`)
- `limit` (int) — `min(20, max_results - len(out))`; shrinks the final page when the ceiling is approached
- `cursor` (str, optional) — `next_cursor` from the previous page, omitted on page 1

**Pre-call validation:** `assert_under_length_cap(q.query_string)` at `x_monitor/queries.py:171` (renamed from `assert_under_operator_cap` in v1.7) raises `ValueError` if the query string exceeds **512 characters**. **The cap is on character length, not on operator count.** This is the official X API v2 self-serve recent-search limit (per [docs.x.com](https://docs.x.com/x-api/posts/search/integrate/operators)). Over-cap queries silently return 0 tweets on X — loud-fail BEFORE the call to prevent credit burn. **v1.7 update:** the v1.6 operator-count check was based on the misleading getxapi.com claim that paren grouping reduces operator count. **Empirically refuted 2026-06-17** — paren-grouping does not bypass the cap; queries with 30 inner ORs in 1, 3, 5, 10, or 15 paren groups all fail at the same character length (verified via direct API probe, boundary 509 → 520 chars, see `references/_validation/2026-06-17-twitterapi-length-cap-probe.md` if checked in). v1.7 Call A = 29 chars, Call B = 218 chars at 7 brands — both well under 512. **Real ceiling for Call B: ~15-17 brands with 3 tokens each (not the v1.6 plan's claimed 21 brands).**

**Credit cost:** **15 credits per call** (TwitterAPI.io charges a 15-credit floor per search call regardless of result count; 15 credits per returned tweet beyond that). Cost confirmed via `verified 2026-06-15` direct API probe and recorded in the v1.6 plan.

**v1.6 call shape (deprecated in v1.7):**

> *Kept for diff context. v1.7 retires this shape entirely.*

**v1.6 call sites (3):**

1. **`x_monitor/run.py` (pre-v1.7) — `RunPipeline.execute` v1.6 plan_calls loop**
   - Per-cycle call list was built by `plan_calls(self.data_dir, models)` (now replaced; see v1.7 below)
   - For each `PlannedCall`, fired `apify.run_search(call.query_string, max_results=50)`
   - **Account calls:** 1 per enabled brand (7 in the original v1.6 deployment), each builds `(from:OFFICIAL OR to:OFFICIAL OR from:STAFF1 OR to:STAFF1 OR ... OR from:STAFF10 OR to:STAFF10) min_faves:1` — exactly 22 operators at 1 official + 10 staff, under the cap.
   - **Intent calls:** 1-3 per bucket (`howto_criticism`, `benchmark_tech`, `praise_other`), bucketed across all 7 brands. Each intent call OR-crosses all brand terms with all bucket tokens, splitting if it would exceed the operator cap. Brand-token map is `_load_brand_tokens_per_model(enabled_models, queries_dir)` from `data/queries/<m>.yaml`.
   - **Total per cycle (7 brands at v1.6):** 7 account + 3-9 intent = **10-16 calls** at 15 credits floor = **150-240 credits/cycle minimum**, plus 15 credits per returned tweet.
   - **Schedule:** every 15 minutes via LaunchAgent `com.fuchitalee.x-monitor.scheduled` (`deploy/com.fuchitalee.x-monitor.scheduled.plist`). Cost ~$12-30/month at 15-min cadence with current brand/staff counts.

2. **`x_monitor/apify.py:295` — `TwitterApiClient.probe_api()` (health check)**
   - Internal liveness check: hits `user/info` on `MiniMaxAI` (a known good handle). Not actually a `run_search` call — see endpoint #3.

3. **Tests (`tests/test_apify.py` and others)** — mocked; no live calls in CI.

**Critical bug fix in v1.6 commit 1 (commit `5301837`):** The previous code called `_get(SEARCH_PATH, params)` once and assumed it was the full set. Two failures flowed from this:
1. **Page cap of 20** was being silently applied even when callers asked for `max_results=50` — the 2026-06-10 run reported `n_results: 20` for nearly every query, wasting 60% of available signal.
2. **Operator cap silent fail** — a malformed query returned 0 tweets, the pipeline logged `n_results: 0`, and the operator had no way to know the query was over-cap.

The fix paginates via `next_cursor` and pre-validates with `assert_under_operator_cap`.

**v1.7 call sites (3):**

1. **`x_monitor/run.py:386` — `RunPipeline.execute` v1.7 plan_calls loop**
   - Per-cycle call list is built by `plan_calls(self.data_dir, models, x_monitor_list_id=<int>)` at `x_monitor/query_plan.py:181-241` — new required `x_monitor_list_id` kwarg.
   - Returns exactly **2** `PlannedCall`s:
     - **Call A** (kind=`account`): `(list:<x_monitor_list_id>) min_faves:1` — **38 characters** with the current real list ID `2067062923525275922` (a 19-digit Snowflake-style ID). Pulls any tweet authored by anyone in the curated public x.com list, which contains all official + staff handles across all enabled brands. The `list:` operator is the **real escape hatch from the 512-char cap**: a single numeric list ID stays ~12-19 chars regardless of how many handles are in the list. (Empirically verified 2026-06-17: a fake list ID `1234567890` returns HTTP 200 with 20 latest tweets — the API doesn't reject unknown lists at query-validation time, it just returns whatever the operator-or-Latest fallback yields.)
     - **Call B** (kind=`brand_wide`): `((BrandTok1a OR BrandTok1b) OR (BrandTok2a) OR ...) min_faves:0` — **333 characters at the current 11 brands** (11 paren groups). Pulls any tweet whose text contains any deduped brand token from `data/queries/<m>.yaml`. Fits under the 512-char cap with ~180 chars of headroom.
   - **Total per cycle:** **2 calls** at 15 credits floor = **30 credits/cycle minimum**, plus 15 credits per returned tweet — **5-8× lower than v1.6's 150-240 credit floor** (v1.6 ceiling was 240 credits for 16 calls; the floor saving scales with the actual call count).
   - **Length-cap math (verified 2026-06-17 against TwitterAPI.io direct probe; updated 2026-06-20 for 11 brands):**
     - Call A: 38 chars → ~13× under cap ✓
     - Call B at 11 brands × ~21 tokens: **333 chars** → ~1.5× under cap ✓ (was 218 chars at 7 brands in the original v1.7 design)
     - Call B ceiling: ~15-17 brands × 3 tokens ≈ 500 chars. **Beyond 11 brands the v1.7 math still fits; the next stretch is 15+ brands, which is a v1.9 concern, not v1.8.**
   - **Why `list:` for Call A instead of a flat OR-chain?** 1 official + 10 staff × 11 brands × 2 (`from:` + `to:`) = 242 OR tokens ≈ 2,400 chars → way over the 512-char cap → silent fail. The `list:` operator pulls tweets from any list member with a ~12-19-char query, making the cap irrelevant. This is the **only** viable way to get the staff handle coverage in a single call.
   - **Why not a paren-grouped union for Call A?** `(from:H1 OR to:H1) (from:H2 OR to:H2) ...` is **AND** in X advanced search (intersection, not union). Wrong shape.
   - **Why paren-group Call B at all?** Cosmetic / readability + a tiny credit-of-doubt: the API parses `(a OR b OR c)` as a single grouped expression, which is the documented X idiom for OR-chains. Ungrouped `a OR b OR c` also works (and is shorter by 2 chars per group) — but paren-grouped is the conventional form, makes the per-brand attribution boundaries visible, and lets the post-fetch regex see the same structure. **Note: paren grouping does NOT change the cap behavior** — see the "Empirical cap probe" callout in `2026-06-16-194558-twitterapi-live-queries-by-model.md`.
   - **Post-fetch attribution:** Both call results run through `attribute_to_brand(text, author_handle, brand_tokens, staff_handles, *, compiled_brand_pattern=None, token_to_brand=None)` (`x_monitor/intent_classifier.py:175`) — a legacy-compat shim that wraps the v1.8 `attribute_to_brands` consolidator. The two keyword args hold a single compiled alternation regex plus a token→brand lookup dict, built once per cycle. Author-handle priority runs first (cheap O(brand × handle_count)); the compiled regex is the wide-net fallback. Sub-millisecond on 200 tweets.
   - **Signal classification (v1.8, per-brand decomposition):** `classify_signal(text, brand_ids, brand_registry, anthropic_client=None)` (`x_monitor/attribution.py:845`) runs against every `(post, brand)` pair after attribution; result is written to `post_brand_signals.signal` (per-brand table added in v1.8 migration 004, commit `ce2eed1`). The 6-signal taxonomy (`release`, `community_question`, `criticism`, `commenter_capture`, `other`, `praise`) is unchanged. The legacy single-string `classify_signal(text)` shim still exists at `x_monitor/intent_classifier.py:104` for callers without brand context (e.g. ad-hoc headline rendering) and emits a `DeprecationWarning`.
   - **List-drift detection:** After Call A's first response, the set of `author_handle`s is compared to the union of `data/accounts/<m>.yaml::accounts + staff` across enabled brands. If a yaml-listed handle is absent for 3 consecutive dry-runs, write `degraded:list_drift: ["expected: alice_dev", ...]` to the run JSON. **Soft warning, not hard fail** — the x.com API doesn't expose list membership. Note: 4 of the 11 enabled brands (`mistral`, `stepfun`, `ernie`, `hunyuan`) currently have **no `data/accounts/<m>.yaml`** (only `data/queries/<m>.yaml` exists). They contribute 0 handles to Call A's drift check and 0 staff-handle priority matches for attribution; their posts only surface via Call B's regex path. List-drift detection only fires for the 7 brands that have accounts yaml.
   - **Translation pass:** After all kept posts are inserted, `translate_kept_posts(kept_all, ...)` (`x_monitor/translator.py:NEW in v1.7`) calls Claude Haiku (batched 20 tweets/request) to produce `text_en` and `text_zh_cn` for each kept post. Failures are non-fatal; the `x-monitor translate` subcommand is the recovery/backfill path.
   - **Anthropic proxy routing (2026-06-20, commit `49a2ab7`):** The `AnthropicClaudeClient` in both `x_monitor/attribution.py` and `x_monitor/translator.py` honors `ANTHROPIC_BASE_URL` and swaps to `MINIMAX_API_TOKEN` when the URL contains `minimax.io`. This lets the translator run in environments without a direct Anthropic key. M3.0 is the proxy's default model (`MiniMax-M3.0`); the operator's `~/.env.secrets::ANTHROPIC_MODEL` overrides. See `feedback_minimax_proxy_anthropic_compat.md` for the full contract.
   - **Schedule:** unchanged — every 15 minutes via LaunchAgent `com.fuchitalee.x-monitor.scheduled`. The `~/.env.secrets` env wrapper now also exports `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_BASE_URL` + `ANTHROPIC_MODEL` + `MINIMAX_API_TOKEN` for proxy routing) for the translation pass.

2. **`x_monitor/apify.py:295` — `TwitterApiClient.probe_api()` (health check)** — unchanged.
3. **Tests (`tests/test_apify.py`, `tests/test_run.py`, `tests/test_translator.py`, `tests/test_query_plan_v17.py`)** — mocked; no live calls in CI.

**v1.7 launch steps (one-time, in order):**
1. Operator creates a public x.com list named (e.g.) `x-monitor-staff` containing the 7 brands' official handles (currently all staff lists are empty, so just 7 handles today; expand as staff populates). The 4 newer brands (`mistral`, `stepfun`, `ernie`, `hunyuan`) are query-only — they have brand tokens for Call B but no account yaml, so they contribute 0 handles to the list. List coverage is therefore the 7 brands × ~1 handle each.
2. Operator copies the list's numeric ID from the x.com URL (the `list:1234567890` portion). The current real list ID is `2067062923525275922`.
3. Operator sets `x_monitor_list_id: 2067062923525275922` in `x-monitoring/config.yaml`. **This field is required** — the new `Config` schema validation fails without it. (Done as of commit `cc02a63` / 2026-06-20.)
4. Operator restarts the LaunchAgent: `launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor.scheduled`.
5. First dry-run (`python -m x_monitor dry-run`) should show 2 calls, a non-empty Call A response with author handles from the curated list, and a Call B response with brand-token hits.

**Ongoing operational task:** When `data/accounts/<m>.yaml::staff` gains a new handle, the operator adds it to the x.com list. The list-drift detection surfaces any miss as a soft warning after 3 cycles. For the 4 query-only brands (`mistral`, `stepfun`, `ernie`, `hunyuan`), no list-side action is needed — their visibility is purely Call B.

---

### 2. `GET /twitter/article` — long-form X article body (v1.4+, unchanged in v1.7)

**Method in code:** `TwitterApiClient.get_article(tweet_id) -> dict | None`
**File:** `x_monitor/apify.py:268-287`
**Path constant:** `ARTICLE_PATH = "/twitter/article"` (`x_monitor/apify.py:34`)
**Credit cost:** **100 credits per call** (flat, regardless of article length)

**Query params sent:**
- `tweet_id` (str) — the integer id of the **tweet that contains the t.co link to the article** (NOT the article path id from the URL). For `x.com/i/article/2064029478616182784`, the relevant tweet_id is on the parent post, not in the URL.

**Returns:** Normalized dict with at least: `title`, `preview_text`, `plain_text` (flattened content blocks: `header-one`/`header-two`/`header-three`/`unstyled`/`markdown`/`unordered-list-item`/`ordered-list-item`), `cover_media_img_url`, `author`, `created_at`. Returns `None` if the tweet has no long-form article or the article is not in the cache.

**Critical bug fix (commit `5bf850d`, 2026-06-16):** The previous code passed the **article path id** (e.g., `2064029478616182784`) to `api.get_article()`. The API rejected it (returned `None` for every call), and the headline cache poisoned itself with `title=null, source="fetched"` entries that were never retried. The fix uses the **post's own `id`/`tweet_id` field** for the API call while still using `x_article_tweet_id(url)` as a detector of "is this an x.com/i/article URL?".

**Routing logic (in both call sites):**
```python
is_x_article = x_article_tweet_id(fetch_target) is not None  # detector only
x_tid = item.get("id") or item.get("tweet_id") or ""        # post's own tweet_id
if is_x_article and api is not None and x_tid:
    article = api.get_article(x_tid)
```
Where `x_article_tweet_id(url)` extracts the path id from a URL matching `x.com/i/article/{digits}` and is used purely to gate whether we're in X-article territory.

**Call sites (2):**

1. **`x_monitor/headlines.py:700` — `enrich_posts()` inner loop**
   - Called from the v1.7 pipeline at `x_monitor/run.py` after `apify.run_search` returns tweets. The pipeline passes `cache=cache, api=apify` to `filter_and_review(...)` (`x_monitor/run.py:447-485`), which routes URL-only posts to `enrich_posts` for headline enrichment.
   - Cache key: `f"x_article:{x_tid}"` (key_override)
   - Per-run cap: `per_run_cap` from `x_monitor/__main__.py` (`200` by default) — counted via `run_fetches_used[0] += 1` (`x_monitor/headlines.py:703`).
   - On success: `cache.put(x_tid, title, SOURCE_FETCHED, ...)` + `item["headline"] = title` + `item["headline_source"] = "fetched"`.
   - On `None` return: `cache.put(x_tid, None, SOURCE_FETCH_FAILED, error="api_no_article", ...)` + `item["headline_source"] = "fetched_failed"`.
   - On exception: `log.info(...)` + `article = None` + treat as failure (no cache write on exceptions).

2. **`x_monitor/__main__.py:592` — `x_monitor relevance backfill --via-api` loop**
   - Operator-initiated backfill for URL-only posts that the live pipeline didn't enrich. Same cache key scheme (`f"x_article:{x_tid}"`).
   - Per-query cap: `per_query_cap * 25` (default `8 * 25 = 200` calls) — defends against an unbounded backfill exhausting the daily credit budget.
   - On success: same cache + DB updates as `enrich_posts`, plus a `[i/len(rows)] fetched=... cached=... failed=... skipped=... via_api=...` progress line every 10 rows.
   - Verified working: 2026-06-16 backfill on 200 posts → 194 fetched (97%), 2 genuine API misses, 4 already-fresh, 0 poisoned.

---

### 3. `GET /twitter/user/info` — public profile lookup (unchanged in v1.7)

**Method in code:** `TwitterApiClient.user_info(handle) -> dict | None`
**File:** `x_monitor/apify.py:242-265`
**Path constant:** `USER_INFO_PATH = "/twitter/user/info"` (`x_monitor/apify.py:31`)
**Credit cost:** **1 credit per call** (low-cost endpoint; exact cost not stated in code — based on TwitterAPI.io public pricing for user-info)

**Query params sent:**
- `userName` (str) — handle WITHOUT the `@` prefix, e.g. `"MiniMaxAI"`

**Returns:** Normalized dict with at least: `handle`, `name`, `description`, `followers_count`, `verified`, `id`. Returns `None` if the user is not found (HTTP 200 but no `data`/`user` key).

**Call sites (2):**

1. **`x_monitor/__main__.py:443` — `x_monitor relevance audit-handles <model>`**
   - For each canonical handle in `data/filters/<model>.yaml::canonical_handles`, fetch the live profile and run a heuristic (`x_monitor/relevance.py:301-313`) checking:
     - name contains any of the brand tokens
     - description contains any of the brand tokens
     - `followers_count >= 1000` (configurable)
     - `verified == True`
   - Result: a per-handle `PASS`/`WARN`/`FAIL` verdict. Used during relevance-rule tuning to catch stale canonical_handles entries.

2. **`x_monitor/apify.py:295` — `TwitterApiClient.probe_api()`**
   - Lightweight liveness check: hit `user/info` on `MiniMaxAI` (a known good handle).
   - Returns `True` iff the call succeeds with a non-empty response.
   - Used by tests and operator diagnostics. Replaces the old cookie probe.
   - Returns `True` on transient errors (429/5xx/network) — those are not liveness failures.

---

### 4. `GET /twitter/user/followers` — follower list (bulk, unchanged in v1.7)

**Method in code:** `TwitterApiClient.run_followers(handle, max_results, cookies)` → `_walk_followers(handle, max_results)`
**File:** `x_monitor/apify.py:230-238` (public) + `_walk_followers` at `x_monitor/apify.py:127-145`
**Path constant:** `FOLLOWERS_PATH = "/twitter/user/followers"` (`x_monitor/apify.py:28`)
**Per-page cap:** 200 followers (`FOLLOWERS_MAX_PER_PAGE = 200`)
**Pagination:** `next_cursor`; pages until `max_results` is hit
**Per-page cost:** variable, per TwitterAPI.io's pricing model:
  - 20-99 returned = **3 credits each**
  - 100-199 = **2 credits each**
  - 200 = **1 credit each** (cheapest)

**Why 200 per page:** Always ask for 200 — the price-per-item is the cheapest (`x_monitor/apify.py:35-38`).

**Query params sent:**
- `userName` (str) — handle WITHOUT the `@` prefix
- `page_size` (int) — always 200
- `cursor` (str, optional) — `next_cursor` from the previous page, omitted on page 1

**Call site (1):**

1. **`x_monitor/__main__.py:180` — `x_monitor accounts refresh <handle>`**
   - Operator-initiated command to refresh a single handle's follower list. Used for the community-graph feature (mapping who follows each model account) and for relevance-rule tuning.
   - `max_results=200` is the default. The `_walk_followers` loop computes `max_pages = max(1, (max_results + 199) // 200)` so a 200-call returns in 1 page, a 400-call in 2 pages, etc.
   - Not part of the scheduled pipeline. Not called from `RunPipeline.execute`.

---

## Call-site × endpoint matrix (v1.7)

| Endpoint | Method | File:line | Trigger | Credits/call | Frequency |
|---|---|---|---|---|---|
| `GET /twitter/tweet/advanced_search` | `run_search` → `_walk_search` | `run.py:412` | Scheduled 15-min + WatchPaths | 15 floor + 15/tweet | **2 calls/cycle (was 10-16)** |
| `GET /twitter/tweet/advanced_search` | (test mocks) | `tests/test_apify.py` | pytest | n/a (mocked) | CI only |
| `GET /twitter/article` | `get_article` | `headlines.py:700` | Live pipeline (URL-only posts) | 100 | Per URL-only post (capped at 200/run) |
| `GET /twitter/article` | `get_article` | `__main__.py` (backfill loop) | `relevance backfill --via-api` | 100 | Per backfill row (capped at 200) |
| `GET /twitter/user/info` | `user_info` | `__main__.py` (audit-handles) | `relevance audit-handles <brand>` | ~1 | Per canonical handle (manual) |
| `GET /twitter/user/info` | `probe_api` | `apify.py:295` | Diagnostic / tests | ~1 | On-demand |
| `GET /twitter/user/followers` | `run_followers` → `_walk_followers` | `__main__.py` (`accounts refresh`) | `accounts refresh <h>` | 1-3 per follower | On-demand (manual) |
| **Anthropic Messages API** (NEW in v1.7) | `translate_batch` | `translator.py:268-310` | End of each 15-min cycle | ~$0.005 / 1000 tweets | 1 call / 20 kept posts |
| **Anthropic Messages API** (NEW in v1.8) | `classify_signal` per brand | `attribution.py:845-893` | Post-attribution per kept post | ~$0.0001 / brand-row | 1 call / brand-row (opt-in via `--with-llm`) |

**The last row is a new endpoint class (Anthropic, not TwitterAPI.io)** — included for completeness. Claude Haiku 4.5 pricing is ~$1/MTok input, $5/MTok output. Typical 200-char tweet ≈ 200 tokens; 1,000 kept posts/cycle ≈ $0.005 per locale. Batched at 20 tweets per request. See `x_monitor/translator.py` (new in v1.7).

---

## Error handling (shared across all endpoints)

`TwitterApiClient._get()` (`x_monitor/apify.py:100-119`) handles errors uniformly:

| HTTP code | Behavior |
|---|---|
| 200 | Return `r.json()` |
| 401 | Raise `TwitterApiAuthError` (fatal; aborts the run via `summary["status"] = "aborted"` in `run.py:396`) |
| 429 | Retry with exponential backoff (1s, 4s) up to `max_retries=2`; raise `TwitterApiRateLimitError` after exhaustion |
| 5xx | Retry with exponential backoff (1s, 2s) up to `max_retries=2`; raise `TwitterApiServerError` after exhaustion |
| Other 4xx | Raise `RuntimeError` with the response text (first 200 chars) |
| `requests.RequestException` (network) | Retry with backoff (1s, 2s) up to `max_retries=2`; re-raise after exhaustion |

`max_retries=2` means up to 3 total attempts per call.

**Anthropic translator (`x_monitor/translator.py`, v1.7) error handling:**

| Error | Behavior |
|---|---|
| 200 OK with valid JSON | Parse `results[]` and write via `bulk_update_translations` |
| 200 OK with malformed JSON | Log warning; mark that tweet as failed; continue |
| 429 / 5xx / network | Retry with exponential backoff (1s, 4s, 1s) up to 3 attempts; on final failure, mark all tweets in the batch as failed, log warning, continue |
| All tweets in a batch failed | Cycle completes; `translation_stats.n_failed` reflects the count; `x-monitor translate` is the recovery |

---

## Cost summary

**Live pipeline (15-min cycle, 11 brands):**

| Component | v1.6 cost | v1.7 cost | Δ |
|---|---|---|---|
| Account calls (TwitterAPI.io) | 11 × 15 = 165 credits floor | **1 × 15 = 15 credits floor** (Call A) | −91% |
| Intent calls (TwitterAPI.io) | 3-9 × 15 = 45-135 credits floor | **1 × 15 = 15 credits floor** (Call B) | −67% to −89% |
| Returned tweet cost (TwitterAPI.io) | N × 15 | N × 15 (unchanged) | 0 |
| URL-only X-article enrichment | 0-200 × 100 credits | 0-200 × 100 credits (unchanged) | 0 |
| **Per-cycle TwitterAPI.io floor** | **210-300 credits** | **30 credits** | **−86% to −90%** |
| **Translation pass (Anthropic, NEW v1.7)** | n/a | ~$0.005 / 1000 kept posts | (additive) |
| **Per-brand signal classification (NEW v1.8)** | n/a | ~$0.0001 / brand-row (Haiku direct; 25× slower via proxy) | (additive) |

**v1.7 idle (no new tweets, no translations):** ~30 credits/cycle × 4 cycles/hour × 24 hours = **2,880 credits/day** (was ~17,300 at v1.6's 11-brand upper bound). At $0.15/1k ≈ **$0.43/day ≈ $13/month** (was ~$2.60/day or ~$78/month).

**v1.7 busy:** 30 credits/cycle + return surcharge + LLM translation ≈ $1-2/day ≈ $30-60/month.

The user-reported figure at the time of the v1.6 plan was **$12-30/month** at 15-min cadence with 7 brands. v1.7 lands the pipeline at the low end of that range for idle and below the median for busy cycles; the 11-brand expansion did **not** raise the floor because Call A and Call B each stay at 1 call/cycle.

**v1.8 reattribute one-time cost (commit `cc02a63`):** the 2026-06-20 backfill of `post_brand_signals` processed ~2,700 brand-rows at ~42 rows/min on direct Haiku 4.5, taking ~65 minutes wall clock and ~$0.10-0.30. Coverage was 74.4% (2,010/2,700 brand-rows; the rest are correct empty-by-design cases where the LLM judges a body-keyword match is a false positive).

---

## Caching and dedup

- **Search results:** NOT cached at the API layer — TwitterAPI.io's own dedup handles repeat queries on their side. The pipeline relies on `posts.tweet_id` UNIQUE constraint in the SQLite store (`x_monitor/store.py`) to dedup.
- **X-article headlines:** Cached in `data/headlines_cache.json` (`x_monitor/headlines.py` cache module) with key `f"x_article:{tweet_id}"`. Versioned entries; `title=None` + `source="fetched_failed"` entries are kept (not retried by default — the `error="api_no_article"` field distinguishes "no article exists" from "transient failure"). The 2026-06-16 bug was a poisoned cache where `title=None, source="fetched"` (note: not "fetched_failed") was being written, which made the pipeline skip retry forever.
- **Backfill cache reuse:** The backfill at `x_monitor/__main__.py:540-560` checks the same cache before issuing a call, so backfill work is incremental across runs.
- **Translations (v1.7 NEW):** Stored directly in `posts.text_en` and `posts.text_zh_cn` columns. Idempotent: `bulk_update_translations` re-running with the same data is a no-op. The `x-monitor translate [--locale en|zh-CN|both] [--limit N]` subcommand is the recovery/backfill path for posts where translation failed (NULL columns).

---

## Why no POST/PUT/DELETE

x-monitor is a **read-only** monitor. It never writes to Twitter, never posts, never modifies user data. All 4 TwitterAPI.io endpoints are pure `GET` reads. The `cookies` parameter that the old ApifyClient required is accepted for backward compatibility but is ignored (`x_monitor/apify.py:204`, `:232`).

---

## Source files for this inventory

- `x_monitor/apify.py` — the `TwitterApiClient` wrapper (442 lines; this doc references line numbers)
- `x_monitor/headlines.py` — the `enrich_posts` X-article branch (`x_monitor/headlines.py:654-720`)
- `x_monitor/__main__.py` — the backfill loop (`x_monitor/__main__.py:520-620`) and CLI subcommands
- `x_monitor/run.py` — the v1.7 pipeline inner loop at `x_monitor/run.py:386-485` (replaces v1.6's 14-call loop)
- `x_monitor/query_plan.py` — the `plan_calls()` function (`x_monitor/query_plan.py:181-241`; v1.7 emits 2 calls: `list:`-based Call A + paren-grouped Call B)
- `x_monitor/queries.py` — the character-length pre-check (`assert_under_length_cap`)
- `x_monitor/intent_classifier.py` — legacy compat shim: `classify_signal(text)` and `attribute_to_brand(text, author_handle, brand_tokens, staff_handles, *, compiled_brand_pattern, token_to_brand)` (v1.7 signature with v1.8 kwargs)
- `x_monitor/attribution.py` — v1.8 per-brand signal decomposition: `attribute_to_brands()`, `classify_signal(text, brand_ids, brand_registry, anthropic_client)` with optional LLM via `AnthropicClaudeClient` (routes through minimax proxy when `ANTHROPIC_BASE_URL` is set)
- `x_monitor/reattribute.py` — v1.8 reattribute CLI subcommand with `--with-llm` flag
- `x_monitor/translator.py` (v1.7 NEW) — Claude Haiku translation pass
- `x_monitor/dashboard.py` — per-locale rendering via `_pick_text(post, locale)`
- `x_monitor/migrations/` — schema migrations including 004 (`company/brand/account` refactor, commit `ce2eed1`)
- `data/headlines_cache.json` — the X-article headline cache
- `x-monitoring/config.yaml` — the v1.7-required `x_monitor_list_id` field (currently `2067062923525275922`)
