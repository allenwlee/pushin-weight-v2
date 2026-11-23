# August 13: five-minute historical search comparison

Five-minute windows recovered **629 known posts versus 588 at ten minutes: 7.0% more**, using **91 versus 65 requests per pass: 40.0% more**. Both five-minute passes returned the same 825 distinct search IDs and the same 629 known controls. All 72 query chains ended with `has_next_page=false`.

This measures the same DeepSeek sample on August 13, 2026, 12:00–15:00 UTC as the [earlier comparison](2026-10-20-150253-august13-search-window-comparison.md). Five-minute results were collected later on October 20; the hourly, fifteen-minute and ten-minute baselines were reused from earlier that day rather than rerun alongside the new requests.

## Results

| Window | Pass | Search calls | Distinct raw IDs | Known controls / 1,757 | Search USD estimate |
| --- | --- | --- | --- | --- | --- |
| 60 minutes | 1 | 21 | 294 | 232 | $0.044550 |
| 60 minutes | 2 | 20 | 294 | 232 | $0.044550 |
| 15 minutes | 1 | 51 | 651 | 502 | $0.099450 |
| 15 minutes | 2 | 51 | 651 | 502 | $0.099450 |
| 10 minutes | 1 | 65 | 756 | 588 | $0.116100 |
| 10 minutes | 2 | 65 | 756 | 588 | $0.116100 |
| 5 minutes | 1 | 91 | 825 | 629 | $0.129150 |
| 5 minutes | 2 | 91 | 825 | 629 | $0.129150 |

## Five-minute results by hour

| UTC hour | Calls, pass 1 / 2 | Distinct IDs, pass 1 / 2 | Known controls recovered, pass 1 / 2 | Original controls |
| --- | --- | --- | --- | --- |
| 12:00Z | 29 / 29 | 239 / 239 | 183 / 183 | 489 |
| 13:00Z | 33 / 33 | 337 / 337 | 263 / 263 | 725 |
| 14:00Z | 29 / 29 | 249 / 249 | 183 / 183 | 543 |

## Gains and losses

| Baseline | Five-minute-only known IDs | Known IDs lost | Net gain | Known controls in combined union |
| --- | --- | --- | --- | --- |
| 60 minutes | 399 | 2 | 397 | 631 |
| 15 minutes | 127 | 0 | 127 | 629 |
| 10 minutes | 44 | 3 | 41 | 632 |

Against ten minutes, five-minute queries gain 44 known controls and lose three, for a net gain of 41. The union of both resolutions recovers 632 known controls. Smaller windows therefore improve this sample but do not form a strict superset. Adding a whole second resolution repeats considerable search work for its few remaining unique controls.

The archived availability check found 1,637 matching controls still retrievable by ID. Five-minute searches recovered 629 of those, **38.4%**, and still missed **1,008**. Availability was observed earlier on October 20, not freshly rechecked for all IDs during this follow-up. None of the 120 controls omitted or unavailable at the earlier lookup appeared in the new five-minute results.

## Method and resource use

Before new requests, reuse the earlier frozen selection: the busiest August day by same-publication-day-first-collected own-text DeepSeek controls, then its three busiest UTC hours. The benchmark contains 489, 725 and 543 controls respectively. It is deliberately a busy sample, not a random sample of all brands or hours.

Unchanged base query: `(DeepSeek OR 深度求索) min_faves:0 -from:xxyweb3`. GET `/twitter/tweet/advanced_search` with `queryType=Latest`, inline Unix `since_time` / `until_time` bounds, and exact previous cursor after page one. No unsupported `limit` parameter. Each hour is partitioned into twelve adjacent five-minute intervals; each is queried twice in interleaved lanes, with at most four concurrent requests. The corrected prior diagnostic controller reuses the unchanged application TwitterApiClient transport and explicit on-demand credential resolver. It does not invoke ingestion or Django models.

Execution: 2026-10-20T07:24:52.048987+00:00 to 2026-10-20T07:26:02.950168+00:00; **70.9 seconds**. **182 physical requests**, all successful HTTP 200, no retries, failures, unknown charges or lookup/model calls. Captured 9,266,877 bytes across 182 exact response bodies. Total estimated search cost for both passes: **$0.2583**. Raw search appearances: 1,650; 825 distinct IDs across both passes. Repeated appearances are retained and included in cost.

The run admitted at most 400 physical calls, $1.25 estimated cost, 60 minutes and 128 MiB, with 100 pages per exact query and at most two attempts per logical page. It used connect/read socket timeouts of 10/75 seconds, zero hidden retries and four workers. All admission checks include in-flight calls and estimated charges. Offline checks exercised spend, in-flight reservation, call ceilings, third-attempt rejection and pass independence. No limits were reached or extended.

This was much faster than the earlier comparison: the five-minute run completed in 71 seconds. Earlier responses were slow and its 37-minute duration included harness repairs and availability lookups. These runs do not isolate why request latency changed, and their total durations are not a controlled speed comparison between window sizes.

## Interpretation

For this busy DeepSeek sample, moving from ten to five minutes yields another 7% of known controls for 40% more requests. That is a measurable but diminishing improvement. The large remaining gap persists; five-minute windows do not solve historical keyword omissions. The repeated result sets are stable in this test, but no optimum for every brand, date or traffic level has been established. Provider-ended pagination proves the end of each query, not complete X coverage.

This diagnostic inserted no application Posts and wrote no production or CollectionRun records. It changed no application code, schema, key configuration, scheduler or deployment. Historical acquisition remains stopped.

## Evidence and sources

Raw bytes, SHA-256 manifests, frozen inputs, exact request parameters/cursors/timestamps, per-hit IDs and text, terminal query states, repeat sets and all gain/loss ID lists are retained privately on fuchitalee at `~/.local/share/render-operations/2026-10-20-august-five-minute-window-comparison`. Manifest SHA-256: `6513e2b3f49c365d8df06b0e57c0f832d6057b0d8776ad3854965f2147639167`. All starts/results, raw hashes/counts, ID/text/time identities and provider-end states reconcile; zero identity conflicts or out-of-window records.

The [official search reference](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search) defines the query parameters. Cost uses [TwitterAPI pricing](https://twitterapi.io/pricing): $0.00015 per returned result slot, including repeated slots, with the minimum charge for an empty request. This is an undiscounted estimate, not an invoice; documentation was checked October 20.

## One-minute windows for a month: feasibility estimate

One-minute windows are historical query bounds, not a one-minute pause between requests. For a 30-day month there are 43,200 windows per distinct query branch, versus 8,640 at five minutes or 2,880 at fifteen minutes. The July 30 campaign used eight grouped routes, A/B1/B2/B3/C1/C2/C3/RARE_EXTRA; applying one-minute partitions to all eight would require at least 345,600 first-page requests before pagination, retries or additional query splitting. This is a count against that saved campaign shape, not a newly verified inventory of every current live discovery route. A 31-day month raises the first-page total to 357,120.

Rebinning only the 825 IDs already returned by one five-minute pass gives 179 occupied minutes out of 180; each occupied minute has at most twenty of these IDs. If one-minute searches returned exactly those same IDs and ended with one empty page per query, the sample would require 179 data pages plus 180 terminal pages: 359 requests versus the observed 91 at five minutes, about 3.95 times as many. Repeating that deliberately busy three-hour workload over a 30-day month would give 86,160 requests for that one branch. This is a workload simulation, not an actual one-minute search or forecast of additional recovered posts; one-minute results could gain and lose IDs, and a whole month is unlikely to have this same peak-hour traffic.

At the documented TwitterAPI empty-request floor, 43,200 all-empty requests cost about $6.48 per branch, or $51.84 for eight branches. Actual returned-post appearances, repeated work and enrichment add cost; do not add an empty-call floor a second time to the same nonempty response. Under the same-ID/one-empty-page assumptions above, the one-branch busy-month simulation costs about $36.18 for search: 198,000 returned appearances plus 43,200 empty calls. This excludes newly recovered posts, retries, cross-route overlap and all model work, and is not an all-brand campaign quote.

Elapsed time depends on response latency and allowed concurrency. For illustration, just 345,600 first-page calls at four concurrent requests take about 48 hours at two seconds per response or ten days at ten seconds; pagination adds work. These are conditional arithmetic scenarios, not measured month completion times. Today's five-minute run was fast, while the earlier run had much slower responses, so a precise estimate needs the one-minute trial and measured latency distribution.

The existing backfill approach can support a long run by checkpointing bounded query/window/cursor work through shared CollectionJob/CollectionRun/CollectionScopeRun storage, streaming saved results, deduplicating before model work, and resuming failed pages without repeating successful ones. A month need not be one long transaction or load all results into memory. No such one-minute campaign, scheduling change or persistence change is authorized or started here. Measure one-minute incremental recovery on the fixed sample before paying for a whole month at that resolution; the vendor's older July case gained nothing from one-minute subdivisions.

## Does this apply to the current live harvester?

Possibly, especially on busy queries, but historical recovery percentages do not establish a live gain. Read-only Render inspection at 2026-10-20T07:35:03Z observed the active harvest cron on deployed commit `64b95c266d4af333ab7bfb2cc50744a98290e5f4`, scheduled `*/15 * * * *`. The source/configuration inspected for this explanation were extracted from that exact commit, not inferred from the newer root checkout or the older diagnostic worktree.

Its ordinary search bounds come from each route's last completed cursor through now, with a one-minute overlap and a fifteen-minute maximum lookback. Some discovery routes have explicit lookback overrides. Scheduled ordinary searches deliberately fetch only one initial page, up to twenty posts, before transferring unfinished coverage to backlog processing. The deployed backlog configuration allows two replay attempts/windows per cycle, within the shared run deadline. These mechanisms matter separately from X's historical filtering.

Consequently, three five-minute provider queries can expose up to sixty fresh results on their first pages where one fifteen-minute query exposes up to twenty. For example, ninety matching posts distributed thirty per five-minute slice would expose sixty on those three first pages rather than twenty, with the remaining work still requiring pagination/backlog. This can reduce dependence on successful deferred replay. It does not prove the present harvester loses the other posts: determining that requires observing backlog completion.

There are two distinct changes: split provider searches into five-minute bounds inside the existing fifteen-minute cycle, or start the entire harvesting cycle every five minutes. The first changes search partitioning; the second also repeats cycle setup, enrichment/metrics scheduling and overlap work. Neither is implemented here. To isolate search-width effects, a matched prospective diagnostic should query the same freshly closed fifteen-minute publication span as one fifteen-minute query and as three five-minute queries, using the same collection time/delay and fully paging each. Repeating on busy and quiet routes would separate real-time search gains from first-page/deferred-replay effects. Use the on-demand credential for such an explicitly authorized probe, leaving scheduled credentials for the normal cron.

The vendor says near-publication searches are more complete; see the [preserved support findings](2026-10-20-135635-twitterapi-support-findings-and-backfill-implications.md). No percentage gain for live harvesting has been measured by the August experiments. A small live comparison is a justified next test, not grounds to change the scheduler immediately.
