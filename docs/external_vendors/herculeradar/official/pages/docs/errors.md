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

# Errors & limits

Built so an agent can retry safely and know when not to.

## Error envelope

Every failure returns the same shape, on REST and MCP alike:

```
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request failed validation",
    "requestId": "req_9f2b4a8c1d0e",
    "docs": "https://…/docs/reference/create_monitor",
    "details": [\
      { "path": "keywords", "message": "Array must contain at least 1 element(s)" }\
    ]
  }
}
```

`requestId` is also returned in the `x-request-id` header — quote it and we can find the exact call. `docs` links to the capability that failed.

## Codes

| Status | Code | Meaning |
| --- | --- | --- |
| `400` | `VALIDATION_ERROR` | Malformed or invalid input. \`details\` names the offending fields. |
| `401` | `UNAUTHORIZED` | Missing, expired or revoked credentials. |
| `402` | `USAGE_LIMIT` | Plan quota exhausted. Collection pauses; reads keep working. |
| `403` | `FORBIDDEN` | The credential lacks the scope this capability needs. |
| `404` | `NOT_FOUND` | Missing, or in a project this credential cannot reach. |
| `409` | `CONFLICT` | Idempotency mismatch, or a duplicate write still in flight. |
| `429` | `RATE_LIMIT` | Too many calls. Honour \`retryAfter\`. |
| `500` | `INTERNAL_ERROR` | Our fault. Safe to retry a keyed write. |

## Idempotency

Send a unique `Idempotency-Key` header (8–128 characters) on every write. A completed response is replayed for 24 hours, so a retry after a network timeout cannot create a second monitor.

- Same key, same body → the stored response is replayed.
- Same key, different body → `409 CONFLICT`; the caller is confused.
- Same key, still running → `409 CONFLICT`, so racing retries cannot both write.
- A failed write releases its key, so the caller can genuinely retry.

## Retry rule

Retry `429` and `5xx` with exponential backoff and jitter. Never retry `400` unchanged — it will fail identically. Only retry writes that carry the same idempotency key and identical input.

## Rate limits

| Plan | Requests per minute |
| --- | --- |
| Trial | 30 |
| Solo | 60 |
| Team | 180 |
| Agency | 600 |

Limits are per project, and every key and connection for a project shares one bucket, so minting more keys does not raise the ceiling.

## Quota

Quota applies to collection, not to reads. When a project reaches its limit new mentions stop being stored and writes that would collect more return`402 USAGE_LIMIT` — existing data stays fully readable. We never bill overage automatically.

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