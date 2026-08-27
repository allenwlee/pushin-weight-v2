# Agent Rules (this repo)

Rules for AI agents (and humans) working in this repo. Honor these unless
explicitly told otherwise.

## UI fixes

Before changing a visible UI surface, browser interaction, mockup fidelity,
locale-visible copy, or visual regression, read and follow
`.claude/skills/fix-ui/SKILL.md`. This applies to every agent working in this
repository, including Claude Code and Codex.

## Harvester changes

Before changing harvest/cycle behavior (CycleRunner, `run_cycle`, backfill,
harvest policy, A/B/C TwitterAPI calls, cursors, metrics refresh, translator
or classifier post-fetch, Render harvest cron, credit burn, or
fetch-vs-insert anomalies), read and follow
`.claude/skills/change-harvester/SKILL.md` **and**
`.claude/skills/avoiding-recurring-mistakes/SKILL.md` (especially M7, M8,
M12, M17, M18). This applies to every agent working in this repository,
including Claude Code and Codex.

## Plans and delivery

Before selecting or creating a PushinWeight plan, run
`./bin/ollija annotate-plan`. Use the exact `plan_path` it returns and enrich
that same plan; do not create a parallel plan. After the final plan write or
document review, rerun `./bin/ollija annotate-plan <plan-path>`.

For LFG and goal, ask the owner once before implementation whether to stop
after staging or continue through production. Persist that explicit choice in
the plan's Ollija metadata (`delivery_target: staging|production` and
`delivery_selected_by_user: true`) and annotate the same plan. Ordinary plans
remain `delivery_target: on-request` and ask nothing.

Before any Git or deployment mutation, the parent workflow must read the
selected delivery target, generated Ollija Delivery Guide, and editable
`Delivery Exceptions`, then run `./bin/ollija annotate-plan <plan-path>
--check`. Resolve conflicts instead of silently bypassing the guide. Ollija is
guidance only: it does not approve, commit, push, deploy, move worktrees, or
run a persistent release process. Read `.claude/skills/ollija/SKILL.md` for the
same portable contract.

After exact-SHA production verification, the generated guide directs the
parent workflow to run guarded `git worktree remove` cleanup only for the
canonical linked worktree. Require it to remain registered, clean, unlocked,
and at the verified candidate SHA; run from the authoritative root without
`--force` and preserve feature branches. Make removal the final filesystem
action. Retain staging-only, failed, unauthorized, dirty, locked,
noncanonical, or candidate-mismatched worktrees. Ollija provides guidance and
does not remove the worktree itself.

## file names
'YYYY-MM-DD-HHMMSS-description' should overrule compound-engineering file naming rules

## Single-stack deployment (v2 Django on Render)

As of 2026-07-27 the v1 Flask + launchd + SQLite stack is **retired**.
There is one production stack: v2.

- **Web:** Django + gunicorn + WhiteNoise on Render, behind Google OAuth
  (URL: `https://pushinweight-web.onrender.com`).
- **Harvest:** One Render cron runs `python manage.py run_cycle` every 15
  minutes. Celery beat is not a production scheduler.
- **Headline worker:** A dedicated queue-only Celery worker and owned broker
  are additive candidate resources; they never run harvesting or beat.
- **DB:** Managed PostgreSQL on Render (service-scoped `DATABASE_URL`). The v1 SQLite file at
  `data/x_monitoring.db` is read-only historical state; do not write to
  it.
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

- **Harvest cost (TwitterAPI credits):** `scripts/harvest_cost/` — run `python -m scripts.harvest_cost` when pricing harvest spend, investigating credit burn, or producing a periodic cost report over recent cycles (search + one-shot metrics). See `scripts/harvest_cost/README.md`.

## Render deploy

Deployment candidates are described by `render.yaml`; applying a Blueprint is
an explicit release action. The current topology is:

- `pushinweight-web` (gunicorn + Django)
- `pushinweight-harvest` (the only scheduler, a 15-minute Render cron)
- managed PostgreSQL
- suspended legacy worker and beat services that must not be reactivated

The V22 headline candidate adds only `pushinweight-headlines` (a queue-isolated
worker) and `pushinweight-headlines-broker`; it does not add beat.

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

## ollija host authority

`fuchitalee` is the sole authoritative host for this repository and ollija's
runtime state. Do not create a checkout, worktree, cache, backup, receipt, or
other PushinWeight/ollija artifact on `allenwlee`; it is only a keyboard and
browser endpoint. Follow the authority-transfer procedure in
`docs/operations/ollija-rollout-baseline.md` before treating any replacement
host as writable.

## allenwlee GUI automation

`allenwlee` has macOS Accessibility permission for Apple's incoming SSH
wrapper (shown by macOS as `sshd-keygen-wrapper` or a shortened `sshkeygen`
label). Authenticated SSH sessions can therefore use `osascript` and System
Events to inspect or control its visible GUI. This does not change repository
authority or grant new filesystem/SSH-key access. Use it only for an explicit
owner-requested keyboard/browser action, identify the intended app/window
before sending input, and read
`docs/operations/2026-08-27-073626-allenwlee-ssh-gui-automation.md` first.

## Memory

Topic files live under `~/.claude/projects/-Users-allenwlee/memory/` and are loaded on demand. Each entry below has a corresponding detail file with the full context.

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
