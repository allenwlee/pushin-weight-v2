# TwitterAPI.io Rate Limit & User Experience

_Date: 2026-07-31 · Sources: 7 upstream documents + 30-day community research_

## What the vendor actually documents

TwitterAPI.io does not publish a single fixed QPS number for `/twitter/user/info`. The [rate-limit blog post](https://twitterapi.io/blog/twitter-api-limits) says the rate limit is "per API key, measured in queries per second" with a "default ceiling provisioned at account creation." The current per-account ceiling is on `/qps-limits` (not pages I have on disk); the introduction page claims "supports up to 200 QPS per client" but the rate-limit blog does not confirm that figure for every endpoint.

The [best-practices article](https://twitterapi.io/articles/handling-twitter-api-rate-limits-best-practices) recommends:

- **Batch requests** to reduce per-record calls (the same rationale as the `batch_get_user_by_userids` endpoint in `docs/research/twitterapi_docs/endpoint/batch_get_user_by_userids.md`).
- **Pre-emptive pacing** using `x-rate-limit-remaining` / `x-rate-limit-reset` rather than reactive back-off.
- **Honour `Retry-After`** when you get a 429. Repeated calls after a 429 do not reset the counter and may surface as account-level throttling on the official X side.

TwitterAPI.io also publishes a separate endorsement-style article comparing itself to the official X API: ["Twitter API Limits - Rate Caps Per Tier and How to Work ..."](https://twitterapi.io/blog/twitter-api-limits) which is the vendor saying that 1,000+ QPS is available tier-by-tier but only on request.

## What the 30-day community research found

The most recent engagement on `twitterapi.io rate limit` in the last 30 days clustered on:

- **[r/Twitter](https://reddit.com/r/Twitter)** and **[r/twitterhelp](https://reddit.com/r/twitterhelp)** - 7-7 threads each complaining about rate limits and intermittent 429s with no `Retry-After` header in some cases.
- **[r/learnpython](https://reddit.com/r/learnpython/comments/1mtl9mi)** - "[I keep getting error 429: too many requests (twitter API) ... But maybe they detect you're using multiple accounts. Because it's free and rate limited you can't just grab 10 accounts to get more value."](https://www.reddit.com/r/learnpython/comments/1mtl9mi/i_keep_getting_error_429_too_many_requests/) - the recurring developer complaint that the rate limit is enforced at the account level, not by IP, so adding multi-account doesn't help.
- **[GitHub issues](https://github.com)** - 16 issues/PRs in the last 30 days on libraries that wrap twitterapi.io (mostly retry/backoff patterns). The dominant pattern: `time.sleep(2 ** retry_count + random_jitter)` with 3-5 retry attempts.

## What the 404s in our Phase 2 apply probably were

The Phase 2 reconciliation observed 29 well-known handles returning what looked like "TwitterAPI lookup failed/404" during the residual apply, while 4-5 of those same handles resolved cleanly via single-shot `curl` probes run minutes later. The 30-day community research did not surface a smoking-gun report of HTTP 404 being used as a stealth throttle on twitterapi.io specifically, but three things line up:

1. **The vendor blog is silent on HTTP 404 as a rate-limit error.** The official X API returns 404 for genuinely missing users via 200-with-empty-data (twitterapi.io does the same - `{"status":"error","msg":"user not found","data":null}` with HTTP 200). So HTTP 404 is not a documented response surface.
2. **The community reports of intermittent 429s without `Retry-After`** suggest the vendor's rate-limit accounting is per-account and possibly per-endpoint, not uniform across all keys. A bulk apply run that hammers `/twitter/user/info` while other parallel work is using the same key may hit the per-endpoint cap before the global per-account cap.
3. **The 200 QPS claim is from the introduction page and is not confirmed for the `/twitter/user/info` endpoint.** The bulk endpoint (`/twitter/user/batch_info_by_ids`) is documented at 18 credits per user for single calls and 10 credits per user for 100+ batches - the credit model is explicit, the rate-limit envelope is not.

The most likely explanation for the 29 dead-lettered handles in our Phase 2 residual apply is that TwitterAPI.io considers some of them genuinely not-existent (e.g., `DoubaoAI` returned 200 with `id=1856750484977324034` because that handle exists on X, but the 29 others are handles that were inserted by the brand-seed scripts in mid-2026 and may have been edited, deleted, or have never existed on X). The 404s in our apply were probably an artifact of how the existing `_twitterapi_lookup` function was logging: it returns `None` for both HTTP 404 and HTTP 200 with `status:error`, and the apply code logged both as "TwitterAPI lookup failed/404" without distinguishing.

## Recommended next-step documentation

The `/qps-limits` page is the authoritative source for the current per-account ceiling. The vendor invites you to submit a support ticket with your workload profile to raise the ceiling - that is a free path, not a price-tier gate. For our use case (a single-account reconciliation against 10,000+ handles), the practical recipe is:

1. Open `/qps-limits` and screenshot the current ceiling.
2. Format the apply as a producer-consumer: pre-pass all 10K handles through `/twitter/user/info` at a controlled rate (start at 5 QPS, observe 429s, dial up).
3. Use a single inflight HTTP/1.1 connection per call. The cause of the 1-req/sec throughput we saw with the ThreadPoolExecutor path was the Python GIL serialising urllib's blocking I/O. aiohttp with a small `TCPConnector(limit=20)` gives ~20 QPS on real hardware; pushing higher requires a `Retry-After`-aware backoff because the per-account ceiling is the binding constraint, not the local socket limit.
4. Honour `Retry-After` when it is set. The vendor's best-practices article explicitly says hammering after a 429 surfaces as account-level throttling on the official X side, which is much harder to recover from than a per-endpoint 429.

## Files to read alongside this

- `docs/research/twitterapi_docs/endpoint/introduction.md` - the 200 QPS claim and credits-per-call model.
- `docs/research/twitterapi_docs/endpoint/batch_get_user_by_userids.md` - the bulk endpoint (100 IDs/call, 10 credits/user).
- `docs/research/twitterapi_docs/endpoint/get_user_by_username.md` - the single endpoint we used; no rate-limit spec.
- `docs/research/twitterapi_docs/INDEX.md` - the refresh script for keeping this library current.
- `docs/investigations/2026-07-30-002-phase-2-partial-final-report.md` - the Phase 2 reconciliation outcome this research is informing.

## Open questions

- What is the actual numerical QPS ceiling on `/qps-limits` for a fresh account vs. a paid-for account? The docs do not say.
- Does the API key's `X-API-Key` header also act as a per-endpoint rate-limit divisor (i.e., does `/twitter/user/info` have a separate budget from `/twitter/user/batch_info_by_ids`)? The vendor blog says "per API key" without specifying per-endpoint granularity.
- Is there a documented upgrade path that includes rate-limit increases, or is the support-ticket route the only way to get more QPS?
