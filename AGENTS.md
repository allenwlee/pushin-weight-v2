# Agent Rules (this repo)

Rules for AI agents (and humans) working in this repo. Honor these unless
explicitly told otherwise.

## file names
'YYYY-MM-DD-HHMMSS-description' should overrule compound-engineering file naming rules

## Single-stack deployment (v2 Django on Render)

As of 2026-07-27 the v1 Flask + launchd + SQLite stack is **retired**.
There is one production stack: v2.

- **Web:** Django + gunicorn + WhiteNoise on Render, behind Google OAuth
  (URL: `https://pushinweight-web.onrender.com`).
- **Harvest:** Celery beat + worker on Render (15-min interval).
- **DB:** Managed PostgreSQL on Render (Render-internal `DATABASE_URL`
  via the `xmonitor-db` service). The v1 SQLite file at
  `data/x_monitoring.db` is read-only historical state; do not write to
  it. The local `data/django_dev.db` is a dev-only SQLite; never point
  prod at it.
- **Models:** `core/models.py` is the source of truth for DB schema.
- **Migrations:** `core/migrations/` (auto-generated from models).
- **Querying prod:** see `reference_pushinweight_prod_db_via_render_cli.md`
  in project memory — Render CLI auth lives on fuchitalee, queries route
  through `ssh fuchitalee 'render psql ...'`.

## Schema (v2 — Django ORM)

Django ORM migrations in `core/migrations/` are the single source of
truth for the DB schema. To generate a migration after editing
`core/models.py`:

```bash
python manage.py makemigrations core
python manage.py migrate
```

The legacy Graphviz schema image at
`docs/reference/images/xmonitor-schema-post-batch.png` (generated from
`docs/reference/schema.dot` via `scripts/build_schema_image.sh`) is
**retired**. Do not regenerate it; the v1 SQLite schema it depicts no
longer drives anything in production.

## Local Django dev

```bash
# Run the dev server (Google OAuth login wall)
python manage.py runserver 0.0.0.0:8000

# Run one harvest cycle
python manage.py run_cycle --dry-run --limit-per-call 20

# Run tests (Django test runner)
pytest

# Run Django system checks
python manage.py check --deploy
```

## Render deploy

Deployment is via Render Blueprint (`render.yaml`). On push to the
Render-connected branch, Render auto-provisions:

- `xmonitor-web` (gunicorn + Django)
- `xmonitor-worker` (Celery worker)
- `xmonitor-beat` (Celery scheduler)
- `xmonitor-db` (managed PostgreSQL)
- `xmonitor-redis` (managed Redis)

Full runbook: `docs/deploy/render.md`.

Manual deploy commands (one-off under Render shell):
```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py load_seed
python manage.py seed_i18n_labels
```

## Documented solutions and shared vocabulary

`docs/solutions/` — documented solutions to past problems (bugs, best
practices, workflow patterns), organized by category with YAML
frontmatter (`module`, `tags`, `problem_type`). Relevant when
implementing or debugging in documented areas.

`CONCEPTS.md` — shared domain vocabulary (entities, named processes,
status concepts). Relevant when orienting to the codebase or
discussing domain concepts.

# pushin-weight-v2 Agent Rules

## Memory

Topic files live under `~/.claude/projects/-Users-allenwlee/memory/` and are loaded on demand. Each entry below has a corresponding detail file with the full context.

- `project_pushin_weight_2026-06.md` — [SUPERSEDED 2026-07-27] v1 + v1.5 + v1.6 deployment, 330 tests, Render Postgres, oauth, allauth — historical; v1 launchd/SQLite stack now retired
- `reference_pushinweight_prod_db_via_render_cli.md` — query prod via render psql dpg-d9go1njeo5us73cg5u00-a --command ... routed through fuchitalee
- `feedback_playwright_first_for_ui.md` — drive Playwright FIRST when fixing UI; do not reason from code
- `feedback_parallel_subagents_ximports.md` — budget a reconciliation subagent for cross-import drift in parallel dispatch
- `feedback_pkill_matches_all_dashboardapp.md` — pkill -f DashboardApp kills ALL host instances; use lsof -iTCP:port
- `feedback_worktree_hygiene_x_monitoring.md` — place x-monitoring worktrees at repo/worktrees/name/, symlink .venv + db
- `feedback_repeat_back_scope_before_acting.md` — when directive is ambiguous on scope, repeat keep/revert list back before acting
- `feedback_scoped_revert_specificity.md` — user revert X = ONLY X, read literal scope, not inferred
- `feedback_plan_filename_matches_repo.md` — plan filenames follow repo docs/plans/ convention, not skill generic guidance
- `feedback_port_module_checklist.md` — port plans need PORT/EXCLUDE/DEFER table per legacy file in scope
- `feedback_remote_path_shape_not_sshfs.md` — /Users/fuchitalee/... is LOCAL; no sshfs; use SSH to reach remote
- `feedback_reattribute_with_llm_required.md` — x-monitor v1.8 reattribute defaults anthropic_client=None; must pass explicitly
- `feedback_xmonitor_cron_v17_list_gate.md` — x-monitor v1.7 RunPipeline raises ValueError unless x_monitor_list_id set
- `feedback_xmonitor_fk_hot_path_2026-06-20.md` — x-monitor hot path IntegrityError FK; fix via OR IGNORE / SELECT-then-INSERT
- `feedback_fuchitalee_pytest_tmpdir_cleaned.md` — macOS cleans TMPDIR mid-run; use --basetemp=$HOME/...
- `minimax_marketing_harness_layout.md` — .harness/ at minimax-marketing root is local-only, no git; do not commit
- `feedback_no_oversell.md` — test must exercise the differentiator; do not claim stacks-can-match wins
- `feedback_artifact_arbiter.md` — for AI demos, artifact is final arbiter; skip pre-validation gates
- `feedback_regression_net_in_every_plan.md` — every plan that modifies existing behavior must include a regression-net unit
- `project_x_monitor_feed_2026-07-16.md` — [x-monitor] column-alias + wire-shape bugs caused 7-row feed; 2-commit fix
- `project_x_monitor_feed_pretty_2026-07-16.md` — [x-monitor] 5-feed UX fixes (relative dates, hyperlinks, grouped classifications)
- `project_x_monitor_filter_wiring_2026-07-16.md` — [x-monitor] full filter wiring 6 commits, control-panel across 7 filter groups
- `project_x_monitor_filter_collapse_2026-07-17.md` — [x-monitor] uncheck any box blanked chart; collapse-to-all sentinel + playwright harness
- `project_x_monitor_role_other_2026-07-17.md` — [x-monitor] synthetic other bucket for account.role; 4th checkbox
- `project_x_monitor_window_1min_bucketing_2026-07-17.md` — [x-monitor] 1d window = 1440 minute buckets; granularity field + tick formatter
- `project_x_monitoring_2026-06-07.md` — [x-monitor] curated query library + community graph for 9 Chinese AI models
- `project_x_monitoring_2026-06-16.md` — [x-monitor] v1.6 OR-collapsed queries + 15-min cron + staleness (complete)
- `project_x_monitoring_2026-06-17.md` — [x-monitor] v1.7 design 2-call wide-net + LLM translation (planned)
- `project_x_monitoring_cloudflare_block_2026-06-18.md` — [x-monitor] list-add blocked by Cloudflare interstitial preflight + create_all
- `project_x_monitoring_combined_chart_2026-06-19.md` — [x-monitor] Combined chart page shipped 3rd topbar tab, multi-brand lines, 6-signal toggle
- `project_x_monitoring_list_management_2026-06-17.md` — [x-monitor] v1.7 list-management script built; BLOCKED on expired OAuth tokens
- `project_x_monitoring_treemap_2026-06-17.md` — [x-monitor] Finviz-style treemap on /, 11 enabled models, 9-card grid preserved
- `project_x_monitoring_v17_2026-06-17.md` — [x-monitor] v1.7 shipped 2-call wide-net + LLM translation + locale switcher
- `project_x_monitoring_v18_2026-06-19.md` — [x-monitor] v1.8 design notes (pre-impl)
- `project_xmonitor_i18n_2026-06-23.md` — [x-monitor] i18n plan in flight; migration 006 shipped, 007 WIP
- `project_xmonitor_quote_tweets_2026-06-22.md` — [x-monitor] quote-tweet capture + RT-fold (Units 1-6) SHIPPED on feat/capture-quote-tweets
- `project_xmonitor_reattribute_blocker_2026-06-21.md` — [x-monitor] real root cause of _unattributed: run.py only ran attribute_to_brands in one branch
- `project_xmonitor_schema_modernization_2026-06-26.md` — [x-monitor] migrations 020+022 landed; signals+signal_labels GONE; 155/155 tests pass
- `project_xmonitor_v18_unit2_rename_2026-06-19.md` — [x-monitor] v1.8 U2 rename notes (pre-impl)
