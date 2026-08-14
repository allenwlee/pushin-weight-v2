#!/usr/bin/env bash
# https://render.com/docs/deploy-django
#
# The migrate step below runs inside a single Python process that
# holds a Postgres session-scoped advisory lock for its lifetime.
# This serializes concurrent build instances (Render auto-scales the
# starter plan and runs build.sh per instance) so they cannot
# deadlock on row-level locks during long-running migrations like
# 0003 (the posts.raw backfill, which scans every row of the posts
# table and would otherwise race with itself across instances, or
# with the harvest cron).
#
# Why a single process: the advisory lock is per-session in Postgres,
# and Django opens its DB connection inside the same Python process
# that runs migrate. By acquiring pg_advisory_lock via Django's
# connection before invoking migrate, every subsequent query from
# migrate holds the same lock. Other build instances block on
# pg_advisory_lock until this one exits.
#
# Lock id 8675309 is arbitrary; pick a stable unique number per app.
set -o errexit

pip install -e ".[dev]"

# Compile i18n message files for zh_CN. Render's Python image is
# Debian-slim which does not include gettext by default.
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq gettext
fi
python manage.py compilemessages

python manage.py collectstatic --no-input --clear

# Acquire the migration advisory lock on the same connection that
# Django will use, then run migrate. The lock is automatically
# released when this Python process exits (Postgres session close).
DJANGO_SETTINGS_MODULE=project.settings python -c "
import django
django.setup()
from django.conf import settings
from django.db import connection
from project.staging import should_run_build_migrations

marker_status = None
if settings.OLLIJA_STAGING_MODE:
    with connection.cursor() as cur:
        cur.execute('SELECT to_regclass($$public.ollija_environment_marker$$)')
        if cur.fetchone()[0] is not None:
            cur.execute(
                'SELECT status FROM public.ollija_environment_marker '
                'WHERE singleton = TRUE'
            )
            row = cur.fetchone()
            marker_status = row[0] if row else None
if not should_run_build_migrations(
    staging_enabled=settings.OLLIJA_STAGING_MODE,
    marker_status=marker_status,
):
    print(
        'Skipped migrations until the Ollija staging database is active',
        flush=True,
    )
    raise SystemExit(0)

with connection.cursor() as cur:
    cur.execute('SELECT pg_advisory_lock(8675309)')
print('Acquired migration advisory lock 8675309', flush=True)

# Run migrate in-process via Django's management command. The
# existing DB connection (with the lock) is reused.
from django.core.management import execute_from_command_line
execute_from_command_line(['manage.py', 'migrate', '--noinput'])

# Lock is released automatically when this process exits, but be
# explicit anyway in case Django ever moves to a connection pool.
with connection.cursor() as cur:
    cur.execute('SELECT pg_advisory_unlock(8675309)')
print('Released migration advisory lock', flush=True)
"
