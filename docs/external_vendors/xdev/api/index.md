# X Developer API endpoints and pricing

Public documentation checked November 23, 2026 JST. The November test used an app bearer token for reads.

| Need | Endpoint and request shape | Source |
| --- | --- | --- |
| Recent keyword search | `GET /2/tweets/search/recent` with `query`, separate `start_time` and `end_time`, `sort_order=recency`, and up to 100 results per page. | [Recent search](https://docs.x.com/x-api/posts/search-recent-posts) |
| Full-archive keyword search | `GET /2/tweets/search/all` with the time parameters and up to 500 results per page. | [Full-archive search](https://docs.x.com/x-api/posts/search-all-posts) |
| List timeline | `GET /2/lists/:id/tweets` with one list ID in the path and pagination. The documented parameters do not include a start/end window. | [List posts](https://docs.x.com/x-api/lists/get-list-posts) |
| Post lookup | `GET /2/tweets` with `ids` and `post.fields`. The tested fields include `note_post`, `article`, `entities`, and `public_metrics`. | [Post lookup](https://docs.x.com/x-api/posts/get-posts-by-ids) |
| Credit usage | `GET /2/usage/credits` for payer-level balance snapshots. | [Credit usage](https://docs.x.com/x-api/usage/get-usage-credits) |

For self-serve search, X documents 512 characters for recent and 1,024 for the full archive. It lists 4,096 for Enterprise on both. Time bounds are separate request parameters, leaving the query string for search operators and terms. The November run exercised a multilingual query but did not probe X's counting behavior at the Unicode boundary. [Search introduction](https://docs.x.com/x-api/posts/search/introduction) · [Query construction](https://docs.x.com/x-api/posts/search/integrate/build-a-query) · [Operators](https://docs.x.com/x-api/posts/search/integrate/operators)

The `list:` search operator is distinct from the dedicated list timeline endpoint. In November we tested one configured list and saw an empty search result and object-level not-found errors in HTTP 200 responses from list posts and members. Multi-list Boolean search was outside the test. [Live list evidence](../research/2026-11-23-135930-official-x-api-measurement.md)

The published Post read price is $0.005. X describes best-effort deduplication of eligible repeated reads within a UTC billing day. User data, expansions, and other billed resources can change the total. The rate-limit table describes request quotas separately from costs. [Pricing](https://docs.x.com/x-api/getting-started/pricing) · [Rate limits](https://docs.x.com/x-api/fundamentals/rate-limits) · [OpenAPI specification](https://docs.x.com/openapi.json)
