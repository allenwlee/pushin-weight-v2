# TwexAPI endpoints and pricing

Public documentation checked November 23, 2026 JST.

| Need | Endpoint and request shape | Source |
| --- | --- | --- |
| Advanced search | `POST /twitter/advanced_search/page` with the `searchTerms` string array, `sortBy` (`Latest` or `Top`), and cursor pagination. The response returns up to 20 tweets per page and uses `next_cursor`. | [Search reference](https://docs.twexapi.io/api-reference/search-endpoints/get-data-page-twitter-advanced-search-page-post) |
| Post lookup | `POST /twitter/tweets/lookup` with an array of tweet IDs. | [Lookup reference](https://docs.twexapi.io/api-reference/tweets-endpoints/get-tweets-by-ids-twitter-tweets-lookup-post) |
| List timeline | `POST /twitter/list/tweets/page` with one `list_id` and an optional `next_cursor`. | [List reference](https://docs.twexapi.io/api-reference/lists-endpoints/get-list-tweets-page-endpoint-twitter-list-tweets-page-post) |
| Balance | `GET /balance` returns credit balance. | [Balance reference](https://docs.twexapi.io/api-reference/balance-endpoints/get-balance-api-balance-get) |

The [live rate card](https://twexapi.io/pricing) lists a typical rate of 5 credits per returned tweet and a 5-credit minimum for an empty successful request. It lists Lite at $20 with 2.5 million credits and 3 requests per second, Basic at $50 with 6 million credits and 5 requests per second, and Pro at $99 with 13 million credits and 10 requests per second. The [rate-limit guide](https://docs.twexapi.io/guides/rate-limits) has different plan figures. Use the live rate card for the published plan comparison and verify limits for the account in use.

Use [Twex's OpenAPI specification](https://twexapi.io/openapi.json) for wire details. The advanced search schema does not specify a query-length ceiling. Our trial tested one term string per request and does not establish multi-term behavior or a query-length limit. Empty pages sometimes still carried a cursor. [Historical recall trial](../research/2026-10-20-163320-twexapi-historical-recall-quick-trial.md)
