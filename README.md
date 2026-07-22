# x-monitor

Last updated: 2026-07-22-17:00:00

> A Flask dashboard + macOS background pipeline that watches X for posts
> about 20 AI model brands, classifies each post by discourse / sentiment /
> nationalism / role, and surfaces the conversation in two home pages.
>
> **v2 (in progress):** Django + PostgreSQL on Render with Google OAuth,
> Celery-based harvest, and full i18n. See [Production (Django/Render)](#production-djangorender)
> below for the new architecture. The legacy Flask/SQLite/launchd stack
> is still running in production — do NOT touch it during migration.

## Architecture at a glance

This repo contains **two stacks** running side-by-side during the v1-to-v2
migration, sharing the same `config.yaml` and `.env.secrets` but targeting
separate databases:

| Stack | Web | DB | Harvest | Auth | Status |
|---|---|---|---|---|---|
| v1 (Flask) | Flask + Jinja2 on :5000 | SQLite (`data/x_monitoring.db`) | 2 launchd agents | None (local) | **Live prod** |
| v2 (Django) | Django + WhiteNoise on Render | PostgreSQL (Render managed) | Celery beat + worker | Google OAuth | **In migration** |

**Do not touch the v1 launchd agents until the cutover is complete.**
See [Transitioning from legacy Flask](#transitioning-from-legacy-flask).

---

## Production (Django/Render) -- v2

The v2 stack runs on Render as three services (web, worker, beat) backed
by managed PostgreSQL and Redis. The web service serves the dashboard
behind Google OAuth; the worker + beat pair replaces the macOS launchd
agents, running the harvest cycle on the same 15-minute cadence.

```
Render (cloud)                              macOS (local -- legacy v1)
┌──────────────────────┐                    ┌───────────────────────┐
│ xmonitor-web         │                    │ launchd harvest       │
│ (gunicorn + Django)  │                    │ (every 15 min)        │
│                       │                    │                       │
│ xmonitor-worker       │    ┌─────────┐     │ launchd config-reload │
│ (Celery worker)      │────│  Redis  │     │ (on config.yaml edit) │
│                       │    └─────────┘     │                       │
│ xmonitor-beat         │                    │ SQLite                │
│ (Celery scheduler)    │────── PostgreSQL   │ data/x_monitoring.db │
└──────────────────────┘                    └───────────────────────┘
```

**Key differences from v1:**
- **Database:** PostgreSQL with Django ORM migrations instead of raw SQL
  files in `x_monitor/migrations/`. Migrations live in `core/migrations/`
  and are auto-generated from `core/models.py`.
- **Auth:** Google OAuth via django-allauth on all dashboard routes --
  no open-to-LAN Flask server.
- **Harvest:** Celery beat (15-min interval) replaces launchd heartbeat.
  The cycle runner (`monitor/cycle.py`) is the same logic ported to
  Django ORM.
- **Deployment:** `render.yaml` Blueprint auto-provisions the full
  service topology on first push.

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
# Edit .env with your API keys (TWITTERAPI_IO_API_KEY, ANTHROPIC_API_KEY,
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
| `load_seed` | Seed the curated base layer: 20 brands, companies, roles, known accounts. Idempotent (get_or_create). Supports `--dry-run`, `--brands a,b,c`, `--no-accounts`. |
| `seed_i18n_labels` | Seed the i18n label tables (post_type_labels, sentiment_labels, discourse_labels, nationalism_labels, role_labels) with known taxonomy values in en + zh-cn. Supports `--dry-run`. |
| `validate_cycle` | Compare a legacy run summary against PG state or another run summary. Exits 0 only when all metrics are within `--tolerance-pct` (default 5%). Used during the battle-test protocol. |
| `migrate` | Apply pending Django migrations (standard Django built-in). |
| `createsuperuser` | Create a Django admin user (for `/admin/` and local testing). |

### Bridge / port scripts

During the migration window, these scripts keep the v1 (SQLite) and v2
(PostgreSQL) data in sync:

| Script | Purpose |
|---|---|
| `scripts/bridge_sqlite_to_pg.py` | Incremental copy: reads the latest v1 run JSON from `data/runs/LATEST.json` and inserts matching rows into PostgreSQL via the Django ORM. Run after each successful legacy cycle. |
| `scripts/port_sqlite_to_django.py` | Historical bulk port: copies all rows from the legacy SQLite DB into PostgreSQL using the Django ORM. One-time operation before cutover. |

### Render deploy quick reference

```bash
# Infrastructure is defined in render.yaml -- Blueprint auto-provisions
# on first push to the Render-connected branch.

# Manual deploy steps (if not using Blueprint):
# 1. Create managed PostgreSQL (xmonitor-db)  in Render Dashboard
# 2. Create managed Redis (xmonitor-redis)    in Render Dashboard
# 3. Create web service from this repo with build.sh / Procfile
# 4. Create worker + beat services (Celery)
# 5. Set the xmonitor-secrets env group in Render Dashboard

# Full runbook: docs/deploy/render.md
```

### Transitioning from legacy Flask

**Do not touch launchd during migration.** The v1 pipeline must continue
harvesting to SQLite without interruption. The v2 stack (Django + PG +
Render) runs in parallel, consuming the same API keys but writing to its
own database.

When the battle-test protocol (see `docs/production-runbook.md`) confirms
v2 equivalence, the cutover proceeds in this order:

1. Operator approves v2 after 1-2 days of parallel running
2. `scripts/bridge_sqlite_to_pg.py` does the final incremental sync
3. Render cron job for harvest is verified active
4. launchd agents are unloaded (NOT deleted -- keep for rollback):
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.harvest.plist
   launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.config-reload.plist
   ```
5. Operator confirms the Render dashboard is serving live data

Rollback: re-load the launchd plists, point the dashboard back at the
SQLite DB. See `docs/production-runbook.md` for the full procedure.

---

## What this is

Built for MiniMax's developer relations team so they always know what the
public is saying about the 20 tracked brands:

```
minimax  qwen  deepseek  glm  mimo  moonshot_kimi  inclusionai  mistral
stepfun  ernie  hunyuan  llama  nemo_megatron  doubao  yi  sensechat
exaone  kuaishou  sakana_ai  upstage
```

Two surfaces to know about:

1. **The pipeline** (`x_monitor.run.RunPipeline`) — the backend that fetches,
   classifies, and persists posts every 15 min.
2. **The dashboard** (`x_monitor.dashboard.DashboardApp`) — a Flask app that
   serves the two Pushin' Weight home pages.

---

## Legacy (v1) — Flask + SQLite + launchd

> The sections below describe the **currently live production v1 stack**.
> This stack continues to run unchanged during the Django migration. All
> new development targets the v2 stack (see [Production (Django/Render)](#production-djangorender)).
> 
> The v1 pipeline, dashboard, deployment, and ops docs are preserved here
> for reference during the migration window. After cutover, these sections
> will be archived and replaced with v2 equivalents.

---

## The pipeline — `x_monitor.run.RunPipeline`

`RunPipeline` is the daily harvest orchestrator. One call = one cycle. A
cycle acquires `fcntl.flock` via `pipeline_lock`, so concurrent cycles
cleanly exit 0 with `degraded:already_running: true` rather than
double-spending the daily TwitterAPI.io budget.

Lifecycle of a cycle:

1. **Load config** — `x_monitor/config.py:load_config` parses `config.yaml`.
   Pydantic-validated; raise on unknown brand slug.
2. **Plan the call set** — `x_monitor/query_plan.py` produces the per-cycle
   call list. Three flavors of Twitter advanced-search calls:
   - **Call A** — `list:<x_monitor_list_id>` operator. Single wide-net
     query against the curated X list. Cheap, but list-only.
   - **Call B** — paren-grouped token union across `enabled_models` split
     into three `call_b_groups` (B1 global, B2 Chinese, B3 specialized).
     Six polysemous brands intentionally absent — covered by Call C.
   - **Call C** — per-spec advanced-search AND-filter from `x_query_specs`
     in `config.yaml`. Co-occurrence queries that disambiguate brands
     whose tokens collide with common nouns.
   The daily tweet budget cap (`daily_ceiling`, default 333) is enforced
   by `degraded_skip_order` — low-yield calls get skipped first.
3. **Fetch** — `x_monitor/apify.py:TwitterApiClient.advanced_search`
   (cookie-free; the file is named `apify.py` for historical reasons —
   see [Retired / removed](#retired--removed) below). Backoff on 429/5xx;
   `degraded:twitterapi_auth: true` on persistent auth failure.
4. **Filter** — `x_monitor/relevance.py` applies each brand's
   `RelevanceConfig` (`canonical_handles`, `must_have_any/none`,
   `cjk_tokens`) to drop noise from the raw search returns.
5. **Attribute** — `x_monitor/attribution.py` decomposes each kept post
   into per-brand mentions across four extraction sources (user_mention,
   hashtag, body_keyword, search_term). One tweet naming two brands
   produces one row per detected brand in `posts_brands*`. Replaces
   v1.7's first-match-wins single-brand classifier.
6. **Classify** — `x_monitor/attribution.py:classify_pragmatics_full` calls
   the configured LLM (DeepSeek V4 Pro via the direct Anthropic-compat
   endpoint by default) per post with the inline system prompt
   `_PRAGMATICS_FULL_SYSTEM_PROMPT`. Emits per-brand discourse
   (10 keys), sentiment (4), nationalism (6), post_type (6), and an
   `unsanctioned` flag.
7. **Persist** — `x_monitor/store.py` writes everything in one transaction
   per post. Schema is migrated forward-only by `x_monitor/migrations/*.sql`
   (currently 001–039).
8. **Emit run JSON** — `data/runs/<run_id>.json` plus the rolling
   `data/runs/LATEST.json` symlink. The dashboard reads `LATEST.json`
   for staleness indicator + http_log spend summary.

CLI flags worth knowing (see `python3 -m x_monitor run --help`):

| Flag | Purpose |
|---|---|
| `--dry-run` | Don't write to DB; print what would have been written |
| `--models a,b,c` | Restrict to a brand subset |
| `--queries A,B1,B2,B3,C1,C2` | Restrict to a call subset |
| `--limit-per-call N` | Cap per-call results (overrides `cfg.search.max_results`) |
| `--no-skip-under-budget` | Force every query through (bypasses daily_ceiling skip order) |
| `--max-pages-per-call N` | Override pagination safety cap (default 5 pages = 100 posts) |

---

## The dashboard — `x_monitor.dashboard.DashboardApp`

Flask app served on `http://127.0.0.1:5000/` (host/port configurable in
`config.yaml::dashboard`). Started/stopped via
`x-monitor dashboard start|stop|status`.

The dashboard renders **two pages** under the Pushin' Weight brand (see
section below):

| Route | Page |
|---|---|
| `GET /` | Multi-brand home (line chart + filter panel + infinite-scroll feed) |
| `GET /<company>/<brand>` | Single-brand home (per-tab area chart + same filter panel + brand-scoped feed) |
| `GET /_/<brand>` | Single-brand home for brands without a company (the `_` namespace) |

### Legacy compatibility

The old topbar views (v1.7) redirect 302 to the new home pages — they
are not gone, they are integrated:

| Legacy route | Redirects to |
|---|---|
| `GET /treemap` | `/` |
| `GET /grid` | `/` |
| `GET /combined` | `/` |
| `GET /_unattributed` | `/` |
| `GET /brand/<brand_id>` | `/<company>/<brand>` or `/_/<brand>` |
| `GET /model/<brand_id>` | same |

The JSON API mirrors the page routes under `/api/v1/`:

- `GET /api/v1/home.chart.json` — multi-brand chart payload
- `GET /api/v1/home.feed.json` — paginated feed (`?cursor=`, `?limit=`)
- `GET /api/v1/home.brand.chart.json` — single-brand chart payload
- `GET /api/v1/home.feed.json?brand=<nick>` — brand-scoped feed

---

## Pushin' Weight home pages (PW)

The dashboard's user-facing surface. Two pages, one design system. The
full UI guide lives at `../docs/reference/home-pages-ui-guide.md` — this
section is the abbreviated overview.

### Multi-brand home (`/`)

- **Top-left (2/3 width)**: combo line chart, one line per brand,
  accent colors per the `--role-*` CSS tokens. X-axis = time (1d hourly,
  1w daily, 1m daily, 1y monthly); Y-axis = posts per period; hover
  tooltip per data point.
- **Top-right (1/3 width)**: control panel with checkbox groups for
  brands, discourse keys, post_types, account.role, cn/us_nationalism,
  and an `unsanctioned` toggle. Default = all on. Filter changes
  propagate to both chart and feed.
- **Bottom half**: infinite-scroll feed (cursor-paginated). Columns:
  datetime, brand chips, translated text (subscript lang), original
  text (parallel column for QA), classification pills (discourse,
  post_type, cn/us nationalism, unsanctioned), and account handle + role
  pill.

### Single-brand home (`/<company>/<brand>`)

- Same control panel and feed as multi-brand.
- The chart becomes an area chart with **tabs**: post_type, discourse,
  account.role, cn_nationalism, us_nationalism, unsanctioned. Each tab
  shows the distribution of categories for the chosen dimension.

### Locale toggle (top right of topbar)

`zh_cn` (default) / `en` / `original`. Drives both the feed translation
column and brand chip display names. The locale cookie is set via
`POST /api/v1/home.locale/<locale>`.

### File pointers

| File | What |
|---|---|
| `x_monitor/templates/home.html.j2` | Multi-brand page shell |
| `x_monitor/templates/brand_home.html.j2` | Single-brand page shell |
| `x_monitor/templates/_home_chart.html.j2` | Multi-brand chart partial |
| `x_monitor/templates/_brand_chart.html.j2` | Single-brand chart partial |
| `x_monitor/templates/_feed_initial.html.j2` | Feed cursor-paginated initial render |
| `x_monitor/templates/_spend_panel.html.j2` | Per-run API spend panel |
| `x_monitor/_home_routes.py` | Route handlers (separated from `dashboard.py` for readability) |
| `x_monitor/static/pw-chart.js` | Multi-brand chart renderer |
| `x_monitor/static/pw-brand-chart.js` | Single-brand chart renderer |
| `x_monitor/static/pw-feed.js` | Feed cursor loader + bottomless scroll |
| `x_monitor/static/pw-filter-store.js` | Client-side filter state |
| `x_monitor/static/pw-locale-toggle.js` | Locale toggle button + cookie sync |
| `x_monitor/static/dashboard.css` | Shared stylesheet (incl. `--pt-*`, `--nat-*`, `--role-*` color tokens) |

UI reference: `../docs/reference/home-pages-ui-guide.md` — element names,
DOM hooks, payload shapes for each pane.

---

## Deployment — two launchd agents

The pipeline runs under two macOS launchd agents with **self-describing
labels** so they're never confused for each other:

### `com.fuchitalee.x-monitor.harvest` — the heartbeat

- **Trigger**: `StartCalendarInterval` at minute 0, 15, 30, 45 of every
  hour (96 cycles/day).
- **Wrapper**: `deploy/run-pipeline-with-notify.sh` → `python -m x_monitor run`.
- **macOS notifications**: pops on non-zero exit ("pipeline failed") and
  on success with >20 signal-drop warnings ("possible LLM/brand drift").
- **Logs**: `~/Library/Logs/x-monitor/harvest-stdout.log` and
  `harvest-stderr.log`.
- **Throttle**: 60s.

### `com.fuchitalee.x-monitor.config-reload` — the reflex

- **Trigger**: `WatchPaths` on `config.yaml` (ThrottleInterval 300s).
  Fires on edits to `enabled_models`, `daily_ceiling`, `x_query_specs`,
  `query_rot_streak_threshold`, etc. — i.e. any operator change that
  should take effect immediately without waiting for the next 15-min
  tick.
- **Wrapper**: `deploy/run-pipeline-watchpaths.sh` → `python -m x_monitor run`.
- **No notifications** — too noisy for config-edit cadence. Errors still
  land in `~/Library/Logs/x-monitor/stderr.log`.
- **Throttle**: 300s.

### Shared behavior

- Both wrappers source `~/.env.secrets` before invoking Python.
- Both honor the operator pause sentinel at `/tmp/x-monitor-paused`.
  `touch /tmp/x-monitor-paused` halts all runs; `rm` resumes.
- Both are debounced by `pipeline_lock` (`fcntl.flock` on
  `data/runs/LOCK`), so a config edit mid-cycle cleanly exits 0.

### Install

```bash
cd /Users/fuchitalee/development/pushin-weight-v2
bash deploy/install.sh             # config-reload (WatchPaths)
bash deploy/install-scheduled.sh   # harvest (15-min cadence)
launchctl list | grep com.fuchitalee.x-monitor
```

Manual trigger:

```bash
launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor.harvest
launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor.config-reload
```

Uninstall: `launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.<label>.plist && rm ~/Library/LaunchAgents/com.fuchitalee.x-monitor.<label>.plist`

Full install/uninstall reference: `deploy/README.md`.

---

## Setup (local MVP — v1 Flask)

```bash
cd /Users/fuchitalee/development/pushin-weight-v2

# 1. Python env
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Secrets (chmod 600, gitignored)
echo 'export TWITTERAPI_IO_API_KEY="..."' >> ~/.env.secrets
echo 'export ANTHROPIC_API_KEY="..."'        >> ~/.env.secrets   # LLM classification
chmod 600 ~/.env.secrets
source ~/.env.secrets

# 3. Apply migrations + smoke-test
x-monitor migrate
x-monitor run --dry-run --limit-per-call 20    # one cycle, no DB writes

# 4. Start dashboard
x-monitor dashboard start
# open http://127.0.0.1:5000/
```

`TWITTERAPI_IO_API_KEY` is the only auth surface — cookies were retired
2026-06-08 when the pipeline migrated from Apify search-with-cookies to
TwitterAPI.io (~$0.15/1k tweets vs $3/1k).

---

## Daily ops

```bash
# Dashboard
x-monitor dashboard start | stop | status

# Review queue (operator triage of ambiguous posts)
x-monitor review list
x-monitor review add <tweet_id> <reason>
x-monitor review resolve <tweet_id>
x-monitor review dismiss <tweet_id>

# Backfill classifications for newly-classified posts
x-monitor backfill unsanctioned-flags --limit 500 --yes

# Pause all runs (operator kill switch — both agents honor it)
touch /tmp/x-monitor-paused
# Resume
rm /tmp/x-monitor-paused
```

---

## Layout

```
x-monitor/                    (repo root — pushin-weight-v2)
├── README.md                 (this file)
├── pyproject.toml             (deps, pytest config)
├── config.yaml                (operator-editable: enabled_models,
│                               daily_ceiling, x_query_specs, dashboard,
│                               query_rot_streak_threshold, etc.)
├── manage.py                  (Django CLI — v2)
├── render.yaml                (Render Blueprint — v2)
├── Procfile                   (Render start command — v2)
├── build.sh                   (Render build script — v2)
├── .env.example               (Env var template — v2)
├── project/                   (Django project -- v2)
│   ├── settings.py            (env-driven config, all 3 apps, Celery)
│   ├── urls.py                (auth + dashboard routing)
│   ├── wsgi.py / asgi.py     (deployment entry points)
│   └── celery.py              (Celery app bootstrap)
├── core/                      (App #1: models + migrations -- v2)
│   ├── models.py              (Single source of truth for DB schema)
│   ├── migrations/            (Auto-generated from models.py)
│   ├── context_processors.py  (i18n template context)
│   └── management/commands/
│       └── seed_i18n_labels.py
├── monitor/                   (App #2: dashboard + harvest -- v2)
│   ├── views.py               (Dashboard view handlers, ~1,100 LOC)
│   ├── cycle.py               (CycleRunner -- harvest orchestrator)
│   ├── urls.py                (Dashboard URL patterns)
│   ├── tasks.py               (Celery task definitions)
│   ├── templates/             (Jinja2 templates)
│   └── management/commands/
│       ├── run_cycle.py       (Harvest cycle CLI)
│       ├── load_seed.py       (Curated base-layer seed)
│       └── validate_cycle.py  (v1-v2 equivalence validator)
├── x_monitor/                 (Legacy v1 — Flask Python package)
│   ├── __main__.py            (the entire CLI — no cli/ subpackage)
│   ├── run.py                 (RunPipeline — daily harvest orchestrator)
│   ├── dashboard.py           (DashboardApp + Flask routes — 2,700 LOC)
│   ├── _home_routes.py        (Pushin' Weight route handlers — 670 LOC)
│   ├── store.py               (SQLite Store — 3,220 LOC, every schema query)
│   ├── attribution.py          (v1.8 multi-brand per-post extraction — 2,215 LOC)
│   ├── apify.py               (TwitterAPI.io HTTP client — cookie-free)
│   ├── translator.py          (LLM translation + pragmatics classification)
│   ├── queries.py             (Query spec model + cost estimation)
│   ├── query_plan.py          (per-cycle call planner — Call A/B/C)
│   ├── relevance.py           (per-model post-fetch filter)
│   ├── config.py              (Pydantic config loader)
│   ├── review.py              (JSON-backed review queue)
│   ├── list_drift.py          (X list follower-drift detector)
│   ├── headlines.py           (URL → article-title resolver)
│   ├── hf_client.py           (HuggingFace Hub API client)
│   ├── hf_products.py         (per-company HF model collector)
│   ├── account_graph.py       (vanity URL + account graph helpers)
│   ├── treemap.py             (SVG treemap — legacy home, still used
│   │                            by some tests + the legacy 302 redirect)
│   ├── intent_classifier.py   (DEPRECATION SHIM — do not import)
│   ├── templates/             (home.html.j2 + brand_home.html.j2 + 4 partials)
│   ├── static/                (dashboard.css + 5 pw-*.js modules)
│   ├── migrations/            (001–039 forward-only SQL)
│   ├── data/
│   │   └── few_shot_pragmatics.jsonl   (LLM few-shot examples)
│   └── CHANGELOG.md
├── tests/                     (pytest — 122+ test files)
├── scripts/                   (one-off backfill / seed / probe / bridge scripts)
│   ├── bridge_sqlite_to_pg.py  (v1 run JSON → PG incremental sync)
│   ├── port_sqlite_to_django.py (v1 SQLite → PG bulk port)
│   └── ...
├── deploy/                    (2 launchd plists + install + wrapper scripts — v1)
├── data/                      (runtime — gitignored)
│   ├── x_monitoring.db            (live SQLite DB, ~85 MB)
│   ├── runs/                      (per-cycle JSONs + LATEST.json symlink)
│   ├── dashboard.pid, .log        (dashboard background process)
│   ├── _review_queue.json         (review queue)
│   └── headlines_cache.json       (URL → title cache)
├── docs/                      (project-local)
│   ├── plans/                      (in-progress + completed plans)
│   ├── notes/                      (operator notes)
│   ├── analysis/                   (probe + classification snapshots)
│   ├── deploy/                     (Render runbook — v2)
│   │   └── render.md
│   ├── production-runbook.md       (Cutover checklist — v2)
│   └── reference/                  (short reference docs)
├── locale/                    (Django i18n .po/.mo files — v2)
└── .venv/                     (local Python venv — gitignored)
```

Sister docs at `../docs/`:

- `../docs/reference/` — reference docs (db-schema, classifier-prompts,
  polarity-calculation, home-pages-ui-guide, twitterapi-live-queries-by-model, etc.)
- `../docs/plans/` — active + completed plans (~44 documents)
- `../docs/brainstorms/` — brainstormed feature proposals

---

## Troubleshooting

**Dashboard at port 5000 won't start.**
`lsof -nP -iTCP:5000 -sTCP:LISTEN` to find the conflict. Change
`config.yaml::dashboard.port` to free it up.

**Dashboard server died.**
`x-monitor dashboard status` shows the last 50 lines of
`data/dashboard.log`. Restart with `x-monitor dashboard start`.

**`data/runs/LATEST.json` shows `degraded:twitterapi_auth: true`.**
The API key in `~/.env.secrets` is invalid or revoked. Update and
restart both agents (the next scheduled tick will pick up the new value
once `launchctl` re-spawns the wrapper).

**`degraded:query_rot: <query_id>`.**
That call has returned zero results for `query_rot_streak_threshold`
consecutive days (default 3). Edit `config.yaml::enabled_models` (or
`x_query_specs::` for C-specs) to either drop the brand / spec or update
the primary tokens in the `brand_keywords` DB table (`is_primary=1` rows).

**LLM classification failing / 401 from the LLM.**
Check `~/.env.secrets` — `ANTHROPIC_API_KEY` must be valid. Note: the
key format depends on which gateway you target. If using the Alibaba
gateway (DS V4 Pro direct), the key is `sk-cp-uhKE…` style; if using
the stock Anthropic endpoint, it's `sk-ant-api…`. The pipeline detects
the gateway from the key prefix.

**No classifications appearing in the feed.**
The (post, brand) tuples have no rows in `posts_brands_signals` /
`posts_brands_discourse` / `posts_unsanctioned_flags` yet. Run
`x-monitor backfill unsanctioned-flags --limit 500 --yes` to populate.

**Pipeline cycle runs but `data/runs/LATEST.json` is stale.**
Check `/tmp/x-monitor-paused` exists. If it does, `rm` it to resume.
Otherwise check the harvest agent is loaded: `launchctl list | grep harvest`.

---

## Where to look next

- **Render deploy runbook**: `docs/deploy/render.md`
- **Cutover checklist + battle-test protocol**: `docs/production-runbook.md`
- **UI deep-dive**: `../docs/reference/home-pages-ui-guide.md`
- **DB schema**: `../docs/reference/db-schema.md`
- **LLM prompts**: `../docs/reference/classifier-prompts.md`
- **Taxonomy tables + brand registry**: `../docs/reference/lookup-tables.md`
- **TwitterAPI.io endpoint inventory**: `../docs/reference/twitterapi-io-calls.md`
- **Polarity math**: `../docs/reference/polarity-calculation-explained.md`
- **TwitterAPI.io query surface**: `../docs/reference/twitterapi-live-queries-by-model.md`
- **Active plans**: `../docs/plans/`
- **Run history**: `x_monitor/CHANGELOG.md`

---

## Retired / removed

These paths existed in earlier versions. Don't add new content here —
they're noted so newcomers don't waste time:

- **Q1–Q6 query taxonomy + `data/queries/<brand>.yaml`** (retired
  2026-07-11) — the per-brand YAML files encoded six query intents
  (release, community_question, criticism, commenter_capture, other,
  praise). The v2 architecture uses a single uniform `(<tokens>)
  (<co_occurrence>) min_faves:N` shape. Brand tokens now live in the
  `brand_keywords` DB table (`is_primary=1` rows). `VALID_QUERY_IDS`
  still exists as a constant in `config.py` but the live cycle never
  reads it.
- **`data/accounts/<brand>.yaml`** (retired 2026-07-11) — official / staff
  handles now live in the `brands_accounts` DB table. Edit via SQL
  migration.
- **`data/filters/<brand>.yaml`** (retired 2026-07-11) — relevance
  filtering now lives in the `brand_keywords` DB table and
  `RelevanceConfig` (code-side). Edit via SQL migration.
- **Apify cookies (`~/.config/x-monitor/cookies.json`)** (retired
  2026-06-08) — pipeline moved to TwitterAPI.io, which is cookie-free.
- **`data/staging.db`** (retired 2026-07-07) — archived to
  `data/staging_archive/`. See `data/staging_archive/RETIRED.md`.
- **`x_monitor/intent_classifier.py`** — kept as a deprecation shim
  that re-exports from `attribution.py` with `DeprecationWarning`. Do
  not import; will be deleted in a future cleanup.
- **`x_monitor/apify.py` filename** — kept for git-blame continuity;
  the class inside is `TwitterApiClient` (TwitterAPI.io), not Apify.

---

## Last reviewed: 2026-07-22 (HEAD 6589175)

### (a) Substantive corrections in this pass

1. **Step 6 (Classify) module path**: `translator.py` → `attribution.py`.
   `classify_pragmatics_full` lives in `attribution.py:1670`, not translator.py.
2. **Step 6 prompt source**: `few_shot_pragmatics.jsonl` → inline constant
   `_PRAGMATICS_FULL_SYSTEM_PROMPT`. The JSONL file is used by the translator
   pass only.
3. **post_type count**: 8 → 6 (matches `_VALID_POST_TYPES` in attribution.py).
4. **Migration range**: 001-038 → 001-039.
5. **`data/filters/<brand>.yaml`**: moved from "kept" to retired. The directory
   no longer exists on disk. Tokens and filters live in the DB.
6. **Q1-Q6 taxonomy retirement**: added to "Retired / removed" section.
7. **Troubleshooting**: `data/filters/<brand>.yaml` token update path replaced
   with `brand_keywords.is_primary=1` DB update path.
8. **"Where to look next"**: added `lookup-tables.md` and
   `twitterapi-io-calls.md`.
9. **LOC counts**: `store.py` 3,143→3,220, `attribution.py` 2,144→2,215.

### (b) Claims not independently verified

- X-list membership (whether all 20 official handles are on the public list)
- Wrapper scripts sourcing `~/.env.secrets`
- macOS notification behavior on non-zero exit
- `x-monitor migrate` CLI subcommand existence
- Anthropic API pricing ($0.005/1000 tweets)

### (c) Drift noticed but not fixed (and why)

- `GET /api/v1/home.feed.json?brand=<nick>`: the server-side handler does not
  read a `brand` query param — brand scoping happens client-side. Not fixed
  because the README describes the URL pattern surface, and a proper fix
  requires understanding how the client uses this parameter.
- Code docstrings in `relevance.py`, `apify.py`, `__main__.py`, `run.py` still
  reference `data/filters/<brand>.yaml` as if current. Code comments are out
  of scope for a README-only edit.
