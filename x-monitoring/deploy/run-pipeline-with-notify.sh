#!/bin/zsh
# {{AGENT_ATTRIBUTION}}
# Run the x-monitor pipeline; on non-zero exit, pop a macOS notification.
#
# Called by the StartCalendarInterval LaunchAgent at :00/:15/:30/:45.
# The pipeline_lock inside x_monitor.run prevents overlap if a previous
# cycle is still running. Failures (auth error, 5xx, crashed process)
# trigger a native macOS notification via osascript.
set -uo pipefail

cd /Users/fuchitalee/development/minimax-marketing/x-monitoring
source ~/.env.secrets

LOG=/tmp/x-monitor-pipeline.log
.venv/bin/python -m x_monitor run > "$LOG" 2>&1
RC=$?

if [[ $RC -ne 0 ]]; then
  # Pull the last 3 lines for the notification body, truncated to 200 chars.
  TAIL=$(tail -3 "$LOG" | tr '\n' ' ' | head -c 200)
  osascript -e "display notification \"Exit $RC — $TAIL\" with title \"x-monitor pipeline failed\" subtitle \"scheduled run\"" 2>/dev/null || true
fi
exit $RC
