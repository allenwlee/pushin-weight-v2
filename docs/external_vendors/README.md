# External vendors

Start here for PushinWeight's research on outside services, including API contracts, prices, observed behavior, and terms.

## X data providers

| Provider | What we have studied |
| --- | --- |
| [TwitterAPI.io (TAPI)](tapi/README.md) | Keyword and list search, query limits, historical coverage, account fields, pricing, and provider incident updates. |
| [TwexAPI (Twex)](twex/README.md) | Search and lookup endpoints, historical recall, fallback usage, credit consumption, and pricing. |
| [X Developer API (XDev)](xdev/README.md) | Official X endpoints, access and field measurements, lists, archive search, pricing, and X terms. |
| [Provider comparisons](comparisons/README.md) | Matched test results and estimates using our recorded request volume. |
| [Shared X legal research and xAI](x_twitter/README.md) | Historical analysis of displaying X content and using xAI/Grok X Search. |

Use each provider's `api/` for wire contracts and pricing sources, `research/` for dated test results and vendor communications, and `legal/` for terms and policy evidence. Add those folders as material warrants. Put studies comparing multiple X providers in [comparisons](comparisons/README.md). Link existing application studies from the relevant provider index when their fixtures or product analysis belong with the original.

For PushinWeight's implemented calls, start with the [call inventory](../reference/twitterapi-io-calls.md). For live receipts, fallback, and public announcements, use [X provider observability](../operations/x-provider-observability.md).
