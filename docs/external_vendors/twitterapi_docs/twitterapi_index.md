# TwitterAPI.io docs (reference library, mirrored 2026-07-30)

Reference copy of <https://docs.twitterapi.io>. Each file is a literal
download of the corresponding upstream `.md` URL — no LLM rewriting, no
extraction. The docs site publishes per-page `.md` URLs specifically for
machine consumption (see `llms.txt` at the upstream root).

`endpoint/get_user_about.md` is the exception: on 2026-08-30 a value-free live
probe proved that the provider's public example omitted six response leaves.
That file is a current project reference combining the public schema with the
observed additions, and records the exact evidence without response values.

**To refresh this library:**

```bash
curl -sSf https://docs.twitterapi.io/llms.txt | grep -oE "(https://docs\.twitterapi\.io/[^\)]+\.md)" | sed "s/\\_/_/g" | sort -u | while read url; do
  curl -sSf -o "endpoint/$(basename "$url")" "$url"
done
```

## Top-level pages

| File | Title | Description |
|---|---|---|
| [introduction.md](introduction.md) | Introduction | API overview and base URL. |
| [authentication.md](authentication.md) | Authentication | Learn how to authenticate your API requests using API keys. |
| [quickstart.md](quickstart.md) | Quickstart | Quickstart guide for getting started. |

## Endpoint reference

All endpoint specs are OpenAPI 3.0.1 YAML in code blocks, prefixed by a one-line
method+path header (e.g. `GET /twitter/tweet/advanced_search`). All require
`ApiKeyAuth` via the `X-API-Key` header.

| File | Title | Description |
|---|---|---|
| [add_user_to_monitor_tweet.md](endpoint/add_user_to_monitor_tweet.md) | Add  a twitter user to monitor his tweets | Add a user to monitor real-time tweets.Monitor tweets from specified accounts, including directly sent tweets, quoted tweets, reply tweets, and retweeted tweets. Please ref:https:/ |
| [add_webhook_rule.md](endpoint/add_webhook_rule.md) | Add Webhook/Websocket Tweet Filter Rule | Add a tweet filter rule. Default rule is not activated.You must call update_rule to activate the rule. |
| [authentication.md](endpoint/authentication.md) | Authentication | Learn how to authenticate your API requests using API keys |
| [batch_get_user_by_userids.md](endpoint/batch_get_user_by_userids.md) | Batch Get User Info By UserIds | Batch get user info by user ids. Pricing: |
| [bookmark_tweet_v2.md](endpoint/bookmark_tweet_v2.md) | Bookmark Tweet | Bookmark a tweet. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.002 per call. |
| [bookmarks_v2.md](endpoint/bookmarks_v2.md) | Get Bookmarks | Get the bookmarks list of the logged-in user. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Returns tweets in the same format as other tw |
| [check_follow_relationship.md](endpoint/check_follow_relationship.md) | Check Follow Relationship | Check if the user is following/followed by the target user. Trial operation price: 100 credits per call. |
| [create_community_v2.md](endpoint/create_community_v2.md) | Create Community V2 | Create a community.You must set the login_cookies.You can get the login_cookies from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [create_tweet_v2.md](endpoint/create_tweet_v2.md) | Create/Reply tweet v2 | Create a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [delete_community_v2.md](endpoint/delete_community_v2.md) | Delete Community V2 | Delete a community.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [delete_tweet_v2.md](endpoint/delete_tweet_v2.md) | Delete Tweet | Delete a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [delete_webhook_rule.md](endpoint/delete_webhook_rule.md) | Delete Webhook/Websocket Tweet Filter Rule | Delete a tweet filter rule. You must set all parameters. |
| [follow_user_v2.md](endpoint/follow_user_v2.md) | Follow User | Follow a user.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [get_all_community_tweets.md](endpoint/get_all_community_tweets.md) | Search Tweets From All Community  | get tweets from all communities,each page returns up to 20 tweets. Use cursor for pagination. |
| [get_article.md](endpoint/get_article.md) | Get Article | get article by tweet id. cost 100 credit per article |
| [get_community_by_id.md](endpoint/get_community_by_id.md) | Get Community Info By Id | Get community info by community id. Price: 20 credits per call. Note: This API is a bit slow, we are still optimizing it. |
| [get_community_members.md](endpoint/get_community_members.md) | Get Community Members | Get members of a community. Page size is 20. |
| [get_community_moderators.md](endpoint/get_community_moderators.md) | Get Community Moderators | Get moderators of a community. Page size is 20. |
| [get_community_tweets.md](endpoint/get_community_tweets.md) | Get Community Tweets | Get tweets of a community. Page size is 20. Order by creation time desc.  |
| [get_list_followers.md](endpoint/get_list_followers.md) | Get List Followers | Get followers of a list. Page size is 20. |
| [get_list_members.md](endpoint/get_list_members.md) | Get List Members | Get members of a list. Page size is 20. |
| [get_my_info.md](endpoint/get_my_info.md) | Get My Account Info | Get my info |
| [get_space_detail.md](endpoint/get_space_detail.md) | Get Space Detail | Get spaces detail by space id |
| [get_trends.md](endpoint/get_trends.md) | Get Trends | Get trends by woeid |
| [get_tweet_by_ids.md](endpoint/get_tweet_by_ids.md) | Get Tweets by IDs | get tweet by tweet ids |
| [get_tweet_quote.md](endpoint/get_tweet_quote.md) | Get Tweet Quotations | get tweet quotes by tweet id.Each page returns exactly 20 quotes. Use cursor for pagination. Order by quote time desc |
| [get_tweet_replies_v2.md](endpoint/get_tweet_replies_v2.md) | Get Tweet Replies V2 | Get tweet replies by tweet id (V2). Each page returns up to 20 replies. Use cursor for pagination. Supports sorting by Relevance, Latest, or Likes. |
| [get_tweet_reply.md](endpoint/get_tweet_reply.md) | Get Tweet Replies | get tweet replies by tweet id.Each page returns up to 20 replies(Sometimes less than 20,because we will filter out ads or other not  tweets). Use cursor for pagination. Order by re |
| [get_tweet_retweeter.md](endpoint/get_tweet_retweeter.md) | Get Tweet Retweeters | get tweet retweeters by tweet id.Each page returns about 100 retweeters. Use cursor for pagination. Order by retweet time desc |
| [get_tweet_thread_context.md](endpoint/get_tweet_thread_context.md) | Get Tweet Thread Context | Get the thread context of a tweet.Suppose a tweet thread consists of t1, t2 (replying to t1), t3 (replying to t2), and t4, t5, t6 (all replying to t3). If we provide an API where y |
| [get_user_about.md](endpoint/get_user_about.md) | Get User Profile About | Strict live-verified success schema, including conditional identity-label rich text and unavailable-account variants omitted from the public example. |
| [get_user_by_username.md](endpoint/get_user_by_username.md) | Get User Info | Get user info by screen name |
| [get_user_followers_ids.md](endpoint/get_user_followers_ids.md) | Get User Followers IDs (Bulk) | Get a user's follower IDs in bulk — **lightweight, IDs only, no profile metadata**. Designed for large-scale follower-graph collection where you join IDs against your own data ware |
| [get_user_followers.md](endpoint/get_user_followers.md) | Get User Followers | Get user followers (with full profile metadata) in reverse chronological order (newest first). Sorted by follow date — most recent followers appear on the first page. Use `cursor`  |
| [get_user_followings.md](endpoint/get_user_followings.md) | Get User Followings | Get user followings (with full profile metadata). Sorted by follow date — most recent followings appear on the first page. Use `cursor` for pagination. |
| [get_user_last_tweets.md](endpoint/get_user_last_tweets.md) | Get User Last Tweets | Retrieve tweets by user name.Sort by created_at. Results are paginated, with each page returning up to 20 tweets.If you only need to fetch the latest tweets from a single user very |
| [get_user_mention.md](endpoint/get_user_mention.md) | Get User Mentions | get tweet mentions by user screen name.Each page returns exactly 20 mentions. Use cursor for pagination. Order by mention time desc |
| [get_user_timeline.md](endpoint/get_user_timeline.md) | Get User TimeLine | Retrieve tweets by user id.Sort by created_at. Results are paginated, with each page returning up to 20 tweets.The content you see is in the same order as the tweets on the user's  |
| [get_user_to_monitor_tweet.md](endpoint/get_user_to_monitor_tweet.md) | Get Users to Monitor Tweet | Get the list of users being monitored for real-time tweets. Returns all users that have been added for tweet monitoring. Please ref:https://twitterapi.io/twitter-stream |
| [get_user_verified_followers.md](endpoint/get_user_verified_followers.md) | Get User Verified Followers | Get user verified followers in reverse chronological order (newest first). Returns exactly 20 verified followers per page, sorted by follow date. Most recent followers appear on th |
| [get_webhook_rules.md](endpoint/get_webhook_rules.md) | Get ALL test Webhook/Websocket Tweet Filter Rules | Get all tweet filter rules.Rule can be used in webhook and websocket.You can also modify the rule in our web page. |
| [introduction.md](endpoint/introduction.md) | Introduction | twitterapi.io docs.The best third-party Twitter API: reliable, high-performance, supports high QPS, and cost-effective. |
| [join_community_v2.md](endpoint/join_community_v2.md) | Join Community v2 | Join a community.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [leave_community_v2.md](endpoint/leave_community_v2.md) | Leave Community V2  | Leave a community.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [like_tweet_v2.md](endpoint/like_tweet_v2.md) | Like Tweet | Like a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [list_timeline.md](endpoint/list_timeline.md) | Get List Tweet TimeLine | Get timeline tweets  from list. Use cursor for pagination. |
| [remove_user_to_monitor_tweet.md](endpoint/remove_user_to_monitor_tweet.md) | Remove a user from  monitor list | Remove a user from monitor real-time tweets.Please ref:https://twitterapi.io/twitter-stream |
| [retweet_tweet_v2.md](endpoint/retweet_tweet_v2.md) | Retweet Tweet  | Retweet a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [search_user.md](endpoint/search_user.md) | Search user by keyword | Search user by keyword |
| [send_dm_v2.md](endpoint/send_dm_v2.md) | Send DM V2 | Send a direct message to a user.You must set the login_cookie..You can get the login_cookie from /twitter/user_login_v2.You can only send DMs to those who have enabled DMs. Sometim |
| [tweet_advanced_search.md](endpoint/tweet_advanced_search.md) | Advanced Search | Advanced search for tweets.Each page returns up to 20 replies(Sometimes less than 20,because we will filter out ads or other not  tweets).    |
| [unbookmark_tweet_v2.md](endpoint/unbookmark_tweet_v2.md) | Unbookmark Tweet | Remove a tweet from bookmarks. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.002 per call. |
| [unfollow_user_v2.md](endpoint/unfollow_user_v2.md) | Unfollow User | Unfollow a user.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [unlike_tweet_v2.md](endpoint/unlike_tweet_v2.md) | Unlike Tweet | Unlike a tweet.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.002 per call.  |
| [update_avatar_v2.md](endpoint/update_avatar_v2.md) | Update Avatar | Update your Twitter avatar/profile picture. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.003 per call. |
| [update_banner_v2.md](endpoint/update_banner_v2.md) | Update Banner | Update your Twitter banner/header image. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.003 per call. |
| [update_profile_v2.md](endpoint/update_profile_v2.md) | Update Profile | Update your Twitter profile information. You must set the login_cookie. You can get the login_cookie from /twitter/user_login_v2. Trial operation price: $0.003 per call. |
| [update_webhook_rule.md](endpoint/update_webhook_rule.md) | Update Webhook/Websocket Tweet Filter Rule | Update a tweet filter rule. You must set all parameters. |
| [upload_media_v2.md](endpoint/upload_media_v2.md) | Upload media | Upload media to twitter.You must set the login_cookie.You can get the login_cookie from /twitter/user_login_v2.Trial operation price: $0.003 per call.  |
| [user_login_v2.md](endpoint/user_login_v2.md) | Log in | Log in directly using your email, username, password, and 2FA secret key. And obtain the Login_cookie,  to post tweets, etc. Please note that the Login_cookie obtained through logi |

## Supplementary research

Local-scope notes this project's agents have added, not from the upstream docs site:

| File | Title | Description |
|---|---|---|
| [rate-limit-ux.md](rate-limit-ux.md) | Rate Limit & User Experience | What the docs actually say about QPS, what 30-day community research found, and what the 29 dead-lettered handles in Phase 2 reconciliation likely were. |


## Pricing (scraped 2026-08-06 from https://twitterapi.io/pricing)

**Source:** `https://twitterapi.io/pricing` (scraped 2026-08-06 via Firecrawl). Reproduce with:
```bash
firecrawl scrape "https://twitterapi.io/pricing" -o .firecrawl/twitterapi-pricing.md
```

### Per-result rates (the canonical pricing model)

| Resource unit | Rate | Notes |
|---|---|---|
| **Tweets** | **15 credits / returned tweet** | `$0.15 per 1K tweets`. Applies to `/twitter/tweet/advanced_search`, `/twitter/tweet/quotes`, `/twitter/tweet/replies`, `/twitter/tweet/retweeter`, `/twitter/tweet/thread_context`, `/twitter/tweet/by_ids`, `/twitter/tweet/last_tweets`, `/twitter/tweet/timeline`, `/twitter/list/timeline`, `/twitter/user/mention`, etc. |
| **Profiles** | **18 credits / returned profile** | `$0.18 per 1K users`. Applies to `/twitter/user/by_username`, `/twitter/user/batch_by_userids`, `/twitter/user/me`. |
| **Followers / Following** | **Tiered, per returned item** | See table below. |
| **Follower IDs** | **Tiered, per returned ID** | See table below. |

### Tiered pricing (followers / following / follower IDs)

Volume discount — the more items per call, the cheaper each one gets.

| Endpoint | Page size | Credits / item |
|---|---|---|
| `/twitter/user/followers` / `/twitter/user/followings` | 20–99 returned | 3 credits each |
| `/twitter/user/followers` / `/twitter/user/followings` | 100–199 returned | 2 credits each |
| `/twitter/user/followers` / `/twitter/user/followings` | 200 returned (max) | 1 credit each |
| `/twitter/user/followers_ids` | 50–199 returned | 2 credits / ID |
| `/twitter/user/followers_ids` | 200–3,999 returned | 1 credit / ID |
| `/twitter/user/followers_ids` | 4,000–5,000 returned | 0.45 credits / ID |

### Per-call floors and special cases

| Rule | Cost |
|---|---|
| **Minimum per call** | 15 credits (waived for bulk data responses) |
| List function calls (effective 2026-10-01) | 150 credits ($0.0015) per call |
| Login V2 | free |
| Tweet create / reply / quote (`v2`) | 300 credits ($0.003) per call |
| Like / retweet / bookmark / follow (`v2`) | 200 credits ($0.002) per call |
| Get article | 100 credits per article |
| Get community info | 20 credits per call |
| Community member / moderator / tweet lists | 20 credits per page |

### Currency

1 USD = 100,000 credits.

### Worked examples (from the pricing page)

- API returns 4 tweets → 60 credits charged
- API returns 2 tweets → 30 credits charged
- API returns 0 or 1 tweet → 15 credits charged (the floor)
- Fetch 200 followers in one call → 200 credits (1 each)
- Fetch 5,000 follower IDs in one call → 2,250 credits (0.45 each)

### Recharge / subscription terms

- Pay-as-you-go, no minimum spend
- Recharged credits never expire
- Bonus credits included with every recharge
- Bonus credits valid for 30 days
- Higher recharge amounts get bigger discounts (up to 5% off)
- Subscription adds monthly credit return on top of per-call rates

### Implication for the x-monitor harvester

The local budget guard in `x_monitor/run.py:959` uses `_CREDITS_PER_ADVANCED_SEARCH_PAGE = 300` — a flat per-page estimate. The actual TwitterAPI.io rate is **15 credits per returned tweet**. The discrepancy matters at scale:

- Per cycle (7 calls × up to 50 tweets each × 15 credits) = **up to 5,250 credits/cycle**
- 96 cycles/day = **up to 504,000 credits/day** (~$7.56/day at the per-tweet rate)
- The `daily_ceiling: 333` in `config.yaml:65` is a stale placeholder; nothing in the codebase enforces it.
- The `_BUDGET_HARD_CAP_CREDITS = 2_000_000` per-cycle guard in `x_monitor/run.py:958` is a single-run limit, not a daily cap.

If you hit HTTP 402 `Credits is not enough. Please recharge.` on the cron, you've exhausted the monthly TwitterAPI.io allotment — top up via `https://twitterapi.io/payment`.

### Related

- `docs/reference/twitterapi-io-calls.md` — operator-facing reference doc on the harvester's call sites. The "300 credits per page" claim there is WRONG per the live pricing model; the doc needs a refresh.
- `x_monitor/run.py:958-978` — the `x_monitor/run.py` budget guard. The `_CREDITS_PER_ADVANCED_SEARCH_PAGE = 300` constant is the source of the drift.
- `x_monitor/apify.py` — the `TwitterApiClient` that dispatches every API call. No per-call credit tracking is currently logged.

---

## Dashboard backend API (undocumented — discovered 2026-08-06)

The TwitterAPI.io dashboard at `https://twitterapi.io/dashboard` is powered by a **separate, undocumented API** under `https://api.twitterapi.io/backend/user/*` that is NOT in the public OpenAPI spec (`https://docs.twitterapi.io/api-reference/openapi.json`). It is reverse-engineered from the Next.js JS bundles the dashboard loads — specifically `/_next/static/chunks/5377-*.js`.

**Discovery source:** `/tmp/.firecrawl/bundle-5377.js` (downloaded 2026-08-06 from the live dashboard HTML). URLs were extracted by grepping all `/_next/static/chunks/*.js` files referenced from `https://twitterapi.io/dashboard` for `fetch(` calls. Refresh by re-running the same grep.

**Auth:** All `/backend/user/*` endpoints require `Authorization: Bearer <session.accessToken>` (NextAuth session token, NOT your X-API-Key). The session token is short-lived (~24h); grab it from a logged-in browser via DevTools → Network → any `/backend/user/*` request → request headers, or automate the NextAuth login flow (`api/auth/signin` + `api/auth/callback/credentials`).

### Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/backend/user/api_calls` | GET | **The "Recent API Calls" table source.** Paginated call log. |
| `/backend/user/consumption_by_endpoint` | GET | Aggregated usage by endpoint. Query: `?days=30&top_n=15` |
| `/backend/user/consumption_summary` | GET | 1d / 7d / 30d window stats |
| `/backend/user/info` | GET | Account info (different from `/oapi/my/info`) |
| `/backend/user/rotate_api_key` | POST | Rotate your API key |
| `/stripe/create_portal_session` | POST | Stripe customer portal link |

### `/backend/user/api_calls` — full spec

This is the endpoint the dashboard's "Recent API Calls" table fetches. 90-day server-side retention.

```
GET https://api.twitterapi.io/backend/user/api_calls?limit=50&cursor=<opaque>
Authorization: Bearer <session.accessToken>
```

**Query params:**
- `limit` — page size. Dashboard uses 50. No documented max.
- `cursor` — opaque pagination cursor. Omit on first request; pass `response.data.next_cursor` on subsequent requests. Loop until `next_cursor` is null/empty.

**Response (200):**
```json
{
  "status": "success",
  "data": {
    "calls": [
      {
        "id": "<string>",
        "trace_id": "<string>",
        "endpoint_path": "/twitter/tweet/advanced_search",
        "method": "GET",
        "http_status": 200,
        "credits_consumed": 15,
        "data_items_count": 20,
        "request_time_ms": 412,
        "time_cost_ms": 387,
        "request_summary": "<string>",
        "response_summary": "<string>",
        "created_at": "<iso8601>"
      }
    ],
    "next_cursor": "<opaque string or null>",
    "data_source": "mysql",
    "retention_days": 90
  }
}
```

**Field-to-table-column mapping** (matches the dashboard table headers):
| JSON field | Dashboard column |
|---|---|
| `endpoint_path` | Endpoint |
| `method` | Method |
| `http_status` | Status |
| `credits_consumed` | Credits |
| `data_items_count` | Data Count |
| `request_time_ms` (or `time_cost_ms`) | Latency |
| `created_at` | Time (UTC+9) |

**Caveat:** The dashboard bundle includes the string `"Method, status, and request/response previews are temporarily unavailable. Full details will r..."` — so `request_summary` and `response_summary` may be redacted in responses. The other fields are populated.

### Pagination behavior

Cursor-based, server-side capped at 90 days retention. For a heavy account (~50k calls over 90 days) at `limit=50`, expect ~1000 page requests. Add a polite `time.sleep(0.3)` between requests.

### `/backend/user/consumption_summary` response shape

```json
{
  "status": "success",
  "data": {
    "window_1d":  { "api_calls_count": N, "credits_consumed": N },
    "window_7d":  { "api_calls_count": N, "credits_consumed": N },
    "window_30d": { "api_calls_count": N, "credits_consumed": N },
    "by_endpoint": [
      { "endpoint_path": "...", "api_calls_count": N, "credits_consumed": N }
    ]
  }
}
```

`/backend/user/consumption_by_endpoint?days=30&top_n=15` returns the same `by_endpoint` shape.

### Use cases for x-monitor

1. **Audit / reconciliation.** Periodically diff the dashboard's `/backend/user/api_calls` against our own application-layer call log to catch drift, missing calls, or unexpected endpoint usage.
2. **Cost reporting.** Pull `/backend/user/consumption_summary` and `/backend/user/consumption_by_endpoint` for monthly cost dashboards without instrumenting the application.
3. **Historical backfill (within 90 days).** Reconstruct usage patterns from the vendor's own log.

### Caveats

- **Undocumented.** Vendor can change paths, field names, auth scheme, or rate limits without notice. Pin to a specific bundle hash if you depend on this.
- **Session token expires.** ~24h lifetime; needs a refresh flow.
- **90-day hard cap.** Older data is gone. Vendor retention is opaque but the dashboard literally tells you `retention_days: 90`.
- **No CSV endpoint.** Convert the JSON yourself; field names map 1:1 to the dashboard table columns.
- **Don't use as system of record.** Application-layer logging (`x_monitor/apify.py` / `x_monitor/run.py`) should remain the source of truth for x-monitor's own analytics. The dashboard API is for vendor-side reconciliation.

### Re-discovery recipe

To re-verify or re-discover these endpoints after a vendor update:

```bash
# Get JS bundle URLs from dashboard HTML
curl -sSf https://twitterapi.io/dashboard | grep -oE 'src="[^"]+\.js"' | sed 's/src="//;s/"$//'

# Grep all bundles for fetch() calls to backend paths
for js in $(curl -sSf https://twitterapi.io/dashboard | grep -oE 'src="[^"]+\.js"' | sed 's/src="//;s/"$//'); do
  curl -sSf "https://twitterapi.io$js" | grep -oE 'fetch\("[^"]+"|"/backend/[^"]+"'
done | sort -u
```
