# TwitterAPI.io call inventory

Version: v0.2.0-beta.1 (v2 Django/Render)
Last updated: 2026-09-21 12:39:30 JST

Pushin Weight uses TwitterAPI.io as its cookie-free X data provider. The v1
Flask/launchd/Apify stack is retired. The scheduled Render cron runs the
Django cycle every 15 minutes; explicitly launched probes, backfills, and
reconciliations use the separate on-demand credential.

## Credentials and transport

| Item | Current value |
| --- | --- |
| Base URL | `https://api.twitterapi.io` |
| Method | `GET` with query parameters |
| Authentication | `X-API-Key: <key>` |
| Scheduled key | `TWITTERAPI_IO_SCHEDULED_API_KEY` |
| On-demand key | `TWITTERAPI_IO_ON_DEMAND_API_KEY` |
| Cursor | Persisted per call/brand bucket in `call_state` |
| Persistence | Django transactions into managed PostgreSQL |

Callers select a purpose explicitly and never fall back to the other key or a
retired unsuffixed variable.

## Seven-call harvest cycle

| Call | Kind | Current role |
| --- | --- | --- |
| A | account | Curated X-list fan-in for official/staff and high-value accounts |
| B1 | brand-wide | Wide bare-name/alias net for top-presence brands |
| B2 | brand-wide | Handle-focused net for top-presence brands |
| B3 | brand-wide | Handle-focused net for the remaining handle brands |
| C1–C3 | brand-wide | Co-occurrence packs for the remaining brands and model terms |

The exact query strings, enabled models, list ID, lengths, headroom, and
brand-to-call coverage are generated in
[`twitterapi-live-queries-by-model.md`](twitterapi-live-queries-by-model.md).
The planner reads `config/harvest_policy.yaml` and `config.yaml`; it does not
read retired per-brand query files.

## Endpoints

- `GET /twitter/tweet/advanced_search` — paginated harvest workhorse.
- `GET /twitter/article` — long-form X article body when required by the
  fetched item.
- `GET /twitter/user/info` — profile lookup for account enrichment.
- `GET /twitter/user/followers` — bounded follower pages for approved
  reconciliation jobs.
- `GET /twitter/tweets` — one-shot by-ID metrics refresh and targeted lookup.
- `GET /twitter/tweet/quotes` — explicitly launched quote lookup; not a
  continuous harvest loop.
- `GET /twitter/list/members` — curated-list roster reconciliation.

The cycle's metrics refresh is a one-shot by-ID lookup after the configured
delay for posts not previously refreshed. It does not run a second scheduler.

## Fetch, attribution, and persistence

1. `monitor/cycle.py` plans calls and resumes each persisted cursor with the
   configured overlap.
2. The fetcher follows bounded pages and retry/backoff rules, records request
   outcomes, and stops at the cycle deadline.
3. Brand attribution uses the configured aliases, handles, keywords, and
   model names. Account-list provenance and query IDs are retained.
4. Django persistence deduplicates by tweet ID, writes post/account snapshots,
   records mentions and brand edges, and queues translation/classification
   enrichment.

The harvest call itself only supplies source data; classification and
translation are separate enrichment work and do not change TwitterAPI credit
accounting.

## Credit and failure boundaries

The repository records request counts, page/cursor state, and sanitized
failure telemetry. Provider pricing and actual credit consumption are runtime
facts from TwitterAPI.io and are not hard-coded as guarantees here. A retryable
provider failure leaves work eligible for a later cycle; it does not create a
second scheduler or silently switch credentials.

## Sources

- `monitor/cycle.py` and `monitor/management/commands/run_cycle.py`
- `x_monitor/apify.py` (TwitterAPI.io client and endpoint wrappers)
- `x_monitor/queries.py`, `x_monitor/query_plan.py`, and
  `x_monitor/harvest_policy.py`
- `config.yaml` and `config/harvest_policy.yaml`
- `scripts/harvest_cost/` for read-only cost reporting
- `core/models.py` for cursor, post, account, and provenance tables

Last reviewed: 2026-09-21 12:39:30 JST — Reconciled the v2 scheduler,
credential split, seven-call shape, endpoint set, cursor persistence, and
metrics-refresh boundary. Exact query composition remains generated in the
companion reference; live provider credit totals remain runtime-only.
