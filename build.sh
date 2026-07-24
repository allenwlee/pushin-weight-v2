#!/usr/bin/env bash
# https://render.com/docs/deploy-django
set -o errexit

pip install -e ".[dev]"

python manage.py compilemessages

python manage.py collectstatic --no-input

python manage.py migrate
