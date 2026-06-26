#!/usr/bin/env bash
# {{AGENT_ATTRIBUTION}}
# Regenerate docs/reference/images/xmonitor-schema-post-batch.png from
# docs/reference/schema.dot.
#
# Usage:
#   scripts/build_schema_image.sh          # rebuild the image
#   scripts/build_schema_image.sh --check  # exit 1 if image is stale (for CI)
#
# Requires: brew install graphviz (provides the `dot` binary).
#
# The .dot source is the single source of truth for the schema image.
# Edit the .dot, then run this script, then commit the regenerated PNG
# alongside the .dot so a future --check has a clean baseline.

set -euo pipefail

# Resolve repo root (script lives at <root>/scripts/, dot lives at <root>/docs/reference/)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOT="$ROOT/docs/reference/schema.dot"
IMG="$ROOT/docs/reference/images/xmonitor-schema-post-batch.png"

if ! command -v dot >/dev/null 2>&1; then
  echo "error: 'dot' not found. Install with: brew install graphviz" >&2
  exit 2
fi

if [[ ! -f "$DOT" ]]; then
  echo "error: $DOT not found" >&2
  exit 2
fi

if [[ "${1:-}" == "--check" ]]; then
  # If schema.dot has unstaged or staged-but-not-committed changes, the
  # image is by definition stale — the committed PNG was rendered from
  # an older .dot.
  if ! git -C "$ROOT" diff --quiet HEAD -- docs/reference/schema.dot 2>/dev/null; then
    echo "schema image is stale: schema.dot has uncommitted changes" >&2
    exit 1
  fi
  # Commit hash that last touched each file. If both touched in the same
  # commit, the image is fresh; otherwise the .dot has drifted ahead and
  # the image needs to be regenerated.
  DOT_HASH="$(git -C "$ROOT" log -1 --format=%H -- docs/reference/schema.dot 2>/dev/null || echo none)"
  IMG_HASH="$(git -C "$ROOT" log -1 --format=%H -- docs/reference/images/xmonitor-schema-post-batch.png 2>/dev/null || echo none)"
  if [[ "$DOT_HASH" != "none" && "$DOT_HASH" == "$IMG_HASH" ]]; then
    echo "schema image is fresh (dot and png both at $DOT_HASH)"
    exit 0
  fi
  echo "schema image is stale: schema.dot at $DOT_HASH, image at $IMG_HASH" >&2
  exit 1
fi

mkdir -p "$(dirname "$IMG")"
dot -Tpng "$DOT" > "$IMG"
echo "wrote $IMG"
