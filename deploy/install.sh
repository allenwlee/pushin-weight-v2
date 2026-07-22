#!/bin/zsh
# {{AGENT_ATTRIBUTION}}
# Install / reload the x-monitor config-reload LaunchAgent on fuchitalee.
# This is the event-driven agent (WatchPaths on config.yaml). Pair with
# install-scheduled.sh for the 15-min cadence (.harvest).
set -euo pipefail

PLIST_SRC="$(dirname "$0")/com.fuchitalee.x-monitor.config-reload.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.fuchitalee.x-monitor.config-reload.plist"
LOG_DIR="$HOME/Library/Logs/x-monitor"
mkdir -p "$LOG_DIR"

if [[ ! -f "$PLIST_SRC" ]]; then
  echo "error: $PLIST_SRC not found" >&2
  exit 1
fi

cp "$PLIST_SRC" "$PLIST_DST"

# Unload if already loaded (idempotent reload)
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "installed: $PLIST_DST"
echo "loaded:    $(launchctl list | grep com.fuchitalee.x-monitor.config-reload || echo 'no — check with launchctl list')"
echo "logs:      $LOG_DIR/stdout.log, $LOG_DIR/stderr.log"
echo
echo "manual run: launchctl kickstart -k gui/\$(id -u)/com.fuchitalee.x-monitor.config-reload"
echo "uninstall:  $0 --uninstall"
