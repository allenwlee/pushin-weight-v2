# Pushin Weight

Version: v0.2.0-beta.1 (package `0.2.0b1`)
Last updated: 2026-09-21 12:39:30 JST

> Pushin Weight watches public X posts about the AI models, labs, and tools
> tracked by the product. It collects source posts, preserves context,
> translates them into English, Simplified Chinese, and Japanese, classifies
> each brand mention, and publishes feeds, charts, and per-brand narratives.

## Architecture at a glance

The supported production stack is the v2 Django application on Render. The
legacy Flask, launchd, Apify, and writable SQLite paths are retired.

| Area | Current implementation |
|---|---|
| Web | Django + Gunicorn + WhiteNoise on Render, behind Google OAuth |
| Database | Managed PostgreSQL; Django models and migrations are authoritative |
| Harvest | One Render cron running `python manage.py run_cycle` every 15 minutes |
| Collection | TwitterAPI.io with scheduled and on-demand credentials |
| Enrichment | DeepInfra direct routes: DeepSeek V4 Flash 0731 classifier; Gemma 4 31B IT Turbo translation and post synthesis |
| Headlines | Queue-isolated Celery worker and broker; never harvests or schedules |
| Locales | `en`, `zh-cn`, and `ja` |

The deployed product release is `v0.2.0-beta.1`, product SHA
`98dee23eda0e5c47b5a39f9c4a384c981285a1e1`. Documentation-only metadata is
kept in Git with `[skip render]` and does not redeploy the product.

---

## Production (Django/Render) -- v2

The v2 stack runs on Render as a web service, one scheduled harvest cron,
managed PostgreSQL, and optional queue-isolated headline worker/broker
resources. The web service serves the dashboard behind Google OAuth. The
Render cron is the only scheduler.

```
Render (cloud)

+----------------------+       +------------------+
| Django web service   |       | PostgreSQL       |
| Google OAuth         |-------| managed database |
+----------+-----------+       +------------------+
           |
+----------v-----------+       +------------------+
| 15-minute harvest    |       | headline worker  |
| Render cron          |       | queue + broker   |
+----------------------+       +------------------+
```

**Current boundaries:**
- **Database:** PostgreSQL with Django ORM migrations generated from
  `core/models.py`; the old SQLite schema is read-only historical state.
- **Auth:** Google OAuth via django-allauth on dashboard routes.
- **Harvest:** The Render cron invokes `monitor/cycle.py` every 15 minutes;
  Celery beat is not a production scheduler.
- **Enrichment:** Post translation, synthesis, classification, and targeted
  extraction are persisted through Django-owned state and attempt tables.
- **Deployment:** `render.yaml` describes the web, cron, database, and
  optional queue-isolated headline resources.

### Django project layout

```
project/          Django project (settings, urls, wsgi/asgi, Celery app)
core/             App #1: models + migrations (source of truth for schema)
monitor/          App #2: dashboard views + harvest management commands
manage.py         Django CLI entry point
render.yaml       Render Blueprint (infrastructure-as-code)
Procfile          Render start command
build.sh          Render build script
.env.example      Env var template for local dev
```

### Quickstart (local Django dev)

```bash
cd /Users/fuchitalee/development/pushin-weight-v2

# 1. Python env
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. PostgreSQL (local)
createdb xmonitor -U xmonitor
# or via Docker: docker run -d --name xmonitor-pg -e POSTGRES_USER=xmonitor \
#   -e POSTGRES_PASSWORD=xmonitor -e POSTGRES_DB=xmonitor -p 5432:5432 postgres:16

# 3. Real secrets -- copy from .env.example and fill in values
cp .env.example .env
# Edit .env with your API keys (TWITTERAPI_IO_SCHEDULED_API_KEY,
# TWITTERAPI_IO_ON_DEMAND_API_KEY, DEEPINFRA_API_KEY,
# GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)

# 4. Apply migrations
python manage.py migrate

# 5. Seed the curated base layer (brands, companies, roles, known accounts)
python manage.py load_seed
python manage.py seed_i18n_labels

# 6. Smoke-test the harvest cycle
python manage.py run_cycle --dry-run --limit-per-call 20

# 7. Run the dev server
python manage.py runserver 0.0.0.0:8000
# Open http://localhost:8000/accounts/login/ (Google OAuth)
```

### Management commands

All commands are invoked via `python manage.py <command>` (or `manage.py`
directly if executable).

| Command | Purpose |
|---|---|
| `run_cycle` | Run one harvest cycle (fetch + filter + attribute + classify + persist). Supports `--dry-run`, `--async` (Celery), `--json`, `--brands`, `--limit-per-call`, `--skip-fetch`, `--max-pages-per-call`. |
| `load_seed` | Seed the curated base layer: 21 enabled brands, companies, roles, and known accounts. Idempotent (get_or_create). |
| `seed_i18n_labels` | Seed post types, product labels, Audience Topics, sentiment, geopolitical, national stance, role, and locale labels for en/zh-cn/ja. |
| `validate_cycle` | Compare a legacy run summary against PG state or another run summary. Exits 0 only when all metrics are within `--tolerance-pct` (default 5%). Used during the battle-test protocol. |
| `migrate` | Apply pending Django migrations (standard Django built-in). |
| `createsuperuser` | Create a Django admin user (for `/admin/` and local testing). |

### Render deployment and local operations

Production is defined by render.yaml and docs/deploy/render.md. The web service
and the single scheduled harvest cron are the required services. Headline
worker/broker resources are queue-isolated and never run harvesting or beat.

The deployed product is tag `v0.2.0-beta.1`. Documentation-only commits
carry `[skip render]`; a documentation push does not redeploy the product.

Useful commands:

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py load_seed
python manage.py seed_i18n_labels
python manage.py run_cycle --dry-run --limit-per-call 20
```

## What this is

Built for product, research, developer-relations, and financial-analysis
readers who need to understand the AI model market. The current enabled
catalog contains 21 model/tool entries:

```
minimax  qwen  deepseek  glm  mimo  moonshot_kimi  inclusionai  mistral
stepfun  ernie  hunyuan  llama  nemo_megatron  doubao  yi  sensechat
exaone  kuaishou  sakana_ai  upstage  dots
```

The application has four cooperating paths:

1. **Harvest** plans seven TwitterAPI.io calls, follows cursors and bounded
   retries, deduplicates source posts, attributes brands, and persists the
   source/account snapshots.
2. **Enrichment** translates posts, generates trilingual commentary, runs the
   two-role classifier, and records targeted jobs, people, events, and
   opportunities.
3. **Presentation** serves locale-aware feeds, charts, filters, account
   context, and the current taxonomy through Django views and JSON DTOs.
4. **Headlines** builds bounded per-brand trend narratives asynchronously in
   the queue-isolated headline worker.

## Harvest and enrichment flow

The cycle planner creates one curated account-list call, three wide brand-net
calls, and three co-occurrence calls. The exact enabled models, aliases,
handles, call lengths, and query strings are generated in the companion
TwitterAPI reference. Each call records its cursor and completion state in
PostgreSQL, so a later cycle can resume without replaying the whole window.

Fetched posts are filtered and attributed before enrichment. A post mentioning
multiple brands creates independent brand edges; classification does not copy
advertising, sentiment, results, or national stance from one brand to another.
Translation preserves source line breaks. Commentary adds an explanation in
English, Simplified Chinese, and Japanese. Failed provider attempts remain in
bounded retry state and are reclaimed by subsequent cycles.

The enrichment database separates source observations from interpretation:
posts and account snapshots preserve what X supplied; classification states,
signals, topics, product labels, geopolitical modes, and promotion evidence
preserve the current interpretation; people, affiliations, job listings,
events, opportunities, and extraction attempts preserve targeted intelligence.

---

## Pushin' Weight home pages (PW)

The dashboard's user-facing surface. Two pages, one design system. The
full UI guide lives at `docs/reference/home-pages-ui-guide.md` — this
section is the abbreviated overview.

### Multi-brand home (`/`)

- **Top-left (2/3 width)**: combo line chart, one line per brand,
  accent colors per the `--role-*` CSS tokens. X-axis = time (1d hourly,
  1w daily, 1m daily, 1y monthly); Y-axis = posts per period; hover
  tooltip per data point.
- **Top-right (1/3 width)**: control panel with checkbox groups for
  brands, post types, Audience Topics, product labels, sentiment,
  geopolitical modes, account role, national stance, and Untracked Brand
  Promotions. Default = all on. Filter changes
  propagate to both chart and feed.
- **Bottom half**: infinite-scroll feed (cursor-paginated). Columns:
  datetime, brand chips, translated text (subscript lang), original
  text (parallel column for QA), classification pills (post type, topic,
  product label, sentiment, geopolitical mode, promotion), and account
  handle + role
  pill.

### Single-brand home (`/<company>/<brand>`)

- Same control panel and feed as multi-brand.
- The chart becomes an area chart with **tabs** for post type, Audience Topic,
  product label, sentiment, geopolitical mode, national stance, and account
  role. Each tab
  shows the distribution of categories for the chosen dimension.

### Locale toggle (top right of topbar)

`zh-cn` (default) / `en` / `ja` / `original`. Drives both the feed translation
column and brand chip display names. The locale cookie is set via
`POST /api/v1/home.locale/<locale>`.

### File pointers

| File | What |
|---|---|
| `monitor/templates/monitor/home.html` | Multi-brand page shell |
| `monitor/templates/monitor/brand_home.html` | Single-brand page shell |
| `monitor/templates/monitor/_home_chart.html` | Multi-brand chart partial |
| `monitor/templates/monitor/_brand_chart.html` | Single-brand chart partial |
| `monitor/templates/monitor/_feed_initial_v22.html` | Feed initial render |
| `monitor/static/pw-chart.js` | Chart and filter behavior |
| `x_monitor/_home_routes.py` | Route handlers (separated from `dashboard.py` for readability) |
| `x_monitor/static/pw-chart.js` | Multi-brand chart renderer |
| `x_monitor/static/pw-brand-chart.js` | Single-brand chart renderer |
| `x_monitor/static/pw-feed.js` | Feed cursor loader + bottomless scroll |
| `x_monitor/static/pw-filter-store.js` | Client-side filter state |
| `x_monitor/static/pw-locale-toggle.js` | Locale toggle button + cookie sync |
| `x_monitor/static/dashboard.css` | Shared stylesheet (incl. `--pt-*`, `--nat-*`, `--role-*` color tokens) |

UI reference: `docs/reference/home-pages-ui-guide.md` — element names,
DOM hooks, payload shapes for each pane.

`headline-state` and `headline-item-state` are display elements, not database columns. Their text comes from a projected `state_label`; the underlying state is calculated for every chart response.

## Generation path

1. The chart builder calls `project_trend_narrative()` with the selected window and brands in [`monitor/views.py`](monitor/views.py).
2. The projection finds the visible run for that window in `trend_narrative_visible_runs`, then loads its per-brand records from `brand_trend_narratives`.
3. Each brand’s persisted status, `verified_at`, and `last_good` are converted into an item state by [`_per_brand_item()`](monitor/trend_narrative_projection.py).
4. The overall headline state is calculated from the displayed item states by [`_v3_projection()`](monitor/trend_narrative_projection.py).
5. The template prints:

   - `trend_narrative.state_label` into `.headline-state`
   - `item.state_label` into `.headline-item-state`

   See [`monitor/templates/monitor/home.html`](monitor/templates/monitor/home.html).

## `headline-item-state` possibilities

These are the actual per-brand UI states:

| State | Display label | Meaning |
|---|---|---|
| `available` | Available / 可用 | The persisted outcome is `approved`, and its `verified_at` time is still inside the freshness limit. |
| `stale` | Stale · last verified… / 过期 · 上次验证于… | Either an approved narrative exceeded its freshness limit, or the latest attempt was held and the previous `last_good` narrative is being served. |
| `unavailable` | Unavailable / 暂不可用 | No outcome exists, or the latest outcome does not contain a publishable narrative. This includes persisted `prepared` or `unavailable` outcomes. |
| `no_content` | No content / 无内容 | Source coverage was complete, but the brand had no posts in that window. This is a valid terminal result, not a processing failure. |
| `data_quality_unavailable` | Data unavailable / 数据不完整 | Source coverage or underlying data was incomplete, so the system deliberately made no trend claim. |

The labels are defined in [`monitor/trend_narrative_projection.py`](monitor/trend_narrative_projection.py).

The browser validator also accepts `disabled` as an item state in [`monitor/static/pw-chart.js`](monitor/static/pw-chart.js), but the current server never emits a disabled item. When headline serving is disabled, it emits an empty item list and sets only the overall state to `disabled`.

## `headline-state` possibilities

This is the aggregate state for the entire headline strip:

| State | Display label | Meaning |
|---|---|---|
| `disabled` | Disabled / 已停用 | Headline serving is not active. No headline items are returned. |
| `unavailable` | Unavailable / 暂不可用 | There are no displayed items, or every displayed item is unavailable. |
| `available` | Available / 可用 | Every displayed item is available. |
| `stale` | Stale / 过期 | Every displayed item is stale. |
| `no_content` | No content / 无内容 | Every displayed item reports no content. |
| `data_quality_unavailable` | Data unavailable / 数据不完整 | Every displayed item reports insufficient source data. |
| `mixed` | Mixed / 混合状态 | The displayed items have different states—for example, one available and one stale. |

The aggregate rule is:

```text
no items             → unavailable
all items same state → that state
different states     → mixed
serving inactive     → disabled
```

The list and labels are defined in [`_v3_state_label()`](monitor/trend_narrative_projection.py).

## Persisted status list

The underlying database status has a different list, stored in `brand_trend_narratives.status` and defined by `BrandTrendNarrative.Status` in [`core/models.py`](core/models.py):

| Persisted status | Meaning |
|---|---|
| `prepared` | Intermediate outcome prepared but not approved for publication. Projects as `unavailable`. |
| `approved` | Verified, publishable narrative. Projects as `available` or `stale`, depending on age. |
| `held` | Latest narrative failed semantic review. If a `last_good` exists, that older narrative is served as `stale`; otherwise lifecycle code converts it to `unavailable`. |
| `unavailable` | No usable narrative could be produced. |
| `no_content` | Complete coverage, but no posts for the brand/window. |
| `data_quality_unavailable` | Data was insufficient or incomplete. |

Freshness limits are stored in [`config.yaml`](config.yaml):

| Window | Becomes stale after |
|---|---:|
| 1 day | 60 minutes |
| 7 days | 120 minutes |
| 30 days | 720 minutes |
| 365 days | 2,880 minutes |

So there is no single centralized list for everything: the persisted statuses live in the Django model, while the derived UI-state possibilities and labels live in `trend_narrative_projection.py`, with a mirrored acceptance list in `pw-chart.js`.

---

## Repository layout

```text
project/             Django settings, URLs, WSGI/ASGI, Celery app
core/                Django models and migrations
monitor/             Dashboard, harvest, enrichment, headline commands
x_monitor/           Provider clients, classifier, translator, compatibility
config.yaml          Committed runtime routes and limits
config/              Harvest policy and brand configuration
render.yaml          Render topology
docs/reference/      Current runtime contracts
docs/plans/          Delivery plans and receipts
tests/               Django, provider, browser, and contract tests
```

Django models and migrations are the production schema authority. The retired
Graphviz schema and legacy SQLite file are read-only historical artifacts.

## Operations and troubleshooting

- Run a dry cycle with `python manage.py run_cycle --dry-run --limit-per-call 20`.
- Run `python manage.py check --deploy` before a Render release.
- Run `pytest` for the complete regression suite.
- Use the Render CLI and the documented PostgreSQL route for production reads.
- The Render cron is the only production scheduler; do not reactivate legacy
  worker or beat services.
- Scheduled and on-demand TwitterAPI credentials are separate. Never silently
  substitute one for the other.
- Retryable enrichment remains pending for later cycles and is not a second
  scheduler.
- Classification, translation, synthesis, and headline status are exposed by
  their Django management commands and read-only status records.

## Where to look next

- [TwitterAPI call inventory](docs/reference/twitterapi-io-calls.md)
- [Live query composition](docs/reference/twitterapi-live-queries-by-model.md)
- [Database schema](docs/reference/db-schema.md)
- [Lookup tables](docs/reference/lookup-tables.md)
- [Classifier prompts](docs/reference/classifier-prompts.md)
- [Post commentary](docs/reference/commenter.md)
- [Post translation](docs/reference/translator-output.md)
- [Rare-type intelligence](docs/reference/rare-types.md)
- [Trend narrative contract](docs/reference/headline-trend-narratives.md)
- [Render deployment runbook](docs/deploy/render.md)
- Production database access is documented in the project memory and Render runbook.

## Retired artifacts

Launchd plists, the v1 Flask dashboard, Apify compatibility naming, writable
SQLite instructions, and the old Graphviz schema are not production paths.
They remain only as read-only compatibility evidence where required.

Last reviewed: 2026-09-21 12:39:30 JST — Detailed README reconciled with the
v2 Django/Render codebase, current release metadata, v4 taxonomy, current
enrichment routes, and queue-only headline topology.
