# August 13 historical search: 1-hour, 15-minute and 10-minute windows

**Shorter windows substantially improved recovery in this busy August sample.** Per pass, hourly searches found 232 known posts; 15-minute searches found 502 (116.4% more), and 10-minute searches found 588 (17.1% more than 15 minutes). The fixed benchmark contains 1,757 previously collected posts. All 66 query chains ended normally.

Both interleaved passes returned the identical native-ID sets for every hour/window-size comparison.

This is a controlled comparison of the same three busy hours, 12:00–15:00 UTC on August 13, 2026. Each method was run twice in interleaved passes. It measures returned IDs and recovery of previously collected known posts; it does not insert or enrich application Posts.

Search completion: 66/66 exact query chains ended normally. Methods with incomplete constituent queries are not eligible for a definitive coverage comparison.

## Aggregate results across the three hours

| Window | Pass | Search calls | Distinct raw IDs | Known posts recovered | Available matching controls recovered | Queries exhausted | Estimated search USD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 60m | 1 | 21 | 294 | 232/1,757 | 232/1,637 | 3/3 | 0.044550 |
| 60m | 2 | 20 | 294 | 232/1,757 | 232/1,637 | 3/3 | 0.044550 |
| 15m | 1 | 51 | 651 | 502/1,757 | 502/1,637 | 12/12 | 0.099450 |
| 15m | 2 | 51 | 651 | 502/1,757 | 502/1,637 | 12/12 | 0.099450 |
| 10m | 1 | 65 | 756 | 588/1,757 | 588/1,637 | 18/18 | 0.116100 |
| 10m | 2 | 65 | 756 | 588/1,757 | 588/1,637 | 18/18 | 0.116100 |

## Results by publication hour

| Hour UTC | Window | Calls pass1/pass2 | Distinct IDs pass1/pass2 | Known posts pass1/pass2 | Controls | Queries exhausted pass1/pass2 |
| --- | --- | --- | --- | --- | --- | --- |
| 12:00Z | 60m | 6 / 6 | 83 / 83 | 66 / 66 | 489 | 1/1 / 1/1 |
| 12:00Z | 15m | 17 / 17 | 207 / 207 | 160 / 160 | 489 | 4/4 / 4/4 |
| 12:00Z | 10m | 20 / 20 | 227 / 227 | 175 / 175 | 489 | 6/6 / 6/6 |
| 13:00Z | 60m | 7 / 7 | 106 / 106 | 88 / 88 | 725 | 1/1 / 1/1 |
| 13:00Z | 15m | 18 / 18 | 230 / 230 | 183 / 183 | 725 | 4/4 / 4/4 |
| 13:00Z | 10m | 23 / 23 | 286 / 286 | 235 / 235 | 725 | 6/6 / 6/6 |
| 14:00Z | 60m | 8 / 7 | 105 / 105 | 78 / 78 | 543 | 1/1 / 1/1 |
| 14:00Z | 15m | 16 / 16 | 214 / 214 | 159 / 159 | 543 | 4/4 / 4/4 |
| 14:00Z | 10m | 22 / 22 | 243 / 243 | 178 / 178 | 543 | 6/6 / 6/6 |

## Paired gains and losses against one-hour search

| Hour UTC | Window | Pass | Additional calls | Narrow-only IDs | Hour-only IDs | Additional known IDs | Known IDs lost | Net known gain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12:00Z | 15m | 1 | 11 | 124 | 0 | 94 | 0 | 94 |
| 12:00Z | 10m | 1 | 14 | 144 | 0 | 109 | 0 | 109 |
| 12:00Z | 15m | 2 | 11 | 124 | 0 | 94 | 0 | 94 |
| 12:00Z | 10m | 2 | 14 | 144 | 0 | 109 | 0 | 109 |
| 13:00Z | 15m | 1 | 11 | 134 | 10 | 104 | 9 | 95 |
| 13:00Z | 10m | 1 | 16 | 184 | 4 | 150 | 3 | 147 |
| 13:00Z | 15m | 2 | 11 | 134 | 10 | 104 | 9 | 95 |
| 13:00Z | 10m | 2 | 16 | 184 | 4 | 150 | 3 | 147 |
| 14:00Z | 15m | 1 | 8 | 112 | 3 | 83 | 2 | 81 |
| 14:00Z | 10m | 1 | 14 | 140 | 2 | 102 | 2 | 100 |
| 14:00Z | 15m | 2 | 9 | 112 | 3 | 83 | 2 | 81 |
| 14:00Z | 10m | 2 | 15 | 140 | 2 | 102 | 2 | 100 |

## Repeat stability

| Hour UTC | Window | Pass1-only IDs | Pass2-only IDs | Overlap / union |
| --- | --- | --- | --- | --- |
| 12:00Z | 60m | 0 | 0 | 1.000000 |
| 12:00Z | 15m | 0 | 0 | 1.000000 |
| 12:00Z | 10m | 0 | 0 | 1.000000 |
| 13:00Z | 60m | 0 | 0 | 1.000000 |
| 13:00Z | 15m | 0 | 0 | 1.000000 |
| 13:00Z | 10m | 0 | 0 | 1.000000 |
| 14:00Z | 60m | 0 | 0 | 1.000000 |
| 14:00Z | 15m | 0 | 0 | 1.000000 |
| 14:00Z | 10m | 0 | 0 | 1.000000 |

## Ten minutes compared directly with fifteen

| Hour UTC | Pass | Additional calls | Ten-minute-only known IDs | Fifteen-minute-only known IDs | Net known gain |
| --- | --- | --- | --- | --- | --- |
| 12:00Z | 1 | 3 | 19 | 4 | 15 |
| 12:00Z | 2 | 3 | 19 | 4 | 15 |
| 13:00Z | 1 | 5 | 57 | 5 | 52 |
| 13:00Z | 2 | 5 | 57 | 5 | 52 |
| 14:00Z | 1 | 6 | 23 | 4 | 19 |
| 14:00Z | 2 | 6 | 23 | 4 | 19 |

A smaller window is not necessarily a strict superset. The paired lists retain both gains and losses. Using both resolutions can recover their union but repeats much of the acquisition cost; compare the marginal unique gain before adopting that as a default.

## Selection, method and execution

Before any new provider result, the frozen selection rule chose the August day with the most stored own-text DeepSeek posts first collected on their publication day, then its three busiest UTC hours. August 13 had 6,154 such controls: 489 in 12:00–13:00 UTC, 725 in 13:00–14:00, and 543 in 14:00–15:00, totaling 1,757. These deliberately busy samples are useful for depth-limit stress testing and are not representative of every hour, brand, or month.

Exact unchanged base query: `(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3`. Send `queryType=Latest`, inline `since_time:<epoch> until_time:<epoch>`, and the previous exact cursor after page one. No unsupported `limit` parameter. For every chosen hour, compare one 60-minute query, four 15-minute queries or six 10-minute queries over the identical full-hour union. Two passes use 18 rotated lanes; each lane completes a slice before its next slice. Initial calls were serial; after two transport failures, the independent continuation used at most 4 concurrent HTTP requests, rotating across lanes. No author filter was added.

| UTC hour start | Start epoch | End epoch |
| --- | --- | --- |
| 2026-08-13T12:00Z | 1786622400 | 1786626000 |
| 2026-08-13T13:00Z | 1786626000 | 1786629600 |
| 2026-08-13T14:00Z | 1786629600 | 1786633200 |

Execution: 2026-10-20T05:22:48.889699+00:00 to 2026-10-20T05:59:53.496018+00:00. Elapsed 2,224.61 seconds (37.1 minutes). Physical requests 304 = 273 search + 31 lookup; estimated undiscounted USD 0.736650, unknown-charge allowance USD 0.009000. Estimate is based on each returned slot, including duplicates, and the empty-call floor; it is not a vendor invoice.

Limits were 600 physical calls, USD 2 estimated spend and 128 MiB of captured response bodies. Within that budget, search was limited to 560 calls / USD 1.70, with 40 calls / USD 0.30 reserved for ID lookups of at most 50 IDs each. The original 20-minute elapsed allowance was increased once to a maximum of 60 minutes from the first start, disclosed to the owner because the responses were slower than expected. Call/spend/capture ceilings, samples, terms, resolutions and two-pass comparison remained fixed. The original manifest and separate amendments are retained.

Three calls failed: one ReadTimeout, one ConnectionError and one ChunkedEncodingError. Each failed logical page was retried once and recovered. There were no hidden transport retries or third attempts. Continuations reused completed pages within each pass; the planned second pass still made independent requests. The unknown-charge allowance for the three uncaptured responses is USD 0.009, separate from the USD 0.73665 estimate for captured results.

The first requests used a 15-second socket timeout. A serial continuation raised it to 45 seconds, then independent work continued with four workers and separate 10-second connection / 75-second read timeouts. A failure could no longer abort all other independent comparisons; twice-failed queries would remain incomplete, and authentication/account/rate failures would stop the run. These harness changes and the later elapsed-time extension were recorded before execution. No query terms, frozen controls or successful page receipts were replaced.

Successful end-to-end request durations had a median of 10.19 seconds, a 95th percentile of 71.07 seconds and a maximum of 131.09 seconds. Socket-read timeouts bound individual waits rather than the whole response duration. Wall time includes 322.9 seconds of stopped-controller repair/transition gaps. The saved per-request timestamps distinguish those gaps from HTTP/capture time. A read-only host check reported healthy network pressure (173 TCP sockets, normal socket pressure and successful HTTPS/local health probes); this does not identify a provider-internal latency cause.

Final stop reason: none. Query outcomes: all 66 provider-exhausted. There were 301 successful HTTP 200 responses and three uncaptured transport failures. All 304 physical starts are retained in the ledger. Original operators, attempt snapshots and amendments remain available.

## Availability and evidence checks

We planned direct ID lookup for all known controls missed by any method/pass, and checked 1538/1538. Current availability/eligibility counts: `{'not_returned_or_unavailable_by_lookup': 120, 'available_matching': 1,637}`. A lookup result is never added to search recovery. For IDs requested by lookup, that later observation takes precedence over a prior search observation. Unavailable/omitted IDs, unknown availability and available-but-unconfirmed eligibility remain separate. Current eligibility requires own-text DeepSeek/深度求索, non-excluded author, the same UTC publication hour and a known nonnegative like count. Null old stored likes are not imputed.

All request starts reconcile with request results. Every captured exact response byte count and SHA-256 matches; every successful top-level hit position, native ID and text matches its saved body. Across the two passes and all three resolutions, 3,402 identified raw search appearances reduce to 788 distinct IDs; 2,614 appearances repeat an already observed search ID. These are cross-method/pass duplicates, not additional Posts. Captured raw search slots 3402; captured raw lookup slots 1443. Failed uncaptured requests have unknown result counts, not zero, and retain separate charge allowances. The first serial harness logged requested_limit=20 as a page-size planning estimate in its first 27 ledger rows; their exact arguments contain no limit parameter, verified for every request. Later rows correctly distinguish provider-default paging from an explicit requested limit. Record issues: `{'missing_id': 25, 'missing_or_unparsed_provider_timestamp': 25}`. Text/author/time identity conflicts: 0. Exact ID sets, additional/lost IDs and availability receipts are retained in results.json and known-positive-availability.json.

## Implication for the next backfill

For this busy DeepSeek sample, 10-minute windows are the stronger primary choice: they recovered 86 more known posts than 15-minute windows, a 17.1% increase, for 65 rather than 51 calls per pass. Estimated search cost across the three hours was USD 0.11610 per pass versus USD 0.09945. Fifteen minutes already provided a major improvement over hourly search: 502 versus 232 known posts, a 116.4% increase. These measurements support shorter windows for this busy route; they do not establish a universal default for every brand or quiet hour.

The 10-minute set gained 99 known posts absent from the 15-minute set, while losing 13 that 15-minute searches found. Their union recovered 601 known posts. Running both would restore those 13 but repeat much of the search cost. Additional recovery from relevant known authors remains a separate, untested stage in this experiment.

Even the best single resolution found only 588 of the 1,637 currently available matching controls (35.9%); 1,049 remained absent from its keyword results. Smaller windows substantially improved coverage without making keyword search complete. The 120 controls omitted or unavailable through ID lookup were excluded from the available-matching denominator, without assigning a deletion or suspension cause.

Lookup returned 1,443 top-level slots: 1,418 identified posts plus 25 blank-identity placeholders. Requests and results were matched by native ID, not array position. These lookups check availability; they do not count as additional search recovery.

## Interpretation limits

Provider-ended pagination establishes the end of that exact query, not exhaustive X coverage. A method can gain some IDs while losing others. Recovery is measured against the frozen 1,757 known positives, not an estimated daily volume or an all-X census. Different repeated sets indicate observed instability rather than automatically proving a backend cause. These samples do not establish an optimal window size for every route. No model, production/domain/collection database write, import, deployment, schedule or service change occurred; the cleared acquisition goal was not restarted.

## Sources and retained artifacts

[Advanced-search parameters](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search), [ID lookup and 50-ID maximum](https://docs.twitterapi.io/api-reference/endpoint/get_tweet_by_ids), and [per-returned-post pricing and empty-call floor](https://twitterapi.io/pricing), checked October 20. Authentication values and headers are not saved.

Private authoritative evidence directory on fuchitalee: `~/.local/share/render-operations/2026-10-20-august-window-recall-comparison`. Frozen manifest SHA-256: `c95b25d1c91018e6972f1b2df6ec1e037e63965668282b81154430111ab1d631`. Files include selection rules and aggregate inventory; selected text controls; manifest/input/runner hashes; starts.jsonl, requests.jsonl, hits.jsonl; exact raw/ responses and raw-manifest.json; query-states/pages; availability plan/results; results.json and identity-conflicts.json.
