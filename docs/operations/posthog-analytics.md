# PostHog site analytics

PostHog records visits to the public homepage and brand pages, so operators can see traffic and usage. It also provides a small server helper for approved events. It is independent of prediction, MCP and harvesting work.

## Normal workflow

Configure the project token, region and environment on the intended web service, then enable analytics. Public pageviews run automatically without a consent cookie or an opt-in control. Do Not Track and Global Privacy Control suppress tracking. The owner selected this behavior for the production activation on October 8, 2026.

Signed-in browsers use `pushinweight:user:<Django-user-pk>`. The next tracked public page resets identity after logout or an account switch. Email, name, page text, query parameters, fragments, filters and authentication URLs are excluded. Automatic click collection, session replay, surveys, flags and error capture are off. The SDK retains its bot filter.

## Application configuration

| Variable | Value |
| --- | --- |
| `POSTHOG_ENABLED` | `False` by default; set `True` only for the chosen activation. |
| `POSTHOG_PROJECT_TOKEN` | Public capture token from the intended project. |
| `POSTHOG_REGION` | `us` or `eu`; controls the allowed ingestion host. |
| `POSTHOG_ENVIRONMENT` | `development`, `test`, `staging` or `production`; empty disables analytics. |

The operator store on fuchitalee currently holds the capture token as `POSTHOG_API_KEY` and the private management key as `POSTHOG_PERSONAL_API_KEY`. Map the capture token to `POSTHOG_PROJECT_TOKEN` in the application environment. The application reads its checkout `.env` and process environment; it does not load `~/.env.secrets`. Parse only the required literal assignments for operator commands; never execute, print or copy the entire store.

`POSTHOG_PERSONAL_API_KEY` is exclusively for project-scoped dashboard management and queries. Never put it in browser configuration or the web service. The initially verified account uses US project 652560, named Default project. Project-scoped keys support `/api/projects/652560/` (or `/api/projects/@current/` when checking the selected project); the collection endpoint `/api/projects/` rejects scoped-project keys.

## Captured data

The response middleware adds a JSON bootstrap and `/static/pw-analytics.js` only to complete public HTML responses. Private, authentication, admin, internal, API and HTMX responses are excluded. It preserves the templates owned by other workstreams. Cookie and tracking-preference headers vary responses; injected responses are private to prevent cross-account caching.

The JavaScript `before_send` hook permits only `$pageview` and `$identify`, preserving required ingestion/identity fields and SDK metadata. Pageviews contain the origin and path with no query or fragment, plus `environment`, `channel=web` and `is_test`. Profile property updates are removed. GeoIP enrichment is disabled; this does not imply that an HTTP service cannot observe connection IP addresses.

Server events use a lazy process-local Python SDK client with a 100-event analytics queue, one analytics sender, a two-second HTTP timeout and one retry. The helper returns whether an event was queued; this is not delivery proof. It never flushes during a web request. Application failure logs include only error types. A filter replaces vendor SDK messages with their severity so raw response bodies, keys and payloads cannot enter those logs.

```python
from project.analytics import capture

capture(
    "analytics setup test",
    distinct_id="setup:<run-uuid>",
    properties={"setup_run_id": "<run-uuid>"},
)
```

Only `analytics setup test` is registered initially, and it is always marked `is_test=true`, including in a production environment. Other workstreams may register reviewed domain events later. Free-form metadata is ignored; the initial helper permits only a bounded setup run ID and fixed environment/channel flags. `user_id=<Django-user-pk>` uses the matching browser identity when an approved event requires it. Short-lived operator processes may explicitly flush with a time budget, then shut down.

## Verification

Prepare a disposable PostgreSQL database and download the current official browser SDK to `.pytest-tmp/posthog-sdk/array.js`. This fixture executes the real SDK without sending test-suite traffic to PostHog:

```sh
mkdir -p .pytest-tmp/posthog-sdk
curl --fail --silent --show-error https://us-assets.i.posthog.com/static/array.js -o .pytest-tmp/posthog-sdk/array.js
uv run --extra dev playwright install chromium
DATABASE_URL=postgresql://<local-test-role>@127.0.0.1:<test-port>/<test-db> \
  uv run --extra dev pytest tests/test_posthog_analytics.py tests/test_posthog_analytics_browser.py \
  --basetemp=.pytest-tmp/posthog-tests
```

The browser tests exercise the real homepage without a consent cookie, Django sessions and logout endpoint, both identity transitions, disabled configuration, browser preferences and SDK failure. The positive fixture represents an ordinary browser with a normal user agent, client hints and `webdriver=false`; a separate unmodified automation fixture verifies bot suppression. All test-suite events remain intercepted and marked as test traffic. No required browser tests may be skipped.

For live verification, send one labeled test pageview and one bounded server setup event, then query their actual records. A capture endpoint HTTP 200 or a queued SDK event alone does not establish ingestion. Use the query API's `refresh=force_async` when a synchronous query times out; poll its returned ID within a fixed time budget. Keep setup receipts and test traffic distinct from deployed production evidence.

## Activation and rollback

The [PushinWeight traffic and usage dashboard](https://us.posthog.com/project/652560/dashboard/2184992) has five tiles: production pageviews, visitors, signed-in visitors, public paths and a separate setup verification table. The setup table uses the actual two labeled records from the initial verification. The existing onboarding dashboard is preserved.

Production dashboard series filter `environment=production` and `is_test=false`; setup traffic is shown separately. The owner authorized direct production deployment with tracking enabled and no opt-in requirement. Disable capture by setting `POSTHOG_ENABLED=False`; the middleware and server helper become inert.

## References

- [Browser configuration](https://posthog.com/docs/libraries/js/config)
- [Python SDK](https://posthog.com/docs/libraries/python)
- [Identity](https://posthog.com/docs/product-analytics/identify)
- [API overview](https://posthog.com/docs/api)
- [Personal API keys](https://posthog.com/docs/api/personal-api-keys)
