# TwexAPI quick trial: historical keyword omissions

**TwexAPI reproduced the observed historical keyword-search gap.** Both July keyword passes returned exactly the same 46 IDs as the archived TwitterAPI query, including 34 of 75 original controls. All five previously investigated missing posts were absent from plain keyword results, but TwexAPI returned all five through both author-filtered search and direct ID lookup.

This is evidence that switching providers did not recover those posts in this sample. It does not prove the two providers share infrastructure, identify X’s internal cause, or establish complete results from either provider.

## Results

| Read | Twex requests | Distinct IDs | Known controls | Outcome |
| --- | --- | --- | --- | --- |
| july31-keyword-p1 | 4 | 46 | 34/75 | no_progress |
| july31-keyword-p2 | 4 | 46 | 34/75 | no_progress |
| july31-five-authors | 2 | 6 | 5/5 targeted missing posts | no_progress |
| aug13-1300-1315-keyword | 5 | 74 | 58/230 | no_progress |

The August query also returned the same 74 IDs as the archived TwitterAPI query for August 13, 13:00–13:15 UTC: Twex-only 0, TwitterAPI-only 0. Two July keyword passes returned identical ID sets. The six author-query results contain all five targeted misses plus one other post.

**Pagination differs:** each of the four search chains reached an empty page whose response still claimed `has_next_page=true` and supplied a new cursor. The trial stopped that chain on zero progress. Therefore all four chains are marked incomplete/no-progress, not provider-exhausted. We did not treat a new cursor as permission to loop through empty pages indefinitely. The historical keyword omission is observed up to this stopping point; exhaustive Twex recall has not been established.

## Exact scenario

July controls are the same 75 own-text DeepSeek posts originally captured near publication, from July 31, 2026, 12:00–12:15 UTC. Bounds are Unix 1785499200–1785500100. The August sample is August 13, 13:00–13:15 UTC, Unix 1786626000–1786626900. These were selected from existing frozen evidence before Twex calls; no new database query was used. Archived TwitterAPI observations and today’s Twex observations were not collected simultaneously.

`july31-keyword-p1`:

```text
(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100
```

`july31-keyword-p2`:

```text
(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1785499200 until_time:1785500100
```

`july31-five-authors`:

```text
(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 (from:viktorg475 OR from:Web3Aible OR from:jhsmith409 OR from:Wizarp_zz OR from:voidfreud) since_time:1785499200 until_time:1785500100
```

`aug13-1300-1315-keyword`:

```text
(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3 since_time:1786626000 until_time:1786626900
```

All search calls used POST `https://api.twexapi.io/twitter/advanced_search/page` with JSON `{"searchTerms":["<complete query above>"],"sortBy":"Latest"}`; subsequent pages add `next_cursor` exactly as returned. No result-limit parameter or extra filters were added. Authentication uses only the literal `TWEXAPI_API_KEY` assignment from the operator’s secret store. Header/key values were not saved.

Direct lookup used POST `/twitter/tweets/lookup`, JSON array:

```json
[
  "2083160778341843345",
  "2083160925813543079",
  "2083161065735532639",
  "2083161164914327965",
  "2083161198011265296"
]
```

All five returned IDs, authors and text match the original frozen control records. Exact UTC timestamps and ID-derived publication times satisfy requested windows; no missing IDs, out-of-window hits or identity conflicts were detected. Only top-level returned post slots count; nested quote/reply objects are not extra search results.

## Trial credits and limits

Balance fell from **20,000 to 19,290 credits: 710 credits used**, or 3.55% of the starting trial. The trial made **18 requests**: 15 search-page requests, one five-ID lookup and two balance reads, all HTTP 200. It took **18.5 seconds**, returned 177 top-level post appearances including repeats/lookup results and saved 781,965 raw bytes. No transport retry, model call or database write occurred.

The [pricing guide](https://docs.twexapi.io/guides/pricing) describes a typical five-credit read. Applied directly to the 177 returned slots that would estimate 885 credits, which differs from the observed 710-credit balance drop. The balance change is the measured account consumption; the reason for the difference is unverified. No per-request charge statement was available in these responses, and no purchase/top-up was made.

Frozen limits: 30 physical requests, at most 3,000 conservatively reserved credits (100 per request), 15 minutes, 32 MiB and ten pages per query. Serial calls, connect/read socket timeouts 10/75 seconds, zero hidden retries. Stop on request/account/capture failure; stop an individual cursor chain on missing/repeated cursor or no progress. Only 1,800 of the conservative credit allowance was reserved by the 18 actual calls; the observed debit was 710.

## Conclusion and retained evidence

The quick trial supplies no evidence of better historical coverage for these matched July and August cases, and exposes a separate empty-page continuation inconsistency. It does not establish Twex’s behavior for long windows, other topics, dates or real-time collection. No app integration, Post import/enrichment, CollectionRun write, schema/configuration, scheduler or deployment change was performed.

The [official search reference](https://docs.twexapi.io/api-reference/search-endpoints/get-data-page-twitter-advanced-search-page-post), [ID lookup reference](https://docs.twexapi.io/api-reference/tweets-endpoints/get-tweets-by-ids-twitter-tweets-lookup-post) and [balance endpoint reference](https://docs.twexapi.io/api-reference/balance-endpoints/get-balance-api-balance-get) were checked October 20. The pricing guide shows `/api/balance` in an example; the endpoint reference and saved OpenAPI agree on `/balance`, which this test used successfully.

Private raw bodies, request/start/hit/cursor ledgers, official OpenAPI snapshot, frozen control/source hashes, full ID comparisons, balance observations and verification receipts remain on fuchitalee at `~/.local/share/render-operations/2026-10-20-twexapi-quick-recall-trial`. Manifest SHA-256: `9c8e22c0e3d4b452da472b3a3b2a1ba37dc3c3fcb55adcc6d79e4abe277b36bf`. All 18 starts/results, saved-body hashes/counts, ID/text mappings and balance observations reconcile.
