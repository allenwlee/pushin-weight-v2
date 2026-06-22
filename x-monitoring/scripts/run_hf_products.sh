#!/usr/bin/env bash
# {{AGENT_ATTRIBUTION}}
# Collect HuggingFace models per brand into the products table.
#
# Sources HF_TOKEN from ~/.env.secrets (if present) so the crawler runs
# authenticated (higher rate limits + access to gated repos you control).
# Anonymous (no token) still collects public models.
#
# Usage:
#   scripts/run_hf_products.sh                          # all enabled brands
#   scripts/run_hf_products.sh --companies deepseek,glm
#   scripts/run_hf_products.sh --brand deepseek --dry-run
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$HOME/.env.secrets" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "$HOME/.env.secrets"
  set -u
fi

cd "$PROJECT_DIR"
exec .venv/bin/python -m x_monitor hf-products "$@"
