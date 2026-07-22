# Agent Rules (this repo)

Rules for AI agents (and humans) working in this repo. Honor these unless
explicitly told otherwise.

## file names
'YYYY-MM-DD-HHMMSS-description' should overrule compound-engineering file naming rules

## Two-stack deployment (v1 + v2)

This repo contains two stacks running side-by-side during the Django
migration. See README.md for the full architecture diagram.

- **v1 (legacy Flask):** live production, must NOT be touched.
  - Harvest: 2 macOS launchd agents (`com.fuchitalee.x-monitor.harvest`,
    `com.fuchitalee.x-monitor.config-reload`).
  - DB: SQLite at `data/x_monitoring.db`.
  - Web: Flask on port 5000 (local-only).
- **v2 (Django/Render):** the target stack, in active development.
  - Harvest: Celery beat + worker on Render.
  - DB: Managed PostgreSQL on Render.
  - Web: Django + gunicorn + WhiteNoise on Render, Google OAuth.
  - Models: `core/models.py` is the source of truth for DB schema.
  - Migrations: `core/migrations/` (auto-generated from models).

**During migration: never stop, unload, or edit the v1 launchd agents.**
The parallel-running protocol is documented in `docs/production-runbook.md`.

## Schema (v2 — Django ORM)

After cutover, Django ORM migrations in `core/migrations/` are the
single source of truth for the DB schema. To generate a migration
after editing `core/models.py`:

```bash
python manage.py makemigrations core
python manage.py migrate
```

**Before cutover:** the legacy Graphviz schema image at
`docs/reference/images/xmonitor-schema-post-batch.png` (generated from
`docs/reference/schema.dot` via `scripts/build_schema_image.sh`) is
still valid for the v1 SQLite schema. After cutover, this image is
retired and replaced with a Django model diagram.

## Schema image regeneration (legacy v1 — still active)

The x-monitor schema image at
`docs/reference/images/xmonitor-schema-post-batch.png` is generated from
`docs/reference/schema.dot` via `scripts/build_schema_image.sh`.

**Trigger:** when any file in `x_monitor/migrations/*.sql`
changes, regenerate the image and co-commit it with the schema changes:

```bash
scripts/build_schema_image.sh
git add docs/reference/schema.dot docs/reference/images/xmonitor-schema-post-batch.png
git commit -m "docs(reference): regenerate schema image"
```

The `.dot` source is the single source of truth — edit the `.dot`, never
edit the PNG directly. The PNG must always be regenerated from the
committed `.dot` and committed in the same commit, so `scripts/build_schema_image.sh --check`
exits 0 on a clean tree.

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
