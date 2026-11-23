# X search and list capabilities across providers

Contract references checked November 23, 2026 JST. The test results describe the app, list and query used.

## Keyword search

| | TwitterAPI.io | TwexAPI | X Developer API |
| --- | --- | --- | --- |
| Request | `GET /twitter/tweet/advanced_search`; `query`, case-sensitive `queryType=Latest`, and `cursor`. | `POST /twitter/advanced_search/page`; `searchTerms` array, `sortBy=Latest`, and `next_cursor`. | `GET /2/tweets/search/recent` or `/2/tweets/search/all`; `query`, `sort_order=recency`, and `next_token`. |
| Time window | Inline `since_time:` and `until_time:` using Unix seconds. Together they occupy 44 bytes when both timestamps have 10 digits and the query already has a term. | The historical trial used the inline time operators in one search term. | Separate `start_time` and `end_time` request parameters. |
| Query size | Our probe worked at 511 UTF-8 bytes and returned an empty response at 513 bytes, even though that query had 511 characters. PushinWeight caps the final wire query at 512 bytes. | The documented request does not specify a limit. Our tests used one term string per request. | X documents 512 characters for recent and 1,024 for full archive on self-serve, with separate time parameters. Unicode counting at the boundary has not been measured. |
| Maximum post results per page | 20. The documented response may be shorter because of filtering. | 20. A short or empty page can still carry a cursor. | 100 recent, 500 full archive. A cursor indicates an available continuation. |

Sources and evidence follow. [TAPI search](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search) · [PushinWeight byte-boundary evidence](../../../x_monitor/queries.py) · [Twex search and billable routes](../twex/api/index.md) · [Twex historical trial](../twex/research/2026-10-20-163320-twexapi-historical-recall-quick-trial.md) · [XDev API index](../xdev/api/index.md)

The [matched DeepSeek sample](2026-11-23-141144-deepseek-xdev-tapi-comparison.md) supplies the exact query and time parameters. Both responses stayed within the same five-minute window and exhausted their exposed pages. XDev returned more IDs, with most extras concentrated in similar promos from one account. The experiment does not establish provider-wide recall or why a given post was omitted.

XDev accepts `min_likes:` in its query syntax. Current TAPI Call A uses vendor-style `min_faves:0`. Translate operators based on the intended rule. In the XDev test, a positive-like floor would have removed known relevant zero-like results. [XDev measurements](../xdev/research/2026-11-23-135930-official-x-api-measurement.md)

## Call A, curated list collection

PushinWeight's saved TAPI search used `(list:2067062923525275922) min_faves:0 -from:xxyweb3`. The dedicated list routes each take one list ID. They use their own pagination and differ from a search that combines a list operator with exclusions and time bounds. [Implemented TAPI call inventory](../../reference/twitterapi-io-calls.md)

| Provider | Dedicated list route | Search evidence |
| --- | --- | --- |
| TAPI | `GET /twitter/list/tweets_timeline` with one `listId` and a `cursor`. | Call A uses one configured list in advanced search. |
| Twex | `POST /twitter/list/tweets/page` with one `list_id` and `next_cursor`. | Search trial used keywords. Multi-list search was outside the trial. |
| XDev | `GET /2/lists/:id/tweets` with one list ID in the path. No documented start/end time on this endpoint. | `list:` search returned zero for the configured list. List posts and membership both returned not-found errors inside HTTP 200 responses. Multi-list Boolean search remains unverified. |

[TAPI list timeline](https://docs.twitterapi.io/api-reference/endpoint/list_timeline) · [Twex list timeline](../twex/api/index.md) · [XDev verified list behavior](../xdev/research/2026-11-23-135930-official-x-api-measurement.md)

## Long-form posts and article bodies

XDev post lookup returned long-form post text via `note_post.text` and an article body via `article.plain_text`. On the matched article example, XDev returned 56,576 characters of body text and the TAPI advanced search result contained a 198-character article preview. TAPI documents **Get Article**, a separate `GET /twitter/article` call with the sharing post's ID, at 100 credits per article. This sample did not use that separate endpoint. [XDev lookup evidence](../xdev/research/2026-11-23-135930-official-x-api-measurement.md) · [TAPI Get Article](https://docs.twitterapi.io/api-reference/endpoint/get_article)
