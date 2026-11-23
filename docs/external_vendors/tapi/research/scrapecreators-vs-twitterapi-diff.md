# ScrapeCreators vs TwitterAPI.io — X API Diff

_Date: 2026-08-04 · Sources: 6 scraped scrapecreators.com Twitter endpoint pages + 4 context pages (introduction, caching, credit-balance, retired-endpoints), diffed against `twitterapi_docs/INDEX.md` (63 endpoints) and `twitterapi_docs/rate-limit-ux.md`._

## TL;DR

**ScrapeCreators is a read-only X API with 6 endpoints, all 1 credit/request.** It has zero write endpoints (no post/like/follow/DM), zero batch endpoints, and zero webhook/streaming endpoints. **TwitterAPI.io has 63 endpoints spanning read + write + streaming.** The two products are not in the same category: ScrapeCreators is a "scrape this URL" wrapper with caching; TwitterAPI.io is a full third-party X client.

For our pushin-weight-v2 use case (read-only reconciliation of brand handles against X user data), ScrapeCreators could substitute for TwitterAPI.io on the 4 endpoints we actually use (`profile`, `user-tweets`, `tweet`, `community`). It cannot replace the write or streaming endpoints if we ever add them.

## ScrapeCreators X endpoint inventory (6 endpoints)

All endpoints are `GET`, return `{"success": true, "credits_remaining": N, "credits_charged": 1, ...}`, and authenticate via the `x-api-key` header. All cost **1 credit per live request**; cache hits cost 0.

| ScrapeCreators path | Params | What it returns | twitterapi.io equivalent |
|---|---|---|---|
| `GET /v1/twitter/profile` | `handle` (required), `cache_max_age` (1d/3d/7d/14d/30d) | Full X user object (`legacy` block: followers, friends, statuses_count, verified, etc.) + `rest_id` + `is_blue_verified` | `get_user_by_username.md` (15-20 credits) — returns a leaner user object |
| `GET /v1/twitter/user-tweets` | `handle`, `trim` (bool) | 100 of user's "most popular" tweets. Docs are explicit: **"these aren't the users latest tweets"** — X returns only the top 100 publicly | `get_user_last_tweets.md` (20/page, sorted by created_at) or `get_user_timeline.md` |
| `GET /v1/twitter/tweet` | `url` (full tweet URL), `trim`, `cache_max_age` | Single tweet details (`full_text`, `favorite_count`, `reply_count`, `view_count`) | `get_tweet_by_ids.md` (takes tweet IDs, not URLs) |
| `GET /v1/twitter/tweet/transcript` | `url`, `cache_max_age` | Transcript for a tweet with attached video | **No equivalent** — twitterapi.io does not expose tweet-video transcripts |
| `GET /v1/twitter/community` | `url` (community URL) | Community details (`name`, `member_count`) | `get_community_by_id.md` (takes community id, 20 credits) |
| `GET /v1/twitter/community/tweets` | `url` | Tweets from a community | `get_community_tweets.md` or `get_all_community_tweets.md` |

**Notable ScrapeCreators design choices:**

- All 1 credit/req flat — no batch discount. (Compare twitterapi.io: 18 credits/user single, 10 credits/user at 100+ batch.)
- `cache_max_age` lets you trade freshness for cost: pass `7d`, you get the cached response for 0 credits if it's ≤ 7 days old, otherwise a live scrape for 1 credit. Cache is "always warming" — every successful request refreshes the cache. Cache keys are endpoint+resource, so different `cache_max_age` values read the same copy.
- Trimmed mode on `user-tweets`/`tweet` shrinks the response (good for batched reconciliation; cuts down on `legacy.*` fields).
- 402 Payment Required is in the response code list — credits can run out.
- Vendor claims "**no rate limits**" (introduction page); recommends keeping usage below 500 concurrent requests for best perf. **This is the opposite of twitterapi.io**, which has per-account QPS caps.

## Diff: endpoints in twitterapi.io but NOT in ScrapeCreators

ScrapeCreators covers **6** of twitterapi.io's **63** X endpoints. The 57 missing endpoints split into four buckets:

### A. Write actions (12 endpoints — all missing)

ScrapeCreators has no write surface at all. twitterapi.io write endpoints (`create_tweet_v2`, `delete_tweet_v2`, `like_tweet_v2`, `unlike_tweet_v2`, `retweet_tweet_v2`, `bookmark_tweet_v2`, `unbookmark_tweet_v2`, `follow_user_v2`, `unfollow_user_v2`, `send_dm_v2`, `upload_media_v2`, `update_profile_v2`, `update_avatar_v2`, `update_banner_v2`, `create_community_v2`, `delete_community_v2`, `join_community_v2`, `leave_community_v2`) all require a `login_cookie` from `/twitter/user_login_v2`. ScrapeCreators does not document any equivalent — it explicitly markets itself as a "public data extraction" tool.

### B. Streaming / webhooks (7 endpoints — all missing)

`add_user_to_monitor_tweet`, `remove_user_to_monitor_tweet`, `get_user_to_monitor_tweet`, `add_webhook_rule`, `update_webhook_rule`, `delete_webhook_rule`, `get_webhook_rules` — all real-time stream control. ScrapeCreators has no streaming surface. If we ever needed real-time tweet monitoring (e.g. for "watch this handle for new posts"), twitterapi.io is the only option.

### C. Read endpoints beyond the basic 4 (~30 endpoints — all missing)

ScrapeCreators is missing essentially every read endpoint beyond `profile`/`user-tweets`/`tweet`:

- `tweet_advanced_search` — keyword/operator search across all tweets
- `search_user` — search users by keyword
- `get_tweet_replies_v2` — tweet replies (V2 with sort by Relevance/Latest/Likes)
- `get_tweet_reply` — tweet replies (V1)
- `get_tweet_quote` — quote tweets
- `get_tweet_retweeter` — retweeters list
- `get_tweet_thread_context` — full thread reconstruction
- `get_article` — long-form articles attached to tweets
- `get_user_mention` — tweets mentioning a user
- `get_user_about` — profile about box
- `get_user_followers`, `get_user_followers_ids`, `get_user_followings`, `get_user_verified_followers` — follower/following graphs (no profile metadata / with metadata / IDs only / verified-only)
- `get_list_followers`, `get_list_members`, `list_timeline` — X List reads
- `bookmarks_v2` — logged-in user's bookmarks
- `get_trends` — trends by WOEID
- `get_space_detail` — Twitter Spaces
- `get_community_members`, `get_community_moderators` — community member lists
- `check_follow_relationship` — does user X follow user Y
- `get_my_info` — own account info (requires login_cookie)
- `user_login_v2` — login (the gating endpoint for write surface)

For pushin-weight-v2's reconciliation use case, the most painful gaps are:

1. **No `tweet_advanced_search`** — we cannot run keyword queries across all X. If our Phase 2 reconciliation ever needs "all tweets mentioning @brand in the last 7 days," twitterapi.io can do it, ScrapeCreators cannot.
2. **No `get_user_followers` / `get_user_followings`** — no follower-graph reads. If we ever need "find verified followers of @brand," ScrapeCreators cannot.
3. **No pagination on user-tweets** — ScrapeCreators docs are explicit that you get 100 tweets max (the top 100 by popularity, not the most recent). twitterapi.io paginates 20/call via cursor.

### D. Bulk / batch endpoints (~5 endpoints — all missing)

- `batch_get_user_by_userids` — 100 user IDs in one call, 10 credits/user (vs 18 single)
- `get_user_followers_ids` — bulk IDs-only, designed for follower-graph collection
- The pattern across twitterapi.io is "use single endpoint at low volume, batch at scale." ScrapeCreators has no batch path, so 1,000 handles = 1,000 credits, no discount.

## Diff: endpoints in ScrapeCreators but NOT in twitterapi.io

**One endpoint:** `GET /v1/twitter/tweet/transcript` — ScrapeCreators returns a transcript for tweets that contain attached video. twitterapi.io does not expose this. If we ever need to ingest video content from X tweets for downstream analysis, ScrapeCreators has a capability twitterapi.io lacks.

This is a small niche — most X data analysis operates on `full_text`, not video transcripts — but worth noting.

## Rate-limit / quota model comparison

| Dimension | ScrapeCreators | TwitterAPI.io |
|---|---|---|
| Vendor-published rate-limit claim | "**No rate limits**" (introduction page) — recommend <500 concurrent | Per-API-key QPS, default ceiling provisioned at account creation; intro page claims 200 QPS |
| Per-account ceiling | Not published (no formal cap) | `/qps-limits` page shows current ceiling (we don't have this snapshot on disk) |
| 429 behaviour | No documented 429 (since "no rate limits") | Yes — intermittent 429s without `Retry-After` per 30-day community research |
| Quota model | Credit pack — 1 credit/req, cache hits free | Credit pack — variable credits/req by endpoint (15-20 user, 20 community, 100 article, $0.002-0.003 for writes) |
| Batch discount | **None** | Yes — 10 vs 18 credits at 100+ batch |
| Free cache | Yes — `cache_max_age` opt-in TTL, 0 credits on hit, always warming | No documented cache layer |
| 402 Payment Required | Yes | (Implicit, but not in our docs) |
| Account-level throttling on official X side | Not documented | Best-practices article: hammering after 429 surfaces as account-level throttle on the official X side |

**For our reconciliation workload**, the practical implication:

- On twitterapi.io, the 1-req/sec throughput we saw was driven by the Python GIL serialising urllib's blocking I/O — not by the API. twitterapi.io's per-endpoint caps can be 200+ QPS if you ask.
- On ScrapeCreators, you could push much higher concurrency (vendor's "500 concurrent requests" guideline). The binding constraint becomes your credit pack burn rate and your HTTP client, not the vendor.
- ScrapeCreators's `cache_max_age=7d` would make our 10,000+ brand-handle reconciliation essentially free on repeat runs — only the first pass costs credits.

## Auth model comparison

| Dimension | ScrapeCreators | TwitterAPI.io |
|---|---|---|
| Header | `x-api-key: <KEY>` | `X-API-Key: <KEY>` |
| Login cookie for writes | **Not required / not supported** | **Required** for any write or "logged-in user" read (bookmarks, my_info) — obtained from `/twitter/user_login_v2` with email + username + password + 2FA secret |
| Write endpoints | None | 18 endpoints gated by login_cookie |
| Surface area for write abuse | Zero | High — login_cookie gives full account control |

ScrapeCreators is safer to give to a third-party agent because it can only read public data. twitterapi.io's login_cookie model means handing the key to an agent gives it write access to the user's X account.

## Pricing model comparison (what we know)

ScrapeCreators publishes "1 credit per request" on every X endpoint. No batch discount. twitterapi.io is variable — `/twitter/user/info` is documented at 18 credits/user (single) and 10 credits/user (100+ batch), writes are $0.002-0.003 USD per call, communities are 20 credits, articles 100 credits, follow-relationship checks 100 credits.

For a 10,000-handle single-pass reconciliation with no batch discount, ScrapeCreators would cost 10,000 credits flat. twitterapi.io would cost ~100,000-180,000 credits (18 single × 10,000, or 100,000 batched). **ScrapeCreators is cheaper per profile read at low volume; the economics flip once you can batch at 100+.**

## Open questions

- Does ScrapeCreators have any unlisted batch endpoint, or is single-call the only path?
- What's the actual QPS we can sustain before ScrapeCreators returns 429 or starts failing? The "no rate limits" claim is marketing copy; the 500-concurrent guideline is the only real number.
- What does the ScrapeCreators `user-tweets` "100 most popular" filter actually look like? If our reconciliation needs recent tweets, we cannot get them from this endpoint at all.
- Does ScrapeCreators support tweet-by-ID lookup, or only by URL? twitterapi.io's `get_tweet_by_ids` takes IDs which is what we usually have on hand; ScrapeCreators appears to require a full URL. Worth verifying with a live probe before any swap.

## Recommendation for pushin-weight-v2

1. **Do not swap.** twitterapi.io covers 63 endpoints vs ScrapeCreators's 6. The Phase 2 reconciliation we already ran used 4-5 read endpoints and could probably have used ScrapeCreators for those, but we'd lose the batch endpoint (`batch_get_user_by_userids`) which is exactly what bulk reconciliation wants.
2. **Consider ScrapeCreators as a fallback / secondary** for transcript extraction (`/v1/twitter/tweet/transcript`) — it's the only capability ScrapeCreators has that twitterapi.io lacks.
3. **Use ScrapeCreators `cache_max_age=7d` if you probe it** — even a one-week cache on profile data would massively reduce credit burn on the residual-apply-style workloads where we re-touch handles.

## Files to read alongside this

- `docs/research/twitterapi_docs/INDEX.md` — the 63-endpoint surface we diffed against.
- `docs/research/twitterapi_docs/rate-limit-ux.md` — the 200 QPS claim, 429 behaviour, and what the 29 dead-lettered handles in Phase 2 probably were.
- `docs/research/twitterapi_docs/endpoint/get_user_by_username.md` — the single user endpoint we used in Phase 2.
- `docs/research/twitterapi_docs/endpoint/batch_get_user_by_userids.md` — the bulk endpoint that gives twitterapi.io its reconciliation economics.
- `.firecrawl/scrapecreators-twitter-profile.md` — the live scrape used for this diff (also `user-tweets`, `tweet`, `tweet/transcript`, `community`, `community/tweets`).
- `.firecrawl/scrapecreators-introduction.md` — "no rate limits" claim and 500-concurrent guideline.
- `.firecrawl/scrapecreators-caching.md` — `cache_max_age` semantics and "always warming" behaviour.
- `.firecrawl/scrapecreators-credit-balance.md` — `credits_remaining` and `credits_charged` in every response.
