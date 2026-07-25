# feat: Productionize x-monitor: Django + PostgreSQL on Render, full i18n, multi-account Google OAuth (harvest continuous)

**Date:** 2026-07-22  
**artifact_contract:** ce-unified-plan/v1  
**artifact_readiness:** implementation-ready  
**product_contract_source:** ce-plan-bootstrap  
**execution:** code  
**Target repo:** pushin-weight-v2

---

## Goal Capsule

Migrate the x-monitor dashboard + supporting pipeline runtime from local Flask + SQLite + macOS launchd to a production-grade Django + PostgreSQL deployment on the user's Render account. The site must be fully internationalized (building on existing zh-CN/en work), support multi-account access via standard Google OAuth, and follow idiomatic Django patterns. The harvest pipeline (15-min cycles that spend the TwitterAPI.io budget and produce the live dataset) must experience **zero disruption** — it continues running on the existing macOS agents against the current SQLite until the new cloud harvest path is separately battle-tested for 1–2 days.

Stop conditions: (1) new Django site live on Render with working Pushin' Weight UIs, (2) Google OAuth login required and functional for team accounts, (3) at least one successful harvest cycle executed via the new Django management command against the production PG (validated by diff against old run JSONs), (4) data ported without loss for the last N days + all curated seed, (5) old launchd harvest still green during transition window.

---

## Problem Frame

Current state (local-only MVP):
- Flask dashboard (`x_monitor/dashboard.py` + `_home_routes.py`, Jinja2 templates, custom JS for charts/feed) served on localhost:5000.
- Raw SQLite store (`x_monitor/store.py`) with 39 forward SQL migrations; ~85 MB live `data/x_monitoring.db`.
- Harvest (`x_monitor/run.py` + attribution, relevance, translator, apify, query_plan) runs via two launchd agents every 15 min; emits `data/runs/LATEST.json` and writes posts/signals.
- Partial i18n already present (text_en / text_zh_cn, display_name_* columns, locale cookie toggle, translator pipeline).
- No user accounts, no auth, no cloud surface. Single-operator local tool.
- Prior parallel experiment (`~/development/pushin_weight`) proved Django 5 + natural-key models + Celery + PG + management command harvest shape.

Why now:
- Ready for production visibility / sharing with team.
- Need proper accounts + OAuth (least privilege, audit).
- SQLite not suitable for cloud concurrent access + growth.
- Flask is fine for tiny local but Django gives first-class i18n (gettext + model labels), ORM safety, admin, forms, auth, static handling, and ecosystem for the multi-account + future API surface.
- Harvest budget and data collection are the crown jewels — any change that risks a missed cycle or double-spend is unacceptable.

Non-goals (for this plan):
- Public unauthenticated site.
- Multi-language beyond current en/zh-CN parity (future).
- Full brand-per-user scoping or RBAC (basic "any authenticated team member sees everything" is sufficient).
- Immediate decommissioning of the Flask code or mac harvest agents.
- Moving every last one-off script in one shot.

Success looks like: team can `https://x-monitor.onrender.com/` (or custom domain), logs in with Google, sees identical (or better) Pushin' Weight experience, and the 15-min data keeps arriving whether the old agents or the new Render-scheduled path are driving it.

---

## Product Contract

### Requirements (R-IDs synthesized from request + constraints)

- R1. Deploy the application to Render (web service + managed PostgreSQL). Use idiomatic Render patterns (gunicorn/uvicorn, build.sh, render.yaml or Blueprint, env-driven DATABASE_URL, static via WhiteNoise).
- R2. Replace Flask with Django 5+ (or current stable) for the web surface and, where practical, the harvest entrypoint.
- R3. Replace SQLite with PostgreSQL as the single source-of-truth data store for both web reads and harvest writes.
- R4. Make the site fully i18n: all UI strings, enum labels, and brand display names support en / zh-CN (and original where applicable) using Django i18n + the established label tables pattern from the pushin_weight reference.
- R5. Add multi-account support with usual OAuth: Google login via django-allauth (or equivalent idiomatic package); login required for all dashboard surfaces; session + CSRF handled by Django.
- R6. Harvest pipeline (fetch → filter → attribute → classify → persist) must continue producing runs with no gaps, no double budget spend, and no data loss throughout the entire transition. Old macOS launchd agents remain the live path until new path is proven.
- R7. Preserve (and improve where cheap) current functionality: two home pages (multi-brand + per-brand), charts, infinite feed, filters, locale toggle, spend panel, review queue hooks, etc.
- R8. Use the pushin_weight repo strictly as reference for Django idioms, model conventions (natural keys + composite PKs for labels/junctions where sensible), management command shape, and Celery wiring — do not copy-paste the entire crawler; converge the live x-monitor logic.
- R9. All changes must be reviewable, reversible where possible, and testable (existing pytest corpus + new Django tests).

### Actors
- A1. Operator (current single user + future team members) — runs harvest, reviews data, configures via Render env / config.yaml ports.
- A2. Authenticated team user (via Google OAuth) — views dashboards, may later gain light ops actions.
- A3. Render platform / scheduled worker — executes harvest cycles in cloud.

### Key Flows (high level)
- F1. Harvest cycle (15 min): unchanged externally; internally either old launchd path or new `manage.py run_cycle` (or Celery task).
- F2. Authenticated dashboard view: Google login → session → protected Pushin' Weight pages + API JSON.
- F3. Locale switch: persists (cookie or user pref) and renders translated content + UI chrome.
- F4. Data port / cutover: one-time or incremental load from SQLite → PG; later dual-run validation.

### Acceptance Examples (AE)
- AE1. New team member can go to the Render URL, "Sign in with Google", and immediately see the live multi-brand home with recent posts and correct zh-CN/en labels.
- AE2. A harvest cycle kicked off via the Django management command against PG produces a run JSON + DB rows that, when diffed against a contemporaneous old-agent run, match on post counts, signals, and spend within tolerance.
- AE3. While the old launchd agents are still the production harvest source, the new Django site (pointing at a PG replica or the primary) renders the same data as the local Flask dashboard.
- AE4. Changing `enabled_models` (or equivalent in new config) affects both the new command and (during transition) is documented for the old path.
- AE5. All existing classifier / translator / relevance behavior is preserved (no regressions in signal quality).

### Scope Boundaries

**In scope**
- Django project layout at the project root (project/, core/, monitor/ apps) mirroring the pushin_weight reference shape (alongside the existing `x_monitor/` package).
- Django models + migrations that can host the current live data shape (adapt reference natural-key style where safe; preserve compatibility for port).
- Google OAuth via allauth (or Django social if simpler), login wall, basic user surface.
- Full port of the two Pushin' Weight home surfaces (server-rendered + JS progressive enhancement or HTMX where it simplifies).
- Management command (and optional Celery task) that can execute a full harvest cycle using the current logic (or refactored shared core).
- Data import / migration tooling + validation (SQLite → PG).
- Render deployment artifacts (render.yaml, build.sh, Procfile if needed, env docs).
- i18n completion: Django translation strings + locale-aware label tables + brand names.
- Dual-run / bridge support so old harvest can keep writing while new path is tested.
- Updated tests, smoketests, and verification that old agents remain green.

**Deferred to Follow-Up Work**
- Custom user model + per-user preferences / watched brands / notifications.
- Public unauthenticated views or embeddable widgets.
- Full deprecation + deletion of Flask code and mac launchd plists (after 1–2 weeks of proven cloud harvest).
- Additional OAuth providers.
- REST API surface beyond the current JSON endpoints needed by the UI.
- Advanced admin tooling or ops dashboards inside Django admin.
- Multi-region / read replicas.

**Outside this product's identity**
- Changes to the X API probe strategy, classifier prompts, or brand taxonomy (those are separate concerns).
- Last30days engine or other unrelated sub-projects.

---

## Planning Contract

### Key Technical Decisions (KTDs)

**KTD1. Structure: Django project colocated at the project root.**  
`project/settings.py`, `manage.py`, `core/` (models + migrations), `monitor/` (new Django app; or keep/refactor as needed) apps. This keeps the harvest code, config, data dir, tests, and deploy scripts in one tree during transition. Mirrors the proven pushin_weight reference layout exactly as requested. The existing `x_monitor/` package becomes the "compat / legacy layer" that the launchd agents continue to invoke unchanged. The root now directly contains `x_monitor/`, `config.yaml`, `pyproject.toml`, `deploy/`, `scripts/`, etc. (the former `x-monitoring/` wrapper directory was removed in housekeeping).

**KTD2. Harvest continuity contract (non-negotiable).**  
Old macOS launchd agents (`com.fuchitalee.x-monitor.harvest` etc.) + current `python -m x_monitor run` + SQLite remain the live production path until the operator explicitly validates 1–2 days of successful new cycles on Render (or local PG) and flips a kill switch / updates agents. During the window a bridge script or dual-persist helper (optional) can keep a PG copy in sync for the new dashboard to read. No cycle is ever "paused" for the migration work itself.

**KTD3. Use Django ORM + Django migrations as the new source of truth for schema.**  
Models in `core/models.py` (inspired by pushin_weight reference: natural keys + CompositePrimaryKey for labels/junctions + TIMESTAMPTZ + case_insensitive collation where PG supports). Forward migrations only. A one-time data port script (similar to existing `scripts/2026-06-06-001-migrate-pushin-weight-records.py`) will load current SQLite content. After cutover, the raw SQL migration dir is historical; new changes go through `makemigrations`.

**KTD4. OAuth provider: Google only (per explicit answer).**  
django-allauth with Google provider. Team members log in with corporate/personal Google accounts. No GitHub in v1. Simple "any authenticated user sees the full dataset" authorization model. allauth provides the usual account linking, email verification hooks, etc. out of the box. LOGIN_REQUIRED middleware or decorator on all dashboard routes.

**KTD5. i18n strategy (idiomatic + incremental).**  
- UI chrome / templates: Django's `gettext`, `ugettext_lazy`, locale middleware, `i18n_patterns` or cookie + `django.middleware.locale.LocaleMiddleware`.
- Enum / lookup labels: keep and extend the `*_labels` junction tables (post_type_labels, stance_labels, etc.) with (key, locale) composite PK exactly as the reference does. Seed + admin or management command for labels.
- Content translations (post text): continue using the existing `text_en` / `text_zh_cn` columns (or equivalent in new schema) populated by the translator pipeline.
- Brand / company display names: i18n columns or label tables.
- The existing locale toggle (zh_cn / en / original) is preserved and wired to Django's language machinery.

**KTD6. Harvest execution in cloud: management command first, Celery optional.**  
Port the cycle logic so `python manage.py run_cycle --dry-run` and normal mode work. For scheduled execution on Render: (a) Render Cron Job calling the management command, or (b) a dedicated worker service running Celery beat (reference pattern). Start with the simplest (cron or a lightweight always-on loop) to minimize moving parts while old path is still authoritative. The command reuses as much of the existing `run.py` / `attribution.py` / `relevance.py` / `store.py` logic as possible (via import or thin adapter layer) to avoid behavioral drift.

**KTD7. Data port & validation.**  
One-time (or windowed) import that:
- Creates PG from Django migrations.
- Loads curated seed (brands, companies, hf_orgs, brands_accounts, search terms, lookup keys + labels).
- Backfills recent posts + signals from SQLite (or from the `data/runs/*.json` artifacts for provenance).
- Produces an auditable JSON report (counts inserted / skipped / diffs).
- Smoketest + "db_diff" style check (reference has `crawler_db_diff`) to prove parity.
Old DB is never deleted; it becomes the rollback source.

**KTD8. Risk controls (controlled & reversible).**
- Feature flags / env var `XMONITOR_HARVEST_MODE=legacy|new|dual`.
- All new code lands behind the existing test corpus + new Django tests + a post-port smoketest that compares run artifacts.
- Deploy the Django site first in "read from PG snapshot" mode while harvest is still SQLite-driven.
- Never spend TwitterAPI budget from the new path until operator has reviewed a dry-run + a small live test cycle.
- Schema image regeneration rule (CLAUDE.md) is extended or a new equivalent is added for Django model changes.

**KTD9. Static + templates.**  
Use WhiteNoise for static in prod (idiomatic for Render). Port Jinja templates to Django templates (or keep Jinja via django-jinja if desired, but standard DjangoTemplates is preferred for i18n). JS assets stay largely the same (served as static); only server context and i18n wiring changes.

**KTD10. Config surface.**  
Keep `config.yaml` (or a Django settings overlay) for operator-editable items (enabled_models, call_b_groups, daily_ceiling, query specs). Load it from Django settings or a management command context so the old launchd path is unaffected. Secrets stay in env (Render dashboard or .env).

### High-Level Technical Design (Chronology & Phasing)

**Overall chronology (risk-ordered, harvest-first):**

1. **Foundation (parallel, zero harvest impact)**
   - Scaffold Django project at the project root (project/, core/, monitor/).
   - Define core models that can accept the current schema data.
   - Add allauth + Google provider + basic login views / middleware.
   - Add i18n wiring + label tables + port existing locale strings.
   - Local PG (or Render preview DB) + data port script + validation reports.
   - `manage.py run_cycle` skeleton that can at least plan and dry-run using existing pipeline modules.

2. **Harvest port (still using old agents as source of truth)**
   - Full cycle implementation in the management command (fetch, filter, attribute, classify, persist via ORM).
   - Smoketests and side-by-side diff tooling.
   - Optional bridge: a small writer that can also persist a copy to PG from the legacy run path (or run the new command against a copy of recent runs).

3. **Dashboard port**
   - Recreate the two home pages + JSON APIs + filter + chart + feed + locale toggle inside Django views/templates.
   - Protected by login.
   - Parity tests (existing test_dashboard*.py adapted or new selenium/playwright + unit).

4. **Render deployment (staging first)**
   - render.yaml or Blueprint describing web + postgres.
   - build.sh (collectstatic + migrate).
   - gunicorn + WhiteNoise.
   - Deploy to a non-prod service or branch; connect a fresh or snapshot PG.
   - Verify login, UI, and (read-only) data.

5. **Cloud harvest validation window (battle test)**
   - Run new `run_cycle` (via manual, cron, or worker) for 1–2 days on the real budget (small caps initially).
   - Operator reviews run JSONs, spend, signal quality, and compares to contemporaneous old runs.
   - Only after explicit approval: update docs, optionally flip a config so new path is primary.

6. **Cutover & cleanup**
   - Point the production Render web service at the now-authoritative PG.
   - Optionally leave old agents running as hot standby or pause them.
   - Update local dev instructions, CLAUDE.md, deploy scripts.
   - (Later) archive Flask code.

**Component relationships (simplified):**
- `core` app owns models (source of truth) + label tables for i18n.
- `monitor` (or crawler) app owns cycle logic, tasks, management commands, relevance/attribution adapters.
- `project` owns settings (env + Render), urls (login + dashboard routes), wsgi/asgi, celery.
- Old `x_monitor/` package and launchd continue to operate unchanged against SQLite during phases 1-5.
- Render Postgres is the eventual single source; SQLite becomes local dev / rollback artifact.

**State machine for harvest source during transition:**
legacy (mac+SQLite) → (parallel validation) → dual (optional bridge) → new (Render cron/worker + PG) → legacy decommissioned.

### Alternatives Considered

- Keep Flask + add SQLAlchemy + Alembic + pg + separate auth layer: rejected — user explicitly asked for Django; Django gives superior i18n + auth + ORM out of the box.
- Big-bang cutover (stop old harvest, switch everything same day): rejected — violates "unabated" and risk-free requirement.
- Fully separate repo for the Django app: rejected — user wants the migration done inside pushin-weight-v2; colocated for shared history and easy cross-port of pipeline logic.
- Email/password + allauth only (no social): rejected — "usual oauth" and explicit Google answer.

### Assumptions
- Operator has access to the Render account and can create a Postgres instance + web service.
- Google OAuth app can be created (client ID/secret) with appropriate redirect URIs for localhost + Render domain.
- The 20 current brands + full recent history + curated seed must be ported; historical data older than ~30–90 days can be summarized if needed for size.
- Existing pytest tests for pipeline behavior will be used to prove the new command produces equivalent outputs.
- No change to the TwitterAPI.io or LLM key surface (still env vars).

### Open Questions (deferred, non-blocking)
- Exact Render service name / custom domain / plan tier.
- Whether to keep a local SQLite dev mode for pure offline pipeline debugging after cutover (nice-to-have).
- Long-term home for the old `x_monitor/` package (delete, keep as thin CLI shim, or extract to a published wheel).

---

## Implementation Units

### U1. Scaffold Django project layout at the project root (reference-aligned)

**Goal:** Create the standard Django layout (`manage.py`, `project/`, `core/`, `monitor/`) so that `python -m project` and `python manage.py` work, without touching the running harvest or Flask dashboard.

**Requirements:** R2, R8.

**Dependencies:** none.

**Files:**
- manage.py (new or minimal, at project root)
- project/__init__.py, settings.py, urls.py, wsgi.py, asgi.py, celery.py (new, at project root)
- core/__init__.py, apps.py (new, at project root)
- monitor/__init__.py, apps.py (new; or name it to allow future convergence with x_monitor)
- pyproject.toml (add Django, psycopg, django-allauth, gunicorn, whitenoise, django-environ, etc. under optional or new extras)
- .env.example (updated)
- tests/ additions for new layout (smoke import tests)

**Approach:** Follow pushin_weight reference exactly for directory shape and settings skeleton. Use `django-admin startproject` inside a temp dir then move files to the project root (alongside the existing `x_monitor/` package, `config.yaml`, etc.). Make settings env-driven with `environ`. Add a `project/__main__.py` shim so `python -m project` behaves like the reference. Do not enable any web routes or models yet. Ensure `pip install -e ".[dev]"` still works and existing `python -m x_monitor run` and `x-monitor` entrypoint are untouched.

**Patterns to follow:** pushin_weight/project/settings.py + pyproject.toml, current root `pyproject.toml`.

**Test scenarios:**
- Happy: after `pip install -e`, `python -m project --help` or `python manage.py --help` shows Django commands.
- Happy: `python -c "import project.settings; import core; import monitor"` succeeds.
- Edge: existing `python -m x_monitor run --help` and `x-monitor` script still function identically.
- Error: missing required env (DJANGO_SECRET_KEY, etc.) produces clear message on settings import in production mode.

**Verification:** `python manage.py check` exits 0 with only the expected "no models" warnings. Layout matches reference at top level.

### U2. Define core models + initial Django migrations matching live data shape

**Goal:** Produce `core/models.py` and 0001_initial migration whose resulting schema can accept a port of the current SQLite tables (brands, companies, accounts, posts, posts_brands_*, signals, runs, lookup keys + labels, etc.).

**Requirements:** R3, R4 (i18n label tables), R8.

**Dependencies:** U1.

**Files:**
- core/models.py (new — the new source of truth, at project root)
- core/migrations/0001_initial.py (generated)
- core/migrations/0002_*.py (i18n label seeds or follow-ups)
- Possibly a `schema/0001_end_state.sql` snapshot (like reference) for human review.
- Update docs/reference/db-schema.md or add note that Django models are now authoritative after cutover.
- core/checks.py (natural key / composite PK invariants, adapted from reference)

**Approach:** Start from the pushin_weight reference models.py (natural keys for brands/companies/hf_orgs/accounts, composite PKs for labels and junctions, TIMESTAMPTZ, case_insensitive collation). Adapt column names/types to exactly match current live SQLite (e.g. keep `accounts.id` AUTOINCREMENT if present, or decide on natural `author_id` PK — document the choice). Include i18n label tables for post_types, stances/sentiments, roles, nationalism keys, discourse, etc. Use `CompositePrimaryKey` for junctions. Make Brand/Company have `display_name_en`, `display_name_zh_cn` etc. Run `makemigrations` and hand-review the SQL. Add system checks.

**Patterns to follow:** pushin_weight/core/models.py (including docstring conventions), current x-monitor schema (docs/reference/db-schema.md + migrations/*.sql), existing i18n columns.

**Test scenarios:**
- `python manage.py makemigrations --check --dry-run` is clean after 0001.
- `python manage.py sqlmigrate core 0001 | grep -i "create table"` produces the expected 30+ tables.
- `python manage.py check` passes the new core checks.
- Happy path model creation: `Brand.objects.create(...)` with natural key slug works; duplicate raises IntegrityError with case-insensitive collation behavior on PG.

**Verification:** A fresh `test_*.db` or local PG can be migrated and `SELECT count(*) FROM _migrations` + table existence matches expectation. Schema image note added (or script adapted) per CLAUDE.md spirit.

### U3. Add Google OAuth + basic multi-account auth wall (django-allauth)

**Goal:** Any access to the dashboard requires a logged-in Google-authenticated user. Provide login/logout flows. No anonymous access.

**Requirements:** R5.

**Dependencies:** U1 (settings/urls skeleton).

**Files:**
- project/settings.py (add allauth apps, middleware, AUTHENTICATION_BACKENDS, SOCIALACCOUNT_PROVIDERS for Google, ACCOUNT_* settings)
- project/urls.py (include allauth urls + dashboard urls under login_required)
- templates/ (account/login.html etc. — minimal or use allauth defaults + branding)
- monitor/ or a new accounts/ app if heavier customization needed (start minimal)
- docs/ or README update for creating the Google OAuth client + adding the Render + localhost redirect URIs.

**Approach:** Install `django-allauth[socialaccount]`. Configure exactly one provider: Google. Use `django.contrib.auth` + allauth. Protect routes with `login_required` (or middleware). Set `LOGIN_URL`, `LOGIN_REDIRECT_URL = "/"`. For production on Render, set proper `CSRF_TRUSTED_ORIGINS`, `SECURE_*` settings behind env. No custom User model in U3 (can be added later). Support the usual "sign in with Google" button.

**Patterns to follow:** django-allauth Google provider docs + reference comments in pushin_weight settings about v2 auth.

**Test scenarios:**
- Happy: unauthenticated GET / → 302 to /accounts/login/ (or allauth Google start).
- Happy: after successful Google login (test via allauth test helpers or mocked), subsequent requests see request.user.is_authenticated and the dashboard content.
- Edge: revoked Google token or bad client secret surfaces a clear error page (not 500).
- Integration: locale cookie still respected on login page.

**Verification:** Manual or pytest with `django.test.Client` + socialaccount test utils shows protected pages 401/redirect when logged out.

### U4. Port / implement full i18n (UI strings + label tables + brand display)

**Goal:** The entire site (chrome + data labels + brand names + existing translated post text) is driven by Django i18n + the new label tables. Locale toggle continues to work and feels native.

**Requirements:** R4.

**Dependencies:** U2 (models with labels).

**Files:**
- core/models.py (label models if not complete in U2)
- core/management/commands/seed_i18n_labels.py (or extend existing seeds)
- Templates updated with `{% load i18n %}`, `{% trans %}`, `{% blocktrans %}`, `get_current_language`.
- Python code using `gettext_lazy`.
- Locale directories `locale/en/LC_MESSAGES/`, `locale/zh_CN/...` (or rely on model labels + a small number of UI strings).
- Static JS or template logic that passes current locale to the feed/chart components (preserve existing pw-locale-toggle.js behavior).
- Update of any hard-coded English strings in dashboard templates/JS.

**Approach:** Use the reference label table pattern (PostTypeLabel etc with composite (key, locale)). Seed the  current values from existing migration seeds / scripts. Wire Django's LocaleMiddleware + a simple cookie or user-language switcher that updates the existing "zh_cn / en / original" semantics. For post content, keep the column-based approach (text_<lang>) but expose via template filters that respect the active language. Make brand chips and filter panel labels come from the DB labels.

**Patterns to follow:** Existing x-monitor i18n (test_dashboard_i18n.py, translator, locale toggle JS, display_name_en columns), pushin_weight label tables.

**Test scenarios:**
- Happy: with language=zh-cn, all enum pills and brand names render the zh label; en renders English.
- Happy: switching locale via the existing toggle updates the feed text column (original vs translated) and the UI labels.
- Edge: unknown locale falls back gracefully.
- Covers existing AE from prior i18n plans.

**Verification:** Existing i18n tests pass (adapted) + new view tests assert correct labels in rendered HTML for each language.

### U5. Data port tooling + validation (SQLite → PG)

**Goal:** Operator can run a script that takes the live `data/x_monitoring.db` (or a subset) and a target PG (via DATABASE_URL) and produces an identical (or semantically equivalent) dataset in the Django models, with an auditable report.

**Requirements:** R3, R7.

**Dependencies:** U2.

**Files:**
- scripts/port_sqlite_to_django.py (new, modeled on the 2026-07-06 pushin_weight migrate script)
- data/migration_logs/ (new reports written here)
- monitor/management/commands/load_seed.py or init_db (like reference)
- Tests: test_port_sqlite_*.py
- Possibly a `tools/db_diff.py` or reuse/extend reference's crawler_db_diff.

**Approach:** Read via sqlite3 or Django's sqlite connection, write via ORM in a transaction per major table family. Handle natural vs surrogate key differences explicitly (map author_id etc.). Support --dry-run, --limit, --since, --brands. Emit JSON report with inserted/skipped/dropped counts per table + hash or sample of key rows. After load, run the existing smoketests or a new "compare latest run against source SQLite" command.

**Patterns to follow:** scripts/2026-06-06-001-migrate-pushin-weight-records.py (and its .aliases.yaml), pushin_weight/tools/*, test_backfill_*, existing migration log practices.

**Test scenarios:**
- Dry-run on a small SQLite clone reports exact counts that would be inserted.
- Real port of a known-good snapshot succeeds; a subsequent `manage.py runs --json` shows the expected run ids and post counts.
- Idempotent re-run does not create duplicates (uses get_or_create or natural key upserts).
- Report file is written with timestamp and git sha.

**Verification:** Operator can diff row counts + a few signal samples between source SQLite and target PG and see zero unexpected differences for the ported window.

### U6. Harvest cycle as Django management command (and optional Celery task)

**Goal:** `python manage.py run_cycle` (and `--dry-run`, `--brand`, `--limit`, `--json`, async enqueue) executes a complete, correct harvest cycle against the Django ORM / PG and emits a run summary compatible with the existing LATEST.json shape.

**Requirements:** R6, R2, R7.

**Dependencies:** U1, U2, U5 (at least for seed), existing pipeline modules.

**Files:**
- monitor/management/commands/run_cycle.py (modeled exactly on reference)
- monitor/tasks.py (Celery wrapper)
- monitor/cycle.py or adapters that call into (or copy/adapt) x_monitor/run.py, attribution, relevance, translator, store logic.
- Updates to x_monitor/config.py or a thin bridge so the same YAML / enabled_models work.
- monitor/apps.py (register checks, ready hook)
- Tests: test_run_cycle_command.py, integration tests that compare outputs.

**Approach (critical for harvest continuity):** The command must produce **bitwise or semantically identical** behavior to the current `x_monitor run`. Strategy: import the existing functions where possible and only swap the persistence layer (Store → Django ORM writes). Or do a faithful port inside the monitor app. Start with full --dry-run parity (no network spend). Only after that, enable writes. Support the same CLI flags by stashing them in `django.conf.settings` (exact pattern from reference). For the old launchd path to remain untouched, this command is a *new* entrypoint.

**Patterns to follow:** pushin_weight/crawler/management/commands/run_cycle.py + tasks.py + cycle.py, current x_monitor/run.py, test_run.py, test_run_pipeline_*.py.

**Test scenarios:**
- `--dry-run --limit-per-call 5 --models minimax` produces the same number of candidate posts and the same classification counts as the legacy path (within non-determinism of LLM).
- Full cycle writes the expected posts, posts_brands, signals, accounts, and a new row in runs table; the emitted JSON (if any) matches the run-summary shape.
- Concurrent cycles are properly serialized or degraded via DB-level lock (or the existing fcntl + new advisory).
- `--async` enqueues and returns quickly; the task completes successfully when worker runs.
- Budget / daily ceiling logic is honored exactly.

**Verification:** Side-by-side run on the same time window produces matching `data/runs/` style output + DB row counts. Existing `test_run.py` and pipeline integration tests pass against the new command (or have parallel new tests).

### U7. Port the Pushin' Weight dashboard UI to Django (protected)

**Goal:** The two home pages, charts, filters, infinite feed, locale toggle, spend panel, and JSON APIs are available at the same routes under Django, behind the login wall, and visually/behaviorally match the current Flask experience.

**Requirements:** R1 (after deploy), R2, R4, R7, R5.

**Dependencies:** U3 (auth), U4 (i18n), U2 (models for queries), U6 (if live data needed).

**Files:**
- monitor/views.py (or dashboard/views.py)
- monitor/urls.py (or included)
- Templates: monitor/templates/monitor/home.html, brand_home.html, partials, etc. (ported from x_monitor/templates/*.j2)
- Static assets moved or symlinked under static/ (or keep in x_monitor/static and collect)
- JS updates only where server context (csrf, locale, user) changes.
- monitor/context_processors.py (brand list, accent colors, current run info)
- API views that return the same JSON shapes as /api/v1/...

**Approach:** Re-implement the route handlers from `_home_routes.py` + dashboard.py as Django class-based or function views using the ORM. Use Django's template language + existing static JS (served by WhiteNoise). Preserve the exact DOM ids/classes the JS expects. Locale is driven by Django. All views decorated or protected. For charts, either server-render initial SVG/HTML or keep the client-side rendering fed by the same JSON contracts.

**Patterns to follow:** x_monitor/_home_routes.py + dashboard.py, templates/, static/pw-*.js, docs/reference/home-pages-ui-guide.md, existing tests/test_dashboard*.py and test_feed_page.py.

**Test scenarios:**
- Authenticated GET / returns 200 with the multi-brand home shell + correct brand chips for current enabled_models.
- Brand drill-down `GET /<company>/<brand>` renders the area chart tabs + scoped feed.
- Filter changes (via the control panel POST or query params) produce correct chart/feed subsets (server or client).
- Locale toggle changes rendered text and labels.
- JSON endpoints return payloads that the existing pw-*.js can consume without modification.
- Unauthenticated access to any of the above redirects to login.

**Verification:** Existing dashboard e2e / feed / chart tests (test_home_e2e.py, test_combined_*, test_feed_page.py) pass or have direct Django equivalents. Visual spot-check in browser matches current local Flask.

### U8. Render deployment artifacts + production settings

**Goal:** `git push` (or Blueprint) to the user's Render account results in a working Django web service connected to a managed Postgres, with static collected, migrations applied, and the site reachable behind Google login.

**Requirements:** R1.

**Dependencies:** U1–U7 (at least a minimal working slice).

**Files:**
- render.yaml (or root render.yaml if preferred)
- build.sh (chmod +x; pip install, collectstatic, migrate)
- Procfile (optional: web: gunicorn ...)
- project/settings.py (production section: DEBUG=False, allowed hosts from env, CSRF trusted from env, WhiteNoise middleware, STATIC_ROOT, logging, etc.)
- .env.example (Render-specific keys: RENDER, DATABASE_URL examples)
- docs/deploy/render.md (new runbook: create Postgres, web service, set env vars for SECRET_KEY, GOOGLE_CLIENT_ID/SECRET, TWITTERAPI_*, ANTHROPIC_*, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS)
- deploy/README.md or root README with cloud instructions.

**Approach (idiomatic Render Django):**
- Use gunicorn (or uvicorn workers for ASGI if needed).
- WhiteNoise for static.
- `env.db("DATABASE_URL")` or dj-database-url.
- Build command: `sh build.sh`.
- Start: `gunicorn project.wsgi:application` (or asgi).
- For cron/scheduled harvest: either (a) add a Render cron job definition in render.yaml that runs `python manage.py run_cycle`, or (b) deploy a separate worker service + celery beat.
- Set PYTHON_VERSION appropriately.
- Health check endpoint.

**Patterns to follow:** Official render.com/docs/deploy-django, the YouTube 2026 tutorials, pushin_weight docs/deploy/ (even if thin), testdriven.io blog patterns for WhiteNoise + build.sh.

**Test scenarios:**
- Local `DEBUG=1 ./build.sh && python manage.py runserver` works.
- Render preview deploy succeeds (build + migrate + static).
- After deploy, the homepage redirects to Google login; after login the UI loads and shows recent data from the PG.
- Static files (css, js, images) load with 200 and correct cache headers.

**Verification:** Render service dashboard shows green web + postgres. Browser visit succeeds end-to-end (login + dashboard). `python manage.py health` or equivalent (if added) reports OK.

### U9. Optional bridge + validation harness for parallel harvest during transition

**Goal:** While mac launchd agents continue as the source of truth, the new dashboard (and operator) can see fresh data in PG with minimal lag, and new harvest cycles can be safely exercised without risking the primary budget.

**Requirements:** R6.

**Dependencies:** U6, U5.

**Files:**
- scripts/bridge_sqlite_to_pg.py (or extend the port script to tail recent runs)
- monitor/management/commands/validate_cycle.py (compares two runs or DB snapshots)
- Updates to data/runs/ handling or a small writer adapter the legacy path can optionally call.
- Docs in the plan or deploy notes describing the 1–2 day battle-test protocol.

**Approach:** Option A (simple): after a successful legacy cycle, the bridge script imports the just-written run JSON / affected posts into PG. Option B (cleaner long-term): run the new `run_cycle` on a restricted budget window (small `--limit`, or a dedicated test brand list) or against a replay of recent API results. Provide a `validate` command that asserts post counts, signal distributions, and spend are within tolerance. The operator uses this during the "battle test" window.

**Patterns to follow:** Existing smoketests (scripts/post_fetch_smoketest.py, tests/test_post_fetch_smoketest*.py), run summary diffing in debug docs, the pushin_weight db_diff tools.

**Test scenarios:**
- Bridge run on a known LATEST.json populates the PG with matching row counts.
- `validate_cycle --source-legacy --target-new --run-id <id>` exits 0 only on match.
- A deliberately limited new cycle (small daily budget slice) succeeds and is reviewed by operator before full switch.

**Verification:** Operator can follow a documented checklist and obtain matching artifacts + sign-off that new path is safe.

### U10. Documentation, CLAUDE.md updates, local dev story, and cutover checklist

**Goal:** After U8/U9, a teammate or future self can set up local Django dev against PG, deploy, and perform the harvest cutover safely.

**Requirements:** All R's (documentation is part of controlled rollout).

**Dependencies:** U1–U9.

**Files:**
- README.md (major update: "Production (Django/Render)" section + "Transitioning from legacy Flask")
- deploy/README.md or new docs/deploy/
- CLAUDE.md (add note about Django migrations instead of / in addition to raw SQL; how to run schema image if still relevant; Render commands)
- .env.example (complete)
- Possibly a `docs/production-runbook.md`
- Update any references in docs/plans/ that mention Flask dashboard paths.

**Approach:** Write clear, copy-pasteable instructions. Include the exact battle-test + cutover steps. Note that old launchd remains until operator says "go". Add a one-line in the schema regeneration rule if the image process needs extension for Django models (or mark the dot as legacy after cutover).

**Test scenarios:** N/A (docs); instead, a peer or the operator can follow the README from a fresh clone and reach a working `manage.py run_cycle --dry-run`.

**Verification:** README contains the full happy-path local + Render story and the explicit "do not touch launchd yet" warning. No broken links or outdated Flask-only instructions in primary docs.

---

## Verification Contract

- All new code must pass `pytest` (existing suite + new tests for U1–U10).
- `python manage.py check --deploy` (with production settings) is clean.
- `python manage.py migrate --check` (or equivalent) shows no pending migrations on a clean PG.
- Smoketest commands (adapted post_fetch_smoketest, new run_cycle dry-run, home page render tests) exit 0 and produce matching artifacts vs legacy.
- Manual browser flow on a Render preview: Google login → multi-brand home → brand page → locale toggle → feed scroll.
- Data port report for the live DB shows 0 dropped critical rows + row counts within 1% of source for the ported window.
- Harvest continuity: at no point during implementation does `launchctl list | grep x-monitor.harvest` show a stopped agent or do we touch the live 15-min agents except for the final optional decommission step after validation.

---

## Definition of Done

- The plan's Implementation Units are complete (or explicitly carved out to a follow-up plan).
- A working Django site (login + Pushin' Weight pages) is deployed to the user's Render account against a real Postgres instance.
- At least one full harvest cycle has been executed successfully via the new `manage.py run_cycle` path against production data shape, reviewed by the operator, and declared equivalent.
- The macOS launchd harvest agents are still running and producing runs (the "unabated" proof).
- Google OAuth works for at least one team account.
- All i18n surfaces (labels + UI + content) render correctly in en and zh-CN.
- Documentation and runbooks are updated so the next person can reproduce the setup.
- `ce-work` (or human) has run the Verification Contract gates.
- Any schema changes have respected the spirit of the CLAUDE.md image rule (or the rule has been updated).

---

## Risks & Dependencies

**Major risks (with mitigations)**
- Budget overspend or missed cycles during experimentation → strict use of --dry-run + small limits + explicit operator approval gate before any new live spend. Old agents stay authoritative.
- Data loss or corruption on port → auditable reports + keep SQLite as source of truth + never delete old DB files until after cutover + successful validation.
- Behavioral drift in classification/attribution after port → heavy reuse of existing modules + side-by-side diff tests + smoketests.
- OAuth misconfig exposing the site → start with localhost + explicit Render domain; use allauth's secure defaults; test revoked tokens.
- Render build / static / DB connection flakes → follow official + reference patterns exactly (WhiteNoise, build.sh, DATABASE_URL); document exact env keys.
- Long transition period leaving two code paths → time-box the battle-test window; schedule the decommission step.

**Dependencies / Prerequisites**
- Access to the Render account and ability to provision a Postgres database.
- Google Cloud / Google API console access to create OAuth 2.0 credentials for the web app.
- A recent full backup or copy of `data/x_monitoring.db` and `data/runs/`.
- Local PostgreSQL (or willingness to use the reference's init scripts against a container) for dev.
- The pushin_weight checkout remains available read-only for reference during implementation.

---

## Sources & Research

- Current implementation: `x_monitor/{dashboard.py,_home_routes.py,run.py,store.py,attribution.py,...}`, `config.yaml`, `tests/`, `deploy/`, `docs/reference/db-schema.md`, `docs/reference/home-pages-ui-guide.md`.
- Reference architecture (use as shape + idioms only): `/Users/fuchitalee/development/pushin_weight/{project/settings.py,core/models.py,crawler/management/commands/run_cycle.py,README.md,pyproject.toml}` and its migrations + seed tools.
- Prior alignment work: plans around natural keys, i18n columns (2026-06-23), pushin_weight record migration (2026-07-06 and 2026-07-07), schema modernization.
- External (Render Django): official Render Django deploy docs, gunicorn + WhiteNoise + build.sh patterns, 2026 tutorials on Render + PG + Django.
- OAuth: django-allauth Google provider documentation and examples.
- Institutional: CLAUDE.md (schema image rule), CONCEPTS.md (run summary / call / pipeline lock vocabulary must be respected in new command output), existing migration log + smoketest discipline.

---

## Appendix (optional notes)

- The 150000-timestamp plan from the same day (new open model discovery) is independent; this production plan does not depend on or block it.
- After this lands, future model additions, brand renames, or classifier changes should be tested against both the legacy path (while it lives) and the new Django command.
- Consider extracting the pure pipeline logic (no web, no Django) into a small `xmonitor-pipeline` package in a later refactor so the two front-ends (legacy CLI + Django command) truly share code.

**Plan written to docs/plans/2026-07-22-002-feat-production-django-postgres-render-plan.md**

---

## Post-generation (for the harness)

(After write + confidence + doc-review in headless, present the standard menu.)
