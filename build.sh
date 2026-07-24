#!/usr/bin/env bash
# Build script for Render — pushinweight.ai
# https://render.com/docs/deploy-django
set -o errexit

pip install -e ".[dev]"

python manage.py compilemessages 2>/dev/null || true

python manage.py collectstatic --no-input

python manage.py migrate
