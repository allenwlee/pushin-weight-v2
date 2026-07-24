#!/usr/bin/env bash
# https://render.com/docs/deploy-django
set -o errexit

pip install -e ".[dev]"

# Compile i18n message files for zh_CN. Render's Python image is
# Debian-slim which does not include gettext by default.
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq gettext
fi
python manage.py compilemessages

python manage.py collectstatic --no-input

python manage.py migrate
