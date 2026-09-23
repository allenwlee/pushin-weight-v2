---
title: Combined rare-type TwitterAPI first-page volume probe
date: 2026-09-24
status: measured-first-pages; full-match-volume-unresolved
---

# Combined rare-type TwitterAPI first-page volume probe

The provisional `rare-types-v3-provisional-2026-09-23` query returned **1,337 raw first-page posts in 192 successful 15-minute searches** over one Sunday and one Tuesday. This is 27.85 observed posts per sampled hour, not the full matching rate: 187 responses, including underfilled ones, carried a continuation cursor. The query SHA-256 was `7ba964d466b62eff6b659362e4b58e27df96f0037744d0ffaa377fb8eec03da1`.

| UTC date | Windows | First-page posts | Posts/hour | Windows with continuation | Estimated credits |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sunday 2026-09-20 | 96 | 689 | 28.71 | 96 | 10,335 |
| Tuesday 2026-09-22 | 96 | 648 | 27.00 | 91 | 9,795 |
| Combined | 192 | 1,337 | 27.85 | 187 | 20,130 |

Five Tuesday windows returned zero; no page returned 20 posts (maximum 17). The median was 7 posts/window and the 95th percentile 13. There were no HTTP failures, missing IDs, duplicates, missing texts, or missing creation timestamps in the captured first pages. All 192 request receipts have a matching raw-response file; the sum of request raw counts equals the 1,337 saved hit rows. The 192 planned calls were all used, with no pagination or retry. These are observed first-page counts, not relevance labels or proof that 20–50 posts/hour is the actual match volume.

The provider did not return confirmed credit usage. At the [listed TwitterAPI rate](https://twitterapi.io/pricing) of 15 credits per returned post, a 15-credit minimum per call, and 100,000 credits per USD, the first pages imply **20,130 credits (~$0.2013)**. This is below the owner's separate 57,600-credit probe ceiling. A continuous 96-call day at the two sampled rates would use about 9,795–10,335 credits/day (~$0.10/day), so the planned 6,000-credit daily cap would interrupt the one-page lane. A 28,800-credit daily cap reserves all 96 first pages at the maximum 300 credits/page (~$0.288/day), but it does not fund pagination. No scheduled setting or key was changed by this probe.

The [Advanced Search documentation](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search) says pages may contain fewer than 20 posts and `has_next_page` indicates more results. Consequently, the continuation rate is a coverage issue even though no first page was full. A separate pagination allowance would be needed to estimate full matching volume. Do not present this first-page measurement as complete recall. The owner must choose whether to preserve one-page, known-incomplete collection or fund a bounded multi-page design; a keeper-percentage threshold is not part of that choice.

The probe ran against TwitterAPI from a temporary directory on the Render production web instance using its Render-managed **on-demand** credential. The credential was neither copied locally nor printed, and the scheduled key was not used. The command writes no application database rows, does not enable the rare-type lane, and does not change the scheduled harvester. Its exact raw JSON responses, `requests.jsonl`, `hits.jsonl`, `report.md`, and run summary were copied to the authoritative host at `.context/rare-volume-20260924/`. The two noncontiguous UTC days were preselected in `.context/rare-volume-20260923/windows.json`; the provider-free preview reserved 192 calls and 57,600 credits before execution.
