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
python scripts/verify_headline_worker_boundary.py

# Compile i18n message files for zh_CN. Render's Python image is
# Debian-slim which does not include gettext by default.
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq gettext
fi
python manage.py compilemessages

python manage.py collectstatic --no-input --clear

# Acquire the migration advisory lock on the same connection that Django uses.
# Every environment, including a fresh isolated staging database, migrates
# during its build.
DJANGO_SETTINGS_MODULE=project.settings python scripts/render_migrate.py
