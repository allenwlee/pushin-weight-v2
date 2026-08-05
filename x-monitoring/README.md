# x-monitor

Last updated: 2026-08-05-20:38:42


A daily dashboard for keeping tabs on what people are saying about 20 AI
models on X (formerly Twitter). Serves the multi-brand home page and
per-brand drill-downs at **pushinweight.ai**, behind Google OAuth.

## What this is

x-monitor scans X every 15 minutes for posts about 20 AI models
(minimax, qwen, deepseek, glm, mimo, moonshot_kimi, inclusionai,
mistral, stepfun, ernie, hunyuan, llama, nemo_megatron, doubao, yi,
sensechat, exaone, kuaishou, sakana_ai, upstage — the canonical
`enabled_models` list in `config.yaml`), attributes each post to the
brands it mentions, persists everything in PostgreSQL, and displays the
results on a browser dashboard with chart, feed, and filter controls.

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
startCommand: python manage.py run_cycle
```

Each cycle executes 5 steps:

1. **Plan calls.** `CycleRunner._plan_calls()` in `monitor/cycle.py` loads
   the X list ID and `x_query_specs` from Django settings (populated from
   `config.yaml` by `project/settings.py`). Primary brand keywords are
   loaded from `BrandKeyword.objects.filter(is_primary=True)` (Django ORM).
   The plan is built by `x_monitor/query_plan.py::plan_calls()`. Emits
   **7 calls** per cycle:

   | Call | Kind | Description |
   |---|---|---|
   | A | List-based fan-in | Curated X list (`x_monitor_list_id`) |
   | B1 | BARE wide-net | Top-presence / global brands (5 brands: minimax, qwen, deepseek, stepfun, hunyuan — no co) |
   | B2 | HANDLE-ONLY | Chinese-language brand handles (4 brands: doubao, glm, sensechat, inclusionai — `@handle` OR-group) |
   | B3 | HANDLE-ONLY | Other-brand official handles (4 brands: nemo_megatron, exaone, sakana_ai, kuaishou — `@handle` OR-group) |
   | C1 | Co-occurrence constrained | llama, mimo, mistral, moonshot_kimi, yi (5-term minimal co + f1-anchors not_include) |
   | C2 | Co-occurrence constrained | ernie, upstage (5-term minimal co + baidu, 文心) |
   | C3 | Co-occurrence constrained | doubao, kuaishou, sensechat (5-term minimal co) |

2. **Fetch tweets.** Each `PlannedCall.query_string` is fired against
   TwitterAPI.io's `advanced_search` endpoint via `TwitterApiClient`
   (`x_monitor/apify.py`). Max 50 tweets per call, up to 5 pages.

3. **Attribute to brands.** Each fetched tweet is stamped with `brand_id`,
   `brand_ids`, and `mentions` via `x_monitor/attribution.py::attribute_to_brands()`.

4. **Persist.** Attributed tweets are written to PostgreSQL via Django ORM:
   `Post`, `Account`, `PostBrand`, `PostBrandMention`, `PostBrandSignal`
   (all defined in `core/models.py`).

5. **Post-fetch (translate + classify)** is handled by the
   [Backfiller](#backfiller-post-fetch-fetch--translate--classify) — not
   the live `run_cycle`.

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

## Backfiller (post-fetch: fetch + translate + classify)

The live `run_cycle` cron only handles steps 1–4 of the pipeline above
(plan, fetch, attribute, persist). Translation and classification are
**not** invoked by the live pipeline. Closing the translate+classify
gap on demand is the Backfiller's job — operators run it manually.

### One-shot scripts

Two earlier-era scripts cover narrow backfill needs:

- `scripts/backfill_brand_keywords.py` — Seeds `brand_keywords` from
  `data/queries/<brand>.yaml` Q2 parens (the operator-curated source of
  truth for brand tokens). INSERT-OR-IGNORE on `(brand_id, pattern)`
  UNIQUE, so re-running is idempotent. Plan:
  `docs/plans/2026-07-10-001-feat-brand-keywords-backfill-plan.md`.
  Used when adding a new brand's yaml.
- `scripts/backfill_classify_recent.py` — Walks `posts` for posts with
  no `posts_brands_signals` row, calls real `classify_post` (not the
  pipeline stub) with attributed brand slugs, and writes via
  `Store.insert_posts_brands_signals`. `--limit N` caps the run;
  `--dry-run` skips LLM calls; `--out FILE.json` dumps the work.

### v2 prod backfiller

The unified batched + resumable + LLM-guarded backfiller is
`python manage.py backfill`:

```bash
python manage.py backfill --since 2026-07-01 --until 2026-07-31
python manage.py backfill --since 2026-07-01 --until 2026-07-31 --max-llm-calls 50
python manage.py backfill --status        # print progress from data/backfill/*.json
python manage.py backfill --reset         # start over
```

Plan: `docs/plans/2026-07-24-002-feat-backfiller-tool-plan.md`.

Key properties:

- Date-bounded: `--since`/`--until` accept `YYYY-MM-DD` or
  `YYYY-MM-DDTHH:MM:SS`. Window size drives `max_results` and
  `max_pages` dynamically.
- Batched + cooperative: `--batch-size N` + `--pause SECONDS` keeps the
  pipeline lock free for the regular 15-min `pushinweight-harvest` cron.
- Resumable: state files in `data/backfill/<epochs>.json` record
  completed call IDs, total posts inserted, and errors. Failed calls
  retry on the next invocation.
- LLM-guarded: `--max-llm-calls N` is the hard safety valve — stops
  classification after N LLM batches; remaining posts wait for the
  next invocation. LLM calls are sequential with `X_MONITOR_LLM_PAUSE_SECONDS`
  (default 1s) between batches.
- Translate + classify: runs the real `classify_post` on new posts,
  writing `text_en` / `text_zh_cn`, `PostBrandSignal`, and
  `PostBrandDiscourse` rows.

**The live pipeline (`run_cycle`) does NOT call this.** Operators run
`manage.py backfill` manually to close the translate+classify gap on
historical windows or to recover after an outage.

**Source of truth files:** `monitor/management/commands/backfill.py`
(command), `monitor/cycle.py` (shared `CycleRunner` — backfiller and
the harvest cron use the same one), `data/backfill/<epochs>.json`
(state files), `scripts/backfill_brand_keywords.py`,
`scripts/backfill_classify_recent.py`.

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

The reference docs in `docs/reference/` are the authoritative
cross-reference for runtime behavior:

| Doc | What it covers |
|---|---|
| `twitterapi-io-calls.md` | TwitterAPI.io endpoint inventory, credit costs, retry/backoff, budget guard |
| `twitterapi-live-queries-by-model.md` | The 7-call hybrid funnel (A + B1 bare + B2/B3 handle-only + C1/C2/C3 co-occurrence) |
| `db-schema.md` | Every table, column, type, FK, index; references the generated PNG |
| `lookup-tables.md` | Enum/lookup tables (`*_keys`, `*_labels`), taxonomy values, brand/company registry |
| `classifier-prompts.md` | Literal LLM system prompt text, JSON output shape, taxonomy legends |
| `home-pages-ui-guide.md` | Dashboard UI element catalog (selectors, data-attrs, JS owners, CSS sources) |
| `schema.dot` + `images/xmonitor-schema-post-batch.png` | Graphviz source + generated schema diagram (referenced by `db-schema.md`) |

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

Other recent retirements (config + data shape):

- `data/queries/<brand>.yaml` -- per-brand keyword YAMLs retired 2026-07-11
  (plan `docs/plans/2026-07-11-001-feat-queries-and-filters-retire-and-export-poststep-plan.md`).
  Replaced by the `brand_keywords` DB table seeded by
  `scripts/backfill_brand_keywords.py` and refreshed by
  `load_seed` / `seed_i18n_labels`.
- `data/accounts/<brand>.yaml` -- per-brand official/staff-handle YAMLs
  retired 2026-07-11 (plan
  `docs/plans/2026-07-11-002-feat-call-b-revival-via-x-query-specs-plan.md`).
  Replaced by the `brands_accounts` DB table (joined to `accounts` and
  `roles`, filtered to `role_id IN (2, 3)` -- i.e. official and staff).
- `x-monitoring/` wrapper directory flattened on 2026-07-22 (plan
  `docs/plans/2026-07-22-002-feat-production-django-postgres-render-plan.md`).
  The wrapper that nested `x_monitor/` has been collapsed; this
  `x-monitoring/README.md` is the surviving shell directory used
  only for this README. The `x_monitor/` Python package now lives at
  the repo root.
- `x_monitor/run.py::RunPipeline` (v1 pipeline) -- replaced by
  `monitor/cycle.py::CycleRunner` (v2). RunPipeline is preserved for
  migration testing but is not invoked by `python manage.py run_cycle`.

Last reviewed: 2026-07-24

Last reviewed: 2026-07-31
- Step 5: post-fetch translate + classify — was "stubbed / deferred",
  replaced with a forward-pointer to the new Backfiller section.
- Pipeline lifecycle: call count was 6, now **7** (added C3 per plan
  2026-07-30-002).
- B1: was "Wide-net + AND-filter", now **BARE wide-net** (no co paren
  per R3).
- B2/B3: were "Wide-net + AND-filter", now **HANDLE-ONLY** (the
  `handles:` XQuerySpec field per U2).
- C1/C2/C3: now document the 5-term minimal co allowlist (R8) and
  R10 (xiaomi/小米/moonshot removed from co).
- Added new `## Backfiller (post-fetch: fetch + translate + classify)`
  section documenting the `manage.py backfill` command, the two
  one-shot scripts (`scripts/backfill_brand_keywords.py`,
  `scripts/backfill_classify_recent.py`), and the explicit "live
  pipeline does NOT call this" callout.
- Where-to-look-next row for `twitterapi-live-queries-by-model.md`
  updated to reflect the 7-call hybrid funnel.

Last reviewed: 2026-08-05
- Brand enumeration in the "What this is" section: was 10 named brands
  + "and others" (misleading), now lists the full 20 in
  `enabled_models` order with a pointer to `config.yaml`.
- Pipeline lifecycle call table: B1 brand count corrected from 6 to 5
  per live `config.yaml::x_query_specs` (B1 wide_net_brands =
  minimax, qwen, deepseek, stepfun, hunyuan). C1 brand set expanded
  from 4 to 5 brands to include `mistral` per
  `docs/plans/2026-07-31-002-fix-demote-mistral-from-b1-to-c1-plan.md`
  and live `x_query_specs` C1. B2 brand list corrected to
  doubao/glm/sensechat/inclusionai; B3 to
  nemo_megatron/exaone/sakana_ai/kuaishou. C2/C3 brand lists
  cross-checked against `twitterapi-live-queries-by-model.md` §"Brand
  → call_ids coverage".
- Render cron `startCommand` corrected: render.yaml is `python
  manage.py run_cycle` (no `--limit-per-call 50` flag). The flag
  is operator-supplied for ad-hoc runs only; see CLI examples below.
- Header `Last updated` and footer `Last reviewed` stamps refreshed to
  2026-08-05.
- "Retired / removed" section expanded with the 2026-07-11 yaml
  retirements, the 2026-07-22 `x-monitoring/` wrapper flatten, and
  the `RunPipeline` -> `CycleRunner` v1-to-v2 migration.

