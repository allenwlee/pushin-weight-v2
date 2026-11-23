# Recent DeepSeek search: fifteen-minute versus five-minute windows

**Fully paginated recent searches returned exactly the same 111 IDs at both resolutions, in both passes.** One fifteen-minute query took seven requests per pass; three adjacent five-minute queries took ten. In this sample, smaller windows added 42.9% more requests and no additional posts.

The initial-page comparison differs: the fifteen-minute query exposed 20 IDs, while the three five-minute queries exposed 60. The 60 contain all of the original 20 plus 40 others. This is a first-page/deferred-work difference, not evidence that the fully paginated fifteen-minute search omitted those 40 posts.

## Results

| Window | Pass | Queries exhausted | Physical calls | Raw slots | Distinct IDs | Initial-page distinct IDs | Estimated search USD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 15 minutes | 1 | 1/1 | 7 | 111 | 111 | 20 | $0.016800 |
| 15 minutes | 2 | 1/1 | 7 | 111 | 111 | 20 | $0.016800 |
| 5 minutes | 1 | 3/3 | 10 | 111 | 111 | 60 | $0.017100 |
| 5 minutes | 2 | 3/3 | 10 | 111 | 111 | 60 | $0.017100 |

Both directions of the fully paginated difference are empty: five-minute-only IDs = 0, fifteen-minute-only IDs = 0. Repeated passes also have zero ID differences. The observed union contains 111 IDs, but it is not an independent inventory of all matching public X posts.

## Method and timing

The frozen publication window is **October 20, 2026, 07:25–07:40 UTC** (16:25–16:40 JST). Freeze selected the most recently closed five-minute UTC boundary, then the preceding fifteen minutes, before seeing any new response. Searches started at 2026-10-20T07:42:58.022653+00:00 and ended at 2026-10-20T07:43:10.457905+00:00. At the first request, the publication-window end was about three minutes old; this is a recent-window comparison, not simultaneous collection at each post’s publication time.

Exact unchanged base query: `(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3`. GET `/twitter/tweet/advanced_search`, `queryType=Latest`, inline Unix time bounds, no unsupported `limit`, exact previous cursor after page one. Requested bounds are half-open. Two interleaved passes compare one fifteen-minute query with three adjacent five-minute queries; narrow-slice order is reversed in the second pass. Maximum four requests run concurrently. No additional language, engagement or author restriction was introduced.

| Resolution | Pass | Slice | Start epoch | End epoch |
| --- | --- | --- | --- | --- |
| 15 | 1 | 0 | 1792481100 | 1792482000 |
| 5 | 1 | 0 | 1792481100 | 1792481400 |
| 5 | 1 | 1 | 1792481400 | 1792481700 |
| 5 | 1 | 2 | 1792481700 | 1792482000 |
| 15 | 2 | 0 | 1792481100 | 1792482000 |
| 5 | 2 | 2 | 1792481700 | 1792482000 |
| 5 | 2 | 1 | 1792481400 | 1792481700 |
| 5 | 2 | 0 | 1792481100 | 1792481400 |

Each cursor chain was fully paginated to an explicit `has_next_page=false`. No cap, timeout, retry, malformed record, missing ID or out-of-window timestamp occurred. Native-ID publication times agree with provider timestamps, and text/author/time identities agree across all appearances. All 34 raw response bodies, request starts/results, slot counts, cursor links and SHA-256 hashes reconcile. Raw appearances: 444; distinct observed IDs: 111; repeated appearances: 333.

The diagnostic reuses the existing application TwitterApiClient transport and explicit on-demand credential resolver from worktree revision `0e0fa643`. It directly tests the provider endpoint and does not execute Django ingestion, alter scheduled cursors or certify accepted/stored/enriched Post counts. The live harvester was previously observed at `64b95c26`; its initial-page/backlog behavior was inspected from that deployed revision. No claim is made that the diagnostic executes its complete current call chain.

## Resources and interpretation

Total **34 successful HTTP requests**, **12.44 seconds**, **$0.0678 estimated**, 1,843,002 captured bytes. Zero failures, retries, unknown charge allowances, model calls, ID lookups or database queries/writes. Only the TwitterAPI on-demand key was used. No scheduled-service, key/configuration, app/schema, cron, import, enrichment, CollectionRun or deployment change occurred.

Frozen ceilings were 160 physical requests including any explicit retries, $0.75 estimated, 30 minutes, 64 MiB and 100 pages per exact query. Four workers, connect/read socket timeouts 10/75 seconds, zero hidden retries and at most two attempts per page. Admission reserves in-flight calls and charges; its previously verified guard logic was reused. No ceiling was reached or extended.

The [August study](2026-10-20-163017-august13-five-minute-window-comparison.md) showed a historical recovery benefit from smaller windows; this recent sample did not. It is one DeepSeek publication window, not a representative multi-brand/live reliability study. Fast-repeat stability reduces observed timing drift but does not rule out indexing delays or posts missing from both methods. This test does not measure polling every five minutes, end-to-end scheduled backlog completion, or absolute X recall.

There is no measured recent full-pagination gain here to justify shortening all live queries. The separate initial-page result supports checking whether the scheduled harvester actually finishes its deferred coverage. If it does, the observed difference disappears after paging. If it does not, more initial slices or better backlog draining could matter; that is a separate implementation decision requiring its own evidence. Do not change the cron from this single experiment.

Search estimates use [TwitterAPI pricing](https://twitterapi.io/pricing): $0.00015 per returned slot including repeats, and the empty-request floor. Fifteen-minute searches cost $0.0168 per pass; five-minute searches cost $0.0171. More requests do not mean proportionally greater result-based charges in this sample. These are estimates, not invoices.

## Could the official X developer API behave differently?

**Yes, a different result is plausible and worth measuring; better recall is not established.** The [official full-archive API](https://docs.x.com/x-api/posts/search/introduction) exposes `/2/tweets/search/all` over the historical archive back to 2006. This is a documented developer retrieval interface; the sources reviewed do not establish that its underlying index is independent of X web search or promise that the specific suppressed posts in our sample are included.

The [endpoint reference](https://docs.x.com/x-api/posts/search-all-posts) supports explicit `start_time` / `end_time`, up to 500 results per page, `next_token` pagination and `sort_order=recency`. These features allow a paginated historical range to be tested directly rather than assuming that minute-sized web-style queries are necessary. Five hundred is a per-page ceiling, not the total result limit or proof of exhaustive coverage. Query/operator syntax must be mapped to the official API rather than forwarding the scraper query unchanged.

One correction to a broad ranking explanation: X says its [Latest web search](https://help.x.com/en/resources/recommender-systems/search-recommendations) bypasses popularity ranking but still applies global visibility filtering, including account-level restrictions. Our probes used Latest. Thus popularity ranking is not an established explanation for our omissions. The same documentation does not prove that full-archive developer search bypasses those exclusions. Deleted/unavailable material and historical indexing gaps cannot be assumed recoverable merely because the endpoint is called full archive.

My inference is that official full-archive search is a more useful independent comparison than trying another similar scraper, because it tests a different documented retrieval interface. It is not a claim of an independent data source or a guaranteed fix. The clean next comparison is the same July 31 fifteen-minute window with 75 frozen known controls, especially the five misses that Twex and TwitterAPI can retrieve by ID/author but omit from ordinary keyword search. Fully page the keyword search, record exact syntax differences, then compare known IDs, both-direction differences and direct-ID availability. No official API request was made or authorized by the documentation question.

Current [X API pricing](https://docs.x.com/x-api/getting-started/pricing), checked October 20, lists $0.005 per Post read: about $5 for 1,000 Posts before other resource charges. It also describes same-UTC-day resource deduplication as a soft guarantee and a three-million-Post monthly read ceiling on pay-per-use. A small controlled test could be inexpensive; a whole-month import needs its own volume and spending calculation. We did not purchase credits, inspect an official bearer token or change any account settings.

## Evidence

Private artifacts on fuchitalee: `~/.local/share/render-operations/2026-10-20-recent-fifteen-vs-five-minute-comparison`. Frozen manifest SHA-256: `39b4369f517b405c51505c0becc264da629af5481b42a161987e9b6ead921fd7`. Retains exact raw bodies, request/start/hit/cursor ledgers, source/input verification, per-method and repeat ID sets, cost/timing and final verification. Reference docs were checked on October 20. Application code and prior diagnostic evidence were preserved.
