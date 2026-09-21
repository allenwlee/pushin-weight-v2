# Pushin Weight

Version: v0.2.0-beta.1 (package `0.2.0b1`)
Last updated: 2026-09-21 12:39:30 JST

Pushin Weight monitors public X posts about the AI models, labs, and tools we
track. It collects posts, preserves source context, translates them into
English, Simplified Chinese, and Japanese, classifies each brand mention, and
shows the resulting feed, charts, and per-brand trend narratives in a Django
web application.

## Current production shape

The supported stack is one Django application on Render:

| Area | Current implementation |
| --- | --- |
| Web | Django, Gunicorn, WhiteNoise, Google OAuth |
| Database | Managed PostgreSQL; Django models and migrations are authoritative |
| Harvest | One Render cron running `python manage.py run_cycle` every 15 minutes |
| External collection | TwitterAPI.io, with separate scheduled and on-demand credentials |
| Enrichment | DeepInfra direct routes: DeepSeek V4 Flash 0731 for classification and Gemma 4 31B IT Turbo for translation/commentary |
| Headlines | Queue-isolated Celery worker and broker; never used for harvesting or scheduling |
| Supported locales | `en`, `zh-cn`, `ja` |

The deployed product release is tagged `v0.2.0-beta.1` and corresponds to
product commit `98dee23eda0e5c47b5a39f9c4a384c981285a1e1`. Documentation-only
release metadata is kept in Git and does not change the deployed product.

## Enrichment and classification

Each at-most-20-post classifier batch makes two concurrent, disjoint calls to
the selected DeepSeek 0731 transport. The content role assigns post types,
Audience Topics, and post-level Untracked Brand Promotions. The brand role
assigns product labels, sentiment, geopolitical modes, and China/US national
stance for each attributed brand. The roles are merged only after both
responses pass the versioned v4 contract; there is no reviewer or repair call
in the production topology.

The current post types are releases/updates, hands-on usage, results analysis,
questions/requests, advertising/marketing, events, opportunities, job
listings, personnel changes, opinions/reactions, research explanations,
business/finance, news reporting, and other. The seven Audience Topics are
local inference, cost/performance, model distillation, evaluations/benchmarks,
openness/licensing, agents/tools, and API/developer surface. Product labels
are bug, complaint, testimonial, ideas/requests, and investigate claim.
Historical rows remain readable through compatibility versions; they are not
silently reclassified.

## Harvest workflow

The cycle planner builds seven TwitterAPI.io calls: one curated account-list
call, three wide brand-net calls, and three co-occurrence calls. A cycle plans
queries from `config/harvest_policy.yaml` and `config.yaml`, fetches pages with
bounded retries, deduplicates posts, attributes brands, and persists the
result through Django transactions. Metrics refresh is a one-shot delayed
lookup for eligible posts; it is not a second scheduler.

See [TwitterAPI call inventory](docs/reference/twitterapi-io-calls.md) and
[live query composition](docs/reference/twitterapi-live-queries-by-model.md)
for the current call contract.

## Trend narratives

The headline worker builds a read-only PostgreSQL dossier, ranks candidate
facts, edits a trilingual narrative, and runs a semantic critic before
publishing a saved brand narrative. The public DTO contains rendered text and
approved evidence only; provider packets, credentials, internal ranks, and
critic details remain server-side. See
[trend narrative reference](docs/reference/headline-trend-narratives.md).

## Local development

```bash
python manage.py runserver 0.0.0.0:8000
python manage.py run_cycle --dry-run --limit-per-call 20
pytest
python manage.py check --deploy
```

Use the repository's `.env`/secret management for credentials. Never commit
API keys or database URLs. The historical SQLite file, if present, is
read-only reference data; it is not a production database.

## Reference documentation

- [TwitterAPI calls](docs/reference/twitterapi-io-calls.md)
- [Live queries by model](docs/reference/twitterapi-live-queries-by-model.md)
- [Database schema](docs/reference/db-schema.md)
- [Lookup tables](docs/reference/lookup-tables.md)
- [Classifier prompts](docs/reference/classifier-prompts.md)
- [Trend narratives](docs/reference/headline-trend-narratives.md)
- [Render deployment runbook](docs/deploy/render.md)

## Current operational limits

Provider calls can remain in retryable pending state after a cycle and are
reclaimed by later cycles. This is normal queue state; it does not change the
persisted taxonomy or schema contract. Provider availability, credit balance,
and live harvest counts are runtime facts and are intentionally not asserted
as static README guarantees.

Last reviewed: 2026-09-21 12:39:30 JST — Snapshot reconciled with the v2
Django/Render stack, current taxonomy v4, DeepInfra enrichment routes, query
planner, and release metadata. Runtime-only provider queue state remains
outside this static overview.
