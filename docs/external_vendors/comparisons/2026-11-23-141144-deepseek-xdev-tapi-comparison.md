# DeepSeek keyword search through XDev and TwitterAPI.io

XDev returned 12 posts and TwitterAPI.io returned four for the same DeepSeek clause in one closed five-minute window. Three IDs overlapped. Both responses ended without a continuation. Seven of the nine XDev-only IDs were similar promos from the same account, so the coverage gain is smaller at the story level than the raw count suggests.

The window was November 22, 2026, **06:25–06:30 JST**, inclusive start and exclusive end. It was selected using a prior indexed sample with known DeepSeek hits and enough headroom to fit on one page. Calls were made on November 23 JST. This is one query and one window.

## Exact calls

The test isolated the DeepSeek clause of the saved production B3 query from November 22 JST. It retained the aliases, contextual requirement on `V4.1F`, account mention and inherited account exclusion. It did not include B3's Qwen and Hunyuan clauses. The test used both services' recency mode and applied no engagement floor.

```text
Q = (DeepSeek OR 深度求索 OR (V4.1F (DeepSeek OR 深度求索 OR LLM OR model OR 模型)) OR @deepseek_ai) -from:xxyweb3

XDev  GET https://api.x.com/2/tweets/search/recent
  query: Q
  start_time: 2026-11-21T21:25:00Z
  end_time: 2026-11-21T21:30:00Z
  max_results: 20
  sort_order: recency
  post.fields: created_at,lang,note_post,entities,public_metrics

TAPI  GET https://api.twitterapi.io/twitter/tweet/advanced_search
  query: Q since_time:1795296300 until_time:1795296600
  queryType: Latest
  cursor: ""
```

Use an app bearer for XDev and the on-demand X-API-Key for TAPI. The UTC strings and Unix seconds above represent the same interval. TAPI sets the page size on the server. Its documentation describes a page of up to 20 and notes that it filters ads and other items. The results do not establish why any specific post was absent. [XDev recent search](https://docs.x.com/x-api/posts/search-recent-posts) · [TAPI advanced search](https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search)

## Observed comparison

| Measure | XDev | TAPI |
| --- | ---: | ---: |
| Physical data requests | 1 | 1 |
| HTTP | 200 | 200 |
| Raw slots / unique IDs | 12 / 12 | 4 / 4 |
| IDs also returned by the other provider | 3 | 3 |
| IDs returned only by this provider | 9 | 1 |
| Outside the requested window | 0 | 0 |
| Continuation | No | No |
| Elapsed time | 288 ms | 1,285 ms |
| Estimated retrieval price | $0.0600 | $0.0006 |

Published retrieval prices give estimates, not billed amounts. X may deduplicate reads already made during the billing day. [X pricing](https://docs.x.com/x-api/getting-started/pricing) · [TAPI pricing](https://docs.twitterapi.io/pricing)

- TAPI returned three of the 12 XDev IDs. All three shared posts had identical text after reading full text from XDev's `note_post` when available. One was a [Japanese comment comparing model behavior](https://x.com/i/web/status/2124253572800102777).
- Seven XDev-only IDs point to similar DeepSeek launch or integration promotions associated with the same account. [Example promo](https://x.com/ObinaGMI/status/2124253791906152650). The remaining two were a [Chinese-language repost about a DeepSeek coding experiment](https://x.com/i/web/status/2124253972236280137) and a [Portuguese reply mentioning DeepSeek](https://x.com/i/web/status/2124253078144581898). All nine XDev-only posts showed zero likes when retrieved.
- The [TAPI-only post](https://x.com/banjyo007/status/2124253157182341613) had a link to an X Article and no visible DeepSeek term. The returned fields did not explain why it matched the query. Its inclusion is evidence of disagreement between the search engines.
- TAPI's four returned posts were not strictly in timestamp order despite `queryType=Latest`. Neither API exposed another page for this query. The combined 13 IDs are an observed union, not a count of all matching posts on X.

Exact request parameters, original response bytes and per-slot hits are in the restricted run directory `~/.local/share/pushinweight/official-x-probe/2026-11-23-141144-deepseek-vs-tapi/` on fuchitalee. The run used one search per provider and had no retries.
