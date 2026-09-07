[HerculeRadar](https://herculeradar.com/) [Use cases](https://herculeradar.com/use-cases/product-feedback) [Sources](https://herculeradar.com/listening/reddit) [Pricing](https://herculeradar.com/#pricing) [Docs](https://herculeradar.com/docs)

[Sign in](https://herculeradar.com/login) [Start free](https://herculeradar.com/login)

[Use cases](https://herculeradar.com/use-cases/product-feedback) [Sources](https://herculeradar.com/listening/reddit) [Pricing](https://herculeradar.com/#pricing) [Docs](https://herculeradar.com/docs)

Developers

[OpenAPI](https://herculeradar.com/openapi.json)

Guides

- [Overview](https://herculeradar.com/docs)
- [Quickstart](https://herculeradar.com/docs/quickstart)
- [Authentication](https://herculeradar.com/docs/authentication)
- [REST API](https://herculeradar.com/docs/api)
- [MCP](https://herculeradar.com/docs/mcp)
- [Webhooks](https://herculeradar.com/docs/webhooks)
- [Errors & limits](https://herculeradar.com/docs/errors)

Projects

- [list\_projects](https://herculeradar.com/docs/reference/list_projects)
- [create\_project](https://herculeradar.com/docs/reference/create_project)
- [get\_project](https://herculeradar.com/docs/reference/get_project)

Monitors

- [list\_monitors](https://herculeradar.com/docs/reference/list_monitors)
- [create\_monitor](https://herculeradar.com/docs/reference/create_monitor)
- [update\_monitor](https://herculeradar.com/docs/reference/update_monitor)
- [delete\_monitor](https://herculeradar.com/docs/reference/delete_monitor)

Mentions

- [list\_mentions](https://herculeradar.com/docs/reference/list_mentions)
- [get\_mention](https://herculeradar.com/docs/reference/get_mention)
- [update\_mention\_status](https://herculeradar.com/docs/reference/update_mention_status)
- [get\_mention\_analytics](https://herculeradar.com/docs/reference/get_mention_analytics)

Alerts

- [list\_alerts](https://herculeradar.com/docs/reference/list_alerts)
- [create\_alert](https://herculeradar.com/docs/reference/create_alert)
- [delete\_alert](https://herculeradar.com/docs/reference/delete_alert)

Usage

- [get\_usage](https://herculeradar.com/docs/reference/get_usage)

# REST API

15 capabilities. Each one is also an MCP tool of the same name.

## Conventions

- Base URL `https://herculeradar.com/api/v1`, JSON in and out, ISO 8601 UTC timestamps.
- Every success returns `{ data, meta }`; every failure returns `{ error }`.
- `meta.requestId` is echoed in the `x-request-id` header — quote it in support.
- `meta.docs` links to the page for that exact capability.
- An API key is scoped to one project, so no endpoint takes a project id.
- Lists page by `cursor`, never by offset.
- Writes accept `Idempotency-Key`; retries replay rather than duplicate.

## Envelope

```
{
  "data": { "…": "the resource" },
  "meta": {
    "capability": "list_mentions",
    "requestId": "req_9f2b4a8c1d0e",
    "idempotencyReplayed": false,
    "docs": "https://herculeradar.com/docs/reference/list_mentions"
  }
}
```

## Projects

A workspace holding monitors, mentions and alerts.

- [`list_projects`List projects`projects:read`](https://herculeradar.com/docs/reference/list_projects)
- [`create_project`Create a project`projects:write`](https://herculeradar.com/docs/reference/create_project)
- [`get_project`Retrieve a project`projects:read`](https://herculeradar.com/docs/reference/get_project)

## Monitors

A keyword set watched across one or more sources.

- [`list_monitors`List monitors`monitors:read`](https://herculeradar.com/docs/reference/list_monitors)
- [`create_monitor`Create a monitor`monitors:write`](https://herculeradar.com/docs/reference/create_monitor)
- [`update_monitor`Update a monitor`monitors:write`](https://herculeradar.com/docs/reference/update_monitor)
- [`delete_monitor`Delete a monitor`monitors:write`](https://herculeradar.com/docs/reference/delete_monitor)

## Mentions

A collected public post with its AI classification.

- [`list_mentions`List mentions`mentions:read`](https://herculeradar.com/docs/reference/list_mentions)
- [`get_mention`Retrieve a mention`mentions:read`](https://herculeradar.com/docs/reference/get_mention)
- [`update_mention_status`Update mention status`mentions:write`](https://herculeradar.com/docs/reference/update_mention_status)
- [`get_mention_analytics`Mention analytics`mentions:read`](https://herculeradar.com/docs/reference/get_mention_analytics)

## Alerts

A rule that pushes matching mentions to email or a webhook.

- [`list_alerts`List alert rules`alerts:read`](https://herculeradar.com/docs/reference/list_alerts)
- [`create_alert`Create an alert rule`alerts:write`](https://herculeradar.com/docs/reference/create_alert)
- [`delete_alert`Delete an alert rule`alerts:write`](https://herculeradar.com/docs/reference/delete_alert)

## Usage

Quota consumption and measured provider cost.

- [`get_usage`Plan usage and cost`usage:read`](https://herculeradar.com/docs/reference/get_usage)

[HerculeRadar](https://herculeradar.com/)

AI that watches the internet for your business.

in

[Use cases](https://herculeradar.com/use-cases)

- [Customer support](https://herculeradar.com/use-cases/customer-support)
- [Product feedback](https://herculeradar.com/use-cases/product-feedback)
- [Testimonials](https://herculeradar.com/use-cases/testimonials)
- [Social selling](https://herculeradar.com/use-cases/social-selling)
- [Competitor monitoring](https://herculeradar.com/use-cases/competitor-monitoring)
- [PR monitoring](https://herculeradar.com/use-cases/pr-monitoring)
- [Reputation management](https://herculeradar.com/use-cases/reputation-management)
- [Agencies](https://herculeradar.com/use-cases/agencies)
- [Brand monitoring](https://herculeradar.com/use-cases/brand-monitoring)
- [Launches](https://herculeradar.com/use-cases/launch-monitoring)

[Sources](https://herculeradar.com/listening)

- [X monitoring](https://herculeradar.com/listening/x)
- [Reddit monitoring](https://herculeradar.com/listening/reddit)
- [YouTube monitoring](https://herculeradar.com/listening/youtube)
- [LinkedIn monitoring](https://herculeradar.com/listening/linkedin)
- [Threads monitoring](https://herculeradar.com/listening/threads)

Developers

- [Pricing](https://herculeradar.com/#pricing)
- [Documentation](https://herculeradar.com/docs)
- [OpenAPI 3.1](https://herculeradar.com/openapi.json)
- [llms.txt](https://herculeradar.com/llms.txt)
- [Privacy](https://herculeradar.com/privacy)
- [Terms](https://herculeradar.com/terms)

My projects

- [![](https://herculeradar.com/projects/metricmap.ico)MetricMap](https://metricmap.app/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "Affiliate analytics — every click, conversion and commission in one map.")
- · [![](https://herculeradar.com/projects/reelsradar.ico)ReelsRadar.io](https://reelsradar.io/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "Find the short-form videos taking off before everyone else does.")
- · [![](https://herculeradar.com/projects/videototext.png)VideoToText](https://videototext.click/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "Turn any video into a transcript you can search and quote.")
- · [![](https://herculeradar.com/projects/commenthunter.ico)CommentHunter.click](https://commenthunter.click/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "Find the comment threads where your product belongs.")
- · [![](https://herculeradar.com/projects/humantext.png)HumanText.click](https://humantext.click/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "Rewrite AI drafts into something a person would actually send.")
- · [![](https://herculeradar.com/projects/kpiboard.png)KpiBoard.io](https://kpiboard.io/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "One board for the handful of numbers that decide the week.")
- · [![](https://herculeradar.com/projects/postroutine.ico)PostRoutine.io](https://postroutine.io/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "Publish on a schedule you can keep, across every network.")
- · [![](https://herculeradar.com/projects/viralclone.ico)ViralClone.click](https://viralclone.click/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "Take what worked once and make it work again.")
- · [![](https://herculeradar.com/projects/seoroutine.ico)SeoRoutine.com](https://seoroutine.com/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "SEO work broken into a routine instead of a project.")
- · [![](https://herculeradar.com/projects/heritagecars.ico)HeritageCars](https://heritagecars.online/?utm_source=herculeradar.com&utm_medium=referral&utm_campaign=footer "Classic cars, catalogued properly.")

© 2026HerculeRadar. Public data only. [Built by![](https://pbs.twimg.com/profile_images/1933039915337408512/D98C7Znz_400x400.jpg)Max Hamal](https://x.com/maksgamal)