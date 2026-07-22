#!/usr/bin/env bash
# x-monitor v2 — Render build script
# Runs on every deploy. Must be idempotent.
set -euo pipefail

echo "=== Installing Python dependencies ==="
pip install -e ".[dev]"

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

echo "=== Applying database migrations ==="
python manage.py migrate --noinput

echo "=== Build complete ==="
