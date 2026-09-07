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

get · mentions:read

# Retrieve a mention

Full text plus AI classification for one mention.

Read onlyIdempotent

## REST

get`/api/v1/mentions/{id}`

```
curl "https://herculeradar.com/api/v1/mentions/:id" \
  --header "Authorization: Bearer hr_live_…"
```

## MCP

Tool name `get_mention`. It takes the same input and returns the same `{ data, meta }`envelope as REST, because both call the same function.

Fetch one mention in full, with its AI classification and a link to the original post.

## Parameters

|     |     |     |
| --- | --- | --- |
| idrequired | string | Mention id |

## Response

```
{
  "data": {
    "id": "7b0f1e3a-1c4d-4a0a-9f2b-2f4a8c1d0e11",
    "source": "reddit",
    "url": "https://reddit.com/r/SaaS/comments/abc123",
    "author_handle": "ops_kate",
    "text": "Our analytics bill tripled. Anyone know a cheaper alternative?",
    "published_at": "2026-09-01T09:14:00.000Z",
    "engagement": {
      "upvotes": 128,
      "comments": 41
    },
    "is_relevant": true,
    "category": "complaint",
    "sentiment": "negative",
    "urgency": 72,
    "ai_summary": "User is priced out of a competitor and asking for alternatives.",
    "status": "new"
  },
  "meta": {
    "capability": "get_mention",
    "requestId": "req_9f2b4a8c1d0e",
    "idempotencyReplayed": false,
    "docs": "https://herculeradar.com/docs/reference/get_mention"
  }
}
```

## Authorization

Requires the `mentions:read` scope. A credential without it gets `403 FORBIDDEN`. Resources in projects the credential cannot reach answer`404 NOT_FOUND` rather than 403, so ids cannot be probed across tenants.

[REST conventions](https://herculeradar.com/docs/api) [MCP setup](https://herculeradar.com/docs/mcp) [Errors & limits](https://herculeradar.com/docs/errors)

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