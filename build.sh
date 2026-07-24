#!/usr/bin/env bash
# Build script for Render — pushinweight.ai
# https://render.com/docs/deploy-django
set -o errexit

pip install -e ".[dev]"

python manage.py collectstatic --no-input

python manage.py migrate
