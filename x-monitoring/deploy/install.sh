#!/bin/zsh
# {{AGENT_ATTRIBUTION}}
# Install / reload the x-monitor LaunchAgent on fuchitalee.
set -euo pipefail

PLIST_SRC="$(dirname "$0")/com.fuchitalee.x-monitor.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.fuchitalee.x-monitor.plist"
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
echo "loaded:    $(launchctl list | grep com.fuchitalee.x-monitor || echo 'no — check with launchctl list')"
echo "logs:      $LOG_DIR/"
echo
echo "manual run: launchctl kickstart -k gui/\$(id -u)/com.fuchitalee.x-monitor"
echo "uninstall:  $0 --uninstall"
