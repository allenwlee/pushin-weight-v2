#!/bin/zsh
# {{AGENT_ATTRIBUTION}}
# Run the x-monitor pipeline; on non-zero exit, pop a macOS notification.
#
# Called by the StartCalendarInterval LaunchAgent at :00/:15/:30/:45.
# The pipeline_lock inside x_monitor.run prevents overlap if a previous
# cycle is still running. Failures (auth error, 5xx, crashed process)
# trigger a native macOS notification via osascript.
#
# On a successful run, also surface high signal-drop rates (LLM
# hallucinations / brand drift) so the operator can catch silent LLM
# degradation that would otherwise only show up as empty dashboard cards.
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
else
  # Surface signal-drop rate on success. Count "dropping signal" warning
  # lines (emitted by store.insert_posts when the LLM returns a brand_id
  # not in the brands table). A high count means LLM drift / brand drift.
  N_DROPS=$(grep -c "dropping signal for" "$LOG" 2>/dev/null || echo 0)
  if [[ "$N_DROPS" -gt 20 ]]; then
    osascript -e "display notification \"Exit 0 — $N_DROPS signals dropped (LLM/brand drift?)\" with title \"x-monitor high signal-drop\" subtitle \"scheduled run\"" 2>/dev/null || true
  fi
fi
exit $RC
