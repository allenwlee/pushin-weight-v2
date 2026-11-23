# Official X API: first-principles test inventory

Prepared November 23, 2026 JST before the live calls. The [same-day measurement](2026-11-23-135930-official-x-api-measurement.md) records which tests ran and what the authorized app returned.

## Purpose

Find the best way to supply PushinWeight with timely evidence about AI models, organizations, people, releases, events and opportunities. Start with the evidence and product use, then test what X can provide. Current vendor queries, field mappings, engagement filters and storage are observations to challenge, not requirements to preserve. Compare providers where their answers are meaningfully comparable, but investigate X-only possibilities separately.

The application currently discovers posts, attributes brands, translates and classifies them, extracts people, jobs, events and opportunities, and presents feeds, charts and headlines (root `README.md`, “What this is”). `core/models.py` already stores post text, relationships, entities, engagement and many vendor-shaped account snapshots. `monitor/quote_tweets.py` and `x_monitor/jev_decisions.py` use quoted context; `x_monitor/__main__.py` has a separate X-article path. These are starting evidence, not a complete definition of useful data or proof of deployed behavior.

## Questions and test cases

| Evidence need | Candidate X capability | What a bounded test must establish |
| --- | --- | --- |
| Discover relevant announcements and discussion, across languages | Recent search; user timelines; list posts; potentially full-archive search | Independent queries based on real brands, people and topics; time coverage, missed known examples, noise, latency and cost. Compare vendor-matched windows separately. Test multilingual names, aliases, account posts, context and rare events without assuming a minimum-like rule is desirable. |
| Get complete source text and links | Post lookup and requested post fields, including long-form text, entities and article data | Exact text, language, expanded URLs, edit history and article body/metadata for known examples; distinguish absent, inaccessible and truncated fields. X documents `note_tweet` and article fields, but availability and completeness remain unmeasured. |
| Understand conversations and claims | Referenced posts, conversation IDs, quotes, replies and post lookup | Whether quoted/replied-to text and authors can be reconstructed, what further requests are needed, how deleted or unavailable parents appear, and whether replies/quotes can be collected with adequate coverage. |
| Identify people and organizations and observe changes | User lookup, profiles, timelines and list members | IDs, handles, names, bios, links, verification, profile images, observed changes and account-to-person evidence. Do not equate an account or mention with employment. |
| Support editorial evidence and visual storytelling | Media attachments and expansions | Media type, image/video URLs or variants, alt text, preview and provenance; whether downstream workers can use the returned fields and whether URLs remain usable. |
| Measure attention and change | Public post and account metrics, post lookup and counts | Metric fields and timestamps, repeated observations, refresh cost, count limitations, and whether metrics support the product question; engagement is a measurement, not proof of importance. |
| Find new opportunities | Search operators, annotations, communities, Spaces, trends, news and filtered stream | Inventory each against an explicit editorial/research use; check official docs, account entitlement and practical sample value before recommending collection. Stream rule changes are separate account mutations and are not authorized by this inventory. |

## Execution design

1. Identify the authorized X app and authentication mechanism, console entitlement, current resource prices, credit balance and spending limit without exposing secrets. Published prices are estimates until checked against the actual account. Existing environment variable names alone do not establish which project owns a credential.
2. Freeze a small acceptance set: known AI announcement, long-form post, article, multilingual post, quote/reply chain, media post, organization account, person account and dense/quiet windows. Obtain identifiers from existing saved evidence or public pages. Document selection and known-positive limitations.
3. Inspect the API reference for each selected endpoint, fields, expansions, maximum results, access and pagination. Freeze per-case queries, time boundaries, eligible-result criteria, physical request/page ceilings and a conservative resource-cost reservation before any live call. Resource-based billing means a request cap alone is not a spending cap. Stop when costs or response expansion bounds cannot be established; reconcile charges with the console. Do not exhaust limits intentionally.
4. Start with low-volume post and user lookup, then matched recent searches, then whichever timeline, list, quote or other read endpoint answers an actual need. Include second-page tests when a continuation exists and fits the cap. Separate documented-only, access-denied, measured, incomplete and unavailable findings. Full archive and streaming require separate entitlement and bounded test designs. Do not modify stream rules as part of read-only tests.
5. For each physical attempt retain restricted, local raw evidence without authorization headers or credentials, request shape and UTC timestamps, status, elapsed time, rate headers, item and unique ID counts, pagination/partial state, missing fields and estimated versus console-observed cost. Preserve duplicates and errors. Do not write experimental records to production. Sanitize and review any fixtures before sharing.
6. Produce a decision matrix: data need, endpoint, account/auth access, quality and omissions, source and field semantics, timeliness, reproducibility, expected volume and cost, and next action. Keep new capabilities distinct from parity tests. In matched comparisons, report overlap and known misses without calling either provider complete.

## Decisions still needed for a live run

- Which X app or credential is authorized for this PushinWeight experiment?
- What is the maximum total spend, including expansion resources, retries and pages? The experiment also needs a conservative request ceiling and account-specific price/usage evidence.

No production route, schema, scheduler, deployment, backfill, X account mutation or provider purchase is authorized by this inventory. Any future schema proposal must inspect current models, migrations and write/read paths before selecting storage.

## Sources

- [X data dictionary](https://docs.x.com/x-api/fundamentals/data-dictionary)
- [X API pricing and credits](https://docs.x.com/x-api/getting-started/pricing)
- [Recent search](https://docs.x.com/x-api/posts/search-recent-posts), [query construction](https://docs.x.com/x-api/posts/search/integrate/build-a-query), and [operators](https://docs.x.com/x-api/posts/search/integrate/operators)
- [Post lookup](https://docs.x.com/x-api/posts/lookup/introduction), [filtered stream](https://docs.x.com/x-api/posts/filtered-stream/introduction), and [rate limits](https://docs.x.com/x-api/fundamentals/rate-limits)
