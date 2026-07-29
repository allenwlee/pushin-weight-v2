#!/usr/bin/env bash
# Shadow-restore: load a pg_dump custom-format file into a non-serving
# shadow database/schema WITHOUT touching live public. Verifies md5 +
# pg_restore TOC, then verifies post-restore pins (post row count).
#
# Run from Render shell on a service that can reach the internal DB
# hostname (NOT as a web build.sh). Credentials come from env vars.
#
# Required env:
#   SHADOW_DATABASE_URL   postgresql://user:pwd@host:port/dbname?...
#   DUMP_PATH             /path/to/pushinweight-YYYYMMDD-HHMMSS.dump
#   EXPECTED_MD5          md5 of DUMP_PATH (from docs/solutions/...)
# Optional env:
#   POSTS_TABLE           default "posts"
#   EXPECTED_POSTS_COUNT  default 28822 (plan pin)
#   PGSSLMODE             default "disable" (Render internal network)
#
# Usage:
#   SHADOW_DATABASE_URL=... DUMP_PATH=/tmp/dump.bin EXPECTED_MD5=... \
#     ./scripts/ops/shadow_restore.sh

set -euo pipefail

: "${SHADOW_DATABASE_URL:?must be set}"
: "${DUMP_PATH:?must be set}"
: "${EXPECTED_MD5:?must be set}"

POSTS_TABLE="${POSTS_TABLE:-posts}"
EXPECTED_POSTS_COUNT="${EXPECTED_POSTS_COUNT:-28822}"
PGSSLMODE="${PGSSLMODE:-disable}"

log() { printf '==> %s\n' "$*"; }

# 1. md5 verify
log "Verifying dump md5"
ACTUAL_MD5=$(md5sum "$DUMP_PATH" | awk '{print $1}')
if [ "$ACTUAL_MD5" != "$EXPECTED_MD5" ]; then
  echo "MD5 MISMATCH: expected $EXPECTED_MD5 got $ACTUAL_MD5" >&2
  exit 1
fi
log "md5 OK ($ACTUAL_MD5)"

# 2. TOC sanity
log "pg_restore --list (tail)"
pg_restore -l "$DUMP_PATH" | tail -5

# 3. Preflight: shadow db reachable, posts table does not exist yet
log "Preflight: psql smoke"
psql "$SHADOW_DATABASE_URL" -tAc "SELECT version();" | head -1
log "Preflight: posts table check"
POSTS_EXISTS=$(psql "$SHADOW_DATABASE_URL" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='$POSTS_TABLE';")
if [ "$POSTS_EXISTS" != "0" ]; then
  echo "posts table already exists in shadow ($POSTS_EXISTS rows). Aborting to avoid clobber." >&2
  exit 1
fi

# 4. Restore into shadow
log "Running pg_restore --no-owner --no-privileges --jobs=1 (no --clean)"
pg_restore \
  --no-owner --no-privileges --jobs=1 \
  -d "$SHADOW_DATABASE_URL" \
  "$DUMP_PATH" 2>&1 | tail -20
RC=${PIPESTATUS[0]}
log "pg_restore exit: $RC"
if [ "$RC" -ne 0 ]; then
  echo "pg_restore FAILED -- shadow is partial. Do not cut over." >&2
  exit "$RC"
fi

# 5. Verify post-restore pins
log "Verifying row count on $POSTS_TABLE"
ACTUAL_COUNT=$(psql "$SHADOW_DATABASE_URL" -tAc "SELECT count(*) FROM $POSTS_TABLE;")
log "Shadow posts count: $ACTUAL_COUNT"
if [ "$ACTUAL_COUNT" != "$EXPECTED_POSTS_COUNT" ]; then
  echo "POSTS COUNT MISMATCH: expected $EXPECTED_POSTS_COUNT got $ACTUAL_COUNT" >&2
  exit 1
fi

log "Shadow restore complete + verified. Safe to proceed with U3 (migrations on shadow) and U4 (cutover)."