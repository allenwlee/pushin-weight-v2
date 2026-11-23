# TwitterAPI support findings and implications for historical backfill

Received from the owner: October 20, 2026, JST. Source: a TwitterAPI.io support response forwarded by the project owner. The original correspondence is retained privately. Related evidence: [original support report and complete request parameters](2026-10-19-091559-twitterapi-historical-search-support-report.md).

This note records the vendor's explanation and its effect on our next backfill design. We made no new API requests to independently reproduce their latest results. The October 16 and 17 captures remain the evidence for our own measurements; the vendor supplied no raw response bodies or per-request timestamps with this reply.

## What the response establishes

TwitterAPI says our request parameters and cursor handling were correct. Their rerun reproduced D1 exactly: 46 distinct IDs, 34 of 75 stored controls, and pages of 20/20/6/0. Their one-minute subdivisions returned the same 46-ID union. Continuing to split this particular interval therefore did not recover its missing controls.

Their explanation separates two sources of historical search loss:

| Behavior | Our saved observation | Vendor explanation | Consequence |
| --- | --- | --- | --- |
| Broad windows omit IDs found with narrower bounds | July 30 B1: 1,095 full-day IDs versus 1,716 across 24 hourly searches; noon hour 3 versus 84 | X stops returning results after a certain depth for broad windows | Avoid a single full-day or full-month keyword cursor chain. Divide the requested range into bounded time windows and finish each chain. |
| Matching known posts are absent even in short windows | D1 recovered 34/75; five sampled omissions returned through ID lookup. The later five-minute study still missed available matching controls. | X filters some accounts/posts from plain keyword search; author-constrained search can expose them | Smaller windows alone cannot restore complete recall. Add a separate recovery path for relevant known authors or known native IDs. |
| Author queries gave no results on October 16 | D4/D5/D6 were empty in the retained responses | Those results were temporary; the vendor now retrieves the expected posts and reports agreement between two backends | Preserve the original failures. Do not reinterpret them as invalid query syntax or pretend that our old tests succeeded. A future bounded retest can establish current behavior. |
| Some pages contain fewer than 20 results | Captured underfilled and empty pages | Advanced search ignores the unsupported `limit` parameter and returns up to about 20 tweets per page | Removing `limit` is client cleanup; it will not enable larger pages or eliminate pagination calls. |
| A terminal timeline response still contains a cursor | Captured empty `data.tweets`, false continuation flag, nonempty cursor | Stop when `has_next_page=false` | A leftover cursor is not permission to keep enumerating that query. |

The vendor attributes the keyword exclusions to X rather than its own drop/filter stage. That attribution is a vendor finding; our independent evidence establishes omissions before application filtering, but does not expose X's internal mechanism. We have not independently established that any particular account is search-limited or “shadowbanned.”

## What this means for the backfiller

**The collection loop can be correct while historical coverage is incomplete.** A fully drained query means the provider ended that exact query. It cannot certify that every matching historical post was returned. Reusing the harvester's parsing, attribution, Post writers and enrichment preserves application behavior; it cannot make historical keyword search recover the same set that was available to near-real-time collection.

This explains why comparing a historic day with today's harvested volume cannot supply an exact missing-post count. The roughly 4,000-post July 30 expectation remains a planning estimate. The reply does not establish the true July 30 population, prove all of our previously excluded raw inputs were correctly rejected, or resolve the separate 18-post cached-import defect.

The next implementation should retain the user's requested date range as the campaign boundary and handle provider searches beneath it:

1. **Collect the full existing scope.** Preserve A, B/C and rare-type queries and the normal eligibility rules. A month-long request should schedule the whole month, with per-query windows no wider than one hour as the initial historical baseline. Denser routes can use smaller windows where matched measurements show a worthwhile gain. Window size controls search coverage; it does not imply a pause or a 15-minute scheduler.
2. **Finish every cursor chain and preserve honest outcomes.** Resume interrupted/capped scopes through their saved cursor. Treat `has_next_page=false` as the end of that query, including timeline responses with a leftover cursor. Keep errors, budget stops and incomplete work separate from provider-ended enumeration. None of those outcomes establishes complete X recall.
3. **Recover from relevant known authors.** Use author-constrained keyword queries based on existing relevant author evidence, and supported timeline or native-ID lookup where appropriate. This supplements broad discovery and cannot discover unknown authors omitted by keyword search. Restricting every query to our curated staff list would lose community coverage and is not the proposed replacement.
4. **Reuse the shared application path.** Use the same normalization, attribution, Post persistence and enrichment as normal collection, and the existing shared collection bookkeeping. Retain the on-demand TwitterAPI and DeepInfra credentials for explicitly launched backfill work. No additional backfill tables or parallel ingestion implementation is proposed.
5. **Measure coverage and cost separately.** Report requested windows, actual calls, raw appearances, distinct IDs, known-positive recovery, accepted Posts and enrichment outcomes separately. For the author-recovery path, compare its additional native IDs and accepted Posts with its additional request cost. Query exhaustion must not be described as an exhaustive X census.

The unsupported advanced-search `limit` parameter should be removed from the shared client in a future scoped code change, with verification of both normal-harvester and backfill requests. Page accounting must remain based on actual responses. That cleanup is not a speed optimization and should not be sold as one.

Before a new acquisition run, the highest-value verification is a bounded matched test of the vendor's now-working author queries for the five known misses, compared with the unchanged keyword baseline. Record exact parameters, responses, continuation flags and per-call times. Then assess whether author recovery adds enough accepted Posts to justify expanding it. A further one-minute-only retry of D1 has no positive evidence behind it.

These are design implications, not a newly authorized run. Collection and import remain stopped under the current task boundary. No source change, deployment, database write, provider/model call or vendor message occurred while saving this note. The original support report is retained unchanged.
