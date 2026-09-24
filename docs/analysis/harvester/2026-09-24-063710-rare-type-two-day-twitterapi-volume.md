---
title: Combined rare-type TwitterAPI first-page volume probe
date: 2026-09-24
status: measured-provider-exhausted-two-day-sample
---

# Combined rare-type TwitterAPI two-day volume probe

The provisional `rare-types-v3-provisional-2026-09-23` query returned **1,337 raw posts in 192 successful 15-minute searches** over one Sunday and one Tuesday: **27.85 posts per sampled hour**. The first pages contained all 1,337 posts. Although 187 first pages carried continuation cursors, each subsequent cursor request returned an empty terminal page. All 192 window chains are therefore exhausted according to the provider responses. The query SHA-256 was `7ba964d466b62eff6b659362e4b58e27df96f0037744d0ffaa377fb8eec03da1`.

| UTC date | Windows | Raw posts | Posts/hour | Empty terminal pages | Estimated credits, both passes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sunday 2026-09-20 | 96 | 689 | 28.71 | 96 | 11,775 |
| Tuesday 2026-09-22 | 96 | 648 | 27.00 | 91 | 11,160 |
| Combined | 192 | 1,337 | 27.85 | 187 | 22,935 |

Five Tuesday windows returned zero; no first page returned 20 posts (maximum 17). The median was 7 posts/window and the 95th percentile 13. There were no HTTP failures, missing IDs, duplicates, missing texts, or missing creation timestamps in the captured first pages. All 1,337 provider-supplied creation times fall inside their respective requested UTC windows. All 192 first-page request receipts have matching raw-response files. The continuation run reused those saved pages rather than buying them again: **187 dispatches, 187 successful request receipts, 187 exact raw-response files, zero returned posts, zero remaining cursors, and zero errors**. No retry occurred. The combined 1,337 posts have 1,337 unique IDs. This is provider-exhausted coverage for the two selected historical days and exact query, not a relevance label, guarantee about future windows, or proof of complete coverage of X itself.

The provider did not return confirmed credit usage. At the [listed TwitterAPI rate](https://twitterapi.io/pricing) of 15 credits per returned post, a 15-credit minimum per call, and 100,000 credits per USD, the first pages imply **20,130 credits (~$0.2013)**, and the 187 empty continuation calls imply **2,805 more credits (~$0.02805)**. The complete diagnostic thus estimates **22,935 credits (~$0.22935)** across two days. This is below the owner's separate 57,600-credit first-pass ceiling and 300,000-credit continuation ceiling. A continuous 96-window day at the two sampled rates would use about 9,795–10,335 credits/day for first pages, or 11,160–11,775 credits/day if every signaled cursor were followed to the empty terminal page. The planned 6,000-credit daily cap would interrupt even the one-page lane. A 28,800-credit daily cap reserves all 96 first pages at the maximum 300 credits/page (~$0.288/day), but it does not fund pagination. No scheduled setting or key was changed by this probe.

The [Advanced Search documentation](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search) says pages may contain fewer than 20 posts and `has_next_page` indicates more results. Here, every one of the 187 signaled cursors instead yielded an empty terminal page. The observed continuation signal was therefore not evidence of additional matching posts in these windows. This does **not** establish that TwitterAPI will always behave that way, so the recurring collection policy still needs an explicit one-page-versus-pagination decision; a keeper-percentage threshold is not part of that decision.

The earlier [query-widening research](2026-09-23-070740-rare-type-query-widening.md) used Grok for wording examples, not an hourly-volume estimate. Its TwitterAPI candidate rates came from just two 15-minute windows each, so they are not a 24-hour comparator to this Sunday/Tuesday measurement.

Both passes ran against TwitterAPI from temporary directories on the Render production web instance using its Render-managed **on-demand** credential. The credential was neither copied locally nor printed, and the scheduled key was not used. The commands wrote no application database rows, did not enable the rare-type lane, and did not change the scheduled harvester. First-pass raw JSON, request/hit ledgers, report, and summary are at `.context/rare-volume-20260924/probe/`; the continuation raw JSON, dispatch/request/hit ledgers, and summary are at `.context/rare-volume-20260924/followup-a/` on the authoritative host. The two noncontiguous UTC days were preselected in `.context/rare-volume-20260923/windows.json`. The continuation was bounded by 2,000 physical calls and 300,000 credits, but stopped naturally after 187 calls and 2,805 estimated credits.
