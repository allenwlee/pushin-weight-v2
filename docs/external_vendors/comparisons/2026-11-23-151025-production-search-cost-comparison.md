# X search costs at PushinWeight's recorded volume

Measured workload from November 20, 2026 JST. Prices checked November 23, 2026 JST. The table reprices one day of recorded scheduled TAPI search traffic. The live tests below provide separate billing evidence.

| Provider | Basis at the recorded volume | One day | 30 days |
| --- | --- | ---: | ---: |
| TwitterAPI.io | 29,973 returned post slots plus 1,536 successful empty calls at 15 credits each. 100,000 credits per USD. | $4.73 | $141.79 |
| TwexAPI | The same 31,509 units at five credits each. 4,726,350 credits in 30 days. | 157,545 credits | $50 Basic plan with 6 million credits. |
| X Developer API | The same recorded posts deduplicated by UTC billing date and ID. 26,579 distinct day/ID pairs at $0.005. | $132.90 | $3,986.85 |

The Twex figure is the smallest published monthly subscription covering the modeled credits. It advertises five requests per second. The lighter $20 plan includes 2.5 million credits. Throughput at peak request bursts and the actual contract on the production account require separate checks. [TAPI pricing](https://docs.twitterapi.io/pricing) · [Twex pricing](https://twexapi.io/pricing) · [X API pricing](https://docs.x.com/x-api/getting-started/pricing)

## How the workload was counted

- The JST calendar day was read from production request receipts and linked response archives. The population was physical requests to `/twitter/tweet/advanced_search` linked to scheduled X collection runs. We counted the `tweets` array in each successful `wire-bytes-v1` response, including duplicate IDs across queries or pages. There were 3,981 HTTP 200 responses, including 1,536 successful empty responses.
- X documents best-effort deduplication within a UTC day. The JST day spans parts of two UTC billing days. November 19 UTC contributed 9,734 slots and 8,672 distinct IDs. November 20 UTC contributed 20,239 slots and 17,907 distinct IDs. We applied the rate to the sum of the distinct counts, assuming no additional same-day reads outside this sample. The estimate does not add a charge for successful empty search.
- Thirty days assume 30 repeats at the same daily volume. Scope is scheduled search only, including the list-based query where it uses advanced search. Metrics lookup, enrichment, articles, separate list calls, other workloads, taxes, and discounts are outside the calculation. A routing change could alter coverage, page counts, and duplicate rates. The table measures the price implications of the same recorded workload.

## Provider-side observations

| Evidence | What was measured |
| --- | --- |
| XDev, November 23 | Payer balance dropped **$0.98** across 31 data requests in the endpoint experiment. The recent-search and counts stage accounted for **$0.60** across 14 sends (two were counts), with 137 returned post slots and 115 distinct post IDs. These are account-level balance differences. [Live measurement](../xdev/research/2026-11-23-135930-official-x-api-measurement.md) |
| Twex trial, October 20 | Balance dropped **710 credits** across 15 search pages, a five-ID lookup, and two balance reads. The search and lookup together returned 177 slots. The trial gives no paid invoice or per-request breakdown. [Trial report](../twex/research/2026-10-20-163320-twexapi-historical-recall-quick-trial.md) |
| Twex fallback, November 23 through 14:30 JST | Production recorded 24 sends, 19 HTTP 200 responses, nine successful empty responses, and 109 slots. Dollar charges were unavailable. [Request history and report](../../operations/x-provider-observability.md) |
