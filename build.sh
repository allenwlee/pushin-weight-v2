#!/usr/bin/env bash
# Build script for Render — pushinweight.ai
# https://render.com/docs/deploy-django
set -o errexit

pip install -e ".[dev]"

# compilemessages requires gettext; skip gracefully if unavailable
if command -v msgfmt &>/dev/null; then
    python manage.py compilemessages
else
    echo "Skipping compilemessages: gettext not installed"
fi
python manage.py collectstatic --no-input

python manage.py migrate
