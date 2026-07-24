# x-monitor

Last updated: 2026-07-24-11:36:23

A daily dashboard for keeping tabs on what people are saying about 20 AI
models on X (formerly Twitter). Serves the multi-brand home page and
per-brand drill-downs at **pushinweight.ai**, behind Google OAuth.

## What this is

x-monitor scans X every 15 minutes for posts about 20 AI models
(MiniMax, Qwen, DeepSeek, GLM, Xiaomi MiMo, Moonshot Kimi, Mistral,
ERNIE, Llama, Doubao, and others), attributes each post to the brands
it mentions, persists everything in PostgreSQL, and displays the results
on a browser dashboard with chart, feed, and filter controls.

It was built for MiniMax's developer relations team so they always know
what the public is saying about these models: who's excited, who's
critical, who's asking questions, and what releases are being discussed.

## Architecture

The v2 stack runs entirely on Render:

| Component | Render resource | What it does |
|---|---|---|
| **Web** | `pushinweight-web` (web service) | gunicorn + Django, serves the dashboard |
| **Harvest** | `pushinweight-harvest` (cron job) | Fires `python manage.py run_cycle` every 15 minutes |
| **Database** | `pushinweight-db` (managed PostgreSQL) | All application data |

The v1 system (Flask + SQLite + macOS launchd) is **retired**. See
[Retired / removed](#retired--removed) at the bottom of this page.

## Pipeline lifecycle

The harvest cycle runs every 15 minutes via the Render cron job
`pushinweight-harvest` (`render.yaml`, schedule `*/15 * * * *`):

```
startCommand: python manage.py run_cycle --limit-per-call 50
```

Each cycle executes 5 steps:

1. **Plan calls.** `CycleRunner._plan_calls()` in `monitor/cycle.py` loads
   the X list ID and `x_query_specs` from Django settings (populated from
   `config.yaml` by `project/settings.py`). Primary brand keywords are
   loaded from `BrandKeyword.objects.filter(is_primary=True)` (Django ORM).
   The plan is built by `x_monitor/query_plan.py::plan_calls()`. Emits
   **6 calls** per cycle:

   | Call | Kind | Description |
   |---|---|---|
   | A | List-based fan-in | Curated X list (`x_monitor_list_id`) |
   | B1 | Wide-net + AND-filter | Top-presence / global brands (6 brands) |
   | B2 | Wide-net + AND-filter | Chinese-language brands (4 brands) |
   | B3 | Wide-net + AND-filter | Specialized / smaller brands (4 brands) |
   | C1 | Co-occurrence constrained | MiMo, Kimi, Yi, Llama |
   | C2 | Co-occurrence constrained | ERNIE, Upstage |

2. **Fetch tweets.** Each `PlannedCall.query_string` is fired against
   TwitterAPI.io's `advanced_search` endpoint via `TwitterApiClient`
   (`x_monitor/apify.py`). Max 50 tweets per call, up to 5 pages.

3. **Attribute to brands.** Each fetched tweet is stamped with `brand_id`,
   `brand_ids`, and `mentions` via `x_monitor/attribution.py::attribute_to_brands()`.

4. **Persist.** Attributed tweets are written to PostgreSQL via Django ORM:
   `Post`, `Account`, `PostBrand`, `PostBrandMention`, `PostBrandSignal`
   (all defined in `core/models.py`).

5. **Post-fetch (stubbed).** Translation and classification steps are
   deferred to a follow-up unit. The `CycleRunner` currently returns zero
   counters for translate/classify.

The command-line entry point is:

```bash
python manage.py run_cycle                  # one cycle, live mode
python manage.py run_cycle --dry-run        # plan calls only, no API calls
python manage.py run_cycle --limit-per-call 20
python manage.py run_cycle --brands minimax,qwen
python manage.py run_cycle --json           # JSON stats to stdout
```

**Source of truth files:** `config.yaml` (enabled models, x_query_specs),
`monitor/cycle.py` (orchestrator), `monitor/management/commands/run_cycle.py`
(CLI), `x_monitor/query_plan.py` (call planner).

## Dashboard

The dashboard is served by Django + gunicorn on Render at
**pushinweight.ai**, behind Google OAuth (django-allauth).

### Routes

| Route | Description |
|---|---|
| `/` | Multi-brand home: chart + feed for all 20 brands |
| `/brands/<brand>/` | Single-brand drill-down (e.g. `/brands/deepseek/`) |
| `/feed/` | JSON API: cursor-paginated feed |
| `/chart/` | JSON API: multi-brand chart data |
| `/chart.html` | HTML partial: chart for htmx swap |
| `/brand-chart/<brand>/` | JSON API: single-brand chart data |
| `/brand-chart/<brand>.html` | HTML partial: single-brand chart for htmx swap |
| `/accounts/login/` | Google OAuth sign-in |
| `/admin/` | Django admin (superuser only) |

### Login flow

1. Visit `https://pushinweight.ai/`.
2. Redirected to `/accounts/login/` -- click "Google" to sign in.
3. On first login, a Django `User` + `SocialAccount` is created.
4. Redirected to the multi-brand home page.

### Home page UI

The multi-brand home (`/`) shows a time-series chart (per-brand post
volume, 5-min or daily buckets) and a scrollable post feed with filters
for discourse, post type, role, language, nationalism axes, and
unsanctioned status. The single-brand page (`/brands/<brand>/`) adds a
tabbed chart for post-type breakdown.

**Source of truth files:** `monitor/views.py` (all views), `project/settings.py`
(auth config, static files, CSRF), `core/models.py` (Brand, Post, PostBrand, etc.).

## Database

**Managed PostgreSQL on Render** (`pushinweight-db`, plan: free).
Django ORM via `core/models.py` is the single source of truth for the
schema. Migrations live in `core/migrations/`.

Key conventions:
- Natural keys as primary keys (nicknames, tweet IDs, author IDs).
- `CompositePrimaryKey` for junction tables.
- `db_collation="case_insensitive"` on all natural-key text columns.
- `JSONField` for tweet entities, raw payloads, product metadata.
- `DateTimeField` with `USE_TZ=True` (stores `TIMESTAMPTZ`).

**Source of truth files:** `core/models.py` (all models), `docs/reference/db-schema.md`
(full table-by-table reference), `docs/reference/lookup-tables.md` (enum/lookup tables).

## Deployment

Deployment is via Render Blueprint (`render.yaml` at the repo root).

On push to the connected branch, Render auto-provisions:

| Resource | Type | Purpose |
|---|---|---|
| `pushinweight-web` | Web service (starter) | gunicorn + Django dashboard |
| `pushinweight-harvest` | Cron job (starter) | Harvest cycle every 15 min |
| `pushinweight-db` | Managed PostgreSQL (free) | Application database |

`build.sh` runs on every deploy:
```bash
pip install -e ".[dev]"
python manage.py collectstatic --noinput
python manage.py migrate --noinput
```

### Render secrets

API keys live in the `pushinweight-secrets` env group on Render:
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` -- Google OAuth
- `TWITTERAPI_IO_API_KEY` -- Twitter data API
- `ANTHROPIC_API_KEY` -- LLM classifier (future)

### Config

Django configuration is in `project/settings.py` -- env-driven via
`django-environ`. `config.yaml` at the repo root holds the operator-editable
tuning knobs: `enabled_models`, `x_query_specs`, `call_b_groups`,
`daily_ceiling`, search caps, degraded-skip order.

**Source of truth files:** `render.yaml` (topology), `project/settings.py`
(Django config), `config.yaml` (pipeline tuning), `build.sh` (build steps),
`docs/deploy/render.md` (full runbook).

## Local dev

```bash
# Run the dev server with Google OAuth
python manage.py runserver 0.0.0.0:8000

# Run one harvest cycle (dry-run -- no API calls, no DB writes)
python manage.py run_cycle --dry-run --limit-per-call 20

# Run a live cycle against production PG
python manage.py run_cycle --limit-per-call 20

# Run Django system checks
python manage.py check --deploy

# Run tests
pytest
```

By default, the local dev server connects to a local PostgreSQL instance
(`postgres://pushinweight:pushinweight@localhost:5432/pushinweight`).
To connect to the Render PostgreSQL instance instead, set `DATABASE_URL`
in your local `.env`:

```
DATABASE_URL=postgres://pushinweight:<password>@<host>:5432/pushinweight
```

Note: Render's external connections are IP-whitelisted. Add your local IP
in Render Dashboard > `pushinweight-db` > Settings.

## Seeds and setup

After first deploy (or when resetting a dev DB), run these one-time
setup commands:

```bash
# Seed the curated base layer (brands, companies, roles, accounts)
python manage.py load_seed

# Seed i18n taxonomy labels (post_type, sentiment, discourse, nationalism, roles)
python manage.py seed_i18n_labels

# Create a Django superuser for /admin/ access
python manage.py createsuperuser
```

## Management commands

| Command | Description |
|---|---|
| `run_cycle` | Run one harvest cycle (see [Pipeline lifecycle](#pipeline-lifecycle)) |
| `load_seed` | Seed brands, companies, roles, and account-brand associations |
| `seed_i18n_labels` | Seed en/zh-cn labels for post types, sentiments, discourse, nationalism, roles |
| `validate_cycle` | Validate the cycle plan against config without fetching |

All commands support `--help` for full usage.

## Where to look next

The 6 reference docs in `docs/reference/` are the authoritative
cross-reference for runtime behavior:

| Doc | What it covers |
|---|---|
| `twitterapi-io-calls.md` | TwitterAPI.io endpoint inventory, credit costs, retry/backoff, budget guard |
| `twitterapi-live-queries-by-model.md` | The 6-call cycle (A + B1/B2/B3 + C1/C2), per-brand token lists, per-cycle state |
| `db-schema.md` | Every table, column, type, FK, index; references the generated PNG |
| `lookup-tables.md` | Enum/lookup tables (`*_keys`, `*_labels`), taxonomy values, brand/company registry |
| `classifier-prompts.md` | Literal LLM system prompt text, JSON output shape, taxonomy legends |
| `home-pages-ui-guide.md` | Dashboard UI element catalog (selectors, data-attrs, JS owners, CSS sources) |

Additional operational docs:
- `docs/deploy/render.md` -- Full Render deployment runbook
- `CONCEPTS.md` -- Shared domain vocabulary (entities, processes, status concepts)
- `docs/solutions/` -- Documented solutions to past problems

## Retired / removed

The v1 stack (Flask + SQLite + macOS launchd) is dead. These paths and
commands no longer exist:

- `python -m x_monitor run` -- replaced by `python manage.py run_cycle`
- `x-monitor` CLI entrypoint -- replaced by Django management commands
- `x-monitor dashboard start` / `stop` -- dashboard is now served by gunicorn on Render
- `x-monitor setup cookies` -- v2 uses TwitterAPI.io (API key), not cookie-based auth
- `x-monitor migrate` -- replaced by `python manage.py migrate`
- `x-monitor reattribute` -- v2 attribution runs inline during the harvest cycle
- `data/x_monitoring.db` -- replaced by managed PostgreSQL on Render
- `data/runs/LATEST.json` / `data/runs/LOCK` -- v2 has no file-based pipeline lock
- `/tmp/x-monitor-paused` sentinel -- not used in v2
- macOS LaunchAgents (`com.fuchitalee.x-monitor.harvest`, `com.fuchitalee.x-monitor.config-reload`) -- replaced by Render cron job
- `deploy/*.plist` files -- replaced by `render.yaml`
- Flask on `localhost:5000` -- replaced by Django + gunicorn on pushinweight.ai

Last reviewed: 2026-07-24
